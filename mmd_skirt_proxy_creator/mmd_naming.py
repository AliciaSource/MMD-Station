import importlib
import re


_ORDER_PREFIX = re.compile(r"^(?P<prefix>[0-9A-Z]{3}_)(?P<name>.*)$")
_SIDE_SUFFIX = re.compile(r"^(?P<name>.*?)[._](?P<side>[LR])$")


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
