import importlib
import logging
import os
import time


LOGGER = logging.getLogger(__name__)

_EXPORTER_MODULE = "bl_ext.blender_org.mmd_tools.core.pmx.exporter"
_PHASES = (
    ("bones", "Bones", "__exportBones"),
    ("mesh_data", "Mesh data", "__loadMeshData"),
    ("mesh_build", "Vertices, faces, and materials", "__exportMeshes"),
    ("material_sort", "Material sorting", "__sortMaterials"),
    ("vertex_morphs", "Vertex morphs", "__exportVertexMorphs"),
    ("bone_morphs", "Bone morphs", "__export_bone_morphs"),
    ("material_morphs", "Material morphs", "__export_material_morphs"),
    ("uv_morphs", "UV morphs", "__export_uv_morphs"),
    ("group_morphs", "Group morphs", "__export_group_morphs"),
    ("display", "Display frames", "__exportDisplayItems"),
    ("rigid_bodies", "Rigid bodies", "__exportRigidBodies"),
    ("joints", "Joints", "__exportJoints"),
    ("textures", "Texture handling", "__copy_textures"),
)
_MODEL_COLLECTIONS = (
    "vertices",
    "faces",
    "textures",
    "materials",
    "bones",
    "morphs",
    "display",
    "rigids",
    "joints",
)

_last_export_profile = None


def _method_name(exporter_class, suffix):
    return next(
        (name for name in exporter_class.__dict__ if name.endswith(suffix)),
        None,
    )


def _record_model_counts(state, exporter):
    model = getattr(exporter, "_PmxExporter__model", None)
    if model is None:
        return
    state["counts"] = {
        name: len(getattr(model, name, ()))
        for name in _MODEL_COLLECTIONS
    }


def _profile_export_call(original_export, exporter_class, pmx_module, filepath, **kwargs):
    started = time.perf_counter()
    state = {
        "filepath": filepath,
        "success": False,
        "phases": {},
        "counts": {},
    }
    restorations = []

    def patch(target, name, replacement):
        restorations.append((target, name, getattr(target, name)))
        setattr(target, name, replacement)

    original_execute = exporter_class.execute

    def execute_with_counts(self, *args, **call_kwargs):
        try:
            return original_execute(self, *args, **call_kwargs)
        finally:
            _record_model_counts(state, self)

    patch(exporter_class, "execute", execute_with_counts)

    for key, label, suffix in _PHASES:
        name = _method_name(exporter_class, suffix)
        if name is None:
            continue
        original_method = getattr(exporter_class, name)

        def timed_method(self, *args, _key=key, _label=label, _method=original_method, **call_kwargs):
            phase_started = time.perf_counter()
            try:
                return _method(self, *args, **call_kwargs)
            finally:
                phase = state["phases"].setdefault(
                    _key,
                    {"label": _label, "seconds": 0.0, "calls": 0},
                )
                phase["seconds"] += time.perf_counter() - phase_started
                phase["calls"] += 1

        patch(exporter_class, name, timed_method)

    original_save = pmx_module.save

    def timed_save(*args, **call_kwargs):
        phase_started = time.perf_counter()
        try:
            return original_save(*args, **call_kwargs)
        finally:
            state["phases"]["serialization"] = {
                "label": "PMX serialization",
                "seconds": time.perf_counter() - phase_started,
                "calls": 1,
            }

    patch(pmx_module, "save", timed_save)

    try:
        result = original_export(filepath=filepath, **kwargs)
        state["success"] = True
        return result
    finally:
        for target, name, original in reversed(restorations):
            setattr(target, name, original)
        state["total_seconds"] = time.perf_counter() - started
        measured = sum(phase["seconds"] for phase in state["phases"].values())
        state["unmeasured_seconds"] = max(0.0, state["total_seconds"] - measured)
        state["file_size"] = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        global _last_export_profile
        _last_export_profile = state
        _log_profile(state)


def _log_profile(profile):
    total = profile["total_seconds"]
    LOGGER.info(
        "[MMD Station Export Profile] total=%.3fs success=%s size=%d path=%s",
        total,
        profile["success"],
        profile["file_size"],
        profile["filepath"],
    )
    phases = sorted(
        profile["phases"].items(),
        key=lambda item: item[1]["seconds"],
        reverse=True,
    )
    for key, phase in phases:
        percent = phase["seconds"] / total * 100.0 if total else 0.0
        LOGGER.info(
            "[MMD Station Export Profile] phase=%s seconds=%.3f percent=%.1f calls=%d label=%s",
            key,
            phase["seconds"],
            percent,
            phase["calls"],
            phase["label"],
        )
    LOGGER.info(
        "[MMD Station Export Profile] phase=unmeasured seconds=%.3f percent=%.1f",
        profile["unmeasured_seconds"],
        profile["unmeasured_seconds"] / total * 100.0 if total else 0.0,
    )
    if profile["counts"]:
        LOGGER.info(
            "[MMD Station Export Profile] counts=%s",
            ",".join(f"{key}:{value}" for key, value in profile["counts"].items()),
        )


def last_export_profile():
    if _last_export_profile is None:
        return None
    return {
        **_last_export_profile,
        "phases": {
            key: dict(value)
            for key, value in _last_export_profile["phases"].items()
        },
        "counts": dict(_last_export_profile["counts"]),
    }


def register_export_profile_hook():
    try:
        exporter_module = importlib.import_module(_EXPORTER_MODULE)
    except ImportError:
        return False
    current_export = exporter_module.export
    if getattr(current_export, "_mmd_station_profile_original", None) is not None:
        return True
    exporter_class = getattr(exporter_module, "__PmxExporter")
    pmx_module = exporter_module.pmx

    def export_with_profile(filepath, **kwargs):
        return _profile_export_call(
            current_export,
            exporter_class,
            pmx_module,
            filepath,
            **kwargs,
        )

    export_with_profile._mmd_station_profile_original = current_export
    exporter_module.export = export_with_profile
    return True


def unregister_export_profile_hook():
    try:
        exporter_module = importlib.import_module(_EXPORTER_MODULE)
    except ImportError:
        return
    current_export = exporter_module.export
    original_export = getattr(current_export, "_mmd_station_profile_original", None)
    if original_export is not None:
        exporter_module.export = original_export
