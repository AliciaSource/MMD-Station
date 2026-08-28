import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
TARGET = os.environ.get("SPX_TEST_SOLVER", "PMX")
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

if not hasattr(bpy.types.Object, "mmd_type"):
    mmd_tools.register()

import mmd_station
from mmd_station.physics_preview import runtime

if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_station.register()

assert TARGET in {"PMX", "MMD"}
root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = TARGET
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root

session = runtime.start_preview(bpy.context)[0]
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)

try:
    for _index in range(12):
        session.tick(interactive=True)

    type_zero_indices = [
        index
        for index, mode in enumerate(session.rigid_modes)
        if mode == 0
        and index in session.bone_offsets
        and session.rigid_pose_bones[index] is not None
    ]
    assert type_zero_indices
    before = [
        session.rigids[index].matrix_world.translation.copy()
        for index in type_zero_indices
    ]
    input_evaluations = session.pose_input.input_evaluation_count
    delta = Vector((0.02, 0.0, 0.0))

    # Do not pre-evaluate the depsgraph. This matches a timer firing while an
    # Object Mode transform modal has changed raw RNA but not matrix_world yet.
    root.location += delta
    assert session.pose_input.raw_input_changes()[0]
    session.tick(interactive=True)

    errors = []
    for original, index in zip(before, type_zero_indices):
        moved = session.rigids[index].matrix_world.translation
        errors.append(((moved - original) - delta).length)
    assert session.pose_input.input_evaluation_count == input_evaluations + 1
    assert max(errors) < 2.0e-5, max(errors)
finally:
    runtime.stop_preview(root)

print(
    "MMD_04_PARENT_EMPTY_LATENCY_OK",
    f"solver={TARGET}",
    f"type0={len(type_zero_indices)}",
    f"max_error={max(errors):.9g}",
)
