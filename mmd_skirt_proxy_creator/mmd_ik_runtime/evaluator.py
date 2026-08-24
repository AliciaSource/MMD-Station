from dataclasses import dataclass, field
from array import array
import math
from pathlib import Path
import struct
import tempfile

import bpy
from bpy.app.handlers import persistent
import numpy as np

from .coordinates import (
    blender_pose_matrix,
    blender_position_to_mmd,
    mmd_position_to_blender,
)
from .ffi import NativeBoneSolver
from .runtime import (
    MMDIKRuntimeError,
    canonical_armature,
    refresh_bindings,
    runtime_state,
    set_action_input,
)
from .vmd_hook import SOURCE_FRAME_KEY, SOURCE_VMD_KEY


_SESSIONS = {}


def _live_object(reference):
    if reference is None:
        return None
    try:
        return (
            reference
            if bpy.data.objects.get(reference.name) is reference
            else None
        )
    except (AttributeError, ReferenceError, TypeError):
        return None


def _root_preview_id(root):
    try:
        return int(root.get("spx_mmd_preview_id", 0))
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return 0


def _root_scene_name(root):
    return _root_scene_identity(root)[0]


def _root_scene_identity(root):
    try:
        scenes = tuple(root.users_scene)
    except (AttributeError, ReferenceError, TypeError):
        return "", 0
    if len(scenes) != 1:
        return "", 0
    scene = scenes[0]
    return scene.name, _rna_pointer(scene)


def _live_scene(reference):
    if reference is None:
        return None
    try:
        return (
            reference
            if bpy.data.scenes.get(reference.name) is reference
            else None
        )
    except (AttributeError, ReferenceError, TypeError):
        return None


def _object_in_scene(obj, scene):
    if obj is None or scene is None:
        return False
    try:
        return any(candidate is scene for candidate in obj.users_scene)
    except (AttributeError, ReferenceError, TypeError):
        return False


def _owner_scene(root):
    try:
        scenes = tuple(root.users_scene)
    except ReferenceError as error:
        raise MMDIKRuntimeError("MMD 模型根对象已丢失") from error
    if len(scenes) != 1:
        raise MMDIKRuntimeError("MMD 模型根对象必须只属于一个 Scene")
    return scenes[0]


def _owner_view_layer(scene, preferred_name="", required_object=None):
    candidates = []
    if preferred_name:
        preferred = scene.view_layers.get(preferred_name)
        if preferred is not None:
            candidates.append(preferred)
    context_scene = getattr(bpy.context, "scene", None)
    context_view_layer = getattr(bpy.context, "view_layer", None)
    if context_scene is scene and context_view_layer is not None:
        candidate = scene.view_layers.get(context_view_layer.name)
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    candidates.extend(
        view_layer
        for view_layer in scene.view_layers
        if view_layer not in candidates
    )
    for view_layer in candidates:
        if (
            required_object is None
            or view_layer.objects.get(required_object.name) is required_object
        ):
            return view_layer
    raise MMDIKRuntimeError("MMD 模型在所属 Scene 的所有 View Layer 中均不可用")


def _session_scene(session, root=None):
    if root is None:
        root = _live_object(getattr(session, "root_ref", None))
    scene = _live_scene(getattr(session, "scene_ref", None))
    if root is not None:
        try:
            owner_scenes = tuple(root.users_scene)
        except ReferenceError:
            return None
        if len(owner_scenes) != 1:
            return None
        owner_scene = owner_scenes[0]
        if scene is not None and scene is not owner_scene:
            return None
        if scene is None:
            stored_name = getattr(session, "scene_name", "")
            if stored_name and owner_scene.name != stored_name:
                return None
            scene = owner_scene
        session.scene_ref = scene
        session.scene_name = scene.name
        session.scene_pointer = _rna_pointer(scene)
        return scene
    if scene is not None:
        return scene
    scene_name = getattr(session, "scene_name", "")
    candidate = bpy.data.scenes.get(scene_name) if scene_name else None
    if candidate is not None:
        scene = candidate
    else:
        scene = None
    if scene is None:
        return None
    session.scene_ref = scene
    session.scene_name = scene.name
    session.scene_pointer = _rna_pointer(scene)
    return scene


def _session_view_layer(session, scene=None, required_object=None):
    scene = scene or _session_scene(session)
    if scene is None:
        raise MMDIKRuntimeError("MMD native Session 所属 Scene 已丢失")
    view_layer = _owner_view_layer(
        scene,
        getattr(session, "view_layer_name", ""),
        required_object=required_object,
    )
    session.view_layer_name = view_layer.name
    return view_layer


def _rna_pointer(value):
    if value is None:
        return 0
    try:
        return int(value.as_pointer())
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return 0


def _armature_rest_signature(armature):
    return tuple(
        (
            bone.name,
            bone.parent.name if bone.parent is not None else "",
            tuple(float(value) for row in bone.matrix_local for value in row),
        )
        for bone in armature.data.bones
    )


def _depsgraph_id_updated(depsgraph, target):
    if depsgraph is None:
        return True
    target_pointer = _rna_pointer(target)
    if not target_pointer:
        return False
    try:
        updates = depsgraph.updates
    except AttributeError:
        return False
    if updates is None:
        return False
    try:
        for update in updates:
            updated = getattr(update, "id", None)
            original = getattr(updated, "original", updated)
            if (
                _rna_pointer(updated) == target_pointer
                or _rna_pointer(original) == target_pointer
            ):
                return True
    except TypeError:
        return False
    return False


def _depsgraph_type_updated(depsgraph, id_type):
    if depsgraph is None:
        return True
    checker = getattr(depsgraph, "id_type_updated", None)
    if not callable(checker):
        return True
    try:
        return bool(checker(id_type))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return True


def _root_fallback_matches(root, session):
    if _live_object(root) is None or getattr(root, "mmd_type", "") != "ROOT":
        return False
    scene = _session_scene(session)
    if scene is None or not _object_in_scene(root, scene):
        return False
    try:
        if tuple(root.users_scene) != (scene,):
            return False
    except ReferenceError:
        return False
    expected_preview_id = int(getattr(session, "root_preview_id", 0) or 0)
    if expected_preview_id > 0:
        return _root_preview_id(root) == expected_preview_id
    return bool(
        getattr(session, "root_pointer", 0)
        and _rna_pointer(root) == getattr(session, "root_pointer", 0)
    )


def _root_matches_session(root, session):
    if _live_object(getattr(session, "root_ref", None)) is not root:
        return False
    expected_preview_id = int(getattr(session, "root_preview_id", 0) or 0)
    if expected_preview_id > 0:
        return _root_preview_id(root) == expected_preview_id
    expected_pointer = int(getattr(session, "root_pointer", 0) or 0)
    return bool(expected_pointer and _rna_pointer(root) == expected_pointer)


def _model_armature(root):
    try:
        if root is None:
            return None
        for child in root.children:
            if child.type == "ARMATURE":
                return child
    except (AttributeError, ReferenceError):
        return None
    return None


def _session_armature_matches(session, candidate):
    candidate = _live_object(candidate)
    root = _live_object(getattr(session, "root_ref", None))
    if candidate is None or candidate.type != "ARMATURE" or root is None:
        return False
    scene = _session_scene(session, root)
    if scene is None:
        return False
    try:
        if tuple(candidate.users_scene) != (scene,):
            return False
    except ReferenceError:
        return False
    return _model_armature(root) is candidate


def _session_armature_fallback(session, name):
    candidate = bpy.data.objects.get(name) if name else None
    return candidate if _session_armature_matches(session, candidate) else None


def _cached_session_armature(session, candidate):
    if not getattr(session, "identity_validated", False):
        return False
    candidate = _live_object(candidate)
    root = _live_object(getattr(session, "root_ref", None))
    scene = _live_scene(getattr(session, "scene_ref", None))
    if candidate is None or root is None or scene is None:
        return False
    try:
        return bool(
            candidate.type == "ARMATURE"
            and getattr(session, "runtime_ref", None) is candidate
            and getattr(session, "canonical_ref", None) is candidate
            and candidate.parent is root
            and session.root_name == root.name
            and session.runtime_name == candidate.name
            and session.canonical_name == candidate.name
            and getattr(session, "scene_name", "") == scene.name
            and getattr(session, "root_pointer", 0) == _rna_pointer(root)
            and getattr(session, "scene_pointer", 0) == _rna_pointer(scene)
            and getattr(session, "binding_object_pointer", 0)
            == _rna_pointer(candidate)
            and getattr(session, "binding_data_pointer", 0)
            == _rna_pointer(candidate.data)
            and scene.objects.get(root.name) is root
            and scene.objects.get(candidate.name) is candidate
        )
    except (AttributeError, ReferenceError):
        return False


def _session_root(registered_name, session, allow_recreated=False):
    root = _live_object(getattr(session, "root_ref", None))
    if root is not None:
        if not _root_matches_session(root, session):
            return None
        scene = _session_scene(session, root)
        if scene is None or not _object_in_scene(root, scene):
            return None
        try:
            return root if tuple(root.users_scene) == (scene,) else None
        except ReferenceError:
            return None
    if not allow_recreated:
        return None
    preview_id = int(getattr(session, "root_preview_id", 0) or 0)
    if preview_id <= 0:
        return None
    scene = _session_scene(session)
    candidates = tuple(
        obj
        for obj in (scene.objects if scene is not None else ())
        if _root_fallback_matches(obj, session)
    )
    return candidates[0] if len(candidates) == 1 else None


def _session_for_root(root):
    if root is None:
        return None
    try:
        session = _SESSIONS.get(root.name)
    except (AttributeError, ReferenceError, TypeError):
        return None
    if session is not None and _root_matches_session(root, session):
        if session.root_name != root.name:
            rebind_session_names(root, session.root_name)
        return session
    for candidate in tuple(_SESSIONS.values()):
        if _root_matches_session(root, candidate):
            rebind_session_names(root, candidate.root_name)
            return candidate
    return None


def rebind_session_names(
    root,
    previous_root_name=None,
    armature=None,
    previous_armature_name=None,
    check_rest=False,
    allow_recreated=False,
):
    if root is None:
        return False
    try:
        root_name = root.name
    except ReferenceError:
        return False
    session = _SESSIONS.get(root_name)
    if session is None and previous_root_name:
        session = _SESSIONS.get(previous_root_name)
    if session is None:
        session = next(
            (
                candidate
                for candidate in _SESSIONS.values()
                if _live_object(getattr(candidate, "root_ref", None)) is root
            ),
            None,
        )
    if session is None:
        return False
    session.identity_validated = False
    if not _root_matches_session(root, session):
        if (
            not allow_recreated
            or _session_root(
                previous_root_name or session.root_name,
                session,
                allow_recreated=True,
            )
            is not root
        ):
            return False
    collision = _SESSIONS.get(root_name)
    if collision is not None and collision is not session:
        raise RuntimeError(f"MMD IK session key already exists: {root_name}")

    runtime = _live_object(armature) or _live_object(
        getattr(session, "runtime_ref", None)
    )
    canonical = _live_object(armature) or _live_object(
        getattr(session, "canonical_ref", None)
    )
    runtime_name = runtime.name if runtime is not None else session.runtime_name
    canonical_name = (
        canonical.name if canonical is not None else session.canonical_name
    )
    root_pointer = _rna_pointer(root)
    root_preview_id = _root_preview_id(root)
    scene = _session_scene(session, root)
    if scene is None:
        return False
    scene_name, scene_pointer = scene.name, _rna_pointer(scene)
    bindings_changed = False
    rebuild_bindings = getattr(session, "rebuild_bindings", None)
    if canonical is not None and callable(rebuild_bindings):
        object_pointer = _rna_pointer(canonical)
        data_pointer = _rna_pointer(canonical.data)
        identity_changed = bool(
            object_pointer != getattr(session, "binding_object_pointer", 0)
            or data_pointer != getattr(session, "binding_data_pointer", 0)
        )
        rest_signature = None
        rest_changed = False
        if identity_changed or check_rest:
            rest_signature = _armature_rest_signature(canonical)
            rest_changed = (
                rest_signature
                != getattr(session, "binding_rest_signature", ())
            )
        if identity_changed or rest_changed:
            if not rebuild_bindings(canonical, rest_signature=rest_signature):
                raise MMDIKRuntimeError(
                    "PMX 骨名与重绑定后的 Runtime Armature 完全不匹配"
                )
            bindings_changed = True
    changed = bool(
        session.root_name != root_name
        or session.runtime_name != runtime_name
        or session.canonical_name != canonical_name
        or getattr(session, "root_ref", None) is not root
        or getattr(session, "root_pointer", 0) != root_pointer
        or int(getattr(session, "root_preview_id", 0) or 0) != root_preview_id
        or getattr(session, "scene_name", "") != scene_name
        or getattr(session, "scene_pointer", 0) != scene_pointer
        or bindings_changed
    )
    for key, candidate in tuple(_SESSIONS.items()):
        if candidate is session and key != root_name:
            _SESSIONS.pop(key, None)
    _SESSIONS[root_name] = session
    session.root_name = root_name
    session.root_ref = root
    session.root_pointer = root_pointer
    session.root_preview_id = root_preview_id
    session.scene_name = scene_name
    session.scene_pointer = scene_pointer
    session.scene_ref = scene
    if runtime is not None:
        session.runtime_name = runtime_name
        session.runtime_ref = runtime
    if canonical is not None:
        session.canonical_name = canonical_name
        session.canonical_ref = canonical
        session.binding_mode = canonical.mode
    return changed


def refresh_session_bindings(root, armature=None, check_rest=False):
    """Rebind names and report whether the native-to-pose mapping was rebuilt."""
    if root is None:
        return False
    try:
        session = _SESSIONS.get(root.name)
    except ReferenceError:
        return False
    if session is None:
        session = next(
            (
                candidate
                for candidate in _SESSIONS.values()
                if _live_object(getattr(candidate, "root_ref", None)) is root
            ),
            None,
        )
    if session is None:
        return False
    if not check_rest and armature is not None:
        try:
            root_name = root.name
            armature_name = armature.name
            scene_name, scene_pointer = _root_scene_identity(root)
            unchanged = bool(
                getattr(session, "root_ref", None) is root
                and getattr(session, "runtime_ref", None) is armature
                and getattr(session, "canonical_ref", None) is armature
                and session.root_name == root_name
                and session.runtime_name == armature_name
                and session.canonical_name == armature_name
                and getattr(session, "root_pointer", 0) == _rna_pointer(root)
                and getattr(session, "binding_object_pointer", 0)
                == _rna_pointer(armature)
                and getattr(session, "binding_data_pointer", 0)
                == _rna_pointer(armature.data)
                and int(getattr(session, "root_preview_id", 0) or 0)
                == _root_preview_id(root)
                and getattr(session, "scene_name", "") == scene_name
                and getattr(session, "scene_pointer", 0) == scene_pointer
            )
        except (AttributeError, ReferenceError):
            unchanged = False
        if unchanged:
            return False
    binding_revision = getattr(session, "binding_revision", None)
    changed = rebind_session_names(
        root,
        session.root_name,
        armature=armature,
        previous_armature_name=session.canonical_name or session.runtime_name,
        check_rest=check_rest,
    )
    if binding_revision is None:
        return changed
    return session.binding_revision != binding_revision


def _registered_session_objects(
    registered_name,
    session,
    allow_recreated=False,
):
    session.identity_validated = False
    root = _live_object(getattr(session, "root_ref", None))
    canonical = _live_object(getattr(session, "canonical_ref", None))
    runtime = _live_object(getattr(session, "runtime_ref", None))
    scene = _session_scene(session, root)
    scene_name = scene.name if scene is not None else ""
    if (
        root is not None
        and canonical is not None
        and runtime is canonical
        and registered_name == root.name
        and session.root_name == root.name
        and session.runtime_name == runtime.name
        and session.canonical_name == canonical.name
        and int(getattr(session, "root_preview_id", 0) or 0)
        == _root_preview_id(root)
        and (not scene_name or scene_name == getattr(session, "scene_name", ""))
        and getattr(session, "binding_object_pointer", 0)
        == _rna_pointer(canonical)
        and getattr(session, "binding_data_pointer", 0)
        == _rna_pointer(canonical.data)
        and _session_armature_matches(session, canonical)
    ):
        session.identity_validated = True
        return root, canonical

    root = _session_root(
        registered_name,
        session,
        allow_recreated=allow_recreated,
    )
    if root is None:
        return None, None
    armature = _model_armature(root)
    if armature is None or not _object_in_scene(armature, scene):
        return None, None
    try:
        armature_owner_is_unique = tuple(armature.users_scene) == (scene,)
    except ReferenceError:
        armature_owner_is_unique = False
    if not armature_owner_is_unique:
        return None, None
    try:
        rebind_session_names(
            root,
            registered_name,
            armature=armature,
            previous_armature_name=session.canonical_name or session.runtime_name,
            allow_recreated=allow_recreated,
        )
    except Exception as error:
        print(f"MMD native Session identity rebind failed for {registered_name}: {error}")
        return None, None
    canonical = session.canonical_object()
    if canonical is not armature:
        return None, None
    session.identity_validated = True
    return root, canonical


def _remove_registered_session(session):
    for key, candidate in tuple(_SESSIONS.items()):
        if candidate is session:
            _SESSIONS.pop(key, None)


def _close_conflicting_session_key(root):
    try:
        session = _SESSIONS.get(root.name)
    except ReferenceError:
        return False
    if session is None or _root_matches_session(root, session):
        return False
    _remove_registered_session(session)
    session.close(restore=False)
    return True


def discard_session(root=None, previous_root_name=None, expected_session=None):
    session = _session_for_root(root)
    if session is None and root is not None:
        session = next(
            (
                candidate
                for candidate in _SESSIONS.values()
                if getattr(candidate, "root_ref", None) is root
            ),
            None,
        )
    if (
        session is None
        and expected_session is not None
        and any(candidate is expected_session for candidate in _SESSIONS.values())
    ):
        session = expected_session
    if session is None:
        return False
    _remove_registered_session(session)
    session.close(restore=False)
    return True


def _resolve_live_source_path(root):
    source_path = Path(str(root.get("spx_mmd_ik_source_pmx", "")))
    if source_path.is_file():
        return source_path
    import_folder = Path(str(root.get("import_folder", "")))
    candidates = tuple(import_folder.glob("*.pmx")) if import_folder.is_dir() else ()
    if len(candidates) == 1:
        root["spx_mmd_ik_source_pmx"] = str(candidates[0])
        return candidates[0]
    return source_path


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _qmul(left, right):
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    value = (
        _f32(_f32(_f32(lw * rx) + _f32(lx * rw)) + _f32(ly * rz) - _f32(lz * ry)),
        _f32(_f32(_f32(lw * ry) - _f32(lx * rz)) + _f32(ly * rw) + _f32(lz * rx)),
        _f32(_f32(_f32(lw * rz) + _f32(lx * ry)) - _f32(ly * rx) + _f32(lz * rw)),
        _f32(_f32(_f32(lw * rw) - _f32(lx * rx)) - _f32(ly * ry) - _f32(lz * rz)),
    )
    length = _f32(math.sqrt(_f32(sum(_f32(item * item) for item in value))))
    return tuple(_f32(item / length) for item in value)


def _mmd_transform(value):
    return (
        float(value.position.x),
        float(value.position.z),
        float(value.position.y),
        -float(value.rotation.x),
        -float(value.rotation.z),
        -float(value.rotation.y),
        float(value.rotation.w),
    )


def _pose_bone_name(pose_bone):
    mmd = getattr(pose_bone, "mmd_bone", None)
    for value in (
        getattr(mmd, "name_j", "") if mmd else "",
        getattr(mmd, "name_e", "") if mmd else "",
        pose_bone.name,
    ):
        if value:
            yield value


def _transform_modal_active():
    window = getattr(bpy.context, "window", None)
    operators = getattr(window, "modal_operators", ()) if window else ()
    return any(
        str(getattr(operator, "bl_idname", "")).startswith("TRANSFORM_OT_")
        for operator in operators
    )


def _transform_modal_pose_matrices(armature):
    if not _transform_modal_active():
        return {}
    active = getattr(bpy.context, "object", None)
    if active is not armature or getattr(active, "mode", "") != "POSE":
        return {}
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
        if pose_bone.bone.select
    }


def _bone_map(armature, solver):
    exact = {pose_bone.name: pose_bone for pose_bone in armature.pose.bones}
    aliases = {}
    for pose_bone in armature.pose.bones:
        for name in _pose_bone_name(pose_bone):
            aliases.setdefault(name, pose_bone)
    return tuple(exact.get(name) or aliases.get(name) for name in solver.names)


def _infer_scale(mapping, solver):
    numerator = 0.0
    denominator = 0.0
    for index, pose_bone in enumerate(mapping):
        if pose_bone is None:
            continue
        source = mmd_position_to_blender(solver.rest_positions[index], 1.0)
        target = pose_bone.bone.head_local
        numerator += source[0] * target.x + source[1] * target.y + source[2] * target.z
        denominator += source[0] ** 2 + source[1] ** 2 + source[2] ** 2
    if denominator <= 1.0e-12:
        raise MMDIKRuntimeError("无法从 PMX 与 Runtime Armature 推导导入缩放")
    scale = numerator / denominator
    if not 1.0e-6 < scale < 1000.0:
        raise MMDIKRuntimeError(f"PMX/Blender 坐标缩放异常：{scale:g}")
    return scale


def _is_generated_constraint(constraint, runtime):
    name = constraint.name.lower()
    if name.startswith("mmd_"):
        return True
    return constraint.type == "IK" and getattr(constraint, "target", None) == runtime


def _mute_generated_constraints(runtime):
    muted = []
    try:
        for pose_bone in runtime.pose.bones:
            for constraint in pose_bone.constraints:
                if not _is_generated_constraint(constraint, runtime):
                    continue
                muted.append((pose_bone.name, constraint.name, bool(constraint.mute)))
                constraint.mute = True
    except Exception:
        _restore_constraints(runtime, muted)
        raise
    return muted


def _restore_constraints(runtime, muted):
    for bone_name, constraint_name, previous in muted:
        pose_bone = runtime.pose.bones.get(bone_name)
        constraint = pose_bone.constraints.get(constraint_name) if pose_bone else None
        if constraint is not None:
            constraint.mute = previous


def _mute_all_constraints(armature):
    muted = []
    for pose_bone in armature.pose.bones:
        for constraint in pose_bone.constraints:
            muted.append((pose_bone.name, constraint.name, bool(constraint.mute)))
            constraint.mute = True
    return muted


def _raw_pose_matrices(armature, bases=None, pose_bones=None):
    matrices = {}

    def resolve(pose_bone):
        cached = matrices.get(pose_bone.name)
        if cached is not None:
            return cached
        rest = pose_bone.bone.matrix_local
        basis = (
            bases.get(pose_bone.name, pose_bone.matrix_basis).copy()
            if bases
            else pose_bone.matrix_basis.copy()
        )
        if pose_bone.parent is None:
            matrix = pose_bone.bone.convert_local_to_pose(basis, rest)
        else:
            matrix = pose_bone.bone.convert_local_to_pose(
                basis,
                rest,
                parent_matrix=resolve(pose_bone.parent),
                parent_matrix_local=pose_bone.parent.bone.matrix_local,
            )
        matrices[pose_bone.name] = matrix
        return matrix

    for pose_bone in pose_bones or armature.pose.bones:
        resolve(pose_bone)
    return matrices


def _live_rotation_to_mmd_rows(matrix):
    return (
        (matrix[0][0], matrix[2][0], matrix[1][0]),
        (matrix[0][2], matrix[2][2], matrix[1][2]),
        (matrix[0][1], matrix[2][1], matrix[1][1]),
    )


def _direct_live_matrix_buffers(session):
    count = len(session.direct_live_bindings)
    position_buffer = getattr(session, "direct_live_position_buffer", None)
    if position_buffer is None or len(position_buffer) != count * 3:
        position_buffer = array("f", [0.0]) * (count * 3)
        session.direct_live_position_buffer = position_buffer
    basis_buffer = getattr(session, "direct_live_basis_buffer", None)
    if basis_buffer is None or len(basis_buffer) != count * 9:
        basis_buffer = array("f", [0.0]) * (count * 9)
        session.direct_live_basis_buffer = basis_buffer
    pose_buffer = getattr(session, "direct_live_pose_buffer", None)
    pose_matrices = getattr(session, "direct_live_pose_matrices", None)
    pose_slots = getattr(session, "direct_live_pose_slots", None)
    rest_matrices = getattr(session, "direct_live_rest_matrices", None)
    canonical = _live_object(getattr(session, "canonical_ref", None))
    if (
        canonical is not None
        and pose_buffer is not None
        and pose_matrices is not None
        and pose_slots is not None
        and rest_matrices is not None
        and len(pose_slots) == count
    ):
        canonical.pose.bones.foreach_get("matrix", pose_buffer)
        heads = np.matmul(
            pose_matrices[pose_slots].transpose((0, 2, 1)),
            rest_matrices,
        )
        positions = np.frombuffer(position_buffer, dtype=np.float32).reshape(
            (-1, 3)
        )
        bases = np.frombuffer(basis_buffer, dtype=np.float32).reshape((-1, 9))
        inverse_scale = 1.0 / session.scale
        positions[:, 0] = heads[:, 0, 3] * inverse_scale
        positions[:, 1] = heads[:, 2, 3] * inverse_scale
        positions[:, 2] = heads[:, 1, 3] * inverse_scale
        bases[:, 0] = heads[:, 0, 0]
        bases[:, 1] = heads[:, 2, 0]
        bases[:, 2] = heads[:, 1, 0]
        bases[:, 3] = heads[:, 0, 2]
        bases[:, 4] = heads[:, 2, 2]
        bases[:, 5] = heads[:, 1, 2]
        bases[:, 6] = heads[:, 0, 1]
        bases[:, 7] = heads[:, 2, 1]
        bases[:, 8] = heads[:, 1, 1]
        return position_buffer, basis_buffer
    inverse_scale = 1.0 / session.scale
    for item, (_index, pose_bone, rest_orientation_inverse) in enumerate(
        session.direct_live_bindings
    ):
        head_transform = pose_bone.matrix @ rest_orientation_inverse
        position = head_transform.translation
        position_offset = item * 3
        position_buffer[position_offset] = position.x * inverse_scale
        position_buffer[position_offset + 1] = position.z * inverse_scale
        position_buffer[position_offset + 2] = position.y * inverse_scale
        basis_offset = item * 9
        basis_buffer[basis_offset] = head_transform[0][0]
        basis_buffer[basis_offset + 1] = head_transform[2][0]
        basis_buffer[basis_offset + 2] = head_transform[1][0]
        basis_buffer[basis_offset + 3] = head_transform[0][2]
        basis_buffer[basis_offset + 4] = head_transform[2][2]
        basis_buffer[basis_offset + 5] = head_transform[1][2]
        basis_buffer[basis_offset + 6] = head_transform[0][1]
        basis_buffer[basis_offset + 7] = head_transform[2][1]
        basis_buffer[basis_offset + 8] = head_transform[1][1]
    return position_buffer, basis_buffer


def _submit_live_pose(session, canonical, scene=None, direct_input=False):
    scene = scene or _session_scene(session)
    if scene is None:
        raise MMDIKRuntimeError("MMD native Session 所属 Scene 已丢失")
    current_frame = (int(scene.frame_current), float(scene.frame_subframe))
    if not session.live_input_dirty and session.live_input_frame == current_frame:
        return False
    session.solver.begin_live_input()
    if direct_input and session.direct_input_isolated:
        positions, bases = _direct_live_matrix_buffers(session)
        session.solver.set_live_matrix_buffers(
            session.live_index_buffer,
            positions,
            bases,
        )
    else:
        matrices = _raw_pose_matrices(
            canonical,
            session.input_basis,
            pose_bones=tuple(pose_bone for _index, pose_bone in session.mapped_order),
        )
        entries = []
        for index, bone_name, rest_orientation_inverse in session.live_bindings:
            pose_matrix = matrices[bone_name]
            head_transform = pose_matrix @ rest_orientation_inverse
            entries.append(
                (
                    index,
                    blender_position_to_mmd(
                        head_transform.translation,
                        session.scale,
                    ),
                    _live_rotation_to_mmd_rows(head_transform),
                )
            )
        session.solver.set_live_matrices(entries)
    session.live_input_dirty = False
    session.live_input_frame = current_frame
    return True


def _live_input_signature(canonical, scene):
    matrix_values = [0.0] * (len(canonical.pose.bones) * 16)
    canonical.pose.bones.foreach_get("matrix_basis", matrix_values)
    return (
        int(scene.frame_current),
        float(scene.frame_subframe),
        *matrix_values,
    )


def _matrix_near_identity(matrix, tolerance=1.0e-6):
    return max(
        abs(matrix[row][column] - (1.0 if row == column else 0.0))
        for row in range(4)
        for column in range(4)
    ) < tolerance


def _cleared_pose_snapshot(canonical, output_basis):
    changed = []
    identity_count = 0
    for name, output in output_basis.items():
        pose_bone = canonical.pose.bones.get(name)
        if pose_bone is None or pose_bone.matrix_basis == output:
            continue
        changed.append(name)
        if _matrix_near_identity(pose_bone.matrix_basis):
            identity_count += 1
    required = max(2, math.ceil(len(output_basis) * 0.2))
    if len(changed) < required or identity_count < math.ceil(len(changed) * 0.9):
        return None
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in canonical.pose.bones
    }


def _action_frame_signature(canonical, frame):
    action = canonical.animation_data.action if canonical.animation_data else None
    if action is None:
        return ()
    values = []
    for curve in action.fcurves:
        if not curve.data_path.startswith('pose.bones["'):
            continue
        for point in curve.keyframe_points:
            if abs(float(point.co.x) - float(frame)) < 1.0e-6:
                values.append(
                    (curve.data_path, int(curve.array_index), float(point.co.y))
                )
                break
    return tuple(values)


def _action_identity(canonical):
    try:
        animation_data = canonical.animation_data
        action = animation_data.action if animation_data else None
        return int(action.as_pointer()) if action is not None else 0
    except ReferenceError:
        return 0


def _basis_channel_values(pose_bone, basis, channel):
    location, rotation, scale = basis.decompose()
    if channel == "location":
        return tuple(location)
    if channel == "scale":
        return tuple(scale)
    if channel == "rotation_quaternion":
        return tuple(rotation)
    if channel == "rotation_euler":
        return tuple(rotation.to_euler(pose_bone.rotation_mode, pose_bone.rotation_euler))
    if channel == "rotation_axis_angle":
        axis, angle = rotation.to_axis_angle()
        return (angle, axis.x, axis.y, axis.z)
    return None


def _export_current_pmx(root, vmd_path=None, scene=None, view_layer=None):
    scene = scene or _owner_scene(root)
    view_layer = view_layer or _owner_view_layer(
        scene,
        required_object=root,
    )
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        selected = tuple(bpy.context.selected_objects)
        active = view_layer.objects.active
        mode = active.mode if active is not None else "OBJECT"
        root_hidden = root.hide_get(view_layer=view_layer)
        if active is not None and mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            root.hide_set(False, view_layer=view_layer)
            root.select_set(True)
            view_layer.objects.active = root
            with tempfile.TemporaryDirectory(prefix="mmd-native-live-") as directory:
                path = Path(directory) / "current_model.pmx"
                result = bpy.ops.mmd_tools.export_pmx(
                    filepath=str(path),
                    scale=12.5,
                    copy_textures_mode="NONE",
                    fix_bone_order=False,
                    sort_materials=False,
                    sort_vertices="NONE",
                )
                if result != {"FINISHED"} or not path.is_file():
                    raise MMDIKRuntimeError("无法自动生成 native 求值所需的 PMX 定义")
                return NativeBoneSolver(path, vmd_path)
        finally:
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            root.hide_set(root_hidden, view_layer=view_layer)
            for obj in selected:
                if view_layer.objects.get(obj.name) is obj:
                    obj.select_set(True)
            if (
                active is not None
                and view_layer.objects.get(active.name) is active
            ):
                view_layer.objects.active = active
                if mode != "OBJECT":
                    bpy.ops.object.mode_set(mode=mode)


@dataclass
class Session:
    root_name: str
    runtime_name: str
    pmx_path: str
    vmd_path: str
    blender_start: int
    vmd_start: int
    solver: NativeBoneSolver
    mapping: tuple
    scale: float
    muted_constraints: list
    original_action: object
    last_vmd_frame: int | None = None
    bone_indices: dict = field(default_factory=dict)
    external_transforms: dict = field(default_factory=dict)
    physics_bind_positions: tuple = ()
    physics_rigid_indices: tuple = ()
    physics_target_bindings: tuple = ()
    physics_feedback_complete: bool = False
    physics_bindings_dirty: bool = False
    canonical_name: str = ""
    live: bool = False
    updating: bool = False
    input_signature: tuple = ()
    output_signature: tuple = ()
    source_vmd: bool = False
    pose_override: bool = False
    input_basis: dict = field(default_factory=dict)
    output_basis: dict = field(default_factory=dict)
    suspended: bool = False
    action_input: bool = False
    action_signature: tuple = ()
    action_identity: int = 0
    solver_matrices: dict = field(default_factory=dict)
    desired_pose: dict = field(default_factory=dict)
    mapped_order: tuple = ()
    mapped_pose_names: frozenset = frozenset()
    live_bindings: tuple = ()
    direct_live_bindings: tuple = ()
    live_index_buffer: object = None
    direct_live_position_buffer: object = None
    direct_live_basis_buffer: object = None
    direct_live_pose_buffer: object = None
    direct_live_pose_matrices: object = None
    direct_live_pose_slots: object = None
    direct_live_rest_matrices: object = None
    live_input_dirty: bool = True
    live_input_frame: tuple | None = None
    pending_input_signature: tuple = ()
    direct_input_isolated: bool = False
    partial_input_basis: bool = False
    blender_override_cache: bool | None = None
    blender_override_modal_active: bool = False
    root_ref: object = None
    runtime_ref: object = None
    canonical_ref: object = None
    root_preview_id: int = 0
    root_pointer: int = 0
    scene_name: str = ""
    scene_pointer: int = 0
    scene_ref: object = None
    view_layer_name: str = ""
    binding_object_pointer: int = 0
    binding_data_pointer: int = 0
    binding_rest_signature: tuple = ()
    binding_revision: int = 0
    binding_mode: str = ""
    identity_validated: bool = False
    closed: bool = False

    def runtime_object(self):
        runtime = _live_object(self.runtime_ref)
        if not _cached_session_armature(self, runtime) and not _session_armature_matches(
            self,
            runtime,
        ):
            runtime = None
        if runtime is None:
            runtime = _session_armature_fallback(self, self.runtime_name)
        if runtime is not None:
            self.runtime_ref = runtime
            self.runtime_name = runtime.name
        return runtime

    def canonical_object(self):
        canonical = _live_object(self.canonical_ref)
        if not _cached_session_armature(
            self,
            canonical,
        ) and not _session_armature_matches(self, canonical):
            canonical = None
        if canonical is None:
            canonical = _session_armature_fallback(
                self,
                self.canonical_name or self.runtime_name
            )
        if canonical is not None:
            self.canonical_ref = canonical
            self.canonical_name = canonical.name
        return canonical

    def _prepare_binding_payload(self, mapping):
        mapped_order = tuple(
            sorted(
                (
                    (index, pose_bone)
                    for index, pose_bone in enumerate(mapping)
                    if pose_bone is not None
                ),
                key=lambda item: len(item[1].parent_recursive),
            )
        )
        mapped_pose_names = frozenset(
            pose_bone.name for _index, pose_bone in mapped_order
        )
        bindings = tuple(
            (
                index,
                pose_bone,
                pose_bone.name,
                pose_bone.bone.matrix_local.to_3x3().to_4x4().inverted_safe(),
            )
            for index, pose_bone in mapped_order
        )
        live_bindings = tuple(
            (index, bone_name, rest_orientation_inverse)
            for index, _pose_bone, bone_name, rest_orientation_inverse in bindings
        )
        direct_live_bindings = tuple(
            (index, pose_bone, rest_orientation_inverse)
            for index, pose_bone, _bone_name, rest_orientation_inverse in bindings
        )
        bone_indices = {}
        for index, pose_bone in enumerate(mapping):
            if pose_bone is None:
                continue
            bone_indices[pose_bone.name] = index
            for alias in _pose_bone_name(pose_bone):
                bone_indices.setdefault(alias, index)
        return (
            mapped_order,
            mapped_pose_names,
            live_bindings,
            direct_live_bindings,
            tuple(binding[0] for binding in bindings),
            bone_indices,
        )

    def _install_binding_payload(self, payload, live_index_buffer, canonical):
        (
            self.mapped_order,
            self.mapped_pose_names,
            self.live_bindings,
            self.direct_live_bindings,
            _live_indices,
            self.bone_indices,
        ) = payload
        self.live_index_buffer = live_index_buffer
        pose_bones = canonical.pose.bones
        pose_slots = {
            pose_bone.name: index for index, pose_bone in enumerate(pose_bones)
        }
        self.direct_live_pose_buffer = array("f", [0.0]) * (
            len(pose_bones) * 16
        )
        self.direct_live_pose_matrices = np.frombuffer(
            self.direct_live_pose_buffer,
            dtype=np.float32,
        ).reshape((-1, 4, 4))
        self.direct_live_pose_slots = np.asarray(
            [
                pose_slots[pose_bone.name]
                for _index, pose_bone, _rest in self.direct_live_bindings
            ],
            dtype=np.intp,
        )
        self.direct_live_rest_matrices = np.asarray(
            [
                tuple(value for row in rest for value in row)
                for _index, _pose_bone, rest in self.direct_live_bindings
            ],
            dtype=np.float64,
        ).reshape((-1, 4, 4))
        self.direct_live_position_buffer = array("f", [0.0]) * (
            len(self.direct_live_bindings) * 3
        )
        self.direct_live_basis_buffer = array("f", [0.0]) * (
            len(self.direct_live_bindings) * 9
        )
        self.live_input_dirty = True
        self.live_input_frame = None
        self.pending_input_signature = ()
        self.output_signature = ()
        self.partial_input_basis = False
        self.blender_override_cache = None
        self.blender_override_modal_active = False

    def refresh_hotpath_bindings(self, canonical):
        payload = self._prepare_binding_payload(self.mapping)
        live_index_buffer = self.solver.prepare_live_matrix_indices(payload[4])
        self._install_binding_payload(payload, live_index_buffer, canonical)
        self.binding_object_pointer = _rna_pointer(canonical)
        self.binding_data_pointer = _rna_pointer(canonical.data)
        self.binding_rest_signature = _armature_rest_signature(canonical)
        self.binding_revision += 1

    def rebuild_bindings(self, canonical, rest_signature=None):
        mapping = _bone_map(canonical, self.solver)
        if not any(pose_bone is not None for pose_bone in mapping):
            return False
        scale = _infer_scale(mapping, self.solver)
        payload = self._prepare_binding_payload(mapping)
        captured_input = (
            {
                pose_bone.name: pose_bone.matrix_basis.copy()
                for pose_bone in canonical.pose.bones
            }
            if self.live
            else None
        )
        if rest_signature is None:
            rest_signature = _armature_rest_signature(canonical)

        self.solver.reset()
        self.solver.clear_external_transforms()
        live_index_buffer = self.solver.prepare_live_matrix_indices(payload[4])

        self.mapping = mapping
        self.scale = scale
        self._install_binding_payload(payload, live_index_buffer, canonical)
        if captured_input is not None:
            self.input_basis = captured_input
        self.output_basis.clear()
        self.input_signature = ()
        self.action_signature = ()
        self.action_identity = 0
        self.solver_matrices.clear()
        self.desired_pose.clear()
        self.external_transforms.clear()
        self.physics_bind_positions = ()
        self.physics_rigid_indices = ()
        self.physics_target_bindings = ()
        self.physics_feedback_complete = False
        self.physics_bindings_dirty = True
        self.last_vmd_frame = None
        self.pose_override = bool(self.live)
        self.binding_object_pointer = _rna_pointer(canonical)
        self.binding_data_pointer = _rna_pointer(canonical.data)
        self.binding_rest_signature = rest_signature
        self.binding_revision += 1
        return True

    def set_direct_input_isolated(self, enabled):
        enabled = bool(enabled)
        if self.direct_input_isolated == enabled:
            return False
        self.direct_input_isolated = enabled
        self.live_input_dirty = True
        self.live_input_frame = None
        return True

    def reconcile_input_basis(self, canonical, scene, signature=None):
        previous_signature = self.input_signature
        was_partial = self.partial_input_basis
        self.input_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in canonical.pose.bones
        }
        self.input_signature = (
            signature
            if signature is not None
            else _live_input_signature(canonical, scene)
        )
        self.partial_input_basis = False
        self.pending_input_signature = ()
        if was_partial or self.input_signature != previous_signature:
            self.pose_override = True
            self.live_input_dirty = True
        return self.input_signature

    def _capture_external_pose(
        self,
        canonical,
        scene,
        known_signature=None,
        direct_input=False,
        basis_updates=None,
    ):
        if not self.input_signature:
            return False
        current_frame = (int(scene.frame_current), float(scene.frame_subframe))
        if self.input_signature[:2] != current_frame:
            return False
        signature = (
            known_signature
            if known_signature is not None
            else _live_input_signature(canonical, scene)
        )
        if signature == self.input_signature:
            return False
        if direct_input:
            if basis_updates is None:
                basis_updates = _transform_modal_pose_matrices(canonical)
            if basis_updates and self.input_basis:
                self.input_basis.update(basis_updates)
                self.partial_input_basis = True
            else:
                self.reconcile_input_basis(
                    canonical,
                    scene,
                    signature=signature,
                )
        else:
            self.partial_input_basis = False
            cleared = _cleared_pose_snapshot(canonical, self.output_basis)
            if cleared is not None:
                self.input_basis = cleared
            else:
                for name, output in self.output_basis.items():
                    pose_bone = canonical.pose.bones.get(name)
                    source = self.input_basis.get(name)
                    if (
                        pose_bone is None
                        or source is None
                        or pose_bone.matrix_basis == output
                    ):
                        continue
                    delta = output.inverted_safe() @ pose_bone.matrix_basis
                    self.input_basis[name] = source @ delta
        self.pose_override = True
        self.input_signature = signature
        self.live_input_dirty = True
        return True

    def _refresh_live_frame_input(
        self,
        canonical,
        scene,
        direct_input=False,
        basis_updates=None,
    ):
        current_frame = (int(scene.frame_current), float(scene.frame_subframe))
        previous_frame = self.input_signature[:2] if self.input_signature else None
        new_frame = previous_frame != current_frame
        was_override = self.pose_override
        known_signature = None
        if direct_input:
            pending = self.pending_input_signature
            self.pending_input_signature = ()
            if pending and pending[:2] == current_frame:
                known_signature = pending
        else:
            self.pending_input_signature = ()
        if not self.input_basis or new_frame:
            self.input_basis = {
                pose_bone.name: pose_bone.matrix_basis.copy()
                for pose_bone in canonical.pose.bones
            }
            self.partial_input_basis = False
            self.input_signature = (
                known_signature
                if known_signature is not None
                else _live_input_signature(canonical, scene)
            )
            self.live_input_dirty = True
        if self.source_vmd and new_frame:
            self.pose_override = False
        elif not new_frame:
            self._capture_external_pose(
                canonical,
                scene,
                known_signature=known_signature,
                direct_input=direct_input,
                basis_updates=basis_updates,
            )
        return new_frame, was_override

    def _desired_output_matrices(self, pose_names=None):
        desired = {}
        for index, pose_bone in self.mapped_order:
            if pose_names is not None and pose_bone.name not in pose_names:
                continue
            values = self.solver.matrix(index)
            if (
                self.solver_matrices.get(index) != values
                or pose_bone.name not in self.desired_pose
            ):
                self.solver_matrices[index] = values
                self.desired_pose[pose_bone.name] = blender_pose_matrix(
                    values,
                    self.scale,
                    pose_bone.bone.matrix_local,
                )
            desired[pose_bone.name] = self.desired_pose[pose_bone.name]
        return desired

    def resolved_output_pose(
        self,
        runtime,
        pose_bones,
        basis_overrides=None,
        matrix_overrides=None,
    ):
        ordered = tuple(pose_bones)
        pose_names = {pose_bone.name for pose_bone in ordered}
        desired = self._desired_output_matrices(pose_names)
        basis_overrides = basis_overrides or {}
        matrix_overrides = matrix_overrides or {}
        resolved = {}
        altered = set()
        for pose_bone in ordered:
            name = pose_bone.name
            parent = pose_bone.parent
            parent_matrix = resolved.get(parent.name) if parent is not None else None
            matrix_override = matrix_overrides.get(name)
            basis_override = basis_overrides.get(name)
            target = desired.get(name)
            if matrix_override is not None:
                matrix = matrix_override.copy()
            elif basis_override is not None or target is None:
                basis = (
                    basis_override
                    if basis_override is not None
                    else pose_bone.matrix_basis
                )
                if parent is None:
                    matrix = pose_bone.bone.convert_local_to_pose(
                        basis,
                        pose_bone.bone.matrix_local,
                    )
                else:
                    matrix = pose_bone.bone.convert_local_to_pose(
                        basis,
                        pose_bone.bone.matrix_local,
                        parent_matrix=parent_matrix,
                        parent_matrix_local=parent.bone.matrix_local,
                    )
            elif parent is None or parent.name not in altered:
                matrix = target
            else:
                basis = pose_bone.bone.convert_local_to_pose(
                    target,
                    pose_bone.bone.matrix_local,
                    parent_matrix=desired.get(parent.name, parent.matrix),
                    parent_matrix_local=parent.bone.matrix_local,
                    invert=True,
                )
                matrix = pose_bone.bone.convert_local_to_pose(
                    basis,
                    pose_bone.bone.matrix_local,
                    parent_matrix=parent_matrix,
                    parent_matrix_local=parent.bone.matrix_local,
                )
            resolved[name] = matrix
            reference = target if target is not None else pose_bone.matrix
            if (
                (parent is not None and parent.name in altered)
                or matrix != reference
            ):
                altered.add(name)
        return resolved

    def _apply_output(self, runtime, scene, update=True, sync_state=True):
        preserved = _transform_modal_pose_matrices(runtime)
        mapped = self.mapped_order
        desired = self._desired_output_matrices()
        changed = set()
        for index, pose_bone in mapped:
            parent = pose_bone.parent
            if parent is None:
                needs_write = pose_bone.matrix != desired[pose_bone.name]
            else:
                needs_write = (
                    parent.name in changed
                    or pose_bone.matrix != desired[pose_bone.name]
                )
            if not needs_write:
                continue
            if parent is None:
                basis = pose_bone.bone.convert_local_to_pose(
                    desired[pose_bone.name], pose_bone.bone.matrix_local, invert=True
                )
            else:
                basis = pose_bone.bone.convert_local_to_pose(
                    desired[pose_bone.name],
                    pose_bone.bone.matrix_local,
                    parent_matrix=desired.get(parent.name, parent.matrix),
                    parent_matrix_local=parent.bone.matrix_local,
                    invert=True,
                )
            if pose_bone.matrix_basis != basis:
                pose_bone.matrix_basis = basis
                changed.add(pose_bone.name)
        for name, matrix in sorted(
            preserved.items(),
            key=lambda item: len(runtime.pose.bones[item[0]].parent_recursive),
        ):
            pose_bone = runtime.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix
        runtime.update_tag(refresh={"OBJECT"})
        if update:
            _session_view_layer(
                self,
                scene,
                required_object=runtime,
            ).update()
        if sync_state:
            self.output_basis = {
                pose_bone.name: pose_bone.matrix_basis.copy()
                for _index, pose_bone in mapped
            }
            self.input_signature = _live_input_signature(runtime, scene)
            self.output_signature = self.input_signature
            self.action_signature = _action_frame_signature(
                runtime, scene.frame_current
            )
            self.action_identity = _action_identity(runtime)
            self.pending_input_signature = ()

    def sync_output_pose(
        self,
        canonical,
        scene,
        known_signature=None,
        direct_input=False,
    ):
        signature = (
            known_signature
            if known_signature is not None
            else _live_input_signature(canonical, scene)
        )
        if direct_input:
            changed = signature != self.output_signature
            self.input_signature = signature
            self.output_signature = signature
            return changed
        if signature == self.output_signature:
            return False
        self.output_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in canonical.pose.bones
            if pose_bone.name in self.bone_indices
        }
        self.input_signature = signature
        self.output_signature = signature
        self.action_signature = _action_frame_signature(
            canonical, scene.frame_current
        )
        self.action_identity = _action_identity(canonical)
        return True

    def repair_current_action_keys(self, canonical, frame):
        action = canonical.animation_data.action if canonical.animation_data else None
        if action is None:
            self.action_signature = ()
            self.action_identity = 0
            return False
        paths = {
            pose_bone.path_from_id(): pose_bone
            for pose_bone in canonical.pose.bones
        }
        changed = False
        for curve in action.fcurves:
            owner_path, separator, channel = curve.data_path.rpartition(".")
            pose_bone = paths.get(owner_path) if separator else None
            basis = self.input_basis.get(pose_bone.name) if pose_bone else None
            values = (
                _basis_channel_values(pose_bone, basis, channel)
                if basis is not None
                else None
            )
            if values is None or curve.array_index >= len(values):
                continue
            for point in curve.keyframe_points:
                if abs(float(point.co.x) - float(frame)) >= 1.0e-6:
                    continue
                expected = float(values[curve.array_index])
                if abs(float(point.co.y) - expected) > 1.0e-7:
                    point.co.y = expected
                    changed = True
                break
        if changed:
            action.update_tag()
        self.action_signature = _action_frame_signature(canonical, frame)
        self.action_identity = _action_identity(canonical)
        return changed

    def restore_input(self, update=True):
        canonical = self.canonical_object()
        if canonical is None:
            return
        scene = _session_scene(self)
        if self.partial_input_basis and scene is not None:
            self.reconcile_input_basis(canonical, scene)
        was_updating = self.updating
        self.updating = True
        self.pending_input_signature = ()
        try:
            for name, matrix in self.input_basis.items():
                pose_bone = canonical.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix
            canonical.update_tag(refresh={"OBJECT"})
            if update:
                _session_view_layer(
                    self,
                    scene,
                    required_object=canonical,
                ).update()
        finally:
            self.updating = was_updating

    def close(self, restore=True):
        if getattr(self, "closed", False):
            return
        self.closed = True
        errors = []
        runtime = None
        if restore and self.live:
            try:
                self.restore_input()
            except Exception as error:
                errors.append(error)
        if restore:
            try:
                runtime = self.runtime_object()
            except Exception as error:
                errors.append(error)
        if runtime is not None:
            try:
                _restore_constraints(runtime, self.muted_constraints)
            except Exception as error:
                errors.append(error)
            try:
                if runtime.animation_data is not None:
                    runtime.animation_data.action = self.original_action
            except Exception as error:
                errors.append(error)
        try:
            self.solver.close()
        except Exception as error:
            errors.append(error)
        if errors:
            raise errors[0]

    def target_frame(self, scene):
        return self.vmd_start + int(scene.frame_current) - self.blender_start

    def capture_physics_bindings(self, preview_session):
        from collections import defaultdict, deque

        from ..physics_preview.runtime import _mmd_physics_name, _read_pmx_physics

        self.physics_bind_positions = ()
        self.physics_rigid_indices = ()
        self.physics_target_bindings = ()
        self.physics_feedback_complete = False
        target_bindings = []
        for rigid_index, rigid in enumerate(preview_session.rigids):
            bone_name = rigid.mmd_rigid.bone
            bone_index = self.bone_indices.get(bone_name) if bone_name else None
            if bone_index is None:
                continue
            source = _mmd_transform(
                preview_session.body_descs[rigid_index].bone_transform
            )
            rest = self.solver.rest_positions[bone_index]
            target_bindings.append(
                (
                    rigid_index,
                    bone_index,
                    tuple(_f32(source[index] - rest[index]) for index in range(3)),
                    source[3:],
                    int(rigid.mmd_rigid.type),
                )
            )
        self.physics_target_bindings = tuple(target_bindings)
        if not Path(self.pmx_path).is_file():
            self.physics_bindings_dirty = False
            return False
        _model_name, source_rigids, _source_joints = _read_pmx_physics(
            self.pmx_path
        )
        source_indices = defaultdict(deque)
        for index, source in enumerate(source_rigids):
            source_indices[source[0]].append(index)
        self.physics_rigid_indices = tuple(
            source_indices[
                _mmd_physics_name(rigid, "mmd_rigid")
            ].popleft()
            if source_indices[_mmd_physics_name(rigid, "mmd_rigid")]
            else None
            for rigid in preview_session.rigids
        )
        self.physics_feedback_complete = (
            len(preview_session.rigids) == len(source_rigids) == self.solver.rigid_count
            and all(index is not None for index in self.physics_rigid_indices)
            and len(set(self.physics_rigid_indices)) == len(source_rigids)
        )
        dll = preview_session.solver.library.dll
        if not hasattr(dll, "mmd_solver_get_basis_transforms"):
            self.physics_bind_positions = ()
            self.physics_bindings_dirty = False
            return any(index is not None for index in self.physics_rigid_indices)
        transforms = preview_session.solver.basis_transforms()
        start = preview_session.body_offset
        local = transforms[start : start + len(preview_session.rigids)]
        self.physics_bind_positions = tuple(
            (float(item.position.x), float(item.position.y), float(item.position.z))
            for item in local
        )
        self.physics_bindings_dirty = False
        return any(index is not None for index in self.physics_rigid_indices)

    def corrected_rigid_position(
        self,
        preview_rigid_index,
        native_rigid_index,
        target,
    ):
        if (
            preview_rigid_index >= len(self.physics_bind_positions)
            or native_rigid_index >= len(self.solver.rigid_positions)
        ):
            return target
        bind = self.physics_bind_positions[preview_rigid_index]
        source = self.solver.rigid_positions[native_rigid_index]
        return tuple(
            _f32(_f32(bind[index] - source[index]) + target[index])
            for index in range(3)
        )

    def evaluate_to(self, scene):
        if self.live:
            return self.evaluate_live(scene)
        runtime = self.runtime_object()
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        target = max(self.vmd_start, self.target_frame(scene))
        if self.last_vmd_frame is None or target < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
            first = self.vmd_start
        elif target == self.last_vmd_frame:
            first = target + 1
        else:
            first = int(self.last_vmd_frame) + 1
        for frame in range(first, target + 1):
            self.solver.evaluate(frame)
        self.last_vmd_frame = target
        self._apply_output(runtime, scene)

    def evaluate_live(self, scene, update=True):
        if self.updating or self.suspended:
            return float(scene.frame_current)
        runtime = self.runtime_object()
        canonical = self.canonical_object()
        if runtime is None or canonical is None:
            raise MMDIKRuntimeError("MMD native 接管骨架已丢失")
        self.updating = True
        try:
            new_frame, was_override = self._refresh_live_frame_input(
                canonical,
                scene,
            )
            target = self.target_frame(scene) if self.source_vmd else float(scene.frame_current)
            if self.source_vmd and not self.pose_override and not self.action_input:
                self.solver.end_live_input()
                self.live_input_dirty = True
                if was_override or self.last_vmd_frame is None or target < self.last_vmd_frame:
                    self.solver.reset()
                    first = int(self.vmd_start)
                else:
                    first = int(self.last_vmd_frame) + 1
                for frame in range(first, int(target) + 1):
                    self.solver.evaluate(float(frame))
                if target != int(target):
                    self.solver.evaluate(float(target))
            else:
                _submit_live_pose(self, canonical, scene)
                self.solver.evaluate(float(target))
            self.last_vmd_frame = float(target)
            self._apply_output(runtime, scene, update=update)
        finally:
            self.updating = False
        return float(scene.frame_current)

    def evaluate_exact(
        self,
        frame,
        apply_output=True,
        update=True,
        sync_state=True,
        scene=None,
        direct_input=False,
        basis_updates=None,
    ):
        scene = scene or _session_scene(self)
        if scene is None:
            raise MMDIKRuntimeError("MMD native Session 所属 Scene 已丢失")
        runtime = self.runtime_object()
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        if self.live:
            canonical = self.canonical_object()
            if canonical is None:
                raise MMDIKRuntimeError("MMD native 控制骨架已丢失")
            self._refresh_live_frame_input(
                canonical,
                scene,
                direct_input=direct_input,
                basis_updates=basis_updates,
            )
            uses_source_vmd = bool(
                self.source_vmd and not self.pose_override and not self.action_input
            )
            if uses_source_vmd:
                self.solver.end_live_input()
                self.live_input_dirty = True
            else:
                _submit_live_pose(
                    self,
                    canonical,
                    scene,
                    direct_input=direct_input,
                )
        else:
            uses_source_vmd = False
        frame = max(float(self.vmd_start), float(frame))
        if self.last_vmd_frame is not None and frame < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
            self.live_input_dirty = True
            if self.live and not uses_source_vmd:
                _submit_live_pose(
                    self,
                    canonical,
                    scene,
                    direct_input=direct_input,
                )
        self.solver.evaluate(frame)
        self.last_vmd_frame = frame
        if apply_output:
            self._apply_output(
                runtime,
                scene,
                update=update,
                sync_state=sync_state,
            )
        return frame

    def evaluate_before_physics(
        self,
        frame,
        apply_output=True,
        update=True,
        sync_state=True,
        scene=None,
        direct_input=False,
        basis_updates=None,
    ):
        scene = scene or _session_scene(self)
        if scene is None:
            raise MMDIKRuntimeError("MMD native Session 所属 Scene 已丢失")
        runtime = self.runtime_object()
        if runtime is None:
            raise MMDIKRuntimeError("MMD IK Runtime Armature 已丢失")
        if self.live:
            canonical = self.canonical_object()
            if canonical is None:
                raise MMDIKRuntimeError("MMD native 控制骨架已丢失")
            self._refresh_live_frame_input(
                canonical,
                scene,
                direct_input=direct_input,
                basis_updates=basis_updates,
            )
            uses_source_vmd = bool(
                self.source_vmd and not self.pose_override and not self.action_input
            )
            if uses_source_vmd:
                self.solver.end_live_input()
                self.live_input_dirty = True
            else:
                _submit_live_pose(
                    self,
                    canonical,
                    scene,
                    direct_input=direct_input,
                )
        else:
            uses_source_vmd = False
        frame = max(float(self.vmd_start), float(frame))
        if self.last_vmd_frame is not None and frame < self.last_vmd_frame:
            self.solver.reset()
            self.external_transforms.clear()
            self.live_input_dirty = True
            if self.live and not uses_source_vmd:
                _submit_live_pose(
                    self,
                    canonical,
                    scene,
                    direct_input=direct_input,
                )
        self.solver.evaluate_before_physics(frame)
        self.last_vmd_frame = frame
        if apply_output:
            self._apply_output(
                runtime,
                scene,
                update=update,
                sync_state=sync_state,
            )
        return frame

    def has_blender_overrides(self, use_cache=False):
        if use_cache:
            if not self.blender_override_modal_active:
                self.blender_override_cache = None
            self.blender_override_modal_active = True
            if self.blender_override_cache is not None:
                return self.blender_override_cache
        else:
            self.blender_override_modal_active = False
            self.blender_override_cache = None
        runtime = self.runtime_object()
        if runtime is None:
            self.blender_override_cache = False
            return False
        owner = runtime
        while owner is not None:
            if owner.animation_data is not None and owner.animation_data.drivers:
                self.blender_override_cache = True
                return True
            if any(not constraint.mute for constraint in owner.constraints):
                self.blender_override_cache = True
                return True
            if owner is runtime and owner.parent_type == "BONE":
                self.blender_override_cache = True
                return True
            owner = owner.parent
        armature_data = runtime.data
        if (
            armature_data.animation_data is not None
            and armature_data.animation_data.drivers
        ):
            self.blender_override_cache = True
            return True
        result = any(
            not constraint.mute
            for pose_bone in runtime.pose.bones
            for constraint in pose_bone.constraints
        )
        self.blender_override_cache = result
        return result


def _initialize_session_identity(session, root, armature, scene, view_layer):
    session.root_ref = root
    session.runtime_ref = armature
    session.canonical_ref = armature
    session.binding_mode = armature.mode
    session.root_preview_id = _root_preview_id(root)
    session.root_pointer = _rna_pointer(root)
    session.scene_name = scene.name
    session.scene_pointer = _rna_pointer(scene)
    session.scene_ref = scene
    session.view_layer_name = view_layer.name


def _cleanup_failed_start(
    session,
    solver,
    runtime,
    muted_constraints,
    original_action,
    original_basis,
):
    errors = []
    if session is not None:
        _remove_registered_session(session)
        try:
            session.close()
        except Exception as error:
            errors.append(error)
    else:
        if runtime is not None:
            try:
                _restore_constraints(runtime, muted_constraints)
            except Exception as error:
                errors.append(error)
            try:
                if runtime.animation_data is not None:
                    runtime.animation_data.action = original_action
            except Exception as error:
                errors.append(error)
        if solver is not None:
            try:
                solver.close()
            except Exception as error:
                errors.append(error)
    if runtime is not None and original_basis:
        try:
            for name, matrix in original_basis.items():
                pose_bone = runtime.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix
            runtime.update_tag(refresh={"OBJECT"})
        except Exception as error:
            errors.append(error)
    for error in errors:
        print(f"MMD native evaluator start cleanup failed: {error}")


def start(root, pmx_path, vmd_path, blender_start=1, vmd_start=0):
    state = runtime_state(root)
    runtime = canonical_armature(root, state) if state and state.get("enabled") else None
    if runtime is None:
        raise MMDIKRuntimeError("请先启用 MMD IK 兼容")
    pmx = Path(bpy.path.abspath(str(pmx_path)))
    vmd = Path(bpy.path.abspath(str(vmd_path)))
    if not pmx.is_file():
        raise MMDIKRuntimeError(f"源 PMX 不存在：{pmx}")
    if not vmd.is_file():
        raise MMDIKRuntimeError(f"VMD 动作不存在：{vmd}")
    scene = _owner_scene(root)
    view_layer = _owner_view_layer(scene, required_object=runtime)
    stop(root)
    _close_conflicting_session_key(root)
    solver = None
    session = None
    muted = []
    original_action = runtime.animation_data.action if runtime.animation_data else None
    original_basis = {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in runtime.pose.bones
    }
    try:
        solver = NativeBoneSolver(pmx, vmd)
        mapping = _bone_map(runtime, solver)
        matched = sum(item is not None for item in mapping)
        if not matched:
            raise MMDIKRuntimeError("PMX 骨名与 Runtime Armature 完全不匹配")
        scale = _infer_scale(mapping, solver)
        muted = _mute_generated_constraints(runtime)
        session = Session(
            root.name,
            runtime.name,
            str(pmx),
            str(vmd),
            int(blender_start),
            int(vmd_start),
            solver,
            mapping,
            scale,
            muted,
            original_action,
        )
        _initialize_session_identity(session, root, runtime, scene, view_layer)
        for index, pose_bone in enumerate(mapping):
            if pose_bone is None:
                continue
            session.bone_indices[pose_bone.name] = index
            for alias in _pose_bone_name(pose_bone):
                session.bone_indices.setdefault(alias, index)
        session.refresh_hotpath_bindings(runtime)
        session.evaluate_to(scene)
        root["spx_mmd_ik_source_pmx"] = str(pmx)
        _SESSIONS[root.name] = session
        return matched, solver.count, scale
    except Exception:
        _cleanup_failed_start(
            session,
            solver,
            runtime,
            muted,
            original_action,
            original_basis,
        )
        raise


def start_live(root, input_basis=None, update=True):
    state = runtime_state(root)
    canonical = canonical_armature(root, state) if state else None
    if not state or not state.get("enabled") or canonical is None:
        raise MMDIKRuntimeError("请先启用 MMD IK 兼容")
    scene = _owner_scene(root)
    view_layer = _owner_view_layer(scene, required_object=canonical)
    stop(root)
    _close_conflicting_session_key(root)
    source_path = _resolve_live_source_path(root)
    action = canonical.animation_data.action if canonical.animation_data else None
    source_vmd = Path(str(action.get(SOURCE_VMD_KEY, ""))) if action is not None else Path()
    has_source_vmd = bool(action is not None and source_vmd.is_file())
    solver = None
    session = None
    muted = []
    original_basis = {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in canonical.pose.bones
    }
    try:
        if source_path.is_file():
            solver = NativeBoneSolver(
                source_path,
                source_vmd if has_source_vmd else None,
            )
        else:
            solver = _export_current_pmx(
                root,
                source_vmd if has_source_vmd else None,
                scene=scene,
                view_layer=view_layer,
            )
        mapping = _bone_map(canonical, solver)
        matched = sum(item is not None for item in mapping)
        if not matched:
            raise MMDIKRuntimeError("当前模型与 native PMX 骨名完全不匹配")
        scale = _infer_scale(mapping, solver)
        session = Session(
            root_name=root.name,
            runtime_name=canonical.name,
            pmx_path=(
                str(source_path) if source_path.is_file() else "<current model>"
            ),
            vmd_path=str(source_vmd) if has_source_vmd else "",
            blender_start=(
                int(action.get(SOURCE_FRAME_KEY, 1)) if has_source_vmd else 1
            ),
            vmd_start=0,
            solver=solver,
            mapping=mapping,
            scale=scale,
            muted_constraints=muted,
            original_action=None,
            canonical_name=canonical.name,
            live=True,
            source_vmd=has_source_vmd,
            action_input=bool(state.get("action_input", False)),
            input_basis={
                name: matrix.copy()
                for name, matrix in (
                    input_basis.items()
                    if input_basis is not None
                    else (
                        (pose_bone.name, pose_bone.matrix_basis)
                        for pose_bone in canonical.pose.bones
                    )
                )
            },
        )
        _initialize_session_identity(session, root, canonical, scene, view_layer)
        for index, pose_bone in enumerate(mapping):
            if pose_bone is None:
                continue
            session.bone_indices[pose_bone.name] = index
            for alias in _pose_bone_name(pose_bone):
                session.bone_indices.setdefault(alias, index)
        session.refresh_hotpath_bindings(canonical)
        session.evaluate_live(scene, update=update)
        _SESSIONS[root.name] = session
        return matched, solver.count, scale
    except Exception:
        _cleanup_failed_start(
            session,
            solver,
            canonical,
            muted,
            None,
            original_basis,
        )
        raise


def stop(root):
    if root is None:
        return
    session = _session_for_root(root)
    if session is not None:
        for key, candidate in tuple(_SESSIONS.items()):
            if candidate is session:
                _SESSIONS.pop(key, None)
        session.close()


def is_active(root):
    return _session_for_root(root) is not None


def enable_action_input(root):
    session = _session_for_root(root)
    if session is None or not session.live:
        return False
    session.action_input = True
    session.live_input_dirty = True
    set_action_input(root, True)
    return True


def replay_live(root, scene=None):
    session = _session_for_root(root)
    if session is None or not session.live:
        return False
    session.restore_input()
    session.last_vmd_frame = None
    session.pose_override = False
    session.input_signature = ()
    session.pending_input_signature = ()
    session.live_input_dirty = True
    target_scene = scene or _session_scene(session, root)
    if target_scene is None:
        raise MMDIKRuntimeError("MMD native Session 所属 Scene 已丢失")
    session.evaluate_live(target_scene)
    return True


def capture_live_input(root):
    session = _session_for_root(root)
    if session is None or not session.live:
        return None
    if session.partial_input_basis:
        canonical = session.canonical_object()
        scene = _session_scene(session, root)
        if canonical is not None and scene is not None:
            session.reconcile_input_basis(canonical, scene)
    return {name: matrix.copy() for name, matrix in session.input_basis.items()}


def restore_live_input(root, snapshot):
    session = _session_for_root(root)
    canonical = session.canonical_object() if session and session.live else None
    if canonical is None or snapshot is None:
        return False
    session.input_basis = {name: matrix.copy() for name, matrix in snapshot.items()}
    session.partial_input_basis = False
    session.pending_input_signature = ()
    session.live_input_dirty = True
    for name, matrix in snapshot.items():
        pose_bone = canonical.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.matrix_basis = matrix
    canonical.update_tag(refresh={"OBJECT"})
    return True


def detach_all_sessions():
    errors = []
    for root_name, session in tuple(_SESSIONS.items()):
        try:
            try:
                if session.live:
                    session.restore_input()
            finally:
                session.solver.close()
        except Exception as error:
            errors.append(error)
        finally:
            _SESSIONS.pop(root_name, None)
    if errors:
        raise errors[0]


def suspend_sessions_for_undo_redo():
    errors = []
    for session in tuple(_SESSIONS.values()):
        if not session.live:
            continue
        session.suspended = True
        session.set_direct_input_isolated(False)
        try:
            session.restore_input(update=False)
        except Exception as error:
            errors.append(error)
    if errors:
        raise errors[0]


def resume_sessions_after_undo_redo(scene=None):
    rebuild_required = False
    for root_name, session in tuple(_SESSIONS.items()):
        root = _session_root(root_name, session, allow_recreated=True)
        if root is not None:
            rebind_session_names(
                root,
                root_name,
                armature=_model_armature(root),
                allow_recreated=True,
            )
        session_scene = _session_scene(session, root) if root is not None else None
        state = runtime_state(root) if root is not None else None
        canonical = _model_armature(root) if state else None
        source_path = _resolve_live_source_path(root) if root else Path()
        if (
            not session.live
            or not state
            or not state.get("enabled")
            or canonical is None
            or session_scene is None
            or not source_path.is_file()
            or source_path.resolve() != Path(session.pmx_path).resolve()
        ):
            session.solver.close()
            _remove_registered_session(session)
            rebuild_required = True
            continue
        refresh_bindings(root)
        binding_revision = session.binding_revision
        refresh_session_bindings(root, canonical, check_rest=True)
        if not any(item is not None for item in session.mapping):
            session.solver.close()
            _remove_registered_session(session)
            rebuild_required = True
            continue
        session.input_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in canonical.pose.bones
        }
        session.output_basis.clear()
        session.input_signature = ()
        session.action_signature = ()
        session.action_identity = 0
        session.solver_matrices.clear()
        session.desired_pose.clear()
        session.external_transforms.clear()
        session.physics_bind_positions = ()
        session.physics_rigid_indices = ()
        session.physics_target_bindings = ()
        session.physics_feedback_complete = False
        session.physics_bindings_dirty = True
        session.last_vmd_frame = None
        session.pose_override = True
        if session.binding_revision == binding_revision:
            session.solver.reset()
            session.solver.clear_external_transforms()
        session.suspended = False
        session.evaluate_live(session_scene, update=False)
    if rebuild_required:
        rebuild_enabled_sessions()


def rebuild_enabled_sessions():
    rebuilt = []
    for root in tuple(bpy.data.objects):
        if getattr(root, "mmd_type", "") != "ROOT":
            continue
        state = runtime_state(root)
        if not state or not state.get("enabled") or _session_for_root(root) is not None:
            continue
        try:
            refresh_bindings(root)
            start_live(root)
        except Exception as error:
            print(f"MMD native live evaluator rebuild failed for {root.name}: {error}")
            continue
        rebuilt.append(root.name)
    return tuple(rebuilt)


def suspend_live(root):
    session = _session_for_root(root)
    if session is None or not session.live:
        return False
    session.suspended = True
    session.restore_input()
    return True


def resume_live(root):
    session = _session_for_root(root)
    if session is None or not session.live:
        return False
    session.suspended = False
    replay_live(root)
    return True


def capture_physics_bindings(root, preview_session):
    session = _session_for_root(root)
    return bool(session and session.capture_physics_bindings(preview_session))


def _physics_model_translation(preview_session):
    current = getattr(preview_session, "ik_motion_anchor", None)
    origin = getattr(preview_session, "motion_anchor_origin", None)
    if current is None:
        current = preview_session.armature.matrix_world
    if origin is None:
        origin = preview_session.saved_armature_matrix
    return blender_position_to_mmd(
        current.translation - origin.translation,
        preview_session.import_scale,
    )


def submit_physics_feedback(
    root,
    preview_session,
    transforms=None,
    update=True,
    apply_output=True,
    sync_state=True,
):
    session = _session_for_root(root)
    if session is None or not session.physics_feedback_complete:
        return 0
    start = preview_session.body_offset
    dll = preview_session.solver.library.dll
    raw_basis = hasattr(dll, "mmd_solver_get_basis_transforms")
    source = preview_session.solver.basis_transforms() if raw_basis else transforms
    if source is None:
        source = preview_session.solver.transforms()
    local = source[start : start + len(preview_session.rigids)]
    model_translation = _physics_model_translation(preview_session)
    submitted = 0
    mmd_matrix_entries = []
    mmd_external_states = []
    for rigid_index, (rigid, transform) in enumerate(zip(preview_session.rigids, local)):
        if int(rigid.mmd_rigid.type) == 0 or not rigid.mmd_rigid.bone:
            continue
        native_rigid_index = (
            session.physics_rigid_indices[rigid_index]
            if rigid_index < len(session.physics_rigid_indices)
            else None
        )
        if native_rigid_index is None:
            continue
        if raw_basis:
            position = (transform.position.x, transform.position.y, transform.position.z)
            if preview_session.solver_target == "MMD":
                position = tuple(
                    position[index] - model_translation[index]
                    for index in range(3)
                )
            state = (
                position,
                tuple(transform.basis_row_major),
            )
            if preview_session.solver_target == "MMD":
                mmd_matrix_entries.append(
                    (native_rigid_index, state[0], state[1])
                )
                mmd_external_states.append((native_rigid_index, state))
            else:
                session.solver.set_external_rigid_matrix(
                    native_rigid_index,
                    state[0],
                    state[1],
                )
        else:
            state = (
                (transform.position.x, transform.position.z, transform.position.y),
                (
                    -transform.rotation.x,
                    -transform.rotation.z,
                    -transform.rotation.y,
                    transform.rotation.w,
                ),
            )
            session.solver.set_external_rigid_transform(
                native_rigid_index,
                state[0],
                state[1],
            )
        if not (raw_basis and preview_session.solver_target == "MMD"):
            session.external_transforms[native_rigid_index] = state
        submitted += 1
    if preview_session.solver_target == "MMD":
        if mmd_matrix_entries:
            session.solver.set_external_rigid_matrices_mmd(mmd_matrix_entries)
            session.external_transforms.update(mmd_external_states)
        session.solver.evaluate_after_physics()
    else:
        session.solver.commit_external()
    runtime = session.runtime_object()
    if apply_output and runtime is not None:
        session._apply_output(
            runtime,
            preview_session.scene,
            update=update,
            sync_state=sync_state,
        )
    return submitted


def evaluate_physics_pose(
    root,
    preview_session,
    vmd_frame=None,
    update=True,
    apply_output=True,
    sync_state=True,
    direct_input=False,
    basis_updates=None,
):
    session = _session_for_root(root)
    if session is None:
        return None
    if preview_session.solver_target == "MMD" and preview_session.mmd_step_count <= 3:
        session.external_transforms.clear()
        session.solver.clear_external_transforms()
    if vmd_frame is None:
        vmd_frame = (
            session.vmd_start
            + preview_session.scene.frame_current
            + preview_session.scene.frame_subframe
            - session.blender_start
        )
    if preview_session.solver_target == "MMD":
        session.evaluate_before_physics(
            vmd_frame,
            apply_output=apply_output,
            update=update,
            sync_state=sync_state,
            scene=preview_session.scene,
            direct_input=direct_input,
            basis_updates=basis_updates,
        )
    else:
        session.evaluate_exact(
            vmd_frame,
            apply_output=apply_output,
            update=update,
            sync_state=sync_state,
            scene=preview_session.scene,
            direct_input=direct_input,
            basis_updates=basis_updates,
        )
    return float(vmd_frame)


def uses_direct_pose_input(root, preview_session, use_cached_overrides=False):
    session = _session_for_root(root)
    return bool(
        session
        and not session.has_blender_overrides(
            use_cache=use_cached_overrides,
        )
    )


def uses_exact_physics_targets(root, preview_session):
    return bool(
        preview_session.solver_target == "MMD"
        and uses_direct_pose_input(root, preview_session)
    )


def resolve_physics_pose(
    root,
    preview_session,
    pose_bones,
    basis_overrides=None,
    matrix_overrides=None,
):
    session = _session_for_root(root)
    if session is None or not uses_direct_pose_input(root, preview_session):
        return None
    return session.resolved_output_pose(
        preview_session.armature,
        pose_bones,
        basis_overrides=basis_overrides,
        matrix_overrides=matrix_overrides,
    )


def prepare_physics_targets(root, preview_session, exact_targets=None):
    session = _session_for_root(root)
    if exact_targets is None:
        exact_targets = uses_exact_physics_targets(root, preview_session)
    if session is None or not exact_targets:
        return 0
    from ..physics_preview.ffi import Quat, Transform, Vec3

    dll = preview_session.solver.library.dll
    raw_targets = hasattr(dll, "mmd_solver_set_body_target_basis")
    model_translation = _physics_model_translation(preview_session)
    submissions = []
    position_corrections = []
    bindings = session.physics_target_bindings
    bone_transforms = session.solver.transforms(
        binding[1] for binding in bindings
    )
    for binding, bone_transform in zip(bindings, bone_transforms):
        rigid_index, _bone_index, base_position, source_rotation, rigid_mode = binding
        x, y, z, qx, qy, qz, qw = bone_transform
        position = (
            _f32(base_position[0] + x),
            _f32(base_position[1] + y),
            _f32(base_position[2] + z),
        )
        delta = (qx, qy, qz, qw)
        rotation = (
            source_rotation
            if delta == (0.0, 0.0, 0.0, 1.0)
            else _qmul(delta, source_rotation)
        )
        physics_position = tuple(
            position[index] + model_translation[index]
            for index in range(3)
        )
        submissions.append(
            (
                preview_session.body_offset + rigid_index,
                Transform(
                    Vec3(
                        physics_position[0],
                        physics_position[2],
                        physics_position[1],
                    ),
                    Quat(-rotation[0], -rotation[2], -rotation[1], rotation[3]),
                ),
            )
        )
        native_rigid_index = (
            session.physics_rigid_indices[rigid_index]
            if rigid_index < len(session.physics_rigid_indices)
            else None
        )
        if rigid_mode == 0 and raw_targets and native_rigid_index is not None:
            position_corrections.append((rigid_index, native_rigid_index))
    preview_session.solver.set_bone_targets(submissions)
    rigid_targets = session.solver.rigid_targets(
        correction[1] for correction in position_corrections
    )
    for correction, target in zip(position_corrections, rigid_targets):
        rigid_index, native_rigid_index = correction
        corrected = session.corrected_rigid_position(
            rigid_index,
            native_rigid_index,
            target[:3],
        )
        preview_session.solver.set_body_target_position(
            preview_session.body_offset + rigid_index,
            tuple(
                corrected[index] + model_translation[index]
                for index in range(3)
            ),
        )
    return len(submissions)


def clear_physics_feedback(root):
    session = _session_for_root(root)
    if session is None:
        return
    session.external_transforms.clear()
    session.pending_input_signature = ()
    session.set_direct_input_isolated(False)
    session.solver.clear_external_transforms()


@persistent
def _frame_change_pre(scene, _depsgraph=None):
    stale = []
    for root_name, session in tuple(_SESSIONS.items()):
        root, canonical = _registered_session_objects(root_name, session)
        if root is None or (session.live and canonical is None):
            stale.append((session, False))
            continue
        if scene.objects.get(root.name) is not root:
            continue
        if session.live and scene.objects.get(canonical.name) is not canonical:
            continue
        if session.live:
            session.restore_input(update=False)
            continue
        try:
            session.evaluate_to(scene)
        except Exception as error:
            print(f"MMD IK evaluator stopped for {root_name}: {error}")
            stale.append((session, True))
    for session, restore in stale:
        _remove_registered_session(session)
        session.close(restore=restore)


@persistent
def _frame_change_post(scene, _depsgraph=None):
    for root_name, session in tuple(_SESSIONS.items()):
        if not session.live or session.updating or session.suspended:
            continue
        root, canonical = _registered_session_objects(root_name, session)
        if root is None or canonical is None:
            _remove_registered_session(session)
            session.close(restore=False)
            continue
        if (
            scene.objects.get(root.name) is not root
            or scene.objects.get(canonical.name) is not canonical
        ):
            continue
        try:
            session.evaluate_live(scene)
        except Exception as error:
            print(f"MMD native live evaluator stopped for {root_name}: {error}")
            _remove_registered_session(session)
            session.close()


@persistent
def _depsgraph_update_post(scene, _depsgraph=None):
    armature_updated = _depsgraph_type_updated(_depsgraph, "ARMATURE")
    action_updated = _depsgraph_type_updated(_depsgraph, "ACTION")
    collection_updated = _depsgraph_type_updated(_depsgraph, "COLLECTION")
    scene_updated = _depsgraph_type_updated(_depsgraph, "SCENE")
    has_update_records = bool(
        _depsgraph is not None and getattr(_depsgraph, "updates", None) is not None
    )
    stale = []
    for root_name, session in tuple(_SESSIONS.items()):
        if not session.live or session.updating or session.suspended:
            continue
        root_ref = _live_object(getattr(session, "root_ref", None))
        canonical_ref = _live_object(getattr(session, "canonical_ref", None))
        owner_scene = _live_scene(getattr(session, "scene_ref", None))
        owner_scene_event = owner_scene is None or owner_scene is scene
        current_frame = (
            (int(scene.frame_current), float(scene.frame_subframe))
            if owner_scene_event
            else None
        )
        frame_changed = (
            owner_scene_event
            and (
                not session.input_signature
                or session.input_signature[:2] != current_frame
            )
        )
        if has_update_records:
            root_updated = _depsgraph_id_updated(_depsgraph, root_ref)
            canonical_object_updated = _depsgraph_id_updated(
                _depsgraph,
                canonical_ref,
            )
            canonical_data_updated = _depsgraph_id_updated(
                _depsgraph,
                getattr(canonical_ref, "data", None),
            )
            identity_updated = bool(
                root_ref is None
                or canonical_ref is None
                or root_updated
                or canonical_object_updated
                or canonical_data_updated
                or collection_updated
                or scene_updated
            )
            pose_input_updated = bool(
                canonical_object_updated or canonical_data_updated
            )
        else:
            object_updated = _depsgraph_type_updated(_depsgraph, "OBJECT")
            canonical_data_updated = armature_updated
            identity_updated = bool(
                root_ref is None
                or canonical_ref is None
                or _depsgraph is None
                or object_updated
                or armature_updated
                or collection_updated
                or scene_updated
            )
            pose_input_updated = armature_updated
        if not identity_updated and not action_updated and not frame_changed:
            continue
        root, canonical = _registered_session_objects(root_name, session)
        if root is None or canonical is None:
            stale.append((session, False))
            continue
        if (
            scene.objects.get(root.name) is not root
            or scene.objects.get(canonical.name) is not canonical
        ):
            continue
        canonical_mode = canonical.mode
        binding_data_updated = canonical_data_updated
        check_rest = bool(
            binding_data_updated
            and (
                canonical_mode == "EDIT"
                or getattr(session, "binding_mode", "") == "EDIT"
            )
        )
        session.binding_mode = canonical_mode
        if check_rest:
            try:
                refresh_session_bindings(root, canonical, check_rest=True)
                canonical = session.canonical_object()
            except Exception as error:
                print(
                    f"MMD native live evaluator binding refresh failed for "
                    f"{root_name}: {error}"
                )
                stale.append((session, True))
                continue
        action_identity = _action_identity(canonical)
        action_maybe_changed = bool(
            action_updated
            or action_identity != getattr(session, "action_identity", 0)
            or frame_changed
        )
        if not pose_input_updated and not action_maybe_changed:
            continue
        signature = _live_input_signature(canonical, scene)
        action_changed = False
        if action_maybe_changed:
            action_signature = _action_frame_signature(
                canonical, scene.frame_current
            )
            action_changed = action_signature != session.action_signature
            if not action_changed:
                session.action_identity = action_identity
        if action_changed:
            session.repair_current_action_keys(canonical, scene.frame_current)
            session.action_input = True
            set_action_input(root, True)
        if signature == session.input_signature and not action_changed:
            continue
        try:
            from ..physics_preview.runtime import is_running

            if is_running(root):
                direct_input = bool(
                    getattr(session, "direct_input_isolated", False)
                )
                basis_updates = (
                    _transform_modal_pose_matrices(canonical)
                    if direct_input
                    else None
                )
                capture_signature = signature
                if direct_input and action_changed:
                    capture_signature = _live_input_signature(canonical, scene)
                session._capture_external_pose(
                    canonical,
                    scene,
                    known_signature=(
                        capture_signature
                        if direct_input
                        else signature
                        if not action_changed
                        else None
                    ),
                    direct_input=direct_input,
                    basis_updates=basis_updates,
                )
                if direct_input:
                    session.pending_input_signature = capture_signature
            else:
                session.evaluate_live(scene, update=False)
        except Exception as error:
            print(f"MMD native live evaluator stopped for {root_name}: {error}")
            stale.append((session, True))
    for session, restore in stale:
        _remove_registered_session(session)
        session.close(restore=restore)


def install_handler():
    if _frame_change_pre not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_frame_change_pre)
    if _depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_update_post)
    if _frame_change_post not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_frame_change_post)


def uninstall_handler():
    if _frame_change_pre in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(_frame_change_pre)
    if _depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_update_post)
    if _frame_change_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_frame_change_post)
    errors = []
    for session in tuple(dict.fromkeys(_SESSIONS.values())):
        _remove_registered_session(session)
        try:
            session.close()
        except Exception as error:
            errors.append(error)
    if errors:
        raise errors[0]
