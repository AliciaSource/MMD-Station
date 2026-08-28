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
if str(MMD_TOOLS_PARENT) not in sys.path:
    sys.path.insert(0, str(MMD_TOOLS_PARENT))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import mmd_tools

mmd_tools.register()
import mmd_station

mmd_station.register()

from mmd_station.mmd_ik_runtime.evaluator import start, stop
from mmd_station.mmd_ik_runtime.runtime import create_runtime
from mmd_station.physics_preview import runtime as physics_runtime


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
    root = next(
        obj
        for obj in bpy.context.scene.objects
        if getattr(obj, "mmd_type", "") == "ROOT"
    )
    root["import_folder"] = str(Path(args.pmx).resolve().parent)
    runtime, _count, _created = create_runtime(bpy.context, root)

    scene = bpy.context.scene
    settings = scene.surface_proxy_creator
    settings.mmd_ik_root = root
    settings.mmd_ik_armature = runtime
    settings.preview_solver_target = "MMD"
    settings.preview_scope = "MODEL"
    settings.preview_gravity = (0.0, 0.0, -9.8)
    settings.preview_update_rigids = False
    settings.preview_substeps = 10
    settings.preview_frequency = 60
    for candidate in (
        obj
        for obj in scene.objects
        if getattr(obj, "mmd_type", "") == "ROOT"
    ):
        candidate.spx_physics_preview_selected = candidate == root

    start(root, args.pmx, args.vmd, blender_start=1, vmd_start=0)
    preview = physics_runtime.start_preview(bpy.context)[0]
    oracle = json.loads(Path(args.oracle).read_text(encoding="utf-8"))["frames"]
    assert len(oracle) >= args.frames
    for step_index in range(args.frames):
        frame = max(0.0, (step_index - 3) * 0.5)
        whole = int(frame)
        scene.frame_set(1 + whole, subframe=frame - whole)
        preview.prepare_step()
        assert preview.step_solver()
        raw = preview.solver.transforms()
        local = raw[preview.body_offset : preview.body_offset + len(preview.rigids)]
        actual = [mmd_transform(item) for item in local]
        expected = oracle[step_index]
        body_matches = sum(bits(a) == bits(e) for a, e in zip(actual, expected))
        float_matches = sum(
            struct.pack("<f", a) == struct.pack("<f", e)
            for actual_body, expected_body in zip(actual, expected)
            for a, e in zip(actual_body, expected_body)
        )
        print(
            f"frame={step_index} bodies={body_matches}/{len(expected)} "
            f"floats={float_matches}/{len(expected) * 7}"
        )
        if body_matches != len(expected):
            mismatches = [index for index, (a, e) in enumerate(zip(actual, expected)) if bits(a) != bits(e)]
            print("MISMATCH", [(index, actual[index], expected[index]) for index in mismatches[:3]])
        assert body_matches == len(expected)
        preview.apply_step()

    physics_runtime.stop_preview(root)
    stop(root)
    print("MMD_RUNTIME_PHYSICS_ORACLE_OK")


main()
