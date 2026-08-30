bl_info = {
    "name": "MMD Station",
    "author": "MMD Station contributors",
    "version": (0, 1, 8),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > MMD Station",
    "description": "Create and edit MMD models, Morphs, physics, and IK workflows",
    "doc_url": "https://github.com/AliciaSource/MMD-Station",
    "category": "Rigging",
}

import bmesh
import bpy
import re
import sys
from math import atan2
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector
from mathutils.kdtree import KDTree

from .core import (
    ProxyBuildError,
    bilinear_grid_weights,
    bone_name,
    build_cylindrical_surface_grid,
    grid_faces,
    grid_vertices,
)
from .collection_organization import place_proxy_object
from .sync import CLASSES as SYNC_CLASSES
from .sync import initialize_proxy_identity
from .sync import register_services as register_sync_services
from .sync import unregister_services as unregister_sync_services
from .mmd_physics import CLASSES as MMD_PHYSICS_CLASSES
from .mmd_physics import (
    associate_existing_proxy_physics,
    draw_browser,
    draw_physics_settings,
    register_browser_auto_refresh,
    register_browser_context_menu,
    register_settings,
    unregister_browser_auto_refresh,
    unregister_browser_context_menu,
)
from .physics_preview import CLASSES as PHYSICS_PREVIEW_CLASSES
from .physics_preview import draw_preview
from .physics_preview import preload_libraries as preload_physics_libraries
from .physics_preview import register_cache_services as register_physics_cache_services
from .physics_preview import register_settings as register_preview_settings
from .physics_preview import register_bake_settings
from .physics_preview import unregister_runtime as unregister_preview_runtime
from .bone_physics_creator import CLASSES as BONE_PHYSICS_CREATOR_CLASSES
from .bone_physics_creator import register_settings as register_bone_physics_creator_settings
from .mmd_ordering import CLASSES as MMD_ORDERING_CLASSES
from .mmd_material_order import CLASSES as MMD_MATERIAL_ORDER_CLASSES
from .mmd_material_order import register_export_hook as register_material_export_hook
from .mmd_material_order import unregister_export_hook as unregister_material_export_hook
from .mmd_bone_subdivision import CLASSES as MMD_BONE_SUBDIVISION_CLASSES
from .mmd_bone_subdivision import register_settings as register_bone_subdivision_settings
from .mmd_ik_runtime import CLASSES as MMD_IK_RUNTIME_CLASSES
from .mmd_ik_runtime import draw as draw_mmd_ik_runtime
from .mmd_ik_runtime import register_services as register_mmd_ik_runtime_services
from .mmd_ik_runtime import register_settings as register_mmd_ik_runtime_settings
from .mmd_ik_runtime import unregister_services as unregister_mmd_ik_runtime_services
from .mmd_morph_editor import CLASSES as MMD_MORPH_EDITOR_CLASSES
from .mmd_morph_editor import draw_morph_editor
from .mmd_morph_editor import register_services as register_morph_editor_services
from .mmd_morph_editor import register_settings as register_morph_editor_settings
from .mmd_morph_editor import unregister_services as unregister_morph_editor_services
from .mmd_display_frame import CLASSES as MMD_DISPLAY_FRAME_CLASSES
from .mmd_display_frame import draw_display_frame_editor
from .mmd_display_frame import register_services as register_display_frame_services
from .mmd_display_frame import register_settings as register_display_frame_settings
from .mmd_display_frame import unregister_services as unregister_display_frame_services
from .mmd_io import CLASSES as MMD_IO_CLASSES
from .mmd_io import draw_mmd_io
from .mmd_export_morph_order import register_export_hook as register_morph_order_export_hook
from .mmd_export_morph_order import unregister_export_hook as unregister_morph_order_export_hook
from .mmd_export_profile import register_export_profile_hook
from .mmd_export_profile import unregister_export_profile_hook
from .mmd_shadow import register_services as register_shadow_services
from .mmd_shadow import unregister_services as unregister_shadow_services
from .vertex_group_tools import CLASSES as VERTEX_GROUP_TOOL_CLASSES
from .vertex_group_tools import register_menu as register_vertex_group_menu
from .vertex_group_tools import unregister_menu as unregister_vertex_group_menu
from . import updater
from .updater import notify as updater_notify


def _version_text():
    package = sys.modules.get(__package__ or "mmd_station")
    version = getattr(package, "bl_info", {}).get("version", (0, 0, 0))
    text = "v" + ".".join(str(part) for part in version)
    try:
        from ._version import BUILD, PRERELEASE
        if PRERELEASE:
            text += "-" + PRERELEASE
        if BUILD:
            text += " (" + BUILD + ")"
    except Exception:
        pass
    return text

def _armature_poll(_self, obj):
    return obj is not None and obj.type == "ARMATURE"

class SPX_Settings(PropertyGroup):
    workspace_tab: EnumProperty(
        name="功能页",
        items=(
            ("PROXY", "代理创建", "创建和编辑裙面代理、骨骼、刚体与 Joint"),
            ("BROWSER", "MMD 查看器", "查看和编辑 MMD 骨骼、刚体与 Joint"),
            ("MORPH", "Morph 编辑器", "编辑、排序、预览并为 MMD Morph 设置 Keyframe"),
            ("DISPLAY", "显示枠", "编辑 PMX 显示枠、骨骼与 Morph 显示项"),
            ("PREVIEW", "物理预览", "使用 Rust DLL 预览 MMD 物理"),
            ("IK", "MMD IK", "创建不影响 PMX 再导出的 MMD 兼容 IK Runtime"),
        ),
        default="PROXY",
    )
    topology: EnumProperty(
        name="代理拓扑",
        items=(
            ("CLOSED", "闭合", "首尾列连接为闭合代理面"),
            ("OPEN", "打开", "首尾列不连接；单列时生成可雕刻控制带与一列物理骨链"),
        ),
        default="CLOSED",
    )
    restore_connect_sides: BoolProperty(
        name="连接左右",
        description="恢复打开代理时连接左、右骨链形成连续表面；关闭时左右保持为同一 Mesh 中的两个独立表面",
        default=False,
    )
    columns: IntProperty(
        name="圆周方向",
        description="设为 1 时生成可雕刻控制带，但只创建一列骨骼与物理",
        default=8,
        min=1,
        max=128,
    )
    rows: IntProperty(
        name="最大高度层数",
        description="最长纵列使用的最大节点数，较短纵列会自动减少层数",
        default=4,
        min=2,
        max=128,
    )
    prefix: StringProperty(
        name="名称前缀",
        description="普通名称创建单侧代理；以左或右开头时识别局部 X 轴另一侧并创建同一 Mesh 内的双侧镜像代理",
        default="Skirt",
    )
    radial_offset: FloatProperty(
        name="径向偏移",
        description="沿各截面径向向外偏移代理点",
        default=0.0,
        subtype="DISTANCE",
    )
    armature: PointerProperty(
        name="目标骨架",
        description="留空时自动创建新骨架",
        type=bpy.types.Object,
        poll=_armature_poll,
    )
    parent_bone: StringProperty(name="连接骨骼", default="")
    write_weights: BoolProperty(name="生成并规格化权重", default=True)
    auto_sync: BoolProperty(
        name="离开编辑/雕刻后自动同步",
        description="编辑期间显示骨链预览，退出 Edit/Sculpt Mode 后提交实际 rest bones",
        default=True,
    )


def _selected_geometry(mesh_object):
    mesh = mesh_object.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    selected_indices = {vertex.index for vertex in bm.verts if vertex.select}
    if not selected_indices:
        raise ProxyBuildError("没有选中顶点")

    selected_faces = [
        face for face in bm.faces if all(vertex.index in selected_indices for vertex in face.verts)
    ]
    if not selected_faces:
        raise ProxyBuildError("选区必须包含完整面")

    vertices = {index: tuple(bm.verts[index].co) for index in selected_indices}
    dense_indices = sorted(vertices)
    dense_vertices = [vertices[index] for index in dense_indices]
    return selected_indices, dense_vertices


def _mirror_prefix(value):
    if value.startswith("左") and value[1:].strip():
        return value[1:].strip(), "L"
    if value.startswith("右") and value[1:].strip():
        return value[1:].strip(), "R"
    return value, ""


def _mirrored_geometry(mesh_object, selected_indices, selected_vertices):
    bm = bmesh.from_edit_mesh(mesh_object.data)
    bm.verts.ensure_lookup_table()
    source = [Vector(coordinate) for coordinate in selected_vertices]
    minimum = Vector(
        tuple(min(point[axis] for point in source) for axis in range(3))
    )
    maximum = Vector(
        tuple(max(point[axis] for point in source) for axis in range(3))
    )
    diagonal = (maximum - minimum).length
    mean_x = sum(point.x for point in source) / len(source)
    if abs(mean_x) <= max(diagonal * 0.01, 1.0e-6):
        raise ProxyBuildError("镜像模式的选区必须明确位于局部 X 轴一侧")

    candidates = [
        vertex
        for vertex in bm.verts
        if vertex.index not in selected_indices
        and vertex.co.x * mean_x <= 1.0e-8
    ]
    if not candidates:
        raise ProxyBuildError("局部 X 轴另一侧没有可用于镜像代理的顶点")
    candidate_tree = KDTree(len(candidates))
    for tree_index, vertex in enumerate(candidates):
        candidate_tree.insert(vertex.co, tree_index)
    candidate_tree.balance()

    mirrored_source = [Vector((-point.x, point.y, point.z)) for point in source]
    exact_tolerance = max(diagonal * 1.0e-5, 1.0e-6)
    exact_indices = []
    exact_distances = []
    for target in mirrored_source:
        _coordinate, tree_index, distance = candidate_tree.find(target)
        exact_indices.append(candidates[tree_index].index)
        exact_distances.append(distance)
    exact = (
        max(exact_distances, default=0.0) <= exact_tolerance
        and len(set(exact_indices)) == len(exact_indices)
    )
    if exact:
        opposite_indices = set(exact_indices)
    else:
        source_tree = KDTree(len(mirrored_source))
        for index, coordinate in enumerate(mirrored_source):
            source_tree.insert(coordinate, index)
        source_tree.balance()
        region_tolerance = max(diagonal * 0.08, exact_tolerance * 4.0)
        opposite_indices = {
            vertex.index
            for vertex in candidates
            if source_tree.find(vertex.co)[2] <= region_tolerance
        }
        opposite_indices.update(exact_indices)
    if len(opposite_indices) < 2:
        raise ProxyBuildError("无法在局部 X 轴另一侧识别对应布料区域")
    opposite_vertices = [
        tuple(bm.verts[index].co)
        for index in sorted(opposite_indices)
    ]
    return opposite_indices, opposite_vertices, exact

def _find_armature(mesh_object, requested_armature):
    if requested_armature is not None:
        return requested_armature
    for modifier in mesh_object.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is not None:
            return modifier.object
    return None

def _deform_group_names(mesh_object, armature_object):
    if armature_object is None:
        return set()
    return {bone.name for bone in armature_object.data.bones if bone.use_deform}

def _locked_weight_sum(mesh_object, vertex_index, deform_group_names):
    result = 0.0
    vertex = mesh_object.data.vertices[vertex_index]
    for membership in vertex.groups:
        group = mesh_object.vertex_groups[membership.group]
        if group.name in deform_group_names and group.lock_weight:
            result += membership.weight
    return result

def _create_proxy_mesh(
    context,
    source_object,
    prefix,
    grid,
    closed,
    column_groups=None,
):
    columns = len(grid)
    row_counts = [len(column) for column in grid]
    column_groups = list(column_groups or [0] * columns)
    vertices = grid_vertices(grid)
    faces = []
    sculpt_width = 0.0
    for group in dict.fromkeys(column_groups):
        group_columns = [
            column
            for column, column_group in enumerate(column_groups)
            if column_group == group
        ]
        if len(group_columns) != 1:
            group_grid = [grid[column] for column in group_columns]
            group_faces = grid_faces(
                group_grid,
                closed=closed,
            )
            group_offset = sum(row_counts[: group_columns[0]])
            faces.extend(
                tuple(index + group_offset for index in face)
                for face in group_faces
            )
            continue

        column = group_columns[0]
        centerline = [Vector(point) for point in grid[column]]
        segment_lengths = sorted(
            (centerline[index + 1] - centerline[index]).length
            for index in range(len(centerline) - 1)
        )
        column_width = max(
            segment_lengths[len(segment_lengths) // 2] * 0.09,
            5.0e-5,
        )
        sculpt_width = max(sculpt_width, column_width)
        offsets = (
            Vector((column_width, 0.0, 0.0)),
            Vector((-column_width, 0.0, 0.0)),
            Vector((0.0, column_width, 0.0)),
            Vector((0.0, -column_width, 0.0)),
        )
        center_offset = sum(row_counts[:column])
        for offset_vector in offsets:
            rail_offset = len(vertices)
            vertices.extend(tuple(point + offset_vector) for point in centerline)
            for row in range(len(centerline) - 1):
                faces.append(
                    (
                        center_offset + row,
                        center_offset + row + 1,
                        rail_offset + row + 1,
                        rail_offset + row,
                    )
                )
    mesh = bpy.data.meshes.new(f"{prefix}_Surface")
    mesh.from_pydata(
        vertices,
        [],
        faces,
    )
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    proxy_object = bpy.data.objects.new(f"{prefix}_Surface", mesh)
    context.collection.objects.link(proxy_object)
    place_proxy_object(context.scene, proxy_object)
    proxy_object.matrix_world = source_object.matrix_world.copy()
    proxy_object.display_type = "WIRE"
    proxy_object.show_in_front = True
    proxy_object["surface_proxy_columns"] = columns
    proxy_object["surface_proxy_max_rows"] = max(row_counts)
    proxy_object["surface_proxy_column_rows"] = row_counts
    proxy_object["surface_proxy_column_bones"] = [count - 1 for count in row_counts]
    proxy_object["surface_proxy_source"] = source_object.name
    proxy_object["surface_proxy_closed"] = closed
    proxy_object["surface_proxy_column_groups"] = column_groups
    proxy_object["surface_proxy_sculpt_width"] = sculpt_width
    return proxy_object

def _ensure_armature(context, source_object, requested_armature, prefix):
    if requested_armature is not None:
        if not any(
            modifier.type == "ARMATURE" and modifier.object == requested_armature
            for modifier in source_object.modifiers
        ):
            modifier = source_object.modifiers.new(
                name=f"{prefix}_Armature", type="ARMATURE"
            )
            modifier.object = requested_armature
        return requested_armature, False
    armature_data = bpy.data.armatures.new(f"{prefix}_Rig")
    armature_object = bpy.data.objects.new(f"{prefix}_Rig", armature_data)
    context.collection.objects.link(armature_object)
    place_proxy_object(context.scene, armature_object)
    armature_object.matrix_world = source_object.matrix_world.copy()
    modifier = source_object.modifiers.new(name=f"{prefix}_Armature", type="ARMATURE")
    modifier.object = armature_object
    return armature_object, True

def _column_bone_name(prefix, column, row, column_sides, local_indices):
    side = column_sides[column] if column < len(column_sides) else ""
    local_column = local_indices[column] if column < len(local_indices) else column
    return bone_name(prefix, local_column, row, side)


def _preflight_output_names(
    prefix,
    armature_object,
    parent_bone,
    grid,
    column_sides,
    local_indices,
):
    if bpy.data.objects.get(f"{prefix}_Surface") is not None:
        raise ProxyBuildError(f"对象已存在：{prefix}_Surface")
    if bpy.data.meshes.get(f"{prefix}_Surface") is not None:
        raise ProxyBuildError(f"Mesh 数据已存在：{prefix}_Surface")
    if armature_object is None:
        if parent_bone:
            raise ProxyBuildError("自动创建新骨架时不能指定连接骨骼")
        if bpy.data.objects.get(f"{prefix}_Rig") is not None:
            raise ProxyBuildError(f"对象已存在：{prefix}_Rig")
        if bpy.data.armatures.get(f"{prefix}_Rig") is not None:
            raise ProxyBuildError(f"Armature 数据已存在：{prefix}_Rig")
        return

    existing_names = set(armature_object.data.bones.keys())
    if parent_bone and parent_bone not in existing_names:
        raise ProxyBuildError(f"连接骨骼不存在：{parent_bone}")
    for column, column_points in enumerate(grid):
        for row in range(len(column_points) - 1):
            name = _column_bone_name(
                prefix, column, row, column_sides, local_indices
            )
            if name in existing_names:
                raise ProxyBuildError(f"骨骼名称已存在：{name}")

def _create_bones(
    context,
    source_object,
    armature_object,
    prefix,
    grid,
    parent_bone,
    column_sides,
    local_indices,
):
    existing_names = set(armature_object.data.bones.keys())
    names = [
        _column_bone_name(prefix, column, row, column_sides, local_indices)
        for column, column_points in enumerate(grid)
        for row in range(len(column_points) - 1)
    ]
    collisions = sorted(existing_names.intersection(names))
    if collisions:
        raise ProxyBuildError(f"骨骼名称已存在：{collisions[0]}")
    if parent_bone and parent_bone not in existing_names:
        raise ProxyBuildError(f"连接骨骼不存在：{parent_bone}")

    source_to_armature = armature_object.matrix_world.inverted() @ source_object.matrix_world
    previous_active = context.view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    if previous_active is not None and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = armature_object
    armature_object.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for column, column_points in enumerate(grid):
            previous_bone = None
            for row in range(len(column_points) - 1):
                edit_bone = armature_object.data.edit_bones.new(
                    _column_bone_name(
                        prefix, column, row, column_sides, local_indices
                    )
                )
                head = source_to_armature @ Vector(column_points[row])
                tail = source_to_armature @ Vector(column_points[row + 1])
                if (tail - head).length <= 1.0e-7:
                    raise ProxyBuildError("生成了零长度骨骼")
                edit_bone.head = head
                edit_bone.tail = tail
                edit_bone.use_deform = True
                edit_bone.inherit_scale = "NONE"
                if previous_bone is not None:
                    edit_bone.parent = previous_bone
                    edit_bone.use_connect = False
                elif parent_bone:
                    edit_bone.parent = armature_object.data.edit_bones[parent_bone]
                    edit_bone.use_connect = False
                previous_bone = edit_bone
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        context.view_layer.objects.active = armature_object
    name_metadata = []
    for column, column_points in enumerate(grid):
        side = column_sides[column] if column < len(column_sides) else ""
        local_column = local_indices[column] if column < len(local_indices) else column
        for row in range(len(column_points) - 1):
            name_metadata.append((
                _column_bone_name(prefix, column, row, column_sides, local_indices),
                bone_name(prefix, local_column, row),
                side,
            ))
    for name, stem, side in name_metadata:
        pose_bone = armature_object.pose.bones.get(name)
        if pose_bone is None or not hasattr(pose_bone, "mmd_bone"):
            continue
        if not pose_bone.mmd_bone.name_j.strip():
            pose_bone.mmd_bone.name_j = (
                f"{'左' if side == 'L' else '右'}{stem}"
                if side
                else stem
            )
        if not pose_bone.mmd_bone.name_e.strip():
            pose_bone.mmd_bone.name_e = f"{stem}_{side}" if side else stem
    return names

def _write_weights(
    mesh_object,
    armature_object,
    selected_indices,
    prefix,
    grid,
    closed,
    column_sides=None,
    local_indices=None,
):
    column_sides = list(column_sides or [""] * len(grid))
    local_indices = list(local_indices or range(len(grid)))
    deform_group_names = _deform_group_names(mesh_object, armature_object)
    locked_sums = {
        index: _locked_weight_sum(mesh_object, index, deform_group_names)
        for index in selected_indices
    }
    invalid = [index for index, total in locked_sums.items() if total > 1.000001]
    if invalid:
        raise ProxyBuildError(
            f"顶点 {invalid[0]} 的锁定 deform 权重之和超过 1，无法保持并规格化"
        )

    generated_groups = {}
    for column, column_points in enumerate(grid):
        for row in range(len(column_points) - 1):
            name = _column_bone_name(
                prefix, column, row, column_sides, local_indices
            )
            generated_groups[(column, row)] = mesh_object.vertex_groups.get(name) or mesh_object.vertex_groups.new(name=name)

    current_deform_names = _deform_group_names(mesh_object, armature_object)
    unlocked_deform_groups = [
        group
        for group in mesh_object.vertex_groups
        if group.name in current_deform_names and not group.lock_weight
    ]
    for vertex_index in sorted(selected_indices):
        for group in unlocked_deform_groups:
            group.remove([vertex_index])
        available = max(0.0, 1.0 - locked_sums[vertex_index])
        weights = bilinear_grid_weights(
            tuple(mesh_object.data.vertices[vertex_index].co),
            grid,
            closed=closed,
        )
        for key, weight in weights.items():
            generated_groups[key].add([vertex_index], available * weight, "REPLACE")


def _bone_side(name):
    for suffix, side in ((".L", "L"), (".R", "R"), ("_L", "L"), ("_R", "R")):
        if name.endswith(suffix):
            return name[:-2], side
    if name.endswith("_M"):
        return name[:-2], ""
    return name, ""


def _derived_proxy_prefix(names):
    stems = [_bone_side(name)[0] for name in names]
    subjects = set()
    for stem in stems:
        grid_match = re.match(r"^(.+)_[A-Z]+\d+$", stem)
        subject = (
            grid_match.group(1)
            if grid_match
            else re.sub(r"\d+$", "", stem)
        )
        subjects.add(re.sub(r"[\s._-]+$", "", subject))
    subjects.discard("")
    return next(iter(subjects)) if len(subjects) == 1 else ""


def _spatially_ordered_chains(chains, closed):
    if len(chains) < 2:
        return list(chains)
    roots = [Vector(chain[0].head_local) for chain in chains]
    if closed:
        center = sum(roots, Vector()) / len(roots)
        return sorted(
            chains,
            key=lambda chain: (
                atan2(
                    chain[0].head_local[1] - center.y,
                    chain[0].head_local[0] - center.x,
                ),
                chain[0].name,
            ),
        )
    first = roots[0]
    second = roots[1]
    longest = -1.0
    for left in range(len(roots)):
        for right in range(left + 1, len(roots)):
            delta = roots[right] - roots[left]
            distance = delta.x * delta.x + delta.y * delta.y
            if distance > longest:
                first = roots[left]
                second = roots[right]
                longest = distance
    axis = Vector((second.x - first.x, second.y - first.y, 0.0))
    if axis.length_squared <= 1.0e-12:
        axis = Vector((1.0, 0.0, 0.0))
    else:
        axis.normalize()
    if (abs(axis.x) >= abs(axis.y) and axis.x < 0.0) or (
        abs(axis.y) > abs(axis.x) and axis.y < 0.0
    ):
        axis.negate()
    return sorted(
        chains,
        key=lambda chain: (Vector(chain[0].head_local).dot(axis), chain[0].name),
    )


def _hierarchy_chains(armature_object, bone_names):
    selected = set(bone_names)
    bones = {name: armature_object.data.bones.get(name) for name in selected}
    missing = sorted(name for name, bone in bones.items() if bone is None)
    if missing:
        raise ProxyBuildError(f"骨骼不存在：{missing[0]}")
    roots = [
        bone
        for bone in bones.values()
        if bone.parent is None or bone.parent.name not in selected
    ]
    chains = []
    consumed = set()
    for root in roots:
        chain = []
        bone = root
        while bone is not None:
            chain.append(bone)
            consumed.add(bone.name)
            children = [child for child in bone.children if child.name in selected]
            if len(children) > 1:
                raise ProxyBuildError(
                    f"骨链在 {bone.name} 处分叉；请只勾选不分叉的纵向骨链"
                )
            bone = children[0] if children else None
        chains.append(chain)
    if consumed != selected:
        raise ProxyBuildError("勾选骨骼无法解析为完整父子骨链")
    return chains


def _grid_is_exact_mirror(grid, column_sides):
    left = [grid[index] for index, side in enumerate(column_sides) if side == "L"]
    right = [grid[index] for index, side in enumerate(column_sides) if side == "R"]
    if not left or len(left) != len(right):
        return False
    diagonal = max(
        (Vector(point).length for column in grid for point in column),
        default=1.0,
    )
    tolerance = max(diagonal * 1.0e-5, 1.0e-6)
    unused = set(range(len(right)))
    for left_column in left:
        candidates = [
            right_index
            for right_index in unused
            if len(right[right_index]) == len(left_column)
        ]
        if not candidates:
            return False
        right_index = min(
            candidates,
            key=lambda index: sum(
                (
                    Vector(left_column[row])
                    - Vector(
                        (
                            -right[index][row][0],
                            right[index][row][1],
                            right[index][row][2],
                        )
                    )
                ).length_squared
                for row in range(len(left_column))
            ),
        )
        if any(
            (
                Vector(left_column[row])
                - Vector(
                    (
                        -right[right_index][row][0],
                        right[right_index][row][1],
                        right[right_index][row][2],
                    )
                )
            ).length
            > tolerance
            for row in range(len(left_column))
        ):
            return False
        unused.remove(right_index)
    return True


def _proxy_grid_from_checked_bones(settings):
    checked = [
        item
        for item in settings.browser_items
        if item.kind == "BONE" and item.selected
    ]
    if not checked:
        raise ProxyBuildError("MMD 查看器中没有勾选骨骼")
    armature_names = {item.armature_name for item in checked}
    if len(armature_names) != 1:
        raise ProxyBuildError("勾选骨骼必须属于同一个 Armature")
    armature_object = bpy.data.objects.get(next(iter(armature_names)))
    if armature_object is None or armature_object.type != "ARMATURE":
        raise ProxyBuildError("勾选骨骼所属的 Armature 不存在")

    pattern = re.compile(r"^(.+)_C(\d+)_R(\d+)$")
    layout = {}
    prefixes = set()
    formats = set()
    legacy = True
    for item in checked:
        stem, side = _bone_side(item.target_name)
        match = pattern.match(stem)
        if match is None:
            legacy = False
            break
        prefixes.add(match.group(1))
        formats.add(bool(side))
        key = (side, int(match.group(2)) - 1)
        row = int(match.group(3)) - 1
        bone = armature_object.data.bones.get(item.target_name)
        if bone is None:
            raise ProxyBuildError(f"骨骼不存在：{item.target_name}")
        if row in layout.setdefault(key, {}):
            raise ProxyBuildError(f"骨骼编号重复：{item.target_name}")
        layout[key][row] = bone
    closed = settings.topology == "CLOSED"
    bone_names = []
    if legacy:
        if len(prefixes) != 1:
            raise ProxyBuildError("勾选骨骼的名称前缀必须统一")
        if len(formats) != 1:
            raise ProxyBuildError("不能混合普通骨骼与左右镜像骨骼")
        prefix = next(iter(prefixes))
        ordered_keys = sorted(
            layout,
            key=lambda key: (("L", "R", "").index(key[0]), key[1]),
        )
        grid = []
        column_sides = []
        local_indices = []
        for side, column in ordered_keys:
            rows = layout[(side, column)]
            if sorted(rows) != list(range(len(rows))):
                raise ProxyBuildError(
                    f"{side or '普通'} C{column + 1:02d} 的层编号必须从 R01 连续排列"
                )
            points = [tuple(rows[row].head_local) for row in range(len(rows))]
            points.append(tuple(rows[len(rows) - 1].tail_local))
            grid.append(points)
            bone_names.extend(rows[row].name for row in range(len(rows)))
            column_sides.append(side)
            local_indices.append(column)
    else:
        chains = _hierarchy_chains(
            armature_object,
            [item.target_name for item in checked],
        )
        if not chains:
            raise ProxyBuildError("没有找到可恢复的父子骨链")
        prefix = _derived_proxy_prefix([chain[0].name for chain in chains])
        if not prefix:
            raise ProxyBuildError(
                "勾选的独立骨链主体名称不一致；请按主体分别创建代理"
            )
        for chain in chains:
            sides = {_bone_side(bone.name)[1] for bone in chain}
            if len(sides) != 1:
                raise ProxyBuildError(
                    f"同一父子骨链的左右后缀必须统一：{chain[0].name}"
                )
        if closed or not settings.restore_connect_sides:
            side_order = {"L": 0, "R": 1, "": 2}
            ordered_chains = []
            for side in sorted(
                {_bone_side(chain[0].name)[1] for chain in chains},
                key=lambda value: side_order[value],
            ):
                side_chains = [
                    chain
                    for chain in chains
                    if _bone_side(chain[0].name)[1] == side
                ]
                ordered_chains.extend(_spatially_ordered_chains(side_chains, closed))
            chains = ordered_chains
        else:
            chains = _spatially_ordered_chains(chains, False)
        grid = [
            [tuple(bone.head_local) for bone in chain] + [tuple(chain[-1].tail_local)]
            for chain in chains
        ]
        bone_names = [bone.name for chain in chains for bone in chain]
        column_sides = [_bone_side(chain[0].name)[1] for chain in chains]
        side_counts = {side: 0 for side in column_sides}
        local_indices = []
        for side in column_sides:
            local_indices.append(side_counts[side])
            side_counts[side] += 1

    mirrored = set(column_sides) == {"L", "R"}
    if not closed and settings.restore_connect_sides:
        column_groups = [0] * len(grid)
    elif mirrored or len(set(column_sides)) > 1:
        side_groups = {
            side: index for index, side in enumerate(dict.fromkeys(column_sides))
        }
        column_groups = [side_groups[side] for side in column_sides]
    else:
        column_groups = [0] * len(grid)
    if closed:
        for group in dict.fromkeys(column_groups):
            group_column_count = sum(value == group for value in column_groups)
            if group_column_count < 3:
                raise ProxyBuildError(
                    "闭合代理的每个独立组至少需要三列骨链"
                )

    mirror_exact = mirrored and _grid_is_exact_mirror(grid, column_sides)
    return (
        armature_object,
        prefix,
        grid,
        closed,
        column_groups,
        column_sides,
        local_indices,
        mirrored,
        mirror_exact,
        bone_names,
    )


def _proxy_bone_names(proxy_object):
    stored_names = list(proxy_object.get("surface_proxy_bone_names", []))
    if stored_names:
        return stored_names

    prefix = str(proxy_object.get("surface_proxy_prefix", ""))
    row_counts = list(proxy_object.get("surface_proxy_column_rows", []))
    if not prefix or not row_counts:
        return []
    column_sides = list(proxy_object.get("surface_proxy_column_sides", []))
    local_indices = list(
        proxy_object.get("surface_proxy_column_local_indices", [])
    )
    if len(column_sides) != len(row_counts):
        column_sides = [""] * len(row_counts)
    if len(local_indices) != len(row_counts):
        local_indices = list(range(len(row_counts)))
    return [
        _column_bone_name(prefix, column, row, column_sides, local_indices)
        for column, count in enumerate(row_counts)
        for row in range(count - 1)
    ]


def _existing_proxy_for_bones(armature_object, bone_names):
    selected_names = set(bone_names)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if str(obj.get("surface_proxy_armature", "")) != armature_object.name:
            continue
        if set(_proxy_bone_names(obj)) == selected_names:
            return obj
    return None


class SPX_OT_RestoreProxyFromCheckedBones(Operator):
    bl_idname = "surface_proxy.restore_proxy_from_checked_bones"
    bl_label = "从勾选骨骼恢复或新建代理"
    bl_description = "按 MMD 查看器中勾选的同前缀代理骨链恢复已有代理 Mesh；不存在时新建"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            (
                armature_object,
                prefix,
                grid,
                closed,
                column_groups,
                column_sides,
                local_indices,
                mirrored,
                mirror_exact,
                bone_names,
            ) = _proxy_grid_from_checked_bones(settings)
            existing = _existing_proxy_for_bones(armature_object, bone_names)
            if existing is not None:
                self.report(
                    {"WARNING"},
                    f"这段骨链已有代理 {existing.name}；请先删除旧代理后再创建",
                )
                return {"CANCELLED"}
            if context.object is not None and context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            proxy_object = _create_proxy_mesh(
                context,
                armature_object,
                prefix,
                grid,
                closed,
                column_groups,
            )
            initialize_proxy_identity(
                proxy_object,
                armature_object,
                prefix,
                grid,
                closed,
            )
            proxy_object["surface_proxy_column_groups"] = column_groups
            proxy_object["surface_proxy_column_sides"] = column_sides
            proxy_object["surface_proxy_column_local_indices"] = local_indices
            proxy_object["surface_proxy_mirror_mode"] = mirrored
            proxy_object["surface_proxy_mirror_exact"] = mirror_exact
            proxy_object["surface_proxy_bone_names"] = bone_names
            proxy_object.data.use_mirror_x = bool(mirrored and mirror_exact)
            proxy_object["surface_proxy_armature"] = armature_object.name
            rigid_count, joint_count = associate_existing_proxy_physics(proxy_object)
            settings.armature = armature_object
            settings.prefix = prefix
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"已新建 {proxy_object.name}：{len(grid)} 列、{sum(len(column) - 1 for column in grid)} 根骨骼"
            + (
                f"；已关联 {rigid_count} 个刚体、{joint_count} 个 Joint"
                if rigid_count or joint_count
                else ""
            )
            + ("；已启用 X Mirror" if mirror_exact else ""),
        )
        return {"FINISHED"}

class SPX_OT_CreateSkirtProxy(Operator):
    bl_idname = "surface_proxy.create_skirt_proxy"
    bl_label = "从选区创建裙面代理"
    bl_description = "从编辑模式选区拟合闭合面、开放面或单列可雕刻控制带，创建纵列骨并重建选区 deform 权重"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        source_object = context.edit_object
        settings = context.scene.surface_proxy_creator
        raw_prefix = settings.prefix.strip()
        prefix, selected_side = _mirror_prefix(raw_prefix)
        if not prefix:
            self.report({"ERROR"}, "名称前缀不能为空")
            return {"CANCELLED"}

        try:
            selected_indices, vertices = _selected_geometry(source_object)
            requested_armature = _find_armature(source_object, settings.armature)
            deform_group_names = _deform_group_names(source_object, requested_armature)
            opposite_indices = set()
            opposite_vertices = []
            mirror_exact = False
            if selected_side:
                opposite_indices, opposite_vertices, mirror_exact = _mirrored_geometry(
                    source_object, selected_indices, vertices
                )
            if settings.write_weights:
                for vertex_index in selected_indices | opposite_indices:
                    if _locked_weight_sum(source_object, vertex_index, deform_group_names) > 1.000001:
                        raise ProxyBuildError(
                            f"顶点 {vertex_index} 的锁定 deform 权重之和超过 1"
                        )

            closed = settings.topology == "CLOSED" and settings.columns != 1
            selected_grid = build_cylindrical_surface_grid(
                vertices,
                settings.columns,
                settings.rows,
                settings.radial_offset,
                closed=closed,
            )
            if selected_side:
                if mirror_exact:
                    opposite_grid = [
                        [(-point[0], point[1], point[2]) for point in column]
                        for column in selected_grid
                    ]
                else:
                    opposite_grid = build_cylindrical_surface_grid(
                        opposite_vertices,
                        settings.columns,
                        settings.rows,
                        settings.radial_offset,
                        closed=closed,
                    )
                if selected_side == "L":
                    left_grid, right_grid = selected_grid, opposite_grid
                    left_indices, right_indices = selected_indices, opposite_indices
                else:
                    left_grid, right_grid = opposite_grid, selected_grid
                    left_indices, right_indices = opposite_indices, selected_indices
                grid = [*left_grid, *right_grid]
                group_width = len(left_grid)
                column_groups = [0] * group_width + [1] * len(right_grid)
                column_sides = ["L"] * group_width + ["R"] * len(right_grid)
                local_indices = list(range(group_width)) + list(range(len(right_grid)))
                weight_tasks = (
                    (left_indices, left_grid, "L"),
                    (right_indices, right_grid, "R"),
                )
            else:
                grid = selected_grid
                column_groups = [0] * len(grid)
                column_sides = [""] * len(grid)
                local_indices = list(range(len(grid)))
                weight_tasks = ((selected_indices, grid, ""),)
            _preflight_output_names(
                prefix,
                requested_armature,
                settings.parent_bone.strip(),
                grid,
                column_sides,
                local_indices,
            )

            bpy.ops.object.mode_set(mode="OBJECT")
            proxy_object = _create_proxy_mesh(
                context,
                source_object,
                prefix,
                grid,
                closed,
                column_groups,
            )
            armature_object, _created = _ensure_armature(
                context, source_object, requested_armature, prefix
            )
            created_bone_names = _create_bones(
                context,
                source_object,
                armature_object,
                prefix,
                grid,
                settings.parent_bone.strip(),
                column_sides,
                local_indices,
            )
            initialize_proxy_identity(
                proxy_object,
                armature_object,
                prefix,
                grid,
                closed,
            )
            proxy_object["surface_proxy_column_groups"] = column_groups
            proxy_object["surface_proxy_column_sides"] = column_sides
            proxy_object["surface_proxy_column_local_indices"] = local_indices
            proxy_object["surface_proxy_bone_names"] = created_bone_names
            proxy_object["surface_proxy_mirror_mode"] = bool(selected_side)
            proxy_object["surface_proxy_mirror_exact"] = bool(mirror_exact)
            proxy_object.data.use_mirror_x = bool(selected_side and mirror_exact)
            if settings.write_weights:
                for indices, side_grid, side in weight_tasks:
                    _write_weights(
                        source_object,
                        armature_object,
                        indices,
                        prefix,
                        side_grid,
                        closed,
                        [side] * len(side_grid),
                        list(range(len(side_grid))),
                    )
            proxy_object["surface_proxy_armature"] = armature_object.name
            settings.physics_proxy = proxy_object
            context.view_layer.objects.active = proxy_object
            proxy_object.select_set(True)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        row_counts = [len(column) for column in grid]
        bone_count = sum(count - 1 for count in row_counts)
        self.report(
            {"INFO"},
            f"已创建 {len(grid)} 列{('闭合面' if closed else '开放代理')}、每列 {min(row_counts)}–{max(row_counts)} 个代理点，共 {bone_count} 根骨骼"
            + (f"；镜像侧按{'精确镜像' if mirror_exact else '独立拟合'}生成" if selected_side else ""),
        )
        return {"FINISHED"}

def draw_workspace(layout, context):
    settings = context.scene.surface_proxy_creator
    draw_mmd_io(layout)
    tabs = layout.row(align=True)
    tabs.scale_y = 1.2
    tabs.prop(settings, "workspace_tab", expand=True)
    if settings.workspace_tab == "PROXY":
        draw_physics_settings(layout, settings, context)
    elif settings.workspace_tab == "BROWSER":
        draw_browser(layout, settings)
    elif settings.workspace_tab == "MORPH":
        draw_morph_editor(layout, context)
    elif settings.workspace_tab == "DISPLAY":
        draw_display_frame_editor(layout, context)
    elif settings.workspace_tab == "PREVIEW":
        draw_preview(layout, settings)
    else:
        draw_mmd_ik_runtime(layout, settings, context)


class SPX_PT_SurfaceProxyCreator(Panel):
    bl_label = "MMD Station"
    bl_idname = "SPX_PT_surface_proxy_creator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD Station"

    def draw(self, context):
        updater_notify.draw_update_banner(self, context)
        column = self.layout.column(align=True)
        title_row = column.row(align=True)
        title_row.label(text="MMD 模型制作工具", icon="TOOL_SETTINGS")
        repository = title_row.operator("wm.url_open", text="GitHub", icon="URL")
        package = sys.modules.get(__package__ or "mmd_station")
        repository.url = getattr(package, "bl_info", {}).get("doc_url", "")
        column.label(text=_version_text(), icon="BLANK1")
        draw_workspace(self.layout, context)


CLASSES = (
    MMD_PHYSICS_CLASSES[0],
    MMD_PHYSICS_CLASSES[1],
    SPX_Settings,
    *SYNC_CLASSES,
    *MMD_PHYSICS_CLASSES[2:],
    *BONE_PHYSICS_CREATOR_CLASSES,
    *MMD_MATERIAL_ORDER_CLASSES,
    *MMD_ORDERING_CLASSES,
    *MMD_BONE_SUBDIVISION_CLASSES,
    *MMD_MORPH_EDITOR_CLASSES,
    *MMD_DISPLAY_FRAME_CLASSES,
    *MMD_IO_CLASSES,
    *PHYSICS_PREVIEW_CLASSES,
    *MMD_IK_RUNTIME_CLASSES,
    *VERTEX_GROUP_TOOL_CLASSES,
    SPX_OT_RestoreProxyFromCheckedBones,
    SPX_OT_CreateSkirtProxy,
    SPX_PT_SurfaceProxyCreator,
)


def register():
    preload_physics_libraries()
    register_physics_cache_services()
    register_settings(SPX_Settings)
    register_preview_settings(SPX_Settings)
    register_bake_settings(SPX_Settings)
    register_bone_physics_creator_settings(SPX_Settings)
    register_bone_subdivision_settings(SPX_Settings)
    register_mmd_ik_runtime_settings(SPX_Settings)
    register_morph_editor_settings(SPX_Settings)
    register_display_frame_settings(SPX_Settings)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.surface_proxy_creator = PointerProperty(type=SPX_Settings)
    register_material_export_hook()
    register_morph_order_export_hook()
    register_export_profile_hook()
    register_shadow_services()
    register_sync_services()
    register_browser_auto_refresh()
    register_browser_context_menu()
    register_vertex_group_menu()
    register_mmd_ik_runtime_services()
    register_morph_editor_services()
    register_display_frame_services()
    updater.register()


def unregister():
    updater.unregister()
    unregister_shadow_services()
    unregister_export_profile_hook()
    unregister_morph_order_export_hook()
    unregister_material_export_hook()
    unregister_display_frame_services()
    unregister_morph_editor_services()
    unregister_mmd_ik_runtime_services()
    unregister_preview_runtime()
    unregister_vertex_group_menu()
    unregister_browser_context_menu()
    unregister_browser_auto_refresh()
    unregister_sync_services()
    del bpy.types.Scene.surface_proxy_creator
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
