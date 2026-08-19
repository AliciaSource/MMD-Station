from dataclasses import dataclass, field
import math
from pathlib import Path
import struct

import bpy
from bpy.app.handlers import persistent

from .coordinates import blender_pose_matrix, mmd_position_to_blender
from .ffi import NativeBoneSolver
from .runtime import MMDIKRuntimeError, runtime_armature, runtime_state


ACTIVE_KEY = "spx_mmd_ik_evaluator_active"
_SESSIONS = {}


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


def _bone_map(armature, solver):
    aliases = {}
    for pose_bone in armature.pose.bones:
        for name in _pose_bone_name(pose_bone):
            aliases.setdefault(name, pose_bone)
    return tuple(aliases.get(name) for name in solver.names)


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

    def _apply_output(self, runtime):
        for index, pose_bone in enumerate(self.mapping):
            if pose_bone is not None:
                pose_bone.matrix = blender_pose_matrix(
                    self.solver.matrix(index), self.scale, pose_bone.bone.matrix_local
                )

    def close(self):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is not None:
            _restore_constraints(runtime, self.muted_constraints)
            if runtime.animation_data is not None:
                runtime.animation_data.action = self.original_action
        self.solver.close()

    def target_frame(self, scene):
        return self.vmd_start + int(scene.frame_current) - self.blender_start

    def capture_physics_bindings(self, preview_session):
        dll = preview_session.solver.library.dll
        if not hasattr(dll, "mmd_solver_get_basis_transforms"):
            self.physics_bind_positions = ()
            return False
        transforms = preview_session.solver.basis_transforms()
        start = preview_session.body_offset
        local = transforms[start : start + len(preview_session.rigids)]
        self.physics_bind_positions = tuple(
            (float(item.position.x), float(item.position.y), float(item.position.z))
            for item in local
        )
        return len(self.physics_bind_positions) == len(preview_session.rigids)

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

    def evaluate_exact(self, frame, apply_output=True):
        runtime = bpy.data.objects.get(self.runtime_name)
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
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
    runtime = runtime_armature(root, state) if state and state.get("enabled") else None
    if runtime is None:
        raise MMDIKRuntimeError("请先创建并启用 MMD IK 兼容骨架")
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
    if runtime.animation_data is not None:
        runtime.animation_data.action = None
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
    root[ACTIVE_KEY] = True
    root["spx_mmd_ik_source_pmx"] = str(pmx)
    session.evaluate_to(bpy.context.scene)
    bpy.context.view_layer.update()
    return matched, solver.count, scale


def stop(root):
    if root is None:
        return
    session = _SESSIONS.pop(root.name, None)
    if session is not None:
        session.close()
    root[ACTIVE_KEY] = False


def is_active(root):
    return root is not None and root.name in _SESSIONS


def capture_physics_bindings(root, preview_session):
    session = _SESSIONS.get(root.name) if root is not None else None
    return bool(session and session.capture_physics_bindings(preview_session))


def submit_physics_feedback(root, preview_session, transforms=None):
    session = _SESSIONS.get(root.name) if root is not None else None
    if session is None:
        return 0
    start = preview_session.body_offset
    dll = preview_session.solver.library.dll
    raw_basis = hasattr(dll, "mmd_solver_get_basis_transforms")
    source = preview_session.solver.basis_transforms() if raw_basis else transforms
    if source is None:
        source = preview_session.solver.transforms()
    local = source[start : start + len(preview_session.rigids)]
    submitted = 0
    for rigid_index, (rigid, transform) in enumerate(zip(preview_session.rigids, local)):
        if int(rigid.mmd_rigid.type) == 0 or not rigid.mmd_rigid.bone:
            continue
        if raw_basis:
            state = (
                (transform.position.x, transform.position.y, transform.position.z),
                tuple(transform.basis_row_major),
            )
            if preview_session.solver_target == "MMD":
                session.solver.set_external_rigid_matrix_mmd(
                    rigid_index,
                    state[0],
                    state[1],
                )
            else:
                session.solver.set_external_rigid_matrix(
                    rigid_index,
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
                rigid_index,
                state[0],
                state[1],
            )
        session.external_transforms[rigid_index] = state
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
    bpy.context.view_layer.update()
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
        preview_session.solver.set_bone_target(
            preview_session.body_offset + rigid_index,
            Transform(
                Vec3(position[0], position[2], position[1]),
                Quat(-rotation[0], -rotation[2], -rotation[1], rotation[3]),
            ),
        )
        if int(rigid.mmd_rigid.type) == 0 and raw_targets:
            target = session.solver.rigid_target(rigid_index)
            if preview_session.mmd_step_count >= 4:
                matrix = session.solver.rigid_matrix(rigid_index)
                preview_session.solver.set_body_target_basis(
                    preview_session.body_offset + rigid_index,
                    matrix[:3],
                    matrix[3:],
                )
            preview_session.solver.set_body_target_position(
                preview_session.body_offset + rigid_index,
                session.corrected_rigid_position(rigid_index, target[:3]),
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
        try:
            session.evaluate_to(scene)
        except Exception as error:
            print(f"MMD IK evaluator stopped for {root_name}: {error}")
            stale.append(root_name)
    for root_name in stale:
        session = _SESSIONS.pop(root_name, None)
        if session is not None:
            session.close()


def install_handler():
    if _frame_change_pre not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_frame_change_pre)


def uninstall_handler():
    if _frame_change_pre in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(_frame_change_pre)
    for root_name in tuple(_SESSIONS):
        root = bpy.data.objects.get(root_name)
        if root is not None:
            stop(root)
        else:
            _SESSIONS.pop(root_name).close()
