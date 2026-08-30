"""Blender smoke test for MMD Station updater registration and panel metadata."""

import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mmd_station
from mmd_station.updater import addon_updater_ops


was_registered = hasattr(bpy.types, "SPX_PT_surface_proxy_creator")
if not was_registered:
    mmd_station.register()
assert hasattr(bpy.types, "SPX_PT_surface_proxy_creator")
assert mmd_station._version_text() == "v0.1.8-dev"
assert mmd_station.bl_info["doc_url"] == (
    "https://github.com/AliciaSource/MMD-Station")
assert addon_updater_ops.updater.user == "AliciaSource"
assert addon_updater_ops.updater.repo == "MMD-Station"
assert addon_updater_ops.updater.include_branches is False
print("MMD_STATION_UPDATER_SMOKE_OK")
