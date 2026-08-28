import importlib

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty
from bpy.types import Operator, UIList


FRAME_SELECTED_PROPERTY = "spx_display_frame_selected"
ITEM_SELECTED_PROPERTY = "spx_display_item_selected"

_SELECTION_REGISTRATIONS = ()


def _mmd_api():
    model_module = importlib.import_module("bl_ext.blender_org.mmd_tools.core.model")
    return model_module.FnModel, model_module.Model


def _root_poll(_self, obj):
    return obj is not None and getattr(obj, "mmd_type", "") == "ROOT"


def _find_root(context, settings):
    root = settings.display_frame_root
    if _root_poll(None, root):
        return root
    active = context.active_object
    if active is None:
        return None
    try:
        FnModel, _Model = _mmd_api()
    except ImportError:
        return None
    return FnModel.find_root_object(active)


def _active_frame(root):
    frames = root.mmd_root.display_item_frames
    index = root.mmd_root.active_display_item_frame
    return frames[index] if 0 <= index < len(frames) else None


def _active_item(frame):
    return frame.data[frame.active_item] if 0 <= frame.active_item < len(frame.data) else None


def _apply_index_order(collection, desired):
    token_property = "_spx_display_reorder_token"
    for index, item in enumerate(collection):
        item[token_property] = index
    for target_index, token in enumerate(desired):
        current_index = next(
            (
                index
                for index, item in enumerate(collection)
                if item.get(token_property) == token
            ),
            -1,
        )
        if current_index >= 0 and current_index != target_index:
            collection.move(current_index, target_index)
    positions = {
        item.get(token_property): index for index, item in enumerate(collection)
    }
    for item in collection:
        if token_property in item:
            del item[token_property]
    return positions


def _reordered_pointers(order, selected, active, action):
    if action == "TOP":
        return [item for item in order if item in selected] + [
            item for item in order if item not in selected
        ]
    if action == "BOTTOM":
        return [item for item in order if item not in selected] + [
            item for item in order if item in selected
        ]
    if action == "UP":
        result = list(order)
        for index in range(1, len(result)):
            if result[index] in selected and result[index - 1] not in selected:
                result[index - 1], result[index] = result[index], result[index - 1]
        return result
    if action == "DOWN":
        result = list(order)
        for index in range(len(result) - 2, -1, -1):
            if result[index] in selected and result[index + 1] not in selected:
                result[index], result[index + 1] = result[index + 1], result[index]
        return result
    block = [item for item in order if item in selected]
    remaining = [item for item in order if item not in selected]
    insert_at = remaining.index(active)
    if action == "AFTER":
        insert_at += 1
    return remaining[:insert_at] + block + remaining[insert_at:]


def _selected_bone_names(context, armature):
    if context.active_object != armature or armature.mode not in {"EDIT", "POSE"}:
        return ()
    if armature.mode == "POSE":
        bones = context.selected_pose_bones or ()
    else:
        bones = context.selected_editable_bones or ()
    selected = {bone.name for bone in bones}
    active = context.active_bone
    if active is not None:
        selected.add(active.name)
    return tuple(bone.name for bone in armature.data.bones if bone.name in selected)


def _bone_is_visible(bone):
    if bone.hide:
        return False
    collections = tuple(getattr(bone, "collections", ()))
    return not collections or any(
        getattr(
            collection,
            "is_visible_effectively",
            getattr(collection, "is_visible", True),
        )
        for collection in collections
    )


def _append_bone_items(frame, bone_names):
    existing = {item.name for item in frame.data if item.type == "BONE"}
    added = 0
    for bone_name in bone_names:
        if bone_name in existing:
            continue
        item = frame.data.add()
        item.type = "BONE"
        item.name = bone_name
        existing.add(bone_name)
        added += 1
    if added:
        frame.active_item = len(frame.data) - 1
    return added


def _append_selected_morphs(root, frame):
    from .mmd_morph_editor import _morph_by_uid, ensure_morph_states

    ensure_morph_states(root)
    states = root.spx_morph_states
    selected = [state for state in states if state.selected]
    if not selected and 0 <= root.spx_morph_active_index < len(states):
        selected = [states[root.spx_morph_active_index]]
    existing = {
        (item.morph_type, item.name)
        for item in frame.data
        if item.type == "MORPH"
    }
    added = 0
    for state in selected:
        morph = _morph_by_uid(root, state.morph_type, state.uid)
        key = (state.morph_type, morph.name) if morph is not None else None
        if key is None or key in existing:
            continue
        item = frame.data.add()
        item.type = "MORPH"
        item.morph_type, item.name = key
        existing.add(key)
        added += 1
    if added:
        frame.active_item = len(frame.data) - 1
    return added


class SPX_UL_DisplayFrames(UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        row = layout.row(align=True)
        row.prop(item, FRAME_SELECTED_PROPERTY, text="")
        if item.is_special:
            split = row.split(factor=0.5, align=True)
            split.label(text=item.name)
            names = split.row(align=True)
            names.label(text=item.name_e)
            names.label(text="", icon="LOCKED")
        else:
            split = row.split(factor=0.5, align=True)
            split.prop(item, "name", text="", emboss=False)
            split.prop(item, "name_e", text="")


class SPX_UL_DisplayItems(UIList):
    def draw_item(
        self,
        _context,
        layout,
        data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        row = layout.row(align=True)
        row.prop(item, ITEM_SELECTED_PROPERTY, text="")
        row.prop(
            item,
            "name",
            text="",
            emboss=False,
            icon="BONE_DATA" if item.type == "BONE" else "SHAPEKEY_DATA",
        )
        row.prop(item, "type", text="", emboss=False)
        if item.type == "MORPH":
            row.prop(item, "morph_type", text="", emboss=False)
        elif data.name != "表情":
            FnModel, _Model = _mmd_api()
            armature = FnModel.find_armature_object(item.id_data)
            operator = row.operator(
                "surface_proxy.select_mmd_item",
                text="",
                icon="RESTRICT_SELECT_OFF",
            )
            operator.kind = "BONE"
            operator.target_name = item.name
            operator.armature_name = armature.name if armature is not None else ""


class SPX_OT_RefreshDisplayFrameEditor(Operator):
    bl_idname = "surface_proxy.refresh_display_frame_editor"
    bl_label = "刷新显示枠编辑器"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            self.report({"ERROR"}, "找不到 MMD 模型 Root")
            return {"CANCELLED"}
        settings.display_frame_root = root
        _FnModel, Model = _mmd_api()
        Model(root).initialDisplayFrames(reset=False)
        return {"FINISHED"}


class SPX_OT_AddDisplayFrame(Operator):
    bl_idname = "surface_proxy.add_display_frame"
    bl_label = "新增显示枠"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        _FnModel, Model = _mmd_api()
        Model(root).initialDisplayFrames(reset=False)
        mmd_root = root.mmd_root
        frames = mmd_root.display_item_frames
        frame = frames.add()
        frame.name = "新建显示枠"
        frame.name_e = "Display Frame"
        new_index = len(frames) - 1
        insert_after = max(1, mmd_root.active_display_item_frame)
        target_index = min(len(frames) - 1, insert_after + 1)
        frames.move(new_index, target_index)
        mmd_root.active_display_item_frame = target_index
        return {"FINISHED"}


class SPX_OT_RemoveSelectedDisplayFrames(Operator):
    bl_idname = "surface_proxy.remove_selected_display_frames"
    bl_label = "删除勾选显示枠"
    bl_description = "删除勾选显示枠；未勾选时处理蓝色活动项；特殊枠只清空内容"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        mmd_root = root.mmd_root
        frames = mmd_root.display_item_frames
        indices = [
            index
            for index, frame in enumerate(frames)
            if getattr(frame, FRAME_SELECTED_PROPERTY)
        ]
        if not indices and 0 <= mmd_root.active_display_item_frame < len(frames):
            indices = [mmd_root.active_display_item_frame]
        removed = cleared = 0
        for index in reversed(indices):
            frame = frames[index]
            if frame.is_special:
                frame.data.clear()
                frame.active_item = 0
                cleared += 1
            else:
                frames.remove(index)
                removed += 1
        mmd_root.active_display_item_frame = min(
            mmd_root.active_display_item_frame,
            max(0, len(frames) - 1),
        )
        if not removed and not cleared:
            return {"CANCELLED"}
        self.report({"INFO"}, f"已删除 {removed} 个显示枠，清空 {cleared} 个特殊枠")
        return {"FINISHED"}


class SPX_OT_SelectDisplayFrames(Operator):
    bl_idname = "surface_proxy.select_display_frames"
    bl_label = "选择显示枠"
    bl_options = {"INTERNAL"}

    action: EnumProperty(
        items=(("ALL", "全选", ""), ("NONE", "全不选", ""), ("INVERT", "反选", ""))
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        for frame in root.mmd_root.display_item_frames:
            if self.action == "ALL":
                setattr(frame, FRAME_SELECTED_PROPERTY, True)
            elif self.action == "NONE":
                setattr(frame, FRAME_SELECTED_PROPERTY, False)
            else:
                setattr(
                    frame,
                    FRAME_SELECTED_PROPERTY,
                    not getattr(frame, FRAME_SELECTED_PROPERTY),
                )
        return {"FINISHED"}


class SPX_OT_ReorderDisplayFrames(Operator):
    bl_idname = "surface_proxy.reorder_display_frames"
    bl_label = "排序显示枠"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TOP", "置顶", ""),
            ("UP", "上移", ""),
            ("DOWN", "下移", ""),
            ("BOTTOM", "置底", ""),
            ("BEFORE", "插入活动项前", ""),
            ("AFTER", "插入活动项后", ""),
        )
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        mmd_root = root.mmd_root
        frames = mmd_root.display_item_frames
        movable_indices = [
            index for index, frame in enumerate(frames) if not frame.is_special
        ]
        order = list(movable_indices)
        active = (
            mmd_root.active_display_item_frame
            if mmd_root.active_display_item_frame in movable_indices
            else None
        )
        selected = {
            index
            for index in movable_indices
            if getattr(frames[index], FRAME_SELECTED_PROPERTY)
        }
        if not selected:
            if self.action in {"TOP", "UP", "DOWN", "BOTTOM"} and active is not None:
                selected.add(active)
            else:
                self.report({"WARNING"}, "请先勾选可移动显示枠")
                return {"CANCELLED"}
        if self.action in {"BEFORE", "AFTER"} and (
            active is None or active in selected
        ):
            self.report({"WARNING"}, "请选择不属于勾选块的普通活动显示枠")
            return {"CANCELLED"}
        desired_movable = _reordered_pointers(
            order,
            selected,
            active,
            self.action,
        )
        special = [index for index, frame in enumerate(frames) if frame.is_special]
        positions = _apply_index_order(frames, special + desired_movable)
        if active is not None:
            mmd_root.active_display_item_frame = positions[active]
        return {"FINISHED"}


class SPX_OT_AddSelectedDisplayItems(Operator):
    bl_idname = "surface_proxy.add_selected_display_items"
    bl_label = "添加所选内容"
    bl_description = "普通显示枠添加当前所选骨骼；表情枠添加 Morph 编辑器中勾选的 Morph"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        if frame.name == "表情":
            added = _append_selected_morphs(root, frame)
            noun = "Morph"
        else:
            FnModel, _Model = _mmd_api()
            armature = FnModel.find_armature_object(root)
            bone_names = _selected_bone_names(context, armature)
            if not bone_names:
                self.report({"WARNING"}, "请在当前模型 Armature 的 Edit Mode 或 Pose Mode 中选择骨骼")
                return {"CANCELLED"}
            added = _append_bone_items(frame, bone_names)
            noun = "骨骼"
        if not added:
            self.report({"INFO"}, f"所选 {noun} 已在当前显示枠中")
            return {"CANCELLED"}
        self.report({"INFO"}, f"已添加 {added} 个{noun}")
        return {"FINISHED"}


class SPX_OT_RemoveSelectedDisplayItems(Operator):
    bl_idname = "surface_proxy.remove_selected_display_items"
    bl_label = "删除勾选显示项"
    bl_description = "删除勾选显示项；未勾选时删除蓝色活动项"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        indices = [
            index
            for index, item in enumerate(frame.data)
            if getattr(item, ITEM_SELECTED_PROPERTY)
        ]
        if not indices and 0 <= frame.active_item < len(frame.data):
            indices = [frame.active_item]
        for index in reversed(indices):
            frame.data.remove(index)
        frame.active_item = min(frame.active_item, max(0, len(frame.data) - 1))
        if not indices:
            return {"CANCELLED"}
        self.report({"INFO"}, f"已删除 {len(indices)} 个显示项")
        return {"FINISHED"}


class SPX_OT_SelectDisplayItems(Operator):
    bl_idname = "surface_proxy.select_display_items"
    bl_label = "选择显示项"
    bl_options = {"INTERNAL"}

    action: EnumProperty(
        items=(("ALL", "全选", ""), ("NONE", "全不选", ""), ("INVERT", "反选", ""))
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        for item in frame.data:
            if self.action == "ALL":
                setattr(item, ITEM_SELECTED_PROPERTY, True)
            elif self.action == "NONE":
                setattr(item, ITEM_SELECTED_PROPERTY, False)
            else:
                setattr(
                    item,
                    ITEM_SELECTED_PROPERTY,
                    not getattr(item, ITEM_SELECTED_PROPERTY),
                )
        return {"FINISHED"}


class SPX_OT_SelectDisplayInterval(Operator):
    bl_idname = "surface_proxy.select_display_interval"
    bl_label = "区间选组"
    bl_description = "以首尾两个已勾选项为端点，补选两者之间的全部项目"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(
        items=(
            ("FRAMES", "显示枠", "补选显示枠区间"),
            ("ITEMS", "显示项", "补选当前显示枠中的显示项区间"),
        )
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        if self.target == "FRAMES":
            collection = root.mmd_root.display_item_frames
            property_name = FRAME_SELECTED_PROPERTY
            noun = "显示枠"
        else:
            frame = _active_frame(root)
            if frame is None:
                return {"CANCELLED"}
            collection = frame.data
            property_name = ITEM_SELECTED_PROPERTY
            noun = "显示项"
        selected_indices = [
            index
            for index, item in enumerate(collection)
            if getattr(item, property_name)
        ]
        if len(selected_indices) < 2:
            self.report({"WARNING"}, f"区间选组至少需要勾选两个{noun}")
            return {"CANCELLED"}
        added = 0
        for item in collection[selected_indices[0] : selected_indices[-1] + 1]:
            if not getattr(item, property_name):
                setattr(item, property_name, True)
                added += 1
        self.report({"INFO"}, f"已补选区间内 {added} 个{noun}")
        return {"FINISHED"}


class SPX_OT_CleanInvalidDisplayItems(Operator):
    bl_idname = "surface_proxy.clean_invalid_display_items"
    bl_label = "清理失效显示项"
    bl_description = "移除当前显示枠中找不到对应骨骼或 Morph 的残余显示项"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        FnModel, _Model = _mmd_api()
        armature = FnModel.find_armature_object(root)
        if armature is None and any(item.type == "BONE" for item in frame.data):
            self.report({"ERROR"}, "找不到当前 MMD 模型的 Armature，未执行清理")
            return {"CANCELLED"}
        invalid_indices = []
        for index, item in enumerate(frame.data):
            if item.type == "BONE":
                invalid = armature.data.bones.get(item.name) is None
            else:
                morphs = getattr(root.mmd_root, item.morph_type, None)
                invalid = morphs is None or morphs.get(item.name) is None
            if invalid:
                invalid_indices.append(index)
        if not invalid_indices:
            self.report({"INFO"}, "当前显示枠中没有失效显示项")
            return {"CANCELLED"}
        for index in reversed(invalid_indices):
            frame.data.remove(index)
        frame.active_item = min(frame.active_item, max(0, len(frame.data) - 1))
        self.report({"INFO"}, f"已清理 {len(invalid_indices)} 个失效显示项")
        return {"FINISHED"}


class SPX_OT_SelectCheckedDisplayBones(Operator):
    bl_idname = "surface_proxy.select_checked_display_bones"
    bl_label = "将勾选项选入 Blender"
    bl_description = "把当前显示枠中已勾选的有效骨骼同步为 Blender Pose Mode 选择"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None or frame.name == "表情":
            return {"CANCELLED"}
        checked_names = [
            item.name
            for item in frame.data
            if item.type == "BONE" and getattr(item, ITEM_SELECTED_PROPERTY)
        ]
        if not checked_names:
            self.report({"ERROR"}, "当前显示枠中没有勾选骨骼")
            return {"CANCELLED"}
        FnModel, _Model = _mmd_api()
        armature = FnModel.find_armature_object(root)
        if armature is None:
            self.report({"ERROR"}, "找不到当前 MMD 模型的 Armature")
            return {"CANCELLED"}
        valid_names = [
            name for name in checked_names if armature.data.bones.get(name) is not None
        ]
        if not valid_names:
            self.report({"ERROR"}, "勾选骨骼均已失效，请先清理残余显示项")
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        armature.hide_set(False)
        armature.select_set(True)
        context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode="POSE")
        selected = set(valid_names)
        for bone in armature.data.bones:
            bone.select = bone.name in selected
        armature.data.bones.active = armature.data.bones[valid_names[-1]]
        skipped = len(checked_names) - len(valid_names)
        message = f"已将 {len(valid_names)} 根勾选骨骼选入 Blender"
        if skipped:
            message += f"；跳过 {skipped} 个失效项"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_ReorderDisplayItems(Operator):
    bl_idname = "surface_proxy.reorder_display_items"
    bl_label = "排序显示项"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TOP", "置顶", ""),
            ("UP", "上移", ""),
            ("DOWN", "下移", ""),
            ("BOTTOM", "置底", ""),
            ("BEFORE", "插入活动项前", ""),
            ("AFTER", "插入活动项后", ""),
        )
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        order = list(range(len(frame.data)))
        active = frame.active_item if _active_item(frame) is not None else None
        selected = {
            index
            for index, item in enumerate(frame.data)
            if getattr(item, ITEM_SELECTED_PROPERTY)
        }
        if not selected:
            if self.action in {"TOP", "UP", "DOWN", "BOTTOM"} and active is not None:
                selected.add(active)
            else:
                self.report({"WARNING"}, "请先勾选显示项")
                return {"CANCELLED"}
        if self.action in {"BEFORE", "AFTER"} and (
            active is None or active in selected
        ):
            self.report({"WARNING"}, "请选择不属于勾选块的活动显示项")
            return {"CANCELLED"}
        desired = _reordered_pointers(order, selected, active, self.action)
        _apply_index_order(frame.data, desired)
        if active is not None:
            frame.active_item = desired.index(active)
        return {"FINISHED"}


class SPX_OT_SmartFillDisplayFrameBones(Operator):
    bl_idname = "surface_proxy.smart_fill_display_frame_bones"
    bl_label = "智能补充未收录骨骼"
    bl_description = "把尚未出现在任何显示枠中的可见骨骼，按 Armature 顺序加入当前显示枠"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None:
            return {"CANCELLED"}
        if frame.name == "表情":
            self.report({"WARNING"}, "表情枠只收录 Morph，请选择其它显示枠")
            return {"CANCELLED"}
        FnModel, _Model = _mmd_api()
        armature = FnModel.find_armature_object(root)
        if armature is None:
            self.report({"ERROR"}, "找不到当前 MMD 模型的 Armature")
            return {"CANCELLED"}
        registered = {
            item.name
            for display_frame in root.mmd_root.display_item_frames
            for item in display_frame.data
            if item.type == "BONE"
        }
        bone_names = [
            bone.name
            for bone in armature.data.bones
            if bone.name not in registered and _bone_is_visible(bone)
        ]
        added = _append_bone_items(frame, bone_names)
        if not added:
            self.report({"INFO"}, "没有可补充的未收录可见骨骼")
            return {"CANCELLED"}
        self.report({"INFO"}, f"已智能补充 {added} 根骨骼")
        return {"FINISHED"}


class SPX_OT_SmartReorderFacialFrame(Operator):
    bl_idname = "surface_proxy.smart_reorder_facial_frame"
    bl_label = "智能重排序表情枠"
    bl_description = "仅收录有有效详情的 Morph，并按群组、材质、UV、骨骼、顶点排序"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        frame = _active_frame(root) if root is not None else None
        if frame is None or frame.name != "表情":
            self.report({"WARNING"}, "请先选择表情显示枠")
            return {"CANCELLED"}
        from .mmd_morph_editor import _morph_has_details

        priority = (
            "group_morphs",
            "material_morphs",
            "uv_morphs",
            "bone_morphs",
            "vertex_morphs",
        )
        ordered = [
            (morph_type, morph.name)
            for morph_type in priority
            for morph in getattr(root.mmd_root, morph_type)
            if (
                bool(morph.data)
                if morph_type == "group_morphs"
                else _morph_has_details(root, morph_type, morph)
            )
        ]
        frame.data.clear()
        for morph_type, morph_name in ordered:
            item = frame.data.add()
            item.type = "MORPH"
            item.morph_type = morph_type
            item.name = morph_name
        frame.active_item = 0
        self.report({"INFO"}, f"表情枠已重排，共收录 {len(ordered)} 个非空 Morph")
        return {"FINISHED"}


def _draw_reorder_buttons(column, operator_idname):
    for action, icon in (
        ("TOP", "TRIA_UP_BAR"),
        ("UP", "TRIA_UP"),
        ("DOWN", "TRIA_DOWN"),
        ("BOTTOM", "TRIA_DOWN_BAR"),
    ):
        column.operator(operator_idname, text="", icon=icon).action = action
    column.separator(factor=0.5)
    for action, icon in (("BEFORE", "ANCHOR_TOP"), ("AFTER", "ANCHOR_BOTTOM")):
        column.operator(operator_idname, text="", icon=icon).action = action


def _draw_selection_buttons(
    layout,
    operator_idname,
    interval_target,
    clean_operator_idname="",
    sync_operator_idname="",
):
    row = layout.row(align=True)
    row.operator(operator_idname, text="全选").action = "ALL"
    row.operator(operator_idname, text="全不选").action = "NONE"
    row.operator(operator_idname, text="反选").action = "INVERT"
    row.operator(
        SPX_OT_SelectDisplayInterval.bl_idname,
        text="区间选组",
    ).target = interval_target
    if clean_operator_idname:
        row.operator(clean_operator_idname, text="清理", icon="TRASH")
    if sync_operator_idname:
        row.operator(
            sync_operator_idname,
            text="",
            icon="RESTRICT_SELECT_OFF",
        )


def _draw_active_item_details(layout, root, frame):
    item = _active_item(frame)
    if item is None:
        return
    box = layout.box()
    box.prop(item, "type", text="类型", expand=True)
    FnModel, _Model = _mmd_api()
    if item.type == "BONE":
        armature = FnModel.find_armature_object(root)
        if armature is None:
            box.label(text="找不到 Armature", icon="ERROR")
        else:
            box.prop_search(item, "name", armature.pose, "bones", text="骨骼")
    else:
        box.prop(item, "morph_type", text="Morph 类型")
        box.prop_search(
            item,
            "name",
            root.mmd_root,
            item.morph_type,
            text="Morph",
        )


def draw_display_frame_editor(layout, context):
    settings = context.scene.surface_proxy_creator
    root = _find_root(context, settings)
    row = layout.row(align=True)
    row.prop(settings, "display_frame_root", text="MMD 模型")
    row.operator("surface_proxy.refresh_display_frame_editor", text="", icon="FILE_REFRESH")
    if root is None:
        layout.label(text="请选择 MMD 模型或模型内对象", icon="INFO")
        return
    mmd_root = root.mmd_root
    frames_row = layout.row()
    frames_row.template_list(
        "SPX_UL_DisplayFrames",
        "",
        mmd_root,
        "display_item_frames",
        mmd_root,
        "active_display_item_frame",
        rows=7,
    )
    frame_buttons = frames_row.column(align=True)
    frame_buttons.operator("surface_proxy.add_display_frame", text="", icon="ADD")
    frame_buttons.operator(
        "surface_proxy.remove_selected_display_frames",
        text="",
        icon="REMOVE",
    )
    frame_buttons.separator(factor=0.5)
    _draw_reorder_buttons(frame_buttons, "surface_proxy.reorder_display_frames")
    _draw_selection_buttons(
        layout,
        "surface_proxy.select_display_frames",
        "FRAMES",
    )

    frame = _active_frame(root)
    if frame is None:
        return
    items_row = layout.row()
    items_row.template_list(
        "SPX_UL_DisplayItems",
        "",
        frame,
        "data",
        frame,
        "active_item",
        rows=9,
    )
    item_buttons = items_row.column(align=True)
    item_buttons.operator(
        "surface_proxy.add_selected_display_items",
        text="",
        icon="ADD",
    )
    item_buttons.operator(
        "surface_proxy.remove_selected_display_items",
        text="",
        icon="REMOVE",
    )
    item_buttons.separator(factor=0.5)
    _draw_reorder_buttons(item_buttons, "surface_proxy.reorder_display_items")
    _draw_selection_buttons(
        layout,
        "surface_proxy.select_display_items",
        "ITEMS",
        "surface_proxy.clean_invalid_display_items",
        "surface_proxy.select_checked_display_bones" if frame.name != "表情" else "",
    )
    if frame.name == "表情":
        layout.operator(
            "surface_proxy.smart_reorder_facial_frame",
            text="智能重排序：群组 → 材质 → UV → 骨骼 → 顶点",
            icon="SORTSIZE",
        )
    else:
        layout.operator(
            "surface_proxy.smart_fill_display_frame_bones",
            text="智能补充未收录的可见骨骼",
            icon="IMPORT",
        )
    _draw_active_item_details(layout, root, frame)


def register_settings(settings_cls):
    settings_cls.__annotations__["display_frame_root"] = PointerProperty(
        name="MMD 模型",
        type=bpy.types.Object,
        poll=_root_poll,
    )


def register_services():
    global _SELECTION_REGISTRATIONS
    root_properties = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.properties.root"
    )
    registrations = (
        (root_properties.MMDDisplayItemFrame, FRAME_SELECTED_PROPERTY),
        (root_properties.MMDDisplayItem, ITEM_SELECTED_PROPERTY),
    )
    for item_type, property_name in registrations:
        if not hasattr(item_type, property_name):
            setattr(
                item_type,
                property_name,
                BoolProperty(
                    name="选择",
                    description="选择该项，供批量删除与排序使用",
                    default=False,
                ),
            )
    _SELECTION_REGISTRATIONS = registrations


def unregister_services():
    global _SELECTION_REGISTRATIONS
    for item_type, property_name in reversed(_SELECTION_REGISTRATIONS):
        if hasattr(item_type, property_name):
            delattr(item_type, property_name)
    _SELECTION_REGISTRATIONS = ()


CLASSES = (
    SPX_UL_DisplayFrames,
    SPX_UL_DisplayItems,
    SPX_OT_RefreshDisplayFrameEditor,
    SPX_OT_AddDisplayFrame,
    SPX_OT_RemoveSelectedDisplayFrames,
    SPX_OT_SelectDisplayFrames,
    SPX_OT_ReorderDisplayFrames,
    SPX_OT_AddSelectedDisplayItems,
    SPX_OT_RemoveSelectedDisplayItems,
    SPX_OT_SelectDisplayItems,
    SPX_OT_SelectDisplayInterval,
    SPX_OT_CleanInvalidDisplayItems,
    SPX_OT_SelectCheckedDisplayBones,
    SPX_OT_ReorderDisplayItems,
    SPX_OT_SmartFillDisplayFrameBones,
    SPX_OT_SmartReorderFacialFrame,
)
