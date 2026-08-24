import ctypes
import statistics
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

if not hasattr(bpy.types.Object, "mmd_type"):
    mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime

if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_skirt_proxy_creator.register()


def _raw_solver_output(session):
    chunks = []
    for values in session.world.outputs():
        if not values:
            continue
        chunks.append(
            ctypes.string_at(
                ctypes.addressof(values),
                ctypes.sizeof(values),
            )
        )
    return b"".join(chunks)


def _driver_basis(session):
    pose_bones = session.presentation_armature.pose.bones
    return {
        name: tuple(value for row in pose_bones[name].matrix_basis for value in row)
        for name in session.driver_pose_bones
        if name in pose_bones
    }


def _maximum_basis_error(first, second):
    return max(
        abs(left - right)
        for name in first
        for left, right in zip(first[name], second[name])
    )


def _evaluated_world_vertices(mesh_object):
    evaluated = mesh_object.evaluated_get(bpy.context.evaluated_depsgraph_get())
    matrix_world = evaluated.matrix_world
    return tuple(matrix_world @ vertex.co for vertex in evaluated.data.vertices)


def _type_zero_error(session):
    errors = []
    for index, rigid in enumerate(session.rigids):
        if session.rigid_modes[index] != 0 or index not in session.bone_offsets:
            continue
        pose_bone = session.rigid_pose_bones[index]
        if session.isolated_output_active:
            bone_pose = session.display_rig.last_pose_targets.get(pose_bone.name)
            if bone_pose is None:
                continue
        else:
            bone_pose = pose_bone.matrix
        expected = (
            session.armature.matrix_world
            @ bone_pose
            @ session.bone_offsets[index]
        )
        rigid_world = session.debug_matrix_world(rigid)
        errors.append((expected.translation - rigid_world.translation).length)
    assert errors
    return max(errors)


def _run_target(root, settings, solver_target):
    settings.preview_solver_target = solver_target
    session = runtime.start_preview(bpy.context)[0]
    display_bindings = ()
    if bpy.app.timers.is_registered(runtime._timer_tick):
        bpy.app.timers.unregister(runtime._timer_tick)
    try:
        for _index in range(10):
            session.tick()
        assert session._optimized_input_enabled()
        assert session.pose_input.fast_external_input_safe
        assert session.pose_input.cache_hits >= 5, session.pose_input.cache_hits

        root_bone = session.armature.pose.bones["全ての親"]
        original_location = root_bone.location.copy()
        input_evaluations = session.pose_input.input_evaluation_count
        root_bone.location = original_location + Vector((0.01, 0.0, 0.0))
        session.tick()
        assert session.pose_input.input_evaluation_count == input_evaluations + 1

        input_evaluations = session.pose_input.input_evaluation_count
        fast_captures = session.pose_input.fast_captures
        root_bone.location = original_location + Vector((0.02, 0.0, 0.0))
        bpy.context.view_layer.update()
        assert session.pose_input.external_input_evaluated
        debug_count_before = session.pose_input.debug_update_count
        kinematic_count_before = (
            session.pose_input.kinematic_debug_update_count
        )
        session.pose_input.force_debug_update = True
        session.tick()
        assert session.pose_input.input_evaluation_count == input_evaluations
        assert session.pose_input.fast_captures == fast_captures + 1
        assert session.pose_input.debug_update_count == debug_count_before + 1
        assert (
            session.pose_input.kinematic_debug_update_count
            == kinematic_count_before + 1
        )
        assert _type_zero_error(session) < 2.0e-5

        session.prepare_step()
        comparison_output = session.world.outputs()
        session.apply_step(*comparison_output)
        canonical_basis = _driver_basis(session)
        comparison_mesh = bpy.data.objects["072_衣服"]
        canonical_vertices = _evaluated_world_vertices(comparison_mesh)
        session._force_display_rig_for_tests = True
        assert session._update_display_rig_state(
            interactive=True,
            compatible=session._isolated_runtime_compatible(),
        )
        assert session.isolated_output_active
        assert session.display_rig.bindings
        display_bindings = session.display_rig.binding_names
        session.prepare_step()
        session.apply_step(*comparison_output)
        display_basis = _driver_basis(session)
        display_mesh = session.display_rig.mesh_bindings[0].display_object
        display_vertices = _evaluated_world_vertices(display_mesh)
        display_equivalence_error = _maximum_basis_error(
            canonical_basis,
            display_basis,
        )
        assert display_equivalence_error < 2.0e-6, display_equivalence_error
        vertex_error = max(
            (first - second).length
            for first, second in zip(canonical_vertices, display_vertices)
        )
        evaluated_display_armature = session.display_rig.armature.evaluated_get(
            bpy.context.evaluated_depsgraph_get()
        )
        rig_pose_error = max(
            abs(left - right)
            for name, target in session.display_rig.last_pose_targets.items()
            for left_row, right_row in zip(
                target,
                evaluated_display_armature.pose.bones[name].matrix,
            )
            for left, right in zip(left_row, right_row)
        )
        assert rig_pose_error < 2.0e-6, rig_pose_error
        assert vertex_error < 2.0e-6, vertex_error
        bpy.context.view_layer.update()
        assert not session.pose_input.self_write_pending

        write_start = session.pose_input.output_write_count
        skipped_start = session.pose_input.skipped_output_count
        step_start = session.mmd_step_count
        session.tick(interactive=True)
        for _index in range(3):
            session.tick(interactive=True)
        assert session.pose_input.output_write_count == write_start + 4
        assert session.pose_input.skipped_output_count == skipped_start
        assert session.pose_input.self_write_pending
        if solver_target == "MMD":
            assert session.mmd_step_count == step_start + 4
        bpy.context.view_layer.update()
        assert not session.pose_input.self_write_pending

        presentation_start = session.pose_input.output_write_count
        evaluation_start = session.pose_input.output_evaluation_count
        debug_start = session.pose_input.debug_update_count
        kinematic_start = session.pose_input.kinematic_debug_update_count
        clean_input_start = session.pose_input.input_evaluation_count
        callback_samples = []
        evaluation_samples = []
        for _index in range(20):
            started = time.perf_counter()
            session.tick(interactive=True)
            callback_samples.append((time.perf_counter() - started) * 1000.0)
            started = time.perf_counter()
            bpy.context.view_layer.update()
            evaluation_samples.append((time.perf_counter() - started) * 1000.0)
        assert session.pose_input.output_write_count - presentation_start == 20
        assert session.pose_input.output_evaluation_count - evaluation_start == 20
        debug_updates = session.pose_input.debug_update_count - debug_start
        assert 4 <= debug_updates <= 6, debug_updates
        assert (
            session.pose_input.kinematic_debug_update_count - kinematic_start
            == 20
        )
        assert session.pose_input.input_evaluation_count == clean_input_start

        motion_presentation_start = session.pose_input.output_write_count
        motion_capture_start = session.pose_input.fast_captures
        motion_input_start = session.pose_input.input_evaluation_count
        motion_samples = []
        motion_type_zero_error = 0.0
        motion_debug_checks = 0
        motion_kinematic_checks = 0
        for index in range(20):
            root_bone.location = original_location + Vector(
                (0.02 + 0.0005 * (index + 1), 0.0, 0.0)
            )
            bpy.context.view_layer.update()
            debug_count_before = session.pose_input.debug_update_count
            kinematic_count_before = (
                session.pose_input.kinematic_debug_update_count
            )
            started = time.perf_counter()
            session.tick(interactive=True)
            motion_samples.append((time.perf_counter() - started) * 1000.0)
            if session.pose_input.debug_update_count != debug_count_before:
                motion_debug_checks += 1
            assert (
                session.pose_input.kinematic_debug_update_count
                == kinematic_count_before + 1
            )
            motion_kinematic_checks += 1
            motion_type_zero_error = max(
                motion_type_zero_error,
                _type_zero_error(session),
            )
            assert motion_type_zero_error < 2.0e-5, motion_type_zero_error
            bpy.context.view_layer.update()
        assert session.pose_input.output_write_count - motion_presentation_start == 20
        assert session.pose_input.fast_captures == motion_capture_start + 20
        assert session.pose_input.input_evaluation_count == motion_input_start
        assert 4 <= motion_debug_checks <= 6, motion_debug_checks
        assert motion_kinematic_checks == 20

        root_bone.location = original_location
        session.world.reset()
        for _index in range(12):
            session.tick(interactive=False)
        synchronous_output = _raw_solver_output(session)
        synchronous_basis = _driver_basis(session)

        session.world.reset()
        staged_write_start = session.pose_input.output_write_count
        staged_skip_start = session.pose_input.skipped_output_count
        for _index in range(12):
            session.tick(interactive=True)
        staged_output = _raw_solver_output(session)
        assert staged_output == synchronous_output
        assert session.pose_input.output_write_count == staged_write_start + 12
        assert session.pose_input.skipped_output_count == staged_skip_start
        bpy.context.view_layer.update()
        session.prepare_step()
        session.apply_step(*session.world.outputs())
        staged_basis = _driver_basis(session)
        basis_error = _maximum_basis_error(synchronous_basis, staged_basis)
        assert basis_error < 2.0e-6, basis_error

        return {
            "solver": solver_target,
            "callback_mean_ms": statistics.mean(callback_samples),
            "callback_median_ms": statistics.median(callback_samples),
            "evaluation_mean_ms": statistics.mean(evaluation_samples),
            "motion_mean_ms": statistics.mean(motion_samples),
            "debug_updates": debug_updates,
            "type_zero_error": motion_type_zero_error,
            "basis_error": basis_error,
            "display_equivalence_error": display_equivalence_error,
            "rig_pose_error": rig_pose_error,
            "vertex_error": vertex_error,
            "writes": session.pose_input.output_write_count,
            "skips": session.pose_input.skipped_output_count,
        }
    finally:
        runtime.stop_preview(root)
        source_armature = bpy.data.objects.get(session.armature_name)
        for object_name, modifier_name in display_bindings:
            mesh_object = bpy.data.objects.get(object_name)
            assert mesh_object is not None
            modifier = mesh_object.modifiers.get(modifier_name)
            assert modifier is not None
            assert modifier.object is source_armature
        assert not any(
            bool(obj.get("spx_physics_preview_display_rig", False))
            for obj in bpy.data.objects
        )


root = bpy.data.objects[ROOT_NAME]
assert root.name not in evaluator._SESSIONS
settings = bpy.context.scene.surface_proxy_creator
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
assert settings.physics_proxy is not None

results = [_run_target(root, settings, target) for target in ("MMD", "PMX")]
for result in results:
    print(
        "MMD_04_PREVIEW_PIPELINE_OK",
        f"solver={result['solver']}",
        f"callback_mean_ms={result['callback_mean_ms']:.3f}",
        f"callback_median_ms={result['callback_median_ms']:.3f}",
        f"evaluation_mean_ms={result['evaluation_mean_ms']:.3f}",
        f"motion_mean_ms={result['motion_mean_ms']:.3f}",
        f"debug_updates={result['debug_updates']}/20",
        f"type0_error={result['type_zero_error']:.9g}",
        f"basis_error={result['basis_error']:.9g}",
        f"display_equivalence_error={result['display_equivalence_error']:.9g}",
        f"rig_pose_error={result['rig_pose_error']:.9g}",
        f"vertex_error={result['vertex_error']:.9g}",
        f"writes={result['writes']}",
        f"skips={result['skips']}",
    )
