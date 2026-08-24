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
from .debug_batch import (
    PreviewDebugBatch,
    cleanup_debug_batch,
    cleanup_stale_debug_batches,
)
from .display_rig import (
    PreviewDisplayRig,
    cleanup_display_rig,
    cleanup_stale_display_rigs,
)
from .pose_pipeline import PoseInputAdapter
from .time_driver import PreviewDeadlineScheduler, PreviewTimeDriver


SHAPES = {"SPHERE": 0, "BOX": 1, "CAPSULE": 2}
SUPPORTED_IMPORT_SCALES = (0.08, 0.1)
_ACTIVE_SESSIONS = {}
_ACTIVE_WORLDS = {}
_STEP_EXECUTOR = None
_SOURCE_PHYSICS_CACHE = {}
_RUNTIME_SUSPENDED = False
_MIN_TIMER_DELAY = 0.001
_VIEW_LAYER_UPDATE_DEPTH = 0
_TIMER_DEADLINE = PreviewDeadlineScheduler(minimum_delay=_MIN_TIMER_DELAY)
_DISPLAY_RIG_SAVE_SUSPENSION = None


class PreviewSessionInvalidError(RuntimeError):
    pass


def _live_object(reference):
    if reference is None:
        return None
    try:
        return (
            reference
            if bpy.data.objects.get(reference.name) is reference
            else None
        )
    except (AttributeError, ReferenceError, TypeError):
        return None


def _live_scene(reference):
    if reference is None:
        return None
    try:
        return (
            reference
            if bpy.data.scenes.get(reference.name) is reference
            else None
        )
    except (AttributeError, ReferenceError, TypeError):
        return None


def _owner_view_layer(scene, preferred_name="", required_object=None):
    candidates = []
    if preferred_name:
        preferred = scene.view_layers.get(preferred_name)
        if preferred is not None:
            candidates.append(preferred)
    context_scene = getattr(bpy.context, "scene", None)
    context_view_layer = getattr(bpy.context, "view_layer", None)
    if context_scene is scene and context_view_layer is not None:
        candidate = scene.view_layers.get(context_view_layer.name)
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    candidates.extend(
        view_layer
        for view_layer in scene.view_layers
        if view_layer not in candidates
    )
    for view_layer in candidates:
        if (
            required_object is None
            or view_layer.objects.get(required_object.name) is required_object
        ):
            return view_layer
        with bpy.context.temp_override(scene=scene, view_layer=view_layer):
            view_layer.update()
        if view_layer.objects.get(required_object.name) is required_object:
            return view_layer
    raise PreviewSessionInvalidError("物理预览对象在所属 Scene 的所有 View Layer 中均不可用")


def _update_view_layer(scene, view_layer):
    global _VIEW_LAYER_UPDATE_DEPTH
    _VIEW_LAYER_UPDATE_DEPTH += 1
    try:
        with bpy.context.temp_override(scene=scene, view_layer=view_layer):
            view_layer.update()
    finally:
        _VIEW_LAYER_UPDATE_DEPTH -= 1


def _tag_view3d_redraw():
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


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


def _restore_view_layer_context(
    view_layer,
    active,
    selected,
    mode,
    active_bone_name,
):
    current = view_layer.objects.active
    if current is not None and current.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in tuple(view_layer.objects):
        try:
            if obj.select_get():
                obj.select_set(False)
        except ReferenceError:
            continue
    for obj in selected:
        try:
            if view_layer.objects.get(obj.name) is obj:
                obj.select_set(True)
        except ReferenceError:
            continue
    try:
        active_available = (
            active is not None
            and view_layer.objects.get(active.name) is active
        )
    except ReferenceError:
        active_available = False
    view_layer.objects.active = active if active_available else None
    if active_available and mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass
    if (
        active_available
        and active.type == "ARMATURE"
        and active_bone_name
        and active_bone_name in active.data.bones
    ):
        active.data.bones.active = active.data.bones[active_bone_name]


def _set_bone_connections(scene, view_layer, armature, values):
    if not values:
        return
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        previous_active = view_layer.objects.active
        previous_mode = (
            previous_active.mode if previous_active is not None else "OBJECT"
        )
        previous_selection = tuple(
            obj for obj in view_layer.objects if obj.select_get()
        )
        previous_active_bone = None
        if previous_active is not None and previous_active.type == "ARMATURE":
            active_bone = previous_active.data.bones.active
            previous_active_bone = (
                active_bone.name if active_bone is not None else None
            )
        previous_hide_select = armature.hide_select
        previous_hidden = armature.hide_get(view_layer=view_layer)
        try:
            if previous_active is not None and previous_mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for obj in previous_selection:
                obj.select_set(False)
            armature.hide_select = False
            armature.hide_set(False, view_layer=view_layer)
            armature.select_set(True)
            view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="EDIT")
            for name, use_connect in values.items():
                edit_bone = armature.data.edit_bones.get(name)
                if edit_bone is not None and edit_bone.parent is not None:
                    edit_bone.use_connect = use_connect
            bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            try:
                if armature.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
            except (ReferenceError, RuntimeError):
                pass
            try:
                armature.select_set(False)
            except (ReferenceError, RuntimeError):
                pass
            try:
                armature.hide_select = previous_hide_select
            except (AttributeError, ReferenceError):
                pass
            try:
                armature.hide_set(previous_hidden, view_layer=view_layer)
            except (ReferenceError, RuntimeError):
                pass
            _restore_view_layer_context(
                view_layer,
                previous_active,
                previous_selection,
                previous_mode,
                previous_active_bone,
            )


def _set_session_bone_connections(session, values):
    if not values:
        return
    setter = getattr(session, "set_bone_connections", None)
    if callable(setter):
        setter(values)
        return
    scene = session.scene
    view_layer = _owner_view_layer(
        scene,
        getattr(session, "view_layer_name", ""),
        required_object=session.armature,
    )
    _set_bone_connections(scene, view_layer, session.armature, values)


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


def _resolve_hierarchical_bone_targets(
    armature,
    animation_pose,
    physics_targets,
    ordered_bones=None,
):
    resolved = {}
    if ordered_bones is None:
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
    if first == second:
        return False
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
        self.scene_name = scene.name
        self.settings = settings
        self.root = root
        self.root_name = root.name
        try:
            self.root_preview_id = int(root.get("spx_mmd_preview_id", 0))
        except (TypeError, ValueError):
            self.root_preview_id = 0
        self.preview_scope = settings.preview_scope
        self.solver_target = settings.preview_solver_target
        self.library = default_library(self.solver_target)
        self.import_scale = _model_import_scale(root)
        self.world_scale = 1.0 / self.import_scale
        self.armature = _model_armature(root)
        if self.armature is None:
            raise RuntimeError("所选 MMD 模型没有 Armature")
        self.armature_name = self.armature.name
        context_scene = getattr(bpy.context, "scene", None)
        context_view_layer = getattr(bpy.context, "view_layer", None)
        preferred_view_layer = (
            context_view_layer.name
            if context_scene is scene and context_view_layer is not None
            else ""
        )
        self.view_layer_name = _owner_view_layer(
            scene,
            preferred_view_layer,
            required_object=self.armature,
        ).name
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
        self.saved_rigid_objects = {
            rigid.name: rigid for rigid in all_rigids
        }
        self.saved_joint_matrices = {
            joint.name: joint.matrix_world.copy() for joint in all_joints
        }
        self.saved_joint_objects = {
            joint.name: joint for joint in all_joints
        }
        self.rigid_debug_scales = {
            rigid: rigid.matrix_world.to_scale().copy() for rigid in all_rigids
        }
        self.joint_debug_scales = {
            joint: joint.matrix_world.to_scale().copy() for joint in all_joints
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
                self.scene,
                self.owner_view_layer(required_object=self.armature),
                self.armature,
                {name: False for name in self.saved_bone_connections},
            )
            self.update_view_layer()
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
            self.set_bone_connections(self.saved_bone_connections)
            self.update_view_layer()
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
        self._refresh_hotpath_bindings()
        self.last_output_basis = self._capture_driver_basis()
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
        self.display_rig = None
        self.debug_batch = None
        self.debug_batch_unavailable = False
        self._debug_batch_exit_pending = False
        self._debug_batch_validation_pending = False
        self._debug_batch_validation_depth = 0
        self._debug_batch_usable_cache = False
        self._debug_rigid_matrices = {}
        self._debug_joint_matrices = {}
        self.display_rig_unavailable = False
        self._display_rig_validation_depth = 0
        self._display_rig_valid_cache = False
        self.isolated_output_was_active = False
        self._native_pose_provider_compatible = False
        self._mmd_ik_direct_pose_active = False
        self._direct_pose_bones_cache = ()
        self.canonical_output_dirty = False
        self.pose_input = PoseInputAdapter(self)
        self._scene_object_count = len(scene.objects)
        self._binding_ids = frozenset((*self.rigids, *self.joints))
        self._binding_names_dirty = False

    def owner_view_layer(self, required_object=None):
        view_layer = _owner_view_layer(
            self.scene,
            getattr(self, "view_layer_name", ""),
            required_object=required_object,
        )
        self.view_layer_name = view_layer.name
        return view_layer

    def update_view_layer(self):
        _update_view_layer(self.scene, self.owner_view_layer())

    def set_bone_connections(self, values):
        _set_bone_connections(
            self.scene,
            self.owner_view_layer(required_object=self.armature),
            self.armature,
            values,
        )

    def _refresh_hotpath_bindings(self):
        self._direct_pose_bones_cache = ()
        self._pose_target_batch_solver = None
        self._pose_target_batches = {}
        pose_bones = self.armature.pose.bones
        self.rigid_modes = tuple(int(rigid.mmd_rigid.type) for rigid in self.rigids)
        self.rigid_pose_bones = tuple(
            pose_bones.get(rigid.mmd_rigid.bone)
            if rigid.mmd_rigid.bone
            else None
            for rigid in self.rigids
        )
        self.driver_pose_bones = {
            name: pose_bones.get(name)
            for name in self.bone_drivers
        }
        self.driver_depths = {
            name: _bone_depth(pose_bone)
            for name, pose_bone in self.driver_pose_bones.items()
            if pose_bone is not None
        }
        required_pose_bones = {}
        for pose_bone in self.driver_pose_bones.values():
            while pose_bone is not None:
                required_pose_bones[pose_bone.name] = pose_bone
                pose_bone = pose_bone.parent
        self.ordered_pose_bones = tuple(
            sorted(required_pose_bones.values(), key=_bone_depth)
        )
        if hasattr(self, "pose_input"):
            self.pose_input.refresh_bindings()

    def _capture_driver_basis(self):
        return {
            name: pose_bone.matrix_basis.copy()
            for name, pose_bone in self.driver_pose_bones.items()
            if pose_bone is not None
        }

    def _isolated_runtime_compatible(self):
        return (
            self.preview_scope == "CURRENT_PROXY"
            and (
                not self.pose_input.native_input_active
                or self._native_pose_provider_compatible
            )
            and len(_ACTIVE_SESSIONS) == 1
            and _ACTIVE_SESSIONS.get(self.root_name) is self
            and self.world is not None
            and len(self.world.sessions) == 1
        )

    def _optimized_input_enabled(self):
        return bool(
            self._isolated_runtime_compatible()
            and (self.solver_target != "MMD" or self.mmd_step_count >= 4)
        )

    @property
    def isolated_output_active(self):
        display_rig = self.display_rig
        if display_rig is None:
            return False
        if self._display_rig_validation_depth:
            return self._display_rig_valid_cache
        return display_rig.valid

    @property
    def presentation_armature(self):
        if self.isolated_output_active:
            return self.display_rig.armature
        return self.armature

    def _display_rig_runtime_allowed(self, interactive, compatible):
        return bool(
            interactive
            and compatible
            and (
                not bpy.app.background
                or getattr(self, "_force_display_rig_for_tests", False)
            )
        )

    def _activate_debug_batch(self):
        if self.debug_batch is not None:
            return self.debug_batch.usable
        if self.armature.mode != "POSE" or self.debug_batch_unavailable:
            return False
        try:
            batch = PreviewDebugBatch.create(self)
        except Exception:
            self.debug_batch_unavailable = True
            traceback.print_exc()
            return False
        if batch is None:
            self.debug_batch_unavailable = True
            return False
        try:
            self.debug_batch = batch
            self.debug_batch_unavailable = False
            self._debug_batch_validation_pending = False
            self._debug_rigid_matrices = {
                rigid: rigid.matrix_world.copy()
                for rigid in batch.source_rigids
            }
            self._debug_joint_matrices = {
                joint: joint.matrix_world.copy()
                for joint in batch.source_joints
            }
            batch.update_all(
                self._debug_rigid_matrices,
                self._debug_joint_matrices,
                visible=bool(self.settings.preview_update_rigids),
            )
            self._debug_batch_usable_cache = True
        except Exception:
            traceback.print_exc()
            self._deactivate_debug_batch()
            return False
        return True

    def _sync_debug_batch_mode(self):
        if self.armature.mode != "POSE":
            if self.debug_batch is None:
                self._debug_batch_exit_pending = False
                return False
            self._debug_batch_exit_pending = True
            self.pose_input.force_debug_update = True
            return False
        self._debug_batch_exit_pending = False
        if (
            self.display_rig is not None
            and self.debug_batch is None
            and not self.debug_batch_unavailable
        ):
            return self._activate_debug_batch()
        return False

    def _deactivate_debug_batch(self):
        batch = self.debug_batch
        if batch is None:
            self._debug_batch_exit_pending = False
            return False
        try:
            for source, matrix in self._debug_rigid_matrices.items():
                if _live_object(source) is source:
                    source.matrix_world = matrix
            for source, matrix in self._debug_joint_matrices.items():
                if _live_object(source) is source:
                    source.matrix_world = matrix
            batch.close()
        except Exception:
            traceback.print_exc()
            try:
                cleanup_debug_batch(batch.owner_token)
            except Exception:
                traceback.print_exc()
        finally:
            self.debug_batch = None
            self._debug_batch_exit_pending = False
            self._debug_batch_validation_pending = False
            self._debug_batch_usable_cache = False
            self._debug_rigid_matrices = {}
            self._debug_joint_matrices = {}
        return True

    def debug_matrix_world(self, obj):
        if self.debug_batch is not None and self.debug_batch.usable:
            if obj in self._debug_rigid_matrices:
                return self._debug_rigid_matrices[obj]
            if obj in self._debug_joint_matrices:
                return self._debug_joint_matrices[obj]
        return obj.matrix_world

    def _sync_debug_batch_visibility(self):
        batch = self.debug_batch
        if batch is None or not self._debug_batch_is_usable():
            return False
        visible = bool(self.settings.preview_update_rigids)
        batch.set_visible(
            visible,
            validated=bool(self._debug_batch_validation_depth),
        )
        return visible

    def _debug_batch_is_usable(self):
        batch = self.debug_batch
        if batch is None:
            return False
        if self._debug_batch_validation_depth:
            return self._debug_batch_usable_cache
        return batch.usable

    def _refresh_debug_batch_usable_cache(self):
        batch = self.debug_batch
        if batch is None:
            self._debug_batch_usable_cache = False
        elif self._debug_batch_validation_pending:
            self._debug_batch_usable_cache = bool(batch.usable)
        return self._debug_batch_usable_cache

    def _activate_display_rig(self):
        if self.isolated_output_active or self.display_rig_unavailable:
            return False
        try:
            plan = PreviewDisplayRig.plan(self)
        except Exception:
            self.display_rig_unavailable = True
            traceback.print_exc()
            return False
        if plan is None:
            self.display_rig_unavailable = True
            return False
        previous_basis = self._capture_driver_basis()
        previous_connections = {
            name: self.armature.data.bones[name].use_connect
            for name in self.saved_bone_connections
            if name in self.armature.data.bones
        }
        previous_output_dirty = self.canonical_output_dirty
        for name, matrix_basis in self.saved_basis.items():
            pose_bone = self.driver_pose_bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        self.canonical_output_dirty = False
        self.set_bone_connections(self.saved_bone_connections)
        self.armature.update_tag(refresh={"OBJECT"})
        self.update_view_layer()
        self.pose_input.invalidate()
        display_rig = None
        try:
            display_rig = PreviewDisplayRig.create(self, plan)
            if display_rig is None:
                raise RuntimeError("DisplayRig plan could not be materialized")
            display_rig.apply_input_pose()
        except Exception:
            self.display_rig_unavailable = True
            if display_rig is not None:
                try:
                    display_rig.close()
                except Exception:
                    traceback.print_exc()
                    cleanup_display_rig(display_rig.owner_token)
            for name, matrix_basis in previous_basis.items():
                pose_bone = self.driver_pose_bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix_basis
            self.set_bone_connections(previous_connections)
            self.canonical_output_dirty = previous_output_dirty
            self.armature.update_tag(refresh={"OBJECT"})
            self.update_view_layer()
            self.pose_input.invalidate()
            traceback.print_exc()
            return True
        self.display_rig = display_rig
        self.debug_batch_unavailable = False
        self._activate_debug_batch()
        self._display_rig_valid_cache = True
        self._direct_pose_bones_cache = ()
        self.isolated_output_was_active = True
        self.pose_input.refresh_watch_bindings()
        self.pose_input.invalidate()
        self.update_view_layer()
        self.last_output_basis = self._capture_driver_basis()
        return True

    def _deactivate_display_rig(
        self,
        allow_retry=True,
        restore_source_connections=False,
    ):
        debug_changed = self._deactivate_debug_batch()
        self.debug_batch_unavailable = False
        display_rig = self.display_rig
        if display_rig is None:
            if restore_source_connections:
                self.set_bone_connections(self.saved_bone_connections)
                self.armature.update_tag(refresh={"OBJECT"})
                self.update_view_layer()
            if allow_retry:
                self.display_rig_unavailable = False
            return bool(restore_source_connections or debug_changed)
        try:
            display_rig.close()
        except Exception:
            traceback.print_exc()
            cleanup_display_rig(display_rig.owner_token)
        finally:
            self.display_rig = None
            self._display_rig_valid_cache = False
            self._direct_pose_bones_cache = ()
        self.pose_input.refresh_watch_bindings()
        connection_values = (
            self.saved_bone_connections
            if restore_source_connections
            else {name: False for name in self.saved_bone_connections}
        )
        self.set_bone_connections(connection_values)
        self.display_rig_unavailable = not allow_retry
        self.canonical_output_dirty = False
        self.last_output_basis = self._capture_driver_basis()
        self.pose_input.invalidate()
        self.armature.update_tag(refresh={"OBJECT"})
        self.update_view_layer()
        return True

    def _update_display_rig_state(self, interactive, compatible):
        debug_batch = self.debug_batch
        if debug_batch is not None:
            if not self._debug_batch_is_usable():
                self._deactivate_display_rig()
                return True
            if self._debug_batch_validation_pending:
                valid = debug_batch.valid
                if not valid:
                    self._deactivate_display_rig()
                    return True
                self._debug_batch_validation_pending = False
        if self.display_rig is not None and not self.isolated_output_active:
            self._deactivate_display_rig(allow_retry=False)
            return True
        if self.isolated_output_active and not compatible:
            self._deactivate_display_rig()
            return True
        if self._display_rig_runtime_allowed(interactive, compatible):
            return self._activate_display_rig()
        return False

    def _pose_target_pmx_euler_batch(self, excluded_indices):
        if self._pose_target_batch_solver is not self.solver:
            self._pose_target_batch_solver = self.solver
            self._pose_target_batches.clear()
        exclusion_key = frozenset(excluded_indices)
        cached = self._pose_target_batches.get(exclusion_key)
        if cached is not None:
            return cached
        bindings = tuple(
            (index, pose_bone)
            for index, pose_bone in enumerate(self.rigid_pose_bones)
            if (
                pose_bone is not None
                and index in self.bone_offsets
                and index not in exclusion_key
            )
        )
        batch = self.solver.bone_target_pmx_euler_batch(
            self.body_offset + index for index, _pose_bone in bindings
        )
        cached = bindings, batch
        self._pose_target_batches[exclusion_key] = cached
        return cached

    def _submit_pose_targets(
        self,
        pose_matrices=None,
        excluded_indices=(),
        capture_targets=True,
    ):
        if not capture_targets:
            bindings, batch = self._pose_target_pmx_euler_batch(excluded_indices)
            export_scale = 1.0 / self.import_scale
            armature_world = self.armature.matrix_world
            positions = batch.positions
            pmx_eulers = batch.pmx_eulers
            for slot, (_index, pose_bone) in enumerate(bindings):
                bone_pose = (
                    pose_matrices[pose_bone.name]
                    if pose_matrices is not None
                    else pose_bone.matrix
                )
                position, rotation, _object_scale = (
                    armature_world @ bone_pose
                ).decompose()
                euler = rotation.to_euler("YXZ")
                base = slot * 3
                positions[base] = float(position.x) * export_scale
                positions[base + 1] = float(position.y) * export_scale
                positions[base + 2] = float(position.z) * export_scale
                pmx_eulers[base] = -float(euler.x)
                pmx_eulers[base + 1] = -float(euler.z)
                pmx_eulers[base + 2] = -float(euler.y)
            batch.submit()
            return ()
        targets = [] if capture_targets else None
        submissions = []
        for index, pose_bone in enumerate(self.rigid_pose_bones):
            if (
                pose_bone is None
                or index not in self.bone_offsets
                or index in excluded_indices
            ):
                continue
            bone_pose = (
                pose_matrices[pose_bone.name]
                if pose_matrices is not None
                else pose_bone.matrix
            )
            target = _pmx_native_matrix_transform(
                self.armature.matrix_world @ bone_pose,
                self.import_scale,
                library=self.library,
            )
            submissions.append((self.body_offset + index, target))
            if capture_targets:
                targets.append((index, Transform.from_buffer_copy(target)))
        self.solver.set_bone_targets(submissions)
        return tuple(targets) if capture_targets else ()

    def _migrate_snapshot_names(
        self,
        matrices,
        objects,
        replacements,
        authoritative_objects,
    ):
        authoritative = frozenset(authoritative_objects)
        authoritative_by_name = {
            obj.name: obj for obj in authoritative
        }
        renames = []
        for old_name, reference in tuple(objects.items()):
            current = replacements.get(old_name)
            if current not in authoritative:
                current = _live_object(reference)
            if current not in authoritative:
                current = authoritative_by_name.get(old_name)
            if current is None:
                continue
            new_name = current.name
            collision = objects.get(new_name)
            if new_name != old_name and collision is not None and collision is not current:
                raise PreviewSessionInvalidError(
                    f"启动快照名称迁移发生冲突：{new_name}"
                )
            renames.append((old_name, new_name, current))
        for old_name, new_name, current in renames:
            matrix = matrices.pop(old_name, None)
            objects.pop(old_name, None)
            if matrix is not None:
                matrices[new_name] = matrix
            objects[new_name] = current

    def _migrate_cached_names(
        self,
        root,
        armature,
        rigids,
        joints,
        all_rigids=(),
        all_joints=(),
        migrate_members=False,
    ):
        new_root_name = root.name
        new_armature_name = armature.name
        collision = _ACTIVE_SESSIONS.get(new_root_name)
        if collision is not None and collision is not self:
            raise PreviewSessionInvalidError(
                f"物理预览 Session 名称迁移发生冲突：{new_root_name}"
            )
        try:
            from ..mmd_ik_runtime.evaluator import refresh_session_bindings

            refresh_session_bindings(root, armature)
        except ImportError:
            pass

        if migrate_members:
            rigid_replacements = dict(zip(self.rigid_names, rigids))
            joint_replacements = dict(zip(self.joint_names, joints))
            self._migrate_snapshot_names(
                self.saved_rigid_matrices,
                self.saved_rigid_objects,
                rigid_replacements,
                all_rigids,
            )
            self._migrate_snapshot_names(
                self.saved_joint_matrices,
                self.saved_joint_objects,
                joint_replacements,
                all_joints,
            )
        was_registered = any(
            session is self for session in _ACTIVE_SESSIONS.values()
        )
        for key, session in tuple(_ACTIVE_SESSIONS.items()):
            if session is self and key != new_root_name:
                _ACTIVE_SESSIONS.pop(key, None)
        if was_registered:
            _ACTIVE_SESSIONS[new_root_name] = self
        self.root_name = new_root_name
        self.armature_name = new_armature_name
        if migrate_members:
            self.rigid_names = [rigid.name for rigid in rigids]
            self.joint_names = [joint.name for joint in joints]
        display_rig = self.display_rig
        if display_rig is not None:
            display_rig.source_armature_name = new_armature_name

    def _resolve_bound_object(
        self,
        reference,
        stored_name,
        scene,
        label,
        authoritative_objects,
    ):
        authoritative = frozenset(authoritative_objects)
        current = _live_object(reference)
        if current not in authoritative:
            candidates = tuple(
                obj for obj in authoritative if obj.name == stored_name
            )
            current = candidates[0] if len(candidates) == 1 else None
        if current is None:
            raise PreviewSessionInvalidError(f"启动快照中的{label}已不存在")
        if scene.objects.get(current.name) is not current:
            raise PreviewSessionInvalidError(f"启动快照中的{label}已脱离原场景")
        return current

    def _resolve_root_object(self, scene, allow_recreated=False):
        def identity_matches(item):
            if item is None or getattr(item, "mmd_type", "") != "ROOT":
                return False
            try:
                preview_id = int(item.get("spx_mmd_preview_id", 0))
            except (TypeError, ValueError):
                return False
            return self.root_preview_id <= 0 or preview_id == self.root_preview_id

        current = _live_object(getattr(self, "root", None))
        if not identity_matches(current):
            current = None
        if current is None and not allow_recreated:
            raise PreviewSessionInvalidError("启动快照中的MMD Root已不存在")
        if current is None:
            current = bpy.data.objects.get(self.root_name)
        if not identity_matches(current):
            current = None
        if current is None and self.root_preview_id > 0:
            candidates = tuple(
                obj
                for obj in scene.objects
                if (
                    getattr(obj, "mmd_type", "") == "ROOT"
                    and int(obj.get("spx_mmd_preview_id", 0))
                    == self.root_preview_id
                )
            )
            if len(candidates) == 1:
                current = candidates[0]
        if current is None:
            raise PreviewSessionInvalidError("启动快照中的MMD Root已不存在")
        if scene.objects.get(current.name) is not current:
            raise PreviewSessionInvalidError("启动快照中的MMD Root已脱离原场景")
        if tuple(current.users_scene) != (scene,):
            raise PreviewSessionInvalidError(
                "Preview root must belong only to its owner scene"
            )
        return current

    def _resolve_armature_object(self, root, scene):
        current = _model_armature(root)
        if current is None:
            raise PreviewSessionInvalidError("启动快照中的Armature已不存在")
        if scene.objects.get(current.name) is not current:
            raise PreviewSessionInvalidError("启动快照中的Armature已脱离原场景")
        if tuple(current.users_scene) != (scene,):
            raise PreviewSessionInvalidError(
                "Preview armature must belong only to its owner scene"
            )
        return current

    def _binding_names_changed(self, updated_ids=None):
        if len(self.rigids) != len(self.rigid_names):
            return True
        if len(self.joints) != len(self.joint_names):
            return True
        try:
            return any(
                (updated_ids is None or obj in updated_ids) and obj.name != name
                for obj, name in zip(self.rigids, self.rigid_names)
            ) or any(
                (updated_ids is None or obj in updated_ids) and obj.name != name
                for obj, name in zip(self.joints, self.joint_names)
            )
        except ReferenceError:
            return True

    def _rebind_blender_data(self, force=False, allow_recreated=False):
        scene = _live_scene(getattr(self, "scene", None))
        if scene is None:
            scene = bpy.data.scenes.get(self.scene_name)
        if scene is None:
            raise PreviewSessionInvalidError("启动快照对应的场景已不存在")
        root = self._resolve_root_object(
            scene,
            allow_recreated=allow_recreated,
        )
        armature = self._resolve_armature_object(root, scene)
        full_rebind = bool(
            force
            or getattr(self, "_binding_names_dirty", False)
            or len(scene.objects) != getattr(self, "_scene_object_count", -1)
        )
        if full_rebind and self.debug_batch is not None:
            self._debug_batch_validation_pending = True
        if full_rebind:
            all_rigids = tuple(_rigid_objects(root))
            all_joints = tuple(_joint_objects(root))
            rigids = [
                self._resolve_bound_object(
                    reference,
                    name,
                    scene,
                    "刚体",
                    all_rigids,
                )
                for reference, name in zip(self.rigids, self.rigid_names)
            ]
            joints = [
                self._resolve_bound_object(
                    reference,
                    name,
                    scene,
                    "Joint",
                    all_joints,
                )
                for reference, name in zip(self.joints, self.joint_names)
            ]
        else:
            all_rigids = ()
            all_joints = ()
            rigids = self.rigids
            joints = self.joints
        changed = bool(
            self.scene is not scene
            or self.root is not root
            or self.armature is not armature
            or any(old is not current for old, current in zip(self.rigids, rigids))
            or any(old is not current for old, current in zip(self.joints, joints))
        )
        self._migrate_cached_names(
            root,
            armature,
            rigids,
            joints,
            all_rigids=all_rigids,
            all_joints=all_joints,
            migrate_members=full_rebind,
        )
        self.scene = scene
        self.scene_name = scene.name
        self.view_layer_name = _owner_view_layer(
            scene,
            getattr(self, "view_layer_name", ""),
            required_object=armature,
        ).name
        self.settings = scene.surface_proxy_creator
        self.root = root
        self.armature = armature
        self.rigids = rigids
        self.joints = joints
        self._scene_object_count = len(scene.objects)
        self._binding_ids = frozenset((*rigids, *joints))
        self._binding_names_dirty = False
        if changed:
            self._refresh_hotpath_bindings()
            self.pose_input.invalidate()
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
        if self.isolated_output_active:
            return False
        driver_names = self.driver_pose_bones
        current_frame = (self.scene.frame_current, self.scene.frame_subframe)
        if (
            current_frame != self.last_frame
            or not driver_names
            or not self.last_output_basis
        ):
            return False
        changed = sum(
            _matrix_changed(
                pose_bone.matrix_basis,
                self.last_output_basis[name],
            )
            for name, pose_bone in driver_names.items()
            if pose_bone is not None and name in self.last_output_basis
        )
        required = max(2, math.ceil(len(driver_names) * 0.2))
        if len(driver_names) == 1:
            required = 1
        return changed >= required

    def _restore_start_snapshot(self):
        self._rebind_blender_data(force=True)
        self.pose_input.invalidate()
        if self.isolated_output_was_active:
            for name, matrix_basis in self.saved_basis.items():
                pose_bone = self.armature.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix_basis
            self.canonical_output_dirty = False
            self._restore_debug_snapshot()
            return
        for name, matrix_basis in self.saved_pose_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        self.canonical_output_dirty = False
        self._restore_debug_snapshot()

    def _restore_authored_driver_pose(self):
        for name, matrix_basis in self.saved_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        self.canonical_output_dirty = False
        self.last_output_basis = self._capture_driver_basis()

    def _restore_debug_snapshot(self):
        root_delta = self.root.matrix_world @ self.saved_root_matrix.inverted_safe()
        authoritative_rigids = frozenset(_rigid_objects(self.root))
        authoritative_joints = frozenset(_joint_objects(self.root))
        batch = self.debug_batch
        if batch is not None and batch.valid:
            self._debug_rigid_matrices = {
                rigid: root_delta @ self.saved_rigid_matrices[name]
                for name, rigid in self.saved_rigid_objects.items()
                if _live_object(rigid) in authoritative_rigids
            }
            self._debug_joint_matrices = {
                joint: root_delta @ self.saved_joint_matrices[name]
                for name, joint in self.saved_joint_objects.items()
                if _live_object(joint) in authoritative_joints
            }
            batch.update_all(
                self._debug_rigid_matrices,
                self._debug_joint_matrices,
                visible=bool(self.settings.preview_update_rigids),
            )
            self.update_view_layer()
            return
        for name, matrix_world in self.saved_rigid_matrices.items():
            rigid = _live_object(self.saved_rigid_objects.get(name))
            if rigid in authoritative_rigids:
                rigid.matrix_world = root_delta @ matrix_world
        for name, matrix_world in self.saved_joint_matrices.items():
            joint = _live_object(self.saved_joint_objects.get(name))
            if joint in authoritative_joints:
                joint.matrix_world = root_delta @ matrix_world
        self.update_view_layer()

    def _capture_debug_state(self):
        authoritative_rigids = frozenset(_rigid_objects(self.root))
        authoritative_joints = frozenset(_joint_objects(self.root))
        batch = self.debug_batch
        if batch is not None and batch.valid:
            active_rigids = frozenset(self.rigids)
            active_joints = frozenset(self.joints)
            rigid_matrices = {
                rigid.name: (
                    matrix if rigid in active_rigids else rigid.matrix_world
                ).copy()
                for rigid, matrix in self._debug_rigid_matrices.items()
                if _live_object(rigid) in authoritative_rigids
            }
            joint_matrices = {
                joint.name: (
                    matrix if joint in active_joints else joint.matrix_world
                ).copy()
                for joint, matrix in self._debug_joint_matrices.items()
                if _live_object(joint) in authoritative_joints
            }
            return rigid_matrices, joint_matrices
        rigid_matrices = {}
        for name in self.saved_rigid_matrices:
            rigid = _live_object(self.saved_rigid_objects.get(name))
            if rigid in authoritative_rigids:
                rigid_matrices[rigid.name] = rigid.matrix_world.copy()
        joint_matrices = {}
        for name in self.saved_joint_matrices:
            joint = _live_object(self.saved_joint_objects.get(name))
            if joint in authoritative_joints:
                joint_matrices[joint.name] = joint.matrix_world.copy()
        return rigid_matrices, joint_matrices

    def _restore_debug_state(self, state):
        rigid_matrices, joint_matrices = state
        authoritative_rigids = {
            rigid.name: rigid for rigid in _rigid_objects(self.root)
        }
        authoritative_joints = {
            joint.name: joint for joint in _joint_objects(self.root)
        }
        batch = self.debug_batch
        if batch is not None and batch.valid:
            authoritative_rigid_objects = frozenset(authoritative_rigids.values())
            authoritative_joint_objects = frozenset(authoritative_joints.values())
            self._debug_rigid_matrices = {
                rigid: rigid_matrices.get(rigid.name, matrix).copy()
                for rigid, matrix in self._debug_rigid_matrices.items()
                if _live_object(rigid) in authoritative_rigid_objects
            }
            self._debug_joint_matrices = {
                joint: joint_matrices.get(joint.name, matrix).copy()
                for joint, matrix in self._debug_joint_matrices.items()
                if _live_object(joint) in authoritative_joint_objects
            }
            batch.update_all(
                self._debug_rigid_matrices,
                self._debug_joint_matrices,
                visible=bool(self.settings.preview_update_rigids),
            )
            self.update_view_layer()
            return
        for name, matrix_world in rigid_matrices.items():
            rigid = authoritative_rigids.get(name)
            if rigid is not None:
                rigid.matrix_world = matrix_world
        for name, matrix_world in joint_matrices.items():
            joint = authoritative_joints.get(name)
            if joint is not None:
                joint.matrix_world = matrix_world
        self.update_view_layer()

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
        optimized_input = self._optimized_input_enabled()
        if not optimized_input:
            self.pose_input.invalidate()
        else:
            raw_changed, driver_changed = self.pose_input.raw_input_changes()
            if (
                self.pose_input.cached_animation_pose is not None
                and not raw_changed
                and not self.pose_input.external_input_evaluated
            ):
                self.pose_input.reuse_prepared_input()
                return
            if (
                self.pose_input.cached_animation_pose is not None
                and self.pose_input.external_input_evaluated
                and self.pose_input.fast_external_input_safe
                and not driver_changed
            ):
                self.pose_input.capture_evaluated_input()
                return
        for name, matrix_basis in self.saved_basis.items():
            pose_bone = self.driver_pose_bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        self.canonical_output_dirty = False
        self.update_view_layer()
        self.pose_input.acknowledge_synchronous_evaluation()
        self.pose_input.input_evaluation_count += 1
        animation_pose = {
            pose_bone.name: pose_bone.matrix.copy()
            for pose_bone in self.pose_input.ordered_input_pose_bones
        }
        targets = self._submit_pose_targets()
        if optimized_input:
            self.pose_input.cache_prepared_input(animation_pose, targets)
            self.pending_animation_pose = self.pose_input.cached_animation_pose
        else:
            self.pending_animation_pose = animation_pose
            self.pose_input.external_input_evaluated = False

    def direct_input_pose_bones(self):
        if self._direct_pose_bones_cache:
            return self._direct_pose_bones_cache
        pose_bones = {
            pose_bone.name: pose_bone
            for pose_bone in self.pose_input.ordered_input_pose_bones
        }
        if self.isolated_output_active:
            pose_bones.update(
                (pose_bone.name, pose_bone)
                for pose_bone in self.display_rig.source_pose_bones
            )
        self._direct_pose_bones_cache = tuple(
            sorted(pose_bones.values(), key=_bone_depth)
        )
        return self._direct_pose_bones_cache

    def prepare_step_from_pose(
        self,
        pose_matrices,
        *,
        submit_targets=True,
        excluded_target_indices=(),
    ):
        if self._rebind_blender_data():
            return False
        animation_pose = pose_matrices
        self.canonical_output_dirty = False
        if submit_targets:
            self._submit_pose_targets(
                pose_matrices,
                excluded_indices=excluded_target_indices,
                capture_targets=False,
            )
        if self.isolated_output_active:
            self.display_rig.input_pose = pose_matrices
        self.pending_animation_pose = animation_pose
        self.pose_input.input_evaluation_count += 1
        return True

    def step_solver(self):
        return self.world.step()

    def apply_step(
        self,
        transforms=None,
        bone_transforms=None,
        joint_states=None,
        present_output=True,
    ):
        animation_pose = self.pending_animation_pose
        if not present_output:
            self.pose_input.mark_output(False)
            self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)
            if self.solver_target == "MMD":
                self.mmd_step_count += 1
            self.pending_animation_pose = None
            return
        asynchronous = bool(
            present_output and getattr(self, "_asynchronous_presentation", False)
        )
        deferred_evaluation = bool(
            present_output and getattr(self, "_defer_presentation_update", False)
        )
        slow_debug_requested = bool(
            getattr(self, "_debug_presentation", True)
        )
        kinematic_debug_requested = bool(
            getattr(self, "_kinematic_debug_presentation", True)
        )
        if bone_transforms is None:
            bone_transforms = self.solver.bone_transforms()
        if slow_debug_requested and transforms is None:
            transforms = self.solver.transforms()
        if slow_debug_requested and joint_states is None:
            joint_states = self.solver.joint_states()
        bone_transforms = bone_transforms[
            self.body_offset:self.body_offset + len(self.rigids)
        ]
        if transforms is not None:
            transforms = transforms[
                self.body_offset:self.body_offset + len(self.rigids)
            ]
        if joint_states is not None:
            joint_states = joint_states[
                self.joint_offset:self.joint_offset + len(self.joints)
            ]
        armature_inverse = self.armature.matrix_world.inverted_safe()
        bone_targets = {}
        type_zero_displays = []
        show_rigids = bool(
            present_output
            and (
                self.settings.preview_update_rigids
                or self._debug_batch_exit_pending
            )
        )
        update_slow_debug = bool(show_rigids and slow_debug_requested)
        update_kinematic_debug = bool(
            show_rigids and kinematic_debug_requested
        )
        debug_batch = (
            self.debug_batch
            if self._debug_batch_is_usable()
            else None
        )
        kinematic_debug_updates = {}
        slow_rigid_debug_updates = {}
        joint_debug_updates = {}
        for index, bone_transform in enumerate(bone_transforms):
            transform = transforms[index] if transforms is not None else None
            rigid = self.rigids[index]
            rigid_mode = self.rigid_modes[index]
            pose_bone = self.rigid_pose_bones[index]
            if (
                rigid_mode == 0
                and index in self.bone_offsets
                and pose_bone is not None
            ):
                if update_kinematic_debug:
                    type_zero_displays.append((index, rigid, pose_bone))
                continue
            rigid_world = None
            if update_slow_debug:
                position, rotation = transform_to_components(transform)
                rigid_world = Matrix.LocRotScale(
                    Vector(position) * self.import_scale,
                    Quaternion(rotation),
                    Vector((1.0, 1.0, 1.0)),
                )
            if rigid_mode == 0 or index not in self.bone_offsets:
                if update_slow_debug:
                    scale = self.rigid_debug_scales.get(rigid)
                    if scale is None:
                        scale = rigid.matrix_world.to_scale()
                    debug_matrix = Matrix.LocRotScale(
                        rigid_world.translation,
                        rigid_world.to_quaternion(),
                        scale,
                    )
                    if debug_batch is None:
                        rigid.matrix_world = debug_matrix
                    else:
                        slow_rigid_debug_updates[rigid] = debug_matrix
                continue
            if pose_bone is None:
                continue
            is_driver = self.bone_drivers.get(pose_bone.name) == index
            if not update_slow_debug and not is_driver:
                continue
            bone_position, bone_rotation = transform_to_components(bone_transform)
            bone_world = Matrix.LocRotScale(
                Vector(bone_position) * self.import_scale,
                Quaternion(bone_rotation),
                Vector((1.0, 1.0, 1.0)),
            )
            if update_slow_debug:
                scale = self.rigid_debug_scales.get(rigid)
                if scale is None:
                    scale = rigid.matrix_world.to_scale()
                debug_matrix = Matrix.LocRotScale(
                    rigid_world.translation,
                    rigid_world.to_quaternion(),
                    scale,
                )
                if debug_batch is None:
                    rigid.matrix_world = debug_matrix
                else:
                    slow_rigid_debug_updates[rigid] = debug_matrix
            if not is_driver:
                continue
            bone_targets[pose_bone.name] = (
                self.driver_depths[pose_bone.name],
                rigid_mode,
                bone_world,
            )
        if update_slow_debug:
            for joint, state in zip(self.joints, joint_states or ()):
                position_a, rotation_a = transform_to_components(state.frame_a)
                position_b, _rotation_b = transform_to_components(state.frame_b)
                position = (
                    (Vector(position_a) + Vector(position_b))
                    * (0.5 * self.import_scale)
                )
                scale = self.joint_debug_scales.get(joint)
                if scale is None:
                    scale = joint.matrix_world.to_scale()
                debug_matrix = Matrix.LocRotScale(
                    position,
                    Quaternion(rotation_a),
                    scale,
                )
                if debug_batch is None:
                    joint.matrix_world = debug_matrix
                else:
                    joint_debug_updates[joint] = debug_matrix
        physics_targets = {
            name: (value[1], armature_inverse @ value[2])
            for name, value in bone_targets.items()
        }
        if self.isolated_output_active:
            resolved_bones = self.display_rig.source_pose_bones
            direct_bones = self.direct_input_pose_bones()
            if type_zero_displays and all(
                pose_bone.name in animation_pose for pose_bone in direct_bones
            ):
                resolved_bones = direct_bones
            pose_targets = _resolve_hierarchical_bone_targets(
                self.armature,
                self.display_rig.input_pose,
                physics_targets,
                ordered_bones=resolved_bones,
            )
            self.display_rig.apply_resolved_pose(pose_targets)
        else:
            pose_targets = _resolve_hierarchical_bone_targets(
                self.armature,
                animation_pose,
                physics_targets,
                ordered_bones=self.ordered_pose_bones,
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
                    matrix_basis = pose_bone.bone.convert_local_to_pose(
                        pose_targets[bone_name],
                        pose_bone.bone.matrix_local,
                        invert=True,
                    )
                else:
                    parent_matrix = pose_targets[parent.name]
                    matrix_basis = pose_bone.bone.convert_local_to_pose(
                        pose_targets[bone_name],
                        pose_bone.bone.matrix_local,
                        parent_matrix=parent_matrix,
                        parent_matrix_local=parent.bone.matrix_local,
                        invert=True,
                    )
                pose_bone.matrix_basis = matrix_basis
                self.last_output_basis[bone_name] = pose_bone.matrix_basis.copy()
            self.canonical_output_dirty = bool(bone_targets)
        debug_pose_targets = pose_targets
        if type_zero_displays and any(
            pose_bone.name not in debug_pose_targets
            for _index, _rigid, pose_bone in type_zero_displays
        ):
            debug_pose_targets = _resolve_hierarchical_bone_targets(
                self.armature,
                animation_pose,
                physics_targets,
                ordered_bones=self.pose_input.ordered_input_pose_bones,
            )
        kinematic_debug_updated = bool(
            update_kinematic_debug and type_zero_displays
        )
        if present_output:
            if not (asynchronous or deferred_evaluation):
                self.update_view_layer()
            for index, rigid, pose_bone in type_zero_displays:
                bone_pose = (
                    debug_pose_targets[pose_bone.name]
                    if self.isolated_output_active
                    else pose_bone.matrix
                )
                rigid_world = (
                    self.armature.matrix_world
                    @ bone_pose
                    @ self.bone_offsets[index]
                )
                scale = self.rigid_debug_scales.get(rigid)
                if scale is None:
                    scale = rigid.matrix_world.to_scale()
                debug_matrix = Matrix.LocRotScale(
                    rigid_world.translation,
                    rigid_world.to_quaternion(),
                    scale,
                )
                if debug_batch is None:
                    rigid.matrix_world = debug_matrix
                else:
                    kinematic_debug_updates[rigid] = debug_matrix
            if debug_batch is not None:
                if kinematic_debug_updated:
                    self._debug_rigid_matrices.update(kinematic_debug_updates)
                    debug_batch.update_kinematic(
                        self._debug_rigid_matrices,
                        visible=show_rigids,
                        validated=bool(self._debug_batch_validation_depth),
                    )
                if update_slow_debug:
                    self._debug_rigid_matrices.update(slow_rigid_debug_updates)
                    self._debug_joint_matrices.update(joint_debug_updates)
                    debug_batch.update_slow(
                        self._debug_rigid_matrices,
                        self._debug_joint_matrices,
                        visible=show_rigids,
                        validated=bool(self._debug_batch_validation_depth),
                    )
                if not (kinematic_debug_updated or update_slow_debug):
                    debug_batch.set_visible(
                        show_rigids,
                        validated=bool(self._debug_batch_validation_depth),
                    )
            if asynchronous:
                _tag_view3d_redraw()
        self.pose_input.mark_output(
            present_output,
            asynchronous=asynchronous,
            debug_updated=update_slow_debug,
            kinematic_debug_updated=kinematic_debug_updated,
        )
        self.last_frame = (self.scene.frame_current, self.scene.frame_subframe)
        if self.solver_target == "MMD":
            self.mmd_step_count += 1
        self.pending_animation_pose = None

    def _finish_solver_only_step(self):
        self.pose_input.mark_output(False)
        if self.solver_target == "MMD":
            self.mmd_step_count += 1
        self.pending_animation_pose = None

    def _finish_debug_batch_mode_exit(self, refresh_output=False):
        if not self._debug_batch_exit_pending:
            return False
        refresh_error = None
        refresh_traceback = None
        try:
            if refresh_output:
                previous_asynchronous = getattr(
                    self,
                    "_asynchronous_presentation",
                    False,
                )
                previous_debug = getattr(self, "_debug_presentation", True)
                previous_kinematic = getattr(
                    self,
                    "_kinematic_debug_presentation",
                    True,
                )
                previous_mmd_step_count = self.mmd_step_count
                try:
                    self._asynchronous_presentation = False
                    self._debug_presentation = True
                    self._kinematic_debug_presentation = True
                    self.apply_step(
                        *self.world.outputs(
                            include_debug=True,
                            include_transforms=True,
                            include_joint_states=True,
                        ),
                        present_output=True,
                    )
                finally:
                    self._asynchronous_presentation = previous_asynchronous
                    self._debug_presentation = previous_debug
                    self._kinematic_debug_presentation = previous_kinematic
                    self.mmd_step_count = previous_mmd_step_count
        except Exception as error:
            refresh_error = error
            refresh_traceback = error.__traceback__
        cleanup_errors = []
        try:
            self._deactivate_debug_batch()
        except Exception as error:
            cleanup_errors.append((error, error.__traceback__))
        try:
            self.update_view_layer()
        except Exception as error:
            cleanup_errors.append((error, error.__traceback__))
        primary_error = refresh_error
        primary_traceback = refresh_traceback
        if primary_error is None and cleanup_errors:
            primary_error, primary_traceback = cleanup_errors.pop(0)
        if primary_error is not None:
            for secondary_error, _secondary_traceback in cleanup_errors:
                primary_error.add_note(
                    "Debug batch mode-exit cleanup also failed: "
                    f"{secondary_error!r}"
                )
            raise primary_error.with_traceback(primary_traceback)
        return True

    def tick(self, interactive=False):
        self._sync_debug_batch_mode()
        display_rig = self.display_rig
        self._display_rig_valid_cache = bool(
            display_rig is not None and display_rig.valid
        )
        self._display_rig_validation_depth += 1
        try:
            self._refresh_debug_batch_usable_cache()
            self._debug_batch_validation_depth += 1
            try:
                interactive = bool(
                    interactive or getattr(self, "_interactive_timer_tick", False)
                )
                self.prepare_step()
                optimized = self._optimized_input_enabled()
                compatible = self._isolated_runtime_compatible()
                if self._update_display_rig_state(interactive, compatible):
                    self.prepare_step()
                    optimized = self._optimized_input_enabled()
                if not self.step_solver():
                    self._finish_debug_batch_mode_exit(refresh_output=True)
                    return
                plan = self.pose_input.presentation_plan(
                    interactive,
                    optimized,
                )
                if self._debug_batch_exit_pending:
                    plan = plan._replace(
                        write_output=True,
                        update_debug=True,
                        update_kinematic_debug=True,
                    )
                self._sync_debug_batch_visibility()
                if not plan.write_output:
                    self._finish_solver_only_step()
                    self._finish_debug_batch_mode_exit(refresh_output=True)
                    return
                self._asynchronous_presentation = plan.asynchronous
                self._debug_presentation = plan.update_debug
                self._kinematic_debug_presentation = plan.update_kinematic_debug
                try:
                    self.apply_step(
                        *self.world.outputs(
                            include_debug=plan.update_debug,
                            include_transforms=(
                                plan.update_debug
                                or self.pose_input.native_input_active
                            ),
                        ),
                        present_output=True,
                    )
                    self._finish_debug_batch_mode_exit()
                finally:
                    self._asynchronous_presentation = False
                    self._debug_presentation = True
                    self._kinematic_debug_presentation = True
            except Exception:
                if self._debug_batch_exit_pending:
                    try:
                        self._finish_debug_batch_mode_exit()
                    except Exception:
                        traceback.print_exc()
                raise
            finally:
                self._debug_batch_validation_depth -= 1
        finally:
            self._display_rig_validation_depth -= 1

    def close(self, restore=True):
        if self.closed:
            return
        terminal_invalid = False
        try:
            self._rebind_blender_data(force=True)
        except PreviewSessionInvalidError:
            terminal_invalid = True
            restore = False
        display_rig = self.display_rig
        try:
            self._deactivate_display_rig(allow_retry=False)
        except (AttributeError, ReferenceError, PreviewSessionInvalidError):
            if not terminal_invalid:
                raise
            if display_rig is not None:
                try:
                    display_rig.close()
                except Exception:
                    traceback.print_exc()
            self.display_rig = None
            self._display_rig_valid_cache = False
            self._deactivate_debug_batch()
            if display_rig is not None:
                cleanup_display_rig(display_rig.owner_token)
        if restore and self.armature is not None:
            self._restore_start_snapshot()
            self.set_bone_connections(self.saved_bone_connections)
            self.update_view_layer()
        self.closed = True


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

    def reset(self, prepared_session=None, *, restore_snapshots=True):
        bodies = []
        joints = []
        body_source_eulers = []
        joint_source_eulers = []
        session_layouts = []
        for session in self.sessions:
            if session is not prepared_session:
                if restore_snapshots:
                    session._restore_start_snapshot()
                session.rebuild_descriptors()
            body_offset = len(bodies)
            joint_offset = len(joints)
            bodies.extend(session.body_descs)
            body_source_eulers.extend(session.body_source_eulers)
            for desc in session.joint_descs:
                adjusted = JointDesc.from_buffer_copy(desc)
                adjusted.body_a += body_offset
                adjusted.body_b += body_offset
                joints.append(adjusted)
            joint_source_eulers.extend(session.joint_source_eulers)
            session_layouts.append((session, body_offset, joint_offset))
        solver = Solver(
            bodies,
            joints,
            self.world_scale,
            library=self.library,
            body_source_eulers=body_source_eulers,
            joint_source_eulers=joint_source_eulers,
        )
        session_states = []
        try:
            solver.set_gravity(self.sessions[0].settings.preview_gravity)
            display_pose_reset = False
            for session, body_offset, joint_offset in session_layouts:
                session_states.append(
                    (
                        session,
                        body_offset,
                        joint_offset,
                        session._capture_driver_basis(),
                        (
                            session.scene.frame_current,
                            session.scene.frame_subframe,
                        ),
                    )
                )
                if session.isolated_output_active:
                    session.display_rig.capture_input_pose()
                    session.display_rig.apply_input_pose()
                    display_pose_reset = True
            if display_pose_reset:
                self.sessions[0].update_view_layer()
        except Exception:
            try:
                solver.close()
            except Exception:
                traceback.print_exc()
            raise
        old_solver = self.solver
        self.solver = solver
        for (
            session,
            body_offset,
            joint_offset,
            last_output_basis,
            last_frame,
        ) in session_states:
            session.body_offset = body_offset
            session.joint_offset = joint_offset
            session.solver = solver
            session.last_output_basis = last_output_basis
            session.last_frame = last_frame
            session.mmd_step_count = 0
            session.pose_input.invalidate()
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

    def outputs(
        self,
        include_debug=True,
        *,
        include_transforms=None,
        include_joint_states=None,
    ):
        if include_transforms is None:
            include_transforms = include_debug
        if include_joint_states is None:
            include_joint_states = include_debug
        return (
            self.solver.transforms() if include_transforms else None,
            self.solver.bone_transforms(),
            self.solver.joint_states() if include_joint_states else None,
        )

    def close(self):
        if self.solver is not None:
            self.solver.close()
            self.solver = None


def _session_for_root(root):
    if root is None:
        return None
    try:
        session = _ACTIVE_SESSIONS.get(root.name)
    except (AttributeError, ReferenceError, TypeError):
        session = None
    if (
        session is not None
        and _live_object(getattr(session, "root", None)) is root
    ):
        return session
    return next(
        (
            candidate
            for candidate in _ACTIVE_SESSIONS.values()
            if _live_object(getattr(candidate, "root", None)) is root
        ),
        None,
    )


def _remove_session_keys(session):
    for key, candidate in tuple(_ACTIVE_SESSIONS.items()):
        if candidate is session:
            _ACTIVE_SESSIONS.pop(key, None)


def _shutdown_idle_runtime():
    global _STEP_EXECUTOR
    if _ACTIVE_SESSIONS:
        return
    if bpy.app.timers.is_registered(_timer_tick):
        try:
            bpy.app.timers.unregister(_timer_tick)
        except (RuntimeError, ValueError):
            pass
    _TIMER_DEADLINE.reset()
    if _STEP_EXECUTOR is not None:
        _STEP_EXECUTOR.shutdown(wait=True)
        _STEP_EXECUTOR = None


def is_running(root=None):
    if root is None:
        return bool(_ACTIVE_SESSIONS)
    return _session_for_root(root) is not None


def _discard_unbound_session(session):
    _remove_session_keys(session)
    world = session.world
    display_rig = getattr(session, "display_rig", None)
    try:
        session.close(restore=False)
    except Exception:
        traceback.print_exc()
        remaining_display_rig = getattr(session, "display_rig", None)
        if remaining_display_rig is not None:
            display_rig = remaining_display_rig
            try:
                remaining_display_rig.close()
            except Exception:
                traceback.print_exc()
        debug_batch = getattr(session, "debug_batch", None)
        if debug_batch is not None:
            try:
                debug_batch.close()
            except Exception:
                traceback.print_exc()
                try:
                    cleanup_debug_batch(debug_batch.owner_token)
                except Exception:
                    traceback.print_exc()
        if display_rig is not None:
            cleanup_display_rig(display_rig.owner_token)
    if world is not None and session in world.sessions:
        world.remove(session)
    session.display_rig = None
    session._display_rig_valid_cache = False
    session.closed = True
    return world


def _discard_terminal_session(
    session,
    error,
    *,
    rebuild_world=True,
    restore_snapshots=True,
):
    try:
        from ..mmd_ik_runtime.evaluator import discard_session

        discard_session(
            root=getattr(session, "root", None),
            previous_root_name=getattr(session, "root_name", None),
        )
    except ImportError:
        pass
    except Exception:
        traceback.print_exc()
    world = _discard_unbound_session(session)
    if world is not None and rebuild_world:
        if world.sessions:
            try:
                world.reset(restore_snapshots=restore_snapshots)
            except Exception:
                traceback.print_exc()
                for remaining in world.sessions:
                    remaining.snapshot_reset_pending = True
        else:
            try:
                world.close()
            finally:
                _ACTIVE_WORLDS.pop(world.key, None)
    try:
        settings = session.settings
        settings.preview_running = bool(_ACTIVE_SESSIONS)
        settings.preview_status = (
            f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
            if _ACTIVE_SESSIONS
            else f"已停止：{error}"
        )
    except (AttributeError, ReferenceError):
        pass
    _shutdown_idle_runtime()
    return world


def suspend_for_undo_redo():
    global _RUNTIME_SUSPENDED
    _RUNTIME_SUSPENDED = bool(_ACTIVE_SESSIONS)
    errors = []
    failed_sessions = []
    for session in tuple(dict.fromkeys(_ACTIVE_SESSIONS.values())):
        try:
            session._deactivate_display_rig(restore_source_connections=True)
        except Exception as error:
            errors.append(error)
            failed_sessions.append((session, error))
    affected_worlds = []
    for session, error in failed_sessions:
        world = session.world
        if world is not None and world not in affected_worlds:
            affected_worlds.append(world)
        try:
            _discard_terminal_session(
                session,
                error,
                rebuild_world=False,
            )
        except Exception as cleanup_error:
            errors.append(cleanup_error)
            traceback.print_exc()
    for world in affected_worlds:
        if world.sessions:
            try:
                world.reset(restore_snapshots=False)
            except Exception as cleanup_error:
                errors.append(cleanup_error)
                traceback.print_exc()
                for remaining in world.sessions:
                    remaining.snapshot_reset_pending = True
        else:
            try:
                world.close()
            except Exception as cleanup_error:
                errors.append(cleanup_error)
                traceback.print_exc()
            finally:
                _ACTIVE_WORLDS.pop(world.key, None)
    _RUNTIME_SUSPENDED = bool(_ACTIVE_SESSIONS)
    if errors:
        raise errors[0]
    return _RUNTIME_SUSPENDED


def suspend_for_runtime_switch(root):
    global _RUNTIME_SUSPENDED
    session = _session_for_root(root)
    if session is None:
        return None
    previous_suspended = _RUNTIME_SUSPENDED
    _RUNTIME_SUSPENDED = True
    session._rebind_blender_data(force=True)
    session._deactivate_display_rig()
    session.pose_input.invalidate()
    session._restore_authored_driver_pose()
    session.armature.update_tag(refresh={"OBJECT"})
    session.update_view_layer()
    return session, previous_suspended


def resume_after_runtime_switch(token):
    global _RUNTIME_SUSPENDED
    if token is None:
        return None
    session, previous_suspended = token
    try:
        session._rebind_blender_data(force=True)
        session.pose_input.invalidate()
    finally:
        _RUNTIME_SUSPENDED = previous_suspended
    return session


def resume_after_undo_redo():
    global _RUNTIME_SUSPENDED, _STEP_EXECUTOR
    rebound = 0
    failed_sessions = []
    affected_worlds = list(
        dict.fromkeys(
            session.world
            for session in _ACTIVE_SESSIONS.values()
            if session.world is not None
        )
    )
    try:
        cleanup_stale_display_rigs()
        for session in tuple(_ACTIVE_SESSIONS.values()):
            try:
                if session._rebind_blender_data(
                    force=True,
                    allow_recreated=True,
                ):
                    rebound += 1
                _set_session_bone_connections(
                    session,
                    {name: False for name in session.saved_bone_connections}
                )
                session.display_rig_unavailable = False
                session.pose_input.invalidate()
            except Exception:
                traceback.print_exc()
                failed_sessions.append(session)
        for session in failed_sessions:
            world = _discard_unbound_session(session)
            if world is not None and world not in affected_worlds:
                affected_worlds.append(world)
        for world in affected_worlds:
            if world.sessions:
                try:
                    world.reset(restore_snapshots=False)
                except Exception:
                    traceback.print_exc()
                    for session in world.sessions:
                        session.snapshot_reset_pending = True
                else:
                    for session in world.sessions:
                        session.snapshot_reset_pending = False
            else:
                world.close()
                _ACTIVE_WORLDS.pop(world.key, None)
        running = bool(_ACTIVE_SESSIONS)
        for session in (*_ACTIVE_SESSIONS.values(), *failed_sessions):
            try:
                session.settings.preview_running = running
                session.settings.preview_status = (
                    f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
                    if running
                    else "已停止"
                )
            except (AttributeError, ReferenceError):
                pass
        if not running and bpy.app.timers.is_registered(_timer_tick):
            bpy.app.timers.unregister(_timer_tick)
        if not running:
            _TIMER_DEADLINE.reset()
            if _STEP_EXECUTOR is not None:
                _STEP_EXECUTOR.shutdown(wait=True)
                _STEP_EXECUTOR = None
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
    cleanup_stale_display_rigs()
    cleanup_stale_debug_batches()
    for scene in bpy.data.scenes:
        try:
            ensure_preview_model_ids(scene)
        except (AttributeError, RuntimeError):
            pass


@persistent
def _stop_preview_before_load(_filepath):
    global _DISPLAY_RIG_SAVE_SUSPENSION, _RUNTIME_SUSPENDED
    try:
        _resume_display_rigs_after_save(_filepath)
        stop_preview(restore=True)
    finally:
        _DISPLAY_RIG_SAVE_SUSPENSION = None
        _RUNTIME_SUSPENDED = False
        _TIMER_DEADLINE.reset()


@persistent
def _suspend_display_rigs_for_save(_filepath):
    global _DISPLAY_RIG_SAVE_SUSPENSION, _RUNTIME_SUSPENDED
    _resume_display_rigs_after_save(_filepath)
    sessions = tuple(_ACTIVE_SESSIONS.values())
    if not sessions:
        return
    previous_suspended = _RUNTIME_SUSPENDED
    session_states = []
    _DISPLAY_RIG_SAVE_SUSPENSION = (previous_suspended, session_states)
    _RUNTIME_SUSPENDED = True
    try:
        for session in sessions:
            session._rebind_blender_data(force=True)
            debug_state = session._capture_debug_state()
            session_states.append((session, session.root, debug_state))
            session._deactivate_display_rig(restore_source_connections=True)
            session._restore_authored_driver_pose()
            _set_session_bone_connections(
                session,
                session.saved_bone_connections,
            )
            session._restore_debug_snapshot()
    except Exception:
        _resume_display_rigs_after_save(_filepath)
        raise


@persistent
def _resume_display_rigs_after_save(_filepath):
    global _DISPLAY_RIG_SAVE_SUSPENSION, _RUNTIME_SUSPENDED
    suspension = _DISPLAY_RIG_SAVE_SUSPENSION
    _DISPLAY_RIG_SAVE_SUSPENSION = None
    if suspension is None:
        return
    previous_suspended, session_states = suspension
    try:
        for session, root, debug_state in session_states:
            if (
                not any(candidate is session for candidate in _ACTIVE_SESSIONS.values())
                or _live_object(getattr(session, "root", None)) is not root
            ):
                continue
            try:
                session._restore_debug_state(debug_state)
                _set_session_bone_connections(
                    session,
                    {name: False for name in session.saved_bone_connections}
                )
                session.display_rig_unavailable = False
                session.pose_input.invalidate()
            except Exception:
                session.snapshot_reset_pending = True
                traceback.print_exc()
    finally:
        _RUNTIME_SUSPENDED = previous_suspended


@persistent
def _ensure_preview_model_ids_after_update(scene, _depsgraph):
    if is_running():
        if _VIEW_LAYER_UPDATE_DEPTH:
            return
        updated_ids = {
            getattr(update.id, "original", update.id)
            for update in _depsgraph.updates
        }
        for session in tuple(_ACTIVE_SESSIONS.values()):
            if session.scene is not scene:
                continue
            session._display_rig_validation_depth += 1
            try:
                root = _live_object(getattr(session, "root", None))
                armature = _live_object(getattr(session, "armature", None))
                if root is None or armature is None:
                    continue
                binding_updates = getattr(
                    session, "_binding_ids", frozenset()
                ).intersection(updated_ids)
                if binding_updates:
                    if session._binding_names_changed(binding_updates):
                        session._binding_names_dirty = True
                        session._debug_batch_validation_pending = True
                    else:
                        try:
                            if any(not obj.hide_viewport for obj in binding_updates):
                                session._debug_batch_validation_pending = True
                        except ReferenceError:
                            session._debug_batch_validation_pending = True
                debug_batch = session.debug_batch
                if (
                    debug_batch is not None
                    and debug_batch.note_depsgraph_updates(updated_ids)
                ):
                    session._debug_batch_validation_pending = True
                observed_ids = [
                    root,
                    armature,
                    armature.data,
                ]
                display_rig = session.display_rig
                if (
                    display_rig is not None
                    and session._display_rig_valid_cache
                ):
                    try:
                        observed_ids.extend(display_rig.observed_ids)
                    except (AttributeError, ReferenceError):
                        pass
                if not any(item in updated_ids for item in observed_ids):
                    continue
                pose_input = getattr(session, "pose_input", None)
                if pose_input is None:
                    continue
                if pose_input.acknowledge_self_write():
                    raw_changed, _driver_changed = pose_input.raw_input_changes()
                    if not raw_changed:
                        continue
                pose_input.external_input_evaluated = True
            finally:
                session._display_rig_validation_depth -= 1
        return
    try:
        ensure_preview_model_ids(scene)
    except (AttributeError, RuntimeError):
        pass


def _ensure_preview_model_ids_deferred():
    try:
        scenes = tuple(bpy.data.scenes)
    except AttributeError:
        return 0.1
    cleanup_stale_display_rigs()
    cleanup_stale_debug_batches()
    for scene in scenes:
        try:
            ensure_preview_model_ids(scene)
        except (AttributeError, RuntimeError):
            pass
    return None


def register_model_id_service():
    if _stop_preview_before_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_stop_preview_before_load)
    if _ensure_preview_model_ids_after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ensure_preview_model_ids_after_load)
    if _ensure_preview_model_ids_after_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_ensure_preview_model_ids_after_update)
    if _suspend_display_rigs_for_save not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_suspend_display_rigs_for_save)
    if _resume_display_rigs_after_save not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_resume_display_rigs_after_save)
    if _resume_display_rigs_after_save not in bpy.app.handlers.save_post_fail:
        bpy.app.handlers.save_post_fail.append(_resume_display_rigs_after_save)
    if not bpy.app.timers.is_registered(_ensure_preview_model_ids_deferred):
        bpy.app.timers.register(_ensure_preview_model_ids_deferred, first_interval=0.0)


def unregister_model_id_service():
    global _DISPLAY_RIG_SAVE_SUSPENSION
    _resume_display_rigs_after_save("")
    _DISPLAY_RIG_SAVE_SUSPENSION = None
    if bpy.app.timers.is_registered(_ensure_preview_model_ids_deferred):
        bpy.app.timers.unregister(_ensure_preview_model_ids_deferred)
    if _ensure_preview_model_ids_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ensure_preview_model_ids_after_load)
    if _stop_preview_before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_stop_preview_before_load)
    if _ensure_preview_model_ids_after_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_ensure_preview_model_ids_after_update)
    if _suspend_display_rigs_for_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_suspend_display_rigs_for_save)
    if _resume_display_rigs_after_save in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_resume_display_rigs_after_save)
    if _resume_display_rigs_after_save in bpy.app.handlers.save_post_fail:
        bpy.app.handlers.save_post_fail.remove(_resume_display_rigs_after_save)
    cleanup_stale_debug_batches()


def model_scale_info(root):
    import_scale, overridden = _inspect_model_import_scale(root)
    return import_scale, 1.0 / import_scale, overridden


def _start_preview(context, root):
    settings = context.scene.surface_proxy_creator
    for active_session in tuple(_ACTIVE_SESSIONS.values()):
        active_session._deactivate_display_rig()
    stop_preview(root=root, restore=True)
    session = PreviewSession(context.scene, settings, root)
    interaction_group = root.spx_mmd_interaction_group_id
    world_key = (
        "group",
        int(session.scene.as_pointer()),
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
    except Exception as start_error:
        cleanup_errors = []
        try:
            if session in world.sessions:
                world.remove(session)
        except Exception as cleanup_error:
            cleanup_errors.append(cleanup_error)
        try:
            session.close(restore=True)
        except Exception as cleanup_error:
            cleanup_errors.append(cleanup_error)
        if world.sessions:
            try:
                world.reset(restore_snapshots=False)
            except Exception as cleanup_error:
                cleanup_errors.append(cleanup_error)
                for remaining in tuple(world.sessions):
                    try:
                        _discard_terminal_session(
                            remaining,
                            cleanup_error,
                            rebuild_world=False,
                        )
                    except Exception as discard_error:
                        cleanup_errors.append(discard_error)
                try:
                    world.close()
                except Exception as close_error:
                    cleanup_errors.append(close_error)
                finally:
                    _ACTIVE_WORLDS.pop(world_key, None)
        else:
            try:
                world.close()
            except Exception as cleanup_error:
                cleanup_errors.append(cleanup_error)
            finally:
                _ACTIVE_WORLDS.pop(world_key, None)
        for cleanup_error in cleanup_errors:
            try:
                start_error.add_note(
                    "Preview start rollback failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            except AttributeError:
                pass
        raise
    _ACTIVE_SESSIONS[root.name] = session
    settings.preview_running = True
    settings.preview_status = f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
    if not bpy.app.timers.is_registered(_timer_tick):
        _TIMER_DEADLINE.reset()
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
    errors = []
    if root is None:
        sessions = list(dict.fromkeys(_ACTIVE_SESSIONS.values()))
        _ACTIVE_SESSIONS.clear()
        worlds = list(dict.fromkeys(_ACTIVE_WORLDS.values()))
        _ACTIVE_WORLDS.clear()
    else:
        session = _session_for_root(root)
        if session is not None:
            _remove_session_keys(session)
        sessions = [session] if session is not None else []
        worlds = []
    try:
        for session in sessions:
            world = session.world
            try:
                try:
                    session.close(restore=restore)
                except PreviewSessionInvalidError:
                    session.close(restore=False)
            except Exception as error:
                errors.append(error)
                if not session.closed:
                    try:
                        session.close(restore=False)
                    except Exception as cleanup_error:
                        errors.append(cleanup_error)
            finally:
                if world is not None and session in world.sessions:
                    try:
                        world.remove(session)
                    except Exception as error:
                        errors.append(error)
                if root is not None and world is not None:
                    try:
                        if world.sessions:
                            world.reset()
                        else:
                            try:
                                world.close()
                            finally:
                                _ACTIVE_WORLDS.pop(world.key, None)
                    except Exception as error:
                        errors.append(error)
                try:
                    if session.settings is not None:
                        session.settings.preview_running = bool(_ACTIVE_SESSIONS)
                        session.settings.preview_status = (
                            f"运行中：{len(_ACTIVE_SESSIONS)} 个模型"
                            if _ACTIVE_SESSIONS
                            else "已停止"
                        )
                except (AttributeError, ReferenceError):
                    pass
        for world in worlds:
            try:
                world.close()
            except Exception as error:
                errors.append(error)
            finally:
                for session in tuple(world.sessions):
                    try:
                        world.remove(session)
                    except Exception as error:
                        errors.append(error)
    finally:
        try:
            _shutdown_idle_runtime()
        except Exception as error:
            errors.append(error)
    if errors:
        raise errors[0]


def reset_preview(root):
    session = _session_for_root(root)
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
        _TIMER_DEADLINE.reset()
        return None
    if _RUNTIME_SUSPENDED:
        _TIMER_DEADLINE.reset()
        return 1.0 / 60.0
    started = time.perf_counter()
    wall_seconds = started if _wall_seconds is None else float(_wall_seconds)
    if len(_ACTIVE_SESSIONS) > 1:
        interval = _timer_tick_parallel(tuple(_ACTIVE_SESSIONS.values()), wall_seconds)
    else:
        intervals = []
        interactive = _wall_seconds is None and not bpy.app.background
        for session in list(_ACTIVE_SESSIONS.values()):
            intervals.append(
                _timer_tick_session(
                    session,
                    wall_seconds,
                    interactive=interactive,
                )
            )
        interval = min(intervals)
    if _wall_seconds is not None:
        return interval
    return _TIMER_DEADLINE.next_delay(
        started,
        time.perf_counter(),
        interval,
    )


def _step_executor():
    global _STEP_EXECUTOR
    if _STEP_EXECUTOR is None:
        _STEP_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, os.cpu_count() or 1),
            thread_name_prefix="mmd-physics",
        )
    return _STEP_EXECUTOR


def _set_preview_status(session, status):
    try:
        session.settings.preview_status = status
    except (AttributeError, ReferenceError):
        pass


def _recover_tick_failure(session, error, interval):
    invalid_error = error if isinstance(error, PreviewSessionInvalidError) else None
    if invalid_error is None:
        try:
            session._rebind_blender_data(force=True)
        except PreviewSessionInvalidError as binding_error:
            invalid_error = binding_error
        except Exception:
            pass
    if invalid_error is not None:
        _discard_terminal_session(session, invalid_error)
        return interval
    traceback.print_exception(type(error), error, error.__traceback__)
    session.consecutive_tick_failures += 1
    session.snapshot_reset_pending = True
    try:
        session.reset_solver()
        session.snapshot_reset_pending = False
        session.auto_reset_count += 1
        _set_preview_status(
            session,
            "运行中：异常后已恢复启动快照 "
            f"({type(error).__name__}: {error})",
        )
    except Exception as recovery_error:
        traceback.print_exc()
        _set_preview_status(
            session,
            "运行中：启动快照恢复失败，将继续重试 "
            f"({type(recovery_error).__name__}: {recovery_error})",
        )
    return interval


def _timer_tick_parallel(sessions, wall_seconds):
    intervals = {}
    runnable_sessions = []
    for session in sessions:
        try:
            intervals[session] = 1.0 / max(
                session.settings.preview_frequency,
                1,
            )
        except Exception as error:
            interval = 1.0 / 60.0
            intervals[session] = interval
            _recover_tick_failure(session, error, interval)
            continue
        runnable_sessions.append(session)
    sessions = tuple(runnable_sessions)
    if not sessions:
        return min(intervals.values(), default=1.0 / 60.0)
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
                session._deactivate_display_rig()
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
        except Exception as error:
            session = next(
                item for item in prepared if item.world is world
            )
            _recover_tick_failure(session, error, intervals[session])
            continue
        for session in prepared:
            if session.world is not world:
                continue
            try:
                session.apply_step(*outputs)
                session.consecutive_tick_failures = 0
            except Exception as error:
                _recover_tick_failure(session, error, intervals[session])
                break
    return min(intervals.values())


def _timer_tick_session(session, wall_seconds, interactive=False):
    interval = 1.0 / 60.0
    try:
        interval = 1.0 / max(session.settings.preview_frequency, 1)
    except Exception as error:
        return _recover_tick_failure(session, error, interval)
    try:
        session.world.sample_time(wall_seconds)
    except Exception as error:
        return _recover_tick_failure(session, error, interval)
    if session.snapshot_reset_pending:
        try:
            session.reset_solver()
            session.snapshot_reset_pending = False
            _set_preview_status(session, "运行中：已恢复启动快照并继续物理")
        except Exception as recovery_error:
            if isinstance(recovery_error, PreviewSessionInvalidError):
                return _recover_tick_failure(session, recovery_error, interval)
            traceback.print_exc()
            _set_preview_status(
                session,
                "运行中：启动快照恢复失败，将继续重试 "
                f"({type(recovery_error).__name__}: {recovery_error})",
            )
            return interval
    try:
        session._interactive_timer_tick = interactive
        try:
            session.tick()
        finally:
            session._interactive_timer_tick = False
        session.consecutive_tick_failures = 0
    except Exception as error:
        return _recover_tick_failure(session, error, interval)
    return interval
