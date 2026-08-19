import importlib
import json
import uuid

import bpy
from mathutils import Matrix


STATE_KEY = "spx_mmd_ik_runtime_state"
RUNTIME_TAG = "spx_mmd_ik_runtime"
MESH_SESSION_KEY = "spx_mmd_ik_session_id"
SCHEMA = 1
EXPORT_MATRIX_KEY = "spx_mmd_ik_export_matrix"


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


def _load_state(root):
    raw = root.get(STATE_KEY, "")
    if not raw:
        return None
    try:
        state = json.loads(str(raw))
    except (TypeError, ValueError) as error:
        raise MMDIKRuntimeError("MMD IK Runtime 状态已损坏") from error
    if state.get("schema") != SCHEMA:
        raise MMDIKRuntimeError("MMD IK Runtime 状态版本不受支持")
    return state


def _save_state(root, state):
    root[STATE_KEY] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def runtime_state(root):
    return _load_state(root)


def runtime_armature(root, state=None):
    state = state or _load_state(root)
    if not state:
        return None
    obj = bpy.data.objects.get(state.get("runtime_armature", ""))
    if obj is None or obj.type != "ARMATURE" or obj.get(RUNTIME_TAG) != state.get("session_id"):
        return None
    return obj


def canonical_armature(root, state=None):
    state = state or _load_state(root)
    if state:
        obj = bpy.data.objects.get(state.get("canonical_armature", ""))
        if obj is not None and obj.type == "ARMATURE":
            return obj
    return mmd_model_api().find_armature_object(root)


def _runtime_collection(scene):
    name = "MMD IK Runtime"
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)
    return collection


def _remap_runtime_references(runtime, canonical):
    for pose_bone in runtime.pose.bones:
        for constraint in pose_bone.constraints:
            if getattr(constraint, "target", None) == canonical:
                constraint.target = runtime


def _store_export_pose(runtime, canonical):
    for source_bone in canonical.pose.bones:
        runtime_bone = runtime.pose.bones.get(source_bone.name)
        if runtime_bone is not None:
            runtime_bone[EXPORT_MATRIX_KEY] = [value for row in source_bone.matrix for value in row]


def _export_pose_matrix(runtime, bone_name):
    bone = runtime.pose.bones.get(bone_name)
    values = bone.get(EXPORT_MATRIX_KEY) if bone is not None else None
    if values is None or len(values) != 16:
        return None
    return Matrix([values[index * 4 : index * 4 + 4] for index in range(4)])


def _iter_model_meshes(root):
    yield from mmd_model_api().iterate_mesh_objects(root)


def _switch_modifiers(root, source_armature, target_armature, session_id, mark):
    switched = []
    for mesh in _iter_model_meshes(root):
        for modifier in mesh.modifiers:
            if modifier.type != "ARMATURE" or modifier.object != source_armature:
                continue
            modifier.object = target_armature
            switched.append((mesh, modifier.name))
        if mark and any(item[0] == mesh for item in switched):
            mesh[MESH_SESSION_KEY] = session_id
    return switched


def create_runtime(context, root):
    state = _load_state(root)
    if state:
        runtime = runtime_armature(root, state)
        if runtime is None:
            raise MMDIKRuntimeError("记录的 Runtime Armature 已丢失；请先复原运行状态")
        count = refresh_bindings(root)
        return runtime, count, False

    canonical = mmd_model_api().find_armature_object(root)
    if canonical is None:
        raise MMDIKRuntimeError("MMD 模型中找不到 Armature")

    session_id = uuid.uuid4().hex
    runtime = canonical.copy()
    runtime.data = canonical.data.copy()
    runtime.name = f"{canonical.name}_MMD_IK_Runtime"
    runtime.data.name = f"{canonical.data.name}_MMD_IK_Runtime"
    runtime.parent = None
    runtime.matrix_world = canonical.matrix_world.copy()
    runtime[RUNTIME_TAG] = session_id
    runtime["spx_mmd_ik_source_armature"] = canonical.name
    _runtime_collection(context.scene).objects.link(runtime)
    _remap_runtime_references(runtime, canonical)
    _store_export_pose(runtime, canonical)

    state = {
        "schema": SCHEMA,
        "session_id": session_id,
        "canonical_armature": canonical.name,
        "runtime_armature": runtime.name,
        "canonical_hidden": bool(canonical.hide_get()),
        "enabled": True,
    }
    _save_state(root, state)
    switched = _switch_modifiers(root, canonical, runtime, session_id, True)
    canonical.hide_set(True)
    runtime.hide_set(False)
    return runtime, len(switched), True


def refresh_bindings(root):
    state = _load_state(root)
    if not state:
        raise MMDIKRuntimeError("当前模型尚未创建 MMD IK Runtime")
    canonical = canonical_armature(root, state)
    runtime = runtime_armature(root, state)
    if canonical is None or runtime is None:
        raise MMDIKRuntimeError("Canonical 或 Runtime Armature 已丢失")
    state["enabled"] = True
    _save_state(root, state)
    switched = _switch_modifiers(root, canonical, runtime, state["session_id"], True)
    canonical.hide_set(True)
    runtime.hide_set(False)
    return len(switched)


def restore_bindings(root, keep_runtime=True):
    state = _load_state(root)
    if not state:
        return 0
    from .evaluator import stop as stop_evaluator

    stop_evaluator(root)
    canonical = canonical_armature(root, state)
    runtime = runtime_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("Canonical Armature 已丢失，无法复原")

    switched = []
    if runtime is not None:
        switched = _switch_modifiers(root, runtime, canonical, state["session_id"], False)
        runtime.hide_set(True)
    for mesh in _iter_model_meshes(root):
        if mesh.get(MESH_SESSION_KEY) == state["session_id"]:
            del mesh[MESH_SESSION_KEY]
    canonical.hide_set(bool(state.get("canonical_hidden", False)))
    state["enabled"] = False
    _save_state(root, state)

    if not keep_runtime:
        if runtime is not None:
            runtime_data = runtime.data
            bpy.data.objects.remove(runtime, do_unlink=True)
            if runtime_data.users == 0:
                bpy.data.armatures.remove(runtime_data)
        del root[STATE_KEY]
    return len(switched)


def reenable_bindings(root):
    state = _load_state(root)
    if not state:
        raise MMDIKRuntimeError("当前模型尚未创建 MMD IK Runtime")
    return refresh_bindings(root)


def selected_armature(root):
    state = _load_state(root)
    if state and state.get("enabled"):
        runtime = runtime_armature(root, state)
        if runtime is not None:
            return runtime
    return canonical_armature(root, state)


def select_armature(root, armature):
    from ..physics_preview.runtime import is_running as physics_is_running

    if physics_is_running(root):
        raise MMDIKRuntimeError("物理预览运行时不能切换 MMD IK 骨架；请先停止物理预览")
    state = _load_state(root)
    canonical = canonical_armature(root, state)
    if canonical is None:
        raise MMDIKRuntimeError("MMD 模型中找不到 mmd_tools 原骨架")
    if armature == canonical:
        return restore_bindings(root, keep_runtime=True) if state else 0
    runtime = runtime_armature(root, state) if state else None
    if runtime is not None and armature == runtime:
        return reenable_bindings(root)
    raise MMDIKRuntimeError("只能选择当前模型的 mmd_tools 原骨架或 MMD IK 兼容骨架")


def export_switch_to_canonical(root):
    state = _load_state(root)
    if not state or not state.get("enabled"):
        return None
    canonical = canonical_armature(root, state)
    runtime = runtime_armature(root, state)
    if canonical is None or runtime is None:
        raise MMDIKRuntimeError("导出保护无法解析 Canonical/Runtime Armature")
    changed = _switch_modifiers(root, runtime, canonical, state["session_id"], False)
    pose_position = canonical.data.pose_position
    action = canonical.animation_data.action if canonical.animation_data is not None else None
    scene_frame = bpy.context.scene.frame_current
    pose_basis = {bone.name: bone.matrix_basis.copy() for bone in canonical.pose.bones}
    constraint_influences = [
        (constraint, constraint.influence)
        for bone in canonical.pose.bones
        for constraint in bone.constraints
    ]
    if canonical.animation_data is not None:
        canonical.animation_data.action = None
    canonical.data.pose_position = "POSE"
    for constraint, _influence in constraint_influences:
        constraint.influence = 0.0
    bpy.context.view_layer.update()
    for bone in canonical.pose.bones:
        matrix = _export_pose_matrix(runtime, bone.name)
        if matrix is not None:
            bone.matrix = matrix
    return {
        "state": state,
        "canonical": canonical,
        "runtime": runtime,
        "changed": [(mesh.name, modifier_name) for mesh, modifier_name in changed],
        "pose_position": pose_position,
        "action": action,
        "scene_frame": scene_frame,
        "pose_basis": pose_basis,
        "constraint_influences": constraint_influences,
    }


def export_restore_runtime(root, transaction):
    if not transaction:
        return 0
    state = _load_state(root)
    if not state or state.get("session_id") != transaction["state"].get("session_id") or not state.get("enabled"):
        return 0
    canonical = transaction["canonical"]
    runtime = transaction["runtime"]
    for constraint, influence in transaction["constraint_influences"]:
        constraint.influence = influence
    for bone_name, matrix_basis in transaction["pose_basis"].items():
        bone = canonical.pose.bones.get(bone_name)
        if bone is not None:
            bone.matrix_basis = matrix_basis
    if canonical.animation_data is not None:
        canonical.animation_data.action = transaction["action"]
    canonical.data.pose_position = transaction["pose_position"]
    bpy.context.scene.frame_set(transaction["scene_frame"])
    bpy.context.view_layer.update()
    restored = 0
    for mesh_name, modifier_name in transaction["changed"]:
        mesh = bpy.data.objects.get(mesh_name)
        if mesh is None:
            continue
        modifier = mesh.modifiers.get(modifier_name)
        if modifier is not None and modifier.type == "ARMATURE" and modifier.object == canonical:
            modifier.object = runtime
            mesh[MESH_SESSION_KEY] = state["session_id"]
            restored += 1
    return restored
