import pathlib
import sys

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_station.mmd_physics import _mmd_api


mmd_station.register()
model = Model.create("CollectionOrganization", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
model_collection = bpy.data.collections.new("CollectionOrganizationModel")
bpy.context.scene.collection.children.link(model_collection)
model_collection.objects.link(root)
for collection in tuple(root.users_collection):
    if collection != model_collection:
        collection.objects.unlink(root)

bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
parent = next(iter(armature.data.edit_bones))
bone_names = ("CollectionProxy1", "CollectionProxy2")
for index, name in enumerate(bone_names):
    bone = armature.data.edit_bones.new(name)
    bone.head = (0.0, 0.0, 1.0 - index)
    bone.tail = (0.0, 0.0, 0.0 - index)
    bone.parent = parent
    parent = bone
bpy.ops.object.mode_set(mode="POSE")
for bone in armature.data.bones:
    bone.select = bone.name in bone_names
armature.data.bones.active = armature.data.bones[bone_names[-1]]

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
assert bpy.ops.surface_proxy.create_physics_from_selected_bones(mode="COMBINED") == {
    "FINISHED"
}
FnModel, _FnRigidBody, _rigid_module = _mmd_api()
expected_collections = {model_collection}
assert set(FnModel.find_rigid_group_object(root).users_collection) == expected_collections
assert set(FnModel.find_joint_group_object(root).users_collection) == expected_collections
assert all(
    set(obj.users_collection) == expected_collections
    for obj in (
        *FnModel.iterate_rigid_body_objects(root),
        *FnModel.iterate_joint_objects(root),
    )
)

settings.browser_items.clear()
for name in bone_names:
    item = settings.browser_items.add()
    item.kind = "BONE"
    item.target_name = name
    item.armature_name = armature.name
    item.selected = True
settings.browser_index = len(settings.browser_items) - 1
settings.topology = "OPEN"
settings.restore_connect_sides = False
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
proxy = bpy.data.objects["CollectionProxy_Surface"]
proxy_collection = bpy.data.collections["MMD Station Proxies"]
assert tuple(proxy.users_collection) == (proxy_collection,)

settings.physics_proxy = proxy
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
physics_objects = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == proxy.name
]
assert physics_objects
assert all(set(obj.users_collection) == expected_collections for obj in physics_objects)
assert set(FnModel.find_rigid_group_object(root).users_collection) == expected_collections
assert set(FnModel.find_joint_group_object(root).users_collection) == expected_collections

print("COLLECTION_ORGANIZATION_REGRESSION_OK")
