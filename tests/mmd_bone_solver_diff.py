import argparse
import ctypes
import json
import struct
from pathlib import Path


def load_oracle(path, frame):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item["frame"] == frame:
                return [(name, bytes.fromhex(raw)) for name, raw in item["objects"][0][1]]
    raise RuntimeError(f"oracle frame {frame} missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True)
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--vmd", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--focus")
    args = parser.parse_args()
    dll = ctypes.CDLL(args.dll)
    dll.spx_mmd_bone_create.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    dll.spx_mmd_bone_create.restype = ctypes.c_void_p
    dll.spx_mmd_bone_count.argtypes = [ctypes.c_void_p]
    dll.spx_mmd_bone_count.restype = ctypes.c_uint32
    dll.spx_mmd_bone_evaluate.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
    dll.spx_mmd_bone_evaluate.restype = ctypes.c_int
    dll.spx_mmd_bone_name_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
    dll.spx_mmd_bone_name_utf8.restype = ctypes.c_int
    dll.spx_mmd_bone_last_error.restype = ctypes.c_char_p
    pmx = Path(args.pmx).read_bytes()
    vmd = Path(args.vmd).read_bytes()
    pmx_buf = ctypes.create_string_buffer(pmx)
    vmd_buf = ctypes.create_string_buffer(vmd)
    instance = dll.spx_mmd_bone_create(pmx_buf, len(pmx), vmd_buf, len(vmd))
    if not instance:
        raise RuntimeError(dll.spx_mmd_bone_last_error().decode())
    try:
        count = dll.spx_mmd_bone_count(instance)
        values = (ctypes.c_float * (count * 16))()
        for frame in range(args.frame + 1):
            if not dll.spx_mmd_bone_evaluate(instance, frame, values, len(values)):
                raise RuntimeError(dll.spx_mmd_bone_last_error().decode())
        oracle = load_oracle(args.oracle, args.frame)
        exact = 0
        exact_matrices = 0
        worst = (0.0, -1, "", -1, 0.0, 0.0)
        first = None
        diff_floats = 0
        per_bone = []
        focus = None
        for i in range(min(count, len(oracle))):
            name_buf = ctypes.create_string_buffer(1024)
            dll.spx_mmd_bone_name_utf8(instance, i, name_buf, len(name_buf))
            name = name_buf.value.decode("utf-8")
            expected_name, expected_raw = oracle[i]
            actual_raw = struct.pack("<16f", *values[i * 16:(i + 1) * 16])
            if args.focus and name == args.focus:
                focus = {"index": i, "exact": actual_raw == expected_raw, "actual": struct.unpack("<16f", actual_raw), "expected": struct.unpack("<16f", expected_raw)}
            if actual_raw == expected_raw:
                exact_matrices += 1
            if actual_raw == expected_raw and name == expected_name:
                exact += 1
                continue
            ev = struct.unpack("<16f", expected_raw)
            av = struct.unpack("<16f", actual_raw)
            bone_max = max(abs(a - e) for a, e in zip(av, ev))
            per_bone.append((bone_max, i, name))
            for j, (a, e) in enumerate(zip(av, ev)):
                if struct.pack("<f", a) != struct.pack("<f", e):
                    diff_floats += 1
                    d = abs(a - e)
                    if first is None:
                        first = (i, name, expected_name, j, a, e)
                    if d > worst[0]:
                        worst = (d, i, name, j, a, e)
        per_bone.sort(reverse=True)
        print(json.dumps({"frame": args.frame, "bones": count, "oracle_bones": len(oracle), "exact_bones": exact, "exact_matrices": exact_matrices, "diff_floats": diff_floats, "first": first, "worst": worst, "worst_bones": per_bone[:10], "focus": focus}, ensure_ascii=False))
    finally:
        dll.spx_mmd_bone_destroy.argtypes = [ctypes.c_void_p]
        dll.spx_mmd_bone_destroy(instance)


if __name__ == "__main__":
    main()
