import math
import traceback

import bpy
from mathutils import Matrix, Quaternion, Vector

from .ffi import BodyDesc, JointDesc, Solver, Vec3, matrix_to_transform, transform_to_components


SHAPES = {"SPHERE": 0, "BOX": 1, "CAPSULE": 2}
_ACTIVE_SESSION = None


def _model_api():
    from ..mmd_physics import _mmd_api

    model_api, _rigid_api, _rigid_module = _mmd_api()
    return model_api


def _model_armature(root):
    return _model_api().find_armature_object(root)


def _rigid_objects(root):
    return [
        obj
        for obj in _model_api().iterate_rigid_body_objects(root)
        if obj.rigid_body is not None
    ]


def _joint_objects(root):
    return [
        obj
        for obj in _model_api().iterate_joint_objects(root)
        if obj.rigid_body_constraint is not None
    ]


def _proxy_physics_objects(proxy, objects):
    proxy_id = str(proxy.get("surface_proxy_physics_id", ""))
    return {
        obj
        for obj in objects
        if (
            proxy_id
            and obj.get("surface_proxy_physics_id") == proxy_id
        )
        or obj.get("surface_proxy_object") == proxy.name
    }


def _set_bone_connections(armature, values):
    if not values:
        return
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    previous_selection = list(bpy.context.selected_objects)
    if previous_active is not None and previous_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in previous_selection:
        obj.select_set(False)
    armature.select_set(True)
    view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name, use_connect in values.items():
            edit_bone = armature.data.edit_bones.get(name)
            if edit_bone is not None and edit_bone.parent is not None:
                edit_bone.use_connect = use_connect
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        armature.select_set(False)
        for obj in previous_selection:
            obj.select_set(True)
        view_layer.objects.active = previous_active
        if previous_active is not None and previous_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=previous_mode)


def _unanchored_dynamic_components(rigids, joints):
    body_indices = {obj: index for index, obj in enumerate(rigids)}
    neighbors = [set() for _rigid in rigids]
    for joint in joints:
        constraint = joint.rigid_body_constraint
        first = body_indices.get(constraint.object1)
        second = body_indices.get(constraint.object2)
        if first is None or second is None or first == second:
            continue
        neighbors[first].add(second)
        neighbors[second].add(first)

    components = []
    remaining = set(range(len(rigids)))
    while remaining:
        pending = [remaining.pop()]
        component = set(pending)
        while pending:
            current = pending.pop()
            for neighbor in neighbors[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        if any(int(rigids[index].mmd_rigid.type) == 0 for index in component):
            continue
        dynamic = [
            rigids[index].name
            for index in sorted(component)
            if int(rigids[index].mmd_rigid.type) != 0
        ]
        if dynamic:
            components.append(tuple(dynamic))
    return tuple(components)


def _bone_depth(pose_bone):
    depth = 0
    parent = pose_bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _resolve_hierarchical_bone_targets(armature, animation_pose, physics_targets):
    resolved = {}
    ordered_bones = sorted(armature.pose.bones, key=_bone_depth)
    for pose_bone in ordered_bones:
        animation_matrix = animation_pose[pose_bone.name]
        parent = pose_bone.parent
        if parent is None:
            inherited = animation_matrix
        else:
            local_animation = animation_pose[parent.name].inverted_safe() @ animation_matrix
            inherited = resolved[parent.name] @ local_animation
        target = physics_targets.get(pose_bone.name)
        if target is not None:
            mode, physics_matrix = target
            if mode == 2:
                inherited = Matrix.LocRotScale(
                    inherited.translation,
                    physics_matrix.to_quaternion(),
                    inherited.to_scale(),
                )
            else:
                inherited = physics_matrix
        resolved[pose_bone.name] = inherited
    return resolved


def _body_desc(obj, armature):
    rigid = obj.mmd_rigid
    body = obj.rigid_body
    blocked = tuple(rigid.collision_group_mask)
    collision_mask = sum(1 << index for index, value in enumerate(blocked) if not value)
    pose_bone = armature.pose.bones.get(rigid.bone) if rigid.bone else None
    bone_world = armature.matrix_world @ pose_bone.matrix if pose_bone else obj.matrix_world
    return BodyDesc(
        int(rigid.type),
        SHAPES.get(rigid.shape, 0),
        matrix_to_transform(obj.matrix_world),
        matrix_to_transform(bone_world),
        int(pose_bone is not None),
        Vec3.from_value(rigid.size),
        max(float(body.mass), 0.0),
        float(body.linear_damping),
        float(body.angular_damping),
        float(body.restitution),
        float(body.friction),
        int(rigid.collision_group_number),
        collision_mask,
    )


def _constraint_vector(constraint, pattern):
    return Vec3(
        float(getattr(constraint, pattern.format(axis="x"))),
        float(getattr(constraint, pattern.format(axis="y"))),
        float(getattr(constraint, pattern.format(axis="z"))),
    )


def _matrix_changed(first, second, epsilon=1.0e-5):
    return any(
        abs(first[row][column] - second[row][column]) > epsilon
        for row in range(4)
        for column in range(4)
    )


def _joint_desc(obj, body_indices):
    constraint = obj.rigid_body_constraint
    if constraint.object1 not in body_indices or constraint.object2 not in body_indices:
        return None
    joint = obj.mmd_joint
    return JointDesc(
        body_indices[constraint.object1],
        body_indices[constraint.object2],
        matrix_to_transform(obj.matrix_world),
        _constraint_vector(constraint, "limit_lin_{axis}_lower"),
        _constraint_vector(constraint, "limit_lin_{axis}_upper"),
        _constraint_vector(constraint, "limit_ang_{axis}_lower"),
        _constraint_vector(constraint, "limit_ang_{axis}_upper"),
        Vec3.from_value(joint.spring_linear),
        Vec3.from_value(joint.spring_angular),
    )


class PreviewSession:
    def __init__(self, scene, settings, root):
        self.scene = scene
        self.settings = settings
        self.root = root
        self.root_name = root.name
        self.armature = _model_armature(root)
        if self.armature is None:
            raise RuntimeError("所选 MMD 模型没有 Armature")
        self.armature_name = self.armature.name
        self.saved_pose_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        all_rigids = _rigid_objects(root)
        all_joints = _joint_objects(root)
        self.saved_rigid_matrices = {
            rigid.name: rigid.matrix_world.copy() for rigid in all_rigids
        }
        self.saved_joint_matrices = {
            joint.name: joint.matrix_world.copy() for joint in all_joints
        }
        if settings.preview_scope == "CURRENT_PROXY":
            proxy = settings.physics_proxy
            if proxy is None:
                raise RuntimeError("当前代理预览需要先选择“当前代理网格”")
            proxy_objects = _proxy_physics_objects(
                proxy,
                [*all_rigids, *all_joints],
            )
            proxy_rigids = {obj for obj in all_rigids if obj in proxy_objects}
            if not proxy_rigids:
                raise RuntimeError("当前代理尚未生成可预览的刚体")
            self.rigids = [
                obj
                for obj in all_rigids
                if obj in proxy_rigids or int(obj.mmd_rigid.type) == 0
            ]
            joint_objects = [obj for obj in all_joints if obj in proxy_objects]
        else:
            self.rigids = all_rigids
            joint_objects = all_joints
        if not self.rigids:
            raise RuntimeError("所选 MMD 模型没有可预览的刚体")
        self.rigid_names = [rigid.name for rigid in self.rigids]
        self.dynamic_rigid_count = sum(
            int(rigid.mmd_rigid.type) != 0 for rigid in self.rigids
        )
        dynamic_bone_names = {
            rigid.mmd_rigid.bone
            for rigid in self.rigids
            if int(rigid.mmd_rigid.type) != 0 and rigid.mmd_rigid.bone
        }
        self.saved_bone_connections = {
            name: self.armature.data.bones[name].use_connect
            for name in dynamic_bone_names
            if name in self.armature.data.bones
            and self.armature.data.bones[name].parent is not None
            and self.armature.data.bones[name].use_connect
        }
        self.unanchored_dynamic_components = _unanchored_dynamic_components(
            self.rigids,
            joint_objects,
        )
        try:
            _set_bone_connections(
                self.armature,
                {name: False for name in self.saved_bone_connections},
            )
            bpy.context.view_layer.update()
            body_indices = {obj: index for index, obj in enumerate(self.rigids)}
            joint_descs = []
            self.joints = []
            for joint in joint_objects:
                desc = _joint_desc(joint, body_indices)
                if desc is not None and desc.body_a != desc.body_b:
                    joint_descs.append(desc)
                    self.joints.append(joint)
            self.joint_names = [joint.name for joint in self.joints]
            self.solver = self._create_solver(joint_descs)
        except Exception:
            for name, matrix_basis in self.saved_pose_basis.items():
                pose_bone = self.armature.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix_basis
            _set_bone_connections(self.armature, self.saved_bone_connections)
            bpy.context.view_layer.update()
            raise
        self.bone_offsets = {}
        self.bone_drivers = {}
        self.saved_basis = {}
        for index, rigid in enumerate(self.rigids):
            bone_name = rigid.mmd_rigid.bone
            pose_bone = self.armature.pose.bones.get(bone_name) if bone_name else None
            if pose_bone is None:
                continue
            bone_world = self.armature.matrix_world @ pose_bone.matrix
            self.bone_offsets[index] = bone_world.inverted_safe() @ rigid.matrix_world
            if int(rigid.mmd_rigid.type) != 0:
                self.saved_basis[bone_name] = self.saved_pose_basis[bone_name].copy()
                current = self.bone_drivers.get(bone_name)
                if (
                    current is None
                    or rigid.rigid_body.mass > self.rigids[current].rigid_body.mass
                ):
                    self.bone_drivers[bone_name] = index
        self.last_output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)
        self.auto_reset_count = 0
        self.consecutive_tick_failures = 0
        self.snapshot_reset_pending = False
        self.closed = False

    def _rebind_blender_data(self):
        scene = bpy.context.scene
        root = bpy.data.objects.get(self.root_name)
        armature = bpy.data.objects.get(self.armature_name)
        rigids = [bpy.data.objects.get(name) for name in self.rigid_names]
        joints = [bpy.data.objects.get(name) for name in self.joint_names]
        if root is None or armature is None:
            raise RuntimeError("启动快照对应的 MMD 模型或 Armature 已不存在")
        if any(rigid is None for rigid in rigids):
            raise RuntimeError("启动快照中的刚体已不存在")
        if any(joint is None for joint in joints):
            raise RuntimeError("启动快照中的 Joint 已不存在")
        changed = (
            self.root is not root
            or self.armature is not armature
            or len(self.rigids) != len(rigids)
            or len(self.joints) != len(joints)
            or any(old is not current for old, current in zip(self.rigids, rigids))
            or any(old is not current for old, current in zip(self.joints, joints))
        )
        self.scene = scene
        self.settings = scene.surface_proxy_creator
        self.root = root
        self.armature = armature
        self.rigids = rigids
        self.joints = joints
        if not self.closed:
            self.settings.preview_running = True
        return changed

    def _create_solver(self, joint_descs=None):
        if joint_descs is None:
            body_indices = {obj: index for index, obj in enumerate(self.rigids)}
            joint_descs = [
                desc
                for desc in (
                    _joint_desc(joint, body_indices) for joint in self.joints
                )
                if desc is not None and desc.body_a != desc.body_b
            ]
        solver = Solver(
            [_body_desc(obj, self.armature) for obj in self.rigids],
            joint_descs,
        )
        solver.set_gravity(self.settings.preview_gravity)
        return solver

    def _broad_pose_reset_detected(self):
        driver_names = set(self.bone_drivers)
        current_frame = (self.scene.frame_current, self.scene.frame_subframe)
        if (
            current_frame != self.last_frame
            or not driver_names
            or not self.last_output_basis
        ):
            return False
        changed = sum(
            _matrix_changed(
                self.armature.pose.bones[name].matrix_basis,
                self.last_output_basis[name],
            )
            for name in driver_names
            if name in self.armature.pose.bones and name in self.last_output_basis
        )
        required = max(2, math.ceil(len(driver_names) * 0.2))
        if len(driver_names) == 1:
            required = 1
        return changed >= required

    def _restore_start_snapshot(self):
        self._rebind_blender_data()
        for name, matrix_basis in self.saved_pose_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        for name, matrix_world in self.saved_rigid_matrices.items():
            rigid = bpy.data.objects.get(name)
            if rigid is not None:
                rigid.matrix_world = matrix_world
        for name, matrix_world in self.saved_joint_matrices.items():
            joint = bpy.data.objects.get(name)
            if joint is not None:
                joint.matrix_world = matrix_world
        bpy.context.view_layer.update()

    def reset_solver(self):
        if self.closed:
            return
        self._restore_start_snapshot()

        old_solver = self.solver
        self.solver = self._create_solver()
        old_solver.close()
        self.last_output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)

    def tick(self):
        if self._rebind_blender_data():
            self.reset_solver()
            self.auto_reset_count += 1
            self.settings.preview_status = (
                f"运行中：Blender 数据重建后已恢复启动快照 {self.auto_reset_count} 次"
            )
        broad_pose_reset = self._broad_pose_reset_detected()
        if broad_pose_reset:
            self.reset_solver()
            self.auto_reset_count += 1
            self.settings.preview_status = (
                f"运行中：已自动重置物理 {self.auto_reset_count} 次"
            )
        for name, matrix_basis in self.saved_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        bpy.context.view_layer.update()
        animation_pose = {
            pose_bone.name: pose_bone.matrix.copy()
            for pose_bone in self.armature.pose.bones
        }
        for index, rigid in enumerate(self.rigids):
            pose_bone = self.armature.pose.bones.get(rigid.mmd_rigid.bone)
            if pose_bone is None or index not in self.bone_offsets:
                continue
            bone_world = self.armature.matrix_world @ pose_bone.matrix
            self.solver.set_bone_target(index, bone_world)
        self.solver.step(1.0 / self.settings.preview_frequency, self.settings.preview_substeps)
        transforms = self.solver.transforms()
        bone_transforms = self.solver.bone_transforms()
        armature_inverse = self.armature.matrix_world.inverted_safe()
        bone_targets = {}
        for index, transform in enumerate(transforms):
            rigid = self.rigids[index]
            position, rotation = transform_to_components(transform)
            rigid_world = Matrix.LocRotScale(
                Vector(position),
                Quaternion(rotation),
                Vector((1.0, 1.0, 1.0)),
            )
            if int(rigid.mmd_rigid.type) == 0 or index not in self.bone_offsets:
                if self.settings.preview_update_rigids:
                    scale = rigid.matrix_world.to_scale()
                    rigid.matrix_world = Matrix.LocRotScale(
                        rigid_world.translation,
                        rigid_world.to_quaternion(),
                        scale,
                    )
                continue
            pose_bone = self.armature.pose.bones.get(rigid.mmd_rigid.bone)
            if pose_bone is None:
                continue
            bone_position, bone_rotation = transform_to_components(bone_transforms[index])
            bone_world = Matrix.LocRotScale(
                Vector(bone_position),
                Quaternion(bone_rotation),
                Vector((1.0, 1.0, 1.0)),
            )
            if self.settings.preview_update_rigids:
                scale = rigid.matrix_world.to_scale()
                rigid.matrix_world = Matrix.LocRotScale(
                    rigid_world.translation,
                    rigid_world.to_quaternion(),
                    scale,
                )
            if self.bone_drivers.get(pose_bone.name) != index:
                continue
            bone_targets[pose_bone.name] = (
                _bone_depth(pose_bone),
                int(rigid.mmd_rigid.type),
                bone_world,
            )
        for joint, state in zip(self.joints, self.solver.joint_states()):
            position_a, rotation_a = transform_to_components(state.frame_a)
            position_b, _rotation_b = transform_to_components(state.frame_b)
            position = (Vector(position_a) + Vector(position_b)) * 0.5
            scale = joint.matrix_world.to_scale()
            joint.matrix_world = Matrix.LocRotScale(
                position,
                Quaternion(rotation_a),
                scale,
            )
        physics_targets = {
            name: (value[1], armature_inverse @ value[2])
            for name, value in bone_targets.items()
        }
        pose_targets = _resolve_hierarchical_bone_targets(
            self.armature,
            animation_pose,
            physics_targets,
        )
        for bone_name, (_depth, _mode, _bone_world) in sorted(
            bone_targets.items(),
            key=lambda item: item[1][0],
        ):
            pose_bone = self.armature.pose.bones.get(bone_name)
            if pose_bone is None:
                continue
            parent = pose_bone.parent
            if parent is None:
                pose_bone.matrix_basis = pose_bone.bone.convert_local_to_pose(
                    pose_targets[bone_name],
                    pose_bone.bone.matrix_local,
                    invert=True,
                )
                continue
            parent_matrix = pose_targets[parent.name]
            pose_bone.matrix_basis = pose_bone.bone.convert_local_to_pose(
                pose_targets[bone_name],
                pose_bone.bone.matrix_local,
                parent_matrix=parent_matrix,
                parent_matrix_local=parent.bone.matrix_local,
                invert=True,
            )
        bpy.context.view_layer.update()
        self.last_output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)

    def close(self, restore=True):
        if self.closed:
            return
        self.closed = True
        self.solver.close()
        if restore and self.armature is not None:
            self._restore_start_snapshot()
            _set_bone_connections(self.armature, self.saved_bone_connections)
            bpy.context.view_layer.update()


def is_running():
    return _ACTIVE_SESSION is not None


def start_preview(context):
    global _ACTIVE_SESSION
    stop_preview(restore=True)
    settings = context.scene.surface_proxy_creator
    root = settings.mmd_root
    if root is None or getattr(root, "mmd_type", "") != "ROOT":
        raise RuntimeError("请先在面板中选择 MMD 模型")
    _ACTIVE_SESSION = PreviewSession(context.scene, settings, root)
    settings.preview_running = True
    settings.preview_status = "运行中"
    if not bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.register(_timer_tick, first_interval=0.0)
    return _ACTIVE_SESSION


def stop_preview(restore=True):
    global _ACTIVE_SESSION
    session = _ACTIVE_SESSION
    _ACTIVE_SESSION = None
    if session is not None:
        session.close(restore=restore)
        if session.settings is not None:
            session.settings.preview_running = False
            session.settings.preview_status = "已停止"
    if bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)


def reset_preview():
    session = _ACTIVE_SESSION
    if session is None:
        raise RuntimeError("物理预览尚未启动")
    session.reset_solver()
    session.settings.preview_status = "运行中：已恢复启动快照并重置物理"
    return session


def _timer_tick():
    session = _ACTIVE_SESSION
    if session is None:
        return None
    try:
        rebound = session._rebind_blender_data()
        if rebound:
            session.snapshot_reset_pending = True
    except Exception as recovery_error:
        traceback.print_exc()
        session.snapshot_reset_pending = True
        settings = bpy.context.scene.surface_proxy_creator
        settings.preview_running = True
        settings.preview_status = (
            "运行中：重新绑定 Blender 数据失败，将继续重试 "
            f"({type(recovery_error).__name__}: {recovery_error})"
        )
        return 1.0 / max(settings.preview_frequency, 1)
    interval = 1.0 / max(session.settings.preview_frequency, 1)
    if session.snapshot_reset_pending:
        try:
            session.reset_solver()
            session.snapshot_reset_pending = False
            session.settings.preview_status = "运行中：已恢复启动快照并继续物理"
        except Exception as recovery_error:
            traceback.print_exc()
            session.settings.preview_status = (
                "运行中：启动快照恢复失败，将继续重试 "
                f"({type(recovery_error).__name__}: {recovery_error})"
            )
            return interval
    try:
        session.tick()
        session.consecutive_tick_failures = 0
    except Exception as error:
        traceback.print_exc()
        session.consecutive_tick_failures += 1
        session.snapshot_reset_pending = True
        try:
            session.reset_solver()
            session.snapshot_reset_pending = False
            session.auto_reset_count += 1
            session.settings.preview_status = (
                "运行中：异常后已恢复启动快照 "
                f"({type(error).__name__}: {error})"
            )
        except Exception as recovery_error:
            traceback.print_exc()
            session.settings.preview_status = (
                "运行中：启动快照恢复失败，将继续重试 "
                f"({type(recovery_error).__name__}: {recovery_error})"
            )
        return interval
    return interval
