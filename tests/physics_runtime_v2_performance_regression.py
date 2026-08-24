import hashlib
import os
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
TARGET = os.environ.get("SPX_TEST_SOLVER", "PMX")
DEBUG_OBJECTS = os.environ.get("SPX_TEST_DEBUG", "0") == "1"
SCOPE = os.environ.get("SPX_TEST_SCOPE", "CURRENT_PROXY")
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

if not hasattr(bpy.types.Object, "mmd_type"):
    mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime

if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_skirt_proxy_creator.register()


def pose_digest(session):
    digest = hashlib.sha256()
    for name in sorted(session.driver_pose_bones):
        pose_bone = session.driver_pose_bones[name]
        if pose_bone is None:
            continue
        for row in pose_bone.matrix_basis:
            for value in row:
                digest.update(float(value).hex().encode("ascii"))
    return digest.hexdigest()


def percentile_95(values):
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * 0.95)]


root = bpy.data.objects[ROOT_NAME]
assert root.name not in evaluator._SESSIONS
settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = TARGET
settings.preview_scope = SCOPE
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = DEBUG_OBJECTS
settings.mmd_root = root
if SCOPE == "CURRENT_PROXY":
    assert settings.physics_proxy is not None
else:
    root.spx_physics_preview_selected = True

session = runtime.start_preview(bpy.context)[0]
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)

try:
    for _index in range(10):
        session.tick(interactive=True)

    assert session.pose_input.native_input_active is False
    assert session._optimized_input_enabled(), TARGET
    assert session.pose_input.cache_hits > 0, TARGET

    root_bone = session.armature.pose.bones["全ての親"]
    original_location = root_bone.location.copy()
    input_evaluations = session.pose_input.input_evaluation_count
    fast_captures = session.pose_input.fast_captures
    presentation_start = session.pose_input.output_evaluation_count
    commit_start = session.pose_input.output_commit_count
    debug_start = session.pose_input.debug_update_count
    phase_samples = {"prepare": [], "step": [], "outputs": [], "apply": []}
    original_prepare_step = session.prepare_step
    original_step_solver = session.step_solver
    original_outputs = session.world.outputs
    original_apply_step = session.apply_step

    def timed_prepare_step():
        started = time.perf_counter()
        try:
            return original_prepare_step()
        finally:
            phase_samples["prepare"].append((time.perf_counter() - started) * 1000.0)

    def timed_step_solver():
        started = time.perf_counter()
        try:
            return original_step_solver()
        finally:
            phase_samples["step"].append((time.perf_counter() - started) * 1000.0)

    def timed_outputs():
        started = time.perf_counter()
        try:
            return original_outputs()
        finally:
            phase_samples["outputs"].append((time.perf_counter() - started) * 1000.0)

    def timed_apply_step(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_apply_step(*args, **kwargs)
        finally:
            phase_samples["apply"].append((time.perf_counter() - started) * 1000.0)

    session.prepare_step = timed_prepare_step
    session.step_solver = timed_step_solver
    session.world.outputs = timed_outputs
    session.apply_step = timed_apply_step
    samples = []
    edit_samples = []
    rigid_sync_errors = []
    for index in range(20):
        edit_started = time.perf_counter()
        root_bone.location = original_location + Vector(
            (0.0005 * (index + 1), 0.0, 0.0)
        )
        bpy.context.view_layer.update()
        edit_samples.append((time.perf_counter() - edit_started) * 1000.0)
        started = time.perf_counter()
        session.tick(interactive=True)
        samples.append((time.perf_counter() - started) * 1000.0)
        if DEBUG_OBJECTS:
            transforms = session.solver.transforms()[
                session.body_offset:session.body_offset + len(session.rigids)
            ]
            for rigid, transform in zip(session.rigids, transforms):
                position, _rotation = runtime.transform_to_components(transform)
                expected = Vector(position) * session.import_scale
                rigid_sync_errors.append(
                    (expected - rigid.matrix_world.translation).length
                )

    assert session.pose_input.input_evaluation_count == input_evaluations
    assert session.pose_input.fast_captures == fast_captures + 20
    presentations = session.pose_input.output_evaluation_count - presentation_start
    commits = session.pose_input.output_commit_count - commit_start
    debug_updates = session.pose_input.debug_update_count - debug_start
    assert commits == 20, commits
    if DEBUG_OBJECTS:
        assert debug_updates == 20, debug_updates
        assert rigid_sync_errors
        assert max(rigid_sync_errors) < 2.0e-5, max(rigid_sync_errors)
    else:
        assert debug_updates == 0, debug_updates
    assert presentations == 0, presentations

    result_digest = pose_digest(session)
    bpy.context.view_layer.update()
    tick_median_limit = 8.0 if SCOPE == "CURRENT_PROXY" else 14.0
    tick_p95_limit = (
        18.0
        if SCOPE == "CURRENT_PROXY" and DEBUG_OBJECTS
        else 16.7
        if SCOPE == "CURRENT_PROXY"
        else 25.0
    )
    assert statistics.median(samples) < tick_median_limit, statistics.median(samples)
    assert percentile_95(samples) < tick_p95_limit, percentile_95(samples)

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
    if DEBUG_OBJECTS:
        assert type_zero_errors
        assert max(type_zero_errors) < 2.1e-3, max(type_zero_errors)
finally:
    runtime.stop_preview(root)

print(
    "PHYSICS_RUNTIME_V2_PERFORMANCE_OK",
    f"target={TARGET}",
    f"scope={SCOPE}",
    f"debug={int(DEBUG_OBJECTS)}",
    f"cache_hits={session.pose_input.cache_hits}",
    f"fast_captures={session.pose_input.fast_captures}",
    f"commits={commits}/20",
    f"sync_evaluations={presentations}/20",
    f"debug_updates={debug_updates}/20",
    f"rigid_sync_error={max(rigid_sync_errors) if rigid_sync_errors else 0.0:.9g}",
    f"edit_median_ms={statistics.median(edit_samples):.3f}",
    f"tick_median_ms={statistics.median(samples):.3f}",
    f"tick_p95_ms={percentile_95(samples):.3f}",
    f"combined_median_ms={statistics.median([a + b for a, b in zip(edit_samples, samples)]):.3f}",
    f"prepare_ms={statistics.median(phase_samples['prepare']):.3f}",
    f"step_ms={statistics.median(phase_samples['step']):.3f}",
    f"outputs_ms={statistics.median(phase_samples['outputs']):.3f}",
    f"apply_ms={statistics.median(phase_samples['apply']):.3f}",
    f"pose_sha256={result_digest}",
)
