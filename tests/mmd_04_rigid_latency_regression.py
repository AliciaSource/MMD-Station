import sys
from pathlib import Path

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "合并2"
DT = 1.0 / 60.0
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
assert root.name not in evaluator._SESSIONS
settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
settings.mmd_root = root
for item in bpy.data.objects:
    if getattr(item, "mmd_type", "") == "ROOT":
        item.spx_physics_preview_selected = item is root

session = runtime.start_preview(bpy.context)[0]
wall_seconds = 0.0
try:
    runtime._timer_tick(wall_seconds)
    for _index in range(8):
        wall_seconds += DT
        runtime._timer_tick(wall_seconds)

    root_bone = session.armature.pose.bones["全ての親"]
    original_location = root_bone.location.copy()
    captured_targets = {}
    solver_type = type(session.solver)
    original_set_bone_targets = solver_type.set_bone_targets

    def capture_bone_targets(solver, entries):
        entries = tuple(entries)
        if solver is session.solver:
            for index, target in entries:
                local_index = index - session.body_offset
                captured_targets[local_index] = runtime.transform_to_components(target)[0]
        return original_set_bone_targets(solver, entries)

    solver_type.set_bone_targets = capture_bone_targets
    wall_seconds += DT
    runtime._timer_tick(wall_seconds)
    baseline_targets = dict(captured_targets)
    before_matrices = {
        index: session.debug_matrix_world(rigid).copy()
        for index, rigid in enumerate(session.rigids)
        if int(rigid.mmd_rigid.type) == 0 and index in session.bone_offsets
    }
    captured_targets.clear()
    root_bone.location = original_location + Vector((0.01, 0.0, 0.0))
    debug_updates = session.pose_input.debug_update_count
    session.pose_input.force_debug_update = True
    try:
        # The production tick must evaluate the authored pose before sampling MMD targets.
        wall_seconds += DT
        runtime._timer_tick(wall_seconds)
    finally:
        solver_type.set_bone_targets = original_set_bone_targets
    target_motions = [
        (
            Vector(captured_targets[index]) - Vector(baseline_targets[index])
        ).length
        * session.import_scale
        for index in before_matrices
        if index in captured_targets and index in baseline_targets
    ]
    assert len(target_motions) == len(before_matrices), (
        len(target_motions),
        len(before_matrices),
    )
    assert session.pose_input.debug_update_count == debug_updates + 1
    minimum_target_motion = min(target_motions)
    maximum_target_motion = max(target_motions)
    assert minimum_target_motion > 0.009, minimum_target_motion

    display_matrices = {}
    for index, rigid in enumerate(session.rigids):
        if index not in before_matrices:
            continue
        pose_bone = session.armature.pose.bones[rigid.mmd_rigid.bone]
        bone_pose = (
            session.display_rig.last_pose_targets[pose_bone.name]
            if session.isolated_output_active
            else pose_bone.matrix
        )
        display_matrices[index] = (
            session.armature.matrix_world
            @ bone_pose
            @ session.bone_offsets[index]
        )
    indexed_errors = [
        (
            (
                expected.translation
                - session.debug_matrix_world(session.rigids[index]).translation
            ).length,
            index,
        )
        for index, expected in display_matrices.items()
    ]
    errors = [error for error, _index in indexed_errors]
    authored_motion = max(
        (expected.translation - before_matrices[index].translation).length
        for index, expected in display_matrices.items()
    )
    assert authored_motion > 0.009, authored_motion
    assert errors
    maximum_error = max(errors)
    if maximum_error >= 2.0e-5:
        print(
            "TYPE_ZERO_ERROR_DETAILS",
            [
                (
                    session.rigids[index].name,
                    session.rigids[index].mmd_rigid.bone,
                    error,
                )
                for error, index in sorted(indexed_errors, reverse=True)[:8]
            ],
        )
    assert maximum_error < 2.0e-5, maximum_error
finally:
    runtime.stop_preview(root)

print(
    "MMD_04_RIGID_LATENCY_REGRESSION_OK",
    f"type0={len(errors)}",
    f"target_motion={minimum_target_motion:.9g}-{maximum_target_motion:.9g}",
    f"authored_motion={authored_motion:.9g}",
    f"max_error={maximum_error:.9g}",
)
