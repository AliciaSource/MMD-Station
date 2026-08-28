import pathlib
import sys

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import mmd_station
from mmd_station.vertex_group_tools import (
    draw_vertex_group_context_menu,
)


def existing_menu_extension(_self, _context):
    pass


bpy.types.MESH_MT_vertex_group_context_menu.append(existing_menu_extension)
mmd_station.register()

draw_functions = getattr(
    bpy.types.MESH_MT_vertex_group_context_menu.draw,
    "_draw_funcs",
    (),
)
assert draw_functions[1] is draw_vertex_group_context_menu
assert draw_functions[2] is existing_menu_extension

mesh_data = bpy.data.meshes.new("LockedWeightMergeData")
mesh_data.from_pydata(
    [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
    [],
    [],
)
mesh = bpy.data.objects.new("LockedWeightMerge", mesh_data)
bpy.context.collection.objects.link(mesh)
bpy.context.view_layer.objects.active = mesh
mesh.select_set(True)

locked_a = mesh.vertex_groups.new(name="LockedA")
locked_a.add([0, 1], 0.25, "REPLACE")
locked_a.lock_weight = True
locked_b = mesh.vertex_groups.new(name="LockedB")
locked_b.add([0], 0.5, "REPLACE")
locked_b.add([2], 0.8, "REPLACE")
locked_b.lock_weight = True
unlocked = mesh.vertex_groups.new(name="Unlocked")
unlocked.add([0, 1, 2], 0.4, "REPLACE")

source_weights = {
    group.name: {
        vertex.index: group.weight(vertex.index)
        for vertex in mesh_data.vertices
        if any(item.group == group.index for item in vertex.groups)
    }
    for group in (locked_a, locked_b, unlocked)
}

bpy.ops.object.mode_set(mode="EDIT")
result = bpy.ops.surface_proxy.create_group_from_locked_weights()
assert result == {"FINISHED"}, result
assert mesh.mode == "EDIT"

created = mesh.vertex_groups.get("锁定组权重")
assert created is not None
expected = {0: 0.75, 1: 0.25, 2: 0.8}
for vertex_index, weight in expected.items():
    assert abs(created.weight(vertex_index) - weight) < 1.0e-6

for group in (locked_a, locked_b, unlocked):
    actual = {
        vertex.index: group.weight(vertex.index)
        for vertex in mesh_data.vertices
        if any(item.group == group.index for item in vertex.groups)
    }
    assert actual == source_weights[group.name]

bpy.ops.object.mode_set(mode="OBJECT")
overflow = mesh.vertex_groups.new(name="Overflow")
overflow.add([0], 0.5, "REPLACE")
overflow.lock_weight = True
result = bpy.ops.surface_proxy.create_group_from_locked_weights()
assert result == {"FINISHED"}, result
created_overflow = mesh.vertex_groups.get("锁定组权重.001")
assert created_overflow is not None
assert abs(created_overflow.weight(0) - 1.0) < 1.0e-6

print("LOCKED_VERTEX_GROUP_WEIGHT_MERGE_OK")
