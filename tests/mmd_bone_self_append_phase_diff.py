import argparse
import ctypes
import json
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True)
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--phase-bone", default="自動振動")
    parser.add_argument("--max-phase", type=int, default=4096)
    args = parser.parse_args()

    dll = ctypes.CDLL(args.dll)
    pointer = ctypes.c_void_p
    value = ctypes.c_float
    dll.spx_mmd_bone_create.argtypes = (pointer, ctypes.c_size_t, pointer, ctypes.c_size_t)
    dll.spx_mmd_bone_create.restype = pointer
    dll.spx_mmd_bone_count.argtypes = (pointer,)
    dll.spx_mmd_bone_count.restype = ctypes.c_uint32
    dll.spx_mmd_bone_evaluate.argtypes = (
        pointer,
        value,
        ctypes.POINTER(value),
        ctypes.c_size_t,
    )
    dll.spx_mmd_bone_name_utf8.argtypes = (
        pointer,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_size_t,
    )
    dll.spx_mmd_bone_destroy.argtypes = (pointer,)

    pmx = Path(args.pmx).read_bytes()
    vmd = Path(args.vmd).read_bytes()
    pmx_buffer = ctypes.create_string_buffer(pmx)
    vmd_buffer = ctypes.create_string_buffer(vmd)
    instance = dll.spx_mmd_bone_create(pmx_buffer, len(pmx), vmd_buffer, len(vmd))
    assert instance
    try:
        count = int(dll.spx_mmd_bone_count(instance))
        output = (value * (count * 16))()
        names = []
        for index in range(count):
            buffer = ctypes.create_string_buffer(1024)
            dll.spx_mmd_bone_name_utf8(instance, index, buffer, len(buffer))
            names.append(buffer.value.decode("utf-8"))
        phase_index = names.index(args.phase_bone)
        oracle = [
            [bytes.fromhex(raw) for _name, raw in record["objects"][0][1]]
            for record in (
                json.loads(line)
                for line in Path(args.oracle).read_text(encoding="utf-8").splitlines()
            )
        ]

        phase = None
        for candidate in range(1, args.max_phase + 1):
            dll.spx_mmd_bone_evaluate(instance, value(0), output, len(output))
            start = phase_index * 16
            actual = struct.pack("<16f", *output[start : start + 16])
            if actual == oracle[0][phase_index]:
                phase = candidate
                break
        assert phase is not None

        first_exact = sum(
            struct.pack("<16f", *output[index * 16 : index * 16 + 16]) == oracle[0][index]
            for index in range(count)
        )
        for frame in range(1, len(oracle)):
            dll.spx_mmd_bone_evaluate(instance, value(frame), output, len(output))
            mismatches = [
                index
                for index in range(count)
                if struct.pack("<16f", *output[index * 16 : index * 16 + 16])
                != oracle[frame][index]
            ]
            assert not mismatches, f"frame {frame}: first mismatch {mismatches[0]}"
        print(
            "MMD_SELF_APPEND_PHASE_DIFF_OK",
            f"phase={phase}",
            f"frame0_exact={first_exact}/{count}",
            f"transition_frames={len(oracle) - 1}",
            f"bones={count}",
        )
    finally:
        dll.spx_mmd_bone_destroy(instance)


main()
