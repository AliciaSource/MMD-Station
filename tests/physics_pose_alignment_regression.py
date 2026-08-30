import pathlib
import sys

import bpy
from mathutils import Euler, Matrix, Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
from mmd_station.mmd_physics import _mmd_api
from mmd_station.physics_preview.runtime import align_model_physics_to_pose
from bl_ext.blender_org.mmd_tools.core.model import Model


def matrix_delta(left, right):
    return max(
        abs(left[row][column] - right[row][column])
        for row in range(4)
        for column in range(4)
    )


mmd_station.register()
model = Model.create("PoseAlignment", "PoseAlignment", 0.08, add_root_bone=True)
root = model.rootObject()
armature = model.armature()
bone = next(iter(armature.data.bones))
pose_bone = armature.pose.bones[bone.name]

FnModel, FnRigidBody, _rigid_module = _mmd_api()
rigid_group = FnModel.ensure_rigid_group_object(bpy.context, root)
joint_group = FnModel.ensure_joint_group_object(bpy.context, root)


def add_rigid(name, bone_name, location):
    obj = FnRigidBody.new_rigid_body_objects(bpy.context, rigid_group, 1)[0]
    return FnRigidBody.setup_rigid_body_object(
        obj=obj,
        name=name,
        name_e=name,
        shape_type=0,
        dynamics_type=1,
        location=location,
        rotation=(0.0, 0.0, 0.0),
        size=(0.1, 0.1, 0.1),
        collision_group_number=0,
        collision_group_mask=[False] * 16,
        mass=1.0,
        friction=0.5,
        bounce=0.0,
        linear_damping=0.5,
        angular_damping=0.5,
        bone=bone_name,
    )


bound = add_rigid("PoseBound", bone.name, (0.0, 0.0, 0.0))
unbound = add_rigid("PoseUnbound", "", (1.0, 2.0, 3.0))
rest_bone_world = armature.matrix_world @ bone.matrix_local
rigid_offset = (
    Matrix.Translation((0.25, -0.4, 0.15))
    @ Euler((0.2, -0.1, 0.35), "XYZ").to_matrix().to_4x4()
)
rest_rigid_world = rest_bone_world @ rigid_offset
bound.matrix_world = rest_rigid_world

joint = FnRigidBody.new_joint_objects(
    bpy.context,
    joint_group,
    1,
    FnModel.get_empty_display_size(root),
)[0]
joint = FnRigidBody.setup_joint_object(
    obj=joint,
    name="PoseJoint",
    name_e="PoseJoint",
    location=Vector((0.6, -0.2, 0.8)),
    rotation=(0.1, 0.2, -0.15),
    rigid_a=bound,
    rigid_b=unbound,
    maximum_location=Vector((0.0, 0.0, 0.0)),
    minimum_location=Vector((0.0, 0.0, 0.0)),
    maximum_rotation=Vector((0.0, 0.0, 0.0)),
    minimum_rotation=Vector((0.0, 0.0, 0.0)),
    spring_angular=Vector((0.0, 0.0, 0.0)),
    spring_linear=Vector((0.0, 0.0, 0.0)),
)
bpy.context.view_layer.update()
rest_unbound_world = unbound.matrix_world.copy()
rest_joint_world = joint.matrix_world.copy()

pose_bone.rotation_mode = "XYZ"
pose_bone.location = (0.3, 0.1, -0.2)
pose_bone.rotation_euler = (0.15, -0.25, 0.4)
bpy.context.view_layer.update()
pose_bone_world = armature.matrix_world @ pose_bone.matrix
pose_delta = pose_bone_world @ rest_bone_world.inverted_safe()

assert align_model_physics_to_pose(root) == (1, 1)
assert matrix_delta(bound.matrix_world, pose_delta @ rest_rigid_world) < 1.0e-6
assert matrix_delta(joint.matrix_world, pose_delta @ rest_joint_world) < 1.0e-6
assert matrix_delta(unbound.matrix_world, rest_unbound_world) < 1.0e-6
assert matrix_delta(bound.matrix_world, pose_bone_world) > 1.0e-3
if bpy.context.scene.rigidbody_world is not None:
    assert not bpy.context.scene.rigidbody_world.enabled

pose_bone.location = (-0.2, 0.45, 0.3)
pose_bone.rotation_euler = (-0.35, 0.1, -0.2)
bpy.context.view_layer.update()
second_pose_world = armature.matrix_world @ pose_bone.matrix
second_delta = second_pose_world @ rest_bone_world.inverted_safe()
settings = bpy.context.scene.surface_proxy_creator
settings.preview_scope = "CURRENT_PROXY"
settings.mmd_root = root
assert bpy.ops.surface_proxy.align_mmd_physics_to_pose() == {"FINISHED"}
assert matrix_delta(bound.matrix_world, second_delta @ rest_rigid_world) < 1.0e-6
assert matrix_delta(joint.matrix_world, second_delta @ rest_joint_world) < 1.0e-6
assert matrix_delta(unbound.matrix_world, rest_unbound_world) < 1.0e-6

armature.animation_data_create()
source_action = bpy.data.actions.new("PoseSource")
source_action["mmd_station_action_uid"] = "pose-source-uid"
armature.animation_data.action = source_action
pose_bone.location = (0.1, 0.0, 0.0)
pose_bone.rotation_euler = (0.0, 0.0, 0.0)
pose_bone.keyframe_insert("location", frame=3, group=bone.name)
pose_bone.location = (0.4, -0.2, 0.15)
pose_bone.keyframe_insert("location", frame=4, group=bone.name)
output_action = source_action.copy()
output_action.name = "PoseSource · Physics Bake"
output_action["mmd_station_physics_generated"] = True
output_action["mmd_station_physics_source_uid"] = "pose-source-uid"
output_action.pop("mmd_station_action_uid", None)
output_curve = output_action.fcurves.find(
    f'pose.bones["{bone.name}"].location',
    index=0,
)
for point in output_curve.keyframe_points:
    point.co.y += 20.0

for frame, expected_source_x in ((3, 0.1), (4, 0.4)):
    armature.animation_data.action = output_action
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    assert pose_bone.location.x > 10.0
    assert align_model_physics_to_pose(root) == (1, 1)
    assert armature.animation_data.action is source_action
    bpy.context.view_layer.update()
    assert abs(pose_bone.location.x - expected_source_x) < 1.0e-6
    source_bone_world = armature.matrix_world @ pose_bone.matrix
    source_delta = source_bone_world @ rest_bone_world.inverted_safe()
    assert matrix_delta(bound.matrix_world, source_delta @ rest_rigid_world) < 1.0e-6
    assert matrix_delta(joint.matrix_world, source_delta @ rest_joint_world) < 1.0e-6

print("MMD_PHYSICS_POSE_ALIGNMENT_OK")
mmd_station.unregister()
