import concurrent.futures
import ctypes
import math
import os
import struct
import time
import traceback
from collections import Counter, defaultdict, deque
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Quaternion, Vector

from .ffi import (
    BodyDesc,
    JointDesc,
    Solver,
    Transform,
    Vec3,
    default_library,
    pmx_euler_to_blender_quaternion,
    transform_to_components,
)
from .time_driver import PreviewTimeDriver


SHAPES = {"SPHERE": 0, "BOX": 1, "CAPSULE": 2}
SUPPORTED_IMPORT_SCALES = (0.08, 0.1)
_ACTIVE_SESSIONS = {}
_ACTIVE_WORLDS = {}
_STEP_EXECUTOR = None
_SOURCE_PHYSICS_CACHE = {}
_RUNTIME_SUSPENDED = False


def _uniform_world_scale(obj, tolerance=1.0e-4):
    scale = tuple(abs(float(value)) for value in obj.matrix_world.decompose()[2])
    largest = max(scale)
    if largest <= 1.0e-8 or max(scale) - min(scale) > largest * tolerance:
        raise RuntimeError(f"{obj.name} 使用了非均匀或零缩放，无法保持 MMD 刚体语义")
    return sum(scale) / 3.0


def _supported_import_scale(value, tolerance=1.0e-4):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    for supported in SUPPORTED_IMPORT_SCALES:
        if abs(value - supported) <= supported * tolerance:
            return supported
    return None


def _native_model_import_scale(root, tolerance=1.0e-4):
    import_scale = float(root.empty_display_size) * 0.2
    supported = _supported_import_scale(import_scale, tolerance)
    if supported is not None:
        return supported
    stored = root.get("spx_mmd_import_scale")
    supported = _supported_import_scale(stored, tolerance)
    if supported is not None:
        return supported
    return 0.08


def _inspect_model_import_scale(root, tolerance=1.0e-4):
    native_scale = _native_model_import_scale(root, tolerance)
    selected_scale = _supported_import_scale(
        getattr(root, "spx_mmd_import_scale_override", "0.08"),
        tolerance,
    )
    if selected_scale is None:
        selected_scale = native_scale
    return selected_scale, selected_scale != native_scale


def _model_import_scale(root, tolerance=1.0e-4):
    import_scale, _overridden = _inspect_model_import_scale(root, tolerance)
    return import_scale


def _model_api():
    from ..mmd_physics import _mmd_api

    model_api, _rigid_api, _rigid_module = _mmd_api()
    return model_api


def _model_armature(root):
    return _model_api().find_armature_object(root)


def _model_motion_anchor(armature):
    return armature.matrix_world.copy()


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
                    physics_matrix.translation,
                    physics_matrix.to_quaternion(),
                    inherited.to_scale(),
                )
            else:
                inherited = physics_matrix
        resolved[pose_bone.name] = inherited
    return resolved


def _pmx_native_matrix_transform(matrix, import_scale, library=None):
    position, rotation, _object_scale = matrix.decompose()
    euler = rotation.to_euler("YXZ")
    pmx_euler = (-float(euler.x), -float(euler.z), -float(euler.y))
    export_scale = 1.0 / import_scale
    return Transform(
        Vec3.from_value(tuple(float(value) * export_scale for value in position)),
        pmx_euler_to_blender_quaternion(pmx_euler, library=library),
    )


def _pmx_native_object_transform(obj, import_scale, library=None):
    transform = _pmx_native_matrix_transform(obj.matrix_world, import_scale, library=library)
    if library is None or library.path.name != "mmd_physics_solver_mmd.dll":
        return transform
    pmx_euler = _pmx_source_euler(obj)
    return Transform(
        transform.position,
        pmx_euler_to_blender_quaternion(
            (pmx_euler.x, pmx_euler.y, pmx_euler.z),
            library=library,
        ),
    )


def _pmx_source_euler(obj):
    euler = obj.rotation_euler
    return Vec3(-float(euler.x), -float(euler.z), -float(euler.y))


def _mmd_physics_name(obj, attribute):
    value = getattr(obj, attribute)
    return value.name_j or value.name_e or obj.name


def _read_pmx_physics(path):
    data = memoryview(Path(path).read_bytes())
    offset = 0

    def read(format_string):
        nonlocal offset
        values = struct.unpack_from("<" + format_string, data, offset)
        offset += struct.calcsize("<" + format_string)
        return values[0] if len(values) == 1 else values

    def skip(size):
        nonlocal offset
        offset += size
        if offset > len(data):
            raise ValueError("PMX data is truncated")

    def text():
        nonlocal offset
        size = read("i")
        raw = bytes(data[offset:offset + size])
        offset += size
        return raw.decode(encoding, errors="replace")

    if bytes(data[:4]) != b"PMX ":
        raise ValueError("Not a PMX file")
    offset = 8
    header_size = read("B")
    header = bytes(data[offset:offset + header_size])
    skip(header_size)
    if len(header) < 8:
        raise ValueError("Invalid PMX header")
    encoding = "utf-16-le" if header[0] == 0 else "utf-8"
    additional_uvs = header[1]
    vertex_index_size = header[2]
    texture_index_size = header[3]
    material_index_size = header[4]
    bone_index_size = header[5]
    morph_index_size = header[6]
    rigid_index_size = header[7]

    model_name = text()
    text()
    text()
    text()

    for _index in range(read("i")):
        skip(32 + additional_uvs * 16)
        deform = read("B")
        if deform == 0:
            skip(bone_index_size)
        elif deform == 1:
            skip(bone_index_size * 2 + 4)
        elif deform in {2, 4}:
            skip(bone_index_size * 4 + 16)
        elif deform == 3:
            skip(bone_index_size * 2 + 40)
        else:
            raise ValueError(f"Unsupported PMX vertex deform {deform}")
        skip(4)
    skip(read("i") * vertex_index_size)
    for _index in range(read("i")):
        text()
    for _index in range(read("i")):
        text()
        text()
        skip(66 + texture_index_size * 2)
        shared_toon = read("B")
        skip(1 if shared_toon else texture_index_size)
        text()
        skip(4)
    for _index in range(read("i")):
        text()
        text()
        skip(12 + bone_index_size + 4)
        flags = read("H")
        skip(bone_index_size if flags & 0x0001 else 12)
        if flags & (0x0100 | 0x0200):
            skip(bone_index_size + 4)
        if flags & 0x0400:
            skip(12)
        if flags & 0x0800:
            skip(24)
        if flags & 0x2000:
            skip(4)
        if flags & 0x0020:
            skip(bone_index_size + 8)
            for _link in range(read("i")):
                skip(bone_index_size)
                if read("B"):
                    skip(24)
    for _index in range(read("i")):
        text()
        text()
        skip(1)
        morph_type = read("B")
        count = read("i")
        sizes = {
            0: morph_index_size + 4,
            1: vertex_index_size + 12,
            2: bone_index_size + 28,
            3: vertex_index_size + 16,
            4: vertex_index_size + 16,
            5: vertex_index_size + 16,
            6: vertex_index_size + 16,
            7: vertex_index_size + 16,
            8: material_index_size + 113,
            9: morph_index_size + 4,
            10: rigid_index_size + 25,
        }
        if morph_type not in sizes:
            raise ValueError(f"Unsupported PMX morph type {morph_type}")
        skip(count * sizes[morph_type])
    for _index in range(read("i")):
        text()
        text()
        skip(1)
        for _element in range(read("i")):
            kind = read("B")
            skip(morph_index_size if kind else bone_index_size)

    rigids = []
    for _index in range(read("i")):
        name = text()
        text()
        skip(bone_index_size + 4)
        size = read("3f")
        skip(12)
        rotation = read("3f")
        mass = read("f")
        skip(17)
        rigids.append((name, rotation, size, mass))

    joints = []
    for _index in range(read("i")):
        name = text()
        text()
        skip(1 + rigid_index_size * 2 + 12)
        rotation = read("3f")
        minimum_location = read("3f")
        maximum_location = read("3f")
        minimum_rotation = read("3f")
        maximum_rotation = read("3f")
        spring_constant = read("3f")
        spring_rotation_constant = read("3f")
        joints.append((
            name,
            rotation,
            minimum_location,
            maximum_location,
            minimum_rotation,
            maximum_rotation,
            spring_constant,
            spring_rotation_constant,
        ))
    return model_name, rigids, joints


def _load_source_physics(root, rigids, joints):
    import_folder = root.get("import_folder")
    if not import_folder:
        return None
    rigid_names = [_mmd_physics_name(obj, "mmd_rigid") for obj in rigids]
    joint_names = [_mmd_physics_name(obj, "mmd_joint") for obj in joints]
    required_rigids = Counter(rigid_names)
    required_joints = Counter(joint_names)
    candidates = []
    for path in Path(import_folder).glob("*.pmx"):
        key = (str(path), path.stat().st_mtime_ns)
        source = _SOURCE_PHYSICS_CACHE.get(key)
        if source is None:
            source = _read_pmx_physics(path)
            _SOURCE_PHYSICS_CACHE[key] = source
        model_name, source_rigids, source_joints = source
        source_rigid_counts = Counter(item[0] for item in source_rigids)
        source_joint_counts = Counter(item[0] for item in source_joints)
        if any(source_rigid_counts[name] < count for name, count in required_rigids.items()):
            continue
        if any(source_joint_counts[name] < count for name, count in required_joints.items()):
            continue
        candidates.append((
            model_name in {root.mmd_root.name, root.mmd_root.name_e},
            len(source_rigids) == len(rigids),
            len(source_joints) == len(joints),
            source_rigids,
            source_joints,
        ))
    if not candidates:
        return None
    _name_match, _rigid_count_match, _joint_count_match, source_rigids, source_joints = max(
        candidates,
        key=lambda item: item[:3],
    )

    def aligned_source_items(objects, source_items, attribute):
        by_name = defaultdict(deque)
        for item in source_items:
            by_name[item[0]].append(item)
        values = []
        for obj in objects:
            fallback = _pmx_source_euler(obj)
            matches = by_name[_mmd_physics_name(obj, attribute)]
            if not matches:
                values.append(None)
                continue
            item = matches.popleft()
            rotation = item[1]
            fallback_values = (fallback.x, fallback.y, fallback.z)
            if max(abs(a - b) for a, b in zip(fallback_values, rotation)) > 2.0e-5:
                values.append(None)
            else:
                values.append(item)
        return values

    rigid_items = aligned_source_items(
        rigids,
        source_rigids,
        "mmd_rigid",
    )
    joint_items = aligned_source_items(joints, source_joints, "mmd_joint")

    return (
        [Vec3.from_value(item[1]) if item is not None else _pmx_source_euler(obj)
         for obj, item in zip(rigids, rigid_items)],
        [Vec3.from_value(item[1]) if item is not None else _pmx_source_euler(obj)
         for obj, item in zip(joints, joint_items)],
        rigid_items,
        joint_items,
    )


def _apply_source_joint_values(descs, source_items):
    for desc, item in zip(descs, source_items):
        if item is None:
            continue
        minimum_location = item[2]
        maximum_location = item[3]
        minimum_rotation = item[4]
        maximum_rotation = item[5]
        linear_spring = item[6]
        angular_spring = item[7]
        desc.linear_lower = Vec3(
            minimum_location[0], minimum_location[2], minimum_location[1])
        desc.linear_upper = Vec3(
            maximum_location[0], maximum_location[2], maximum_location[1])
        desc.angular_upper = Vec3(
            -minimum_rotation[0], -minimum_rotation[2], -minimum_rotation[1])
        desc.angular_lower = Vec3(
            -maximum_rotation[0], -maximum_rotation[2], -maximum_rotation[1])
        desc.linear_spring = Vec3(
            linear_spring[0], linear_spring[2], linear_spring[1])
        desc.angular_spring = Vec3(
            angular_spring[0], angular_spring[2], angular_spring[1])


def _apply_source_body_values(descs, source_items, library):
    for desc, item in zip(descs, source_items):
        if item is None:
            continue
        size = item[2]
        if int(desc.shape) == 1:
            desc.size = Vec3(size[0], size[2], size[1])
        else:
            desc.size = Vec3(size[0], size[1], size[2])
        desc.mass = item[3]
        desc.transform.rotation = pmx_euler_to_blender_quaternion(
            item[1],
            library=library,
        )


def _mmd_position_roundtrip(position, bone_position):
    def float32(value):
        return ctypes.c_float(value).value

    return Vec3(
        float32(float32(position.x - bone_position.x) + bone_position.x),
        float32(float32(position.y - bone_position.y) + bone_position.y),
        float32(float32(position.z - bone_position.z) + bone_position.z),
    )


def _body_desc(obj, armature, import_scale=1.0, library=None):
    rigid = obj.mmd_rigid
    body = obj.rigid_body
    blocked = tuple(rigid.collision_group_mask)
    collision_mask = sum(1 << index for index, value in enumerate(blocked) if not value)
    pose_bone = armature.pose.bones.get(rigid.bone) if rigid.bone else None
    bone_world = armature.matrix_world @ pose_bone.matrix if pose_bone else obj.matrix_world
    object_scale = _uniform_world_scale(obj)
    export_scale = 1.0 / import_scale
    shape_size = Vector(rigid.size) * object_scale
    shape_size *= export_scale
    object_transform = _pmx_native_object_transform(obj, import_scale, library=library)
    bone_transform = _pmx_native_matrix_transform(bone_world, import_scale, library=library)
    if (
        pose_bone is not None
        and library is not None
        and library.path.name == "mmd_physics_solver_mmd.dll"
    ):
        rest_bone_world = armature.matrix_world @ pose_bone.bone.head_local
        rest_bone_position = Vec3.from_value(
            tuple(float(value) * export_scale for value in rest_bone_world)
        )
        object_transform = Transform(
            _mmd_position_roundtrip(object_transform.position, rest_bone_position),
            object_transform.rotation,
        )
    return BodyDesc(
        int(rigid.type),
        SHAPES.get(rigid.shape, 0),
        object_transform,
        bone_transform,
        int(pose_bone is not None),
        Vec3.from_value(shape_size),
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


def _scaled_vec3(value, scale):
    return Vec3.from_value(Vector((value.x, value.y, value.z)) * scale)


def _matrix_changed(first, second, epsilon=1.0e-5):
    return any(
        abs(first[row][column] - second[row][column]) > epsilon
        for row in range(4)
        for column in range(4)
    )


def _scene_time_seconds(scene):
    fps_base = float(scene.render.fps_base)
    fps = float(scene.render.fps) / fps_base if fps_base > 0.0 else 60.0
    return (float(scene.frame_current) + float(scene.frame_subframe)) / max(fps, 1.0e-6)


def _scene_is_playing(scene):
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is not None:
        for window in window_manager.windows:
            screen = window.screen
            if window.scene is scene and screen is not None and screen.is_animation_playing:
                return True
    screen = getattr(bpy.context, "screen", None)
    return bool(screen is not None and screen.is_animation_playing)


def _joint_desc(obj, body_indices, import_scale=1.0, library=None):
    constraint = obj.rigid_body_constraint
    if constraint.object1 not in body_indices or constraint.object2 not in body_indices:
        return None
    joint = obj.mmd_joint
    object_scale = _uniform_world_scale(obj)
    export_scale = 1.0 / import_scale
    linear_lower = _constraint_vector(constraint, "limit_lin_{axis}_lower")
    linear_upper = _constraint_vector(constraint, "limit_lin_{axis}_upper")
    linear_lower = _scaled_vec3(linear_lower, object_scale * export_scale)
    linear_upper = _scaled_vec3(linear_upper, object_scale * export_scale)
    return JointDesc(
        body_indices[constraint.object1],
        body_indices[constraint.object2],
        _pmx_native_object_transform(obj, import_scale, library=library),
        linear_lower,
        linear_upper,
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
        self.solver_target = settings.preview_solver_target
        self.library = default_library(self.solver_target)
        self.import_scale = _model_import_scale(root)
        self.world_scale = 1.0 / self.import_scale
        self.armature = _model_armature(root)
        if self.armature is None:
            raise RuntimeError("所选 MMD 模型没有 Armature")
        self.armature_name = self.armature.name
        self.motion_anchor_origin = _model_motion_anchor(self.armature)
        self.saved_root_matrix = root.matrix_world.copy()
        self.saved_armature_matrix = self.armature.matrix_world.copy()
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
            joint_source_eulers = []
            self.joints = []
            for joint in joint_objects:
                desc = _joint_desc(
                    joint,
                    body_indices,
                    self.import_scale,
                    library=self.library,
                )
                if desc is not None and desc.body_a != desc.body_b:
                    joint_descs.append(desc)
                    joint_source_eulers.append(_pmx_source_euler(joint))
                    self.joints.append(joint)
            self.joint_names = [joint.name for joint in self.joints]
            self.body_descs = [
                _body_desc(
                    obj,
                    self.armature,
                    self.import_scale,
                    library=self.library,
                )
                for obj in self.rigids
            ]
            self.joint_descs = joint_descs
            self.body_source_eulers = [_pmx_source_euler(obj) for obj in self.rigids]
            self.joint_source_eulers = joint_source_eulers
            source_physics = (
                _load_source_physics(self.root, self.rigids, self.joints)
                if self.solver_target == "MMD"
                else None
            )
            if source_physics is not None:
                (
                    self.body_source_eulers,
                    self.joint_source_eulers,
                    source_body_items,
                    source_joint_items,
                ) = source_physics
                _apply_source_body_values(
                    self.body_descs,
                    source_body_items,
                    self.library,
                )
                _apply_source_joint_values(self.joint_descs, source_joint_items)
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
                self.bone_drivers[bone_name] = index
        self.last_output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)
        self.auto_reset_count = 0
        self.consecutive_tick_failures = 0
        self.snapshot_reset_pending = False
        self.mmd_step_count = 0
        self.closed = False
        self.world = None
        self.solver = None
        self.body_offset = 0
        self.joint_offset = 0

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

    def rebuild_descriptors(self):
        body_indices = {obj: index for index, obj in enumerate(self.rigids)}
        self.body_descs = [
            _body_desc(
                obj,
                self.armature,
                self.import_scale,
                library=self.library,
            )
            for obj in self.rigids
        ]
        self.body_source_eulers = [_pmx_source_euler(obj) for obj in self.rigids]
        self.joint_descs = []
        self.joint_source_eulers = []
        for joint in self.joints:
            desc = _joint_desc(
                joint,
                body_indices,
                self.import_scale,
                library=self.library,
            )
            if desc is not None and desc.body_a != desc.body_b:
                self.joint_descs.append(desc)
                self.joint_source_eulers.append(_pmx_source_euler(joint))
        source_physics = (
            _load_source_physics(self.root, self.rigids, self.joints)
            if self.solver_target == "MMD"
            else None
        )
        if source_physics is not None:
            (
                self.body_source_eulers,
                self.joint_source_eulers,
                source_body_items,
                source_joint_items,
            ) = source_physics
            _apply_source_body_values(
                self.body_descs,
                source_body_items,
                self.library,
            )
            _apply_source_joint_values(self.joint_descs, source_joint_items)

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
        root_delta = self.root.matrix_world @ self.saved_root_matrix.inverted_safe()
        for name, matrix_basis in self.saved_pose_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        for name, matrix_world in self.saved_rigid_matrices.items():
            rigid = bpy.data.objects.get(name)
            if rigid is not None:
                rigid.matrix_world = root_delta @ matrix_world
        for name, matrix_world in self.saved_joint_matrices.items():
            joint = bpy.data.objects.get(name)
            if joint is not None:
                joint.matrix_world = root_delta @ matrix_world
        bpy.context.view_layer.update()

    def reset_solver(self):
        if self.closed:
            return
        self.world.reset()

    def prepare_step(self):
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
        kinematic_bone_poses = {}
        if self.solver_target == "MMD" and self.mmd_step_count >= 4:
            for index, rigid in enumerate(self.rigids):
                if int(rigid.mmd_rigid.type) != 0:
                    continue
                pose_bone = self.armature.pose.bones.get(rigid.mmd_rigid.bone)
                if pose_bone is not None and index in self.bone_offsets:
                    kinematic_bone_poses[index] = pose_bone.matrix.copy()
        for name, matrix_basis in self.saved_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        bpy.context.view_layer.update()
        self.pending_animation_pose = {
            pose_bone.name: pose_bone.matrix.copy()
            for pose_bone in self.armature.pose.bones
        }
        for index, rigid in enumerate(self.rigids):
            pose_bone = self.armature.pose.bones.get(rigid.mmd_rigid.bone)
            if pose_bone is None or index not in self.bone_offsets:
                continue
            bone_pose = kinematic_bone_poses.get(
                index,
                pose_bone.matrix,
            )
            bone_world = self.armature.matrix_world @ bone_pose
            target = _pmx_native_matrix_transform(
                bone_world,
                self.import_scale,
                library=self.library,
            )
            self.solver.set_bone_target(self.body_offset + index, target)

    def step_solver(self):
        return self.world.step()

    def apply_step(self, transforms=None, bone_transforms=None, joint_states=None):
        animation_pose = self.pending_animation_pose
        if transforms is None:
            transforms = self.solver.transforms()
            bone_transforms = self.solver.bone_transforms()
            joint_states = self.solver.joint_states()
        transforms = transforms[self.body_offset:self.body_offset + len(self.rigids)]
        bone_transforms = bone_transforms[
            self.body_offset:self.body_offset + len(self.rigids)
        ]
        joint_states = joint_states[
            self.joint_offset:self.joint_offset + len(self.joints)
        ]
        armature_inverse = self.armature.matrix_world.inverted_safe()
        bone_targets = {}
        for index, transform in enumerate(transforms):
            rigid = self.rigids[index]
            position, rotation = transform_to_components(transform)
            rigid_world = Matrix.LocRotScale(
                Vector(position) * self.import_scale,
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
                Vector(bone_position) * self.import_scale,
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
        for joint, state in zip(self.joints, joint_states):
            position_a, rotation_a = transform_to_components(state.frame_a)
            position_b, _rotation_b = transform_to_components(state.frame_b)
            position = (
                (Vector(position_a) + Vector(position_b))
                * (0.5 * self.import_scale)
            )
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
        if self.solver_target == "MMD":
            self.mmd_step_count += 1
        self.pending_animation_pose = None

    def tick(self):
        self.prepare_step()
        if self.step_solver():
            self.apply_step(*self.world.outputs())

    def close(self, restore=True):
        if self.closed:
            return
        self.closed = True
        if restore and self.armature is not None:
            self._restore_start_snapshot()
            _set_bone_connections(self.armature, self.saved_bone_connections)
            bpy.context.view_layer.update()


class PreviewWorld:
    def __init__(self, key, import_scale, solver_target, library):
        self.key = key
        self.import_scale = import_scale
        self.solver_target = solver_target
        self.library = library
        self.world_scale = 1.0
        self.sessions = []
        self.solver = None
        self.generation = 0
        self.time_driver = PreviewTimeDriver(fixed_hz=60, max_substeps=10)
        self.pending_step_seconds = None

    def add(self, session):
        self.sessions.append(session)
        session.world = self

    def remove(self, session):
        self.sessions.remove(session)
        session.world = None
        session.solver = None

    def reset(self, prepared_session=None):
        bodies = []
        joints = []
        body_source_eulers = []
        joint_source_eulers = []
        for session in self.sessions:
            if session is not prepared_session:
                session._restore_start_snapshot()
                session.rebuild_descriptors()
            session.body_offset = len(bodies)
            session.joint_offset = len(joints)
            bodies.extend(session.body_descs)
            body_source_eulers.extend(session.body_source_eulers)
            for desc in session.joint_descs:
                adjusted = JointDesc.from_buffer_copy(desc)
                adjusted.body_a += session.body_offset
                adjusted.body_b += session.body_offset
                joints.append(adjusted)
            joint_source_eulers.extend(session.joint_source_eulers)
        solver = Solver(
            bodies,
            joints,
            self.world_scale,
            library=self.library,
            body_source_eulers=body_source_eulers,
            joint_source_eulers=joint_source_eulers,
        )
        solver.set_gravity(self.sessions[0].settings.preview_gravity)
        old_solver = self.solver
        self.solver = solver
        for session in self.sessions:
            session.solver = solver
            session.last_output_basis = {
                pose_bone.name: pose_bone.matrix_basis.copy()
                for pose_bone in session.armature.pose.bones
            }
            session.last_frame = (
                session.scene.frame_current,
                session.scene.frame_subframe,
            )
            session.mmd_step_count = 0
        if old_solver is not None:
            old_solver.close()
        self.time_driver.reset()
        self.pending_step_seconds = None
        self.generation += 1

    def step(self):
        settings = self.sessions[0].settings
        step_seconds = self.pending_step_seconds
        self.pending_step_seconds = None
        if step_seconds is None:
            step_seconds = 1.0 / 60.0
        if step_seconds <= 0.0:
            return False
        self.solver.step(step_seconds, settings.preview_substeps)
        return True

    def sample_time(self, wall_seconds):
        scene = self.sessions[0].scene
        self.time_driver.max_substeps = max(
            int(self.sessions[0].settings.preview_substeps),
            1,
        )
        decision = self.time_driver.sample(
            scene_seconds=_scene_time_seconds(scene),
            wall_seconds=wall_seconds,
            playing=_scene_is_playing(scene),
        )
        if decision.reset_required:
            self.reset()
            decision = self.time_driver.sample(
                scene_seconds=_scene_time_seconds(scene),
                wall_seconds=wall_seconds,
                playing=_scene_is_playing(scene),
            )
        self.pending_step_seconds = decision.step_seconds
        return decision

    def outputs(self):
        return (
            self.solver.transforms(),
            self.solver.bone_transforms(),
            self.solver.joint_states(),
        )

    def close(self):
        if self.solver is not None:
            self.solver.close()
            self.solver = None


def is_running(root=None):
    if root is None:
        return bool(_ACTIVE_SESSIONS)
    return root.name in _ACTIVE_SESSIONS


def suspend_for_undo_redo():
    global _RUNTIME_SUSPENDED
    _RUNTIME_SUSPENDED = bool(_ACTIVE_SESSIONS)
    return _RUNTIME_SUSPENDED


def suspend_for_runtime_switch(root):
    global _RUNTIME_SUSPENDED
    session = _ACTIVE_SESSIONS.get(root.name) if root is not None else None
    if session is None:
        return None
    previous_suspended = _RUNTIME_SUSPENDED
    _RUNTIME_SUSPENDED = True
    session._rebind_blender_data()
    for name, matrix_basis in session.saved_pose_basis.items():
        pose_bone = session.armature.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.matrix_basis = matrix_basis
    session.armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    return session, previous_suspended


def resume_after_runtime_switch(token):
    global _RUNTIME_SUSPENDED
    if token is None:
        return None
    session, previous_suspended = token
    try:
        session._rebind_blender_data()
    finally:
        _RUNTIME_SUSPENDED = previous_suspended
    return session


def resume_after_undo_redo():
    global _RUNTIME_SUSPENDED
    rebound = 0
    try:
        for session in tuple(_ACTIVE_SESSIONS.values()):
            if session._rebind_blender_data():
                rebound += 1
    finally:
        _RUNTIME_SUSPENDED = False
    return rebound


def active_session_info():
    return tuple(
        (
            session.root_name,
            session.import_scale,
            session.world_scale,
            session.root.spx_mmd_interaction_group_id,
            session.solver_target,
        )
        for session in _ACTIVE_SESSIONS.values()
    )


def preview_roots(scene):
    def sort_key(obj):
        try:
            model_id = int(obj.get("spx_mmd_preview_id", 0))
        except (TypeError, ValueError):
            model_id = 0
        return (model_id <= 0, model_id if model_id > 0 else 0, obj.name.casefold())

    return tuple(
        sorted(
            (
                obj
                for obj in scene.objects
                if getattr(obj, "mmd_type", "") == "ROOT"
            ),
            key=sort_key,
        )
    )


def ensure_preview_model_ids(scene):
    roots = preview_roots(scene)
    used = set()
    missing = []
    newly_assigned = set()
    for root in roots:
        try:
            model_id = int(root.get("spx_mmd_preview_id", 0))
        except (TypeError, ValueError):
            model_id = 0
        if model_id > 0 and model_id not in used:
            used.add(model_id)
        else:
            missing.append(root)

    next_id = max(int(scene.get("spx_mmd_next_preview_id", 1)), max(used, default=0) + 1)
    for root in missing:
        while next_id in used:
            next_id += 1
        root["spx_mmd_preview_id"] = next_id
        newly_assigned.add(root.name)
        used.add(next_id)
        next_id += 1
    if int(scene.get("spx_mmd_next_preview_id", 0)) != next_id:
        scene["spx_mmd_next_preview_id"] = next_id

    valid_groups = {str(model_id) for model_id in used}
    for root in roots:
        native_scale = _native_model_import_scale(root)
        if _supported_import_scale(root.get("spx_mmd_import_scale")) != native_scale:
            root["spx_mmd_import_scale"] = native_scale
        selected_scale = _supported_import_scale(getattr(root, "spx_mmd_import_scale_override", None))
        if not root.get("spx_mmd_scale_user_selected") or selected_scale is None:
            if selected_scale != native_scale:
                root["spx_mmd_scale_assignment"] = True
                try:
                    root.spx_mmd_import_scale_override = f"{native_scale:g}"
                finally:
                    del root["spx_mmd_scale_assignment"]
        own_id = str(int(root["spx_mmd_preview_id"]))
        if (
            root.name in newly_assigned
            or getattr(root, "spx_mmd_interaction_group_id", "") not in valid_groups
        ):
            root.spx_mmd_interaction_group_id = own_id
    return roots


def preview_model_id(root):
    try:
        model_id = int(root.get("spx_mmd_preview_id", 0))
    except (TypeError, ValueError):
        return None
    return model_id if model_id > 0 else None


def renumber_preview_models(scene):
    if is_running():
        raise RuntimeError("请先停止全部物理预览，再重新排序模型编号")
    roots = ensure_preview_model_ids(scene)
    previous = tuple(
        (
            root,
            int(root["spx_mmd_preview_id"]),
            root.spx_mmd_interaction_group_id,
        )
        for root in roots
    )
    id_map = {
        old_id: new_id
        for new_id, (_root, old_id, _group_id) in enumerate(previous, 1)
    }
    for new_id, (root, _old_id, _group_id) in enumerate(previous, 1):
        root["spx_mmd_preview_id"] = new_id
    scene["spx_mmd_next_preview_id"] = len(previous) + 1
    for new_id, (root, _old_id, old_group_id) in enumerate(previous, 1):
        try:
            mapped_group_id = id_map.get(int(old_group_id), new_id)
        except (TypeError, ValueError):
            mapped_group_id = new_id
        root.spx_mmd_interaction_group_id = str(mapped_group_id)
    return roots


@persistent
def _ensure_preview_model_ids_after_load(_dummy):
    for scene in bpy.data.scenes:
        try:
            ensure_preview_model_ids(scene)
        except (AttributeError, RuntimeError):
            pass


@persistent
def _ensure_preview_model_ids_after_update(scene, _depsgraph):
    try:
        ensure_preview_model_ids(scene)
    except (AttributeError, RuntimeError):
        pass


def _ensure_preview_model_ids_deferred():
    try:
        scenes = tuple(bpy.data.scenes)
    except AttributeError:
        return 0.1
    for scene in scenes:
        try:
            ensure_preview_model_ids(scene)
        except (AttributeError, RuntimeError):
            pass
    return None


def register_model_id_service():
    if _ensure_preview_model_ids_after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ensure_preview_model_ids_after_load)
    if _ensure_preview_model_ids_after_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_ensure_preview_model_ids_after_update)
    if not bpy.app.timers.is_registered(_ensure_preview_model_ids_deferred):
        bpy.app.timers.register(_ensure_preview_model_ids_deferred, first_interval=0.0)


def unregister_model_id_service():
    if bpy.app.timers.is_registered(_ensure_preview_model_ids_deferred):
        bpy.app.timers.unregister(_ensure_preview_model_ids_deferred)
    if _ensure_preview_model_ids_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ensure_preview_model_ids_after_load)
    if _ensure_preview_model_ids_after_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_ensure_preview_model_ids_after_update)


def model_scale_info(root):
    import_scale, overridden = _inspect_model_import_scale(root)
    return import_scale, 1.0 / import_scale, overridden


def _start_preview(context, root):
    settings = context.scene.surface_proxy_creator
    stop_preview(root=root, restore=True)
    session = PreviewSession(context.scene, settings, root)
    interaction_group = root.spx_mmd_interaction_group_id
    world_key = (
        "group",
        session.solver_target,
        session.import_scale,
        interaction_group,
    )
    world = _ACTIVE_WORLDS.get(world_key)
    if world is None:
        world = PreviewWorld(
            world_key,
            session.import_scale,
            session.solver_target,
            session.library,
        )
        _ACTIVE_WORLDS[world_key] = world
    world.add(session)
    try:
        world.reset(prepared_session=session)
    except Exception:
        world.remove(session)
        session.close(restore=True)
        if not world.sessions:
            world.close()
            _ACTIVE_WORLDS.pop(world_key, None)
        raise
    _ACTIVE_SESSIONS[root.name] = session
    settings.preview_running = True
    settings.preview_status = f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
    if not bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.register(_timer_tick, first_interval=0.0)
    return session


def start_preview(context):
    settings = context.scene.surface_proxy_creator
    ensure_preview_model_ids(context.scene)
    if settings.preview_scope == "CURRENT_PROXY":
        roots = (settings.mmd_root,) if settings.mmd_root is not None else ()
    else:
        roots = tuple(
            root
            for root in preview_roots(context.scene)
            if root.spx_physics_preview_selected
        )
    if not roots:
        raise RuntimeError("请至少勾选一个 MMD 模型")
    for root in roots:
        if getattr(root, "mmd_type", "") != "ROOT":
            raise RuntimeError(f"{root.name} 不是 MMD Root")
        _model_import_scale(root)
    roots = tuple(root for root in roots if not is_running(root))
    if not roots:
        raise RuntimeError("勾选的 MMD 模型均已在预览")
    started = []
    try:
        for root in roots:
            started.append(_start_preview(context, root))
    except Exception:
        for session in started:
            stop_preview(root=session.root, restore=True)
        raise
    return tuple(started)


def stop_preview(root=None, restore=True):
    global _STEP_EXECUTOR
    if root is None:
        sessions = list(_ACTIVE_SESSIONS.values())
        _ACTIVE_SESSIONS.clear()
        worlds = list(_ACTIVE_WORLDS.values())
        _ACTIVE_WORLDS.clear()
        for world in worlds:
            world.close()
    else:
        session = _ACTIVE_SESSIONS.pop(root.name, None)
        sessions = [session] if session is not None else []
    for session in sessions:
        world = session.world
        if world is not None:
            world.remove(session)
        session.close(restore=restore)
        if root is not None and world is not None:
            if world.sessions:
                world.reset()
            else:
                world.close()
                _ACTIVE_WORLDS.pop(world.key, None)
        if session.settings is not None:
            session.settings.preview_running = bool(_ACTIVE_SESSIONS)
            session.settings.preview_status = (
                f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
                if _ACTIVE_SESSIONS
                else "已停止"
            )
    if not _ACTIVE_SESSIONS and bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)
    if not _ACTIVE_SESSIONS and _STEP_EXECUTOR is not None:
        _STEP_EXECUTOR.shutdown(wait=True)
        _STEP_EXECUTOR = None


def reset_preview(root):
    session = _ACTIVE_SESSIONS.get(root.name) if root is not None else None
    if session is None:
        raise RuntimeError("物理预览尚未启动")
    session.world.reset()
    session.settings.preview_status = "运行中：已恢复启动快照并重置物理"
    return session


def reset_all_previews():
    if not _ACTIVE_WORLDS:
        raise RuntimeError("物理预览尚未启动")
    for world in tuple(_ACTIVE_WORLDS.values()):
        world.reset()
    for session in _ACTIVE_SESSIONS.values():
        session.settings.preview_status = "运行中：已恢复全部启动快照并重置物理"
    return tuple(_ACTIVE_SESSIONS.values())


def _timer_tick(_wall_seconds=None):
    if not _ACTIVE_SESSIONS:
        return None
    if _RUNTIME_SUSPENDED:
        return 1.0 / 60.0
    wall_seconds = time.perf_counter() if _wall_seconds is None else float(_wall_seconds)
    if len(_ACTIVE_SESSIONS) > 1:
        return _timer_tick_parallel(tuple(_ACTIVE_SESSIONS.values()), wall_seconds)
    intervals = []
    for session in list(_ACTIVE_SESSIONS.values()):
        intervals.append(_timer_tick_session(session, wall_seconds))
    return min(intervals)


def _step_executor():
    global _STEP_EXECUTOR
    if _STEP_EXECUTOR is None:
        _STEP_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, os.cpu_count() or 1),
            thread_name_prefix="mmd-physics",
        )
    return _STEP_EXECUTOR


def _recover_tick_failure(session, error, interval):
    traceback.print_exception(type(error), error, error.__traceback__)
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


def _timer_tick_parallel(sessions, wall_seconds):
    intervals = {
        session: 1.0 / max(session.settings.preview_frequency, 1)
        for session in sessions
    }
    prepared = []
    for world in tuple(dict.fromkeys(session.world for session in sessions)):
        try:
            world.sample_time(wall_seconds)
        except Exception as error:
            session = world.sessions[0]
            _recover_tick_failure(session, error, intervals[session])
    for attempt in range(2):
        prepared.clear()
        generations = {world: world.generation for world in _ACTIVE_WORLDS.values()}
        for session in sessions:
            try:
                if session.snapshot_reset_pending:
                    session.reset_solver()
                    session.snapshot_reset_pending = False
                    session.settings.preview_status = "运行中：已恢复启动快照并继续物理"
                session.prepare_step()
                prepared.append(session)
            except Exception as error:
                _recover_tick_failure(session, error, intervals[session])
        if not any(world.generation != generation for world, generation in generations.items()):
            break
        if attempt == 1:
            return min(intervals.values())
    worlds = tuple(dict.fromkeys(session.world for session in prepared))
    futures = {
        _step_executor().submit(world.step): world
        for world in worlds
    }
    stepped_worlds = []
    for future, world in futures.items():
        try:
            if future.result():
                stepped_worlds.append(world)
        except Exception as error:
            session = world.sessions[0]
            _recover_tick_failure(session, error, intervals[session])
    for world in stepped_worlds:
        try:
            outputs = world.outputs()
            for session in prepared:
                if session.world is world:
                    session.apply_step(*outputs)
                    session.consecutive_tick_failures = 0
        except Exception as error:
            session = world.sessions[0]
            _recover_tick_failure(session, error, intervals[session])
    return min(intervals.values())


def _timer_tick_session(session, wall_seconds):
    interval = 1.0 / max(session.settings.preview_frequency, 1)
    try:
        session.world.sample_time(wall_seconds)
    except Exception as error:
        return _recover_tick_failure(session, error, interval)
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
        return _recover_tick_failure(session, error, interval)
    return interval
