"""Exercise isolated conversion with real Blender evaluation."""
from pathlib import Path
import sys
import math
import bpy
import addon_utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not hasattr(bpy.types.Object, "mmd_type"):
    addon_utils.enable("bl_ext.blender_org.mmd_tools")
addon_utils.disable("mmd_station", default_set=False)
import mmd_station
mmd_station.register()
from mmd_station import mmd_morph_editor as editor
from bl_ext.blender_org.mmd_tools.core.model import Model

model = Model.create("Isolation", add_root_bone=True)
root, arm = model.rootObject(), model.armature()
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
b = arm.data.edit_bones.new("Target")
b.head, b.tail = (0, 0, 0), (0, 1, 0)
bpy.ops.object.mode_set(mode="OBJECT")
mesh = bpy.data.meshes.new("IsolationMesh")
mesh.from_pydata([(1, 0, 0), (0, 1, 0), (0, 0, 0)], [], [(0, 1, 2)])
obj = bpy.data.objects.new("IsolationMesh", mesh)
bpy.context.scene.collection.objects.link(obj)
obj.parent = arm
obj.vertex_groups.new(name="Target").add([0, 1], 1, "REPLACE")
mod = obj.modifiers.new("Rig", "ARMATURE")
mod.object = arm
basis = obj.shape_key_add(name="Basis")
other = obj.shape_key_add(name="Other")
other.data[0].co.z = 8
other.value = 1
pose = arm.pose.bones["Target"]
pose.location = (0, 0, 7)
driver = pose.driver_add("location", 2).driver
driver.expression = "7"
constraint = pose.constraints.new("LIMIT_LOCATION")
constraint.use_min_z = True
constraint.min_z = 7
constraint.owner_space = "LOCAL"
morph = root.mmd_root.bone_morphs.add()
morph.name = "TargetMorph"
offset = morph.data.add()
offset.bone = "Target"
offset.location = (0, 0, 2)
offset.rotation = (math.cos(math.pi / 4), 0, 0, math.sin(math.pi / 4))
offset.spx_scale = (2, 1, 1)
editor.ensure_morph_states(root)
root.mmd_root.active_morph_type = "bone_morphs"
root.mmd_root.active_morph = 0
bpy.context.view_layer.update()
before = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures))
result = editor._run_filtered_bone_morph_conversion(bpy.context, root, morph)
assert result[0] == {"FINISHED"}, result
key = obj.data.shape_keys.key_blocks["TargetMorph"]
assert (key.data[0].co - __import__("mathutils").Vector((0, 2, 2))).length < 1e-5, tuple(key.data[0].co)
assert (key.data[2].co - basis.data[2].co).length < 1e-6
assert other.value == 1 and pose.location.z == 7 and constraint.min_z == 7
assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures))
assert bpy.context.view_layer.objects.active == arm

# Other vertex/bone morphs and a group are active in the host runtime.
vertex = root.mmd_root.vertex_morphs.add()
vertex.name = "Other"
extra = root.mmd_root.bone_morphs.add()
extra.name = "Extra"
data = extra.data.add()
data.bone = "Target"
data.location = (0, 0, 20)
group = root.mmd_root.group_morphs.add()
group.name = "Combination"
for kind, name in (("vertex_morphs", "Other"), ("bone_morphs", "Extra")):
    data = group.data.add()
    data.morph_type, data.name, data.factor = kind, name, 0.5
editor.ensure_morph_states(root)
states = {s.morph_name: s for s in root.spx_morph_states}
for name in ("Other", "Extra", "Combination"):
    states[name].value = 1
bpy.context.view_layer.update()
assert "spx_morph_runtime_error" not in root, root.get("spx_morph_runtime_error")
assert abs(other.value - 1.5) < 1e-6, other.value
values = [(s.uid, s.value) for s in root.spx_morph_states]
other_value = other.value
before = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures))
editor._run_filtered_bone_morph_conversion(bpy.context, root, morph)
assert (key.data[0].co - __import__("mathutils").Vector((0, 2, 2))).length < 1e-5
assert values == [(s.uid, s.value) for s in root.spx_morph_states]
assert other.value == other_value
assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures))

# Pose mode and an unrelated active object cannot redirect nested operators.
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
editor._run_filtered_bone_morph_conversion(bpy.context, root, morph)
assert bpy.context.mode == "POSE" and bpy.context.view_layer.objects.active == arm
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.objects.active = None
editor._run_filtered_bone_morph_conversion(bpy.context, root, morph)
assert bpy.context.view_layer.objects.active is None

# Failed writes restore earlier meshes instead of leaving partial output.
from mmd_station.mmd_bone_conversion import write_shape_keys, sample
points = [v.co.copy() for v in key.data]
try:
    write_shape_keys({obj: [object()] * 3}, "TargetMorph")
except (TypeError, ValueError):
    pass
else:
    raise AssertionError("Expected write failure")
assert all((a.co - b).length < 1e-6 for a, b in zip(key.data, points))
try:
    sample(bpy.context, arm, morph, {obj: {999999}})
except IndexError:
    pass
else:
    raise AssertionError("Expected sampling failure")
assert before == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures))
print("BONE_CONVERSION_ISOLATION_OK")
