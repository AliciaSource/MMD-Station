import pathlib
import sys

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_skirt_proxy_creator


mmd_skirt_proxy_creator.register()
assert mmd_skirt_proxy_creator._derived_proxy_prefix(
    ["Bone_Piao031.L", "Bone_Piao032.L"]
) == "Bone_Piao"
assert mmd_skirt_proxy_creator._derived_proxy_prefix(
    ["后发A1.L", "后发A2.L"]
) == "后发A"
assert mmd_skirt_proxy_creator._derived_proxy_prefix(
    ["后发B1.R", "后发B2.R"]
) == "后发B"
assert not mmd_skirt_proxy_creator._derived_proxy_prefix(
    ["后发A1.L", "后发A2.L", "后发B1.R", "后发B2.R"]
)

armature_data = bpy.data.armatures.new("NoOverwriteArmatureData")
armature = bpy.data.objects.new("NoOverwriteArmature", armature_data)
bpy.context.collection.objects.link(armature)
bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")

chains = (
    ("Bone_Piao031.L", "Bone_Piao032.L", 0.0),
    ("Bone_Piao041.L", "Bone_Piao042.L", 1.0),
)
for root_name, child_name, x in chains:
    root = armature_data.edit_bones.new(root_name)
    root.head = (x, 0.0, 1.0)
    root.tail = (x, 0.0, 0.5)
    child = armature_data.edit_bones.new(child_name)
    child.head = root.tail
    child.tail = (x, 0.0, 0.0)
    child.parent = root
    child.use_connect = True
bpy.ops.object.mode_set(mode="OBJECT")

settings = bpy.context.scene.surface_proxy_creator
settings.topology = "OPEN"
settings.restore_connect_sides = False
sentinel_data = bpy.data.meshes.new("ExistingProxySelectionData")
sentinel = bpy.data.objects.new("ExistingProxySelection", sentinel_data)
bpy.context.collection.objects.link(sentinel)
settings.physics_proxy = sentinel


def select_chain(names):
    settings.browser_items.clear()
    for name in names:
        item = settings.browser_items.add()
        item.kind = "BONE"
        item.target_name = name
        item.armature_name = armature.name
        item.selected = True
    settings.browser_index = len(settings.browser_items) - 1


def browser_state():
    return (
        [
            (item.kind, item.target_name, item.armature_name, item.selected)
            for item in settings.browser_items
        ],
        settings.browser_index,
    )


first_chain = chains[0][:2]
second_chain = chains[1][:2]
select_chain(first_chain)
first_browser_state = browser_state()
selection_before = set(bpy.context.selected_objects)
active_before = bpy.context.view_layer.objects.active
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
first_proxy = bpy.data.objects["Bone_Piao_Surface"]
assert browser_state() == first_browser_state
assert settings.physics_proxy == sentinel
assert set(bpy.context.selected_objects) == selection_before
assert bpy.context.view_layer.objects.active == active_before
assert not first_proxy.select_get()
first_pointer = first_proxy.as_pointer()
first_mesh_pointer = first_proxy.data.as_pointer()
first_coordinates = [vertex.co.copy() for vertex in first_proxy.data.vertices]

select_chain(first_chain)
rejected_browser_state = browser_state()
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"CANCELLED"}
assert browser_state() == rejected_browser_state
assert settings.physics_proxy == sentinel
assert bpy.data.objects["Bone_Piao_Surface"].as_pointer() == first_pointer
assert bpy.data.objects["Bone_Piao_Surface"].data.as_pointer() == first_mesh_pointer
assert [vertex.co.copy() for vertex in first_proxy.data.vertices] == first_coordinates
assert bpy.data.objects.get("Bone_Piao_Surface.001") is None

select_chain(second_chain)
second_browser_state = browser_state()
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
second_proxy = bpy.data.objects["Bone_Piao_Surface.001"]
assert browser_state() == second_browser_state
assert settings.physics_proxy == sentinel
assert set(bpy.context.selected_objects) == selection_before
assert bpy.context.view_layer.objects.active == active_before
assert not second_proxy.select_get()
assert first_proxy.as_pointer() == first_pointer
assert set(first_proxy["surface_proxy_bone_names"]) == set(first_chain)
assert set(second_proxy["surface_proxy_bone_names"]) == set(second_chain)

print("PROXY_CREATION_NO_OVERWRITE_OK")
