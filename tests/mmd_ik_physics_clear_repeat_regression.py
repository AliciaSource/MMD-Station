import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ARMATURE_NAME = "\u5408\u5e762_arm"
PROXY_NAME = "\u88d9\u5b50_Surface"
IK_NAME = "\u8db3\uff29\uff2b.L"
FOOT_CHAIN = ("\u8db3.L", "\u3072\u3056.L", "\u8db3\u9996.L", "\u3064\u307e\u5148.L")

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator, lifecycle
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
armature = bpy.data.objects[ARMATURE_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
ik_session = evaluator._SESSIONS[root.name]

armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="POSE")
ik_bone = armature.pose.bones[IK_NAME]


def select_ik():
    for bone in armature.data.bones:
        bone.select = False
    ik_bone.bone.select = True
    armature.data.bones.active = ik_bone.bone


def clear_all_and_capture():
    ik_session.suspended = True
    try:
        assert bpy.ops.pose.user_transforms_clear(only_selected=False) == {"FINISHED"}
        bpy.context.view_layer.update()
    finally:
        ik_session.suspended = False
    evaluator._depsgraph_update_post(bpy.context.scene)
    bpy.context.view_layer.update()
    return {
        name: armature.pose.bones[name].matrix.copy()
        for name in FOOT_CHAIN
    }


def repeat_clear_selected(pre_clear_pose):
    lifecycle._undo_redo_pre(bpy.context.scene)
    for name, matrix_basis in pre_clear_pose.items():
        armature.pose.bones[name].matrix_basis = matrix_basis
    select_ik()
    bpy.context.view_layer.update()
    assert bpy.ops.pose.user_transforms_clear(only_selected=True) == {"FINISHED"}
    lifecycle._undo_redo_post(bpy.context.scene)
    if bpy.app.timers.is_registered(lifecycle._resume_undo_redo_timer):
        bpy.app.timers.unregister(lifecycle._resume_undo_redo_timer)
    lifecycle._resume_undo_redo_timer()
    bpy.context.view_layer.update()


select_ik()
settings.preview_scope = "CURRENT_PROXY"
settings.preview_solver_target = "MMD"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
settings.physics_proxy = bpy.data.objects[PROXY_NAME]
preview = runtime.start_preview(bpy.context)[0]
runtime._timer_tick(0.0)

before_rigids = [rigid.matrix_world.copy() for rigid in preview.rigids]
ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.05, 0.0, 0.0))
bpy.context.view_layer.update()
runtime._timer_tick(1.0 / 60.0)
maximum_rigid_motion = max(
    (rigid.matrix_world.translation - before.translation).length
    for rigid, before in zip(preview.rigids, before_rigids)
)
assert maximum_rigid_motion < 0.15, maximum_rigid_motion

pre_clear_pose = {
    pose_bone.name: pose_bone.matrix_basis.copy()
    for pose_bone in armature.pose.bones
}
cleared_chain = clear_all_and_capture()
assert all(
    evaluator._matrix_near_identity(matrix)
    for matrix in ik_session.input_basis.values()
)

repeat_clear_selected(pre_clear_pose)
maximum_repeat_error = max(
    (armature.pose.bones[name].matrix.translation - cleared.translation).length
    for name, cleared in cleared_chain.items()
)
assert evaluator._matrix_near_identity(ik_bone.matrix_basis)
assert maximum_repeat_error < 1.0e-5, maximum_repeat_error
assert preview.consecutive_tick_failures == 0

runtime.stop_preview(root)
bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print(
    "MMD_IK_PHYSICS_CLEAR_REPEAT_REGRESSION_OK",
    f"rigid_motion={maximum_rigid_motion:.9g}",
    f"repeat_error={maximum_repeat_error:.9g}",
)
