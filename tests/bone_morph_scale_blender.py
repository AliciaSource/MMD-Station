"""Focused real Blender regression; all generated files are temporary."""

import json
from pathlib import Path
import sys
import tempfile

import bpy
import addon_utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not hasattr(bpy.types.Object, "mmd_type"):
    addon_utils.enable("bl_ext.blender_org.mmd_tools")
addon_utils.disable("mmd_station", default_set=False)
import mmd_station
mmd_station.register()
from mmd_station import mmd_bone_morph_scale as scale
from mmd_station import mmd_morph_editor as editor
from mmd_station.morph_sidecar import read_payload, sidecar_path
from bl_ext.blender_org.mmd_tools.core.model import Model
from bl_ext.blender_org.mmd_tools.core import pmx
from bl_ext.blender_org.mmd_tools.core.pmx import exporter, importer


def close(actual, expected):
    assert max(abs(a - b) for a, b in zip(actual, expected)) < 1.0e-4, (tuple(actual), expected)


model = Model.create("ScaleFixture", add_root_bone=True)
root = model.rootObject()
arm = model.armature()
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
child = arm.data.edit_bones.new("Child")
child.head, child.tail = (0, 1, 0), (0, 2, 0)
parent = arm.data.edit_bones.new("Parent")
parent.head, parent.tail = (0, 0, 0), (0, 1, 0)
child.parent = parent
still = arm.data.edit_bones.new("InheritedOnly")
still.head, still.tail = (0, 2, 0), (0, 3, 0)
still.parent = child
bpy.ops.object.mode_set(mode="POSE")
for b in arm.pose.bones:
    b.mmd_bone.name_j = b.name
    b.mmd_bone.name_e = b.name
morph = root.mmd_root.bone_morphs.add()
morph.name = "ScalePose"
morph.name_e = "ScalePose"
editor.ensure_morph_states(root)
settings = bpy.context.scene.surface_proxy_creator
settings.morph_editor_root = root
settings.morph_editor_type = "bone_morphs"
root.spx_morph_active_index = 0
parent = arm.pose.bones["Parent"]
child = arm.pose.bones["Child"]
parent.location.x = 0.25
child.scale = (1.2, 0.8, 1.5)
child.rotation_mode = "XYZ"
child.rotation_euler.z = 0.3
assert bpy.ops.surface_proxy.save_bone_morph_pose() == {"FINISHED"}
assert [d.bone for d in morph.data] == ["Parent", "Child"]
assert bpy.ops.surface_proxy.save_bone_morph_pose() == {"FINISHED"}
assert len(morph.data) == 2
close(morph.data[1].spx_scale, (1.2, 0.8, 1.5))
assert abs(morph.data[1].rotation.angle - 0.3) < 1.0e-5

# The ordinary plus captures all three transform channels.
arm.data.bones.active = child.bone
child.bone.select = True
assert bpy.ops.surface_proxy.add_morph_offset() == {"FINISHED"}
close(morph.data[-1].spx_scale, child.scale)
assert morph.data[-1].bone == "Child"
assert len(morph.data) == 2
morph.active_data = 1
child.scale = (1.4, 0.7, 1.6)
assert bpy.ops.mmd_tools.apply_bone_morph_offset() == {"FINISHED"}
close(morph.data[1].spx_scale, child.scale)
assert bpy.ops.mmd_tools.clear_bone_morph_view() == {"FINISHED"}
assert bpy.ops.mmd_tools.edit_bone_morph_offset() == {"FINISHED"}
close(child.scale, (1.4, 0.7, 1.6))
assert bpy.ops.mmd_tools.clear_bone_morph_view() == {"FINISHED"}
assert bpy.ops.mmd_tools.view_bone_morph() == {"FINISHED"}
close(child.scale, (1.4, 0.7, 1.6))
bpy.ops.mmd_tools.clear_bone_morph_view()

# Runtime constraints must not overwrite authored scale channels.
state = root.spx_morph_states[0]
state.value = 0.5
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
assert not root.get(editor.RUNTIME_ERROR_PROPERTY), root.get(editor.RUNTIME_ERROR_PROPERTY)
close(child.scale, (1, 1, 1))
close(child.matrix.to_scale(), (1.2, 0.85, 1.3))
state.value = 0
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
close(child.matrix.to_scale(), (1, 1, 1))

# Adding/removing offsets after an existing bind must rebuild native bindings.
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
extra = arm.pose.bones["InheritedOnly"]
arm.data.bones.active = extra.bone
extra.bone.select = True
extra.scale = (2, 2, 2)
assert bpy.ops.surface_proxy.add_morph_offset() == {"FINISHED"}
assert len(morph.data) == 3
assert bpy.context.mode == "POSE"
assert bpy.context.active_pose_bone == extra
extra.scale = (1, 1, 1)
state.value = 0.5
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
constraint = next(c for c in extra.constraints if c.name.startswith(scale.PREFIX))
assert abs(constraint.to_min_x_scale - 1.5) < 1.0e-5
assert bpy.ops.surface_proxy.remove_morph_offset() == {"FINISHED"}
assert len(morph.data) == 2
assert not any(c.name.startswith(scale.PREFIX) for c in extra.constraints)
state.value = 0

# Signed scales and extrapolated weights use the same per-axis linear delta.
morph.data[1].spx_scale = (-1, 1, 2)
state.value = 1
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
assert child.matrix.determinant() < 0
state.value = -0.5
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
close(child.matrix.to_scale(), (2, 1, 0.5))
state.value = 0
morph.data[1].spx_scale = (1.4, 0.7, 1.6)

# Group Morph factors participate without double-applying their weights.
group = root.mmd_root.group_morphs.add()
group.name = "ScaleGroup"
group.name_e = "ScaleGroup"
member = group.data.add()
member.morph_type = "bone_morphs"
member.name = morph.name
member.factor = 0.5
editor.ensure_morph_states(root)
group_state = next(s for s in root.spx_morph_states if s.morph_type == "group_morphs")
group_state.value = 1
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()
close(child.matrix.to_scale(), (1.2, 0.85, 1.3))
group_state.value = 0
editor.evaluate_morph_root(root)
bpy.context.view_layer.update()

bpy.ops.object.mode_set(mode="OBJECT")
with tempfile.TemporaryDirectory(prefix="bone-morph-scale-") as temp:
    path = Path(temp) / "Body.pmx"
    kwargs = dict(root=root, armature=arm, meshes=[], rigid_bodies=[], joints=[], scale=1.0, copy_textures=False)
    exporter.export(str(path), **kwargs)
    sidecar = sidecar_path(path)
    assert sidecar.name == "Body.Morph.json"
    payload = read_payload(sidecar)
    assert len(payload["entries"]) == 1, payload
    standard = pmx.load(str(path))
    comments = (standard.comment, standard.comment_e)
    exporter.export(str(path), **kwargs)
    assert len(list(Path(temp).glob("*.json"))) == 1
    assert read_payload(sidecar) == payload
    from mmd_station.mmd_export_profile import last_export_profile
    assert last_export_profile().get("fast"), last_export_profile()
    renamed = Path(temp) / "Renamed.pmx"
    renamed.write_bytes(path.read_bytes())
    sidecar_path(renamed).write_bytes(sidecar.read_bytes())
    loader = importer.PMXImporter()
    loader.execute(filepath=str(renamed), types={"ARMATURE", "MORPHS"}, scale=1.0)
    restored = loader._PMXImporter__root
    restored_morph = restored.mmd_root.bone_morphs[0]
    close(restored_morph.data[1].spx_scale, (1.4, 0.7, 1.6))
    restored_morph.data[1].spx_scale = (1, 1, 1)
    arbitrary = Path(temp) / "anything.json"
    arbitrary.write_bytes(sidecar.read_bytes())
    assert bpy.ops.surface_proxy.import_bone_morph_scale(filepath=str(arbitrary), target_root=restored.name) == {"FINISHED"}
    close(restored_morph.data[1].spx_scale, (1.4, 0.7, 1.6))
    assert scale.import_scales(restored, arbitrary) == (1, 0)
    assert len(restored_morph.data) == 2
    broken = json.loads(arbitrary.read_text(encoding="utf-8"))
    broken["entries"][0]["bone"]["name"] = "Absent"
    arbitrary.write_text(json.dumps(broken), encoding="utf-8")
    assert scale.import_scales(restored, arbitrary) == (0, 1)
    arbitrary.write_text('{"version": 99}', encoding="utf-8")
    try:
        scale.import_scales(restored, arbitrary)
        raise AssertionError("Invalid JSON was accepted")
    except ValueError:
        pass
    # Unchanged standard morphs and comments, with stale sidecar removal.
    bpy.context.view_layer.objects.active = arm
    morph.data[1].spx_scale = (1, 1, 1)
    exporter.export(str(path), **kwargs)
    assert not sidecar.exists()
    standard2 = pmx.load(str(path))
    assert (standard2.comment, standard2.comment_e) == comments
    assert [(m.name, len(m.offsets)) for m in standard.morphs] == [(m.name, len(m.offsets)) for m in standard2.morphs]
    for before, after in zip(standard.morphs, standard2.morphs):
        if before.type_index() == 2:
            for a, b in zip(before.offsets, after.offsets):
                close(a.location_offset, b.location_offset)
                close(a.rotation_offset, b.rotation_offset)
    # Persistent property survives save/reopen independently of JSON.
    morph.data[1].spx_scale = (1.4, 0.7, 1.6)
    blend = Path(temp) / "scales.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    root_name = root.name
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    close(bpy.data.objects[root_name].mmd_root.bone_morphs[0].data[1].spx_scale, (1.4, 0.7, 1.6))

mmd_station.unregister()
assert all(not c.name.startswith(scale.PREFIX) for o in bpy.data.objects if o.type == "ARMATURE" for b in o.pose.bones for c in b.constraints)
mmd_station.register()
assert len(scale._PATCHES) == 7
print("BONE_MORPH_SCALE_REGRESSION_OK")
