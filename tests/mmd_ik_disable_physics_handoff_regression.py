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
PROXY_NAME = "\u88d9\u5b50_Surface"
IK_NAME = "\u8db3\uff29\uff2b.L"
FOOT_CHAIN = ("\u8db3.L", "\u3072\u3056.L", "\u8db3\u9996.L", "\u3064\u307e\u5148.L")
TARGET = os.environ.get("SPX_TEST_SOLVER", "MMD")

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
from mmd_station.physics_preview import runtime

mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
armature = bpy.data.objects[ARMATURE_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
settings.preview_scope = "CURRENT_PROXY"
settings.preview_solver_target = TARGET
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
settings.physics_proxy = bpy.data.objects[PROXY_NAME]

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
native_session = evaluator._SESSIONS[root.name]
constraint_states = tuple(native_session.muted_constraints)
preview = runtime.start_preview(bpy.context)[0]
runtime._timer_tick(0.0)

ik_bone = armature.pose.bones[IK_NAME]
ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.04, 0.0, 0.0))
bpy.context.view_layer.update()
runtime._timer_tick(1.0 / 60.0)

world = preview.world
solver = preview.solver
generation = world.generation
driver_basis = preview._capture_driver_basis()
rigid_matrices = {rigid.name: rigid.matrix_world.copy() for rigid in preview.rigids}

assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}
assert root.name not in evaluator._SESSIONS
assert runtime._ACTIVE_SESSIONS[root.name] is preview
assert preview.world is world
assert preview.solver is solver
assert world.generation == generation
assert preview.runtime_adapter is None

maximum_driver_error = max(
    (
        preview.armature.pose.bones[name].matrix_basis.translation
        - matrix.translation
    ).length
    for name, matrix in driver_basis.items()
)
maximum_rigid_error = max(
    (rigid.matrix_world.translation - rigid_matrices[rigid.name].translation).length
    for rigid in preview.rigids
)
assert maximum_driver_error < 1.0e-6, maximum_driver_error
assert maximum_rigid_error < 1.0e-6, maximum_rigid_error

armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="POSE")
for bone in armature.data.bones:
    bone.select = False
ik_bone.bone.select = True
armature.data.bones.active = ik_bone.bone
assert bpy.ops.pose.user_transforms_clear(only_selected=False) == {"FINISHED"}
bpy.context.view_layer.update()
runtime._timer_tick(2.0 / 60.0)
cleared_chain = {
    name: armature.pose.bones[name].matrix.copy()
    for name in FOOT_CHAIN
}

ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.03, 0.0, 0.0))
bpy.context.view_layer.update()
runtime._timer_tick(3.0 / 60.0)
assert bpy.ops.pose.user_transforms_clear(only_selected=True) == {"FINISHED"}
bpy.context.view_layer.update()
runtime._timer_tick(4.0 / 60.0)

maximum_clear_error = max(
    (armature.pose.bones[name].matrix.translation - cleared.translation).length
    for name, cleared in cleared_chain.items()
)

assert evaluator._matrix_near_identity(ik_bone.matrix_basis)
assert maximum_clear_error < 1.0e-5, maximum_clear_error
assert preview.consecutive_tick_failures == 0
assert all(
    armature.pose.bones[bone_name].constraints[constraint_name].mute == previous
    for bone_name, constraint_name, previous in constraint_states
)

runtime.stop_preview(root)
print(
    "MMD_IK_DISABLE_PHYSICS_HANDOFF_REGRESSION_OK",
    TARGET,
    f"drivers={len(driver_basis)}",
    f"driver_error={maximum_driver_error:.9g}",
    f"rigid_error={maximum_rigid_error:.9g}",
    f"clear_error={maximum_clear_error:.9g}",
)
