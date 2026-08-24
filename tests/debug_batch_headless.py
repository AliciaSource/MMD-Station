import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy as np
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import debug_batch, runtime


def pointer_set(items):
    return {int(item.as_pointer()) for item in items}


def layer_collection_for(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        found = layer_collection_for(child, collection)
        if found is not None:
            return found
    return None


def mesh_coordinates(mesh):
    values = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", values)
    return values.reshape((-1, 3)).astype(np.float64)


def transformed(local_vertices, matrix):
    local_h = np.ones((len(local_vertices), 4), dtype=np.float64)
    local_h[:, :3] = np.asarray(local_vertices, dtype=np.float64)
    matrix_array = np.asarray([list(row) for row in matrix], dtype=np.float64)
    return np.einsum("ij,nj->ni", matrix_array[:3, :], local_h)


def joint_arrow_local(size):
    vertices = []
    edges = []
    shaft = size * 0.75
    radius = size * 0.035
    vertices.append((0.0, 0.0, 0.0))
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
                (0, offset),
                (offset, offset + 1),
                (offset, offset + 2),
                (offset, offset + 3),
            )
        )
    return tuple(vertices), tuple(edges)


class MatrixSource:
    def __init__(self, name, matrix):
        self.name = name
        self._matrix = matrix
        self.matrix_reads = 0

    @property
    def matrix_world(self):
        self.matrix_reads += 1
        return self._matrix


matrix_source = MatrixSource("Matrix Buffer Source", Matrix.Identity(4))
matrix_buffer = np.empty((1, 4, 4), dtype=np.float64)
assert debug_batch._matrix_array(
    (matrix_source,),
    {matrix_source: Matrix.Translation((1.0, 2.0, 3.0))},
    matrix_buffer,
) is matrix_buffer
assert matrix_source.matrix_reads == 0
debug_batch._matrix_array((matrix_source,), {}, matrix_buffer)
assert matrix_source.matrix_reads == 1
invalid_matrix = Matrix.Identity(4)
invalid_matrix[0][0] = float("nan")
try:
    debug_batch._matrix_array(
        (matrix_source,),
        {matrix_source: invalid_matrix},
        matrix_buffer,
    )
except ValueError as error:
    assert "Matrix Buffer Source" in str(error)
else:
    raise AssertionError("Non-finite debug matrix was accepted")


def new_rigid(name, vertices, faces, material, smooth):
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, (), faces)
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.material_index = 0
        polygon.use_smooth = smooth
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.display_type = "SOLID"
    obj.show_wire = False
    obj.show_all_edges = False
    obj.show_in_front = True
    obj.color = (0.25, 0.5, 0.75, 1.0)
    return obj


def new_batch_fixture(target_scene, name, material):
    collection = bpy.data.collections.new(f"{name} Collection")
    target_scene.collection.children.link(collection)
    rigid = new_rigid(
        f"{name} Rigid",
        ((0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (0.0, 0.25, 0.0)),
        ((0, 1, 2),),
        material,
        False,
    )
    joint = bpy.data.objects.new(f"{name} Joint", None)
    joint.empty_display_type = "ARROWS"
    joint.empty_display_size = 0.2
    collection.objects.link(rigid)
    collection.objects.link(joint)
    session = SimpleNamespace(
        scene=target_scene,
        root_name=name,
        saved_rigid_objects={rigid.name: rigid},
        saved_joint_objects={joint.name: joint},
    )
    batch = debug_batch.PreviewDebugBatch.create(session)
    assert batch is not None and batch.valid
    return collection, rigid, joint, batch


def remove_batch_fixture(collection, rigid, joint):
    mesh = rigid.data if bpy.data.objects.get(rigid.name) is rigid else None
    for obj in (rigid, joint):
        if bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    if bpy.data.collections.get(collection.name) is collection:
        bpy.data.collections.remove(collection)


scene = bpy.context.scene
for obj in tuple(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for collection in tuple(scene.collection.children):
    scene.collection.children.unlink(collection)
    if collection.users == 0:
        bpy.data.collections.remove(collection)

view_layer_secondary = scene.view_layers.new("Debug Batch Secondary")
collection_a = bpy.data.collections.new("Debug Batch Source A")
collection_b = bpy.data.collections.new("Debug Batch Source B")
orphan_collection = bpy.data.collections.new("Debug Batch Orphan Membership")
scene.collection.children.link(collection_a)
scene.collection.children.link(collection_b)

material_a = bpy.data.materials.new("Debug Batch Material A")
material_b = bpy.data.materials.new("Debug Batch Material B")
rigid_a_vertices = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
rigid_b_vertices = (
    (-0.5, -0.5, 0.0),
    (0.5, -0.5, 0.0),
    (0.5, 0.5, 0.0),
    (-0.5, 0.5, 0.0),
)
rigid_a = new_rigid(
    "Debug Rigid A",
    rigid_a_vertices,
    ((0, 1, 2),),
    material_a,
    True,
)
rigid_b = new_rigid(
    "Debug Rigid B",
    rigid_b_vertices,
    ((0, 1, 2, 3),),
    material_b,
    False,
)
joint_a = bpy.data.objects.new("Debug Joint A", None)
joint_b = bpy.data.objects.new("Debug Joint B", None)
joint_a.empty_display_type = "ARROWS"
joint_b.empty_display_type = "ARROWS"
joint_a.empty_display_size = 0.25
joint_b.empty_display_size = 0.5
joint_a.hide_select = False
joint_b.hide_select = True

collection_a.objects.link(rigid_a)
collection_b.objects.link(rigid_a)
orphan_collection.objects.link(rigid_a)
collection_b.objects.link(rigid_b)
collection_a.objects.link(joint_a)
collection_b.objects.link(joint_b)

sources = (rigid_a, rigid_b, joint_a, joint_b)
joint_b.hide_viewport = True
original_memberships = {
    source: pointer_set(source.users_collection) for source in sources
}
original_hide_viewport = {source: bool(source.hide_viewport) for source in sources}
original_hide_select = {source: bool(source.hide_select) for source in sources}
session = SimpleNamespace(
    scene=scene,
    root_name="Debug Batch Unit Root",
    saved_rigid_objects={rigid_a.name: rigid_a, rigid_b.name: rigid_b},
    saved_joint_objects={joint_a.name: joint_a, joint_b.name: joint_b},
    settings=SimpleNamespace(preview_update_rigids=False),
)

unsupported_memberships = {
    source: pointer_set(source.users_collection) for source in sources
}
unsupported_marked_before = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
joint_a.empty_display_type = "PLAIN_AXES"
assert debug_batch.PreviewDebugBatch.create(session) is None
joint_a.empty_display_type = "ARROWS"
unsupported_marked_after = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
assert unsupported_marked_after == unsupported_marked_before
for source in sources:
    assert pointer_set(source.users_collection) == unsupported_memberships[source]
    assert bool(source.hide_viewport) == original_hide_viewport[source]
    assert bool(source.hide_select) == original_hide_select[source]
    assert debug_batch._OWNER_KEY not in source

batch = debug_batch.PreviewDebugBatch.create(session)
assert batch is not None
assert batch.usable
assert batch.valid
assert batch.visible is False
helpers = (
    batch.kinematic_rigid_object,
    batch.slow_rigid_object,
    batch.static_rigid_object,
    batch.slow_joint_object,
    batch.static_joint_object,
)
helper_meshes = (
    batch.kinematic_rigid_mesh,
    batch.slow_rigid_mesh,
    batch.static_rigid_mesh,
    batch.slow_joint_mesh,
    batch.static_joint_mesh,
)
assert len(set(helpers)) == 5
assert len(set(helper_meshes)) == 5
assert all(helper.hide_viewport for helper in helpers)
assert batch.kinematic_rigids == ()
assert batch.slow_rigids == (rigid_a, rigid_b)
assert batch.static_rigids == ()
assert batch.slow_joints == (joint_a, joint_b)
assert batch.static_joints == ()
assert len(batch.kinematic_rigid_mesh.vertices) == 0
assert len(batch.static_rigid_mesh.vertices) == 0
assert len(batch.static_joint_mesh.vertices) == 0
assert batch.slow_joint_object.hide_select
assert batch.static_joint_object.hide_select
session.debug_batch = batch
session._debug_batch_validation_depth = 0
session._debug_batch_usable_cache = False
session._debug_batch_is_usable = lambda: (
    runtime.PreviewSession._debug_batch_is_usable(session)
)
assert not runtime.PreviewSession._sync_debug_batch_visibility(session)
session.settings.preview_update_rigids = True
assert runtime.PreviewSession._sync_debug_batch_visibility(session)
assert all(not helper.hide_viewport for helper in helpers)
session.settings.preview_update_rigids = False
assert not runtime.PreviewSession._sync_debug_batch_visibility(session)
assert all(helper.hide_viewport for helper in helpers)
session.settings.preview_update_rigids = True
parking = batch.parking_collection
assert parking is not None
assert bpy.data.collections.get(parking.name) is parking
assert parking.hide_viewport
assert parking.get(debug_batch._OWNER_KEY, "") == batch.owner_token
assert parking.get(debug_batch._KIND_KEY, "") == "parking"
assert parking.get(debug_batch._SCENE_KEY, "") == scene.name
assert scene.collection.children.get(parking.name) is parking
parking_layers = tuple(
    layer_collection_for(view_layer.layer_collection, parking)
    for view_layer in scene.view_layers
)
assert len(parking_layers) == 2
assert all(layer_collection is not None for layer_collection in parking_layers)
assert batch.parking_layer_collections == parking_layers
assert all(not layer_collection.exclude for layer_collection in parking_layers)

validity_probe = sources[0]
validity_probe.hide_viewport = False
assert batch.usable
assert not batch.valid
validity_probe.hide_viewport = True
assert batch.valid
collection_a.objects.link(validity_probe)
assert batch.usable
assert not batch.valid
collection_a.objects.unlink(validity_probe)
assert batch.valid
parking.hide_viewport = False
assert not batch.usable
assert not batch.valid
parking.hide_viewport = True
assert batch.usable
assert batch.valid
scene.collection.children.unlink(parking)
assert not batch.usable
assert not batch.valid
scene.collection.children.link(parking)
assert batch.usable
assert batch.valid
assert len(batch.source_rigids) == 2
assert len(batch.source_joints) == 2
assert len(batch.rigid_mesh.vertices) == 7
assert len(batch.rigid_mesh.polygons) == 2
assert len(batch.joint_mesh.vertices) == 26
assert len(batch.joint_mesh.edges) == 24
joint_a_local, joint_a_edges = joint_arrow_local(0.25)
joint_b_local, joint_b_edges = joint_arrow_local(0.5)
assert np.max(
    np.abs(
        mesh_coordinates(batch.joint_mesh)
        - np.asarray((*joint_a_local, *joint_b_local), dtype=np.float64)
    )
) < 1.0e-6
assert tuple(tuple(edge.vertices) for edge in batch.joint_mesh.edges) == (
    *joint_a_edges,
    *tuple((first + 13, second + 13) for first, second in joint_b_edges),
)
for local_vertices, size in ((joint_a_local, 0.25), (joint_b_local, 0.5)):
    assert (size, 0.0, 0.0) in local_vertices
    assert (0.0, size, 0.0) in local_vertices
    assert (0.0, 0.0, size) in local_vertices
assert tuple(bool(polygon.use_smooth) for polygon in batch.rigid_mesh.polygons) == (
    True,
    False,
)
assert tuple(
    int(batch.rigid_mesh.materials[polygon.material_index].as_pointer())
    for polygon in batch.rigid_mesh.polygons
) == (int(material_a.as_pointer()), int(material_b.as_pointer()))
assert batch.rigid_object.display_type == "SOLID"
assert batch.rigid_object.show_in_front
assert tuple(batch.rigid_object.color) == (0.25, 0.5, 0.75, 1.0)
for helper in helpers:
    assert scene.collection.objects.get(helper.name) is helper
    assert pointer_set(helper.users_collection) == pointer_set((scene.collection,))
    for view_layer in scene.view_layers:
        assert helper.name in view_layer.objects
for source in sources:
    assert scene.objects.get(source.name) is source
    assert pointer_set(source.users_collection) == pointer_set((parking,))
    assert source.hide_viewport
    assert source.get(debug_batch._OWNER_KEY, "") == batch.owner_token
    assert source.get(debug_batch._KIND_KEY, "") == "source"
    for view_layer in scene.view_layers:
        assert source.name in view_layer.objects

rigid_a_initial = rigid_a.matrix_world.copy()
rigid_b_initial = rigid_b.matrix_world.copy()
rigid_a_matrix = Matrix.Translation((1.0, 2.0, 3.0))
rigid_b_matrix = Matrix.Translation((-2.0, 0.5, 1.0)) @ Matrix.Rotation(
    0.5,
    4,
    "Z",
)
joint_a_matrix = Matrix.Translation((4.0, 0.0, 0.0))
joint_b_matrix = Matrix.Translation((0.0, -3.0, 2.0)) @ Matrix.Rotation(
    0.25,
    4,
    "X",
)
batch.update(
    {rigid_a: rigid_a_matrix, rigid_b: rigid_b_matrix},
    {joint_a: joint_a_matrix, joint_b: joint_b_matrix},
)
buffer_objects = (
    batch._rigid_matrices,
    batch._joint_matrices,
    batch._rigid_owned_matrices,
    batch._joint_owned_matrices,
    batch._rigid_coordinates,
    batch._joint_coordinates,
    batch._rigid_values,
    batch._joint_values,
)
expected_rigid = np.concatenate(
    (
        transformed(rigid_a_vertices, rigid_a_matrix),
        transformed(rigid_b_vertices, rigid_b_matrix),
    )
)
assert np.max(np.abs(mesh_coordinates(batch.rigid_mesh) - expected_rigid)) < 1.0e-6
expected_joints = np.concatenate(
    (
        transformed(joint_a_local, joint_a_matrix),
        transformed(joint_b_local, joint_b_matrix),
    )
)
assert np.max(np.abs(mesh_coordinates(batch.joint_mesh) - expected_joints)) < 1.0e-6
assert rigid_a.matrix_world == rigid_a_initial
assert rigid_b.matrix_world == rigid_b_initial

batch.update(
    {rigid_b: rigid_b_matrix},
    {joint_b: joint_b_matrix},
)
expected_sparse_rigid = np.concatenate(
    (
        transformed(rigid_a_vertices, rigid_a.matrix_world),
        transformed(rigid_b_vertices, rigid_b_matrix),
    )
)
expected_sparse_joints = np.concatenate(
    (
        transformed(joint_a_local, joint_a.matrix_world),
        transformed(joint_b_local, joint_b_matrix),
    )
)
assert (
    np.max(
        np.abs(mesh_coordinates(batch.rigid_mesh) - expected_sparse_rigid)
    )
    < 1.0e-6
)
assert (
    np.max(
        np.abs(mesh_coordinates(batch.joint_mesh) - expected_sparse_joints)
    )
    < 1.0e-6
)
assert all(
    expected is current
    for expected, current in zip(
        buffer_objects,
        (
            batch._rigid_matrices,
            batch._joint_matrices,
            batch._rigid_owned_matrices,
            batch._joint_owned_matrices,
            batch._rigid_coordinates,
            batch._joint_coordinates,
            batch._rigid_values,
            batch._joint_values,
        ),
    )
)

batch.update({}, {}, visible=False)
assert all(helper.hide_viewport for helper in helpers)
for view_layer in scene.view_layers:
    assert all(helper.hide_get(view_layer=view_layer) for helper in helpers)
batch.update({}, {}, visible=True)
assert all(not helper.hide_viewport for helper in helpers)
for view_layer in scene.view_layers:
    assert all(not helper.hide_get(view_layer=view_layer) for helper in helpers)

steady_validation_count = batch.validation_count
for offset in (0.1, 0.2, 0.3):
    batch.update(
        {
            rigid_a: Matrix.Translation((offset, 0.0, 0.0)),
            rigid_b: rigid_b_matrix,
        },
        {joint_a: joint_a_matrix, joint_b: joint_b_matrix},
    )
    assert not batch.note_depsgraph_updates(
        {
            *helpers,
            *helper_meshes,
            batch.parking_collection,
        }
    )
assert batch.validation_count == steady_validation_count
assert batch.usable
assert batch.note_depsgraph_updates({batch.parking_collection})

helper_matrix = helpers[0].matrix_world.copy()
helpers[0].matrix_world = Matrix.Translation((4.0, 5.0, 6.0))
assert batch.note_depsgraph_updates(
    {
        *helpers,
        *helper_meshes,
        batch.parking_collection,
    }
)
helpers[0].matrix_world = helper_matrix
assert batch.usable

batch.parking_collection.hide_viewport = False
assert batch.note_depsgraph_updates(
    {
        *helpers,
        *helper_meshes,
        batch.parking_collection,
    }
)
batch.parking_collection.hide_viewport = True
assert batch.usable

rigid_a_transform = rigid_a.matrix_world.copy()
rigid_a.matrix_world = Matrix.Translation((9.0, 8.0, 7.0))
assert not batch.note_depsgraph_updates({rigid_a})
assert batch.validation_count == steady_validation_count
rigid_a.matrix_world = rigid_a_transform

rigid_a_mesh = rigid_a.data
replacement_mesh = rigid_a_mesh.copy()
rigid_a.data = replacement_mesh
assert batch.note_depsgraph_updates({rigid_a})
assert not batch.valid
rigid_a.data = rigid_a_mesh
bpy.data.meshes.remove(replacement_mesh)
assert batch.valid

joint_a_size = joint_a.empty_display_size
joint_a.empty_display_size = joint_a_size * 1.5
assert batch.note_depsgraph_updates({joint_a})
assert not batch.valid
joint_a.empty_display_size = joint_a_size
assert batch.valid

mutation_scene = bpy.data.scenes.new("Debug Batch Mutation Scene")
mutation_scene.collection.objects.link(batch.rigid_object)
assert not batch.usable
mutation_scene.collection.objects.unlink(batch.rigid_object)
assert batch.usable
mutation_scene.collection.children.link(parking)
assert not batch.usable
assert not batch.valid
mutation_scene.collection.children.unlink(parking)
assert batch.usable
assert batch.valid
mutation_scene.collection.objects.link(rigid_a)
assert not batch.valid
mutation_scene.collection.objects.unlink(rigid_a)
assert batch.valid

batch.rigid_object.matrix_world = Matrix.Translation((1.0, 0.0, 0.0))
assert not batch.usable
batch.rigid_object.matrix_world = Matrix.Identity(4)
assert batch.usable

rigid_a_vertex = rigid_a_mesh.vertices[0]
rigid_a_coordinate = rigid_a_vertex.co.copy()
rigid_a_vertex.co.x += 0.125
assert batch.note_depsgraph_updates({rigid_a_mesh})
assert not batch.valid
rigid_a_vertex.co = rigid_a_coordinate

batch.rigid_mesh.vertices.add(1)
assert not batch.usable
bpy.data.scenes.remove(mutation_scene)

owner_token = batch.owner_token
helper_names = tuple(helper.name for helper in helpers)
parking_name = parking.name
batch.close()
assert batch.closed
assert owner_token not in debug_batch._LIVE_BATCHES
assert all(bpy.data.objects.get(name) is None for name in helper_names)
assert bpy.data.collections.get(parking_name) is None
for source in sources:
    assert pointer_set(source.users_collection) == original_memberships[source]
    assert bool(source.hide_viewport) == original_hide_viewport[source]
    assert bool(source.hide_select) == original_hide_select[source]
    assert debug_batch._OWNER_KEY not in source
    assert debug_batch._SOURCE_COLLECTIONS_KEY not in source
    assert debug_batch._SOURCE_HIDE_VIEWPORT_KEY not in source

stale_batch = debug_batch.PreviewDebugBatch.create(session)
assert stale_batch is not None and stale_batch.valid
stale_owner = stale_batch.owner_token
stale_helper_names = tuple(
    helper.name
    for helper in (
        stale_batch.kinematic_rigid_object,
        stale_batch.slow_rigid_object,
        stale_batch.static_rigid_object,
        stale_batch.slow_joint_object,
        stale_batch.static_joint_object,
    )
)
stale_parking = stale_batch.parking_collection
stale_parking_name = stale_parking.name
for source in sources:
    assert pointer_set(source.users_collection) == pointer_set((stale_parking,))
debug_batch._LIVE_BATCHES.pop(stale_owner)
assert debug_batch.cleanup_stale_debug_batches() == 1
assert all(bpy.data.objects.get(name) is None for name in stale_helper_names)
assert bpy.data.collections.get(stale_parking_name) is None
for source in sources:
    assert pointer_set(source.users_collection) == original_memberships[source]
    assert bool(source.hide_viewport) == original_hide_viewport[source]
    assert bool(source.hide_select) == original_hide_select[source]
    assert debug_batch._OWNER_KEY not in source

marked_before_failure = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
original_new_joint_helper = debug_batch._new_joint_helper


def fail_new_joint_helper(*_args, **_kwargs):
    raise RuntimeError("injected debug batch helper failure")


debug_batch._new_joint_helper = fail_new_joint_helper
try:
    try:
        debug_batch.PreviewDebugBatch.create(session)
    except RuntimeError as error:
        assert str(error) == "injected debug batch helper failure"
    else:
        raise AssertionError("Injected debug batch failure did not propagate")
finally:
    debug_batch._new_joint_helper = original_new_joint_helper
marked_after_failure = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
assert marked_after_failure == marked_before_failure
for source in sources:
    assert pointer_set(source.users_collection) == original_memberships[source]
    assert bool(source.hide_viewport) == original_hide_viewport[source]
    assert debug_batch._OWNER_KEY not in source

second_scene = bpy.data.scenes.new("Debug Batch Second Scene")
second_scene.collection.objects.link(rigid_a)
before_fail_memberships = {
    source: pointer_set(source.users_collection) for source in sources
}
marked_before = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
assert debug_batch.PreviewDebugBatch.create(session) is None
marked_after = sum(
    bool(item.get(debug_batch._OWNER_KEY, ""))
    for item in (*bpy.data.objects, *bpy.data.meshes, *bpy.data.collections)
)
assert marked_after == marked_before
for source in sources:
    assert pointer_set(source.users_collection) == before_fail_memberships[source]
second_scene.collection.objects.unlink(rigid_a)
bpy.data.scenes.remove(second_scene)

isolation_a = new_batch_fixture(scene, "Debug Batch Isolation A", material_a)
isolation_b = new_batch_fixture(scene, "Debug Batch Isolation B", material_a)
isolation_a_collection, isolation_a_rigid, isolation_a_joint, isolation_a_batch = (
    isolation_a
)
isolation_b_collection, isolation_b_rigid, isolation_b_joint, isolation_b_batch = (
    isolation_b
)
isolation_a_owner = isolation_a_batch.owner_token
isolation_a_helpers = tuple(
    helper.name
    for helper in (
        isolation_a_batch.kinematic_rigid_object,
        isolation_a_batch.slow_rigid_object,
        isolation_a_batch.static_rigid_object,
        isolation_a_batch.slow_joint_object,
        isolation_a_batch.static_joint_object,
    )
)
isolation_b_owner = isolation_b_batch.owner_token


def fail_isolation_a_close():
    raise ValueError("synthetic targeted close failure")


isolation_a_batch.close = fail_isolation_a_close
assert debug_batch.cleanup_debug_batch(isolation_a_batch.owner_token)
assert isolation_a_owner not in debug_batch._LIVE_BATCHES
assert all(bpy.data.objects.get(name) is None for name in isolation_a_helpers)
assert scene.objects.get(isolation_a_rigid.name) is isolation_a_rigid
assert scene.objects.get(isolation_a_joint.name) is isolation_a_joint
assert isolation_b_owner in debug_batch._LIVE_BATCHES
assert isolation_b_batch.usable
assert isolation_b_batch.valid
isolation_b_batch.close()
remove_batch_fixture(
    isolation_a_collection,
    isolation_a_rigid,
    isolation_a_joint,
)
remove_batch_fixture(
    isolation_b_collection,
    isolation_b_rigid,
    isolation_b_joint,
)

detached_scene = bpy.data.scenes.new("Debug Batch Detached Target Scene")
detached_fixture = new_batch_fixture(
    detached_scene,
    "Debug Batch Detached Target",
    material_a,
)
detached_collection, detached_rigid, detached_joint, detached_batch = detached_fixture
detached_parking = detached_batch.parking_collection
detached_scene.collection.children.unlink(detached_collection)
assert detached_scene.collection.children.get(detached_parking.name) is detached_parking
assert all(
    detached_scene.objects.get(source.name) is source
    for source in (detached_rigid, detached_joint)
)
detached_batch.close()
assert detached_batch.closed
for source in (detached_rigid, detached_joint):
    assert detached_scene.objects.get(source.name) is source
    assert pointer_set(source.users_collection) == pointer_set(
        (detached_collection, detached_scene.collection)
    )
remove_batch_fixture(
    detached_collection,
    detached_rigid,
    detached_joint,
)
bpy.data.scenes.remove(detached_scene)

deleted_scene = bpy.data.scenes.new("Debug Batch Deleted Owner Scene")
deleted_fixture = new_batch_fixture(
    deleted_scene,
    "Debug Batch Deleted Owner",
    material_a,
)
deleted_collection, deleted_rigid, deleted_joint, deleted_batch = deleted_fixture
deleted_owner = deleted_batch.owner_token
deleted_helper_names = tuple(
    helper.name
    for helper in (
        deleted_batch.kinematic_rigid_object,
        deleted_batch.slow_rigid_object,
        deleted_batch.static_rigid_object,
        deleted_batch.slow_joint_object,
        deleted_batch.static_joint_object,
    )
)
bpy.data.scenes.remove(deleted_scene)
deleted_batch.close()
assert deleted_batch.closed
assert deleted_owner not in debug_batch._LIVE_BATCHES
assert all(bpy.data.objects.get(name) is None for name in deleted_helper_names)
assert scene.objects.get(deleted_rigid.name) is None
assert scene.objects.get(deleted_joint.name) is None
assert pointer_set(deleted_rigid.users_collection) == pointer_set((deleted_collection,))
assert pointer_set(deleted_joint.users_collection) == pointer_set((deleted_collection,))
remove_batch_fixture(deleted_collection, deleted_rigid, deleted_joint)

lost_scene = bpy.data.scenes.new("Debug Batch Lost Owner Scene")
lost_fixture = new_batch_fixture(
    lost_scene,
    "Debug Batch Lost Owner",
    material_a,
)
lost_collection, lost_rigid, lost_joint, lost_batch = lost_fixture
lost_owner = lost_batch.owner_token
lost_scene_name = lost_scene.name
lost_mesh = lost_rigid.data
bpy.data.scenes.remove(lost_scene)
bpy.data.collections.remove(lost_collection)
lost_batch.close()
assert lost_batch.closed
assert lost_owner not in debug_batch._LIVE_BATCHES
assert scene.objects.get(lost_rigid.name) is None
assert scene.objects.get(lost_joint.name) is None
assert len(lost_rigid.users_collection) == 1
assert len(lost_joint.users_collection) == 1
recovery_collection = lost_rigid.users_collection[0]
assert recovery_collection is lost_joint.users_collection[0]
assert recovery_collection.get(debug_batch._RECOVERY_KEY, "") == lost_owner
assert recovery_collection.get(debug_batch._RECOVERY_SCENE_KEY, "") == lost_scene_name
assert recovery_collection.use_fake_user
for obj in (lost_rigid, lost_joint):
    bpy.data.objects.remove(obj, do_unlink=True)
if bpy.data.meshes.get(lost_mesh.name) is lost_mesh and lost_mesh.users == 0:
    bpy.data.meshes.remove(lost_mesh)
bpy.data.collections.remove(recovery_collection)

partition_collection = bpy.data.collections.new("Debug Batch Partition Sources")
scene.collection.children.link(partition_collection)
partition_kinematic_vertices = (
    (0.0, 0.0, 0.0),
    (0.3, 0.0, 0.0),
    (0.0, 0.3, 0.0),
)
partition_slow_vertices = (
    (-0.2, -0.2, 0.0),
    (0.2, -0.2, 0.0),
    (0.2, 0.2, 0.0),
    (-0.2, 0.2, 0.0),
)
partition_static_vertices = (
    (0.0, 0.0, 0.0),
    (0.4, 0.0, 0.0),
    (0.4, 0.4, 0.0),
    (0.0, 0.4, 0.0),
    (0.2, 0.2, 0.3),
)
partition_kinematic = new_rigid(
    "Debug Batch Partition Kinematic",
    partition_kinematic_vertices,
    ((0, 1, 2),),
    material_a,
    False,
)
partition_slow = new_rigid(
    "Debug Batch Partition Slow",
    partition_slow_vertices,
    ((0, 1, 2, 3),),
    material_a,
    False,
)
partition_static = new_rigid(
    "Debug Batch Partition Static",
    partition_static_vertices,
    ((0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)),
    material_a,
    False,
)
partition_slow_joint = bpy.data.objects.new(
    "Debug Batch Partition Slow Joint",
    None,
)
partition_static_joint = bpy.data.objects.new(
    "Debug Batch Partition Static Joint",
    None,
)
partition_slow_joint.empty_display_type = "ARROWS"
partition_static_joint.empty_display_type = "ARROWS"
partition_slow_joint.empty_display_size = 0.4
partition_static_joint.empty_display_size = 0.6
partition_sources = (
    partition_kinematic,
    partition_slow,
    partition_static,
    partition_slow_joint,
    partition_static_joint,
)
for source in partition_sources:
    partition_collection.objects.link(source)
partition_static_joint.hide_viewport = True
partition_memberships = {
    source: pointer_set(source.users_collection) for source in partition_sources
}
partition_hide_viewport = {
    source: bool(source.hide_viewport) for source in partition_sources
}
partition_session = SimpleNamespace(
    scene=scene,
    root_name="Debug Batch Partition Root",
    saved_rigid_objects={
        partition_kinematic.name: partition_kinematic,
        partition_slow.name: partition_slow,
        partition_static.name: partition_static,
    },
    saved_joint_objects={
        partition_slow_joint.name: partition_slow_joint,
        partition_static_joint.name: partition_static_joint,
    },
    rigids=(partition_kinematic, partition_slow),
    joints=(partition_slow_joint,),
    rigid_modes=(0, 2),
    bone_offsets={0: Matrix.Identity(4)},
    rigid_pose_bones=(object(), None),
)
partition_batch = debug_batch.PreviewDebugBatch.create(partition_session)
assert partition_batch is not None and partition_batch.valid
assert partition_batch.kinematic_rigids == (partition_kinematic,)
assert partition_batch.slow_rigids == (partition_slow,)
assert partition_batch.static_rigids == (partition_static,)
assert partition_batch.slow_joints == (partition_slow_joint,)
assert partition_batch.static_joints == (partition_static_joint,)
assert len(partition_batch.source_rigids) == 3
assert len(partition_batch.source_joints) == 2
assert len(partition_batch.kinematic_rigid_mesh.vertices) == 3
assert len(partition_batch.slow_rigid_mesh.vertices) == 4
assert len(partition_batch.static_rigid_mesh.vertices) == 5
assert len(partition_batch.slow_joint_mesh.vertices) == 13
assert len(partition_batch.static_joint_mesh.vertices) == 13
partition_helpers = (
    partition_batch.kinematic_rigid_object,
    partition_batch.slow_rigid_object,
    partition_batch.static_rigid_object,
    partition_batch.slow_joint_object,
    partition_batch.static_joint_object,
)
partition_helper_meshes = (
    partition_batch.kinematic_rigid_mesh,
    partition_batch.slow_rigid_mesh,
    partition_batch.static_rigid_mesh,
    partition_batch.slow_joint_mesh,
    partition_batch.static_joint_mesh,
)
assert partition_batch.observed_ids.issuperset(
    {*partition_helpers, *partition_helper_meshes, *partition_sources}
)
assert (partition_batch.kinematic_update_count, partition_batch.slow_update_count, partition_batch.static_update_count) == (0, 0, 0)

kinematic_matrix = Matrix.Translation((1.0, 0.0, 0.0))
slow_matrix = Matrix.Translation((0.0, 2.0, 0.0))
slow_joint_matrix = Matrix.Translation((0.0, 0.0, 3.0))
static_matrix = Matrix.Translation((-1.0, -2.0, 0.5))
static_joint_matrix = Matrix.Translation((0.5, -0.5, 1.0))
partition_batch.update_all(
    {
        partition_kinematic: kinematic_matrix,
        partition_slow: slow_matrix,
        partition_static: static_matrix,
    },
    {
        partition_slow_joint: slow_joint_matrix,
        partition_static_joint: static_joint_matrix,
    },
    visible=False,
)
assert all(helper.hide_viewport for helper in partition_helpers)
assert (
    partition_batch.kinematic_update_count,
    partition_batch.slow_update_count,
    partition_batch.static_update_count,
) == (1, 1, 1)
expected_hidden_static = transformed(partition_static_vertices, static_matrix)
partition_static_joint_local, _partition_static_joint_edges = (
    joint_arrow_local(0.6)
)
expected_hidden_static_joint = transformed(
    partition_static_joint_local,
    static_joint_matrix,
)
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_rigid_mesh)
        - expected_hidden_static
    )
) < 1.0e-6
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_joint_mesh)
        - expected_hidden_static_joint
    )
) < 1.0e-6
partition_batch.update_kinematic(
    {partition_kinematic: kinematic_matrix},
    visible=True,
)
assert all(not helper.hide_viewport for helper in partition_helpers)
assert (
    partition_batch.kinematic_update_count,
    partition_batch.slow_update_count,
    partition_batch.static_update_count,
) == (2, 1, 1)
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_rigid_mesh)
        - expected_hidden_static
    )
) < 1.0e-6
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_joint_mesh)
        - expected_hidden_static_joint
    )
) < 1.0e-6
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.kinematic_rigid_mesh)
        - transformed(partition_kinematic_vertices, kinematic_matrix)
    )
) < 1.0e-6

static_rigid_before = mesh_coordinates(partition_batch.static_rigid_mesh).copy()
static_joint_before = mesh_coordinates(partition_batch.static_joint_mesh).copy()
for offset in (0.1, 0.2, 0.3):
    current_slow_matrix = Matrix.Translation((offset, 2.0, 0.0))
    partition_batch.update_slow(
        {partition_slow: current_slow_matrix},
        {partition_slow_joint: slow_joint_matrix},
    )
assert partition_batch.slow_update_count == 4
assert partition_batch.static_update_count == 1
assert np.array_equal(
    mesh_coordinates(partition_batch.static_rigid_mesh),
    static_rigid_before,
)
assert np.array_equal(
    mesh_coordinates(partition_batch.static_joint_mesh),
    static_joint_before,
)
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.slow_rigid_mesh)
        - transformed(partition_slow_vertices, current_slow_matrix)
    )
) < 1.0e-6

second_static_matrix = Matrix.Translation((-2.0, -1.0, 0.75))
second_static_joint_matrix = Matrix.Translation((1.5, -0.25, 2.0))
partition_batch.update_static(
    {partition_static: second_static_matrix},
    {partition_static_joint: second_static_joint_matrix},
    visible=False,
)
assert partition_batch.static_update_count == 2
assert all(helper.hide_viewport for helper in partition_helpers)
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_rigid_mesh)
        - transformed(partition_static_vertices, second_static_matrix)
    )
) < 1.0e-6
assert np.max(
    np.abs(
        mesh_coordinates(partition_batch.static_joint_mesh)
        - transformed(partition_static_joint_local, second_static_joint_matrix)
    )
) < 1.0e-6
partition_batch.update_slow({}, {}, visible=False)
assert partition_batch.slow_update_count == 4
assert all(helper.hide_viewport for helper in partition_helpers)
for view_layer in scene.view_layers:
    assert all(
        helper.hide_get(view_layer=view_layer)
        for helper in partition_helpers
    )
partition_batch.update_kinematic({}, visible=True)
assert partition_batch.kinematic_update_count == 3
assert all(not helper.hide_viewport for helper in partition_helpers)
for view_layer in scene.view_layers:
    assert all(
        not helper.hide_get(view_layer=view_layer)
        for helper in partition_helpers
    )

counts_before_all = (
    partition_batch.kinematic_update_count,
    partition_batch.slow_update_count,
    partition_batch.static_update_count,
)
partition_batch.update_all(
    {
        partition_kinematic: kinematic_matrix,
        partition_slow: slow_matrix,
        partition_static: static_matrix,
    },
    {
        partition_slow_joint: slow_joint_matrix,
        partition_static_joint: static_joint_matrix,
    },
)
assert (
    partition_batch.kinematic_update_count,
    partition_batch.slow_update_count,
    partition_batch.static_update_count,
) == tuple(count + 1 for count in counts_before_all)
assert not partition_batch.note_depsgraph_updates(
    {*partition_helpers, *partition_helper_meshes}
)
partition_batch.static_rigid_object.matrix_world = Matrix.Translation((1.0, 0.0, 0.0))
assert not partition_batch.usable
partition_batch.static_rigid_object.matrix_world = Matrix.Identity(4)
assert partition_batch.usable and partition_batch.valid

partition_helper_names = tuple(helper.name for helper in partition_helpers)
partition_mesh_names = tuple(mesh.name for mesh in partition_helper_meshes)
exit_rigid_matrices = {
    partition_kinematic: kinematic_matrix,
    partition_slow: slow_matrix,
    partition_static: static_matrix,
}
exit_joint_matrices = {
    partition_slow_joint: slow_joint_matrix,
    partition_static_joint: static_joint_matrix,
}
exit_session = SimpleNamespace(
    debug_batch=partition_batch,
    _debug_batch_exit_pending=True,
    _debug_batch_validation_pending=True,
    _debug_batch_usable_cache=True,
    _debug_rigid_matrices=exit_rigid_matrices,
    _debug_joint_matrices=exit_joint_matrices,
)
assert runtime.PreviewSession._deactivate_debug_batch(exit_session)
assert exit_session.debug_batch is None
assert not exit_session._debug_batch_exit_pending
assert partition_batch.closed
assert all(bpy.data.objects.get(name) is None for name in partition_helper_names)
assert all(bpy.data.meshes.get(name) is None for name in partition_mesh_names)
for source in partition_sources:
    assert pointer_set(source.users_collection) == partition_memberships[source]
    assert bool(source.hide_viewport) == partition_hide_viewport[source]
    assert debug_batch._OWNER_KEY not in source
for source, expected in (*exit_rigid_matrices.items(), *exit_joint_matrices.items()):
    assert max(
        abs(actual - target)
        for actual_row, target_row in zip(source.matrix_world, expected)
        for actual, target in zip(actual_row, target_row)
    ) < 1.0e-7

partition_source_meshes = (
    partition_kinematic.data,
    partition_slow.data,
    partition_static.data,
)
for source in partition_sources:
    bpy.data.objects.remove(source, do_unlink=True)
for mesh in partition_source_meshes:
    if bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
bpy.data.collections.remove(partition_collection)

assert debug_batch.cleanup_stale_debug_batches() == 0
print(
    "SPX_DEBUG_BATCH_HEADLESS_OK",
    "rigids=2",
    "joints=2",
    "view_layers=2",
    "geometry=ok",
    "joint_arrows=directional_outline",
    "unsupported_joint_display=per_object_fallback",
    "joint_selection=batched_unselectable_restore_exact",
    "pose_exit_matrix_flush=exact",
    "matrix_buffers=ok",
    "sparse_fallback=ok",
    "finite_validation=ok",
    "materials=ok",
    "smooth=ok",
    "visibility=ok",
    "parking=ok",
    "close_restore=ok",
    "failure_cleanup=ok",
    "stale_cleanup=ok",
    "multiscene_fail_closed=ok",
    "runtime_mutation_fail_closed=ok",
    "targeted_cleanup_isolation=ok",
    "detached_target_scene_fallback=ok",
    "deleted_scene_recovery=ok",
    "partitions=ok",
    "partition_counts=ok",
    "partition_visibility=ok",
    "static_steady=ok",
)
