import argparse
import ctypes
import json
import math
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

from mmd_station.mmd_ik_runtime.ffi import NativeBoneSolver
from mmd_station.physics_preview.ffi import Quat, Transform, Vec3
from mmd_station.physics_preview.runtime import PreviewSession, PreviewWorld
def bits(values):
    return struct.pack("<7f", *values)


def mmd_transform(value):
    return (
        float(value.position.x),
        float(value.position.z),
        float(value.position.y),
        -float(value.rotation.x),
        -float(value.rotation.z),
        -float(value.rotation.y),
        float(value.rotation.w),
    )


def f32(value):
    return ctypes.c_float(value).value


def qmul(left, right):
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    value = (
        f32(f32(f32(lw * rx) + f32(lx * rw)) + f32(ly * rz) - f32(lz * ry)),
        f32(f32(f32(lw * ry) - f32(lx * rz)) + f32(ly * rw) + f32(lz * rx)),
        f32(f32(f32(lw * rz) + f32(lx * ry)) - f32(ly * rx) + f32(lz * rw)),
        f32(f32(f32(lw * rw) - f32(lx * rx)) - f32(ly * ry) - f32(lz * rz)),
    )
    length = f32(math.sqrt(f32(sum(f32(item * item) for item in value))))
    return tuple(f32(item / length) for item in value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--frames", type=int, default=13)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

    bpy.ops.mmd_tools.import_model(
        filepath=args.pmx,
        types={"ARMATURE", "PHYSICS"},
        scale=0.08,
        clean_model=False,
        remove_doubles=False,
        fix_bone_order=False,
        rename_bones=False,
    )
    root = next(obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", "") == "ROOT")
    root["import_folder"] = str(Path(args.pmx).resolve().parent)
    settings = bpy.context.scene.surface_proxy_creator
    settings.preview_solver_target = "MMD"
    settings.preview_scope = "MODEL"
    settings.preview_gravity = (0.0, 0.0, -9.8)
    settings.preview_update_rigids = False
    settings.preview_substeps = 10
    settings.preview_frequency = 60
    settings.preview_status = ""
    settings.preview_running = True
    session = PreviewSession(bpy.context.scene, settings, root)
    world = PreviewWorld(("bone-physics-diff",), session.import_scale, "MMD", session.library)
    world.add(session)
    world.reset()
    initial_bodies = world.solver.basis_transforms()

    oracle = json.loads(Path(args.oracle).read_text(encoding="utf-8"))["frames"]
    with NativeBoneSolver(args.pmx, args.vmd) as bones:
        indices = {name: index for index, name in enumerate(bones.names)}
        exact_bodies = []
        for step_index in range(args.frames):
            frame = max(0.0, (step_index - 3) * 0.5)
            if step_index <= 3:
                bones.clear_external_transforms()
            bones.evaluate(frame)
            for rigid_index, rigid in enumerate(session.rigids):
                bone_index = indices.get(rigid.mmd_rigid.bone)
                if bone_index is None:
                    continue
                x, y, z, qx, qy, qz, qw = bones.transform(bone_index)
                source_mmd = mmd_transform(session.body_descs[rigid_index].bone_transform)
                rest_x, rest_y, rest_z = bones.rest_positions[bone_index]
                position = (
                    f32(f32(source_mmd[0] - rest_x) + x),
                    f32(f32(source_mmd[1] - rest_y) + y),
                    f32(f32(source_mmd[2] - rest_z) + z),
                )
                initial = source_mmd[3:]
                delta = (qx, qy, qz, qw)
                total = initial if delta == (0.0, 0.0, 0.0, 1.0) else qmul(delta, initial)
                world.solver.set_bone_target(
                    session.body_offset + rigid_index,
                    Transform(
                        Vec3(position[0], position[2], position[1]),
                        Quat(-total[0], -total[2], -total[1], total[3]),
                    ),
                )
                if step_index > 3 and int(rigid.mmd_rigid.type) == 0:
                    rigid_matrix = bones.rigid_matrix(rigid_index)
                    world.solver.set_body_target_basis(
                        session.body_offset + rigid_index,
                        rigid_matrix[:3],
                        rigid_matrix[3:],
                    )
                if int(rigid.mmd_rigid.type) == 0:
                    rigid_target = bones.rigid_target(rigid_index)
                    bind = initial_bodies[rigid_index].position
                    source = bones.rigid_positions[rigid_index]
                    target_position = tuple(f32(f32(value - source[index]) + rigid_target[index]) for index, value in enumerate((bind.x, bind.y, bind.z)))
                    world.solver.set_body_target_position(
                        session.body_offset + rigid_index,
                        target_position,
                    )
            world.solver.step(1.0 / 60.0, settings.preview_substeps)
            body_transforms = world.solver.transforms()
            body_basis_transforms = world.solver.basis_transforms()
            for rigid_index, (rigid, transform) in enumerate(
                zip(session.rigids, body_basis_transforms)
            ):
                if int(rigid.mmd_rigid.type) == 0:
                    continue
                bones.set_external_rigid_matrix(
                    rigid_index,
                    (transform.position.x, transform.position.y, transform.position.z),
                    tuple(transform.basis_row_major),
                )
            bones.commit_external()
            actual = [mmd_transform(value) for value in world.solver.transforms()]
            expected = oracle[step_index]
            body_matches = sum(bits(a) == bits(e) for a, e in zip(actual, expected))
            float_matches = sum(
                struct.pack("<f", a) == struct.pack("<f", e)
                for actual_body, expected_body in zip(actual, expected)
                for a, e in zip(actual_body, expected_body)
            )
            exact_bodies.append(body_matches)
            print(
                f"frame={step_index} bodies={body_matches}/{len(expected)} "
                f"floats={float_matches}/{len(expected) * 7}"
            )
    world.close()
    session.close(restore=True)
    if exact_bodies != [len(oracle[0])] * args.frames:
        raise SystemExit(1)
    print("MMD_BONE_PHYSICS_DIFF_OK")


main()
