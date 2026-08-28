import argparse
import struct
import sys
from pathlib import Path

import bpy


REPO = Path(__file__).resolve().parents[1]
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
if str(MMD_TOOLS_PARENT) not in sys.path:
    sys.path.insert(0, str(MMD_TOOLS_PARENT))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import mmd_tools

mmd_tools.register()
import mmd_station

mmd_station.register()

from mmd_station.mmd_ik_runtime.coordinates import blender_pose_matrix
from mmd_station.mmd_ik_runtime.evaluator import (
    _bone_map,
    _infer_scale,
    _mute_generated_constraints,
    _restore_constraints,
)
from mmd_station.mmd_ik_runtime.ffi import NativeBoneSolver
from mmd_station.mmd_ik_runtime.runtime import (
    canonical_armature,
    create_runtime,
)
from mmd_station.physics_preview.runtime import PreviewSession, PreviewWorld


def transform_bits(transform):
    return struct.pack(
        "<7f",
        transform.position.x,
        transform.position.y,
        transform.position.z,
        transform.rotation.x,
        transform.rotation.y,
        transform.rotation.z,
        transform.rotation.w,
    )


def run_case(pmx_path, vmd_path, frames, use_runtime):
    bpy.ops.mmd_tools.import_model(
        filepath=pmx_path,
        types={"ARMATURE", "PHYSICS"},
        scale=0.08,
        clean_model=False,
        remove_doubles=False,
        fix_bone_order=False,
        rename_bones=False,
    )
    roots = [
        obj
        for obj in bpy.context.scene.objects
        if getattr(obj, "mmd_type", "") == "ROOT" and "spx_pmx_tested" not in obj
    ]
    root = roots[-1]
    root["spx_pmx_tested"] = True
    root["import_folder"] = str(Path(pmx_path).resolve().parent)
    armature = canonical_armature(root)
    if use_runtime:
        armature, _count, _created = create_runtime(bpy.context, root)

    settings = bpy.context.scene.surface_proxy_creator
    settings.preview_solver_target = "PMX"
    settings.preview_scope = "MODEL"
    settings.preview_gravity = (0.0, 0.0, -9.8)
    settings.preview_update_rigids = False
    settings.preview_substeps = 10
    settings.preview_frequency = 60
    settings.preview_running = True

    with NativeBoneSolver(pmx_path, vmd_path) as bones:
        mapping = _bone_map(armature, bones)
        scale = _infer_scale(mapping, bones)
        muted = _mute_generated_constraints(armature)
        bones.evaluate(0.0)
        for index, pose_bone in enumerate(mapping):
            if pose_bone is not None:
                pose_bone.matrix = blender_pose_matrix(
                    bones.matrix(index), scale, pose_bone.bone.matrix_local
                )
        bpy.context.view_layer.update()

        session = PreviewSession(bpy.context.scene, settings, root)
        world = PreviewWorld(
            ("pmx-runtime-parity", use_runtime),
            session.import_scale,
            "PMX",
            session.library,
        )
        world.add(session)
        world.reset()
        descriptors = (
            tuple(bytes(item) for item in session.body_descs),
            tuple(bytes(item) for item in session.joint_descs),
        )
        output = []
        for frame in range(frames):
            bones.evaluate(float(frame))
            for index, pose_bone in enumerate(mapping):
                if pose_bone is not None:
                    pose_bone.matrix = blender_pose_matrix(
                        bones.matrix(index), scale, pose_bone.bone.matrix_local
                    )
            bpy.context.view_layer.update()
            session.prepare_step()
            world.solver.step(1.0 / 60.0, settings.preview_substeps)
            output.append(tuple(transform_bits(item) for item in world.solver.transforms()))
        world.close()
        session.close(restore=True)
        _restore_constraints(armature, muted)
    return descriptors, tuple(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--frames", type=int, default=13)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

    canonical = run_case(args.pmx, args.vmd, args.frames, False)
    runtime = run_case(args.pmx, args.vmd, args.frames, True)
    assert canonical == runtime
    bodies = len(canonical[1][0]) if canonical[1] else 0
    print(
        "PMX_RUNTIME_BONE_PARITY_OK",
        f"frames={args.frames}",
        f"bodies={bodies}",
    )


main()
