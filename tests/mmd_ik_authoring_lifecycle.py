import os
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(r"D:\MMD\模型\Alicia\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx")
VMD = Path(r"D:\MMD\动作\mmd motion\HMVR Teo\m7_teo_0918.vmd")
OUTPUT = Path(os.environ["MMD_IK_AUTHORING_BLEND"])
sys.path.insert(0, str(MMD_TOOLS_PARENT))
sys.path.insert(0, str(REPO))

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator

mmd_skirt_proxy_creator.register()

from mmd_tools.core.model import FnModel
from mmd_tools.core.pmx.importer import PMXImporter
from mmd_tools.core.vmd.importer import VMDImporter
from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import (
    _SESSIONS,
    _depsgraph_update_post,
    is_active,
)
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import runtime_state


PMXImporter().execute(
    filepath=str(PMX),
    types={"MESH", "ARMATURE", "MORPHS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
armature = FnModel.find_armature_object(root)
VMDImporter(filepath=str(VMD), scale=0.08, frame_margin=0).assign(armature)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
bpy.context.scene.frame_set(41)
bpy.context.view_layer.update()

for obj in bpy.context.selected_objects:
    obj.select_set(False)
armature.hide_set(False)
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="POSE")
pose_bone = armature.pose.bones.get("全ての親") or next(iter(armature.pose.bones))
pose_bone_name = pose_bone.name
armature.data.bones.active = pose_bone.bone
pose_bone.bone.select = True

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
assert is_active(root)
session = _SESSIONS[root.name]
original_input = session.input_basis[pose_bone.name].copy()
pose_bone.matrix_basis.translation.x += 0.25
bpy.context.view_layer.update()
_depsgraph_update_post(bpy.context.scene)
edited_input = session.input_basis[pose_bone.name].copy()
assert abs(edited_input.translation.x - original_input.translation.x) > 0.1

assert bpy.ops.surface_proxy.mmd_ik_insert_keyframe(keying_set="LocRotScale") == {"FINISHED"}
assert session.action_input and runtime_state(root)["action_input"]
action = armature.animation_data.action
data_path = f'pose.bones["{pose_bone.name}"].location'
location_curves = [curve for curve in action.fcurves if curve.data_path == data_path]
assert len(location_curves) == 3
for curve in location_curves:
    point = next(
        point
        for point in curve.keyframe_points
        if abs(point.co.x - bpy.context.scene.frame_current) < 1.0e-6
    )
    assert abs(point.co.y - edited_input.translation[curve.array_index]) < 1.0e-5

# Property-diamond/script keying bypasses the I-key operator; the action watcher
# repairs those keys back to the cached input pose on the same depsgraph update.
pose_bone.matrix_basis.translation.z += 0.15
bpy.context.view_layer.update()
_depsgraph_update_post(bpy.context.scene)
property_input = session.input_basis[pose_bone.name].copy()
assert pose_bone.keyframe_insert("location", frame=bpy.context.scene.frame_current)
_depsgraph_update_post(bpy.context.scene)
for curve in location_curves:
    point = next(
        point
        for point in curve.keyframe_points
        if abs(point.co.x - bpy.context.scene.frame_current) < 1.0e-6
    )
    assert abs(point.co.y - property_input.translation[curve.array_index]) < 1.0e-5
edited_input = property_input

bpy.context.scene.frame_set(42)
bpy.context.scene.frame_set(41)
session = _SESSIONS[root.name]
assert session.action_input
assert abs(session.input_basis[pose_bone.name].translation.x - edited_input.translation.x) < 1.0e-5

bpy.ops.ed.undo_push(message="MMD IK authoring baseline")
root_name = root.name
pose_bone.matrix_basis.translation.y += 0.1
bpy.context.view_layer.update()
_depsgraph_update_post(bpy.context.scene)
bpy.ops.ed.undo_push(message="MMD IK authoring edit")
assert bpy.ops.ed.undo() == {"FINISHED"}
from mmd_skirt_proxy_creator.mmd_ik_runtime.lifecycle import _rebuild_timer

_rebuild_timer()
root = bpy.data.objects.get(root_name)
assert root is not None and is_active(root)
assert bpy.ops.ed.redo() == {"FINISHED"}
_rebuild_timer()
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
assert is_active(root)

armature = FnModel.find_armature_object(root)
session = _SESSIONS[root.name]
saved_input = {name: matrix.copy() for name, matrix in session.input_basis.items()}
assert bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), check_existing=False) == {"FINISHED"}
assert OUTPUT.is_file() and is_active(root)
session = _SESSIONS[root.name]
assert all(
    max(
        abs(session.input_basis[name][row][column] - matrix[row][column])
        for row in range(4)
        for column in range(4)
    ) < 1.0e-5
    for name, matrix in saved_input.items()
)
print("MMD_IK_AUTHORING_SAVE_OK", pose_bone_name, OUTPUT)
