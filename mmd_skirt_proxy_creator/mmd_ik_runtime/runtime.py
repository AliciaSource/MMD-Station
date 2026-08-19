import importlib
import json
import uuid

import bpy
from bpy.props import StringProperty


STATE_KEY = "spx_mmd_ik_runtime_state"
RUNTIME_TAG = "spx_mmd_ik_runtime"
MESH_SESSION_KEY = "spx_mmd_ik_session_id"
OUTPUT_CONSTRAINT_NAME = ".MMD Native Output"
SCHEMA = 2


def register_state_property():
    if not hasattr(bpy.types.Object, STATE_KEY):
        setattr(
            bpy.types.Object,
            STATE_KEY,
            StringProperty(
                name="MMD IK internal state",
                options={"HIDDEN"},
            ),
        )


def unregister_state_property():
    if hasattr(bpy.types.Object, STATE_KEY):
        delattr(bpy.types.Object, STATE_KEY)


class MMDIKRuntimeError(RuntimeError):
    pass


def _import_mmd_module(suffix):
    errors = []
    for base in ("bl_ext.blender_org.mmd_tools", "mmd_tools"):
        try:
            return importlib.import_module(f"{base}.{suffix}")
        except ImportError as error:
            errors.append(error)
    raise MMDIKRuntimeError("需要先安装并启用官方 mmd_tools 扩展") from errors[-1]


def mmd_model_api():
    if not hasattr(bpy.types.Object, "mmd_type"):
        raise MMDIKRuntimeError("需要先启用官方 mmd_tools 扩展")
    return _import_mmd_module("core.model").FnModel


def resolve_root(context, requested=None):
    FnModel = mmd_model_api()
    if requested is not None:
        if getattr(requested, "mmd_type", "") != "ROOT":
            raise MMDIKRuntimeError("指定对象不是 MMD 模型根对象")
        return requested
    root = FnModel.find_root_object(context.active_object)
    if root is None:
        raise MMDIKRuntimeError("请选择 mmd_tools 导入模型中的对象")
    return root


def _decode_state(root):
    raw = root.get(STATE_KEY, "")
    if not raw:
        return None
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError) as error:
        raise MMDIKRuntimeError("MMD IK 状态已损坏") from error


def _remove_legacy_output(canonical):
    for pose_bone in canonical.pose.bones:
        for constraint in tuple(pose_bone.constraints):
            if constraint.name == OUTPUT_CONSTRAINT_NAME:
                pose_bone.constraints.remove(constraint)


def _restore_constraint_mutes(canonical, state):
    _remove_legacy_output(canonical)
    for bone_name, constraint_name, previous in state.get("muted_constraints", []):
        pose_bone = canonical.pose.bones.get(bone_name)
        constraint = pose_bone.constraints.get(constraint_name) if pose_bone else None
        if constraint is not None:
            constraint.mute = bool(previous)


def _load_state(root):
    state = _decode_state(root)
    if state is None:
        return None
    if state.get("schema") == SCHEMA:
        return state
    canonical = mmd_model_api().find_armature_object(root)
    if canonical is None:
        raise MMDIKRuntimeError("旧版 MMD IK 状态无法解析原骨架")
    _restore_constraint_mutes(canonical, state)
    runtime = bpy.data.objects.get(state.get("runtime_armature", ""))
    if runtime is not None and runtime != canonical:
        for mesh in mmd_model_api().iterate_mesh_objects(root):
            for modifier in mesh.modifiers:
                if modifier.type == "ARMATURE" and modifier.object == runtime:
                    modifier.object = canonical
        data = runtime.data
        bpy.data.objects.remove(runtime, do_unlink=True)
        if data.users == 0:
            bpy.data.armatures.remove(data)
    del root[STATE_KEY]
    return None


def _save_state(root, state):
    root[STATE_KEY] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def runtime_state(root):
    return _load_state(root)


def set_action_input(root, enabled=True):
    state = _load_state(root)
    if not state:
        return False
    state["action_input"] = bool(enabled)
    _save_state(root, state)
    return True


def canonical_armature(root, state=None):
    state = state or _load_state(root)
    if state:
        obj = bpy.data.objects.get(state.get("canonical_armature", ""))
        if obj is not None and obj.type == "ARMATURE":
            return obj
    return mmd_model_api().find_armature_object(root)


def runtime_armature(root, state=None):
    return None


def _iter_model_meshes(root):
    yield from mmd_model_api().iterate_mesh_objects(root)


def _mute_constraints(canonical):
    muted = []
    _remove_legacy_output(canonical)
    for pose_bone in canonical.pose.bones:
        for constraint in pose_bone.constraints:
            muted.append((pose_bone.name, constraint.name, bool(constraint.mute)))
            constraint.mute = True
    return muted


def create_runtime(context, root):
    state = _load_state(root)
    canonical = canonical_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("MMD 模型中找不到 Armature")
    if state:
        refresh_bindings(root)
        return canonical, len(list(_iter_model_meshes(root))), False
    state = {
        "schema": SCHEMA,
        "session_id": uuid.uuid4().hex,
        "canonical_armature": canonical.name,
        "enabled": True,
        "binding_mode": "MEMORY_ONLY",
        "action_input": False,
        "muted_constraints": _mute_constraints(canonical),
    }
    _save_state(root, state)
    return canonical, len(list(_iter_model_meshes(root))), True


def refresh_bindings(root):
    state = _load_state(root)
    if not state:
        raise MMDIKRuntimeError("当前模型尚未启用 MMD IK 兼容")
    canonical = canonical_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("原 mmd_tools 骨架已丢失")
    _restore_constraint_mutes(canonical, state)
    state["enabled"] = True
    state["muted_constraints"] = _mute_constraints(canonical)
    _save_state(root, state)
    return len(list(_iter_model_meshes(root)))


def restore_bindings(root, keep_runtime=True):
    state = _load_state(root)
    if not state:
        return 0
    from .evaluator import stop as stop_evaluator

    stop_evaluator(root)
    canonical = canonical_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("原 mmd_tools 骨架已丢失，无法复原")
    _restore_constraint_mutes(canonical, state)
    canonical.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    if keep_runtime:
        state["enabled"] = False
        _save_state(root, state)
    else:
        del root[STATE_KEY]
    return len(list(_iter_model_meshes(root)))


def reenable_bindings(root):
    return refresh_bindings(root)


def selected_armature(root):
    return canonical_armature(root)


def select_armature(root, armature):
    canonical = canonical_armature(root)
    if canonical is None:
        raise MMDIKRuntimeError("MMD 模型中找不到 mmd_tools 原骨架")
    if armature != canonical:
        raise MMDIKRuntimeError("MMD IK 接管始终使用当前模型的 mmd_tools 原骨架")
    return 0


def export_switch_to_canonical(root):
    state = _load_state(root)
    if not state or not state.get("enabled"):
        return None
    canonical = canonical_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("导出保护无法解析原骨架")
    from .evaluator import suspend_live

    suspend_live(root)
    _restore_constraint_mutes(canonical, state)
    canonical.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    return {"state": state, "canonical": canonical}


def export_restore_runtime(root, transaction):
    if not transaction:
        return 0
    state = _load_state(root)
    if not state or state.get("session_id") != transaction["state"].get("session_id"):
        return 0
    canonical = canonical_armature(root, state)
    state["muted_constraints"] = _mute_constraints(canonical)
    state["enabled"] = True
    _save_state(root, state)
    from .evaluator import resume_live

    resume_live(root)
    return len(list(_iter_model_meshes(root)))
