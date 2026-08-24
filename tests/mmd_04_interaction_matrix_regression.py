import math
import os
import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import bpy
from mathutils import Matrix, Quaternion, Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
ROOT_BONE_NAME = "全ての親"
FOOT_BONE_NAME = "足D.L"
DT = 1.0 / 60.0
WARMUP_TICKS = 30
ROOT_MOVE_TICKS = 60
FOOT_ROTATE_TICKS = 60
HOLD_TICKS = 30
ROOT_MOVE_DISTANCE = 0.06
FOOT_ROTATION_RADIANS = 0.35

sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import display_rig as display_rig_module
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()


def _matrix_finite(matrix):
    return all(math.isfinite(value) for row in matrix for value in row)


def _basis_error(actual, expected):
    rotation_error = _rotation_error(actual, expected)
    return max(
        (actual.translation - expected.translation).length,
        rotation_error,
        (actual.to_scale() - expected.to_scale()).length,
    )


def _rotation_error(actual, expected):
    angle = actual.to_quaternion().rotation_difference(
        expected.to_quaternion()
    ).angle
    return min(angle, abs(math.tau - angle))


def _canonical_input_pose(session):
    return {
        pose_bone.name: pose_bone.matrix.copy()
        for pose_bone in session.direct_input_pose_bones()
    }


def _current_physics_targets(session):
    bone_transforms = session.solver.bone_transforms()
    armature_inverse = session.armature.matrix_world.inverted_safe()
    targets = {}
    for index, bone_transform in enumerate(
        bone_transforms[
            session.body_offset:session.body_offset + len(session.rigids)
        ]
    ):
        mode = session.rigid_modes[index]
        pose_bone = session.rigid_pose_bones[index]
        if (
            mode == 0
            or index not in session.bone_offsets
            or pose_bone is None
            or session.bone_drivers.get(pose_bone.name) != index
        ):
            continue
        position, rotation = runtime.transform_to_components(bone_transform)
        bone_world = Matrix.LocRotScale(
            Vector(position) * session.import_scale,
            Quaternion(rotation),
            Vector((1.0, 1.0, 1.0)),
        )
        targets[pose_bone.name] = (mode, armature_inverse @ bone_world)
    return targets


def _type_zero_error(session, current_input_pose):
    ordered_bones = tuple(
        sorted(
            (
                session.armature.pose.bones[name]
                for name in current_input_pose
                if name in session.armature.pose.bones
            ),
            key=lambda pose_bone: len(pose_bone.parent_recursive),
        )
    )
    assert len(ordered_bones) == len(current_input_pose)
    resolved_pose = runtime._resolve_hierarchical_bone_targets(
        session.armature,
        current_input_pose,
        _current_physics_targets(session),
        ordered_bones=ordered_bones,
    )
    errors = []
    for index, rigid in enumerate(session.rigids):
        if session.rigid_modes[index] != 0 or index not in session.bone_offsets:
            continue
        pose_bone = session.rigid_pose_bones[index]
        bone_pose = resolved_pose.get(pose_bone.name)
        assert bone_pose is not None, pose_bone.name
        expected = (
            session.armature.matrix_world
            @ bone_pose
            @ session.bone_offsets[index]
        )
        rigid_world = session.debug_matrix_world(rigid)
        rotation_error = rigid_world.to_quaternion().rotation_difference(
            expected.to_quaternion()
        ).angle
        errors.append(
            max(
                (rigid_world.translation - expected.translation).length,
                min(rotation_error, abs(math.tau - rotation_error)),
            )
        )
    assert errors
    return max(errors)


def _native_pose_matrix(ik_session, bone_name):
    if ik_session is None:
        return None
    index = ik_session.bone_indices.get(bone_name)
    if index is None:
        return None
    pose_bone = ik_session.mapping[index]
    if pose_bone is None:
        return None
    return evaluator.blender_pose_matrix(
        ik_session.solver.matrix(index),
        ik_session.scale,
        pose_bone.bone.matrix_local,
    )


def _presentation_pose_matrix(session, bone_name):
    pose_bone = session.presentation_armature.pose.bones.get(bone_name)
    return pose_bone.matrix.copy() if pose_bone is not None else None


def _dynamic_signatures(session):
    transforms = session.solver.transforms()
    signatures = {1: [], 2: []}
    for index, mode in enumerate(session.rigid_modes):
        if mode not in signatures:
            continue
        location, rotation = runtime.transform_to_components(
            transforms[session.body_offset + index]
        )
        values = (*location, *rotation)
        assert all(math.isfinite(value) for value in values), (mode, index, values)
        signatures[mode].extend(values)
    assert signatures[1]
    assert signatures[2]
    return {mode: tuple(values) for mode, values in signatures.items()}


def _presented_dynamic_signatures(session):
    signatures = {1: [], 2: []}
    presentation_armature = session.presentation_armature
    presentation_bones = presentation_armature.pose.bones
    for index, mode in enumerate(session.rigid_modes):
        if mode not in signatures:
            continue
        rigid = session.rigids[index]
        pose_bone = session.rigid_pose_bones[index]
        rigid_world = session.debug_matrix_world(rigid)
        signatures[mode].extend(
            value for row in rigid_world for value in row
        )
        if pose_bone is not None:
            presented_bone = presentation_bones.get(pose_bone.name)
            assert presented_bone is not None, pose_bone.name
            bone_world = presentation_armature.matrix_world @ presented_bone.matrix
            signatures[mode].extend(value for row in bone_world for value in row)
    assert signatures[1]
    assert signatures[2]
    assert all(
        math.isfinite(value)
        for values in signatures.values()
        for value in values
    )
    return {mode: tuple(values) for mode, values in signatures.items()}


def _dynamic_bone_error(session):
    bone_transforms = session.solver.bone_transforms()
    presentation_armature = session.presentation_armature
    errors = []
    for bone_name, rigid_index in session.bone_drivers.items():
        if session.rigid_modes[rigid_index] not in {1, 2}:
            continue
        presented_bone = presentation_armature.pose.bones.get(bone_name)
        assert presented_bone is not None, bone_name
        position, rotation = runtime.transform_to_components(
            bone_transforms[session.body_offset + rigid_index]
        )
        expected = Matrix.LocRotScale(
            Vector(position) * session.import_scale,
            Quaternion(rotation),
            Vector((1.0, 1.0, 1.0)),
        )
        actual = presentation_armature.matrix_world @ presented_bone.matrix
        errors.append(_basis_error(actual, expected))
    assert errors
    return max(errors)


def _native_pose_error(ik_session, preview_session):
    if ik_session is None:
        return 0.0, ""
    dynamic_bones = {
        pose_bone.name: pose_bone
        for index, pose_bone in enumerate(preview_session.rigid_pose_bones)
        if pose_bone is not None and preview_session.rigid_modes[index] in {1, 2}
    }
    physics_branches = set(dynamic_bones)
    for dynamic_bone in dynamic_bones.values():
        physics_branches.update(child.name for child in dynamic_bone.children_recursive)
    errors = []
    presentation_bones = preview_session.presentation_armature.pose.bones
    for index, pose_bone in enumerate(ik_session.mapping):
        if pose_bone is None or pose_bone.name in physics_branches:
            continue
        presented_bone = presentation_bones.get(pose_bone.name)
        if presented_bone is None:
            continue
        expected = evaluator.blender_pose_matrix(
            ik_session.solver.matrix(index),
            ik_session.scale,
            pose_bone.bone.matrix_local,
        )
        errors.append(
            (_basis_error(presented_bone.matrix, expected), pose_bone.name)
        )
    assert errors, "no comparable native/presentation pose bone"
    error, bone_name = max(errors)
    pose_bone = preview_session.armature.pose.bones[bone_name]
    diagnostic = (
        bone_name,
        tuple(parent.name for parent in pose_bone.parent_recursive),
        bool(pose_bone.bone.select),
    )
    return error, diagnostic


def _signature_delta(previous, current):
    return max(abs(left - right) for left, right in zip(previous, current))


def _percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _pipeline_counters(session):
    pose_input = session.pose_input
    return (
        pose_input.output_write_count,
        pose_input.skipped_output_count,
        pose_input.output_evaluation_count,
        pose_input.kinematic_debug_update_count,
        bool(pose_input.self_write_pending),
    )


def _pipeline_counter_delta(start, end):
    writes = end[0] - start[0]
    skipped = end[1] - start[1]
    evaluations = end[2] - start[2]
    kinematic_updates = end[3] - start[3]
    attempts = writes + skipped
    return {
        "writes": writes,
        "skipped": skipped,
        "evaluations": evaluations,
        "kinematic_updates": kinematic_updates,
        "attempts": attempts,
        "write_ratio": writes / max(attempts, 1),
        "skip_ratio": skipped / max(attempts, 1),
        "evaluation_per_write": evaluations / max(writes, 1),
        "pending_start": start[4],
        "pending_end": end[4],
    }


def _assert_runtime_identity(session, identity):
    active_session, world, solver, generation = identity
    assert session is active_session
    assert runtime._ACTIVE_SESSIONS.get(session.root_name) is active_session
    assert session.world is world
    assert session.solver is solver
    assert world.solver is solver
    assert world.sessions == [session]
    assert world.generation == generation
    assert session.auto_reset_count == 0
    assert session.consecutive_tick_failures == 0
    assert not session.snapshot_reset_pending
    assert not session.closed


def _activate_pose_bone(armature, pose_bone):
    if bpy.context.object is armature and bpy.context.mode == "POSE":
        for bone in armature.data.bones:
            bone.select = False
        pose_bone.bone.select = True
        armature.data.bones.active = pose_bone.bone
        assert bpy.context.view_layer.objects.active == armature
        assert armature.data.bones.active.name == pose_bone.name
        return
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    armature.hide_set(False)
    armature.hide_viewport = False
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    for bone in armature.data.bones:
        bone.select = False
    pose_bone.bone.select = True
    armature.data.bones.active = pose_bone.bone
    bpy.ops.object.mode_set(mode="POSE")
    assert bpy.context.mode == "POSE"
    assert bpy.context.view_layer.objects.active == armature
    assert armature.data.bones.active.name == pose_bone.name


def _assert_finite_scene(session, edited_bone):
    assert _matrix_finite(edited_bone.matrix_basis)
    assert _matrix_finite(edited_bone.matrix)
    for rigid in session.rigids:
        assert _matrix_finite(session.debug_matrix_world(rigid)), rigid.name
    for joint in session.joints:
        assert _matrix_finite(session.debug_matrix_world(joint)), joint.name


solver_target = os.environ.get("SPX_TEST_SOLVER_TARGET", "MMD")
ik_enabled = bool(os.environ.get("SPX_ENABLE_IK"))
assert solver_target in {"MMD", "PMX"}

root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_solver_target = solver_target
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
assert settings.physics_proxy is not None

for item in bpy.data.objects:
    if getattr(item, "mmd_type", "") == "ROOT":
        item.spx_physics_preview_selected = item is root

ik_session = None
original_modal_probe = None
if ik_enabled:
    source_pmx = Path(root.get("spx_mmd_ik_source_pmx", ""))
    if not source_pmx.is_file():
        source_pmx = Path(root["import_folder"]) / f"{ROOT_NAME}.pmx"
        root["spx_mmd_ik_source_pmx"] = str(source_pmx)
    assert source_pmx.is_file(), source_pmx
    settings.mmd_ik_root = root
    assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
    ik_session = evaluator._SESSIONS[root.name]
    original_modal_probe = getattr(evaluator, "_transform_modal_active", None)
    evaluator._transform_modal_active = lambda: True
else:
    assert root.name not in evaluator._SESSIONS

session = None
failure_events = []
direct_pose_inputs = []
original_prepare_step_from_pose = None
original_failure_handler = runtime._recover_tick_failure


def _track_tick_failure(failed_session, error, interval):
    failure_events.append((type(error).__name__, str(error)))
    return original_failure_handler(failed_session, error, interval)


runtime._recover_tick_failure = _track_tick_failure
try:
    session = runtime.start_preview(bpy.context)[0]
    session._force_display_rig_for_tests = True
    if ik_session is not None:
        original_prepare_step_from_pose = session.prepare_step_from_pose

        def capture_prepare_step_from_pose(pose_matrices, *args, **kwargs):
            direct_pose_inputs.append(
                {
                    name: matrix.copy()
                    for name, matrix in pose_matrices.items()
                }
            )
            return original_prepare_step_from_pose(
                pose_matrices,
                *args,
                **kwargs,
            )

        session.prepare_step_from_pose = capture_prepare_step_from_pose
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    armature = session.armature
    root_bone = armature.pose.bones[ROOT_BONE_NAME]
    foot_bone = armature.pose.bones[FOOT_BONE_NAME]
    root_baseline = root_bone.matrix_basis.copy()
    foot_baseline = foot_bone.matrix_basis.copy()
    identity = (session, session.world, session.solver, session.world.generation)
    ik_identity = (
        (
            ik_session,
            bpy.data.objects[ik_session.runtime_name],
            ik_session.solver,
        )
        if ik_session is not None
        else None
    )
    wall_seconds = 0.0
    maximum_type_zero_error = 0.0
    type_zero_debug_checks = 0
    maximum_dynamic_bone_error = 0.0
    maximum_native_pose_error = 0.0
    maximum_root_error = 0.0
    maximum_foot_error = 0.0
    maximum_root_native_translation = 0.0
    maximum_root_presented_translation = 0.0
    maximum_foot_native_rotation = 0.0
    maximum_foot_presented_rotation = 0.0
    maximum_foot_chain_response = 0.0
    output_writes = session.pose_input.output_write_count
    dynamic_previous = None
    presented_previous = None
    dynamic_frozen_runs = {1: 0, 2: 0}
    dynamic_longest_frozen = {1: 0, 2: 0}
    dynamic_changed_ticks = {1: 0, 2: 0}
    presented_frozen_runs = {1: 0, 2: 0}
    presented_longest_frozen = {1: 0, 2: 0}
    presented_changed_ticks = {1: 0, 2: 0}
    tick_durations = []
    input_update_durations = []
    output_update_durations = []
    frame_durations = []

    def tick(
        edited_bone,
        expect_output=True,
        track_dynamic_motion=False,
        check_native_pose=False,
        input_update_duration=0.0,
    ):
        global wall_seconds
        global maximum_type_zero_error
        global type_zero_debug_checks
        global maximum_dynamic_bone_error
        global maximum_native_pose_error
        global output_writes
        global dynamic_previous
        global presented_previous
        direct_pose_input_count = len(direct_pose_inputs)
        current_input_pose = (
            _canonical_input_pose(session) if ik_session is None else None
        )
        wall_seconds += DT
        kinematic_debug_updates = (
            session.pose_input.kinematic_debug_update_count
        )
        started = perf_counter()
        interval = runtime._timer_tick_session(
            session,
            wall_seconds,
            interactive=True,
        )
        callback_duration = perf_counter() - started
        tick_durations.append(callback_duration)
        assert interval is not None
        _assert_runtime_identity(session, identity)
        if ik_identity is not None:
            expected_ik, expected_runtime, expected_solver = ik_identity
            current_ik = evaluator._SESSIONS.get(root.name)
            assert current_ik is expected_ik
            assert bpy.data.objects.get(current_ik.runtime_name) == expected_runtime
            assert current_ik.solver is expected_solver
        if expect_output:
            assert session.pose_input.output_write_count == output_writes + 1
            assert (
                session.pose_input.kinematic_debug_update_count
                == kinematic_debug_updates + 1
            )
        output_writes = session.pose_input.output_write_count
        if expect_output:
            if ik_session is not None:
                assert len(direct_pose_inputs) > direct_pose_input_count
                current_input_pose = direct_pose_inputs[-1]
            assert current_input_pose is not None
            type_zero_debug_checks += 1
            maximum_type_zero_error = max(
                maximum_type_zero_error,
                _type_zero_error(session, current_input_pose),
            )
            assert maximum_type_zero_error < 2.0e-5, maximum_type_zero_error
        view_started = perf_counter()
        bpy.context.view_layer.update()
        output_update_duration = perf_counter() - view_started
        input_update_durations.append(input_update_duration)
        output_update_durations.append(output_update_duration)
        frame_durations.append(
            input_update_duration + callback_duration + output_update_duration
        )
        maximum_dynamic_bone_error = max(
            maximum_dynamic_bone_error,
            _dynamic_bone_error(session),
        )
        assert maximum_dynamic_bone_error < 2.0e-5, maximum_dynamic_bone_error
        if check_native_pose:
            native_pose_error, native_pose_bone = _native_pose_error(
                ik_session,
                session,
            )
            maximum_native_pose_error = max(
                maximum_native_pose_error,
                native_pose_error,
            )
            assert maximum_native_pose_error < 1.5e-3, (
                maximum_native_pose_error,
                native_pose_bone,
            )
        _assert_finite_scene(session, edited_bone)
        current = _dynamic_signatures(session)
        presented = _presented_dynamic_signatures(session)
        if track_dynamic_motion and dynamic_previous is not None:
            for mode in (1, 2):
                delta = _signature_delta(dynamic_previous[mode], current[mode])
                if delta <= 1.0e-9:
                    dynamic_frozen_runs[mode] += 1
                else:
                    dynamic_frozen_runs[mode] = 0
                    dynamic_changed_ticks[mode] += 1
                dynamic_longest_frozen[mode] = max(
                    dynamic_longest_frozen[mode], dynamic_frozen_runs[mode]
                )
                presented_delta = _signature_delta(
                    presented_previous[mode], presented[mode]
                )
                if presented_delta <= 1.0e-9:
                    presented_frozen_runs[mode] += 1
                else:
                    presented_frozen_runs[mode] = 0
                    presented_changed_ticks[mode] += 1
                presented_longest_frozen[mode] = max(
                    presented_longest_frozen[mode],
                    presented_frozen_runs[mode],
                )
        dynamic_previous = current
        presented_previous = presented

    runtime._timer_tick(0.0)
    output_writes = session.pose_input.output_write_count
    for warmup_index in range(WARMUP_TICKS):
        tick(root_bone, check_native_pose=warmup_index == WARMUP_TICKS - 1)
    assert session.isolated_output_active
    root_native_baseline = _native_pose_matrix(ik_session, ROOT_BONE_NAME)
    root_presented_baseline = _presentation_pose_matrix(session, ROOT_BONE_NAME)
    if ik_session is not None:
        assert root_native_baseline is not None, ROOT_BONE_NAME
        assert root_presented_baseline is not None, ROOT_BONE_NAME

    _activate_pose_bone(armature, root_bone)
    original_display_modal_probe = display_rig_module._transform_modal_active
    display_rig_module._transform_modal_active = lambda scene=None: True
    motion_start_index = len(tick_durations)
    motion_pipeline_start = _pipeline_counters(session)
    dynamic_previous = _dynamic_signatures(session)
    presented_previous = _presented_dynamic_signatures(session)
    for index in range(1, ROOT_MOVE_TICKS + 1):
        phase = index / (ROOT_MOVE_TICKS / 2)
        offset = ROOT_MOVE_DISTANCE * (phase if phase <= 1.0 else 2.0 - phase)
        target = root_baseline.copy()
        target.translation = root_baseline.translation + Vector((offset, 0.0, 0.0))
        root_bone.matrix_basis = target
        input_started = perf_counter()
        bpy.context.view_layer.update()
        input_update_duration = perf_counter() - input_started
        tick(
            root_bone,
            track_dynamic_motion=True,
            check_native_pose=index % 10 == 0,
            input_update_duration=input_update_duration,
        )
        root_error = _basis_error(root_bone.matrix_basis, target)
        maximum_root_error = max(maximum_root_error, root_error)
        assert root_error < 2.0e-5, (index, root_error)
        assert armature.data.bones.active.name == root_bone.name
        if ik_session is not None:
            current_native = _native_pose_matrix(ik_session, ROOT_BONE_NAME)
            current_presented = _presentation_pose_matrix(session, ROOT_BONE_NAME)
            assert current_native is not None, ROOT_BONE_NAME
            assert current_presented is not None, ROOT_BONE_NAME
            maximum_root_native_translation = max(
                maximum_root_native_translation,
                (
                    current_native.translation
                    - root_native_baseline.translation
                ).length,
            )
            maximum_root_presented_translation = max(
                maximum_root_presented_translation,
                (
                    current_presented.translation
                    - root_presented_baseline.translation
                ).length,
            )

    for mode in (1, 2):
        assert dynamic_changed_ticks[mode] >= ROOT_MOVE_TICKS - 3, (
            mode,
            dynamic_changed_ticks[mode],
        )
        assert dynamic_longest_frozen[mode] <= 2, (
            mode,
            dynamic_longest_frozen[mode],
        )
        assert presented_changed_ticks[mode] >= ROOT_MOVE_TICKS - 3, (
            mode,
            presented_changed_ticks[mode],
        )
        assert presented_longest_frozen[mode] <= 2, (
            mode,
            presented_longest_frozen[mode],
        )

    _activate_pose_bone(armature, foot_bone)
    foot_native_baselines = {}
    foot_presented_baseline = None
    if ik_session is not None:
        foot_chain_names = tuple(
            name
            for name in (
                FOOT_BONE_NAME,
                *(child.name for child in foot_bone.children_recursive),
            )
            if name in ik_session.bone_indices
        )
        assert (
            len(foot_chain_names) > 1
            and foot_chain_names[0] == FOOT_BONE_NAME
        ), foot_chain_names
        foot_native_baselines = {
            name: _native_pose_matrix(ik_session, name)
            for name in foot_chain_names
        }
        assert all(
            matrix is not None for matrix in foot_native_baselines.values()
        )
        foot_presented_baseline = _presentation_pose_matrix(
            session,
            FOOT_BONE_NAME,
        )
    for index in range(1, FOOT_ROTATE_TICKS + 1):
        angle = FOOT_ROTATION_RADIANS * index / FOOT_ROTATE_TICKS
        target = foot_baseline @ Matrix.Rotation(angle, 4, "Z")
        foot_bone.matrix_basis = target
        input_started = perf_counter()
        bpy.context.view_layer.update()
        input_update_duration = perf_counter() - input_started
        tick(
            foot_bone,
            check_native_pose=index % 10 == 0,
            input_update_duration=input_update_duration,
        )
        foot_error = _basis_error(foot_bone.matrix_basis, target)
        maximum_foot_error = max(maximum_foot_error, foot_error)
        assert foot_error < 2.0e-5, (index, foot_error)
        assert armature.data.bones.active.name == foot_bone.name
        if ik_session is not None:
            current_foot_native = _native_pose_matrix(
                ik_session,
                FOOT_BONE_NAME,
            )
            assert current_foot_native is not None, FOOT_BONE_NAME
            maximum_foot_native_rotation = max(
                maximum_foot_native_rotation,
                _rotation_error(
                    current_foot_native,
                    foot_native_baselines[FOOT_BONE_NAME],
                ),
            )
            maximum_foot_chain_response = max(
                maximum_foot_chain_response,
                *(
                    _basis_error(
                        _native_pose_matrix(ik_session, name),
                        baseline,
                    )
                    for name, baseline in foot_native_baselines.items()
                    if name != FOOT_BONE_NAME
                ),
            )
            current_foot_presented = _presentation_pose_matrix(
                session,
                FOOT_BONE_NAME,
            )
            if (
                foot_presented_baseline is not None
                and current_foot_presented is not None
            ):
                maximum_foot_presented_rotation = max(
                    maximum_foot_presented_rotation,
                    _rotation_error(
                        current_foot_presented,
                        foot_presented_baseline,
                    ),
                )

    if ik_session is not None:
        assert maximum_root_native_translation > ROOT_MOVE_DISTANCE * 0.8, (
            maximum_root_native_translation,
            maximum_root_presented_translation,
        )
        assert maximum_root_presented_translation > ROOT_MOVE_DISTANCE * 0.8, (
            maximum_root_native_translation,
            maximum_root_presented_translation,
        )
        assert maximum_foot_native_rotation > FOOT_ROTATION_RADIANS * 0.5, (
            maximum_foot_native_rotation,
            maximum_foot_chain_response,
        )
        assert maximum_foot_chain_response > FOOT_ROTATION_RADIANS * 0.5, (
            maximum_foot_native_rotation,
            maximum_foot_chain_response,
        )
        if foot_presented_baseline is not None:
            assert (
                maximum_foot_presented_rotation
                > FOOT_ROTATION_RADIANS * 0.5
            ), maximum_foot_presented_rotation

    motion_end_index = len(tick_durations)
    motion_pipeline_end = _pipeline_counters(session)
    assert session.display_rig.force_normal_update
    display_rig_module._transform_modal_active = original_display_modal_probe
    held_foot = foot_bone.matrix_basis.copy()
    held_ik_input = (
        ik_session.input_basis[FOOT_BONE_NAME].copy()
        if ik_session is not None and FOOT_BONE_NAME in ik_session.input_basis
        else None
    )
    maximum_hold_drift = 0.0
    for hold_index in range(HOLD_TICKS):
        tick(foot_bone, check_native_pose=hold_index == HOLD_TICKS - 1)
        if hold_index == 0:
            assert not session.display_rig.force_normal_update
        maximum_hold_drift = max(
            maximum_hold_drift,
            _basis_error(foot_bone.matrix_basis, held_foot),
        )
        if held_ik_input is not None:
            maximum_hold_drift = max(
                maximum_hold_drift,
                _basis_error(ik_session.input_basis[FOOT_BONE_NAME], held_ik_input),
            )
    assert maximum_hold_drift < 2.0e-5, maximum_hold_drift
    final_pipeline_counters = _pipeline_counters(session)

    exit_batch = session.debug_batch
    assert exit_batch is not None
    exit_hide_select = {
        source: bool(source.hide_select)
        for source in (*exit_batch.source_rigids, *exit_batch.source_joints)
    }
    exit_matrices = {}
    original_deactivate_debug_batch = session._deactivate_debug_batch

    def tracked_deactivate_debug_batch():
        if session._debug_batch_exit_pending:
            exit_matrices.update(
                {
                    source: matrix.copy()
                    for source, matrix in (
                        *session._debug_rigid_matrices.items(),
                        *session._debug_joint_matrices.items(),
                    )
                }
            )
        return original_deactivate_debug_batch()

    session._deactivate_debug_batch = tracked_deactivate_debug_batch
    debug_updates_before_exit = session.pose_input.debug_update_count
    bpy.ops.object.mode_set(mode="OBJECT")
    assert armature.mode == "OBJECT"
    tick(foot_bone)
    assert session.debug_batch is None
    assert session.pose_input.debug_update_count == debug_updates_before_exit + 1
    assert exit_matrices
    pose_exit_matrix_error = max(
        _basis_error(source.matrix_world, expected)
        for source, expected in exit_matrices.items()
    )
    assert pose_exit_matrix_error < 2.0e-5, pose_exit_matrix_error
    assert all(
        bool(source.hide_select) == hidden
        for source, hidden in exit_hide_select.items()
    )
    session._deactivate_debug_batch = original_deactivate_debug_batch

    _activate_pose_bone(armature, foot_bone)
    tick(foot_bone)
    assert session.debug_batch is not None
    assert type_zero_debug_checks > 0
    assert not failure_events, failure_events
finally:
    runtime._recover_tick_failure = original_failure_handler
    if "original_display_modal_probe" in globals():
        display_rig_module._transform_modal_active = original_display_modal_probe
    if session is not None and original_prepare_step_from_pose is not None:
        session.prepare_step_from_pose = original_prepare_step_from_pose
    if session is not None and "original_deactivate_debug_batch" in globals():
        session._deactivate_debug_batch = original_deactivate_debug_batch
    if session is not None:
        runtime.stop_preview(root)
    if ik_enabled:
        if original_modal_probe is None:
            del evaluator._transform_modal_active
        else:
            evaluator._transform_modal_active = original_modal_probe
        assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}

motion_tick_durations = tick_durations[motion_start_index:motion_end_index]
motion_input_update_durations = input_update_durations[
    motion_start_index:motion_end_index
]
motion_output_update_durations = output_update_durations[
    motion_start_index:motion_end_index
]
motion_frame_durations = frame_durations[motion_start_index:motion_end_index]
motion_pipeline = _pipeline_counter_delta(
    motion_pipeline_start,
    motion_pipeline_end,
)
hold_pipeline = _pipeline_counter_delta(
    motion_pipeline_end,
    final_pipeline_counters,
)

print(
    "MMD_04_INTERACTION_MATRIX_OK",
    f"solver={solver_target}",
    f"ik={ik_enabled}",
    f"isolated={session.isolated_output_was_active}",
    f"root_ticks={ROOT_MOVE_TICKS}",
    f"foot_ticks={FOOT_ROTATE_TICKS}",
    f"hold_ticks={HOLD_TICKS}",
    f"type0_error={maximum_type_zero_error:.9g}",
    f"dynamic_bone_error={maximum_dynamic_bone_error:.9g}",
    f"native_pose_error={maximum_native_pose_error:.9g}",
    f"root_error={maximum_root_error:.9g}",
    f"foot_error={maximum_foot_error:.9g}",
    f"root_native_move={maximum_root_native_translation:.9g}",
    f"root_presented_move={maximum_root_presented_translation:.9g}",
    f"foot_native_rotation={maximum_foot_native_rotation:.9g}",
    f"foot_presented_rotation={maximum_foot_presented_rotation:.9g}",
    f"foot_chain_response={maximum_foot_chain_response:.9g}",
    f"hold_drift={maximum_hold_drift:.9g}",
    f"pose_exit_matrix_error={pose_exit_matrix_error:.9g}",
    "pose_mode_reentry=ok",
    f"dynamic_changed={dynamic_changed_ticks}",
    f"dynamic_frozen={dynamic_longest_frozen}",
    f"presented_changed={presented_changed_ticks}",
    f"presented_frozen={presented_longest_frozen}",
    f"motion_pipeline={motion_pipeline}",
    f"hold_pipeline={hold_pipeline}",
    f"callback_mean_ms={mean(tick_durations) * 1000.0:.3f}",
    f"callback_median_ms={median(tick_durations) * 1000.0:.3f}",
    f"motion_callback_mean_ms={mean(motion_tick_durations) * 1000.0:.3f}",
    f"motion_callback_median_ms={median(motion_tick_durations) * 1000.0:.3f}",
    f"motion_input_mean_ms={mean(motion_input_update_durations) * 1000.0:.3f}",
    f"motion_input_median_ms={median(motion_input_update_durations) * 1000.0:.3f}",
    f"motion_output_mean_ms={mean(motion_output_update_durations) * 1000.0:.3f}",
    f"motion_output_median_ms={median(motion_output_update_durations) * 1000.0:.3f}",
    f"motion_frame_mean_ms={mean(motion_frame_durations) * 1000.0:.3f}",
    f"motion_frame_median_ms={median(motion_frame_durations) * 1000.0:.3f}",
    f"motion_frame_p90_ms={_percentile(motion_frame_durations, 0.9) * 1000.0:.3f}",
    f"motion_frame_max_ms={max(motion_frame_durations) * 1000.0:.3f}",
    "modal_normals=deferred_and_flushed",
)
