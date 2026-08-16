import importlib
import math
import os
import re
import uuid

import bpy
from bl_operators.presets import AddPresetBase
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Menu, Operator, PropertyGroup, UIList
from mathutils import Euler, Matrix, Vector

from .bone_physics_creator import draw as draw_bone_physics_creator
from .core import ProxyBuildError, proxy_bone_name
from .mmd_ordering import draw as draw_mmd_ordering
from .mirror_physics import CLASSES as MIRROR_PHYSICS_CLASSES, draw_mirror_tools


PHYSICS_SCHEMA = 1

PHYSICS_SETTING_NAMES = (
    "rigid_shape",
    "top_rigid_type",
    "body_rigid_type",
    "rigid_radius_ratio",
    "rigid_length_ratio",
    "rigid_depth_ratio",
    "mass",
    "friction",
    "restitution",
    "linear_damping",
    "angular_damping",
    "collision_group_number",
    "collision_group_mask",
    "create_horizontal_joints",
    "limit_linear_lower",
    "limit_linear_upper",
    "limit_angular_lower",
    "limit_angular_upper",
    "spring_linear",
    "spring_angular",
    "horizontal_limit_linear_lower",
    "horizontal_limit_linear_upper",
    "horizontal_limit_angular_lower",
    "horizontal_limit_angular_upper",
    "horizontal_spring_linear",
    "horizontal_spring_angular",
)

RIGID_INTERPOLATED_NAMES = (
    "rigid_radius_ratio",
    "rigid_length_ratio",
    "rigid_depth_ratio",
    "mass",
    "linear_damping",
    "angular_damping",
    "restitution",
    "friction",
)

JOINT_VECTOR_NAMES = (
    "limit_linear_lower",
    "limit_linear_upper",
    "limit_angular_lower",
    "limit_angular_upper",
    "spring_linear",
    "spring_angular",
    "horizontal_limit_linear_lower",
    "horizontal_limit_linear_upper",
    "horizontal_limit_angular_lower",
    "horizontal_limit_angular_upper",
    "horizontal_spring_linear",
    "horizontal_spring_angular",
)

JOINT_INTERPOLATION_NAMES = (
    "limit_linear",
    "limit_angular",
    "spring_linear",
    "spring_angular",
    "horizontal_limit_linear",
    "horizontal_limit_angular",
    "horizontal_spring_linear",
    "horizontal_spring_angular",
)

ADAPTIVE_SCALAR_NAMES = RIGID_INTERPOLATED_NAMES + tuple(
    f"{name}_end" for name in RIGID_INTERPOLATED_NAMES
)
ADAPTIVE_VECTOR_NAMES = JOINT_VECTOR_NAMES + tuple(
    f"{name}_end" for name in JOINT_VECTOR_NAMES
)
ANGLE_VECTOR_NAMES = {
    name for name in ADAPTIVE_VECTOR_NAMES if "limit_angular" in name
}

PHYSICS_SETTING_NAMES += tuple(
    name
    for base_name in RIGID_INTERPOLATED_NAMES
    for name in (f"{base_name}_interpolate", f"{base_name}_end")
)
PHYSICS_SETTING_NAMES += tuple(
    f"{base_name}_end" for base_name in JOINT_VECTOR_NAMES
)
PHYSICS_SETTING_NAMES += tuple(
    f"{base_name}_interpolate" for base_name in JOINT_INTERPOLATION_NAMES
)
PHYSICS_SETTING_NAMES += (
    "rigid_radius_multiply",
    "rigid_length_multiply",
)

PHYSICS_PRESET_SUBDIR = "mmd_skirt_proxy_creator/physics"
AUTO_RIGID_WIDTH_HALF_SPAN = 0.55
AUTO_RIGID_LENGTH_SPAN = 1.10
AUTO_RIGID_DEPTH_SPAN = 0.20


def _adaptive_number_text(value, angle=False):
    numeric = math.degrees(value) if angle else float(value)
    if abs(numeric) < 0.00005:
        numeric = 0.0
    text = f"{numeric:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".00"
    else:
        decimals = len(text.rsplit(".", 1)[1])
        if decimals < 2:
            text += "0" * (2 - decimals)
    return f"{text}°" if angle else text


def _adaptive_number_value(text, angle=False):
    cleaned = str(text).strip().removesuffix("°").strip().replace(",", ".")
    numeric = float(cleaned)
    return math.radians(numeric) if angle else numeric


def _adaptive_scalar_property_name(name):
    return f"adaptive_number_{name}"


def _adaptive_vector_property_name(name, index):
    return f"adaptive_number_{name}_{index}"


def _adaptive_scalar_getter(name):
    def getter(settings):
        return _adaptive_number_text(getattr(settings, name))

    return getter


def _adaptive_scalar_setter(name):
    def setter(settings, text):
        try:
            setattr(settings, name, _adaptive_number_value(text))
        except ValueError:
            pass

    return setter


def _adaptive_vector_getter(name, index, angle):
    def getter(settings):
        return _adaptive_number_text(getattr(settings, name)[index], angle=angle)

    return getter


def _adaptive_vector_setter(name, index, angle):
    def setter(settings, text):
        try:
            value = _adaptive_number_value(text, angle=angle)
        except ValueError:
            return
        values = list(getattr(settings, name))
        values[index] = value
        setattr(settings, name, values)

    return setter


def _mmd_api():
    try:
        model_module = importlib.import_module("bl_ext.blender_org.mmd_tools.core.model")
        rigid_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.rigid_body"
        )
    except ImportError as error:
        raise ProxyBuildError("需要先安装并启用官方 mmd_tools 扩展") from error
    if not hasattr(bpy.types.Object, "mmd_type"):
        raise ProxyBuildError("需要先启用官方 mmd_tools 扩展")
    return model_module.FnModel, rigid_module.FnRigidBody, rigid_module


def _proxy_armature(proxy_object):
    if proxy_object is None or proxy_object.type != "MESH":
        raise ProxyBuildError("请选择裙面代理 Mesh")
    if "surface_proxy_schema" not in proxy_object:
        raise ProxyBuildError("所选 Mesh 不是已识别的裙面代理")
    armature = bpy.data.objects.get(str(proxy_object.get("surface_proxy_armature", "")))
    if armature is None or armature.type != "ARMATURE":
        raise ProxyBuildError("代理关联的 Armature 不存在")
    return armature


def _proxy_structure(proxy_object, armature):
    prefix = str(proxy_object.get("surface_proxy_prefix", ""))
    row_counts = list(proxy_object.get("surface_proxy_column_rows", []))
    expected = {
        proxy_bone_name(proxy_object, prefix, column, row)
        for column, count in enumerate(row_counts)
        for row in range(count - 1)
    }
    if prefix and row_counts and expected.issubset(armature.data.bones.keys()):
        return prefix, row_counts
    from .sync import identify_proxy

    recovered_armature, prefix, row_counts, _mapping = identify_proxy(proxy_object)
    if recovered_armature != armature:
        raise ProxyBuildError("恢复后的代理 Armature 与原关联不一致")
    return prefix, row_counts


def _proxy_poll(_self, obj):
    return (
        obj is not None
        and obj.type == "MESH"
        and "surface_proxy_schema" in obj
    )


def _selected_proxy(context, settings):
    proxy_object = settings.physics_proxy
    active = context.active_object
    if proxy_object is None and _proxy_poll(None, active):
        proxy_object = active
        settings.physics_proxy = active
    _proxy_armature(proxy_object)
    return proxy_object


def _physics_setting_key(name):
    return f"spx_physics_{name}"


def _save_proxy_physics_settings(proxy_object, settings):
    for name in PHYSICS_SETTING_NAMES:
        value = getattr(settings, name)
        if hasattr(value, "to_list"):
            value = value.to_list()
        elif not isinstance(value, (str, int, float, bool)):
            value = list(value)
        proxy_object[_physics_setting_key(name)] = value


def _load_proxy_physics_settings(settings, proxy_object):
    if proxy_object is None:
        return
    for name in PHYSICS_SETTING_NAMES:
        key = _physics_setting_key(name)
        legacy_key = f"surface_proxy_physics_setting_{name}"
        if key in proxy_object:
            setattr(settings, name, proxy_object[key])
        elif len(legacy_key) <= 63 and legacy_key in proxy_object:
            setattr(settings, name, proxy_object[legacy_key])
        else:
            prop = settings.bl_rna.properties[name]
            value = (
                tuple(prop.default_array)
                if getattr(prop, "is_array", False)
                else prop.default
            )
            setattr(settings, name, value)
    root = bpy.data.objects.get(str(proxy_object.get("surface_proxy_mmd_root", "")))
    if root is None:
        try:
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
            root = FnModel.find_root_object(_proxy_armature(proxy_object))
        except ProxyBuildError:
            root = None
    if root is not None and getattr(root, "mmd_type", "") == "ROOT":
        settings.mmd_root = root


def _physics_proxy_changed(settings, _context):
    _load_proxy_physics_settings(settings, settings.physics_proxy)
    settings.browser_items.clear()


def _resolve_root(context, requested_root=None, proxy_object=None):
    FnModel, _FnRigidBody, _rigid_module = _mmd_api()
    if requested_root is not None:
        if requested_root.mmd_type != "ROOT":
            raise ProxyBuildError("指定对象不是 MMD 模型根对象")
        return requested_root

    candidates = [context.active_object]
    if proxy_object is not None:
        candidates.append(_proxy_armature(proxy_object))
    for candidate in candidates:
        if candidate is None:
            continue
        root = FnModel.find_root_object(candidate)
        if root is not None:
            return root
    raise ProxyBuildError("找不到 MMD 模型根对象；请在查看面板中指定模型")


def _assigned_to_other_proxy(obj, proxy_object, proxy_id):
    if obj.get("surface_proxy_physics_schema") != PHYSICS_SCHEMA:
        return False
    assigned_id = str(obj.get("surface_proxy_physics_id", ""))
    assigned_name = str(obj.get("surface_proxy_object", ""))
    return (assigned_id and assigned_id != proxy_id) or (
        assigned_name and assigned_name != proxy_object.name
    )


def associate_existing_proxy_physics(proxy_object):
    exact_names = list(proxy_object.get("surface_proxy_bone_names", []))
    if not exact_names:
        return 0, 0
    proxy_id = str(proxy_object.get("surface_proxy_physics_id", ""))
    if not proxy_id:
        proxy_id = uuid.uuid4().hex
        proxy_object["surface_proxy_physics_id"] = proxy_id
    armature = _proxy_armature(proxy_object)
    prefix, row_counts = _proxy_structure(proxy_object, armature)
    slots_by_bone = {
        proxy_bone_name(proxy_object, prefix, column, row): (column, row)
        for column, count in enumerate(row_counts)
        for row in range(count - 1)
    }
    FnModel, _FnRigidBody, _rigid_module = _mmd_api()
    root = FnModel.find_root_object(armature)
    if root is None:
        return 0, 0
    proxy_object["surface_proxy_mmd_root"] = root.name

    rigid_slots = {}
    for rigid in FnModel.iterate_rigid_body_objects(root):
        if _assigned_to_other_proxy(rigid, proxy_object, proxy_id):
            continue
        slot = slots_by_bone.get(str(getattr(rigid.mmd_rigid, "bone", "")))
        if slot is None:
            continue
        _mark_physics_object(rigid, proxy_object, "RIGID", slot[0], slot[1])
        rigid_slots[rigid] = slot

    closed = bool(proxy_object.get("surface_proxy_closed", True))
    column_groups = _column_groups(proxy_object, len(row_counts))
    horizontal_pairs = set(_column_pairs(column_groups, closed))
    joint_count = 0
    for joint in FnModel.iterate_joint_objects(root):
        if _assigned_to_other_proxy(joint, proxy_object, proxy_id):
            continue
        constraint = joint.rigid_body_constraint
        if constraint is None:
            continue
        rigid_a = constraint.object1
        rigid_b = constraint.object2
        slot_a = rigid_slots.get(rigid_a)
        slot_b = rigid_slots.get(rigid_b)
        role = ""
        column = -1
        row = -1
        following = -1
        if slot_a is not None and slot_b is not None:
            if slot_a[0] == slot_b[0] and abs(slot_a[1] - slot_b[1]) == 1:
                role = "JOINT_VERTICAL"
                column = slot_a[0]
                row = max(slot_a[1], slot_b[1])
            elif slot_a[1] == slot_b[1]:
                if (slot_a[0], slot_b[0]) in horizontal_pairs:
                    column, following = slot_a[0], slot_b[0]
                elif (slot_b[0], slot_a[0]) in horizontal_pairs:
                    column, following = slot_b[0], slot_a[0]
                if following >= 0:
                    role = "JOINT_HORIZONTAL"
                    row = slot_a[1]
        elif slot_a is not None or slot_b is not None:
            slot = slot_a if slot_a is not None else slot_b
            other = rigid_b if slot_a is not None else rigid_a
            if slot[1] == 0 and other is not None:
                top_name = proxy_bone_name(proxy_object, prefix, slot[0], 0)
                top_bone = armature.data.bones.get(top_name)
                other_bone = str(getattr(other.mmd_rigid, "bone", ""))
                if top_bone is not None and top_bone.parent is not None:
                    if other_bone == top_bone.parent.name:
                        role = "JOINT_ANCHOR"
                        column = slot[0]
                        row = 0
        if not role:
            continue
        _mark_physics_object(joint, proxy_object, role, column, row)
        if role == "JOINT_HORIZONTAL":
            joint["surface_proxy_following_column"] = following
        joint_count += 1
    return len(rigid_slots), joint_count


def _proxy_physics_objects(proxy_object):
    proxy_id = str(proxy_object.get("surface_proxy_physics_id", ""))
    if not proxy_id:
        proxy_id = uuid.uuid4().hex
        proxy_object["surface_proxy_physics_id"] = proxy_id
    associate_existing_proxy_physics(proxy_object)
    result = []
    for obj in bpy.data.objects:
        if obj.get("surface_proxy_physics_schema") != PHYSICS_SCHEMA:
            continue
        if (
            obj.get("surface_proxy_physics_id") == proxy_id
            or obj.get("surface_proxy_object") == proxy_object.name
        ):
            obj["surface_proxy_physics_id"] = proxy_id
            obj["surface_proxy_object"] = proxy_object.name
            result.append(obj)
    return result


def _proxy_grid(proxy_object, armature, row_counts):
    prefix = str(proxy_object.get("surface_proxy_prefix", ""))
    grid = []
    for column, count in enumerate(row_counts):
        points = []
        for row in range(count - 1):
            name = proxy_bone_name(proxy_object, prefix, column, row)
            bone = armature.data.bones.get(name)
            if bone is None:
                raise ProxyBuildError(f"缺少代理骨骼：{name}")
            points.append(bone.head_local.copy())
        points.append(bone.tail_local.copy())
        grid.append(points)
    return grid


def _segment_index(column, factor):
    return min(
        int(round(factor * max(len(column) - 2, 0))),
        len(column) - 2,
    )


def _column_groups(proxy_object, column_count):
    groups = list(proxy_object.get("surface_proxy_column_groups", []))
    return groups if len(groups) == column_count else [0] * column_count


def _group_columns(column_groups, column):
    group = column_groups[column]
    return [index for index, value in enumerate(column_groups) if value == group]


def _column_pairs(column_groups, closed):
    pairs = []
    for group in dict.fromkeys(column_groups):
        columns = [index for index, value in enumerate(column_groups) if value == group]
        pairs.extend(zip(columns, columns[1:]))
        if closed and len(columns) > 2:
            pairs.append((columns[-1], columns[0]))
    return pairs


def _following_column(column_groups, column, closed):
    columns = _group_columns(column_groups, column)
    position = columns.index(column)
    if position + 1 < len(columns):
        return columns[position + 1]
    return columns[0] if closed and len(columns) > 2 else -1


def _horizontal_joint_location(grid, column, following, row):
    return (
        grid[column][row]
        + grid[column][row + 1]
        + grid[following][row]
        + grid[following][row + 1]
    ) * 0.25


def _joint_names_from_rigid_b(rigid_b, role):
    name_j = rigid_b.mmd_rigid.name_j.strip() or rigid_b.name
    name_e = rigid_b.mmd_rigid.name_e.strip() or name_j
    if role == "JOINT_HORIZONTAL":
        name_j = f"{name_j}_H"
        name_e = f"{name_e}_H"
    return name_j, name_e


def _sync_joint_name_from_rigid_b(joint):
    constraint = joint.rigid_body_constraint
    rigid_b = constraint.object2 if constraint is not None else None
    if rigid_b is None or rigid_b.mmd_type != "RIGID_BODY":
        return False
    role = str(joint.get("surface_proxy_role", ""))
    name_j, name_e = _joint_names_from_rigid_b(rigid_b, role)
    joint.name = f"J.{name_j}"
    joint.mmd_joint.name_j = name_j
    joint.mmd_joint.name_e = name_e
    return True


def _segment_geometry(grid, column, row, closed, column_groups=None):
    points = grid[column]
    head = points[row]
    tail = points[row + 1]
    midpoint = (head + tail) * 0.5
    vertical = tail - head
    length = vertical.length
    if length <= 1.0e-8:
        raise ProxyBuildError(f"代理第 {column + 1} 列第 {row + 1} 段长度为零")
    vertical.normalize()

    column_groups = column_groups or [0] * len(grid)
    group_columns = _group_columns(column_groups, column)
    factor = row / max(len(points) - 2, 1)
    neighbours = []
    position = group_columns.index(column)
    if closed and len(group_columns) > 2:
        neighbour_indices = (
            group_columns[(position - 1) % len(group_columns)],
            group_columns[(position + 1) % len(group_columns)],
        )
    else:
        neighbour_indices = tuple(
            group_columns[index]
            for index in (position - 1, position + 1)
            if 0 <= index < len(group_columns)
        )
    for neighbour in neighbour_indices:
        neighbour_row = _segment_index(grid[neighbour], factor)
        neighbour_midpoint = (
            grid[neighbour][neighbour_row] + grid[neighbour][neighbour_row + 1]
        ) * 0.5
        neighbours.append((neighbour, neighbour_midpoint))

    if len(neighbours) == 2:
        tangent = neighbours[1][1] - neighbours[0][1]
    elif neighbours:
        tangent = neighbours[0][1] - midpoint
        if neighbours[0][0] < column:
            tangent.negate()
    else:
        axis = Vector((0.0, 0.0, midpoint.z))
        normal_hint = midpoint - axis
        if normal_hint.length <= 1.0e-8:
            normal_hint = Vector((1.0, 0.0, 0.0))
        tangent = normal_hint.cross(vertical)
    tangent -= vertical * tangent.dot(vertical)
    if tangent.length <= 1.0e-8:
        tangent = vertical.orthogonal()
    tangent.normalize()
    normal = vertical.cross(tangent)
    normal.normalize()

    layer_midpoints = []
    for candidate_index in group_columns:
        candidate = grid[candidate_index]
        candidate_row = _segment_index(candidate, factor)
        layer_midpoints.append(
            (candidate[candidate_row] + candidate[candidate_row + 1]) * 0.5
        )
    layer_center = sum(layer_midpoints, Vector()) / len(layer_midpoints)
    outward = midpoint - layer_center
    if outward.length <= 1.0e-8:
        outward = midpoint - Vector((0.0, 0.0, midpoint.z))
    if outward.length > 1.0e-8 and normal.dot(outward) < 0.0:
        normal.negate()
        tangent.negate()

    widths = [(neighbour_midpoint - midpoint).length for _index, neighbour_midpoint in neighbours]
    if widths:
        width = max(widths)
    else:
        width = length * 0.7
    width = max(width, length * 0.05, 0.001)
    depth = max(min(width, length) * AUTO_RIGID_DEPTH_SPAN, 0.001)
    rotation = Matrix((tangent, normal, vertical)).transposed().to_euler("YXZ")
    return {
        "head": head,
        "tail": tail,
        "location": midpoint,
        "rotation": rotation,
        "width": width,
        "length": length,
        "depth": depth,
        "normal": normal,
    }


def _source_value(source, name):
    if hasattr(source, name):
        return getattr(source, name)
    return source.get(_physics_setting_key(name), 0.0)


def _source_interpolated_scalar(source, name, factor):
    start = float(_source_value(source, name))
    if not bool(_source_value(source, f"{name}_interpolate")):
        return start
    end = float(_source_value(source, f"{name}_end"))
    return start + (end - start) * factor


def _rigid_size(shape, geometry, source, factor):
    bone_length = geometry["length"]
    radius_ratio = _source_interpolated_scalar(source, "rigid_radius_ratio", factor)
    length_ratio = _source_interpolated_scalar(source, "rigid_length_ratio", factor)
    depth_ratio = _source_interpolated_scalar(source, "rigid_depth_ratio", factor)
    radius_scale = 2.0 if bool(_source_value(source, "rigid_radius_multiply")) else 1.0
    length_scale = 2.0 if bool(_source_value(source, "rigid_length_multiply")) else 1.0
    radius = (
        bone_length * radius_ratio * radius_scale
        if radius_ratio > 1.0e-8
        else geometry["width"] * AUTO_RIGID_WIDTH_HALF_SPAN
    )
    length = (
        bone_length * length_ratio * length_scale
        if length_ratio > 1.0e-8
        else geometry["length"] * AUTO_RIGID_LENGTH_SPAN
    )
    depth = (
        bone_length * depth_ratio
        if depth_ratio > 1.0e-8
        else geometry["depth"] * 0.5
    )
    radius = max(radius, 0.001)
    length = max(length, 0.001)
    depth = max(depth, 0.001)
    if shape == "SPHERE":
        return Vector((max(radius, length * 0.5), 0.0, 0.0))
    if shape == "BOX":
        return Vector((radius, depth, max(length * 0.5, 0.001)))
    if radius_ratio <= 1.0e-8:
        radius = min(radius, length * 0.45)
    cylinder_length = max(length - radius * 2.0, 0.001)
    return Vector((radius, cylinder_length, 0.0))


def _interpolation_factor(index, count):
    return index / (count - 1) if count > 1 else 0.0


def _rigid_interpolation_factor(row, row_counts):
    max_point_count = max(row_counts, default=0)
    return _interpolation_factor(row, max_point_count - 1)


def _joint_interpolation_factor(row, row_counts):
    max_point_count = max(row_counts, default=0)
    return _interpolation_factor(row - 1, max_point_count - 2)


def _interpolated_scalar(settings, name, factor):
    start = float(getattr(settings, name))
    if not getattr(settings, f"{name}_interpolate"):
        return start
    end = float(getattr(settings, f"{name}_end"))
    return start + (end - start) * factor


def _interpolated_vector(settings, name, factor):
    start = getattr(settings, name)
    end = getattr(settings, f"{name}_end")
    if name.endswith(("_lower", "_upper")):
        interpolation_name = name.rsplit("_", 1)[0]
    else:
        interpolation_name = name
    enabled = getattr(settings, f"{interpolation_name}_interpolate")
    return [
        start[index] + (end[index] - start[index]) * factor
        if enabled[index]
        else start[index]
        for index in range(3)
    ]


def _joint_vectors(settings, role, factor):
    prefix = "horizontal_" if role == "JOINT_HORIZONTAL" else ""
    return (
        Vector(_interpolated_vector(settings, f"{prefix}limit_linear_upper", factor)),
        Vector(_interpolated_vector(settings, f"{prefix}limit_linear_lower", factor)),
        Euler(_interpolated_vector(settings, f"{prefix}limit_angular_upper", factor), "XYZ"),
        Euler(_interpolated_vector(settings, f"{prefix}limit_angular_lower", factor), "XYZ"),
        Vector(_interpolated_vector(settings, f"{prefix}spring_angular", factor)),
        Vector(_interpolated_vector(settings, f"{prefix}spring_linear", factor)),
    )


def _apply_stable_long_skirt_preset(settings):
    settings.rigid_shape = "BOX"
    settings.top_rigid_type = "2"
    settings.body_rigid_type = "1"
    settings.rigid_radius_ratio = 0.0
    settings.rigid_length_ratio = 0.0
    settings.rigid_depth_ratio = 0.15
    settings.rigid_radius_multiply = False
    settings.rigid_length_multiply = False

    scalar_values = {
        "rigid_radius_ratio": (False, 0.0),
        "rigid_length_ratio": (False, 0.0),
        "rigid_depth_ratio": (True, 0.5),
        "mass": (True, 0.4),
        "linear_damping": (True, 0.99),
        "angular_damping": (True, 0.99),
        "restitution": (False, 0.0),
        "friction": (False, 0.3),
    }
    settings.mass = 2.0
    settings.linear_damping = 0.995
    settings.angular_damping = 0.995
    settings.restitution = 0.0
    settings.friction = 0.3
    settings.collision_group_number = 5
    collision_mask = [False] * 16
    collision_mask[5] = True
    settings.collision_group_mask = collision_mask
    for name, (interpolate, end) in scalar_values.items():
        setattr(settings, f"{name}_interpolate", interpolate)
        setattr(settings, f"{name}_end", end)

    settings.create_horizontal_joints = True
    joint_values = {
        "limit_linear_lower": (0.0, 0.0, 0.0),
        "limit_linear_upper": (0.0, 0.0, 0.0),
        "limit_angular_lower": tuple(
            math.radians(value) for value in (-8.0, 0.0, 0.0)
        ),
        "limit_angular_upper": tuple(
            math.radians(value) for value in (8.0, 0.0, 0.0)
        ),
        "spring_linear": (0.0, 800.0, 0.0),
        "spring_angular": (12.0, 5.0, 5.0),
        "horizontal_limit_linear_lower": (0.0, 0.0, 0.0),
        "horizontal_limit_linear_upper": (0.02, 0.0, 0.0),
        "horizontal_limit_angular_lower": tuple(
            math.radians(value) for value in (-10.0, -3.0, -5.0)
        ),
        "horizontal_limit_angular_upper": tuple(
            math.radians(value) for value in (10.0, 3.0, 5.0)
        ),
        "horizontal_spring_linear": (120.0, 0.0, 0.0),
        "horizontal_spring_angular": (0.8, 1.5, 4.0),
    }
    joint_end_values = {
        "limit_linear_lower": (0.0, 0.0, 0.0),
        "limit_linear_upper": (0.0, 0.0, 0.0),
        "limit_angular_lower": tuple(
            math.radians(value) for value in (-18.0, -7.0, -7.0)
        ),
        "limit_angular_upper": tuple(
            math.radians(value) for value in (18.0, 7.0, 7.0)
        ),
        "spring_linear": (0.0, 250.0, 0.0),
        "spring_angular": (4.0, 2.0, 2.0),
        "horizontal_limit_linear_lower": (0.0, 0.0, 0.0),
        "horizontal_limit_linear_upper": (0.03, 0.0, 0.0),
        "horizontal_limit_angular_lower": tuple(
            math.radians(value) for value in (-18.0, -5.0, -12.0)
        ),
        "horizontal_limit_angular_upper": tuple(
            math.radians(value) for value in (18.0, 5.0, 12.0)
        ),
        "horizontal_spring_linear": (40.0, 0.0, 0.0),
        "horizontal_spring_angular": (0.25, 0.5, 1.5),
    }
    for name, value in joint_values.items():
        setattr(settings, name, value)
        setattr(settings, f"{name}_end", joint_end_values[name])
    joint_interpolation = {
        "limit_linear": (False, False, False),
        "limit_angular": (True, False, False),
        "spring_linear": (False, True, False),
        "spring_angular": (True, True, True),
        "horizontal_limit_linear": (True, False, False),
        "horizontal_limit_angular": (True, True, True),
        "horizontal_spring_linear": (True, False, False),
        "horizontal_spring_angular": (True, True, True),
    }
    for name, value in joint_interpolation.items():
        setattr(settings, f"{name}_interpolate", value)


def _mark_physics_object(obj, proxy_object, role, column, row):
    obj["surface_proxy_physics_schema"] = PHYSICS_SCHEMA
    obj["surface_proxy_object"] = proxy_object.name
    obj["surface_proxy_physics_id"] = proxy_object["surface_proxy_physics_id"]
    obj["surface_proxy_role"] = role
    obj["surface_proxy_column"] = column
    obj["surface_proxy_row"] = row


def _anchor_rigid_map(proxy_object, armature, prefix, row_counts, grid, rigid_objects):
    rigids_by_bone = {}
    for rigid in rigid_objects:
        bone_name_value = str(getattr(rigid.mmd_rigid, "bone", ""))
        if bone_name_value:
            rigids_by_bone.setdefault(bone_name_value, []).append(rigid)

    anchors = {}
    for column in range(len(row_counts)):
        top_bone = armature.data.bones.get(
            proxy_bone_name(proxy_object, prefix, column, 0)
        )
        if top_bone is None or top_bone.parent is None:
            continue
        candidates = rigids_by_bone.get(top_bone.parent.name, [])
        if not candidates:
            continue
        location = grid[column][0]
        armature_inverse = armature.matrix_world.inverted_safe()
        anchors[column] = min(
            candidates,
            key=lambda rigid: (
                int(rigid.mmd_rigid.type) != 0,
                (
                    armature_inverse @ rigid.matrix_world.translation - location
                ).length_squared,
                rigid.name,
            ),
        )
    return anchors


def create_proxy_physics(context, proxy_object, settings):
    armature = _proxy_armature(proxy_object)
    prefix, row_counts = _proxy_structure(proxy_object, armature)
    root = _resolve_root(context, settings.mmd_root, proxy_object)
    FnModel, FnRigidBody, rigid_module = _mmd_api()
    if FnModel.find_armature_object(root) != armature:
        raise ProxyBuildError("代理 Armature 不属于指定的 MMD 模型")
    existing = _proxy_physics_objects(proxy_object)

    rigid_group = FnModel.ensure_rigid_group_object(context, root)
    joint_group = FnModel.ensure_joint_group_object(context, root)
    rigid_map = {}
    created = []
    mask = list(settings.collision_group_mask)
    closed = bool(proxy_object.get("surface_proxy_closed", True))
    grid = _proxy_grid(proxy_object, armature, row_counts)
    column_groups = _column_groups(proxy_object, len(row_counts))
    anchor_map = _anchor_rigid_map(
        proxy_object,
        armature,
        prefix,
        row_counts,
        grid,
        list(FnModel.iterate_rigid_body_objects(root)),
    )
    try:
        rigid_descriptors = []
        for column, point_count in enumerate(row_counts):
            for row in range(point_count - 1):
                name = proxy_bone_name(proxy_object, prefix, column, row)
                bone = armature.data.bones.get(name)
                if bone is None:
                    raise ProxyBuildError(f"缺少代理骨骼：{name}")
                factor = _rigid_interpolation_factor(row, row_counts)
                rigid_descriptors.append(
                    (
                        column,
                        row,
                        name,
                        _segment_geometry(
                            grid, column, row, closed, column_groups
                        ),
                        factor,
                        int(settings.top_rigid_type)
                        if row == 0
                        else int(settings.body_rigid_type),
                    )
                )
        rigid_objects = FnRigidBody.new_rigid_body_objects(
            context,
            rigid_group,
            len(rigid_descriptors),
        )
        created.extend(rigid_objects)
        for rigid, descriptor in zip(rigid_objects, rigid_descriptors):
            column, row, name, geometry, factor, dynamics_type = descriptor
            rigid = FnRigidBody.setup_rigid_body_object(
                obj=rigid,
                shape_type=rigid_module.shapeType(settings.rigid_shape),
                location=geometry["location"],
                rotation=geometry["rotation"],
                size=_rigid_size(settings.rigid_shape, geometry, settings, factor),
                dynamics_type=dynamics_type,
                name=name,
                name_e=name,
                collision_group_number=settings.collision_group_number,
                collision_group_mask=mask,
                mass=_interpolated_scalar(settings, "mass", factor),
                friction=_interpolated_scalar(settings, "friction", factor),
                bounce=_interpolated_scalar(settings, "restitution", factor),
                linear_damping=_interpolated_scalar(
                    settings, "linear_damping", factor
                ),
                angular_damping=_interpolated_scalar(
                    settings, "angular_damping", factor
                ),
                bone=name,
            )
            _mark_physics_object(rigid, proxy_object, "RIGID", column, row)
            rigid["surface_proxy_bone_length"] = geometry["length"]
            rigid["surface_proxy_normal"] = list(geometry["normal"])
            rigid_map[(column, row)] = rigid

        joint_descriptors = []
        for column, anchor_rigid in anchor_map.items():
            geometry = _segment_geometry(
                grid, column, 0, closed, column_groups
            )
            joint_descriptors.append(
                (
                    "JOINT_ANCHOR",
                    column,
                    0,
                    anchor_rigid,
                    rigid_map[(column, 0)],
                    grid[column][0],
                    geometry["rotation"],
                    0.0,
                )
            )
        for column, point_count in enumerate(row_counts):
            for row in range(1, point_count - 1):
                geometry = _segment_geometry(
                    grid, column, row, closed, column_groups
                )
                joint_descriptors.append(
                    (
                        "JOINT_VERTICAL",
                        column,
                        row,
                        rigid_map[(column, row - 1)],
                        rigid_map[(column, row)],
                        grid[column][row],
                        geometry["rotation"],
                        _joint_interpolation_factor(row, row_counts),
                    )
                )

        if settings.create_horizontal_joints:
            for column, following in _column_pairs(column_groups, closed):
                shared_bones = min(row_counts[column], row_counts[following]) - 1
                for row in range(shared_bones):
                    geometry = _segment_geometry(
                        grid, column, row, closed, column_groups
                    )
                    joint_descriptors.append(
                        (
                            "JOINT_HORIZONTAL",
                            column,
                            row,
                            rigid_map[(column, row)],
                            rigid_map[(following, row)],
                            _horizontal_joint_location(grid, column, following, row),
                            geometry["rotation"],
                            _rigid_interpolation_factor(row, row_counts),
                        )
                    )

        joint_objects = FnRigidBody.new_joint_objects(
            context,
            joint_group,
            len(joint_descriptors),
            FnModel.get_empty_display_size(root),
        )
        created.extend(joint_objects)
        for joint, descriptor in zip(joint_objects, joint_descriptors):
            role, column, row, rigid_a, rigid_b, location, rotation, factor = descriptor
            joint_args = _joint_vectors(settings, role, factor)
            joint_name, joint_name_e = _joint_names_from_rigid_b(rigid_b, role)
            joint = FnRigidBody.setup_joint_object(
                obj=joint,
                name=joint_name,
                name_e=joint_name_e,
                location=location,
                rotation=rotation,
                rigid_a=rigid_a,
                rigid_b=rigid_b,
                maximum_location=joint_args[0],
                minimum_location=joint_args[1],
                maximum_rotation=joint_args[2],
                minimum_rotation=joint_args[3],
                spring_angular=joint_args[4],
                spring_linear=joint_args[5],
            )
            _mark_physics_object(joint, proxy_object, role, column, row)
            if role == "JOINT_HORIZONTAL":
                joint["surface_proxy_following_column"] = int(
                    rigid_b["surface_proxy_column"]
                )
    except Exception:
        for obj in reversed(created):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        raise

    for obj in sorted(existing, key=lambda item: item.mmd_type != "JOINT"):
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    proxy_object["surface_proxy_mmd_root"] = root.name
    _save_proxy_physics_settings(proxy_object, settings)
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    proxy_object.hide_set(False)
    proxy_object.select_set(True)
    context.view_layer.objects.active = proxy_object
    return len(rigid_map), len(joint_descriptors)


def update_proxy_physics(context, proxy_object, settings):
    armature = _proxy_armature(proxy_object)
    prefix, row_counts = _proxy_structure(proxy_object, armature)
    root = _resolve_root(context, settings.mmd_root, proxy_object)
    FnModel, _FnRigidBody, _rigid_module = _mmd_api()
    if FnModel.find_armature_object(root) != armature:
        raise ProxyBuildError("代理 Armature 不属于指定的 MMD 模型")
    objects = _proxy_physics_objects(proxy_object)
    if not objects:
        raise ProxyBuildError("该代理尚未生成刚体和 Joint")
    closed = bool(proxy_object.get("surface_proxy_closed", True))
    grid = _proxy_grid(proxy_object, armature, row_counts)
    column_groups = _column_groups(proxy_object, len(row_counts))
    rigid_count = 0
    joint_count = 0
    for obj in objects:
        role = str(obj.get("surface_proxy_role", ""))
        column = int(obj.get("surface_proxy_column", -1))
        row = int(obj.get("surface_proxy_row", -1))
        if role == "RIGID":
            factor = _rigid_interpolation_factor(row, row_counts)
            name = proxy_bone_name(proxy_object, prefix, column, row)
            if armature.data.bones.get(name) is None:
                raise ProxyBuildError(f"缺少代理骨骼：{name}")
            geometry = _segment_geometry(
                grid, column, row, closed, column_groups
            )
            obj.location = geometry["location"]
            obj.rotation_euler = geometry["rotation"]
            obj.mmd_rigid.shape = settings.rigid_shape
            obj.mmd_rigid.size = _rigid_size(settings.rigid_shape, geometry, settings, factor)
            obj.mmd_rigid.type = (
                settings.top_rigid_type if row == 0 else settings.body_rigid_type
            )
            obj.mmd_rigid.collision_group_number = settings.collision_group_number
            obj.mmd_rigid.collision_group_mask = list(settings.collision_group_mask)
            obj.rigid_body.mass = _interpolated_scalar(settings, "mass", factor)
            obj.rigid_body.friction = _interpolated_scalar(
                settings, "friction", factor
            )
            obj.rigid_body.restitution = _interpolated_scalar(
                settings, "restitution", factor
            )
            obj.rigid_body.linear_damping = _interpolated_scalar(
                settings, "linear_damping", factor
            )
            obj.rigid_body.angular_damping = _interpolated_scalar(
                settings, "angular_damping", factor
            )
            if abs(float(obj.get("surface_proxy_bone_length", 0.0)) - geometry["length"]) > 1.0e-8:
                obj["surface_proxy_bone_length"] = geometry["length"]
            stored_normal = Vector(obj.get("surface_proxy_normal", geometry["normal"]))
            if (stored_normal - geometry["normal"]).length > 1.0e-8:
                obj["surface_proxy_normal"] = list(geometry["normal"])
            rigid_count += 1
        elif role.startswith("JOINT_"):
            if role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
                factor = (
                    0.0
                    if role == "JOINT_ANCHOR"
                    else _joint_interpolation_factor(row, row_counts)
                )
            else:
                closed = bool(proxy_object.get("surface_proxy_closed", True))
                following = int(
                    obj.get(
                        "surface_proxy_following_column",
                        _following_column(column_groups, column, closed),
                    )
                )
                if following < 0 or following >= len(row_counts):
                    continue
                factor = _rigid_interpolation_factor(row, row_counts)
            joint_args = _joint_vectors(settings, role, factor)
            constraint = obj.rigid_body_constraint
            if role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
                name = proxy_bone_name(proxy_object, prefix, column, row)
                if armature.data.bones.get(name) is None:
                    raise ProxyBuildError(f"缺少代理骨骼：{name}")
                geometry = _segment_geometry(
                    grid, column, row, closed, column_groups
                )
                obj.location = grid[column][row]
                obj.rotation_euler = geometry["rotation"]
            elif constraint.object1 is not None and constraint.object2 is not None:
                following = int(
                    obj.get(
                        "surface_proxy_following_column",
                        _following_column(column_groups, column, closed),
                    )
                )
                geometry = _segment_geometry(
                    grid, column, row, closed, column_groups
                )
                obj.location = _horizontal_joint_location(
                    grid, column, following, row
                )
                obj.rotation_euler = geometry["rotation"]
            for axis, upper, lower in zip(
                "xyz", joint_args[0], joint_args[1]
            ):
                setattr(constraint, f"limit_lin_{axis}_upper", upper)
                setattr(constraint, f"limit_lin_{axis}_lower", lower)
            for axis, upper, lower in zip(
                "xyz", joint_args[2], joint_args[3]
            ):
                setattr(constraint, f"limit_ang_{axis}_upper", upper)
                setattr(constraint, f"limit_ang_{axis}_lower", lower)
            obj.mmd_joint.spring_angular = joint_args[4]
            obj.mmd_joint.spring_linear = joint_args[5]
            joint_count += 1
    _save_proxy_physics_settings(proxy_object, settings)
    return rigid_count, joint_count


def sync_proxy_physics_transforms(proxy_object):
    armature = _proxy_armature(proxy_object)
    prefix, row_counts = _proxy_structure(proxy_object, armature)
    objects = _proxy_physics_objects(proxy_object)
    if not objects:
        return 0, 0
    closed = bool(proxy_object.get("surface_proxy_closed", True))
    grid = _proxy_grid(proxy_object, armature, row_counts)
    column_groups = _column_groups(proxy_object, len(row_counts))
    rigid_count = 0
    joint_count = 0
    joints = []
    for obj in objects:
        role = str(obj.get("surface_proxy_role", ""))
        column = int(obj.get("surface_proxy_column", -1))
        row = int(obj.get("surface_proxy_row", -1))
        if role == "RIGID":
            name = proxy_bone_name(proxy_object, prefix, column, row)
            bone = armature.data.bones.get(name)
            if bone is None:
                raise ProxyBuildError(f"缺少代理骨骼：{name}")
            geometry = _segment_geometry(
                grid, column, row, closed, column_groups
            )
            if (obj.location - geometry["location"]).length > 1.0e-8:
                obj.location = geometry["location"]
            if any(
                abs(first - second) > 1.0e-8
                for first, second in zip(obj.rotation_euler, geometry["rotation"])
            ):
                obj.rotation_euler = geometry["rotation"]
            rigid_count += 1
        elif role.startswith("JOINT_"):
            joints.append((obj, role, column, row))
    for obj, role, column, row in joints:
        if role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
            name = proxy_bone_name(proxy_object, prefix, column, row)
            bone = armature.data.bones.get(name)
            if bone is None:
                raise ProxyBuildError(f"缺少代理骨骼：{name}")
            geometry = _segment_geometry(
                grid, column, row, closed, column_groups
            )
            location = grid[column][row]
        else:
            following = int(
                obj.get(
                    "surface_proxy_following_column",
                    _following_column(column_groups, column, closed),
                )
            )
            if following < 0 or following >= len(row_counts):
                continue
            geometry = _segment_geometry(
                grid, column, row, closed, column_groups
            )
            location = _horizontal_joint_location(grid, column, following, row)
        if (obj.location - location).length > 1.0e-8:
            obj.location = location
        if any(
            abs(first - second) > 1.0e-8
            for first, second in zip(obj.rotation_euler, geometry["rotation"])
        ):
            obj.rotation_euler = geometry["rotation"]
        joint_count += 1
    return rigid_count, joint_count


class SPX_MMD_BrowserItem(PropertyGroup):
    selected: BoolProperty(name="批量选择")
    kind: StringProperty()
    target_name: StringProperty()
    label: StringProperty()
    detail: StringProperty()
    armature_name: StringProperty()
    order_index: IntProperty(default=-1)


class SPX_UL_MMDItems(UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        icon = {"BONE": "BONE_DATA", "RIGID": "MESH_UVSPHERE", "JOINT": "CONSTRAINT"}.get(
            item.kind,
            "DOT",
        )
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=f"{item.order_index:03d}")
        row.label(text=item.label, icon=icon)
        row.label(text=item.detail)
        operator = row.operator("surface_proxy.select_mmd_item", text="", icon="RESTRICT_SELECT_OFF")
        operator.kind = item.kind
        operator.target_name = item.target_name
        operator.armature_name = item.armature_name

    def filter_items(self, _context, data, property_name):
        items = getattr(data, property_name)
        search = data.browser_search.casefold().strip()
        if not search:
            return [], []
        flags = [
            self.bitflag_filter_item
            if search in f"{item.label} {item.detail}".casefold()
            else 0
            for item in items
        ]
        return flags, []


class SPX_OT_CreateMMDPhysics(Operator):
    bl_idname = "surface_proxy.create_mmd_physics"
    bl_label = "生成 MMD 刚体和 Joint"
    bl_description = "按当前参数生成物理；当前代理已有物理时，重建其刚体和 Joint"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            settings = context.scene.surface_proxy_creator
            proxy_object = _selected_proxy(context, settings)
            rebuilt = bool(_proxy_physics_objects(proxy_object))
            rigid_count, joint_count = create_proxy_physics(
                context,
                proxy_object,
                settings,
            )
        except (ProxyBuildError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        action = "已重建" if rebuilt else "已创建"
        self.report({"INFO"}, f"{action} {rigid_count} 个刚体、{joint_count} 个 Joint")
        return {"FINISHED"}


class SPX_MT_PhysicsPresets(Menu):
    bl_label = "自定义预设"
    bl_idname = "SPX_MT_physics_presets"
    preset_subdir = PHYSICS_PRESET_SUBDIR
    preset_operator = "script.execute_preset"
    draw = Menu.draw_preset


class SPX_OT_ApplyStableLongSkirtPreset(Operator):
    bl_idname = "surface_proxy.apply_stable_long_skirt_preset"
    bl_label = "稳定中长裙"
    bl_description = "将推荐的刚体、纵 Joint 与横 Joint 参数填入当前面板，不立即修改已生成对象"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _apply_stable_long_skirt_preset(context.scene.surface_proxy_creator)
        self.report({"INFO"}, "已填入“稳定中长裙”物理参数；点击应用参数后更新当前代理")
        return {"FINISHED"}


class SPX_OT_AddPhysicsPreset(AddPresetBase, Operator):
    bl_idname = "surface_proxy.add_physics_preset"
    bl_label = "保存物理预设"
    preset_menu = SPX_MT_PhysicsPresets.bl_idname
    preset_subdir = PHYSICS_PRESET_SUBDIR
    preset_defines = ["settings = bpy.context.scene.surface_proxy_creator"]
    preset_values = [f"settings.{name}" for name in PHYSICS_SETTING_NAMES]

    def execute(self, context):
        if not self.remove_active:
            return super().execute(context)
        menu_class = getattr(bpy.types, self.preset_menu)
        active_name = menu_class.bl_label.casefold()
        directory = bpy.utils.user_resource(
            "SCRIPTS",
            path=os.path.join("presets", self.preset_subdir),
        )
        if directory and os.path.isdir(directory):
            for entry in os.scandir(directory):
                if entry.is_file() and entry.name.lower().endswith(".py"):
                    display_name = bpy.path.display_name(
                        entry.name,
                        title_case=False,
                    )
                    if display_name.casefold() == active_name:
                        os.remove(entry.path)
                        menu_class.bl_label = "自定义预设"
                        return {"FINISHED"}
        self.report({"WARNING"}, "没有找到可删除的当前自定义预设")
        return {"CANCELLED"}


class SPX_OT_UpdateMMDPhysics(Operator):
    bl_idname = "surface_proxy.update_mmd_physics"
    bl_label = "应用参数到当前代理"
    bl_description = "将当前面板参数重新应用到已经生成且属于当前代理的刚体和 Joint，不影响其它代理"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            settings = context.scene.surface_proxy_creator
            rigid_count, joint_count = update_proxy_physics(
                context,
                _selected_proxy(context, settings),
                settings,
            )
        except (ProxyBuildError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已更新 {rigid_count} 个刚体、{joint_count} 个 Joint")
        return {"FINISHED"}


class SPX_OT_SyncMMDPhysics(Operator):
    bl_idname = "surface_proxy.sync_mmd_physics"
    bl_label = "同步当前代理刚体和 Joint"
    bl_description = "只按当前代理骨骼更新其关联刚体和 Joint 的位置与旋转，不修改形状、类型、尺寸或物理参数"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            rigid_count, joint_count = sync_proxy_physics_transforms(
                _selected_proxy(context, settings)
            )
        except (ProxyBuildError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"已同步当前代理的 {rigid_count} 个刚体、{joint_count} 个 Joint",
        )
        return {"FINISHED"}


class SPX_OT_RefreshMMDBrowser(Operator):
    bl_idname = "surface_proxy.refresh_mmd_browser"
    bl_label = "刷新模型列表"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        checked = {
            (item.kind, item.target_name)
            for item in settings.browser_items
            if item.selected
        }
        settings.mmd_root = root
        settings.browser_items.clear()
        armature = FnModel.find_armature_object(root)
        proxy = settings.physics_proxy if settings.browser_current_proxy_only else None
        proxy_objects = set(_proxy_physics_objects(proxy)) if proxy is not None else None
        proxy_bones = None
        if proxy is not None:
            try:
                proxy_armature = _proxy_armature(proxy)
                prefix, row_counts = _proxy_structure(proxy, proxy_armature)
            except ProxyBuildError as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            proxy_bones = {
                proxy_bone_name(proxy, prefix, column, row)
                for column, count in enumerate(row_counts)
                for row in range(count - 1)
            }
        if settings.browser_kind == "BONE" and armature is not None:
            bones = [
                bone
                for bone in armature.pose.bones
                if not getattr(bone, "is_mmd_shadow_bone", False)
            ]
            bones.sort(
                key=lambda bone: (
                    bone.mmd_bone.bone_id
                    if bone.mmd_bone.bone_id >= 0
                    else float("inf"),
                    bone.name,
                )
            )
            for order_index, pose_bone in enumerate(bones):
                bone = pose_bone.bone
                if proxy_bones is not None and bone.name not in proxy_bones:
                    continue
                item = settings.browser_items.add()
                item.kind = "BONE"
                item.target_name = bone.name
                item.label = bone.name
                item.detail = bone.parent.name if bone.parent else "根骨"
                item.armature_name = armature.name
                item.order_index = order_index
                item.selected = (item.kind, item.target_name) in checked
        elif settings.browser_kind == "RIGID":
            rigids = sorted(
                FnModel.iterate_rigid_body_objects(root),
                key=lambda rigid: rigid.name,
            )
            for order_index, rigid in enumerate(rigids):
                if proxy_objects is not None and rigid not in proxy_objects:
                    continue
                item = settings.browser_items.add()
                item.kind = "RIGID"
                item.target_name = rigid.name
                item.label = rigid.mmd_rigid.name_j or rigid.name
                item.detail = (
                    f"骨骼: {rigid.mmd_rigid.bone or '-'} | "
                    f"组 {int(rigid.mmd_rigid.collision_group_number) + 1}"
                )
                item.order_index = order_index
                item.selected = (item.kind, item.target_name) in checked
        else:
            joints = sorted(
                FnModel.iterate_joint_objects(root),
                key=lambda joint: joint.name,
            )
            for order_index, joint in enumerate(joints):
                if proxy_objects is not None and joint not in proxy_objects:
                    continue
                item = settings.browser_items.add()
                item.kind = "JOINT"
                item.target_name = joint.name
                item.label = joint.mmd_joint.name_j or joint.name
                constraint = joint.rigid_body_constraint
                first = constraint.object1.name if constraint and constraint.object1 else "-"
                second = constraint.object2.name if constraint and constraint.object2 else "-"
                item.detail = f"{first} ↔ {second}"
                item.order_index = order_index
                item.selected = (item.kind, item.target_name) in checked
        settings.browser_index = min(
            settings.browser_index,
            max(len(settings.browser_items) - 1, 0),
        )
        return {"FINISHED"}


class SPX_OT_SelectMMDItem(Operator):
    bl_idname = "surface_proxy.select_mmd_item"
    bl_label = "选择 MMD 项目"

    kind: StringProperty()
    target_name: StringProperty()
    armature_name: StringProperty()
    extend: BoolProperty(default=False, options={"HIDDEN"})

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not self.extend:
            bpy.ops.object.select_all(action="DESELECT")
        if self.kind == "BONE":
            armature = bpy.data.objects.get(self.armature_name)
            if armature is None or self.target_name not in armature.data.bones:
                return {"CANCELLED"}
            armature.hide_set(False)
            armature.select_set(True)
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="POSE")
            if not self.extend:
                for bone in armature.data.bones:
                    bone.select = False
            bone = armature.data.bones[self.target_name]
            bone.select = True
            armature.data.bones.active = bone
        else:
            obj = bpy.data.objects.get(self.target_name)
            if obj is None:
                return {"CANCELLED"}
            obj.hide_set(False)
            obj.hide_select = False
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return {"FINISHED"}


def _checked_items(settings, kind=None):
    return [
        item
        for item in settings.browser_items
        if item.selected and (kind is None or item.kind == kind)
    ]


class SPX_OT_SetMMDBrowserChecks(Operator):
    bl_idname = "surface_proxy.set_mmd_browser_checks"
    bl_label = "设置批量勾选"

    action: EnumProperty(
        items=(("ALL", "全选", ""), ("NONE", "全不选", ""), ("INVERT", "反选", ""))
    )

    def execute(self, context):
        items = context.scene.surface_proxy_creator.browser_items
        for item in items:
            if self.action == "ALL":
                item.selected = True
            elif self.action == "NONE":
                item.selected = False
            else:
                item.selected = not item.selected
        return {"FINISHED"}


def _active_browser_item(settings):
    if not settings.browser_items:
        return None
    index = min(settings.browser_index, len(settings.browser_items) - 1)
    return settings.browser_items[index]


class SPX_OT_QuickCheckMMDGroup(Operator):
    bl_idname = "surface_proxy.quick_check_mmd_group"
    bl_label = "快速选组"

    mode: EnumProperty(
        items=(
            ("PREFIX", "按名称前缀", ""),
            ("BONE_BRANCH", "已勾选骨骼及子级", ""),
            ("BONE_COLUMN", "同列骨骼", ""),
            ("RIGID_GROUP", "相同碰撞组", ""),
            ("RIGID_TYPE", "相同刚体类型", ""),
            ("CONNECTED", "相连物理组", ""),
        )
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        active = _active_browser_item(settings)
        if active is None:
            return {"CANCELLED"}
        names = set()
        if self.mode == "PREFIX":
            prefix = settings.browser_prefix
            if not prefix:
                self.report({"ERROR"}, "名称前缀不能为空")
                return {"CANCELLED"}
            names = {
                item.target_name
                for item in settings.browser_items
                if item.label.startswith(prefix) or item.target_name.startswith(prefix)
            }
        elif self.mode == "BONE_BRANCH":
            checked = [
                item
                for item in settings.browser_items
                if item.kind == "BONE" and item.selected
            ]
            if not checked:
                self.report({"ERROR"}, "请先勾选至少一根骨骼")
                return {"CANCELLED"}
            branch_keys = set()
            for item in checked:
                armature = bpy.data.objects.get(item.armature_name)
                bone = armature.data.bones.get(item.target_name) if armature else None
                if bone is None:
                    continue
                stack = [bone]
                while stack:
                    current = stack.pop()
                    branch_keys.add((armature.name, current.name))
                    stack.extend(current.children)
            for item in settings.browser_items:
                if (item.armature_name, item.target_name) in branch_keys:
                    item.selected = True
            return {"FINISHED"}
        elif self.mode == "BONE_COLUMN":
            match = re.match(r"^(.*_C\d+)_R\d+$", active.target_name)
            if match is None:
                self.report({"ERROR"}, "当前骨骼名称不包含代理列信息")
                return {"CANCELLED"}
            prefix = match.group(1)
            names = {
                item.target_name
                for item in settings.browser_items
                if item.kind == "BONE" and item.target_name.startswith(prefix + "_R")
            }
        elif self.mode in {"RIGID_GROUP", "RIGID_TYPE"}:
            rigid = bpy.data.objects.get(active.target_name)
            if rigid is None or rigid.mmd_type != "RIGID_BODY":
                return {"CANCELLED"}
            for item in settings.browser_items:
                candidate = bpy.data.objects.get(item.target_name)
                if candidate is None or candidate.mmd_type != "RIGID_BODY":
                    continue
                if self.mode == "RIGID_GROUP":
                    matches = (
                        candidate.mmd_rigid.collision_group_number
                        == rigid.mmd_rigid.collision_group_number
                    )
                else:
                    matches = candidate.mmd_rigid.type == rigid.mmd_rigid.type
                if matches:
                    names.add(item.target_name)
        else:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
            joints = list(FnModel.iterate_joint_objects(root))
            seed_rigids = set()
            if active.kind == "RIGID":
                rigid = bpy.data.objects.get(active.target_name)
                if rigid is not None:
                    seed_rigids.add(rigid)
            elif active.kind == "JOINT":
                joint = bpy.data.objects.get(active.target_name)
                constraint = joint.rigid_body_constraint if joint else None
                if constraint:
                    seed_rigids.update(
                        obj
                        for obj in (constraint.object1, constraint.object2)
                        if obj is not None
                    )
            connected_joints = set()
            pending = list(seed_rigids)
            visited = set(seed_rigids)
            while pending:
                rigid = pending.pop()
                for joint in joints:
                    constraint = joint.rigid_body_constraint
                    ends = {constraint.object1, constraint.object2}
                    if rigid not in ends:
                        continue
                    connected_joints.add(joint)
                    for endpoint in ends:
                        if endpoint is not None and endpoint not in visited:
                            visited.add(endpoint)
                            pending.append(endpoint)
            names = {
                obj.name
                for obj in (visited if active.kind == "RIGID" else connected_joints)
            }
        for item in settings.browser_items:
            if item.target_name in names:
                item.selected = True
        return {"FINISHED"}


class SPX_MT_MMDQuickSelect(Menu):
    bl_label = "快速选组"
    bl_idname = "SPX_MT_mmd_quick_select"

    def draw(self, context):
        layout = self.layout
        kind = context.scene.surface_proxy_creator.browser_kind
        layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="按名称前缀").mode = "PREFIX"
        layout.separator()
        if kind == "BONE":
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="已勾选骨骼及子级").mode = "BONE_BRANCH"
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="同列代理骨骼").mode = "BONE_COLUMN"
        elif kind == "RIGID":
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="相同碰撞组").mode = "RIGID_GROUP"
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="相同刚体类型").mode = "RIGID_TYPE"
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="相连物理组").mode = "CONNECTED"
        else:
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="相连物理组").mode = "CONNECTED"


class SPX_OT_PrefixFromActiveMMDItem(Operator):
    bl_idname = "surface_proxy.prefix_from_active_mmd_item"
    bl_label = "从活动项提取前缀"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        active = _active_browser_item(settings)
        if active is None:
            return {"CANCELLED"}
        label = active.label
        match = re.search(r"\d", label)
        settings.browser_prefix = label[: match.start()] if match else label
        return {"FINISHED"}


class SPX_OT_SelectCheckedMMDItems(Operator):
    bl_idname = "surface_proxy.select_checked_mmd_items"
    bl_label = "将勾选项选入 Blender"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        items = _checked_items(settings, settings.browser_kind)
        if not items:
            self.report({"ERROR"}, "没有勾选项目")
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        if settings.browser_kind == "BONE":
            armature = bpy.data.objects.get(items[0].armature_name)
            if armature is None:
                return {"CANCELLED"}
            armature.hide_set(False)
            armature.select_set(True)
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="POSE")
            for bone in armature.data.bones:
                bone.select = bone.name in {item.target_name for item in items}
            armature.data.bones.active = armature.data.bones.get(items[-1].target_name)
        else:
            active = None
            for item in items:
                obj = bpy.data.objects.get(item.target_name)
                if obj is None:
                    continue
                obj.hide_set(False)
                obj.hide_select = False
                obj.select_set(True)
                active = obj
            context.view_layer.objects.active = active
        return {"FINISHED"}


class SPX_OT_SyncSelectedMMDObjectsToBrowser(Operator):
    bl_idname = "surface_proxy.sync_selected_mmd_objects_to_browser"
    bl_label = "从 3D 视图同步选中项目"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        expected_type = {
            "RIGID": "RIGID_BODY",
            "JOINT": "JOINT",
        }.get(settings.browser_kind)
        if expected_type is None:
            self.report({"ERROR"}, "该入口只处理刚体和 Joint")
            return {"CANCELLED"}
        selected_names = {
            obj.name
            for obj in context.selected_objects
            if obj.mmd_type == expected_type
        }
        if not selected_names:
            label = "刚体" if settings.browser_kind == "RIGID" else "Joint"
            self.report({"ERROR"}, f"3D 视图中没有选中 {label}")
            return {"CANCELLED"}
        active = context.active_object
        active_name = (
            active.name
            if active is not None and active.mmd_type == expected_type
            else None
        )
        bpy.ops.surface_proxy.refresh_mmd_browser()
        active_index = None
        matched = 0
        for index, item in enumerate(settings.browser_items):
            item.selected = item.target_name in selected_names
            if item.selected:
                matched += 1
            if item.target_name == active_name:
                active_index = index
        if active_index is not None:
            settings.browser_index = active_index
        count_label = "个刚体" if settings.browser_kind == "RIGID" else "个 Joint"
        if matched != len(selected_names):
            self.report(
                {"WARNING"},
                f"已同步 {matched}/{len(selected_names)} {count_label}；关闭“仅显示当前代理”可显示其余项目",
            )
        else:
            self.report({"INFO"}, f"已同步 {matched} {count_label} 到查看器")
        return {"FINISHED"}


def _missing_mmd_bone_names(blender_name):
    match = re.match(r"^(.*?)[._]([LR])$", blender_name)
    if match is None:
        return blender_name, blender_name
    base_name, side = match.groups()
    side_prefix = "左" if side == "L" else "右"
    return f"{side_prefix}{base_name}", f"{base_name}_{side}"


class SPX_OT_FillMissingMMDBoneNames(Operator):
    bl_idname = "surface_proxy.fill_missing_mmd_bone_names"
    bl_label = "补全空缺 MMD 名称"
    bl_description = "按 Blender 骨骼名及 .L/.R、_L/_R 侧向后缀补全空缺的 MMD 名称和英文名称，不覆盖已有内容"
    bl_options = {"REGISTER", "UNDO"}

    scope: EnumProperty(
        name="范围",
        items=(
            ("CHECKED", "勾选骨骼", "只处理查看器中已勾选的骨骼"),
            ("ALL", "全部骨骼", "处理当前 MMD 模型的全部骨骼"),
            ("ACTIVE", "活动骨骼", "只处理查看器中的活动骨骼"),
        ),
        default="CHECKED",
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
            armature = FnModel.find_armature_object(root)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if armature is None:
            self.report({"ERROR"}, "当前 MMD 模型没有骨架")
            return {"CANCELLED"}

        if self.scope == "ALL":
            names = {bone.name for bone in armature.pose.bones}
        elif self.scope == "ACTIVE":
            active = _active_browser_item(settings)
            if active is None or active.kind != "BONE":
                self.report({"ERROR"}, "没有活动骨骼")
                return {"CANCELLED"}
            names = {active.target_name}
        else:
            names = {
                item.target_name for item in _checked_items(settings, "BONE")
            }
            if not names:
                self.report({"ERROR"}, "没有勾选骨骼")
                return {"CANCELLED"}

        changed_bones = 0
        changed_fields = 0
        for name in names:
            pose_bone = armature.pose.bones.get(name)
            if pose_bone is None or not hasattr(pose_bone, "mmd_bone"):
                continue
            name_j, name_e = _missing_mmd_bone_names(pose_bone.name)
            changed = False
            if not pose_bone.mmd_bone.name_j.strip():
                pose_bone.mmd_bone.name_j = name_j
                changed = True
                changed_fields += 1
            if not pose_bone.mmd_bone.name_e.strip():
                pose_bone.mmd_bone.name_e = name_e
                changed = True
                changed_fields += 1
            changed_bones += int(changed)
        self.report(
            {"INFO"},
            f"已补全 {changed_bones} 根骨骼的 {changed_fields} 个空缺名称字段",
        )
        return {"FINISHED"}


class SPX_OT_SyncJointNamesFromRigidB(Operator):
    bl_idname = "surface_proxy.sync_joint_names_from_rigid_b"
    bl_label = "同步刚体 B 名称到 Joint"
    bl_description = "纵向和锚定 Joint 直接使用刚体 B 名称；横向 Joint 使用刚体 B 名称加 _H 后缀"
    bl_options = {"REGISTER", "UNDO"}

    scope: EnumProperty(
        name="范围",
        items=(
            ("CHECKED", "勾选 Joint", "只处理查看器中已勾选的 Joint"),
            ("ALL", "全部 Joint", "处理当前 MMD 模型的全部 Joint"),
        ),
        default="CHECKED",
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if self.scope == "ALL":
            joints = list(FnModel.iterate_joint_objects(root))
        else:
            joints = [
                obj
                for item in _checked_items(settings, "JOINT")
                if (obj := bpy.data.objects.get(item.target_name)) is not None
                and obj.mmd_type == "JOINT"
            ]
            if not joints:
                self.report({"ERROR"}, "没有勾选 Joint")
                return {"CANCELLED"}
        changed = 0
        skipped = 0
        renamed = []
        for joint in joints:
            if _sync_joint_name_from_rigid_b(joint):
                changed += 1
                renamed.append(joint)
            else:
                skipped += 1
        bpy.ops.surface_proxy.refresh_mmd_browser()
        renamed_names = {joint.name for joint in renamed}
        for item in settings.browser_items:
            item.selected = item.target_name in renamed_names
        self.report(
            {"INFO"},
            f"已同步 {changed} 个 Joint 名称；跳过 {skipped} 个缺少刚体 B 的 Joint",
        )
        return {"FINISHED"}


def _delete_rigids_and_linked_joints(root, rigids):
    FnModel, _FnRigidBody, _rigid_module = _mmd_api()
    rigid_set = set(rigids)
    joints = [
        joint
        for joint in FnModel.iterate_joint_objects(root)
        if joint.rigid_body_constraint.object1 in rigid_set
        or joint.rigid_body_constraint.object2 in rigid_set
    ]
    for joint in joints:
        bpy.data.objects.remove(joint, do_unlink=True)
    for rigid in rigids:
        bpy.data.objects.remove(rigid, do_unlink=True)
    return len(rigids), len(joints)


class SPX_OT_DeleteCheckedMMDItems(Operator):
    bl_idname = "surface_proxy.delete_checked_mmd_items"
    bl_label = "删除勾选项"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, _event):
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _resolve_root(context, settings.mmd_root)
        items = _checked_items(settings, settings.browser_kind)
        if not items:
            self.report({"ERROR"}, "没有勾选项目")
            return {"CANCELLED"}
        if settings.browser_kind == "BONE":
            self.report({"ERROR"}, "骨骼请使用“清理勾选骨骼”并指定权重归并骨骼")
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if settings.browser_kind == "RIGID":
            rigids = [
                obj
                for obj in (bpy.data.objects.get(item.target_name) for item in items)
                if obj is not None and obj.mmd_type == "RIGID_BODY"
            ]
            rigid_count, joint_count = _delete_rigids_and_linked_joints(root, rigids)
        else:
            joints = [
                obj
                for obj in (bpy.data.objects.get(item.target_name) for item in items)
                if obj is not None and obj.mmd_type == "JOINT"
            ]
            for joint in joints:
                bpy.data.objects.remove(joint, do_unlink=True)
            rigid_count, joint_count = 0, len(joints)
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report({"INFO"}, f"已删除 {rigid_count} 个刚体、{joint_count} 个 Joint")
        return {"FINISHED"}


def _merge_bone_weights(root, source_names, target_name):
    FnModel, _FnRigidBody, _rigid_module = _mmd_api()
    vertex_count = 0
    mesh_count = 0
    mesh_objects = [
        obj
        for obj in FnModel.iterate_child_objects(root)
        if obj.type == "MESH" and obj.mmd_type != "RIGID_BODY"
    ]
    for mesh_object in mesh_objects:
        source_groups = [
            mesh_object.vertex_groups.get(name)
            for name in source_names
            if mesh_object.vertex_groups.get(name) is not None
        ]
        if not source_groups:
            continue
        target_group = mesh_object.vertex_groups.get(target_name)
        if target_group is None:
            target_group = mesh_object.vertex_groups.new(name=target_name)
        source_indices = {group.index for group in source_groups}
        changed = 0
        for vertex in mesh_object.data.vertices:
            weight = sum(
                membership.weight
                for membership in vertex.groups
                if membership.group in source_indices
            )
            if weight > 0.0:
                target_group.add([vertex.index], weight, "ADD")
                changed += 1
        for group in source_groups:
            mesh_object.vertex_groups.remove(group)
        if changed:
            mesh_count += 1
            vertex_count += changed
    return mesh_count, vertex_count


class SPX_OT_CleanupCheckedBones(Operator):
    bl_idname = "surface_proxy.cleanup_checked_bones"
    bl_label = "清理勾选骨骼"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, _event):
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _resolve_root(context, settings.mmd_root)
        FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        armature = FnModel.find_armature_object(root)
        selected_names = {
            item.target_name for item in _checked_items(settings, "BONE")
        }
        target_name = settings.cleanup_root_bone.strip()
        if not selected_names:
            self.report({"ERROR"}, "没有勾选骨骼")
            return {"CANCELLED"}
        if armature is None or target_name not in armature.data.bones:
            self.report({"ERROR"}, "请选择有效的权重归并骨骼")
            return {"CANCELLED"}
        selected_names.intersection_update(armature.data.bones.keys())
        if target_name in selected_names:
            self.report({"ERROR"}, "权重归并骨骼不能同时被清理")
            return {"CANCELLED"}
        ancestor = armature.data.bones[target_name].parent
        while ancestor is not None:
            if ancestor.name in selected_names:
                self.report({"ERROR"}, "权重归并骨骼不能位于待清理骨骼的子级")
                return {"CANCELLED"}
            ancestor = ancestor.parent

        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        mesh_count, vertex_count = _merge_bone_weights(
            root,
            selected_names,
            target_name,
        )
        rigids = [
            rigid
            for rigid in FnModel.iterate_rigid_body_objects(root)
            if rigid.mmd_rigid.bone in selected_names
        ]
        rigid_count, joint_count = _delete_rigids_and_linked_joints(root, rigids)

        bpy.ops.object.select_all(action="DESELECT")
        armature.hide_set(False)
        armature.select_set(True)
        context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode="EDIT")
        target = armature.data.edit_bones.get(target_name)
        for edit_bone in list(armature.data.edit_bones):
            if (
                edit_bone.name not in selected_names
                and edit_bone.parent is not None
                and edit_bone.parent.name in selected_names
            ):
                edit_bone.parent = target
                edit_bone.use_connect = False
        for name in selected_names:
            edit_bone = armature.data.edit_bones.get(name)
            if edit_bone is not None:
                armature.data.edit_bones.remove(edit_bone)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report(
            {"INFO"},
            f"已清理 {len(selected_names)} 根骨骼；{mesh_count} 个 Mesh 的 {vertex_count} 个顶点权重归并到 {target_name}；删除 {rigid_count} 个刚体、{joint_count} 个 Joint",
        )
        return {"FINISHED"}


def _browser_kind_changed(settings, _context):
    settings.browser_items.clear()
    if settings.mmd_root is not None:
        try:
            bpy.ops.surface_proxy.refresh_mmd_browser()
        except RuntimeError:
            pass


def _get_collision_group_display(settings):
    return int(settings.collision_group_number) + 1


def _set_collision_group_display(settings, value):
    settings.collision_group_number = max(0, min(15, int(value) - 1))


def _get_block_same_collision_group(settings):
    index = int(settings.collision_group_number)
    return bool(settings.collision_group_mask[index])


def _set_block_same_collision_group(settings, value):
    index = int(settings.collision_group_number)
    mask = list(settings.collision_group_mask)
    mask[index] = bool(value)
    settings.collision_group_mask = mask


def register_settings(cls):
    rigid_types = (("0", "跟随骨骼", ""), ("1", "物理", ""), ("2", "物理 + 骨骼", ""))
    properties = {}
    properties["physics_tab"] = EnumProperty(
        name="设定页",
        items=(
            ("BASIC", "基本", "模型与生成入口"),
            ("RIGID", "刚体", "刚体形状、碰撞和动力学参数"),
            ("VERTICAL", "纵 Joint", "纵向 Joint 参数"),
            ("HORIZONTAL", "横 Joint", "横向 Joint 参数"),
        ),
        default="BASIC",
    )
    properties["mmd_root"] = bpy.props.PointerProperty(
        name="MMD 模型",
        type=bpy.types.Object,
        poll=lambda _self, obj: getattr(obj, "mmd_type", "") == "ROOT",
    )
    properties["physics_proxy"] = bpy.props.PointerProperty(
        name="当前代理网格",
        description="生成、参数应用和自动同步只处理这个代理及其关联刚体与 Joint",
        type=bpy.types.Object,
        poll=_proxy_poll,
        update=_physics_proxy_changed,
    )
    properties["auto_sync_physics"] = BoolProperty(
        name="骨骼变动后自动同步刚体与 Joint",
        description="退出骨架 Edit Mode 或同步代理骨骼后，只更新当前代理关联的物理对象",
        default=True,
    )
    properties["rigid_shape"] = EnumProperty(
        name="刚体形状",
        items=(("SPHERE", "球体", ""), ("BOX", "盒体", ""), ("CAPSULE", "胶囊", "")),
        default="BOX",
    )
    properties["top_rigid_type"] = EnumProperty(
        name="顶层类型",
        description="每列第一层刚体的类型",
        items=rigid_types,
        default="2",
    )
    properties["body_rigid_type"] = EnumProperty(
        name="下层类型",
        description="每列第一层以下所有刚体的类型",
        items=rigid_types,
        default="1",
    )
    properties["rigid_radius_ratio"] = FloatProperty(
        name="宽度 / 骨长",
        description="0 时按相邻列最大间距自动计算，并保留横向搭接",
        default=0.0,
        min=0.0,
        max=2.0,
        precision=4,
    )
    properties["rigid_length_ratio"] = FloatProperty(
        name="高度 / 骨长",
        description="0 时自动超出骨段两端，与上下刚体搭接",
        default=0.0,
        min=0.0,
        max=2.0,
        precision=4,
    )
    properties["rigid_depth_ratio"] = FloatProperty(
        name="深度 / 骨长",
        description="0 时按局部单元宽度与高度自动计算覆盖厚度",
        default=0.0,
        min=0.0,
        max=2.0,
        precision=4,
    )
    properties["rigid_radius_multiply"] = BoolProperty(
        name="宽度倍加",
        description="将宽度计算结果乘以 2",
    )
    properties["rigid_length_multiply"] = BoolProperty(
        name="高度倍加",
        description="将高度计算结果乘以 2",
    )
    properties["mass"] = FloatProperty(name="质量", default=0.0, min=0.0, precision=4)
    properties["friction"] = FloatProperty(
        name="摩擦", default=0.0, min=0.0, max=1.0, precision=4
    )
    properties["restitution"] = FloatProperty(
        name="弹性", default=0.0, min=0.0, max=1.0, precision=4
    )
    properties["linear_damping"] = FloatProperty(
        name="移动阻尼", default=0.0, min=0.0, max=1.0, precision=4
    )
    properties["angular_damping"] = FloatProperty(
        name="旋转阻尼", default=0.0, min=0.0, max=1.0, precision=4
    )
    properties["collision_group_number"] = IntProperty(name="碰撞组", default=0, min=0, max=15)
    properties["collision_group_display"] = IntProperty(
        name="碰撞组",
        description="显示为 1–16；内部 MMD 索引仍为 0–15",
        min=1,
        max=16,
        get=_get_collision_group_display,
        set=_set_collision_group_display,
    )
    properties["collision_group_mask"] = bpy.props.BoolVectorProperty(name="不碰撞组", size=16, subtype="LAYER")
    properties["block_same_collision_group"] = BoolProperty(
        name="屏蔽同组碰撞",
        description="把当前碰撞组同时加入不碰撞组，避免同组刚体互相碰撞",
        get=_get_block_same_collision_group,
        set=_set_block_same_collision_group,
    )
    properties["create_horizontal_joints"] = BoolProperty(name="生成横向 Joint", default=True)
    properties["limit_linear_lower"] = FloatVectorProperty(
        name="移动下限", size=3, subtype="XYZ", precision=4
    )
    properties["limit_linear_upper"] = FloatVectorProperty(
        name="移动上限", size=3, subtype="XYZ", precision=4
    )
    properties["limit_angular_lower"] = FloatVectorProperty(
        name="旋转下限",
        size=3,
        subtype="EULER",
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    properties["limit_angular_upper"] = FloatVectorProperty(
        name="旋转上限",
        size=3,
        subtype="EULER",
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    properties["spring_linear"] = FloatVectorProperty(
        name="移动弹簧", size=3, subtype="XYZ", min=0.0, precision=4
    )
    properties["spring_angular"] = FloatVectorProperty(
        name="旋转弹簧",
        size=3,
        subtype="XYZ",
        min=0.0,
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    properties["horizontal_limit_linear_lower"] = FloatVectorProperty(
        name="移动下限",
        size=3,
        subtype="XYZ",
        precision=4,
    )
    properties["horizontal_limit_linear_upper"] = FloatVectorProperty(
        name="移动上限",
        size=3,
        subtype="XYZ",
        precision=4,
    )
    properties["horizontal_limit_angular_lower"] = FloatVectorProperty(
        name="旋转下限",
        size=3,
        subtype="EULER",
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    properties["horizontal_limit_angular_upper"] = FloatVectorProperty(
        name="旋转上限",
        size=3,
        subtype="EULER",
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    properties["horizontal_spring_linear"] = FloatVectorProperty(
        name="移动弹簧",
        size=3,
        subtype="XYZ",
        min=0.0,
        precision=4,
    )
    properties["horizontal_spring_angular"] = FloatVectorProperty(
        name="旋转弹簧",
        size=3,
        subtype="XYZ",
        min=0.0,
        default=(0.0, 0.0, 0.0),
        precision=4,
    )
    scalar_interpolation = (
        ("rigid_radius_ratio", 0.0, 0.0, 2.0),
        ("rigid_length_ratio", 0.0, 0.0, 2.0),
        ("rigid_depth_ratio", 0.0, 0.0, 2.0),
        ("mass", 0.0, 0.0, None),
        ("linear_damping", 0.0, 0.0, 1.0),
        ("angular_damping", 0.0, 0.0, 1.0),
        ("restitution", 0.0, 0.0, 1.0),
        ("friction", 0.0, 0.0, 1.0),
    )
    for name, default, minimum, maximum in scalar_interpolation:
        properties[f"{name}_interpolate"] = BoolProperty(name="线性补间")
        arguments = {"name": "末端值", "default": default, "min": minimum}
        if maximum is not None:
            arguments["max"] = maximum
        arguments["precision"] = 4
        properties[f"{name}_end"] = FloatProperty(**arguments)
    vector_interpolation = (
        ("limit_linear_lower", "XYZ", (0.0, 0.0, 0.0), None),
        ("limit_linear_upper", "XYZ", (0.0, 0.0, 0.0), None),
        ("limit_angular_lower", "EULER", (0.0, 0.0, 0.0), None),
        ("limit_angular_upper", "EULER", (0.0, 0.0, 0.0), None),
        ("spring_linear", "XYZ", (0.0, 0.0, 0.0), 0.0),
        ("spring_angular", "XYZ", (0.0, 0.0, 0.0), 0.0),
        ("horizontal_limit_linear_lower", "XYZ", (0.0, 0.0, 0.0), None),
        ("horizontal_limit_linear_upper", "XYZ", (0.0, 0.0, 0.0), None),
        (
            "horizontal_limit_angular_lower",
            "EULER",
            (0.0, 0.0, 0.0),
            None,
        ),
        (
            "horizontal_limit_angular_upper",
            "EULER",
            (0.0, 0.0, 0.0),
            None,
        ),
        ("horizontal_spring_linear", "XYZ", (0.0, 0.0, 0.0), 0.0),
        ("horizontal_spring_angular", "XYZ", (0.0, 0.0, 0.0), 0.0),
    )
    for name, subtype, default, minimum in vector_interpolation:
        arguments = {
            "name": "末端值",
            "size": 3,
            "subtype": subtype,
            "default": default,
            "precision": 4,
        }
        if minimum is not None:
            arguments["min"] = minimum
        properties[f"{name}_end"] = FloatVectorProperty(**arguments)
    for name in JOINT_INTERPOLATION_NAMES:
        properties[f"{name}_interpolate"] = bpy.props.BoolVectorProperty(
            name="线性补间",
            size=3,
        )
    for name in ADAPTIVE_SCALAR_NAMES:
        properties[_adaptive_scalar_property_name(name)] = StringProperty(
            name="数值",
            description="默认显示两位小数，按实际输入最多显示四位",
            get=_adaptive_scalar_getter(name),
            set=_adaptive_scalar_setter(name),
            options={"SKIP_SAVE"},
        )
    for name in ADAPTIVE_VECTOR_NAMES:
        angle = name in ANGLE_VECTOR_NAMES
        for index in range(3):
            properties[_adaptive_vector_property_name(name, index)] = StringProperty(
                name="数值",
                description="默认显示两位小数，按实际输入最多显示四位",
                get=_adaptive_vector_getter(name, index, angle),
                set=_adaptive_vector_setter(name, index, angle),
                options={"SKIP_SAVE"},
            )
    properties["browser_kind"] = EnumProperty(
        name="查看类型",
        items=(("BONE", "骨骼", ""), ("RIGID", "刚体", ""), ("JOINT", "Joint", "")),
        default="BONE",
        update=_browser_kind_changed,
    )
    properties["browser_current_proxy_only"] = BoolProperty(
        name="仅显示当前代理",
        description="只列出当前代理对应的骨骼、刚体或 Joint",
        default=False,
        update=_browser_kind_changed,
    )
    properties["browser_search"] = StringProperty(name="搜索")
    properties["mirror_include_joints"] = BoolProperty(
        name="同时处理关联 Joint",
        description="创建或同步勾选刚体的镜像对象时，同时处理端点可解析的关联 Joint",
        default=True,
    )
    properties["browser_prefix"] = StringProperty(
        name="名称前缀",
        description="按可见名称或 Blender 对象名的开头批量勾选",
    )
    properties["browser_items"] = CollectionProperty(type=SPX_MMD_BrowserItem)
    properties["browser_index"] = IntProperty(default=0, min=0)
    properties["cleanup_root_bone"] = StringProperty(
        name="权重归并骨骼",
        description="清理勾选骨骼前，将这些骨骼的全部顶点组权重归并到此骨骼",
    )
    cls.__annotations__.update(properties)


def _draw_numbered_collision_mask(layout, data, property_name):
    layout.label(text="不碰撞组")
    for start in (0, 8):
        row = layout.row(align=True)
        for index in range(start, start + 8):
            row.prop(
                data,
                property_name,
                index=index,
                text=str(index + 1),
                toggle=True,
            )


def _interpolation_grid(layout, columns):
    return layout.grid_flow(
        row_major=True,
        columns=columns,
        even_columns=True,
        even_rows=True,
        align=True,
    )


def _centered_cell(grid):
    cell = grid.row(align=True)
    cell.alignment = "CENTER"
    return cell


def _centered_label(grid, text):
    _centered_cell(grid).label(text=text)


def _centered_checkbox(grid, settings, name, index=None):
    cell = _centered_cell(grid)
    arguments = {"text": ""}
    if index is not None:
        arguments["index"] = index
    cell.prop(settings, name, **arguments)


def _draw_interpolation_header(layout):
    grid = _interpolation_grid(layout, 4)
    for text in ("参数", "起始值", "补间", "末端值"):
        _centered_label(grid, text)


def _draw_scalar_interpolation(layout, settings, name, label):
    grid = _interpolation_grid(layout, 4)
    grid.label(text=label)
    grid.prop(settings, _adaptive_scalar_property_name(name), text="")
    _centered_checkbox(grid, settings, f"{name}_interpolate")
    end = grid.row(align=True)
    end.enabled = getattr(settings, f"{name}_interpolate")
    end.prop(settings, _adaptive_scalar_property_name(f"{name}_end"), text="")


def _draw_size_interpolation(
    layout,
    settings,
    name,
    label,
    multiply_name=None,
):
    grid = _interpolation_grid(layout, 5)
    if multiply_name is None:
        grid.label(text="")
    else:
        _centered_checkbox(grid, settings, multiply_name)
    grid.label(text=label)
    grid.prop(settings, _adaptive_scalar_property_name(name), text="")
    _centered_checkbox(grid, settings, f"{name}_interpolate")
    end = grid.row(align=True)
    end.enabled = getattr(settings, f"{name}_interpolate")
    end.prop(settings, _adaptive_scalar_property_name(f"{name}_end"), text="")


def _draw_limit_interpolation(layout, settings, prefix, name, label):
    group = layout.box()
    group.label(text=label)
    lower_name = f"{prefix}{name}_lower"
    upper_name = f"{prefix}{name}_upper"
    interpolation_name = f"{prefix}{name}_interpolate"
    enabled = getattr(settings, interpolation_name)
    grid = _interpolation_grid(group, 6)
    for text in ("轴", "起始下限", "起始上限", "补间", "末端下限", "末端上限"):
        _centered_label(grid, text)
    for index, axis in enumerate("XYZ"):
        grid.label(text=axis)
        grid.prop(
            settings, _adaptive_vector_property_name(lower_name, index), text=""
        )
        grid.prop(
            settings, _adaptive_vector_property_name(upper_name, index), text=""
        )
        _centered_checkbox(grid, settings, interpolation_name, index=index)
        lower_end = grid.row(align=True)
        lower_end.enabled = enabled[index]
        lower_end.prop(
            settings,
            _adaptive_vector_property_name(f"{lower_name}_end", index),
            text="",
        )
        upper_end = grid.row(align=True)
        upper_end.enabled = enabled[index]
        upper_end.prop(
            settings,
            _adaptive_vector_property_name(f"{upper_name}_end", index),
            text="",
        )


def _draw_spring_interpolation(layout, settings, name, label):
    group = layout.box()
    group.label(text=label)
    enabled = getattr(settings, f"{name}_interpolate")
    grid = _interpolation_grid(group, 4)
    for text in ("轴", "起始值", "补间", "末端值"):
        _centered_label(grid, text)
    for index, axis in enumerate("XYZ"):
        grid.label(text=axis)
        grid.prop(settings, _adaptive_vector_property_name(name, index), text="")
        _centered_checkbox(grid, settings, f"{name}_interpolate", index=index)
        end = grid.row(align=True)
        end.enabled = enabled[index]
        end.prop(
            settings,
            _adaptive_vector_property_name(f"{name}_end", index),
            text="",
        )


def _draw_joint_settings(layout, settings, prefix):
    _draw_limit_interpolation(layout, settings, prefix, "limit_linear", "移动限制")
    _draw_limit_interpolation(layout, settings, prefix, "limit_angular", "旋转限制")
    _draw_spring_interpolation(
        layout, settings, f"{prefix}spring_linear", "移动弹簧"
    )
    _draw_spring_interpolation(
        layout, settings, f"{prefix}spring_angular", "旋转弹簧"
    )


def _draw_proxy_creator_settings(layout, settings, context):
    creator = layout.box()
    creator.label(text="代理创建", icon="MOD_CLOTH")
    topology = creator.row(align=True)
    topology.prop(settings, "topology", expand=True)
    dimensions = creator.row(align=True)
    dimensions.prop(settings, "columns")
    dimensions.prop(settings, "rows")
    creator.prop(settings, "prefix")
    creator.label(text="名称以左/右开头：双侧同 Mesh 镜像模式", icon="MOD_MIRROR")
    creator.prop(settings, "radial_offset")
    creator.prop(settings, "armature")
    if settings.armature is not None:
        creator.prop_search(
            settings,
            "parent_bone",
            settings.armature.data,
            "bones",
        )
    else:
        creator.prop(settings, "parent_bone")
    creator.prop(settings, "write_weights")
    creator.operator("surface_proxy.create_skirt_proxy", icon="MOD_CLOTH")
    if settings.columns == 1:
        creator.label(text="单列模式：生成可雕刻控制带，物理仍为一列", icon="INFO")
        creator.label(text="雕刻时请保持动态拓扑关闭", icon="INFO")
    elif settings.topology == "CLOSED" and settings.columns < 3:
        creator.label(text="闭合代理面至少需要 3 列", icon="ERROR")
    if context is not None and (
        context.edit_object is None or context.edit_object.type != "MESH"
    ):
        creator.label(text="请在 Mesh Edit Mode 中选择裙子顶点", icon="INFO")

    editor = layout.box()
    editor.label(text="代理编辑", icon="EDITMODE_HLT")
    editor.prop(settings, "auto_sync")
    editor.operator("surface_proxy.sync_proxy_bones", icon="ARMATURE_DATA")
    editor.operator("surface_proxy.rebind_proxy_weights", icon="MOD_VERTEX_WEIGHT")
    editor.operator("surface_proxy.identify_proxy", icon="FILE_REFRESH")
    if not bpy.app.background:
        from . import sync as proxy_sync

        if proxy_sync._DRAW_HANDLE is None:
            editor.label(text="蓝线绘制服务未注册，请 Reload Scripts", icon="ERROR")
        if not bpy.app.timers.is_registered(proxy_sync._sync_on_proxy_mode_exit):
            editor.label(text="自动同步服务未注册，请 Reload Scripts", icon="ERROR")
    proxy_object = settings.physics_proxy
    if proxy_object is not None:
        sync_error = str(proxy_object.get("surface_proxy_sync_error", ""))
        if sync_error:
            editor.label(text=f"自动同步失败：{sync_error}", icon="ERROR")


def draw_physics_settings(layout, settings, context=None):
    box = layout.box()
    box.label(text="MMD 刚体与 Joint")
    box.prop(settings, "mmd_root")
    box.prop(settings, "physics_proxy")
    tabs = box.row(align=True)
    tabs.prop(settings, "physics_tab", expand=True)
    presets = box.box()
    presets.label(text="物理参数预设", icon="PRESET")
    presets.operator(
        SPX_OT_ApplyStableLongSkirtPreset.bl_idname,
        text="填入：稳定中长裙",
        icon="IMPORT",
    )
    preset_row = presets.row(align=True)
    preset_row.menu(
        SPX_MT_PhysicsPresets.bl_idname,
        text=SPX_MT_PhysicsPresets.bl_label,
    )
    preset_row.operator(SPX_OT_AddPhysicsPreset.bl_idname, text="", icon="ADD")
    remove = preset_row.row(align=True)
    remove.enabled = SPX_MT_PhysicsPresets.bl_label != "自定义预设"
    operator = remove.operator(
        SPX_OT_AddPhysicsPreset.bl_idname,
        text="",
        icon="REMOVE",
    )
    operator.remove_active = True
    presets.label(text="预设只填入面板；点击底部“应用参数”后才更新当前代理", icon="INFO")
    page = box.column()
    if settings.physics_tab == "BASIC":
        _draw_proxy_creator_settings(page, settings, context)
        sync = page.box()
        sync.label(text="刚体与 Joint 同步", icon="PHYSICS")
        sync.prop(settings, "auto_sync_physics")
        sync.operator(SPX_OT_SyncMMDPhysics.bl_idname, icon="FILE_REFRESH")
        sync.label(text="同步只更新刚体与 Joint 的位置、旋转，不修改形状、类型或尺寸", icon="INFO")
        sync.label(text="参数在对应页签修改后，点击底部“应用参数到当前代理”", icon="INFO")
    elif settings.physics_tab == "RIGID":
        shape = page.box()
        shape.label(text="形状与类型", icon="MESH_UVSPHERE")
        row = shape.row(align=True)
        row.prop(settings, "rigid_shape")
        row.prop(settings, "top_rigid_type")
        row.prop(settings, "body_rigid_type")
        size = page.box()
        size.label(text="尺寸", icon="DRIVER_DISTANCE")
        size.label(text="尺寸值为 0 时按代理单元自动适配；非 0 时按骨长比例覆盖", icon="INFO")
        header = _interpolation_grid(size, 5)
        for text in ("倍加", "参数", "起始值", "补间", "末端值"):
            _centered_label(header, text)
        _draw_size_interpolation(
            size,
            settings,
            "rigid_radius_ratio",
            "宽度 / 骨长",
            "rigid_radius_multiply",
        )
        _draw_size_interpolation(
            size,
            settings,
            "rigid_length_ratio",
            "高度 / 骨长",
            "rigid_length_multiply",
        )
        _draw_size_interpolation(
            size, settings, "rigid_depth_ratio", "深度 / 骨长"
        )
        dynamics = page.box()
        dynamics.label(text="物理演算参数", icon="PHYSICS")
        _draw_interpolation_header(dynamics)
        _draw_scalar_interpolation(dynamics, settings, "mass", "质量")
        _draw_scalar_interpolation(
            dynamics, settings, "linear_damping", "移动阻尼"
        )
        _draw_scalar_interpolation(
            dynamics, settings, "angular_damping", "旋转阻尼"
        )
        _draw_scalar_interpolation(dynamics, settings, "restitution", "弹性")
        _draw_scalar_interpolation(dynamics, settings, "friction", "摩擦")
        collision = page.box()
        collision.label(text="碰撞", icon="MOD_PHYSICS")
        collision.prop(settings, "collision_group_display")
        collision.prop(settings, "block_same_collision_group")
        _draw_numbered_collision_mask(
            collision, settings, "collision_group_mask"
        )
    elif settings.physics_tab == "VERTICAL":
        _draw_joint_settings(page, settings, "")
    else:
        page.prop(settings, "create_horizontal_joints")
        horizontal = page.column()
        horizontal.enabled = settings.create_horizontal_joints
        _draw_joint_settings(horizontal, settings, "horizontal_")
    row = box.row(align=True)
    row.operator("surface_proxy.create_mmd_physics", icon="PHYSICS")
    row.operator("surface_proxy.update_mmd_physics", icon="FILE_REFRESH")


def draw_browser(layout, settings):
    layout.prop(settings, "mmd_root")
    layout.prop(settings, "physics_proxy", text="代理范围")
    layout.prop(settings, "browser_current_proxy_only")
    row = layout.row(align=True)
    row.prop(settings, "browser_kind", expand=True)
    row.operator("surface_proxy.refresh_mmd_browser", text="", icon="FILE_REFRESH")
    layout.prop(settings, "browser_search", icon="VIEWZOOM")
    row = layout.row(align=True)
    row.prop(settings, "browser_prefix")
    row.operator(
        SPX_OT_PrefixFromActiveMMDItem.bl_idname,
        text="",
        icon="EYEDROPPER",
    )
    layout.template_list(
        "SPX_UL_MMDItems",
        "",
        settings,
        "browser_items",
        settings,
        "browser_index",
        rows=10,
    )
    selected_count = len(_checked_items(settings, settings.browser_kind))
    layout.label(
        text=f"当前列表：{len(settings.browser_items)} 项；已勾选：{selected_count} 项"
    )
    row = layout.row(align=True)
    operator = row.operator(
        SPX_OT_SetMMDBrowserChecks.bl_idname,
        text="全选",
    )
    operator.action = "ALL"
    operator = row.operator(
        SPX_OT_SetMMDBrowserChecks.bl_idname,
        text="全不选",
    )
    operator.action = "NONE"
    operator = row.operator(
        SPX_OT_SetMMDBrowserChecks.bl_idname,
        text="反选",
    )
    operator.action = "INVERT"
    row.menu(SPX_MT_MMDQuickSelect.bl_idname, text="快速选组", icon="GROUP_BONE")
    draw_mmd_ordering(layout, settings)
    row = layout.row(align=True)
    row.operator(
        SPX_OT_SelectCheckedMMDItems.bl_idname,
        icon="RESTRICT_SELECT_OFF",
    )
    if settings.browser_kind != "BONE":
        row.operator(
            SPX_OT_DeleteCheckedMMDItems.bl_idname,
            icon="TRASH",
        )
        object_label = "刚体" if settings.browser_kind == "RIGID" else "Joint"
        layout.operator(
            SPX_OT_SyncSelectedMMDObjectsToBrowser.bl_idname,
            text=f"从 3D 视图同步选中{object_label}",
            icon="UV_SYNC_SELECT",
        )
        draw_mirror_tools(layout, settings)
        if settings.browser_kind == "JOINT":
            names_box = layout.box()
            names_box.label(text="同步刚体 B 名称到 Joint", icon="SORTALPHA")
            names_row = names_box.row(align=True)
            operator = names_row.operator(
                SPX_OT_SyncJointNamesFromRigidB.bl_idname,
                text="同步勾选",
            )
            operator.scope = "CHECKED"
            operator = names_row.operator(
                SPX_OT_SyncJointNamesFromRigidB.bl_idname,
                text="同步全部",
            )
            operator.scope = "ALL"
            names_box.label(text="纵向直接使用刚体 B 名称；横向追加 _H", icon="INFO")
    else:
        layout.operator(
            "surface_proxy.sync_selected_bones_to_browser",
            icon="UV_SYNC_SELECT",
        )
        restore_box = layout.box()
        restore_box.label(text="从勾选骨骼恢复代理", icon="MOD_CLOTH")
        restore_topology = restore_box.row(align=True)
        restore_topology.prop(settings, "topology", expand=True)
        if settings.topology == "OPEN":
            restore_box.prop(settings, "restore_connect_sides")
        restore_box.operator(
            "surface_proxy.restore_proxy_from_checked_bones",
            icon="FILE_REFRESH",
        )
        restore_box.label(text="支持普通、.L/.R 与 _L/_R 父子骨链", icon="INFO")
        draw_bone_physics_creator(layout, settings)
        names_box = layout.box()
        names_box.label(text="补全空缺 MMD 骨骼名称", icon="SORTALPHA")
        names_row = names_box.row(align=True)
        operator = names_row.operator(
            SPX_OT_FillMissingMMDBoneNames.bl_idname,
            text="补全勾选",
        )
        operator.scope = "CHECKED"
        operator = names_row.operator(
            SPX_OT_FillMissingMMDBoneNames.bl_idname,
            text="补全全部",
        )
        operator.scope = "ALL"
        names_box.label(text="只填写空字段，不覆盖已有名称", icon="INFO")
        box = layout.box()
        box.label(text="批量清理骨骼", icon="BONE_DATA")
        root = settings.mmd_root
        armature = None
        if root is not None:
            try:
                FnModel, _FnRigidBody, _rigid_module = _mmd_api()
                armature = FnModel.find_armature_object(root)
            except ProxyBuildError:
                pass
        if armature is not None:
            box.prop_search(
                settings,
                "cleanup_root_bone",
                armature.data,
                "bones",
            )
        else:
            box.prop(settings, "cleanup_root_bone")
        box.operator(
            SPX_OT_CleanupCheckedBones.bl_idname,
            icon="TRASH",
        )
        box.label(text="权重会先归并；绑定刚体和相关 Joint 会一并删除", icon="INFO")
    _draw_active_mmd_inspector(layout, settings)


def _draw_active_mmd_inspector(layout, settings):
    item = _active_browser_item(settings)
    if item is None:
        return
    box = layout.box()
    box.label(text="活动项属性", icon="PROPERTIES")
    if item.kind == "BONE":
        armature = bpy.data.objects.get(item.armature_name)
        pose_bone = armature.pose.bones.get(item.target_name) if armature else None
        if pose_bone is None:
            box.label(text="骨骼已不存在", icon="ERROR")
            return
        box.label(text=f"骨骼：{pose_bone.name}")
        if hasattr(pose_bone, "mmd_bone"):
            box.prop(pose_bone.mmd_bone, "name_j")
            box.prop(pose_bone.mmd_bone, "name_e")
            operator = box.operator(
                SPX_OT_FillMissingMMDBoneNames.bl_idname,
                text="补全当前空缺名称",
                icon="SORTALPHA",
            )
            operator.scope = "ACTIVE"
        box.prop(pose_bone.bone, "use_deform")
        return

    obj = bpy.data.objects.get(item.target_name)
    if obj is None:
        box.label(text="对象已不存在", icon="ERROR")
        return
    if item.kind == "RIGID":
        rigid = obj.mmd_rigid
        box.prop(rigid, "name_j")
        box.prop(rigid, "name_e")
        root = settings.mmd_root
        armature = None
        if root is not None:
            try:
                FnModel, _FnRigidBody, _rigid_module = _mmd_api()
                armature = FnModel.find_armature_object(root)
            except ProxyBuildError:
                pass
        if armature is not None:
            box.prop_search(rigid, "bone", armature.pose, "bones")
        else:
            box.prop(rigid, "bone")
        row = box.row(align=True)
        row.prop(rigid, "type")
        row.prop(rigid, "shape")
        box.prop(rigid, "size")
        box.prop(rigid, "collision_group_number", text="碰撞组（内部 0–15）")
        _draw_numbered_collision_mask(box, rigid, "collision_group_mask")
        body = obj.rigid_body
        if body is not None:
            row = box.row(align=True)
            row.prop(body, "mass")
            row.prop(body, "friction")
            row.prop(body, "restitution")
            row = box.row(align=True)
            row.prop(body, "linear_damping")
            row.prop(body, "angular_damping")
        return

    joint = obj.mmd_joint
    constraint = obj.rigid_body_constraint
    box.prop(joint, "name_j")
    box.prop(joint, "name_e")
    if constraint is None:
        box.label(text="Joint 约束不存在", icon="ERROR")
        return
    row = box.row(align=True)
    row.prop(constraint, "object1", text="刚体 A")
    row.prop(constraint, "object2", text="刚体 B")
    for axis in "xyz":
        row = box.row(align=True)
        row.label(text=f"移动 {axis.upper()}")
        row.prop(constraint, f"limit_lin_{axis}_lower", text="下限")
        row.prop(constraint, f"limit_lin_{axis}_upper", text="上限")
    for axis in "xyz":
        row = box.row(align=True)
        row.label(text=f"旋转 {axis.upper()}")
        row.prop(constraint, f"limit_ang_{axis}_lower", text="下限")
        row.prop(constraint, f"limit_ang_{axis}_upper", text="上限")
    box.prop(joint, "spring_linear")
    box.prop(joint, "spring_angular")


def _draw_mmd_list_context_menu(self, context):
    settings = getattr(context.scene, "surface_proxy_creator", None)
    pointer = getattr(context, "button_pointer", None)
    prop = getattr(context, "button_prop", None)
    if (
        settings is None
        or pointer != settings
        or getattr(prop, "identifier", "") not in {"browser_items", "browser_index"}
    ):
        return
    self.layout.separator()
    self.layout.menu(SPX_MT_MMDQuickSelect.bl_idname, icon="GROUP_BONE")
    self.layout.operator(
        SPX_OT_SelectCheckedMMDItems.bl_idname,
        icon="RESTRICT_SELECT_OFF",
    )
    if settings.browser_kind == "BONE":
        self.layout.operator(SPX_OT_CleanupCheckedBones.bl_idname, icon="TRASH")
    else:
        self.layout.operator(SPX_OT_DeleteCheckedMMDItems.bl_idname, icon="TRASH")


def register_browser_context_menu():
    bpy.types.UI_MT_list_item_context_menu.append(_draw_mmd_list_context_menu)


def unregister_browser_context_menu():
    bpy.types.UI_MT_list_item_context_menu.remove(_draw_mmd_list_context_menu)


CLASSES = (
    SPX_MMD_BrowserItem,
    SPX_UL_MMDItems,
    SPX_OT_CreateMMDPhysics,
    SPX_MT_PhysicsPresets,
    SPX_OT_ApplyStableLongSkirtPreset,
    SPX_OT_AddPhysicsPreset,
    SPX_OT_UpdateMMDPhysics,
    SPX_OT_SyncMMDPhysics,
    SPX_OT_RefreshMMDBrowser,
    SPX_OT_SelectMMDItem,
    SPX_OT_SetMMDBrowserChecks,
    SPX_OT_QuickCheckMMDGroup,
    SPX_OT_PrefixFromActiveMMDItem,
    SPX_MT_MMDQuickSelect,
    SPX_OT_SelectCheckedMMDItems,
    SPX_OT_SyncSelectedMMDObjectsToBrowser,
    SPX_OT_FillMissingMMDBoneNames,
    SPX_OT_SyncJointNamesFromRigidB,
    *MIRROR_PHYSICS_CLASSES,
    SPX_OT_DeleteCheckedMMDItems,
    SPX_OT_CleanupCheckedBones,
)
