import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator, physics_bridge
from mmd_skirt_proxy_creator.physics_preview import runtime
from mmd_skirt_proxy_creator.physics_preview.ffi import BoneTargetPmxEulerBatch

mmd_skirt_proxy_creator.register()


def _maximum_matrix_error(first, second, pose_bones):
    return max(
        abs(left - right)
        for pose_bone in pose_bones
        for first_row, second_row in zip(
            first[pose_bone.name],
            second[pose_bone.name],
        )
        for left, right in zip(first_row, second_row)
    )


root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.mmd_ik_root = root
settings.preview_solver_target = "MMD"
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
source = Path(root.get("spx_mmd_ik_source_pmx", ""))
if not source.is_file():
    source = Path(root["import_folder"]) / "合并2.pmx"
    root["spx_mmd_ik_source_pmx"] = str(source)
assert source.is_file(), source
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

preview = None
constraint = None
try:
    preview = runtime.start_preview(bpy.context)[0]
    preview._force_display_rig_for_tests = True
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    for _index in range(6):
        preview.tick(interactive=True)
        bpy.context.view_layer.update()
    native = evaluator._SESSIONS[root.name]
    assert preview.isolated_output_active
    assert preview._native_pose_provider_compatible
    identity = (preview, preview.world, preview.solver, native, native.solver)
    reference_positions = []
    reference_bases = []
    inverse_scale = 1.0 / native.scale
    for _index, pose_bone, rest_inverse in native.direct_live_bindings:
        head_transform = pose_bone.matrix @ rest_inverse
        position = head_transform.translation
        reference_positions.extend(
            (
                position.x * inverse_scale,
                position.z * inverse_scale,
                position.y * inverse_scale,
            )
        )
        reference_bases.extend(
            value
            for row in evaluator._live_rotation_to_mmd_rows(head_transform)
            for value in row
        )
    direct_buffers = evaluator._direct_live_matrix_buffers(native)
    direct_buffer_error = max(
        max(
            abs(first - second)
            for first, second in zip(reference_positions, direct_buffers[0])
        ),
        max(
            abs(first - second)
            for first, second in zip(reference_bases, direct_buffers[1])
        ),
    )
    assert direct_buffer_error < 2.0e-6, direct_buffer_error
    repeated_direct_buffers = evaluator._direct_live_matrix_buffers(native)
    assert repeated_direct_buffers[0] is direct_buffers[0]
    assert repeated_direct_buffers[1] is direct_buffers[1]

    submit_count = [0]
    submitted_body_indices = []
    original_submit = runtime.PreviewSession._submit_pose_targets
    original_set_bone_targets = preview.solver.set_bone_targets
    original_euler_batch_submit = BoneTargetPmxEulerBatch.submit

    def tracked_submit(session, pose_matrices=None, **kwargs):
        submit_count[0] += 1
        return original_submit(session, pose_matrices, **kwargs)

    def tracked_set_bone_targets(entries):
        entries = tuple(entries)
        submitted_body_indices.extend(index for index, _target in entries)
        return original_set_bone_targets(entries)

    def tracked_euler_batch_submit(batch):
        submitted_body_indices.extend(batch.index_values)
        return original_euler_batch_submit(batch)

    runtime.PreviewSession._submit_pose_targets = tracked_submit
    preview.solver.set_bone_targets = tracked_set_bone_targets
    BoneTargetPmxEulerBatch.submit = tracked_euler_batch_submit
    try:
        preview.tick(interactive=True)
    finally:
        runtime.PreviewSession._submit_pose_targets = original_submit
        BoneTargetPmxEulerBatch.submit = original_euler_batch_submit
        del preview.solver.set_bone_targets
    expected_target_indices = {
        preview.body_offset + index
        for index, pose_bone in enumerate(preview.rigid_pose_bones)
        if pose_bone is not None and index in preview.bone_offsets
    }
    assert submit_count[0] == 1, submit_count[0]
    assert expected_target_indices <= set(submitted_body_indices), (
        len(expected_target_indices),
        len(set(submitted_body_indices)),
        sorted(expected_target_indices - set(submitted_body_indices))[:10],
    )
    assert len(submitted_body_indices) == len(expected_target_indices)

    display = preview.display_rig
    display_names = {pose_bone.name for pose_bone in display.source_pose_bones}
    post_candidate = next(
        pose_bone
        for pose_bone in preview.pose_input.ordered_input_pose_bones
        if pose_bone.name in display_names
        and pose_bone.name in native.mapped_pose_names
        and pose_bone.name not in preview.bone_drivers
    )
    original_resolved_output_pose = native.resolved_output_pose
    original_feedback = evaluator.submit_physics_feedback
    original_apply_step = physics_bridge._ORIGINAL_APPLY_STEP
    original_display_apply = display.apply_resolved_pose
    feedback_phase = [False]
    expected_post_pose = []
    prepared_post_pose = []
    presentation_calls = []

    def synthetic_feedback(*_args, **_kwargs):
        feedback_phase[0] = True
        return 1

    def tracked_resolved_output_pose(*args, **kwargs):
        resolved_pose = original_resolved_output_pose(*args, **kwargs)
        if not feedback_phase[0]:
            return resolved_pose
        resolved_pose = dict(resolved_pose)
        resolved_pose[post_candidate.name] = (
            resolved_pose[post_candidate.name]
            @ Matrix.Translation((0.0007, 0.0, 0.0))
        )
        expected_post_pose.append(resolved_pose[post_candidate.name].copy())
        return resolved_pose

    def tracked_apply_step(session, *args, **kwargs):
        prepared_post_pose.append(
            session.pending_animation_pose[post_candidate.name].copy()
        )
        return original_apply_step(session, *args, **kwargs)

    def tracked_display_apply(pose_targets):
        presentation_calls.append(pose_targets)
        return original_display_apply(pose_targets)

    evaluator.submit_physics_feedback = synthetic_feedback
    native.resolved_output_pose = tracked_resolved_output_pose
    physics_bridge._ORIGINAL_APPLY_STEP = tracked_apply_step
    display.apply_resolved_pose = tracked_display_apply
    try:
        preview.tick(interactive=True)
    finally:
        evaluator.submit_physics_feedback = original_feedback
        del native.resolved_output_pose
        physics_bridge._ORIGINAL_APPLY_STEP = original_apply_step
        del display.apply_resolved_pose
    assert len(expected_post_pose) == 1
    assert len(prepared_post_pose) == 1
    assert len(presentation_calls) == 1
    post_physics_error = max(
        abs(left - right)
        for expected_row, prepared_row in zip(
            expected_post_pose[0],
            prepared_post_pose[0],
        )
        for left, right in zip(expected_row, prepared_row)
    )
    assert post_physics_error < 1.0e-7, post_physics_error

    ordered = preview.direct_input_pose_bones()
    nondefault_inheritance = sum(
        pose_bone.bone.inherit_scale != "FULL"
        or not pose_bone.bone.use_inherit_rotation
        for pose_bone in ordered
    )
    assert nondefault_inheritance > 0
    basis_overrides = {
        name: matrix
        for name, matrix in preview.saved_basis.items()
        if name not in native.mapped_pose_names and name in preview.driver_pose_bones
    }
    operation_center = preview.armature.pose.bones.get("操作中心")
    matrix_overrides = (
        {operation_center.name: operation_center.matrix.copy()}
        if operation_center is not None
        else None
    )
    resolved = native.resolved_output_pose(
        preview.armature,
        ordered,
        basis_overrides=basis_overrides,
        matrix_overrides=matrix_overrides,
    )
    saved_basis = {
        pose_bone.name: pose_bone.matrix_basis.copy()
        for pose_bone in preview.armature.pose.bones
    }
    native._apply_output(
        preview.armature,
        preview.scene,
        update=False,
        sync_state=False,
    )
    if operation_center is not None:
        operation_center.matrix = matrix_overrides[operation_center.name]
    for name, matrix in basis_overrides.items():
        preview.armature.pose.bones[name].matrix_basis = matrix
    reference = evaluator._raw_pose_matrices(preview.armature)
    resolved_error = _maximum_matrix_error(resolved, reference, ordered)
    assert resolved_error < 2.0e-5, resolved_error
    for name, matrix in saved_basis.items():
        preview.armature.pose.bones[name].matrix_basis = matrix
    preview.armature.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()

    unmapped = sum(
        pose_bone.name not in native.mapped_pose_names for pose_bone in ordered
    )
    assert unmapped > 0
    constraint = preview.armature.constraints.new("LIMIT_LOCATION")
    constraint.use_min_x = True
    constraint.min_x = preview.armature.location.x + 0.25
    assert native.has_blender_overrides()
    preview.tick(interactive=True)
    bpy.context.view_layer.update()
    assert not preview._native_pose_provider_compatible
    assert not preview.isolated_output_active
    assert identity == (preview, preview.world, preview.solver, native, native.solver)

    preview.armature.constraints.remove(constraint)
    constraint = None
    preview.tick(interactive=True)
    bpy.context.view_layer.update()
    assert preview._native_pose_provider_compatible
    assert preview.isolated_output_active
    assert identity == (preview, preview.world, preview.solver, native, native.solver)
    print(
        "MMD_04_NATIVE_POSE_PROVIDER_REGRESSION_OK",
        f"bones={len(ordered)}",
        f"unmapped={unmapped}",
        f"nondefault_inheritance={nondefault_inheritance}",
        f"resolved_error={resolved_error:.9g}",
        f"direct_buffer_error={direct_buffer_error:.9g}",
        "constraint_fallback=ok",
        "reactivation=ok",
        "exact_targets=complete_without_duplicates",
        "post_physics_single_present=ok",
    )
finally:
    if constraint is not None and preview is not None:
        preview.armature.constraints.remove(constraint)
    if preview is not None:
        runtime.stop_preview(root)
    if root.name in evaluator._SESSIONS:
        bpy.ops.surface_proxy.remove_mmd_ik_runtime()
