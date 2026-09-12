"""Exercise real Action slots, NLA binding, conversion defaults and rollback."""

from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mmd_station
from mmd_station.blender_compat import action_fcurves, assign_action, link_strip_action, set_uv_selection
from mmd_station.mmd_bone_conversion import write_shape_keys
from mmd_station.physics_preview.bake import _replace_curve_range, _restore_curve_range


mmd_station.register()
scene = bpy.context.scene
first = bpy.data.objects.new("SlotFirst", None)
second = bpy.data.objects.new("SlotSecond", None)
scene.collection.objects.link(first)
scene.collection.objects.link(second)
action = bpy.data.actions.new("SharedSlots")
first_slot = action.slots.new(id_type="OBJECT", name=first.name)
second_slot = action.slots.new(id_type="OBJECT", name=second.name)
for obj, slot, value in ((first, first_slot, 2.0), (second, second_slot, 7.0)):
    obj.animation_data_create()
    obj.animation_data.action = action
    obj.animation_data.action_slot = slot
    curve = action_fcurves(action, obj).new("location", index=0, action_group="Owner")
    curve.keyframe_points.insert(1, value)
    curve.keyframe_points.insert(3, value + 2)
scene.frame_set(2)
assert abs(first.location.x - 3) < 1e-5, first.location[:]
assert abs(second.location.x - 8) < 1e-5, second.location[:]
assert action_fcurves(action, second).find("location", index=0).evaluate(1) == 7

# Copied Actions must retain the non-first slot without touching their source.
copied = action.copy()
assign_action(second.animation_data, copied)
assert second.animation_data.action_slot.identifier == second_slot.identifier
_replace_curve_range(copied, "location", 0, "Owner", 1, 3, [(1, 17), (3, 19)], second)
scene.frame_set(1)
assert second.location.x == 17
assert action_fcurves(action, second).find("location", index=0).evaluate(1) == 7
assert action_fcurves(copied, first).find("location", index=0).evaluate(1) == 2
_restore_curve_range(copied, action, "location", 0, 1, 3, second)
assert action_fcurves(copied, second).find("location", index=0).evaluate(1) == 7
assign_action(second.animation_data, action)
track = second.animation_data.nla_tracks.new()
strip = track.strips.new("SecondSlot", 1, action)
link_strip_action(strip, action, second)
assert strip.action_slot.identifier == second_slot.identifier
assign_action(second.animation_data, None)
scene.frame_set(2)
assert abs(second.location.x - 8) < 1e-5, second.location[:]
assert action_fcurves(action, strip).find("location", index=0).evaluate(1) == 7
second.animation_data.nla_tracks.remove(track)
assign_action(second.animation_data, action, slot=second_slot)
scoped = action_fcurves(copied, second)
scoped.remove(scoped.find("location", index=0))
assert not list(scoped)
scoped.new("location", index=1).keyframe_points.insert(1, 3)
assert len(scoped) == 1 and scoped[0].array_index == 1
scoped.clear()
assert len(scoped) == 0 and len(action_fcurves(copied, first)) == 1

# Refuse an ambiguous action-only lookup rather than mutating another owner.
try:
    list(action_fcurves(action))
except RuntimeError:
    pass
else:
    raise AssertionError("A multi-owner Action must require an explicit owner")

mesh = bpy.data.meshes.new("Converted")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
obj = bpy.data.objects.new("Converted", mesh)
scene.collection.objects.link(obj)
write_shape_keys({obj: [v.co + Vector((0, 0, 1)) for v in mesh.vertices]}, "Result")
key = mesh.shape_keys.key_blocks["Result"]
assert key.value == 0.0
key.value = 0.25
write_shape_keys({obj: [v.co + Vector((0, 0, 2)) for v in mesh.vertices]}, "Result")
assert key.value == 0.25
shape_action = bpy.data.actions.new("ShapeAction")
assign_action(mesh.shape_keys.animation_data_create(), shape_action)
curve = action_fcurves(shape_action, mesh.shape_keys).new(key.path_from_id("value"))
curve.keyframe_points.insert(1, 0.2)
curve.keyframe_points.insert(3, 0.8)
scene.frame_set(2)
assert abs(key.value - 0.5) < 1e-5
assert mesh.shape_keys.animation_data.action_slot.target_id_type == "KEY"

# A mismatched single-slot Action must not expose another ID type's curves.
typed_action = bpy.data.actions.new("TypedAction")
object_curve = action_fcurves(typed_action, first).new("location", index=0)
object_curve.keyframe_points.insert(1, 11)
key_curves = action_fcurves(typed_action, mesh.shape_keys)
assert not list(key_curves)
key_curves.clear()
assert object_curve.evaluate(1) == 11
key_curves.new(key.path_from_id("value")).keyframe_points.insert(1, 0.6)
assert len(typed_action.slots) == 2
assert object_curve.evaluate(1) == 11

# Blender 4.x's legacy new() creates an UNSPECIFIED slot until assignment.
if bpy.app.version < (5, 0, 0):
    for owner, path, value in ((second, "location", 13),
                               (mesh.shape_keys, key.path_from_id("value"), 0.4)):
        legacy = bpy.data.actions.new("LegacyUnspecified")
        legacy.fcurves.new(path, index=0).keyframe_points.insert(1, value)
        assert legacy.slots[0].target_id_type == "UNSPECIFIED"
        assert action_fcurves(legacy, owner).find(path, index=0) is not None
        assign_action(owner.animation_data_create(), legacy)
        assert len(legacy.slots) == 1
        assert owner.animation_data.action_slot is not None
        scene.frame_set(1)
    assert second.location.x == 13
    assert abs(key.value - 0.4) < 1e-6

uv_layer = mesh.uv_layers.new()
for index, selected in enumerate((True, False, True)):
    set_uv_selection(mesh, uv_layer, index, selected)
if bpy.app.version >= (5, 0, 0):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    assert [loop.uv_select_vert for face in bm.faces for loop in face.loops] == [True, False, True]
    bm.free()
else:
    assert [item.select for item in uv_layer.data] == [True, False, True]
mmd_station.unregister()
mmd_station.register()
assert hasattr(bpy.types.Scene, "surface_proxy_creator")
assert hasattr(bpy.types.Object, "spx_morph_states")
mmd_station.unregister()
print("BLENDER_COMPAT_REGRESSION_OK")
