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
    parser.add_argument("--max-phase", type=int, default=4096)
    args = parser.parse_args()

    oracle = [json.loads(line) for line in Path(args.oracle).read_text(encoding="utf-8").splitlines()]
    expected = [[bytes.fromhex(raw) for _name, raw in item["objects"][0][1]] for item in oracle]
    dll = ctypes.CDLL(args.dll)
    dll.spx_mmd_bone_create.argtypes = (
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
    )
    dll.spx_mmd_bone_create.restype = ctypes.c_void_p
    dll.spx_mmd_bone_count.argtypes = (ctypes.c_void_p,)
    dll.spx_mmd_bone_count.restype = ctypes.c_uint32
    dll.spx_mmd_bone_evaluate.argtypes = (
        ctypes.c_void_p,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
    )
    dll.spx_mmd_bone_destroy.argtypes = (ctypes.c_void_p,)

    pmx = Path(args.pmx).read_bytes()
    vmd = Path(args.vmd).read_bytes()
    pmx_buffer = ctypes.create_string_buffer(pmx)
    vmd_buffer = ctypes.create_string_buffer(vmd)
    instance = dll.spx_mmd_bone_create(pmx_buffer, len(pmx), vmd_buffer, len(vmd))
    if not instance:
        raise RuntimeError("native solver creation failed")
    try:
        count = dll.spx_mmd_bone_count(instance)
        output = (ctypes.c_float * (count * 16))()

        def matrix(index):
            start = index * 16
            return struct.pack("<16f", *output[start : start + 16])

        phase = None
        for tick in range(args.max_phase):
            dll.spx_mmd_bone_evaluate(instance, float(tick), output, len(output))
            if all(matrix(index) == expected[0][index] for index in range(count)):
                phase = tick
                break
        if phase is None:
            raise AssertionError(f"no exact oracle phase in {args.max_phase} evaluations")
        for oracle_index in range(1, len(expected)):
            dll.spx_mmd_bone_evaluate(instance, float(phase + oracle_index), output, len(output))
            mismatches = [index for index in range(count) if matrix(index) != expected[oracle_index][index]]
            if mismatches:
                raise AssertionError(
                    f"frame {oracle_index}: {len(mismatches)} matrix mismatches, first={mismatches[0]}"
                )
        print(
            "MMD_BONE_PHASE_DIFF_OK",
            f"phase={phase}",
            f"frames={len(expected)}",
            f"bones={count}",
        )
    finally:
        dll.spx_mmd_bone_destroy(instance)


if __name__ == "__main__":
    main()
