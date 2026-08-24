import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime import physics_bridge
from mmd_skirt_proxy_creator.physics_preview import runtime


class SentinelError(RuntimeError):
    pass


class FakeSolver:
    created = []

    def __init__(
        self,
        bodies,
        joints,
        world_scale,
        library=None,
        body_source_eulers=(),
        joint_source_eulers=(),
    ):
        self.bodies = tuple(bodies)
        self.joints = tuple(joints)
        self.world_scale = world_scale
        self.library = library
        self.body_source_eulers = tuple(body_source_eulers)
        self.joint_source_eulers = tuple(joint_source_eulers)
        self.gravity = None
        self.closed = False
        self.__class__.created.append(self)

    @property
    def body_count(self):
        return len(self.bodies)

    def set_gravity(self, gravity):
        self.gravity = tuple(gravity)

    def close(self):
        self.closed = True


class FakePoseInput:
    def __init__(self):
        self.invalidations = 0

    def invalidate(self):
        self.invalidations += 1


class FakeDisplayRig:
    def __init__(self, apply_error=None):
        self.apply_error = apply_error
        self.capture_calls = 0
        self.apply_calls = 0

    def capture_input_pose(self):
        self.capture_calls += 1

    def apply_input_pose(self):
        self.apply_calls += 1
        if self.apply_error is not None:
            raise self.apply_error


class FakeScene:
    _next_pointer = 1000

    def __init__(self, name):
        self.name = name
        self.frame_current = 1
        self.frame_subframe = 0.0
        self.surface_proxy_creator = SimpleNamespace()
        self._pointer = self.__class__._next_pointer
        self.__class__._next_pointer += 1

    def as_pointer(self):
        return self._pointer


class FakeRoot:
    def __init__(
        self,
        name,
        descriptor,
        interaction_group="group",
        joint_body_pairs=(),
    ):
        self.name = name
        self.descriptor = descriptor
        self.spx_mmd_interaction_group_id = interaction_group
        self.joint_body_pairs = tuple(joint_body_pairs)


def body_descriptors(root):
    value = root.descriptor
    return list(value) if isinstance(value, (list, tuple)) else [value]


def joint_descriptors(root):
    result = []
    for body_a, body_b in root.joint_body_pairs:
        desc = runtime.JointDesc()
        desc.body_a = body_a
        desc.body_b = body_b
        result.append(desc)
    return result


class FakeSession:
    def __init__(self, scene, root, solver_target="MMD"):
        self.scene = scene
        self.scene_name = scene.name
        self.settings = SimpleNamespace(
            preview_gravity=(0.0, 0.0, -9.8),
            preview_running=True,
            preview_status="running",
        )
        self.root = root
        self.root_name = root.name
        self.armature = SimpleNamespace()
        self.saved_bone_connections = {}
        self.solver_target = solver_target
        self.import_scale = 0.08
        self.library = None
        self.body_descs = body_descriptors(root)
        self.joint_descs = joint_descriptors(root)
        self.body_source_eulers = [()] * len(self.body_descs)
        self.joint_source_eulers = [()] * len(self.joint_descs)
        self.body_offset = 0
        self.joint_offset = 0
        self.solver = None
        self.world = None
        self.last_output_basis = {}
        self.mmd_step_count = 0
        self.pose_input = FakePoseInput()
        self.display_rig = None
        self.display_rig_unavailable = False
        self.snapshot_reset_pending = False
        self.closed = False
        self.restore_calls = 0
        self.rebuild_calls = 0
        self.deactivate_calls = 0
        self.deactivate_error = None

    @property
    def isolated_output_active(self):
        return self.display_rig is not None

    def _capture_driver_basis(self):
        return {}

    def _restore_start_snapshot(self):
        self.restore_calls += 1

    def rebuild_descriptors(self):
        self.rebuild_calls += 1
        self.body_descs = body_descriptors(self.root)
        self.joint_descs = joint_descriptors(self.root)
        self.body_source_eulers = [()] * len(self.body_descs)
        self.joint_source_eulers = [()] * len(self.joint_descs)

    def _rebind_blender_data(self, force=False, allow_recreated=False):
        assert force
        return False

    def _deactivate_display_rig(self, **_kwargs):
        self.deactivate_calls += 1
        if self.deactivate_error is not None:
            raise self.deactivate_error
        return False

    def update_view_layer(self):
        pass

    def close(self, restore=True):
        self.closed = True


def clear_runtime_state():
    for world in tuple(runtime._ACTIVE_WORLDS.values()):
        try:
            world.close()
        except Exception:
            pass
        for session in tuple(world.sessions):
            if session in world.sessions:
                world.remove(session)
    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_WORLDS.clear()
    runtime._RUNTIME_SUSPENDED = False


physics_bridge.install()
original_solver = runtime.Solver
original_preview_session = runtime.PreviewSession
original_clear_feedback = evaluator.clear_physics_feedback
original_capture_bindings = evaluator.capture_physics_bindings
original_discard_session = evaluator.discard_session
runtime.Solver = FakeSolver
evaluator.clear_physics_feedback = lambda _root: None
evaluator.capture_physics_bindings = lambda _root, _session: True


try:
    clear_runtime_state()

    scene_a = FakeScene("Undo descriptor scene A")
    scene_b = FakeScene("Undo descriptor scene B")
    session_a = FakeSession(scene_a, FakeRoot("Undo root A", "before A"))
    session_b = FakeSession(scene_b, FakeRoot("Undo root B", "before B"))
    world_a = runtime.PreviewWorld(("undo", "A"), 0.08, "MMD", None)
    world_b = runtime.PreviewWorld(("undo", "B"), 0.08, "MMD", None)
    world_a.add(session_a)
    world_b.add(session_b)
    world_a.reset(prepared_session=session_a)
    world_b.reset(prepared_session=session_b)
    generation_a = world_a.generation
    generation_b = world_b.generation
    restore_a = session_a.restore_calls
    restore_b = session_b.restore_calls
    session_a.root.descriptor = "after undo A"
    session_b.root.descriptor = "after undo B"
    runtime._ACTIVE_SESSIONS.update(
        {session_a.root_name: session_a, session_b.root_name: session_b}
    )
    runtime._ACTIVE_WORLDS.update({world_a.key: world_a, world_b.key: world_b})
    runtime._RUNTIME_SUSPENDED = True

    rebound = runtime.resume_after_undo_redo()

    assert rebound == 0
    assert world_a.generation == generation_a + 1
    assert world_b.generation == generation_b + 1
    assert world_a.solver.bodies == ("after undo A",)
    assert world_b.solver.bodies == ("after undo B",)
    assert session_a.rebuild_calls == 1
    assert session_b.rebuild_calls == 1
    assert session_a.restore_calls == restore_a
    assert session_b.restore_calls == restore_b
    assert not runtime._RUNTIME_SUSPENDED
    print("SPX_UNDO_WORLD_DESCRIPTOR_REBUILD_OK")

    clear_runtime_state()

    scene = FakeScene("Reset display rollback scene")
    session = FakeSession(
        scene,
        FakeRoot("Reset display rollback root", "stable body"),
    )
    world = runtime.PreviewWorld(("reset", "display rollback"), 0.08, "MMD", None)
    world.add(session)
    world.reset(prepared_session=session)
    runtime._ACTIVE_SESSIONS[session.root_name] = session
    runtime._ACTIVE_WORLDS[world.key] = world
    stable_solver = world.solver
    stable_generation = world.generation
    stable_invalidations = session.pose_input.invalidations
    display_error = SentinelError("reset display apply failed")
    display_rig = FakeDisplayRig(display_error)
    session.display_rig = display_rig
    FakeSolver.created.clear()

    try:
        world.reset(prepared_session=session)
    except SentinelError as error:
        assert error is display_error
    else:
        raise AssertionError("Injected reset-time DisplayRig failure did not propagate")

    assert len(FakeSolver.created) == 1
    failed_solver = FakeSolver.created[0]
    assert failed_solver.closed
    assert world.solver is stable_solver
    assert session.solver is stable_solver
    assert not stable_solver.closed
    assert world.generation == stable_generation
    assert session.pose_input.invalidations == stable_invalidations
    assert display_rig.capture_calls == 1
    assert display_rig.apply_calls == 1
    print("SPX_RESET_DISPLAY_FAILURE_ROLLBACK_OK")

    clear_runtime_state()

    scene = FakeScene("Shared rollback scene")
    settings = scene.surface_proxy_creator
    settings.preview_running = True
    settings.preview_status = "running"
    existing_root_a = FakeRoot(
        "Existing shared root A",
        ("existing A0", "existing A1"),
        "shared",
        joint_body_pairs=((0, 1),),
    )
    existing_root_b = FakeRoot("Existing shared root B", "existing B0", "shared")
    failed_root = FakeRoot(
        "Failed shared root",
        ("failed 0", "failed 1"),
        "shared",
        joint_body_pairs=((0, 1),),
    )
    existing_a = FakeSession(scene, existing_root_a)
    existing_b = FakeSession(scene, existing_root_b)
    failed = FakeSession(scene, failed_root)
    world_key = (
        "group",
        int(scene.as_pointer()),
        "MMD",
        0.08,
        "shared",
    )
    shared_world = runtime.PreviewWorld(world_key, 0.08, "MMD", None)
    shared_world.add(existing_a)
    shared_world.add(existing_b)
    shared_world.reset()
    shared_initial_solver = shared_world.solver
    existing_restore_calls = {
        existing_a: existing_a.restore_calls,
        existing_b: existing_b.restore_calls,
    }
    runtime._ACTIVE_SESSIONS.update(
        {
            existing_a.root_name: existing_a,
            existing_b.root_name: existing_b,
        }
    )
    runtime._ACTIVE_WORLDS[world_key] = shared_world
    FakeSolver.created.clear()
    capture_records = []

    def fail_new_capture(_root, preview_session):
        capture_records.append((preview_session, preview_session.solver))
        if preview_session is failed:
            raise SentinelError("capture failed for new session")
        return True

    evaluator.capture_physics_bindings = fail_new_capture
    runtime.PreviewSession = lambda _scene, _settings, _root: failed
    context = SimpleNamespace(scene=scene)
    try:
        runtime._start_preview(context, failed_root)
    except SentinelError as error:
        assert str(error) == "capture failed for new session"
    else:
        raise AssertionError("Injected shared-world capture failure did not propagate")

    assert shared_world.sessions == [existing_a, existing_b]
    assert shared_world.solver.body_count == 3
    assert shared_world.solver.bodies == (
        "existing A0",
        "existing A1",
        "existing B0",
    )
    assert len(shared_world.solver.joints) == 1
    assert shared_world.solver.joints[0].body_a == 0
    assert shared_world.solver.joints[0].body_b == 1
    assert existing_a.body_offset == 0
    assert existing_a.joint_offset == 0
    assert existing_b.body_offset == 2
    assert existing_b.joint_offset == 1
    assert existing_a.solver is shared_world.solver
    assert existing_b.solver is shared_world.solver
    for existing in (existing_a, existing_b):
        assert any(
            captured is existing and solver is shared_world.solver
            for captured, solver in capture_records
        )
    assert FakeSolver.created[-1] is shared_world.solver
    assert all(solver.closed for solver in FakeSolver.created[:-1])
    assert shared_initial_solver.closed
    assert not shared_world.solver.closed
    assert existing_a.restore_calls == existing_restore_calls[existing_a] + 1
    assert existing_b.restore_calls == existing_restore_calls[existing_b] + 1
    assert failed.world is None
    assert failed.solver is None
    assert failed.closed
    assert runtime._ACTIVE_SESSIONS == {
        existing_a.root_name: existing_a,
        existing_b.root_name: existing_b,
    }
    assert runtime._ACTIVE_WORLDS == {world_key: shared_world}
    print("SPX_SHARED_WORLD_CAPTURE_ROLLBACK_OK")

    clear_runtime_state()
    evaluator.capture_physics_bindings = lambda _root, _session: True
    runtime.PreviewSession = original_preview_session

    scene = FakeScene("Suspend isolation scene")
    failed_suspend = FakeSession(
        scene,
        FakeRoot("Failed suspend root", "failed suspend", "shared suspend"),
    )
    healthy_shared_suspend = FakeSession(
        scene,
        FakeRoot(
            "Healthy shared suspend root",
            "healthy shared suspend",
            "shared suspend",
        ),
    )
    healthy_other_suspend = FakeSession(
        scene,
        FakeRoot(
            "Healthy other suspend root",
            "healthy other suspend",
            "other suspend",
        ),
    )
    failed_suspend.deactivate_error = SentinelError("suspend display failure")
    shared_suspend_world = runtime.PreviewWorld(
        ("suspend", "shared"),
        0.08,
        "MMD",
        None,
    )
    healthy_other_world = runtime.PreviewWorld(
        ("suspend", "healthy other"),
        0.08,
        "MMD",
        None,
    )
    shared_suspend_world.add(failed_suspend)
    shared_suspend_world.add(healthy_shared_suspend)
    healthy_other_world.add(healthy_other_suspend)
    shared_suspend_world.reset()
    healthy_other_world.reset(prepared_session=healthy_other_suspend)
    shared_solver_before_suspend = shared_suspend_world.solver
    shared_generation_before_suspend = shared_suspend_world.generation
    shared_restore_before_suspend = healthy_shared_suspend.restore_calls
    runtime._ACTIVE_SESSIONS.update(
        {
            failed_suspend.root_name: failed_suspend,
            healthy_shared_suspend.root_name: healthy_shared_suspend,
            healthy_other_suspend.root_name: healthy_other_suspend,
        }
    )
    runtime._ACTIVE_WORLDS.update(
        {
            shared_suspend_world.key: shared_suspend_world,
            healthy_other_world.key: healthy_other_world,
        }
    )
    discard_calls = []

    def fail_native_discard(*, root=None, previous_root_name=None):
        discard_calls.append((root, previous_root_name))
        raise SentinelError("native discard failure")

    evaluator.discard_session = fail_native_discard

    try:
        runtime.suspend_for_undo_redo()
    except SentinelError as error:
        assert str(error) == "suspend display failure"
    else:
        raise AssertionError("Injected suspend failure did not propagate")

    assert failed_suspend.closed
    assert failed_suspend.world is None
    assert shared_solver_before_suspend.closed
    assert failed_suspend.root_name not in runtime._ACTIVE_SESSIONS
    assert discard_calls == [(failed_suspend.root, failed_suspend.root_name)]
    assert shared_suspend_world.generation == shared_generation_before_suspend + 1
    assert shared_suspend_world.sessions == [healthy_shared_suspend]
    assert shared_suspend_world.solver is healthy_shared_suspend.solver
    assert shared_suspend_world.solver.bodies == ("healthy shared suspend",)
    assert healthy_shared_suspend.body_offset == 0
    assert healthy_shared_suspend.joint_offset == 0
    assert healthy_shared_suspend.restore_calls == shared_restore_before_suspend
    assert healthy_shared_suspend.deactivate_calls == 1
    assert healthy_other_suspend.deactivate_calls == 1
    assert runtime._ACTIVE_SESSIONS == {
        healthy_shared_suspend.root_name: healthy_shared_suspend,
        healthy_other_suspend.root_name: healthy_other_suspend,
    }
    assert runtime._ACTIVE_WORLDS == {
        shared_suspend_world.key: shared_suspend_world,
        healthy_other_world.key: healthy_other_world,
    }
    assert runtime._RUNTIME_SUSPENDED
    print("SPX_UNDO_SUSPEND_FAILURE_ISOLATION_OK")
finally:
    runtime.PreviewSession = original_preview_session
    runtime.Solver = original_solver
    evaluator.clear_physics_feedback = original_clear_feedback
    evaluator.capture_physics_bindings = original_capture_bindings
    evaluator.discard_session = original_discard_session
    clear_runtime_state()


print("PHYSICS_PREVIEW_LIFECYCLE_TRANSACTION_REGRESSION_OK")
