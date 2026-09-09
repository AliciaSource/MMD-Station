"""Refresh, force-name and stale Morph-reference regression with real datablocks."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import addon_utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
addon_utils.disable("mmd_station", default_set=False)
import mmd_station
mmd_station.register()
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_station.mmd_material_order import ordered_materials
from mmd_station.mmd_morph_editor import _material_targets, _model_materials, repair_material_references


def mesh(name, armature, material, linked=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    data.materials.append(material)
    obj = bpy.data.objects.new(name, data)
    obj.parent = armature
    if linked:
        bpy.context.scene.collection.objects.link(obj)
    return obj


model = Model.create("MaterialIdentityFixture", add_root_bone=True)
root = model.rootObject()
old = bpy.data.materials.new("Surface")
old.mmd_material.name_j = "Surface"
old.use_nodes = True
current = old.copy()
current.name = "Imported Surface"
orphan = mesh("DetachedSurface", model.armature(), old, linked=False)
live = mesh("CurrentSurface", model.armature(), current)
morph = root.mmd_root.material_morphs.add()
morph.name = "HideSurface"
offset = morph.data.add()
offset.material = old.name
offset.related_mesh = orphan.data.name
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.browser_kind = "MATERIAL"
before = len(bpy.data.materials)
for _ in range(3):
    bpy.ops.surface_proxy.refresh_mmd_browser()
    assert [i.material for i in settings.browser_items] == [current]
    assert len(bpy.data.materials) == before
assert offset.material_data == current
assert offset.related_mesh == live.data.name
from mmd_station import mmd_morph_editor as editor
offset.offset_type = "MULT"
offset.diffuse_color = (1, 1, 1, 0)
editor.ensure_morph_states(root)
state = next(s for s in root.spx_morph_states if s.morph_type == "material_morphs")
state.value = 1
editor.evaluate_morph_root(root)
assert editor._existing_output_bridges(current)[0].inputs["Opacity"].default_value == 0
state.value = 0
editor.evaluate_morph_root(root)
assert editor._existing_output_bridges(current)[0].inputs["Opacity"].default_value == 1
assert ordered_materials(root) == [current]
settings.browser_items[0].selected = True
bpy.ops.surface_proxy.sync_material_names(direction="MMD_TO_BLENDER")
assert current.name == "Surface"
assert old.name != "Surface"
assert orphan.data.materials[0] == old
assert offset.material_data == current
current.name = "Renamed Surface"
assert _material_targets(_model_materials(root), offset) == (current,)
assert offset.material == current.name

# Stale references resolve by MMD name, never by global material-name lookup.
offset.material = old.name
assert _material_targets(_model_materials(root), offset) == (current,)
assert repair_material_references(root) == 1
assert offset.material_data == current

# Multiple equally named candidates are not guessed or treated as all-material.
other = current.copy()
other.name = "Other Surface"
mesh("OtherSurface", model.armature(), other)
offset.material = old.name
assert _material_targets(_model_materials(root), offset) == ()
assert repair_material_references(root) == 0
assert offset.material_data == old
assert _material_targets([current], SimpleNamespace(material_data=None, material="", material_id=42)) == ()
assert _material_targets([current], SimpleNamespace(material_data=None, material="", material_id=-1)) == (current,)

# Intentional hidden linked meshes are still part of the model.
live.hide_set(True)
assert current in ordered_materials(root)
print("MATERIAL_IDENTITY_REGRESSION_OK")
