import bpy
import re
from bpy.types import Operator


NEW_GROUP_NAME = "锁定组权重"
_ORIGINAL_VERTEX_GROUP_MENU_DRAW = None


class SPX_OT_CreateGroupFromLockedWeights(Operator):
    bl_idname = "surface_proxy.create_group_from_locked_weights"
    bl_label = "用锁定组的权重创建新组"
    bl_description = "将当前物体所有锁定顶点组的权重逐顶点相加到新组，保留原组权重"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        locked_group_indices = {
            group.index for group in obj.vertex_groups if group.lock_weight
        }
        if not locked_group_indices:
            self.report({"WARNING"}, "当前物体没有锁定的顶点组")
            return {"CANCELLED"}

        original_mode = obj.mode
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            combined_weights = []
            for vertex in obj.data.vertices:
                weight = sum(
                    membership.weight
                    for membership in vertex.groups
                    if membership.group in locked_group_indices
                )
                if weight > 0.0:
                    combined_weights.append((vertex.index, weight))

            new_group = obj.vertex_groups.new(name=NEW_GROUP_NAME)
            for vertex_index, weight in combined_weights:
                new_group.add([vertex_index], weight, "REPLACE")
            obj.vertex_groups.active_index = new_group.index
        finally:
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)

        self.report(
            {"INFO"},
            f"已将 {len(locked_group_indices)} 个锁定组的权重合并到 {new_group.name}（{len(combined_weights)} 个顶点）",
        )
        return {"FINISHED"}


class SPX_OT_ConvertActiveGroupToMirrored(Operator):
    bl_idname = "surface_proxy.convert_active_group_to_mirrored"
    bl_label = "将所选顶点组转为镜像顶点组"
    bl_description = "按局部 X 轴将活动组原地拆成 .L/.R，中心线权重各分一半"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == "MESH"
            and obj.vertex_groups.active is not None
        )

    def execute(self, context):
        obj = context.active_object
        source_group = obj.vertex_groups.active
        source_name = source_group.name
        if re.search(r"(?:\.[LR]|_[LR])$", source_name):
            self.report({"WARNING"}, "所选顶点组已经带有左右后缀")
            return {"CANCELLED"}

        left_name = f"{source_name}.L"
        right_name = f"{source_name}.R"
        collisions = [
            name for name in (left_name, right_name) if obj.vertex_groups.get(name)
        ]
        if collisions:
            self.report(
                {"WARNING"},
                f"目标顶点组已存在：{', '.join(collisions)}",
            )
            return {"CANCELLED"}

        source_index = source_group.index
        source_locked = source_group.lock_weight
        maximum_x = max(
            (abs(vertex.co.x) for vertex in obj.data.vertices),
            default=0.0,
        )
        center_tolerance = max(maximum_x * 1.0e-6, 1.0e-6)
        weighted_vertices = []
        for vertex in obj.data.vertices:
            for membership in vertex.groups:
                if membership.group == source_index and membership.weight > 0.0:
                    weighted_vertices.append(
                        (vertex.index, vertex.co.x, membership.weight)
                    )
                    break

        original_mode = obj.mode
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            source_group.name = left_name
            right_group = obj.vertex_groups.new(name=right_name)
            right_group.lock_weight = source_locked
            for vertex_index, x_coordinate, weight in weighted_vertices:
                if x_coordinate < -center_tolerance:
                    source_group.remove([vertex_index])
                    right_group.add([vertex_index], weight, "REPLACE")
                elif x_coordinate <= center_tolerance:
                    half_weight = weight * 0.5
                    source_group.add([vertex_index], half_weight, "REPLACE")
                    right_group.add([vertex_index], half_weight, "REPLACE")

            obj.vertex_groups.active_index = right_group.index
            while right_group.index > source_index + 1:
                bpy.ops.object.vertex_group_move(direction="UP")
            obj.vertex_groups.active_index = source_index
        finally:
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)

        self.report(
            {"INFO"},
            f"已将 {source_name} 原地转换为 {left_name} / {right_name}",
        )
        return {"FINISHED"}


def draw_builtin_vertex_group_context_menu(self, _context):
    layout = self.layout

    layout.operator(
        "object.vertex_group_sort",
        icon="SORTALPHA",
        text="Sort by Name",
    ).sort_type = "NAME"
    layout.operator(
        "object.vertex_group_sort",
        icon="BONE_DATA",
        text="Sort by Bone Hierarchy",
    ).sort_type = "BONE_HIERARCHY"
    layout.separator()
    layout.operator("object.vertex_group_copy", icon="DUPLICATE")
    layout.operator("object.vertex_group_copy_to_selected")
    layout.separator()
    layout.operator(
        "object.vertex_group_mirror", icon="ARROW_LEFTRIGHT"
    ).use_topology = False
    layout.operator(
        "object.vertex_group_mirror", text="Mirror Vertex Group (Topology)"
    ).use_topology = True
    layout.operator(SPX_OT_ConvertActiveGroupToMirrored.bl_idname)
    layout.separator()
    layout.operator(
        "object.vertex_group_remove_from",
        icon="X",
        text="Remove from All Groups",
    ).use_all_groups = True
    layout.operator(
        "object.vertex_group_remove_from", text="Clear Active Group"
    ).use_all_verts = True
    layout.operator(
        "object.vertex_group_remove", text="Delete All Unlocked Groups"
    ).all_unlocked = True
    layout.operator("object.vertex_group_remove", text="Delete All Groups").all = True
    layout.separator()
    props = layout.operator("object.vertex_group_lock", icon="LOCKED", text="Lock All")
    props.action, props.mask = "LOCK", "ALL"
    props = layout.operator(
        "object.vertex_group_lock", icon="UNLOCKED", text="Unlock All"
    )
    props.action, props.mask = "UNLOCK", "ALL"
    props = layout.operator("object.vertex_group_lock", text="Lock Invert All")
    props.action, props.mask = "INVERT", "ALL"


def draw_vertex_group_context_menu(self, _context):
    self.layout.operator(SPX_OT_CreateGroupFromLockedWeights.bl_idname)


def register_menu():
    global _ORIGINAL_VERTEX_GROUP_MENU_DRAW
    menu_type = bpy.types.MESH_MT_vertex_group_context_menu
    menu_type.append(draw_vertex_group_context_menu)

    draw_functions = getattr(menu_type.draw, "_draw_funcs", None)
    if draw_functions and draw_vertex_group_context_menu in draw_functions:
        draw_functions.remove(draw_vertex_group_context_menu)
        native_index = next(
            (
                index
                for index, function in enumerate(draw_functions)
                if function.__module__ == "bl_ui.properties_data_mesh"
            ),
            0,
        )
        _ORIGINAL_VERTEX_GROUP_MENU_DRAW = draw_functions[native_index]
        draw_functions[native_index] = draw_builtin_vertex_group_context_menu
        draw_functions.insert(native_index + 1, draw_vertex_group_context_menu)


def unregister_menu():
    global _ORIGINAL_VERTEX_GROUP_MENU_DRAW
    menu_type = bpy.types.MESH_MT_vertex_group_context_menu
    draw_functions = getattr(menu_type.draw, "_draw_funcs", None)
    if draw_functions and draw_builtin_vertex_group_context_menu in draw_functions:
        replacement_index = draw_functions.index(
            draw_builtin_vertex_group_context_menu
        )
        if _ORIGINAL_VERTEX_GROUP_MENU_DRAW is not None:
            draw_functions[replacement_index] = _ORIGINAL_VERTEX_GROUP_MENU_DRAW
    _ORIGINAL_VERTEX_GROUP_MENU_DRAW = None
    try:
        menu_type.remove(draw_vertex_group_context_menu)
    except ValueError:
        pass


CLASSES = (
    SPX_OT_CreateGroupFromLockedWeights,
    SPX_OT_ConvertActiveGroupToMirrored,
)
