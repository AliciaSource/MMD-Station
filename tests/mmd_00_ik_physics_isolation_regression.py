import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
from mmd_station.physics_preview import runtime


if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_station.register()

root = next(
    obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", "") == "ROOT"
)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.mmd_ik_root = root
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
root.spx_physics_preview_selected = True
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root

preview = next(item for item in runtime.start_preview(bpy.context) if item.root == root)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)

world = preview.world
solver = preview.solver
generation = world.generation
for _index in range(4):
    preview.tick(interactive=True)

assert not hasattr(preview, "runtime_adapter")
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
native_session = evaluator._SESSIONS[root.name]
assert runtime._ACTIVE_SESSIONS[root.name] is preview
assert preview.world is world
assert preview.solver is solver
assert world.generation == generation
assert not hasattr(preview, "runtime_adapter")
assert not hasattr(native_session, "physics_feedback_complete")
assert not hasattr(native_session, "physics_rigid_indices")

for _index in range(4):
    preview.tick(interactive=True)

assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}
assert runtime._ACTIVE_SESSIONS[root.name] is preview
assert preview.world is world
assert preview.solver is solver
assert world.generation == generation
assert not hasattr(preview, "runtime_adapter")
assert preview.consecutive_tick_failures == 0

runtime.stop_preview(root)
print(
    "MMD_00_IK_PHYSICS_ISOLATION_OK",
    f"generation={generation}",
    f"drivers={len(preview.driver_pose_bones)}",
)
