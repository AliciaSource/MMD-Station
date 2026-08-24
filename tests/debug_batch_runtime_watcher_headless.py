import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import debug_batch, runtime


def new_rigid(name, material):
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(
        ((0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (0.0, 0.25, 0.0)),
        (),
        ((0, 1, 2),),
    )
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.display_type = "SOLID"
    obj.show_in_front = True
    return obj


scene = bpy.context.scene
for obj in tuple(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for collection in tuple(scene.collection.children):
    scene.collection.children.unlink(collection)
    if collection.users == 0:
        bpy.data.collections.remove(collection)

source_collection = bpy.data.collections.new("Debug Batch Watcher Sources")
scene.collection.children.link(source_collection)
material = bpy.data.materials.new("Debug Batch Watcher Material")
solver_rigid = new_rigid("Debug Batch Solver Rigid", material)
non_solver_rigid = new_rigid("Debug Batch Non Solver Rigid", material)
solver_joint = bpy.data.objects.new("Debug Batch Solver Joint", None)
non_solver_joint = bpy.data.objects.new("Debug Batch Non Solver Joint", None)
solver_joint.empty_display_type = "ARROWS"
non_solver_joint.empty_display_type = "ARROWS"
for source in (solver_rigid, non_solver_rigid, solver_joint, non_solver_joint):
    source_collection.objects.link(source)

batch_session = SimpleNamespace(
    scene=scene,
    root_name="Debug Batch Watcher Root",
    saved_rigid_objects={
        solver_rigid.name: solver_rigid,
        non_solver_rigid.name: non_solver_rigid,
    },
    saved_joint_objects={
        solver_joint.name: solver_joint,
        non_solver_joint.name: non_solver_joint,
    },
    rigids=(solver_rigid,),
    joints=(solver_joint,),
    rigid_modes=(0,),
    bone_offsets={0: Matrix.Identity(4)},
    rigid_pose_bones=(object(),),
)
batch = debug_batch.PreviewDebugBatch.create(batch_session)
assert batch is not None and batch.valid
assert batch.kinematic_rigids == (solver_rigid,)
assert batch.slow_rigids == ()
assert batch.static_rigids == (non_solver_rigid,)
assert batch.slow_joints == (solver_joint,)
assert batch.static_joints == (non_solver_joint,)
assert len(batch.kinematic_rigid_mesh.vertices) == 3
assert len(batch.slow_rigid_mesh.vertices) == 0
assert len(batch.static_rigid_mesh.vertices) == 3
assert len(batch.slow_joint_mesh.vertices) == 13
assert len(batch.static_joint_mesh.vertices) == 13
helper_objects = (
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

root = bpy.data.objects.new("Debug Batch Watcher Runtime Root", None)
armature_data = bpy.data.armatures.new("Debug Batch Watcher Armature Data")
armature = bpy.data.objects.new("Debug Batch Watcher Armature", armature_data)
scene.collection.objects.link(root)
scene.collection.objects.link(armature)
fake_session = SimpleNamespace(
    scene=scene,
    root=root,
    armature=armature,
    _binding_ids=frozenset((solver_rigid, solver_joint)),
    _binding_names_changed=lambda _updates=None: False,
    _binding_names_dirty=False,
    debug_batch=batch,
    _debug_batch_validation_pending=False,
    _debug_batch_validation_depth=0,
    _debug_batch_usable_cache=True,
    display_rig=None,
    _display_rig_valid_cache=False,
    _display_rig_validation_depth=0,
    pose_input=None,
)


def notify(*ids):
    depsgraph = SimpleNamespace(
        updates=tuple(SimpleNamespace(id=item) for item in ids)
    )
    runtime._ensure_preview_model_ids_after_update(scene, depsgraph)


previous_sessions = dict(runtime._ACTIVE_SESSIONS)
runtime._ACTIVE_SESSIONS.clear()
runtime._ACTIVE_SESSIONS["Debug Batch Watcher"] = fake_session
try:
    assert non_solver_rigid not in fake_session._binding_ids
    assert non_solver_joint not in fake_session._binding_ids
    assert runtime.PreviewSession._refresh_debug_batch_usable_cache(
        fake_session
    )
    initial_validation_count = batch.validation_count
    for offset in (0.1, 0.2, 0.3, 0.4):
        batch.update_kinematic(
            {solver_rigid: Matrix.Translation((offset, 0.0, 0.0))},
        )
        batch.update_slow({}, {solver_joint: Matrix.Identity(4)})
        notify(*helper_objects, *helper_meshes, batch.parking_collection)
        assert not fake_session._debug_batch_validation_pending
        assert batch.validation_count == initial_validation_count
        assert batch.static_update_count == 0

    assert batch.kinematic_update_count == 4
    assert batch.slow_update_count == 4
    assert batch.static_update_count == 0

    assert not batch.note_depsgraph_updates({helper_objects[0]})
    helper_matrix = helper_objects[0].matrix_world.copy()
    helper_objects[0].matrix_world = Matrix.Translation((1.0, 0.0, 0.0))
    assert batch.note_depsgraph_updates({helper_objects[0]})
    assert not batch.valid
    helper_objects[0].matrix_world = helper_matrix
    assert batch.valid

    assert batch.note_depsgraph_updates({batch.parking_collection})
    assert batch.valid
    initial_validation_count = batch.validation_count

    non_solver_transform = non_solver_rigid.matrix_world.copy()
    non_solver_rigid.matrix_world = Matrix.Translation((3.0, 2.0, 1.0))
    notify(non_solver_rigid)
    assert not fake_session._debug_batch_validation_pending
    assert batch.validation_count == initial_validation_count
    non_solver_rigid.matrix_world = non_solver_transform

    non_solver_joint.hide_viewport = False
    notify(non_solver_joint)
    assert fake_session._debug_batch_validation_pending
    non_solver_joint.hide_viewport = True
    assert batch.valid
    fake_session._debug_batch_validation_pending = False

    count_before_geometry_dirty = batch.validation_count
    notify(non_solver_rigid.data)
    assert fake_session._debug_batch_validation_pending
    assert not batch.valid
    assert batch.validation_count == count_before_geometry_dirty + 1

    mode_probe = object.__new__(runtime.PreviewSession)
    mode_probe.armature = SimpleNamespace(mode="OBJECT")
    mode_probe.display_rig = object()
    mode_probe.debug_batch = object()
    mode_probe.debug_batch_unavailable = False
    mode_probe._debug_batch_exit_pending = False
    mode_probe.pose_input = SimpleNamespace(force_debug_update=False)
    mode_calls = []
    mode_probe._deactivate_debug_batch = lambda: mode_calls.append("deactivate") or True
    mode_probe._activate_debug_batch = lambda: mode_calls.append("activate") or True
    assert not mode_probe._sync_debug_batch_mode()
    assert mode_calls == []
    assert mode_probe._debug_batch_exit_pending
    assert mode_probe.pose_input.force_debug_update
    mode_probe.armature.mode = "POSE"
    mode_probe.debug_batch = None
    assert mode_probe._sync_debug_batch_mode()
    assert mode_calls == ["activate"]
    assert not mode_probe._debug_batch_exit_pending
    mode_probe.debug_batch = None
    mode_probe.debug_batch_unavailable = True
    assert not mode_probe._sync_debug_batch_mode()
    assert mode_calls == ["activate"]

    class ExplodingBatch:
        @property
        def usable(self):
            raise RuntimeError("usable sentinel")

    depth_probe = object.__new__(runtime.PreviewSession)
    depth_probe.armature = SimpleNamespace(mode="POSE")
    depth_probe.display_rig = None
    depth_probe._display_rig_validation_depth = 0
    depth_probe.debug_batch = ExplodingBatch()
    depth_probe._debug_batch_validation_pending = True
    depth_probe._debug_batch_validation_depth = 0
    depth_probe._debug_batch_usable_cache = True
    try:
        depth_probe.tick()
    except RuntimeError as error:
        assert str(error) == "usable sentinel"
    else:
        raise AssertionError("Usable cache probe must raise")
    assert depth_probe._display_rig_validation_depth == 0
    assert depth_probe._debug_batch_validation_depth == 0

    class ExplodingValidBatch:
        @property
        def valid(self):
            raise RuntimeError("valid sentinel")

    pending_probe = object.__new__(runtime.PreviewSession)
    pending_probe.debug_batch = ExplodingValidBatch()
    pending_probe._debug_batch_validation_pending = True
    pending_probe._debug_batch_validation_depth = 1
    pending_probe._debug_batch_usable_cache = True
    try:
        pending_probe._update_display_rig_state(False, True)
    except RuntimeError as error:
        assert str(error) == "valid sentinel"
    else:
        raise AssertionError("Valid probe must raise")
    assert pending_probe._debug_batch_validation_pending

    class ExitWorldProbe:
        def __init__(self, calls):
            self.calls = calls

        def outputs(self, **kwargs):
            self.calls.append(("outputs", kwargs))
            return ("rigid output", "bone output", "joint output")

    def make_exit_probe(apply_error=None, update_error=None):
        calls = []
        probe = object.__new__(runtime.PreviewSession)
        probe.display_rig = None
        probe._display_rig_validation_depth = 0
        probe._debug_batch_validation_depth = 0
        probe._debug_batch_exit_pending = True
        probe._asynchronous_presentation = True
        probe._debug_presentation = False
        probe._kinematic_debug_presentation = False
        probe.mmd_step_count = 7
        probe.world = ExitWorldProbe(calls)
        probe._sync_debug_batch_mode = lambda: None
        probe._refresh_debug_batch_usable_cache = lambda: None
        probe.prepare_step = lambda: None
        probe._optimized_input_enabled = lambda: True
        probe._isolated_runtime_compatible = lambda: True
        probe._update_display_rig_state = lambda _interactive, _compatible: False
        probe.step_solver = lambda: False

        def apply_step(*args, **kwargs):
            calls.append(("apply", args, kwargs))
            assert not probe._asynchronous_presentation
            assert probe._debug_presentation
            assert probe._kinematic_debug_presentation
            probe.mmd_step_count += 1
            if apply_error is not None:
                raise apply_error

        def deactivate():
            calls.append(("deactivate",))
            probe._debug_batch_exit_pending = False
            return True

        probe.apply_step = apply_step
        probe._deactivate_debug_batch = deactivate
        def update_view_layer():
            calls.append(("update",))
            if update_error is not None:
                raise update_error

        probe.update_view_layer = update_view_layer
        return probe, calls

    zero_step_probe, zero_step_calls = make_exit_probe()
    zero_step_probe.tick()
    assert [call[0] for call in zero_step_calls] == [
        "outputs",
        "apply",
        "deactivate",
        "update",
    ]
    assert zero_step_calls[0][1] == {
        "include_debug": True,
        "include_transforms": True,
        "include_joint_states": True,
    }
    assert zero_step_calls[1][2] == {"present_output": True}
    assert not zero_step_probe._debug_batch_exit_pending
    assert zero_step_probe._asynchronous_presentation
    assert not zero_step_probe._debug_presentation
    assert not zero_step_probe._kinematic_debug_presentation
    assert zero_step_probe.mmd_step_count == 7
    assert zero_step_probe._display_rig_validation_depth == 0
    assert zero_step_probe._debug_batch_validation_depth == 0

    failure_probe, failure_calls = make_exit_probe(
        RuntimeError("apply sentinel"),
        RuntimeError("update sentinel"),
    )
    try:
        failure_probe.tick()
    except RuntimeError as error:
        assert str(error) == "apply sentinel"
        assert any("update sentinel" in note for note in error.__notes__)
    else:
        raise AssertionError("Exit refresh probe must raise")
    assert [call[0] for call in failure_calls] == [
        "outputs",
        "apply",
        "deactivate",
        "update",
    ]
    assert not failure_probe._debug_batch_exit_pending
    assert failure_probe._asynchronous_presentation
    assert not failure_probe._debug_presentation
    assert not failure_probe._kinematic_debug_presentation
    assert failure_probe.mmd_step_count == 7
    assert failure_probe._display_rig_validation_depth == 0
    assert failure_probe._debug_batch_validation_depth == 0
finally:
    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS.update(previous_sessions)
    batch.close()

source_meshes = (solver_rigid.data, non_solver_rigid.data)
for obj in (
    solver_rigid,
    non_solver_rigid,
    solver_joint,
    non_solver_joint,
    root,
    armature,
):
    if bpy.data.objects.get(obj.name) is obj:
        bpy.data.objects.remove(obj, do_unlink=True)
for mesh in source_meshes:
    if bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
if bpy.data.armatures.get(armature_data.name) is armature_data:
    bpy.data.armatures.remove(armature_data)
if bpy.data.collections.get(source_collection.name) is source_collection:
    bpy.data.collections.remove(source_collection)

assert debug_batch.cleanup_stale_debug_batches() == 0
print(
    "SPX_DEBUG_BATCH_RUNTIME_WATCHER_OK",
    "non_solver_source=ok",
    "mesh_dirty=ok",
    "transform_only=ok",
    "helper_self_write_guard=ok",
    "partition_watchers=ok",
    "pose_mode_selection_boundary=ok",
    "unsupported_retry_suppressed=ok",
    "zero_step_exit_refresh=ok",
    "refresh_failure_cleanup=ok",
    "static_steady=ok",
    "steady_full_validation=0",
)
