import hashlib
import logging
import os
import struct
import time
from array import array
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from bpy.app.handlers import persistent


LOGGER = logging.getLogger(__name__)

_STRUCTURAL_OPTIONS = (
    "scale",
    "fix_bone_order",
    "overwrite_bone_morphs_from_action_pose",
    "translate_in_presets",
    "sort_materials",
    "sort_vertices",
    "disable_specular",
    "export_vertex_colors_as_adduv2",
    "normal_handling",
    "ik_angle_limits",
)


@dataclass
class ShadowModel:
    root_pointer: int
    model: object
    add_uv_count: int
    options: tuple
    geometry_signature: tuple
    content_fingerprint: bytes
    bone_map: dict
    bone_name_table: list
    material_name_table: list
    vertex_morphs: dict
    uv_morphs: dict
    uv_types: dict
    rigid_pointers: set
    joint_pointers: set
    watched_pointers: set
    source_filepath: str
    invalid_reasons: set = field(default_factory=set)


_shadows = {}
_tracking_suspended = 0


def _pointer(value):
    try:
        return value.as_pointer()
    except (AttributeError, ReferenceError):
        return 0


def _matrix_signature(matrix):
    return tuple(round(value, 9) for row in matrix for value in row)


def _modifier_signature(modifier):
    return (
        modifier.name,
        modifier.type,
        modifier.show_viewport,
        modifier.show_render,
    )


def _foreach_bytes(collection, attribute, typecode, width):
    if not collection:
        return b""
    values = array(typecode, [0]) * (len(collection) * width)
    collection.foreach_get(attribute, values)
    return values.tobytes()


def _simple_rna_signature(value):
    entries = []
    for prop in value.bl_rna.properties:
        if prop.identifier == "rna_type" or prop.type == "COLLECTION":
            continue
        try:
            item = getattr(value, prop.identifier)
        except (AttributeError, RuntimeError, TypeError):
            continue
        if prop.type == "POINTER":
            item = _pointer(item)
        elif getattr(prop, "is_array", False):
            item = tuple(item)
        elif not isinstance(item, (bool, float, int, str)):
            continue
        entries.append((prop.identifier, item))
    return tuple(entries)


def _content_fingerprint(meshes, armature):
    digest = hashlib.blake2b(digest_size=32)
    for mesh_object in sorted(meshes, key=lambda item: item.name):
        mesh = mesh_object.data
        digest.update(mesh_object.name.encode("utf-8", errors="surrogatepass"))
        digest.update(_foreach_bytes(mesh.vertices, "co", "f", 3))
        digest.update(_foreach_bytes(mesh.edges, "vertices", "i", 2))
        digest.update(_foreach_bytes(mesh.edges, "use_edge_sharp", "b", 1))
        digest.update(_foreach_bytes(mesh.loops, "vertex_index", "i", 1))
        digest.update(_foreach_bytes(mesh.polygons, "loop_start", "i", 1))
        digest.update(_foreach_bytes(mesh.polygons, "loop_total", "i", 1))
        digest.update(_foreach_bytes(mesh.polygons, "material_index", "i", 1))
        digest.update(_foreach_bytes(mesh.polygons, "use_smooth", "b", 1))
        for uv_layer in mesh.uv_layers:
            digest.update(uv_layer.name.encode("utf-8", errors="surrogatepass"))
            digest.update(_foreach_bytes(uv_layer.data, "uv", "f", 2))
        shape_keys = getattr(mesh, "shape_keys", None)
        if shape_keys is not None:
            for key in shape_keys.key_blocks:
                digest.update(key.name.encode("utf-8", errors="surrogatepass"))
                digest.update(struct.pack("<Q", _pointer(key)))
                digest.update(struct.pack("<Q", _pointer(key.relative_key)))
                digest.update(_foreach_bytes(key.data, "co", "f", 3))
        digest.update(
            repr(tuple((group.index, group.name) for group in mesh_object.vertex_groups)).encode("utf-8")
        )
        group_indices = array("I")
        group_weights = array("f")
        for vertex in mesh.vertices:
            for group in vertex.groups:
                group_indices.extend((vertex.index, group.group))
                group_weights.append(group.weight)
        digest.update(group_indices.tobytes())
        digest.update(group_weights.tobytes())
        digest.update(repr(tuple(_simple_rna_signature(modifier) for modifier in mesh_object.modifiers)).encode("utf-8"))
        for slot in mesh_object.material_slots:
            material = slot.material
            if material is None:
                digest.update(b"NONE")
                continue
            digest.update(material.name.encode("utf-8", errors="surrogatepass"))
            digest.update(repr(_simple_rna_signature(material)).encode("utf-8"))
            digest.update(repr(_simple_rna_signature(material.mmd_material)).encode("utf-8"))
    if armature is not None:
        digest.update(repr(_armature_signature(armature)).encode("utf-8"))
        digest.update(repr(_simple_rna_signature(armature.data)).encode("utf-8"))
        for pose_bone in armature.pose.bones:
            digest.update(pose_bone.name.encode("utf-8", errors="surrogatepass"))
            digest.update(repr(_simple_rna_signature(pose_bone)).encode("utf-8"))
            mmd_bone = getattr(pose_bone, "mmd_bone", None)
            if mmd_bone is not None:
                digest.update(repr(_simple_rna_signature(mmd_bone)).encode("utf-8"))
            digest.update(repr(_matrix_signature(pose_bone.matrix_basis)).encode("utf-8"))
    return digest.digest()


def _mesh_signature(mesh_object):
    mesh = mesh_object.data
    shape_keys = getattr(mesh, "shape_keys", None)
    return (
        _pointer(mesh_object),
        mesh_object.name,
        _pointer(mesh),
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.loops),
        len(mesh.polygons),
        _matrix_signature(mesh_object.matrix_world),
        tuple(_modifier_signature(modifier) for modifier in mesh_object.modifiers),
        tuple(_pointer(slot.material) for slot in mesh_object.material_slots),
        _pointer(shape_keys),
        tuple(key.name for key in shape_keys.key_blocks) if shape_keys else (),
    )


def _armature_signature(armature):
    if armature is None:
        return ()
    return (
        _pointer(armature),
        _pointer(armature.data),
        _matrix_signature(armature.matrix_world),
        tuple(
            (
                bone.name,
                bone.parent.name if bone.parent else "",
                tuple(round(value, 9) for value in bone.head_local),
                tuple(round(value, 9) for value in bone.tail_local),
            )
            for bone in armature.data.bones
        ),
    )


def _geometry_signature(meshes, armature):
    return (
        tuple(_mesh_signature(mesh) for mesh in sorted(meshes, key=lambda item: item.name)),
        _armature_signature(armature),
    )


def _option_signature(kwargs):
    return tuple((name, kwargs.get(name)) for name in _STRUCTURAL_OPTIONS)


def _private_name(exporter_class, suffix):
    return next(
        name for name in exporter_class.__dict__
        if name.endswith(suffix)
    )


def _morph_pointer_map(root, model, pmx_module, collection_name, morph_class):
    exported = {}
    for morph in model.morphs:
        if isinstance(morph, morph_class):
            exported.setdefault(morph.name, []).append(morph)
    mapped = {}
    for item in getattr(root.mmd_root, collection_name):
        candidates = exported.get(item.name, [])
        if not candidates:
            return None
        mapped[_pointer(item)] = candidates.pop(0)
    if any(candidates for candidates in exported.values()):
        return None
    return mapped


def _watched_pointers(meshes, armature):
    pointers = set()
    for mesh_object in meshes:
        pointers.add(_pointer(mesh_object))
        pointers.add(_pointer(mesh_object.data))
        shape_keys = getattr(mesh_object.data, "shape_keys", None)
        if shape_keys is not None:
            pointers.add(_pointer(shape_keys))
        for slot in mesh_object.material_slots:
            if slot.material is not None:
                pointers.add(_pointer(slot.material))
    if armature is not None:
        pointers.add(_pointer(armature))
        pointers.add(_pointer(armature.data))
    pointers.discard(0)
    return pointers


def capture_full_export(filepath, kwargs, state, pmx_module):
    root = kwargs.get("root")
    model = state.get("_model")
    exporter = state.get("_exporter")
    bone_map = state.get("_bone_map")
    meshes = tuple(state.get("_mesh_objects", ()))
    rigid_objects = tuple(state.get("_rigid_objects", ()))
    joint_objects = tuple(state.get("_joint_objects", ()))
    if root is None or model is None or exporter is None or bone_map is None:
        return False

    vertex_morphs = _morph_pointer_map(
        root,
        model,
        pmx_module,
        "vertex_morphs",
        pmx_module.VertexMorph,
    )
    uv_morphs = _morph_pointer_map(
        root,
        model,
        pmx_module,
        "uv_morphs",
        pmx_module.UVMorph,
    )
    if vertex_morphs is None or uv_morphs is None:
        LOGGER.info("[MMD Station Shadow] full export completed without a reusable Morph map")
        return False

    armature = kwargs.get("armature")
    global _tracking_suspended
    _tracking_suspended += 1
    try:
        bpy.context.view_layer.update()
    finally:
        _tracking_suspended -= 1
    shadow = ShadowModel(
        root_pointer=_pointer(root),
        model=model,
        add_uv_count=int(getattr(exporter, "_PmxExporter__add_uv_count", 0)),
        options=_option_signature(kwargs),
        geometry_signature=_geometry_signature(meshes, armature),
        content_fingerprint=_content_fingerprint(meshes, armature),
        bone_map=dict(bone_map),
        bone_name_table=list(getattr(exporter, "_PmxExporter__bone_name_table", ())),
        material_name_table=list(getattr(exporter, "_PmxExporter__material_name_table", ())),
        vertex_morphs=vertex_morphs,
        uv_morphs=uv_morphs,
        uv_types={
            pointer: morph.type_index()
            for pointer, morph in uv_morphs.items()
        },
        rigid_pointers={_pointer(obj) for obj in rigid_objects},
        joint_pointers={_pointer(obj) for obj in joint_objects},
        watched_pointers=_watched_pointers(meshes, armature),
        source_filepath=str(filepath),
    )
    _shadows[shadow.root_pointer] = shadow
    LOGGER.info(
        "[MMD Station Shadow] captured root=%s vertices=%d faces=%d morphs=%d rigids=%d joints=%d",
        root.name,
        len(model.vertices),
        len(model.faces),
        len(model.morphs),
        len(model.rigids),
        len(model.joints),
    )
    return True


def _update_static_morphs(root, shadow, exporter_class):
    categories = exporter_class.CATEGORIES
    changes = []
    current_vertex = {
        _pointer(item): item
        for item in root.mmd_root.vertex_morphs
    }
    current_uv = {
        _pointer(item): item
        for item in root.mmd_root.uv_morphs
    }
    if set(current_vertex) != set(shadow.vertex_morphs):
        raise ValueError("Vertex Morph collection changed")
    if set(current_uv) != set(shadow.uv_morphs):
        raise ValueError("UV Morph collection changed")

    for pointer, item in current_vertex.items():
        morph = shadow.vertex_morphs[pointer]
        changes.append((morph, morph.name, morph.name_e, morph.category))
        morph.name = item.name
        morph.name_e = item.name_e
        morph.category = categories.get(item.category, 4)
    for pointer, item in current_uv.items():
        morph = shadow.uv_morphs[pointer]
        if item.uv_index + 3 != shadow.uv_types[pointer]:
            raise ValueError("UV Morph type changed")
        changes.append((morph, morph.name, morph.name_e, morph.category))
        morph.name = item.name
        morph.name_e = item.name_e
        morph.category = categories.get(item.category, 4)
    return changes


def _build_morphs_and_display(root, shadow, exporter_class, pmx_module, kwargs):
    exporter = exporter_class()
    model = pmx_module.Model()
    setattr(exporter, "_PmxExporter__model", model)
    setattr(exporter, "_PmxExporter__armature", kwargs.get("armature"))
    setattr(exporter, "_PmxExporter__scale", kwargs.get("scale", 1.0))
    setattr(
        exporter,
        "_PmxExporter__overwrite_bone_morphs_from_action_pose",
        kwargs.get("overwrite_bone_morphs_from_action_pose", False),
    )
    setattr(exporter, "_PmxExporter__bone_name_table", list(shadow.bone_name_table))
    setattr(exporter, "_PmxExporter__material_name_table", list(shadow.material_name_table))

    model.morphs.extend(shadow.vertex_morphs.values())
    getattr(exporter, _private_name(exporter_class, "__export_bone_morphs"))(root)
    getattr(exporter, _private_name(exporter_class, "__export_material_morphs"))(root)
    model.morphs.extend(shadow.uv_morphs.values())
    getattr(exporter, _private_name(exporter_class, "__export_group_morphs"))(root)
    morph_map = getattr(exporter, _private_name(exporter_class, "__get_pmx_morph_map"))(root)
    model.morphs.sort(
        key=lambda morph: morph_map.get(
            (exporter.MORPH_TYPES[type(morph)], morph.name),
            float("inf"),
        )
    )
    getattr(exporter, _private_name(exporter_class, "__exportDisplayItems"))(
        root,
        shadow.bone_map,
    )
    return model.morphs, model.display


def _build_rigids_and_joints(shadow, exporter_class, pmx_module, kwargs):
    rigid_objects = sorted(tuple(kwargs.get("rigid_bodies", ())), key=lambda obj: obj.name)
    joint_objects = sorted(tuple(kwargs.get("joints", ())), key=lambda obj: obj.name)
    if {_pointer(obj) for obj in rigid_objects} != shadow.rigid_pointers:
        raise ValueError("Rigid body collection changed")
    if {_pointer(obj) for obj in joint_objects} != shadow.joint_pointers:
        raise ValueError("Joint collection changed")

    exporter = exporter_class()
    model = pmx_module.Model()
    setattr(exporter, "_PmxExporter__model", model)
    setattr(exporter, "_PmxExporter__scale", kwargs.get("scale", 1.0))
    rigid_map = getattr(
        exporter,
        _private_name(exporter_class, "__exportRigidBodies"),
    )(rigid_objects, shadow.bone_map)
    getattr(exporter, _private_name(exporter_class, "__exportJoints"))(
        joint_objects,
        rigid_map,
    )
    return model.rigids, model.joints


def _update_model_metadata(root, model):
    old = (model.name, model.name_e, model.comment, model.comment_e)
    model.name = root.mmd_root.name or root.name
    model.name_e = root.mmd_root.name_e
    text = bpy.data.texts.get(root.mmd_root.comment_text)
    if text is not None:
        model.comment = text.as_string().replace("\n", "\r\n")
    text = bpy.data.texts.get(root.mmd_root.comment_e_text)
    if text is not None:
        model.comment_e = text.as_string().replace("\n", "\r\n")
    return old


def _copy_textures(exporter_class, exporter_module, shadow, root, filepath, mode):
    if mode == "NONE":
        return
    exporter = exporter_class()
    setattr(exporter, "_PmxExporter__model", shadow.model)
    output_dir = os.path.dirname(filepath)
    import_folder = root.get("import_folder", "")
    base_folder = exporter_module.FnContext.get_addon_preferences_attribute(
        exporter_module.FnContext.ensure_context(),
        "base_texture_folder",
        "",
    )
    getattr(exporter, _private_name(exporter_class, "__copy_textures"))(
        output_dir,
        import_folder or base_folder,
        copy_textures_mode=mode,
    )


def _write_atomic(pmx_module, filepath, model, add_uv_count):
    target = Path(filepath)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.mmdstation-{os.getpid()}.tmp")
    try:
        pmx_module.save(str(temporary), model, add_uv_count=add_uv_count)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def try_fast_export(filepath, kwargs, exporter_module, exporter_class, pmx_module):
    root = kwargs.get("root")
    if root is None:
        return None
    shadow = _shadows.get(_pointer(root))
    if shadow is None:
        return None
    if _option_signature(kwargs) != shadow.options:
        LOGGER.info("[MMD Station Shadow] fallback: structural export options changed")
        return None

    meshes = tuple(kwargs.get("meshes", ()))
    if _geometry_signature(meshes, kwargs.get("armature")) != shadow.geometry_signature:
        LOGGER.info("[MMD Station Shadow] fallback: model structure changed")
        return None
    if shadow.invalid_reasons:
        if _content_fingerprint(meshes, kwargs.get("armature")) != shadow.content_fingerprint:
            LOGGER.info(
                "[MMD Station Shadow] fallback: %s",
                ", ".join(sorted(shadow.invalid_reasons)),
            )
            return None
        shadow.invalid_reasons.clear()

    started = time.perf_counter()
    morph_changes = []
    old_metadata = None
    old_sections = None
    global _tracking_suspended
    _tracking_suspended += 1
    try:
        morph_changes = _update_static_morphs(root, shadow, exporter_class)
        morphs, display = _build_morphs_and_display(
            root,
            shadow,
            exporter_class,
            pmx_module,
            kwargs,
        )
        rigids, joints = _build_rigids_and_joints(
            shadow,
            exporter_class,
            pmx_module,
            kwargs,
        )
        model = shadow.model
        old_metadata = _update_model_metadata(root, model)
        old_sections = (model.morphs, model.display, model.rigids, model.joints)
        model.morphs = morphs
        model.display = display
        model.rigids = rigids
        model.joints = joints
        _copy_textures(
            exporter_class,
            exporter_module,
            shadow,
            root,
            filepath,
            kwargs.get("copy_textures_mode", "NONE"),
        )
        _write_atomic(pmx_module, filepath, model, shadow.add_uv_count)
        shadow.source_filepath = str(filepath)
    except Exception:
        LOGGER.exception("[MMD Station Shadow] fast export failed; falling back")
        if old_sections is not None:
            model.morphs, model.display, model.rigids, model.joints = old_sections
        if old_metadata is not None:
            model.name, model.name_e, model.comment, model.comment_e = old_metadata
        for morph, name, name_e, category in morph_changes:
            morph.name = name
            morph.name_e = name_e
            morph.category = category
        shadow.invalid_reasons.add("fast export preparation failed")
        return None
    finally:
        _tracking_suspended -= 1

    elapsed = time.perf_counter() - started
    return {
        "filepath": str(filepath),
        "success": True,
        "fast": True,
        "total_seconds": elapsed,
        "unmeasured_seconds": 0.0,
        "file_size": os.path.getsize(filepath),
        "phases": {
            "shadow_save": {
                "label": "Runtime Shadow save",
                "seconds": elapsed,
                "calls": 1,
            },
        },
        "counts": {
            "vertices": len(shadow.model.vertices),
            "faces": len(shadow.model.faces),
            "textures": len(shadow.model.textures),
            "materials": len(shadow.model.materials),
            "bones": len(shadow.model.bones),
            "morphs": len(shadow.model.morphs),
            "display": len(shadow.model.display),
            "rigids": len(shadow.model.rigids),
            "joints": len(shadow.model.joints),
        },
    }


@persistent
def _clear_on_load(_unused):
    clear_runtime_shadows()


@persistent
def _track_depsgraph_updates(_scene, depsgraph):
    if _tracking_suspended or not _shadows:
        return
    updated = {
        _pointer(getattr(update.id, "original", update.id))
        for update in depsgraph.updates
    }
    updated.discard(0)
    if not updated:
        return
    for shadow in _shadows.values():
        if updated & shadow.watched_pointers:
            shadow.invalid_reasons.add("Mesh, Armature, ShapeKey, or Material changed")


def clear_runtime_shadows():
    _shadows.clear()


def runtime_shadow_count():
    return len(_shadows)


def register_services():
    if _clear_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_clear_on_load)
    if _track_depsgraph_updates not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_track_depsgraph_updates)


def unregister_services():
    if _track_depsgraph_updates in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_track_depsgraph_updates)
    if _clear_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_clear_on_load)
    clear_runtime_shadows()
