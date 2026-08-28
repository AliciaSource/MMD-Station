from mathutils import Vector


SCALE_TOLERANCE = 1.0e-4
SCALE_EPSILON = 1.0e-8


def _absolute_scale(values):
    return tuple(abs(float(value)) for value in values)


def _is_uniform_scale(values, tolerance=SCALE_TOLERANCE):
    scale = _absolute_scale(values)
    largest = max(scale)
    return (
        largest > SCALE_EPSILON
        and max(scale) - min(scale) <= largest * tolerance
    )


def rigid_world_scale_is_invalid(obj, tolerance=SCALE_TOLERANCE):
    return not _is_uniform_scale(obj.matrix_world.decompose()[2], tolerance)


def rigid_object_scale_needs_bake(obj, tolerance=SCALE_TOLERANCE):
    return any(
        abs(value - 1.0) > tolerance
        for value in _absolute_scale(obj.scale)
    )


def uniform_rigid_world_scale(obj, tolerance=SCALE_TOLERANCE):
    scale = _absolute_scale(obj.matrix_world.decompose()[2])
    if not _is_uniform_scale(scale, tolerance):
        raise RuntimeError(
            f"{obj.name} 使用了非均匀或零缩放，无法保持 MMD 刚体语义"
        )
    return sum(scale) / 3.0


def rigid_scale_repair_plan(obj, tolerance=SCALE_TOLERANCE):
    local_scale = _absolute_scale(obj.scale)
    if min(local_scale) <= SCALE_EPSILON:
        return None, "对象含零缩放，无法推断原始刚体尺寸"

    if obj.parent is not None:
        parent_scale = obj.parent.matrix_world.decompose()[2]
        if not _is_uniform_scale(parent_scale, tolerance):
            return None, "非均匀缩放来自父级，不能只修改当前刚体"

    size = Vector(obj.mmd_rigid.size)
    shape = obj.mmd_rigid.shape
    if shape == "BOX":
        return tuple(size[index] * local_scale[index] for index in range(3)), ""
    if shape == "SPHERE":
        if not _is_uniform_scale(local_scale, tolerance):
            return None, "非均匀缩放已把 Sphere 变成椭球，PMX Sphere 无法精确表示"
        scale = sum(local_scale) / 3.0
        return (size.x * scale, size.y, size.z), ""
    if shape == "CAPSULE":
        radial_scale = (local_scale[0] + local_scale[1]) * 0.5
        if abs(local_scale[0] - local_scale[1]) > radial_scale * tolerance:
            return None, "Capsule 的 X/Y 径向缩放不同，PMX Capsule 无法精确表示"
        radius = size.x * radial_scale
        total_height = (size.y + 2.0 * size.x) * local_scale[2]
        height = total_height - 2.0 * radius
        if height <= SCALE_EPSILON:
            return None, "缩放后的 Capsule 无法还原为有效的 Radius/Height"
        return (radius, height, size.z), ""
    return None, f"不支持修复刚体形状：{shape}"


def bake_rigid_object_scale(obj, tolerance=SCALE_TOLERANCE):
    new_size, reason = rigid_scale_repair_plan(obj, tolerance)
    if new_size is None:
        raise ValueError(reason)
    obj.mmd_rigid.size = new_size
    obj.scale = (1.0, 1.0, 1.0)
    return new_size
