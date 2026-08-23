import hashlib
import re

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.types import Operator
from mathutils import Vector

from .core import ProxyBuildError, bilinear_grid_weights, bone_name, proxy_bone_name


SCHEMA_VERSION = 2
_DIRTY_PHYSICS_PROXIES = set()
_PROXY_MODES = {}
_TIMER_PENDING = False
_DRAW_HANDLE = None


def _prefix_from_name(name):
    match = re.match(r"^(.*)_Surface(?:\.\d+)?$", name)
    return match.group(1) if match else ""


def _mesh_state(proxy_object):
    if proxy_object.mode == "EDIT":
        bm = bmesh.from_edit_mesh(proxy_object.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        coordinates = [vertex.co.copy() for vertex in bm.verts]
        edges = [(edge.verts[0].index, edge.verts[1].index) for edge in bm.edges]
    else:
        coordinates = [vertex.co.copy() for vertex in proxy_object.data.vertices]
        edges = [(edge.vertices[0], edge.vertices[1]) for edge in proxy_object.data.edges]
    normalized_edges = sorted(tuple(sorted(edge)) for edge in edges)
    payload = f"{len(coordinates)}|{normalized_edges}".encode("ascii")
    return coordinates, hashlib.sha256(payload).hexdigest()


def _matching_armature(prefix):
    pattern = re.compile(rf"^{re.escape(prefix)}_C\d+_R\d+(?:\.[LR])?$")
    matches = []
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and any(pattern.match(bone.name) for bone in obj.data.bones):
            matches.append(obj)
    if len(matches) != 1:
        raise ProxyBuildError(
            "无法唯一确定代理骨架" if matches else "没有找到与代理名称匹配的骨架"
        )
    return matches[0]


def _bone_layout(armature_object, prefix):
    pattern = re.compile(
        rf"^{re.escape(prefix)}_C(?P<column>\d+)_R(?P<row>\d+)(?:\.(?P<side>[LR]))?$"
    )
    keyed_layout = {}
    for bone in armature_object.data.bones:
        match = pattern.match(bone.name)
        if match:
            column = int(match.group("column")) - 1
            row = int(match.group("row")) - 1
            side = match.group("side") or ""
            keyed_layout.setdefault((side, column), {})[row] = bone
    if not keyed_layout:
        raise ProxyBuildError("没有找到代理骨骼")
    ordered_keys = sorted(
        keyed_layout,
        key=lambda key: (("L", "R", "").index(key[0]), key[1]),
    )
    for side in {key[0] for key in ordered_keys}:
        columns = sorted(key[1] for key in ordered_keys if key[0] == side)
        if columns != list(range(len(columns))):
            raise ProxyBuildError("代理骨骼列编号不连续")
    layout = {index: keyed_layout[key] for index, key in enumerate(ordered_keys)}
    if not layout:
        raise ProxyBuildError("代理骨骼列编号不连续")
    row_counts = []
    for column in range(len(layout)):
        rows = layout[column]
        if sorted(rows) != list(range(len(rows))):
            raise ProxyBuildError(f"代理第 {column + 1} 列骨骼编号不连续")
        row_counts.append(len(rows) + 1)
    sides = [key[0] for key in ordered_keys]
    local_indices = [key[1] for key in ordered_keys]
    groups = [0 if side in {"", "L"} else 1 for side in sides]
    return layout, row_counts, sides, local_indices, groups


def _recover_vertex_map(proxy_object, armature_object, layout, row_counts):
    coordinates, _signature = _mesh_state(proxy_object)
    if len(coordinates) < sum(row_counts):
        raise ProxyBuildError("代理顶点数量少于骨链控制点数量")
    armature_to_proxy = proxy_object.matrix_world.inverted() @ armature_object.matrix_world
    targets = []
    for column, count in enumerate(row_counts):
        rows = layout[column]
        for row in range(count - 1):
            targets.append(armature_to_proxy @ rows[row].head_local)
        targets.append(armature_to_proxy @ rows[count - 2].tail_local)

    available = set(range(len(coordinates)))
    vertex_map = []
    maximum_distance = 0.0
    for target in targets:
        index = min(available, key=lambda candidate: (coordinates[candidate] - target).length)
        maximum_distance = max(maximum_distance, (coordinates[index] - target).length)
        vertex_map.append(index)
        available.remove(index)
    diagonal = max((point - coordinates[0]).length for point in coordinates)
    if maximum_distance > max(diagonal * 0.1, 1.0e-5):
        raise ProxyBuildError("代理顶点与骨链位置差异过大，无法安全恢复映射")
    return vertex_map


def _infer_closed(proxy_object, row_counts, vertex_map):
    if len(row_counts) < 3:
        return False
    edge_keys = {
        tuple(sorted(edge.vertices))
        for edge in proxy_object.data.edges
    }
    first = set(vertex_map[: row_counts[0]])
    last_offset = sum(row_counts[:-1])
    last = set(vertex_map[last_offset : last_offset + row_counts[-1]])
    return any(
        tuple(sorted((first_vertex, last_vertex))) in edge_keys
        for first_vertex in first
        for last_vertex in last
    )


def identify_proxy(proxy_object):
    if proxy_object is None or proxy_object.type != "MESH":
        raise ProxyBuildError("请选择代理 Mesh")
    stored_prefix = str(proxy_object.get("surface_proxy_prefix", ""))
    name_prefix = _prefix_from_name(proxy_object.name)
    armature_name = str(proxy_object.get("surface_proxy_armature", ""))
    stored_armature = bpy.data.objects.get(armature_name)
    armatures = (
        [stored_armature]
        if stored_armature is not None and stored_armature.type == "ARMATURE"
        else [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    )
    candidates = []
    portable_pattern = re.compile(r"^(?P<prefix>.+)_C\d+_R\d+(?:\.[LR])?$")
    for armature_object in armatures:
        prefixes = [prefix for prefix in (stored_prefix, name_prefix) if prefix]
        prefixes.extend(
            match.group("prefix")
            for bone in armature_object.data.bones
            if (match := portable_pattern.match(bone.name)) is not None
        )
        for prefix in dict.fromkeys(prefixes):
            try:
                layout, row_counts, sides, local_indices, groups = _bone_layout(
                    armature_object, prefix
                )
                vertex_map = _recover_vertex_map(
                    proxy_object, armature_object, layout, row_counts
                )
            except ProxyBuildError:
                continue
            candidates.append(
                (
                    armature_object,
                    prefix,
                    layout,
                    row_counts,
                    vertex_map,
                    sides,
                    local_indices,
                    groups,
                )
            )
    if len(candidates) != 1:
        raise ProxyBuildError(
            "无法唯一恢复代理身份" if candidates else "没有找到与所选网格匹配的代理骨链"
        )
    (
        armature_object,
        prefix,
        layout,
        row_counts,
        vertex_map,
        sides,
        local_indices,
        groups,
    ) = candidates[0]
    _coordinates, signature = _mesh_state(proxy_object)
    proxy_object["surface_proxy_schema"] = SCHEMA_VERSION
    proxy_object["surface_proxy_prefix"] = prefix
    proxy_object["surface_proxy_columns"] = len(row_counts)
    proxy_object["surface_proxy_max_rows"] = max(row_counts)
    proxy_object["surface_proxy_column_rows"] = row_counts
    proxy_object["surface_proxy_column_bones"] = [count - 1 for count in row_counts]
    proxy_object["surface_proxy_vertex_map"] = vertex_map
    proxy_object["surface_proxy_topology"] = signature
    proxy_object["surface_proxy_armature"] = armature_object.name
    proxy_object["surface_proxy_column_sides"] = sides
    proxy_object["surface_proxy_column_local_indices"] = local_indices
    proxy_object["surface_proxy_column_groups"] = groups
    proxy_object["surface_proxy_mirror_mode"] = any(sides)
    if "surface_proxy_closed" not in proxy_object:
        proxy_object["surface_proxy_closed"] = _infer_closed(
            proxy_object,
            row_counts,
            vertex_map,
        )
    proxy_object.display_type = "WIRE"
    proxy_object.show_in_front = True
    return armature_object, prefix, row_counts, vertex_map


def initialize_proxy_identity(proxy_object, armature_object, prefix, grid, closed=True):
    row_counts = [len(column) for column in grid]
    _coordinates, signature = _mesh_state(proxy_object)
    proxy_object["surface_proxy_schema"] = SCHEMA_VERSION
    proxy_object["surface_proxy_prefix"] = prefix
    proxy_object["surface_proxy_vertex_map"] = list(range(sum(row_counts)))
    proxy_object["surface_proxy_topology"] = signature
    proxy_object["surface_proxy_armature"] = armature_object.name
    proxy_object["surface_proxy_closed"] = bool(closed)


def _source_meshes(proxy_object, armature_object, generated_names):
    source_name = str(proxy_object.get("surface_proxy_source", ""))
    candidates = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj == proxy_object:
            continue
        uses_armature = any(
            modifier.type == "ARMATURE" and modifier.object == armature_object
            for modifier in obj.modifiers
        )
        if not uses_armature and obj.name != source_name:
            continue
        affected = [
            vertex.index
            for vertex in obj.data.vertices
            if any(
                obj.vertex_groups[membership.group].name in generated_names
                and membership.weight > 1.0e-8
                for membership in vertex.groups
            )
        ]
        if affected:
            candidates.append((obj, affected))
    if not candidates:
        raise ProxyBuildError("没有找到包含当前代理骨骼权重的原网格")
    proxy_object["surface_proxy_sources"] = "\n".join(
        obj.name for obj, _affected in candidates
    )
    return candidates


def rebind_proxy_weights(proxy_object):
    armature_object = bpy.data.objects.get(str(proxy_object["surface_proxy_armature"]))
    prefix = str(proxy_object["surface_proxy_prefix"])
    row_counts = list(proxy_object["surface_proxy_column_rows"])
    vertex_map = list(proxy_object["surface_proxy_vertex_map"])
    coordinates, signature = _mesh_state(proxy_object)
    if signature != str(proxy_object["surface_proxy_topology"]):
        raise ProxyBuildError("代理拓扑已改变，不能重新计算权重")
    generated_names = {
        proxy_bone_name(proxy_object, prefix, column, row)
        for column, count in enumerate(row_counts)
        for row in range(count - 1)
    }
    source_meshes = _source_meshes(
        proxy_object, armature_object, generated_names
    )
    deform_names = {
        bone.name for bone in armature_object.data.bones if bone.use_deform
    }
    locked_sums = {}
    for source_object, affected in source_meshes:
        object_sums = {}
        for vertex_index in affected:
            total = 0.0
            for membership in source_object.data.vertices[vertex_index].groups:
                group = source_object.vertex_groups[membership.group]
                if group.name in deform_names and group.lock_weight:
                    total += membership.weight
            if total > 1.000001:
                raise ProxyBuildError(
                    f"{source_object.name} 顶点 {vertex_index} 的锁定 deform 权重之和超过 1"
                )
            object_sums[vertex_index] = total
        locked_sums[source_object.name] = object_sums

    grid = []
    offset = 0
    for count in row_counts:
        grid.append(
            [tuple(coordinates[vertex_map[offset + row]]) for row in range(count)]
        )
        offset += count
    total_affected = 0
    proxy_inverse = proxy_object.matrix_world.inverted()
    column_groups = list(
        proxy_object.get("surface_proxy_column_groups", [0] * len(grid))
    )
    if len(column_groups) != len(grid):
        column_groups = [0] * len(grid)
    grouped_columns = {
        group: [column for column, value in enumerate(column_groups) if value == group]
        for group in dict.fromkeys(column_groups)
    }
    bone_groups = {
        proxy_bone_name(proxy_object, prefix, column, row): column_groups[column]
        for column, count in enumerate(row_counts)
        for row in range(count - 1)
    }
    for source_object, affected in source_meshes:
        generated_groups = {
            (column, row): source_object.vertex_groups.get(
                proxy_bone_name(proxy_object, prefix, column, row)
            )
            or source_object.vertex_groups.new(
                name=proxy_bone_name(proxy_object, prefix, column, row)
            )
            for column, count in enumerate(row_counts)
            for row in range(count - 1)
        }
        unlocked_deform_groups = [
            group
            for group in source_object.vertex_groups
            if group.name in deform_names and not group.lock_weight
        ]
        source_to_proxy = proxy_inverse @ source_object.matrix_world
        for vertex_index in affected:
            existing_group_weights = {}
            for membership in source_object.data.vertices[vertex_index].groups:
                name = source_object.vertex_groups[membership.group].name
                group = bone_groups.get(name)
                if group is not None:
                    existing_group_weights[group] = (
                        existing_group_weights.get(group, 0.0) + membership.weight
                    )
            for group in unlocked_deform_groups:
                group.remove([vertex_index])
            available = max(
                0.0, 1.0 - locked_sums[source_object.name][vertex_index]
            )
            point = source_to_proxy @ source_object.data.vertices[vertex_index].co
            if existing_group_weights:
                selected_group = max(
                    existing_group_weights, key=existing_group_weights.get
                )
            else:
                selected_group = min(
                    grouped_columns,
                    key=lambda group: min(
                        (Vector(grid[column][row]) - point).length_squared
                        for column in grouped_columns[group]
                        for row in range(len(grid[column]))
                    ),
                )
            columns = grouped_columns[selected_group]
            side_grid = [grid[column] for column in columns]
            weights = bilinear_grid_weights(
                tuple(point),
                side_grid,
                closed=(
                    len(grouped_columns) == 1
                    and bool(proxy_object.get("surface_proxy_closed", True))
                ),
            )
            for (local_column, row), weight in weights.items():
                generated_groups[(columns[local_column], row)].add(
                    [vertex_index], available * weight, "REPLACE"
                )
        total_affected += len(affected)
    return len(source_meshes), total_affected


def ensure_connected_proxy_bones(context, armature_object, prefix, row_counts, parent_name):
    previous_active = context.view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    previous_selection = list(context.selected_objects)
    if previous_active is not None and previous_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in previous_selection:
        obj.select_set(False)
    armature_object.select_set(True)
    context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        anchor = armature_object.data.edit_bones.get(parent_name) if parent_name else None
        if parent_name and anchor is None:
            raise ProxyBuildError(f"连接骨骼不存在：{parent_name}")
        for column, count in enumerate(row_counts):
            parent = anchor
            for row in range(count - 1):
                name = bone_name(prefix, column, row)
                edit_bone = armature_object.data.edit_bones.get(name)
                if edit_bone is None:
                    raise ProxyBuildError(f"缺少代理骨骼：{name}")
                edit_bone.parent = parent
                edit_bone.use_connect = False
                edit_bone.inherit_scale = "NONE"
                parent = edit_bone
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        armature_object.select_set(False)
        for obj in previous_selection:
            obj.select_set(True)
        context.view_layer.objects.active = previous_active
        if previous_active is not None and previous_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=previous_mode)


def sync_proxy_bones(context, proxy_object, restore_mode=True):
    if "surface_proxy_schema" not in proxy_object:
        identify_proxy(proxy_object)
    armature_object = bpy.data.objects.get(str(proxy_object["surface_proxy_armature"]))
    prefix = str(proxy_object["surface_proxy_prefix"])
    row_counts = list(proxy_object["surface_proxy_column_rows"])
    vertex_map = list(proxy_object["surface_proxy_vertex_map"])
    coordinates, signature = _mesh_state(proxy_object)
    if signature != str(proxy_object["surface_proxy_topology"]):
        raise ProxyBuildError("代理拓扑已改变；只能移动或雕刻现有顶点")
    if len(vertex_map) != sum(row_counts) or max(vertex_map) >= len(coordinates):
        raise ProxyBuildError("代理顶点映射无效，请重新识别代理")

    original_mode = proxy_object.mode
    if original_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
        coordinates, _signature = _mesh_state(proxy_object)
    previous_active = context.view_layer.objects.active
    previous_selection = [obj for obj in context.selected_objects]
    for obj in previous_selection:
        obj.select_set(False)
    armature_object.select_set(True)
    context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode="EDIT")
    proxy_to_armature = armature_object.matrix_world.inverted() @ proxy_object.matrix_world
    offset = 0
    try:
        for column, count in enumerate(row_counts):
            for row in range(count - 1):
                edit_bone = armature_object.data.edit_bones.get(
                    proxy_bone_name(proxy_object, prefix, column, row)
                )
                if edit_bone is None:
                    raise ProxyBuildError(
                        f"缺少代理骨骼：{proxy_bone_name(proxy_object, prefix, column, row)}"
                    )
                edit_bone.head = proxy_to_armature @ coordinates[vertex_map[offset + row]]
                edit_bone.tail = proxy_to_armature @ coordinates[vertex_map[offset + row + 1]]
            offset += count
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        armature_object.select_set(False)
        for obj in previous_selection:
            obj.select_set(True)
        context.view_layer.objects.active = previous_active
        if restore_mode and previous_active == proxy_object and original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=original_mode)
    return sum(count - 1 for count in row_counts)


class SPX_OT_IdentifyProxy(Operator):
    bl_idname = "surface_proxy.identify_proxy"
    bl_label = "识别或恢复所选代理"
    bl_description = "根据对象名、骨骼名和拓扑恢复导入后丢失的代理元数据"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            proxy_object = context.active_object
            _armature, prefix, rows, _mapping = identify_proxy(proxy_object)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        context.scene.surface_proxy_creator.physics_proxy = proxy_object
        self.report({"INFO"}, f"已识别 {prefix}：{len(rows)} 列代理")
        return {"FINISHED"}


class SPX_OT_SyncProxyBones(Operator):
    bl_idname = "surface_proxy.sync_proxy_bones"
    bl_label = "同步骨骼到代理"
    bl_description = "保持名称、层级和权重不变，将骨骼端点同步到代理顶点"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proxy_object = context.active_object
        settings = context.scene.surface_proxy_creator
        try:
            count = sync_proxy_bones(context, proxy_object)
            rigid_count = joint_count = 0
            if settings.auto_sync_physics and settings.physics_proxy == proxy_object:
                from .mmd_physics import sync_proxy_physics_transforms

                rigid_count, joint_count = sync_proxy_physics_transforms(proxy_object)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        message = f"已同步 {count} 根骨骼"
        if rigid_count or joint_count:
            message += f"、{rigid_count} 个刚体、{joint_count} 个 Joint"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_RebindProxyWeights(Operator):
    bl_idname = "surface_proxy.rebind_proxy_weights"
    bl_label = "根据代理重算权重"
    bl_description = "无需选择顶点，只重算原本已有当前代理骨骼权重的顶点并保留 locked deform 权重"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proxy_object = context.active_object
        try:
            if proxy_object is None or proxy_object.type != "MESH":
                raise ProxyBuildError("请选择需要作为依据的代理 Mesh")
            if "surface_proxy_schema" not in proxy_object:
                identify_proxy(proxy_object)
            mesh_count, vertex_count = rebind_proxy_weights(proxy_object)
        except ProxyBuildError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"已重算 {mesh_count} 个网格、{vertex_count} 个顶点权重",
        )
        return {"FINISHED"}


CLASSES = (
    SPX_OT_IdentifyProxy,
    SPX_OT_SyncProxyBones,
    SPX_OT_RebindProxyWeights,
)


def _draw_proxy_bones():
    proxy_object = bpy.context.active_object
    if (
        proxy_object is None
        or proxy_object.type != "MESH"
        or "surface_proxy_schema" not in proxy_object
        or proxy_object.mode not in {"EDIT", "SCULPT"}
    ):
        return
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader

        coordinates, signature = _mesh_state(proxy_object)
        if signature != str(proxy_object["surface_proxy_topology"]):
            return
        row_counts = list(proxy_object["surface_proxy_column_rows"])
        vertex_map = list(proxy_object["surface_proxy_vertex_map"])
        lines = []
        offset = 0
        for count in row_counts:
            for row in range(count - 1):
                lines.extend(
                    (
                        proxy_object.matrix_world
                        @ coordinates[vertex_map[offset + row]],
                        proxy_object.matrix_world
                        @ coordinates[vertex_map[offset + row + 1]],
                    )
                )
            offset += count
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": lines})
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(2.0)
        shader.bind()
        shader.uniform_float("color", (0.1, 0.8, 1.0, 0.9))
        batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")
    except (KeyError, ReferenceError, RuntimeError):
        return


def _run_pending_sync():
    global _TIMER_PENDING
    for name in list(_DIRTY_PHYSICS_PROXIES):
        proxy_object = bpy.data.objects.get(name)
        if proxy_object is None:
            _DIRTY_PHYSICS_PROXIES.discard(name)
            continue
        try:
            armature_object = bpy.data.objects.get(
                str(proxy_object.get("surface_proxy_armature", ""))
            )
            if armature_object is None or armature_object.mode != "OBJECT" or (
                bpy.context.object is not None
                and bpy.context.object.mode != "OBJECT"
            ):
                continue
            from .mmd_physics import sync_proxy_physics_transforms

            sync_proxy_physics_transforms(proxy_object)
            if "surface_proxy_physics_sync_error" in proxy_object:
                del proxy_object["surface_proxy_physics_sync_error"]
        except ProxyBuildError as error:
            proxy_object["surface_proxy_physics_sync_error"] = str(error)
        _DIRTY_PHYSICS_PROXIES.discard(name)
    if _DIRTY_PHYSICS_PROXIES:
        return 0.25
    _TIMER_PENDING = False
    return None


def _schedule_pending_sync():
    global _TIMER_PENDING
    if not bpy.app.timers.is_registered(_run_pending_sync):
        bpy.app.timers.register(_run_pending_sync, first_interval=0.1)
    _TIMER_PENDING = True


def _sync_on_proxy_mode_exit():
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "surface_proxy_creator", None)
    live_names = set()
    for obj in bpy.data.objects:
        if obj.type != "MESH" or "surface_proxy_schema" not in obj:
            continue
        live_names.add(obj.name)
        current_mode = obj.mode
        previous_mode = _PROXY_MODES.get(obj.name, current_mode)
        _PROXY_MODES[obj.name] = current_mode
        if (
            settings is None
            or not settings.auto_sync
            or previous_mode not in {"EDIT", "SCULPT"}
            or current_mode != "OBJECT"
        ):
            continue
        try:
            sync_proxy_bones(bpy.context, obj, restore_mode=False)
            if settings.auto_sync_physics and settings.physics_proxy == obj:
                from .mmd_physics import sync_proxy_physics_transforms

                sync_proxy_physics_transforms(obj)
            if "surface_proxy_sync_error" in obj:
                del obj["surface_proxy_sync_error"]
        except (ProxyBuildError, RuntimeError) as error:
            obj["surface_proxy_sync_error"] = str(error)
    for name in set(_PROXY_MODES) - live_names:
        del _PROXY_MODES[name]
    return 0.1


@persistent
def _depsgraph_proxy_update(_scene, depsgraph):
    global _TIMER_PENDING
    settings = getattr(bpy.context.scene, "surface_proxy_creator", None)
    if settings is not None and getattr(settings, "preview_running", False):
        return
    updated_ids = {update.id for update in depsgraph.updates}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if "surface_proxy_schema" not in obj and _prefix_from_name(obj.name):
            try:
                identify_proxy(obj)
            except ProxyBuildError:
                pass
    if settings is not None and settings.auto_sync_physics:
        proxy_object = settings.physics_proxy
        if proxy_object is not None:
            armature_object = bpy.data.objects.get(
                str(proxy_object.get("surface_proxy_armature", ""))
            )
            if (
                armature_object is not None
                and armature_object.mode == "EDIT"
                and (
                    armature_object in updated_ids
                    or armature_object.data in updated_ids
                )
            ):
                _DIRTY_PHYSICS_PROXIES.add(proxy_object.name)
    if _DIRTY_PHYSICS_PROXIES:
        _schedule_pending_sync()


@persistent
def _load_proxy_identity(_unused):
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if "surface_proxy_schema" not in obj and _prefix_from_name(obj.name):
            try:
                identify_proxy(obj)
            except ProxyBuildError:
                pass
        if "surface_proxy_schema" in obj:
            _PROXY_MODES[obj.name] = obj.mode


def _initialize_proxy_services():
    try:
        _load_proxy_identity(None)
    except AttributeError as error:
        if "_RestrictData" not in str(error):
            raise
        return 0.1
    return None


def register_services():
    global _DRAW_HANDLE
    if _depsgraph_proxy_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_proxy_update)
    if _load_proxy_identity not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_proxy_identity)
    if not bpy.app.timers.is_registered(_initialize_proxy_services):
        bpy.app.timers.register(_initialize_proxy_services, first_interval=0.1)
    if not bpy.app.timers.is_registered(_sync_on_proxy_mode_exit):
        bpy.app.timers.register(
            _sync_on_proxy_mode_exit,
            first_interval=0.1,
            persistent=True,
        )
    if not bpy.app.background and _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_proxy_bones, (), "WINDOW", "POST_VIEW"
        )


def unregister_services():
    global _DRAW_HANDLE, _TIMER_PENDING
    if _depsgraph_proxy_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_proxy_update)
    if _load_proxy_identity in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_proxy_identity)
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
    if bpy.app.timers.is_registered(_run_pending_sync):
        bpy.app.timers.unregister(_run_pending_sync)
    if bpy.app.timers.is_registered(_initialize_proxy_services):
        bpy.app.timers.unregister(_initialize_proxy_services)
    if bpy.app.timers.is_registered(_sync_on_proxy_mode_exit):
        bpy.app.timers.unregister(_sync_on_proxy_mode_exit)
    _DIRTY_PHYSICS_PROXIES.clear()
    _PROXY_MODES.clear()
    _TIMER_PENDING = False
