import re

import bpy
from bpy.types import Operator
from mathutils import Euler, Matrix, Vector

from .mmd_naming import (
    normalize_mmd_indices,
    normalized_mmd_names,
    set_ordered_object_name,
)


class MirrorPhysicsError(RuntimeError):
    pass


_SIDE_SUFFIX = re.compile(r"^(.*)(\.L|\.R|_L|_R)((?:[._-].*)?)$")
_MIRROR_COPY_SUFFIX = re.compile(r"^(.*)_M$")
_REFLECT_X = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))


def mirrored_name(name):
    value = str(name or "")
    match = _SIDE_SUFFIX.match(value)
    if match:
        prefix, marker, tail = match.groups()
        replacements = {".L": ".R", ".R": ".L", "_L": "_R", "_R": "_L"}
        return f"{prefix}{replacements[marker]}{tail}"
    if value.startswith("左"):
        return f"右{value[1:]}"
    if value.startswith("右"):
        return f"左{value[1:]}"
    copy_match = _MIRROR_COPY_SUFFIX.match(value)
    if copy_match:
        return copy_match.group(1)
    return f"{value}_M" if value else None


def _side(name):
    value = str(name or "")
    match = _SIDE_SUFFIX.match(value)
    if match:
        return "L" if match.group(2) in {".L", "_L"} else "R"
    if value.startswith("左"):
        return "L"
    if value.startswith("右"):
        return "R"
    if _MIRROR_COPY_SUFFIX.match(value):
        return "M"
    return None


def mirrored_world_matrix(obj, armature):
    local = armature.matrix_world.inverted_safe() @ obj.matrix_world
    return armature.matrix_world @ (_REFLECT_X @ local @ _REFLECT_X)


def mirrored_bounds(lower, upper, signs):
    mirrored_lower = []
    mirrored_upper = []
    for low, high, sign in zip(lower, upper, signs):
        if sign < 0.0:
            mirrored_lower.append(-high)
            mirrored_upper.append(-low)
        else:
            mirrored_lower.append(low)
            mirrored_upper.append(high)
    return Vector(mirrored_lower), Vector(mirrored_upper)


def _rigid_names(source, armature, bone_name):
    pose_bone = armature.pose.bones.get(bone_name)
    fallback_j = pose_bone.mmd_bone.name_j if pose_bone else ""
    fallback_e = pose_bone.mmd_bone.name_e if pose_bone else ""
    source_side = _source_side(source)
    if source_side in {"L", "R"}:
        source_j = source.mmd_rigid.name_j
        source_e = source.mmd_rigid.name_e
        name_j = (
            mirrored_name(source_j)
            if source_j
            else fallback_j or mirrored_name(source_j or source.name)
        )
        name_e = (
            mirrored_name(source_e)
            if source_e
            else fallback_e or mirrored_name(source_e or source_j or source.name)
        )
    else:
        base_j = source.mmd_rigid.name_j or source.name
        base_e = source.mmd_rigid.name_e or base_j
        name_j = mirrored_name(base_j)
        name_e = mirrored_name(base_e)
    return normalized_mmd_names(name_j, name_e, bone_name)


def _mirror_bone(source, armature):
    source_name = source.mmd_rigid.bone
    side = _side(source_name)
    if side in {"L", "R"}:
        bone_name = mirrored_name(source_name)
        return bone_name if bone_name in armature.data.bones else None
    return source_name if source_name in armature.data.bones else None


def _find_mirror_rigid(source, rigids, armature, allow_shared=False):
    bone_name = _mirror_bone(source, armature)
    if bone_name is None:
        if allow_shared:
            local_x = (armature.matrix_world.inverted_safe() @ source.matrix_world).translation.x
            if abs(local_x) <= 1.0e-5:
                return source
        return None
    candidates = [
        rigid
        for rigid in rigids
        if rigid != source and rigid.mmd_rigid.bone == bone_name
    ]
    name_j, name_e = _rigid_names(source, armature, bone_name)
    source_name_j = str(source.mmd_rigid.name_j or "")
    source_name_e = str(source.mmd_rigid.name_e or "")
    if source_name_j:
        candidates = [
            rigid for rigid in candidates if rigid.mmd_rigid.name_j == name_j
        ]
    elif source_name_e:
        candidates = [
            rigid for rigid in candidates if rigid.mmd_rigid.name_e == name_e
        ]
    else:
        candidates = [
            rigid
            for rigid in candidates
            if rigid.mmd_rigid.name_j == name_j
            or rigid.mmd_rigid.name_e == name_e
        ]
    if not candidates:
        if allow_shared and _source_side(source) is None:
            return source
        return None
    candidates.sort(
        key=lambda rigid: (
            rigid.mmd_rigid.name_j != name_j,
            rigid.mmd_rigid.name_e != name_e,
            int(rigid.mmd_rigid.type) != int(source.mmd_rigid.type),
            rigid.mmd_rigid.shape != source.mmd_rigid.shape,
            rigid.name,
        )
    )
    return candidates[0]


def _copy_rigid(source, target, armature, bone_name):
    source_body = source.rigid_body
    target_body = target.rigid_body
    if source_body is None or target_body is None:
        raise MirrorPhysicsError("刚体缺少 Blender Rigid Body 数据")
    name_j, name_e = _rigid_names(source, armature, bone_name)
    target.mmd_rigid.name_j = name_j
    target.mmd_rigid.name_e = name_e
    set_ordered_object_name(target, name_j)
    target.mmd_rigid.bone = bone_name
    target.mmd_rigid.type = source.mmd_rigid.type
    target.mmd_rigid.shape = source.mmd_rigid.shape
    target.mmd_rigid.size = source.mmd_rigid.size
    target.mmd_rigid.collision_group_number = source.mmd_rigid.collision_group_number
    target.mmd_rigid.collision_group_mask = list(source.mmd_rigid.collision_group_mask)
    target_body.mass = source_body.mass
    target_body.friction = source_body.friction
    target_body.restitution = source_body.restitution
    target_body.linear_damping = source_body.linear_damping
    target_body.angular_damping = source_body.angular_damping
    target.matrix_world = mirrored_world_matrix(source, armature)


def _create_mirror_rigid(
    context,
    source,
    armature,
    rigid_group,
    FnRigidBody,
    rigid_module,
):
    bone_name = _mirror_bone(source, armature)
    if bone_name is None:
        raise MirrorPhysicsError(f"无法识别镜像骨骼：{source.mmd_rigid.bone or source.name}")
    body = source.rigid_body
    if body is None:
        raise MirrorPhysicsError(f"刚体缺少 Blender Rigid Body 数据：{source.name}")
    name_j, name_e = _rigid_names(source, armature, bone_name)
    target = FnRigidBody.new_rigid_body_objects(context, rigid_group, 1)[0]
    try:
        target = FnRigidBody.setup_rigid_body_object(
            obj=target,
            shape_type=rigid_module.shapeType(source.mmd_rigid.shape),
            location=source.location,
            rotation=source.rotation_euler,
            size=Vector(source.mmd_rigid.size),
            dynamics_type=int(source.mmd_rigid.type),
            name=name_j,
            name_e=name_e,
            collision_group_number=source.mmd_rigid.collision_group_number,
            collision_group_mask=list(source.mmd_rigid.collision_group_mask),
            mass=body.mass,
            friction=body.friction,
            bounce=body.restitution,
            linear_damping=body.linear_damping,
            angular_damping=body.angular_damping,
            bone=bone_name,
        )
        target.matrix_world = mirrored_world_matrix(source, armature)
        return target
    except Exception:
        if target.name in bpy.data.objects:
            bpy.data.objects.remove(target, do_unlink=True)
        raise


def _joint_names(source, rigid_b):
    horizontal_j = str(source.mmd_joint.name_j).endswith("_H")
    horizontal_e = str(source.mmd_joint.name_e).endswith("_H")
    source_j = str(source.mmd_joint.name_j)
    source_e = str(source.mmd_joint.name_e)
    name_j = mirrored_name(source_j[:-2] if horizontal_j else source_j)
    name_e = mirrored_name(source_e[:-2] if horizontal_e else source_e)
    fallback_j = rigid_b.mmd_rigid.name_j or rigid_b.name
    fallback_e = rigid_b.mmd_rigid.name_e or rigid_b.name
    name_j, name_e = normalized_mmd_names(
        name_j or fallback_j,
        name_e or fallback_e,
        rigid_b.mmd_rigid.bone,
    )
    return (
        f"{name_j}_H" if horizontal_j else name_j,
        f"{name_e}_H" if horizontal_e else name_e,
    )


def _joint_endpoints(joint):
    constraint = joint.rigid_body_constraint
    if constraint is None or constraint.object1 is None or constraint.object2 is None:
        return None
    return constraint.object1, constraint.object2


def _find_mirror_joint(source, joints, rigid_a, rigid_b):
    candidates = []
    target_names = _joint_names(source, rigid_b)
    for joint in joints:
        if joint == source:
            continue
        endpoints = _joint_endpoints(joint)
        if endpoints is None or set(endpoints) != {rigid_a, rigid_b}:
            continue
        candidates.append(joint)
    if not candidates:
        return None
    candidates.sort(
        key=lambda joint: (
            _joint_endpoints(joint) != (rigid_a, rigid_b),
            joint.mmd_joint.name_j != target_names[0],
            joint.mmd_joint.name_e != target_names[1],
            joint.name,
        )
    )
    return candidates[0]


def _copy_constraint_flags(source, target):
    names = ["enabled", "disable_collisions", "use_override_solver_iterations", "solver_iterations"]
    for axis in "xyz":
        names.extend(
            (
                f"use_limit_lin_{axis}",
                f"use_limit_ang_{axis}",
                f"use_spring_{axis}",
                f"use_spring_ang_{axis}",
                f"spring_damping_{axis}",
                f"spring_damping_ang_{axis}",
            )
        )
    for name in names:
        if hasattr(source, name) and hasattr(target, name):
            setattr(target, name, getattr(source, name))


def _joint_parameters(source):
    constraint = source.rigid_body_constraint
    linear_lower = Vector(tuple(getattr(constraint, f"limit_lin_{axis}_lower") for axis in "xyz"))
    linear_upper = Vector(tuple(getattr(constraint, f"limit_lin_{axis}_upper") for axis in "xyz"))
    angular_lower = Vector(tuple(getattr(constraint, f"limit_ang_{axis}_lower") for axis in "xyz"))
    angular_upper = Vector(tuple(getattr(constraint, f"limit_ang_{axis}_upper") for axis in "xyz"))
    linear_lower, linear_upper = mirrored_bounds(
        linear_lower,
        linear_upper,
        (-1.0, 1.0, 1.0),
    )
    angular_lower, angular_upper = mirrored_bounds(
        angular_lower,
        angular_upper,
        (1.0, -1.0, -1.0),
    )
    return linear_lower, linear_upper, angular_lower, angular_upper


def _copy_joint(source, target, armature, rigid_a, rigid_b):
    source_constraint = source.rigid_body_constraint
    target_constraint = target.rigid_body_constraint
    if source_constraint is None or target_constraint is None:
        raise MirrorPhysicsError("镜像 Joint 缺少 Rigid Body Constraint")
    linear_lower, linear_upper, angular_lower, angular_upper = _joint_parameters(source)
    name_j, name_e = _joint_names(source, rigid_b)
    target.mmd_joint.name_j = name_j
    target.mmd_joint.name_e = name_e
    set_ordered_object_name(target, name_j, joint=True)
    target_constraint.object1 = rigid_a
    target_constraint.object2 = rigid_b
    for axis, lower, upper in zip("xyz", linear_lower, linear_upper):
        setattr(target_constraint, f"limit_lin_{axis}_lower", lower)
        setattr(target_constraint, f"limit_lin_{axis}_upper", upper)
    for axis, lower, upper in zip("xyz", angular_lower, angular_upper):
        setattr(target_constraint, f"limit_ang_{axis}_lower", lower)
        setattr(target_constraint, f"limit_ang_{axis}_upper", upper)
    target.mmd_joint.spring_linear = source.mmd_joint.spring_linear
    target.mmd_joint.spring_angular = source.mmd_joint.spring_angular
    _copy_constraint_flags(source_constraint, target_constraint)
    target.matrix_world = mirrored_world_matrix(source, armature)


def _create_mirror_joint(
    context,
    source,
    armature,
    rigid_a,
    rigid_b,
    joint_group,
    root,
    FnModel,
    FnRigidBody,
):
    linear_lower, linear_upper, angular_lower, angular_upper = _joint_parameters(source)
    name_j, name_e = _joint_names(source, rigid_b)
    target = FnRigidBody.new_joint_objects(
        context,
        joint_group,
        1,
        FnModel.get_empty_display_size(root),
    )[0]
    try:
        target = FnRigidBody.setup_joint_object(
            obj=target,
            name=name_j,
            name_e=name_e,
            location=source.location,
            rotation=source.rotation_euler,
            rigid_a=rigid_a,
            rigid_b=rigid_b,
            maximum_location=linear_upper,
            minimum_location=linear_lower,
            maximum_rotation=Euler(angular_upper, "XYZ"),
            minimum_rotation=Euler(angular_lower, "XYZ"),
            spring_angular=Vector(source.mmd_joint.spring_angular),
            spring_linear=Vector(source.mmd_joint.spring_linear),
        )
        _copy_constraint_flags(source.rigid_body_constraint, target.rigid_body_constraint)
        target.matrix_world = mirrored_world_matrix(source, armature)
        return target
    except Exception:
        if target.name in bpy.data.objects:
            bpy.data.objects.remove(target, do_unlink=True)
        raise


def _source_side(obj):
    if obj.mmd_type == "RIGID_BODY":
        return _side(obj.mmd_rigid.bone) or _side(obj.mmd_rigid.name_j) or _side(obj.mmd_rigid.name_e)
    endpoints = _joint_endpoints(obj)
    return (
        _side(obj.mmd_joint.name_j)
        or _side(obj.mmd_joint.name_e)
        or (_source_side(endpoints[1]) if endpoints else None)
    )


def _canonical_sources(objects, counterpart):
    selected = set(objects)
    result = []
    for source in objects:
        target = counterpart(source)
        if target in selected and _source_side(source) in {"R", "M"}:
            continue
        result.append(source)
    return result


def _checked_objects(settings, kind):
    from .mmd_physics import _checked_items

    expected = "RIGID_BODY" if kind == "RIGID" else "JOINT"
    return [
        obj
        for item in _checked_items(settings, kind)
        if (obj := bpy.data.objects.get(item.target_name)) is not None
        and obj.mmd_type == expected
    ]


def _refresh_targets(settings, target_names):
    bpy.ops.surface_proxy.refresh_mmd_browser()
    visible = 0
    for index, item in enumerate(settings.browser_items):
        item.selected = item.target_name in target_names
        if item.selected:
            settings.browser_index = index
            visible += 1
    return visible


def _run(context, create):
    from .mmd_physics import _mmd_api, _resolve_root

    settings = context.scene.surface_proxy_creator
    kind = settings.browser_kind
    if kind not in {"RIGID", "JOINT"}:
        raise MirrorPhysicsError("请切换到刚体或 Joint 页")
    sources = _checked_objects(settings, kind)
    if not sources:
        raise MirrorPhysicsError("没有勾选刚体" if kind == "RIGID" else "没有勾选 Joint")
    root = _resolve_root(context, settings.mmd_root)
    FnModel, FnRigidBody, rigid_module = _mmd_api()
    armature = FnModel.find_armature_object(root)
    if armature is None:
        raise MirrorPhysicsError("当前 MMD 模型没有骨架")
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    rigid_group = FnModel.ensure_rigid_group_object(context, root)
    joint_group = FnModel.ensure_joint_group_object(context, root)
    rigids = list(FnModel.iterate_rigid_body_objects(root))
    joints = list(FnModel.iterate_joint_objects(root))
    created_rigids = created_joints = synced_rigids = synced_joints = existing = skipped = 0
    target_objects = set()
    source_to_target = {}

    def rigid_counterpart(source):
        return _find_mirror_rigid(source, rigids, armature)

    if kind == "RIGID":
        sources = _canonical_sources(sources, rigid_counterpart)
        for source in sources:
            bone_name = _mirror_bone(source, armature)
            if bone_name is None:
                skipped += 1
                continue
            target = _find_mirror_rigid(source, rigids, armature)
            if create:
                if target is None:
                    target = _create_mirror_rigid(
                        context,
                        source,
                        armature,
                        rigid_group,
                        FnRigidBody,
                        rigid_module,
                    )
                    rigids.append(target)
                    created_rigids += 1
                else:
                    existing += 1
            elif target is None:
                skipped += 1
                continue
            else:
                _copy_rigid(source, target, armature, bone_name)
                synced_rigids += 1
            source_to_target[source] = target
            target_objects.add(target)

        if settings.mirror_include_joints:
            selected_set = set(sources)
            associated = [
                joint
                for joint in joints
                if (endpoints := _joint_endpoints(joint)) is not None
                and endpoints[1] in selected_set
            ]

            def joint_counterpart(source):
                endpoints = _joint_endpoints(source)
                if endpoints is None:
                    return None
                target_a = source_to_target.get(endpoints[0]) or _find_mirror_rigid(
                    endpoints[0], rigids, armature, allow_shared=True
                )
                target_b = source_to_target.get(endpoints[1]) or _find_mirror_rigid(
                    endpoints[1], rigids, armature, allow_shared=True
                )
                if target_a is None or target_b is None:
                    return None
                return _find_mirror_joint(source, joints, target_a, target_b)

            associated = _canonical_sources(associated, joint_counterpart)
            for source in associated:
                endpoints = _joint_endpoints(source)
                target_a = source_to_target.get(endpoints[0]) or _find_mirror_rigid(
                    endpoints[0], rigids, armature, allow_shared=True
                )
                target_b = source_to_target.get(endpoints[1]) or _find_mirror_rigid(
                    endpoints[1], rigids, armature, allow_shared=True
                )
                if target_a is None or target_b is None:
                    skipped += 1
                    continue
                target = _find_mirror_joint(source, joints, target_a, target_b)
                if create:
                    if target is None:
                        target = _create_mirror_joint(
                            context,
                            source,
                            armature,
                            target_a,
                            target_b,
                            joint_group,
                            root,
                            FnModel,
                            FnRigidBody,
                        )
                        joints.append(target)
                        created_joints += 1
                    else:
                        existing += 1
                elif target is None:
                    skipped += 1
                else:
                    _copy_joint(source, target, armature, target_a, target_b)
                    synced_joints += 1
    else:
        def joint_counterpart(source):
            endpoints = _joint_endpoints(source)
            if endpoints is None:
                return None
            target_a = _find_mirror_rigid(endpoints[0], rigids, armature, allow_shared=True)
            target_b = _find_mirror_rigid(endpoints[1], rigids, armature, allow_shared=True)
            if target_a is None or target_b is None:
                return None
            return _find_mirror_joint(source, joints, target_a, target_b)

        sources = _canonical_sources(sources, joint_counterpart)
        for source in sources:
            endpoints = _joint_endpoints(source)
            if endpoints is None:
                skipped += 1
                continue
            target_a = _find_mirror_rigid(endpoints[0], rigids, armature, allow_shared=True)
            target_b = _find_mirror_rigid(endpoints[1], rigids, armature, allow_shared=True)
            if target_a is None or target_b is None:
                skipped += 1
                continue
            target = _find_mirror_joint(source, joints, target_a, target_b)
            if create:
                if target is None:
                    target = _create_mirror_joint(
                        context,
                        source,
                        armature,
                        target_a,
                        target_b,
                        joint_group,
                        root,
                        FnModel,
                        FnRigidBody,
                    )
                    joints.append(target)
                    created_joints += 1
                else:
                    existing += 1
            elif target is None:
                skipped += 1
                continue
            else:
                _copy_joint(source, target, armature, target_a, target_b)
                synced_joints += 1
            target_objects.add(target)

    context.view_layer.update()
    if create and (created_rigids or created_joints):
        normalize_mmd_indices(root, FnModel)
    target_names = {target.name for target in target_objects}
    _refresh_targets(settings, target_names)
    return {
        "created_rigids": created_rigids,
        "created_joints": created_joints,
        "synced_rigids": synced_rigids,
        "synced_joints": synced_joints,
        "existing": existing,
        "skipped": skipped,
    }


def _report(operator, result, create):
    if create:
        message = (
            f"已创建 {result['created_rigids']} 个镜像刚体、"
            f"{result['created_joints']} 个镜像 Joint；"
            f"已存在 {result['existing']} 项，跳过 {result['skipped']} 项"
        )
    else:
        message = (
            f"已同步 {result['synced_rigids']} 个镜像刚体、"
            f"{result['synced_joints']} 个镜像 Joint；"
            f"跳过 {result['skipped']} 项"
        )
    operator.report({"INFO"}, message)


class SPX_OT_CreateMirroredMMDItems(Operator):
    bl_idname = "surface_proxy.create_mirrored_mmd_items"
    bl_label = "创建镜像刚体/Joint"
    bl_description = "根据勾选源项创建镜像对象，并重新映射骨骼与刚体端点"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = _run(context, True)
        except (MirrorPhysicsError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        _report(self, result, True)
        return {"FINISHED"}


class SPX_OT_SyncMirroredMMDItems(Operator):
    bl_idname = "surface_proxy.sync_mirrored_mmd_items"
    bl_label = "同步镜像刚体/Joint"
    bl_description = "把勾选源项的参数按镜像坐标和轴向换算后同步到已有镜像对象"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = _run(context, False)
        except (MirrorPhysicsError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        _report(self, result, False)
        return {"FINISHED"}


def draw_mirror_tools(layout, settings):
    if settings.browser_kind not in {"RIGID", "JOINT"}:
        return
    label = "刚体" if settings.browser_kind == "RIGID" else "Joint"
    box = layout.box()
    box.label(text=f"镜像{label}", icon="MOD_MIRROR")
    if settings.browser_kind == "RIGID":
        box.prop(settings, "mirror_include_joints")
    row = box.row(align=True)
    row.operator(
        SPX_OT_CreateMirroredMMDItems.bl_idname,
        text=f"创建镜像{label}",
        icon="DUPLICATE",
    )
    row.operator(
        SPX_OT_SyncMirroredMMDItems.bl_idname,
        text=f"同步镜像{label}",
        icon="FILE_REFRESH",
    )
    box.label(text="仅处理当前列表已勾选的源项", icon="INFO")
    box.label(text="无左右标识时使用 _M 作为镜像配对后缀", icon="INFO")


CLASSES = (
    SPX_OT_CreateMirroredMMDItems,
    SPX_OT_SyncMirroredMMDItems,
)
