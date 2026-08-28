import copy
from pathlib import Path

from .runtime import _import_mmd_module


def restore_source_ik_and_bone_morphs(exported_path, source_path):
    exported_path = Path(exported_path)
    source_path = Path(source_path)
    if not exported_path.is_file() or not source_path.is_file():
        return False
    pmx = _import_mmd_module("core.pmx")
    exported = pmx.load(str(exported_path))
    source = pmx.load(str(source_path))
    exported_indices = {bone.name: index for index, bone in enumerate(exported.bones)}
    source_bones = source.bones
    source_ik = {bone.name: bone for bone in source_bones if bone.isIK}
    for bone in exported.bones:
        source_bone = source_ik.get(bone.name)
        if source_bone is None:
            continue
        target_name = source_bones[source_bone.target].name
        if target_name not in exported_indices:
            continue
        links = []
        valid = True
        for source_link in source_bone.ik_links:
            link_name = source_bones[source_link.target].name
            if link_name not in exported_indices:
                valid = False
                break
            link = copy.copy(source_link)
            link.target = exported_indices[link_name]
            links.append(link)
        if not valid:
            continue
        bone.target = exported_indices[target_name]
        bone.loopCount = source_bone.loopCount
        bone.rotationConstraint = source_bone.rotationConstraint
        bone.ik_links = links

    source_morphs = {
        morph.name: morph for morph in source.morphs if isinstance(morph, pmx.BoneMorph)
    }
    for morph in exported.morphs:
        source_morph = source_morphs.get(morph.name)
        if not isinstance(morph, pmx.BoneMorph) or source_morph is None:
            continue
        offsets = []
        for source_offset in source_morph.offsets:
            bone_name = source_bones[source_offset.index].name
            if bone_name not in exported_indices:
                continue
            offset = pmx.BoneMorphOffset()
            offset.index = exported_indices[bone_name]
            offset.location_offset = source_offset.location_offset
            offset.rotation_offset = source_offset.rotation_offset
            offsets.append(offset)
        morph.offsets = offsets

    add_uv_count = max((len(vertex.additional_uvs) for vertex in exported.vertices), default=0)
    pmx.save(str(exported_path), exported, add_uv_count=add_uv_count)
    return True
