import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ROOT_BONE_NAME = "\u5168\u3066\u306e\u89aa"
FOOT_BONE_NAME = "\u8db3D.L"
TARGET_MESH_NAME = "072_\u8863\u670d"
DISPLAY_MARKER = "spx_physics_preview_display_rig"
SOURCE_ARMATURE_KEY = "spx_physics_preview_source_armature"
DISPLAY_KIND_KEY = "spx_physics_preview_display_kind"
SOURCE_OBJECT_KEY = "spx_physics_preview_source_object"
SOURCE_HIDE_VIEWPORT_KEY = "spx_physics_preview_source_hide_viewport"
SOURCE_OWNER_KEY = "spx_physics_preview_display_source_owner"
SOURCE_TOKEN_KEY = "spx_physics_preview_display_source_token"
PHASE = os.environ.get("SPX_LIFECYCLE_PHASE", "exercise")
SAVE_PATH = Path(os.environ.get("SPX_LIFECYCLE_SAVE_PATH", ""))
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import lifecycle
from mmd_skirt_proxy_creator.physics_preview import runtime
from mmd_skirt_proxy_creator.physics_preview.display_rig import (
    PreviewDisplayRig,
    cleanup_stale_display_rigs,
)

mmd_skirt_proxy_creator.register()


def _display_objects():
    return tuple(
        obj
        for obj in bpy.data.objects
        if bool(obj.get(DISPLAY_MARKER, ""))
    )


def _display_rigs():
    return tuple(obj for obj in _display_objects() if obj.type == "ARMATURE")


def _display_sources():
    return tuple(
        obj
        for obj in bpy.data.objects
        if bool(obj.get(SOURCE_OWNER_KEY, ""))
    )


def _assert_session_membership(session):
    detached = tuple(
        (
            obj.name,
            tuple(scene.name for scene in obj.users_scene),
            tuple(collection.name for collection in obj.users_collection),
            obj.hide_viewport,
        )
        for obj in (*session.rigids, *session.joints)
        if session.scene.objects.get(obj.name) is not obj
    )
    assert not detached, detached[:5]


def _pose_context_signature():
    active = bpy.context.view_layer.objects.active
    active_bone = None
    if active is not None and active.type == "ARMATURE":
        bone = active.data.bones.active
        active_bone = bone.name if bone is not None else None
    return (
        active.name if active is not None else None,
        active.mode if active is not None else None,
        tuple(sorted(obj.name for obj in bpy.context.selected_objects)),
        active_bone,
    )


def _enter_pose_context(armature):
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    armature.hide_select = False
    armature.hide_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    active_bone = armature.data.bones.get(FOOT_BONE_NAME)
    assert active_bone is not None, FOOT_BONE_NAME
    active_bone.select = True
    armature.data.bones.active = active_bone
    return _pose_context_signature()


def _assert_modifier_bindings(display_rig, expected_armature):
    for binding in display_rig.bindings:
        mesh_object = bpy.data.objects.get(binding.mesh_name)
        assert mesh_object is not None, binding.mesh_name
        modifier = mesh_object.modifiers.get(binding.modifier_name)
        assert modifier is not None, binding.modifier_name
        assert modifier.object is expected_armature
        mesh_binding = next(
            item
            for item in display_rig.mesh_bindings
            if item.source_object is mesh_object
        )
        output = mesh_binding.display_object
        output_modifier = output.modifiers.get(binding.modifier_name)
        assert output_modifier is not None, binding.modifier_name
        assert output_modifier.object is display_rig.armature
        assert output.data is mesh_object.data
        assert output.parent is None
        assert output.hide_render
        assert output.hide_select
        assert not output.hide_viewport
        assert output.get(DISPLAY_MARKER, "") == display_rig.owner_token
        assert output.get(DISPLAY_KIND_KEY, "") == "output"
        assert output.get(SOURCE_TOKEN_KEY, "") == mesh_binding.source_token
        assert mesh_object.get(SOURCE_OWNER_KEY, "") == display_rig.owner_token
        assert mesh_object.get(SOURCE_TOKEN_KEY, "") == mesh_binding.source_token


def _matrix_error(first, second):
    return max(
        abs(left - right)
        for first_row, second_row in zip(first, second)
        for left, right in zip(first_row, second_row)
    )


def _debug_state_error(first, second):
    errors = []
    for first_group, second_group in zip(first, second):
        assert first_group.keys() == second_group.keys()
        errors.extend(
            (name, _matrix_error(first_group[name], second_group[name]))
            for name in first_group
        )
    return max(errors, key=lambda item: item[1])


def _remove_object_and_data(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data.users == 0:
        bpy.data.meshes.remove(data)


def _exercise_stale_cleanup(scene, source_armature):
    assert not _display_objects()
    stale_data = source_armature.data.copy()
    stale_data_name = stale_data.name
    stale = bpy.data.objects.new(".SPX stale display test", stale_data)
    stale_name = stale.name
    stale[DISPLAY_MARKER] = "stale-test-token"
    stale[DISPLAY_KIND_KEY] = "rig"
    stale[SOURCE_ARMATURE_KEY] = source_armature.name
    stale_data[DISPLAY_MARKER] = "stale-test-token"
    scene.collection.objects.link(stale)

    mesh_data = bpy.data.meshes.new(".SPX stale binding mesh data")
    mesh_data.from_pydata([(0.0, 0.0, 0.0)], [], [])
    mesh = bpy.data.objects.new(".SPX stale binding mesh", mesh_data)
    scene.collection.objects.link(mesh)
    source_name = mesh.name
    source_token = "stale-source-token"
    output = mesh.copy()
    output.name = ".SPX stale output"
    output[DISPLAY_MARKER] = "stale-test-token"
    output[DISPLAY_KIND_KEY] = "output"
    output[SOURCE_OBJECT_KEY] = source_name
    output[SOURCE_TOKEN_KEY] = source_token
    output[SOURCE_HIDE_VIEWPORT_KEY] = False
    scene.collection.objects.link(output)
    output_name = output.name
    mesh[SOURCE_OWNER_KEY] = "stale-test-token"
    mesh[SOURCE_TOKEN_KEY] = source_token
    mesh[SOURCE_HIDE_VIEWPORT_KEY] = False
    mesh.hide_viewport = True
    mesh.name = f"{source_name}__RENAMED"
    try:
        assert cleanup_stale_display_rigs() == 1
        assert bpy.data.objects.get(stale_name) is None
        assert bpy.data.armatures.get(stale_data_name) is None
        assert bpy.data.objects.get(output_name) is None
        assert not mesh.hide_viewport
        assert mesh.data is mesh_data
        assert mesh_data.users == 1
        assert SOURCE_OWNER_KEY not in mesh
        assert SOURCE_TOKEN_KEY not in mesh
        assert SOURCE_HIDE_VIEWPORT_KEY not in mesh
        assert not _display_objects()
    finally:
        _remove_object_and_data(mesh)

    orphan_token = "stale-orphan-data-token"
    orphan_mesh = bpy.data.meshes.new(".SPX stale orphan mesh data")
    orphan_mesh[DISPLAY_MARKER] = orphan_token
    orphan_mesh_name = orphan_mesh.name
    orphan_output = bpy.data.objects.new(".SPX stale orphan output", orphan_mesh)
    orphan_output[DISPLAY_MARKER] = orphan_token
    orphan_output[DISPLAY_KIND_KEY] = "output"
    scene.collection.objects.link(orphan_output)
    bpy.data.objects.remove(orphan_output, do_unlink=True)
    assert orphan_mesh.users == 0

    orphan_armature = source_armature.data.copy()
    orphan_armature[DISPLAY_MARKER] = orphan_token
    orphan_armature_name = orphan_armature.name
    orphan_rig = bpy.data.objects.new(".SPX stale orphan rig", orphan_armature)
    orphan_rig[DISPLAY_MARKER] = orphan_token
    orphan_rig[DISPLAY_KIND_KEY] = "rig"
    scene.collection.objects.link(orphan_rig)
    bpy.data.objects.remove(orphan_rig, do_unlink=True)
    assert orphan_armature.users == 0

    assert cleanup_stale_display_rigs() == 1
    assert bpy.data.meshes.get(orphan_mesh_name) is None
    assert bpy.data.armatures.get(orphan_armature_name) is None
    assert not _display_objects()
    print("SPX_DISPLAY_ORPHAN_DATABLOCK_CLEAN_OK")


def _activate_display(session):
    session._force_display_rig_for_tests = True
    changed = session._update_display_rig_state(
        interactive=True,
        compatible=session._isolated_runtime_compatible(),
    )
    assert changed
    assert session.isolated_output_active
    assert len(_display_rigs()) == 1
    assert len(_display_objects()) == 1 + len(session.display_rig.mesh_bindings)
    assert session.scene.objects.get(session.display_rig.armature.name) is session.display_rig.armature
    assert session.display_rig.armature.hide_viewport
    assert not any(
        bool(scene.get(DISPLAY_MARKER, ""))
        for scene in bpy.data.scenes
    )
    assert all(
        binding.display_object.data is binding.source_object.data
        and not bool(binding.display_object.data.get(DISPLAY_MARKER, ""))
        for binding in session.display_rig.mesh_bindings
    )
    return session.display_rig


def _exercise_view_layer_hidden_source(session):
    scene = session.scene
    source = bpy.data.objects[TARGET_MESH_NAME]
    baseline_plan = PreviewDisplayRig.plan(session)
    assert baseline_plan is not None
    assert any(binding.mesh_object is source for binding in baseline_plan.bindings)
    view_layer = scene.view_layers.new("SPX hidden source test")
    try:
        source.hide_set(True, view_layer=view_layer)
        plan = PreviewDisplayRig.plan(session)
        assert plan is None
        assert not session._activate_display_rig()
        assert not session.isolated_output_active
        assert not source.hide_viewport
        step_count = session.mmd_step_count
        session.tick(interactive=False)
        assert session.mmd_step_count > step_count
        assert not session.isolated_output_active
    finally:
        source.hide_set(False, view_layer=view_layer)
        scene.view_layers.remove(view_layer)
        session._deactivate_display_rig()
    restored_plan = PreviewDisplayRig.plan(session)
    assert restored_plan is not None
    assert any(binding.mesh_object is source for binding in restored_plan.bindings)
    print("SPX_DISPLAY_VIEW_LAYER_HIDDEN_SOURCE_OK")


def _excluded_debug_objects(session):
    active_rigid_names = set(session.rigid_names)
    active_joint_names = set(session.joint_names)
    excluded_rigid = next(
        (
            bpy.data.objects.get(name)
            for name in session.saved_rigid_matrices
            if name not in active_rigid_names
            and bpy.data.objects.get(name) is not None
        ),
        None,
    )
    excluded_joint = next(
        (
            bpy.data.objects.get(name)
            for name in session.saved_joint_matrices
            if name not in active_joint_names
            and bpy.data.objects.get(name) is not None
        ),
        None,
    )
    assert excluded_rigid is not None
    assert excluded_joint is not None
    return excluded_rigid, excluded_joint


def _edit_excluded_debug_objects(session):
    excluded_rigid, excluded_joint = _excluded_debug_objects(session)
    excluded_rigid.matrix_world = (
        Matrix.Translation((0.017, -0.011, 0.009))
        @ excluded_rigid.matrix_world
    )
    excluded_joint.matrix_world = (
        excluded_joint.matrix_world
        @ Matrix.Rotation(0.13, 4, "Z")
    )
    bpy.context.view_layer.update()
    expected = (
        excluded_rigid.matrix_world.copy(),
        excluded_joint.matrix_world.copy(),
    )
    assert (
        _matrix_error(
            expected[0],
            session.saved_rigid_matrices[excluded_rigid.name],
        )
        > 1.0e-5
    )
    assert (
        _matrix_error(
            expected[1],
            session.saved_joint_matrices[excluded_joint.name],
        )
        > 1.0e-5
    )
    return excluded_rigid, excluded_joint, expected


def _assert_excluded_debug_objects(objects, expected):
    errors = tuple(
        _matrix_error(obj.matrix_world, matrix_world)
        for obj, matrix_world in zip(objects, expected)
    )
    assert max(errors) < 1.0e-6, errors
    return errors


def _exercise_source_mesh_rename(session, pose_signature):
    display = _activate_display(session)
    source = bpy.data.objects[TARGET_MESH_NAME]
    binding = next(
        item
        for item in display.mesh_bindings
        if item.source_object is source
    )
    source_name = source.name
    renamed_source_name = f"{source_name}__SPX_RENAME_TEST"
    source_hidden = binding.source_hide_viewport
    output = binding.display_object
    assert bpy.data.objects.get(renamed_source_name) is None
    assert source.hide_viewport
    try:
        source.name = renamed_source_name
        assert display.valid
        session.tick(interactive=False)
        bpy.context.view_layer.update()
        assert session.display_rig is display
        assert display.valid
        assert output.get(SOURCE_OBJECT_KEY, "") == renamed_source_name
        assert source.get(SOURCE_TOKEN_KEY, "") == binding.source_token
        assert source.hide_viewport
        assert session._deactivate_display_rig(restore_source_connections=True)
        assert not _display_objects()
        assert source.hide_viewport is source_hidden
        assert SOURCE_OWNER_KEY not in source
        assert SOURCE_TOKEN_KEY not in source
        assert SOURCE_HIDE_VIEWPORT_KEY not in source
        assert source.name == renamed_source_name
        assert _pose_context_signature() == pose_signature
    finally:
        if session.display_rig is not None:
            session._deactivate_display_rig(restore_source_connections=True)
        source.hide_viewport = source_hidden
        source.name = source_name
        session.display_rig_unavailable = False
    print(
        "SPX_DISPLAY_SOURCE_RENAME_CLEAN_OK",
        f"source={source_name}",
    )


def _exercise_display_mutation_fallback(session, pose_signature):
    source = bpy.data.objects[TARGET_MESH_NAME]
    authored_data = source.data
    test_data = authored_data.copy()
    source.data = test_data
    solver_identity = id(session.world.solver)
    failure_count = session.consecutive_tick_failures
    reset_count = session.auto_reset_count
    display = _activate_display(session)
    try:
        test_data.vertices.add(1)
        test_data.update()
        assert not display.valid
        _assert_session_membership(session)
        session.tick(interactive=True)
        assert session.display_rig is None
        assert session.display_rig_unavailable
        assert not source.hide_viewport
        assert not _display_objects()
        assert id(session.world.solver) == solver_identity
        assert session.consecutive_tick_failures == failure_count
        assert session.auto_reset_count == reset_count
        assert _pose_context_signature() == pose_signature
    finally:
        if session.display_rig is not None:
            session._deactivate_display_rig(allow_retry=False)
        source.data = authored_data
        if test_data.users == 0:
            bpy.data.meshes.remove(test_data)
        session.display_rig_unavailable = False

    display = _activate_display(session)
    binding = next(
        item for item in display.bindings if item.mesh_object is source
    )
    modifier = binding.modifier
    try:
        modifier.show_viewport = False
        assert not display.valid
        session.tick(interactive=True)
        assert session.display_rig is None
        assert session.display_rig_unavailable
        assert not source.hide_viewport
        assert not _display_objects()
        assert id(session.world.solver) == solver_identity
        assert session.consecutive_tick_failures == failure_count
        assert session.auto_reset_count == reset_count
        assert _pose_context_signature() == pose_signature
    finally:
        modifier.show_viewport = True
        if session.display_rig is not None:
            session._deactivate_display_rig(allow_retry=False)
        session.display_rig_unavailable = False

    display = _activate_display(session)
    binding = next(
        item for item in display.bindings if item.mesh_object is source
    )
    modifier = binding.modifier
    preserve_volume = modifier.use_deform_preserve_volume
    try:
        modifier.use_deform_preserve_volume = not preserve_volume
        assert not display.valid
        session.tick(interactive=True)
        assert session.display_rig is None
        assert session.display_rig_unavailable
        assert not source.hide_viewport
        assert not _display_objects()
        assert id(session.world.solver) == solver_identity
        assert session.consecutive_tick_failures == failure_count
        assert session.auto_reset_count == reset_count
        assert _pose_context_signature() == pose_signature
    finally:
        modifier.use_deform_preserve_volume = preserve_volume
        if session.display_rig is not None:
            session._deactivate_display_rig(allow_retry=False)
        session.display_rig_unavailable = False
    print("SPX_DISPLAY_MUTATION_FALLBACK_OK")


def _finish_undo_redo_resume():
    callback = lifecycle._resume_undo_redo_timer
    if bpy.app.timers.is_registered(callback):
        bpy.app.timers.unregister(callback)
    callback()
    assert not runtime._RUNTIME_SUSPENDED


def _exercise():
    assert SAVE_PATH.name and SAVE_PATH.suffix.lower() == ".blend"
    assert not SAVE_PATH.exists()
    scene = bpy.context.scene
    root = bpy.data.objects[ROOT_NAME]
    source_armature = runtime._model_armature(root)
    assert source_armature is not None
    assert ROOT_BONE_NAME in source_armature.pose.bones
    assert FOOT_BONE_NAME in source_armature.pose.bones

    _exercise_stale_cleanup(scene, source_armature)
    pose_signature = _enter_pose_context(source_armature)

    settings = scene.surface_proxy_creator
    settings.preview_scope = "CURRENT_PROXY"
    settings.preview_frequency = 60
    settings.preview_substeps = 10
    settings.preview_update_rigids = True
    settings.preview_solver_target = "MMD"
    settings.mmd_root = root
    assert settings.physics_proxy is not None

    session = runtime.start_preview(bpy.context)[0]
    root_name = session.root_name
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    try:
        assert _pose_context_signature() == pose_signature
        for _index in range(6):
            session.tick(interactive=False)
        _assert_session_membership(session)

        _exercise_view_layer_hidden_source(session)

        display = _activate_display(session)
        display_names = display.binding_names
        _assert_modifier_bindings(display, source_armature)
        assert bpy.data.objects[TARGET_MESH_NAME].hide_viewport
        assert _pose_context_signature() == pose_signature

        assert session._deactivate_display_rig(restore_source_connections=True)
        assert not _display_objects()
        assert not _display_sources()
        assert not bpy.data.objects[TARGET_MESH_NAME].hide_viewport
        _assert_session_membership(session)
        for object_name, modifier_name in display_names:
            mesh_object = bpy.data.objects[object_name]
            assert mesh_object.modifiers[modifier_name].object is source_armature
        assert _pose_context_signature() == pose_signature

        _exercise_display_mutation_fallback(session, pose_signature)
        _exercise_source_mesh_rename(session, pose_signature)

        display = _activate_display(session)
        display_names = display.binding_names
        (
            excluded_rigid,
            excluded_joint,
            excluded_debug_expected,
        ) = _edit_excluded_debug_objects(session)
        runtime_debug_before_suspend = session._capture_debug_state()
        root_delta = (
            session.root.matrix_world
            @ session.saved_root_matrix.inverted_safe()
        )
        authored_debug = (
            {
                name: root_delta @ session.saved_rigid_matrices[name]
                for name in runtime_debug_before_suspend[0]
            },
            {
                name: root_delta @ session.saved_joint_matrices[name]
                for name in runtime_debug_before_suspend[1]
            },
        )
        runtime._suspend_display_rigs_for_save("")
        assert runtime._RUNTIME_SUSPENDED
        assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is not None
        assert not _display_objects()
        assert not _display_sources()
        assert _pose_context_signature() == pose_signature
        for object_name, modifier_name in display_names:
            mesh_object = bpy.data.objects[object_name]
            assert mesh_object.modifiers[modifier_name].object is source_armature
        assert all(
            source_armature.data.bones[name].use_connect == use_connect
            for name, use_connect in session.saved_bone_connections.items()
        )
        authored_name, authored_error = _debug_state_error(
            authored_debug,
            session._capture_debug_state(),
        )
        assert authored_error < 1.0e-6, (authored_name, authored_error)
        runtime._resume_display_rigs_after_save("")
        assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
        assert not runtime._RUNTIME_SUSPENDED
        restored_name, restored_error = _debug_state_error(
            runtime_debug_before_suspend,
            session._capture_debug_state(),
        )
        assert restored_error < 1.0e-6, (restored_name, restored_error)
        excluded_resume_errors = _assert_excluded_debug_objects(
            (excluded_rigid, excluded_joint),
            excluded_debug_expected,
        )
        assert _pose_context_signature() == pose_signature

        display = _activate_display(session)
        display_names = display.binding_names
        debug_state_before_save = session._capture_debug_state()
        assert bpy.ops.wm.save_as_mainfile(
            filepath=str(SAVE_PATH),
            check_existing=False,
            copy=True,
        ) == {"FINISHED"}
        assert SAVE_PATH.is_file()
        assert runtime._DISPLAY_RIG_SAVE_SUSPENSION is None
        assert not runtime._RUNTIME_SUSPENDED
        assert not session.isolated_output_active
        assert not _display_objects()
        assert not _display_sources()
        for object_name, modifier_name in display_names:
            mesh_object = bpy.data.objects[object_name]
            assert mesh_object.modifiers[modifier_name].object is source_armature
        assert _pose_context_signature() == pose_signature
        debug_state_after_save = session._capture_debug_state()
        assert len(debug_state_after_save) == len(debug_state_before_save)
        debug_name, debug_error = _debug_state_error(
            debug_state_before_save,
            debug_state_after_save,
        )
        print(
            "SPX_DISPLAY_SAVE_DEBUG_DRIFT",
            f"object={debug_name}",
            f"error={debug_error:.9g}",
        )
        assert debug_error < 1.0e-6, (debug_name, debug_error)
        excluded_save_errors = _assert_excluded_debug_objects(
            (excluded_rigid, excluded_joint),
            excluded_debug_expected,
        )

        display = _activate_display(session)
        assert _pose_context_signature() == pose_signature
        session_identity = id(session)
        world_identity = id(session.world)
        solver = session.world.solver
        generation = session.world.generation

        bpy.ops.ed.undo_push(message="SPX display lifecycle baseline")
        current_root = bpy.data.objects[root_name]
        current_root["spx_display_lifecycle_probe"] = 1
        bpy.ops.ed.undo_push(message="SPX display lifecycle edit")
        assert bpy.ops.ed.undo() == {"FINISHED"}
        assert runtime._RUNTIME_SUSPENDED
        assert runtime._ACTIVE_SESSIONS[root_name].display_rig is None
        undo_resurrected_rigs = len(_display_objects())
        _finish_undo_redo_resume()
        assert not _display_objects()
        assert not _display_sources()
        session = runtime._ACTIVE_SESSIONS[root_name]
        assert id(session) == session_identity
        assert id(session.world) == world_identity
        assert session.world.solver is not solver
        assert solver.handle is None
        assert session.world.generation == generation + 1
        solver = session.world.solver
        generation = session.world.generation
        assert "spx_display_lifecycle_probe" not in bpy.data.objects[root_name]
        assert _pose_context_signature() == pose_signature

        assert bpy.ops.ed.redo() == {"FINISHED"}
        assert runtime._RUNTIME_SUSPENDED
        _finish_undo_redo_resume()
        assert not _display_objects()
        assert not _display_sources()
        session = runtime._ACTIVE_SESSIONS[root_name]
        assert id(session) == session_identity
        assert id(session.world) == world_identity
        assert session.world.solver is not solver
        assert solver.handle is None
        assert session.world.generation == generation + 1
        assert bpy.data.objects[root_name]["spx_display_lifecycle_probe"] == 1

        session._force_display_rig_for_tests = True
        recreated = _activate_display(session)
        assert recreated.valid
        assert session.consecutive_tick_failures == 0
        assert session.auto_reset_count == 0
        assert _pose_context_signature() == pose_signature
        _assert_modifier_bindings(recreated, session.armature)

        print(
            "MMD_04_DISPLAY_RIG_LIFECYCLE_EXERCISE_OK",
            f"bindings={len(recreated.bindings)}",
            f"display_bones={len(recreated.pose_bones)}",
            f"session_identity={session_identity}",
            f"world_identity={world_identity}",
            f"solver_identity={id(session.world.solver)}",
            f"solver_generation={session.world.generation}",
            f"undo_resurrected_rigs={undo_resurrected_rigs}",
            f"save_authored_error={authored_error:.9g}",
            f"save_resume_error={restored_error:.9g}",
            f"save_post_error={debug_error:.9g}",
            "excluded_resume_error="
            f"{max(excluded_resume_errors):.9g}",
            f"excluded_save_error={max(excluded_save_errors):.9g}",
        )
    finally:
        if runtime._RUNTIME_SUSPENDED:
            cleanup_stale_display_rigs()
            _finish_undo_redo_resume()
        elif _display_objects() or _display_sources():
            cleanup_stale_display_rigs()
        current_root = bpy.data.objects.get(root_name)
        if current_root is not None:
            runtime.stop_preview(current_root)
        else:
            runtime.stop_preview()
        assert not _display_objects()
        assert not _display_sources()


def _verify_saved_copy():
    assert bpy.data.filepath == str(SAVE_PATH)
    assert not _display_objects()
    assert not _display_sources()
    root = bpy.data.objects[ROOT_NAME]
    source_armature = runtime._model_armature(root)
    assert source_armature is not None
    target_mesh = bpy.data.objects[TARGET_MESH_NAME]
    assert not bool(target_mesh.data.get(DISPLAY_MARKER, ""))
    assert SOURCE_OWNER_KEY not in target_mesh
    assert SOURCE_TOKEN_KEY not in target_mesh
    assert SOURCE_HIDE_VIEWPORT_KEY not in target_mesh
    target_modifiers = tuple(
        modifier
        for modifier in target_mesh.modifiers
        if modifier.type == "ARMATURE"
    )
    assert target_modifiers
    assert all(
        modifier.object is source_armature
        for modifier in target_modifiers
    )
    affected = 0
    for mesh_object in bpy.context.scene.objects:
        if mesh_object.type != "MESH":
            continue
        for modifier in mesh_object.modifiers:
            if modifier.type != "ARMATURE" or modifier.object is None:
                continue
            assert not bool(modifier.object.get(DISPLAY_MARKER, ""))
            if modifier.object is source_armature:
                affected += 1
    assert affected > 0
    assert cleanup_stale_display_rigs() == 0
    print(
        "MMD_04_DISPLAY_RIG_LIFECYCLE_RELOAD_OK",
        f"canonical_modifiers={affected}",
        f"filepath={SAVE_PATH}",
    )


if PHASE == "exercise":
    _exercise()
elif PHASE == "verify_saved":
    _verify_saved_copy()
else:
    raise AssertionError(f"Unknown SPX_LIFECYCLE_PHASE: {PHASE}")
