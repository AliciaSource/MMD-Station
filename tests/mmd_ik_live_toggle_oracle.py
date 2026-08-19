import json
import os
import struct
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org")
sys.path.insert(0, str(REPO))

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator

mmd_skirt_proxy_creator.register()

from mmd_tools.core.model import FnModel
from mmd_tools.core.pmx.importer import PMXImporter
from mmd_tools.core.vmd.importer import VMDImporter
from mmd_tools.core import vmd
from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import (
    _SESSIONS,
    _depsgraph_update_post,
    is_active,
    replay_live,
    restore_live_input,
)
from mmd_skirt_proxy_creator.mmd_ik_runtime.coordinates import blender_pose_matrix
from mmd_skirt_proxy_creator.mmd_ik_runtime.ffi import NativeBoneSolver
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import (
    runtime_state,
)
from mmd_skirt_proxy_creator.physics_preview import runtime as physics_runtime


PMX = Path(r"D:\MMD\模型\Alicia\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx")
VMD = Path(r"D:\MMD\动作\mmd motion\HMVR Teo\m7_teo_0918.vmd")
assert PMX.is_file() and VMD.is_file(), (PMX, VMD)
ORACLE = Path(os.environ["MMD_IK_ORACLE"])
assert ORACLE.is_file(), ORACLE
vmd_file = vmd.File()
vmd_file.load(filepath=str(VMD))
ik_frames = sorted(
    {
        key.frame_number
        for name, keys in vmd_file.boneAnimation.items()
        if "足ＩＫ" in name or "足IK" in name
        for key in keys
    }
)
print("FOOT_IK_FRAMES", ik_frames[:40])

PMXImporter().execute(
    filepath=str(PMX),
    types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
armature = FnModel.find_armature_object(root)
VMDImporter(filepath=str(VMD), scale=0.08, frame_margin=0).assign(armature)
assert Path(root["spx_mmd_ik_source_pmx"]).resolve() == PMX.resolve()
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
modifiers = [
    modifier
    for mesh in FnModel.iterate_mesh_objects(root)
    for modifier in mesh.modifiers
    if modifier.type == "ARMATURE"
]
assert modifiers and all(modifier.object == armature for modifier in modifiers)
raw_solver = NativeBoneSolver(PMX, VMD)
raw_indices = {name: index for index, name in enumerate(raw_solver.names)}
knee_names = tuple(name for name in ("左ひざ", "右ひざ") if name in raw_indices and name in armature.pose.bones)
assert knee_names
best = None
for blender_frame in range(1, 182, 5):
    bpy.context.scene.frame_set(blender_frame)
    bpy.context.view_layer.update()
    raw_solver.evaluate(float(blender_frame - 1))
    difference = 0.0
    for name in knee_names:
        bone = armature.pose.bones[name]
        expected = blender_pose_matrix(
            raw_solver.matrix(raw_indices[name]), 0.08, bone.bone.matrix_local
        )
        difference = max(
            difference,
            max(abs(bone.matrix[row][column] - expected[row][column]) for row in range(4) for column in range(4)),
        )
    if best is None or difference > best[0]:
        best = (difference, blender_frame)
assert best is not None and best[0] > 1.0e-6, best
print("KNEE_DIFFERENCE", best)
bpy.context.scene.frame_set(best[1])
bpy.context.view_layer.update()
object_names = set(bpy.data.objects.keys())
collection_names = set(bpy.data.collections.keys())
armature_data_names = set(bpy.data.armatures.keys())
constraint_names = {
    bone.name: tuple((constraint.name, constraint.mute) for constraint in bone.constraints)
    for bone in armature.pose.bones
}
settings.preview_scope = "MODEL"
root.spx_physics_preview_selected = True
physics_runtime.start_preview(bpy.context)
assert physics_runtime.is_running(root)
before_knees = {name: armature.pose.bones[name].matrix.copy() for name in knee_names}
before_basis = {name: armature.pose.bones[name].matrix_basis.copy() for name in knee_names}

result = bpy.ops.surface_proxy.create_mmd_ik_runtime()
print("ENABLE", result)
state = runtime_state(root)
assert result == {"FINISHED"} and is_active(root)
assert state["schema"] == 2 and state["binding_mode"] == "MEMORY_ONLY"
assert physics_runtime.is_running(root)
assert physics_runtime._ACTIVE_SESSIONS[root.name].armature == armature
assert all(modifier.object == armature for modifier in modifiers)
assert set(bpy.data.objects.keys()) == object_names
assert set(bpy.data.collections.keys()) == collection_names
assert set(bpy.data.armatures.keys()) == armature_data_names
assert {
    bone.name: tuple(constraint.name for constraint in bone.constraints)
    for bone in armature.pose.bones
} == {
    bone_name: tuple(name for name, _mute in constraints)
    for bone_name, constraints in constraint_names.items()
}
session = _SESSIONS[root.name]
assert session.runtime_name == armature.name == session.canonical_name
for name in knee_names:
    print("KNEE_MAPPING", name, [(i, session.solver.names[i]) for i, bone in enumerate(session.mapping) if bone.name == name])
raw_solver.evaluate(float(best[1] - 1))
live_matches = {}
for name in knee_names:
    index = session.bone_indices[name]
    live_matrix = session.solver.matrix(index)
    raw_matrix = raw_solver.matrix(raw_indices[name])
    live_matches[name] = struct.pack("<16f", *session.solver.matrix(index)) == struct.pack(
        "<16f", *raw_solver.matrix(raw_indices[name])
    )
    print("LIVE_RAW_KNEE_MAX", name, max(abs(a - b) for a, b in zip(live_matrix, raw_matrix)))
print("LIVE_RAW_KNEE_BITS", live_matches)
record = next(
    json.loads(line)
    for line in ORACLE.read_text(encoding="utf-8").splitlines()
    if json.loads(line)["frame"] == best[1] - 1
)
oracle_bones = record["objects"][0][1]
native_exact = sum(
    name == session.solver.names[index]
    and bytes.fromhex(raw) == struct.pack("<16f", *session.solver.matrix(index))
    for index, (name, raw) in enumerate(oracle_bones)
)
assert native_exact == len(oracle_bones) == session.solver.count
print("MMD_IK_ON_ORACLE_BITS", f"{native_exact}/{len(oracle_bones)}")
physics_runtime.stop_preview(root)
for name in knee_names:
    bone = armature.pose.bones[name]
    expected = blender_pose_matrix(
        raw_solver.matrix(raw_indices[name]), 0.08, bone.bone.matrix_local
    )
    print(
        "VISIBLE_KNEE_MAX",
        name,
        max(abs(bone.matrix[row][column] - expected[row][column]) for row in range(4) for column in range(4)),
    )
    assert max(
        abs(bone.matrix[row][column] - expected[row][column])
        for row in range(4)
        for column in range(4)
    ) < 5.0e-6
    assert max(
        abs(bone.matrix[row][column] - before_knees[name][row][column])
        for row in range(4)
        for column in range(4)
    ) > 1.0e-6

pose_bone = armature.pose.bones.get("全ての親") or next(iter(armature.pose.bones))
for name in knee_names:
    print(
        "MMD_IK_CACHED_INPUT_BASIS_MAX",
        name,
        max(abs(session.input_basis[name][row][column] - before_basis[name][row][column]) for row in range(4) for column in range(4)),
    )
before = pose_bone.matrix.copy()
saved_input = {name: matrix.copy() for name, matrix in session.input_basis.items()}
pose_bone.matrix_basis.translation.x += 0.25
bpy.context.view_layer.update()
_depsgraph_update_post(bpy.context.scene)
after = pose_bone.matrix.copy()
assert before != after
restore_live_input(root, saved_input)
replay_live(root)

result = bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print("DISABLE", result)
assert result == {"FINISHED"} and not is_active(root) and runtime_state(root) is None
assert all(modifier.object == armature for modifier in modifiers)
assert set(bpy.data.objects.keys()) == object_names
assert set(bpy.data.collections.keys()) == collection_names
assert set(bpy.data.armatures.keys()) == armature_data_names
assert {
    bone.name: tuple((constraint.name, constraint.mute) for constraint in bone.constraints)
    for bone in armature.pose.bones
} == constraint_names
for name in knee_names:
    bone = armature.pose.bones[name]
    print(
        "MMD_IK_OFF_BASIS_MAX",
        name,
        max(abs(bone.matrix_basis[row][column] - before_basis[name][row][column]) for row in range(4) for column in range(4)),
    )
    restored_max = max(
        abs(bone.matrix[row][column] - before_knees[name][row][column])
        for row in range(4)
        for column in range(4)
    )
    print("MMD_IK_OFF_KNEE_MAX", name, restored_max)
    assert restored_max < 1.0e-5
print("MMD_IK_OFF_RESTORED", f"knees={len(knee_names)}", f"native_difference={best[0]:.9f}")
print("MMD_IK_MEMORY_ONLY_ORACLE_OK", len(armature.pose.bones), pose_bone.name)
