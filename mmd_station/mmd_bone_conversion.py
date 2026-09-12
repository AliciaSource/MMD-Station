"""Sample a bone morph on detached, animation-free evaluation copies."""
import bpy
from mathutils import Matrix


def sample(context, armature, morph, weighted_vertices):
    objects, meshes, armatures = [], [], []
    try:
        rig = armature.copy()
        objects.append(rig)
        rig.data = armature.data.copy()
        armatures.append(rig.data)
        rig.animation_data_clear()
        rig.data.animation_data_clear()
        rig.parent = None
        rig.matrix_world = armature.matrix_world.copy()
        rig.mmd_type = "NONE"
        for constraint in list(rig.constraints):
            rig.constraints.remove(constraint)
        context.scene.collection.objects.link(rig)
        rig.hide_set(False)
        rig.hide_viewport = False
        rig.data.pose_position = "POSE"
        for bone in rig.pose.bones:
            for constraint in list(bone.constraints):
                bone.constraints.remove(constraint)
            bone.matrix_basis = Matrix.Identity(4)
        for offset in morph.data:
            bone = rig.pose.bones.get(offset.bone)
            if bone is None:
                continue
            bone.rotation_mode = "QUATERNION"
            bone.location += offset.location
            bone.rotation_quaternion = bone.rotation_quaternion @ offset.rotation
            bone.scale = tuple(a * b for a, b in zip(bone.scale, offset.spx_scale))
        results = {}
        for source, indices in weighted_vertices.items():
            obj = source.copy()
            objects.append(obj)
            obj.data = source.data.copy()
            meshes.append(obj.data)
            obj.animation_data_clear()
            obj.data.animation_data_clear()
            obj.parent = None
            obj.matrix_world = source.matrix_world.copy()
            for constraint in list(obj.constraints):
                obj.constraints.remove(constraint)
            basis = source.data.shape_keys.reference_key if source.data.shape_keys else None
            coordinates = [v.co.copy() for v in (basis.data if basis else source.data.vertices)]
            obj.shape_key_clear()
            for vertex, co in zip(obj.data.vertices, coordinates):
                vertex.co = co
            for modifier in list(obj.modifiers):
                if modifier.type == "ARMATURE" and modifier.object == armature:
                    modifier.object = rig
                    modifier.show_viewport = True
                else:
                    obj.modifiers.remove(modifier)
            context.scene.collection.objects.link(obj)
            obj.hide_set(False)
            obj.hide_viewport = False
            context.view_layer.update()
            evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
            evaluated_mesh = evaluated.to_mesh()
            try:
                if len(evaluated_mesh.vertices) != len(coordinates):
                    raise ValueError("Bone morph evaluation changed vertex count")
                for index in indices:
                    coordinates[index] = evaluated_mesh.vertices[index].co.copy()
                results[source] = coordinates
            finally:
                evaluated.to_mesh_clear()
        return results
    finally:
        for obj in reversed(objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)
        for arm in armatures:
            bpy.data.armatures.remove(arm)


def write_shape_keys(results, name):
    backups, created, bases = [], [], []
    try:
        for obj, coordinates in results.items():
            if not obj.data.shape_keys:
                bases.append((obj, obj.shape_key_add(name="Basis", from_mix=False)))
            keys = obj.data.shape_keys
            key = keys.key_blocks.get(name)
            if key == keys.reference_key:
                raise ValueError("Cannot overwrite the reference shape key")
            if key is None:
                key = obj.shape_key_add(name=name, from_mix=False)
                key.value = 0.0
                created.append((obj, key))
            else:
                backups.append((key, [v.co.copy() for v in key.data], key.relative_key))
            key.relative_key = keys.reference_key
            for point, co in zip(key.data, coordinates):
                point.co = co
    except Exception:
        for key, coordinates, relative in backups:
            key.relative_key = relative
            for point, co in zip(key.data, coordinates):
                point.co = co
        for obj, key in reversed(created):
            obj.shape_key_remove(key)
        for obj, key in reversed(bases):
            obj.shape_key_remove(key)
        raise
