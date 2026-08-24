MMD_TO_BLENDER_AXIS = (
    (1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 1.0, 0.0),
)


def _transpose3(matrix):
    return tuple(tuple(matrix[column][row] for column in range(3)) for row in range(3))


def _multiply3(left, right):
    return tuple(
        tuple(sum(left[row][index] * right[index][column] for index in range(3)) for column in range(3))
        for row in range(3)
    )


def mmd_position_to_blender(position, scale):
    return (position[0] * scale, position[2] * scale, position[1] * scale)


def blender_position_to_mmd(position, scale):
    inverse_scale = 1.0 / scale
    return (position[0] * inverse_scale, position[2] * inverse_scale, position[1] * inverse_scale)


def mmd_row_rotation_to_blender(matrix):
    return (
        (matrix[0][0] + 0.0, matrix[2][0] + 0.0, matrix[1][0] + 0.0),
        (matrix[0][2] + 0.0, matrix[2][2] + 0.0, matrix[1][2] + 0.0),
        (matrix[0][1] + 0.0, matrix[2][1] + 0.0, matrix[1][1] + 0.0),
    )


def blender_rotation_to_mmd_rows(matrix):
    axis = MMD_TO_BLENDER_AXIS
    return _transpose3(_multiply3(_multiply3(axis, matrix), axis))


def split_mmd_bone_matrix(values):
    if len(values) != 16:
        raise ValueError("MMD bone matrix must contain 16 float32 values")
    rotation = (
        (values[0], values[1], values[2]),
        (values[4], values[5], values[6]),
        (values[8], values[9], values[10]),
    )
    position = (values[12], values[13], values[14])
    return rotation, position


def blender_head_transform(values, scale):
    rotation, position = split_mmd_bone_matrix(values)
    converted_rotation = mmd_row_rotation_to_blender(rotation)
    converted_position = mmd_position_to_blender(position, scale)
    return (
        (*converted_rotation[0], converted_position[0]),
        (*converted_rotation[1], converted_position[1]),
        (*converted_rotation[2], converted_position[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def blender_pose_matrix(values, scale, rest_matrix):
    from mathutils import Matrix

    head_transform = Matrix(blender_head_transform(values, scale))
    rest_orientation = rest_matrix.to_3x3().to_4x4()
    return head_transform @ rest_orientation
