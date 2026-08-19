import math
import struct

from mmd_skirt_proxy_creator.mmd_ik_runtime.coordinates import (
    blender_head_transform,
    blender_position_to_mmd,
    blender_rotation_to_mmd_rows,
    mmd_position_to_blender,
    mmd_row_rotation_to_blender,
)


def bits(values):
    return struct.pack(f"<{len(values)}f", *values)


def flatten(matrix):
    return tuple(value for row in matrix for value in row)


position = (1.25, -2.5, 3.75)
for scale in (0.08, 1.0, 12.5):
    converted = mmd_position_to_blender(position, scale)
    restored = blender_position_to_mmd(converted, scale)
    assert all(math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12) for actual, expected in zip(restored, position))

rotations = (
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ((0.36, 0.48, -0.8), (-0.8, 0.6, 0.0), (0.48, 0.64, 0.6)),
)
for rotation in rotations:
    converted = mmd_row_rotation_to_blender(rotation)
    restored = blender_rotation_to_mmd_rows(converted)
    assert bits(flatten(restored)) == bits(flatten(rotation))

raw = (
    0.0, -1.0, 0.0, 0.0,
    1.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    2.0, 3.0, 4.0, 1.0,
)
converted = blender_head_transform(raw, 0.08)
assert converted[0][3] == 0.16
assert converted[1][3] == 0.32
assert converted[2][3] == 0.24
assert blender_rotation_to_mmd_rows(tuple(tuple(converted[row][column] for column in range(3)) for row in range(3))) == (
    (0.0, -1.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0),
)

print("MMD_COORDINATE_ADAPTER_OK")
