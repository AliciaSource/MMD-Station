from dataclasses import dataclass, field
import math
from pathlib import Path
import struct
import tempfile

import bpy
from bpy.app.handlers import persistent

from .coordinates import (
    blender_pose_matrix,
    blender_position_to_mmd,
    blender_rotation_to_mmd_rows,
    mmd_position_to_blender,
)
from .ffi import NativeBoneSolver
from .runtime import (
    MMDIKRuntimeError,
    canonical_armature,
    refresh_bindings,
    runtime_state,
    set_action_input,
)
from .vmd_hook import SOURCE_FRAME_KEY, SOURCE_VMD_KEY


_SESSIONS = {}


def _resolve_live_source_path(root):
    source_path = Path(str(root.get("spx_mmd_ik_source_pmx", "")))
    if source_path.is_file():
        return source_path
    import_folder = Path(str(root.get("import_folder", "")))
    candidates = tuple(import_folder.glob("*.pmx")) if import_folder.is_dir() else ()
    if len(candidates) == 1:
        root["spx_mmd_ik_source_pmx"] = str(candidates[0])
        return candidates[0]
    return source_path


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _qmul(left, right):
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    value = (
        _f32(_f32(_f32(lw * rx) + _f32(lx * rw)) + _f32(ly * rz) - _f32(lz * ry)),
        _f32(_f32(_f32(lw * ry) - _f32(lx * rz)) + _f32(ly * rw) + _f32(lz * rx)),
        _f32(_f32(_f32(lw * rz) + _f32(lx * ry)) - _f32(ly * rx) + _f32(lz * rw)),
        _f32(_f32(_f32(lw * rw) - _f32(lx * rx)) - _f32(ly * ry) - _f32(lz * rz)),
    )
    length = _f32(math.sqrt(_f32(sum(_f32(item * item) for item in value))))
    return tuple(_f32(item / length) for item in value)


def _mmd_transform(value):
    return (
        float(value.position.x),
        float(value.position.z),
        float(value.position.y),
        -float(value.rotation.x),
        -float(value.rotation.z),
        -float(value.rotation.y),
        float(value.rotation.w),
    )


def _pose_bone_name(pose_bone):
    mmd = getattr(pose_bone, "mmd_bone", None)
    for value in (
        getattr(mmd, "name_j", "") if mmd else "",
        getattr(mmd, "name_e", "") if mmd else "",
        pose_bone.name,
    ):
        if value:
            yield value


def _transform_modal_active():
    window = getattr(bpy.context, "window", None)
    operators = getattr(window, "modal_operators", ()) if window else ()
    return any(
        str(getattr(operator, "bl_idname", "")).startswith("TRANSFORM_OT_")
        for operator in operators
    )


def _transform_modal_pose_matrices(armature):
    if not _transform_modal_active():
        return {}
    active = getattr(bpy.context, "object", None)
    if active is not armature or getattr(active, "mode", "") != "POSE":
        return {}
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
        if pose_bone.bone.select
    }


def _bone_map(armature, solver):
    exact = {pose_bone.name: pose_bone for pose_bone in armature.pose.bones}
    aliases = {}
    for pose_bone in armature.pose.bones:
        for name in _pose_bone_name(pose_bone):
            aliases.setdefault(name, pose_bone)
    return tuple(exact.get(name) or aliases.get(name) for name in solver.names)


def _infer_scale(mapping, solver):
    numerator = 0.0
    denominator = 0.0
    for index, pose_bone in enumerate(mapping):
        if pose_bone is None:
            continue
        source = mmd_position_to_blender(solver.rest_positions[index], 1.0)
        target = pose_bone.bone.head_local
        numerator += source[0] * target.x + source[1] * target.y + source[2] * target.z
        denominator += source[0] ** 2 + source[1] ** 2 + source[2] ** 2
    if denominator <= 1.0e-12:
        raise MMDIKRuntimeError("无法从 PMX 与 Runtime Armature 推导导入缩放")
    scale = numerator / denominator
    if not 1.0e-6 < scale < 1000.0:
        raise MMDIKRuntimeError(f"PMX/Blender 坐标缩放异常：{scale:g}")
    return scale


def _is_generated_constraint(constraint, runtime):
    name = constraint.name.lower()
    if name.startswith("mmd_"):
        return True
    return constraint.type == "IK" and getattr(constraint, "target", None) == runtime


def _mute_generated_constraints(runtime):
    muted = []
    for pose_bone in runtime.pose.bones:
        for constraint in pose_bone.constraints:
            if not _is_generated_constraint(constraint, runtime):
                continue
            muted.append((pose_bone.name, constraint.name, bool(constraint.mute)))
            constraint.mute = True
    return muted


def _restore_constraints(runtime, muted):
    for bone_name, constraint_name, previous in muted:
        pose_bone = runtime.pose.bones.get(bone_name)
        constraint = pose_bone.constraints.get(constraint_name) if pose_bone else None
        if constraint is not None:
            constraint.mute = previous


def _mute_all_constraints(armature):
    muted = []
    for pose_bone in armature.pose.bones:
        for constraint in pose_bone.constraints:
            muted.append((pose_bone.name, constraint.name, bool(constraint.mute)))
            constraint.mute = True
    return muted


def _raw_pose_matrices(armature, bases=None):
    matrices = {}

    def resolve(pose_bone):
        cached = matrices.get(pose_bone.name)
        if cached is not None:
            return cached
        rest = pose_bone.bone.matrix_local
        basis = bases.get(pose_bone.name, pose_bone.matrix_basis).copy() if bases else pose_bone.matrix_basis.copy()
        if pose_bone.parent is None:
            matrix = rest @ basis
        else:
            parent_matrix = resolve(pose_bone.parent)
            matrix = (
                parent_matrix
                @ pose_bone.parent.bone.matrix_local.inverted_safe()
                @ rest
                @ basis
            )
        matrices[pose_bone.name] = matrix
        return matrix

    for pose_bone in armature.pose.bones:
        resolve(pose_bone)
    return matrices


def _submit_live_pose(session, canonical):
    matrices = _raw_pose_matrices(canonical, session.input_basis)
    session.solver.begin_live_input()
    for index, runtime_bone in enumerate(session.mapping):
        if runtime_bone is None:
            continue
        source_bone = canonical.pose.bones.get(runtime_bone.name)
        if source_bone is None:
            continue
        pose_matrix = matrices[source_bone.name]
        rest_orientation = source_bone.bone.matrix_local.to_3x3().to_4x4()
        head_transform = pose_matrix @ rest_orientation.inverted_safe()
        session.solver.set_live_matrix(
            index,
            blender_position_to_mmd(head_transform.translation, session.scale),
            blender_rotation_to_mmd_rows(head_transform.to_3x3()),
        )


def _live_input_signature(canonical, scene):
    values = [int(scene.frame_current), float(scene.frame_subframe)]
    for pose_bone in canonical.pose.bones:
        values.extend(float(value) for row in pose_bone.matrix_basis for value in row)
    return tuple(values)


def _matrix_near_identity(matrix, tolerance=1.0e-6):
    return max(
        abs(matrix[row][column] - (1.0 if row == column else 0.0))
        for row in range(4)
        for column in range(4)
    ) < tolerance


def _cleared_pose_snapshot(canonical, output_basis):
    changed = []
    identity_count = 0
    for name, output in output_basis.items():
        pose_bone = canonical.pose.bones.get(name)
        if pose_bone is None or pose_bone.matrix_basis == output:
            continue
        changed.append(name)
        if _matrix_near_identity(pose_bone.matrix_basis):
            identity_count += 1
    required = max(2, math.ceil(len(output_basis) * 0.2))
    if len(changed) < required or identity_count < math.ceil(len(changed) * 0.9):
        return None
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in canonical.pose.bones
    }


def _action_frame_signature(canonical, frame):
    action = canonical.animation_data.action if canonical.animation_data else None
    if action is None:
        return ()
    values = []
    for curve in action.fcurves:
        if not curve.data_path.startswith('pose.bones["'):
            continue
        for point in curve.keyframe_points:
            if abs(float(point.co.x) - float(frame)) < 1.0e-6:
                values.append(
                    (curve.data_path, int(curve.array_index), float(point.co.y))
                )
                break
    return tuple(values)


def _basis_channel_values(pose_bone, basis, channel):
    location, rotation, scale = basis.decompose()
    if channel == "location":
        return tuple(location)
    if channel == "scale":
        return tuple(scale)
    if channel == "rotation_quaternion":
        return tuple(rotation)
    if channel == "rotation_euler":
        return tuple(rotation.to_euler(pose_bone.rotation_mode, pose_bone.rotation_euler))
    if channel == "rotation_axis_angle":
        axis, angle = rotation.to_axis_angle()
        return (angle, axis.x, axis.y, axis.z)
    return None


def _export_current_pmx(root, vmd_path=None):
    selected = tuple(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    mode = active.mode if active is not None else "OBJECT"
    if active is not None and mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        root.hide_set(False)
        root.select_set(True)
        bpy.context.view_layer.objects.active = root
        with tempfile.TemporaryDirectory(prefix="mmd-native-live-") as directory:
            path = Path(directory) / "current_model.pmx"
            result = bpy.ops.mmd_tools.export_pmx(
                filepath=str(path),
                scale=12.5,
                copy_textures_mode="NONE",
                fix_bone_order=False,
                sort_materials=False,
                sort_vertices="NONE",
            )
            if result != {"FINISHED"} or not path.is_file():
                raise MMDIKRuntimeError("无法自动生成 native 求值所需的 PMX 定义")
            return NativeBoneSolver(path, vmd_path)
    finally:
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in selected:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        if active is not None and active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = active
            if mode != "OBJECT":
                bpy.ops.object.mode_set(mode=mode)


@dataclass
class Session:
    root_name: str
    runtime_name: str
    pmx_path: str
    vmd_path: str
    blender_start: int
    vmd_start: int
    solver: NativeBoneSolver
    mapping: tuple
    scale: float
    muted_constraints: list
    original_action: object
    last_vmd_frame: int | None = None
    bone_indices: dict = field(default_factory=dict)
    external_transforms: dict = field(default_factory=dict)
    physics_bind_positions: tuple = ()
    physics_rigid_indices: tuple = ()
    physics_feedback_complete: bool = False
    canonical_name: str = ""
    live: bool = False
    updating: bool = False
    input_signature: tuple = ()
    source_vmd: bool = False
    pose_override: bool = False
    input_basis: dict = field(default_factory=dict)
    output_basis: dict = field(default_factory=dict)
    suspended: bool = False
    action_input: bool = False
    action_signature: tuple = ()
    solver_matrices: dict = field(default_factory=dict)
    desired_pose: dict = field(default_factory=dict)

    def _capture_external_pose(self, canonical, scene):
        if not self.input_signature:
            return False
        current_frame = (int(scene.frame_current), float(scene.frame_subframe))
        if self.input_signature[:2] != current_frame:
            return False
        signature = _live_input_signature(canonical, scene)
        if signature == self.input_signature:
            return False
        cleared = _cleared_pose_snapshot(canonical, self.output_basis)
        if cleared is not None:
            self.input_basis = cleared
        else:
            for name, output in self.output_basis.items():
                pose_bone = canonical.pose.bones.get(name)
                source = self.input_basis.get(name)
                if pose_bone is None or source is None or pose_bone.matrix_basis == output:
                    continue
                delta = output.inverted_safe() @ pose_bone.matrix_basis
                self.input_basis[name] = source @ delta
        self.pose_override = True
        self.input_signature = signature
        return True

    def _apply_output(self, runtime, update=True):
        preserved = _transform_modal_pose_matrices(runtime)
        mapped = [(index, pose_bone) for index, pose_bone in enumerate(self.mapping) if pose_bone is not None]
        mapped.sort(key=lambda item: len(item[1].parent_recursive))
        desired = {}
        for index, pose_bone in mapped:
            values = self.solver.matrix(index)
            if self.solver_matrices.get(index) != values:
                self.solver_matrices[index] = values
                self.desired_pose[pose_bone.name] = blender_pose_matrix(
                    values,
                    self.scale,
                    pose_bone.bone.matrix_local,
                )
            desired[pose_bone.name] = self.desired_pose[pose_bone.name]
        changed = set()
        for index, pose_bone in mapped:
            parent = pose_bone.parent
            if parent is None:
                needs_write = pose_bone.matrix != desired[pose_bone.name]
            else:
                needs_write = (
                    parent.name in changed
                    or pose_bone.matrix != desired[pose_bone.name]
                )
            if not needs_write:
                continue
            if parent is None:
                basis = pose_bone.bone.convert_local_to_pose(
                    desired[pose_bone.name], pose_bone.bone.matrix_local, invert=True
                )
            else:
                basis = pose_bone.bone.convert_local_to_pose(
                    desired[pose_bone.name],
                    pose_bone.bone.matrix_local,
                    parent_matrix=desired.get(parent.name, parent.matrix),
                    parent_matrix_local=parent.bone.matrix_local,
                    invert=True,
                )
            if pose_bone.matrix_basis != basis:
                pose_bone.matrix_basis = basis
                changed.add(pose_bone.name)
        for name, matrix in sorted(
            preserved.items(),
            key=lambda item: len(runtime.pose.bones[item[0]].parent_recursive),
        ):
            pose_bone = runtime.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix
        runtime.update_tag(refresh={"OBJECT"})
        if update:
            bpy.context.view_layer.update()
        self.output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for _index, pose_bone in mapped
        }
        self.input_signature = _live_input_signature(runtime, bpy.context.scene)
        self.action_signature = _action_frame_signature(
            runtime, bpy.context.scene.frame_current
        )

    def sync_output_pose(self, canonical, scene):
        self.output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in canonical.pose.bones
            if pose_bone.name in self.bone_indices
        }
        self.input_signature = _live_input_signature(canonical, scene)
        self.action_signature = _action_frame_signature(
            canonical, scene.frame_current
        )

    def repair_current_action_keys(self, canonical, frame):
        action = canonical.animation_data.action if canonical.animation_data else None
        if action is None:
            self.action_signature = ()
            return False
        paths = {
            pose_bone.path_from_id(): pose_bone
            for pose_bone in canonical.pose.bones
        }
        changed = False
        for curve in action.fcurves:
            owner_path, separator, channel = curve.data_path.rpartition(".")
            pose_bone = paths.get(owner_path) if separator else None
            basis = self.input_basis.get(pose_bone.name) if pose_bone else None
            values = (
                _basis_channel_values(pose_bone, basis, channel)
                if basis is not None
                else None
            )
            if values is None or curve.array_index >= len(values):
                continue
            for point in curve.keyframe_points:
                if abs(float(point.co.x) - float(frame)) >= 1.0e-6:
                    continue
                expected = float(values[curve.array_index])
                if abs(float(point.co.y) - expected) > 1.0e-7:
                    point.co.y = expected
                    changed = True
                break
        if changed:
            action.update_tag()
        self.action_signature = _action_frame_signature(canonical, frame)
        return changed

    def restore_input(self, update=True):
        canonical = bpy.data.objects.get(self.canonical_name or self.runtime_name)
        if canonical is None:
            return
        was_updating = self.updating
        self.updating = True
        try:
            for name, matrix in self.input_basis.items():
                pose_bone = canonical.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix
            canonical.update_tag(refresh={"OBJECT"})
            if update:
                bpy.context.view_layer.update()
        finally:
            self.updating = was_updating

    def close(self):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is not None:
            if self.live:
                self.restore_input()
            _restore_constraints(runtime, self.muted_constraints)
            if runtime.animation_data is not None:
                runtime.animation_data.action = self.original_action
        self.solver.close()

    def target_frame(self, scene):
        return self.vmd_start + int(scene.frame_current) - self.blender_start

    def capture_physics_bindings(self, preview_session):
        from collections import defaultdict, deque

        from ..physics_preview.runtime import _mmd_physics_name, _read_pmx_physics

        self.physics_bind_positions = ()
        self.physics_rigid_indices = ()
        self.physics_feedback_complete = False
        if not Path(self.pmx_path).is_file():
            return False
        _model_name, source_rigids, _source_joints = _read_pmx_physics(
            self.pmx_path
        )
        source_indices = defaultdict(deque)
        for index, source in enumerate(source_rigids):
            source_indices[source[0]].append(index)
        self.physics_rigid_indices = tuple(
            source_indices[
                _mmd_physics_name(rigid, "mmd_rigid")
            ].popleft()
            if source_indices[_mmd_physics_name(rigid, "mmd_rigid")]
            else None
            for rigid in preview_session.rigids
        )
        self.physics_feedback_complete = (
            len(preview_session.rigids) == len(source_rigids) == self.solver.rigid_count
            and all(index is not None for index in self.physics_rigid_indices)
            and len(set(self.physics_rigid_indices)) == len(source_rigids)
        )
        dll = preview_session.solver.library.dll
        if not hasattr(dll, "mmd_solver_get_basis_transforms"):
            self.physics_bind_positions = ()
            return any(index is not None for index in self.physics_rigid_indices)
        transforms = preview_session.solver.basis_transforms()
        start = preview_session.body_offset
        local = transforms[start : start + len(preview_session.rigids)]
        self.physics_bind_positions = tuple(
            (float(item.position.x), float(item.position.y), float(item.position.z))
            for item in local
        )
        return any(index is not None for index in self.physics_rigid_indices)

    def corrected_rigid_position(self, rigid_index, target):
        if (
            rigid_index >= len(self.physics_bind_positions)
            or rigid_index >= len(self.solver.rigid_positions)
        ):
            return target
        bind = self.physics_bind_positions[rigid_index]
        source = self.solver.rigid_positions[rigid_index]
        return tuple(
            _f32(_f32(bind[index] - source[index]) + target[index])
            for index in range(3)
        )

    def evaluate_to(self, scene):
        if self.live:
            return self.evaluate_live(scene)
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        target = max(self.vmd_start, self.target_frame(scene))
        if self.last_vmd_frame is None or target < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
            first = self.vmd_start
        elif target == self.last_vmd_frame:
            first = target + 1
        else:
            first = int(self.last_vmd_frame) + 1
        for frame in range(first, target + 1):
            self.solver.evaluate(frame)
        self.last_vmd_frame = target
        self._apply_output(runtime)

    def evaluate_live(self, scene, update=True):
        if self.updating or self.suspended:
            return float(scene.frame_current)
        runtime = bpy.data.objects.get(self.runtime_name)
        canonical = bpy.data.objects.get(self.canonical_name)
        if runtime is None or canonical is None:
            raise MMDIKRuntimeError("MMD native 接管骨架已丢失")
        self.updating = True
        try:
            signature = _live_input_signature(canonical, scene)
            current_frame = (int(scene.frame_current), float(scene.frame_subframe))
            previous_frame = self.input_signature[:2] if self.input_signature else None
            new_frame = previous_frame != current_frame
            was_override = self.pose_override
            if not self.input_basis or new_frame:
                self.input_basis = {
                    pose_bone.name: pose_bone.matrix_basis.copy()
                    for pose_bone in canonical.pose.bones
                }
            if self.source_vmd and new_frame:
                self.pose_override = False
            elif not new_frame and signature != self.input_signature:
                self._capture_external_pose(canonical, scene)
            target = self.target_frame(scene) if self.source_vmd else float(scene.frame_current)
            if self.source_vmd and not self.pose_override and not self.action_input:
                self.solver.end_live_input()
                if was_override or self.last_vmd_frame is None or target < self.last_vmd_frame:
                    self.solver.reset()
                    first = int(self.vmd_start)
                else:
                    first = int(self.last_vmd_frame) + 1
                for frame in range(first, int(target) + 1):
                    self.solver.evaluate(float(frame))
                if target != int(target):
                    self.solver.evaluate(float(target))
            else:
                _submit_live_pose(self, canonical)
                self.solver.evaluate(float(target))
            self.last_vmd_frame = float(target)
            self._apply_output(runtime, update=update)
        finally:
            self.updating = False
        return float(scene.frame_current)

    def evaluate_exact(self, frame, apply_output=True):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        if self.live:
            canonical = bpy.data.objects.get(self.canonical_name)
            if canonical is None:
                raise MMDIKRuntimeError("MMD native 控制骨架已丢失")
            self._capture_external_pose(canonical, bpy.context.scene)
            if self.source_vmd and not self.pose_override and not self.action_input:
                self.solver.end_live_input()
            else:
                _submit_live_pose(self, canonical)
        frame = max(float(self.vmd_start), float(frame))
        if self.last_vmd_frame is not None and frame < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
        self.solver.evaluate(frame)
        self.last_vmd_frame = frame
        if apply_output:
            self._apply_output(runtime)
        return frame

    def evaluate_before_physics(self, frame, apply_output=True):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        if self.live:
            canonical = bpy.data.objects.get(self.canonical_name)
            if canonical is None:
                raise MMDIKRuntimeError("MMD native 控制骨架已丢失")
            self._capture_external_pose(canonical, bpy.context.scene)
            if self.source_vmd and not self.pose_override and not self.action_input:
                self.solver.end_live_input()
            else:
                _submit_live_pose(self, canonical)
        frame = max(float(self.vmd_start), float(frame))
        if self.last_vmd_frame is not None and frame < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
        self.solver.evaluate_before_physics(frame)
        self.last_vmd_frame = frame
        if apply_output:
            self._apply_output(runtime)
        return frame

    def has_blender_overrides(self):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is None:
            return False
        if runtime.animation_data is not None and runtime.animation_data.drivers:
            return True
        return any(
            not constraint.mute and not _is_generated_constraint(constraint, runtime)
            for pose_bone in runtime.pose.bones
            for constraint in pose_bone.constraints
        )


def start(root, pmx_path, vmd_path, blender_start=1, vmd_start=0):
    state = runtime_state(root)
    runtime = canonical_armature(root, state) if state and state.get("enabled") else None
    if runtime is None:
        raise MMDIKRuntimeError("请先启用 MMD IK 兼容")
    pmx = Path(bpy.path.abspath(str(pmx_path)))
    vmd = Path(bpy.path.abspath(str(vmd_path)))
    if not pmx.is_file():
        raise MMDIKRuntimeError(f"源 PMX 不存在：{pmx}")
    if not vmd.is_file():
        raise MMDIKRuntimeError(f"VMD 动作不存在：{vmd}")
    stop(root)
    solver = NativeBoneSolver(pmx, vmd)
    mapping = _bone_map(runtime, solver)
    matched = sum(item is not None for item in mapping)
    if not matched:
        solver.close()
        raise MMDIKRuntimeError("PMX 骨名与 Runtime Armature 完全不匹配")
    scale = _infer_scale(mapping, solver)
    original_action = runtime.animation_data.action if runtime.animation_data else None
    session = Session(
        root.name,
        runtime.name,
        str(pmx),
        str(vmd),
        int(blender_start),
        int(vmd_start),
        solver,
        mapping,
        scale,
        _mute_generated_constraints(runtime),
        original_action,
    )
    for index, pose_bone in enumerate(mapping):
        if pose_bone is None:
            continue
        session.bone_indices[pose_bone.name] = index
        for alias in _pose_bone_name(pose_bone):
            session.bone_indices.setdefault(alias, index)
    _SESSIONS[root.name] = session
    root["spx_mmd_ik_source_pmx"] = str(pmx)
    session.evaluate_to(bpy.context.scene)
    bpy.context.view_layer.update()
    return matched, solver.count, scale


def start_live(root, input_basis=None, update=True):
    state = runtime_state(root)
    canonical = canonical_armature(root, state) if state else None
    if not state or not state.get("enabled") or canonical is None:
        raise MMDIKRuntimeError("请先启用 MMD IK 兼容")
    stop(root)
    source_path = _resolve_live_source_path(root)
    action = canonical.animation_data.action if canonical.animation_data else None
    source_vmd = Path(str(action.get(SOURCE_VMD_KEY, ""))) if action is not None else Path()
    has_source_vmd = bool(action is not None and source_vmd.is_file())
    if source_path.is_file():
        solver = NativeBoneSolver(source_path, source_vmd if has_source_vmd else None)
    else:
        solver = _export_current_pmx(root, source_vmd if has_source_vmd else None)
    mapping = _bone_map(canonical, solver)
    matched = sum(item is not None for item in mapping)
    if not matched:
        solver.close()
        raise MMDIKRuntimeError("当前模型与 native PMX 骨名完全不匹配")
    scale = _infer_scale(mapping, solver)
    muted = []
    session = Session(
        root_name=root.name,
        runtime_name=canonical.name,
        pmx_path=str(source_path) if source_path.is_file() else "<current model>",
        vmd_path=str(source_vmd) if has_source_vmd else "",
        blender_start=int(action.get(SOURCE_FRAME_KEY, 1)) if has_source_vmd else 1,
        vmd_start=0,
        solver=solver,
        mapping=mapping,
        scale=scale,
        muted_constraints=muted,
        original_action=None,
        canonical_name=canonical.name,
        live=True,
        source_vmd=has_source_vmd,
        action_input=bool(state.get("action_input", False)),
        input_basis={
            name: matrix.copy()
            for name, matrix in (
                input_basis.items()
                if input_basis is not None
                else (
                    (pose_bone.name, pose_bone.matrix_basis)
                    for pose_bone in canonical.pose.bones
                )
            )
        },
    )
    for index, pose_bone in enumerate(mapping):
        if pose_bone is None:
            continue
        session.bone_indices[pose_bone.name] = index
        for alias in _pose_bone_name(pose_bone):
            session.bone_indices.setdefault(alias, index)
    _SESSIONS[root.name] = session
    session.evaluate_live(bpy.context.scene, update=update)
    return matched, solver.count, scale


def stop(root):
    if root is None:
        return
    session = _SESSIONS.pop(root.name, None)
    if session is not None:
        session.close()


def is_active(root):
    return root is not None and root.name in _SESSIONS


def enable_action_input(root):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.live:
        return False
    session.action_input = True
    set_action_input(root, True)
    return True


def replay_live(root, scene=None):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.live:
        return False
    session.restore_input()
    session.last_vmd_frame = None
    session.pose_override = False
    session.input_signature = ()
    session.evaluate_live(scene or bpy.context.scene)
    return True


def capture_live_input(root):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.live:
        return None
    return {name: matrix.copy() for name, matrix in session.input_basis.items()}


def restore_live_input(root, snapshot):
    session = _SESSIONS.get(root.name) if root is not None else None
    canonical = bpy.data.objects.get(session.canonical_name) if session and session.live else None
    if canonical is None or snapshot is None:
        return False
    session.input_basis = {name: matrix.copy() for name, matrix in snapshot.items()}
    for name, matrix in snapshot.items():
        pose_bone = canonical.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.matrix_basis = matrix
    canonical.update_tag(refresh={"OBJECT"})
    return True


def detach_all_sessions():
    for root_name, session in tuple(_SESSIONS.items()):
        if session.live:
            session.restore_input()
        session.solver.close()
        _SESSIONS.pop(root_name, None)


def suspend_sessions_for_undo_redo():
    for session in tuple(_SESSIONS.values()):
        if not session.live:
            continue
        session.suspended = True
        session.restore_input(update=False)


def resume_sessions_after_undo_redo(scene=None):
    scene = scene or bpy.context.scene
    rebuild_required = False
    for root_name, session in tuple(_SESSIONS.items()):
        root = bpy.data.objects.get(root_name)
        state = runtime_state(root) if root is not None else None
        canonical = canonical_armature(root, state) if state else None
        source_path = _resolve_live_source_path(root) if root else Path()
        if (
            not session.live
            or not state
            or not state.get("enabled")
            or canonical is None
            or not source_path.is_file()
            or source_path.resolve() != Path(session.pmx_path).resolve()
        ):
            session.solver.close()
            _SESSIONS.pop(root_name, None)
            rebuild_required = True
            continue
        refresh_bindings(root)
        mapping = _bone_map(canonical, session.solver)
        if not any(item is not None for item in mapping):
            session.solver.close()
            _SESSIONS.pop(root_name, None)
            rebuild_required = True
            continue
        session.runtime_name = canonical.name
        session.canonical_name = canonical.name
        session.mapping = mapping
        session.scale = _infer_scale(mapping, session.solver)
        session.bone_indices.clear()
        for index, pose_bone in enumerate(mapping):
            if pose_bone is None:
                continue
            session.bone_indices[pose_bone.name] = index
            for alias in _pose_bone_name(pose_bone):
                session.bone_indices.setdefault(alias, index)
        session.input_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in canonical.pose.bones
        }
        session.output_basis.clear()
        session.input_signature = ()
        session.action_signature = ()
        session.solver_matrices.clear()
        session.desired_pose.clear()
        session.external_transforms.clear()
        session.physics_bind_positions = ()
        session.physics_rigid_indices = ()
        session.physics_feedback_complete = False
        session.last_vmd_frame = None
        session.pose_override = True
        session.solver.reset()
        session.solver.clear_external_transforms()
        session.suspended = False
        session.evaluate_live(scene, update=False)
    if rebuild_required:
        rebuild_enabled_sessions()


def rebuild_enabled_sessions():
    rebuilt = []
    for root in tuple(bpy.data.objects):
        if getattr(root, "mmd_type", "") != "ROOT":
            continue
        state = runtime_state(root)
        if not state or not state.get("enabled") or root.name in _SESSIONS:
            continue
        try:
            refresh_bindings(root)
            start_live(root)
        except Exception as error:
            print(f"MMD native live evaluator rebuild failed for {root.name}: {error}")
            continue
        rebuilt.append(root.name)
    return tuple(rebuilt)


def suspend_live(root):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.live:
        return False
    session.suspended = True
    session.restore_input()
    return True


def resume_live(root):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.live:
        return False
    session.suspended = False
    replay_live(root)
    return True


def capture_physics_bindings(root, preview_session):
    session = _SESSIONS.get(root.name) if root is not None else None
    return bool(session and session.capture_physics_bindings(preview_session))


def _physics_model_translation(preview_session):
    current = getattr(preview_session, "ik_motion_anchor", None)
    origin = getattr(preview_session, "motion_anchor_origin", None)
    if current is None:
        current = preview_session.armature.matrix_world
    if origin is None:
        origin = preview_session.saved_armature_matrix
    return blender_position_to_mmd(
        current.translation - origin.translation,
        preview_session.import_scale,
    )


def submit_physics_feedback(root, preview_session, transforms=None):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None or not session.physics_feedback_complete:
        return 0
    start = preview_session.body_offset
    dll = preview_session.solver.library.dll
    raw_basis = hasattr(dll, "mmd_solver_get_basis_transforms")
    source = preview_session.solver.basis_transforms() if raw_basis else transforms
    if source is None:
        source = preview_session.solver.transforms()
    local = source[start : start + len(preview_session.rigids)]
    model_translation = _physics_model_translation(preview_session)
    submitted = 0
    for rigid_index, (rigid, transform) in enumerate(zip(preview_session.rigids, local)):
        if int(rigid.mmd_rigid.type) == 0 or not rigid.mmd_rigid.bone:
            continue
        native_rigid_index = (
            session.physics_rigid_indices[rigid_index]
            if rigid_index < len(session.physics_rigid_indices)
            else None
        )
        if native_rigid_index is None:
            continue
        if raw_basis:
            position = (transform.position.x, transform.position.y, transform.position.z)
            if preview_session.solver_target == "MMD":
                position = tuple(
                    position[index] - model_translation[index]
                    for index in range(3)
                )
            state = (
                position,
                tuple(transform.basis_row_major),
            )
            if preview_session.solver_target == "MMD":
                session.solver.set_external_rigid_matrix_mmd(
                    native_rigid_index,
                    state[0],
                    state[1],
                )
            else:
                session.solver.set_external_rigid_matrix(
                    native_rigid_index,
                    state[0],
                    state[1],
                )
        else:
            state = (
                (transform.position.x, transform.position.z, transform.position.y),
                (
                    -transform.rotation.x,
                    -transform.rotation.z,
                    -transform.rotation.y,
                    transform.rotation.w,
                ),
            )
            session.solver.set_external_rigid_transform(
                native_rigid_index,
                state[0],
                state[1],
            )
        session.external_transforms[native_rigid_index] = state
        submitted += 1
    if preview_session.solver_target == "MMD":
        session.solver.evaluate_after_physics()
    else:
        session.solver.commit_external()
    runtime = bpy.data.objects.get(session.runtime_name)
    if runtime is not None:
        session._apply_output(runtime)
        bpy.context.view_layer.update()
    return submitted


def evaluate_physics_pose(root, preview_session, vmd_frame=None):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None:
        return None
    if preview_session.solver_target == "MMD" and preview_session.mmd_step_count <= 3:
        session.external_transforms.clear()
        session.solver.clear_external_transforms()
    if vmd_frame is None:
        vmd_frame = (
            session.vmd_start
            + preview_session.scene.frame_current
            + preview_session.scene.frame_subframe
            - session.blender_start
        )
    if preview_session.solver_target == "MMD":
        session.evaluate_before_physics(vmd_frame, apply_output=True)
    else:
        session.evaluate_exact(vmd_frame, apply_output=True)
    return float(vmd_frame)


def uses_exact_physics_targets(root, preview_session):
    session = _SESSIONS.get(root.name) if root is not None else None
    return bool(
        session
        and preview_session.solver_target == "MMD"
        and not session.has_blender_overrides()
    )


def prepare_physics_targets(root, preview_session):
    session = _SESSIONS.get(root.name) if root is not None else None
    if not uses_exact_physics_targets(root, preview_session):
        return 0
    from ..physics_preview.ffi import Quat, Transform, Vec3

    dll = preview_session.solver.library.dll
    raw_targets = hasattr(dll, "mmd_solver_set_body_target_basis")
    model_translation = _physics_model_translation(preview_session)
    submitted = 0
    for rigid_index, rigid in enumerate(preview_session.rigids):
        bone_name = rigid.mmd_rigid.bone
        bone_index = session.bone_indices.get(bone_name) if bone_name else None
        if bone_index is None:
            continue
        x, y, z, qx, qy, qz, qw = session.solver.transform(bone_index)
        source = _mmd_transform(preview_session.body_descs[rigid_index].bone_transform)
        rest_x, rest_y, rest_z = session.solver.rest_positions[bone_index]
        position = (
            _f32(_f32(source[0] - rest_x) + x),
            _f32(_f32(source[1] - rest_y) + y),
            _f32(_f32(source[2] - rest_z) + z),
        )
        delta = (qx, qy, qz, qw)
        rotation = (
            source[3:]
            if delta == (0.0, 0.0, 0.0, 1.0)
            else _qmul(delta, source[3:])
        )
        physics_position = tuple(
            position[index] + model_translation[index]
            for index in range(3)
        )
        preview_session.solver.set_bone_target(
            preview_session.body_offset + rigid_index,
            Transform(
                Vec3(
                    physics_position[0],
                    physics_position[2],
                    physics_position[1],
                ),
                Quat(-rotation[0], -rotation[2], -rotation[1], rotation[3]),
            ),
        )
        if int(rigid.mmd_rigid.type) == 0 and raw_targets:
            target = session.solver.rigid_target(rigid_index)
            corrected = session.corrected_rigid_position(rigid_index, target[:3])
            preview_session.solver.set_body_target_position(
                preview_session.body_offset + rigid_index,
                tuple(
                    corrected[index] + model_translation[index]
                    for index in range(3)
                ),
            )
        submitted += 1
    return submitted


def clear_physics_feedback(root):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None:
        return
    session.external_transforms.clear()
    session.solver.clear_external_transforms()


@persistent
def _frame_change_pre(scene, _depsgraph=None):
    stale = []
    for root_name, session in tuple(_SESSIONS.items()):
        root = bpy.data.objects.get(root_name)
        if root is None:
            stale.append(root_name)
            continue
        if session.live:
            session.restore_input(update=False)
            continue
        try:
            session.evaluate_to(scene)
        except Exception as error:
            print(f"MMD IK evaluator stopped for {root_name}: {error}")
            stale.append(root_name)
    for root_name in stale:
        session = _SESSIONS.pop(root_name, None)
        if session is not None:
            session.close()


@persistent
def _frame_change_post(scene, _depsgraph=None):
    for root_name, session in tuple(_SESSIONS.items()):
        if not session.live or session.updating or session.suspended:
            continue
        try:
            session.evaluate_live(scene)
        except Exception as error:
            print(f"MMD native live evaluator stopped for {root_name}: {error}")
            _SESSIONS.pop(root_name, None)
            session.close()


@persistent
def _depsgraph_update_post(scene, _depsgraph=None):
    stale = []
    for root_name, session in tuple(_SESSIONS.items()):
        if not session.live or session.updating or session.suspended:
            continue
        root = bpy.data.objects.get(root_name)
        canonical = bpy.data.objects.get(session.canonical_name)
        if root is None or canonical is None:
            stale.append(root_name)
            continue
        signature = _live_input_signature(canonical, scene)
        action_signature = _action_frame_signature(canonical, scene.frame_current)
        action_changed = action_signature != session.action_signature
        if action_changed:
            session.repair_current_action_keys(canonical, scene.frame_current)
            session.action_input = True
            set_action_input(root, True)
        if signature == session.input_signature and not action_changed:
            continue
        try:
            from ..physics_preview.runtime import is_running

            if is_running(root):
                session._capture_external_pose(canonical, scene)
            else:
                session.evaluate_live(scene, update=False)
        except Exception as error:
            print(f"MMD native live evaluator stopped for {root_name}: {error}")
            stale.append(root_name)
    for root_name in stale:
        session = _SESSIONS.pop(root_name, None)
        if session is not None:
            session.close()


def install_handler():
    if _frame_change_pre not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_frame_change_pre)
    if _depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_update_post)
    if _frame_change_post not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_frame_change_post)


def uninstall_handler():
    if _frame_change_pre in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(_frame_change_pre)
    if _depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_update_post)
    if _frame_change_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_frame_change_post)
    for root_name in tuple(_SESSIONS):
        root = bpy.data.objects.get(root_name)
        if root is not None:
            stop(root)
        else:
            _SESSIONS.pop(root_name).close()
