"""MMD Station host-level auto-updater wiring.

This package vendors the GPL ``addon_updater`` fork used by Velo Tools and
configures it to update the complete ``mmd_station`` add-on from published
``AliciaSource/MMD-Station`` GitHub Releases.
"""

import bpy

from . import addon_updater_ops
from . import notify


class MMD_STATION_AddonUpdaterPreferences(bpy.types.AddonPreferences):
    """Add-on preferences containing update notification settings."""

    bl_idname = "mmd_station"

    auto_update_notify: bpy.props.BoolProperty(
        name="自动接收更新通知",
        description=("启用后，打开 MMD Station 面板时会按下方间隔自动检查更新，"
                     "检测到新版本就在面板顶部显示提示"),
        default=True,
    )  # type: ignore
    auto_check_update: bpy.props.BoolProperty(
        name="自动检查更新",
        description="启用后，按下方间隔在后台自动检查更新",
        default=True,
    )  # type: ignore
    updater_interval_months: bpy.props.IntProperty(
        name="月", description="检查更新的间隔月数", default=0, min=0,
    )  # type: ignore
    updater_interval_days: bpy.props.IntProperty(
        name="天", description="检查更新的间隔天数", default=1, min=0, max=31,
    )  # type: ignore
    updater_interval_hours: bpy.props.IntProperty(
        name="时", description="检查更新的间隔小时数", default=0, min=0, max=23,
    )  # type: ignore
    updater_interval_minutes: bpy.props.IntProperty(
        name="分", description="检查更新的间隔分钟数", default=0, min=0, max=59,
    )  # type: ignore
    receive_prereleases: bpy.props.BoolProperty(
        name="接收预发布版本",
        description=("启用后，更新检查会包含 GitHub 上标记为 pre-release 的版本；"
                     "默认只接收稳定的正式版本"),
        default=False,
    )  # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "auto_update_notify")
        layout.prop(self, "receive_prereleases")
        addon_updater_ops.check_for_update_background()
        addon_updater_ops.update_settings_ui(self, context)


def register():
    for cls in addon_updater_ops.classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_class(MMD_STATION_AddonUpdaterPreferences)
    addon_updater_ops.register()
    if not getattr(addon_updater_ops.updater, "invalid_updater", False):
        addon_updater_ops.updater.show_popups = False
    for cls in notify.classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(notify.classes):
        bpy.utils.unregister_class(cls)
    notify.reset_state()
    addon_updater_ops.unregister()
    bpy.utils.unregister_class(MMD_STATION_AddonUpdaterPreferences)
    for cls in reversed(addon_updater_ops.classes):
        bpy.utils.unregister_class(cls)
