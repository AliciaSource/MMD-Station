import importlib
from dataclasses import dataclass

import bpy
from mathutils import Euler, Matrix, Vector

from ..collection_organization import place_mmd_objects
from ..mmd_naming import bone_mmd_names, normalize_mmd_indices
from .selection import restore_bone_selection, selected_bones_from_view


class BonePhysicsError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildResult:
    selected: int
    created_rigids: int
    reused_rigids: int
    created_joints: int
    skipped_joints: int
    created_rigid_names: tuple
    created_joint_names: tuple


def _mmd_api():
    try:
        model_module = importlib.import_module("bl_ext.blender_org.mmd_tools.core.model")
        rigid_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.rigid_body"
        )
    except ImportError as error:
        raise BonePhysicsError("需要先安装并启用官方 mmd_tools 扩展") from error
    return model_module.FnModel, rigid_module.FnRigidBody, rigid_module


def _resolve_model(settings):
    root = settings.mmd_root
    if root is None or getattr(root, "mmd_type", "") != "ROOT":
        raise BonePhysicsError("请先选择 MMD 模型")
    FnModel, FnRigidBody, rigid_module = _mmd_api()
    armature = FnModel.find_armature_object(root)
    if armature is None:
        raise BonePhysicsError("当前 MMD 模型没有骨架")
    return root, armature, FnModel, FnRigidBody, rigid_module


def resolve_armature(settings):
    _root, armature, _FnModel, _FnRigidBody, _rigid_module = _resolve_model(settings)
    return armature


def _bone_geometry(bone):
    head = bone.head_local.copy()
    tail = bone.tail_local.copy()
    direction = tail - head
    length = direction.length
    if length <= 1.0e-7:
        raise BonePhysicsError(f"骨骼长度为零：{bone.name}")
    direction.normalize()
    tangent = bone.x_axis.copy()
    tangent -= direction * tangent.dot(direction)
    if tangent.length <= 1.0e-7:
        tangent = direction.orthogonal()
    tangent.normalize()
    normal = direction.cross(tangent).normalized()
    rotation = Matrix((tangent, normal, direction)).transposed().to_euler("YXZ")
    return head, tail, length, rotation


def _rigid_size(settings, length):
    radius = max(length * settings.bone_creator_radius_ratio, 0.001)
    rigid_length = max(length * settings.bone_creator_length_ratio, 0.001)
    depth = max(length * settings.bone_creator_depth_ratio, 0.001)
    if settings.bone_creator_shape == "SPHERE":
        return Vector((radius, 0.0, 0.0))
    if settings.bone_creator_shape == "BOX":
        return Vector((radius, depth, rigid_length * 0.5))
    radius = min(radius, rigid_length * 0.45)
    return Vector((radius, max(rigid_length - radius * 2.0, 0.001), 0.0))


def _pmx_name(bone_name):
    return bone_name[:16]


def _rigids_by_bone(FnModel, root):
    result = {}
    for rigid in FnModel.iterate_rigid_body_objects(root):
        bone_name = str(rigid.mmd_rigid.bone)
        if bone_name:
            result.setdefault(bone_name, []).append(rigid)
    for values in result.values():
        values.sort(key=lambda obj: obj.name)
    return result


def _existing_joint_pairs(FnModel, root):
    pairs = set()
    for joint in FnModel.iterate_joint_objects(root):
        constraint = joint.rigid_body_constraint
        if constraint is None or constraint.object1 is None or constraint.object2 is None:
            continue
        pairs.add(frozenset((constraint.object1.name, constraint.object2.name)))
    return pairs


def _preferred_rigid(candidates, dynamics_type=None):
    if dynamics_type is not None:
        exact = [
            rigid
            for rigid in candidates
            if int(rigid.mmd_rigid.type) == dynamics_type
        ]
        if exact:
            return exact[0]
    return candidates[0]


def _create_rigid(
    context,
    settings,
    bone,
    dynamics_type,
    rigid_group,
    armature,
    FnRigidBody,
    rigid_module,
):
    head, tail, length, rotation = _bone_geometry(bone)
    rigid = FnRigidBody.new_rigid_body_objects(context, rigid_group, 1)[0]
    pose_bone = armature.pose.bones[bone.name]
    name, name_e = (
        _pmx_name(value) for value in bone_mmd_names(pose_bone, bone.name)
    )
    return FnRigidBody.setup_rigid_body_object(
        obj=rigid,
        shape_type=rigid_module.shapeType(settings.bone_creator_shape),
        location=(head + tail) * 0.5,
        rotation=rotation,
        size=_rigid_size(settings, length),
        dynamics_type=dynamics_type,
        name=name,
        name_e=name_e,
        collision_group_number=settings.bone_creator_collision_group,
        collision_group_mask=list(settings.bone_creator_collision_mask),
        mass=settings.bone_creator_mass,
        friction=settings.bone_creator_friction,
        bounce=settings.bone_creator_restitution,
        linear_damping=settings.bone_creator_linear_damping,
        angular_damping=settings.bone_creator_angular_damping,
        bone=bone.name,
    )


def _create_joint(
    context,
    settings,
    child_bone,
    rigid_a,
    rigid_b,
    joint_group,
    armature,
    root,
    FnModel,
    FnRigidBody,
):
    joint = FnRigidBody.new_joint_objects(
        context,
        joint_group,
        1,
        FnModel.get_empty_display_size(root),
    )[0]
    pose_bone = armature.pose.bones[child_bone.name]
    name, name_e = (
        _pmx_name(value) for value in bone_mmd_names(pose_bone, child_bone.name)
    )
    return FnRigidBody.setup_joint_object(
        obj=joint,
        name=name,
        name_e=name_e,
        location=child_bone.head_local,
        rotation=rigid_b.rotation_euler.copy(),
        rigid_a=rigid_a,
        rigid_b=rigid_b,
        maximum_location=Vector(settings.bone_creator_limit_linear_upper),
        minimum_location=Vector(settings.bone_creator_limit_linear_lower),
        maximum_rotation=Euler(settings.bone_creator_limit_angular_upper, "XYZ"),
        minimum_rotation=Euler(settings.bone_creator_limit_angular_lower, "XYZ"),
        spring_angular=Vector(settings.bone_creator_spring_angular),
        spring_linear=Vector(settings.bone_creator_spring_linear),
    )


def create_from_selected(context, settings, mode):
    root, armature, FnModel, FnRigidBody, rigid_module = _resolve_model(settings)
    selected_names, active_name = selected_bones_from_view(context, armature)
    original_mode = armature.mode
    if original_mode not in {"POSE", "EDIT"}:
        raise BonePhysicsError("请在骨架 Edit Mode 或 Pose Mode 中选择骨骼")
    if original_mode == "EDIT":
        bpy.ops.object.mode_set(mode="OBJECT")
    else:
        bpy.ops.object.mode_set(mode="OBJECT")

    created_objects = []
    created_rigids = 0
    reused_rigids = 0
    created_joints = 0
    skipped_joints = 0
    created_rigid_objects = []
    created_joint_objects = []
    try:
        selected_bones = [armature.data.bones[name] for name in selected_names]
        rigid_group = FnModel.ensure_rigid_group_object(context, root)
        joint_group = FnModel.ensure_joint_group_object(context, root)
        place_mmd_objects(context.scene, root, (rigid_group, joint_group))
        by_bone = _rigids_by_bone(FnModel, root)
        existing_pairs = _existing_joint_pairs(FnModel, root)
        create_rigids = mode in {"FOLLOW", "PHYSICS", "COMBINED"}
        create_joints = mode in {"JOINT", "COMBINED"}
        dynamics_type = 0 if mode == "FOLLOW" else int(settings.bone_creator_physics_type)

        if create_rigids:
            for bone in selected_bones:
                exact = [
                    rigid
                    for rigid in by_bone.get(bone.name, ())
                    if int(rigid.mmd_rigid.type) == dynamics_type
                ]
                if exact and settings.bone_creator_conflict == "REUSE":
                    reused_rigids += 1
                    continue
                rigid = _create_rigid(
                    context,
                    settings,
                    bone,
                    dynamics_type,
                    rigid_group,
                    armature,
                    FnRigidBody,
                    rigid_module,
                )
                created_objects.append(rigid)
                created_rigid_objects.append(rigid)
                by_bone.setdefault(bone.name, []).append(rigid)
                created_rigids += 1

            place_mmd_objects(context.scene, root, created_rigid_objects)

        if create_joints:
            for child_bone in selected_bones:
                parent_bone = child_bone.parent
                if parent_bone is None:
                    skipped_joints += 1
                    continue
                parent_rigids = by_bone.get(parent_bone.name, ())
                child_rigids = by_bone.get(child_bone.name, ())
                if not parent_rigids or not child_rigids:
                    skipped_joints += 1
                    continue
                preferred_type = dynamics_type if mode == "COMBINED" else None
                rigid_a = _preferred_rigid(parent_rigids, preferred_type)
                rigid_b = _preferred_rigid(child_rigids, preferred_type)
                pair = frozenset((rigid_a.name, rigid_b.name))
                if pair in existing_pairs:
                    skipped_joints += 1
                    continue
                joint = _create_joint(
                    context,
                    settings,
                    child_bone,
                    rigid_a,
                    rigid_b,
                    joint_group,
                    armature,
                    root,
                    FnModel,
                    FnRigidBody,
                )
                created_objects.append(joint)
                created_joint_objects.append(joint)
                existing_pairs.add(pair)
                created_joints += 1

            place_mmd_objects(context.scene, root, created_joint_objects)
    except Exception:
        for obj in reversed(created_objects):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        raise
    finally:
        restore_bone_selection(
            context,
            armature,
            original_mode,
            selected_names,
            active_name,
        )
    kinds = []
    if created_rigid_objects:
        kinds.append("RIGID")
    if created_joint_objects:
        kinds.append("JOINT")
    if kinds:
        normalize_mmd_indices(root, FnModel, kinds)
    return BuildResult(
        selected=len(selected_names),
        created_rigids=created_rigids,
        reused_rigids=reused_rigids,
        created_joints=created_joints,
        skipped_joints=skipped_joints,
        created_rigid_names=tuple(obj.name for obj in created_rigid_objects),
        created_joint_names=tuple(obj.name for obj in created_joint_objects),
    )
