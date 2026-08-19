import json
import os
import struct
import sys
import tempfile
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(
    "D:/MMD/\u6a21\u578b/Alicia/Endfield-Laevatain/"
    "Endfield-LaevatainVer1.04_By_Alicia/LaevatainVer1.04_ALL.pmx"
)
VMD = Path("D:/MMD/\u52a8\u4f5c/mmd motion/HMVR Teo/m7_teo_0918.vmd")
sys.path.insert(0, str(MMD_TOOLS_PARENT))
sys.path.insert(0, str(REPO))

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime.coordinates import blender_pose_matrix
from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import _SESSIONS, is_active
from mmd_skirt_proxy_creator.mmd_ik_runtime.export_hook import canonical_export
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import (
    MMDIKRuntimeError,
    OUTPUT_CONSTRAINT_NAME,
    STATE_KEY,
    canonical_armature,
    refresh_bindings,
    runtime_state,
    select_armature,
)
from mmd_skirt_proxy_creator.mmd_ik_runtime.ui import _validate_action_vmd
from mmd_skirt_proxy_creator.physics_preview import runtime as physics_runtime
from mmd_tools.core.model import FnModel
from mmd_tools.core.pmx.importer import PMXImporter
from mmd_tools.core.vmd.importer import VMDImporter
from mmd_tools.core import pmx

mmd_skirt_proxy_creator.register()


def bone_morph_snapshot(root):
    result = []
    for morph in root.mmd_root.bone_morphs:
        offsets = []
        for data in morph.data:
            offsets.append(
                {
                    "bone": data.bone,
                    "location": [float(value) for value in data.location],
                    "rotation": [float(value) for value in data.rotation],
                }
            )
        result.append({"name": morph.name, "name_e": morph.name_e, "category": morph.category, "data": offsets})
    return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def float_bits(values):
    return struct.pack(f"<{len(values)}f", *values).hex()


def pmx_ik_morph_snapshot(path):
    model = pmx.load(str(path))
    bones = model.bones
    ik = {}
    for bone in bones:
        if not bone.isIK:
            continue
        links = []
        for link in bone.ik_links:
            links.append(
                {
                    "bone": bones[link.target].name,
                    "minimum": None if link.minimumAngle is None else float_bits(link.minimumAngle),
                    "maximum": None if link.maximumAngle is None else float_bits(link.maximumAngle),
                }
            )
        ik[bone.name] = {
            "target": bones[bone.target].name,
            "loop_count": bone.loopCount,
            "rotation_constraint": float_bits([bone.rotationConstraint]),
            "links": links,
        }
    bone_morphs = {}
    for morph in model.morphs:
        if not isinstance(morph, pmx.BoneMorph):
            continue
        bone_morphs[morph.name] = [
            {
                "bone": bones[offset.index].name,
                "location": float_bits(offset.location_offset),
                "rotation": float_bits(offset.rotation_offset),
            }
            for offset in morph.offsets
        ]
    return {"ik": ik, "bone_morphs": bone_morphs}


PMXImporter().execute(
    filepath=str(PMX),
    types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
canonical = FnModel.find_armature_object(root)
meshes = list(FnModel.iterate_mesh_objects(root))
assert canonical is not None and meshes
settings = bpy.context.scene.surface_proxy_creator
solver_target = os.environ.get("SPX_TEST_SOLVER_TARGET", "MMD")
assert solver_target in {"MMD", "PMX"}
settings.preview_solver_target = solver_target
settings.mmd_ik_root = root
assert settings.mmd_ik_armature == canonical

# mmd_tools converts quaternion interpolation to Blender Nlerp, so the exact
# evaluator follows the original VMD bytes recorded on the imported Action.
VMDImporter(filepath=str(VMD), scale=0.08, frame_margin=0).assign(canonical)
imported_action = canonical.animation_data.action
assert Path(imported_action["spx_mmd_ik_source_vmd"]) == VMD.resolve()
settings.mmd_ik_action = imported_action
assert Path(settings.mmd_ik_vmd_path) == VMD.resolve()
assert settings.mmd_ik_start_frame == 1
with tempfile.TemporaryDirectory(prefix="mmd-ik-vmd-hash-") as directory:
    changed_vmd = Path(directory) / VMD.name
    changed_vmd.write_bytes(VMD.read_bytes() + b"changed")
    original_source = imported_action["spx_mmd_ik_source_vmd"]
    imported_action["spx_mmd_ik_source_vmd"] = str(changed_vmd)
    try:
        try:
            _validate_action_vmd(imported_action, changed_vmd)
        except MMDIKRuntimeError:
            pass
        else:
            raise AssertionError("modified Action source VMD was accepted")
    finally:
        imported_action["spx_mmd_ik_source_vmd"] = original_source

# Simulate a model that was split by material before runtime creation.
for index in range(2):
    duplicate = meshes[0].copy()
    duplicate.data = meshes[0].data
    duplicate.name = f"MMDIKMaterialSplit{index}"
    duplicate.parent = meshes[0].parent
    meshes[0].users_collection[0].objects.link(duplicate)

meshes = list(FnModel.iterate_mesh_objects(root))
expected_modifiers = [
    modifier
    for mesh in meshes
    for modifier in mesh.modifiers
    if modifier.type == "ARMATURE" and modifier.object == canonical
]
assert expected_modifiers
morph_before = bone_morph_snapshot(root)

object_names = set(bpy.data.objects.keys())
collection_names = set(bpy.data.collections.keys())
armature_data_names = set(bpy.data.armatures.keys())
constraint_names = {
    bone.name: tuple(constraint.name for constraint in bone.constraints)
    for bone in canonical.pose.bones
}

# A schema-1 file is migrated in-place before the memory-only session starts.
legacy = canonical.copy()
legacy.data = canonical.data.copy()
legacy.name = "MMDIKLegacyRuntime"
canonical.users_collection[0].objects.link(legacy)
legacy_bone = next(iter(canonical.pose.bones))
legacy_constraint = legacy_bone.constraints.new("COPY_TRANSFORMS")
legacy_constraint.name = OUTPUT_CONSTRAINT_NAME
legacy_constraint.target = legacy
legacy_constraint.subtarget = legacy_bone.name
expected_modifiers[0].object = legacy
root[STATE_KEY] = json.dumps(
    {
        "schema": 1,
        "canonical_armature": canonical.name,
        "runtime_armature": legacy.name,
        "enabled": True,
        "muted_constraints": [],
    }
)

result = bpy.ops.surface_proxy.create_mmd_ik_runtime()
assert result == {"FINISHED"}
state = runtime_state(root)
assert state["schema"] == 2 and state["binding_mode"] == "MEMORY_ONLY"
assert is_active(root)
assert set(bpy.data.objects.keys()) == object_names
assert set(bpy.data.collections.keys()) == collection_names
assert set(bpy.data.armatures.keys()) == armature_data_names
assert all(modifier.object == canonical for modifier in expected_modifiers)
assert bone_morph_snapshot(root) == morph_before
assert settings.mmd_ik_armature == canonical
assert {
    bone.name: tuple(constraint.name for constraint in bone.constraints)
    for bone in canonical.pose.bones
} == constraint_names

try:
    select_armature(root, bpy.data.objects.new("MMDIKInvalidArmature", bpy.data.armatures.new("MMDIKInvalidData")))
except MMDIKRuntimeError:
    pass
else:
    raise AssertionError("non-canonical armature was accepted")
bpy.data.objects.remove(bpy.data.objects["MMDIKInvalidArmature"], do_unlink=True)
bpy.data.armatures.remove(bpy.data.armatures["MMDIKInvalidData"])

# Material separation after activation keeps the original armature binding.
late_mesh = meshes[0].copy()
late_mesh.data = meshes[0].data
late_mesh.name = "MMDIKLateMaterialSplit"
late_mesh.parent = meshes[0].parent
meshes[0].users_collection[0].objects.link(late_mesh)
late_modifier = next(modifier for modifier in late_mesh.modifiers if modifier.type == "ARMATURE")
late_modifier.object = canonical
assert refresh_bindings(root) == len(list(FnModel.iterate_mesh_objects(root)))
assert late_modifier.object == canonical

session = _SESSIONS[root.name]
assert session.live and session.runtime_name == canonical.name == session.canonical_name
assert session.solver.count == 621
scene = bpy.context.scene
scene.frame_set(2)
print("MMD_IK_FRAME_TWO", session.last_vmd_frame)
assert session.last_vmd_frame == 1
scene.frame_set(2)
assert session.last_vmd_frame == 1
scene.frame_set(1)
assert session.last_vmd_frame == 0
sample_index = next(index for index, bone in enumerate(session.mapping) if bone is not None)
sample_bone = session.mapping[sample_index]
expected = blender_pose_matrix(
    session.solver.matrix(sample_index), session.scale, sample_bone.bone.matrix_local
)
assert max(
    abs(sample_bone.matrix[row][column] - expected[row][column])
    for row in range(4)
    for column in range(4)
) < 1.0e-5

assert physics_runtime._model_armature(root) == canonical
settings.preview_scope = "MODEL"
for candidate in (obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT"):
    candidate.spx_physics_preview_selected = candidate == root
preview_session = physics_runtime.start_preview(bpy.context)[0]
assert preview_session.armature == canonical
preview_session.prepare_step()
assert preview_session.step_solver()
preview_session.apply_step()
assert session.external_transforms
physics_runtime.stop_preview(root)
assert not session.external_transforms
assert is_active(root)

# Export sees canonical bindings, while success and failure both restore runtime.
with canonical_export(root):
    assert all(
        modifier.object == canonical
        for mesh in FnModel.iterate_mesh_objects(root)
        for modifier in mesh.modifiers
        if modifier.type == "ARMATURE"
    )
assert late_modifier.object == canonical

try:
    with canonical_export(root):
        assert late_modifier.object == canonical
        raise RuntimeError("synthetic export failure")
except RuntimeError:
    pass
assert late_modifier.object == canonical
assert bone_morph_snapshot(root) == morph_before

# The ordinary mmd_tools UI export is wrapped transactionally and must leave
# the live runtime bindings untouched. PMX IK and Bone Morph payloads must
# round-trip without any runtime-specific changes.
for obj in bpy.context.selected_objects:
    obj.select_set(False)
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
with tempfile.TemporaryDirectory(prefix="mmd-ik-runtime-") as directory:
    exported = Path(directory) / "runtime_roundtrip.pmx"
    result = bpy.ops.mmd_tools.export_pmx(
        filepath=str(exported),
        scale=12.5,
        copy_textures_mode="NONE",
        fix_bone_order=False,
        sort_materials=False,
        sort_vertices="NONE",
    )
    assert result == {"FINISHED"} and exported.exists()
    exported_snapshot = pmx_ik_morph_snapshot(exported)
    source_snapshot = pmx_ik_morph_snapshot(PMX)
    if exported_snapshot != source_snapshot:
        for section in ("ik", "bone_morphs"):
            for name in sorted(set(exported_snapshot[section]) | set(source_snapshot[section])):
                if exported_snapshot[section].get(name) != source_snapshot[section].get(name):
                    print("MMD_IK_EXPORT_DIFF", section, name)
                    print("exported", exported_snapshot[section].get(name))
                    print("source", source_snapshot[section].get(name))
                    break
    assert exported_snapshot == source_snapshot
assert late_modifier.object == canonical
assert bone_morph_snapshot(root) == morph_before

settings.mmd_ik_armature = canonical
assert all(
    modifier.object == canonical
    for mesh in FnModel.iterate_mesh_objects(root)
    for modifier in mesh.modifiers
    if modifier.type == "ARMATURE"
)
assert bone_morph_snapshot(root) == morph_before

result = bpy.ops.surface_proxy.remove_mmd_ik_runtime()
assert result == {"FINISHED"}
assert runtime_state(root) is None
assert set(bpy.data.objects.keys()) == object_names | {late_mesh.name}
assert set(bpy.data.collections.keys()) == collection_names
assert set(bpy.data.armatures.keys()) == armature_data_names
assert settings.mmd_ik_armature == canonical
assert bone_morph_snapshot(root) == morph_before

print(
    "MMD_IK_RUNTIME_SMOKE_OK",
    f"solver={solver_target}",
    f"meshes={len(meshes) + 1}",
    f"modifiers={len(expected_modifiers) + 1}",
    f"bone_morphs={len(root.mmd_root.bone_morphs)}",
)
