import sys
from pathlib import Path

import bpy
from mathutils import Vector


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
    obj
    for obj in bpy.context.scene.objects
    if getattr(obj, "mmd_type", "") == "ROOT"
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

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = next(
    item for item in runtime.start_preview(bpy.context) if item.root == root
)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)

type_zero_errors = []
view_layer_updates = 0
original_update_view_layer = runtime._update_view_layer
try:
    for _index in range(8):
        session.tick(interactive=True)

    type_zero_indices = [
        index
        for index, mode in enumerate(session.rigid_modes)
        if mode == 0
        and index in session.bone_offsets
        and session.rigid_pose_bones[index] is not None
    ]
    assert type_zero_indices
    delta = Vector((0.025, 0.0, 0.0))

    def count_view_layer_update():
        global view_layer_updates
        view_layer_updates += 1
        return original_update_view_layer()

    runtime._update_view_layer = count_view_layer_update

    for _index in range(8):
        evaluated_before = session.armature.matrix_world.translation.copy()
        root.location += delta
        stale_before_tick = session.armature.matrix_world.translation.copy()
        assert (stale_before_tick - evaluated_before).length < 1.0e-7

        session.tick(interactive=True)
        evaluated_after = session.armature.matrix_world.translation.copy()
        type_zero_errors.append(
            max(
                (
                    (
                        session.armature.matrix_world
                        @ session.rigid_pose_bones[index].matrix
                        @ session.bone_offsets[index]
                    ).translation
                    - session.rigids[index].matrix_world.translation
                ).length
                for index in type_zero_indices
            )
        )
        assert (evaluated_after - evaluated_before - delta).length < 2.0e-6

    assert max(type_zero_errors) < 2.0e-5, max(type_zero_errors)
    assert view_layer_updates == 8, view_layer_updates
finally:
    runtime._update_view_layer = original_update_view_layer
    runtime.stop_preview(root)
    if root.name in evaluator._SESSIONS:
        bpy.ops.surface_proxy.remove_mmd_ik_runtime()

print(
    "MMD_00_IK_MMD_PARENT_EMPTY_LATENCY_OK",
    f"moves={len(type_zero_errors)}",
    f"type0_error={max(type_zero_errors):.9g}",
    f"type0={len(type_zero_indices)}",
    f"view_updates={view_layer_updates}",
)
