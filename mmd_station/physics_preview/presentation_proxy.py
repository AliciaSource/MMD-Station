from dataclasses import dataclass
import hashlib

import bpy


_COLLECTION_PREFIX = "_MMD_STATION_PHYSICS_VIEW_"


@dataclass
class SourceMeshState:
    name: str
    hidden: bool
    modifier_visibility: tuple


def _eligible_meshes(meshes, armature, view_layer):
    eligible = []
    for obj in meshes:
        if (
            obj.type != "MESH"
            or obj.name not in view_layer.objects
            or obj.hide_get()
        ):
            continue
        armature_modifiers = [
            modifier
            for modifier in obj.modifiers
            if modifier.type == "ARMATURE" and modifier.object == armature
        ]
        if (
            len(armature_modifiers) != 1
            or any(
                modifier.type not in {"ARMATURE", "UV_WARP"}
                or modifier.type == "ARMATURE"
                and modifier.object not in {None, armature}
                for modifier in obj.modifiers
            )
        ):
            continue
        eligible.append(obj)
    return eligible


def _redirect_modifiers(obj, armature, proxy_armature):
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == armature:
            modifier.object = proxy_armature
        elif modifier.type == "UV_WARP":
            if modifier.object_from == armature:
                modifier.object_from = proxy_armature
            if modifier.object_to == armature:
                modifier.object_to = proxy_armature


class PhysicsPresentationProxy:
    def __init__(self, scene, root, armature, meshes, driver_names):
        self.scene = scene
        self.root_name = root.name
        self.armature_name = armature.name
        self.driver_names = frozenset(driver_names)
        self.source_states = ()
        self.shape_bindings = ()
        self.proxy_mesh_names = ()
        identity = hashlib.blake2b(root.name.encode("utf-8"), digest_size=6).hexdigest()
        self.collection_name = f"{_COLLECTION_PREFIX}{identity}"
        self.proxy_armature_name = f"{self.collection_name}_Armature"
        self.proxy_mesh_name = f"{self.collection_name}_Mesh"
        self.merged = False
        try:
            self._build(armature, meshes)
        except Exception:
            self.close()
            raise

    @property
    def armature(self):
        return bpy.data.objects.get(self.proxy_armature_name)

    @property
    def meshes(self):
        return tuple(
            obj
            for name in self.proxy_mesh_names
            for obj in (bpy.data.objects.get(name),)
            if obj is not None
        )

    @property
    def mesh(self):
        meshes = self.meshes
        return meshes[0] if meshes else None

    def _build(self, armature, meshes):
        view_layer = bpy.context.view_layer
        sources = _eligible_meshes(meshes, armature, view_layer)
        if len(sources) < 2:
            raise RuntimeError("The model has no compatible split meshes for preview optimization")

        collection = bpy.data.collections.new(self.collection_name)
        self.scene.collection.children.link(collection)
        proxy_armature = armature.copy()
        proxy_armature.data = armature.data.copy()
        proxy_armature.name = self.proxy_armature_name
        proxy_armature.data.name = f"{self.proxy_armature_name}_Data"
        collection.objects.link(proxy_armature)
        proxy_armature.animation_data_clear()
        proxy_armature.matrix_world = armature.matrix_world.copy()
        for pose_bone in proxy_armature.pose.bones:
            for constraint in tuple(pose_bone.constraints):
                pose_bone.constraints.remove(constraint)
        proxy_armature.hide_render = True
        proxy_armature.hide_set(True)

        source_states = []
        copies = []
        source_by_copy = {}
        for index, source in enumerate(sources):
            source_states.append(
                SourceMeshState(
                    source.name,
                    source.hide_get(),
                    tuple(
                        (modifier.name, bool(modifier.show_viewport))
                        for modifier in source.modifiers
                    ),
                )
            )
            copy = source.copy()
            copy.data = source.data.copy()
            copy.name = f"{self.collection_name}_{index:03d}_{source.name}"
            for target_collection in tuple(copy.users_collection):
                target_collection.objects.unlink(copy)
            collection.objects.link(copy)
            _redirect_modifiers(copy, armature, proxy_armature)
            copies.append(copy)
            source_by_copy[copy.name] = source.name

        self.source_states = tuple(source_states)
        merge_safe = not any(
            source.animation_data is not None
            or source.constraints
            or any(modifier.type == "UV_WARP" for modifier in source.modifiers)
            for source in sources
        )
        if merge_safe:
            proxy_meshes = (self._join_copies(copies, view_layer),)
            proxy_meshes[0].name = self.proxy_mesh_name
            proxy_meshes[0].data.name = f"{self.proxy_mesh_name}_Data"
            self.merged = True
            shape_sources = {}
            for source in sources:
                shape_keys = source.data.shape_keys
                if shape_keys is None:
                    continue
                for key_block in shape_keys.key_blocks:
                    shape_sources.setdefault(key_block.name, source.name)
            self.shape_bindings = tuple(
                (proxy_meshes[0].name, key_name, source_name)
                for key_name, source_name in shape_sources.items()
            )
        else:
            proxy_meshes = tuple(copies)
            first_name = proxy_meshes[0].name
            proxy_meshes[0].name = self.proxy_mesh_name
            source_by_copy[proxy_meshes[0].name] = source_by_copy.pop(
                first_name,
                sources[0].name,
            )
            bindings = []
            for proxy_mesh in proxy_meshes:
                source_name = source_by_copy[proxy_mesh.name]
                source = bpy.data.objects.get(source_name)
                shape_keys = source.data.shape_keys if source is not None else None
                if shape_keys is None:
                    continue
                bindings.extend(
                    (proxy_mesh.name, key_block.name, source_name)
                    for key_block in shape_keys.key_blocks
                )
            self.shape_bindings = tuple(bindings)

        self.proxy_mesh_names = tuple(obj.name for obj in proxy_meshes)
        for proxy_mesh in proxy_meshes:
            shape_keys = proxy_mesh.data.shape_keys
            if shape_keys is not None:
                shape_keys.animation_data_clear()
        for source in sources:
            source.hide_set(True)
            for modifier in source.modifiers:
                modifier.show_viewport = False
        self.sync_from_canonical(armature, force=True)

    def _join_copies(self, copies, view_layer):
        selected = tuple(bpy.context.selected_objects)
        active = view_layer.objects.active
        mode = active.mode if active is not None else "OBJECT"
        if active is not None and mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            for obj in tuple(bpy.context.selected_objects):
                obj.select_set(False)
            for obj in copies:
                obj.hide_set(False)
                obj.select_set(True)
            view_layer.objects.active = copies[0]
            if bpy.ops.object.join() != {"FINISHED"}:
                raise RuntimeError("Unable to merge preview meshes")
            return view_layer.objects.active
        finally:
            for obj in tuple(bpy.context.selected_objects):
                obj.select_set(False)
            for obj in selected:
                if obj.name in view_layer.objects:
                    obj.select_set(True)
            if active is not None and active.name in view_layer.objects:
                view_layer.objects.active = active
                if mode != "OBJECT":
                    bpy.ops.object.mode_set(mode=mode)

    def sync_from_canonical(self, armature, force=False):
        proxy_armature = self.armature
        if proxy_armature is None or not self.meshes:
            return False
        changed = force or proxy_armature.matrix_world != armature.matrix_world
        proxy_armature.matrix_world = armature.matrix_world.copy()
        for pose_bone in sorted(
            proxy_armature.pose.bones,
            key=lambda bone: len(bone.parent_recursive),
        ):
            if pose_bone.name in self.driver_names:
                continue
            source = armature.pose.bones.get(pose_bone.name)
            if source is None or not force and pose_bone.matrix == source.matrix:
                continue
            pose_bone.matrix = source.matrix.copy()
            changed = True
        for proxy_name, key_name, source_name in self.shape_bindings:
            proxy_object = bpy.data.objects.get(proxy_name)
            source_object = bpy.data.objects.get(source_name)
            proxy_keys = (
                proxy_object.data.shape_keys
                if proxy_object is not None and proxy_object.type == "MESH"
                else None
            )
            source_keys = (
                source_object.data.shape_keys
                if source_object is not None and source_object.type == "MESH"
                else None
            )
            target = proxy_keys.key_blocks.get(key_name) if proxy_keys else None
            source = source_keys.key_blocks.get(key_name) if source_keys else None
            if target is None or source is None or target.value == source.value:
                continue
            target.value = source.value
            changed = True
        if changed:
            proxy_armature.update_tag(refresh={"OBJECT"})
            for proxy_mesh in self.meshes:
                proxy_mesh.update_tag(refresh={"OBJECT"})
        return changed

    def close(self):
        view_layer = bpy.context.view_layer
        for state in self.source_states:
            source = bpy.data.objects.get(state.name)
            if source is None:
                continue
            if source.name in view_layer.objects:
                source.hide_set(state.hidden)
            visibility = dict(state.modifier_visibility)
            for modifier in source.modifiers:
                if modifier.name in visibility:
                    modifier.show_viewport = visibility[modifier.name]
        collection = bpy.data.collections.get(self.collection_name)
        if collection is not None:
            for obj in tuple(collection.objects):
                data = getattr(obj, "data", None)
                object_type = obj.type
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    if object_type == "MESH":
                        bpy.data.meshes.remove(data)
                    elif object_type == "ARMATURE":
                        bpy.data.armatures.remove(data)
            bpy.data.collections.remove(collection)
