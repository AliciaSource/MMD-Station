import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator

from .ffi import library_path
from .runtime import is_running, reset_preview, start_preview, stop_preview


class SPX_OT_StartMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.start_mmd_physics_preview"
    bl_label = "开始物理预览"
    bl_description = "用独立 Rust DLL 读取当前 MMD 刚体和 Joint 并驱动骨骼"

    def execute(self, context):
        try:
            session = start_preview(context)
        except (RuntimeError, OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Rust 物理预览已启动：{session.dynamic_rigid_count} 个动态刚体",
        )
        if session.unanchored_dynamic_components:
            examples = "、".join(
                component[0]
                for component in session.unanchored_dynamic_components[:3]
            )
            self.report(
                {"WARNING"},
                f"发现 {len(session.unanchored_dynamic_components)} 组未连接静态刚体的动态链，"
                f"将按 MMD 语义自由下落：{examples}",
            )
        return {"FINISHED"}


class SPX_OT_StopMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.stop_mmd_physics_preview"
    bl_label = "停止并恢复姿态"

    def execute(self, _context):
        stop_preview(restore=True)
        return {"FINISHED"}


class SPX_OT_ResetMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.reset_mmd_physics_preview"
    bl_label = "重置物理预览"

    def execute(self, _context):
        try:
            reset_preview()
        except (RuntimeError, OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def register_settings(cls):
    annotations = cls.__annotations__
    annotations["preview_running"] = BoolProperty(
        name="正在预览",
        default=False,
        options={"HIDDEN", "SKIP_SAVE"},
    )
    annotations["preview_frequency"] = IntProperty(
        name="固定频率",
        description="Rust 求解器固定步长频率",
        default=60,
        min=30,
        max=240,
    )
    annotations["preview_status"] = StringProperty(
        name="预览状态",
        default="已停止",
        options={"HIDDEN", "SKIP_SAVE"},
    )
    annotations["preview_scope"] = EnumProperty(
        name="预览范围",
        description="当前代理只求解该代理，并保留模型的 0 型刚体作为锚点和碰撞体",
        items=(
            ("CURRENT_PROXY", "当前代理", "不释放模型中其它动态刚体"),
            ("MODEL", "整个模型", "求解模型中的全部刚体和 Joint"),
        ),
        default="CURRENT_PROXY",
    )
    annotations["preview_substeps"] = IntProperty(
        name="子步",
        default=2,
        min=1,
        max=32,
    )
    annotations["preview_gravity"] = FloatVectorProperty(
        name="重力",
        size=3,
        subtype="ACCELERATION",
        default=(0.0, 0.0, -9.80665),
    )
    annotations["preview_update_rigids"] = BoolProperty(
        name="显示刚体运动",
        description="把求解结果同步到 MMD 刚体对象，便于检查",
        default=True,
    )


def draw_preview(layout, settings):
    box = layout.box()
    box.label(text="Rust MMD 物理预览", icon="PHYSICS")
    box.prop(settings, "mmd_root")
    box.prop(settings, "preview_scope", expand=True)
    if settings.preview_scope == "CURRENT_PROXY":
        box.prop(settings, "physics_proxy", text="当前代理")
    path = library_path()
    status = "DLL 已就绪" if path.is_file() else "DLL 缺失"
    box.label(text=status, icon="CHECKMARK" if path.is_file() else "ERROR")
    row = box.row(align=True)
    row.prop(settings, "preview_frequency")
    row.prop(settings, "preview_substeps")
    box.prop(settings, "preview_gravity")
    box.prop(settings, "preview_update_rigids")
    row = box.row(align=True)
    running = is_running()
    box.label(
        text=settings.preview_status,
        icon="PLAY" if running else "PAUSE",
    )
    start = row.row(align=True)
    start.enabled = not running
    start.operator(SPX_OT_StartMMDPhysicsPreview.bl_idname, icon="PLAY")
    stop = row.row(align=True)
    stop.enabled = running
    stop.operator(SPX_OT_StopMMDPhysicsPreview.bl_idname, icon="PAUSE")
    reset = row.row(align=True)
    reset.enabled = running
    reset.operator(SPX_OT_ResetMMDPhysicsPreview.bl_idname, icon="FILE_REFRESH")
    box.label(text="清空全部姿态或发生异常时恢复启动快照并继续运行", icon="INFO")
    box.label(text="启动快照包含全部骨骼、刚体和 Joint", icon="INFO")
    box.label(text="不创建 Blender Rigid Body World", icon="INFO")


CLASSES = (
    SPX_OT_StartMMDPhysicsPreview,
    SPX_OT_StopMMDPhysicsPreview,
    SPX_OT_ResetMMDPhysicsPreview,
)
