import pathlib
import sys
import tempfile

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from bl_ext.blender_org.mmd_tools.core import pmx
from bl_ext.blender_org.mmd_tools.core.model import FnModel, Model
from mmd_station.mmd_material_order import (
    draw_name_sync,
    material_identity,
    ordered_materials,
)
from mmd_station.mmd_physics import SPX_UL_MMDItems


class RecordingUILayout:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        self.alignment = "LEFT"

    def row(self, **_kwargs):
        return RecordingUILayout(self.calls)

    def split(self, **_kwargs):
        return RecordingUILayout(self.calls)

    def prop(self, owner, property_name, **kwargs):
        self.calls.append((owner, property_name, kwargs))

    def label(self, **_kwargs):
        return None

    def operator(self, *_args, **_kwargs):
        return type("RecordedOperator", (), {})()


class MaterialControlsLayoutProbe:
    def __init__(self, node_type="layout", kwargs=None):
        self.node_type = node_type
        self.kwargs = kwargs or {}
        self.children = []

    def _child(self, node_type, kwargs):
        child = MaterialControlsLayoutProbe(node_type, kwargs)
        self.children.append(child)
        return child

    def row(self, **kwargs):
        return self._child("row", kwargs)

    def split(self, **kwargs):
        return self._child("split", kwargs)

    def operator(self, operator_id, **kwargs):
        self.children.append(MaterialControlsLayoutProbe("operator", {
            "operator_id": operator_id,
            **kwargs,
        }))
        return type("RecordedOperator", (), {})()

    def prop(self, owner, property_name, **kwargs):
        self.children.append(MaterialControlsLayoutProbe("prop", {
            "owner": owner,
            "property_name": property_name,
            **kwargs,
        }))

    def label(self, **kwargs):
        self.children.append(MaterialControlsLayoutProbe("label", kwargs))


def make_material(name, name_j, name_e):
    material = bpy.data.materials.new(name)
    material.mmd_material.name_j = name_j
    material.mmd_material.name_e = name_e
    return material


def make_mesh(name, armature, material_positions):
    vertices = []
    faces = []
    for index, (_material, position) in enumerate(material_positions):
        start = len(vertices)
        vertices.extend(
            (
                (position, 0.0, 0.0),
                (position, 1.0, 0.0),
                (position, 0.0, 1.0),
            )
        )
        faces.append((start, start + 1, start + 2))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    for material, _position in material_positions:
        mesh.materials.append(material)
    for index, polygon in enumerate(mesh.polygons):
        polygon.material_index = index
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    modifier = obj.modifiers.new(name="mmd_armature", type="ARMATURE")
    modifier.object = armature
    return obj


mmd_station.register()
model = Model.create("MaterialOrderRegression", add_root_bone=True)
root = model.rootObject()
armature = model.armature()

material_a = make_material("BL_A", "PMX_A", "PMX_A_EN")
material_b = make_material("BL_B", "PMX_B", "PMX_B_EN")
material_c = make_material("BL_C", "PMX_C", "PMX_C_EN")

# Native mmd_tools order is mesh name first, then used material-slot index.
multi_mesh = make_mesh(
    "A_Mesh",
    armature,
    ((material_c, 0.0), (material_a, 10.0)),
)
single_mesh = make_mesh("Z_Mesh", armature, ((material_b, 20.0),))
assert ordered_materials(root) == [material_c, material_a, material_b]

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.browser_kind = "MATERIAL"
assert abs(settings.material_split_shapekey_cleanup_threshold - 1e-4) < 1e-9
controls_probe = MaterialControlsLayoutProbe()
draw_name_sync(controls_probe, settings)
controls_row = controls_probe.children[0]
first_third = controls_row.children[0]
assert first_third.node_type == "split"
assert abs(first_third.kwargs["factor"] - (1.0 / 3.0)) < 1e-9
remaining_thirds = first_third.children[1]
assert remaining_thirds.node_type == "split"
assert remaining_thirds.kwargs["factor"] == 0.5
split_controls = remaining_thirds.children[0]
assert split_controls.node_type == "row"
assert split_controls.children[0].kwargs["operator_id"] == (
    "surface_proxy.separate_active_mesh_by_materials"
)
auto_sync = split_controls.children[1]
assert auto_sync.kwargs["property_name"] == "material_order_auto_sync"
assert auto_sync.kwargs["text"] == ""
threshold_control = remaining_thirds.children[1]
assert threshold_control.kwargs["property_name"] == (
    "material_split_shapekey_cleanup_threshold"
)
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
next(item for item in settings.browser_items if item.material == material_b).selected = True
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="TOP") == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a]

material_b.name = "BL_B_Renamed"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a]
assert [item.material for item in settings.browser_items] == [
    material_b,
    material_c,
    material_a,
]
assert [item.order_index for item in settings.browser_items] == [0, 1, 2]

# Blender material copies inherit custom properties. A copied material must
# receive a new ordering identity instead of replacing its source in the viewer.
source_identity = material_identity(material_a)
material_a_copy = material_a.copy()
material_a_copy.name = "BL_A_Copy"
assert material_identity(material_a_copy) == source_identity
copy_mesh = make_mesh("Y_Copy", armature, ((material_a_copy, 15.0),))
assert ordered_materials(root) == [
    material_b,
    material_c,
    material_a,
    material_a_copy,
]
assert material_identity(material_a) == source_identity
assert material_identity(material_a_copy) != source_identity
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert [item.material for item in settings.browser_items] == [
    material_b,
    material_c,
    material_a,
    material_a_copy,
]
bpy.data.objects.remove(copy_mesh, do_unlink=True)
bpy.data.materials.remove(material_a_copy)
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a]
assert [item.material for item in settings.browser_items] == [
    material_b,
    material_c,
    material_a,
]

# Match the Morph editor's label-like name fields: the UIList owns single-click
# row activation, while Blender reserves text editing for double-click.
browser_item = next(item for item in settings.browser_items if item.material == material_b)
recording_layout = RecordingUILayout()
SPX_UL_MMDItems.draw_item(
    None,
    bpy.context,
    recording_layout,
    settings,
    browser_item,
    0,
    settings,
    "browser_index",
    settings.browser_index,
)
material_props = {
    property_name: kwargs
    for owner, property_name, kwargs in recording_layout.calls
    if owner in {material_b, material_b.mmd_material}
}
assert material_props["name"]["emboss"] is False
assert material_props["name_j"]["emboss"] is False
assert "emboss" not in material_props["name_e"]

# Material navigation selects the corresponding Mesh in Object Mode.
assert bpy.ops.surface_proxy.select_mmd_item(
    kind="MATERIAL",
    target_name=material_b.name,
) == {"FINISHED"}
assert bpy.context.mode == "OBJECT"
assert bpy.context.active_object is single_mesh
assert single_mesh.active_material is material_b
assert set(bpy.context.selected_objects) == {single_mesh}
assert settings.browser_items[settings.browser_index].material is material_b

# Checked materials round-trip through selected Mesh objects while retaining
# every material actually used by a multi-material mesh.
for item in settings.browser_items:
    item.selected = item.material in {material_c, material_a}
assert bpy.ops.surface_proxy.select_checked_mmd_items() == {"FINISHED"}
assert bpy.context.mode == "OBJECT"
assert bpy.context.active_object is multi_mesh
assert set(bpy.context.selected_objects) == {multi_mesh}
assert multi_mesh.active_material is material_a
assert bpy.ops.surface_proxy.sync_selected_mmd_objects_to_browser() == {"FINISHED"}
assert {
    item.material for item in settings.browser_items if item.selected
} == {material_c, material_a}

external_conflict = make_material(
    "ExternalConflict",
    "ExternalConflict",
    "ExternalConflict",
)
external_conflict.mmd_material.material_id = 0
assert bpy.ops.surface_proxy.calibrate_material_order() == {"FINISHED"}
assert [
    material.mmd_material.material_id
    for material in (material_b, material_c, material_a)
] == [0, 1, 2]
assert external_conflict.mmd_material.material_id >= 3
assert single_mesh.name == "000_Z_Mesh"
assert multi_mesh.name == "A_Mesh"

basis = multi_mesh.shape_key_add(name="Basis")
tiny_key = multi_mesh.shape_key_add(name="TinyResidual")
tiny_key.data[0].co.x = basis.data[0].co.x + 5e-5
large_key = multi_mesh.shape_key_add(name="LargeResidual")
large_key.data[3].co.x = basis.data[3].co.x + 2e-4
settings.material_split_shapekey_cleanup_threshold = 1e-4

bpy.ops.object.select_all(action="DESELECT")
multi_mesh.select_set(True)
bpy.context.view_layer.objects.active = multi_mesh
assert bpy.ops.surface_proxy.separate_active_mesh_by_materials() == {"FINISHED"}
material_owners = {}
for mesh_object in FnModel.iterate_mesh_objects(root):
    used = {
        mesh_object.data.materials[polygon.material_index]
        for polygon in mesh_object.data.polygons
        if polygon.material_index < len(mesh_object.data.materials)
    }
    if len(used) == 1:
        material_owners[next(iter(used))] = mesh_object
assert material_owners[material_b] is single_mesh
assert single_mesh.name == "000_Z_Mesh"
assert material_owners[material_c].name.startswith("001_")
assert material_owners[material_a].name.startswith("002_")
assert all(
    "mmd_normal" not in mesh_object.data.attributes
    for mesh_object in (material_owners[material_c], material_owners[material_a])
)
assert all(
    "TinyResidual" not in mesh_object.data.shape_keys.key_blocks
    for mesh_object in (material_owners[material_c], material_owners[material_a])
)
assert "LargeResidual" in material_owners[material_a].data.shape_keys.key_blocks
assert (
    material_owners[material_a].data.shape_keys.key_blocks["LargeResidual"].data[0].co
    - material_owners[material_a].data.shape_keys.key_blocks["Basis"].data[0].co
).length > settings.material_split_shapekey_cleanup_threshold

# Auto sync handles a multi-selection as one stable block and only touches
# positions whose material actually changed.
material_d = make_material("BL_D", "PMX_D", "PMX_D_EN")
unaffected_mesh = make_mesh("D_Mesh", armature, ((material_d, 30.0),))
multi_guard = make_mesh(
    "MultiGuard",
    armature,
    ((material_c, 40.0), (material_a, 50.0)),
)
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.calibrate_material_order() == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a, material_d]
unaffected_mesh.name = "777_D_Mesh"
settings.material_order_auto_sync = True
for item in settings.browser_items:
    item.selected = item.material in {material_c, material_a}
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="UP") == {"FINISHED"}
assert ordered_materials(root) == [material_c, material_a, material_b, material_d]
assert [
    material.mmd_material.material_id
    for material in (material_c, material_a, material_b, material_d)
] == [0, 1, 2, 3]
assert material_owners[material_c].name.startswith("000_")
assert material_owners[material_a].name.startswith("001_")
assert single_mesh.name.startswith("002_")
assert unaffected_mesh.name == "777_D_Mesh"
assert multi_guard.name == "MultiGuard"

# Move the same two-material block back, then remove the temporary unaffected
# material so the export assertions below retain their original fixture.
assert bpy.ops.surface_proxy.reorder_checked_mmd_items(action="DOWN") == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a, material_d]
bpy.data.objects.remove(unaffected_mesh, do_unlink=True)
bpy.data.materials.remove(material_d)
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.calibrate_material_order() == {"FINISHED"}
assert ordered_materials(root) == [material_b, material_c, material_a]
assert multi_guard.name == "MultiGuard"

assert bpy.ops.surface_proxy.sync_material_names(direction="BLENDER_TO_MMD") == {
    "FINISHED"
}
for material in (material_a, material_b, material_c):
    assert material.mmd_material.name_j == material.name
    assert material.mmd_material.name_e == material.name
for material, name_j, name_e in (
    (material_a, "PMX_A", "PMX_A_EN"),
    (material_b, "PMX_B", "PMX_B_EN"),
    (material_c, "PMX_C", "PMX_C_EN"),
):
    material.mmd_material.name_j = name_j
    material.mmd_material.name_e = name_e
assert bpy.ops.surface_proxy.sync_material_names(direction="MMD_TO_BLENDER") == {
    "FINISHED"
}
assert [material.name for material in ordered_materials(root)] == [
    "PMX_B",
    "PMX_C",
    "PMX_A",
]

for obj in bpy.context.selected_objects:
    obj.select_set(False)
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
with tempfile.TemporaryDirectory(prefix="mmd-material-order-") as directory:
    output = pathlib.Path(directory) / "material_order.pmx"
    result = bpy.ops.mmd_tools.export_pmx(
        filepath=str(output),
        scale=1.0,
        copy_textures_mode="NONE",
        fix_bone_order=False,
        sort_materials=True,
        sort_vertices="NONE",
    )
    assert result == {"FINISHED"}
    exported = pmx.load(str(output))
    assert [material.name for material in exported.materials] == [
        "PMX_B",
        "PMX_C",
        "PMX_A",
    ]
    roots_before = {obj for obj in bpy.data.objects if obj.mmd_type == "ROOT"}
    import_result = bpy.ops.mmd_tools.import_model(
        filepath=str(output),
        types={"MESH", "ARMATURE"},
        scale=1.0,
        clean_model=False,
        remove_doubles=False,
        fix_bone_order=False,
        rename_bones=False,
    )
    assert import_result == {"FINISHED"}
    imported_root = next(
        obj
        for obj in bpy.data.objects
        if obj.mmd_type == "ROOT" and obj not in roots_before
    )
    assert [
        material.mmd_material.name_j
        for material in ordered_materials(imported_root)
    ] == ["PMX_B", "PMX_C", "PMX_A"]

print("MMD_MATERIAL_ORDER_REGRESSION_OK")
