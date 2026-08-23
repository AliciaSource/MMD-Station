import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "鸣潮_达妮娅1.2（blue ver）"
PMX_NAME = "鸣潮_达妮娅1.2（blue ver）.pmx"

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
root.spx_physics_preview_selected = True

# Normal mmd_tools preview must keep stepping during a Blender transform modal.
normal_armature = runtime._model_armature(root)
normal_root_bone = normal_armature.pose.bones["全ての親"]
normal_baseline = normal_root_bone.matrix_basis.copy()
normal_preview = runtime.start_preview(bpy.context)[0]
runtime._timer_tick(0.0)
bridge_calls = []
original_modal_capture = evaluator._transform_modal_pose_matrices
original_feedback_submit = evaluator.submit_physics_feedback


def track_modal_capture(armature):
    bridge_calls.append("modal_capture")
    return original_modal_capture(armature)


def track_feedback_submit(root, preview_session, transforms=None):
    bridge_calls.append("feedback_submit")
    return original_feedback_submit(root, preview_session, transforms)


evaluator._transform_modal_pose_matrices = track_modal_capture
evaluator.submit_physics_feedback = track_feedback_submit
try:
    runtime._timer_tick(0.5 / 60.0)
finally:
    evaluator._transform_modal_pose_matrices = original_modal_capture
    evaluator.submit_physics_feedback = original_feedback_submit
assert not bridge_calls, bridge_calls
normal_step_count = normal_preview.mmd_step_count
original_modal_probe = getattr(evaluator, "_transform_modal_active", None)
evaluator._transform_modal_active = lambda: True
try:
    normal_root_bone.matrix_basis = normal_baseline @ Matrix.Translation(
        (0.0, 0.05, 0.0)
    )
    bpy.context.view_layer.update()
    runtime._timer_tick(1.0 / 60.0)
    assert normal_preview.mmd_step_count > normal_step_count
    type0_error = 0.0
    for index, rigid in enumerate(normal_preview.rigids):
        if int(rigid.mmd_rigid.type) != 0 or index not in normal_preview.bone_offsets:
            continue
        pose_bone = normal_armature.pose.bones.get(rigid.mmd_rigid.bone)
        if pose_bone is None:
            continue
        expected = (
            normal_armature.matrix_world
            @ pose_bone.matrix
            @ normal_preview.bone_offsets[index]
        )
        type0_error = max(
            type0_error,
            (expected.translation - rigid.matrix_world.translation).length,
        )
    assert type0_error < 2.0e-5, type0_error
finally:
    if original_modal_probe is None:
        del evaluator._transform_modal_active
    else:
        evaluator._transform_modal_active = original_modal_probe
runtime.stop_preview(root)
normal_root_bone.matrix_basis = normal_baseline
bpy.context.view_layer.update()

root["spx_mmd_ik_source_pmx"] = str(Path(root["import_folder"]) / PMX_NAME)
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

session = evaluator._SESSIONS[root.name]
armature = runtime._model_armature(root)
for bone in armature.data.bones:
    bone.select = False
ik_bone = armature.pose.bones["足ＩＫ.L"]
ik_bone.bone.select = True
armature.data.bones.active = ik_bone.bone
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
if armature.mode != "POSE":
    bpy.ops.object.mode_set(mode="POSE")
baseline_input = session.input_basis[ik_bone.name].copy()
baseline_ik = ik_bone.matrix_basis.copy()
chain_names = ("足.L", "ひざ.L", "足首.L")
baseline_chain = {
    name: armature.pose.bones[name].matrix.copy()
    for name in chain_names
}
edited = baseline_ik @ Matrix.Translation((0.05, 0.0, 0.0))

original_modal_probe = getattr(evaluator, "_transform_modal_active", None)
evaluator._transform_modal_active = lambda: True
try:
    ik_bone.matrix_basis = edited
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    assert (ik_bone.matrix_basis.translation - edited.translation).length < 1.0e-7
    assert ik_bone.matrix_basis.to_quaternion().rotation_difference(
        edited.to_quaternion()
    ).angle < 1.0e-6
    current_input = session.input_basis[ik_bone.name]
    assert (current_input.translation - baseline_input.translation).length > 0.04
    chain_change = max(
        max(
            (
                armature.pose.bones[name].matrix.translation
                - baseline_chain[name].translation
            ).length,
            armature.pose.bones[name].matrix.to_quaternion().rotation_difference(
                baseline_chain[name].to_quaternion()
            ).angle,
        )
        for name in chain_names
    )
    assert chain_change > 1.0e-3, chain_change

    evaluator._transform_modal_active = lambda: False
    evaluator._depsgraph_update_post(bpy.context.scene)
    assert (ik_bone.matrix_basis.translation - edited.translation).length < 1.0e-6
    assert ik_bone.matrix_basis.to_quaternion().rotation_difference(
        edited.to_quaternion()
    ).angle < 1.0e-6
    evaluator._transform_modal_active = lambda: True

    ik_bone.matrix_basis = baseline_ik
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    canceled_input = session.input_basis[ik_bone.name]
    assert (canceled_input.translation - baseline_input.translation).length < 1.0e-6
    assert canceled_input.to_quaternion().rotation_difference(
        baseline_input.to_quaternion()
    ).angle < 1.0e-6
finally:
    if original_modal_probe is None:
        del evaluator._transform_modal_active
    else:
        evaluator._transform_modal_active = original_modal_probe

evaluator._depsgraph_update_post(bpy.context.scene)

pose_bone = armature.pose.bones["全ての親"]
for bone in armature.data.bones:
    bone.select = False
pose_bone.bone.select = True
armature.data.bones.active = pose_bone.bone

settings.preview_solver_target = "PMX"
preview_session = runtime.start_preview(bpy.context)[0]
runtime._timer_tick(0.0)
baseline_input = session.input_basis[pose_bone.name].copy()
baseline_output = pose_bone.matrix_basis.copy()
edited = baseline_output.copy()
edited = edited @ Matrix.Translation((0.0, 0.05, 0.0))
edited = edited @ Matrix.Rotation(0.35, 4, "Z")

original_evaluator_modal_probe = evaluator._transform_modal_active
evaluator._transform_modal_active = lambda: True
try:
    pose_bone.matrix_basis = edited
    bpy.context.view_layer.update()
    runtime._timer_tick(1.0 / 60.0)
    assert (pose_bone.matrix_basis.translation - edited.translation).length < 1.0e-7
    assert pose_bone.matrix_basis.to_quaternion().rotation_difference(
        edited.to_quaternion()
    ).angle < 1.0e-6
    current_input = session.input_basis[pose_bone.name]
    assert (current_input.translation - baseline_input.translation).length > 0.04
    assert current_input.to_quaternion().rotation_difference(
        baseline_input.to_quaternion()
    ).angle > 0.3
    partial = edited.copy()
    partial.translation = baseline_output.translation
    pose_bone.matrix_basis = partial
    bpy.context.view_layer.update()
    runtime._timer_tick(2.0 / 60.0)
    pose_bone.matrix_basis = baseline_output
    bpy.context.view_layer.update()
    runtime._timer_tick(3.0 / 60.0)
    assert (pose_bone.matrix_basis.translation - baseline_output.translation).length < 1.0e-7
    assert pose_bone.matrix_basis.to_quaternion().rotation_difference(
        baseline_output.to_quaternion()
    ).angle < 1.0e-6
    current_input = session.input_basis[pose_bone.name]
    assert (current_input.translation - baseline_input.translation).length < 1.0e-7
    assert current_input.to_quaternion().rotation_difference(
        baseline_input.to_quaternion()
    ).angle < 1.0e-6
finally:
    evaluator._transform_modal_active = original_evaluator_modal_probe

runtime.stop_preview(root)
bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print("MMD_IK_TRANSFORM_MODAL_REGRESSION_OK")
