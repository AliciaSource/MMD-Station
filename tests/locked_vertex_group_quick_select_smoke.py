import pathlib
import sys

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import mmd_station


mmd_station.register()

armature_data = bpy.data.armatures.new("LockedGroupArmatureData")
armature = bpy.data.objects.new("LockedGroupArmature", armature_data)
bpy.context.collection.objects.link(armature)
bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for index, name in enumerate(("LockedBone", "UnlockedBone")):
    bone = armature_data.edit_bones.new(name)
    bone.head = (float(index), 0.0, 0.0)
    bone.tail = (float(index), 0.0, 1.0)
bpy.ops.object.mode_set(mode="OBJECT")

mesh_data = bpy.data.meshes.new("LockedGroupMeshData")
mesh_data.from_pydata([(0.0, 0.0, 0.0)], [], [])
mesh = bpy.data.objects.new("LockedGroupMesh", mesh_data)
bpy.context.collection.objects.link(mesh)
locked_bone_group = mesh.vertex_groups.new(name="LockedBone")
locked_bone_group.lock_weight = True
unlocked_bone_group = mesh.vertex_groups.new(name="UnlockedBone")
unlocked_bone_group.lock_weight = False
ordinary_group = mesh.vertex_groups.new(name="LockedOrdinaryGroup")
ordinary_group.lock_weight = True

settings = bpy.context.scene.surface_proxy_creator
settings.browser_kind = "BONE"
settings.browser_items.clear()
for name in ("LockedBone", "UnlockedBone"):
    item = settings.browser_items.add()
    item.kind = "BONE"
    item.target_name = name
    item.armature_name = armature.name
    item.selected = False
settings.browser_index = 0

bpy.ops.object.select_all(action="DESELECT")
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
result = bpy.ops.surface_proxy.quick_check_mmd_group(mode="LOCKED_VERTEX_GROUPS")
assert result == {"FINISHED"}, result
assert {item.target_name for item in settings.browser_items if item.selected} == {
    "LockedBone"
}

print("LOCKED_VERTEX_GROUP_QUICK_SELECT_OK")
