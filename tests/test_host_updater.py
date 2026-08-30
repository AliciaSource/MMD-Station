"""Offline tests for MMD Station's host-level updater configuration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "mmd_station" / "updater"
MANAGED_MODULES = (
    "bpy",
    "bpy.app",
    "bpy.app.handlers",
    "addon_utils",
    "mmd_station",
    "mmd_station.updater",
    "mmd_station.updater.addon_updater",
    "mmd_station.updater.addon_updater_ops",
)


class _Deferred:
    pass


def _property(*_args, **_kwargs):
    return _Deferred()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_ops():
    saved = {name: sys.modules.get(name) for name in MANAGED_MODULES}
    try:
        bpy = types.ModuleType("bpy")
        handlers = types.ModuleType("bpy.app.handlers")
        handlers.persistent = lambda function: function
        app = types.ModuleType("bpy.app")
        app.version = (4, 4, 0)
        app.handlers = handlers
        bpy.app = app
        bpy.props = types.SimpleNamespace(
            BoolProperty=_property,
            IntProperty=_property,
            StringProperty=_property,
            EnumProperty=_property,
            _PropertyDeferred=_Deferred,
        )
        bpy.types = types.SimpleNamespace(
            Operator=type("Operator", (), {}),
            AddonPreferences=type("AddonPreferences", (), {}),
            Panel=type("Panel", (), {}),
        )
        bpy.context = types.SimpleNamespace(
            preferences=types.SimpleNamespace(addons={}))
        bpy.utils = types.SimpleNamespace(
            register_class=lambda _class: None,
            unregister_class=lambda _class: None,
        )
        sys.modules["bpy"] = bpy
        sys.modules["bpy.app"] = app
        sys.modules["bpy.app.handlers"] = handlers
        sys.modules["addon_utils"] = types.ModuleType("addon_utils")

        package = types.ModuleType("mmd_station")
        package.__path__ = [str(ROOT / "mmd_station")]
        package.bl_info = {"version": (0, 1, 8)}
        sys.modules["mmd_station"] = package

        updater_package = types.ModuleType("mmd_station.updater")
        updater_package.__path__ = [str(PACKAGE)]
        sys.modules["mmd_station.updater"] = updater_package

        _load(
            "mmd_station.updater.addon_updater",
            PACKAGE / "addon_updater.py",
        )
        return _load(
            "mmd_station.updater.addon_updater_ops",
            PACKAGE / "addon_updater_ops.py",
        )
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


OPS = _load_ops()


def _set_preferences(receive_prereleases):
    preferences = types.SimpleNamespace(
        receive_prereleases=receive_prereleases,
        auto_check_update=True,
        updater_interval_months=0,
        updater_interval_days=1,
        updater_interval_hours=0,
        updater_interval_minutes=0,
    )
    OPS.bpy.context.preferences.addons["mmd_station"] = types.SimpleNamespace(
        preferences=preferences)


def test_updater_targets_alicia_mmd_station_releases():
    OPS.register()
    updater = OPS.updater
    assert updater.addon == "mmd_station"
    assert updater.user == "AliciaSource"
    assert updater.repo == "MMD-Station"
    assert updater.website == "https://github.com/AliciaSource/MMD-Station/releases"
    assert updater.current_version == (0, 1, 8)
    assert updater.include_branches is False
    assert updater.use_releases is True


def test_operator_namespace_is_unique():
    assert OPS.AddonUpdaterInstallPopup.bl_idname == "mmd_station.updater_install_popup"


def test_version_tuple_from_release_title():
    assert OPS.updater.version_tuple_from_text("v0.1.8") == (0, 1, 8)


def test_prerelease_filter_requires_opt_in():
    tag = {"name": "v0.1.9-beta.1", "prerelease": True}
    _set_preferences(False)
    assert OPS.skip_tag_function(OPS.updater, tag) is True
    _set_preferences(True)
    assert OPS.skip_tag_function(OPS.updater, tag) is False


def test_release_asset_selector_requires_zip():
    tag = {
        "assets": [
            {"browser_download_url": "https://example.invalid/notes.txt"},
            {"browser_download_url": "https://example.invalid/mmd_station-0.1.8.zip"},
        ]
    }
    assert OPS.select_link_function(OPS.updater, tag).endswith(
        "mmd_station-0.1.8.zip")
    assert OPS.select_link_function(OPS.updater, {"assets": []}) is None


def test_native_libraries_are_overwritten_during_update():
    OPS.register()
    assert "*.dll" in OPS.updater.overwrite_patterns
