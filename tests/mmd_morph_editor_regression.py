import pathlib
import sys
import tempfile
from types import SimpleNamespace

import bpy
from mathutils import Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from mmd_station import mmd_morph_editor as morph_editor_module
from mmd_station import mmd_physics as mmd_physics_module
from bl_ext.blender_org.mmd_tools.core.model import FnModel, Model
from bl_ext.blender_org.mmd_tools.core import vmd
from mmd_station.mmd_material_order import ordered_materials, set_material_order
from mmd_station.mmd_morph_clipboard import (
    apply_pmx_editor_morphs,
    parse_pmx_editor_morph_csv,
    serialize_pmx_editor_morphs,
)
from mmd_station.mmd_morph_editor import (
    DETAIL_SELECTED_PROPERTY,
    OUTPUT_BRIDGE_PROPERTY,
    UV_DETAIL_SELECTED_PROPERTY,
    VERTEX_DETAIL_SELECTED_PROPERTY,
    _clear_uv_morph_preview,
    _create_uv_morph_preview,
    _migrate_placeholder_animation,
    _morph_state_data_path,
    _morph_state_structure_is_current,
    _morph_states_are_current,
    _refresh_morph_state_metadata,
    _preinitialize_imported_morphs,
    _remove_imported_shape_key_curves,
    ensure_morph_states,
)
from mmd_station.mmd_physics import _draw_active_mmd_inspector


class InspectorLayoutProbe:
    def __init__(self, labels=None, properties=None, operators=None):
        self.labels = labels if labels is not None else []
        self.properties = properties if properties is not None else []
        self.operators = operators if operators is not None else []
        self.active = True

    def row(self, **_kwargs):
        return InspectorLayoutProbe(self.labels, self.properties, self.operators)

    def column(self, **_kwargs):
        return InspectorLayoutProbe(self.labels, self.properties, self.operators)

    def split(self, **_kwargs):
        return InspectorLayoutProbe(self.labels, self.properties, self.operators)

    def box(self):
        return InspectorLayoutProbe(self.labels, self.properties, self.operators)

    def separator(self, **_kwargs):
        return None

    def menu(self, *_args, **_kwargs):
        return None

    def template_list(self, *_args, **_kwargs):
        return None

    def label(self, text="", **_kwargs):
        self.labels.append(text)

    def prop(self, data, name, **_kwargs):
        assert hasattr(data, name), name
        self.properties.append(name)

    def prop_search(self, data, name, *_args, **_kwargs):
        assert hasattr(data, name), name
        self.properties.append(name)

    def operator(self, operator_id, **_kwargs):
        self.operators.append(operator_id)
        return SimpleNamespace()


class MorphListLayoutProbe:
    def __init__(self, nodes=None, properties=None, operators=None):
        self.nodes = nodes if nodes is not None else []
        self.properties = properties if properties is not None else []
        self.operators = operators if operators is not None else []
        self.ui_units_x = 0.0
        self.use_property_decorate = False
        self.nodes.append(self)

    def row(self, **_kwargs):
        return MorphListLayoutProbe(self.nodes, self.properties, self.operators)

    def prop(self, data, name, **kwargs):
        self.properties.append((self, data, name, kwargs))

    def operator(self, operator_id, **kwargs):
        properties = SimpleNamespace()
        self.operators.append((self, operator_id, kwargs, properties))
        return properties


def make_material(name, shader_type="ShaderNodeBsdfPrincipled"):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new(shader_type)
    material.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
    return material


def make_custom_group_material(name):
    shader_group = bpy.data.node_groups.new(name + "Shader", "ShaderNodeTree")
    shader_group.interface.new_socket(
        name="Surface",
        in_out="OUTPUT",
        socket_type="NodeSocketShader",
    )
    group_output = shader_group.nodes.new("NodeGroupOutput")
    emission = shader_group.nodes.new("ShaderNodeEmission")
    shader_group.links.new(emission.outputs[0], group_output.inputs["Surface"])
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeGroup")
    shader.node_tree = shader_group
    material.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
    return material


def make_mesh(name, armature, material, x_offset):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        (
            (x_offset, 0.0, 0.0),
            (x_offset + 1.0, 0.0, 0.0),
            (x_offset, 1.0, 0.0),
        ),
        (),
        ((0, 1, 2),),
    )
    mesh.uv_layers.new(name="UVMap")
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    modifier = obj.modifiers.new(name="mmd_armature", type="ARMATURE")
    modifier.object = armature
    obj.shape_key_add(name="Basis")
    obj.shape_key_add(name="Smile")
    return obj


def bridge_nodes(material):
    return [
        node
        for node in material.node_tree.nodes
        if bool(node.get(OUTPUT_BRIDGE_PROPERTY, False))
    ]


mmd_station.register()
model = Model.create("MorphEditorRegression", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
parent_edit_bone = armature.data.edit_bones[0]
child_edit_bone = armature.data.edit_bones.new("WeightedChild")
child_edit_bone.head = parent_edit_bone.tail
child_edit_bone.tail = parent_edit_bone.tail + Vector((0.0, 0.0, 1.0))
child_edit_bone.parent = parent_edit_bone
weighted_child_name = child_edit_bone.name
bpy.ops.object.mode_set(mode="OBJECT")
material = make_material("Body", "ShaderNodeBsdfPrincipled")
custom_material = make_custom_group_material("CustomBody")
hidden_material = make_material("InitiallyHidden", "ShaderNodeBsdfPrincipled")
hidden_material.mmd_material.alpha = 0.0
hidden_shader = next(
    node
    for node in hidden_material.node_tree.nodes
    if node.inputs.get("Alpha") is not None
)
hidden_shader.inputs["Alpha"].default_value = 0.0
mesh_a = make_mesh("Face", armature, material, 0.0)
mesh_b = make_mesh("Mouth", armature, material, 2.0)
custom_mesh = make_mesh("CustomMesh", armature, custom_material, 4.0)
hidden_mesh = make_mesh("HiddenMesh", armature, hidden_material, 6.0)

vertex_morph = root.mmd_root.vertex_morphs.add()
vertex_morph.name = "Smile"
vertex_morph.name_e = "Smile"

uv_morph = root.mmd_root.uv_morphs.add()
uv_morph.name = "UVShift"
uv_morph.name_e = "UVShift"
uv_morph.uv_index = 0
uv_data = uv_morph.data.add()
uv_data.index = 0
uv_data.offset = (0.0, 0.0, 0.0, 0.0)

rename_uv_morph = root.mmd_root.uv_morphs.add()
rename_uv_morph.name = "RenameUV"
rename_uv_morph.name_e = "RenameUV"
rename_uv_morph.uv_index = 0
rename_uv_morph.data_type = "VERTEX_GROUP"
rename_uv_morph.vertex_group_scale = 0.125
rename_uv_group = mesh_a.vertex_groups.new(name="UV_RenameUV+X")
rename_uv_group.add((0,), 1.0, "REPLACE")

hide_morph = root.mmd_root.material_morphs.add()
hide_morph.name = "Hide"
hide_morph.name_e = "Hide"
hide_data = hide_morph.data.add()
hide_data.material = material.name
hide_data.offset_type = "ADD"
hide_data.diffuse_color = (0.25, 0.0, 0.0, -1.0)
hide_data.edge_color = (0.0, 0.0, 0.0, 0.0)
custom_hide_data = hide_morph.data.add()
custom_hide_data.material = custom_material.name
custom_hide_data.offset_type = "ADD"
custom_hide_data.diffuse_color = (0.0, 0.0, 0.25, -1.0)

mult_morph = root.mmd_root.material_morphs.add()
mult_morph.name = "FadeMultiply"
mult_data = mult_morph.data.add()
mult_data.material = material.name
mult_data.offset_type = "MULT"
mult_data.diffuse_color = (1.0, 1.0, 1.0, 0.5)
mult_data.edge_color = (1.0, 1.0, 1.0, 0.5)

show_morph = root.mmd_root.material_morphs.add()
show_morph.name = "ShowHidden"
show_data = show_morph.data.add()
show_data.material = hidden_material.name
show_data.offset_type = "ADD"
show_data.diffuse_color = (0.0, 0.0, 0.0, 1.0)

preset_morph = root.mmd_root.material_morphs.add()
preset_morph.name = "PresetBatch"
for preset_material in (material, custom_material):
    preset_data = preset_morph.data.add()
    preset_data.material = preset_material.name
    preset_data.offset_type = "MULT"
    preset_data.diffuse_color = (0.2, 0.3, 0.4, 0.5)
    preset_data.specular_color = (0.6, 0.7, 0.8)
    preset_data.shininess = 12.0
    preset_data.ambient_color = (0.9, 0.8, 0.7)
    preset_data.edge_color = (0.6, 0.5, 0.4, 0.3)
    preset_data.edge_weight = 2.0
    preset_data.texture_factor = (0.1, 0.2, 0.3, 0.4)
    preset_data.sphere_texture_factor = (0.5, 0.6, 0.7, 0.8)
    preset_data.toon_texture_factor = (0.9, 0.8, 0.7, 0.6)

bone_morph = root.mmd_root.bone_morphs.add()
bone_morph.name = "BoneMove"
bone_data = bone_morph.data.add()
bone_data.bone = armature.pose.bones[0].name
bone_data.location = (0.25, 0.0, 0.0)

convert_morph = root.mmd_root.bone_morphs.add()
convert_morph.name = "BoneConvert"
convert_data = convert_morph.data.add()
convert_data.bone = armature.pose.bones[0].name
convert_data.location = (0.5, 0.0, 0.0)
weighted_group = mesh_a.vertex_groups.new(name=weighted_child_name)
weighted_group.add((0,), 1.0, "REPLACE")
mesh_b.vertex_groups.new(name=weighted_child_name)
unrelated_group = custom_mesh.vertex_groups.new(name="UnrelatedBone")
unrelated_group.add((0, 1, 2), 1.0, "REPLACE")

ensure_morph_states(root)
assert _morph_states_are_current(root)
states = {state.morph_name: state for state in root.spx_morph_states}
assert {"Smile", "Hide", "FadeMultiply", "ShowHidden"}.issubset(states)
assert hasattr(bpy.types.Object, VERTEX_DETAIL_SELECTED_PROPERTY)
assert hasattr(bpy.types.Object, UV_DETAIL_SELECTED_PROPERTY)
assert hasattr(type(hide_data), DETAIL_SELECTED_PROPERTY)
assert hasattr(type(bone_data), DETAIL_SELECTED_PROPERTY)
assert hasattr(type(uv_data), DETAIL_SELECTED_PROPERTY)
hide_data.spx_morph_detail_selected = True
bone_data.spx_morph_detail_selected = True
uv_data.spx_morph_detail_selected = True
assert hide_data.spx_morph_detail_selected
assert bone_data.spx_morph_detail_selected
assert uv_data.spx_morph_detail_selected

# A single Material Morph target accepts both presets without being checked.
root.spx_morph_active_index = root.spx_morph_states.find(states["FadeMultiply"].uid)
mult_data.spx_morph_detail_selected = False
assert bpy.ops.surface_proxy.apply_material_morph_preset(preset="HIDE") == {
    "FINISHED"
}
assert mult_data.offset_type == "ADD"
assert tuple(mult_data.diffuse_color) == (0.0, 0.0, 0.0, -1.0)
assert tuple(mult_data.edge_color) == (0.0, 0.0, 0.0, -1.0)
assert not mult_data.spx_morph_detail_selected
assert bpy.ops.surface_proxy.apply_material_morph_preset(preset="SHOW") == {
    "FINISHED"
}
assert tuple(mult_data.diffuse_color) == (0.0, 0.0, 0.0, 1.0)
assert tuple(mult_data.edge_color) == (0.0, 0.0, 0.0, 1.0)
assert not mult_data.spx_morph_detail_selected
mult_data.offset_type = "MULT"
mult_data.diffuse_color = (1.0, 1.0, 1.0, 0.5)
mult_data.edge_color = (1.0, 1.0, 1.0, 0.5)
morph_editor_module.evaluate_morph_root(root)

# Multiple targets still require at least one checked detail row.
root.spx_morph_active_index = root.spx_morph_states.find(states["PresetBatch"].uid)
assert bpy.ops.surface_proxy.select_morph_details(action="ALL") == {"FINISHED"}
assert all(data.spx_morph_detail_selected for data in preset_morph.data)
assert bpy.ops.surface_proxy.select_morph_details(action="INVERT") == {"FINISHED"}
assert not any(data.spx_morph_detail_selected for data in preset_morph.data)
assert bpy.ops.surface_proxy.apply_material_morph_preset(preset="HIDE") == {
    "CANCELLED"
}

# Checked targets receive the preset and stale parameters are cleared.
assert bpy.ops.surface_proxy.select_morph_details(action="ALL") == {"FINISHED"}
preset_morph.data[1].spx_morph_detail_selected = False
assert bpy.ops.surface_proxy.apply_material_morph_preset(preset="HIDE") == {
    "FINISHED"
}
for preset_data in (preset_morph.data[0],):
    assert preset_data.offset_type == "ADD"
    assert tuple(preset_data.diffuse_color) == (0.0, 0.0, 0.0, -1.0)
    assert tuple(preset_data.specular_color) == (0.0, 0.0, 0.0)
    assert preset_data.shininess == 0.0
    assert tuple(preset_data.ambient_color) == (0.0, 0.0, 0.0)
    assert tuple(preset_data.edge_color) == (0.0, 0.0, 0.0, -1.0)
    assert preset_data.edge_weight == 0.0
    assert tuple(preset_data.texture_factor) == (0.0, 0.0, 0.0, 0.0)
    assert tuple(preset_data.sphere_texture_factor) == (0.0, 0.0, 0.0, 0.0)
    assert tuple(preset_data.toon_texture_factor) == (0.0, 0.0, 0.0, 0.0)
assert preset_morph.data[1].offset_type == "MULT"
assert max(
    abs(actual - expected)
    for actual, expected in zip(
        preset_morph.data[1].diffuse_color,
        (0.2, 0.3, 0.4, 0.5),
        strict=True,
    )
) < 1.0e-6
assert bpy.ops.surface_proxy.select_morph_details(action="ALL") == {"FINISHED"}
assert bpy.ops.surface_proxy.apply_material_morph_preset(preset="SHOW") == {
    "FINISHED"
}
for preset_data in preset_morph.data:
    assert preset_data.offset_type == "ADD"
    assert tuple(preset_data.diffuse_color) == (0.0, 0.0, 0.0, 1.0)
    assert tuple(preset_data.specular_color) == (0.0, 0.0, 0.0)
    assert tuple(preset_data.edge_color) == (0.0, 0.0, 0.0, 1.0)

# Bone-to-Vertex conversion only touches meshes and vertices with direct,
# non-zero weights for a bone referenced by the source Bone Morph.
root.spx_morph_active_index = root.spx_morph_states.find(states["BoneConvert"].uid)
bpy.context.view_layer.objects.active = root
assert bpy.ops.surface_proxy.convert_weighted_bone_morph() == {
    "FINISHED"
}
ensure_morph_states(root)
states = {state.morph_name: state for state in root.spx_morph_states}
assert root.mmd_root.bone_morphs.get("BoneConvertB") is not None
assert root.mmd_root.vertex_morphs.get("BoneConvert") is not None
converted_key = mesh_a.data.shape_keys.key_blocks["BoneConvert"]
converted_basis = converted_key.relative_key
assert (converted_key.data[0].co - converted_basis.data[0].co).length > 1.0e-6
for vertex_index in (1, 2):
    assert (
        converted_key.data[vertex_index].co
        - converted_basis.data[vertex_index].co
    ).length < 1.0e-7
for mesh_object in (mesh_b, custom_mesh, hidden_mesh):
    assert "BoneConvert" not in mesh_object.data.shape_keys.key_blocks

# Selecting a central list row keeps official mmd_tools detail operators aligned.
bone_state_index = root.spx_morph_states.find(states["BoneMove"].uid)
root.spx_morph_active_index = bone_state_index
assert root.mmd_root.active_morph_type == "bone_morphs"
assert root.mmd_root.bone_morphs[root.mmd_root.active_morph].name == "BoneMove"

# Panel drawing only reads this cache; stale data is refreshed outside draw.
root.spx_morph_states[0].morph_name = "Stale"
assert not _morph_states_are_current(root)
ensure_morph_states(root)
assert _morph_states_are_current(root)

# Morph collection order is authoritative. A facial-frame order must never
# reorder the Morph editor, including an empty Morph used as a separator.
separator_morph = root.mmd_root.material_morphs.add()
separator_morph.name = "--Separator--"
root.mmd_root.material_morphs.move(
    len(root.mmd_root.material_morphs) - 1,
    root.mmd_root.material_morphs.find("Hide") + 1,
)
ensure_morph_states(root)
material_order_before_rename = [
    morph.name for morph in root.mmd_root.material_morphs
]
Model(root).initialDisplayFrames(reset=False)
facial = root.mmd_root.display_item_frames["表情"]
facial.data.clear()
show_display_item = facial.data.add()
show_display_item.type = "MORPH"
show_display_item.morph_type = "material_morphs"
show_display_item.name = "ShowHidden"
hide_display_item = facial.data.add()
hide_display_item.type = "MORPH"
hide_display_item.morph_type = "material_morphs"
hide_display_item.name = "Hide"
assert _morph_states_are_current(root)
hide_morph.name = "HideRenamed"
assert not _morph_states_are_current(root)
assert _morph_state_structure_is_current(root)
_refresh_morph_state_metadata(root)
assert _morph_states_are_current(root)
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "HideRenamed" if name == "Hide" else name
    for name in material_order_before_rename
]
assert [(item.morph_type, item.name) for item in facial.data] == [
    ("material_morphs", "ShowHidden"),
    ("material_morphs", "HideRenamed"),
]
hide_morph.name = "Hide"
_refresh_morph_state_metadata(root)
assert _morph_states_are_current(root)
assert [morph.name for morph in root.mmd_root.material_morphs] == (
    material_order_before_rename
)
assert [(item.morph_type, item.name) for item in facial.data] == [
    ("material_morphs", "ShowHidden"),
    ("material_morphs", "Hide"),
]
root.mmd_root.material_morphs.remove(
    root.mmd_root.material_morphs.find("--Separator--")
)
ensure_morph_states(root)
states = {state.morph_name: state for state in root.spx_morph_states}

# Named state paths remain keyframeable, while Morph sorting stays independent
# from the facial frame.
states["Hide"].keyframe_insert(data_path="value", frame=1)
hide_path = states["Hide"].path_from_id("value")
assert any(
    curve.data_path == hide_path for curve in root.animation_data.action.fcurves
)
settings = bpy.context.scene.surface_proxy_creator
settings.morph_editor_root = root
settings.morph_editor_type = "material_morphs"

# Every Morph tab shares a 0 | slider | 1 value row. The endpoint buttons use
# fixed one-unit layouts, while the keyframe decoration remains on state.value.
morph_list_probe = MorphListLayoutProbe()
morph_editor_module.SPX_UL_MorphEditor.draw_item(
    None,
    bpy.context,
    morph_list_probe,
    root,
    states["Hide"],
    0,
    root,
    "spx_morph_active_index",
    root.spx_morph_states.find(states["Hide"].uid),
)
value_properties = [
    record for record in morph_list_probe.properties if record[2] == "value"
]
assert len(value_properties) == 1
slider_layout, slider_state, _name, slider_kwargs = value_properties[0]
assert slider_state == states["Hide"]
assert slider_kwargs.get("slider") is True
assert slider_layout.use_property_decorate
endpoint_operators = [
    record
    for record in morph_list_probe.operators
    if record[1] == "surface_proxy.set_morph_value"
]
assert [record[2].get("text") for record in endpoint_operators] == ["0", "1"]
assert all(record[0].ui_units_x == 1.0 for record in endpoint_operators)
assert [record[3].value for record in endpoint_operators] == [0.0, 1.0]
assert all(record[3].morph_uid == states["Hide"].uid for record in endpoint_operators)
assert all(record[3].root_name == root.name for record in endpoint_operators)
assert states["Hide"].path_from_id("value") == hide_path

# The material browser embeds the complete MMD Texture and MMD Material
# controls for its active material instead of requiring the Properties editor.
settings.mmd_root = root
settings.browser_kind = "MATERIAL"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
settings.browser_index = next(
    index
    for index, browser_item in enumerate(settings.browser_items)
    if browser_item.material == material
)
inspector_probe = InspectorLayoutProbe()
_draw_active_mmd_inspector(inspector_probe, settings)
assert {
    "browser_material_texture_expanded",
    "browser_mmd_material_expanded",
    "material_id",
    "name_j",
    "name_e",
    "comment",
    "diffuse_color",
    "alpha",
    "sphere_texture_type",
    "toon_texture",
} <= set(inspector_probe.properties)
assert inspector_probe.operators.count(
    "surface_proxy.open_browser_material_texture"
) == 2
assert "surface_proxy.copy_browser_material_property_to_checked" in (
    inspector_probe.operators
)

settings.browser_material_texture_expanded = False
settings.browser_mmd_material_expanded = False
collapsed_probe = InspectorLayoutProbe()
_draw_active_mmd_inspector(collapsed_probe, settings)
assert {
    "browser_material_texture_expanded",
    "browser_mmd_material_expanded",
} <= set(collapsed_probe.properties)
assert "material_id" not in collapsed_probe.properties
assert "sphere_texture_type" not in collapsed_probe.properties
assert not collapsed_probe.operators
settings.browser_material_texture_expanded = True
settings.browser_mmd_material_expanded = True

# The real Material Tab draw path reaches the embedded inspector before its
# material-only early return.
inspector_calls = []
original_inspector_draw = mmd_physics_module._draw_active_mmd_inspector
mmd_physics_module._draw_active_mmd_inspector = (
    lambda _layout, _settings: inspector_calls.append(_settings.browser_kind)
)
try:
    mmd_physics_module.draw_browser(InspectorLayoutProbe(), settings)
finally:
    mmd_physics_module._draw_active_mmd_inspector = original_inspector_draw
assert inspector_calls == ["MATERIAL"]

# Field-specific batch copy uses browser checks rather than Blender object
# selection and supports both scalar and array-valued MMD material properties.
for browser_item in settings.browser_items:
    browser_item.selected = browser_item.material in {material, custom_material}
original_batch_values = {
    material: (
        material.mmd_material.alpha,
        tuple(material.mmd_material.diffuse_color),
    ),
    custom_material: (
        custom_material.mmd_material.alpha,
        tuple(custom_material.mmd_material.diffuse_color),
    ),
}
material.mmd_material.alpha = 0.375
custom_material.mmd_material.alpha = 0.875
assert bpy.ops.surface_proxy.copy_browser_material_property_to_checked(
    material_name=material.name,
    property_name="alpha",
) == {"FINISHED"}
assert abs(custom_material.mmd_material.alpha - 0.375) < 1.0e-6
material.mmd_material.diffuse_color = (0.1, 0.2, 0.3)
custom_material.mmd_material.diffuse_color = (0.8, 0.7, 0.6)
assert bpy.ops.surface_proxy.copy_browser_material_property_to_checked(
    material_name=material.name,
    property_name="diffuse_color",
) == {"FINISHED"}
assert max(
    abs(actual - expected)
    for actual, expected in zip(
        custom_material.mmd_material.diffuse_color,
        (0.1, 0.2, 0.3),
        strict=True,
    )
) < 1.0e-6
for browser_item in settings.browser_items:
    browser_item.selected = False
assert bpy.ops.surface_proxy.copy_browser_material_property_to_checked(
    material_name=material.name,
    property_name="alpha",
) == {"CANCELLED"}
for batch_material, (alpha, diffuse_color) in original_batch_values.items():
    batch_material.mmd_material.alpha = alpha
    batch_material.mmd_material.diffuse_color = diffuse_color

assert bpy.ops.surface_proxy.open_browser_material_texture(
    material_name=material.name,
    texture_kind="MAIN",
    filepath="//missing-inspector-texture.png",
) == {"FINISHED"}
assert bpy.ops.surface_proxy.remove_browser_material_texture(
    material_name=material.name,
    texture_kind="MAIN",
) == {"FINISHED"}

# Refresh restores model ShapeKeys that are missing from the Vertex Morph list,
# while minus removes both the metadata row and every matching real/proxy key.
for mesh_object in (mesh_a, mesh_b):
    mesh_object.shape_key_add(name="RefreshOnly")
placeholder = Model(root).morph_slider.placeholder(create=True)
placeholder.shape_key_add(name="RefreshOnly")
placeholder.shape_key_add(name="PlaceholderOnly")
assert root.mmd_root.vertex_morphs.get("RefreshOnly") is None
settings.morph_editor_type = "vertex_morphs"
assert bpy.ops.surface_proxy.refresh_morph_editor() == {"FINISHED"}
refresh_morph = root.mmd_root.vertex_morphs.get("RefreshOnly")
assert refresh_morph is not None
assert refresh_morph.name_e == "RefreshOnly"
assert root.mmd_root.vertex_morphs.get("PlaceholderOnly") is None
refresh_state = next(
    state
    for state in root.spx_morph_states
    if state.morph_type == "vertex_morphs" and state.morph_name == "RefreshOnly"
)
for state in root.spx_morph_states:
    state.selected = False
root.spx_morph_active_index = root.spx_morph_states.find(refresh_state.uid)
assert bpy.ops.surface_proxy.remove_selected_morphs() == {"FINISHED"}
assert root.mmd_root.vertex_morphs.get("RefreshOnly") is None
for mesh_object in (mesh_a, mesh_b):
    assert "RefreshOnly" not in mesh_object.data.shape_keys.key_blocks
assert "RefreshOnly" not in placeholder.data.shape_keys.key_blocks
placeholder.shape_key_remove(placeholder.data.shape_keys.key_blocks["PlaceholderOnly"])
settings.morph_editor_type = "material_morphs"

# New Morphs are inserted directly below the active row instead of appended.
states = {state.morph_name: state for state in root.spx_morph_states}
root.spx_morph_active_index = root.spx_morph_states.find(states["Hide"].uid)
material_names_before_add = [
    morph.name for morph in root.mmd_root.material_morphs
]
facial_items_before_add = [
    (item.type, item.morph_type, item.name) for item in facial.data
]
assert bpy.ops.surface_proxy.add_morph() == {"FINISHED"}
new_state = root.spx_morph_states[root.spx_morph_active_index]
assert new_state.morph_name == "新建 Morph"
hide_index = material_names_before_add.index("Hide")
assert [morph.name for morph in root.mmd_root.material_morphs] == (
    material_names_before_add[: hide_index + 1]
    + ["新建 Morph"]
    + material_names_before_add[hide_index + 1 :]
)
assert [
    (item.type, item.morph_type, item.name) for item in facial.data
] == facial_items_before_add
for state in root.spx_morph_states:
    state.selected = state.uid == new_state.uid
assert bpy.ops.surface_proxy.remove_selected_morphs() == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == (
    material_names_before_add
)

material_states = [
    state for state in root.spx_morph_states if state.morph_type == "material_morphs"
]
for state in material_states:
    state.selected = False
material_states[0].selected = True
material_states[-1].selected = True
assert bpy.ops.surface_proxy.select_morph_interval() == {"FINISHED"}
assert all(state.selected for state in material_states)
for state in material_states:
    state.selected = False
material_states[0].selected = True
assert bpy.ops.surface_proxy.select_morph_interval() == {"CANCELLED"}
material_states[0].selected = False
hide_morph.name_e = "OldHideEnglish"
show_morph.name_e = "OldShowEnglish"
states["Hide"].selected = True
states["ShowHidden"].selected = True
assert bpy.ops.surface_proxy.copy_morph_japanese_names_to_english() == {
    "FINISHED"
}
assert hide_morph.name_e == hide_morph.name
assert show_morph.name_e == show_morph.name
assert morph_editor_module._parse_morph_name_translations(
    '```json\n["Eye+", "[Hide]-"]\n```',
    2,
) == ["Eye+", "[Hide]-"]
assert morph_editor_module._validate_morph_name_translations(
    ["目+", "[隐藏]-"],
    ["Eye+", "[Hide]-"],
) == ["Eye+", "[Hide]-"]
assert morph_editor_module._compact_english_morph_name("cross eyed") == "CrossEyed"
assert morph_editor_module._compact_english_morph_name("+lower eyes") == "+LowerEyes"
assert morph_editor_module._compact_english_morph_name("cross-eyed") == "Cross-Eyed"
assert morph_editor_module._normalize_morph_direction_tokens("Emo3Left") == "Emo3_L"
assert morph_editor_module._normalize_morph_direction_tokens("LeftEye") == "Eye_L"
assert morph_editor_module._normalize_morph_direction_tokens("RightEye") == "Eye_R"
assert morph_editor_module._normalize_morph_direction_tokens(
    "PupilUpRight"
) == "Pupil_Up_R"
assert morph_editor_module._normalize_morph_direction_tokens(
    "LeftPupilDown"
) == "Pupil_Down_L"
assert morph_editor_module._normalize_morph_direction_tokens(
    "Pupil_Up_R"
) == "Pupil_Up_R"
assert morph_editor_module._validate_morph_name_translations(
    ["emo3左"],
    ["Emo3_L"],
) == ["Emo3_L"]
try:
    morph_editor_module._validate_morph_name_translations(
        ["目+"],
        ["VeryLongEyeNameX+"],
    )
except ValueError as exc:
    assert "超过 16 个字符" in str(exc)
else:
    raise AssertionError("Translations longer than 16 characters must be rejected")
try:
    morph_editor_module._validate_morph_name_translations(["目+"], ["Eye-"])
except ValueError as exc:
    assert "完整保留原名称符号" in str(exc)
else:
    raise AssertionError("Translations that change protected symbols must be rejected")
assert morph_editor_module._morph_ai_chat_completions_url(
    "https://api.example.com"
) == "https://api.example.com/v1/chat/completions"
assert morph_editor_module._morph_ai_chat_completions_url(
    "https://api.example.com/v1/"
) == "https://api.example.com/v1/chat/completions"
original_addon_preferences = morph_editor_module._addon_preferences
original_translation_request = morph_editor_module._request_morph_name_translations
morph_editor_module._addon_preferences = lambda _context: SimpleNamespace()
morph_editor_module._request_morph_name_translations = (
    lambda _preferences, names: [f"{name}_AI" for name in names]
)
try:
    assert bpy.ops.surface_proxy.translate_morph_names_with_ai() == {"FINISHED"}
finally:
    morph_editor_module._addon_preferences = original_addon_preferences
    morph_editor_module._request_morph_name_translations = original_translation_request
assert hide_morph.name_e == f"{hide_morph.name}_AI"
assert show_morph.name_e == f"{show_morph.name}_AI"
states["Hide"].selected = False
states["ShowHidden"].selected = False
assert bpy.ops.surface_proxy.copy_morph_japanese_names_to_english() == {
    "CANCELLED"
}
assert bpy.ops.surface_proxy.translate_morph_names_with_ai() == {"CANCELLED"}
states["FadeMultiply"].selected = True
facial_items_before_reorder = [
    (item.type, item.morph_type, item.name) for item in facial.data
]
assert bpy.ops.surface_proxy.reorder_morphs(action="TOP") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "FadeMultiply",
    "Hide",
    "ShowHidden",
    "PresetBatch",
]
assert [
    (item.type, item.morph_type, item.name) for item in facial.data
] == facial_items_before_reorder
states = {state.morph_name: state for state in root.spx_morph_states}
states["FadeMultiply"].selected = False
states["Hide"].selected = True
states["ShowHidden"].selected = True
root.spx_morph_active_index = root.spx_morph_states.find(
    states["FadeMultiply"].uid
)
assert bpy.ops.surface_proxy.reorder_morphs(action="BEFORE") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "Hide",
    "ShowHidden",
    "FadeMultiply",
    "PresetBatch",
]
states = {state.morph_name: state for state in root.spx_morph_states}
states["Hide"].selected = False
states["ShowHidden"].selected = False
states["Hide"].selected = True
root.spx_morph_active_index = root.spx_morph_states.find(
    states["ShowHidden"].uid
)
assert bpy.ops.surface_proxy.reorder_morphs(action="AFTER") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "ShowHidden",
    "Hide",
    "FadeMultiply",
    "PresetBatch",
]
states = {state.morph_name: state for state in root.spx_morph_states}
root.spx_morph_active_index = root.spx_morph_states.find(states["Hide"].uid)
assert bpy.ops.surface_proxy.reorder_morphs(action="BEFORE") == {"CANCELLED"}
states["Hide"].selected = False
for state in root.spx_morph_states:
    state.selected = False

# The four directional moves fall back to the blue active row when nothing is
# checked. The two anchor moves still require an explicit checked block.
states = {state.morph_name: state for state in root.spx_morph_states}
root.spx_morph_active_index = root.spx_morph_states.find(states["FadeMultiply"].uid)
assert bpy.ops.surface_proxy.reorder_morphs(action="TOP") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "FadeMultiply",
    "ShowHidden",
    "Hide",
    "PresetBatch",
]
assert bpy.ops.surface_proxy.reorder_morphs(action="DOWN") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "ShowHidden",
    "FadeMultiply",
    "Hide",
    "PresetBatch",
]
states = {state.morph_name: state for state in root.spx_morph_states}
root.spx_morph_active_index = root.spx_morph_states.find(states["ShowHidden"].uid)
assert bpy.ops.surface_proxy.reorder_morphs(action="BOTTOM") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "FadeMultiply",
    "Hide",
    "PresetBatch",
    "ShowHidden",
]
assert bpy.ops.surface_proxy.reorder_morphs(action="UP") == {"FINISHED"}
assert [morph.name for morph in root.mmd_root.material_morphs] == [
    "FadeMultiply",
    "Hide",
    "ShowHidden",
    "PresetBatch",
]
order_before_anchor_moves = [
    morph.name for morph in root.mmd_root.material_morphs
]
assert bpy.ops.surface_proxy.reorder_morphs(action="BEFORE") == {"CANCELLED"}
assert bpy.ops.surface_proxy.reorder_morphs(action="AFTER") == {"CANCELLED"}
assert [
    morph.name for morph in root.mmd_root.material_morphs
] == order_before_anchor_moves
assert [
    (item.type, item.morph_type, item.name) for item in facial.data
] == facial_items_before_reorder
root.animation_data_clear()
states = {state.morph_name: state for state in root.spx_morph_states}

# Material detail add collects every non-empty slot from selected model meshes,
# removes shared-material duplicates, and inserts the new block after the active row.
smart_material_a = make_material("SmartMaterialA")
smart_material_b = make_material("SmartMaterialB")
smart_morph = root.mmd_root.material_morphs.add()
smart_morph.name = "SmartMaterialAdd"
smart_anchor = smart_morph.data.add()
smart_anchor.related_mesh = hidden_mesh.data.name
smart_anchor.material = hidden_material.name
smart_tail = smart_morph.data.add()
smart_tail.related_mesh = custom_mesh.data.name
smart_tail.material = custom_material.name
smart_morph.active_data = 0
ensure_morph_states(root)
states = {state.morph_name: state for state in root.spx_morph_states}
root.spx_morph_active_index = root.spx_morph_states.find(
    states["SmartMaterialAdd"].uid
)
for scene_object in bpy.context.selected_objects:
    scene_object.select_set(False)
original_material_order = ordered_materials(root, FnModel)
custom_mesh.data.materials[0] = smart_material_a
hidden_mesh.data.materials[0] = smart_material_b
mesh_a.select_set(True)
custom_mesh.select_set(True)
hidden_mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh_a
set_material_order(
    root,
    [smart_material_b, material, smart_material_a]
    + [
        ordered_material
        for ordered_material in original_material_order
        if ordered_material not in {smart_material_b, material, smart_material_a}
    ],
)
assert bpy.ops.surface_proxy.add_morph_offset() == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    smart_material_b.name,
    material.name,
    smart_material_a.name,
    custom_material.name,
]
assert [data.related_mesh for data in smart_morph.data[1:4]] == [
    hidden_mesh.data.name,
    mesh_a.data.name,
    custom_mesh.data.name,
]
assert smart_morph.active_data == 1
assert bpy.ops.surface_proxy.add_morph_offset() == {"CANCELLED"}
assert len(smart_morph.data) == 5
custom_mesh.data.materials[0] = custom_material
hidden_mesh.data.materials[0] = hidden_material
set_material_order(root, original_material_order)
smart_morph.data.move(1, 3)

# Detail interval selection fills only the rows between the first and last
# checked endpoints and rejects a single endpoint without changing selection.
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}
smart_morph.data[1].spx_morph_detail_selected = True
smart_morph.data[4].spx_morph_detail_selected = True
assert bpy.ops.surface_proxy.select_morph_details(action="INTERVAL") == {
    "FINISHED"
}
assert [data.spx_morph_detail_selected for data in smart_morph.data] == [
    False,
    True,
    True,
    True,
    True,
]
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}
smart_morph.data[2].spx_morph_detail_selected = True
assert bpy.ops.surface_proxy.select_morph_details(action="INTERVAL") == {
    "CANCELLED"
}
assert [data.spx_morph_detail_selected for data in smart_morph.data] == [
    False,
    False,
    True,
    False,
    False,
]
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}

# Detail sorting keeps the checked rows stable and retains the blue active row.
smart_morph.data[2].spx_morph_detail_selected = True
smart_morph.data[4].spx_morph_detail_selected = True
smart_morph.active_data = 0
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="AFTER") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    smart_material_a.name,
    custom_material.name,
    material.name,
    smart_material_b.name,
]
assert smart_morph.active_data == 0
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="TOP") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    smart_material_a.name,
    custom_material.name,
    hidden_material.name,
    material.name,
    smart_material_b.name,
]
assert smart_morph.active_data == 2
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="DOWN") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    smart_material_a.name,
    custom_material.name,
    material.name,
    smart_material_b.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="BOTTOM") == {
    "FINISHED"
}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    material.name,
    smart_material_b.name,
    smart_material_a.name,
    custom_material.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="UP") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    material.name,
    smart_material_a.name,
    custom_material.name,
    smart_material_b.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="BEFORE") == {
    "FINISHED"
}
assert [data.material for data in smart_morph.data] == [
    smart_material_a.name,
    custom_material.name,
    hidden_material.name,
    material.name,
    smart_material_b.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="AFTER") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    smart_material_a.name,
    custom_material.name,
    material.name,
    smart_material_b.name,
]
assert smart_morph.active_data == 0
smart_morph.data[0].spx_morph_detail_selected = True
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="BEFORE") == {
    "CANCELLED"
}
smart_morph.data[0].spx_morph_detail_selected = False
for data in smart_morph.data:
    data.spx_morph_detail_selected = False

# Detail lists use the same implicit active-row fallback for the four
# directional moves, while anchor moves still require a checked block.
smart_morph.active_data = 2
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="TOP") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    custom_material.name,
    hidden_material.name,
    smart_material_a.name,
    material.name,
    smart_material_b.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="DOWN") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    hidden_material.name,
    custom_material.name,
    smart_material_a.name,
    material.name,
    smart_material_b.name,
]
smart_morph.active_data = 0
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="BOTTOM") == {
    "FINISHED"
}
assert [data.material for data in smart_morph.data] == [
    custom_material.name,
    smart_material_a.name,
    material.name,
    smart_material_b.name,
    hidden_material.name,
]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="UP") == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    custom_material.name,
    smart_material_a.name,
    material.name,
    hidden_material.name,
    smart_material_b.name,
]
detail_order_before_anchor_moves = [data.material for data in smart_morph.data]
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="BEFORE") == {
    "CANCELLED"
}
assert bpy.ops.surface_proxy.reorder_morph_offsets(action="AFTER") == {
    "CANCELLED"
}
assert [data.material for data in smart_morph.data] == detail_order_before_anchor_moves

# Detail minus deletes every checked row when checks exist, otherwise it falls
# back to the blue active row.
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}
detail_materials_before_remove = [data.material for data in smart_morph.data]
smart_morph.active_data = 4
smart_morph.data[1].spx_morph_detail_selected = True
smart_morph.data[3].spx_morph_detail_selected = True
assert bpy.ops.surface_proxy.remove_morph_offset() == {"FINISHED"}
assert [data.material for data in smart_morph.data] == [
    detail_materials_before_remove[index] for index in (0, 2, 4)
]
assert smart_morph.active_data == 1
active_material_before_remove = smart_morph.data[smart_morph.active_data].material
assert bpy.ops.surface_proxy.remove_morph_offset() == {"FINISHED"}
assert active_material_before_remove not in {
    data.material for data in smart_morph.data
}
assert len(smart_morph.data) == 2

# Non-material tabs keep the original empty-offset add behavior.
root.spx_morph_active_index = root.spx_morph_states.find(states["UVShift"].uid)
uv_offset_count = len(uv_morph.data)
assert bpy.ops.surface_proxy.add_morph_offset() == {"FINISHED"}
assert len(uv_morph.data) == uv_offset_count + 1
assert bpy.ops.surface_proxy.remove_morph_offset() == {"FINISHED"}
assert len(uv_morph.data) == uv_offset_count
states = {state.morph_name: state for state in root.spx_morph_states}

# A single central Vertex Morph value updates every matching ShapeKey.
states["Smile"].value = 0.625
assert abs(mesh_a.data.shape_keys.key_blocks["Smile"].value - 0.625) < 1.0e-6
assert abs(mesh_b.data.shape_keys.key_blocks["Smile"].value - 0.625) < 1.0e-6
assert abs(custom_mesh.data.shape_keys.key_blocks["Smile"].value - 0.625) < 1.0e-6

# Vertex detail object buttons select the exact mesh and activate its ShapeKey.
root.spx_morph_active_index = root.spx_morph_states.find(states["Smile"].uid)
vertex_targets = [
    mesh_object
    for mesh_object in FnModel.iterate_mesh_objects(root)
    if mesh_object.data.shape_keys.key_blocks.get("Smile") is not None
]
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}
vertex_targets[0].spx_morph_vertex_target_selected = True
vertex_targets[-1].spx_morph_vertex_target_selected = True
assert bpy.ops.surface_proxy.select_morph_details(action="INTERVAL") == {
    "FINISHED"
}
assert all(target.spx_morph_vertex_target_selected for target in vertex_targets)
assert bpy.ops.surface_proxy.select_morph_details(action="NONE") == {"FINISHED"}
vertex_targets[1].spx_morph_vertex_target_selected = True
assert bpy.ops.surface_proxy.select_morph_details(action="INTERVAL") == {
    "CANCELLED"
}
assert [
    target.spx_morph_vertex_target_selected for target in vertex_targets
] == [index == 1 for index in range(len(vertex_targets))]

mesh_b.select_set(True)
result = bpy.ops.surface_proxy.select_vertex_morph_object(
    root_name=root.name,
    object_name=mesh_a.name,
    morph_uid=states["Smile"].uid,
)
assert result == {"FINISHED"}
assert bpy.context.view_layer.objects.active == mesh_a
assert mesh_a.select_get()
assert not mesh_b.select_get()
assert mesh_a.active_shape_key.name == "Smile"
mesh_a.spx_morph_vertex_target_selected = True
assert mesh_a.spx_morph_vertex_target_selected
assert not mesh_a.spx_morph_uv_target_selected

# The first Material Morph adjustment installs one output bridge on the body.
assert bridge_nodes(material) == []
states["Hide"].value = 0.4
body_bridges = bridge_nodes(material)
assert len(body_bridges) == 1
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.6) < 1.0e-6
assert body_bridges[0].inputs["Add Strength"].default_value > 0.0
custom_bridges = bridge_nodes(custom_material)
assert len(custom_bridges) == 1
assert abs(custom_bridges[0].inputs["Opacity"].default_value - 0.6) < 1.0e-6

# ADD alpha starts from the PMX material's authored base alpha.
assert bridge_nodes(hidden_material) == []
states["ShowHidden"].value = 0.5
hidden_bridges = bridge_nodes(hidden_material)
assert len(hidden_bridges) == 1
assert abs(hidden_bridges[0].inputs["Opacity"].default_value - 0.5) < 1.0e-6
assert abs(hidden_shader.inputs["Alpha"].default_value - 1.0) < 1.0e-6
states["ShowHidden"].value = 0.0
assert abs(hidden_bridges[0].inputs["Opacity"].default_value - 0.0) < 1.0e-6

# Repeated adjustments only update the existing bridge.
states["Hide"].value = 0.5
assert bridge_nodes(material) == body_bridges
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.5) < 1.0e-6

# MULT and ADD are accumulated independently: 0.8 + (-0.25) = 0.55.
states["Hide"].value = 0.25
states["FadeMultiply"].value = 0.4
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.55) < 1.0e-6

# An outline material created later is discovered and receives its own bridge.
states["FadeMultiply"].value = 0.0
edge_material = make_material("mmd_edge." + material.name, "ShaderNodeEmission")
assert bridge_nodes(edge_material) == []
states["Hide"].value = 0.5
assert bridge_nodes(edge_material) == []

# Body and outline alpha follow their independent PMX Material Morph channels.
states["Hide"].value = 1.0
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.0) < 1.0e-6
assert bridge_nodes(edge_material) == []
states["Hide"].value = 0.0
states["FadeMultiply"].value = 0.5
edge_bridges = bridge_nodes(edge_material)
assert len(edge_bridges) == 1
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.75) < 1.0e-6
assert abs(edge_bridges[0].inputs["Opacity"].default_value - 0.75) < 1.0e-6

# Reset restores neutral bridge inputs without removing or duplicating nodes.
states["Hide"].value = 0.0
states["FadeMultiply"].value = 0.0
assert abs(body_bridges[0].inputs["Opacity"].default_value - 1.0) < 1.0e-6
assert abs(edge_bridges[0].inputs["Opacity"].default_value - 1.0) < 1.0e-6
assert len(bridge_nodes(material)) == 1
assert len(bridge_nodes(edge_material)) == 1

# Keyframed central values are evaluated during frame changes.
states["Hide"].value = 0.0
states["Hide"].keyframe_insert(data_path="value", frame=1)
states["Hide"].value = 1.0
states["Hide"].keyframe_insert(data_path="value", frame=2)
bpy.context.scene.frame_set(1)
assert abs(body_bridges[0].inputs["Opacity"].default_value - 1.0) < 1.0e-6
bpy.context.scene.frame_set(2)
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.0) < 1.0e-6
root.animation_data_clear()
states["Hide"].value = 0.0

# Bone Morph values lazily create the official non-material runtime only.
states["BoneMove"].value = 0.3
assert "spx_morph_runtime_error" not in root, root.get("spx_morph_runtime_error")
assert abs(model.morph_slider.get("BoneMove").value - 0.3) < 1.0e-6
placeholder = model.morph_slider.placeholder()
for mesh_object in (mesh_a, mesh_b, custom_mesh, hidden_mesh):
    shape_keys = mesh_object.data.shape_keys
    assert not any(key.name.startswith("mmd_bind") for key in shape_keys.key_blocks)
    smile = shape_keys.key_blocks["Smile"]
    assert not smile.mute
    animation_data = shape_keys.animation_data
    assert animation_data is None or not any(
        curve.data_path == smile.path_from_id("value")
        and any(
            target.id == placeholder
            for variable in curve.driver.variables
            for target in variable.targets
        )
        for curve in animation_data.drivers
    )
assert not any(
    node.name.startswith("mmd_bind") for node in material.node_tree.nodes
)

# A mesh-local ShapeKey remains directly editable after Bone/UV runtime binding.
mesh_a.data.shape_keys.key_blocks["Smile"].value = 0.125
assert abs(mesh_a.data.shape_keys.key_blocks["Smile"].value - 0.125) < 1.0e-6
assert abs(mesh_b.data.shape_keys.key_blocks["Smile"].value - 0.625) < 1.0e-6
states["Smile"].value = 0.6
states["Smile"].value = 0.625
for mesh_object in (mesh_a, mesh_b, custom_mesh, hidden_mesh):
    assert abs(mesh_object.data.shape_keys.key_blocks["Smile"].value - 0.625) < 1.0e-6

# The add-on preview switches away from temporary layers before deleting them.
_create_uv_morph_preview(root, mesh_a, uv_morph)
assert mesh_a.data.uv_layers.active.name.startswith("__uv.")
_clear_uv_morph_preview(root)
assert mesh_a.data.uv_layers.active.name == "UVMap"
assert not any(layer.name.startswith("__uv.") for layer in mesh_a.data.uv_layers)

# Group Morph evaluation reuses the lazy non-material mmd_tools runtime while
# Material Morph output remains owned by this add-on.
collection_group = root.mmd_root.group_morphs.add()
collection_group.name = "CollectSelected"
existing_collection_offset = collection_group.data.add()
existing_collection_offset.morph_type = "material_morphs"
existing_collection_offset.name = "Hide"
existing_collection_offset.factor = 0.5
ensure_morph_states(root)
states = {state.morph_name: state for state in root.spx_morph_states}
for state in root.spx_morph_states:
    state.selected = state.morph_name in {"Hide", "UVShift", "BoneMove", "Smile"}
root.spx_morph_active_index = root.spx_morph_states.find(
    states["CollectSelected"].uid
)
assert bpy.ops.surface_proxy.collect_selected_morphs_into_group() == {"FINISHED"}
assert {
    (data.morph_type, data.name)
    for data in collection_group.data
} == {
    ("material_morphs", "Hide"),
    ("uv_morphs", "UVShift"),
    ("bone_morphs", "BoneMove"),
    ("vertex_morphs", "Smile"),
}
assert sum(
    data.morph_type == "material_morphs" and data.name == "Hide"
    for data in collection_group.data
) == 1
assert all(
    abs(data.factor - 1.0) < 1.0e-6
    for data in collection_group.data
    if (data.morph_type, data.name) != ("material_morphs", "Hide")
)
assert bpy.ops.surface_proxy.collect_selected_morphs_into_group() == {"CANCELLED"}
for state in root.spx_morph_states:
    state.selected = False
root.mmd_root.group_morphs.remove(
    root.mmd_root.group_morphs.find("CollectSelected")
)
ensure_morph_states(root)

group_morph = root.mmd_root.group_morphs.add()
group_morph.name = "GroupHide"
group_offset = group_morph.data.add()
group_offset.morph_type = "material_morphs"
group_offset.name = "Hide"
group_offset.factor = 0.5
group_vertex_offset = group_morph.data.add()
group_vertex_offset.morph_type = "vertex_morphs"
group_vertex_offset.name = "Smile"
group_vertex_offset.factor = 0.25
group_bone_offset = group_morph.data.add()
group_bone_offset.morph_type = "bone_morphs"
group_bone_offset.name = "BoneMove"
group_bone_offset.factor = 2.4
group_offset.spx_morph_detail_selected = True
assert group_offset.spx_morph_detail_selected
ensure_morph_states(root)
states = {state.morph_name: state for state in root.spx_morph_states}
states["GroupHide"].value = 1.0
assert "spx_morph_runtime_error" not in root, root.get("spx_morph_runtime_error")
assert bool(root.get("spx_morph_lightweight_bound", False))
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.5) < 1.0e-6
assert abs(edge_bridges[0].inputs["Opacity"].default_value - 1.0) < 1.0e-6
group_slider = model.morph_slider.get("GroupHide")
assert group_slider is None or abs(group_slider.value) < 1.0e-6
assert abs(model.morph_slider.get("Smile").value) < 1.0e-6
for mesh_object in (mesh_a, mesh_b, custom_mesh, hidden_mesh):
    assert abs(mesh_object.data.shape_keys.key_blocks["Smile"].value - 0.875) < 1.0e-6
assert abs(model.morph_slider.get("BoneMove").value - 2.7) < 1.0e-6
assert model.morph_slider.get("BoneMove").slider_max >= 2.7
assert not any(
    node.name.startswith("mmd_bind") for node in material.node_tree.nodes
)

# Editing a Group Morph detail factor through RNA immediately recomputes the
# already-active group instead of waiting for its top-level slider to move.
group_offset.spx_morph_factor_live = 0.25
assert group_offset.factor == 0.25
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.75) < 1.0e-6
group_offset.spx_morph_factor_live = 0.5
assert group_offset.factor == 0.5
assert abs(body_bridges[0].inputs["Opacity"].default_value - 0.5) < 1.0e-6

# Numeric entry is unrestricted while mouse dragging keeps the 0..1 soft range.
value_property = root.spx_morph_states[0].bl_rna.properties["value"]
assert value_property.soft_min == 0.0
assert value_property.soft_max == 1.0
assert value_property.hard_min < -1.0e20
assert value_property.hard_max > 1.0e20
states["GroupHide"].value = 0.0
assert abs(model.morph_slider.get("BoneMove").value - 0.3) < 1.0e-6
states["Smile"].value = -2.5
for mesh_object in (mesh_a, mesh_b, custom_mesh, hidden_mesh):
    smile = mesh_object.data.shape_keys.key_blocks["Smile"]
    assert abs(smile.value + 2.5) < 1.0e-6
    assert smile.slider_min <= -3.0
states["Smile"].value = 3.25
for mesh_object in (mesh_a, mesh_b, custom_mesh, hidden_mesh):
    smile = mesh_object.data.shape_keys.key_blocks["Smile"]
    assert abs(smile.value - 3.25) < 1.0e-6
    assert smile.slider_max >= 4.0
states["Smile"].value = 0.0

# A negative ADD weight reverses the RGB contribution instead of being clamped
# at the editor property boundary.
states["Hide"].value = -1.0
assert abs(body_bridges[0].inputs["Tint Color"].default_value[0] - 0.75) < 1.0e-6
assert abs(body_bridges[0].inputs["Tint Color"].default_value[1] - 1.0) < 1.0e-6
states["Hide"].value = 0.0

# Imported placeholder curves migrate to stable UID paths on the MMD Root.
root.animation_data_clear()
model.morph_slider.create()
placeholder_keys = placeholder.data.shape_keys
placeholder_keys.animation_data_clear()
source_action = bpy.data.actions.new("SyntheticVmd_facial")
placeholder_keys.animation_data_create().action = source_action
for name in ("Smile", "Hide", "BoneMove", "UVShift", "GroupHide"):
    key_block = placeholder_keys.key_blocks[name]
    curve = source_action.fcurves.new(key_block.path_from_id("value"))
    curve.keyframe_points.insert(10.0, 0.0)
    curve.keyframe_points.insert(20.0, 1.0)

mesh_action = bpy.data.actions.new("SyntheticVmd_mesh")
mesh_a.data.shape_keys.animation_data_create().action = mesh_action
mesh_curve = mesh_action.fcurves.new(
    mesh_a.data.shape_keys.key_blocks["Smile"].path_from_id("value")
)
mesh_curve.keyframe_points.insert(10.0, 0.0)
mesh_curve.keyframe_points.insert(20.0, 1.0)

imported_uids = _migrate_placeholder_animation(root)
assert imported_uids == {
    states[name].uid
    for name in ("Smile", "Hide", "BoneMove", "UVShift", "GroupHide")
}
destination_paths = {curve.data_path for curve in root.animation_data.action.fcurves}
assert {
    _morph_state_data_path(states[name])
    for name in ("Smile", "Hide", "BoneMove", "UVShift", "GroupHide")
}.issubset(destination_paths)
_remove_imported_shape_key_curves(root)
assert not source_action.fcurves
assert not mesh_action.fcurves
_preinitialize_imported_morphs(root, imported_uids)
bpy.context.scene.frame_set(20)
assert abs(states["Smile"].value - 1.0) < 1.0e-6
assert abs(states["Hide"].value - 1.0) < 1.0e-6
assert abs(states["BoneMove"].value - 1.0) < 1.0e-6
assert abs(states["UVShift"].value - 1.0) < 1.0e-6
assert abs(states["GroupHide"].value - 1.0) < 1.0e-6
assert bool(root.get("spx_morph_lightweight_bound", False))
assert "spx_morph_runtime_error" not in root, root.get("spx_morph_runtime_error")

# Root-side Morph curves are bridged back to ShapeKey curves transactionally
# so the stock mmd_tools VMD exporter can serialize the same frames and values.
morph_editor_module._install_vmd_io_hooks()
previous_placeholder_action = placeholder_keys.animation_data.action
previous_basis_mute = placeholder_keys.key_blocks[0].mute
for scene_object in tuple(bpy.context.selected_objects):
    scene_object.select_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
with tempfile.TemporaryDirectory(prefix="mmd-station-vmd-") as directory:
    output_path = pathlib.Path(directory) / "morph-roundtrip.vmd"
    assert bpy.ops.mmd_tools.export_vmd(
        filepath=str(output_path),
        use_frame_range=False,
    ) == {"FINISHED"}
    exported_vmd = vmd.File()
    exported_vmd.load(filepath=str(output_path))
    first_export = {}
    for name in ("Smile", "Hide", "BoneMove", "UVShift", "GroupHide"):
        frame_weights = {
            int(key.frame_number): float(key.weight)
            for key in exported_vmd.shapeKeyAnimation[name]
        }
        assert abs(frame_weights[9] - 0.0) < 1.0e-6
        assert abs(frame_weights[19] - 1.0) < 1.0e-6
        first_export[name] = frame_weights
    assert placeholder_keys.animation_data.action == previous_placeholder_action
    assert placeholder_keys.key_blocks[0].mute == previous_basis_mute
    assert bpy.data.actions.get(".MMD Station VMD Export Morph") is None

    # A real stock mmd_tools import is intercepted in the opposite direction:
    # imported ShapeKey curves become the same keyframeable central sliders.
    root.animation_data_clear()
    bpy.context.scene.frame_set(1)
    assert bpy.ops.mmd_tools.import_vmd(
        filepath=str(output_path),
        scale=1.0,
        margin=0,
        create_new_action=True,
    ) == {"FINISHED"}
    imported_paths = {curve.data_path for curve in root.animation_data.action.fcurves}
    assert {
        _morph_state_data_path(states[name])
        for name in ("Smile", "Hide", "BoneMove", "UVShift", "GroupHide")
    }.issubset(imported_paths)
    imported_placeholder_action = placeholder_keys.animation_data.action

    roundtrip_path = pathlib.Path(directory) / "morph-roundtrip-second.vmd"
    assert bpy.ops.mmd_tools.export_vmd(
        filepath=str(roundtrip_path),
        use_frame_range=False,
    ) == {"FINISHED"}
    roundtrip_vmd = vmd.File()
    roundtrip_vmd.load(filepath=str(roundtrip_path))
    for name, expected in first_export.items():
        actual = {
            int(key.frame_number): float(key.weight)
            for key in roundtrip_vmd.shapeKeyAnimation[name]
        }
        assert actual == expected, (name, expected, actual)

    # Morph-only export from an active model mesh receives missing non-Vertex
    # names transactionally and restores the mesh ShapeKey layout afterwards.
    mesh_key_names = tuple(mesh_a.data.shape_keys.key_blocks.keys())
    mesh_action_before_export = mesh_a.data.shape_keys.animation_data.action
    root.select_set(False)
    mesh_a.select_set(True)
    bpy.context.view_layer.objects.active = mesh_a
    mesh_only_path = pathlib.Path(directory) / "morph-only.vmd"
    assert bpy.ops.mmd_tools.export_vmd(
        filepath=str(mesh_only_path),
        use_frame_range=False,
    ) == {"FINISHED"}
    mesh_only_vmd = vmd.File()
    mesh_only_vmd.load(filepath=str(mesh_only_path))
    for name, expected in first_export.items():
        actual = {
            int(key.frame_number): float(key.weight)
            for key in mesh_only_vmd.shapeKeyAnimation[name]
        }
        assert actual == expected, (name, expected, actual)
    assert tuple(mesh_a.data.shape_keys.key_blocks.keys()) == mesh_key_names
    assert mesh_a.data.shape_keys.animation_data.action == mesh_action_before_export
    mesh_a.select_set(False)
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
assert placeholder_keys.animation_data.action == imported_placeholder_action
assert placeholder_keys.key_blocks[0].mute == previous_basis_mute
assert bpy.data.actions.get(".MMD Station VMD Export Morph") is None

# Renaming a bound vertex-group UV Morph rebuilds the runtime scale path instead
# of leaving the dummy-armature driver pointed at the old collection key.
dummy_armature = model.morph_slider.dummy_armature


def uv_runtime_target_paths():
    return {
        target.data_path
        for curve in dummy_armature.animation_data.drivers
        for variable in curve.driver.variables
        for target in variable.targets
        if target.data_path
    }


assert 'mmd_root.uv_morphs["RenameUV"].vertex_group_scale' in (
    uv_runtime_target_paths()
)
rename_uv_state = next(
    state
    for state in root.spx_morph_states
    if state.morph_type == "uv_morphs" and state.morph_name == "RenameUV"
)
rename_uv_state.value = 0.75
rename_uv_morph.name = "RenamedUV"
_refresh_morph_state_metadata(root)
assert mesh_a.vertex_groups.get("UV_RenamedUV+X") is not None
assert mesh_a.vertex_groups.get("UV_RenameUV+X") is None
assert abs(model.morph_slider.get("RenamedUV").value - 0.75) < 1.0e-6
assert 'mmd_root.uv_morphs["RenamedUV"].vertex_group_scale' in (
    uv_runtime_target_paths()
)
assert 'mmd_root.uv_morphs["RenameUV"].vertex_group_scale' not in (
    uv_runtime_target_paths()
)

# A saved legacy file can already have matching state/morph names while its
# bound driver still targets the pre-rename collection key. The explicit
# refresh button must force a runtime rebuild even without a fresh rename.
scale_target = next(
    target
    for curve in dummy_armature.animation_data.drivers
    for variable in curve.driver.variables
    for target in variable.targets
    if target.data_path
    == 'mmd_root.uv_morphs["RenamedUV"].vertex_group_scale'
)
scale_target.data_path = 'mmd_root.uv_morphs["LegacyRenameUV"].vertex_group_scale'
assert _morph_states_are_current(root)
assert bpy.ops.surface_proxy.refresh_morph_editor() == {"FINISHED"}
assert 'mmd_root.uv_morphs["RenamedUV"].vertex_group_scale' in (
    uv_runtime_target_paths()
)
assert 'mmd_root.uv_morphs["LegacyRenameUV"].vertex_group_scale' not in (
    uv_runtime_target_paths()
)
assert abs(model.morph_slider.get("RenamedUV").value - 0.75) < 1.0e-6

# The UV-tab minus removes the Morph plus its encoded vertex groups and bound
# runtime artifacts from every model mesh.
delete_uv_morph = root.mmd_root.uv_morphs.add()
delete_uv_morph.name = "DeleteUV"
delete_uv_morph.name_e = "DeleteUV"
delete_uv_morph.uv_index = 0
delete_uv_morph.data_type = "VERTEX_GROUP"
delete_uv_morph.vertex_group_scale = 0.25
for mesh_object in (mesh_a, mesh_b):
    group = mesh_object.vertex_groups.new(name="UV_DeleteUV+Y")
    group.add((0,), 1.0, "REPLACE")
similar_name_group = mesh_a.vertex_groups.new(name="UV_DeleteUVExtra+Y")
similar_name_group.add((0,), 1.0, "REPLACE")
ensure_morph_states(root)
delete_uv_state = next(
    state
    for state in root.spx_morph_states
    if state.morph_type == "uv_morphs" and state.morph_name == "DeleteUV"
)
delete_uv_state.value = 0.5
assert model.morph_slider.get("DeleteUV") is not None
assert any(
    modifier.type == "UV_WARP" and modifier.vertex_group == "UV_DeleteUV+Y"
    for mesh_object in (mesh_a, mesh_b)
    for modifier in mesh_object.modifiers
)
for state in root.spx_morph_states:
    state.selected = state.uid == delete_uv_state.uid
settings.morph_editor_type = "uv_morphs"
root.spx_morph_active_index = root.spx_morph_states.find(delete_uv_state.uid)
assert bpy.ops.surface_proxy.remove_selected_morphs() == {"FINISHED"}
assert root.mmd_root.uv_morphs.get("DeleteUV") is None
assert model.morph_slider.get("DeleteUV") is None
assert all(
    mesh_object.vertex_groups.get("UV_DeleteUV+Y") is None
    for mesh_object in (mesh_a, mesh_b)
)
assert mesh_a.vertex_groups.get("UV_DeleteUVExtra+Y") is not None
assert not any(
    modifier.type == "UV_WARP" and modifier.vertex_group == "UV_DeleteUV+Y"
    for mesh_object in (mesh_a, mesh_b)
    for modifier in mesh_object.modifiers
)

# NLA imports keep their strip timing while targeting the same stable UID path.
states = {state.morph_name: state for state in root.spx_morph_states}
root.animation_data_clear()
placeholder_keys.animation_data_clear()
nla_source = bpy.data.actions.new("SyntheticVmdNla_facial")
nla_curve = nla_source.fcurves.new(
    placeholder_keys.key_blocks["Smile"].path_from_id("value")
)
nla_curve.keyframe_points.insert(1.0, 0.0)
nla_curve.keyframe_points.insert(30.0, 1.0)
placeholder_animation = placeholder_keys.animation_data_create()
source_track = placeholder_animation.nla_tracks.new()
source_track.name = "SyntheticVmdNla_facial"
source_strip = source_track.strips.new("SyntheticVmdNla_facial", 12, nla_source)
source_strip.blend_type = "COMBINE"
nla_uids = _migrate_placeholder_animation(root)
assert nla_uids == {states["Smile"].uid}
assert len(root.animation_data.nla_tracks) == 1
destination_strip = root.animation_data.nla_tracks[0].strips[0]
assert abs(destination_strip.frame_start - source_strip.frame_start) < 1.0e-6
assert destination_strip.blend_type == source_strip.blend_type
assert {
    curve.data_path for curve in destination_strip.action.fcurves
} == {_morph_state_data_path(states["Smile"])}
_remove_imported_shape_key_curves(root)
assert not nla_source.fcurves

# Cleanup is scoped to checked Morphs in the current tab and preserves every
# checked Morph that still has visible detail content.
empty_morph_names = {
    "material_morphs": "EmptyMaterial",
    "uv_morphs": "EmptyUV",
    "bone_morphs": "EmptyBone",
    "vertex_morphs": "EmptyVertex",
    "group_morphs": "EmptyGroup",
}
nonempty_morph_names = {
    "material_morphs": "Hide",
    "uv_morphs": "CleanupUVGroupKeep",
    "bone_morphs": "BoneMove",
    "vertex_morphs": "CleanupVertexKeep",
    "group_morphs": "CleanupGroupKeep",
}
for morph_type, morph_name in empty_morph_names.items():
    morph = getattr(root.mmd_root, morph_type).add()
    morph.name = morph_name
cleanup_vertex_keep = root.mmd_root.vertex_morphs.add()
cleanup_vertex_keep.name = nonempty_morph_names["vertex_morphs"]
cleanup_vertex_key = mesh_a.shape_key_add(name=cleanup_vertex_keep.name)
cleanup_vertex_key.data[0].co.x += 1.0e-3
cleanup_uv_keep = root.mmd_root.uv_morphs.add()
cleanup_uv_keep.name = nonempty_morph_names["uv_morphs"]
cleanup_uv_keep.data_type = "VERTEX_GROUP"
mesh_a.vertex_groups.new(name=f"UV_{cleanup_uv_keep.name}+X")
cleanup_group_keep = root.mmd_root.group_morphs.add()
cleanup_group_keep.name = nonempty_morph_names["group_morphs"]
cleanup_group_offset = cleanup_group_keep.data.add()
cleanup_group_offset.morph_type = "material_morphs"
cleanup_group_offset.name = "Hide"
dangling_group_name = "CleanupGroupDangling"
cleanup_group_dangling = root.mmd_root.group_morphs.add()
cleanup_group_dangling.name = dangling_group_name
for group_morph in (cleanup_group_keep, cleanup_group_dangling):
    dangling_offset = group_morph.data.add()
    dangling_offset.morph_type = "vertex_morphs"
    dangling_offset.name = empty_morph_names["vertex_morphs"]
ensure_morph_states(root)

morph_types = list(empty_morph_names)
for morph_index, morph_type in enumerate(morph_types):
    empty_name = empty_morph_names[morph_type]
    settings.morph_editor_type = morph_type
    for state in root.spx_morph_states:
        state.selected = (
            state.morph_type == morph_type
            and state.morph_name
            in {
                empty_name,
                nonempty_morph_names[morph_type],
                dangling_group_name,
            }
        )
    assert bpy.ops.surface_proxy.clean_selected_empty_morphs() == {"FINISHED"}
    assert getattr(root.mmd_root, morph_type).get(empty_name) is None
    assert (
        getattr(root.mmd_root, morph_type).get(nonempty_morph_names[morph_type])
        is not None
    )
    if morph_type == "group_morphs":
        assert root.mmd_root.group_morphs.get(dangling_group_name) is None
    for other_type in morph_types[morph_index + 1 :]:
        assert (
            getattr(root.mmd_root, other_type).get(empty_morph_names[other_type])
            is not None
        )

# Vertex cleanup matches Velo Tools: each model-mesh ShapeKey is compared to
# Basis by maximum local-space Euclidean displacement.
assert abs(settings.morph_editor_shapekey_cleanup_threshold - 1.0e-4) < 1.0e-9
threshold_partial = root.mmd_root.vertex_morphs.add()
threshold_partial.name = "ThresholdPartial"
threshold_partial_name = threshold_partial.name
partial_small = mesh_a.shape_key_add(name=threshold_partial.name)
partial_small.data[0].co.x += 5.0e-5
partial_large = mesh_b.shape_key_add(name=threshold_partial.name)
partial_large.data[0].co.x += 2.0e-4
threshold_empty = root.mmd_root.vertex_morphs.add()
threshold_empty.name = "ThresholdEmpty"
threshold_empty_name = threshold_empty.name
for mesh_object in (mesh_a, mesh_b):
    key_block = mesh_object.shape_key_add(name=threshold_empty.name)
    key_block.data[0].co.x += 5.0e-5
ensure_morph_states(root)
settings.morph_editor_type = "vertex_morphs"
for state in root.spx_morph_states:
    state.selected = state.morph_name == threshold_partial.name
assert bpy.ops.surface_proxy.clean_selected_empty_morphs() == {"FINISHED"}
assert root.mmd_root.vertex_morphs.get(threshold_partial_name) is not None
assert threshold_partial_name not in mesh_a.data.shape_keys.key_blocks
assert threshold_partial_name in mesh_b.data.shape_keys.key_blocks
for state in root.spx_morph_states:
    state.selected = state.morph_name == threshold_empty.name
assert bpy.ops.surface_proxy.clean_selected_empty_morphs() == {"FINISHED"}
assert root.mmd_root.vertex_morphs.get(threshold_empty_name) is None
for mesh_object in (mesh_a, mesh_b):
    assert threshold_empty_name not in mesh_object.data.shape_keys.key_blocks

for state in root.spx_morph_states:
    state.selected = False
settings.morph_editor_type = "material_morphs"
assert bpy.ops.surface_proxy.clean_selected_empty_morphs() == {"CANCELLED"}
states_after_cleanup = {state.morph_name: state for state in root.spx_morph_states}
states_after_cleanup["Hide"].selected = True
assert bpy.ops.surface_proxy.clean_selected_empty_morphs() == {"CANCELLED"}
root.mmd_root.group_morphs.remove(
    root.mmd_root.group_morphs.find(nonempty_morph_names["group_morphs"])
)
ensure_morph_states(root)

# MMD Viewer interval selection follows the current filtered list and is shared
# by every viewer tab that exposes the checked-item list.
settings.browser_items.clear()
settings.browser_filter_by_prefix = False
settings.browser_prefix = ""
settings.browser_search = "Keep"
for label in ("KeepA", "Hidden", "KeepB", "KeepC"):
    item = settings.browser_items.add()
    item.kind = "BONE"
    item.label = label
    item.target_name = label
settings.browser_items[0].selected = True
settings.browser_items[3].selected = True
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="RANGE") == {"FINISHED"}
assert [item.selected for item in settings.browser_items] == [True, False, True, True]
for item in settings.browser_items:
    item.selected = False
settings.browser_items[0].selected = True
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="RANGE") == {"CANCELLED"}

# The MMD Viewer material tab reuses the Morph AI preferences and translation
# pipeline, but reads selected MMD Japanese material names and writes name_e.
settings.browser_items.clear()
settings.browser_search = ""
material.mmd_material.name_j = "左目上"
custom_material.mmd_material.name_j = "右目下"
for target_material in (material, custom_material):
    item = settings.browser_items.add()
    item.kind = "MATERIAL"
    item.material = target_material
    item.selected = True
original_addon_preferences = morph_editor_module._addon_preferences
original_translation_request = morph_editor_module._request_morph_name_translations
morph_editor_module._addon_preferences = lambda _context: SimpleNamespace()
morph_editor_module._request_morph_name_translations = (
    lambda _preferences, names: [
        "Eye_Up_L" if name == "左目上" else "Eye_Down_R"
        for name in names
    ]
)
try:
    assert bpy.ops.surface_proxy.translate_selected_material_names_with_ai() == {
        "FINISHED"
    }
finally:
    morph_editor_module._addon_preferences = original_addon_preferences
    morph_editor_module._request_morph_name_translations = original_translation_request
assert material.mmd_material.name_e == "Eye_Up_L"
assert custom_material.mmd_material.name_e == "Eye_Down_R"

# Bone AI translation consumes the checked MMD Japanese names and writes three
# coordinated conventions without breaking vertex groups or Bone Morph links.
parent_old_name = bone_data.bone
child_old_name = weighted_child_name
parent_pose_bone = armature.pose.bones[parent_old_name]
child_pose_bone = armature.pose.bones[child_old_name]
parent_pose_bone.mmd_bone.name_j = "左上臂"
parent_pose_bone.mmd_bone.name_e = "OldParent_L"
child_pose_bone.mmd_bone.name_j = "袖子A1.R"
child_pose_bone.mmd_bone.name_e = "OldChild_R"
settings.mmd_root = root
settings.browser_kind = "BONE"
settings.browser_items.clear()
for bone_name in (parent_old_name, child_old_name):
    item = settings.browser_items.add()
    item.kind = "BONE"
    item.target_name = bone_name
    item.label = bone_name
    item.armature_name = armature.name
    item.selected = True

original_addon_preferences = morph_editor_module._addon_preferences
original_translation_request = morph_editor_module._request_morph_name_translations
morph_editor_module._addon_preferences = lambda _context: SimpleNamespace()


def translate_bone_names(_preferences, names, **kwargs):
    assert names == ["上臂", "袖子A1"]
    assert kwargs["max_characters"] == 14
    assert "client adds the side markers" in kwargs["extra_instruction"]
    return ["UpperArm", "SleeveA1"]


morph_editor_module._request_morph_name_translations = translate_bone_names
try:
    assert bpy.ops.surface_proxy.translate_selected_bone_names_with_ai() == {
        "FINISHED"
    }
finally:
    morph_editor_module._addon_preferences = original_addon_preferences
    morph_editor_module._request_morph_name_translations = original_translation_request

parent_pose_bone = armature.pose.bones["UpperArm.L"]
child_pose_bone = armature.pose.bones["SleeveA1.R"]
assert parent_pose_bone.mmd_bone.name_j == "左UpperArm"
assert parent_pose_bone.mmd_bone.name_e == "UpperArm_L"
assert child_pose_bone.mmd_bone.name_j == "右SleeveA1"
assert child_pose_bone.mmd_bone.name_e == "SleeveA1_R"
assert armature.pose.bones.get(parent_old_name) is None
assert armature.pose.bones.get(child_old_name) is None
assert mesh_a.vertex_groups.get("SleeveA1.R") is not None
assert mesh_b.vertex_groups.get("SleeveA1.R") is not None
assert mesh_a.vertex_groups.get(child_old_name) is None
assert bone_data.bone == "UpperArm.L"
assert convert_data.bone == "UpperArm.L"
assert {
    item.target_name for item in settings.browser_items if item.selected
} == {"UpperArm.L", "SleeveA1.R"}

# PMX Editor CSV recognizes all five editor morph classes. Only the three
# name-addressable classes are applied across models; unsafe PMX vertex-index
# data is retained as an explicit skipped result.
clipboard_bone_name = parent_pose_bone.mmd_bone.name_j or parent_pose_bone.name
clipboard_material_name = material.mmd_material.name_j or material.name
clipboard_text = f'''\
;Morph header
Morph,"ClipboardMaterial","ClipboardMaterial",4,8
;MaterialMorph header
MaterialMorph,"ClipboardMaterial","{clipboard_material_name}",1,0.1,0.2,0.3,-1,0.4,0.5,0.6,8,0.7,0.8,0.9,1.5,0.11,0.12,0.13,-1,0.21,0.22,0.23,0.24,0.31,0.32,0.33,0.34,0.41,0.42,0.43,0.44
Morph,"ClipboardBone","ClipboardBone",4,2
;BoneMorph header
BoneMorph,"ClipboardBone","{clipboard_bone_name}",1,2,3,10,-20,30
Morph,"ClipboardGroup","ClipboardGroup",4,0
;GroupMorph header
GroupMorph,"ClipboardGroup","ClipboardMaterial",0.75
GroupMorph,"ClipboardGroup","MissingTarget",0.5
Morph,"ClipboardVertex","ClipboardVertex",4,1
;VertexMorph header
VertexMorph,"ClipboardVertex",0,1,2,3
Morph,"ClipboardUV","ClipboardUV",4,3
;UVMorph header
UVMorph,"ClipboardUV",0,0.1,0.2,0.3,0.4
'''
clipboard_records = parse_pmx_editor_morph_csv(clipboard_text)
assert [record.morph_type for record in clipboard_records] == [
    "material_morphs",
    "bone_morphs",
    "group_morphs",
    "vertex_morphs",
    "uv_morphs",
]
fixture_records = parse_pmx_editor_morph_csv(
    (PROJECT_ROOT / "tests" / "fixtures" / "pmx_editor_morph_clipboard.csv").read_text(
        encoding="utf-8"
    )
)
assert [(record.name, record.morph_type, len(record.details)) for record in fixture_records] == [
    ("[HalfBody]", "group_morphs", 5),
    ("披风-*", "material_morphs", 2),
    ("AnalToy1+", "bone_morphs", 1),
    ("AnalToy幅", "bone_morphs", 3),
]
clipboard_result = apply_pmx_editor_morphs(root, clipboard_records)
assert clipboard_result["created"] == 3
assert clipboard_result["updated"] == 0
assert clipboard_result["skipped"] == ["ClipboardVertex", "ClipboardUV"]
assert clipboard_result["unresolved"] == []
clipboard_material = root.mmd_root.material_morphs["ClipboardMaterial"]
assert len(clipboard_material.data) == 1
assert clipboard_material.data[0].material == material.name
assert tuple(round(value, 3) for value in clipboard_material.data[0].diffuse_color) == (
    0.1,
    0.2,
    0.3,
    -1.0,
)
clipboard_bone = root.mmd_root.bone_morphs["ClipboardBone"]
assert len(clipboard_bone.data) == 1
assert clipboard_bone.data[0].bone == parent_pose_bone.name
clipboard_group = root.mmd_root.group_morphs["ClipboardGroup"]
assert [(item.name, item.morph_type, round(item.factor, 2)) for item in clipboard_group.data] == [
    ("ClipboardMaterial", "material_morphs", 0.75),
    ("MissingTarget", "vertex_morphs", 0.5),
]

# Dangling Group Morph references from PMX Editor must survive paste so the
# user can replace them manually in the detail editor.
user_group_records = parse_pmx_editor_morph_csv(
    'Morph,"[HalfBody]","[HalfBody]",4,0\n'
    'GroupMorph,"[HalfBody]","裙子1-*",1\n'
    'GroupMorph,"[HalfBody]","胖次-*",1\n'
)
user_group_result = apply_pmx_editor_morphs(root, user_group_records)
assert user_group_result["created"] == 1
half_body = root.mmd_root.group_morphs["[HalfBody]"]
assert [item.name for item in half_body.data] == ["裙子1-*", "胖次-*"]

serialized_text, serialized_count, serialized_skipped = serialize_pmx_editor_morphs(
    root,
    (
        ("material_morphs", clipboard_material),
        ("bone_morphs", clipboard_bone),
        ("group_morphs", clipboard_group),
    ),
)
assert serialized_count == 3
assert serialized_skipped == []
serialized_records = parse_pmx_editor_morph_csv(serialized_text)
assert [record.morph_type for record in serialized_records] == [
    "material_morphs",
    "bone_morphs",
    "group_morphs",
]
assert len(serialized_records[0].details) == 1
assert len(serialized_records[1].details) == 1
assert len(serialized_records[2].details) == 2
clipboard_bone_rotation = clipboard_bone.data[0].rotation.copy()
roundtrip_result = apply_pmx_editor_morphs(root, serialized_records)
assert roundtrip_result["updated"] == 3
assert clipboard_bone_rotation.rotation_difference(
    clipboard_bone.data[0].rotation
).angle < 1.0e-6

ensure_morph_states(root)
settings.morph_editor_root = root
clipboard_layout = InspectorLayoutProbe()
morph_editor_module.draw_morph_editor(clipboard_layout, bpy.context)
assert "surface_proxy.copy_selected_morphs_to_clipboard" in clipboard_layout.operators
assert "surface_proxy.paste_morphs_from_clipboard" in clipboard_layout.operators

states = {state.morph_name: state for state in root.spx_morph_states}
states["Hide"].value = 0.25
button_value_path = states["Hide"].path_from_id("value")
assert bpy.ops.surface_proxy.set_morph_value(
    root_name=root.name,
    morph_uid=states["Hide"].uid,
    value=1.0,
) == {"FINISHED"}
assert states["Hide"].value == 1.0
assert states["Hide"].path_from_id("value") == button_value_path

print("MMD_MORPH_EDITOR_REGRESSION_OK")
