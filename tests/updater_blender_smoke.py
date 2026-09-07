"""Blender smoke test for MMD Station updater registration and panel metadata."""

import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mmd_station
from mmd_station import mmd_morph_editor
from mmd_station.updater import addon_updater_ops


was_registered = hasattr(bpy.types, "SPX_PT_surface_proxy_creator")
if not was_registered:
    mmd_station.register()
assert hasattr(bpy.types, "SPX_PT_surface_proxy_creator")
from mmd_station._version import PRERELEASE
expected_version = "v" + ".".join(map(str, mmd_station.bl_info["version"]))
if PRERELEASE:
    expected_version += "-" + PRERELEASE
assert mmd_station._version_text() == expected_version
assert mmd_station.bl_info["doc_url"] == (
    "https://github.com/AliciaSource/MMD-Station")
assert addon_updater_ops.updater.user == "AliciaSource"
assert addon_updater_ops.updater.repo == "MMD-Station"
assert addon_updater_ops.updater.include_branches is False
preferences = bpy.context.preferences.addons["mmd_station"].preferences
assert hasattr(preferences, "morph_ai_api_url")
assert hasattr(preferences, "morph_ai_api_key")
assert hasattr(preferences, "morph_ai_model")
assert not hasattr(bpy.types, "SPX_MorphAIAddonPreferences")
resolved_preferences = mmd_morph_editor._addon_preferences(bpy.context)
assert resolved_preferences is not None
assert resolved_preferences.as_pointer() == preferences.as_pointer()
print("MMD_STATION_UPDATER_SMOKE_OK")
