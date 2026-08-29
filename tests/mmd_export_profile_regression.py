from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _FakeModel:
    def __init__(self):
        self.vertices = [1, 2, 3]
        self.faces = [1]
        self.textures = []
        self.materials = [1]
        self.bones = [1, 2]
        self.morphs = []
        self.display = [1, 2]
        self.rigids = [1]
        self.joints = [1]


class _FakeExporter:
    def __exportBones(self):
        return "bones"

    def __loadMeshData(self):
        return "mesh"

    def __exportRigidBodies(self):
        return "rigids"

    def __exportJoints(self):
        return "joints"

    def execute(self, filepath):
        self._PmxExporter__model = _FakeModel()
        self.__exportBones()
        self.__loadMeshData()
        self.__exportRigidBodies()
        self.__exportJoints()
        _FAKE_PMX.save(filepath, self._PmxExporter__model)


def _save(filepath, _model):
    Path(filepath).write_bytes(b"PMX")


_FAKE_PMX = SimpleNamespace(save=_save)


def _export(filepath, **_kwargs):
    _FakeExporter().execute(filepath)
    return "done"


def _reload_addon():
    existing = sys.modules.get("mmd_station")
    if existing is not None:
        try:
            existing.unregister()
        except Exception:
            pass
    for name in list(sys.modules):
        if name == "mmd_station" or name.startswith("mmd_station."):
            del sys.modules[name]
    module = importlib.import_module("mmd_station")
    module.register()
    return module


def main():
    module = _reload_addon()
    try:
        from mmd_station import mmd_export_profile

        with tempfile.TemporaryDirectory() as directory:
            filepath = str(Path(directory) / "profile.pmx")
            result = mmd_export_profile._profile_export_call(
                _export,
                _FakeExporter,
                _FAKE_PMX,
                filepath,
            )
            assert result == "done"
            profile = mmd_export_profile.last_export_profile()
            assert profile["success"] is True
            assert profile["file_size"] == 3
            assert profile["counts"]["vertices"] == 3
            assert profile["counts"]["rigids"] == 1
            assert profile["counts"]["joints"] == 1
            assert set(profile["phases"]) == {
                "bones",
                "mesh_data",
                "rigid_bodies",
                "joints",
                "serialization",
            }
            assert all(phase["calls"] == 1 for phase in profile["phases"].values())

        exporter_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.pmx.exporter"
        )
        assert getattr(
            exporter_module.export,
            "_mmd_station_profile_original",
            None,
        ) is not None
        print("MMD_EXPORT_PROFILE_REGRESSION_OK")
    finally:
        module.unregister()


if __name__ == "__main__":
    main()
