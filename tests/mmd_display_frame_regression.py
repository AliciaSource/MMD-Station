import pathlib
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_station.mmd_display_frame import (
    FRAME_SELECTED_PROPERTY,
    ITEM_SELECTED_PROPERTY,
    _draw_active_frame_statistics,
)


def add_bone(armature, name, x):
    bone = armature.data.edit_bones.new(name)
    bone.head = Vector((x, 0.0, 0.0))
    bone.tail = Vector((x, 0.0, 1.0))
    return bone


def add_mesh_with_shape_key(armature, shape_key_name):
    mesh = bpy.data.meshes.new("DisplayFrameMesh")
    mesh.from_pydata(((0.0, 0.0, 0.0),), (), ())
    obj = bpy.data.objects.new("DisplayFrameMesh", mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    modifier = obj.modifiers.new(name="mmd_armature", type="ARMATURE")
    modifier.object = armature
    obj.shape_key_add(name="Basis")
    obj.shape_key_add(name=shape_key_name)


mmd_station.register()
model = Model.create("DisplayFrameRegression", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
settings = bpy.context.scene.surface_proxy_creator
settings.display_frame_root = root

bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
add_bone(armature, "SelectedBone", 1.0)
add_bone(armature, "MissingBone", 2.0)
add_bone(armature, "HiddenBone", 3.0)
bpy.ops.object.mode_set(mode="POSE")
for bone in armature.data.bones:
    bone.select = bone.name == "SelectedBone"
armature.data.bones.active = armature.data.bones["SelectedBone"]
armature.data.bones["HiddenBone"].hide = True

assert bpy.ops.surface_proxy.add_display_frame() == {"FINISHED"}
frame = root.mmd_root.display_item_frames[root.mmd_root.active_display_item_frame]
frame.name = "追加骨骼"
frame.name_e = "Additional Bones"
assert bpy.ops.surface_proxy.add_selected_display_items() == {"FINISHED"}
assert [item.name for item in frame.data] == ["SelectedBone"]

assert bpy.ops.surface_proxy.smart_fill_display_frame_bones() == {"FINISHED"}
bone_items = [item.name for item in frame.data if item.type == "BONE"]
assert "SelectedBone" in bone_items
assert "MissingBone" in bone_items
assert "HiddenBone" not in bone_items

for item in frame.data:
    setattr(item, ITEM_SELECTED_PROPERTY, item.name in {"SelectedBone", "MissingBone"})
extra = frame.data.add()
extra.type = "BONE"
extra.name = "Anchor"
frame.active_item = len(frame.data) - 1
assert bpy.ops.surface_proxy.reorder_display_items(action="BOTTOM") == {"FINISHED"}
assert [item.name for item in frame.data][-2:] == ["SelectedBone", "MissingBone"]
for item in frame.data:
    setattr(item, ITEM_SELECTED_PROPERTY, False)
setattr(frame.data[0], ITEM_SELECTED_PROPERTY, True)
setattr(frame.data[-1], ITEM_SELECTED_PROPERTY, True)
assert bpy.ops.surface_proxy.select_display_interval(target="ITEMS") == {"FINISHED"}
assert all(getattr(item, ITEM_SELECTED_PROPERTY) for item in frame.data)

invalid_bone = frame.data.add()
invalid_bone.type = "BONE"
invalid_bone.name = "RenamedBoneResidual"
invalid_morph = frame.data.add()
invalid_morph.type = "MORPH"
invalid_morph.morph_type = "bone_morphs"
invalid_morph.name = "MissingMorphResidual"
assert bpy.ops.surface_proxy.clean_invalid_display_items() == {"FINISHED"}
assert "RenamedBoneResidual" not in {item.name for item in frame.data}
assert "MissingMorphResidual" not in {item.name for item in frame.data}
assert {"SelectedBone", "MissingBone"} <= {item.name for item in frame.data}
assert bpy.ops.surface_proxy.select_checked_display_bones() == {"FINISHED"}
assert armature.mode == "POSE"
assert {
    bone.name for bone in armature.data.bones if bone.select
} == {"SelectedBone", "MissingBone"}

assert bpy.ops.object.mode_set(mode="OBJECT") == {"FINISHED"}
add_mesh_with_shape_key(armature, "VertexDetailed")

material_morph = root.mmd_root.material_morphs.add()
material_morph.name = "MaterialDetailed"
material_morph.data.add()
hidden_material = root.mmd_root.material_morphs.add()
hidden_material.name = "MaterialHiddenDetailed"
hidden_material.category = "SYSTEM"
hidden_material.data.add()
empty_material = root.mmd_root.material_morphs.add()
empty_material.name = "MaterialEmpty"

uv_morph = root.mmd_root.uv_morphs.add()
uv_morph.name = "UVDetailed"
uv_morph.data.add()

bone_morph = root.mmd_root.bone_morphs.add()
bone_morph.name = "BoneDetailed"
bone_morph.data.add().bone = "SelectedBone"

vertex_morph = root.mmd_root.vertex_morphs.add()
vertex_morph.name = "VertexDetailed"
empty_vertex = root.mmd_root.vertex_morphs.add()
empty_vertex.name = "VertexEmpty"

group_morph = root.mmd_root.group_morphs.add()
group_morph.name = "GroupDetailed"
group_offset = group_morph.data.add()
group_offset.morph_type = "material_morphs"
group_offset.name = material_morph.name
empty_group = root.mmd_root.group_morphs.add()
empty_group.name = "GroupEmpty"

facial_index = root.mmd_root.display_item_frames.find("表情")
assert facial_index >= 0
root.mmd_root.active_display_item_frame = facial_index
assert bpy.ops.surface_proxy.smart_reorder_facial_frame() == {"FINISHED"}
facial = root.mmd_root.display_item_frames[facial_index]
assert [(item.morph_type, item.name) for item in facial.data] == [
    ("group_morphs", "GroupDetailed"),
    ("material_morphs", "MaterialDetailed"),
    ("uv_morphs", "UVDetailed"),
    ("bone_morphs", "BoneDetailed"),
    ("vertex_morphs", "VertexDetailed"),
]


class LabelCapture:
    def __init__(self):
        self.labels = []

    def label(self, *, text):
        self.labels.append(text)


statistics_layout = LabelCapture()
_draw_active_frame_statistics(statistics_layout, facial)
_draw_active_frame_statistics(statistics_layout, frame)
assert statistics_layout.labels == [
    "当前显示枠：共 5 项；Morph：5 项；骨骼：0 项",
    "当前显示枠：共 2 项；Morph：0 项；骨骼：2 项",
]
assert root.mmd_root.material_morphs.get("MaterialEmpty") is not None
assert root.mmd_root.material_morphs.get("MaterialHiddenDetailed") is not None
assert facial.data.get("MaterialHiddenDetailed") is None
assert root.mmd_root.vertex_morphs.get("VertexEmpty") is not None
assert root.mmd_root.group_morphs.get("GroupEmpty") is not None

custom_frames = [frame for frame in root.mmd_root.display_item_frames if not frame.is_special]
assert custom_frames
for display_frame in root.mmd_root.display_item_frames:
    setattr(display_frame, FRAME_SELECTED_PROPERTY, False)
setattr(root.mmd_root.display_item_frames[0], FRAME_SELECTED_PROPERTY, True)
setattr(root.mmd_root.display_item_frames[-1], FRAME_SELECTED_PROPERTY, True)
assert bpy.ops.surface_proxy.select_display_interval(target="FRAMES") == {"FINISHED"}
assert all(
    getattr(display_frame, FRAME_SELECTED_PROPERTY)
    for display_frame in root.mmd_root.display_item_frames
)
root.mmd_root.active_display_item_frame = facial_index
assert bpy.ops.surface_proxy.reorder_display_frames(action="TOP") == {"FINISHED"}
assert all(frame.is_special for frame in root.mmd_root.display_item_frames[:2])

mmd_station.unregister()
print("MMD_DISPLAY_FRAME_REGRESSION_OK")
