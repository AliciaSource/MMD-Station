import importlib
import re


_ORDER_PREFIX = re.compile(r"^(?P<prefix>[0-9A-Z]{3}_)(?P<name>.*)$")
_SIDE_SUFFIX = re.compile(r"^(?P<name>.*?)[._](?P<side>[LR])$")
_CJK_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_LETTER = re.compile(r"[A-Za-z]")


def normalized_mmd_names(name_j, name_e, blender_name):
    match = _SIDE_SUFFIX.match(blender_name)
    fallback = match.group("name") if match else blender_name
    side = match.group("side") if match else ""
    name_j = str(name_j or fallback).strip()
    name_e = str(name_e or fallback).strip()
    if not side:
        return name_j, name_e

    suffix_j = _SIDE_SUFFIX.match(name_j)
    if suffix_j:
        name_j = suffix_j.group("name")
    if name_j.startswith(("左", "右")):
        name_j = name_j[1:]
    suffix_e = _SIDE_SUFFIX.match(name_e)
    if suffix_e:
        name_e = suffix_e.group("name")
    if name_e.startswith(("左", "右")):
        name_e = name_e[1:]
    return f"{'左' if side == 'L' else '右'}{name_j}", f"{name_e}_{side}"


def bone_mmd_names(pose_bone, blender_name):
    mmd_bone = getattr(pose_bone, "mmd_bone", None)
    return normalized_mmd_names(
        getattr(mmd_bone, "name_j", ""),
        getattr(mmd_bone, "name_e", ""),
        blender_name,
    )


def standardized_bone_mmd_names(pose_bone, blender_name):
    mmd_bone = getattr(pose_bone, "mmd_bone", None)
    current_j = str(getattr(mmd_bone, "name_j", "") or "").strip()
    current_e = str(getattr(mmd_bone, "name_e", "") or "").strip()
    blender_match = _SIDE_SUFFIX.match(blender_name)
    blender_base = blender_match.group("name") if blender_match else blender_name
    side = blender_match.group("side") if blender_match else ""

    preserve_bilingual_bodies = (
        bool(_CJK_CHARACTER.search(current_j))
        and current_e.isascii()
        and bool(_ASCII_LETTER.search(current_e))
    )
    if preserve_bilingual_bodies:
        name_j = current_j[1:] if current_j.startswith(("左", "右")) else current_j
        name_e = current_e[1:] if current_e.startswith(("左", "右")) else current_e
        match_j = _SIDE_SUFFIX.match(name_j)
        match_e = _SIDE_SUFFIX.match(name_e)
        name_j = match_j.group("name") if match_j else name_j
        name_e = match_e.group("name") if match_e else name_e
    else:
        name_j = blender_base
        name_e = blender_base

    if not side:
        return name_j, name_e
    return f"{'左' if side == 'L' else '右'}{name_j}", f"{name_e}_{side}"


def set_ordered_object_name(obj, base_name, joint=False):
    match = _ORDER_PREFIX.match(obj.name)
    prefix = match.group("prefix") if match else ""
    type_prefix = "J." if joint else ""
    obj.name = f"{prefix}{type_prefix}{base_name}"


def normalize_mmd_indices(root, FnModel, kinds=("RIGID", "JOINT")):
    misc_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.operators.misc"
    )
    if "RIGID" in kinds:
        rigids = sorted(FnModel.iterate_rigid_body_objects(root), key=lambda obj: obj.name)
        misc_module.MoveObject.normalize_indices(rigids)
    if "JOINT" in kinds:
        joints = sorted(FnModel.iterate_joint_objects(root), key=lambda obj: obj.name)
        misc_module.MoveObject.normalize_indices(joints)
