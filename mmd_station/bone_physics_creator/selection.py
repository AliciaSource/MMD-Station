import bpy


class BoneSelectionError(RuntimeError):
    pass


def selected_bones_from_view(context, armature):
    if context.object != armature:
        raise BoneSelectionError("请在当前 MMD 模型的骨架上选择骨骼")
    if armature.mode == "POSE":
        selected = tuple(bone.name for bone in (context.selected_pose_bones or ()))
        active = context.active_pose_bone.name if context.active_pose_bone else ""
    elif armature.mode == "EDIT":
        selected = tuple(bone.name for bone in (context.selected_editable_bones or ()))
        active_bone = armature.data.bones.active
        active = active_bone.name if active_bone else ""
    else:
        raise BoneSelectionError("请在骨架 Edit Mode 或 Pose Mode 中选择骨骼")
    if not selected:
        raise BoneSelectionError("3D 视图中没有选中骨骼")
    return tuple(sorted(set(selected))), active


def restore_bone_selection(context, armature, mode, selected_names, active_name):
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode=mode)
    selected = set(selected_names)
    if mode == "POSE":
        for bone in armature.data.bones:
            bone.select = bone.name in selected
        armature.data.bones.active = armature.data.bones.get(active_name)
    else:
        for bone in armature.data.edit_bones:
            bone.select = bone.name in selected
            bone.select_head = bone.select
            bone.select_tail = bone.select
        armature.data.bones.active = armature.data.bones.get(active_name)
