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

mmd_skirt_proxy_creator.register()

from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import _SESSIONS, start, stop
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import create_runtime
from mmd_skirt_proxy_creator.physics_preview import runtime as physics_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--frames", type=int, default=31)
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
    for candidate in (obj for obj in scene.objects if getattr(obj, "mmd_type", "") == "ROOT"):
        candidate.spx_physics_preview_selected = candidate == root

    start(root, args.pmx, args.vmd, blender_start=1, vmd_start=0)
    preview = physics_runtime.start_preview(bpy.context)[0]
    session = _SESSIONS[root.name]
    oracle = [json.loads(line) for line in Path(args.oracle).read_text(encoding="utf-8").splitlines()]
    assert len(oracle) >= args.frames
    for step_index in range(3 + args.frames * 2):
        frame = max(0.0, (step_index - 3) * 0.5)
        whole = int(frame)
        scene.frame_set(1 + whole, subframe=frame - whole)
        preview.prepare_step()
        assert preview.step_solver()
        preview.apply_step()
        if step_index < 3 or frame != whole:
            continue
        expected = [bytes.fromhex(raw) for _name, raw in oracle[whole]["objects"][0][1]]
        actual = [
            struct.pack("<16f", *session.solver.matrix(index))
            for index in range(session.solver.count)
        ]
        exact = sum(left == right for left, right in zip(actual, expected))
        bits = sum(
            left == right
            for actual_matrix, expected_matrix in zip(actual, expected)
            for left, right in zip(
                struct.unpack("<16I", actual_matrix),
                struct.unpack("<16I", expected_matrix),
            )
        )
        print(f"frame={whole} bones={exact}/{len(expected)} bits={bits}/{len(expected) * 16}")
        assert exact == len(expected)

    physics_runtime.stop_preview(root)
    stop(root)
    print("MMD_RUNTIME_BONE_ORACLE_OK")


main()
