import importlib
from pathlib import Path

import bpy


SOURCE_PMX_KEY = "spx_mmd_ik_source_pmx"
_PATCHES = []


def _modules():
    result = []
    for name in (
        "bl_ext.blender_org.mmd_tools.core.pmx.importer",
        "mmd_tools.core.pmx.importer",
    ):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if all(module.PMXImporter is not existing.PMXImporter for existing in result):
            result.append(module)
    return result


def _wrap(owner):
    current = owner.execute
    if getattr(current, "_spx_mmd_ik_pmx_wrapper", False):
        return current._spx_mmd_ik_original

    def wrapped(self, *args, **kwargs):
        before = set(bpy.data.objects)
        result = current(self, *args, **kwargs)
        filepath = kwargs.get("filepath") or getattr(self, "filepath", "")
        if filepath:
            source = str(Path(filepath).resolve())
            for obj in set(bpy.data.objects) - before:
                if getattr(obj, "mmd_type", "") == "ROOT":
                    obj[SOURCE_PMX_KEY] = source
        return result

    wrapped._spx_mmd_ik_pmx_wrapper = True
    wrapped._spx_mmd_ik_original = current
    owner.execute = wrapped
    return current


def install():
    if _PATCHES:
        return
    for module in _modules():
        owner = module.PMXImporter
        _PATCHES.append((owner, _wrap(owner)))


def uninstall():
    for owner, original in reversed(_PATCHES):
        current = owner.execute
        if getattr(current, "_spx_mmd_ik_pmx_wrapper", False):
            owner.execute = original
    _PATCHES.clear()
