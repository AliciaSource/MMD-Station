import hashlib
import importlib
from pathlib import Path

import bpy


SOURCE_VMD_KEY = "spx_mmd_ik_source_vmd"
SOURCE_SHA256_KEY = "spx_mmd_ik_source_vmd_sha256"
SOURCE_FRAME_KEY = "spx_mmd_ik_source_vmd_frame"
_PATCHES = []


def _modules():
    result = []
    for name in (
        "bl_ext.blender_org.mmd_tools.core.vmd.importer",
        "mmd_tools.core.vmd.importer",
    ):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if all(module.VMDImporter is not existing.VMDImporter for existing in result):
            result.append(module)
    return result


def _stamp(action, filepath, frame_start):
    if action is None:
        return
    path = Path(filepath).resolve()
    action[SOURCE_VMD_KEY] = str(path)
    action[SOURCE_SHA256_KEY] = hashlib.sha256(path.read_bytes()).hexdigest()
    action[SOURCE_FRAME_KEY] = int(frame_start)


def _wrap(owner):
    current = owner.assign
    if getattr(current, "_spx_mmd_ik_vmd_wrapper", False):
        return current._spx_mmd_ik_original

    def wrapped(self, obj, action_name=None):
        before = set(bpy.data.actions)
        result = current(self, obj, action_name)
        vmd_file = getattr(self, "_VMDImporter__vmdFile")
        frame_start = int(getattr(self, "_VMDImporter__frame_start", 0)) + int(
            getattr(self, "_VMDImporter__frame_margin", 0)
        )
        for action in set(bpy.data.actions) - before:
            _stamp(action, vmd_file.filepath, frame_start)
        animation_data = getattr(obj, "animation_data", None)
        if animation_data is not None:
            _stamp(animation_data.action, vmd_file.filepath, frame_start)
        shape_keys = getattr(getattr(obj, "data", None), "shape_keys", None)
        if shape_keys is not None and shape_keys.animation_data is not None:
            _stamp(shape_keys.animation_data.action, vmd_file.filepath, frame_start)
        return result

    wrapped._spx_mmd_ik_vmd_wrapper = True
    wrapped._spx_mmd_ik_original = current
    owner.assign = wrapped
    return current


def install():
    if _PATCHES:
        return
    for module in _modules():
        owner = module.VMDImporter
        _PATCHES.append((owner, _wrap(owner)))


def uninstall():
    for owner, original in reversed(_PATCHES):
        current = owner.assign
        if getattr(current, "_spx_mmd_ik_vmd_wrapper", False):
            owner.assign = original
    _PATCHES.clear()
