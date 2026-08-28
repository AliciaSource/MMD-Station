import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "鸣潮_达妮娅1.2（blue ver）"
RING_NAME = "202_Skirt_C01_R01"
MOVE = -0.182507
DT = 1.0 / 60.0
SETTLE_STEPS = 60
MOVE_STEPS = 30
POST_STEPS = 180

sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.physics_preview import runtime


def tick(wall_seconds):
    interval = runtime._timer_tick(wall_seconds)
    assert interval is not None


def sample(session, armature, ring):
    ring_bone = armature.pose.bones[ring.mmd_rigid.bone]
    return {
        "ring": ring.matrix_world.translation.copy(),
        "ring_bone": (armature.matrix_world @ ring_bone.matrix).translation.copy(),
        "rigid_matrices": [rigid.matrix_world.copy() for rigid in session.rigids],
        "bone_matrices": [
            armature.matrix_world @ armature.pose.bones[rigid.mmd_rigid.bone].matrix
            if rigid.mmd_rigid.bone in armature.pose.bones
            else None
            for rigid in session.rigids
        ],
    }


def final_mode_errors(session, before, after):
    errors = {0: 0.0, 1: 0.0, 2: 0.0}
    for index, rigid in enumerate(session.rigids):
        before_bone = before["bone_matrices"][index]
        after_bone = after["bone_matrices"][index]
        if before_bone is None or after_bone is None:
            continue
        initial = before_bone.inverted_safe() @ before["rigid_matrices"][index]
        current = after_bone.inverted_safe() @ after["rigid_matrices"][index]
        mode = int(rigid.mmd_rigid.type)
        errors[mode] = max(
            errors[mode],
            (current.translation - initial.translation).length,
        )
    return errors


def assert_type0_targets(session):
    maximum = 0.0
    for index, rigid in enumerate(session.rigids):
        if int(rigid.mmd_rigid.type) != 0 or index not in session.bone_offsets:
            continue
        pose_bone = session.armature.pose.bones.get(rigid.mmd_rigid.bone)
        if pose_bone is None:
            continue
        expected = (
            session.armature.matrix_world @ pose_bone.matrix @ session.bone_offsets[index]
        )
        maximum = max(
            maximum,
            (expected.translation - rigid.matrix_world.translation).length,
        )
    assert maximum < 2.0e-5, maximum


def run_case(session, move):
    wall_seconds = 0.0
    tick(wall_seconds)
    for _index in range(SETTLE_STEPS):
        wall_seconds += DT
        tick(wall_seconds)
    before = sample(session, armature, ring)
    for frame in range(1, MOVE_STEPS + 1):
        move(frame)
        bpy.context.view_layer.update()
        wall_seconds += DT
        tick(wall_seconds)
    for _index in range(POST_STEPS):
        wall_seconds += DT
        tick(wall_seconds)
    after = sample(session, armature, ring)
    initial_relative = before["ring"] - before["ring_bone"]
    ring_error = (
        after["ring"] - after["ring_bone"] - initial_relative
    ).length
    errors = final_mode_errors(session, before, after)
    assert ring_error < 2.0e-3, ring_error
    assert errors[1] < 2.0e-5, errors
    assert errors[2] < 5.0e-3, errors
    assert session.auto_reset_count == 0
    assert_type0_targets(session)


mmd_station.register()
target = os.environ.get("SPX_TEST_SOLVER_TARGET", "PMX")
assert target in {"PMX", "MMD"}
root = bpy.data.objects.get(ROOT_NAME)
if root is None:
    root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")

if os.environ.get("SPX_ENABLE_IK"):
    source = Path(root["import_folder"]) / "鸣潮_达妮娅1.2（blue ver）.pmx"
    root["spx_mmd_ik_source_pmx"] = str(source)
    settings = bpy.context.scene.surface_proxy_creator
    settings.mmd_ik_root = root
    assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}

settings = bpy.context.scene.surface_proxy_creator
settings.preview_solver_target = target
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
root.spx_physics_preview_selected = True
settings.mmd_root = root
armature = runtime._model_armature(root)
ring = next(rigid for rigid in runtime._rigid_objects(root) if RING_NAME in rigid.name)

try:
    base_root = root.matrix_world.copy()
    session = runtime.start_preview(bpy.context)[0]
    if os.environ.get("SPX_ENABLE_IK"):
        from mmd_station.mmd_ik_runtime import evaluator

        assert not evaluator._SESSIONS[root.name].physics_feedback_complete
    run_case(
        session,
        lambda frame: setattr(
            root,
            "matrix_world",
            Matrix.Translation((0.0, MOVE * frame / MOVE_STEPS, 0.0)) @ base_root,
        ),
    )
    runtime.stop_preview(root)

    root_bone = armature.pose.bones["全ての親"]
    base_bone = root_bone.location.copy()
    session = runtime.start_preview(bpy.context)[0]
    run_case(
        session,
        lambda frame: setattr(
            root_bone,
            "location",
            base_bone + Vector((0.0, MOVE * frame / MOVE_STEPS, 0.0)),
        ),
    )
    root_bone.location = base_bone
    runtime.stop_preview(root)
finally:
    runtime.stop_preview(root)
    if os.environ.get("SPX_ENABLE_IK"):
        bpy.ops.surface_proxy.remove_mmd_ik_runtime()

print("MMD_07_ROOT_MOTION_REGRESSION_OK", f"solver={target}", f"ik={bool(os.environ.get('SPX_ENABLE_IK'))}")
