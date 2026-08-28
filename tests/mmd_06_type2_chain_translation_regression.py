import os
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.physics_preview import runtime

mmd_station.register()


solver_target = os.environ.get("SPX_TEST_SOLVER_TARGET", "PMX")
assert solver_target in {"PMX", "MMD"}
root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_scope = "MODEL"
settings.preview_solver_target = solver_target
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = False

session = runtime.start_preview(bpy.context)[0]
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
try:
    pairs = []
    for bone_name, rigid_index in session.bone_drivers.items():
        if session.rigid_modes[rigid_index] != 2:
            continue
        pose_bone = session.driver_pose_bones[bone_name]
        parent = pose_bone.parent
        if parent is None:
            continue
        parent_index = session.bone_drivers.get(parent.name)
        if parent_index is None or session.rigid_modes[parent_index] != 2:
            continue
        pairs.append((parent, pose_bone))
    assert pairs

    initial_local = {
        child.name: parent.matrix.inverted_safe() @ child.matrix
        for parent, child in pairs
    }
    initial_positions = {
        child.name: child.matrix.translation.copy()
        for _parent, child in pairs
    }

    for _index in range(120):
        session.tick()

    local_errors = []
    displacements = []
    for parent, child in pairs:
        actual_local = parent.matrix.inverted_safe() @ child.matrix
        local_errors.append(
            (actual_local.translation - initial_local[child.name].translation).length
        )
        displacements.append(
            (child.matrix.translation - initial_positions[child.name]).length
        )

    max_local_error = max(local_errors)
    max_displacement = max(displacements)
    assert max_local_error < 2.0e-5, max_local_error
    assert max_displacement > 1.0e-4, max_displacement
finally:
    runtime.stop_preview(root)

print(
    "MMD_06_TYPE2_CHAIN_TRANSLATION_OK",
    f"solver={solver_target}",
    f"pairs={len(pairs)}",
    f"local_error={max_local_error:.9g}",
    f"displacement={max_displacement:.9g}",
)
