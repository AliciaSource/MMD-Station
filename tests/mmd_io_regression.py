from __future__ import annotations

import importlib
import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _LayoutRecorder:
    def __init__(self, calls):
        self.calls = calls

    def row(self, **_kwargs):
        return _LayoutRecorder(self.calls)

    def column(self, **_kwargs):
        return _LayoutRecorder(self.calls)

    def label(self, **kwargs):
        self.calls.append(("label", kwargs.get("text"), kwargs.get("icon")))

    def operator(self, operator_id, **kwargs):
        self.calls.append(("operator", operator_id, kwargs.get("text")))
        return object()


class _LastProperties:
    def __init__(self, filepath):
        self.filepath = filepath


class _WindowManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.requested_operator = None

    def operator_properties_last(self, operator_id):
        self.requested_operator = operator_id
        return _LastProperties(self.filepath)


class _Context:
    def __init__(self, filepath):
        self.window_manager = _WindowManager(filepath)


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
        from mmd_station import mmd_io

        expected_targets = {
            "mmd_station.import_model": "mmd_tools.import_model",
            "mmd_station.export_pmx": "mmd_tools.export_pmx",
            "mmd_station.import_vmd": "mmd_tools.import_vmd",
            "mmd_station.export_vmd": "mmd_tools.export_vmd",
            "mmd_station.import_vpd": "mmd_tools.import_vpd",
            "mmd_station.export_vpd": "mmd_tools.export_vpd",
        }
        assert {
            cls.bl_idname: cls.target_operator for cls in mmd_io.CLASSES
        } == expected_targets
        assert {
            cls.bl_idname
            for cls in mmd_io.CLASSES
            if cls.reuse_last_filepath
        } == {
            "mmd_station.export_pmx",
            "mmd_station.export_vmd",
            "mmd_station.export_vpd",
        }

        context = _Context("D:/MMD/exports/remembered.pmx")
        export_proxy = mmd_io.MMD_STATION_OT_ExportPMX
        assert export_proxy._target_invoke_kwargs(context) == {
            "filepath": "D:/MMD/exports/remembered.pmx"
        }
        assert context.window_manager.requested_operator == "mmd_tools.export_pmx"
        assert mmd_io.MMD_STATION_OT_ImportModel._target_invoke_kwargs(context) == {}

        empty_context = _Context("")
        assert export_proxy._target_invoke_kwargs(empty_context) == {}

        for operator_id in expected_targets:
            module_name, operator_name = operator_id.split(".", 1)
            operator = getattr(getattr(bpy.ops, module_name), operator_name)
            operator.get_rna_type()

        calls = []
        mmd_io.draw_mmd_io(_LayoutRecorder(calls))
        assert calls == [
            ("label", "模型", "OUTLINER_OB_ARMATURE"),
            ("operator", "mmd_station.import_model", "导入"),
            ("operator", "mmd_station.export_pmx", "导出"),
            ("label", "运动", "ANIM"),
            ("operator", "mmd_station.import_vmd", "导入"),
            ("operator", "mmd_station.export_vmd", "导出"),
            ("label", "姿态", "POSE_HLT"),
            ("operator", "mmd_station.import_vpd", "导入"),
            ("operator", "mmd_station.export_vpd", "导出"),
        ]

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert source.index("draw_mmd_io(layout)") < source.index(
            'tabs.prop(settings, "workspace_tab", expand=True)'
        )
        print("MMD_IO_REGRESSION_OK")
    finally:
        module.unregister()


if __name__ == "__main__":
    main()
