import importlib

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator


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
    FnModel.realign_bone_ids(0, bone_morphs, pose_bones)


def _expand_bone_selection(items, selected):
    expanded = set(selected)
    stack = list(selected)
    while stack:
        bone = stack.pop()
        for child in bone.children:
            if getattr(child, "is_mmd_shadow_bone", False) or child in expanded:
                continue
            expanded.add(child)
            stack.append(child)
    return [item for item in items if item in expanded]


def _bone_order_is_valid(desired, current):
    positions = {bone: index for index, bone in enumerate(desired)}
    id_map = {
        bone.mmd_bone.bone_id: bone
        for bone in current
        if bone.mmd_bone.bone_id >= 0
    }
    for bone in desired:
        parent = bone.parent
        while parent is not None and getattr(parent, "is_mmd_shadow_bone", False):
            parent = parent.parent
        if parent in positions and positions[parent] >= positions[bone]:
            return False
        dependency = id_map.get(bone.mmd_bone.additional_transform_bone_id)
        if (
            dependency in positions
            and dependency.mmd_bone.transform_after_dynamics
            == bone.mmd_bone.transform_after_dynamics
            and dependency.mmd_bone.transform_order == bone.mmd_bone.transform_order
            and positions[dependency] >= positions[bone]
        ):
            return False
    return True


def _resolve_items(settings, kind, checked_names, active_name):
    FnModel, MoveObject = _mmd_api()
    root = _resolve_root(settings, FnModel)
    if kind == "BONE":
        _armature, items = _bone_order(FnModel, root)
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
    explicit_selected = list(selected)
    effective_selected = (
        _expand_bone_selection(items, selected) if kind == "BONE" else selected
    )
    desired = _reorder_block(items, effective_selected, action, active)
    if kind == "BONE":
        if desired == items or not _bone_order_is_valid(desired, items):
            applied = items
        else:
            _apply_bone_order(FnModel, root, desired)
            applied = _bone_order(FnModel, root)[1]
    else:
        MoveObject.normalize_indices(desired)
        applied = sorted(items, key=lambda item: item.name)
    return (
        [item.name for item in explicit_selected],
        active.name if active is not None else None,
        applied != items,
        len(effective_selected),
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

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        kind = settings.browser_kind
        checked_names = [
            item.target_name
            for item in settings.browser_items
            if item.kind == kind and item.selected
        ]
        active = None
        if settings.browser_items:
            index = min(settings.browser_index, len(settings.browser_items) - 1)
            candidate = settings.browser_items[index]
            if candidate.kind == kind:
                active = candidate.target_name
        try:
            moved_names, active_name, changed, affected_count = reorder_mmd_items(
                settings,
                kind,
                checked_names,
                self.action,
                active,
            )
        except OrderingError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        bpy.ops.surface_proxy.refresh_mmd_browser()
        moved = set(moved_names)
        for index, item in enumerate(settings.browser_items):
            item.selected = item.target_name in moved
            if active_name is not None and item.target_name == active_name:
                settings.browser_index = index
        if not changed:
            if kind == "BONE":
                message = "顺序未变化：所选骨骼不能越过自己的父骨或其它变换依赖"
            else:
                message = "顺序未变化：勾选项已经位于该方向的边界"
            self.report({"WARNING"}, message)
        elif kind == "BONE" and affected_count > len(moved_names):
            self.report(
                {"INFO"},
                f"已调整 {len(moved_names)} 个勾选骨骼及其 {affected_count - len(moved_names)} 个子级",
            )
        else:
            self.report({"INFO"}, f"已调整 {len(moved_names)} 项的实际 PMX 顺序")
        return {"FINISHED"}


def draw(layout, settings):
    box = layout.box()
    box.label(text="PMX 实际顺序", icon="SORTSIZE")
    row = box.row(align=True)
    for action, text, icon in (
        ("TOP", "置顶", "TRIA_UP_BAR"),
        ("UP", "上移", "TRIA_UP"),
        ("DOWN", "下移", "TRIA_DOWN"),
        ("BOTTOM", "置底", "TRIA_DOWN_BAR"),
    ):
        operator = row.operator(
            SPX_OT_ReorderCheckedMMDItems.bl_idname,
            text=text,
            icon=icon,
        )
        operator.action = action
    row = box.row(align=True)
    operator = row.operator(
        SPX_OT_ReorderCheckedMMDItems.bl_idname,
        text="插到活动项前",
    )
    operator.action = "BEFORE"
    operator = row.operator(
        SPX_OT_ReorderCheckedMMDItems.bl_idname,
        text="插到活动项后",
    )
    operator.action = "AFTER"
    box.label(text="勾选项作为一块；蓝色活动行是插入位置", icon="INFO")
    if settings.browser_kind == "BONE":
        box.label(text="父骨移动会携带全部子级，且不能越过自己的父骨", icon="INFO")


CLASSES = (SPX_OT_ReorderCheckedMMDItems,)
