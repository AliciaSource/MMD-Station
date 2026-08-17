import pathlib
import re
import sys

import bpy
from mathutils import Euler, Matrix, Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_skirt_proxy_creator
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_skirt_proxy_creator.mmd_physics import _mmd_api
from mmd_skirt_proxy_creator.mirror_physics import mirrored_name, mirrored_world_matrix


mmd_skirt_proxy_creator.register()


def assert_matrix_close(actual, expected, tolerance=1.0e-6):
    assert max(
        abs(actual[row][column] - expected[row][column])
        for row in range(4)
        for column in range(4)
    ) < tolerance


assert mirrored_name("Skirt.L") == "Skirt.R"
assert mirrored_name("Skirt_R") == "Skirt_L"
assert mirrored_name("左袖") == "右袖"
assert mirrored_name("Body") == "Body_M"
assert mirrored_name("Body_M") == "Body"
model = Model.create("BonePhysicsCreatorSmoke", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
root_bone = next(iter(armature.data.bones))
CHAIN_A = "Creator_A"
CHAIN_B = "Creator_B"
CHAIN_C = "Creator_C_1234567890"
SIBLING = "Creator_Sibling"
MIRROR_A_L = "MirA.L"
MIRROR_B_L = "MirB.L"
MIRROR_A_R = "MirA.R"
MIRROR_B_R = "MirB.R"

bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
parent = armature.data.edit_bones[root_bone.name]
for index, name in enumerate((CHAIN_A, CHAIN_B, CHAIN_C)):
    bone = armature.data.edit_bones.new(name)
    bone.head = (0.0, 0.0, 1.0 + index)
    bone.tail = (0.0, 0.0, 2.0 + index)
    bone.parent = parent
    parent = bone
sibling = armature.data.edit_bones.new(SIBLING)
sibling.head = (1.0, 0.0, 1.0)
sibling.tail = (1.0, 0.0, 2.0)
sibling.parent = armature.data.edit_bones[root_bone.name]
bpy.ops.object.mode_set(mode="POSE")

for name in (CHAIN_A, CHAIN_B, CHAIN_C, SIBLING):
    armature.pose.bones[name].mmd_bone.name_j = f"物理{name}"
    armature.pose.bones[name].mmd_bone.name_e = f"Physics_{name}"

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.browser_current_proxy_only = False


def select_pose(*names):
    selected = set(names)
    for bone in armature.data.bones:
        bone.select = bone.name in selected
    armature.data.bones.active = armature.data.bones[names[-1]]


select_pose(CHAIN_A, CHAIN_B, CHAIN_C)
assert bpy.ops.surface_proxy.sync_selected_bones_to_browser() == {"FINISHED"}
checked = {
    item.target_name
    for item in settings.browser_items
    if item.kind == "BONE" and item.selected
}
assert checked == {CHAIN_A, CHAIN_B, CHAIN_C}
assert settings.browser_items[settings.browser_index].target_name == CHAIN_C

select_pose(CHAIN_A)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="FOLLOW") == {"FINISHED"}

settings.bone_creator_physics_type = "2"
select_pose(CHAIN_B)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="PHYSICS") == {"FINISHED"}
FnModel, _FnRigidBody, _rigid_module = _mmd_api()
chain_b_rigid = next(
    rigid
    for rigid in FnModel.iterate_rigid_body_objects(root)
    if rigid.mmd_rigid.bone == CHAIN_B
)
assert chain_b_rigid.mmd_rigid.name_j == f"物理{CHAIN_B}"
assert chain_b_rigid.mmd_rigid.name_e == f"Physics_{CHAIN_B}"[:16]
assert re.match(r"^\d{3}_物理Creator_B$", chain_b_rigid.name)
chain_b_bone = armature.data.bones[CHAIN_B]
chain_b_direction = (chain_b_bone.tail_local - chain_b_bone.head_local).normalized()
chain_b_basis = chain_b_rigid.rotation_euler.to_matrix()
assert (chain_b_basis @ Vector((0.0, 0.0, 1.0))).dot(chain_b_direction) > 0.999999
assert chain_b_basis.determinant() > 0.999999
chain_b_rigid.rotation_euler = Euler((0.41, -0.72, 1.13), "YXZ")

select_pose(CHAIN_A, CHAIN_B)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="JOINT") == {"FINISHED"}
chain_ab_joint = next(
    joint
    for joint in FnModel.iterate_joint_objects(root)
    if joint.rigid_body_constraint.object2 == chain_b_rigid
)
assert chain_ab_joint.mmd_joint.name_j == f"物理{CHAIN_B}"
assert chain_ab_joint.mmd_joint.name_e == f"Physics_{CHAIN_B}"[:16]
assert re.match(r"^\d{3}_J\.物理Creator_B$", chain_ab_joint.name)
assert (
    chain_ab_joint.rotation_euler.to_quaternion().rotation_difference(
        chain_b_rigid.rotation_euler.to_quaternion()
    ).angle
    < 1.0e-6
)

settings.bone_creator_physics_type = "1"
settings.browser_search = "stale filter"
settings.browser_current_proxy_only = True
select_pose(CHAIN_B, CHAIN_C)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="COMBINED") == {"FINISHED"}
assert settings.browser_kind == "JOINT"
assert settings.browser_search == ""
assert not settings.browser_current_proxy_only
assert any(item.selected for item in settings.browser_items if item.kind == "JOINT")

rigids = list(FnModel.iterate_rigid_body_objects(root))
joints = list(FnModel.iterate_joint_objects(root))
types_by_bone = {}
for rigid in rigids:
    types_by_bone.setdefault(rigid.mmd_rigid.bone, set()).add(int(rigid.mmd_rigid.type))
assert 0 in types_by_bone[CHAIN_A]
assert 2 in types_by_bone[CHAIN_B]
assert 1 in types_by_bone[CHAIN_B]
assert 1 in types_by_bone[CHAIN_C]
assert all(len(rigid.mmd_rigid.name_j) <= 16 for rigid in rigids)
assert all(len(joint.mmd_joint.name_j) <= 16 for joint in joints)
assert any(
    rigid.mmd_rigid.bone == CHAIN_C
    and rigid.mmd_rigid.name_j == f"物理{CHAIN_C}"[:16]
    for rigid in rigids
)
assert len(joints) == 3
joint_bones = {
    frozenset(
        (
            joint.rigid_body_constraint.object1.mmd_rigid.bone,
            joint.rigid_body_constraint.object2.mmd_rigid.bone,
        )
    )
    for joint in joints
}
assert frozenset((CHAIN_A, CHAIN_B)) in joint_bones
assert frozenset((CHAIN_B, CHAIN_C)) in joint_bones
assert any(
    joint.mmd_joint.name_j == f"物理{CHAIN_C}"[:16]
    and frozenset(
        (
            joint.rigid_body_constraint.object1.mmd_rigid.bone,
            joint.rigid_body_constraint.object2.mmd_rigid.bone,
        )
    )
    == frozenset((CHAIN_B, CHAIN_C))
    for joint in joints
)

bpy.ops.object.mode_set(mode="EDIT")
for bone in armature.data.edit_bones:
    selected = bone.name in {CHAIN_A, CHAIN_C}
    bone.select = selected
    bone.select_head = selected
    bone.select_tail = selected
armature.data.bones.active = armature.data.bones[CHAIN_A]
assert bpy.ops.surface_proxy.sync_selected_bones_to_browser() == {"FINISHED"}
checked = {
    item.target_name
    for item in settings.browser_items
    if item.kind == "BONE" and item.selected
}
assert checked == {CHAIN_A, CHAIN_C}
assert armature.mode == "EDIT"


def refresh(kind):
    settings.browser_kind = kind
    settings.browser_search = ""
    settings.browser_current_proxy_only = False
    assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}


def check_only(*names):
    selected = set(names)
    for item in settings.browser_items:
        item.selected = item.target_name in selected


bpy.ops.object.mode_set(mode="POSE")
for bone_id, name in enumerate((root_bone.name, CHAIN_A, CHAIN_B, CHAIN_C, SIBLING)):
    armature.pose.bones[name].mmd_bone.bone_id = bone_id
refresh("BONE")
bone_rows = {item.target_name: index for index, item in enumerate(settings.browser_items)}
check_only(CHAIN_A)
settings.browser_index = bone_rows[CHAIN_A]
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="DOWN") == {"FINISHED"}
assert armature.pose.bones[SIBLING].mmd_bone.bone_id < armature.pose.bones[CHAIN_A].mmd_bone.bone_id
assert armature.pose.bones[CHAIN_A].mmd_bone.bone_id < armature.pose.bones[CHAIN_B].mmd_bone.bone_id
assert armature.pose.bones[CHAIN_B].mmd_bone.bone_id < armature.pose.bones[CHAIN_C].mmd_bone.bone_id
assert [item.order_index for item in settings.browser_items] == list(
    range(len(settings.browser_items))
)

refresh("RIGID")
rigid_order = sorted(rigids, key=lambda item: item.name)
selected_rigids = [rigid_order[1], rigid_order[3]]
active_rigid = rigid_order[0]
check_only(*(item.name for item in selected_rigids))
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == active_rigid.name
)
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="AFTER") == {"FINISHED"}
assert sorted(rigids, key=lambda item: item.name) == [
    active_rigid,
    *selected_rigids,
    rigid_order[2],
]
assert [item.order_index for item in settings.browser_items] == list(
    range(len(settings.browser_items))
)
assert {
    item.target_name for item in settings.browser_items if item.selected
} == {item.name for item in selected_rigids}

refresh("JOINT")
joint_order = sorted(joints, key=lambda item: item.name)
selected_joint = joint_order[-1]
active_joint = joint_order[0]
check_only(selected_joint.name)
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == active_joint.name
)
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="BEFORE") == {"FINISHED"}
assert sorted(joints, key=lambda item: item.name) == [
    selected_joint,
    active_joint,
    joint_order[1],
]
assert [item.order_index for item in settings.browser_items] == list(
    range(len(settings.browser_items))
)

bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="EDIT")
for x, first, second in (
    (2.0, MIRROR_A_L, MIRROR_B_L),
    (-2.0, MIRROR_A_R, MIRROR_B_R),
):
    first_bone = armature.data.edit_bones.new(first)
    first_bone.head = (x, 0.0, 1.0)
    first_bone.tail = (x, 0.0, 2.0)
    first_bone.parent = armature.data.edit_bones[root_bone.name]
    second_bone = armature.data.edit_bones.new(second)
    second_bone.head = (x, 0.0, 2.0)
    second_bone.tail = (x, 0.0, 3.0)
    second_bone.parent = first_bone
bpy.ops.object.mode_set(mode="POSE")
for name_j, name_e, name in (
    ("左镜像A", "MirrorA_L", MIRROR_A_L),
    ("左镜像B", "MirrorB_L", MIRROR_B_L),
    ("右镜像A", "MirrorA_R", MIRROR_A_R),
    ("右镜像B", "MirrorB_R", MIRROR_B_R),
):
    armature.pose.bones[name].mmd_bone.name_j = name_j
    armature.pose.bones[name].mmd_bone.name_e = name_e
select_pose(MIRROR_A_L, MIRROR_B_L)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="COMBINED") == {"FINISHED"}
rigids = list(FnModel.iterate_rigid_body_objects(root))
joints = list(FnModel.iterate_joint_objects(root))
left_rigids = {
    rigid.mmd_rigid.bone: rigid
    for rigid in rigids
    if rigid.mmd_rigid.bone in {MIRROR_A_L, MIRROR_B_L}
}
assert set(left_rigids) == {MIRROR_A_L, MIRROR_B_L}
assert left_rigids[MIRROR_A_L].mmd_rigid.name_j == "左镜像A"
assert left_rigids[MIRROR_A_L].mmd_rigid.name_e == "MirrorA_L"
assert re.match(r"^\d{3}_左镜像A$", left_rigids[MIRROR_A_L].name)
left_joint = next(
    joint
    for joint in joints
    if {
        joint.rigid_body_constraint.object1,
        joint.rigid_body_constraint.object2,
    }
    == set(left_rigids.values())
)
assert left_joint.mmd_joint.name_j == "左镜像B"
assert left_joint.mmd_joint.name_e == "MirrorB_L"
assert re.match(r"^\d{3}_J\.左镜像B$", left_joint.name)
left_rigids[MIRROR_A_L].rigid_body.mass = 3.25
left_rigids[MIRROR_A_L].location.x += 0.35
distractor = left_rigids[MIRROR_A_L].copy()
left_rigids[MIRROR_A_L].users_collection[0].objects.link(distractor)
distractor.name = "ExistingRightRigid"
distractor.mmd_rigid.bone = MIRROR_A_R
distractor.mmd_rigid.name_j = "OtherRight"
distractor.mmd_rigid.name_e = "OtherRight"
left_joint.rigid_body_constraint.limit_lin_x_lower = -0.1
left_joint.rigid_body_constraint.limit_lin_x_upper = 0.4
left_joint.rigid_body_constraint.limit_ang_y_lower = -0.3
left_joint.rigid_body_constraint.limit_ang_y_upper = 0.6
refresh("RIGID")
check_only(*(rigid.name for rigid in left_rigids.values()))
settings.mirror_include_joints = True
assert bpy.ops.surface_proxy.create_mirrored_mmd_items() == {"FINISHED"}
rigids = list(FnModel.iterate_rigid_body_objects(root))
joints = list(FnModel.iterate_joint_objects(root))
right_rigids = {
    rigid.mmd_rigid.bone: rigid
    for rigid in rigids
    if rigid.mmd_rigid.bone in {MIRROR_A_R, MIRROR_B_R}
    and rigid.mmd_rigid.name_j
    == mirrored_name(left_rigids[rigid.mmd_rigid.bone.replace(".R", ".L")].mmd_rigid.name_j)
}
assert set(right_rigids) == {MIRROR_A_R, MIRROR_B_R}
assert distractor not in right_rigids.values()
right_joint = next(
    joint
    for joint in joints
    if {
        joint.rigid_body_constraint.object1,
        joint.rigid_body_constraint.object2,
    }
    == set(right_rigids.values())
)
assert abs(right_rigids[MIRROR_A_R].rigid_body.mass - 3.25) < 1.0e-6
assert abs(
    right_rigids[MIRROR_A_R].matrix_world.translation.x
    + left_rigids[MIRROR_A_L].matrix_world.translation.x
) < 1.0e-6
assert abs(right_joint.rigid_body_constraint.limit_lin_x_lower + 0.4) < 1.0e-6
assert abs(right_joint.rigid_body_constraint.limit_lin_x_upper - 0.1) < 1.0e-6
assert abs(right_joint.rigid_body_constraint.limit_ang_y_lower + 0.6) < 1.0e-6
assert abs(right_joint.rigid_body_constraint.limit_ang_y_upper - 0.3) < 1.0e-6
left_rigids[MIRROR_A_L].rigid_body.mass = 4.5
left_joint.mmd_joint.spring_linear = Vector((1.0, 2.0, 3.0))
refresh("RIGID")
check_only(*(rigid.name for rigid in left_rigids.values()))
assert bpy.ops.surface_proxy.sync_mirrored_mmd_items() == {"FINISHED"}
assert abs(right_rigids[MIRROR_A_R].rigid_body.mass - 4.5) < 1.0e-6
assert tuple(right_joint.mmd_joint.spring_linear) == (1.0, 2.0, 3.0)

root.matrix_world = Matrix.Translation((1.7, -0.9, 2.3)) @ Euler(
    (0.31, -0.22, 0.47), "XYZ"
).to_matrix().to_4x4()
bpy.context.view_layer.update()
left_rigids[MIRROR_A_L].rotation_euler = Euler((0.27, -0.63, 1.04), "YXZ")
left_joint.rotation_euler = Euler((-0.52, 0.38, -0.91), "YXZ")
refresh("RIGID")
check_only(*(rigid.name for rigid in left_rigids.values()))
assert bpy.ops.surface_proxy.sync_mirrored_mmd_items() == {"FINISHED"}
for left_name, right_name in (
    (MIRROR_A_L, MIRROR_A_R),
    (MIRROR_B_L, MIRROR_B_R),
):
    assert_matrix_close(
        right_rigids[right_name].matrix_world,
        mirrored_world_matrix(left_rigids[left_name], armature),
    )
assert_matrix_close(
    right_joint.matrix_world,
    mirrored_world_matrix(left_joint, armature),
)

copy_source = left_rigids[MIRROR_A_L]
copy_source.mmd_rigid.bone = root_bone.name
copy_source.mmd_rigid.name_j = "BodyCore"
copy_source.mmd_rigid.name_e = "BodyCore"
left_joint.rigid_body_constraint.object1 = copy_source
left_joint.rigid_body_constraint.object2 = left_rigids[MIRROR_B_L]
bpy.data.objects.remove(right_joint, do_unlink=True)
refresh("RIGID")
check_only(left_rigids[MIRROR_B_L].name)
settings.mirror_include_joints = True
assert bpy.ops.surface_proxy.create_mirrored_mmd_items() == {"FINISHED"}
shared_anchor_joint = next(
    joint
    for joint in FnModel.iterate_joint_objects(root)
    if joint.rigid_body_constraint.object1 == copy_source
    and joint.rigid_body_constraint.object2 == right_rigids[MIRROR_B_R]
)
bpy.data.objects.remove(shared_anchor_joint, do_unlink=True)
refresh("RIGID")
check_only(copy_source.name)
settings.mirror_include_joints = False
assert bpy.ops.surface_proxy.create_mirrored_mmd_items() == {"FINISHED"}
copy_target = next(
    rigid
    for rigid in FnModel.iterate_rigid_body_objects(root)
    if rigid != copy_source
    and rigid.mmd_rigid.bone == root_bone.name
    and rigid.mmd_rigid.name_j == "BodyCore_M"
)
refresh("RIGID")
check_only(left_rigids[MIRROR_B_L].name)
settings.mirror_include_joints = True
assert bpy.ops.surface_proxy.create_mirrored_mmd_items() == {"FINISHED"}
mirrored_anchor_joint = next(
    joint
    for joint in FnModel.iterate_joint_objects(root)
    if joint.rigid_body_constraint.object1 == copy_target
    and joint.rigid_body_constraint.object2 == right_rigids[MIRROR_B_R]
)
assert mirrored_anchor_joint is not None
bpy.data.objects.remove(mirrored_anchor_joint, do_unlink=True)
refresh("JOINT")
check_only(left_joint.name)
assert bpy.ops.surface_proxy.create_mirrored_mmd_items() == {"FINISHED"}
mirrored_anchor_joint = next(
    joint
    for joint in FnModel.iterate_joint_objects(root)
    if joint.rigid_body_constraint.object1 == copy_target
    and joint.rigid_body_constraint.object2 == right_rigids[MIRROR_B_R]
)
left_joint.rigid_body_constraint.limit_ang_z_lower = -0.25
left_joint.rigid_body_constraint.limit_ang_z_upper = 0.75
refresh("JOINT")
check_only(left_joint.name)
assert bpy.ops.surface_proxy.sync_mirrored_mmd_items() == {"FINISHED"}
assert abs(mirrored_anchor_joint.rigid_body_constraint.limit_ang_z_lower + 0.75) < 1.0e-6
assert abs(mirrored_anchor_joint.rigid_body_constraint.limit_ang_z_upper - 0.25) < 1.0e-6
copy_source.rigid_body.mass = 6.75
refresh("RIGID")
check_only(copy_source.name)
assert bpy.ops.surface_proxy.sync_mirrored_mmd_items() == {"FINISHED"}
assert abs(copy_target.rigid_body.mass - 6.75) < 1.0e-6

print(
    "BONE_PHYSICS_CREATOR_SMOKE_OK "
    f"rigids={len(rigids)} joints={len(joints)} ordered=3"
)

mmd_skirt_proxy_creator.unregister()
