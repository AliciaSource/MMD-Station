import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mmd_station


SOURCE_TITLE = "MMD \u6a21\u578b\u5236\u4f5c\u5de5\u5177"
SOURCE_DESCRIPTION = "\u4ece\u52fe\u9009\u9aa8\u9abc\u6062\u590d\u6216\u65b0\u5efa\u4ee3\u7406"
SOURCE_DYNAMIC = "\u5df2\u6dfb\u52a0 3 \u4e2a\u6750\u8d28\u8be6\u60c5\u9879"


mmd_station.i18n.register()
original_locale = bpy.context.preferences.view.language
try:
    expected = {
        "zh_HANS": (
            SOURCE_TITLE,
            SOURCE_DESCRIPTION,
            SOURCE_DYNAMIC,
        ),
        "zh_HANT": (
            SOURCE_TITLE,
            SOURCE_DESCRIPTION,
            SOURCE_DYNAMIC,
        ),
        "en_US": (
            "MMD Model Authoring Toolkit",
            "Restore or Create Proxy from Checked Bones",
            "added 3 material detail items",
        ),
        "ja_JP": (
            "MMD Model Authoring Toolkit",
            "Restore or Create Proxy from Checked Bones",
            "added 3 material detail items",
        ),
    }
    for locale, values in expected.items():
        bpy.context.preferences.view.language = locale
        actual = (
            bpy.app.translations.pgettext_iface(SOURCE_TITLE),
            bpy.app.translations.pgettext_tip(SOURCE_DESCRIPTION),
            mmd_station.i18n.iface(SOURCE_DYNAMIC),
        )
        assert actual == values, (locale, actual, values)
        operator_text = bpy.app.translations.pgettext_iface(
            SOURCE_DESCRIPTION,
            bpy.app.translations.contexts.operator_default,
        )
        assert operator_text == values[1], (locale, operator_text, values[1])
finally:
    bpy.context.preferences.view.language = original_locale
    mmd_station.i18n.unregister()

print("MMD_STATION_I18N_BLENDER_SMOKE_OK")
