import pathlib
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from bl_ext.blender_org.mmd_tools.core.model import Model
from mmd_station.mmd_physics import _mmd_api
from mmd_station.mmd_rigid_scale import (
    rigid_object_scale_needs_bake,
    rigid_world_scale_is_invalid,
    uniform_rigid_world_scale,
)


def world_bounds(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return tuple(
        value
        for axis in range(3)
        for value in (
            min(point[axis] for point in points),
            max(point[axis] for point in points),
        )
    )


def make_rigid(FnModel, FnRigidBody, rigid_module, root, bone_name, name, shape, size):
    group = FnModel.ensure_rigid_group_object(bpy.context, root)
    rigid = FnRigidBody.new_rigid_body_objects(bpy.context, group, 1)[0]
    return FnRigidBody.setup_rigid_body_object(
        obj=rigid,
        shape_type=rigid_module.shapeType(shape),
        location=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
        size=size,
        dynamics_type=1,
        name=name,
        name_e=name,
        collision_group_number=0,
        collision_group_mask=[False] * 16,
        mass=1.0,
        friction=0.5,
        bounce=0.0,
        linear_damping=0.5,
        angular_damping=0.5,
        bone=bone_name,
    )


mmd_station.register()
model = Model.create("RigidScaleDiagnosticRegression", add_root_bone=True)
root = model.rootObject()
armature = model.armature()
bone_name = next(iter(armature.data.bones)).name
FnModel, FnRigidBody, rigid_module = _mmd_api()

capsule = make_rigid(
    FnModel,
    FnRigidBody,
    rigid_module,
    root,
    bone_name,
    "ScaledCapsule",
    "CAPSULE",
    (0.0469570495, 0.2714201212, 0.0),
)
capsule.scale = (1.0578223467, 1.0578224659, 0.9999998808)
unfixable_sphere = make_rigid(
    FnModel,
    FnRigidBody,
    rigid_module,
    root,
    bone_name,
    "EllipsoidSphere",
    "SPHERE",
    (0.1, 0.0, 0.0),
)
unfixable_sphere.scale = (2.0, 1.0, 1.0)
uniform_box = make_rigid(
    FnModel,
    FnRigidBody,
    rigid_module,
    root,
    bone_name,
    "UniformScaledBox",
    "BOX",
    (0.2, 0.3, 0.4),
)
uniform_box.scale = (1.092, 1.092, 1.092)
bpy.context.view_layer.update()

capsule_bounds_before = world_bounds(capsule)
capsule_size_before = Vector(capsule.mmd_rigid.size)
sphere_scale_before = tuple(unfixable_sphere.scale)
uniform_box_bounds_before = world_bounds(uniform_box)
uniform_box_size_before = Vector(uniform_box.mmd_rigid.size)
assert not rigid_world_scale_is_invalid(uniform_box)
assert rigid_object_scale_needs_bake(uniform_box)
assert abs(uniform_rigid_world_scale(uniform_box) - 1.092) < 1.0e-6

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.browser_kind = "DIAGNOSTIC"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
issues = {
    item.target_name: item
    for item in settings.browser_diagnostics
    if item.code.startswith("RIGID_SCALE")
}
assert issues[capsule.name].code == "RIGID_SCALE_BAKE", [
    (item.target_name, item.code, item.message)
    for item in settings.browser_diagnostics
]
assert issues[unfixable_sphere.name].code == "RIGID_SCALE_UNFIXABLE", [
    (item.target_name, item.code, item.message)
    for item in settings.browser_diagnostics
]
assert issues[uniform_box.name].code == "RIGID_SCALE_NORMALIZE", [
    (item.target_name, item.code, item.message)
    for item in settings.browser_diagnostics
]
assert issues[uniform_box.name].severity == "WARNING"
assert "物理预览仍可运行" in issues[uniform_box.name].message

uniform_box_issue = issues[uniform_box.name]
assert bpy.ops.surface_proxy.repair_mmd_diagnostic(
    code=uniform_box_issue.code,
    target_kind=uniform_box_issue.target_kind,
    target_name=uniform_box_issue.target_name,
    diagnostic_message=uniform_box_issue.message,
) == {"FINISHED"}
assert not rigid_world_scale_is_invalid(uniform_box)
assert not rigid_object_scale_needs_bake(uniform_box)
assert all(abs(value - 1.0) < 1.0e-6 for value in uniform_box.scale)
for actual, original in zip(uniform_box.mmd_rigid.size, uniform_box_size_before):
    assert abs(actual - original * 1.092) < 1.0e-6
uniform_box_bounds_after = world_bounds(uniform_box)
assert all(
    abs(before - after) < 1.0e-6
    for before, after in zip(
        uniform_box_bounds_before,
        uniform_box_bounds_after,
        strict=True,
    )
)
assert not any(
    item.target_name == uniform_box.name and item.code.startswith("RIGID_SCALE")
    for item in settings.browser_diagnostics
)

capsule_issue = issues[capsule.name]
assert bpy.ops.surface_proxy.repair_mmd_diagnostic(
    code=capsule_issue.code,
    target_kind=capsule_issue.target_kind,
    target_name=capsule_issue.target_name,
    diagnostic_message=capsule_issue.message,
) == {"FINISHED"}

assert not rigid_world_scale_is_invalid(capsule)
assert abs(uniform_rigid_world_scale(capsule) - 1.0) < 1.0e-6
assert all(abs(value - 1.0) < 1.0e-6 for value in capsule.scale)
expected_radius = capsule_size_before.x * (1.0578223467 + 1.0578224659) * 0.5
expected_height = (
    capsule_size_before.y + 2.0 * capsule_size_before.x
) * 0.9999998808 - 2.0 * expected_radius
assert abs(capsule.mmd_rigid.size[0] - expected_radius) < 1.0e-6
assert abs(capsule.mmd_rigid.size[1] - expected_height) < 1.0e-6
capsule_bounds_after = world_bounds(capsule)
assert all(
    abs(before - after) < 1.0e-6
    for before, after in zip(capsule_bounds_before, capsule_bounds_after, strict=True)
)
assert not any(
    item.target_name == capsule.name and item.code.startswith("RIGID_SCALE")
    for item in settings.browser_diagnostics
)

sphere_issue = next(
    item
    for item in settings.browser_diagnostics
    if item.target_name == unfixable_sphere.name
)
try:
    bpy.ops.surface_proxy.repair_mmd_diagnostic(
        code=sphere_issue.code,
        target_kind=sphere_issue.target_kind,
        target_name=sphere_issue.target_name,
        diagnostic_message=sphere_issue.message,
    )
except RuntimeError as error:
    assert "PMX Sphere 无法精确表示" in str(error)
else:
    raise AssertionError("Unfixable Sphere scale should be rejected")
assert tuple(unfixable_sphere.scale) == sphere_scale_before
assert rigid_world_scale_is_invalid(unfixable_sphere)

print("MMD_RIGID_SCALE_DIAGNOSTIC_REGRESSION_OK")
