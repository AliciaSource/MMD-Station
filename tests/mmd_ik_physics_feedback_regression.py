import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "鸣潮_达妮娅1.2（blue ver）"
PMX_NAME = "鸣潮_达妮娅1.2（blue ver）.pmx"

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator, lifecycle
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
root["spx_mmd_ik_source_pmx"] = str(Path(root["import_folder"]) / PMX_NAME)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

session = evaluator._SESSIONS[root.name]
armature = runtime._model_armature(root)
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
root.spx_physics_preview_selected = True

exact_target_submissions = []
exact_rigid_target_sequences = []
original_prepare_physics_targets = evaluator.prepare_physics_targets
native_solver_type = type(session.solver)
original_rigid_targets = native_solver_type.rigid_targets
rigid_target_calls = []


def expected_target_bindings(preview_session):
    output = []
    for rigid_index, rigid in enumerate(preview_session.rigids):
        bone_name = rigid.mmd_rigid.bone
        bone_index = session.bone_indices.get(bone_name) if bone_name else None
        if bone_index is None:
            continue
        source = evaluator._mmd_transform(
            preview_session.body_descs[rigid_index].bone_transform
        )
        rest = session.solver.rest_positions[bone_index]
        output.append(
            (
                rigid_index,
                bone_index,
                tuple(
                    evaluator._f32(source[index] - rest[index])
                    for index in range(3)
                ),
                source[3:],
                int(rigid.mmd_rigid.type),
            )
        )
    return tuple(output)


def track_rigid_targets(solver, rigid_indices):
    rigid_indices = tuple(rigid_indices)
    rigid_target_calls.extend(rigid_indices)
    return original_rigid_targets(solver, rigid_indices)


def track_exact_targets(root, preview_session, *args, **kwargs):
    call_start = len(rigid_target_calls)
    submitted = original_prepare_physics_targets(
        root,
        preview_session,
        *args,
        **kwargs,
    )
    exact_target_submissions.append((preview_session.solver_target, submitted))
    expected = tuple(
        session.physics_rigid_indices[rigid_index]
        for rigid_index, _bone_index, _position, _rotation, rigid_mode in (
            session.physics_target_bindings
        )
        if rigid_mode == 0
        and rigid_index < len(session.physics_rigid_indices)
        and session.physics_rigid_indices[rigid_index] is not None
    )
    exact_rigid_target_sequences.append(
        (expected, tuple(rigid_target_calls[call_start:]))
    )
    return submitted


evaluator.prepare_physics_targets = track_exact_targets
native_solver_type.rigid_targets = track_rigid_targets
try:
    for solver_target in ("PMX", "MMD"):
        settings.preview_solver_target = solver_target
        preview_session = runtime.start_preview(bpy.context)[0]
        runtime._timer_tick(0.0)
        feedback_indices = session.physics_rigid_indices
        feedback_target_bindings = session.physics_target_bindings
        assert len(feedback_indices) == len(preview_session.rigids)
        assert any(index is not None for index in feedback_indices)
        assert feedback_target_bindings
        assert feedback_target_bindings == expected_target_bindings(preview_session)
        feedback_complete = session.physics_feedback_complete
        identities = (
            session,
            session.solver,
            preview_session,
            preview_session.world,
            preview_session.world.solver,
        )
        lifecycle._undo_redo_pre(bpy.context.scene)
        assert runtime._RUNTIME_SUSPENDED
        resume_callback = lifecycle._resume_undo_redo_timer
        if bpy.app.timers.is_registered(resume_callback):
            bpy.app.timers.unregister(resume_callback)
        resume_callback()
        assert session.physics_feedback_complete == feedback_complete
        assert session.physics_rigid_indices == feedback_indices
        assert session.physics_target_bindings is not feedback_target_bindings
        assert session.physics_target_bindings == expected_target_bindings(
            preview_session
        )
        assert not session.physics_bindings_dirty
        if hasattr(
            preview_session.solver.library.dll,
            "mmd_solver_get_basis_transforms",
        ):
            basis = preview_session.solver.basis_transforms()
            start = preview_session.body_offset
            expected_bind_positions = tuple(
                (
                    float(item.position.x),
                    float(item.position.y),
                    float(item.position.z),
                )
                for item in basis[start : start + len(preview_session.rigids)]
            )
            assert session.physics_bind_positions == expected_bind_positions
        else:
            assert session.physics_bind_positions == ()
        assert identities[:4] == (
            session,
            session.solver,
            preview_session,
            preview_session.world,
        )
        assert preview_session.solver is preview_session.world.solver
        assert preview_session.solver is not identities[4]
        assert identities[4].handle is None
        bone_name = next(
            name
            for name in sorted(preview_session.bone_drivers)
            if name in session.input_basis
        )
        pose_bone = armature.pose.bones[bone_name]
        pose_bone.matrix_basis = pose_bone.matrix_basis @ Matrix.Translation(
            (0.001, 0.0, 0.0)
        )
        bpy.context.view_layer.update()
        evaluator._depsgraph_update_post(bpy.context.scene)
        runtime._timer_tick(1.0 / 60.0)
        accepted = session.input_basis[bone_name].copy()

        maximum_drift = 0.0
        for tick in range(2, 12):
            runtime._timer_tick(tick / 60.0)
            current = session.input_basis[bone_name]
            maximum_drift = max(
                maximum_drift,
                (current.translation - accepted.translation).length,
                current.to_quaternion().rotation_difference(
                    accepted.to_quaternion()
                ).angle,
            )
        assert maximum_drift < 1.0e-7, (solver_target, bone_name, maximum_drift)
        runtime.stop_preview(root)
finally:
    evaluator.prepare_physics_targets = original_prepare_physics_targets
    native_solver_type.rigid_targets = original_rigid_targets

assert exact_target_submissions
assert {target for target, _submitted in exact_target_submissions} == {"MMD"}
assert min(submitted for _target, submitted in exact_target_submissions) > 0
assert exact_rigid_target_sequences
assert all(expected and actual == expected for expected, actual in exact_rigid_target_sequences)

bpy.ops.surface_proxy.remove_mmd_ik_runtime()
print(
    "MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK",
    f"exact_calls={len(exact_target_submissions)}",
    f"exact_min={min(submitted for _target, submitted in exact_target_submissions)}",
    "undo_recapture=ok",
)
