import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "鸣潮_达妮娅1.2（blue ver）"
PMX_NAME = "鸣潮_达妮娅1.2（blue ver）.pmx"

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
from mmd_station.physics_preview import runtime

mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
root["spx_mmd_ik_source_pmx"] = str(Path(root["import_folder"]) / PMX_NAME)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

session = evaluator._SESSIONS[root.name]
armature = runtime._model_armature(root)
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
root.spx_physics_preview_selected = True

exact_target_submissions = []
original_prepare_physics_targets = evaluator.prepare_physics_targets


def track_exact_targets(root, preview_session):
    submitted = original_prepare_physics_targets(root, preview_session)
    exact_target_submissions.append((preview_session.solver_target, submitted))
    return submitted


evaluator.prepare_physics_targets = track_exact_targets
try:
    for solver_target in ("PMX", "MMD"):
        settings.preview_solver_target = solver_target
        preview_session = runtime.start_preview(bpy.context)[0]
        runtime._timer_tick(0.0)
        bone_name = next(
            name
            for name in sorted(preview_session.bone_drivers)
            if name in session.input_basis
        )
        pose_bone = armature.pose.bones[bone_name]
        pose_bone.matrix_basis = pose_bone.matrix_basis @ Matrix.Translation(
            (0.001, 0.0, 0.0)
        )
        bpy.context.view_layer.update()
        evaluator._depsgraph_update_post(bpy.context.scene)
        runtime._timer_tick(1.0 / 60.0)
        accepted = session.input_basis[bone_name].copy()

        maximum_drift = 0.0
        for tick in range(2, 12):
            runtime._timer_tick(tick / 60.0)
            current = session.input_basis[bone_name]
            maximum_drift = max(
                maximum_drift,
                (current.translation - accepted.translation).length,
                current.to_quaternion().rotation_difference(
                    accepted.to_quaternion()
                ).angle,
            )
        assert maximum_drift < 1.0e-7, (solver_target, bone_name, maximum_drift)
        runtime.stop_preview(root)
finally:
    evaluator.prepare_physics_targets = original_prepare_physics_targets

assert exact_target_submissions
assert {target for target, _submitted in exact_target_submissions} == {"MMD"}
assert min(submitted for _target, submitted in exact_target_submissions) > 0

bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print(
    "MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK",
    f"exact_calls={len(exact_target_submissions)}",
    f"exact_min={min(submitted for _target, submitted in exact_target_submissions)}",
)
