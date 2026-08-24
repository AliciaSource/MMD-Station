import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ROOT_BONE_NAME = "\u5168\u3066\u306e\u89aa"
FOOT_BONE_NAME = "\u8db3D.L"
DISPLAY_MARKER = "spx_physics_preview_display_rig"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.physics_preview import runtime
from mmd_skirt_proxy_creator.physics_preview.display_rig import PreviewDisplayRig
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator as mmd_evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime import lifecycle as mmd_lifecycle

mmd_skirt_proxy_creator.register()


def _matrix_error(first, second):
    return max(
        abs(left - right)
        for first_row, second_row in zip(first, second)
        for left, right in zip(first_row, second_row)
    )


def _basis_snapshot(armature):
    return {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in armature.pose.bones
    }


def _assert_basis(snapshot, armature, tolerance=2.0e-6):
    error = 0.0
    changed_name = ""
    for name, expected in snapshot.items():
        pose_bone = armature.pose.bones.get(name)
        assert pose_bone is not None, name
        current_error = _matrix_error(expected, pose_bone.matrix_basis)
        if current_error > error:
            error = current_error
            changed_name = name
    assert error <= tolerance, (changed_name, error)
    return error


def _connection_snapshot(session):
    return {
        name: bool(session.armature.data.bones[name].use_connect)
        for name in session.saved_bone_connections
    }


def _assert_connections(session, expected):
    current = _connection_snapshot(session)
    assert current
    assert all(value is expected for value in current.values()), current


def _display_objects():
    return tuple(
        obj
        for obj in bpy.data.objects
        if obj.type == "ARMATURE" and bool(obj.get(DISPLAY_MARKER, ""))
    )


def _display_source_state(display_rig):
    return tuple(
        (binding.source_object, binding.source_hide_viewport)
        for binding in display_rig.mesh_bindings
    )


def _assert_display_sources_restored(source_state):
    for source, hidden in source_state:
        assert bpy.data.objects.get(source.name) is source
        assert source.hide_viewport is hidden, (source.name, source.hide_viewport, hidden)


def _modifier_snapshot(plan):
    return tuple(
        (
            binding.mesh_object.name,
            binding.modifier.name,
            binding.modifier.object.name if binding.modifier.object else None,
        )
        for binding in plan.bindings
    )


def _assert_modifiers(snapshot):
    for object_name, modifier_name, armature_name in snapshot:
        mesh_object = bpy.data.objects.get(object_name)
        assert mesh_object is not None, object_name
        modifier = mesh_object.modifiers.get(modifier_name)
        assert modifier is not None, (object_name, modifier_name)
        assert modifier.object is not None, (object_name, modifier_name)
        assert modifier.object.name == armature_name, (
            object_name,
            modifier_name,
            modifier.object.name,
            armature_name,
        )


def _configure_settings(root):
    settings = bpy.context.scene.surface_proxy_creator
    settings.preview_scope = "CURRENT_PROXY"
    settings.preview_frequency = 60
    settings.preview_substeps = 10
    settings.preview_update_rigids = True
    settings.preview_solver_target = "MMD"
    settings.mmd_root = root
    assert settings.physics_proxy is not None
    return settings


def _start_session(root):
    assert not runtime._ACTIVE_SESSIONS
    session = runtime.start_preview(bpy.context)[0]
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    for _index in range(6):
        session.tick(interactive=False)
    session._force_display_rig_for_tests = True
    if not session.saved_bone_connections:
        candidate = next(
            pose_bone
            for pose_bone in session.driver_pose_bones.values()
            if (
                pose_bone is not None
                and pose_bone.parent is not None
                and (
                    pose_bone.bone.head_local
                    - pose_bone.parent.bone.tail_local
                ).length < 1.0e-5
            )
        )
        session.saved_bone_connections = {candidate.name: True}
    _assert_connections(session, False)
    return session


def _activate_display(session):
    session.display_rig_unavailable = False
    session._force_display_rig_for_tests = True
    changed = session._update_display_rig_state(
        interactive=True,
        compatible=session._isolated_runtime_compatible(),
    )
    assert changed
    assert session.isolated_output_active
    assert len(_display_objects()) == 1
    _assert_connections(session, True)
    return session.display_rig


def _stop_session(root):
    runtime.stop_preview(root)
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert not _display_objects()


def _restore_named_pose(armature, snapshot):
    for name, matrix_basis in snapshot.items():
        pose_bone = armature.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.matrix_basis = matrix_basis
    armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()


def _exercise_live_object_renames(root):
    session = _start_session(root)
    armature = session.armature
    display_rig = _activate_display(session)
    source_state = _display_source_state(display_rig)
    world = session.world
    solver = session.solver
    generation = world.generation
    reset_count = session.auto_reset_count
    root_name = root.name
    armature_name = armature.name

    root.name = f"{root_name}__SPX_RENAME__"
    bpy.context.view_layer.update()
    for _index in range(2):
        runtime._timer_tick_session(session, time.perf_counter(), interactive=False)
    assert runtime.is_running(root)
    assert runtime._ACTIVE_SESSIONS == {root.name: session}
    assert session.root_name == root.name
    assert session.world is world
    assert session.solver is solver
    assert world.generation == generation
    assert session.auto_reset_count == reset_count
    assert session.consecutive_tick_failures == 0
    assert not session.snapshot_reset_pending

    armature.name = f"{armature_name}__SPX_RENAME__"
    bpy.context.view_layer.update()
    for _index in range(2):
        runtime._timer_tick_session(session, time.perf_counter(), interactive=False)
    assert runtime.is_running(root)
    assert runtime._ACTIVE_SESSIONS == {root.name: session}
    assert session.root_name == root.name
    assert session.armature_name == armature.name
    assert session.world is world
    assert session.solver is solver
    assert world.generation == generation
    assert session.auto_reset_count == reset_count
    assert session.consecutive_tick_failures == 0
    assert not session.snapshot_reset_pending
    assert session.display_rig is display_rig
    assert session.isolated_output_active
    assert display_rig.source_armature_name == armature.name
    native_session = mmd_evaluator._session_for_root(root)
    if native_session is not None:
        assert mmd_evaluator._SESSIONS.get(root.name) is native_session
        assert native_session.root_name == root.name
        assert native_session.runtime_name == armature.name
        assert native_session.canonical_name == armature.name

    runtime.stop_preview(root)
    assert not runtime.is_running(root)
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert not _display_objects()
    _assert_display_sources_restored(source_state)
    root.name = root_name
    armature.name = armature_name
    bpy.context.view_layer.update()
    print("SPX_LIVE_ROOT_ARMATURE_RENAME_OK")


def _exercise_live_physics_object_renames(root):
    session = _start_session(root)
    display_rig = _activate_display(session)
    source_state = _display_source_state(display_rig)
    rigid = next(
        rigid for rigid in session.rigids if int(rigid.mmd_rigid.type) != 0
    )
    joint = session.joints[0]
    rigid_name = rigid.name
    joint_name = joint.name
    authored_rigid = session.saved_rigid_matrices[rigid_name].copy()
    authored_joint = session.saved_joint_matrices[joint_name].copy()

    fake_depsgraph = SimpleNamespace(
        updates=(SimpleNamespace(id=rigid), SimpleNamespace(id=joint))
    )
    session._binding_names_dirty = False
    runtime._ensure_preview_model_ids_after_update(session.scene, fake_depsgraph)
    assert not session._binding_names_dirty

    rigid.name = f"{rigid_name}__SPX_RENAME__"
    joint.name = f"{joint_name}__SPX_RENAME__"
    rigid.matrix_world = rigid.matrix_world @ Matrix.Translation((0.013, -0.007, 0.004))
    joint.matrix_world = joint.matrix_world @ Matrix.Translation((-0.009, 0.005, 0.003))
    runtime_rigid = rigid.matrix_world.copy()
    runtime_joint = joint.matrix_world.copy()
    bpy.context.view_layer.update()
    runtime._ensure_preview_model_ids_after_update(session.scene, fake_depsgraph)
    assert session._binding_names_dirty

    runtime._suspend_display_rigs_for_save("")
    assert runtime._RUNTIME_SUSPENDED
    assert rigid.name in session.rigid_names
    assert joint.name in session.joint_names
    assert rigid.name in session.saved_rigid_matrices
    assert joint.name in session.saved_joint_matrices
    assert rigid_name not in session.saved_rigid_matrices
    assert joint_name not in session.saved_joint_matrices
    save_pre_rigid_error = _matrix_error(rigid.matrix_world, authored_rigid)
    save_pre_joint_error = _matrix_error(joint.matrix_world, authored_joint)
    assert save_pre_rigid_error < 1.0e-7, save_pre_rigid_error
    assert save_pre_joint_error < 1.0e-7, save_pre_joint_error

    runtime._resume_display_rigs_after_save("")
    assert not runtime._RUNTIME_SUSPENDED
    save_post_rigid_error = _matrix_error(rigid.matrix_world, runtime_rigid)
    save_post_joint_error = _matrix_error(joint.matrix_world, runtime_joint)
    assert save_post_rigid_error < 1.0e-7, save_post_rigid_error
    assert save_post_joint_error < 1.0e-7, save_post_joint_error

    runtime.stop_preview(root)
    stop_rigid_error = _matrix_error(rigid.matrix_world, authored_rigid)
    stop_joint_error = _matrix_error(joint.matrix_world, authored_joint)
    assert stop_rigid_error < 1.0e-7, stop_rigid_error
    assert stop_joint_error < 1.0e-7, stop_joint_error
    assert not _display_objects()
    _assert_display_sources_restored(source_state)
    rigid.name = rigid_name
    joint.name = joint_name
    bpy.context.view_layer.update()
    print(
        "SPX_LIVE_RIGID_JOINT_RENAME_OK",
        f"save_pre={max(save_pre_rigid_error, save_pre_joint_error):.9g}",
        f"save_post={max(save_post_rigid_error, save_post_joint_error):.9g}",
        f"stop={max(stop_rigid_error, stop_joint_error):.9g}",
        "debug_self_write_rebind=skipped",
    )


def _finish_undo_redo_resume():
    timer = mmd_lifecycle._resume_undo_redo_timer
    if bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)
    if mmd_lifecycle._UNDO_REDO_RESUME_PENDING:
        timer()


def _root_by_preview_id(preview_id):
    matches = tuple(
        obj
        for obj in bpy.context.scene.objects
        if (
            getattr(obj, "mmd_type", "") == "ROOT"
            and int(obj.get("spx_mmd_preview_id", 0)) == preview_id
        )
    )
    assert len(matches) == 1, tuple(obj.name for obj in matches)
    return matches[0]


def _exercise_rename_undo_redo(root):
    session = _start_session(root)
    armature = session.armature
    world = session.world
    solver = session.solver
    generation = world.generation
    preview_id = session.root_preview_id
    root_name = root.name
    armature_name = armature.name
    renamed_root = f"{root_name}__SPX_UNDO_RENAME__"
    renamed_armature = f"{armature_name}__SPX_UNDO_RENAME__"

    bpy.ops.ed.undo_push(message="SPX before active rename")
    root.name = renamed_root
    armature.name = renamed_armature
    bpy.context.view_layer.update()
    for _index in range(2):
        runtime._timer_tick_session(session, time.perf_counter(), interactive=False)
    bpy.ops.ed.undo_push(message="SPX after active rename")

    assert bpy.ops.ed.undo() == {"FINISHED"}
    _finish_undo_redo_resume()
    root = _root_by_preview_id(preview_id)
    assert root.name == root_name, root.name
    assert session.root is root
    assert session.root_name == root.name
    assert runtime._ACTIVE_SESSIONS == {root.name: session}
    assert runtime.is_running(root)
    assert session.world is world
    assert session.solver is world.solver
    assert session.solver is not solver
    assert solver.handle is None
    assert world.generation == generation + 1
    solver = session.solver
    generation = world.generation

    assert bpy.ops.ed.redo() == {"FINISHED"}
    _finish_undo_redo_resume()
    root = _root_by_preview_id(preview_id)
    assert root.name == renamed_root, root.name
    assert session.root is root
    assert session.root_name == root.name
    assert session.armature.name == renamed_armature
    assert runtime._ACTIVE_SESSIONS == {root.name: session}
    assert runtime.is_running(root)
    assert session.world is world
    assert session.solver is world.solver
    assert session.solver is not solver
    assert solver.handle is None
    assert world.generation == generation + 1

    root.name = root_name
    session.armature.name = armature_name
    bpy.context.view_layer.update()
    for _index in range(2):
        runtime._timer_tick_session(session, time.perf_counter(), interactive=False)
    runtime.stop_preview(root)
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert not _display_objects()
    print("SPX_RENAME_UNDO_REDO_IDENTITY_OK")
    return root


def _exercise_runtime_switch(root, initial_named_pose):
    session = _start_session(root)
    armature = session.armature
    _activate_display(session)
    root_bone = armature.pose.bones[ROOT_BONE_NAME]
    foot_bone = armature.pose.bones[FOOT_BONE_NAME]
    root_bone.matrix_basis = (
        root_bone.matrix_basis @ Matrix.Translation((0.031, -0.017, 0.023))
    )
    foot_bone.matrix_basis = (
        foot_bone.matrix_basis @ Matrix.Rotation(0.19, 4, "Y")
    )
    armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    authored = {
        ROOT_BONE_NAME: root_bone.matrix_basis.copy(),
        FOOT_BONE_NAME: foot_bone.matrix_basis.copy(),
    }

    token = runtime.suspend_for_runtime_switch(root)
    assert token is not None
    assert runtime._RUNTIME_SUSPENDED
    assert not session.isolated_output_active
    _assert_basis(authored, armature)
    _assert_connections(session, False)
    session.pose_input.set_native_input_active(True)
    resumed = runtime.resume_after_runtime_switch(token)
    assert resumed is session
    assert not runtime._RUNTIME_SUSPENDED
    assert session.pose_input.native_input_active
    _assert_basis(authored, armature)
    _assert_connections(session, False)

    session.pose_input.set_native_input_active(False)
    _stop_session(root)
    _restore_named_pose(armature, initial_named_pose)
    print("SPX_RUNTIME_SWITCH_AUTHORED_POSE_OK")


def _exercise_fallback_runtime_switch(root, initial_named_pose):
    session = _start_session(root)
    armature = session.armature
    assert ROOT_BONE_NAME not in session.driver_pose_bones
    assert FOOT_BONE_NAME not in session.driver_pose_bones
    assert ROOT_BONE_NAME not in session.saved_basis
    assert FOOT_BONE_NAME not in session.saved_basis

    session.pose_input.set_native_input_active(True)
    compatible = session._isolated_runtime_compatible()
    assert not compatible
    assert not session._update_display_rig_state(True, compatible)
    assert not session.isolated_output_active
    _assert_connections(session, False)

    root_bone = armature.pose.bones[ROOT_BONE_NAME]
    foot_bone = armature.pose.bones[FOOT_BONE_NAME]
    for root_delta, foot_angle in (
        ((0.007, -0.003, 0.004), 0.031),
        ((-0.002, 0.006, 0.003), -0.047),
        ((0.005, 0.002, -0.001), 0.029),
    ):
        root_bone.matrix_basis = (
            root_bone.matrix_basis @ Matrix.Translation(root_delta)
        )
        foot_bone.matrix_basis = (
            foot_bone.matrix_basis @ Matrix.Rotation(foot_angle, 4, "Y")
        )
        armature.update_tag(refresh={"OBJECT"})
        bpy.context.view_layer.update()
    authored = {
        ROOT_BONE_NAME: root_bone.matrix_basis.copy(),
        FOOT_BONE_NAME: foot_bone.matrix_basis.copy(),
    }

    driver_name = _perturb_driver_basis(session, 0.012)
    assert _matrix_error(
        session.armature.pose.bones[driver_name].matrix_basis,
        session.saved_basis[driver_name],
    ) > 1.0e-5
    world = session.world
    solver = session.solver

    token = runtime.suspend_for_runtime_switch(root)
    assert token is not None
    assert runtime._RUNTIME_SUSPENDED
    assert not session.isolated_output_active
    assert session.pose_input.native_input_active
    authored_error = _assert_basis(authored, armature)
    driver_error = _assert_driver_snapshot_restored(session)
    _assert_connections(session, False)

    resumed = runtime.resume_after_runtime_switch(token)
    assert resumed is session
    assert not runtime._RUNTIME_SUSPENDED
    assert session.pose_input.native_input_active
    assert session.world is world
    assert session.solver is solver
    authored_error = max(authored_error, _assert_basis(authored, armature))
    driver_error = max(driver_error, _assert_driver_snapshot_restored(session))
    _assert_connections(session, False)

    session.pose_input.set_native_input_active(False)
    _stop_session(root)
    _restore_named_pose(armature, initial_named_pose)
    print(
        "SPX_FALLBACK_RUNTIME_SWITCH_POSE_OK",
        f"driver={driver_name}",
        f"authored_error={authored_error:.9g}",
        f"driver_error={driver_error:.9g}",
    )


def _exercise_save_undo_connections(root):
    session = _start_session(root)
    _activate_display(session)
    runtime._suspend_display_rigs_for_save("")
    assert runtime._RUNTIME_SUSPENDED
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is not None
    _assert_connections(session, True)
    runtime._resume_display_rigs_after_save("")
    assert not runtime._RUNTIME_SUSPENDED
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
    assert not session.isolated_output_active
    _assert_connections(session, False)

    _activate_display(session)
    assert runtime.suspend_for_undo_redo()
    assert runtime._RUNTIME_SUSPENDED
    assert not session.isolated_output_active
    _assert_connections(session, True)
    runtime.resume_after_undo_redo()
    assert not runtime._RUNTIME_SUSPENDED
    _assert_connections(session, False)
    _stop_session(root)
    print("SPX_SAVE_UNDO_CANONICAL_CONNECTIONS_OK")


def _exercise_no_display_undo_connections(root):
    session = _start_session(root)
    world = session.world
    solver = session.solver
    generation = world.generation
    session.pose_input.set_native_input_active(True)
    compatible = session._isolated_runtime_compatible()
    assert not compatible
    assert not session._update_display_rig_state(True, compatible)
    assert session.display_rig is None
    assert not _display_objects()
    _assert_connections(session, False)

    assert runtime.suspend_for_undo_redo()
    assert runtime._RUNTIME_SUSPENDED
    assert session.display_rig is None
    _assert_connections(session, True)

    runtime.resume_after_undo_redo()
    assert not runtime._RUNTIME_SUSPENDED
    assert runtime._ACTIVE_SESSIONS.get(session.root_name) is session
    assert session.world is world
    assert session.solver is world.solver
    assert session.solver is not solver
    assert solver.handle is None
    assert world.generation == generation + 1
    assert session.display_rig is None
    _assert_connections(session, False)
    session.tick(interactive=False)
    assert session.consecutive_tick_failures == 0
    assert not session.snapshot_reset_pending
    _assert_connections(session, False)

    session.pose_input.set_native_input_active(False)
    _stop_session(root)
    print("SPX_NO_DISPLAY_UNDO_CONNECTIONS_OK")


def _perturb_driver_basis(session, amount):
    name, pose_bone = next(
        (name, pose_bone)
        for name, pose_bone in session.driver_pose_bones.items()
        if pose_bone is not None
    )
    pose_bone.matrix_basis = (
        pose_bone.matrix_basis @ Matrix.Translation((amount, 0.0, 0.0))
    )
    session.canonical_output_dirty = True
    session.armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    assert _matrix_error(pose_bone.matrix_basis, session.saved_basis[name]) > 1.0e-5
    return name


def _assert_driver_snapshot_restored(session):
    maximum_error = 0.0
    changed_name = ""
    for name, expected in session.saved_basis.items():
        pose_bone = session.armature.pose.bones[name]
        error = _matrix_error(pose_bone.matrix_basis, expected)
        if error > maximum_error:
            maximum_error = error
            changed_name = name
    assert maximum_error < 1.0e-7, (changed_name, maximum_error)
    return maximum_error


def _force_multi_session_fallback(session):
    sentinel_name = "__spx_runtime_transition_sentinel__"
    assert sentinel_name not in runtime._ACTIVE_SESSIONS
    runtime._ACTIVE_SESSIONS[sentinel_name] = session
    try:
        compatible = session._isolated_runtime_compatible()
        assert not compatible
        assert session._update_display_rig_state(True, compatible)
    finally:
        runtime._ACTIVE_SESSIONS.pop(sentinel_name, None)
    assert not session.isolated_output_active
    _assert_connections(session, False)


def _exercise_fallback_reset_stop(root):
    session = _start_session(root)
    _activate_display(session)
    _force_multi_session_fallback(session)
    reset_driver = _perturb_driver_basis(session, 0.013)
    runtime.reset_preview(root)
    reset_error = _assert_driver_snapshot_restored(session)

    _activate_display(session)
    _force_multi_session_fallback(session)
    stop_driver = _perturb_driver_basis(session, -0.011)
    saved_basis = {
        name: matrix.copy() for name, matrix in session.saved_basis.items()
    }
    armature = session.armature
    _stop_session(root)
    stop_error = max(
        _matrix_error(armature.pose.bones[name].matrix_basis, expected)
        for name, expected in saved_basis.items()
    )
    assert stop_error < 1.0e-7, stop_error
    print(
        "SPX_FALLBACK_RESET_STOP_CLEAN_OK",
        f"reset_driver={reset_driver}",
        f"stop_driver={stop_driver}",
        f"reset_error={reset_error:.9g}",
        f"stop_error={stop_error:.9g}",
    )


def _exercise_activation_rollback(root):
    session = _start_session(root)
    plan = PreviewDisplayRig.plan(session)
    assert plan is not None
    modifier_state = _modifier_snapshot(plan)
    _perturb_driver_basis(session, 0.009)
    basis_state = _basis_snapshot(session.armature)
    connection_state = _connection_snapshot(session)
    dirty_state = session.canonical_output_dirty
    armature_count = len(bpy.data.armatures)

    original_plan = PreviewDisplayRig.__dict__["plan"]

    def fail_plan(_cls, _session):
        raise RuntimeError("injected DisplayRig plan failure")

    PreviewDisplayRig.plan = classmethod(fail_plan)
    try:
        assert not session._activate_display_rig()
    finally:
        PreviewDisplayRig.plan = original_plan
    assert not session.isolated_output_active
    assert not _display_objects()
    assert len(bpy.data.armatures) == armature_count
    _assert_basis(basis_state, session.armature)
    assert _connection_snapshot(session) == connection_state
    _assert_modifiers(modifier_state)
    assert session.canonical_output_dirty is dirty_state

    session.display_rig_unavailable = False
    original_init = PreviewDisplayRig.__dict__["__init__"]

    def fail_init(*_args, **_kwargs):
        raise RuntimeError("injected DisplayRig create failure")

    PreviewDisplayRig.__init__ = fail_init
    try:
        session._activate_display_rig()
    finally:
        PreviewDisplayRig.__init__ = original_init
    assert not session.isolated_output_active
    assert not _display_objects()
    assert len(bpy.data.armatures) == armature_count
    rollback_error = _assert_basis(basis_state, session.armature)
    assert _connection_snapshot(session) == connection_state
    _assert_modifiers(modifier_state)
    assert session.canonical_output_dirty is dirty_state

    _stop_session(root)
    print(
        "SPX_DISPLAY_ACTIVATION_ROLLBACK_OK",
        f"basis_error={rollback_error:.9g}",
        f"modifiers={len(modifier_state)}",
    )


def _exercise_save_exception_safety(root):
    session = _start_session(root)
    _activate_display(session)
    original_restore_snapshot = session._restore_debug_snapshot

    def fail_restore_snapshot():
        raise RuntimeError("injected save suspend failure")

    session._restore_debug_snapshot = fail_restore_snapshot
    try:
        try:
            runtime._suspend_display_rigs_for_save("")
        except RuntimeError as error:
            assert "injected save suspend failure" in str(error)
        else:
            raise AssertionError("Injected save suspend failure did not propagate")
    finally:
        session._restore_debug_snapshot = original_restore_snapshot
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
    assert not runtime._RUNTIME_SUSPENDED
    assert not session.isolated_output_active
    _assert_connections(session, False)

    _activate_display(session)
    runtime._suspend_display_rigs_for_save("")
    assert runtime._RUNTIME_SUSPENDED
    original_restore_state = session._restore_debug_state

    def fail_restore_state(_state):
        raise RuntimeError("injected save resume failure")

    session._restore_debug_state = fail_restore_state
    try:
        runtime._resume_display_rigs_after_save("")
    finally:
        session._restore_debug_state = original_restore_state
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
    assert not runtime._RUNTIME_SUSPENDED
    assert session.snapshot_reset_pending
    session.snapshot_reset_pending = False
    _stop_session(root)
    print("SPX_SAVE_EXCEPTION_SAFETY_OK")


def _exercise_load_pre_cleanup(root):
    session = _start_session(root)
    _activate_display(session)
    world = session.world
    solver = world.solver
    executor = runtime._step_executor()
    runtime._TIMER_DEADLINE.next_delay(10.0, 10.001, 1.0 / 60.0)
    assert runtime._TIMER_DEADLINE.deadline is not None
    runtime._suspend_display_rigs_for_save("")
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is not None
    assert runtime._RUNTIME_SUSPENDED

    runtime._stop_preview_before_load("")
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert session.closed
    assert session.world is None
    assert session.solver is None
    assert world.solver is None
    assert solver is not None
    assert runtime._STEP_EXECUTOR is None
    assert executor is not runtime._STEP_EXECUTOR
    assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
    assert not runtime._RUNTIME_SUSPENDED
    assert runtime._TIMER_DEADLINE.deadline is None
    assert not bpy.app.timers.is_registered(runtime._timer_tick)
    assert not _display_objects()
    print("SPX_LOAD_PRE_RUNTIME_CLEANUP_OK")


class _UnboundWorldProbe:
    def __init__(self, key, session):
        self.key = key
        self.sessions = [session]
        self.closed = False

    def remove(self, session):
        self.sessions.remove(session)
        session.world = None

    def close(self):
        self.closed = True


def _exercise_stop_exception_transaction(root):
    session = _start_session(root)
    world = session.world
    settings = session.settings
    original_deactivate = session._deactivate_display_rig
    deactivate_observations = []

    def fail_deactivate(*, allow_retry=True):
        deactivate_observations.append((session.closed, allow_retry))
        raise RuntimeError("__SPX_CLOSE_DEACTIVATE_FAILURE__")

    session._deactivate_display_rig = fail_deactivate
    try:
        try:
            session.close(restore=False)
        except RuntimeError as error:
            assert str(error) == "__SPX_CLOSE_DEACTIVATE_FAILURE__"
        else:
            raise AssertionError("PreviewSession.close swallowed the injected failure")
        assert deactivate_observations == [(False, False)]
        assert not session.closed
    finally:
        session._deactivate_display_rig = original_deactivate

    original_close = session.close
    close_calls = []
    executor = runtime._step_executor()
    runtime._TIMER_DEADLINE.next_delay(10.0, 10.001, 1.0 / 60.0)

    def fail_close(*, restore=True):
        close_calls.append(restore)
        raise RuntimeError("__SPX_STOP_CLOSE_FAILURE__")

    session.close = fail_close
    try:
        try:
            runtime.stop_preview(root)
        except RuntimeError as error:
            assert str(error) == "__SPX_STOP_CLOSE_FAILURE__"
        else:
            raise AssertionError("stop_preview swallowed the injected failure")
        assert close_calls == [True, False]
        assert not runtime._ACTIVE_SESSIONS
        assert not runtime._ACTIVE_WORLDS
        assert not world.sessions
        assert world.solver is None
        assert session.world is None
        assert session.solver is None
        assert not session.closed
        assert runtime._STEP_EXECUTOR is None
        assert executor is not runtime._STEP_EXECUTOR
        assert runtime._TIMER_DEADLINE.deadline is None
        assert not bpy.app.timers.is_registered(runtime._timer_tick)
        assert not settings.preview_running
        assert "已停止" in settings.preview_status
    finally:
        session.close = original_close
        if not session.closed:
            original_close(restore=False)
        runtime.stop_preview()
    assert session.closed

    session = _start_session(root)
    display_rig = _activate_display(session)
    source_state = _display_source_state(display_rig)
    original_clear_feedback = mmd_evaluator.clear_physics_feedback

    def fail_clear_feedback(_root):
        raise RuntimeError("__SPX_CLEAR_FEEDBACK_FAILURE__")

    mmd_evaluator.clear_physics_feedback = fail_clear_feedback
    try:
        try:
            runtime.stop_preview(root)
        except RuntimeError as error:
            assert str(error) == "__SPX_CLEAR_FEEDBACK_FAILURE__"
        else:
            raise AssertionError("Feedback cleanup failure did not propagate")
    finally:
        mmd_evaluator.clear_physics_feedback = original_clear_feedback
    assert session.closed
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert not _display_objects()
    _assert_display_sources_restored(source_state)
    print("SPX_STOP_EXCEPTION_TRANSACTION_OK")


def _exercise_unbound_session_cleanup(root):
    session = _start_session(root)
    scene = session.scene
    settings = session.settings
    healthy_world = session.world
    healthy_solver = session.solver
    healthy_generation = healthy_world.generation
    healthy_rebind = session._rebind_blender_data
    rebind_calls = []

    bad_root = bpy.data.objects.new("__SPX unbound root probe__", None)
    bad_armature_data = bpy.data.armatures.new("__SPX unbound armature data__")
    bad_armature = bpy.data.objects.new(
        "__SPX unbound armature probe__",
        bad_armature_data,
    )
    scene.collection.objects.link(bad_root)
    scene.collection.objects.link(bad_armature)

    bad_session = object.__new__(runtime.PreviewSession)
    bad_session.root_name = bad_root.name
    bad_session.root_preview_id = 0
    bad_session.armature_name = bad_armature.name
    bad_session.scene_name = scene.name
    bad_session.scene = scene
    bad_session.root = bad_root
    bad_session.armature = bad_armature
    bad_session.rigid_names = []
    bad_session.joint_names = []
    bad_session.settings = settings
    bad_session.display_rig = None
    bad_session.debug_batch = None
    bad_session._display_rig_validation_depth = 0
    bad_session.closed = False
    bad_session._deactivate_display_rig = lambda **_kwargs: False
    bad_world_key = ("__SPX_UNBOUND_WORLD_PROBE__",)
    bad_world = _UnboundWorldProbe(bad_world_key, bad_session)
    bad_session.world = bad_world

    active_sessions = tuple(runtime._ACTIVE_SESSIONS.items())
    assert active_sessions == ((session.root_name, session),)
    assert bad_world_key not in runtime._ACTIVE_WORLDS

    def observe_healthy_rebind(force=False, allow_recreated=False):
        rebind_calls.append(force)
        return healthy_rebind(
            force=force,
            allow_recreated=allow_recreated,
        )

    session._rebind_blender_data = observe_healthy_rebind
    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS[bad_session.root_name] = bad_session
    runtime._ACTIVE_SESSIONS.update(active_sessions)
    runtime._ACTIVE_WORLDS[bad_world_key] = bad_world
    try:
        assert runtime.suspend_for_undo_redo()
        assert runtime._RUNTIME_SUSPENDED
        bpy.data.objects.remove(bad_armature, do_unlink=True)
        if bad_armature_data.users == 0:
            bpy.data.armatures.remove(bad_armature_data)

        runtime.resume_after_undo_redo()
        assert not runtime._RUNTIME_SUSPENDED
        assert bad_session.root_name not in runtime._ACTIVE_SESSIONS
        assert bad_world_key not in runtime._ACTIVE_WORLDS
        assert bad_session.closed
        assert bad_session.world is None
        assert bad_world.closed
        assert rebind_calls == [True]
        assert runtime._ACTIVE_SESSIONS.get(session.root_name) is session
        assert session.world is healthy_world
        assert session.solver is healthy_world.solver
        assert session.solver is not healthy_solver
        assert healthy_solver.handle is None
        assert healthy_world.generation == healthy_generation + 1
        assert not session.snapshot_reset_pending
        assert session.consecutive_tick_failures == 0
        session.tick(interactive=False)
        assert not session.snapshot_reset_pending
        assert session.consecutive_tick_failures == 0
        assert rebind_calls == [True, False]
    finally:
        session._rebind_blender_data = healthy_rebind
        runtime._ACTIVE_SESSIONS.pop(bad_session.root_name, None)
        runtime._ACTIVE_WORLDS.pop(bad_world_key, None)
        existing_root = bpy.data.objects.get(bad_session.root_name)
        if existing_root is not None:
            bpy.data.objects.remove(existing_root, do_unlink=True)
        existing_armature = bpy.data.objects.get(bad_session.armature_name)
        if existing_armature is not None:
            data = existing_armature.data
            bpy.data.objects.remove(existing_armature, do_unlink=True)
            if data.users == 0:
                bpy.data.armatures.remove(data)
    _stop_session(root)
    print(
        "SPX_UNBOUND_SESSION_CLEANUP_OK",
        f"healthy_rebind_calls={len(rebind_calls)}",
        f"bad_world_closed={bad_world.closed}",
    )


def _exercise_direct_root_delete(root):
    session = _start_session(root)
    display_rig = _activate_display(session)
    source_state = _display_source_state(display_rig)
    world = session.world
    settings = session.settings

    bpy.data.objects.remove(root, do_unlink=True)
    runtime._timer_tick(_wall_seconds=time.perf_counter())
    assert not runtime._ACTIVE_SESSIONS
    assert not runtime._ACTIVE_WORLDS
    assert session.closed
    assert session.world is None
    assert session.solver is None
    assert not world.sessions
    assert world.solver is None
    assert not _display_objects()
    _assert_display_sources_restored(source_state)
    assert not settings.preview_running
    assert "已停止" in settings.preview_status
    runtime.stop_preview()
    runtime.stop_preview()
    print("SPX_DIRECT_ROOT_DELETE_TERMINAL_CLEAN_OK")


def _exercise_native_session_name_migration():
    scene = bpy.context.scene
    root = bpy.data.objects.new("__SPX native root rename probe__", None)
    root.mmd_type = "ROOT"
    armature_data = bpy.data.armatures.new("__SPX native armature data probe__")
    armature = bpy.data.objects.new(
        "__SPX native armature rename probe__",
        armature_data,
    )
    scene.collection.objects.link(root)
    scene.collection.objects.link(armature)
    armature.parent = root
    old_root_name = root.name
    old_armature_name = armature.name
    probe = SimpleNamespace(
        root_name=old_root_name,
        runtime_name=old_armature_name,
        canonical_name=old_armature_name,
        root_ref=root,
        runtime_ref=armature,
        canonical_ref=armature,
        root_preview_id=0,
        root_pointer=mmd_evaluator._rna_pointer(root),
        scene_name=scene.name,
        scene_pointer=mmd_evaluator._rna_pointer(scene),
        scene_ref=scene,
        binding_object_pointer=mmd_evaluator._rna_pointer(armature),
        binding_data_pointer=mmd_evaluator._rna_pointer(armature.data),
        binding_mode=armature.mode,
        identity_validated=True,
    )
    original_sessions = dict(mmd_evaluator._SESSIONS)
    assert old_root_name not in original_sessions
    mmd_evaluator._SESSIONS[old_root_name] = probe
    try:
        assert mmd_evaluator._root_matches_session(root, probe)
        assert mmd_evaluator._cached_session_armature(probe, armature)
        root.name = f"{old_root_name}__RENAMED__"
        armature.name = f"{old_armature_name}__RENAMED__"
        assert mmd_evaluator._session_for_root(root) is probe
        assert mmd_evaluator._SESSIONS.get(root.name) is probe
        assert len(mmd_evaluator._SESSIONS) == len(original_sessions) + 1
        assert probe.root_name == root.name
        assert probe.runtime_name == armature.name
        assert probe.canonical_name == armature.name
    finally:
        for key, session in tuple(mmd_evaluator._SESSIONS.items()):
            if session is probe:
                mmd_evaluator._SESSIONS.pop(key, None)
        assert mmd_evaluator._SESSIONS == original_sessions
        bpy.data.objects.remove(root, do_unlink=True)
        bpy.data.objects.remove(armature, do_unlink=True)
        if armature_data.users == 0:
            bpy.data.armatures.remove(armature_data)
    print("SPX_NATIVE_SESSION_RENAME_KEY_OK")


def _exercise_native_invalid_rename_cleanup():
    scene = bpy.context.scene
    root = bpy.data.objects.new("__SPX invalid native root probe__", None)
    scene.collection.objects.link(root)
    old_root_name = root.name
    close_calls = []
    rebuild_calls = []
    probe = SimpleNamespace(
        root_name=old_root_name,
        runtime_name="",
        canonical_name="",
        root_ref=root,
        runtime_ref=None,
        canonical_ref=None,
        root_preview_id=0,
        scene_name=scene.name,
        live=True,
        pmx_path="",
        solver=SimpleNamespace(close=lambda: close_calls.append(True)),
    )
    original_sessions = dict(mmd_evaluator._SESSIONS)
    original_rebuild = mmd_evaluator.rebuild_enabled_sessions
    assert old_root_name not in original_sessions
    mmd_evaluator._SESSIONS[old_root_name] = probe
    mmd_evaluator.rebuild_enabled_sessions = lambda: rebuild_calls.append(True)
    try:
        root.name = f"{old_root_name}__RENAMED__"
        mmd_evaluator.resume_sessions_after_undo_redo(scene)
        assert close_calls == [True]
        assert rebuild_calls == [True]
        assert all(session is not probe for session in mmd_evaluator._SESSIONS.values())
    finally:
        mmd_evaluator.rebuild_enabled_sessions = original_rebuild
        for key, session in tuple(mmd_evaluator._SESSIONS.items()):
            if session is probe:
                mmd_evaluator._SESSIONS.pop(key, None)
        assert mmd_evaluator._SESSIONS == original_sessions
        bpy.data.objects.remove(root, do_unlink=True)
    print("SPX_NATIVE_INVALID_RENAME_CLEANUP_OK")


root = bpy.data.objects[ROOT_NAME]
settings = _configure_settings(root)
armature = runtime._model_armature(root)
assert armature is not None
assert ROOT_BONE_NAME in armature.pose.bones
assert FOOT_BONE_NAME in armature.pose.bones
initial_named_pose = {
    ROOT_BONE_NAME: armature.pose.bones[ROOT_BONE_NAME].matrix_basis.copy(),
    FOOT_BONE_NAME: armature.pose.bones[FOOT_BONE_NAME].matrix_basis.copy(),
}

try:
    _exercise_runtime_switch(root, initial_named_pose)
    _exercise_live_object_renames(root)
    _exercise_live_physics_object_renames(root)
    root = _exercise_rename_undo_redo(root)
    _exercise_fallback_runtime_switch(root, initial_named_pose)
    _exercise_save_undo_connections(root)
    _exercise_no_display_undo_connections(root)
    _exercise_fallback_reset_stop(root)
    _exercise_activation_rollback(root)
    _exercise_save_exception_safety(root)
    _exercise_stop_exception_transaction(root)
    _exercise_unbound_session_cleanup(root)
    _exercise_load_pre_cleanup(root)
    _exercise_native_session_name_migration()
    _exercise_native_invalid_rename_cleanup()
    _exercise_direct_root_delete(root)
finally:
    PreviewDisplayRig.plan = PreviewDisplayRig.__dict__["plan"]
    if runtime._DISPLAY_RIG_SAVE_SUSPENSION is not None:
        runtime._resume_display_rigs_after_save("")
    runtime.stop_preview()
    runtime._RUNTIME_SUSPENDED = False
    runtime._DISPLAY_RIG_SAVE_SUSPENSION = None

print("MMD_04_RUNTIME_TRANSITION_REGRESSION_OK")
