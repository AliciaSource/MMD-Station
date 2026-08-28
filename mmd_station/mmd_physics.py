import importlib
import math
import os
import re
import time
import uuid

import bpy
from bpy.app.handlers import persistent
from bl_operators.presets import AddPresetBase
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Menu, Operator, PropertyGroup, UIList
from mathutils import Euler, Matrix, Vector

from .bone_physics_creator import draw as draw_bone_physics_creator
from .collection_organization import place_mmd_objects
from .core import ProxyBuildError, proxy_bone_name
from .mmd_naming import (
    bone_mmd_names,
    normalize_mmd_indices,
    normalized_mmd_names,
    set_ordered_object_name,
    standardized_bone_mmd_names,
)
from .mmd_ordering import draw as draw_mmd_ordering
from .mmd_bone_subdivision import draw as draw_mmd_bone_subdivision
from .mmd_rigid_scale import (
    bake_rigid_object_scale,
    rigid_object_scale_needs_bake,
    rigid_scale_repair_plan,
    rigid_world_scale_is_invalid,
)
from .mmd_material_order import (
    draw_name_sync as draw_material_name_sync,
    material_identity,
    ordered_materials,
    register_export_hook as register_material_export_hook,
)
from .mirror_physics import (
    CLASSES as MIRROR_PHYSICS_CLASSES,
    _find_mirror_joint,
    _find_mirror_rigid,
    _joint_endpoints,
    _side,
    _source_side,
    draw_mirror_tools,
    mirrored_name,
)


PHYSICS_SCHEMA = 1
_BROWSER_AUTO_REFRESH_DELAY = 0.25
_BROWSER_AUTO_REFRESH_DEADLINE = 0.0
_BROWSER_AUTO_REFRESH_DIRTY = False
_BROWSER_AUTO_REFRESH_IN_PROGRESS = False

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

APPLY_PROTECTION_SETTING_NAMES = (
    "protect_apply_location",
    "protect_apply_rotation",
    "protect_apply_joint_location",
    "protect_apply_joint_rotation",
    "protect_apply_shape",
    "protect_apply_size",
    "protect_apply_type",
    "protect_apply_dynamics",
    "protect_apply_collision",
    "protect_apply_joint_parameters",
)

PROXY_PHYSICS_SETTING_NAMES = PHYSICS_SETTING_NAMES + APPLY_PROTECTION_SETTING_NAMES

PHYSICS_PRESET_SUBDIR = "mmd_station/physics"
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
    for name in PROXY_PHYSICS_SETTING_NAMES:
        value = getattr(settings, name)
        if hasattr(value, "to_list"):
            value = value.to_list()
        elif not isinstance(value, (str, int, float, bool)):
            value = list(value)
        proxy_object[_physics_setting_key(name)] = value


def _load_proxy_physics_settings(settings, proxy_object):
    if proxy_object is None:
        return
    for name in PROXY_PHYSICS_SETTING_NAMES:
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
    settings.browser_diagnostics.clear()


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


def _horizontal_joint_rotation(
    grid,
    column,
    following,
    row,
    rigid_a=None,
    rigid_b=None,
):
    midpoint_a = (grid[column][row] + grid[column][row + 1]) * 0.5
    midpoint_b = (grid[following][row] + grid[following][row + 1]) * 0.5
    horizontal = midpoint_b - midpoint_a
    if horizontal.length <= 1.0e-8:
        raise ProxyBuildError(
            f"代理第 {column + 1} 列与第 {following + 1} 列的横 Joint 间距为零"
        )
    horizontal.normalize()

    vertical = (
        grid[column][row + 1]
        - grid[column][row]
        + grid[following][row + 1]
        - grid[following][row]
    ) * 0.5
    vertical -= horizontal * vertical.dot(horizontal)
    if vertical.length <= 1.0e-8:
        vertical = horizontal.orthogonal()
    vertical.normalize()
    normal = vertical.cross(horizontal)
    normal.normalize()

    references = []
    for rigid in (rigid_a, rigid_b):
        if rigid is None:
            continue
        stored_value = rigid.get("surface_proxy_normal")
        stored = (
            Vector(stored_value)
            if stored_value is not None and len(stored_value) == 3
            else Vector((0.0, 0.0, 0.0))
        )
        if stored.length <= 1.0e-8:
            stored = rigid.rotation_euler.to_matrix() @ Vector((0.0, 1.0, 0.0))
        stored -= vertical * stored.dot(vertical)
        if stored.length > 1.0e-8:
            stored.normalize()
            references.append(stored)
    if references:
        reference = references[-1].copy()
        for candidate in references[:-1]:
            if candidate.dot(reference) < 0.0:
                candidate = -candidate
            reference += candidate
        if reference.length > 1.0e-8 and normal.dot(reference) < 0.0:
            horizontal.negate()
            normal.negate()
    return Matrix((horizontal, normal, vertical)).transposed().to_euler("YXZ")


def _manual_joint_transform(rigid_a, rigid_b, role, parent):
    position_a = rigid_a.matrix_world.translation
    position_b = rigid_b.matrix_world.translation
    connection = position_b - position_a
    span = connection.length
    if span <= 1.0e-8:
        raise ProxyBuildError("两个刚体的位置重合，无法计算 Joint 轴线")
    connection.normalize()

    orientation_a = rigid_a.matrix_world.to_3x3().normalized()
    orientation_b = rigid_b.matrix_world.to_3x3().normalized()
    tangent_axis = (
        Vector((1.0, 0.0, 0.0))
        if role == "JOINT_HORIZONTAL"
        else Vector((0.0, 0.0, 1.0))
    )
    tangent_a = (orientation_a @ tangent_axis).normalized()
    tangent_b = (orientation_b @ tangent_axis).normalized()
    if tangent_a.dot(connection) < 0.0:
        tangent_a.negate()
    if tangent_b.dot(connection) < 0.0:
        tangent_b.negate()
    handle_a = tangent_a * span
    handle_b = tangent_b * span
    curve_position = (
        (position_a + position_b) * 0.5
        + (handle_a - handle_b) * 0.125
    )
    curve_tangent = (
        (position_b - position_a) * 1.5
        - (handle_a + handle_b) * 0.25
    )
    if curve_tangent.length <= 1.0e-8:
        curve_tangent = connection
    curve_tangent.normalize()

    normal_a = orientation_a @ Vector((0.0, 1.0, 0.0))
    normal_b = orientation_b @ Vector((0.0, 1.0, 0.0))
    if normal_a.dot(normal_b) < 0.0:
        normal_a.negate()

    normal = normal_a + normal_b
    candidates = (
        normal,
        normal_b,
        orientation_b @ Vector((1.0, 0.0, 0.0)),
        orientation_b @ Vector((0.0, 0.0, 1.0)),
    )
    for candidate in candidates:
        normal = candidate - curve_tangent * candidate.dot(curve_tangent)
        if normal.length > 1.0e-8:
            break
    else:
        normal = curve_tangent.orthogonal()
    normal.normalize()

    if role == "JOINT_HORIZONTAL":
        axis_x = curve_tangent
        axis_y = normal
        axis_z = axis_x.cross(axis_y).normalized()
    else:
        axis_z = curve_tangent
        axis_y = normal
        axis_x = axis_y.cross(axis_z).normalized()
    world_matrix = Matrix((axis_x, axis_y, axis_z)).transposed().to_4x4()
    world_matrix.translation = curve_position
    local_matrix = parent.matrix_world.inverted_safe() @ world_matrix
    return local_matrix.to_translation(), local_matrix.to_euler("YXZ")


def _joint_names_from_rigid_b(rigid_b, role):
    name_j = rigid_b.mmd_rigid.name_j.strip() or rigid_b.name
    name_e = rigid_b.mmd_rigid.name_e.strip() or name_j
    name_j, name_e = normalized_mmd_names(
        name_j,
        name_e,
        rigid_b.mmd_rigid.bone,
    )
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
    set_ordered_object_name(joint, name_j, joint=True)
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
    settings.rigid_depth_ratio = 0.1
    settings.rigid_radius_multiply = False
    settings.rigid_length_multiply = False

    scalar_values = {
        "rigid_radius_ratio": (False, 0.0),
        "rigid_length_ratio": (False, 0.0),
        "rigid_depth_ratio": (True, 0.4),
        "mass": (True, 1.0),
        "linear_damping": (True, 0.9999),
        "angular_damping": (True, 0.99),
        "restitution": (False, 0.0),
        "friction": (False, 0.3),
    }
    settings.mass = 12.0
    settings.linear_damping = 0.99
    settings.angular_damping = 0.9999
    settings.restitution = 0.0
    settings.friction = 0.0
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
        "limit_angular_lower": (0.0, 0.0, 0.0),
        "limit_angular_upper": (0.0, 0.0, 0.0),
        "spring_linear": (0.0, 0.0, 0.0),
        "spring_angular": (12.0, 5.0, 5.0),
        "horizontal_limit_linear_lower": (0.0, 0.0, 0.0),
        "horizontal_limit_linear_upper": (0.0, 0.0, 0.0),
        "horizontal_limit_angular_lower": tuple(
            math.radians(value) for value in (-10.0, -3.0, -5.0)
        ),
        "horizontal_limit_angular_upper": tuple(
            math.radians(value) for value in (10.0, 3.0, 5.0)
        ),
        "horizontal_spring_linear": (0.0, 0.0, 0.0),
        "horizontal_spring_angular": (0.8, 1.5, 4.0),
    }
    joint_end_values = {
        "limit_linear_lower": (0.0, 0.0, 0.0),
        "limit_linear_upper": (0.0, 0.0, 0.0),
        "limit_angular_lower": (0.0, 0.0, 0.0),
        "limit_angular_upper": (0.0, 0.0, 0.0),
        "spring_linear": (0.0, 0.0, 0.0),
        "spring_angular": (4.0, 2.0, 2.0),
        "horizontal_limit_linear_lower": (0.0, 0.0, 0.0),
        "horizontal_limit_linear_upper": (0.0, 0.0, 0.0),
        "horizontal_limit_angular_lower": tuple(
            math.radians(value) for value in (-18.0, -5.0, -12.0)
        ),
        "horizontal_limit_angular_upper": tuple(
            math.radians(value) for value in (18.0, 5.0, 12.0)
        ),
        "horizontal_spring_linear": (0.0, 40.0, 0.0),
        "horizontal_spring_angular": (0.25, 0.5, 1.5),
    }
    for name, value in joint_values.items():
        setattr(settings, name, value)
        setattr(settings, f"{name}_end", joint_end_values[name])
    joint_interpolation = {
        "limit_linear": (False, False, False),
        "limit_angular": (False, False, False),
        "spring_linear": (False, False, False),
        "spring_angular": (True, True, True),
        "horizontal_limit_linear": (False, False, False),
        "horizontal_limit_angular": (True, True, True),
        "horizontal_spring_linear": (False, False, False),
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
    place_mmd_objects(context.scene, root, (rigid_group, joint_group))
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
                pose_bone = armature.pose.bones.get(name)
                name_j, name_e = bone_mmd_names(pose_bone, name)
                factor = _rigid_interpolation_factor(row, row_counts)
                rigid_descriptors.append(
                    (
                        column,
                        row,
                        name,
                        name_j,
                        name_e,
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
        place_mmd_objects(context.scene, root, rigid_objects)
        for rigid, descriptor in zip(rigid_objects, rigid_descriptors):
            column, row, name, name_j, name_e, geometry, factor, dynamics_type = descriptor
            rigid = FnRigidBody.setup_rigid_body_object(
                obj=rigid,
                shape_type=rigid_module.shapeType(settings.rigid_shape),
                location=geometry["location"],
                rotation=geometry["rotation"],
                size=_rigid_size(settings.rigid_shape, geometry, settings, factor),
                dynamics_type=dynamics_type,
                name=name_j,
                name_e=name_e,
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
                    rigid_a = rigid_map[(column, row)]
                    rigid_b = rigid_map[(following, row)]
                    joint_descriptors.append(
                        (
                            "JOINT_HORIZONTAL",
                            column,
                            row,
                            rigid_a,
                            rigid_b,
                            _horizontal_joint_location(grid, column, following, row),
                            _horizontal_joint_rotation(
                                grid,
                                column,
                                following,
                                row,
                                rigid_a,
                                rigid_b,
                            ),
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
        place_mmd_objects(context.scene, root, joint_objects)
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

    normalize_mmd_indices(root, FnModel)

    proxy_object["surface_proxy_mmd_root"] = root.name
    _save_proxy_physics_settings(proxy_object, settings)
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    proxy_object.hide_set(False)
    proxy_object.select_set(True)
    context.view_layer.objects.active = proxy_object
    return len(rigid_map), len(joint_descriptors)


def _joint_apply_protected(settings):
    return any(
        getattr(settings, name)
        for name in (
            "protect_apply_joint_location",
            "protect_apply_joint_rotation",
            "protect_apply_joint_parameters",
        )
    )


def _reconcile_horizontal_joints(
    context,
    proxy_object,
    root,
    FnModel,
    FnRigidBody,
    objects,
    grid,
    row_counts,
    column_groups,
    closed,
    settings,
):
    if _joint_apply_protected(settings):
        return objects, 0, 0, 0

    rigid_map = {
        (
            int(obj.get("surface_proxy_column", -1)),
            int(obj.get("surface_proxy_row", -1)),
        ): obj
        for obj in objects
        if obj.get("surface_proxy_role") == "RIGID"
    }
    desired = {}
    unavailable = set()
    if settings.create_horizontal_joints:
        for column, following in _column_pairs(column_groups, closed):
            shared_bones = min(row_counts[column], row_counts[following]) - 1
            for row in range(shared_bones):
                key = (column, following, row)
                if (
                    (column, row) not in rigid_map
                    or (following, row) not in rigid_map
                ):
                    unavailable.add(key)
                else:
                    desired[key] = None
    existing = {}
    remove = []
    for obj in objects:
        if obj.get("surface_proxy_role") != "JOINT_HORIZONTAL":
            continue
        if obj.get("surface_proxy_manual_joint"):
            continue
        column = int(obj.get("surface_proxy_column", -1))
        row = int(obj.get("surface_proxy_row", -1))
        following = int(
            obj.get(
                "surface_proxy_following_column",
                _following_column(column_groups, column, closed),
            )
        )
        key = (column, following, row)
        if key in unavailable:
            continue
        if key in desired and key not in existing:
            existing[key] = obj
        else:
            remove.append(obj)

    missing = [key for key in desired if key not in existing]
    created = []
    if missing:
        joint_group = FnModel.ensure_joint_group_object(context, root)
        created = FnRigidBody.new_joint_objects(
            context,
            joint_group,
            len(missing),
            FnModel.get_empty_display_size(root),
        )
        place_mmd_objects(context.scene, root, (joint_group, *created))
        try:
            for joint, (column, following, row) in zip(created, missing):
                rigid_a = rigid_map[(column, row)]
                rigid_b = rigid_map[(following, row)]
                factor = _rigid_interpolation_factor(row, row_counts)
                joint_args = _joint_vectors(settings, "JOINT_HORIZONTAL", factor)
                joint_name, joint_name_e = _joint_names_from_rigid_b(
                    rigid_b,
                    "JOINT_HORIZONTAL",
                )
                FnRigidBody.setup_joint_object(
                    obj=joint,
                    name=joint_name,
                    name_e=joint_name_e,
                    location=_horizontal_joint_location(
                        grid,
                        column,
                        following,
                        row,
                    ),
                    rotation=_horizontal_joint_rotation(
                        grid,
                        column,
                        following,
                        row,
                        rigid_a,
                        rigid_b,
                    ),
                    rigid_a=rigid_a,
                    rigid_b=rigid_b,
                    maximum_location=joint_args[0],
                    minimum_location=joint_args[1],
                    maximum_rotation=joint_args[2],
                    minimum_rotation=joint_args[3],
                    spring_angular=joint_args[4],
                    spring_linear=joint_args[5],
                )
                _mark_physics_object(
                    joint,
                    proxy_object,
                    "JOINT_HORIZONTAL",
                    column,
                    row,
                )
                joint["surface_proxy_following_column"] = following
        except Exception:
            for joint in created:
                if joint.name in bpy.data.objects:
                    bpy.data.objects.remove(joint, do_unlink=True)
            raise

    current = [obj for obj in objects if obj not in remove]
    for joint in remove:
        if joint.name in bpy.data.objects:
            bpy.data.objects.remove(joint, do_unlink=True)
    if created or remove:
        normalize_mmd_indices(root, FnModel, kinds=("JOINT",))
    current.extend(created)
    return current, len(created), len(remove), len(unavailable)


def update_proxy_physics(context, proxy_object, settings):
    armature = _proxy_armature(proxy_object)
    prefix, row_counts = _proxy_structure(proxy_object, armature)
    root = _resolve_root(context, settings.mmd_root, proxy_object)
    FnModel, FnRigidBody, _rigid_module = _mmd_api()
    if FnModel.find_armature_object(root) != armature:
        raise ProxyBuildError("代理 Armature 不属于指定的 MMD 模型")
    objects = _proxy_physics_objects(proxy_object)
    if not objects:
        raise ProxyBuildError("该代理尚未生成刚体和 Joint")
    closed = bool(proxy_object.get("surface_proxy_closed", True))
    grid = _proxy_grid(proxy_object, armature, row_counts)
    column_groups = _column_groups(proxy_object, len(row_counts))
    (
        objects,
        horizontal_created,
        horizontal_removed,
        horizontal_skipped,
    ) = _reconcile_horizontal_joints(
        context,
        proxy_object,
        root,
        FnModel,
        FnRigidBody,
        objects,
        grid,
        row_counts,
        column_groups,
        closed,
        settings,
    )
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
            if not settings.protect_apply_location:
                obj.location = geometry["location"]
            if not settings.protect_apply_rotation:
                obj.rotation_euler = geometry["rotation"]
            if not settings.protect_apply_shape:
                obj.mmd_rigid.shape = settings.rigid_shape
            if not settings.protect_apply_size:
                obj.mmd_rigid.size = _rigid_size(
                    settings.rigid_shape,
                    geometry,
                    settings,
                    factor,
                )
            if not settings.protect_apply_type:
                obj.mmd_rigid.type = (
                    settings.top_rigid_type
                    if row == 0
                    else settings.body_rigid_type
                )
            if not settings.protect_apply_collision:
                obj.mmd_rigid.collision_group_number = (
                    settings.collision_group_number
                )
                obj.mmd_rigid.collision_group_mask = list(
                    settings.collision_group_mask
                )
            if not settings.protect_apply_dynamics:
                obj.rigid_body.mass = _interpolated_scalar(
                    settings, "mass", factor
                )
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
            if (
                "surface_proxy_normal" not in obj
                or (stored_normal - geometry["normal"]).length > 1.0e-8
            ):
                obj["surface_proxy_normal"] = list(geometry["normal"])
            rigid_count += 1
        elif role.startswith("JOINT_"):
            manual_joint = bool(obj.get("surface_proxy_manual_joint"))
            if manual_joint:
                factor = float(obj.get("surface_proxy_manual_joint_factor", 0.0))
            elif role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
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
            if (
                manual_joint
                and constraint is not None
                and constraint.object1 is not None
                and constraint.object2 is not None
            ):
                location, rotation = _manual_joint_transform(
                    constraint.object1,
                    constraint.object2,
                    role,
                    obj.parent,
                )
                if not settings.protect_apply_joint_location:
                    obj.location = location
                if not settings.protect_apply_joint_rotation:
                    obj.rotation_euler = rotation
            elif role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
                name = proxy_bone_name(proxy_object, prefix, column, row)
                if armature.data.bones.get(name) is None:
                    raise ProxyBuildError(f"缺少代理骨骼：{name}")
                geometry = _segment_geometry(
                    grid, column, row, closed, column_groups
                )
                if not settings.protect_apply_joint_location:
                    obj.location = grid[column][row]
                if not settings.protect_apply_joint_rotation:
                    obj.rotation_euler = geometry["rotation"]
            elif constraint.object1 is not None and constraint.object2 is not None:
                following = int(
                    obj.get(
                        "surface_proxy_following_column",
                        _following_column(column_groups, column, closed),
                    )
                )
                if not settings.protect_apply_joint_location:
                    obj.location = _horizontal_joint_location(
                        grid, column, following, row
                    )
                if not settings.protect_apply_joint_rotation:
                    obj.rotation_euler = _horizontal_joint_rotation(
                        grid,
                        column,
                        following,
                        row,
                        constraint.object1,
                        constraint.object2,
                    )
            if not settings.protect_apply_joint_parameters:
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
    return (
        rigid_count,
        joint_count,
        horizontal_created,
        horizontal_removed,
        horizontal_skipped,
    )


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
        constraint = obj.rigid_body_constraint
        if (
            obj.get("surface_proxy_manual_joint")
            and constraint is not None
            and constraint.object1 is not None
            and constraint.object2 is not None
        ):
            location, rotation = _manual_joint_transform(
                constraint.object1,
                constraint.object2,
                role,
                obj.parent,
            )
            geometry = {"rotation": rotation}
        elif role in {"JOINT_ANCHOR", "JOINT_VERTICAL"}:
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
            location = _horizontal_joint_location(grid, column, following, row)
            geometry = {
                "rotation": _horizontal_joint_rotation(
                    grid,
                    column,
                    following,
                    row,
                    constraint.object1 if constraint is not None else None,
                    constraint.object2 if constraint is not None else None,
                )
            }
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
    material: PointerProperty(type=bpy.types.Material)


class SPX_MMD_DiagnosticItem(PropertyGroup):
    severity: StringProperty()
    code: StringProperty()
    target_kind: StringProperty()
    target_name: StringProperty()
    armature_name: StringProperty()
    label: StringProperty()
    message: StringProperty()
    solution: StringProperty()
    search_text: StringProperty()


def _material_table_columns(layout):
    selection_split = layout.split(factor=0.045, align=True)
    selection = selection_split.row(align=True)
    remaining = selection_split.row(align=True)
    navigation_split = remaining.split(factor=0.955, align=True)
    content = navigation_split.row(align=True)
    navigation = navigation_split.row(align=True)
    order_split = content.split(factor=0.085, align=True)
    order = order_split.row(align=True)
    names = order_split.row(align=True)
    blender_split = names.split(factor=1.0 / 3.0, align=True)
    blender_name = blender_split.row(align=True)
    mmd_names = blender_split.row(align=True)
    mmd_split = mmd_names.split(factor=0.5, align=True)
    mmd_name = mmd_split.row(align=True)
    mmd_english_name = mmd_split.row(align=True)
    return selection, order, blender_name, mmd_name, mmd_english_name, navigation


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
        if item.kind == "MATERIAL":
            row = layout.row(align=True)
            (
                selection,
                order,
                blender_name,
                mmd_name,
                mmd_english_name,
                navigation,
            ) = _material_table_columns(row)
            selection.prop(item, "selected", text="")
            order.alignment = "CENTER"
            order.label(text=f"{item.order_index:03d}")
            material = item.material
            if material is None:
                blender_name.label(text="材质已不存在", icon="ERROR")
                return
            blender_name.prop(material, "name", text="", emboss=False)
            mmd_name.prop(material.mmd_material, "name_j", text="", emboss=False)
            mmd_english_name.prop(material.mmd_material, "name_e", text="")
            operator = navigation.operator(
                "surface_proxy.select_mmd_item",
                text="",
                icon="RESTRICT_SELECT_OFF",
            )
            operator.kind = item.kind
            operator.target_name = material.name
            return
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
        prefix = data.browser_prefix.casefold().strip()
        use_prefix = data.browser_filter_by_prefix and bool(prefix)
        if not search and not use_prefix:
            return [], []
        flags = [
            self.bitflag_filter_item
            if _mmd_browser_item_visible(data, item)
            else 0
            for item in items
        ]
        return flags, []


class SPX_UL_MMDDiagnostics(UIList):
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
        icon = "ERROR" if item.severity == "ERROR" else "INFO"
        row = layout.row(align=True)
        row.label(text=item.label, icon=icon)
        row.label(text=item.message)
        if item.target_name:
            operator = row.operator(
                "surface_proxy.jump_to_mmd_diagnostic",
                text="",
                icon="RESTRICT_SELECT_OFF",
            )
            operator.target_kind = item.target_kind
            operator.target_name = item.target_name
            operator.armature_name = item.armature_name
        operator = row.operator(
            "surface_proxy.repair_mmd_diagnostic",
            text="",
            icon="TOOL_SETTINGS",
        )
        operator.code = item.code
        operator.target_kind = item.target_kind
        operator.target_name = item.target_name
        operator.armature_name = item.armature_name
        operator.diagnostic_message = item.message

    def filter_items(self, _context, data, property_name):
        items = getattr(data, property_name)
        search = data.browser_search.casefold().strip()
        if not search:
            return [], []
        flags = [
            self.bitflag_filter_item
            if search
            in f"{item.label} {item.message} {item.solution} {item.search_text}".casefold()
            else 0
            for item in items
        ]
        return flags, []


def _add_mmd_diagnostic(
    settings,
    severity,
    target_kind,
    target_name,
    label,
    message,
    solution,
    armature_name="",
    search_text="",
    code="",
):
    item = settings.browser_diagnostics.add()
    item.severity = severity
    item.code = code
    item.target_kind = target_kind
    item.target_name = target_name
    item.armature_name = armature_name
    item.label = label
    item.message = message
    item.solution = solution
    item.search_text = search_text


def _mmd_rigid_components(rigids, joints):
    rigid_set = set(rigids)
    neighbors = {rigid: set() for rigid in rigids}
    incident_joints = {rigid: [] for rigid in rigids}
    for joint in joints:
        constraint = joint.rigid_body_constraint
        if constraint is None:
            continue
        first = constraint.object1
        second = constraint.object2
        if first not in rigid_set or second not in rigid_set or first is second:
            continue
        neighbors[first].add(second)
        neighbors[second].add(first)
        incident_joints[first].append(joint)
        incident_joints[second].append(joint)

    components = []
    remaining = set(rigids)
    while remaining:
        start = min(remaining, key=lambda rigid: rigid.name)
        remaining.remove(start)
        component = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for neighbor in neighbors[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        components.append(component)
    return components, neighbors, incident_joints


def _scan_mmd_diagnostics(settings, root, FnModel):
    settings.browser_diagnostics.clear()
    armature = FnModel.find_armature_object(root)
    armature_name = armature.name if armature is not None else ""
    if armature is None:
        _add_mmd_diagnostic(
            settings,
            "ERROR",
            "BONE",
            "",
            "骨骼",
            "MMD 模型缺少 Armature",
            "模型结构不完整；请重新导入 PMX，或把 Armature 正确归入这个 MMD Root。",
        )
        return

    bones = [
        bone
        for bone in armature.pose.bones
        if not getattr(bone, "is_mmd_shadow_bone", False)
    ]
    bone_names = {bone.name for bone in bones}
    bone_ids = {}
    for bone in bones:
        mmd_bone = bone.mmd_bone
        if not mmd_bone.name_j.strip():
            _add_mmd_diagnostic(
                settings,
                "WARNING",
                "BONE",
                bone.name,
                f"骨骼：{bone.name}",
                "MMD 名称为空",
                "跳转后填写名称；留空时导出器会改用 Blender 骨骼名。",
                armature_name,
                code="BONE_NAME_EMPTY",
            )
        bone_id = int(mmd_bone.bone_id)
        if bone_id >= 0:
            bone_ids.setdefault(bone_id, []).append(bone.name)
        if (
            (mmd_bone.has_additional_rotation or mmd_bone.has_additional_location)
            and not mmd_bone.additional_transform_bone
        ):
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "BONE",
                bone.name,
                f"骨骼：{bone.name}",
                "追加变换缺少目标骨骼",
                "跳转后指定追加变换的目标骨骼，或关闭“旋转 + / 移动 +”。",
                armature_name,
            )
    for bone_id, names in bone_ids.items():
        if len(names) < 2:
            continue
        joined_names = "、".join(names)
        for name in names:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "BONE",
                name,
                f"骨骼：{name}",
                f"Bone ID {bone_id} 重复：{joined_names}",
                "跳转后为重复骨骼分配不同 Bone ID；不要删除仍被 Morph 或追加变换引用的骨骼。",
                armature_name,
            )

    rigids = list(FnModel.iterate_rigid_body_objects(root))
    rigid_set = set(rigids)
    for rigid in rigids:
        label = rigid.mmd_rigid.name_j or rigid.name
        if rigid_world_scale_is_invalid(rigid):
            new_size, repair_reason = rigid_scale_repair_plan(rigid)
            scale_text = ", ".join(
                f"{float(value):.6g}"
                for value in rigid.matrix_world.decompose()[2]
            )
            fixable = new_size is not None
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "RIGID",
                rigid.name,
                f"刚体：{label}",
                f"非均匀或零缩放会阻止物理预览：({scale_text})",
                (
                    "点击工具按钮，把可表示的缩放无损折算进 MMD 刚体尺寸并将对象 Scale 归一。"
                    if fixable
                    else f"无法安全自动修复：{repair_reason}。请手动恢复可表示的刚体形状。"
                ),
                code="RIGID_SCALE_BAKE" if fixable else "RIGID_SCALE_UNFIXABLE",
            )
        elif rigid_object_scale_needs_bake(rigid):
            new_size, repair_reason = rigid_scale_repair_plan(rigid)
            scale_text = ", ".join(
                f"{float(value):.6g}" for value in rigid.scale
            )
            fixable = new_size is not None
            _add_mmd_diagnostic(
                settings,
                "WARNING",
                "RIGID",
                rigid.name,
                f"刚体：{label}",
                f"对象 Scale 未归一，但物理预览仍可运行：({scale_text})",
                (
                    "点击工具按钮，把均匀缩放无损折算进 MMD 刚体尺寸并将对象 Scale 归一。"
                    if fixable
                    else f"无法安全自动修复：{repair_reason}。请手动归一对象 Scale。"
                ),
                code="RIGID_SCALE_NORMALIZE" if fixable else "RIGID_SCALE_UNFIXABLE",
            )
        if rigid.rigid_body is None:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "RIGID",
                rigid.name,
                f"刚体：{label}",
                "缺少 Blender Rigid Body 数据",
                "该对象不再是完整刚体；通常应从原 PMX 重新导入或重新创建该刚体。",
            )
        bone_name = rigid.mmd_rigid.bone
        if bone_name and bone_name not in bone_names:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "RIGID",
                rigid.name,
                f"刚体：{label}",
                f"绑定骨骼不存在：{bone_name}",
                "跳转后把“骨骼”改为当前模型中实际存在的骨骼。",
            )

    joints = list(FnModel.iterate_joint_objects(root))
    for joint in joints:
        label = joint.mmd_joint.name_j or joint.name
        constraint = joint.rigid_body_constraint
        if constraint is None:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "JOINT",
                joint.name,
                f"Joint：{label}",
                "缺少 Rigid Body Constraint",
                "该对象不再是完整 Joint；通常应重新创建该 Joint。",
            )
            continue
        first = constraint.object1
        second = constraint.object2
        if first is None:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "JOINT",
                joint.name,
                f"Joint：{label}",
                "缺少连接的刚体 A",
                "跳转后在活动项属性的“刚体 A”中选择正确刚体。",
            )
        if second is None:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "JOINT",
                joint.name,
                f"Joint：{label}",
                "缺少连接的刚体 B",
                "跳转后在活动项属性的“刚体 B”中选择正确刚体。",
            )
        for endpoint, endpoint_label in ((first, "A"), (second, "B")):
            if endpoint is not None and endpoint not in rigid_set:
                _add_mmd_diagnostic(
                    settings,
                    "ERROR",
                    "JOINT",
                    joint.name,
                    f"Joint：{label}",
                    f"刚体 {endpoint_label} 不属于当前 MMD 模型：{endpoint.name}",
                    f"跳转后把“刚体 {endpoint_label}”换成当前 MMD 模型内的刚体。",
                )
        if first is not None and first is second:
            _add_mmd_diagnostic(
                settings,
                "ERROR",
                "JOINT",
                joint.name,
                f"Joint：{label}",
                "刚体 A 与刚体 B 指向同一对象",
                "跳转后把其中一个端点改成实际要连接的另一个刚体。",
            )

    components, neighbors, incident_joints = _mmd_rigid_components(rigids, joints)
    for component in components:
        dynamic = [
            rigid for rigid in component if int(rigid.mmd_rigid.type) != 0
        ]
        if not dynamic or any(
            int(rigid.mmd_rigid.type) == 0 for rigid in component
        ):
            continue
        endpoints = [
            rigid
            for rigid in dynamic
            if len(neighbors[rigid].intersection(component)) <= 1
        ]
        head = min(endpoints or dynamic, key=lambda rigid: rigid.name)
        label = head.mmd_rigid.name_j or head.name
        related = sorted(component, key=lambda rigid: rigid.name)
        component_joints = sorted(
            {
                joint
                for rigid in component
                for joint in incident_joints[rigid]
            },
            key=lambda joint: joint.name,
        )
        head_joints = [
            joint for joint in component_joints if joint in incident_joints[head]
        ]
        target_joint = (
            min(head_joints or component_joints, key=lambda joint: joint.name)
            if component_joints
            else None
        )
        search_text = " ".join(
            (
                " ".join(
                    value
                    for value in (
                        rigid.name,
                        rigid.mmd_rigid.name_j,
                        rigid.mmd_rigid.name_e,
                        rigid.mmd_rigid.bone,
                    )
                    if value
                )
                for rigid in related
            )
        )
        joint_search_text = " ".join(
            " ".join(
                value
                for value in (
                    joint.name,
                    joint.mmd_joint.name_j,
                    joint.mmd_joint.name_e,
                )
                if value
            )
            for joint in component_joints
        )
        _add_mmd_diagnostic(
            settings,
            "WARNING",
            "JOINT" if target_joint is not None else "RIGID",
            target_joint.name if target_joint is not None else head.name,
            f"动态链：{label}",
            f"{len(dynamic)} 个动态刚体无法通过 Joint 到达 0 型锚点",
            (
                "跳转后检查链首附近 Joint 的刚体 A/B。若锚定 Joint 已丢失，请以该 Joint 为参照创建或恢复连接到 0 型刚体或其它已锚定物理链；不要把整条链全部改成 0 型。"
                if target_joint is not None
                else "这个自由分量没有可跳转的 Joint；请创建连接到 0 型刚体或其它已锚定物理链的 Joint，不要把整条链全部改成 0 型。"
            ),
            search_text=f"{search_text} {joint_search_text}".strip(),
            code="UNANCHORED_COMPONENT",
        )


def _tag_browser_redraw():
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _refresh_mmd_browser_from_changes():
    global _BROWSER_AUTO_REFRESH_DIRTY, _BROWSER_AUTO_REFRESH_IN_PROGRESS
    if _BROWSER_AUTO_REFRESH_IN_PROGRESS:
        return False
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "surface_proxy_creator", None) if scene else None
    if (
        settings is None
        or settings.mmd_root is None
        or getattr(settings, "preview_running", False)
    ):
        return False
    _BROWSER_AUTO_REFRESH_IN_PROGRESS = True
    try:
        root = _resolve_root(bpy.context, settings.mmd_root)
        FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        _scan_mmd_diagnostics(settings, root, FnModel)
        settings.browser_diagnostic_index = min(
            settings.browser_diagnostic_index,
            max(len(settings.browser_diagnostics) - 1, 0),
        )
        if settings.browser_kind != "DIAGNOSTIC":
            result = bpy.ops.surface_proxy.refresh_mmd_browser()
            if result != {"FINISHED"}:
                return False
        _BROWSER_AUTO_REFRESH_DIRTY = False
        _tag_browser_redraw()
        return True
    except (ProxyBuildError, RuntimeError, ReferenceError, ValueError):
        return False
    finally:
        _BROWSER_AUTO_REFRESH_IN_PROGRESS = False


def _run_mmd_browser_auto_refresh():
    now = time.monotonic()
    if now < _BROWSER_AUTO_REFRESH_DEADLINE:
        return max(_BROWSER_AUTO_REFRESH_DEADLINE - now, 0.01)
    _refresh_mmd_browser_from_changes()
    return None


def _schedule_mmd_browser_auto_refresh():
    global _BROWSER_AUTO_REFRESH_DEADLINE
    _BROWSER_AUTO_REFRESH_DEADLINE = time.monotonic() + _BROWSER_AUTO_REFRESH_DELAY
    if not bpy.app.timers.is_registered(_run_mmd_browser_auto_refresh):
        bpy.app.timers.register(
            _run_mmd_browser_auto_refresh,
            first_interval=_BROWSER_AUTO_REFRESH_DELAY,
        )


def _object_belongs_to_mmd_root(obj, root):
    current = obj
    visited = set()
    while current is not None and current not in visited:
        if current is root:
            return True
        visited.add(current)
        current = current.parent
    return False


def _depsgraph_update_affects_mmd_root(update, root):
    data = update.id
    if isinstance(data, bpy.types.Object):
        return _object_belongs_to_mmd_root(data, root)
    if isinstance(data, bpy.types.Armature):
        model_objects = (root, *root.children_recursive)
        return any(
            obj.data is data
            for obj in model_objects
            if obj.type == "ARMATURE"
        )
    if isinstance(data, bpy.types.Collection):
        try:
            return any(
                _object_belongs_to_mmd_root(obj, root)
                for obj in data.all_objects
            )
        except ReferenceError:
            return False
    return False


@persistent
def _mmd_browser_depsgraph_update(scene, depsgraph):
    global _BROWSER_AUTO_REFRESH_DIRTY
    if _BROWSER_AUTO_REFRESH_IN_PROGRESS or scene is not getattr(
        bpy.context, "scene", None
    ):
        return
    settings = getattr(scene, "surface_proxy_creator", None)
    if (
        settings is None
        or settings.mmd_root is None
        or getattr(settings, "preview_running", False)
    ):
        return
    if not any(
        _depsgraph_update_affects_mmd_root(update, settings.mmd_root)
        for update in depsgraph.updates
    ):
        return
    _BROWSER_AUTO_REFRESH_DIRTY = True
    if getattr(settings, "workspace_tab", "") == "BROWSER":
        _schedule_mmd_browser_auto_refresh()


def register_browser_auto_refresh():
    handlers = bpy.app.handlers.depsgraph_update_post
    if _mmd_browser_depsgraph_update not in handlers:
        handlers.append(_mmd_browser_depsgraph_update)


def unregister_browser_auto_refresh():
    handlers = bpy.app.handlers.depsgraph_update_post
    if _mmd_browser_depsgraph_update in handlers:
        handlers.remove(_mmd_browser_depsgraph_update)
    if bpy.app.timers.is_registered(_run_mmd_browser_auto_refresh):
        bpy.app.timers.unregister(_run_mmd_browser_auto_refresh)


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
            (
                rigid_count,
                joint_count,
                horizontal_created,
                horizontal_removed,
                horizontal_skipped,
            ) = update_proxy_physics(
                context,
                _selected_proxy(context, settings),
                settings,
            )
        except (ProxyBuildError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        message = f"已更新 {rigid_count} 个刚体、{joint_count} 个 Joint"
        if horizontal_created:
            message += f"；新增 {horizontal_created} 个横 Joint"
        if horizontal_removed:
            message += f"；移除 {horizontal_removed} 个横 Joint"
        if horizontal_skipped:
            message += f"；跳过 {horizontal_skipped} 个缺少刚体端点的横 Joint"
        self.report({"INFO"}, message)
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
        global _BROWSER_AUTO_REFRESH_DIRTY
        settings = context.scene.surface_proxy_creator
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        register_material_export_hook()
        checked = {
            (
                item.kind,
                material_identity(item.material)
                if item.kind == "MATERIAL" and item.material is not None
                else item.target_name,
            )
            for item in settings.browser_items
            if item.selected
        }
        settings.mmd_root = root
        settings.browser_items.clear()
        if settings.browser_kind == "DIAGNOSTIC":
            _scan_mmd_diagnostics(settings, root, FnModel)
            settings.browser_diagnostic_index = min(
                settings.browser_diagnostic_index,
                max(len(settings.browser_diagnostics) - 1, 0),
            )
            _BROWSER_AUTO_REFRESH_DIRTY = False
            return {"FINISHED"}
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
        if settings.browser_kind == "MATERIAL":
            for order_index, material in enumerate(ordered_materials(root, FnModel)):
                item = settings.browser_items.add()
                item.kind = "MATERIAL"
                item.target_name = material.name
                item.label = material.name
                item.detail = (
                    f"{material.mmd_material.name_j} "
                    f"{material.mmd_material.name_e}"
                )
                item.order_index = order_index
                item.material = material
                item.selected = (
                    item.kind,
                    material_identity(material),
                ) in checked
        elif settings.browser_kind == "BONE" and armature is not None:
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
                    f"组 {int(rigid.mmd_rigid.collision_group_number)}"
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
        _BROWSER_AUTO_REFRESH_DIRTY = False
        return {"FINISHED"}


def _select_material_objects_in_blender(context, root, FnModel, materials):
    materials = [material for material in materials if material is not None]
    if not materials:
        raise ProxyBuildError("没有可选入 Blender 的材质")
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")

    material_priority = {
        material: priority for priority, material in enumerate(materials)
    }
    active_object = None
    selected_objects = 0
    for mesh_object in FnModel.iterate_mesh_objects(root):
        if mesh_object.name not in context.view_layer.objects:
            continue
        used_slot_indices = {
            polygon.material_index for polygon in mesh_object.data.polygons
        }
        slot_priorities = {
            index: material_priority[material]
            for index, material in enumerate(mesh_object.data.materials)
            if index in used_slot_indices and material in material_priority
        }
        if not slot_priorities:
            continue
        active_slot = max(
            slot_priorities,
            key=lambda index: slot_priorities[index],
        )
        mesh_object.active_material_index = active_slot
        mesh_object.hide_set(False)
        mesh_object.hide_select = False
        mesh_object.select_set(True)
        active_object = mesh_object
        selected_objects += 1

    if active_object is None:
        raise ProxyBuildError("当前 MMD 模型没有使用所选材质的可见 Mesh")
    context.view_layer.objects.active = active_object
    return selected_objects


def _selected_materials_from_blender(context, mesh_objects):
    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    model_meshes = set(mesh_objects)
    selected_meshes = [
        obj
        for obj in context.selected_objects
        if obj in model_meshes and obj.type == "MESH"
    ]
    selected_materials = {
        mesh_object.data.materials[index]
        for mesh_object in selected_meshes
        for index in {
            polygon.material_index for polygon in mesh_object.data.polygons
        }
        if index < len(mesh_object.data.materials)
        and mesh_object.data.materials[index] is not None
    }
    active_material = None
    active_object = context.active_object
    if active_object in model_meshes and active_object.type == "MESH":
        active_material = active_object.active_material
    return selected_materials, active_material


class SPX_OT_OpenBrowserMaterialTexture(Operator):
    bl_idname = "surface_proxy.open_browser_material_texture"
    bl_label = "添加 MMD 纹理"
    bl_options = {"REGISTER", "UNDO"}

    material_name: StringProperty(options={"HIDDEN"})
    texture_kind: EnumProperty(
        items=(("MAIN", "纹理", ""), ("SPHERE", "球体纹理", "")),
        options={"HIDDEN"},
    )
    filepath: StringProperty(subtype="FILE_PATH", maxlen=1024)
    use_filter_image: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, _context):
        material = bpy.data.materials.get(self.material_name)
        if material is None:
            self.report({"ERROR"}, "材质已不存在")
            return {"CANCELLED"}
        material_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.material"
        )
        fn_material = material_module.FnMaterial(material)
        if self.texture_kind == "SPHERE":
            fn_material.create_sphere_texture(self.filepath)
        else:
            fn_material.create_texture(self.filepath)
        return {"FINISHED"}


class SPX_OT_RemoveBrowserMaterialTexture(Operator):
    bl_idname = "surface_proxy.remove_browser_material_texture"
    bl_label = "移除 MMD 纹理"
    bl_options = {"REGISTER", "UNDO"}

    material_name: StringProperty(options={"HIDDEN"})
    texture_kind: EnumProperty(
        items=(("MAIN", "纹理", ""), ("SPHERE", "球体纹理", "")),
        options={"HIDDEN"},
    )

    def execute(self, _context):
        material = bpy.data.materials.get(self.material_name)
        if material is None:
            self.report({"ERROR"}, "材质已不存在")
            return {"CANCELLED"}
        material_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.material"
        )
        fn_material = material_module.FnMaterial(material)
        if self.texture_kind == "SPHERE":
            fn_material.remove_sphere_texture()
        else:
            fn_material.remove_texture()
        return {"FINISHED"}


_BATCH_EDITABLE_MMD_MATERIAL_PROPERTIES = {
    "name_j",
    "name_e",
    "comment",
    "diffuse_color",
    "alpha",
    "specular_color",
    "shininess",
    "ambient_color",
    "is_double_sided",
    "enabled_drop_shadow",
    "enabled_self_shadow_map",
    "enabled_self_shadow",
    "enabled_toon_edge",
    "edge_color",
    "edge_weight",
    "sphere_texture_type",
    "is_shared_toon_texture",
    "shared_toon_texture",
    "toon_texture",
}


class SPX_OT_CopyBrowserMaterialPropertyToChecked(Operator):
    bl_idname = "surface_proxy.copy_browser_material_property_to_checked"
    bl_label = "复制字段到勾选材质"
    bl_description = "将活动材质的当前字段复制到 MMD 查看器中全部勾选材质"
    bl_options = {"REGISTER", "UNDO"}

    material_name: StringProperty(options={"HIDDEN"})
    property_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        if self.property_name not in _BATCH_EDITABLE_MMD_MATERIAL_PROPERTIES:
            self.report({"ERROR"}, "该字段不支持批量编辑")
            return {"CANCELLED"}
        source_material = bpy.data.materials.get(self.material_name)
        if source_material is None:
            self.report({"ERROR"}, "活动材质已不存在")
            return {"CANCELLED"}
        settings = context.scene.surface_proxy_creator
        targets = [
            item.material
            for item in _checked_items(settings, "MATERIAL")
            if item.material is not None
        ]
        if not targets:
            self.report({"WARNING"}, "请先勾选要批量编辑的材质")
            return {"CANCELLED"}
        value = getattr(source_material.mmd_material, self.property_name)
        if hasattr(value, "to_tuple"):
            value = value.to_tuple()
        elif not isinstance(value, (str, int, float, bool)) and hasattr(value, "__iter__"):
            value = tuple(value)
        for material in targets:
            setattr(material.mmd_material, self.property_name, value)
        self.report({"INFO"}, f"已将字段同步到 {len(targets)} 个勾选材质")
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
        if self.kind == "MATERIAL":
            settings = context.scene.surface_proxy_creator
            material = bpy.data.materials.get(self.target_name)
            if material is None:
                self.report({"ERROR"}, "材质已不存在")
                return {"CANCELLED"}
            try:
                root = _resolve_root(context, settings.mmd_root)
                FnModel, _FnRigidBody, _rigid_module = _mmd_api()
                object_count = _select_material_objects_in_blender(
                    context,
                    root,
                    FnModel,
                    [material],
                )
            except (ProxyBuildError, RuntimeError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            for index, item in enumerate(settings.browser_items):
                if item.kind == "MATERIAL" and item.material == material:
                    settings.browser_index = index
                    break
            self.report(
                {"INFO"},
                f"已在 Object Mode 选中 {object_count} 个 Mesh",
            )
            return {"FINISHED"}
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


class SPX_OT_JumpToMMDDiagnostic(Operator):
    bl_idname = "surface_proxy.jump_to_mmd_diagnostic"
    bl_label = "跳转到问题项"

    target_kind: StringProperty()
    target_name: StringProperty()
    armature_name: StringProperty()

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        settings.browser_current_proxy_only = False
        settings.browser_filter_by_prefix = False
        settings.browser_search = ""
        settings.browser_kind = self.target_kind
        if bpy.ops.surface_proxy.refresh_mmd_browser() != {"FINISHED"}:
            return {"CANCELLED"}
        for index, item in enumerate(settings.browser_items):
            if item.kind == self.target_kind and item.target_name == self.target_name:
                settings.browser_index = index
                break
        else:
            self.report({"ERROR"}, "问题项已不存在；请重新运行诊断")
            return {"CANCELLED"}
        return bpy.ops.surface_proxy.select_mmd_item(
            kind=self.target_kind,
            target_name=self.target_name,
            armature_name=self.armature_name,
        )


class SPX_OT_RepairMMDDiagnostic(Operator):
    bl_idname = "surface_proxy.repair_mmd_diagnostic"
    bl_label = "尝试安全修复"
    bl_description = "只执行能够确定结果的修复；无法可靠推断时停止并要求手动处理"
    bl_options = {"REGISTER", "UNDO"}

    code: StringProperty()
    target_kind: StringProperty()
    target_name: StringProperty()
    armature_name: StringProperty()
    diagnostic_message: StringProperty()

    def execute(self, context):
        if self.code in {
            "RIGID_SCALE_BAKE",
            "RIGID_SCALE_NORMALIZE",
            "RIGID_SCALE_UNFIXABLE",
        }:
            rigid = bpy.data.objects.get(self.target_name)
            if rigid is None or getattr(rigid, "mmd_type", "") != "RIGID_BODY":
                self.report({"ERROR"}, "问题刚体已不存在；请重新运行诊断")
                return {"CANCELLED"}
            if not (
                rigid_world_scale_is_invalid(rigid)
                or rigid_object_scale_needs_bake(rigid)
            ):
                _refresh_mmd_browser_from_changes()
                self.report({"INFO"}, "该刚体的缩放问题已经消失")
                return {"FINISHED"}
            new_size, reason = rigid_scale_repair_plan(rigid)
            if new_size is None:
                self.report({"ERROR"}, f"无法安全自动修复：{reason}")
                return {"CANCELLED"}
            bake_rigid_object_scale(rigid)
            context.view_layer.update()
            if rigid_world_scale_is_invalid(rigid):
                self.report({"ERROR"}, "尺寸已经折算，但父级仍使刚体保持非均匀缩放")
                return {"CANCELLED"}
            if rigid_object_scale_needs_bake(rigid):
                self.report({"ERROR"}, "尺寸已经折算，但对象 Scale 未能归一")
                return {"CANCELLED"}
            if not _refresh_mmd_browser_from_changes():
                self.report({"ERROR"}, "刚体缩放已修复，但诊断刷新失败；请手动刷新")
                return {"CANCELLED"}
            size_text = ", ".join(f"{float(value):.6g}" for value in new_size)
            self.report(
                {"INFO"},
                f"已将缩放折算进 MMD 刚体尺寸：({size_text})",
            )
            return {"FINISHED"}

        if self.code == "BONE_NAME_EMPTY":
            armature = bpy.data.objects.get(self.armature_name)
            pose_bone = (
                armature.pose.bones.get(self.target_name)
                if armature is not None and armature.type == "ARMATURE"
                else None
            )
            if pose_bone is None:
                self.report({"ERROR"}, "问题骨骼已不存在；请重新运行诊断")
                return {"CANCELLED"}
            name_j, name_e = bone_mmd_names(pose_bone, pose_bone.name)
            if not pose_bone.mmd_bone.name_j.strip():
                pose_bone.mmd_bone.name_j = name_j
            if not pose_bone.mmd_bone.name_e.strip():
                pose_bone.mmd_bone.name_e = name_e
            if not _refresh_mmd_browser_from_changes():
                self.report({"ERROR"}, "已写入骨骼名称，但诊断刷新失败；请手动刷新")
                return {"CANCELLED"}
            self.report({"INFO"}, f"已将 MMD 骨骼名称补为：{name_j}")
            return {"FINISHED"}

        message = self.diagnostic_message or "当前问题"
        self.report(
            {"ERROR"},
            f"无法安全自动修复“{message}”：缺少唯一可靠的目标数据，请跳转后手动处理",
        )
        return {"CANCELLED"}


def _checked_items(settings, kind=None):
    return [
        item
        for item in settings.browser_items
        if item.selected and (kind is None or item.kind == kind)
    ]


_BONE_SIDE_SUFFIX = re.compile(r"^(?P<body>.*?)[._](?P<side>[LR])$", re.IGNORECASE)
_BONE_SIDE_PREFIX = re.compile(
    r"^(?P<side>Left|Right)(?P<body>(?:[._ -].*|[A-Z0-9].*))$",
)
_BONE_SIDE_WORD_SUFFIX = re.compile(
    r"^(?P<body>.*?)(?P<side>Left|Right)$",
)


def _split_bone_name_side(value):
    text = str(value or "").strip()
    if not text:
        return "", ""
    if text[0] in {"左", "右"}:
        return text[1:].lstrip("._ -"), "L" if text[0] == "左" else "R"
    match = _BONE_SIDE_SUFFIX.fullmatch(text)
    if match:
        return match.group("body").rstrip("._ -"), match.group("side").upper()
    match = _BONE_SIDE_PREFIX.fullmatch(text)
    if match:
        side = "L" if match.group("side").casefold() == "left" else "R"
        return match.group("body").lstrip("._ -"), side
    match = _BONE_SIDE_WORD_SUFFIX.fullmatch(text)
    if match and match.group("body"):
        side = "L" if match.group("side").casefold() == "left" else "R"
        return match.group("body").rstrip("._ -"), side
    return text, ""


def _bone_ai_translation_source(pose_bone):
    mmd_bone = pose_bone.mmd_bone
    source_body, side = _split_bone_name_side(mmd_bone.name_j)
    if not side:
        _name_e_body, side = _split_bone_name_side(mmd_bone.name_e)
    if not side:
        _blender_body, side = _split_bone_name_side(pose_bone.name)
    return source_body, side


def _preflight_bone_ai_rename(FnModel, root, armature, rename_map):
    active_map = {old: new for old, new in rename_map.items() if old != new}
    targets = list(active_map.values())
    if len(targets) != len(set(targets)):
        raise ProxyBuildError("AI 翻译产生了重复的 Blender 骨骼名")

    existing_bones = set(armature.data.bones.keys())
    source_bones = set(active_map)
    collisions = set(targets) & (existing_bones - source_bones)
    if collisions:
        raise ProxyBuildError(f"已存在目标 Blender 骨骼名：{sorted(collisions)[0]}")

    expected_groups = []
    for mesh_object in FnModel.iterate_child_objects(root):
        if mesh_object.type != "MESH" or mesh_object.mmd_type == "RIGID_BODY":
            continue
        existing_groups = {group.name for group in mesh_object.vertex_groups}
        source_groups = source_bones & existing_groups
        group_collisions = {
            active_map[source]
            for source in source_groups
            if active_map[source] in existing_groups
            and active_map[source] not in source_groups
        }
        if group_collisions:
            raise ProxyBuildError(
                f"网格 {mesh_object.name} 已存在目标顶点组："
                f"{sorted(group_collisions)[0]}"
            )
        expected_groups.append(
            (
                mesh_object,
                {source: active_map[source] for source in source_groups},
            )
        )
    return expected_groups


def _rename_ai_bones(FnModel, root, armature, rename_map):
    active_map = {old: new for old, new in rename_map.items() if old != new}
    if not active_map:
        return
    expected_groups = _preflight_bone_ai_rename(
        FnModel,
        root,
        armature,
        active_map,
    )
    model_module = importlib.import_module("bl_ext.blender_org.mmd_tools.core.model")
    model = model_module.Model(root)

    reserved_names = set(armature.data.bones.keys()) | set(active_map.values())
    temporary_names = {}
    for index, old_name in enumerate(active_map):
        temporary_name = f"__SPX_AI_BONE_RENAME_{index:04d}__"
        while temporary_name in reserved_names:
            temporary_name += "_"
        reserved_names.add(temporary_name)
        model.renameBone(old_name, temporary_name)
        temporary_names[temporary_name] = active_map[old_name]
    for temporary_name, final_name in temporary_names.items():
        model.renameBone(temporary_name, final_name)

    for mesh_object, group_map in expected_groups:
        for old_name, final_name in group_map.items():
            if (
                mesh_object.vertex_groups.get(old_name) is not None
                or mesh_object.vertex_groups.get(final_name) is None
            ):
                raise ProxyBuildError(
                    f"网格 {mesh_object.name} 顶点组未随骨骼重命名：{old_name}"
                )


def _mmd_browser_item_visible(settings, item):
    search = settings.browser_search.casefold().strip()
    prefix = settings.browser_prefix.casefold().strip()
    use_prefix = settings.browser_filter_by_prefix and bool(prefix)
    if item.kind == "MATERIAL" and item.material is not None:
        material = item.material
        names = (
            material.name,
            material.mmd_material.name_j,
            material.mmd_material.name_e,
        )
    else:
        names = (item.label, item.detail, item.target_name)
    folded_names = tuple(str(name).casefold() for name in names)
    return (
        not search or search in " ".join(folded_names)
    ) and (
        not use_prefix or any(name.startswith(prefix) for name in folded_names)
    )


class SPX_OT_SetMMDBrowserChecks(Operator):
    bl_idname = "surface_proxy.set_mmd_browser_checks"
    bl_label = "设置批量勾选"

    action: EnumProperty(
        items=(
            ("ALL", "全选", ""),
            ("NONE", "全不选", ""),
            ("INVERT", "反选", ""),
            ("RANGE", "区间选组", "补选最前与最后一个已勾选可见项之间的全部项目"),
        )
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        items = settings.browser_items
        if self.action == "RANGE":
            visible_items = [item for item in items if _mmd_browser_item_visible(settings, item)]
            selected_indices = [
                index for index, item in enumerate(visible_items) if item.selected
            ]
            if len(selected_indices) < 2:
                self.report({"WARNING"}, "区间选组至少需要勾选两个可见项目")
                return {"CANCELLED"}
            added = 0
            for item in visible_items[selected_indices[0] : selected_indices[-1] + 1]:
                if not item.selected:
                    item.selected = True
                    added += 1
            self.report({"INFO"}, f"已补选区间内 {added} 个项目")
            return {"FINISHED"}
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


def _bone_mirror_item(source_item, items):
    armature = bpy.data.objects.get(source_item.armature_name)
    source = armature.pose.bones.get(source_item.target_name) if armature else None
    if source is None:
        return None
    source_names = (
        source.name,
        str(source.mmd_bone.name_j or ""),
        str(source.mmd_bone.name_e or ""),
    )
    mirrored_names = {
        mirrored_name(name)
        for name in source_names
        if name and _side(name) in {"L", "R"}
    }
    if not mirrored_names:
        return None
    for item in items:
        if item == source_item or item.armature_name != source_item.armature_name:
            continue
        candidate = armature.pose.bones.get(item.target_name)
        if candidate is None:
            continue
        candidate_names = {
            candidate.name,
            str(candidate.mmd_bone.name_j or ""),
            str(candidate.mmd_bone.name_e or ""),
        }
        if mirrored_names & candidate_names:
            return item
    return None


def _add_mirror_browser_checks(context, settings):
    checked = _checked_items(settings, settings.browser_kind)
    if not checked:
        raise ProxyBuildError("请先勾选至少一项")
    targets = set()
    if settings.browser_kind == "BONE":
        for source_item in checked:
            target_item = _bone_mirror_item(source_item, settings.browser_items)
            if target_item is not None:
                targets.add(target_item.target_name)
    else:
        root = _resolve_root(context, settings.mmd_root)
        FnModel, _FnRigidBody, _rigid_module = _mmd_api()
        armature = FnModel.find_armature_object(root)
        if armature is None:
            raise ProxyBuildError("当前 MMD 模型没有骨架")
        rigids = list(FnModel.iterate_rigid_body_objects(root))
        joints = list(FnModel.iterate_joint_objects(root))
        for source_item in checked:
            source = bpy.data.objects.get(source_item.target_name)
            if source is None or _source_side(source) not in {"L", "R"}:
                continue
            if settings.browser_kind == "RIGID":
                target = _find_mirror_rigid(source, rigids, armature)
            else:
                endpoints = _joint_endpoints(source)
                if endpoints is None:
                    continue
                target_a = _find_mirror_rigid(
                    endpoints[0], rigids, armature, allow_shared=True
                )
                target_b = _find_mirror_rigid(
                    endpoints[1], rigids, armature, allow_shared=True
                )
                target = (
                    _find_mirror_joint(source, joints, target_a, target_b)
                    if target_a is not None and target_b is not None
                    else None
                )
            if target is not None:
                targets.add(target.name)
    added = 0
    for item in settings.browser_items:
        if item.target_name in targets and not item.selected:
            item.selected = True
            added += 1
    return added, len(checked) - len(targets)


class SPX_OT_QuickCheckMMDGroup(Operator):
    bl_idname = "surface_proxy.quick_check_mmd_group"
    bl_label = "快速选组"

    mode: EnumProperty(
        items=(
            ("PREFIX", "按名称前缀", ""),
            ("LOCKED_VERTEX_GROUPS", "当前物体锁定顶点组", ""),
            ("BONE_BRANCH", "已勾选骨骼及子级", ""),
            ("BONE_COLUMN", "同列骨骼", ""),
            ("RIGID_GROUP", "相同碰撞组", ""),
            ("RIGID_TYPE", "相同刚体类型", ""),
            ("CONNECTED", "相连物理组", ""),
            ("MIRROR", "按镜像加选另一边", ""),
        )
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        if self.mode == "MIRROR":
            try:
                added, unmatched = _add_mirror_browser_checks(context, settings)
            except (ProxyBuildError, RuntimeError, ValueError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            self.report(
                {"INFO"},
                f"已加选 {added} 个镜像项；{unmatched} 个勾选项没有匹配镜像",
            )
            return {"FINISHED"}
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
        elif self.mode == "LOCKED_VERTEX_GROUPS":
            mesh_object = context.active_object
            if mesh_object is None or mesh_object.type != "MESH":
                self.report({"ERROR"}, "请先选择一个 Mesh 物体")
                return {"CANCELLED"}
            locked_names = {
                group.name for group in mesh_object.vertex_groups if group.lock_weight
            }
            if not locked_names:
                self.report({"ERROR"}, "当前物体没有锁定顶点组")
                return {"CANCELLED"}
            matched = 0
            for item in settings.browser_items:
                if item.kind == "BONE" and item.target_name in locked_names:
                    item.selected = True
                    matched += 1
            if not matched:
                self.report({"INFO"}, "锁定顶点组中没有当前骨架对应的骨骼")
            return {"FINISHED"}
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
        layout.operator(
            SPX_OT_QuickCheckMMDGroup.bl_idname,
            text="按镜像加选另一边",
        ).mode = "MIRROR"
        layout.separator()
        if kind == "BONE":
            layout.operator(SPX_OT_QuickCheckMMDGroup.bl_idname, text="当前物体锁定顶点组").mode = "LOCKED_VERTEX_GROUPS"
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


class SPX_OT_TranslateSelectedBoneNamesWithAI(Operator):
    bl_idname = "surface_proxy.translate_selected_bone_names_with_ai"
    bl_label = "AI翻译勾选骨骼日文名"
    bl_description = (
        "翻译勾选骨骼的 MMD 日文名，并同步生成 MMD 英文名与 Blender 骨骼名"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        checked_items = _checked_items(settings, "BONE")
        if not checked_items:
            self.report({"ERROR"}, "请先勾选至少一个骨骼")
            return {"CANCELLED"}
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
            armature = FnModel.find_armature_object(root)
            if armature is None:
                raise ProxyBuildError("当前 MMD 模型没有骨架")

            translation_targets = []
            skipped = 0
            seen = set()
            for item in checked_items:
                old_name = item.target_name
                if old_name in seen:
                    continue
                seen.add(old_name)
                pose_bone = armature.pose.bones.get(old_name)
                if pose_bone is None:
                    skipped += 1
                    continue
                source_body, side = _bone_ai_translation_source(pose_bone)
                if not source_body:
                    skipped += 1
                    continue
                translation_targets.append((old_name, source_body, side))
            if not translation_targets:
                raise ProxyBuildError("勾选骨骼没有可翻译的 MMD 日文名")

            from . import mmd_morph_editor

            preferences = mmd_morph_editor._addon_preferences(context)
            translations = mmd_morph_editor._request_morph_name_translations(
                preferences,
                [source for _old, source, _side in translation_targets],
                max_characters=14,
                extra_instruction=(
                    "Translate only the bone-name body. Do not add Left, Right, "
                    "_L, _R, .L, .R, or Japanese side prefixes; the client adds "
                    "the side markers."
                ),
            )

            rename_map = {}
            translated_names = {}
            for (old_name, _source, side), translation in zip(
                translation_targets,
                translations,
                strict=True,
            ):
                base_name, _translated_side = _split_bone_name_side(translation)
                if not base_name:
                    raise ProxyBuildError(f"骨骼 {old_name} 的翻译结果为空")
                if len(base_name) > 14:
                    raise ProxyBuildError(
                        f"骨骼 {old_name} 的英文主体超过 14 个字符：{base_name}"
                    )
                side_prefix = "左" if side == "L" else "右" if side == "R" else ""
                mmd_name_j = side_prefix + base_name
                mmd_name_e = base_name + (f"_{side}" if side else "")
                blender_name = base_name + (f".{side}" if side else "")
                rename_map[old_name] = blender_name
                translated_names[old_name] = (
                    mmd_name_j,
                    mmd_name_e,
                    blender_name,
                )

            _rename_ai_bones(FnModel, root, armature, rename_map)
            for old_name, names in translated_names.items():
                mmd_name_j, mmd_name_e, blender_name = names
                pose_bone = armature.pose.bones.get(blender_name)
                if pose_bone is None:
                    raise ProxyBuildError(f"重命名后找不到骨骼：{blender_name}")
                pose_bone.mmd_bone.name_j = mmd_name_j
                pose_bone.mmd_bone.name_e = mmd_name_e
                for item in checked_items:
                    if item.target_name == old_name:
                        item.target_name = blender_name
                        item.label = blender_name

            bpy.ops.surface_proxy.refresh_mmd_browser()
        except (ProxyBuildError, ValueError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        message = f"已翻译并同步 {len(translation_targets)} 个骨骼名称"
        if skipped:
            message += f"；跳过 {skipped} 个无效或空名称骨骼"
        self.report({"INFO"}, message)
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
        if settings.browser_kind == "MATERIAL":
            try:
                root = _resolve_root(context, settings.mmd_root)
                FnModel, _FnRigidBody, _rigid_module = _mmd_api()
                object_count = _select_material_objects_in_blender(
                    context,
                    root,
                    FnModel,
                    [item.material for item in items],
                )
            except (ProxyBuildError, RuntimeError) as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            self.report(
                {"INFO"},
                f"已在 Object Mode 选中 {object_count} 个 Mesh",
            )
            return {"FINISHED"}
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
        if settings.browser_kind == "MATERIAL":
            try:
                root = _resolve_root(context, settings.mmd_root)
                FnModel, _FnRigidBody, _rigid_module = _mmd_api()
                selected_materials, active_material = (
                    _selected_materials_from_blender(
                        context,
                        FnModel.iterate_mesh_objects(root),
                    )
                )
            except ProxyBuildError as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            if not selected_materials:
                self.report(
                    {"ERROR"},
                    "3D 视图中没有选中使用有效材质的 Mesh",
                )
                return {"CANCELLED"}
            bpy.ops.surface_proxy.refresh_mmd_browser()
            active_index = None
            matched = 0
            for index, item in enumerate(settings.browser_items):
                item.selected = (
                    item.kind == "MATERIAL" and item.material in selected_materials
                )
                if item.selected:
                    matched += 1
                if item.kind == "MATERIAL" and item.material == active_material:
                    active_index = index
            if active_index is not None:
                settings.browser_index = active_index
            if matched != len(selected_materials):
                self.report(
                    {"WARNING"},
                    f"已同步 {matched}/{len(selected_materials)} 个材质；清除搜索或名称前缀过滤可显示其余材质",
                )
            else:
                self.report({"INFO"}, f"已同步 {matched} 个材质到查看器")
            return {"FINISHED"}
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


def _bones_share_chain(bone_a, bone_b):
    current = bone_a
    while current is not None:
        if current == bone_b:
            return True
        current = current.parent
    current = bone_b
    while current is not None:
        if current == bone_a:
            return True
        current = current.parent
    return False


class SPX_OT_CreateJointFromCheckedRigids(Operator):
    bl_idname = "surface_proxy.create_joint_from_checked_rigids"
    bl_label = "根据所选刚体创建 Joint"
    bl_description = "使用两个勾选刚体创建 Joint；查看器活动项作为刚体 B，另一个作为刚体 A"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        checked = _checked_items(settings, "RIGID")
        if len(checked) != 2:
            self.report({"ERROR"}, "必须且只能勾选两个刚体")
            return {"CANCELLED"}
        active = _active_browser_item(settings)
        if active is None or active.kind != "RIGID" or active not in checked:
            self.report({"ERROR"}, "请将两个勾选刚体中的一个设为查看器活动项；该项将作为刚体 B")
            return {"CANCELLED"}

        rigid_b = bpy.data.objects.get(active.target_name)
        rigid_a_item = next(item for item in checked if item != active)
        rigid_a = bpy.data.objects.get(rigid_a_item.target_name)
        if (
            rigid_a is None
            or rigid_b is None
            or rigid_a.mmd_type != "RIGID_BODY"
            or rigid_b.mmd_type != "RIGID_BODY"
        ):
            self.report({"ERROR"}, "勾选的刚体已不存在；请刷新查看器")
            return {"CANCELLED"}

        proxy_object = settings.physics_proxy
        if proxy_object is None:
            self.report({"ERROR"}, "请先指定当前代理网格")
            return {"CANCELLED"}
        try:
            armature = _proxy_armature(proxy_object)
            root = _resolve_root(context, settings.mmd_root, proxy_object)
            FnModel, FnRigidBody, _rigid_module = _mmd_api()
            proxy_objects = set(_proxy_physics_objects(proxy_object))
            if rigid_a not in proxy_objects or rigid_b not in proxy_objects:
                raise ProxyBuildError("两个刚体都必须属于当前代理网格")
            bone_a = armature.data.bones.get(str(rigid_a.mmd_rigid.bone))
            bone_b = armature.data.bones.get(str(rigid_b.mmd_rigid.bone))
            if bone_a is None or bone_b is None:
                raise ProxyBuildError("两个刚体都必须绑定当前代理骨架中的骨骼")

            role = (
                "JOINT_VERTICAL"
                if _bones_share_chain(bone_a, bone_b)
                else "JOINT_HORIZONTAL"
            )
            column_a = int(rigid_a.get("surface_proxy_column", -1))
            column_b = int(rigid_b.get("surface_proxy_column", -1))
            row_a = int(rigid_a.get("surface_proxy_row", -1))
            row_b = int(rigid_b.get("surface_proxy_row", -1))
            if min(column_a, column_b, row_a, row_b) < 0:
                raise ProxyBuildError("无法读取所选刚体在当前代理中的列/行位置")
            _prefix, row_counts = _proxy_structure(proxy_object, armature)
            if role == "JOINT_VERTICAL":
                column = column_b
                row = max(row_a, row_b)
                factor = _joint_interpolation_factor(row, row_counts)
            else:
                column = column_a
                row = row_b
                factor = _rigid_interpolation_factor(row_b, row_counts)

            joint_group = FnModel.ensure_joint_group_object(context, root)
            joint = FnRigidBody.new_joint_objects(
                context,
                joint_group,
                1,
                FnModel.get_empty_display_size(root),
            )[0]
            place_mmd_objects(context.scene, root, (joint_group, joint))
            try:
                location, rotation = _manual_joint_transform(
                    rigid_a,
                    rigid_b,
                    role,
                    joint_group,
                )
                joint_args = _joint_vectors(settings, role, factor)
                name, name_e = _joint_names_from_rigid_b(rigid_b, role)
                joint = FnRigidBody.setup_joint_object(
                    obj=joint,
                    name=name,
                    name_e=name_e,
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
                joint["surface_proxy_manual_joint"] = True
                joint["surface_proxy_manual_joint_factor"] = factor
                if role == "JOINT_HORIZONTAL":
                    joint["surface_proxy_following_column"] = column_b
            except Exception:
                if joint.name in bpy.data.objects:
                    bpy.data.objects.remove(joint, do_unlink=True)
                raise
            normalize_mmd_indices(root, FnModel, kinds=("JOINT",))
        except (ProxyBuildError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        joint.hide_set(False)
        joint.hide_select = False
        joint.select_set(True)
        context.view_layer.objects.active = joint
        role_label = "纵 Joint" if role == "JOINT_VERTICAL" else "横 Joint"
        self.report(
            {"INFO"},
            f"已创建 {role_label}：A={rigid_a.name}，B={rigid_b.name}",
        )
        return {"FINISHED"}


class SPX_OT_FillMissingMMDBoneNames(Operator):
    bl_idname = "surface_proxy.fill_missing_mmd_bone_names"
    bl_label = "补全并标准化 MMD 名称"
    bl_description = "按 Blender 骨骼名及 .L/.R、_L/_R 侧向后缀填写并标准化 MMD 名称和英文名称"
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
        for name in names:
            pose_bone = armature.pose.bones.get(name)
            if pose_bone is None or not hasattr(pose_bone, "mmd_bone"):
                continue
            name_j, name_e = standardized_bone_mmd_names(pose_bone, pose_bone.name)
            if (
                pose_bone.mmd_bone.name_j != name_j
                or pose_bone.mmd_bone.name_e != name_e
            ):
                pose_bone.mmd_bone.name_j = name_j
                pose_bone.mmd_bone.name_e = name_e
                changed_bones += 1
        self.report(
            {"INFO"},
            f"已标准化 {changed_bones} 根骨骼的 MMD 名称",
        )
        return {"FINISHED"}


def _bone_names_for_physics_sync(armature, bone_name, horizontal=False):
    pose_bone = armature.pose.bones.get(bone_name)
    if pose_bone is None:
        return None
    suffix = "_H" if horizontal else ""
    mmd_bone = getattr(pose_bone, "mmd_bone", None)
    name_j = str(getattr(mmd_bone, "name_j", "") or "").strip()
    name_e = str(getattr(mmd_bone, "name_e", "") or "").strip()
    return (
        f"{pose_bone.name}{suffix}",
        f"{name_j}{suffix}" if name_j else "",
        f"{name_e}{suffix}" if name_e else "",
    )


def _checked_bone_names(settings):
    return {item.target_name for item in _checked_items(settings, "BONE")}


class SPX_OT_SyncBoneNamesToRigids(Operator):
    bl_idname = "surface_proxy.sync_bone_names_to_rigids"
    bl_label = "将骨骼名称同步到刚体"
    bl_description = "将勾选骨骼的 Blender 名称、MMD 名称和 MMD 英文名称同步到绑定刚体；空名称保持为空"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        names = _checked_bone_names(settings)
        if not names:
            self.report({"ERROR"}, "没有勾选骨骼")
            return {"CANCELLED"}
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

        changed = 0
        for rigid in FnModel.iterate_rigid_body_objects(root):
            bone_name = str(getattr(rigid.mmd_rigid, "bone", ""))
            if bone_name not in names:
                continue
            synced = _bone_names_for_physics_sync(armature, bone_name)
            if synced is None:
                continue
            blender_name, name_j, name_e = synced
            set_ordered_object_name(rigid, blender_name)
            rigid.mmd_rigid.name_j = name_j
            rigid.mmd_rigid.name_e = name_e
            changed += 1
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report({"INFO"}, f"已将骨骼名称同步到 {changed} 个刚体")
        return {"FINISHED"}


class SPX_OT_SyncBoneNamesToJoints(Operator):
    bl_idname = "surface_proxy.sync_bone_names_to_joints"
    bl_label = "将骨骼名称同步到 Joint"
    bl_description = "按刚体 B 绑定骨骼同步 Blender、MMD 和 MMD 英文名称；自动识别横向 Joint 并保留 _H"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        names = _checked_bone_names(settings)
        if not names:
            self.report({"ERROR"}, "没有勾选骨骼")
            return {"CANCELLED"}
        try:
            root = _resolve_root(context, settings.mmd_root)
            FnModel, _FnRigidBody, _rigid_module = _mmd_api()
            armature = FnModel.find_armature_object(root)
            if settings.physics_proxy is not None:
                associate_existing_proxy_physics(settings.physics_proxy)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if armature is None:
            self.report({"ERROR"}, "当前 MMD 模型没有骨架")
            return {"CANCELLED"}

        changed = 0
        skipped = 0
        for joint in FnModel.iterate_joint_objects(root):
            constraint = joint.rigid_body_constraint
            rigid_b = constraint.object2 if constraint is not None else None
            if rigid_b is None or rigid_b.mmd_type != "RIGID_BODY":
                skipped += 1
                continue
            bone_name = str(getattr(rigid_b.mmd_rigid, "bone", ""))
            if bone_name not in names:
                continue
            horizontal = joint.get("surface_proxy_role") == "JOINT_HORIZONTAL"
            synced = _bone_names_for_physics_sync(armature, bone_name, horizontal)
            if synced is None:
                skipped += 1
                continue
            blender_name, name_j, name_e = synced
            set_ordered_object_name(joint, blender_name, joint=True)
            joint.mmd_joint.name_j = name_j
            joint.mmd_joint.name_e = name_e
            changed += 1
        bpy.ops.surface_proxy.refresh_mmd_browser()
        message = f"已将骨骼名称同步到 {changed} 个 Joint"
        if skipped:
            message += f"；跳过 {skipped} 个缺少有效刚体 B 或骨骼的 Joint"
        self.report({"INFO"}, message)
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
    settings.browser_diagnostics.clear()
    if settings.mmd_root is not None:
        try:
            bpy.ops.surface_proxy.refresh_mmd_browser()
        except RuntimeError:
            pass


def _get_collision_group_display(settings):
    return int(settings.collision_group_number)


def _set_collision_group_display(settings, value):
    settings.collision_group_number = max(0, min(15, int(value)))


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
        description="MMD 碰撞组索引（0–15）",
        min=0,
        max=15,
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
    properties["protect_apply_location"] = BoolProperty(
        name="刚体位置",
        description="应用参数到当前代理时保留刚体的现有位移",
    )
    properties["protect_apply_rotation"] = BoolProperty(
        name="刚体旋转",
        description="应用参数到当前代理时保留刚体的现有旋转",
    )
    properties["protect_apply_joint_location"] = BoolProperty(
        name="Joint 位置",
        description="应用参数到当前代理时保留 Joint 的现有位移",
    )
    properties["protect_apply_joint_rotation"] = BoolProperty(
        name="Joint 旋转",
        description="应用参数到当前代理时保留 Joint 的现有旋转",
    )
    properties["protect_apply_shape"] = BoolProperty(
        name="刚体形状",
        description="应用参数到当前代理时保留刚体的现有形状",
    )
    properties["protect_apply_size"] = BoolProperty(
        name="刚体尺寸",
        description="应用参数到当前代理时保留刚体的现有尺寸",
    )
    properties["protect_apply_type"] = BoolProperty(
        name="刚体类型",
        description="应用参数到当前代理时保留刚体的现有类型",
    )
    properties["protect_apply_dynamics"] = BoolProperty(
        name="刚体演算参数",
        description="应用参数到当前代理时保留质量、阻尼、弹性和摩擦",
    )
    properties["protect_apply_joint_parameters"] = BoolProperty(
        name="Joint 演算参数",
        description="应用参数到当前代理时保留 Joint 的移动/旋转限制和弹簧参数",
    )
    properties["protect_apply_collision"] = BoolProperty(
        name="碰撞设置",
        description="应用参数到当前代理时保留碰撞组和不碰撞组",
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
        items=(
            ("MATERIAL", "材质", ""),
            ("BONE", "骨骼", ""),
            ("RIGID", "刚体", ""),
            ("JOINT", "Joint", ""),
            ("DIAGNOSTIC", "诊断", ""),
        ),
        default="BONE",
        update=_browser_kind_changed,
    )
    properties["browser_current_proxy_only"] = BoolProperty(
        name="仅显示当前代理",
        description="只列出当前代理对应的骨骼、刚体或 Joint",
        default=False,
        update=_browser_kind_changed,
    )
    properties["browser_filter_by_prefix"] = BoolProperty(
        name="按前缀过滤",
        description="只显示可见名称或 Blender 名称以“名称前缀”开头的项目；可与当前代理过滤叠加",
        default=False,
    )
    properties["material_order_auto_sync"] = BoolProperty(
        name="自动同步校对",
        description="材质顺序改变时，只更新实际换位材质的 ID 及其单材质物体编号；多材质物体不改名",
        default=False,
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
    properties["browser_diagnostics"] = CollectionProperty(
        type=SPX_MMD_DiagnosticItem
    )
    properties["browser_diagnostic_index"] = IntProperty(default=0, min=0)
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
                text=str(index),
                toggle=True,
            )


def _draw_apply_protection(layout, settings):
    protection = layout.box()
    protection.label(text="应用保护（禁止更新）", icon="LOCKED")
    protection.label(
        text="勾选项在点击底部“应用参数到当前代理”时保留现有值",
        icon="INFO",
    )
    protection.label(
        text="不影响“生成”或“同步当前代理刚体和 Joint”",
        icon="INFO",
    )
    protection.label(
        text="三个 Joint 保护均关闭时，应用会按“生成横向 Joint”增删横 Joint",
        icon="INFO",
    )
    grid = protection.grid_flow(
        row_major=True,
        columns=2,
        even_columns=True,
        align=True,
    )
    for name in (
        "protect_apply_location",
        "protect_apply_rotation",
        "protect_apply_joint_location",
        "protect_apply_joint_rotation",
        "protect_apply_shape",
        "protect_apply_size",
        "protect_apply_type",
        "protect_apply_dynamics",
        "protect_apply_collision",
        "protect_apply_joint_parameters",
    ):
        grid.prop(settings, name)


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
        _draw_apply_protection(page, settings)
    elif settings.physics_tab == "VERTICAL":
        _draw_joint_settings(page, settings, "")
        _draw_apply_protection(page, settings)
    else:
        page.prop(settings, "create_horizontal_joints")
        horizontal = page.column()
        horizontal.enabled = settings.create_horizontal_joints
        _draw_joint_settings(horizontal, settings, "horizontal_")
        _draw_apply_protection(page, settings)
    row = box.row(align=True)
    row.operator("surface_proxy.create_mmd_physics", icon="PHYSICS")
    row.operator("surface_proxy.update_mmd_physics", icon="FILE_REFRESH")


def draw_browser(layout, settings):
    if (
        _BROWSER_AUTO_REFRESH_DIRTY
        and not _BROWSER_AUTO_REFRESH_IN_PROGRESS
        and not getattr(settings, "preview_running", False)
        and not bpy.app.timers.is_registered(_run_mmd_browser_auto_refresh)
    ):
        _schedule_mmd_browser_auto_refresh()
    layout.prop(settings, "mmd_root")
    if settings.browser_kind in {"BONE", "RIGID", "JOINT"}:
        layout.prop(settings, "physics_proxy", text="代理范围")
        row = layout.row(align=True)
        row.prop(settings, "browser_current_proxy_only")
        row.prop(settings, "browser_filter_by_prefix")
    elif settings.browser_kind == "MATERIAL":
        layout.prop(settings, "browser_filter_by_prefix")
    row = layout.row(align=True)
    row.prop(settings, "browser_kind", expand=True)
    row.operator("surface_proxy.refresh_mmd_browser", text="", icon="FILE_REFRESH")
    layout.prop(settings, "browser_search", icon="VIEWZOOM")
    if settings.browser_kind == "DIAGNOSTIC":
        layout.label(text="这里只报告可确认的模型结构问题，不评判物理参数。", icon="INFO")
        layout.template_list(
            "SPX_UL_MMDDiagnostics",
            "",
            settings,
            "browser_diagnostics",
            settings,
            "browser_diagnostic_index",
            rows=10,
        )
        error_count = sum(
            item.severity == "ERROR" for item in settings.browser_diagnostics
        )
        warning_count = len(settings.browser_diagnostics) - error_count
        if settings.browser_diagnostics:
            layout.label(
                text=f"发现 {error_count} 个错误、{warning_count} 个警告",
                icon="ERROR" if error_count else "INFO",
            )
            layout.label(
                text="每行右侧：箭头跳转，工具按钮尝试安全修复",
                icon="INFO",
            )
            index = min(
                settings.browser_diagnostic_index,
                len(settings.browser_diagnostics) - 1,
            )
            active_issue = settings.browser_diagnostics[index]
            help_box = layout.box()
            help_box.label(text=f"当前问题：{active_issue.message}", icon="QUESTION")
            help_box.label(text=f"处理方法：{active_issue.solution}", icon="TOOL_SETTINGS")
        else:
            layout.label(text="未发现异常", icon="CHECKMARK")
        return
    row = layout.row(align=True)
    row.prop(settings, "browser_prefix")
    row.operator(
        SPX_OT_PrefixFromActiveMMDItem.bl_idname,
        text="",
        icon="EYEDROPPER",
    )
    browser_table = layout.row()
    list_column = browser_table.column()
    if settings.browser_kind == "MATERIAL":
        header = list_column.row(align=True)
        (
            selection,
            order,
            blender_name,
            mmd_name,
            mmd_english_name,
            navigation,
        ) = _material_table_columns(header)
        selection.label(text="")
        for column, text in (
            (order, "序号"),
            (blender_name, "Blender 材质名"),
            (mmd_name, "MMD 名称"),
            (mmd_english_name, "MMD 英文名"),
        ):
            column.alignment = "CENTER"
            column.label(text=text)
        navigation.label(text="")
    list_column.template_list(
        "SPX_UL_MMDItems",
        "",
        settings,
        "browser_items",
        settings,
        "browser_index",
        rows=10,
    )
    order_buttons = browser_table.column(align=True)
    if settings.browser_kind == "MATERIAL":
        order_buttons.label(text="", icon="BLANK1")
    draw_mmd_ordering(order_buttons, settings)
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
    operator = row.operator(
        SPX_OT_SetMMDBrowserChecks.bl_idname,
        text="区间选组",
    )
    operator.action = "RANGE"
    if settings.browser_kind != "MATERIAL":
        row.menu(SPX_MT_MMDQuickSelect.bl_idname, text="快速选组", icon="GROUP_BONE")
    draw_mmd_bone_subdivision(layout, settings)
    if settings.browser_kind == "MATERIAL":
        layout.operator(
            SPX_OT_SelectCheckedMMDItems.bl_idname,
            icon="RESTRICT_SELECT_OFF",
        )
        layout.operator(
            SPX_OT_SyncSelectedMMDObjectsToBrowser.bl_idname,
            text="从 3D 视图同步选中材质",
            icon="UV_SYNC_SELECT",
        )
        draw_material_name_sync(layout, settings)
        _draw_active_mmd_inspector(layout, settings)
        return
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
        if settings.browser_kind == "RIGID":
            joint_box = layout.box()
            joint_box.operator(
                SPX_OT_CreateJointFromCheckedRigids.bl_idname,
                icon="CONSTRAINT_BONE",
            )
            joint_box.label(
                text="只能勾选两个刚体；活动项为 B，另一个为 A",
                icon="INFO",
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
        names_box.label(text="补全并标准化 MMD 骨骼名称", icon="SORTALPHA")
        translate_row = names_box.row(align=True)
        translate_row.operator(
            SPX_OT_TranslateSelectedBoneNamesWithAI.bl_idname,
            text="AI翻译勾选骨骼日文名",
            icon="WORLD",
        )
        translate_row.operator(
            "surface_proxy.morph_ai_settings",
            text="",
            icon="PREFERENCES",
        )
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
        sync_row = names_box.row(align=True)
        sync_row.operator(
            SPX_OT_SyncBoneNamesToRigids.bl_idname,
            text="骨骼名同步到刚体",
        )
        sync_row.operator(
            SPX_OT_SyncBoneNamesToJoints.bl_idname,
            text="骨骼名同步到 Joint",
        )
        names_box.label(text="镜像骨骼统一左/右与 _L/_R；中英双语主体保持不变", icon="INFO")
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


def _draw_batchable_mmd_material_property(
    layout,
    material,
    property_name,
    *,
    text=None,
    slider=False,
    expand=False,
):
    row = layout.row(align=True)
    keywords = {"slider": slider, "expand": expand}
    if text is not None:
        keywords["text"] = text
    row.prop(material.mmd_material, property_name, **keywords)
    operator = row.operator(
        SPX_OT_CopyBrowserMaterialPropertyToChecked.bl_idname,
        text="",
        icon="COPYDOWN",
    )
    operator.material_name = material.name
    operator.property_name = property_name
    return row


def _draw_browser_material_texture(layout, material):
    material_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.material"
    )
    fn_material = material_module.FnMaterial(material)
    mmd_material = material.mmd_material
    box = layout.box()
    box.label(text="MMD 纹理", icon="TEXTURE")
    for texture_kind, label, texture in (
        ("MAIN", "纹理", fn_material.get_texture()),
        ("SPHERE", "球体纹理", fn_material.get_sphere_texture()),
    ):
        box.label(text=f"{label}：")
        row = box.row(align=True)
        if texture is not None and texture.type == "IMAGE" and texture.image:
            row.prop(texture.image, "filepath", text="")
            operator = row.operator(
                SPX_OT_RemoveBrowserMaterialTexture.bl_idname,
                text="",
                icon="PANEL_CLOSE",
            )
            operator.material_name = material.name
            operator.texture_kind = texture_kind
        else:
            operator = row.operator(
                SPX_OT_OpenBrowserMaterialTexture.bl_idname,
                text="添加",
                icon="FILE_FOLDER",
            )
            operator.material_name = material.name
            operator.texture_kind = texture_kind
            if texture is not None:
                row.label(text="纹理节点无有效图像", icon="ERROR")
        if texture_kind == "SPHERE":
            _draw_batchable_mmd_material_property(
                box,
                material,
                "sphere_texture_type",
                expand=True,
            )
    row = _draw_batchable_mmd_material_property(
        box,
        material,
        "is_shared_toon_texture",
    )
    shared = box.row(align=True)
    shared.active = mmd_material.is_shared_toon_texture
    _draw_batchable_mmd_material_property(
        shared,
        material,
        "shared_toon_texture",
    )
    custom = box.row(align=True)
    custom.active = not mmd_material.is_shared_toon_texture
    _draw_batchable_mmd_material_property(
        custom,
        material,
        "toon_texture",
    )


def _draw_browser_mmd_material(layout, material):
    mmd_material = material.mmd_material
    box = layout.box()
    box.label(text="MMD 材质", icon="MATERIAL")
    box.label(text="字段右侧复制图标：同步到勾选材质", icon="INFO")
    row = box.row(align=True)
    row.label(text="信息：")
    if not mmd_material.is_id_unique():
        row.label(icon="ERROR")
    row.prop(mmd_material, "material_id", text="ID")
    _draw_batchable_mmd_material_property(box, material, "name_j")
    _draw_batchable_mmd_material_property(box, material, "name_e")
    _draw_batchable_mmd_material_property(box, material, "comment")
    box.label(text="颜色：")
    _draw_batchable_mmd_material_property(box, material, "diffuse_color")
    _draw_batchable_mmd_material_property(
        box,
        material,
        "alpha",
        slider=True,
    )
    _draw_batchable_mmd_material_property(box, material, "specular_color")
    _draw_batchable_mmd_material_property(
        box,
        material,
        "shininess",
        slider=True,
    )
    _draw_batchable_mmd_material_property(box, material, "ambient_color")
    box.label(text="阴影：")
    for property_name in (
        "is_double_sided",
        "enabled_drop_shadow",
        "enabled_self_shadow_map",
        "enabled_self_shadow",
        "enabled_toon_edge",
    ):
        _draw_batchable_mmd_material_property(box, material, property_name)
    edge = box.row()
    edge.active = mmd_material.enabled_toon_edge
    _draw_batchable_mmd_material_property(edge, material, "edge_color")
    _draw_batchable_mmd_material_property(
        edge,
        material,
        "edge_weight",
        slider=True,
    )


def _draw_active_mmd_inspector(layout, settings):
    item = _active_browser_item(settings)
    if item is None:
        return
    if settings.browser_kind == "MATERIAL":
        material = item.material
        if material is None:
            box = layout.box()
            box.label(text="材质已不存在", icon="ERROR")
            return
        _draw_browser_material_texture(layout, material)
        _draw_browser_mmd_material(layout, material)
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
            mmd_bone = pose_bone.mmd_bone
            row = box.row(align=True)
            row.label(text="信息")
            if not mmd_bone.is_id_unique():
                row.label(text="Bone ID 重复", icon="ERROR")
            row.prop(mmd_bone, "bone_id", text="ID")
            box.prop(mmd_bone, "name_j")
            box.prop(mmd_bone, "name_e")
            operator = box.operator(
                SPX_OT_FillMissingMMDBoneNames.bl_idname,
                text="补全并标准化当前名称",
                icon="SORTALPHA",
            )
            operator.scope = "ACTIVE"
            row = box.row(align=True)
            row.prop(mmd_bone, "transform_order")
            row.prop(mmd_bone, "transform_after_dynamics")
            row = box.row(align=True)
            row.prop(mmd_bone, "is_controllable")
            row.prop(mmd_bone, "is_tip")
            if any(constraint.type == "IK" for constraint in pose_bone.constraints):
                box.prop(mmd_bone, "ik_rotation_constraint")

            axes = box.column(align=True)
            axes.prop(mmd_bone, "enabled_fixed_axis")
            row = axes.row()
            row.active = mmd_bone.enabled_fixed_axis
            row.prop(mmd_bone, "fixed_axis", text="")
            axes.prop(mmd_bone, "enabled_local_axes")
            row = axes.row(align=True)
            row.active = mmd_bone.enabled_local_axes
            row.prop(mmd_bone, "local_axis_x")
            row.prop(mmd_bone, "local_axis_z")

            additional = box.column(align=True)
            row = additional.row(align=True)
            row.prop(
                mmd_bone,
                "has_additional_rotation",
                text="旋转 +",
                toggle=True,
            )
            row.prop(
                mmd_bone,
                "has_additional_location",
                text="移动 +",
                toggle=True,
            )
            if mmd_bone.is_additional_transform_dirty:
                row.label(icon="ERROR")
            additional.prop_search(
                mmd_bone,
                "additional_transform_bone",
                armature.pose,
                "bones",
                text="目标骨骼",
                icon="BONE_DATA",
            )
            additional.prop(
                mmd_bone,
                "additional_transform_influence",
                text="影响",
                slider=True,
            )

            connection = box.column(align=True)
            connection.label(text="骨骼末端指向")
            connection.prop(mmd_bone, "display_connection_type", text="类型")
            if mmd_bone.display_connection_type == "BONE":
                connection.prop_search(
                    mmd_bone,
                    "display_connection_bone",
                    armature.pose,
                    "bones",
                    text="目标骨骼",
                    icon="BONE_DATA",
                )
            elif mmd_bone.display_connection_type == "OFFSET":
                connection.label(text="偏移将在导出时自动计算", icon="INFO")
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
        box.prop(rigid, "collision_group_number", text="碰撞组")
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
    elif settings.browser_kind != "MATERIAL":
        self.layout.operator(SPX_OT_DeleteCheckedMMDItems.bl_idname, icon="TRASH")


def register_browser_context_menu():
    bpy.types.UI_MT_list_item_context_menu.append(_draw_mmd_list_context_menu)


def unregister_browser_context_menu():
    bpy.types.UI_MT_list_item_context_menu.remove(_draw_mmd_list_context_menu)


CLASSES = (
    SPX_MMD_BrowserItem,
    SPX_MMD_DiagnosticItem,
    SPX_UL_MMDItems,
    SPX_UL_MMDDiagnostics,
    SPX_OT_CreateMMDPhysics,
    SPX_MT_PhysicsPresets,
    SPX_OT_ApplyStableLongSkirtPreset,
    SPX_OT_AddPhysicsPreset,
    SPX_OT_UpdateMMDPhysics,
    SPX_OT_SyncMMDPhysics,
    SPX_OT_RefreshMMDBrowser,
    SPX_OT_SelectMMDItem,
    SPX_OT_JumpToMMDDiagnostic,
    SPX_OT_RepairMMDDiagnostic,
    SPX_OT_SetMMDBrowserChecks,
    SPX_OT_QuickCheckMMDGroup,
    SPX_OT_PrefixFromActiveMMDItem,
    SPX_MT_MMDQuickSelect,
    SPX_OT_TranslateSelectedBoneNamesWithAI,
    SPX_OT_SelectCheckedMMDItems,
    SPX_OT_SyncSelectedMMDObjectsToBrowser,
    SPX_OT_OpenBrowserMaterialTexture,
    SPX_OT_RemoveBrowserMaterialTexture,
    SPX_OT_CopyBrowserMaterialPropertyToChecked,
    SPX_OT_CreateJointFromCheckedRigids,
    SPX_OT_FillMissingMMDBoneNames,
    SPX_OT_SyncBoneNamesToRigids,
    SPX_OT_SyncBoneNamesToJoints,
    SPX_OT_SyncJointNamesFromRigidB,
    *MIRROR_PHYSICS_CLASSES,
    SPX_OT_DeleteCheckedMMDItems,
    SPX_OT_CleanupCheckedBones,
)
