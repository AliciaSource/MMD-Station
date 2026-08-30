import pathlib
import sys
from types import SimpleNamespace

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from mmd_station.mmd_physics import _mmd_api
from mmd_station.physics_preview.bake import (
    BakeJob,
    _segments,
    _source_action,
    draw_bake,
)
from bl_ext.blender_org.mmd_tools.core.model import Model


mmd_station.register()

model = Model.create("PhysicsBakeRegression", add_root_bone=True)
root = model.rootObject()
root.empty_display_size = 0.4
armature = model.armature()
bone = next(iter(armature.data.bones))

FnModel, FnRigidBody, rigid_module = _mmd_api()
rigid_group = FnModel.ensure_rigid_group_object(bpy.context, root)


def add_rigid(name, dynamics_type, z):
    rigid = FnRigidBody.new_rigid_body_objects(bpy.context, rigid_group, 1)[0]
    return FnRigidBody.setup_rigid_body_object(
        obj=rigid,
        shape_type=rigid_module.shapeType("SPHERE"),
        location=(0.0, 0.0, z),
        rotation=(0.0, 0.0, 0.0),
        size=(0.15, 0.15, 0.15),
        dynamics_type=dynamics_type,
        name=name,
        name_e=name,
        collision_group_number=0,
        collision_group_mask=[False] * 16,
        mass=1.0,
        friction=0.5,
        bounce=0.0,
        linear_damping=0.5,
        angular_damping=0.5,
        bone=bone.name,
    )


add_rigid("BakeAnchor", 0, 0.0)
add_rigid("BakeDynamic", 1, -0.3)

source = bpy.data.actions.new("BakeSource")
armature.animation_data_create().action = source
source_curve = source.fcurves.new(
    f'pose.bones["{bpy.utils.escape_identifier(bone.name)}"].location',
    index=0,
)
source_curve.keyframe_points.add(2)
source_curve.keyframe_points.foreach_set("co", (1.0, 0.1, 3.0, 0.3))
for point in source_curve.keyframe_points:
    point.interpolation = "LINEAR"
bpy.context.scene.frame_set(bpy.context.scene.frame_current)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_scope = "MODEL"
settings.preview_solver_target = "PMX"
settings.preview_update_rigids = False
settings.physics_bake_start = 1
settings.physics_bake_end = 3
settings.physics_bake_preroll = 2
settings.physics_bake_continuity = "INDEPENDENT"

original_frame = bpy.context.scene.frame_current
original_action = armature.animation_data.action
original_basis = armature.pose.bones[bone.name].matrix_basis.copy()
cancelled = BakeJob(bpy.context, "FAST")
assert cancelled.steps[:2] == [(1, False), (1, False)]
assert min(frame for frame, _store in cancelled.steps) == 1
assert not root.hide_get() and not armature.hide_get()
cancelled._evaluate_source_action(2)
assert abs(cancelled.work_armature.pose.bones[bone.name].location.x - 0.2) < 1.0e-6
assert armature.pose.bones[bone.name].matrix_basis == original_basis
work_collection_name = cancelled.work_collection.name
cancelled.step()
assert armature.pose.bones[bone.name].matrix_basis == original_basis
armature.pose.bones[bone.name].location.x += 42.0
cancelled.close()
assert bpy.data.collections.get(work_collection_name) is None
assert not cancelled.work_objects
assert bpy.context.scene.frame_current == original_frame
assert armature.animation_data.action is original_action
assert not root.hide_get() and not armature.hide_get()
restored_basis = armature.pose.bones[bone.name].matrix_basis
restore_delta = max(
    abs(restored_basis[row][column] - original_basis[row][column])
    for row in range(4)
    for column in range(4)
)
assert restore_delta < 1.0e-6

settings.physics_bake_preroll = 0
job = BakeJob(bpy.context, "FAST")
while job.step():
    pass
first = job.finish()
output = armature.animation_data.action
assert first["start"] == 1 and first["end"] == 3
assert output is not source
assert output.get("mmd_station_physics_generated", False)
assert _source_action(armature) is source
assert _segments(output) == [first]
bone_prefix = f'pose.bones["{bpy.utils.escape_identifier(bone.name)}"]'
assert output.fcurves.find(f"{bone_prefix}.location", index=0) is not None
assert output.fcurves.find(f"{bone_prefix}.rotation_quaternion", index=0) is not None
assert len(source.fcurves) == 1

settings.physics_bake_start = 4
settings.physics_bake_end = 5
settings.physics_bake_continuity = "CONTINUE"
job = BakeJob(bpy.context, "PLAYBACK")
assert job.simulation_start == 1
while job.step():
    pass
second = job.finish()
segments = _segments(armature.animation_data.action)
assert [(item["start"], item["end"]) for item in segments] == [(1, 3), (4, 5)]
assert second["continuity"] == "CONTINUE"
location_curve = armature.animation_data.action.fcurves.find(
    f"{bone_prefix}.location",
    index=0,
)
assert [point.co.x for point in location_curve.keyframe_points] == [1, 2, 3, 4, 5]
assert all(point.interpolation == "LINEAR" for point in location_curve.keyframe_points)


class LayoutProbe:
    def __init__(self):
        self.enabled = True
        self.labels = []
        self.operators = []

    def box(self):
        return self

    def row(self, **_kwargs):
        return self

    def label(self, **kwargs):
        self.labels.append(kwargs.get("text", ""))

    def prop(self, *_args, **_kwargs):
        return None

    def operator(self, identifier, **_kwargs):
        self.operators.append(identifier)
        return SimpleNamespace()


layout = LayoutProbe()
draw_bake(layout, settings)
assert "surface_proxy.bake_mmd_physics" in layout.operators
assert "surface_proxy.delete_mmd_physics_bake_segment" in layout.operators
assert any("已完成烘焙区间" in label for label in layout.labels)

assert bpy.ops.surface_proxy.delete_mmd_physics_bake_segment(
    segment_id=segments[0]["id"]
) == {"FINISHED"}
remaining = _segments(armature.animation_data.action)
assert len(remaining) == 1 and remaining[0]["status"] == "STALE"
location_curve = armature.animation_data.action.fcurves.find(
    f"{bone_prefix}.location",
    index=0,
)
assert [point.co.x for point in location_curve.keyframe_points] == [1, 3, 4, 5]

assert bpy.ops.surface_proxy.clear_mmd_physics_bake() == {"FINISHED"}
assert armature.animation_data.action is source

settings.preview_solver_target = "MMD"
settings.physics_bake_start = 1
settings.physics_bake_end = 2
settings.physics_bake_continuity = "INDEPENDENT"
job = BakeJob(bpy.context, "FAST")
while job.step():
    pass
mmd_segment = job.finish()
assert mmd_segment["start"] == 1 and mmd_segment["end"] == 2
assert len(_segments(armature.animation_data.action)) == 1
assert bpy.ops.surface_proxy.clear_mmd_physics_bake() == {"FINISHED"}

print("MMD_PHYSICS_BAKE_REGRESSION_OK")
mmd_station.unregister()
