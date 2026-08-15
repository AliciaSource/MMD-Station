import pathlib
import sys

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_skirt_proxy_creator
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_skirt_proxy_creator.mmd_physics import _mmd_api


mmd_skirt_proxy_creator.register()
model = Model.create("BonePhysicsCreatorSmoke", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
root_bone = next(iter(armature.data.bones))
CHAIN_A = "Creator_A"
CHAIN_B = "Creator_B"
CHAIN_C = "Creator_C_1234567890"
SIBLING = "Creator_Sibling"

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

select_pose(CHAIN_A, CHAIN_B)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="JOINT") == {"FINISHED"}

settings.bone_creator_physics_type = "1"
settings.browser_search = "stale filter"
settings.browser_current_proxy_only = True
select_pose(CHAIN_B, CHAIN_C)
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="COMBINED") == {"FINISHED"}
assert settings.browser_kind == "JOINT"
assert settings.browser_search == ""
assert not settings.browser_current_proxy_only
assert any(item.selected for item in settings.browser_items if item.kind == "JOINT")

FnModel, _FnRigidBody, _rigid_module = _mmd_api()
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
    and rigid.mmd_rigid.name_j == CHAIN_C[:16]
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
    joint.mmd_joint.name_j == CHAIN_C[:16]
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

print(
    "BONE_PHYSICS_CREATOR_SMOKE_OK "
    f"rigids={len(rigids)} joints={len(joints)} ordered=3"
)

mmd_skirt_proxy_creator.unregister()
