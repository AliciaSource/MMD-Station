from .i18n import report
import bpy
from bpy.types import Operator


class _MMDToolsIOProxy(Operator):
    target_operator = ""
    reuse_last_filepath = False

    @classmethod
    def poll(cls, _context):
        try:
            module_name, operator_name = cls.target_operator.split(".", 1)
            return getattr(getattr(bpy.ops, module_name), operator_name).poll()
        except (AttributeError, RuntimeError, ValueError):
            return False

    @classmethod
    def _target_invoke_kwargs(cls, context):
        if not cls.reuse_last_filepath:
            return {}
        last_properties = context.window_manager.operator_properties_last(
            cls.target_operator
        )
        filepath = getattr(last_properties, "filepath", "")
        return {"filepath": filepath} if filepath else {}

    def _invoke_target(self, context):
        try:
            module_name, operator_name = self.target_operator.split(".", 1)
            operator = getattr(getattr(bpy.ops, module_name), operator_name)
            return operator("INVOKE_DEFAULT", **self._target_invoke_kwargs(context))
        except (AttributeError, RuntimeError, ValueError) as error:
            report(self, {"ERROR"}, f"无法启动 mmd_tools I/O：{error}")
            return {"CANCELLED"}

    def invoke(self, context, _event):
        return self._invoke_target(context)

    def execute(self, context):
        return self._invoke_target(context)


class MMD_STATION_OT_ImportModel(_MMDToolsIOProxy):
    bl_idname = "mmd_station.import_model"
    bl_label = "导入 MMD 模型"
    bl_description = "使用 mmd_tools 导入 PMD/PMX 模型"
    target_operator = "mmd_tools.import_model"


class MMD_STATION_OT_ExportPMX(_MMDToolsIOProxy):
    bl_idname = "mmd_station.export_pmx"
    bl_label = "导出 PMX 模型"
    bl_description = "首次完整导出建立运行时 Shadow；同一 Blender 会话中的安全小改动可快速覆盖或另存为"
    target_operator = "mmd_tools.export_pmx"
    reuse_last_filepath = True


class MMD_STATION_OT_ImportVMD(_MMDToolsIOProxy):
    bl_idname = "mmd_station.import_vmd"
    bl_label = "导入 VMD 运动"
    bl_description = "使用 mmd_tools 导入 VMD 运动"
    target_operator = "mmd_tools.import_vmd"


class MMD_STATION_OT_ExportVMD(_MMDToolsIOProxy):
    bl_idname = "mmd_station.export_vmd"
    bl_label = "导出 VMD 运动"
    bl_description = "使用 MMD Station 导出入口导出 VMD 运动"
    target_operator = "mmd_tools.export_vmd"
    reuse_last_filepath = True


class MMD_STATION_OT_ImportVPD(_MMDToolsIOProxy):
    bl_idname = "mmd_station.import_vpd"
    bl_label = "导入 VPD 姿态"
    bl_description = "使用 mmd_tools 导入 VPD 姿态"
    target_operator = "mmd_tools.import_vpd"


class MMD_STATION_OT_ExportVPD(_MMDToolsIOProxy):
    bl_idname = "mmd_station.export_vpd"
    bl_label = "导出 VPD 姿态"
    bl_description = "使用 MMD Station 导出入口导出 VPD 姿态"
    target_operator = "mmd_tools.export_vpd"
    reuse_last_filepath = True


def draw_mmd_io(layout):
    row = layout.row()

    column = row.column(align=True)
    column.label(text="模型", icon="OUTLINER_OB_ARMATURE")
    column.operator(MMD_STATION_OT_ImportModel.bl_idname, text="导入")
    column.operator(MMD_STATION_OT_ExportPMX.bl_idname, text="导出")

    column = row.column(align=True)
    column.label(text="运动", icon="ANIM")
    column.operator(MMD_STATION_OT_ImportVMD.bl_idname, text="导入")
    column.operator(MMD_STATION_OT_ExportVMD.bl_idname, text="导出")

    column = row.column(align=True)
    column.label(text="姿态", icon="POSE_HLT")
    column.operator(MMD_STATION_OT_ImportVPD.bl_idname, text="导入")
    column.operator(MMD_STATION_OT_ExportVPD.bl_idname, text="导出")


CLASSES = (
    MMD_STATION_OT_ImportModel,
    MMD_STATION_OT_ExportPMX,
    MMD_STATION_OT_ImportVMD,
    MMD_STATION_OT_ExportVMD,
    MMD_STATION_OT_ImportVPD,
    MMD_STATION_OT_ExportVPD,
)
