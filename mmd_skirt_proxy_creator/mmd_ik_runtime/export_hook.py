import importlib
from contextlib import contextmanager

from .pmx_payload import restore_source_ik_and_bone_morphs
from .runtime import export_restore_runtime, export_switch_to_canonical


_PATCHES = []


def _fileio_modules():
    modules = []
    for name in (
        "bl_ext.blender_org.mmd_tools.operators.fileio",
        "mmd_tools.operators.fileio",
    ):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if all(module.ExportPmx is not item.ExportPmx for item in modules):
            modules.append(module)
    return modules


@contextmanager
def canonical_export(root):
    transaction = export_switch_to_canonical(root)
    try:
        yield
    finally:
        export_restore_runtime(root, transaction)


def _wrap(owner):
    current = owner._do_execute
    if getattr(current, "_spx_mmd_ik_export_wrapper", False):
        return current._spx_mmd_ik_original

    def wrapped(self, context, root):
        with canonical_export(root):
            result = current(self, context, root)
            source_path = root.get("spx_mmd_ik_source_pmx", "")
            if source_path:
                root["spx_mmd_ik_payload_restored"] = restore_source_ik_and_bone_morphs(
                    self.filepath, source_path
                )
            return result

    wrapped._spx_mmd_ik_export_wrapper = True
    wrapped._spx_mmd_ik_original = current
    owner._do_execute = wrapped
    return current


def install():
    if _PATCHES:
        return True
    for module in _fileio_modules():
        owner = module.ExportPmx
        original = _wrap(owner)
        _PATCHES.append((owner, original))
    return bool(_PATCHES)


def uninstall():
    for owner, original in reversed(_PATCHES):
        current = owner._do_execute
        if getattr(current, "_spx_mmd_ik_export_wrapper", False):
            owner._do_execute = original
    _PATCHES.clear()
