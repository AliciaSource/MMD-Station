import statistics
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
from mmd_station.physics_preview import runtime

mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
assert root.name not in evaluator._SESSIONS
settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = "MMD"
settings.preview_scope = "CURRENT_PROXY"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
assert settings.physics_proxy is not None

session = runtime.start_preview(bpy.context)[0]
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
try:
    for _index in range(10):
        session.tick()
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
    session.tick()
    assert session.pose_input.input_evaluation_count == input_evaluations
    assert session.pose_input.fast_captures == fast_captures + 1
    type_zero_errors = []
    for index, rigid in enumerate(session.rigids):
        if session.rigid_modes[index] != 0 or index not in session.bone_offsets:
            continue
        pose_bone = session.rigid_pose_bones[index]
        expected = (
            session.armature.matrix_world
            @ pose_bone.matrix
            @ session.bone_offsets[index]
        )
        type_zero_errors.append(
            (expected.translation - rigid.matrix_world.translation).length
        )
    assert type_zero_errors
    assert max(type_zero_errors) < 2.0e-5, max(type_zero_errors)

    presentation_start = session.pose_input.output_evaluation_count
    commit_start = session.pose_input.output_commit_count
    debug_start = session.pose_input.debug_update_count
    clean_input_start = session.pose_input.input_evaluation_count
    samples = []
    for _index in range(20):
        started = time.perf_counter()
        session.tick(interactive=True)
        samples.append((time.perf_counter() - started) * 1000.0)
    presentation_count = (
        session.pose_input.output_evaluation_count - presentation_start
    )
    commit_count = session.pose_input.output_commit_count - commit_start
    debug_count = session.pose_input.debug_update_count - debug_start
    assert presentation_count == 0, presentation_count
    assert commit_count == 20, commit_count
    assert debug_count == 20, debug_count
    assert session.pose_input.input_evaluation_count == clean_input_start

    motion_presentation_start = session.pose_input.output_evaluation_count
    motion_commit_start = session.pose_input.output_commit_count
    motion_debug_start = session.pose_input.debug_update_count
    motion_capture_start = session.pose_input.fast_captures
    motion_input_start = session.pose_input.input_evaluation_count
    motion_samples = []
    motion_rigid_errors = []
    for index in range(20):
        root_bone.location = original_location + Vector(
            (0.02 + 0.0005 * (index + 1), 0.0, 0.0)
        )
        bpy.context.view_layer.update()
        started = time.perf_counter()
        session.tick(interactive=True)
        motion_samples.append((time.perf_counter() - started) * 1000.0)
        transforms = session.solver.transforms()[
            session.body_offset:session.body_offset + len(session.rigids)
        ]
        for rigid, transform in zip(session.rigids, transforms):
            position, _rotation = runtime.transform_to_components(transform)
            expected = Vector(position) * session.import_scale
            motion_rigid_errors.append(
                (expected - rigid.matrix_world.translation).length
            )
    motion_presentations = (
        session.pose_input.output_evaluation_count - motion_presentation_start
    )
    motion_commits = session.pose_input.output_commit_count - motion_commit_start
    motion_debugs = session.pose_input.debug_update_count - motion_debug_start
    assert motion_presentations == 0, motion_presentations
    assert motion_commits == 20, motion_commits
    assert motion_debugs == 20, motion_debugs
    assert session.pose_input.fast_captures == motion_capture_start + 20
    assert session.pose_input.input_evaluation_count == motion_input_start
    motion_type_zero_errors = []
    for index, rigid in enumerate(session.rigids):
        if session.rigid_modes[index] != 0 or index not in session.bone_offsets:
            continue
        pose_bone = session.rigid_pose_bones[index]
        expected = (
            session.armature.matrix_world
            @ pose_bone.matrix
            @ session.bone_offsets[index]
        )
        motion_type_zero_errors.append(
            (expected.translation - rigid.matrix_world.translation).length
        )
    assert motion_type_zero_errors
    assert max(motion_type_zero_errors) < 2.0e-5
    assert motion_rigid_errors
    assert max(motion_rigid_errors) < 2.0e-5, max(motion_rigid_errors)
finally:
    runtime.stop_preview(root)

print(
    "MMD_04_PREVIEW_PIPELINE_OK",
    f"cache_hits={session.pose_input.cache_hits}",
    f"fast_captures={session.pose_input.fast_captures}",
    f"commits={commit_count}/20",
    f"sync_evaluations={presentation_count}/20",
    f"debug_updates={debug_count}/20",
    f"type0_error={max(type_zero_errors):.9g}",
    f"mean_ms={statistics.mean(samples):.3f}",
    f"median_ms={statistics.median(samples):.3f}",
    f"motion_mean_ms={statistics.mean(motion_samples):.3f}",
    f"motion_type0_error={max(motion_type_zero_errors):.9g}",
    f"motion_rigid_error={max(motion_rigid_errors):.9g}",
)
