import argparse
import json
import struct
import sys
from pathlib import Path

import bpy


REPO = Path(__file__).resolve().parents[1]
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime.coordinates import (
    blender_position_to_mmd,
    blender_rotation_to_mmd_rows,
)
from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import (
    _SESSIONS,
    _bone_map,
    start,
    stop,
)
from mmd_skirt_proxy_creator.mmd_ik_runtime.ffi import NativeBoneSolver
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import (
    canonical_armature,
    create_runtime,
)
from mmd_skirt_proxy_creator.physics_preview import runtime as physics_runtime
from mmd_tools.core.vmd.importer import VMDImporter

mmd_skirt_proxy_creator.register()


ROTATION_COMPONENTS = (0, 1, 2, 4, 5, 6, 8, 9, 10)
TRANSLATION_COMPONENTS = (12, 13, 14)


def _float_bits(value):
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def _matrix_hex(values):
    return struct.pack("<16f", *values).hex()


def _pose_matrix_mmd(pose_bone, scale):
    rest_orientation = pose_bone.bone.matrix_local.to_3x3().to_4x4()
    head_transform = pose_bone.matrix @ rest_orientation.inverted_safe()
    rotation = blender_rotation_to_mmd_rows(head_transform.to_3x3())
    position = blender_position_to_mmd(head_transform.translation, scale)
    return (
        *rotation[0],
        0.0,
        *rotation[1],
        0.0,
        *rotation[2],
        0.0,
        *position,
        1.0,
    )


def _oracle(path, frames):
    records = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_frame = {int(record["frame"]): record for record in records}
    return {
        frame: {
            name: tuple(struct.unpack("<16f", bytes.fromhex(raw)))
            for name, raw in by_frame[frame]["objects"][0][1]
        }
        for frame in range(frames)
    }


def _compare(actual, expected):
    names = tuple(expected)
    missing = [name for name in names if name not in actual]
    extra = [name for name in actual if name not in expected]
    exact_bones = 0
    exact_floats = 0
    exact_rotations = 0
    exact_translations = 0
    first = None
    max_abs = 0.0
    for name in names:
        if name not in actual:
            continue
        left = actual[name]
        right = expected[name]
        left_bits = tuple(_float_bits(value) for value in left)
        right_bits = tuple(_float_bits(value) for value in right)
        if left_bits == right_bits:
            exact_bones += 1
        exact_floats += sum(a == b for a, b in zip(left_bits, right_bits))
        if all(left_bits[index] == right_bits[index] for index in ROTATION_COMPONENTS):
            exact_rotations += 1
        if all(left_bits[index] == right_bits[index] for index in TRANSLATION_COMPONENTS):
            exact_translations += 1
        for component, (a, b) in enumerate(zip(left_bits, right_bits)):
            max_abs = max(max_abs, abs(float(left[component]) - float(right[component])))
            if first is None and a != b:
                first = {
                    "bone": name,
                    "component": component,
                    "actual_bits": f"{a:08x}",
                    "expected_bits": f"{b:08x}",
                    "actual": float(left[component]),
                    "expected": float(right[component]),
                }
    return {
        "bones": len(names),
        "exact_bones": exact_bones,
        "exact_floats": exact_floats,
        "total_floats": len(names) * 16,
        "exact_rotations": exact_rotations,
        "exact_translations": exact_translations,
        "missing": missing,
        "extra": extra,
        "first_mismatch": first,
        "max_abs_component_error": max_abs,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skeleton", choices=("MMD_TOOLS", "MMD_IK"), required=True)
    parser.add_argument("--solver", choices=("PMX", "MMD"), required=True)
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--startup-steps", type=int, default=3)
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
    root = next(
        obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", "") == "ROOT"
    )
    root["import_folder"] = str(Path(args.pmx).resolve().parent)
    armature = canonical_armature(root)
    scene = bpy.context.scene
    settings = scene.surface_proxy_creator
    settings.preview_solver_target = args.solver
    settings.preview_scope = "MODEL"
    settings.preview_gravity = (0.0, 0.0, -9.8)
    settings.preview_update_rigids = False
    settings.preview_substeps = 10
    settings.preview_frequency = 60
    settings.mmd_ik_root = root
    for candidate in (
        obj for obj in scene.objects if getattr(obj, "mmd_type", "") == "ROOT"
    ):
        candidate.spx_physics_preview_selected = candidate == root

    if args.skeleton == "MMD_IK":
        armature, _count, _created = create_runtime(bpy.context, root)
        settings.mmd_ik_armature = armature
        start(root, args.pmx, args.vmd, blender_start=1, vmd_start=0)
    else:
        VMDImporter(filepath=args.vmd, scale=0.08, frame_margin=0).assign(armature)

    with NativeBoneSolver(args.pmx, args.vmd) as names_solver:
        bone_names = tuple(names_solver.names)
        mapping = _bone_map(armature, names_solver)
    if any(pose_bone is None for pose_bone in mapping):
        raise AssertionError("Not every PMX bone maps to the Blender armature")

    expected = _oracle(args.oracle, args.frames)
    preview = physics_runtime.start_preview(bpy.context)[0]
    output_frames = []
    comparisons = []
    for step_index in range(args.startup_steps + args.frames * 2):
        frame = max(0.0, (step_index - args.startup_steps) * 0.5)
        whole = int(frame)
        scene.frame_set(1 + whole, subframe=frame - whole)
        preview.prepare_step()
        assert preview.step_solver()
        preview.apply_step(*preview.world.outputs())
        if step_index < args.startup_steps or frame != whole or whole >= args.frames:
            continue
        if args.skeleton == "MMD_IK":
            native_session = _SESSIONS[root.name]
            matrices = {
                name: tuple(native_session.solver.matrix(index))
                for index, name in enumerate(native_session.solver.names)
            }
        else:
            matrices = {
                name: _pose_matrix_mmd(pose_bone, preview.import_scale)
                for name, pose_bone in zip(bone_names, mapping)
            }
        comparison = _compare(matrices, expected[whole])
        comparison["frame"] = whole
        comparisons.append(comparison)
        output_frames.append(
            {
                "frame": whole,
                "bones": [
                    {"name": name, "matrix_f32_hex": _matrix_hex(matrices[name])}
                    for name in bone_names
                ],
            }
        )
        print(
            "FOUR_WAY_FRAME",
            f"skeleton={args.skeleton}",
            f"solver={args.solver}",
            f"frame={whole}",
            f"bones={comparison['exact_bones']}/{comparison['bones']}",
            f"rotations={comparison['exact_rotations']}/{comparison['bones']}",
            f"translations={comparison['exact_translations']}/{comparison['bones']}",
            f"floats={comparison['exact_floats']}/{comparison['total_floats']}",
        )

    result = {
        "schema": 1,
        "pmx": str(Path(args.pmx).resolve()),
        "vmd": str(Path(args.vmd).resolve()),
        "oracle": str(Path(args.oracle).resolve()),
        "skeleton": args.skeleton,
        "solver": args.solver,
        "startup_steps": args.startup_steps,
        "frames": output_frames,
        "comparisons": comparisons,
        "bit_exact": all(item["exact_bones"] == item["bones"] for item in comparisons),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    physics_runtime.stop_preview(root)
    if args.skeleton == "MMD_IK":
        stop(root)
    print(
        "ROSSI_FOUR_WAY_BONE_PARITY_COMPLETE",
        f"skeleton={args.skeleton}",
        f"solver={args.solver}",
        f"bit_exact={result['bit_exact']}",
        f"output={output_path}",
    )


main()
