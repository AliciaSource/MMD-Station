import argparse
import json
import math
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

from mmd_tools.core.model import FnModel
from mmd_tools.core.vmd.importer import VMDImporter
from mmd_station.mmd_ik_runtime.coordinates import blender_pose_matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--bone", default="センター")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

    bpy.ops.mmd_tools.import_model(
        filepath=args.pmx,
        types={"ARMATURE"},
        scale=0.08,
        clean_model=False,
        remove_doubles=False,
        fix_bone_order=False,
        rename_bones=False,
    )
    root = next(obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", "") == "ROOT")
    armature = FnModel.find_armature_object(root)
    VMDImporter(filepath=args.vmd, scale=0.08, frame_margin=0).assign(armature)
    pose_bone = next(
        bone
        for bone in armature.pose.bones
        if bone.name == args.bone
        or bone.mmd_bone.name_j == args.bone
        or bone.mmd_bone.name_e == args.bone
    )
    oracle = [json.loads(line) for line in Path(args.oracle).read_text(encoding="utf-8").splitlines()]
    errors = []
    for record in oracle:
        frame = int(record["frame"])
        bpy.context.scene.frame_set(frame + 1)
        expected_raw = next(raw for name, raw in record["objects"][0][1] if name == args.bone)
        import struct

        expected = blender_pose_matrix(
            struct.unpack("<16f", bytes.fromhex(expected_raw)),
            0.08,
            pose_bone.bone.matrix_local,
        )
        delta = pose_bone.matrix.translation - expected.translation
        errors.append(float(delta.length))
        print(f"frame={frame} root_translation_error={delta.length:.12g}")
    rms = math.sqrt(sum(value * value for value in errors) / len(errors))
    print(
        "MMD_TOOLS_ROOT_MOTION_METRIC_OK",
        f"frames={len(errors)}",
        f"max_blender_units={max(errors):.12g}",
        f"rms_blender_units={rms:.12g}",
        f"max_mmd_units={max(errors) / 0.08:.12g}",
    )


main()
