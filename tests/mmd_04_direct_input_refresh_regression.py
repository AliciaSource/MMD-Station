import os
import sys
from array import array
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ROOT_BONE_NAME = "\u5168\u3066\u306e\u89aa"
FRAME_STABLE = 10
FRAME_SKIPPED = 20
HOTPATH_TICKS = 24
SOLVER_TARGET = os.environ.get("SPX_TEST_SOLVER_TARGET", "MMD")
assert SOLVER_TARGET in {"MMD", "PMX"}
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_tools.core.model import FnModel
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()


def _matrix_error(first, second):
    return max(
        abs(left - right)
        for first_row, second_row in zip(first, second)
        for left, right in zip(first_row, second_row)
    )


def _legacy_live_payload(
    native,
    canonical,
    raw_pose_matrices=evaluator._raw_pose_matrices,
):
    matrices = raw_pose_matrices(
        canonical,
        native.input_basis,
        pose_bones=tuple(pose_bone for _index, pose_bone in native.mapped_order),
    )
    positions = array("f")
    bases = array("f")
    for _index, bone_name, rest_orientation_inverse in native.live_bindings:
        head_transform = matrices[bone_name] @ rest_orientation_inverse
        positions.extend(
            evaluator.blender_position_to_mmd(
                head_transform.translation,
                native.scale,
            )
        )
        basis = evaluator._live_rotation_to_mmd_rows(head_transform)
        bases.extend(value for row in basis for value in row)
    return matrices, positions, bases


def _prepare_direct_pose(preview):
    preview.prepare_step()
    assert preview._mmd_ik_direct_pose_active
    assert preview.isolated_output_active
    pose = {
        name: matrix.copy()
        for name, matrix in preview.display_rig.input_pose.items()
    }
    assert ROOT_BONE_NAME in pose
    return pose


def _exercise_foreign_scene_handlers(native, source_scene):
    foreign_scene = bpy.data.scenes.new("SPX foreign handler scene")
    restore_calls = 0
    evaluate_calls = 0
    refresh_scenes = []
    submit_scenes = []
    original_restore_input = native.restore_input
    original_evaluate_to = native.evaluate_to
    original_refresh_input = native._refresh_live_frame_input
    original_submit_live_pose = evaluator._submit_live_pose
    original_live = native.live

    def counted_restore_input(*args, **kwargs):
        nonlocal restore_calls
        restore_calls += 1
        return original_restore_input(*args, **kwargs)

    def counted_evaluate_to(*args, **kwargs):
        nonlocal evaluate_calls
        evaluate_calls += 1
        return original_evaluate_to(*args, **kwargs)

    def counted_refresh_input(canonical, scene, **kwargs):
        refresh_scenes.append(scene)
        return original_refresh_input(canonical, scene, **kwargs)

    def counted_submit_live_pose(session, canonical, scene, **kwargs):
        submit_scenes.append(scene)
        return original_submit_live_pose(
            session,
            canonical,
            scene,
            **kwargs,
        )

    try:
        native.restore_input = counted_restore_input
        evaluator._frame_change_pre(foreign_scene)
        native.live = False
        native.evaluate_to = counted_evaluate_to
        evaluator._frame_change_pre(foreign_scene)
        native.live = True
        native._refresh_live_frame_input = counted_refresh_input
        evaluator._submit_live_pose = counted_submit_live_pose
        with bpy.context.temp_override(
            scene=foreign_scene,
            view_layer=foreign_scene.view_layers[0],
        ):
            native.evaluate_exact(
                max(float(native.vmd_start), float(native.last_vmd_frame or 0.0)),
                apply_output=False,
                update=False,
                sync_state=False,
                scene=source_scene,
            )
    finally:
        native.restore_input = original_restore_input
        native.evaluate_to = original_evaluate_to
        native._refresh_live_frame_input = original_refresh_input
        evaluator._submit_live_pose = original_submit_live_pose
        native.live = original_live
        bpy.data.scenes.remove(foreign_scene)
    assert restore_calls == 0, restore_calls
    assert evaluate_calls == 0, evaluate_calls
    assert refresh_scenes == [source_scene], refresh_scenes
    assert submit_scenes == [source_scene], submit_scenes
    print("MMD_IK_FOREIGN_SCENE_HANDLERS_OK")


scene = bpy.context.scene
root = bpy.data.objects[ROOT_NAME]
armature = FnModel.find_armature_object(root)
assert armature is not None
root_bone = armature.pose.bones[ROOT_BONE_NAME]

if armature.animation_data is not None:
    armature.animation_data_clear()
action = bpy.data.actions.new("SPX direct input refresh regression")
armature.animation_data_create()
armature.animation_data.action = action
baseline_location = root_bone.location.copy()
for frame, offset in ((1, 0.0), (FRAME_STABLE, 0.2), (FRAME_SKIPPED, 0.4)):
    root_bone.location = baseline_location + Vector((offset, 0.0, 0.0))
    assert root_bone.keyframe_insert("location", frame=frame)
for curve in action.fcurves:
    for point in curve.keyframe_points:
        point.interpolation = "LINEAR"

expected_basis = {}
for frame in (FRAME_STABLE, FRAME_SKIPPED):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    expected_basis[frame] = root_bone.matrix_basis.copy()
scene.frame_set(1)
bpy.context.view_layer.update()

settings = scene.surface_proxy_creator
settings.mmd_root = root
settings.mmd_ik_root = root
settings.preview_solver_target = SOLVER_TARGET
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
assert settings.physics_proxy is not None
for item in bpy.data.objects:
    if getattr(item, "mmd_type", "") == "ROOT":
        item.spx_physics_preview_selected = item is root

if bpy.context.object is not armature or bpy.context.mode != "POSE":
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    armature.hide_set(False)
    armature.hide_viewport = False
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
assert bpy.context.object is armature and bpy.context.mode == "POSE"

source = Path(str(root.get("spx_mmd_ik_source_pmx", "")))
if not source.is_file():
    source = Path(str(root["import_folder"])) / f"{ROOT_NAME}.pmx"
    root["spx_mmd_ik_source_pmx"] = str(source)
assert source.is_file(), source
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

preview = None
native = None
try:
    native = evaluator._SESSIONS[root.name]
    assert not native.source_vmd
    preview = runtime.start_preview(bpy.context)[0]
    preview._force_display_rig_for_tests = True
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    for _index in range(7):
        preview.tick(interactive=True)
    assert preview.isolated_output_active
    assert preview.debug_batch is not None
    assert preview._native_pose_provider_compatible
    assert not native.has_blender_overrides()
    _exercise_foreign_scene_handlers(native, scene)

    identities = (
        preview,
        preview.world,
        preview.world.solver,
        native,
        native.solver,
    )

    scene.frame_set(FRAME_STABLE)
    bpy.context.view_layer.update()
    assert native.input_signature[:2] == (FRAME_STABLE, 0.0)
    stable_input_error = _matrix_error(
        native.input_basis[ROOT_BONE_NAME],
        expected_basis[FRAME_STABLE],
    )
    assert stable_input_error < 2.0e-5, stable_input_error
    stable_pose = _prepare_direct_pose(preview)
    if preview.step_solver():
        preview.apply_step(*preview.world.outputs())

    native.suspended = True
    scene.frame_set(FRAME_SKIPPED)
    bpy.context.view_layer.update()
    authored_input_error = _matrix_error(
        preview.armature.pose.bones[ROOT_BONE_NAME].matrix_basis,
        expected_basis[FRAME_SKIPPED],
    )
    assert authored_input_error < 2.0e-5, authored_input_error
    native.suspended = False

    refreshed_pose = _prepare_direct_pose(preview)
    assert native.input_signature[:2] == (FRAME_SKIPPED, 0.0)
    refreshed_input_error = _matrix_error(
        native.input_basis[ROOT_BONE_NAME],
        expected_basis[FRAME_SKIPPED],
    )
    assert refreshed_input_error < 2.0e-5, refreshed_input_error
    direct_pose_delta = _matrix_error(
        stable_pose[ROOT_BONE_NAME],
        refreshed_pose[ROOT_BONE_NAME],
    )
    assert direct_pose_delta > 0.1, direct_pose_delta
    assert identities == (
        preview,
        preview.world,
        preview.world.solver,
        native,
        native.solver,
    )

    if preview.step_solver():
        preview.apply_step(*preview.world.outputs())
    assert native.input_signature[:2] == (FRAME_SKIPPED, 0.0)
    assert identities == (
        preview,
        preview.world,
        preview.world.solver,
        native,
        native.solver,
    )

    original_live_signature = evaluator._live_input_signature
    original_action_signature = evaluator._action_frame_signature
    original_cleared_snapshot = evaluator._cleared_pose_snapshot
    original_raw_pose_matrices = evaluator._raw_pose_matrices
    original_set_live_matrices = native.solver.set_live_matrices
    original_set_live_matrix_buffers = native.solver.set_live_matrix_buffers
    signature_calls = []
    action_signature_calls = []
    cleared_snapshot_calls = []
    raw_pose_calls = []
    legacy_live_calls = []
    flat_live_calls = []
    input_durations = []
    callback_durations = []
    callback_signature_calls = []
    maximum_direct_matrix_error = 0.0
    maximum_direct_payload_error = 0.0
    equivalence_checks = 0
    output_basis = native.output_basis
    output_basis_snapshot = {
        name: matrix.copy() for name, matrix in output_basis.items()
    }

    def tracked_live_signature(canonical, target_scene):
        signature_calls.append((canonical, target_scene))
        return original_live_signature(canonical, target_scene)

    def tracked_action_signature(canonical, frame):
        action_signature_calls.append((canonical, frame))
        return original_action_signature(canonical, frame)

    def tracked_cleared_snapshot(canonical, output):
        cleared_snapshot_calls.append((canonical, output))
        return original_cleared_snapshot(canonical, output)

    def tracked_raw_pose_matrices(*args, **kwargs):
        raw_pose_calls.append((args, kwargs))
        return original_raw_pose_matrices(*args, **kwargs)

    def tracked_set_live_matrices(entries):
        legacy_live_calls.append(entries)
        return original_set_live_matrices(entries)

    def tracked_set_live_matrix_buffers(prepared_indices, positions, bases):
        flat_live_calls.append((prepared_indices, positions, bases))
        return original_set_live_matrix_buffers(
            prepared_indices,
            positions,
            bases,
        )

    motion_baseline = root_bone.location.copy()
    wall_seconds = 0.0
    assert runtime._timer_tick_session(
        preview,
        wall_seconds,
        interactive=True,
    ) is not None
    evaluator._live_input_signature = tracked_live_signature
    evaluator._action_frame_signature = tracked_action_signature
    evaluator._cleared_pose_snapshot = tracked_cleared_snapshot
    evaluator._raw_pose_matrices = tracked_raw_pose_matrices
    native.solver.set_live_matrices = tracked_set_live_matrices
    native.solver.set_live_matrix_buffers = tracked_set_live_matrix_buffers
    try:
        for index in range(HOTPATH_TICKS):
            direction = 1.0 if index % 2 else -1.0
            root_bone.location = motion_baseline + Vector(
                (direction * (0.001 + index * 0.00001), 0.0, 0.0)
            )
            signature_start = len(signature_calls)
            started = perf_counter()
            bpy.context.view_layer.update()
            input_durations.append((perf_counter() - started) * 1000.0)
            input_signature_count = len(signature_calls) - signature_start
            assert input_signature_count == 1, (index, input_signature_count)
            authored_basis = root_bone.matrix_basis.copy()
            legacy_matrices, legacy_positions, legacy_bases = _legacy_live_payload(
                native,
                armature,
            )
            direct_positions, direct_bases = evaluator._direct_live_matrix_buffers(
                native
            )
            assert len(direct_positions) == len(legacy_positions)
            assert len(direct_bases) == len(legacy_bases)
            direct_matrix_error = max(
                _matrix_error(
                    legacy_matrices[pose_bone.name],
                    pose_bone.matrix,
                )
                for _bone_index, pose_bone, _rest_inverse
                in native.direct_live_bindings
            )
            direct_payload_error = max(
                max(
                    abs(left - right)
                    for left, right in zip(direct_positions, legacy_positions)
                ),
                max(
                    abs(left - right)
                    for left, right in zip(direct_bases, legacy_bases)
                ),
            )
            maximum_direct_matrix_error = max(
                maximum_direct_matrix_error,
                direct_matrix_error,
            )
            maximum_direct_payload_error = max(
                maximum_direct_payload_error,
                direct_payload_error,
            )
            equivalence_checks += 1
            assert direct_matrix_error < 1.5e-6, (index, direct_matrix_error)
            assert direct_payload_error < 2.0e-5, (index, direct_payload_error)
            callback_start = len(signature_calls)
            wall_seconds += 1.0 / 60.0
            started = perf_counter()
            assert runtime._timer_tick_session(
                preview,
                wall_seconds,
                interactive=True,
            ) is not None
            callback_durations.append((perf_counter() - started) * 1000.0)
            callback_signature_calls.append(len(signature_calls) - callback_start)
            input_error = _matrix_error(
                native.input_basis[ROOT_BONE_NAME],
                authored_basis,
            )
            assert input_error < 2.0e-5, (index, input_error)
    finally:
        evaluator._live_input_signature = original_live_signature
        evaluator._action_frame_signature = original_action_signature
        evaluator._cleared_pose_snapshot = original_cleared_snapshot
        evaluator._raw_pose_matrices = original_raw_pose_matrices
        native.solver.set_live_matrices = original_set_live_matrices
        native.solver.set_live_matrix_buffers = original_set_live_matrix_buffers

    assert not any(callback_signature_calls), callback_signature_calls
    assert not action_signature_calls, len(action_signature_calls)
    assert not cleared_snapshot_calls, len(cleared_snapshot_calls)
    assert not raw_pose_calls, len(raw_pose_calls)
    assert not legacy_live_calls, len(legacy_live_calls)
    assert len(flat_live_calls) == HOTPATH_TICKS, len(flat_live_calls)
    assert equivalence_checks == HOTPATH_TICKS, equivalence_checks
    assert native.output_basis is output_basis
    assert set(native.output_basis) == set(output_basis_snapshot)
    assert all(
        native.output_basis[name] == matrix
        for name, matrix in output_basis_snapshot.items()
    )
    combined_durations = [
        input_duration + callback_duration
        for input_duration, callback_duration in zip(
            input_durations,
            callback_durations,
        )
    ]

    replay_scenes = []
    original_replay_live = evaluator.replay_live

    def tracked_replay_live(target_root, scene=None):
        replay_scenes.append(scene)
        return original_replay_live(target_root, scene=scene)

    try:
        evaluator.replay_live = tracked_replay_live
        runtime.stop_preview(root)
        preview = None
    finally:
        evaluator.replay_live = original_replay_live
    assert replay_scenes == [scene], replay_scenes

    print(
        "MMD_04_DIRECT_INPUT_REFRESH_OK",
        f"solver={SOLVER_TARGET}",
        f"stable_error={stable_input_error:.9g}",
        f"authored_error={authored_input_error:.9g}",
        f"refreshed_error={refreshed_input_error:.9g}",
        f"direct_delta={direct_pose_delta:.9g}",
        f"hotpath_ticks={HOTPATH_TICKS}",
        f"input_median_ms={median(input_durations):.6f}",
        f"input_p90_ms={quantiles(input_durations, n=10, method='inclusive')[8]:.6f}",
        f"callback_median_ms={median(callback_durations):.6f}",
        f"callback_p90_ms={quantiles(callback_durations, n=10, method='inclusive')[8]:.6f}",
        f"combined_median_ms={median(combined_durations):.6f}",
        f"combined_p90_ms={quantiles(combined_durations, n=10, method='inclusive')[8]:.6f}",
        f"signature_calls={len(signature_calls)}",
        f"callback_signature_calls={sum(callback_signature_calls)}",
        f"action_signature_calls={len(action_signature_calls)}",
        f"cleared_snapshot_calls={len(cleared_snapshot_calls)}",
        f"raw_pose_calls={len(raw_pose_calls)}",
        f"legacy_live_calls={len(legacy_live_calls)}",
        f"flat_live_calls={len(flat_live_calls)}",
        f"matrix_error={maximum_direct_matrix_error:.9g}",
        f"payload_error={maximum_direct_payload_error:.9g}",
        f"replay_scene_calls={len(replay_scenes)}",
        f"identities={tuple(id(item) for item in identities)}",
    )
finally:
    if native is not None:
        native.suspended = False
    if preview is not None and root.name in runtime._ACTIVE_SESSIONS:
        runtime.stop_preview(root)
    if root.name in evaluator._SESSIONS:
        bpy.ops.surface_proxy.remove_mmd_ik_runtime()
