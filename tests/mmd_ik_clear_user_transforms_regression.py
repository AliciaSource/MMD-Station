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
from mmd_skirt_proxy_creator.mmd_ik_runtime import lifecycle
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
root.pop("spx_mmd_ik_source_pmx", None)
expected_pmx = Path(root["import_folder"]) / PMX_NAME
assert evaluator._resolve_live_source_path(root).resolve() == expected_pmx.resolve()
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

session = evaluator._SESSIONS[root.name]
armature = runtime._model_armature(root)
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
if armature.mode != "POSE":
    bpy.ops.object.mode_set(mode="POSE")

ik_bone = armature.pose.bones["足ＩＫ.L"]
ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.05, 0.0, 0.0))
bpy.context.view_layer.update()
session.evaluate_live(bpy.context.scene)

session.suspended = True
try:
    assert bpy.ops.pose.user_transforms_clear(only_selected=False) == {"FINISHED"}
    bpy.context.view_layer.update()
    cleared_basis = {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
    }
finally:
    session.suspended = False

evaluator._depsgraph_update_post(bpy.context.scene)

maximum_input_error = 0.0
for name, cleared in cleared_basis.items():
    current = session.input_basis.get(name)
    if current is None:
        continue
    maximum_input_error = max(
        maximum_input_error,
        (current.translation - cleared.translation).length,
        current.to_quaternion().rotation_difference(cleared.to_quaternion()).angle,
    )
assert maximum_input_error < 1.0e-6, maximum_input_error

maximum_pose_translation = max(
    pose_bone.matrix.translation.length
    for pose_bone in armature.pose.bones
)
assert maximum_pose_translation < 100.0, maximum_pose_translation

settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
root.spx_physics_preview_selected = True
preview_session = runtime.start_preview(bpy.context)[0]
runtime._timer_tick(0.0)

ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.05, 0.0, 0.0))
bpy.context.view_layer.update()
runtime._timer_tick(1.0 / 60.0)

session.suspended = True
try:
    assert bpy.ops.pose.user_transforms_clear(only_selected=False) == {"FINISHED"}
    bpy.context.view_layer.update()
    cleared_basis = {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
    }
finally:
    session.suspended = False

runtime._timer_tick(2.0 / 60.0)
maximum_input_error = 0.0
for name, cleared in cleared_basis.items():
    current = session.input_basis.get(name)
    if current is None:
        continue
    maximum_input_error = max(
        maximum_input_error,
        (current.translation - cleared.translation).length,
        current.to_quaternion().rotation_difference(cleared.to_quaternion()).angle,
    )
assert maximum_input_error < 1.0e-6, maximum_input_error
assert preview_session.consecutive_tick_failures == 0

root_name = root.name
original_session = evaluator._SESSIONS[root_name]
original_solver = original_session.solver
original_preview_session = runtime._ACTIVE_SESSIONS[root_name]
original_preview_solver = original_preview_session.solver


lifecycle._undo_redo_pre(bpy.context.scene)
assert original_session.suspended
assert runtime._RUNTIME_SUSPENDED
assert bpy.ops.pose.user_transforms_clear(only_selected=False) == {"FINISHED"}
lifecycle._undo_redo_post(bpy.context.scene)
if bpy.app.timers.is_registered(lifecycle._resume_undo_redo_timer):
    bpy.app.timers.unregister(lifecycle._resume_undo_redo_timer)
lifecycle._resume_undo_redo_timer()
assert evaluator._SESSIONS[root_name] is original_session
assert original_session.solver is original_solver
assert runtime._ACTIVE_SESSIONS[root_name] is original_preview_session
resumed_preview_solver = original_preview_session.solver
assert resumed_preview_solver is original_preview_session.world.solver
assert resumed_preview_solver is not original_preview_solver
assert original_preview_solver.handle is None

resumed_session = evaluator._SESSIONS[root_name]
assert resumed_session is original_session
assert resumed_session.solver is original_solver
assert not resumed_session.suspended
assert runtime._ACTIVE_SESSIONS[root_name] is original_preview_session
assert original_preview_session.solver is resumed_preview_solver
assert not runtime._RUNTIME_SUSPENDED
assert max(
    max(
        abs(value - (1.0 if row == column else 0.0))
        for row, matrix_row in enumerate(matrix)
        for column, value in enumerate(matrix_row)
    )
    for matrix in resumed_session.input_basis.values()
) < 1.0e-6
runtime._timer_tick(3.0 / 60.0)
assert preview_session.consecutive_tick_failures == 0

runtime.stop_preview(root)
bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print("MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK")
