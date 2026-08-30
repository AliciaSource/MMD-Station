from .i18n import report
import re

import bpy
from bpy.props import IntProperty
from bpy.types import Operator
from mathutils import Vector

from .mmd_naming import normalized_mmd_names
from .mmd_ordering import (
    OrderingError,
    _apply_bone_order,
    _bone_order,
    _mmd_api,
    _resolve_root,
)


_SIDE_SUFFIX = re.compile(r"^(?P<stem>.*?)(?P<side>[._][LR])$")
_NUMBERED_STEM = re.compile(r"^(?P<subject>.*?)(?P<number>\d+)$")
_EPSILON = 1.0e-7


def _unique_segment_name(existing_names, source_name, segment_index):
    match = _SIDE_SUFFIX.match(source_name)
    stem = match.group("stem") if match else source_name
    side = match.group("side") if match else ""
    base = f"{stem}_S{segment_index:02d}"
    candidate = f"{base}{side}"
    duplicate = 2
    while candidate in existing_names:
        candidate = f"{base}_{duplicate}{side}"
        duplicate += 1
    existing_names.add(candidate)
    return candidate


def _parameter_step(first, second):
    return max((second - first).length, _EPSILON) ** 0.5


def _centripetal_point(p0, p1, p2, p3, factor):
    t0 = 0.0
    t1 = t0 + _parameter_step(p0, p1)
    t2 = t1 + _parameter_step(p1, p2)
    t3 = t2 + _parameter_step(p2, p3)
    value = t1 + (t2 - t1) * factor

    a1 = ((t1 - value) / (t1 - t0)) * p0 + ((value - t0) / (t1 - t0)) * p1
    a2 = ((t2 - value) / (t2 - t1)) * p1 + ((value - t1) / (t2 - t1)) * p2
    a3 = ((t3 - value) / (t3 - t2)) * p2 + ((value - t2) / (t3 - t2)) * p3
    b1 = ((t2 - value) / (t2 - t0)) * a1 + ((value - t0) / (t2 - t0)) * a2
    b2 = ((t3 - value) / (t3 - t1)) * a2 + ((value - t1) / (t3 - t1)) * a3
    return ((t2 - value) / (t2 - t1)) * b1 + ((value - t1) / (t2 - t1)) * b2


def _arc_length_points(p0, p1, p2, p3, segment_count):
    sample_count = max(segment_count * 24, 48)
    samples = [
        _centripetal_point(p0, p1, p2, p3, index / sample_count)
        for index in range(sample_count + 1)
    ]
    samples[0] = p1.copy()
    samples[-1] = p2.copy()
    cumulative = [0.0]
    for previous, current in zip(samples, samples[1:]):
        cumulative.append(cumulative[-1] + (current - previous).length)
    total_length = cumulative[-1]
    if total_length <= _EPSILON:
        raise OrderingError("不能细分零长度骨骼")

    result = [p1.copy()]
    sample_index = 1
    for segment_index in range(1, segment_count):
        target = total_length * segment_index / segment_count
        while cumulative[sample_index] < target:
            sample_index += 1
        start_length = cumulative[sample_index - 1]
        end_length = cumulative[sample_index]
        factor = (
            (target - start_length) / (end_length - start_length)
            if end_length > start_length
            else 0.0
        )
        result.append(samples[sample_index - 1].lerp(samples[sample_index], factor))
    result.append(p2.copy())
    return result


def _continuation_child(bone, selected_names):
    direction = bone.tail_local - bone.head_local
    if direction.length <= _EPSILON:
        return None
    direction.normalize()
    candidates = []
    for child in bone.children:
        if (child.head_local - bone.tail_local).length > 1.0e-5:
            continue
        child_direction = child.tail_local - child.head_local
        if child_direction.length <= _EPSILON:
            continue
        child_direction.normalize()
        candidates.append(
            (child.name in selected_names, direction.dot(child_direction), child.name, child)
        )
    return max(candidates, default=(False, -2.0, "", None))[-1]


def _curve_points(bone, selected_names, segment_count):
    p1 = bone.head_local.copy()
    p2 = bone.tail_local.copy()
    direction = p2 - p1
    if direction.length <= _EPSILON:
        raise OrderingError(f"不能细分零长度骨骼：{bone.name}")

    parent = bone.parent
    has_parent_curve = (
        parent is not None
        and (parent.tail_local - p1).length <= 1.0e-5
        and (parent.tail_local - parent.head_local).length > _EPSILON
    )
    p0 = parent.head_local.copy() if has_parent_curve else p1 - direction

    child = _continuation_child(bone, selected_names)
    has_child_curve = child is not None
    p3 = child.tail_local.copy() if has_child_curve else p2 + direction
    if not has_parent_curve and not has_child_curve:
        return [p1.lerp(p2, index / segment_count) for index in range(segment_count + 1)], False
    return _arc_length_points(p0, p1, p2, p3, segment_count), True


def _bone_depth(bone):
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _numbered_name_parts(name):
    side_match = _SIDE_SUFFIX.match(name)
    stem = side_match.group("stem") if side_match else name
    side = side_match.group("side") if side_match else ""
    number_match = _NUMBERED_STEM.match(stem)
    if number_match is None or not number_match.group("subject"):
        raise OrderingError(f"骨骼名末尾缺少可连续重排的编号：{name}")
    number_text = number_match.group("number")
    return (
        number_match.group("subject"),
        int(number_text),
        len(number_text),
        side,
    )


def _selected_chains(armature, selected_names, order_index):
    selected_bones = {
        name: armature.data.bones[name]
        for name in selected_names
        if name in armature.data.bones
    }
    roots = [
        bone
        for bone in selected_bones.values()
        if bone.parent is None or bone.parent.name not in selected_names
    ]
    roots.sort(key=lambda bone: order_index[bone.name])
    chains = []
    visited = set()
    for root in roots:
        chain = []
        current = root
        while current is not None and current.name not in visited:
            visited.add(current.name)
            chain.append(current)
            children = [
                child for child in current.children if child.name in selected_names
            ]
            if len(children) > 1:
                raise OrderingError(f"勾选骨链存在分叉，请按分支分别细分：{current.name}")
            current = children[0] if children else None
        chains.append(chain)
    if visited != selected_names:
        missing = min(selected_names - visited, key=order_index.get)
        raise OrderingError(f"无法解析勾选骨链层级：{missing}")
    return chains


def _continuous_name_map(armature, selected_names, created_names, original_order):
    order_index = {bone.name: index for index, bone in enumerate(original_order)}
    plans = []
    for chain in _selected_chains(armature, selected_names, order_index):
        root_subject, root_number, root_width, root_side = _numbered_name_parts(
            chain[0].name
        )
        entries = []
        for bone in chain:
            subject, _number, width, side = _numbered_name_parts(bone.name)
            if subject != root_subject or side != root_side:
                raise OrderingError(
                    f"同一勾选骨链必须使用相同主体名称和左右后缀：{chain[0].name}"
                )
            root_width = max(root_width, width)
            entries.append(bone.name)
            entries.extend(created_names[bone.name])
        plans.append(
            {
                "subject": root_subject,
                "start": root_number,
                "width": root_width,
                "side": root_side,
                "entries": entries,
                "order": order_index[chain[0].name],
            }
        )

    grouped = {}
    for plan in plans:
        key = (
            plan["subject"],
            plan["start"],
            plan["width"],
            len(plan["entries"]),
        )
        grouped.setdefault(key, []).append(plan)

    occupied = set(armature.data.bones.keys()) - selected_names
    reserved = set()
    rename_map = {}
    for key, group in sorted(
        grouped.items(),
        key=lambda item: min(plan["order"] for plan in item[1]),
    ):
        subject, requested_start, width, entry_count = key
        start = requested_start
        while True:
            targets = [
                f"{subject}{number:0{width}d}{plan['side']}"
                for plan in group
                for number in range(start, start + entry_count)
            ]
            if not (set(targets) & occupied) and not (set(targets) & reserved):
                break
            start += 1
        for plan in group:
            targets = [
                f"{subject}{number:0{width}d}{plan['side']}"
                for number in range(start, start + entry_count)
            ]
            rename_map.update(zip(plan["entries"], targets))
            reserved.update(targets)
    return rename_map


def _rename_bones_and_vertex_groups(FnModel, root, armature, rename_map):
    active_map = {old: new for old, new in rename_map.items() if old != new}
    expected_groups = []
    for mesh_object in FnModel.iterate_child_objects(root):
        if mesh_object.type != "MESH" or mesh_object.mmd_type == "RIGID_BODY":
            continue
        existing_groups = {group.name for group in mesh_object.vertex_groups}
        source_groups = {old for old in active_map if old in existing_groups}
        collisions = {
            active_map[old]
            for old in source_groups
            if active_map[old] in existing_groups
            and active_map[old] not in source_groups
        }
        if collisions:
            raise OrderingError(
                f"Mesh {mesh_object.name} 已有目标编号顶点组：{sorted(collisions)[0]}"
            )
        expected_groups.append(
            (mesh_object, {active_map[name] for name in source_groups})
        )

    bone_temporary_names = {}
    existing_bone_names = set(armature.data.bones.keys())
    for index, old_name in enumerate(active_map):
        temporary_name = f"__SPX_SUBDIV_RENAME_{index:04d}__"
        while temporary_name in existing_bone_names:
            temporary_name += "_"
        existing_bone_names.add(temporary_name)
        armature.data.bones[old_name].name = temporary_name
        bone_temporary_names[temporary_name] = active_map[old_name]
    for temporary_name, final_name in bone_temporary_names.items():
        armature.data.bones[temporary_name].name = final_name

    for mesh_object, final_names in expected_groups:
        missing = [
            name for name in final_names if mesh_object.vertex_groups.get(name) is None
        ]
        if missing:
            raise OrderingError(
                f"Mesh {mesh_object.name} 顶点组未随骨骼同步重命名：{sorted(missing)[0]}"
            )

    for final_name in rename_map.values():
        pose_bone = armature.pose.bones[final_name]
        name_j, name_e = normalized_mmd_names("", "", final_name)
        pose_bone.mmd_bone.name_j = name_j
        pose_bone.mmd_bone.name_e = name_e


def _copy_mmd_metadata(source_pose_bone, target_pose_bone, segment_index):
    source = source_pose_bone.mmd_bone
    target = target_pose_bone.mmd_bone
    source_name_j = source.name_j.strip() or source_pose_bone.name
    source_name_e = source.name_e.strip() or source_pose_bone.name
    target.name_j = f"{source_name_j}_S{segment_index:02d}"
    target.name_e = f"{source_name_e}_S{segment_index:02d}"
    for name in (
        "transform_order",
        "transform_after_dynamics",
        "is_controllable",
        "enabled_fixed_axis",
        "fixed_axis",
        "enabled_local_axes",
        "local_axis_x",
        "local_axis_z",
    ):
        if hasattr(source, name) and hasattr(target, name):
            setattr(target, name, getattr(source, name))


def _split_weights(FnModel, root, created_names, segment_count):
    mesh_count = 0
    vertex_count = 0
    for mesh_object in FnModel.iterate_child_objects(root):
        if mesh_object.type != "MESH" or mesh_object.mmd_type == "RIGID_BODY":
            continue
        mesh_changed = False
        for source_name, new_names in created_names.items():
            source_group = mesh_object.vertex_groups.get(source_name)
            if source_group is None:
                continue
            target_groups = [
                mesh_object.vertex_groups.get(name)
                or mesh_object.vertex_groups.new(name=name)
                for name in new_names
            ]
            source_index = source_group.index
            weights = []
            for vertex in mesh_object.data.vertices:
                weight = next(
                    (
                        membership.weight
                        for membership in vertex.groups
                        if membership.group == source_index
                    ),
                    0.0,
                )
                if weight > 0.0:
                    weights.append((vertex.index, weight / segment_count))
            for vertex_index, divided_weight in weights:
                source_group.add([vertex_index], divided_weight, "REPLACE")
                for target_group in target_groups:
                    target_group.add([vertex_index], divided_weight, "REPLACE")
            if weights:
                mesh_changed = True
                vertex_count += len(weights)
        if mesh_changed:
            mesh_count += 1
    return mesh_count, vertex_count


def subdivide_checked_bones(context, settings, segment_count):
    if segment_count < 2:
        raise OrderingError("细分段数必须至少为 2")
    FnModel, _MoveObject = _mmd_api()
    root = _resolve_root(settings, FnModel)
    armature, original_order = _bone_order(FnModel, root)
    selected_names = {
        item.target_name
        for item in settings.browser_items
        if item.kind == "BONE" and item.selected
    }
    if not selected_names:
        raise OrderingError("请先勾选要细分的骨骼")
    selected_names.intersection_update(bone.name for bone in original_order)
    if not selected_names:
        raise OrderingError("勾选骨骼已失效，请刷新列表后重试")

    existing_names = set(armature.data.bones.keys())
    created_names = {}
    specifications = []
    curved_count = 0
    for bone in original_order:
        if bone.name not in selected_names:
            continue
        data_bone = armature.data.bones[bone.name]
        points, curved = _curve_points(data_bone, selected_names, segment_count)
        curved_count += int(curved)
        new_names = [
            _unique_segment_name(existing_names, bone.name, index)
            for index in range(2, segment_count + 1)
        ]
        created_names[bone.name] = new_names
        specifications.append(
            {
                "name": bone.name,
                "depth": _bone_depth(data_bone),
                "points": points,
                "new_names": new_names,
                "children": [
                    (child.name, child.use_connect) for child in data_bone.children
                ],
                "collections": [collection.name for collection in data_bone.collections],
            }
        )
    rename_map = _continuous_name_map(
        armature,
        selected_names,
        created_names,
        original_order,
    )

    previous_active = context.view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    previous_selected = [obj for obj in context.selected_objects]
    if previous_active is not None and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for specification in sorted(specifications, key=lambda item: item["depth"]):
            edit_bones = armature.data.edit_bones
            source = edit_bones.get(specification["name"])
            if source is None:
                raise OrderingError(f"骨骼已不存在：{specification['name']}")
            source_roll_axis = source.z_axis.copy()
            source_roll = source.roll
            source_use_deform = source.use_deform
            source_inherit_scale = source.inherit_scale
            source_envelope_distance = source.envelope_distance
            source_envelope_weight = source.envelope_weight
            source_head_radius = source.head_radius
            source_tail_radius = source.tail_radius
            for child_name, _use_connect in specification["children"]:
                child = edit_bones.get(child_name)
                if child is not None and child.parent == source:
                    child.use_connect = False
                    child.parent = None

            points = specification["points"]
            source.tail = points[1]
            source.roll = source_roll
            source.align_roll(source_roll_axis)
            previous = source
            for index, name in enumerate(specification["new_names"], start=1):
                new_bone = edit_bones.new(name)
                new_bone.head = points[index]
                new_bone.tail = points[index + 1]
                new_bone.parent = previous
                new_bone.use_connect = False
                new_bone.use_deform = source_use_deform
                new_bone.inherit_scale = source_inherit_scale
                new_bone.envelope_distance = source_envelope_distance
                new_bone.envelope_weight = source_envelope_weight
                new_bone.head_radius = source_head_radius
                new_bone.tail_radius = source_tail_radius
                new_bone.roll = source_roll
                new_bone.align_roll(source_roll_axis)
                for collection_name in specification["collections"]:
                    collection = armature.data.collections.get(collection_name)
                    if collection is not None:
                        collection.assign(new_bone)
                previous = new_bone

            for child_name, use_connect in specification["children"]:
                child = edit_bones.get(child_name)
                if child is not None:
                    child.parent = previous
                    child.use_connect = use_connect
    finally:
        if armature.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

    for source_name, new_names in created_names.items():
        source_pose_bone = armature.pose.bones[source_name]
        for segment_index, new_name in enumerate(new_names, start=2):
            _copy_mmd_metadata(
                source_pose_bone,
                armature.pose.bones[new_name],
                segment_index,
            )

    desired = []
    for bone in original_order:
        desired.append(bone)
        desired.extend(
            armature.pose.bones[name] for name in created_names.get(bone.name, ())
        )
    mesh_count, vertex_count = _split_weights(
        FnModel,
        root,
        created_names,
        segment_count,
    )
    _rename_bones_and_vertex_groups(
        FnModel,
        root,
        armature,
        rename_map,
    )
    _apply_bone_order(FnModel, root, desired)

    final_created_names = {
        rename_map[source_name]: [rename_map[name] for name in new_names]
        for source_name, new_names in created_names.items()
    }

    bpy.ops.surface_proxy.refresh_mmd_browser()
    result_names = set(final_created_names)
    for names in final_created_names.values():
        result_names.update(names)
    for index, item in enumerate(settings.browser_items):
        item.selected = item.kind == "BONE" and item.target_name in result_names
        if item.selected:
            settings.browser_index = index

    bpy.ops.object.select_all(action="DESELECT")
    for obj in previous_selected:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if previous_active is not None and previous_active.name in bpy.data.objects:
        context.view_layer.objects.active = previous_active
        if previous_mode == "POSE" and previous_active.type == "ARMATURE":
            bpy.ops.object.mode_set(mode="POSE")
        elif previous_mode == "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")

    return {
        "source_count": len(created_names),
        "created_count": sum(len(names) for names in created_names.values()),
        "curved_count": curved_count,
        "mesh_count": mesh_count,
        "vertex_count": vertex_count,
        "created_names": final_created_names,
    }


class SPX_OT_SubdivideCheckedMMDBones(Operator):
    bl_idname = "surface_proxy.subdivide_checked_mmd_bones"
    bl_label = "细分勾选骨骼"
    bl_description = "沿骨链曲率细分勾选骨骼，连续重编号、重排 PMX 顺序并等分原顶点组权重"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        try:
            result = subdivide_checked_bones(
                context,
                settings,
                settings.bone_subdivide_segments,
            )
        except OrderingError as error:
            report(self, {"ERROR"}, str(error))
            return {"CANCELLED"}
        report(self,
            {"INFO"},
            f"已将 {result['source_count']} 根骨骼细分为 {settings.bone_subdivide_segments} 段，新增 {result['created_count']} 根；{result['mesh_count']} 个 Mesh 的 {result['vertex_count']} 个顶点权重已等分",
        )
        return {"FINISHED"}


def register_settings(cls):
    cls.__annotations__["bone_subdivide_segments"] = IntProperty(
        name="细分段数",
        description="每根勾选骨骼最终包含的曲线分段数量",
        default=2,
        min=2,
        max=32,
    )


def draw(layout, settings):
    if settings.browser_kind != "BONE":
        return
    box = layout.box()
    box.label(text="骨骼细分", icon="BONE_DATA")
    row = box.row(align=True)
    row.prop(settings, "bone_subdivide_segments")
    row.operator(SPX_OT_SubdivideCheckedMMDBones.bl_idname, icon="MOD_SUBSURF")
    box.label(text="按骨链曲率重采样；孤立骨骼退回直线均分", icon="INFO")
    box.label(text="骨链连续重编号；新骨有父子层级但不连接", icon="INFO")
    box.label(text="原顶点组权重按段数等分", icon="INFO")


CLASSES = (SPX_OT_SubdivideCheckedMMDBones,)
