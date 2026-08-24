import pathlib
import sys
from types import SimpleNamespace

import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.vertex_group_tools import (
    SPX_OT_ConvertActiveGroupToMirrored,
    draw_builtin_vertex_group_context_menu,
)


mmd_skirt_proxy_creator.register()
draw_functions = getattr(
    bpy.types.MESH_MT_vertex_group_context_menu.draw,
    "_draw_funcs",
    (),
)
assert draw_builtin_vertex_group_context_menu in draw_functions


class LayoutProbe:
    def __init__(self):
        self.events = []

    def operator(self, operator_id, **_kwargs):
        self.events.append(("OPERATOR", operator_id))
        return SimpleNamespace()

    def separator(self):
        self.events.append(("SEPARATOR", ""))


layout_probe = LayoutProbe()
draw_builtin_vertex_group_context_menu(
    SimpleNamespace(layout=layout_probe),
    bpy.context,
)
operator_ids = [value for event, value in layout_probe.events if event == "OPERATOR"]
mirror_indices = [
    index
    for index, operator_id in enumerate(operator_ids)
    if operator_id == "object.vertex_group_mirror"
]
conversion_index = operator_ids.index(
    SPX_OT_ConvertActiveGroupToMirrored.bl_idname
)
assert conversion_index == mirror_indices[-1] + 1

mesh_data = bpy.data.meshes.new("MirrorConversionData")
mesh_data.from_pydata(
    [
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (1.0e-8, 0.0, 0.0),
        (0.5, 0.0, 0.0),
    ],
    [],
    [],
)
mesh = bpy.data.objects.new("MirrorConversion", mesh_data)
bpy.context.collection.objects.link(mesh)
bpy.context.view_layer.objects.active = mesh
mesh.select_set(True)

before = mesh.vertex_groups.new(name="Before")
source = mesh.vertex_groups.new(name="Bone_Piao210")
after_a = mesh.vertex_groups.new(name="AfterA")
after_b = mesh.vertex_groups.new(name="AfterB")
before.add([0, 1, 2, 3, 4], 0.1, "REPLACE")
after_a.add([4], 0.3, "REPLACE")
after_b.add([1], 0.7, "REPLACE")
source.add([0], 0.8, "REPLACE")
source.add([1], 0.6, "REPLACE")
source.add([2], 0.4, "REPLACE")
source.add([3], 0.2, "REPLACE")
source.lock_weight = True
mesh.vertex_groups.active_index = source.index

bpy.ops.object.mode_set(mode="EDIT")
result = bpy.ops.surface_proxy.convert_active_group_to_mirrored()
assert result == {"FINISHED"}, result
assert mesh.mode == "EDIT"
assert [group.name for group in mesh.vertex_groups] == [
    "Before",
    "Bone_Piao210.L",
    "Bone_Piao210.R",
    "AfterA",
    "AfterB",
]
assert mesh.vertex_groups.active.name == "Bone_Piao210.L"
left = mesh.vertex_groups["Bone_Piao210.L"]
right = mesh.vertex_groups["Bone_Piao210.R"]
assert left.lock_weight and right.lock_weight
assert abs(left.weight(0) - 0.8) < 1.0e-6
assert abs(right.weight(1) - 0.6) < 1.0e-6
assert abs(left.weight(2) - 0.2) < 1.0e-6
assert abs(right.weight(2) - 0.2) < 1.0e-6
assert abs(left.weight(3) - 0.1) < 1.0e-6
assert abs(right.weight(3) - 0.1) < 1.0e-6
assert all(group.name != "Bone_Piao210" for group in mesh.vertex_groups)
assert abs(before.weight(4) - 0.1) < 1.0e-6
assert abs(after_a.weight(4) - 0.3) < 1.0e-6
assert abs(after_b.weight(1) - 0.7) < 1.0e-6

bpy.ops.object.mode_set(mode="OBJECT")
collision_source = mesh.vertex_groups.new(name="Collision")
mesh.vertex_groups.new(name="Collision.L")
mesh.vertex_groups.active_index = collision_source.index
names_before_collision = [group.name for group in mesh.vertex_groups]
assert bpy.ops.surface_proxy.convert_active_group_to_mirrored() == {"CANCELLED"}
assert [group.name for group in mesh.vertex_groups] == names_before_collision

print("MIRROR_VERTEX_GROUP_CONVERSION_OK")
