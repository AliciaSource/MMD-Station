import json
import uuid
from typing import NamedTuple

import bpy
import numpy as np
from mathutils import Matrix


_OWNER_KEY = "spx_physics_preview_debug_batch_owner"
_KIND_KEY = "spx_physics_preview_debug_batch_kind"
_SCENE_KEY = "spx_physics_preview_debug_batch_scene"
_SOURCE_COLLECTIONS_KEY = "spx_physics_preview_debug_batch_collections"
_SOURCE_HIDE_VIEWPORT_KEY = "spx_physics_preview_debug_batch_hide_viewport"
_RECOVERY_KEY = "spx_physics_preview_debug_batch_recovery"
_RECOVERY_SCENE_KEY = "spx_physics_preview_debug_batch_recovery_scene"
_PARKING_NAME_PREFIX = ".SPX Physics Preview Debug Parking"
_RIGID_NAME_PREFIX = ".SPX Physics Preview Rigid Debug"
_JOINT_NAME_PREFIX = ".SPX Physics Preview Joint Debug"
_RECOVERY_NAME_PREFIX = ".SPX Physics Preview Recovered"
_LIVE_BATCHES = {}
_SUPPORTED_JOINT_DISPLAY_TYPES = frozenset(("ARROWS",))
_ARROW_SHAFT_FRACTION = 0.75
_ARROW_HEAD_RADIUS_FRACTION = 0.035


class _UnsupportedBatch(RuntimeError):
    pass


class _SourceState(NamedTuple):
    source: object
    collections: tuple
    collection_names: tuple
    hide_viewport: bool


class _RigidGeometry(NamedTuple):
    vertices: tuple
    edges: tuple
    faces: tuple
    vertex_owner: object
    local_h: object
    materials: tuple
    polygon_material_indices: tuple
    smooth_flags: tuple
    display_state: tuple


class _JointGeometry(NamedTuple):
    vertices: tuple
    edges: tuple
    vertex_owner: object
    local_h: object


class _BatchPlan(NamedTuple):
    scene: object
    source_rigids: tuple
    source_joints: tuple
    source_states: tuple
    kinematic_rigids: tuple
    slow_rigids: tuple
    static_rigids: tuple
    slow_joints: tuple
    static_joints: tuple
    kinematic_rigid_geometry: object
    slow_rigid_geometry: object
    static_rigid_geometry: object
    slow_joint_geometry: object
    static_joint_geometry: object


class _RigidPartition:
    def __init__(self, sources, output, mesh, geometry):
        self.sources = sources
        self.object = output
        self.mesh = mesh
        self.vertex_owner = geometry.vertex_owner
        self.local_h = geometry.local_h
        self.matrices = np.empty((len(sources), 4, 4), dtype=np.float64)
        self.owned_matrices = np.empty((len(self.local_h), 3, 4), dtype=np.float64)
        self.coordinates = np.empty((len(self.local_h), 3), dtype=np.float64)
        self.values = np.empty(len(self.local_h) * 3, dtype=np.float32)
        self.helper_counts = (
            len(geometry.vertices),
            len(geometry.edges),
            len(geometry.faces),
            sum(len(face) for face in geometry.faces),
            len(geometry.materials),
        )
        self.display_state = _display_state(output)

    def update(self, matrix_mapping):
        values = _transform_vertices(
            self.local_h,
            self.vertex_owner,
            _matrix_array(self.sources, matrix_mapping, self.matrices),
            self.owned_matrices,
            self.coordinates,
            self.values,
        )
        if len(self.mesh.vertices):
            self.mesh.vertices.foreach_set("co", values)
        self.mesh.update_gpu_tag()


class _JointPartition:
    def __init__(self, sources, output, mesh, geometry):
        self.sources = sources
        self.object = output
        self.mesh = mesh
        self.vertex_owner = geometry.vertex_owner
        self.local_h = geometry.local_h
        self.matrices = np.empty((len(sources), 4, 4), dtype=np.float64)
        self.owned_matrices = np.empty((len(self.local_h), 3, 4), dtype=np.float64)
        self.coordinates = np.empty((len(self.local_h), 3), dtype=np.float64)
        self.values = np.empty(len(self.local_h) * 3, dtype=np.float32)
        self.helper_counts = (
            len(geometry.vertices),
            len(geometry.edges),
            0,
            0,
        )
        self.display_state = (
            output.display_type,
            bool(output.show_in_front),
            bool(output.hide_render),
            bool(output.hide_select),
        )

    def update(self, matrix_mapping):
        values = _transform_vertices(
            self.local_h,
            self.vertex_owner,
            _matrix_array(self.sources, matrix_mapping, self.matrices),
            self.owned_matrices,
            self.coordinates,
            self.values,
        )
        if len(self.mesh.vertices):
            self.mesh.vertices.foreach_set("co", values)
        self.mesh.update_gpu_tag()


def _same_rna(first, second):
    if first is second:
        return True
    try:
        return first.as_pointer() == second.as_pointer()
    except (AttributeError, ReferenceError):
        return False


def _live_id(collection, item):
    try:
        return item is not None and collection.get(item.name) is item
    except (AttributeError, ReferenceError):
        return False


def _local_id(item):
    return bool(
        item is not None
        and item.library is None
        and getattr(item, "override_library", None) is None
    )


def _single_scene_object(obj, scene):
    try:
        users = tuple(obj.users_scene)
    except (AttributeError, ReferenceError):
        return False
    return len(users) == 1 and _same_rna(users[0], scene)


def _id_pointer(item):
    try:
        return int(item.as_pointer()) if item is not None else 0
    except (AttributeError, ReferenceError):
        return 0


def _live_scene(scene):
    return scene if _live_id(bpy.data.scenes, scene) else None


def _direct_collection_object(collection, obj):
    try:
        return len(obj.users_collection) == 1 and _same_rna(
            obj.users_collection[0],
            collection,
        )
    except (AttributeError, ReferenceError):
        return False


def _collection_scene_signature(collection):
    if not _live_id(bpy.data.collections, collection):
        return None
    owners = []
    for scene in bpy.data.scenes:
        try:
            if _same_rna(scene.collection, collection) or any(
                _same_rna(candidate, collection)
                for candidate in scene.collection.children_recursive
            ):
                owners.append(_id_pointer(scene))
        except ReferenceError:
            continue
    return (collection.name, tuple(sorted(owners)))


def _scene_contains_collection(scene, collection):
    if scene is None or collection is None:
        return False
    try:
        return _same_rna(scene.collection, collection) or any(
            _same_rna(candidate, collection)
            for candidate in scene.collection.children_recursive
        )
    except (AttributeError, ReferenceError):
        return False


def _recovery_collection(owner_token, scene_name):
    token = str(owner_token or uuid.uuid4().hex)
    for collection in bpy.data.collections:
        if collection.get(_RECOVERY_KEY, "") == token:
            return collection
    label = str(scene_name or "missing scene")
    collection = bpy.data.collections.new(
        f"{_RECOVERY_NAME_PREFIX} [{label}] [{token[:8]}]"
    )
    collection.use_fake_user = True
    collection[_RECOVERY_KEY] = token
    collection[_RECOVERY_SCENE_KEY] = label
    return collection


def _layer_collection_for(layer_collection, collection):
    if _same_rna(layer_collection.collection, collection):
        return layer_collection
    for child in layer_collection.children:
        found = _layer_collection_for(child, collection)
        if found is not None:
            return found
    return None


def _mark(item, owner_token, kind, scene_name):
    item[_OWNER_KEY] = owner_token
    item[_KIND_KEY] = kind
    item[_SCENE_KEY] = scene_name


def _clear_source_marker(source):
    for key in (
        _OWNER_KEY,
        _KIND_KEY,
        _SCENE_KEY,
        _SOURCE_COLLECTIONS_KEY,
        _SOURCE_HIDE_VIEWPORT_KEY,
    ):
        try:
            if key in source:
                del source[key]
        except ReferenceError:
            return


def _display_state(source):
    return (
        source.display_type,
        bool(source.show_wire),
        bool(source.show_all_edges),
        bool(source.show_in_front),
        tuple(float(value) for value in source.color),
    )


def _matrix_signature(matrix):
    try:
        return tuple(float(value) for row in matrix for value in row)
    except (AttributeError, ReferenceError, TypeError):
        return None


def _source_membership_signature(source, scene, parking_collection):
    try:
        return (
            bool(source.hide_viewport),
            _direct_collection_object(parking_collection, source),
            _single_scene_object(source, scene),
        )
    except (AttributeError, ReferenceError):
        return None


def _rigid_quick_signature(source, scene, parking_collection):
    try:
        mesh = source.data
        return (
            source.name,
            source.type,
            _id_pointer(mesh),
            len(mesh.vertices),
            len(mesh.edges),
            len(mesh.polygons),
            _display_state(source),
            _source_membership_signature(source, scene, parking_collection),
            source.get(_OWNER_KEY, ""),
            source.get(_KIND_KEY, ""),
            source.get(_SCENE_KEY, ""),
        )
    except (AttributeError, ReferenceError):
        return None


def _joint_quick_signature(source, scene, parking_collection):
    try:
        return (
            source.name,
            source.type,
            str(source.empty_display_type),
            float(source.empty_display_size),
            _source_membership_signature(source, scene, parking_collection),
            source.get(_OWNER_KEY, ""),
            source.get(_KIND_KEY, ""),
            source.get(_SCENE_KEY, ""),
        )
    except (AttributeError, ReferenceError):
        return None


def _rigid_geometry_signature(source):
    try:
        mesh = source.data
        vertices = tuple(
            component
            for vertex in mesh.vertices
            for component in (float(vertex.co.x), float(vertex.co.y), float(vertex.co.z))
        )
        edges = tuple(
            vertex_index
            for edge in mesh.edges
            for vertex_index in tuple(int(value) for value in edge.vertices)
        )
        polygons = tuple(
            (
                tuple(int(value) for value in polygon.vertices),
                int(polygon.material_index),
                bool(polygon.use_smooth),
                _id_pointer(
                    source.material_slots[polygon.material_index].material
                    if polygon.material_index < len(source.material_slots)
                    else None
                ),
            )
            for polygon in mesh.polygons
        )
        return (vertices, edges, polygons)
    except (AttributeError, ReferenceError):
        return None


def _build_rigid_geometry(sources, fallback_display_state=None):
    vertices = []
    edges = []
    faces = []
    owners = []
    face_materials = []
    smooth_flags = []
    vertex_offset = 0
    states = {_display_state(source) for source in sources}
    if len(states) > 1:
        raise _UnsupportedBatch("Rigid debug objects do not share a display state")
    display_state = (
        next(iter(states))
        if states
        else fallback_display_state
    )
    if display_state is None:
        raise _UnsupportedBatch("Rigid debug partition has no display state")

    for source_index, source in enumerate(sources):
        mesh = source.data
        local_vertices = [tuple(vertex.co) for vertex in mesh.vertices]
        if not local_vertices:
            raise _UnsupportedBatch("Rigid debug mesh has no vertices")
        vertices.extend(local_vertices)
        owners.extend([source_index] * len(local_vertices))
        edges.extend(
            tuple(vertex_offset + vertex_index for vertex_index in edge.vertices)
            for edge in mesh.edges
        )
        for polygon in mesh.polygons:
            faces.append(
                tuple(
                    vertex_offset + vertex_index
                    for vertex_index in polygon.vertices
                )
            )
            material = None
            if polygon.material_index < len(source.material_slots):
                material = source.material_slots[polygon.material_index].material
            face_materials.append(material)
            smooth_flags.append(bool(polygon.use_smooth))
        vertex_offset += len(local_vertices)

    has_material = any(material is not None for material in face_materials)
    if has_material and any(material is None for material in face_materials):
        raise _UnsupportedBatch(
            "Mixed material and material-less rigid faces are unsupported"
        )
    materials = []
    material_slots = {}
    polygon_material_indices = []
    if has_material:
        for material in face_materials:
            pointer = int(material.as_pointer())
            slot = material_slots.get(pointer)
            if slot is None:
                slot = len(materials)
                material_slots[pointer] = slot
                materials.append(material)
            polygon_material_indices.append(slot)
    else:
        polygon_material_indices = [0] * len(faces)

    local_h = np.ones((len(vertices), 4), dtype=np.float64)
    if vertices:
        local_h[:, :3] = np.asarray(vertices, dtype=np.float64)
    return _RigidGeometry(
        tuple(vertices),
        tuple(edges),
        tuple(faces),
        np.asarray(owners, dtype=np.intp),
        local_h,
        tuple(materials),
        tuple(polygon_material_indices),
        tuple(smooth_flags),
        display_state,
    )


def _build_joint_geometry(sources):
    unsupported_types = sorted(
        {
            str(source.empty_display_type)
            for source in sources
            if str(source.empty_display_type)
            not in _SUPPORTED_JOINT_DISPLAY_TYPES
        }
    )
    if unsupported_types:
        raise _UnsupportedBatch(
            "Unsupported joint Empty display type: "
            + ", ".join(unsupported_types)
        )

    vertices = []
    edges = []
    owners = []
    for source_index, source in enumerate(sources):
        size = max(abs(float(source.empty_display_size)), 1.0e-6)
        shaft = size * _ARROW_SHAFT_FRACTION
        radius = size * _ARROW_HEAD_RADIUS_FRACTION
        origin = len(vertices)
        vertices.append((0.0, 0.0, 0.0))
        owners.append(source_index)
        for axis in range(3):
            offset = len(vertices)
            perpendicular = tuple(index for index in range(3) if index != axis)
            tip = [0.0, 0.0, 0.0]
            tip[axis] = size
            vertices.append(tuple(tip))
            for first, second in (
                (radius, 0.0),
                (-0.5 * radius, 0.8660254037844386 * radius),
                (-0.5 * radius, -0.8660254037844386 * radius),
            ):
                wing = [0.0, 0.0, 0.0]
                wing[axis] = shaft
                wing[perpendicular[0]] = first
                wing[perpendicular[1]] = second
                vertices.append(tuple(wing))
            edges.extend(
                (
                    (origin, offset),
                    (offset, offset + 1),
                    (offset, offset + 2),
                    (offset, offset + 3),
                )
            )
            owners.extend([source_index] * 4)
    local_h = np.ones((len(vertices), 4), dtype=np.float64)
    if vertices:
        local_h[:, :3] = np.asarray(vertices, dtype=np.float64)
    return _JointGeometry(
        tuple(vertices),
        tuple(edges),
        np.asarray(owners, dtype=np.intp),
        local_h,
    )


def _source_objects(session):
    rigid_mapping = getattr(session, "saved_rigid_objects", None)
    joint_mapping = getattr(session, "saved_joint_objects", None)
    if not rigid_mapping or joint_mapping is None:
        raise _UnsupportedBatch("Preview session has no saved debug objects")
    rigids = tuple(rigid_mapping.values())
    joints = tuple(joint_mapping.values())
    if not rigids or len(set(rigids).union(joints)) != len(rigids) + len(joints):
        raise _UnsupportedBatch("Saved debug object bindings are incomplete")
    return rigids, joints


def _plan(session):
    scene = getattr(session, "scene", None)
    if not _local_id(scene):
        raise _UnsupportedBatch("Preview scene is not locally editable")
    rigids, joints = _source_objects(session)
    states = []
    for source in (*rigids, *joints):
        if not _local_id(source) or not _single_scene_object(source, scene):
            raise _UnsupportedBatch("Debug source is not exclusive to the preview scene")
        if any(key in source for key in (_OWNER_KEY, _SOURCE_COLLECTIONS_KEY)):
            raise _UnsupportedBatch("Debug source already belongs to a debug batch")
        collections = tuple(source.users_collection)
        if not collections or any(not _local_id(collection) for collection in collections):
            raise _UnsupportedBatch("Debug source collection is not locally editable")
        states.append(
            _SourceState(
                source,
                collections,
                tuple(collection.name for collection in collections),
                bool(source.hide_viewport),
            )
        )
    if any(source.type != "MESH" for source in rigids):
        raise _UnsupportedBatch("Saved rigid debug object is not a Mesh")
    if any(source.type != "EMPTY" for source in joints):
        raise _UnsupportedBatch("Saved joint debug object is not an Empty")
    active_rigids = tuple(getattr(session, "rigids", rigids))
    active_joints = tuple(getattr(session, "joints", joints))
    if (
        len(set(active_rigids)) != len(active_rigids)
        or len(set(active_joints)) != len(active_joints)
        or not set(active_rigids).issubset(rigids)
        or not set(active_joints).issubset(joints)
    ):
        raise _UnsupportedBatch("Active debug bindings do not match saved sources")

    rigid_modes = getattr(session, "rigid_modes", None)
    if rigid_modes is not None and len(rigid_modes) != len(active_rigids):
        raise _UnsupportedBatch("Active rigid mode cache is misaligned")
    bone_offsets = getattr(session, "bone_offsets", {})
    rigid_pose_bones = tuple(getattr(session, "rigid_pose_bones", ()))
    kinematic_rigids = []
    slow_rigids = []
    for index, rigid in enumerate(active_rigids):
        mode = (
            int(rigid_modes[index])
            if rigid_modes is not None
            else int(getattr(getattr(rigid, "mmd_rigid", None), "type", 1))
        )
        pose_bone = (
            rigid_pose_bones[index]
            if index < len(rigid_pose_bones)
            else None
        )
        if mode == 0 and index in bone_offsets and pose_bone is not None:
            kinematic_rigids.append(rigid)
        else:
            slow_rigids.append(rigid)

    active_rigid_set = frozenset(active_rigids)
    active_joint_set = frozenset(active_joints)
    static_rigids = tuple(rigid for rigid in rigids if rigid not in active_rigid_set)
    static_joints = tuple(joint for joint in joints if joint not in active_joint_set)
    kinematic_rigids = tuple(kinematic_rigids)
    slow_rigids = tuple(slow_rigids)
    fallback_display_state = _display_state(rigids[0])
    return _BatchPlan(
        scene,
        rigids,
        joints,
        tuple(states),
        kinematic_rigids,
        slow_rigids,
        static_rigids,
        active_joints,
        static_joints,
        _build_rigid_geometry(kinematic_rigids, fallback_display_state),
        _build_rigid_geometry(slow_rigids, fallback_display_state),
        _build_rigid_geometry(static_rigids, fallback_display_state),
        _build_joint_geometry(active_joints),
        _build_joint_geometry(static_joints),
    )


def _new_rigid_helper(
    scene,
    root_name,
    owner_token,
    geometry,
    partition_label="",
):
    label = f" {partition_label}" if partition_label else ""
    mesh = bpy.data.meshes.new(
        f"{_RIGID_NAME_PREFIX}{label} Mesh [{root_name}]"
    )
    _mark(mesh, owner_token, "rigid-mesh", scene.name)
    mesh.from_pydata(geometry.vertices, geometry.edges, geometry.faces)
    for material in geometry.materials:
        mesh.materials.append(material)
    for polygon, material_index, smooth in zip(
        mesh.polygons,
        geometry.polygon_material_indices,
        geometry.smooth_flags,
    ):
        polygon.material_index = material_index
        polygon.use_smooth = smooth
    mesh.update()

    output = bpy.data.objects.new(
        f"{_RIGID_NAME_PREFIX}{label} [{root_name}]",
        mesh,
    )
    _mark(output, owner_token, "rigid-output", scene.name)
    scene.collection.objects.link(output)
    output.matrix_world = Matrix.Identity(4)
    output.hide_render = True
    output.hide_select = True
    (
        output.display_type,
        output.show_wire,
        output.show_all_edges,
        output.show_in_front,
        output.color,
    ) = geometry.display_state
    return output, mesh


def _new_joint_helper(
    scene,
    root_name,
    owner_token,
    geometry,
    partition_label="",
):
    label = f" {partition_label}" if partition_label else ""
    mesh = bpy.data.meshes.new(
        f"{_JOINT_NAME_PREFIX}{label} Mesh [{root_name}]"
    )
    _mark(mesh, owner_token, "joint-mesh", scene.name)
    mesh.from_pydata(geometry.vertices, geometry.edges, ())
    mesh.update()
    output = bpy.data.objects.new(
        f"{_JOINT_NAME_PREFIX}{label} [{root_name}]",
        mesh,
    )
    _mark(output, owner_token, "joint-output", scene.name)
    scene.collection.objects.link(output)
    output.matrix_world = Matrix.Identity(4)
    output.display_type = "WIRE"
    output.show_in_front = True
    output.hide_render = True
    output.hide_select = True
    return output, mesh


def _new_parking_collection(scene, root_name, owner_token):
    parking = bpy.data.collections.new(
        f"{_PARKING_NAME_PREFIX} [{root_name}]"
    )
    _mark(parking, owner_token, "parking", scene.name)
    scene.collection.children.link(parking)
    parking.hide_viewport = True
    layer_collections = tuple(
        _layer_collection_for(view_layer.layer_collection, parking)
        for view_layer in scene.view_layers
    )
    if any(layer_collection is None for layer_collection in layer_collections):
        raise RuntimeError("Debug parking collection is missing from a ViewLayer")
    return parking, layer_collections


def _restore_targets(
    collection_refs,
    collection_names,
    scene,
    owner_token,
    scene_name,
):
    targets = []
    for collection in collection_refs:
        if _live_id(bpy.data.collections, collection) and collection not in targets:
            targets.append(collection)
    for name in collection_names:
        collection = bpy.data.collections.get(name)
        if collection is not None and collection not in targets:
            targets.append(collection)
    if targets:
        return tuple(targets)
    if scene is not None:
        return (scene.collection,)
    return (_recovery_collection(owner_token, scene_name),)


def _restore_source_state(state, scene, owner_token):
    source = state.source
    if not _live_id(bpy.data.objects, source):
        return False
    try:
        if (
            source.get(_OWNER_KEY, "") != owner_token
            or source.get(_KIND_KEY, "") != "source"
        ):
            return False
    except (AttributeError, ReferenceError):
        return False
    live_scene = _live_scene(scene)
    scene_name = source.get(_SCENE_KEY, "")
    targets = _restore_targets(
        state.collections,
        state.collection_names,
        live_scene,
        owner_token,
        scene_name,
    )
    for collection in targets:
        if source.name not in collection.objects:
            collection.objects.link(source)
    if live_scene is not None and not any(
        _scene_contains_collection(live_scene, target)
        for target in targets
    ):
        if live_scene.collection.objects.get(source.name) is not source:
            live_scene.collection.objects.link(source)
        targets = (*targets, live_scene.collection)
    for collection in tuple(source.users_collection):
        if collection not in targets:
            collection.objects.unlink(source)
    source.hide_viewport = state.hide_viewport
    _clear_source_marker(source)
    return True


def _scene_for_owner(owner_token, marked_items=()):
    for item in marked_items:
        try:
            scene = bpy.data.scenes.get(item.get(_SCENE_KEY, ""))
        except ReferenceError:
            continue
        if scene is not None:
            return scene
    for scene in bpy.data.scenes:
        for collection in scene.collection.children_recursive:
            try:
                if collection.get(_OWNER_KEY, "") == owner_token:
                    return scene
            except ReferenceError:
                continue
    return None


def _restore_marked_source(source, scene, parking_collections, owner_token):
    if not _live_id(bpy.data.objects, source):
        return False
    try:
        if (
            source.get(_OWNER_KEY, "") != owner_token
            or source.get(_KIND_KEY, "") != "source"
        ):
            return False
    except (AttributeError, ReferenceError):
        return False
    try:
        names = json.loads(source.get(_SOURCE_COLLECTIONS_KEY, "[]"))
    except (TypeError, ValueError):
        names = []
    live_scene = _live_scene(scene)
    scene_name = source.get(_SCENE_KEY, "")
    targets = _restore_targets(
        (),
        tuple(str(name) for name in names),
        live_scene,
        owner_token,
        scene_name,
    )
    for collection in targets:
        if source.name not in collection.objects:
            collection.objects.link(source)
    if live_scene is not None and not any(
        _scene_contains_collection(live_scene, target)
        for target in targets
    ):
        if live_scene.collection.objects.get(source.name) is not source:
            live_scene.collection.objects.link(source)
        targets = (*targets, live_scene.collection)
    for collection in tuple(source.users_collection):
        if not any(_same_rna(collection, target) for target in targets):
            collection.objects.unlink(source)
    source.hide_viewport = bool(source.get(_SOURCE_HIDE_VIEWPORT_KEY, False))
    _clear_source_marker(source)
    return True


def _remove_object(obj):
    if _live_id(bpy.data.objects, obj):
        bpy.data.objects.remove(obj, do_unlink=True)


def _remove_mesh(mesh):
    if _live_id(bpy.data.meshes, mesh) and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _cleanup_owner(owner_token):
    marked_collections = tuple(
        collection
        for collection in bpy.data.collections
        if collection.get(_OWNER_KEY, "") == owner_token
    )
    marked_objects = tuple(
        obj for obj in bpy.data.objects if obj.get(_OWNER_KEY, "") == owner_token
    )
    marked_meshes = tuple(
        mesh for mesh in bpy.data.meshes if mesh.get(_OWNER_KEY, "") == owner_token
    )
    scene = _scene_for_owner(
        owner_token,
        (*marked_collections, *marked_objects, *marked_meshes),
    )
    scene_name = ""
    for item in (*marked_collections, *marked_objects, *marked_meshes):
        try:
            scene_name = str(item.get(_SCENE_KEY, ""))
        except ReferenceError:
            continue
        if scene_name:
            break
    parking_collections = tuple(
        collection
        for collection in marked_collections
        if collection.get(_KIND_KEY, "") == "parking"
    )
    sources = tuple(
        obj
        for obj in marked_objects
        if obj.get(_KIND_KEY, "") == "source"
    )
    for source in sources:
        _restore_marked_source(
            source,
            scene,
            parking_collections,
            owner_token,
        )
    for obj in marked_objects:
        if obj.get(_KIND_KEY, "") in {"rigid-output", "joint-output"}:
            _remove_object(obj)
    for parking in parking_collections:
        if not _live_id(bpy.data.collections, parking):
            continue
        remaining = tuple(parking.objects)
        if remaining:
            live_scene = _live_scene(scene)
            fallback_collection = (
                live_scene.collection
                if live_scene is not None
                else _recovery_collection(owner_token, scene_name)
            )
        for obj in remaining:
            if obj.name not in fallback_collection.objects:
                fallback_collection.objects.link(obj)
            parking.objects.unlink(obj)
        bpy.data.collections.remove(parking)
    for mesh in marked_meshes:
        _remove_mesh(mesh)


def _matrix_array(sources, matrix_mapping, output=None):
    source_count = len(sources)
    matrices = (
        np.empty((source_count, 4, 4), dtype=np.float64)
        if output is None
        else output
    )
    if matrices.shape != (source_count, 4, 4) or matrices.dtype != np.float64:
        raise ValueError("Invalid debug matrix buffer")
    flat_matrices = matrices.reshape((source_count, 16))
    for source_index, source in enumerate(sources):
        matrix = matrix_mapping.get(source)
        if matrix is None:
            matrix = source.matrix_world
        values = [value for row in matrix for value in row]
        if len(values) != 16:
            raise ValueError(f"Invalid debug transform for {source.name!r}")
        flat_matrices[source_index] = values
    finite = np.all(np.isfinite(matrices), axis=(1, 2))
    if not np.all(finite):
        invalid_index = int(np.flatnonzero(~finite)[0])
        raise ValueError(
            f"Invalid debug transform for {sources[invalid_index].name!r}"
        )
    return matrices


def _transform_vertices(
    local_h,
    owners,
    matrices,
    owned_matrices=None,
    coordinates=None,
    output=None,
):
    if len(local_h) == 0:
        return np.empty(0, dtype=np.float32) if output is None else output[:0]
    if owned_matrices is None or coordinates is None or output is None:
        transformed = np.einsum(
            "nij,nj->ni",
            matrices[owners, :3, :],
            local_h,
            optimize=True,
        )
        return np.ascontiguousarray(transformed, dtype=np.float32).ravel()
    np.take(matrices[:, :3, :], owners, axis=0, out=owned_matrices)
    np.einsum(
        "nij,nj->ni",
        owned_matrices,
        local_h,
        optimize=True,
        out=coordinates,
    )
    np.copyto(output.reshape((-1, 3)), coordinates, casting="unsafe")
    return output


class PreviewDebugBatch:
    def __init__(
        self,
        session,
        owner_token,
        plan,
        parking_collection,
        parking_layer_collections,
        kinematic_rigid_helper,
        slow_rigid_helper,
        static_rigid_helper,
        slow_joint_helper,
        static_joint_helper,
    ):
        self.session = session
        self.scene = session.scene
        self.owner_token = owner_token
        self.source_states = plan.source_states
        self.source_rigids = plan.source_rigids
        self.source_joints = plan.source_joints
        self.kinematic_rigids = plan.kinematic_rigids
        self.slow_rigids = plan.slow_rigids
        self.static_rigids = plan.static_rigids
        self.slow_joints = plan.slow_joints
        self.static_joints = plan.static_joints
        self.parking_collection = parking_collection
        self.parking_layer_collections = parking_layer_collections

        self._kinematic_rigid_partition = _RigidPartition(
            self.kinematic_rigids,
            *kinematic_rigid_helper,
            plan.kinematic_rigid_geometry,
        )
        self._slow_rigid_partition = _RigidPartition(
            self.slow_rigids,
            *slow_rigid_helper,
            plan.slow_rigid_geometry,
        )
        self._static_rigid_partition = _RigidPartition(
            self.static_rigids,
            *static_rigid_helper,
            plan.static_rigid_geometry,
        )
        self._slow_joint_partition = _JointPartition(
            self.slow_joints,
            *slow_joint_helper,
            plan.slow_joint_geometry,
        )
        self._static_joint_partition = _JointPartition(
            self.static_joints,
            *static_joint_helper,
            plan.static_joint_geometry,
        )
        self._rigid_partitions = (
            self._kinematic_rigid_partition,
            self._slow_rigid_partition,
            self._static_rigid_partition,
        )
        self._joint_partitions = (
            self._slow_joint_partition,
            self._static_joint_partition,
        )
        self._partitions = (*self._rigid_partitions, *self._joint_partitions)

        self.kinematic_rigid_object = self._kinematic_rigid_partition.object
        self.kinematic_rigid_mesh = self._kinematic_rigid_partition.mesh
        self.slow_rigid_object = self._slow_rigid_partition.object
        self.slow_rigid_mesh = self._slow_rigid_partition.mesh
        self.static_rigid_object = self._static_rigid_partition.object
        self.static_rigid_mesh = self._static_rigid_partition.mesh
        self.slow_joint_object = self._slow_joint_partition.object
        self.slow_joint_mesh = self._slow_joint_partition.mesh
        self.static_joint_object = self._static_joint_partition.object
        self.static_joint_mesh = self._static_joint_partition.mesh

        # Keep the original single-batch attributes as slow-domain aliases.
        self.rigid_object = self.slow_rigid_object
        self.rigid_mesh = self.slow_rigid_mesh
        self.joint_object = self.slow_joint_object
        self.joint_mesh = self.slow_joint_mesh
        self.rigid_vertex_owner = self._slow_rigid_partition.vertex_owner
        self.rigid_local_h = self._slow_rigid_partition.local_h
        self.joint_vertex_owner = self._slow_joint_partition.vertex_owner
        self.joint_local_h = self._slow_joint_partition.local_h
        self._rigid_matrices = self._slow_rigid_partition.matrices
        self._joint_matrices = self._slow_joint_partition.matrices
        self._rigid_owned_matrices = self._slow_rigid_partition.owned_matrices
        self._joint_owned_matrices = self._slow_joint_partition.owned_matrices
        self._rigid_coordinates = self._slow_rigid_partition.coordinates
        self._joint_coordinates = self._slow_joint_partition.coordinates
        self._rigid_values = self._slow_rigid_partition.values
        self._joint_values = self._slow_joint_partition.values
        self._rigid_helper_counts = self._slow_rigid_partition.helper_counts
        self._joint_helper_counts = self._slow_joint_partition.helper_counts
        self._rigid_helper_display_state = self._slow_rigid_partition.display_state
        self._joint_helper_display_state = self._slow_joint_partition.display_state

        self.kinematic_update_count = 0
        self.slow_update_count = 0
        self.static_update_count = 0
        self._helper_matrix_signature = _matrix_signature(Matrix.Identity(4))
        self._rigid_quick_signatures = {
            source: _rigid_quick_signature(source, self.scene, parking_collection)
            for source in self.source_rigids
        }
        self._joint_quick_signatures = {
            source: _joint_quick_signature(source, self.scene, parking_collection)
            for source in self.source_joints
        }
        self._rigid_geometry_signatures = {
            source: _rigid_geometry_signature(source)
            for source in self.source_rigids
        }
        original_collections = frozenset(
            collection
            for state in self.source_states
            for collection in state.collections
        )
        self._original_collection_signatures = {
            collection: _collection_scene_signature(collection)
            for collection in original_collections
        }
        self._source_objects = frozenset(
            (*self.source_rigids, *self.source_joints)
        )
        self._source_data = frozenset(
            source.data for source in self.source_rigids
        )
        self._original_collections = original_collections
        self._helper_objects = tuple(partition.object for partition in self._partitions)
        self._helper_meshes = tuple(partition.mesh for partition in self._partitions)
        self._helper_partitions = {
            partition.object: (
                partition,
                partition in self._rigid_partitions,
            )
            for partition in self._partitions
        }
        self._self_observed_ids = frozenset(
            (parking_collection, *self._helper_objects, *self._helper_meshes)
        )
        self._self_write_ids = frozenset(self._helper_meshes)
        self.observed_ids = frozenset(
            (
                *self._source_objects,
                *self._source_data,
                *self._original_collections,
                *self._self_observed_ids,
            )
        )
        self._geometry_dirty = False
        self._validation_count = 0
        self.visible = None
        self.closed = False

    @classmethod
    def create(cls, session):
        try:
            plan = _plan(session)
        except (_UnsupportedBatch, AttributeError, ReferenceError):
            return None

        owner_token = uuid.uuid4().hex
        root_name = str(
            getattr(session, "root_name", "")
            or getattr(getattr(session, "root", None), "name", "MMD")
        )
        parking_collection = None
        parking_layer_collections = ()
        try:
            (
                parking_collection,
                parking_layer_collections,
            ) = _new_parking_collection(plan.scene, root_name, owner_token)
            for state in plan.source_states:
                source = state.source
                _mark(source, owner_token, "source", plan.scene.name)
                source[_SOURCE_COLLECTIONS_KEY] = json.dumps(
                    state.collection_names,
                    ensure_ascii=False,
                )
                source[_SOURCE_HIDE_VIEWPORT_KEY] = state.hide_viewport
                if source.name not in parking_collection.objects:
                    parking_collection.objects.link(source)
                for collection in tuple(source.users_collection):
                    if not _same_rna(collection, parking_collection):
                        collection.objects.unlink(source)
                source.hide_viewport = True

            kinematic_rigid_helper = _new_rigid_helper(
                plan.scene,
                root_name,
                owner_token,
                plan.kinematic_rigid_geometry,
                "Kinematic",
            )
            slow_rigid_helper = _new_rigid_helper(
                plan.scene,
                root_name,
                owner_token,
                plan.slow_rigid_geometry,
                "Slow",
            )
            static_rigid_helper = _new_rigid_helper(
                plan.scene,
                root_name,
                owner_token,
                plan.static_rigid_geometry,
                "Static",
            )
            slow_joint_helper = _new_joint_helper(
                plan.scene,
                root_name,
                owner_token,
                plan.slow_joint_geometry,
                "Slow",
            )
            static_joint_helper = _new_joint_helper(
                plan.scene,
                root_name,
                owner_token,
                plan.static_joint_geometry,
                "Static",
            )
            if any(
                plan.scene.objects.get(source.name) is not source
                for source in (*plan.source_rigids, *plan.source_joints)
            ):
                raise RuntimeError("Parking removed a debug source from its Scene")
            batch = cls(
                session,
                owner_token,
                plan,
                parking_collection,
                parking_layer_collections,
                kinematic_rigid_helper,
                slow_rigid_helper,
                static_rigid_helper,
                slow_joint_helper,
                static_joint_helper,
            )
            _LIVE_BATCHES[owner_token] = batch
            batch.set_visible(False)
            return batch
        except Exception:
            try:
                for state in plan.source_states:
                    _restore_source_state(state, plan.scene, owner_token)
            finally:
                _cleanup_owner(owner_token)
            raise

    def _rigid_partition_usable(self, partition):
        counts = (
            len(partition.mesh.vertices),
            len(partition.mesh.edges),
            len(partition.mesh.polygons),
            len(partition.mesh.loops),
            len(partition.mesh.materials),
        )
        return bool(
            _live_id(bpy.data.objects, partition.object)
            and _live_id(bpy.data.meshes, partition.mesh)
            and partition.object.data is partition.mesh
            and self.scene.objects.get(partition.object.name) is partition.object
            and _direct_collection_object(self.scene.collection, partition.object)
            and partition.object.get(_OWNER_KEY, "") == self.owner_token
            and partition.object.get(_KIND_KEY, "") == "rigid-output"
            and partition.mesh.get(_OWNER_KEY, "") == self.owner_token
            and partition.mesh.get(_KIND_KEY, "") == "rigid-mesh"
            and partition.object.mode == "OBJECT"
            and _matrix_signature(partition.object.matrix_world)
            == self._helper_matrix_signature
            and counts == partition.helper_counts
            and partition.matrices.shape == (len(partition.sources), 4, 4)
            and partition.values.size == counts[0] * 3
            and _display_state(partition.object) == partition.display_state
        )

    def _joint_partition_usable(self, partition):
        counts = (
            len(partition.mesh.vertices),
            len(partition.mesh.edges),
            len(partition.mesh.polygons),
            len(partition.mesh.loops),
        )
        display_state = (
            partition.object.display_type,
            bool(partition.object.show_in_front),
            bool(partition.object.hide_render),
            bool(partition.object.hide_select),
        )
        return bool(
            _live_id(bpy.data.objects, partition.object)
            and _live_id(bpy.data.meshes, partition.mesh)
            and partition.object.data is partition.mesh
            and self.scene.objects.get(partition.object.name) is partition.object
            and _direct_collection_object(self.scene.collection, partition.object)
            and partition.object.get(_OWNER_KEY, "") == self.owner_token
            and partition.object.get(_KIND_KEY, "") == "joint-output"
            and partition.mesh.get(_OWNER_KEY, "") == self.owner_token
            and partition.mesh.get(_KIND_KEY, "") == "joint-mesh"
            and partition.object.mode == "OBJECT"
            and _matrix_signature(partition.object.matrix_world)
            == self._helper_matrix_signature
            and counts == partition.helper_counts
            and partition.matrices.shape == (len(partition.sources), 4, 4)
            and partition.values.size == counts[0] * 3
            and display_state == partition.display_state
        )

    @property
    def usable(self):
        if self.closed:
            return False
        try:
            return bool(
                _live_id(bpy.data.scenes, self.scene)
                and self._parking_collection_usable()
                and all(
                    self._rigid_partition_usable(partition)
                    for partition in self._rigid_partitions
                )
                and all(
                    self._joint_partition_usable(partition)
                    for partition in self._joint_partitions
                )
            )
        except (AttributeError, ReferenceError):
            return False

    def _parking_collection_usable(self):
        try:
            return bool(
                _live_id(bpy.data.collections, self.parking_collection)
                and self.parking_collection.get(_OWNER_KEY, "")
                == self.owner_token
                and self.parking_collection.get(_KIND_KEY, "") == "parking"
                and self.parking_collection.get(_SCENE_KEY, "")
                == self.scene.name
                and self.scene.collection.children.get(
                    self.parking_collection.name
                )
                is self.parking_collection
                and self.parking_collection.users == 1
                and self.parking_collection.hide_viewport
            )
        except (AttributeError, ReferenceError):
            return False

    @property
    def valid(self):
        if not self.usable:
            return False
        self._validation_count += 1
        if self._geometry_dirty:
            return False
        try:
            rigid_valid = all(
                _rigid_quick_signature(
                    source,
                    self.scene,
                    self.parking_collection,
                )
                == self._rigid_quick_signatures[source]
                and _rigid_geometry_signature(source)
                == self._rigid_geometry_signatures[source]
                for source in self.source_rigids
            )
            joint_valid = all(
                _joint_quick_signature(
                    source,
                    self.scene,
                    self.parking_collection,
                )
                == self._joint_quick_signatures[source]
                for source in self.source_joints
            )
            collections_valid = all(
                _collection_scene_signature(collection) == signature
                for collection, signature in self._original_collection_signatures.items()
            )
            return bool(rigid_valid and joint_valid and collections_valid)
        except (AttributeError, KeyError, ReferenceError):
            return False

    @property
    def validation_count(self):
        return self._validation_count

    def note_depsgraph_updates(self, updated_ids):
        if self.closed:
            return False
        matched = self.observed_ids.intersection(updated_ids)
        if not matched:
            return False
        self_writes = matched.intersection(self._self_write_ids)
        external = matched.difference(self._self_write_ids)
        if not external:
            return False
        helper_updates = external.intersection(self._helper_objects)
        if helper_updates:
            helpers_usable = all(
                (
                    self._rigid_partition_usable(partition)
                    if is_rigid
                    else self._joint_partition_usable(partition)
                )
                for helper in helper_updates
                for partition, is_rigid in (self._helper_partitions[helper],)
            )
            if not helpers_usable:
                return True
            external = external.difference(self._helper_objects)
            if not external:
                return False
        if self.parking_collection in external and self_writes:
            if not self._parking_collection_usable():
                return True
            external = external.difference((self.parking_collection,))
            if not external:
                return False
        if external.intersection(self._self_observed_ids):
            return True
        if external.intersection(self._source_data):
            self._geometry_dirty = True
            return True
        if external.intersection(self._original_collections):
            return True
        for source in external.intersection(self._source_objects):
            if source in self._rigid_quick_signatures:
                current = _rigid_quick_signature(
                    source,
                    self.scene,
                    self.parking_collection,
                )
                if current != self._rigid_quick_signatures[source]:
                    return True
                continue
            current = _joint_quick_signature(
                source,
                self.scene,
                self.parking_collection,
            )
            if current != self._joint_quick_signatures.get(source):
                return True
        return False

    def _set_visible(self, visible):
        visible = bool(visible)
        if self.visible is visible:
            return
        hidden = not visible
        for output in self._helper_objects:
            output.hide_viewport = hidden
            for view_layer in self.scene.view_layers:
                output.hide_set(hidden, view_layer=view_layer)
        self.visible = visible

    def _require_usable(self, validated):
        if self.closed or (not validated and not self.usable):
            raise RuntimeError("Preview debug batch is no longer valid")

    def set_visible(self, visible, *, validated=False):
        self._require_usable(validated)
        self._set_visible(visible)

    def update_kinematic(
        self,
        rigid_matrices,
        visible=True,
        *,
        validated=False,
    ):
        self._require_usable(validated)
        self._set_visible(visible)
        if not visible:
            return
        self._kinematic_rigid_partition.update(rigid_matrices)
        self.kinematic_update_count += 1

    def update_slow(
        self,
        rigid_matrices,
        joint_matrices,
        visible=True,
        *,
        validated=False,
    ):
        self._require_usable(validated)
        self._set_visible(visible)
        if not visible:
            return
        self._slow_rigid_partition.update(rigid_matrices)
        self._slow_joint_partition.update(joint_matrices)
        self.slow_update_count += 1

    def update_static(
        self,
        rigid_matrices,
        joint_matrices,
        visible=True,
        *,
        validated=False,
    ):
        self._require_usable(validated)
        self._set_visible(visible)
        self._static_rigid_partition.update(rigid_matrices)
        self._static_joint_partition.update(joint_matrices)
        self.static_update_count += 1

    def update_all(
        self,
        rigid_matrices,
        joint_matrices,
        visible=True,
        *,
        validated=False,
    ):
        self._require_usable(validated)
        self._set_visible(visible)
        self._kinematic_rigid_partition.update(rigid_matrices)
        self._slow_rigid_partition.update(rigid_matrices)
        self._slow_joint_partition.update(joint_matrices)
        self._static_rigid_partition.update(rigid_matrices)
        self._static_joint_partition.update(joint_matrices)
        self.kinematic_update_count += 1
        self.slow_update_count += 1
        self.static_update_count += 1

    def update(self, rigid_matrices, joint_matrices, visible=True):
        self.update_all(rigid_matrices, joint_matrices, visible=visible)

    def close(self):
        if self.closed:
            return
        first_error = None
        for state in self.source_states:
            try:
                _restore_source_state(state, self.scene, self.owner_token)
            except (AttributeError, ReferenceError, RuntimeError) as error:
                if first_error is None:
                    first_error = error
        try:
            _cleanup_owner(self.owner_token)
        except (AttributeError, ReferenceError, RuntimeError) as error:
            if first_error is None:
                first_error = error
        if first_error is None:
            self.closed = True
            _LIVE_BATCHES.pop(self.owner_token, None)
            return
        raise first_error


def cleanup_debug_batch(owner_token):
    owner_token = str(owner_token or "")
    if not owner_token:
        return False
    batch = _LIVE_BATCHES.get(owner_token)
    if batch is not None:
        try:
            batch.close()
            return True
        except Exception:
            pass
    try:
        _cleanup_owner(owner_token)
    finally:
        _LIVE_BATCHES.pop(owner_token, None)
    return True


def cleanup_stale_debug_batches():
    owner_tokens = set(_LIVE_BATCHES)
    owner_tokens.update(
        collection.get(_OWNER_KEY, "")
        for collection in bpy.data.collections
        if collection.get(_OWNER_KEY, "")
    )
    owner_tokens.update(
        obj.get(_OWNER_KEY, "")
        for obj in bpy.data.objects
        if obj.get(_OWNER_KEY, "")
    )
    owner_tokens.update(
        mesh.get(_OWNER_KEY, "")
        for mesh in bpy.data.meshes
        if mesh.get(_OWNER_KEY, "")
    )
    for owner_token in tuple(owner_tokens):
        cleanup_debug_batch(owner_token)
    return len(owner_tokens)
