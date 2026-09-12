"""Run one regression in an isolated Blender process and extension profile."""

import importlib
import os
from pathlib import Path
import runpy
import sys

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
test_path = Path(os.environ["MMD_TEST_SCRIPT"]).resolve()
extension_root = Path(os.environ["MMD_TEST_EXTENSIONS"]).resolve()
repos = bpy.context.preferences.extensions.repos
repo = next((item for item in repos if item.module == "blender_org"), None)
if repo is None:
    repo = repos.new(name="Test MMD Tools", module="blender_org",
                     custom_directory=str(extension_root))
else:
    repo.use_custom_directory = True
    repo.custom_directory = str(extension_root)
bpy.context.preferences.view.language = "zh_HANS"
addon_utils.modules_refresh()
dependency = addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=False)
assert dependency is not None, "MMD Tools could not be enabled"

# Older regressions use the legacy package spelling. Both names must resolve
# to the same dependency classes, not two separately registered add-ons.
for name, module in list(sys.modules.items()):
    if name == "bl_ext.blender_org.mmd_tools" or name.startswith("bl_ext.blender_org.mmd_tools."):
        sys.modules[name.removeprefix("bl_ext.blender_org.")] = module
source = test_path.read_text(encoding="utf-8-sig")
if os.environ.get("MMD_TEST_ADDON_ROOT"):
    sys.path.insert(0, os.environ["MMD_TEST_ADDON_ROOT"])
    importlib.import_module("mmd_station")
if "mmd_tools.register()" in source:
    addon_utils.disable("bl_ext.blender_org.mmd_tools", default_set=False)
if "mmd_station" not in bpy.context.preferences.addons:
    bpy.context.preferences.addons.new().module = "mmd_station"
print("MATRIX_ENV", bpy.app.version_string, dependency.__file__, flush=True)
if os.environ.get("MMD_TEST_ENABLE_ADDON") == "1":
    assert addon_utils.enable("mmd_station", default_set=False)
if os.environ.get("MMD_TEST_BLEND"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MMD_TEST_BLEND"])
    from mmd_station.physics_preview import cache
    cache._cache_directory = lambda blend_path=None: Path(os.environ["TEMP"]) / "physics-cache"
runpy.run_path(str(test_path), run_name="__main__")
print("MATRIX_CASE_OK", test_path.name, flush=True)
