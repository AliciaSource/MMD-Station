import uuid
from typing import NamedTuple

import bpy


_RUNTIME_MARKER = "spx_physics_preview_display_rig"
_RUNTIME_KIND_KEY = "spx_physics_preview_display_kind"
_SOURCE_ARMATURE_KEY = "spx_physics_preview_source_armature"
_SOURCE_OBJECT_KEY = "spx_physics_preview_source_object"
_SOURCE_HIDE_VIEWPORT_KEY = "spx_physics_preview_source_hide_viewport"
_SOURCE_OWNER_KEY = "spx_physics_preview_display_source_owner"
_SOURCE_TOKEN_KEY = "spx_physics_preview_display_source_token"
_RIG_NAME_PREFIX = ".SPX Physics Preview Rig"
_OUTPUT_NAME_PREFIX = ".SPX Physics Preview Mesh"


class ModifierBinding(NamedTuple):
    mesh_object: object
    modifier: object
    source_armature: object
    mesh_name: str
    modifier_name: str
    source_name: str


class DisplayRigPlan(NamedTuple):
    bindings: tuple
    keep_names: frozenset


class DisplayMeshBinding(NamedTuple):
    source_object: object
    source_name: str
    source_token: str
    display_object: object
    source_collections: tuple
    topology_signature: tuple
    source_hide_viewport: bool


def _matrix_values(matrix):
    return (
        matrix[0][0],
        matrix[1][0],
        matrix[2][0],
        matrix[3][0],
        matrix[0][1],
        matrix[1][1],
        matrix[2][1],
        matrix[3][1],
        matrix[0][2],
        matrix[1][2],
        matrix[2][2],
        matrix[3][2],
        matrix[0][3],
        matrix[1][3],
        matrix[2][3],
        matrix[3][3],
    )


def _single_scene_object(obj, scene):
    return tuple(obj.users_scene) == (scene,)


def _visible_in_all_view_layers(obj, scene):
    for view_layer in scene.view_layers:
        if obj.hide_get(view_layer=view_layer):
            return False
        if not obj.visible_get(view_layer=view_layer):
            return False
    return True


def _same_scene(first, second):
    if first is second:
        return True
    try:
        return first.as_pointer() == second.as_pointer()
    except (AttributeError, ReferenceError):
        return False


def _transform_modal_active(scene=None, window_manager=None):
    manager = window_manager
    if manager is None:
        manager = getattr(bpy.context, "window_manager", None)
    if manager is None:
        return False
    try:
        windows = tuple(manager.windows)
    except (AttributeError, ReferenceError):
        return False
    for window in windows:
        try:
            if scene is not None and not _same_scene(window.scene, scene):
                continue
            operators = tuple(window.modal_operators)
        except (AttributeError, ReferenceError):
            continue
        if any(
            str(getattr(operator, "bl_idname", "")).startswith("TRANSFORM_OT_")
            for operator in operators
        ):
            return True
    return False


def _local_id(item):
    return (
        item is not None
        and item.library is None
        and getattr(item, "override_library", None) is None
    )


def _used_bone_names(mesh_object, armature):
    bone_names = set(armature.data.bones.keys())
    group_names = {
        group.index: group.name
        for group in mesh_object.vertex_groups
        if group.name in bone_names
    }
    if not group_names:
        return set()
    used_indices = {
        element.group
        for vertex in mesh_object.data.vertices
        for element in vertex.groups
        if element.weight > 0.0 and element.group in group_names
    }
    return {group_names[index] for index in used_indices}


def _physics_influence_names(armature, driver_names):
    influenced = set(driver_names)
    for bone in armature.data.bones:
        parent = bone.parent
        while parent is not None:
            if parent.name in driver_names:
                influenced.add(bone.name)
                break
            parent = parent.parent
    return influenced


def _closure_with_ancestors(armature, bone_names):
    closure = set()
    for name in bone_names:
        bone = armature.data.bones.get(name)
        while bone is not None:
            closure.add(bone.name)
            bone = bone.parent
    return closure


def _affected_modifiers(scene, armature, driver_names):
    if (
        not _local_id(scene)
        or not _local_id(armature)
        or not _local_id(armature.data)
        or not _single_scene_object(armature, scene)
    ):
        return (), set()
    influenced = _physics_influence_names(armature, driver_names)
    bindings = []
    weighted_names = set()
    for mesh_object in scene.objects:
        if mesh_object.type != "MESH":
            continue
        modifiers = tuple(
            modifier
            for modifier in mesh_object.modifiers
            if modifier.type == "ARMATURE" and modifier.object is armature
        )
        if not modifiers:
            continue
        used_names = _used_bone_names(mesh_object, armature)
        if not used_names.intersection(influenced):
            continue
        if (
            mesh_object.hide_viewport
            or not _visible_in_all_view_layers(mesh_object, scene)
        ):
            return (), set()
        enabled_modifiers = tuple(
            modifier for modifier in mesh_object.modifiers if modifier.show_viewport
        )
        if (
            not _local_id(mesh_object)
            or not _local_id(mesh_object.data)
            or not _single_scene_object(mesh_object, scene)
            or len(modifiers) != 1
            or enabled_modifiers != modifiers
        ):
            return (), set()
        modifier = modifiers[0]
        if not modifier.use_vertex_groups or modifier.use_bone_envelopes:
            return (), set()
        weighted_names.update(used_names)
        bindings.append(
            ModifierBinding(
                mesh_object,
                modifier,
                armature,
                mesh_object.name,
                modifier.name,
                armature.name,
            )
        )
    keep_names = _closure_with_ancestors(
        armature,
        weighted_names.union(driver_names),
    )
    if any(
        getattr(armature.data.bones.get(name), "bbone_segments", 1) > 1
        for name in keep_names
    ):
        return (), set()
    return tuple(bindings), keep_names


def _restore_context(view_layer, active, selected, mode, active_bone_name):
    current = view_layer.objects.active
    if current is not None and current.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in tuple(view_layer.objects):
        if obj.select_get():
            obj.select_set(False)
    for obj in selected:
        try:
            if view_layer.objects.get(obj.name) is obj:
                obj.select_set(True)
        except ReferenceError:
            continue
    try:
        active_available = (
            active is not None
            and view_layer.objects.get(active.name) is active
        )
    except ReferenceError:
        active_available = False
    view_layer.objects.active = active if active_available else None
    if active_available and mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass
    if (
        active_available
        and active.type == "ARMATURE"
        and active_bone_name
        and active_bone_name in active.data.bones
    ):
        active.data.bones.active = active.data.bones[active_bone_name]


def _prune_armature(
    scene,
    view_layer,
    armature,
    keep_names,
    disconnected_names,
):
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        view_layer.update()
        if view_layer.objects.get(armature.name) is not armature:
            raise RuntimeError("DisplayRig armature is unavailable in owner View Layer")
        active = view_layer.objects.active
        selected = tuple(obj for obj in view_layer.objects if obj.select_get())
        mode = active.mode if active is not None else "OBJECT"
        active_bone_name = None
        if active is not None and active.type == "ARMATURE":
            active_bone = active.data.bones.active
            active_bone_name = active_bone.name if active_bone is not None else None
        previous_hide_select = armature.hide_select
        previous_hidden = armature.hide_get(view_layer=view_layer)
        try:
            if active is not None and active.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for obj in selected:
                obj.select_set(False)
            armature.hide_select = False
            armature.hide_set(False, view_layer=view_layer)
            armature.select_set(True)
            view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="EDIT")
            edit_bones = armature.data.edit_bones
            for edit_bone in tuple(edit_bones):
                if edit_bone.name not in keep_names:
                    edit_bones.remove(edit_bone)
            for name in disconnected_names:
                edit_bone = edit_bones.get(name)
                if edit_bone is not None and edit_bone.parent is not None:
                    edit_bone.use_connect = False
            bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            try:
                if armature.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
            except (ReferenceError, RuntimeError):
                pass
            try:
                armature.select_set(False)
            except (ReferenceError, RuntimeError):
                pass
            try:
                armature.hide_select = previous_hide_select
            except (AttributeError, ReferenceError):
                pass
            try:
                armature.hide_set(previous_hidden, view_layer=view_layer)
            except (ReferenceError, RuntimeError):
                pass
            _restore_context(
                view_layer,
                active,
                selected,
                mode,
                active_bone_name,
            )


def _mark_runtime_id(item, owner_token, kind):
    item[_RUNTIME_MARKER] = owner_token
    item[_RUNTIME_KIND_KEY] = kind


def _copy_display_settings(source, output):
    for name in (
        "color",
        "display_type",
        "show_all_edges",
        "show_in_front",
        "show_name",
        "show_texture_space",
        "show_transparent",
        "show_wire",
    ):
        try:
            setattr(output, name, getattr(source, name))
        except (AttributeError, TypeError):
            continue


def _mesh_topology_signature(mesh):
    return (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.loops),
        len(mesh.polygons),
    )


def _same_rna(first, second):
    return first is second or (
        first is not None
        and second is not None
        and first.as_pointer() == second.as_pointer()
    )


def _armature_modifier_signature(modifier):
    return (
        modifier.use_deform_preserve_volume,
        modifier.use_vertex_groups,
        modifier.use_bone_envelopes,
        modifier.vertex_group,
        modifier.invert_vertex_group,
        modifier.use_multi_modifier,
    )


def _link_like_source(scene, source, output):
    linked = False
    for collection in tuple(source.users_collection):
        try:
            if source.name not in collection.objects:
                continue
            collection.objects.link(output)
            linked = True
        except (ReferenceError, RuntimeError):
            continue
    if not linked:
        scene.collection.objects.link(output)


def _remove_object(obj):
    try:
        if bpy.data.objects.get(obj.name) is not obj:
            return
        bpy.data.objects.remove(obj, do_unlink=True)
    except ReferenceError:
        return


def _live_id(collection, item):
    try:
        return item is not None and collection.get(item.name) is item
    except (AttributeError, ReferenceError):
        return False


def _collection_signature(collections):
    try:
        return tuple(sorted(collection.as_pointer() for collection in collections))
    except ReferenceError:
        return ()


def _clear_source_marker(source, owner_token="", source_token=""):
    try:
        if owner_token and source.get(_SOURCE_OWNER_KEY, "") != owner_token:
            return
        if source_token and source.get(_SOURCE_TOKEN_KEY, "") != source_token:
            return
        for key in (
            _SOURCE_OWNER_KEY,
            _SOURCE_TOKEN_KEY,
            _SOURCE_HIDE_VIEWPORT_KEY,
        ):
            if key in source:
                del source[key]
    except (AttributeError, ReferenceError):
        return


def _marked_source_for_output(output, owner_token, marked_sources):
    try:
        source_token = str(output.get(_SOURCE_TOKEN_KEY, ""))
        source_name = str(output.get(_SOURCE_OBJECT_KEY, ""))
    except ReferenceError:
        return None
    if not source_token:
        return None
    token_candidates = tuple(
        source
        for source in marked_sources
        if source_token and source.get(_SOURCE_TOKEN_KEY, "") == source_token
    )
    if source_name:
        for source in token_candidates:
            if source.name == source_name:
                return source
    if len(token_candidates) == 1:
        return token_candidates[0]
    source = bpy.data.objects.get(source_name)
    if source is None:
        return None
    try:
        source_owner = source.get(_SOURCE_OWNER_KEY, "")
        source_marker = source.get(_SOURCE_TOKEN_KEY, "")
    except ReferenceError:
        return None
    if source_owner != owner_token or source_marker != source_token:
        return None
    return source


def _restore_source(source, hidden, owner_token="", source_token=""):
    if not _live_id(bpy.data.objects, source):
        return False
    try:
        if owner_token and source.get(_SOURCE_OWNER_KEY, "") != owner_token:
            return False
        if source_token and source.get(_SOURCE_TOKEN_KEY, "") != source_token:
            return False
        source.hide_viewport = bool(hidden)
    except (AttributeError, ReferenceError):
        return False
    _clear_source_marker(source, owner_token, source_token)
    return True


def _cleanup_owner(owner_token):
    marked_objects = tuple(
        obj
        for obj in bpy.data.objects
        if obj.get(_RUNTIME_MARKER, "") == owner_token
    )
    marked_sources = tuple(
        obj
        for obj in bpy.data.objects
        if obj.get(_SOURCE_OWNER_KEY, "") == owner_token
    )
    restored_sources = set()
    for obj in marked_objects:
        if obj.get(_RUNTIME_KIND_KEY, "") != "output":
            continue
        source = _marked_source_for_output(obj, owner_token, marked_sources)
        if source is None:
            continue
        try:
            hidden = bool(
                obj.get(
                    _SOURCE_HIDE_VIEWPORT_KEY,
                    source.get(_SOURCE_HIDE_VIEWPORT_KEY, False),
                )
            )
            source_token = str(obj.get(_SOURCE_TOKEN_KEY, ""))
        except (AttributeError, ReferenceError):
            continue
        if _restore_source(source, hidden, owner_token, source_token):
            restored_sources.add(source.as_pointer())
    for source in marked_sources:
        try:
            if source.as_pointer() in restored_sources:
                continue
            hidden = bool(source.get(_SOURCE_HIDE_VIEWPORT_KEY, False))
            source_token = str(source.get(_SOURCE_TOKEN_KEY, ""))
        except (AttributeError, ReferenceError):
            continue
        _restore_source(source, hidden, owner_token, source_token)
    for obj in marked_objects:
        _remove_object(obj)
    for scene in tuple(bpy.data.scenes):
        if scene.get(_RUNTIME_MARKER, "") != owner_token:
            continue
        try:
            bpy.data.scenes.remove(scene)
        except ReferenceError:
            pass
    marked_data = tuple(bpy.data.armatures) + tuple(bpy.data.meshes)
    for data in marked_data:
        try:
            if data.users != 0 or data.get(_RUNTIME_MARKER, "") != owner_token:
                continue
            if isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)
            elif isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
        except ReferenceError:
            continue


class PreviewDisplayRig:
    def __init__(
        self,
        session,
        armature,
        bindings,
        mesh_bindings,
        owner_token,
    ):
        self.session = session
        self.source_armature_name = session.armature.name
        self.armature = armature
        self.bindings = bindings
        self.mesh_bindings = mesh_bindings
        self.owner_token = owner_token
        self.source_pose_bones = tuple(
            sorted(
                (
                    session.armature.pose.bones[pose_bone.name]
                    for pose_bone in armature.pose.bones
                ),
                key=lambda pose_bone: len(pose_bone.parent_recursive),
            )
        )
        self.pose_bones = tuple(armature.pose.bones)
        self.bone_slots = {
            pose_bone.name: index for index, pose_bone in enumerate(self.pose_bones)
        }
        self.basis_values = [0.0] * (len(self.pose_bones) * 16)
        self.input_pose = {}
        self.last_pose_targets = None
        # Retained as a lightweight interaction-state compatibility flag.
        # Live evaluated meshes no longer need manual normal synchronization.
        self.force_normal_update = True
        self.closed = False
        self.capture_input_pose()

    @classmethod
    def plan(cls, session):
        bindings, keep_names = _affected_modifiers(
            session.scene,
            session.armature,
            set(session.driver_pose_bones),
        )
        if not bindings or not keep_names:
            return None
        return DisplayRigPlan(bindings, frozenset(keep_names))

    @classmethod
    def create(cls, session, plan=None):
        plan = plan or cls.plan(session)
        if plan is None:
            return None
        bindings = plan.bindings
        keep_names = plan.keep_names
        source_armature = session.armature
        owner_view_layer = session.owner_view_layer(
            required_object=source_armature,
        )
        owner_token = uuid.uuid4().hex
        armature = None
        armature_data = None
        created_outputs = []
        source_states = []
        try:
            armature_data = source_armature.data.copy()
            armature_data.animation_data_clear()
            _mark_runtime_id(armature_data, owner_token, "rig-data")
            armature = bpy.data.objects.new(
                f"{_RIG_NAME_PREFIX} [{session.root_name}]",
                armature_data,
            )
            armature.data.name = f"{armature.name} Data"
            _mark_runtime_id(armature, owner_token, "rig")
            armature[_SOURCE_ARMATURE_KEY] = source_armature.name
            armature.matrix_world = source_armature.matrix_world
            session.scene.collection.objects.link(armature)
            _prune_armature(
                session.scene,
                owner_view_layer,
                armature,
                keep_names,
                set(session.driver_pose_bones),
            )
            armature.parent = None
            armature.animation_data_clear()
            armature.constraints.clear()
            armature.hide_viewport = True
            armature.hide_render = True
            armature.hide_select = True
            armature.show_in_front = False

            mesh_bindings = []
            for index, binding in enumerate(bindings):
                source = binding.mesh_object
                if any(
                    key in source
                    for key in (
                        _SOURCE_OWNER_KEY,
                        _SOURCE_TOKEN_KEY,
                        _SOURCE_HIDE_VIEWPORT_KEY,
                    )
                ):
                    raise RuntimeError("Display source already has runtime metadata")
                source_token = uuid.uuid4().hex
                source_collections = tuple(source.users_collection)
                source_hidden = bool(source.hide_viewport)
                source_world = source.matrix_world.copy()
                output = source.copy()
                created_outputs.append(output)
                output.name = f"{_OUTPUT_NAME_PREFIX} {index} [{source.name}]"
                output.parent = None
                output.matrix_world = source_world
                output.animation_data_clear()
                output.constraints.clear()
                copied_modifier = output.modifiers.get(binding.modifier_name)
                if copied_modifier is None or copied_modifier.type != "ARMATURE":
                    raise RuntimeError("Display mesh lost its Armature modifier")
                copied_modifier.object = armature
                _mark_runtime_id(output, owner_token, "output")
                output[_SOURCE_OBJECT_KEY] = source.name
                output[_SOURCE_TOKEN_KEY] = source_token
                output[_SOURCE_HIDE_VIEWPORT_KEY] = source_hidden
                output.hide_viewport = False
                output.hide_render = True
                output.hide_select = True
                _copy_display_settings(source, output)
                _link_like_source(session.scene, source, output)
                for view_layer in session.scene.view_layers:
                    output.hide_set(False, view_layer=view_layer)

                source_states.append((source, source_hidden, source_token))
                source[_SOURCE_OWNER_KEY] = owner_token
                source[_SOURCE_TOKEN_KEY] = source_token
                source[_SOURCE_HIDE_VIEWPORT_KEY] = source_hidden
                source.hide_viewport = True
                mesh_bindings.append(
                    DisplayMeshBinding(
                        source,
                        source.name,
                        source_token,
                        output,
                        source_collections,
                        _mesh_topology_signature(source.data),
                        source_hidden,
                    )
                )
            display = cls(
                session,
                armature,
                bindings,
                tuple(mesh_bindings),
                owner_token,
            )
            display.apply_input_pose()
            return display
        except Exception:
            for source, hidden, source_token in source_states:
                _restore_source(source, hidden, owner_token, source_token)
            _cleanup_owner(owner_token)
            for output in created_outputs:
                _remove_object(output)
            if armature is not None:
                try:
                    if bpy.data.objects.get(armature.name) is armature:
                        bpy.data.objects.remove(armature, do_unlink=True)
                except ReferenceError:
                    pass
            if armature_data is not None:
                try:
                    if armature_data.users == 0:
                        bpy.data.armatures.remove(armature_data)
                except ReferenceError:
                    pass
            raise

    @property
    def valid(self):
        if self.closed:
            return False
        try:
            scene = self.session.scene
            if (
                bpy.data.scenes.get(scene.name) is not scene
                or bpy.data.objects.get(self.armature.name) is not self.armature
                or self.armature.get(_RUNTIME_MARKER, "") != self.owner_token
                or self.armature.get(_RUNTIME_KIND_KEY, "") != "rig"
                or not _live_id(bpy.data.armatures, self.armature.data)
                or self.armature.data.get(_RUNTIME_MARKER, "") != self.owner_token
                or not _single_scene_object(self.armature, scene)
                or scene.objects.get(self.armature.name) is not self.armature
                or tuple(self.armature.users_collection) != (scene.collection,)
                or not self.armature.hide_viewport
                or not self.armature.hide_render
                or not self.armature.hide_select
                or self.armature.parent is not None
                or bool(self.armature.constraints)
                or self.armature.animation_data is not None
            ):
                return False
            if len(self.bindings) != len(self.mesh_bindings):
                return False
            for source_binding, binding in zip(self.bindings, self.mesh_bindings):
                source = binding.source_object
                output = binding.display_object
                if (
                    not _live_id(bpy.data.objects, source)
                    or scene.objects.get(source.name) is not source
                    or source.type != "MESH"
                    or source.get(_SOURCE_OWNER_KEY, "") != self.owner_token
                    or source.get(_SOURCE_TOKEN_KEY, "") != binding.source_token
                    or bool(source.get(_SOURCE_HIDE_VIEWPORT_KEY, False))
                    != binding.source_hide_viewport
                    or not source.hide_viewport
                    or _mesh_topology_signature(source.data)
                    != binding.topology_signature
                    or _collection_signature(source.users_collection)
                    != _collection_signature(binding.source_collections)
                ):
                    return False
                source_modifier = source.modifiers.get(source_binding.modifier_name)
                if not _same_rna(source_modifier, source_binding.modifier):
                    return False
                enabled_modifiers = tuple(
                    modifier for modifier in source.modifiers if modifier.show_viewport
                )
                if (
                    source_modifier.type != "ARMATURE"
                    or source_modifier.object is not source_binding.source_armature
                    or len(enabled_modifiers) != 1
                    or not _same_rna(enabled_modifiers[0], source_modifier)
                    or not source_modifier.use_vertex_groups
                    or source_modifier.use_bone_envelopes
                    or not _live_id(bpy.data.objects, output)
                    or not _single_scene_object(output, scene)
                    or scene.objects.get(output.name) is not output
                    or source.data is not output.data
                    or output.get(_RUNTIME_MARKER, "") != self.owner_token
                    or output.get(_RUNTIME_KIND_KEY, "") != "output"
                    or output.get(_SOURCE_TOKEN_KEY, "") != binding.source_token
                    or bool(output.get(_SOURCE_HIDE_VIEWPORT_KEY, False))
                    != binding.source_hide_viewport
                    or output.hide_viewport
                    or not output.hide_render
                    or not output.hide_select
                    or output.parent is not None
                    or bool(output.constraints)
                    or output.animation_data is not None
                    or not _visible_in_all_view_layers(output, scene)
                    or _collection_signature(output.users_collection)
                    != _collection_signature(binding.source_collections)
                ):
                    return False
                output_modifier = output.modifiers.get(
                    source_binding.modifier_name
                )
                output_enabled_modifiers = tuple(
                    modifier for modifier in output.modifiers if modifier.show_viewport
                )
                if (
                    output_modifier is None
                    or output_modifier.type != "ARMATURE"
                    or output_modifier.object is not self.armature
                    or len(output_enabled_modifiers) != 1
                    or not _same_rna(output_enabled_modifiers[0], output_modifier)
                    or _armature_modifier_signature(source_modifier)
                    != _armature_modifier_signature(output_modifier)
                ):
                    return False
            return True
        except (AttributeError, ReferenceError):
            return False

    @property
    def binding_names(self):
        return tuple(
            (binding.mesh_name, binding.modifier_name)
            for binding in self.bindings
        )

    @property
    def observed_ids(self):
        values = [self.armature, self.armature.data]
        for binding in self.mesh_bindings:
            values.extend((binding.display_object, binding.display_object.data))
        return tuple(values)

    def _set_basis(self, bone_name, matrix):
        slot = self.bone_slots.get(bone_name)
        if slot is None:
            return
        offset = slot * 16
        self.basis_values[offset:offset + 16] = _matrix_values(matrix)

    def capture_input_pose(self):
        self.input_pose = {
            pose_bone.name: pose_bone.matrix.copy()
            for pose_bone in self.source_pose_bones
        }

    def _write_resolved_pose(self, pose_targets):
        display_bones = self.armature.pose.bones
        for source_bone in self.source_pose_bones:
            display_bone = display_bones[source_bone.name]
            parent = source_bone.parent
            if parent is None:
                matrix_basis = display_bone.bone.convert_local_to_pose(
                    pose_targets[source_bone.name],
                    display_bone.bone.matrix_local,
                    invert=True,
                )
            else:
                display_parent = display_bones[parent.name]
                matrix_basis = display_bone.bone.convert_local_to_pose(
                    pose_targets[source_bone.name],
                    display_bone.bone.matrix_local,
                    parent_matrix=pose_targets[parent.name],
                    parent_matrix_local=display_parent.bone.matrix_local,
                    invert=True,
                )
            self._set_basis(source_bone.name, matrix_basis)
        source_matrix = self.session.armature.matrix_world
        if self.armature.matrix_world != source_matrix:
            self.armature.matrix_world = source_matrix
        self.armature.pose.bones.foreach_set("matrix_basis", self.basis_values)
        self.armature.update_tag(refresh={"OBJECT"})

    def _normal_update_due(self, defer):
        if defer:
            self.force_normal_update = True
            return False
        due = bool(self.force_normal_update)
        self.force_normal_update = False
        return due

    def transform_modal_active(self):
        return _transform_modal_active(scene=self.session.scene)

    def apply_resolved_pose(self, pose_targets):
        self.last_pose_targets = pose_targets
        self._normal_update_due(self.transform_modal_active())
        self._write_resolved_pose(pose_targets)
        for binding in self.mesh_bindings:
            source_matrix = binding.source_object.matrix_world
            output = binding.display_object
            if output.matrix_world != source_matrix:
                output.matrix_world = source_matrix
            if output.get(_SOURCE_OBJECT_KEY, "") != binding.source_object.name:
                output[_SOURCE_OBJECT_KEY] = binding.source_object.name

    def apply_input_pose(self):
        self.apply_resolved_pose(self.input_pose)

    def close(self):
        if self.closed:
            return
        first_error = None
        for binding in self.mesh_bindings:
            source = None
            try:
                candidate = binding.source_object
                if bpy.data.objects.get(candidate.name) is candidate:
                    source = candidate
            except ReferenceError:
                pass
            if source is None:
                candidates = tuple(
                    obj
                    for obj in bpy.data.objects
                    if (
                        obj.get(_SOURCE_OWNER_KEY, "") == self.owner_token
                        and obj.get(_SOURCE_TOKEN_KEY, "") == binding.source_token
                    )
                )
                if len(candidates) == 1:
                    source = candidates[0]
            if source is None:
                candidate = bpy.data.objects.get(binding.source_name)
                if candidate is not None:
                    try:
                        if (
                            candidate.get(_SOURCE_OWNER_KEY, "")
                            == self.owner_token
                            and candidate.get(_SOURCE_TOKEN_KEY, "")
                            == binding.source_token
                        ):
                            source = candidate
                    except ReferenceError:
                        pass
            if source is None:
                continue
            try:
                _restore_source(
                    source,
                    binding.source_hide_viewport,
                    self.owner_token,
                    binding.source_token,
                )
            except (AttributeError, ReferenceError, RuntimeError) as error:
                if first_error is None:
                    first_error = error
        try:
            _cleanup_owner(self.owner_token)
        except (AttributeError, ReferenceError, RuntimeError) as error:
            if first_error is None:
                first_error = error
        self.closed = True
        if first_error is not None:
            raise first_error


def cleanup_display_rig(owner_token):
    owner_token = str(owner_token or "")
    if not owner_token:
        return False
    _cleanup_owner(owner_token)
    return True


def cleanup_stale_display_rigs():
    owner_tokens = {
        obj.get(_RUNTIME_MARKER, "")
        for obj in bpy.data.objects
        if bool(obj.get(_RUNTIME_MARKER, ""))
    }
    owner_tokens.update(
        obj.get(_SOURCE_OWNER_KEY, "")
        for obj in bpy.data.objects
        if bool(obj.get(_SOURCE_OWNER_KEY, ""))
    )
    owner_tokens.update(
        scene.get(_RUNTIME_MARKER, "")
        for scene in bpy.data.scenes
        if bool(scene.get(_RUNTIME_MARKER, ""))
    )
    owner_tokens.update(
        data.get(_RUNTIME_MARKER, "")
        for data in (*bpy.data.armatures, *bpy.data.meshes)
        if bool(data.get(_RUNTIME_MARKER, ""))
    )
    for owner_token in owner_tokens:
        _cleanup_owner(owner_token)
    return len(owner_tokens)
