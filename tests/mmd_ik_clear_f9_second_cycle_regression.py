import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ARMATURE_NAME = "\u5408\u5e762_arm"
IK_NAME = "\u8db3\uff29\uff2b.L"
FOOT_CHAIN = ("\u8db3.L", "\u3072\u3056.L", "\u8db3\u9996.L", "\u3064\u307e\u5148.L")
PROXY_NAME = "\u88d9\u5b50_Surface"
TARGET = os.environ.get("SPX_TEST_SOLVER", "NONE")

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator, lifecycle
from mmd_station.physics_preview import runtime

mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
armature = bpy.data.objects[ARMATURE_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = evaluator._SESSIONS[root.name]
ik_is_owned = IK_NAME in session.output_bone_names()

if TARGET != "NONE":
    settings.preview_scope = "CURRENT_PROXY"
    settings.preview_solver_target = TARGET
    settings.preview_frequency = 60
    settings.preview_substeps = 10
    settings.preview_update_rigids = True
    settings.mmd_root = root
    settings.physics_proxy = bpy.data.objects[PROXY_NAME]
    preview = runtime.start_preview(bpy.context)[0]
    runtime._timer_tick(0.0)
else:
    preview = None
physics_time = 0.0

armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="POSE")
ik_bone = armature.pose.bones[IK_NAME]


def select_ik():
    for bone in armature.data.bones:
        bone.select = False
    ik_bone.bone.select = True
    armature.data.bones.active = ik_bone.bone


def capture_basis():
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
    }


def capture_chain():
    return {
        name: armature.pose.bones[name].matrix.copy()
        for name in FOOT_CHAIN
    }


def step_physics():
    global physics_time
    if preview is None:
        return
    physics_time += 1.0 / 60.0
    runtime._timer_tick(physics_time)


def finish_resume():
    lifecycle._undo_redo_post(bpy.context.scene)
    if bpy.app.timers.is_registered(lifecycle._resume_undo_redo_timer):
        bpy.app.timers.unregister(lifecycle._resume_undo_redo_timer)
    lifecycle._resume_undo_redo_timer()
    bpy.context.view_layer.update()
    step_physics()


def clear_direct(only_selected):
    session.suspended = True
    try:
        assert bpy.ops.pose.user_transforms_clear(
            only_selected=only_selected
        ) == {"FINISHED"}
        bpy.context.view_layer.update()
    finally:
        session.suspended = False
    evaluator._depsgraph_update_post(bpy.context.scene)
    bpy.context.view_layer.update()
    step_physics()


def redo_clear(
    pre_operation_basis,
    only_selected,
    stale_selected_basis=None,
    settled_output_basis=None,
):
    lifecycle._undo_redo_pre(bpy.context.scene)
    for name, matrix_basis in pre_operation_basis.items():
        armature.pose.bones[name].matrix_basis = matrix_basis
    select_ik()
    bpy.context.view_layer.update()
    assert bpy.ops.pose.user_transforms_clear(
        only_selected=only_selected
    ) == {"FINISHED"}
    if settled_output_basis is not None:
        for name in session.output_bone_names():
            armature.pose.bones[name].matrix_basis = settled_output_basis[name]
    if stale_selected_basis is not None:
        ik_bone.matrix_basis = stale_selected_basis[IK_NAME]
    finish_resume()


select_ik()
first_pre_clear = capture_basis()
clear_direct(only_selected=True)
redo_clear(first_pre_clear, only_selected=False)
first_clear_chain = capture_chain()
assert all(
    evaluator._matrix_near_identity(matrix)
    for matrix in session.input_basis.values()
)

ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.05, 0.0, 0.0))
bpy.context.view_layer.update()
evaluator._depsgraph_update_post(bpy.context.scene)
bpy.context.view_layer.update()
step_physics()
second_pre_clear = capture_basis()
moved_chain = capture_chain()
movement = max(
    (moved_chain[name].translation - first_clear_chain[name].translation).length
    for name in FOOT_CHAIN
)
assert movement > 1.0e-3, movement

clear_direct(only_selected=False)
second_clear_basis = capture_basis()
redo_clear(
    second_pre_clear,
    only_selected=True,
    stale_selected_basis=second_pre_clear,
    settled_output_basis=second_clear_basis,
)

ik_input_error = max(
    abs(session.input_basis[IK_NAME][row][column] - Matrix.Identity(4)[row][column])
    for row in range(4)
    for column in range(4)
)
ik_display_error = max(
    abs(ik_bone.matrix_basis[row][column] - Matrix.Identity(4)[row][column])
    for row in range(4)
    for column in range(4)
)
chain_error = max(
    (armature.pose.bones[name].matrix.translation - first_clear_chain[name].translation).length
    for name in FOOT_CHAIN
)
assert ik_input_error < 1.0e-6, ik_input_error
assert ik_display_error < 1.0e-6, ik_display_error
assert chain_error < 1.0e-5, chain_error
assert preview is None or preview.consecutive_tick_failures == 0

if preview is not None:
    runtime.stop_preview(root)
bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print(
    "MMD_IK_CLEAR_F9_SECOND_CYCLE_REGRESSION_OK",
    TARGET,
    f"ik_owned={ik_is_owned}",
    f"movement={movement:.9g}",
    f"ik_input_error={ik_input_error:.9g}",
    f"ik_display_error={ik_display_error:.9g}",
    f"chain_error={chain_error:.9g}",
)
