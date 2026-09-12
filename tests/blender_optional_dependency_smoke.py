"""Enable the host with valid MMD Tools and absent/broken legacy aliases."""

import importlib.abc
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class UnavailableDependency(importlib.abc.MetaPathFinder):
    error = ModuleNotFoundError

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mmd_tools" or fullname.startswith("mmd_tools."):
            raise self.error("Synthetic incompatible optional dependency")
        return None


finder = UnavailableDependency()
sys.meta_path.insert(0, finder)
for name in list(sys.modules):
    if name == "mmd_tools" or name.startswith("mmd_tools."):
        del sys.modules[name]
import mmd_station

for error in (ModuleNotFoundError, AttributeError):
    finder.error = error
    mmd_station.register()
    assert hasattr(bpy.types.Scene, "surface_proxy_creator")
    mmd_station.unregister()
    assert not hasattr(bpy.types.Scene, "surface_proxy_creator")
sys.meta_path.remove(finder)
print("OPTIONAL_DEPENDENCY_SMOKE_OK")
