import hashlib
import json
import pathlib
import shutil
import struct
import tempfile
import uuid
import zlib

import bpy
from bpy.app.handlers import persistent

from .ffi import ABI_VERSION


CACHE_SCHEMA = 1
CHECKPOINT_INTERVAL = 10
_MAGIC = b"MSPC0001"
_CACHE_PATHS = {}


def _cache_directory(blend_path=None):
    blend_path = pathlib.Path(blend_path or bpy.data.filepath) if (blend_path or bpy.data.filepath) else None
    if blend_path is None:
        return pathlib.Path(tempfile.gettempdir()) / "mmd_station_unsaved_cache"
    return blend_path.parent / f"{blend_path.name}.mmd_station_cache" / "physics"


def cache_id(action, create=False):
    value = str(action.get("mmd_station_physics_cache_id", "")) if action is not None else ""
    if not value and create:
        value = uuid.uuid4().hex
        action["mmd_station_physics_cache_id"] = value
    return value


def cache_path(action, create=False, blend_path=None):
    value = cache_id(action, create=create)
    if not value:
        return None
    return _cache_directory(blend_path) / f"{value}.mspc"


def _hash_value(digest, value):
    data = str(value).encode("utf-8", "surrogatepass")
    digest.update(struct.pack("<I", len(data)))
    digest.update(data)


def _ctypes_value(value):
    fields = getattr(type(value), "_fields_", None)
    if fields is not None:
        return tuple(
            (name, _ctypes_value(getattr(value, name)))
            for name, *_field_type in fields
        )
    if hasattr(value, "_length_"):
        return tuple(_ctypes_value(item) for item in value)
    return getattr(value, "value", value)


def context_hash(root, source_action, session, settings):
    digest = hashlib.sha256()
    _hash_value(digest, CACHE_SCHEMA)
    _hash_value(digest, ABI_VERSION)
    _hash_value(digest, root.name)
    _hash_value(digest, source_action.get("mmd_station_action_uid", ""))
    _hash_value(digest, session.solver_target)
    _hash_value(digest, session.import_scale)
    _hash_value(digest, tuple(float(value) for value in settings.preview_gravity))
    _hash_value(digest, int(settings.preview_substeps))
    for rigid, desc in zip(session.rigids, session.body_descs, strict=True):
        _hash_value(digest, rigid.name)
        _hash_value(
            digest,
            (
                desc.mode,
                desc.shape,
                _ctypes_value(desc.size),
                desc.mass,
                desc.linear_damping,
                desc.angular_damping,
                desc.restitution,
                desc.friction,
                desc.collision_group,
                desc.collision_mask,
                rigid.mmd_rigid.bone,
                tuple(rigid.get("mmd_station_physics_rest_matrix", ())),
            ),
        )
    for joint, desc in zip(session.joints, session.joint_descs, strict=True):
        _hash_value(digest, joint.name)
        _hash_value(
            digest,
            (
                desc.body_a,
                desc.body_b,
                _ctypes_value(desc.linear_lower),
                _ctypes_value(desc.linear_upper),
                _ctypes_value(desc.angular_lower),
                _ctypes_value(desc.angular_upper),
                _ctypes_value(desc.linear_spring),
                _ctypes_value(desc.angular_spring),
                tuple(joint.get("mmd_station_physics_rest_matrix", ())),
            ),
        )
    for curve in sorted(
        source_action.fcurves,
        key=lambda item: (item.data_path, item.array_index),
    ):
        _hash_value(digest, curve.data_path)
        _hash_value(digest, curve.array_index)
        _hash_value(digest, curve.mute)
        for point in curve.keyframe_points:
            _hash_value(
                digest,
                (
                    float(point.co.x),
                    float(point.co.y),
                    point.interpolation,
                    point.easing,
                    tuple(point.handle_left),
                    tuple(point.handle_right),
                    point.handle_left_type,
                    point.handle_right_type,
                ),
            )
    return digest.hexdigest()


def write_cache(action, header, checkpoints):
    path = cache_path(action, create=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = dict(header)
    header.update(
        schema=CACHE_SCHEMA,
        snapshot_abi=ABI_VERSION,
        checkpoint_interval=CHECKPOINT_INTERVAL,
    )
    header_bytes = json.dumps(
        header,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(_MAGIC)
        stream.write(struct.pack("<I", len(header_bytes)))
        stream.write(header_bytes)
        stream.write(struct.pack("<I", len(checkpoints)))
        for frame, snapshot in sorted(checkpoints.items()):
            snapshot = bytes(snapshot)
            compressed = zlib.compress(snapshot, level=1)
            stream.write(struct.pack("<iII", int(frame), len(snapshot), len(compressed)))
            stream.write(compressed)
    temporary.replace(path)
    _CACHE_PATHS[cache_id(action)] = path
    action["mmd_station_physics_cache_frames"] = len(checkpoints)
    return path


def read_cache(action, expected_hash=None):
    value = cache_id(action)
    if not value:
        return None, {}
    candidates = []
    tracked = _CACHE_PATHS.get(value)
    if tracked is not None:
        candidates.append(pathlib.Path(tracked))
    expected_path = cache_path(action)
    if expected_path is not None and expected_path not in candidates:
        candidates.append(expected_path)
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        return None, {}
    try:
        with path.open("rb") as stream:
            if stream.read(len(_MAGIC)) != _MAGIC:
                return None, {}
            header_size_data = stream.read(4)
            if len(header_size_data) != 4:
                return None, {}
            header_size = struct.unpack("<I", header_size_data)[0]
            header = json.loads(stream.read(header_size).decode("utf-8"))
            if (
                int(header.get("schema", 0)) != CACHE_SCHEMA
                or int(header.get("snapshot_abi", 0)) != ABI_VERSION
                or expected_hash is not None
                and str(header.get("context_hash", "")) != str(expected_hash)
            ):
                return None, {}
            count_data = stream.read(4)
            if len(count_data) != 4:
                return None, {}
            checkpoints = {}
            for _index in range(struct.unpack("<I", count_data)[0]):
                record = stream.read(12)
                if len(record) != 12:
                    return None, {}
                frame, raw_size, compressed_size = struct.unpack("<iII", record)
                snapshot = zlib.decompress(stream.read(compressed_size))
                if len(snapshot) != raw_size:
                    return None, {}
                checkpoints[frame] = snapshot
    except (OSError, ValueError, TypeError, json.JSONDecodeError, zlib.error):
        return None, {}
    _CACHE_PATHS[value] = path
    return header, checkpoints


def nearest_checkpoint(checkpoints, frame, strictly_before=False):
    candidates = [
        value
        for value in checkpoints
        if value < frame or not strictly_before and value <= frame
    ]
    return max(candidates) if candidates else None


def remove_cache(action):
    value = cache_id(action)
    paths = {cache_path(action), _CACHE_PATHS.pop(value, None)}
    for path in paths:
        if path is not None:
            try:
                pathlib.Path(path).unlink(missing_ok=True)
            except OSError:
                pass


@persistent
def _save_cache_sidecars(_dummy):
    if not bpy.data.filepath:
        return
    destination_directory = _cache_directory()
    for action in bpy.data.actions:
        value = cache_id(action)
        if not value:
            continue
        destination = destination_directory / f"{value}.mspc"
        source = _CACHE_PATHS.get(value)
        if source is None:
            source = destination
        source = pathlib.Path(source)
        if source.is_file() and source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        if destination.is_file():
            _CACHE_PATHS[value] = destination


@persistent
def _load_cache_sidecars(_dummy):
    _CACHE_PATHS.clear()
    for action in bpy.data.actions:
        path = cache_path(action)
        if path is not None and path.is_file():
            _CACHE_PATHS[cache_id(action)] = path


def _initialize_cache_sidecars():
    try:
        _load_cache_sidecars(None)
    except AttributeError as error:
        if "_RestrictData" not in str(error):
            raise
        return 0.1
    return None


def register_services():
    if _save_cache_sidecars not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_save_cache_sidecars)
    if _save_cache_sidecars not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_save_cache_sidecars)
    if _load_cache_sidecars not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_cache_sidecars)
    if not bpy.app.timers.is_registered(_initialize_cache_sidecars):
        bpy.app.timers.register(_initialize_cache_sidecars, first_interval=0.1)


def unregister_services():
    if bpy.app.timers.is_registered(_initialize_cache_sidecars):
        bpy.app.timers.unregister(_initialize_cache_sidecars)
    for handlers, callback in (
        (bpy.app.handlers.save_pre, _save_cache_sidecars),
        (bpy.app.handlers.save_post, _save_cache_sidecars),
        (bpy.app.handlers.load_post, _load_cache_sidecars),
    ):
        if callback in handlers:
            handlers.remove(callback)
    _CACHE_PATHS.clear()
