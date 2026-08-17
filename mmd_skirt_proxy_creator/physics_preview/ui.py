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
from .runtime import (
    active_session_info,
    is_running,
    model_scale_info,
    preview_model_id,
    preview_roots,
    register_model_id_service,
    renumber_preview_models,
    reset_all_previews,
    reset_preview,
    start_preview,
    stop_preview,
)


_INTERACTION_GROUP_ITEMS = []


def _mark_scale_as_user_selected(root, _context):
    if not root.get("spx_mmd_scale_assignment"):
        root["spx_mmd_scale_user_selected"] = True


def _interaction_group_items(_root, context):
    scene = context.scene if context is not None else bpy.context.scene
    _INTERACTION_GROUP_ITEMS.clear()
    for root in preview_roots(scene):
        model_id = preview_model_id(root)
        if model_id is not None:
            _INTERACTION_GROUP_ITEMS.append(
                (
                    str(model_id),
                    f"#{model_id} {root.name}",
                    "选择相同编号且基础尺度相同的模型共享碰撞 world",
                )
            )
    return _INTERACTION_GROUP_ITEMS


class SPX_OT_StartMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.start_mmd_physics_preview"
    bl_label = "开始物理预览"
    bl_description = "用独立 Rust DLL 读取当前 MMD 刚体和 Joint 并驱动骨骼"

    def execute(self, context):
        try:
            sessions = start_preview(context)
        except (RuntimeError, OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Rust 物理预览已启动：{len(sessions)} 个模型，"
            f"{sum(session.dynamic_rigid_count for session in sessions)} 个动态刚体",
        )
        unanchored = [
            component
            for session in sessions
            for component in session.unanchored_dynamic_components
        ]
        if unanchored:
            examples = "、".join(
                component[0]
                for component in unanchored[:3]
            )
            self.report(
                {"WARNING"},
                f"发现 {len(unanchored)} 组未连接静态刚体的动态链，"
                f"将按 MMD 语义自由下落：{examples}",
            )
        return {"FINISHED"}


class SPX_OT_StopMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.stop_mmd_physics_preview"
    bl_label = "停止并恢复姿态"

    root_name: StringProperty(options={"HIDDEN"})

    def execute(self, _context):
        root = bpy.data.objects.get(self.root_name) if self.root_name else None
        if root is None:
            root = _context.scene.surface_proxy_creator.mmd_root
        stop_preview(root=root, restore=True)
        return {"FINISHED"}


class SPX_OT_StopAllMMDPhysicsPreviews(Operator):
    bl_idname = "surface_proxy.stop_all_mmd_physics_previews"
    bl_label = "停止全部"

    def execute(self, _context):
        stop_preview(restore=True)
        return {"FINISHED"}


class SPX_OT_SetMMDPhysicsPreviewSelection(Operator):
    bl_idname = "surface_proxy.set_mmd_physics_preview_selection"
    bl_label = "设置模型选择"

    selected: BoolProperty(options={"HIDDEN"})

    def execute(self, context):
        for root in preview_roots(context.scene):
            root.spx_physics_preview_selected = self.selected
        return {"FINISHED"}


class SPX_OT_RenumberMMDPhysicsPreviewModels(Operator):
    bl_idname = "surface_proxy.renumber_mmd_physics_preview_models"
    bl_label = "重新排序编号"
    bl_description = "压缩模型编号空缺，同时保留现有模型交互组关系"

    def execute(self, context):
        try:
            roots = renumber_preview_models(context.scene)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已重新排序 {len(roots)} 个 MMD 模型编号")
        return {"FINISHED"}


class SPX_OT_ResetMMDPhysicsPreview(Operator):
    bl_idname = "surface_proxy.reset_mmd_physics_preview"
    bl_label = "重置物理预览"

    root_name: StringProperty(options={"HIDDEN"})

    def execute(self, _context):
        try:
            root = bpy.data.objects.get(self.root_name) if self.root_name else None
            if root is None:
                root = _context.scene.surface_proxy_creator.mmd_root
            reset_preview(root)
        except (RuntimeError, OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class SPX_OT_ResetAllMMDPhysicsPreviews(Operator):
    bl_idname = "surface_proxy.reset_all_mmd_physics_previews"
    bl_label = "重置全部物理预览"

    def execute(self, _context):
        try:
            sessions = reset_all_previews()
        except (RuntimeError, OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已重置 {len(sessions)} 个模型的物理预览")
        return {"FINISHED"}


def register_settings(cls):
    bpy.types.Object.spx_physics_preview_selected = BoolProperty(
        name="参与物理预览",
        default=False,
        options={"SKIP_SAVE"},
    )
    bpy.types.Object.spx_mmd_import_scale_override = EnumProperty(
        name="求解尺度",
        items=(
            ("0.08", "0.08", "按 0.08 导入尺度求解"),
            ("0.1", "0.1", "按 0.1 导入尺度求解"),
        ),
        default="0.08",
        update=_mark_scale_as_user_selected,
    )
    bpy.types.Object.spx_mmd_interaction_group_id = EnumProperty(
        name="交互编号",
        description="相同求解尺度和相同编号的模型共享 Bullet world；停止对应模型的预览后可修改",
        items=_interaction_group_items,
    )
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
    annotations["preview_solver_target"] = EnumProperty(
        name="物理对齐目标",
        description="选择预览 DLL 的目标实现；切换前需停止全部物理预览",
        items=(
            ("MMD", "MMD 本体", "使用按 MikuMikuDance 9.32 x64 初始化路径构建的 DLL"),
            ("PMX", "PMX Editor", "使用已与 PmxNLib 2.5 对齐的 DLL"),
        ),
        default="MMD",
    )
    annotations["preview_substeps"] = IntProperty(
        name="最大追帧步数",
        description="对应 MMD/Bullet 的 maxSubSteps；物理固定为 60 Hz，正常 60 FPS 下该值不会改变弹簧响应",
        default=10,
        min=1,
        max=32,
    )
    annotations["preview_gravity"] = FloatVectorProperty(
        name="重力",
        size=3,
        subtype="ACCELERATION",
        description="MMD 重力参数；DLL 内部独立处理模型几何尺度，不需要按 0.08 导入比例换算",
        default=(0.0, 0.0, -9.8),
    )
    annotations["preview_update_rigids"] = BoolProperty(
        name="显示刚体运动",
        description="把求解结果同步到 MMD 刚体对象，便于检查",
        default=True,
    )
    register_model_id_service()


def draw_preview(layout, settings):
    box = layout.box()
    box.label(text="Rust MMD 物理预览", icon="PHYSICS")
    target_row = box.row()
    target_row.enabled = not is_running()
    target_row.prop(settings, "preview_solver_target", expand=True)
    box.prop(settings, "preview_scope", expand=True)
    if settings.preview_scope == "CURRENT_PROXY":
        box.prop(settings, "mmd_root")
        box.prop(settings, "physics_proxy", text="当前代理")
    else:
        roots = preview_roots(bpy.context.scene)
        selection_header = box.row(align=True)
        selection_header.label(text="参与预览的 MMD 模型")
        select_all = selection_header.operator(
            SPX_OT_SetMMDPhysicsPreviewSelection.bl_idname,
            text="全选",
        )
        select_all.selected = True
        select_none = selection_header.operator(
            SPX_OT_SetMMDPhysicsPreviewSelection.bl_idname,
            text="全不选",
        )
        select_none.selected = False
        renumber = selection_header.row(align=True)
        renumber.enabled = not is_running()
        renumber.operator(
            SPX_OT_RenumberMMDPhysicsPreviewModels.bl_idname,
            text="重新排序编号",
            icon="SORT_ASC",
        )
        for root in roots:
            try:
                model_row = box.row(align=True)
                model_id = preview_model_id(root)
                label = f"#{model_id} {root.name}" if model_id is not None else root.name
                model_row.prop(root, "spx_physics_preview_selected", text=label)
                model_row.prop(root, "spx_mmd_import_scale_override", text="求解尺度")
                import_scale, world_scale, overridden = model_scale_info(root)
                scale_kind = "自定义" if overridden else "原生"
                model_row.label(text=f"{scale_kind} {import_scale:g} / DLL ×{world_scale:g}")
                group_row = model_row.row(align=True)
                group_row.enabled = not is_running(root)
                group_row.prop(root, "spx_mmd_interaction_group_id", text="交互编号")
            except RuntimeError:
                model_row.label(text="无法自动识别；请选择 0.08 或 0.1", icon="ERROR")
            except Exception:
                error_row = box.row(align=True)
                error_row.label(text=f"{root.name} 的预览设置无效", icon="ERROR")
    target = settings.preview_solver_target
    path = library_path(target)
    status = f"{target} DLL 已就绪" if path.is_file() else f"{target} DLL 缺失"
    box.label(text=status, icon="CHECKMARK" if path.is_file() else "ERROR")
    row = box.row(align=True)
    row.prop(settings, "preview_frequency")
    row.prop(settings, "preview_substeps")
    box.prop(settings, "preview_gravity")
    box.prop(settings, "preview_update_rigids")
    box.label(text="默认各模型按自己的编号独立并行；同求解尺度、同编号共享碰撞 world", icon="INFO")
    box.label(text="强制修改求解尺度会改变 MMD 空间尺寸，并失去原尺寸 bit 级对齐", icon="INFO")
    running = (
        is_running(settings.mmd_root)
        if settings.preview_scope == "CURRENT_PROXY"
        else any(
            is_running(root)
            for root in preview_roots(bpy.context.scene)
            if root.spx_physics_preview_selected
        )
    )
    sessions = active_session_info()
    box.label(text=settings.preview_status, icon="PLAY" if sessions else "PAUSE")
    row = box.row(align=True)
    start = row.row(align=True)
    if settings.preview_scope == "MODEL":
        selected_roots = tuple(
            root
            for root in preview_roots(bpy.context.scene)
            if root.spx_physics_preview_selected
        )
        start.enabled = any(not is_running(root) for root in selected_roots)
        start.operator(
            SPX_OT_StartMMDPhysicsPreview.bl_idname,
            text="启动已勾选模型",
            icon="PLAY",
        )
        stop_all = row.row(align=True)
        stop_all.enabled = is_running()
        stop_all.operator(
            SPX_OT_StopAllMMDPhysicsPreviews.bl_idname,
            text="停止全部",
            icon="CANCEL",
        )
        reset_all = row.row(align=True)
        reset_all.enabled = is_running()
        reset_all.operator(
            SPX_OT_ResetAllMMDPhysicsPreviews.bl_idname,
            text="重置全部",
            icon="FILE_REFRESH",
        )
    else:
        start.enabled = not running
        start.operator(
            SPX_OT_StartMMDPhysicsPreview.bl_idname,
            text="启动当前代理",
            icon="PLAY",
        )
        stop = row.row(align=True)
        stop.enabled = running
        stop.operator(
            SPX_OT_StopMMDPhysicsPreview.bl_idname,
            text="停止当前模型",
            icon="PAUSE",
        )
        reset = row.row(align=True)
        reset.enabled = running
        reset.operator(SPX_OT_ResetMMDPhysicsPreview.bl_idname, icon="FILE_REFRESH")
    if sessions:
        active_box = box.box()
        header = active_box.row(align=True)
        header.label(text="正在预览的模型", icon="OUTLINER_OB_ARMATURE")
        for root_name, import_scale, world_scale, interaction_group, solver_target in sessions:
            session_row = active_box.row(align=True)
            session_row.label(
                text=(
                    f"{root_name}  导入 {import_scale:g} / DLL ×{world_scale:g}"
                    + f" / {solver_target} / 交互编号 #{interaction_group}"
                )
            )
            reset_operator = session_row.operator(
                SPX_OT_ResetMMDPhysicsPreview.bl_idname,
                text="",
                icon="FILE_REFRESH",
            )
            reset_operator.root_name = root_name
            operator = session_row.operator(
                SPX_OT_StopMMDPhysicsPreview.bl_idname,
                text="",
                icon="X",
            )
            operator.root_name = root_name
    box.label(text="清空全部姿态或发生异常时恢复启动快照并继续运行", icon="INFO")
    box.label(text="启动快照包含全部骨骼、刚体和 Joint", icon="INFO")
    box.label(text="不创建 Blender Rigid Body World", icon="INFO")


CLASSES = (
    SPX_OT_StartMMDPhysicsPreview,
    SPX_OT_StopMMDPhysicsPreview,
    SPX_OT_StopAllMMDPhysicsPreviews,
    SPX_OT_SetMMDPhysicsPreviewSelection,
    SPX_OT_RenumberMMDPhysicsPreviewModels,
    SPX_OT_ResetMMDPhysicsPreview,
    SPX_OT_ResetAllMMDPhysicsPreviews,
)
