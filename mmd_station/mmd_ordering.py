from .i18n import iface, report
import importlib

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from .mmd_material_order import (
    ordered_materials,
    set_material_order,
    sync_changed_material_order,
)


class OrderingError(RuntimeError):
    pass


def _mmd_api():
    try:
        model_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.model"
        )
        misc_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.operators.misc"
        )
    except ImportError as error:
        raise OrderingError("需要先启用官方 mmd_tools 插件") from error
    return model_module.FnModel, misc_module.MoveObject


def _reorder_block(items, selected_items, action, active_item=None):
    selected = set(selected_items)
    if not selected:
        if action in {"TOP", "UP", "DOWN", "BOTTOM"} and active_item in items:
            selected.add(active_item)
        else:
            raise OrderingError("请先勾选要排序的项目")
    if any(item not in items for item in selected):
        raise OrderingError("勾选项目已失效，请刷新列表后重试")

    if action == "TOP":
        return [item for item in items if item in selected] + [
            item for item in items if item not in selected
        ]
    if action == "BOTTOM":
        return [item for item in items if item not in selected] + [
            item for item in items if item in selected
        ]
    if action == "UP":
        result = list(items)
        for index in range(1, len(result)):
            if result[index] in selected and result[index - 1] not in selected:
                result[index - 1], result[index] = result[index], result[index - 1]
        return result
    if action == "DOWN":
        result = list(items)
        for index in range(len(result) - 2, -1, -1):
            if result[index] in selected and result[index + 1] not in selected:
                result[index], result[index + 1] = result[index + 1], result[index]
        return result
    if action not in {"BEFORE", "AFTER"}:
        raise OrderingError(f"未知排序动作：{action}")
    if active_item is None or active_item not in items:
        raise OrderingError("请选择一个活动行作为插入位置")
    if active_item in selected:
        raise OrderingError("活动行不能同时属于勾选块")

    block = [item for item in items if item in selected]
    remaining = [item for item in items if item not in selected]
    insert_at = remaining.index(active_item)
    if action == "AFTER":
        insert_at += 1
    return remaining[:insert_at] + block + remaining[insert_at:]


def _resolve_root(settings, FnModel):
    root = settings.mmd_root
    if root is None:
        raise OrderingError("请先选择 MMD 模型")
    resolved = FnModel.find_root_object(root)
    if resolved is None:
        raise OrderingError("所选对象不属于有效的 MMD 模型")
    return resolved


def _bone_order(FnModel, root):
    armature = FnModel.find_armature_object(root)
    if armature is None:
        raise OrderingError("MMD 模型没有骨架")
    bones = [
        bone
        for bone in armature.pose.bones
        if not getattr(bone, "is_mmd_shadow_bone", False)
    ]
    bones.sort(
        key=lambda bone: (
            bone.mmd_bone.bone_id
            if bone.mmd_bone.bone_id >= 0
            else float("inf"),
            bone.name,
        )
    )
    return armature, bones


def _apply_bone_order(FnModel, root, desired):
    armature = FnModel.find_armature_object(root)
    pose_bones = armature.pose.bones
    bone_morphs = root.mmd_root.bone_morphs
    FnModel.realign_bone_ids(0, bone_morphs, pose_bones)
    for target_index, desired_bone in enumerate(desired):
        current = _bone_order(FnModel, root)[1]
        if current[target_index] == desired_bone:
            continue
        FnModel.shift_bone_id(
            desired_bone.mmd_bone.bone_id,
            current[target_index].mmd_bone.bone_id,
            bone_morphs,
            pose_bones,
        )


def _resolve_items(settings, kind, checked_names, active_name):
    FnModel, MoveObject = _mmd_api()
    root = _resolve_root(settings, FnModel)
    if kind == "BONE":
        _armature, items = _bone_order(FnModel, root)
        by_name = {item.name: item for item in items}
    elif kind == "MATERIAL":
        items = ordered_materials(root, FnModel)
        by_name = {item.name: item for item in items}
    elif kind == "RIGID":
        items = sorted(FnModel.iterate_rigid_body_objects(root), key=lambda item: item.name)
        by_name = {item.name: item for item in items}
    elif kind == "JOINT":
        items = sorted(FnModel.iterate_joint_objects(root), key=lambda item: item.name)
        by_name = {item.name: item for item in items}
    else:
        raise OrderingError(f"不支持的项目类型：{kind}")
    try:
        selected = [by_name[name] for name in checked_names]
    except KeyError as error:
        raise OrderingError("勾选项目已失效，请刷新列表后重试") from error
    active = by_name.get(active_name)
    return FnModel, MoveObject, root, items, selected, active


def reorder_mmd_items(settings, kind, checked_names, action, active_name=None):
    FnModel, MoveObject, root, items, selected, active = _resolve_items(
        settings,
        kind,
        checked_names,
        active_name,
    )
    desired = _reorder_block(items, selected, action, active)
    affected_count = len(selected) if selected else 1
    if kind == "BONE":
        if desired == items:
            applied = items
        else:
            _apply_bone_order(FnModel, root, desired)
            applied = _bone_order(FnModel, root)[1]
    elif kind == "MATERIAL":
        if desired != items:
            set_material_order(root, desired)
            if settings.material_order_auto_sync:
                sync_changed_material_order(root, items, desired, FnModel)
        applied = ordered_materials(root, FnModel)
    else:
        MoveObject.normalize_indices(desired)
        applied = sorted(items, key=lambda item: item.name)
    return (
        [item.name for item in selected],
        active.name if active is not None else None,
        applied != items,
        affected_count,
    )


class SPX_OT_ReorderCheckedMMDItems(Operator):
    bl_idname = "surface_proxy.reorder_checked_mmd_items"
    bl_label = "调整实际 PMX 顺序"
    bl_description = "将勾选项作为一个稳定块调整真实 PMX 导出顺序"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TOP", "置顶", ""),
            ("UP", "上移", ""),
            ("DOWN", "下移", ""),
            ("BOTTOM", "置底", ""),
            ("BEFORE", "插到活动项前", ""),
            ("AFTER", "插到活动项后", ""),
        ),
        options={"HIDDEN"},
    )

    @classmethod
    def description(cls, _context, properties):
        return iface({
            "TOP": "将勾选项置顶；未勾选时移动蓝色活动项",
            "UP": "将勾选项上移一位；未勾选时移动蓝色活动项",
            "DOWN": "将勾选项下移一位；未勾选时移动蓝色活动项",
            "BOTTOM": "将勾选项置底；未勾选时移动蓝色活动项",
            "BEFORE": "将勾选项作为一个块插入蓝色活动行之前",
            "AFTER": "将勾选项作为一个块插入蓝色活动行之后",
        }.get(properties.action, cls.bl_description))

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        kind = settings.browser_kind
        checked_names = [
            item.material.name
            if kind == "MATERIAL" and item.material is not None
            else item.target_name
            for item in settings.browser_items
            if item.kind == kind and item.selected
        ]
        active = None
        if settings.browser_items:
            index = min(settings.browser_index, len(settings.browser_items) - 1)
            candidate = settings.browser_items[index]
            if candidate.kind == kind:
                active = (
                    candidate.material.name
                    if kind == "MATERIAL" and candidate.material is not None
                    else candidate.target_name
                )
        try:
            moved_names, active_name, changed, affected_count = reorder_mmd_items(
                settings,
                kind,
                checked_names,
                self.action,
                active,
            )
        except OrderingError as error:
            report(self, {"ERROR"}, str(error))
            return {"CANCELLED"}

        bpy.ops.surface_proxy.refresh_mmd_browser()
        moved = set(moved_names)
        for index, item in enumerate(settings.browser_items):
            item_name = (
                item.material.name
                if item.kind == "MATERIAL" and item.material is not None
                else item.target_name
            )
            item.selected = item_name in moved
            if active_name is not None and item_name == active_name:
                settings.browser_index = index
        if not changed:
            report(self, {"WARNING"}, "顺序未变化：待移动项已经位于该方向的边界")
        else:
            report(self, {"INFO"}, f"已调整 {affected_count} 项的实际 PMX 顺序")
        return {"FINISHED"}


def draw(layout, _settings):
    for action, icon in (
        ("TOP", "TRIA_UP_BAR"),
        ("UP", "TRIA_UP"),
        ("DOWN", "TRIA_DOWN"),
        ("BOTTOM", "TRIA_DOWN_BAR"),
        ("BEFORE", "ANCHOR_TOP"),
        ("AFTER", "ANCHOR_BOTTOM"),
    ):
        if action == "BEFORE":
            layout.separator(factor=0.5)
        operator = layout.operator(
            SPX_OT_ReorderCheckedMMDItems.bl_idname,
            text="",
            icon=icon,
        )
        operator.action = action


CLASSES = (SPX_OT_ReorderCheckedMMDItems,)
