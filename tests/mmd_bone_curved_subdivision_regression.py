import bpy
from mmd_station import mmd_ordering

selected_names = [
    "Bone_Piao160.L",
    "Bone_Piao160.R",
    "Bone_Piao161.L",
    "Bone_Piao161.R",
    "Bone_Piao162.L",
    "Bone_Piao162.R",
]
segment_count = 3
final_segments = {}
for side in (".L", ".R"):
    for source_offset, source_number in enumerate((160, 161, 162)):
        start = 160 + source_offset * segment_count
        final_segments[f"Bone_Piao{source_number}{side}"] = [
            f"Bone_Piao{number}{side}"
            for number in range(start, start + segment_count)
        ]
settings = bpy.context.scene.surface_proxy_creator
if settings.mmd_root is None:
    settings.mmd_root = bpy.data.objects.get("合并2")
settings.browser_kind = "BONE"
settings.bone_subdivide_segments = segment_count
FnModel, _MoveObject = mmd_ordering._mmd_api()
root = mmd_ordering._resolve_root(settings, FnModel)
armature, before_order = mmd_ordering._bone_order(FnModel, root)
before_count = len(before_order)
before_geometry = {
    name: (
        armature.data.bones[name].head_local.copy(),
        armature.data.bones[name].tail_local.copy(),
        [(child.name, child.use_connect) for child in armature.data.bones[name].children],
    )
    for name in selected_names
}
weight_snapshot = {}
for mesh in FnModel.iterate_child_objects(root):
    if mesh.type != "MESH" or mesh.mmd_type == "RIGID_BODY":
        continue
    for name in selected_names:
        group = mesh.vertex_groups.get(name)
        if group is None:
            continue
        values = {}
        for vertex in mesh.data.vertices:
            weight = next(
                (membership.weight for membership in vertex.groups if membership.group == group.index),
                0.0,
            )
            if weight > 0.0:
                values[vertex.index] = weight
        if values:
            weight_snapshot[(mesh.name, name)] = values

print("ACTUAL_SUBDIVIDE_BEFORE", before_count, "weighted_groups", len(weight_snapshot))
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
found = set()
for item in settings.browser_items:
    item.selected = item.kind == "BONE" and item.target_name in selected_names
    if item.selected:
        found.add(item.target_name)
assert found == set(selected_names), (found, selected_names)
result = bpy.ops.surface_proxy.subdivide_checked_mmd_bones()
print("ACTUAL_SUBDIVIDE_OPERATOR", result)
assert result == {"FINISHED"}

armature, after_order = mmd_ordering._bone_order(FnModel, root)
assert len(after_order) == before_count + len(selected_names) * (segment_count - 1)
after_names = [bone.name for bone in after_order]
max_curve_deviation = 0.0
for source_name in selected_names:
    segment_names = final_segments[source_name]
    final_source_name = segment_names[0]
    source_index = after_names.index(final_source_name)
    assert after_names[source_index : source_index + segment_count] == segment_names
    assert [armature.pose.bones[name].mmd_bone.bone_id for name in segment_names] == list(
        range(source_index, source_index + segment_count)
    )
    points = [armature.data.bones[final_source_name].head_local.copy()]
    points.extend(armature.data.bones[name].tail_local.copy() for name in segment_names)
    old_head, old_tail, old_children = before_geometry[source_name]
    assert (points[0] - old_head).length < 1.0e-7
    assert (points[-1] - old_tail).length < 1.0e-7
    for index in range(1, segment_count):
        linear = old_head.lerp(old_tail, index / segment_count)
        max_curve_deviation = max(max_curve_deviation, (points[index] - linear).length)
    for first, second in zip(segment_names, segment_names[1:]):
        assert armature.data.bones[second].parent.name == first
        assert not armature.data.bones[second].use_connect
    for child_name, use_connect in old_children:
        final_child_name = final_segments.get(child_name, [child_name])[0]
        child = armature.data.bones[final_child_name]
        assert child.parent.name == segment_names[-1], (source_name, final_child_name, child.parent.name)
        assert child.use_connect == use_connect

assert max_curve_deviation > 1.0e-6, max_curve_deviation
assert weight_snapshot, "The selected real bones must exercise weight redistribution"
max_weight_error = 0.0
for (mesh_name, source_name), values in weight_snapshot.items():
    mesh = bpy.data.objects[mesh_name]
    group_names = final_segments[source_name]
    groups = [mesh.vertex_groups[name] for name in group_names]
    for vertex_index, original_weight in values.items():
        weights = []
        vertex = mesh.data.vertices[vertex_index]
        memberships = {membership.group: membership.weight for membership in vertex.groups}
        for group in groups:
            weights.append(memberships.get(group.index, 0.0))
        max_weight_error = max(
            max_weight_error,
            abs(sum(weights) - original_weight),
            max(abs(weight - original_weight / segment_count) for weight in weights),
        )
assert max_weight_error < 1.0e-6, max_weight_error
expected_proxy_bones = {
    name for names in final_segments.values() for name in names
}
assert {
    item.target_name
    for item in settings.browser_items
    if item.kind == "BONE" and item.selected
} == expected_proxy_bones
settings.topology = "OPEN"
settings.restore_connect_sides = False
existing_objects = set(bpy.data.objects)
proxy_result = bpy.ops.surface_proxy.restore_proxy_from_checked_bones()
print("ACTUAL_SUBDIVIDE_PROXY", proxy_result)
assert proxy_result == {"FINISHED"}
created_objects = set(bpy.data.objects) - existing_objects
proxy_objects = [
    obj
    for obj in created_objects
    if obj.type == "MESH"
    and set(obj.get("surface_proxy_bone_names", ())) == expected_proxy_bones
]
assert len(proxy_objects) == 1, [obj.name for obj in created_objects]
print(
    "ACTUAL_05_BLEND_CURVED_SUBDIVISION_PROXY_OK",
    "created",
    len(selected_names) * (segment_count - 1),
    "curve_deviation",
    max_curve_deviation,
    "weight_error",
    max_weight_error,
)
