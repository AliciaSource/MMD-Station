from dataclasses import dataclass
import hashlib

import bpy


_COLLECTION_PREFIX = "_MMD_STATION_PHYSICS_VIEW_"


@dataclass
class SourceMeshState:
    name: str
    hidden: bool
    hide_render: bool
    modifier_visibility: tuple


def _eligible_meshes(meshes, armature, view_layer):
    eligible = []
    for obj in meshes:
        if (
            obj.type != "MESH"
            or obj.name not in view_layer.objects
            or obj.hide_get()
            or obj.hide_render
        ):
            continue
        armature_modifiers = [
            modifier
            for modifier in obj.modifiers
            if modifier.type == "ARMATURE" and modifier.object == armature
        ]
        if (
            len(armature_modifiers) != 1
            or not armature_modifiers[0].show_viewport
            or not armature_modifiers[0].show_render
        ):
            continue
        eligible.append(obj)
    return eligible


def _merge_safe(sources, armature):
    for source in sources:
        if source.animation_data is not None or source.constraints:
            return False
        for modifier in source.modifiers:
            if modifier.type != "ARMATURE" or modifier.object != armature:
                return False
    return True


class PhysicsPresentationProxy:
    def __init__(self, scene, root, armature, meshes, _driver_names):
        self.scene = scene
        self.root_name = root.name
        self.armature_name = armature.name
        self.source_states = ()
        self.shape_bindings = ()
        self.shape_binding_refs = ()
        self.proxy_mesh_names = ()
        identity = hashlib.blake2b(root.name.encode("utf-8"), digest_size=6).hexdigest()
        self.collection_name = f"{_COLLECTION_PREFIX}{identity}"
        self.proxy_mesh_name = f"{self.collection_name}_Mesh"
        self.merged = False
        try:
            self._build(armature, meshes)
        except Exception:
            self.close()
            raise

    @property
    def armature(self):
        return bpy.data.objects.get(self.armature_name)

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
        candidates = [
            source
            for source in _eligible_meshes(meshes, armature, view_layer)
            if _merge_safe((source,), armature)
        ]
        if len(candidates) < 2:
            raise RuntimeError("The model has no compatible split meshes for preview optimization")

        collection = bpy.data.collections.new(self.collection_name)
        self.scene.collection.children.link(collection)
        source_states = []
        shape_bindings = []
        copies = []
        shape_sources = {}
        for source_index, source in enumerate(candidates):
            source_states.append(
                SourceMeshState(
                    source.name,
                    source.hide_get(),
                    bool(source.hide_render),
                    tuple(
                        (
                            modifier.name,
                            bool(modifier.show_viewport),
                            bool(modifier.show_render),
                        )
                        for modifier in source.modifiers
                    ),
                )
            )
            shape_keys = source.data.shape_keys
            if shape_keys is not None:
                for key_block in shape_keys.key_blocks:
                    shape_sources.setdefault(key_block.name, source.name)
            copy = source.copy()
            copy.data = source.data.copy()
            copy.name = f"{self.collection_name}_{source_index:03d}_{source.name}"
            for target_collection in tuple(copy.users_collection):
                target_collection.objects.unlink(copy)
            collection.objects.link(copy)
            copies.append(copy)

        proxy_mesh = self._join_copies(copies, view_layer)
        proxy_mesh.name = self.proxy_mesh_name
        proxy_mesh.data.name = f"{self.proxy_mesh_name}_Data"
        shape_keys = proxy_mesh.data.shape_keys
        if shape_keys is not None:
            shape_bindings.extend(
                (proxy_mesh.name, key_block.name, shape_sources[key_block.name])
                for key_block in shape_keys.key_blocks
            )

        self.source_states = tuple(source_states)
        self.shape_bindings = tuple(shape_bindings)
        self._refresh_shape_binding_refs()
        self.proxy_mesh_names = (proxy_mesh.name,)
        self.merged = True

        for state in self.source_states:
            source = bpy.data.objects.get(state.name)
            if source is None:
                continue
            source.hide_set(True)
            source.hide_render = True
            for modifier in source.modifiers:
                modifier.show_viewport = False
                modifier.show_render = False
        view_layer.update()

    def _join_copies(self, copies, view_layer):
        selected_names = tuple(obj.name for obj in bpy.context.selected_objects)
        active = view_layer.objects.active
        active_name = active.name if active is not None else ""
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
            for name in selected_names:
                obj = bpy.data.objects.get(name)
                if obj is not None and obj.name in view_layer.objects:
                    obj.select_set(True)
            active = bpy.data.objects.get(active_name)
            if active is not None and active.name in view_layer.objects:
                view_layer.objects.active = active
                if mode != "OBJECT":
                    bpy.ops.object.mode_set(mode=mode)

    def _refresh_shape_binding_refs(self):
        refs = []
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
            if target is not None and source is not None:
                refs.append((target, source))
        self.shape_binding_refs = tuple(refs)

    def sync_from_canonical(self, _armature, force=False):
        changed = False
        try:
            for target, source in self.shape_binding_refs:
                if not force and target.value == source.value:
                    continue
                target.value = source.value
                changed = True
        except ReferenceError:
            self._refresh_shape_binding_refs()
            return self.sync_from_canonical(_armature, force=force)
        if changed:
            for proxy_mesh in self.meshes:
                proxy_mesh.update_tag(refresh={"OBJECT"})
        return changed

    def close(self):
        collection = bpy.data.collections.get(self.collection_name)
        if collection is not None:
            for obj in tuple(collection.objects):
                data = getattr(obj, "data", None)
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    bpy.data.meshes.remove(data)
            bpy.data.collections.remove(collection)

        view_layer = bpy.context.view_layer
        for state in self.source_states:
            source = bpy.data.objects.get(state.name)
            if source is None:
                continue
            if source.name in view_layer.objects:
                source.hide_set(state.hidden)
            source.hide_render = state.hide_render
            visibility = {
                name: (show_viewport, show_render)
                for name, show_viewport, show_render in state.modifier_visibility
            }
            for modifier in source.modifiers:
                if modifier.name in visibility:
                    modifier.show_viewport, modifier.show_render = visibility[
                        modifier.name
                    ]
