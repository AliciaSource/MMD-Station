import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(
    r"D:\MMD\MEGA\_Alicia模型\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.physics_preview import runtime as physics_runtime
from mmd_tools.core.pmx.importer import PMXImporter

mmd_skirt_proxy_creator.register()


PMXImporter().execute(
    filepath=str(PMX),
    types={"ARMATURE", "PHYSICS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
root["spx_mmd_ik_source_pmx"] = str(PMX)
for obj in bpy.context.selected_objects:
    obj.select_set(False)
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root

settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = "PMX"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = False
settings.mmd_ik_root = root
root.spx_physics_preview_selected = True

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = physics_runtime.start_preview(bpy.context)[0]
for _index in range(4):
    session.prepare_step()
    assert session.step_solver()
    session.apply_step(*session.world.outputs())

assert session.auto_reset_count == 0, session.settings.preview_status
physics_runtime.stop_preview(root)
assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}
print("MMD_IK_PHYSICS_RESET_REGRESSION_OK")
