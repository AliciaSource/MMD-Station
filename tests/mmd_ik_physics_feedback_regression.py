import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u9e23\u6f6e_\u8fbe\u59ae\u5a051.2\uff08blue ver\uff09"
PMX_NAME = "\u9e23\u6f6e_\u8fbe\u59ae\u5a051.2\uff08blue ver\uff09.pmx"
IK_NAME = "\u8db3\uff29\uff2b.L"
CHAIN_NAMES = ("\u8db3.L", "\u3072\u3056.L", "\u8db3\u9996.L")

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
from mmd_station.physics_preview import runtime

if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
root["spx_mmd_ik_source_pmx"] = str(Path(root["import_folder"]) / PMX_NAME)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
root.spx_physics_preview_selected = True

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = evaluator._SESSIONS[root.name]
armature = runtime._model_armature(root)
assert not hasattr(evaluator, "submit_physics_feedback")
assert not hasattr(evaluator, "prepare_physics_targets")

results = []
for solver_target in ("PMX", "MMD"):
    settings.preview_solver_target = solver_target
    preview = next(item for item in runtime.start_preview(bpy.context) if item.root == root)
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    world = preview.world
    solver = preview.solver
    generation = world.generation
    for _index in range(4):
        preview.tick(interactive=True)

    ik_bone = armature.pose.bones[IK_NAME]
    chain_before = {
        name: armature.pose.bones[name].matrix.copy() for name in CHAIN_NAMES
    }
    ik_bone.matrix_basis = ik_bone.matrix_basis @ Matrix.Translation((0.015, 0.0, 0.0))
    armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    chain_change = max(
        (
            armature.pose.bones[name].matrix.translation
            - chain_before[name].translation
        ).length
        for name in CHAIN_NAMES
    )
    assert chain_change > 1.0e-4, (solver_target, chain_change)

    for _index in range(6):
        preview.tick(interactive=True)
    assert preview.world is world
    assert preview.solver is solver
    assert world.generation == generation
    assert not hasattr(preview, "runtime_adapter")
    assert preview.consecutive_tick_failures == 0
    results.append((solver_target, chain_change))
    runtime.stop_preview(root)

bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print(
    "MMD_IK_PHYSICS_ISOLATION_REGRESSION_OK",
    " ".join(f"{target}={change:.9g}" for target, change in results),
)
