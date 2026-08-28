import math
import os
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(
    r"D:\MMD\MEGA\_Alicia模型\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.physics_preview import runtime as physics_runtime
from mmd_tools.core.pmx.importer import PMXImporter

mmd_station.register()


solver_target = os.environ.get("SPX_TEST_SOLVER_TARGET", "PMX")
assert solver_target in {"PMX", "MMD"}
PMXImporter().execute(
    filepath=str(PMX),
    types={"ARMATURE", "PHYSICS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
for obj in bpy.context.selected_objects:
    obj.select_set(False)
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root

settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = solver_target
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
root.spx_physics_preview_selected = True
def run_step(session):
    session.prepare_step()
    animation_pose = {
        name: matrix.copy() for name, matrix in session.pending_animation_pose.items()
    }
    session.world.pending_step_seconds = 1.0 / 60.0
    assert session.step_solver()
    outputs = session.world.outputs()
    session.apply_step(*outputs)
    return animation_pose, outputs


session = physics_runtime.start_preview(bpy.context)[0]
outputs = None
for _frame in range(30):
    _animation_pose, outputs = run_step(session)
type_zero_indices = [
    index
    for index, rigid in enumerate(session.rigids)
    if int(rigid.mmd_rigid.type) == 0 and index in session.bone_offsets
]
assert type_zero_indices
display_before = [
    tuple(float(value) for value in session.rigids[index].matrix_world.translation)
    for index in type_zero_indices
]
kinematic_before = {
    index: tuple(
        float(value)
        for value in physics_runtime.transform_to_components(
            outputs[0][index]
        )[0]
    )
    for index in type_zero_indices
}
root_delta = physics_runtime.Vector((0.01, 0.0, 0.005))
root.location += root_delta
bpy.context.view_layer.update()
session.prepare_step()
for _frame in range(3):
    session.world.pending_step_seconds = 1.0 / 60.0
    assert session.step_solver()
root_move_outputs = session.world.outputs()
kinematic_after = root_move_outputs[0]
animation_pose = {
    name: matrix.copy() for name, matrix in session.pending_animation_pose.items()
}
# Model-object motion is an authored kinematic target and must reach the solver.
expected_native_delta = tuple(float(value) / session.import_scale for value in root_delta)
kinematic_target_errors = [
    math.dist(
        expected_native_delta,
        tuple(
            float(value) - kinematic_before[index][axis]
            for axis, value in enumerate(
                physics_runtime.transform_to_components(kinematic_after[index])[0]
            )
        ),
    )
    for index in type_zero_indices
]
max_kinematic_target_error = max(kinematic_target_errors)
kinematic_target_pass_fraction = sum(
    error < 2.0e-5 for error in kinematic_target_errors
) / len(kinematic_target_errors)
session.apply_step(*root_move_outputs)
display_after = [
    tuple(float(value) for value in session.rigids[index].matrix_world.translation)
    for index in type_zero_indices
]
display_frame_errors = [
    math.dist(
        tuple(float(value) for value in root_delta),
        tuple(moved[axis] - control[axis] for axis in range(3)),
    )
    for control, moved in zip(display_before, display_after)
]
max_display_frame_error = max(display_frame_errors)
display_frame_pass_fraction = sum(
    error < 2.0e-5 for error in display_frame_errors
) / len(display_frame_errors)

type_two_indices = [
    index
    for index, rigid in enumerate(session.rigids)
    if int(rigid.mmd_rigid.type) == 2
    and session.bone_drivers.get(rigid.mmd_rigid.bone) == index
]
assert type_two_indices
max_type_two_blender_error = 0.0
for index in type_two_indices:
    rigid = session.rigids[index]
    bone_name = rigid.mmd_rigid.bone
    pose_bone = session.armature.pose.bones[bone_name]
    parent = pose_bone.parent
    expected_matrix = animation_pose[bone_name]
    actual_matrix = pose_bone.matrix
    if parent is not None:
        expected_matrix = animation_pose[parent.name].inverted_safe() @ expected_matrix
        actual_matrix = parent.matrix.inverted_safe() @ actual_matrix
    max_type_two_blender_error = max(
        max_type_two_blender_error,
        (actual_matrix.translation - expected_matrix.translation).length,
    )

root_bone = session.armature.pose.bones.get("全ての親")
assert root_bone is not None
for _frame in range(60):
    root_bone.location.x += 0.001
    root_bone.location.z += 0.0005
    bpy.context.view_layer.update()
    animation_pose, _outputs = run_step(session)
    for index in type_two_indices:
        rigid = session.rigids[index]
        bone_name = rigid.mmd_rigid.bone
        pose_bone = session.armature.pose.bones[bone_name]
        parent = pose_bone.parent
        expected_matrix = animation_pose[bone_name]
        actual_matrix = pose_bone.matrix
        if parent is not None:
            expected_matrix = animation_pose[parent.name].inverted_safe() @ expected_matrix
            actual_matrix = parent.matrix.inverted_safe() @ actual_matrix
        max_type_two_blender_error = max(
            max_type_two_blender_error,
            (actual_matrix.translation - expected_matrix.translation).length,
        )

assert kinematic_target_pass_fraction > 0.95, kinematic_target_pass_fraction
assert display_frame_pass_fraction > 0.95, display_frame_pass_fraction
assert max_type_two_blender_error < 2.0e-5, max_type_two_blender_error
assert session.auto_reset_count == 0
physics_runtime.stop_preview(root)
print(
    "PHYSICS_ROOT_OFFSET_REGRESSION_OK",
    f"solver={solver_target}",
    f"kinematic_target_error={max_kinematic_target_error:.9g}",
    f"kinematic_target_pass_fraction={kinematic_target_pass_fraction:.6f}",
    f"display_frame_error={max_display_frame_error:.9g}",
    f"display_frame_pass_fraction={display_frame_pass_fraction:.6f}",
    f"type2_blender_error={max_type_two_blender_error:.9g}",
)
