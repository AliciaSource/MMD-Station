from ..i18n import report
import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from .evaluator import (
    enable_action_input,
    is_active,
    resume_live,
    suspend_live,
)
from .runtime import mmd_model_api


_KEYMAPS = []


def _keying_sets(_self, context):
    scene = context.scene if context is not None else bpy.context.scene
    return [
        (item.bl_idname, item.bl_label, item.bl_description or item.bl_label)
        for item in scene.keying_sets_all
    ]


def _active_root(context):
    active = context.active_object
    if active is None:
        return None
    return mmd_model_api().find_root_object(active)


def _run_with_input_pose(context, callback):
    root = _active_root(context)
    if root is None or not is_active(root):
        return callback()
    suspend_live(root)
    try:
        result = callback()
        if result == {"FINISHED"}:
            enable_action_input(root)
        return result
    finally:
        resume_live(root)


def _rotation_path(pose_bone):
    if pose_bone.rotation_mode == "QUATERNION":
        return "rotation_quaternion"
    if pose_bone.rotation_mode == "AXIS_ANGLE":
        return "rotation_axis_angle"
    return "rotation_euler"


def _direct_pose_keying(context, keying_set, delete=False):
    active = context.active_object
    if active is None or active.type != "ARMATURE" or active.mode != "POSE":
        return {"CANCELLED"}
    selected = tuple(context.selected_pose_bones or ())
    if not selected:
        selected = tuple(bone for bone in active.pose.bones if bone.bone.select)
    if not selected:
        return {"CANCELLED"}
    lowered = keying_set.lower()
    paths = []
    if "loc" in lowered or keying_set in {"Location", "WholeCharacterSelected"}:
        paths.append("location")
    if "rot" in lowered or keying_set in {"Rotation", "WholeCharacterSelected"}:
        paths.append("rotation")
    if "scal" in lowered or keying_set in {"Scaling", "WholeCharacterSelected"}:
        paths.append("scale")
    if not paths:
        return {"CANCELLED"}
    changed = False
    for pose_bone in selected:
        for path in paths:
            data_path = _rotation_path(pose_bone) if path == "rotation" else path
            if delete:
                changed = pose_bone.keyframe_delete(
                    data_path, frame=context.scene.frame_current
                ) or changed
            else:
                changed = pose_bone.keyframe_insert(
                    data_path,
                    frame=context.scene.frame_current,
                    group=pose_bone.name,
                ) or changed
    return {"FINISHED"} if changed else {"CANCELLED"}


class SPX_OT_MMDIKInsertKeyframe(Operator):
    bl_idname = "surface_proxy.mmd_ik_insert_keyframe"
    bl_label = "插入关键帧"
    bl_description = "在 MMD IK 接管期间把用户输入姿态而非 DLL 输出写入 Action"
    bl_options = {"REGISTER", "UNDO"}

    keying_set: EnumProperty(name="Keying Set", items=_keying_sets)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, _event):
        active = context.scene.keying_sets.active
        if active is not None:
            self.keying_set = active.bl_idname
            return self.execute(context)
        return context.window_manager.invoke_search_popup(self)

    def execute(self, context):
        if not self.keying_set:
            report(self, {"ERROR"}, "请选择 Keying Set")
            return {"CANCELLED"}
        def insert():
            try:
                return bpy.ops.anim.keyframe_insert_by_name(type=self.keying_set)
            except RuntimeError:
                return _direct_pose_keying(context, self.keying_set)

        return _run_with_input_pose(context, insert)


class SPX_OT_MMDIKDeleteKeyframe(Operator):
    bl_idname = "surface_proxy.mmd_ik_delete_keyframe"
    bl_label = "删除关键帧"
    bl_description = "在 MMD IK 接管期间从输入 Action 删除当前帧关键帧"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        def delete():
            try:
                return bpy.ops.anim.keyframe_delete_v3d(confirm=False)
            except RuntimeError:
                return _direct_pose_keying(
                    context, "LocRotScale", delete=True
                )

        return _run_with_input_pose(context, delete)


CLASSES = (
    SPX_OT_MMDIKInsertKeyframe,
    SPX_OT_MMDIKDeleteKeyframe,
)


def install_keymaps():
    if _KEYMAPS:
        return
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return
    keymap = keyconfig.keymaps.new(name="Pose", space_type="EMPTY")
    insert = keymap.keymap_items.new(
        SPX_OT_MMDIKInsertKeyframe.bl_idname, "I", "PRESS"
    )
    delete = keymap.keymap_items.new(
        SPX_OT_MMDIKDeleteKeyframe.bl_idname, "I", "PRESS", alt=True
    )
    _KEYMAPS.extend(((keymap, insert), (keymap, delete)))


def uninstall_keymaps():
    for keymap, item in reversed(_KEYMAPS):
        keymap.keymap_items.remove(item)
    _KEYMAPS.clear()
