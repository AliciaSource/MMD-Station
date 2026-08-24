import importlib.util
import math
import random
import struct
import sys
from pathlib import Path


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MODULE_PATH = (
    REPO
    / "mmd_skirt_proxy_creator"
    / "mmd_ik_runtime"
    / "coordinates.py"
)

spec = importlib.util.spec_from_file_location("spx_mmd_coordinates", MODULE_PATH)
coordinates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinates)


def transpose3(matrix):
    return tuple(
        tuple(matrix[column][row] for column in range(3))
        for row in range(3)
    )


def multiply3(left, right):
    return tuple(
        tuple(
            sum(
                left[row][index] * right[index][column]
                for index in range(3)
            )
            for column in range(3)
        )
        for row in range(3)
    )


def reference_mmd_to_blender(matrix):
    axis = coordinates.MMD_TO_BLENDER_AXIS
    return multiply3(multiply3(axis, transpose3(matrix)), axis)


def reference_blender_to_mmd(matrix):
    axis = coordinates.MMD_TO_BLENDER_AXIS
    return transpose3(multiply3(multiply3(axis, matrix), axis))


def matrix_bits(matrix):
    return b"".join(
        struct.pack("<d", value)
        for row in matrix
        for value in row
    )


minimum_subnormal = float.fromhex("0x0.0000000000001p-1022")
minimum_normal = sys.float_info.min
maximum_finite = sys.float_info.max
boundary_values = (
    0.0,
    -0.0,
    minimum_subnormal,
    -minimum_subnormal,
    minimum_normal,
    -minimum_normal,
    1.0,
    -1.0,
    math.pi,
    -math.e,
    maximum_finite,
    -maximum_finite,
)
cases = []
for offset in range(len(boundary_values)):
    values = tuple(
        boundary_values[(offset + index) % len(boundary_values)]
        for index in range(9)
    )
    cases.append(tuple(values[index:index + 3] for index in range(0, 9, 3)))

generator = random.Random(0x5A17C0DE)
for _index in range(4096):
    values = []
    for _item in range(9):
        exponent = generator.randint(-900, 900)
        values.append(math.ldexp(generator.uniform(-1.0, 1.0), exponent))
    cases.append(tuple(tuple(values[row * 3:row * 3 + 3]) for row in range(3)))

for index, matrix in enumerate(cases):
    expected_forward = reference_mmd_to_blender(matrix)
    actual_forward = coordinates.mmd_row_rotation_to_blender(matrix)
    assert matrix_bits(actual_forward) == matrix_bits(expected_forward), index

    expected_reverse = reference_blender_to_mmd(matrix)
    actual_reverse = coordinates.blender_rotation_to_mmd_rows(matrix)
    assert matrix_bits(actual_reverse) == matrix_bits(expected_reverse), index

    roundtrip = coordinates.blender_rotation_to_mmd_rows(actual_forward)
    expected_roundtrip = reference_blender_to_mmd(expected_forward)
    assert matrix_bits(roundtrip) == matrix_bits(expected_roundtrip), index

print(
    "MMD_COORDINATE_PERMUTATION_OK",
    f"cases={len(cases)}",
    "forward=bit_exact",
    "reverse=bit_exact",
    "roundtrip=bit_exact",
)
