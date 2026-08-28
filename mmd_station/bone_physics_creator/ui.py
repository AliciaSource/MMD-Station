import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from bpy.types import Operator

from .builder import BonePhysicsError, create_from_selected, resolve_armature
from .selection import BoneSelectionError, selected_bones_from_view


class SPX_OT_SyncSelectedBonesToBrowser(Operator):
    bl_idname = "surface_proxy.sync_selected_bones_to_browser"
    bl_label = "从 3D 视图同步选中骨骼"
    bl_description = "读取当前 MMD 骨架在 Edit/Pose Mode 中的选中骨骼并勾选到查看器"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            armature = resolve_armature(settings)
            selected_names, active_name = selected_bones_from_view(context, armature)
        except (BonePhysicsError, BoneSelectionError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings.browser_kind = "BONE"
        try:
            bpy.ops.surface_proxy.refresh_mmd_browser()
        except RuntimeError:
            pass
        selected = set(selected_names)
        active_index = None
        matched = 0
        for index, item in enumerate(settings.browser_items):
            item.selected = item.kind == "BONE" and item.target_name in selected
            if item.selected:
                matched += 1
            if item.kind == "BONE" and item.target_name == active_name:
                active_index = index
        if active_index is not None:
            settings.browser_index = active_index
        if matched != len(selected):
            self.report(
                {"WARNING"},
                f"已同步 {matched}/{len(selected)} 根骨骼；关闭“仅显示当前代理”可显示其余骨骼",
            )
        else:
            self.report({"INFO"}, f"已同步 {matched} 根骨骼到查看器")
        return {"FINISHED"}


class SPX_OT_CreatePhysicsFromSelectedBones(Operator):
    bl_idname = "surface_proxy.create_physics_from_selected_bones"
    bl_label = "从选中骨骼创建 MMD 物理"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        items=(
            ("FOLLOW", "骨骼追踪刚体", "创建 type 0 跟随骨骼刚体"),
            ("PHYSICS", "物理刚体", "创建 type 1 或 type 2 动态刚体"),
            ("JOINT", "基础 Joint", "使用已有刚体按直接父子骨骼创建 Joint"),
            ("COMBINED", "刚体 + 连接 Joint", "创建或复用刚体并连接父子 Joint"),
        ),
        options={"HIDDEN"},
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            result = create_from_selected(
                context,
                settings,
                self.mode,
            )
        except (BonePhysicsError, BoneSelectionError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        target_kind = "JOINT" if self.mode in {"JOINT", "COMBINED"} else "RIGID"
        target_names = set(
            result.created_joint_names
            if target_kind == "JOINT"
            else result.created_rigid_names
        )
        settings.browser_search = ""
        settings.browser_current_proxy_only = False
        settings.browser_kind = target_kind
        try:
            bpy.ops.surface_proxy.refresh_mmd_browser()
        except RuntimeError:
            pass
        active_index = None
        for index, item in enumerate(settings.browser_items):
            item.selected = item.kind == target_kind and item.target_name in target_names
            if item.selected:
                active_index = index
        if active_index is not None:
            settings.browser_index = active_index
        self.report(
            {"INFO"},
            f"选中 {result.selected} 根；创建刚体 {result.created_rigids}、复用 {result.reused_rigids}、创建 Joint {result.created_joints}、跳过 Joint {result.skipped_joints}",
        )
        return {"FINISHED"}


def register_settings(cls):
    cls.__annotations__.update(
        {
            "bone_creator_shape": EnumProperty(
                name="刚体形状",
                items=(("SPHERE", "球体", ""), ("BOX", "盒体", ""), ("CAPSULE", "胶囊", "")),
                default="CAPSULE",
            ),
            "bone_creator_physics_type": EnumProperty(
                name="物理类型",
                items=(("1", "物理", ""), ("2", "物理 + 骨骼", "")),
                default="1",
            ),
            "bone_creator_conflict": EnumProperty(
                name="已有刚体",
                items=(("REUSE", "复用相同类型", ""), ("NEW", "创建副本", "")),
                default="REUSE",
            ),
            "bone_creator_radius_ratio": FloatProperty(name="半径 / 骨长", default=0.25, min=0.001, max=2.0),
            "bone_creator_length_ratio": FloatProperty(name="长度 / 骨长", default=0.9, min=0.001, max=2.0),
            "bone_creator_depth_ratio": FloatProperty(name="厚度 / 骨长", default=0.15, min=0.001, max=2.0),
            "bone_creator_mass": FloatProperty(name="质量", default=1.0, min=0.0),
            "bone_creator_linear_damping": FloatProperty(name="移动阻尼", default=0.5, min=0.0, max=1.0),
            "bone_creator_angular_damping": FloatProperty(name="旋转阻尼", default=0.5, min=0.0, max=1.0),
            "bone_creator_restitution": FloatProperty(name="弹性", default=0.0, min=0.0, max=1.0),
            "bone_creator_friction": FloatProperty(name="摩擦", default=0.5, min=0.0, max=1.0),
            "bone_creator_collision_group": IntProperty(name="碰撞组", default=0, min=0, max=15),
            "bone_creator_collision_mask": bpy.props.BoolVectorProperty(name="不碰撞组", size=16, subtype="LAYER"),
            "bone_creator_limit_linear_lower": FloatVectorProperty(name="移动下限", size=3, subtype="XYZ"),
            "bone_creator_limit_linear_upper": FloatVectorProperty(name="移动上限", size=3, subtype="XYZ"),
            "bone_creator_limit_angular_lower": FloatVectorProperty(name="旋转下限", size=3, subtype="EULER"),
            "bone_creator_limit_angular_upper": FloatVectorProperty(name="旋转上限", size=3, subtype="EULER"),
            "bone_creator_spring_linear": FloatVectorProperty(name="移动弹簧", size=3, subtype="XYZ", min=0.0),
            "bone_creator_spring_angular": FloatVectorProperty(name="旋转弹簧", size=3, subtype="XYZ", min=0.0),
            "bone_creator_show_advanced": BoolProperty(name="高级参数", default=False),
        }
    )


def draw(layout, settings):
    box = layout.box()
    box.label(text="从选中骨骼创建 MMD 物理", icon="PHYSICS")
    row = box.row(align=True)
    row.prop(settings, "bone_creator_shape")
    row.prop(settings, "bone_creator_physics_type")
    box.prop(settings, "bone_creator_conflict")
    row = box.row(align=True)
    row.prop(settings, "bone_creator_radius_ratio")
    row.prop(settings, "bone_creator_length_ratio")
    row.prop(settings, "bone_creator_depth_ratio")
    grid = box.grid_flow(columns=2, even_columns=True, align=True)
    operator = grid.operator(SPX_OT_CreatePhysicsFromSelectedBones.bl_idname, text="骨骼追踪刚体")
    operator.mode = "FOLLOW"
    operator = grid.operator(SPX_OT_CreatePhysicsFromSelectedBones.bl_idname, text="物理刚体")
    operator.mode = "PHYSICS"
    operator = grid.operator(SPX_OT_CreatePhysicsFromSelectedBones.bl_idname, text="基础 Joint")
    operator.mode = "JOINT"
    operator = grid.operator(SPX_OT_CreatePhysicsFromSelectedBones.bl_idname, text="刚体 + 连接 Joint")
    operator.mode = "COMBINED"
    box.prop(settings, "bone_creator_show_advanced", toggle=True)
    if settings.bone_creator_show_advanced:
        column = box.column(align=True)
        column.prop(settings, "bone_creator_mass")
        column.prop(settings, "bone_creator_linear_damping")
        column.prop(settings, "bone_creator_angular_damping")
        column.prop(settings, "bone_creator_restitution")
        column.prop(settings, "bone_creator_friction")
        column.prop(settings, "bone_creator_collision_group")
        column.prop(settings, "bone_creator_collision_mask")
        column.prop(settings, "bone_creator_limit_linear_lower")
        column.prop(settings, "bone_creator_limit_linear_upper")
        column.prop(settings, "bone_creator_limit_angular_lower")
        column.prop(settings, "bone_creator_limit_angular_upper")
        column.prop(settings, "bone_creator_spring_linear")
        column.prop(settings, "bone_creator_spring_angular")


CLASSES = (
    SPX_OT_SyncSelectedBonesToBrowser,
    SPX_OT_CreatePhysicsFromSelectedBones,
)
