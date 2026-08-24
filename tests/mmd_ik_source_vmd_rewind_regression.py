import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(
    r"D:\MMD\模型\Alicia\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx"
)
VMD = Path(r"D:\MMD\动作\mmd motion\HMVR Teo\m7_teo_0918.vmd")
FORWARD_FRAME = 72.0
REWIND_FRAME = 19.0
TOLERANCE = 2.0e-5
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime.ffi import NativeBoneSolver

mmd_skirt_proxy_creator.register()

from mmd_tools.core.model import FnModel
from mmd_tools.core.pmx.importer import PMXImporter
from mmd_tools.core.vmd.importer import VMDImporter


def _solver_snapshot(solver):
    return tuple(solver.matrix(index) for index in range(solver.count))


def _snapshot_error(actual, expected):
    assert len(actual) == len(expected)
    return max(
        abs(left - right)
        for actual_matrix, expected_matrix in zip(actual, expected)
        for left, right in zip(actual_matrix, expected_matrix)
    )


def _fresh_snapshot(method_name, frame):
    solver = NativeBoneSolver(PMX, VMD)
    try:
        solver.end_live_input()
        getattr(solver, method_name)(frame)
        return solver.names, _solver_snapshot(solver)
    finally:
        solver.close()


def _exercise_rewind(session, session_method, solver_method):
    calls = {"begin": 0, "end": 0, "set": 0, "batch": 0, "reset": 0}
    original_begin = NativeBoneSolver.begin_live_input
    original_end = NativeBoneSolver.end_live_input
    original_set = NativeBoneSolver.set_live_matrix
    original_batch = NativeBoneSolver.set_live_matrices
    original_reset = NativeBoneSolver.reset

    def counted_begin(solver):
        if solver is session.solver:
            calls["begin"] += 1
        return original_begin(solver)

    def counted_end(solver):
        if solver is session.solver:
            calls["end"] += 1
        return original_end(solver)

    def counted_set(solver, index, position, basis_rows):
        if solver is session.solver:
            calls["set"] += 1
        return original_set(solver, index, position, basis_rows)

    def counted_batch(solver, entries):
        if solver is session.solver:
            calls["batch"] += 1
        return original_batch(solver, entries)

    def counted_reset(solver):
        if solver is session.solver:
            calls["reset"] += 1
        return original_reset(solver)

    initial_live_input_frame = session.live_input_frame
    NativeBoneSolver.begin_live_input = counted_begin
    NativeBoneSolver.end_live_input = counted_end
    NativeBoneSolver.set_live_matrix = counted_set
    NativeBoneSolver.set_live_matrices = counted_batch
    NativeBoneSolver.reset = counted_reset
    try:
        method = getattr(session, session_method)
        method(
            FORWARD_FRAME,
            apply_output=False,
            update=False,
            sync_state=False,
        )
        assert session.last_vmd_frame == FORWARD_FRAME
        method(
            REWIND_FRAME,
            apply_output=False,
            update=False,
            sync_state=False,
        )
    finally:
        NativeBoneSolver.begin_live_input = original_begin
        NativeBoneSolver.end_live_input = original_end
        NativeBoneSolver.set_live_matrix = original_set
        NativeBoneSolver.set_live_matrices = original_batch
        NativeBoneSolver.reset = original_reset

    assert calls["begin"] == 0, calls
    assert calls["set"] == 0, calls
    assert calls["batch"] == 0, calls
    assert calls["reset"] == 1, calls
    assert calls["end"] == 2, calls
    assert session.last_vmd_frame == REWIND_FRAME
    assert session.live_input_frame == initial_live_input_frame
    assert session.live_input_dirty
    assert session.source_vmd
    assert not session.pose_override
    assert not session.action_input

    names, expected = _fresh_snapshot(solver_method, REWIND_FRAME)
    assert tuple(session.solver.names) == tuple(names)
    error = _snapshot_error(_solver_snapshot(session.solver), expected)
    assert error <= TOLERANCE, (session_method, error)
    print(
        "MMD_IK_SOURCE_VMD_REWIND_PATH_OK",
        f"path={session_method}",
        f"begin={calls['begin']}",
        f"end={calls['end']}",
        f"set={calls['set']}",
        f"reset={calls['reset']}",
        f"matrix_error={error:.9g}",
    )


assert PMX.is_file(), PMX
assert VMD.is_file(), VMD
PMXImporter().execute(
    filepath=str(PMX),
    types={"MESH", "ARMATURE", "MORPHS"},
    scale=0.08,
    fix_bone_order=False,
)
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
armature = FnModel.find_armature_object(root)
VMDImporter(filepath=str(VMD), scale=0.08, frame_margin=0).assign(armature)
bpy.context.scene.frame_set(41)
bpy.context.view_layer.update()

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root
assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = evaluator._SESSIONS[root.name]
assert session.live
assert session.source_vmd
assert not session.pose_override
assert not session.action_input
assert session.live_input_frame is None

try:
    _exercise_rewind(session, "evaluate_exact", "evaluate")
    session.solver.reset()
    session.last_vmd_frame = None
    session.external_transforms.clear()
    session.live_input_dirty = True
    _exercise_rewind(
        session,
        "evaluate_before_physics",
        "evaluate_before_physics",
    )
finally:
    if root.name in evaluator._SESSIONS:
        bpy.ops.surface_proxy.remove_mmd_ik_runtime()

print("MMD_IK_SOURCE_VMD_REWIND_REGRESSION_OK")
