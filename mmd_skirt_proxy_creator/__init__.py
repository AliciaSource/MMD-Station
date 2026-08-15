bl_info = {
    "name": "MMD Skirt Proxy Creator",
    "author": "MMD Skirt Proxy Creator contributors",
    "version": (0, 1, 7),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > MMD代理",
    "description": "Create and edit fitted skirt proxy surfaces with matching bone columns",
    "category": "Rigging",
}

import bmesh
import bpy
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

from .core import (
    ProxyBuildError,
    bilinear_grid_weights,
    bone_name,
    build_cylindrical_surface_grid,
    grid_faces,
    grid_vertices,
)
from .sync import CLASSES as SYNC_CLASSES
from .sync import initialize_proxy_identity
from .sync import register_services as register_sync_services
from .sync import unregister_services as unregister_sync_services
from .mmd_physics import CLASSES as MMD_PHYSICS_CLASSES
from .mmd_physics import (
    draw_browser,
    draw_physics_settings,
    register_browser_context_menu,
    register_settings,
    unregister_browser_context_menu,
)
from .physics_preview import CLASSES as PHYSICS_PREVIEW_CLASSES
from .physics_preview import draw_preview
from .physics_preview import register_settings as register_preview_settings
from .physics_preview import unregister_runtime as unregister_preview_runtime
from .bone_physics_creator import CLASSES as BONE_PHYSICS_CREATOR_CLASSES
from .bone_physics_creator import register_settings as register_bone_physics_creator_settings
from .mmd_ordering import CLASSES as MMD_ORDERING_CLASSES

def _armature_poll(_self, obj):
    return obj is not None and obj.type == "ARMATURE"

class SPX_Settings(PropertyGroup):
    topology: EnumProperty(
        name="代理拓扑",
        items=(
            ("CLOSED", "闭合", "首尾列连接为闭合代理面"),
            ("OPEN", "打开", "首尾列不连接；单列时生成一条代理线"),
        ),
        default="CLOSED",
    )
    columns: IntProperty(
        name="圆周方向",
        description="设为 1 时始终生成一条开放代理线",
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
    prefix: StringProperty(name="名称前缀", default="Skirt")
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

def _create_proxy_mesh(context, source_object, prefix, grid, closed):
    columns = len(grid)
    row_counts = [len(column) for column in grid]
    faces = grid_faces(grid, closed=closed)
    edges = []
    if not faces:
        offset = 0
        for count in row_counts:
            edges.extend((offset + row, offset + row + 1) for row in range(count - 1))
            offset += count
    mesh = bpy.data.meshes.new(f"{prefix}_Surface")
    mesh.from_pydata(
        grid_vertices(grid),
        edges,
        faces,
    )
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    proxy_object = bpy.data.objects.new(f"{prefix}_Surface", mesh)
    context.collection.objects.link(proxy_object)
    proxy_object.matrix_world = source_object.matrix_world.copy()
    proxy_object.display_type = "WIRE"
    proxy_object.show_in_front = True
    proxy_object["surface_proxy_columns"] = columns
    proxy_object["surface_proxy_max_rows"] = max(row_counts)
    proxy_object["surface_proxy_column_rows"] = row_counts
    proxy_object["surface_proxy_column_bones"] = [count - 1 for count in row_counts]
    proxy_object["surface_proxy_source"] = source_object.name
    proxy_object["surface_proxy_closed"] = closed
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
    armature_object.matrix_world = source_object.matrix_world.copy()
    modifier = source_object.modifiers.new(name=f"{prefix}_Armature", type="ARMATURE")
    modifier.object = armature_object
    return armature_object, True

def _preflight_output_names(prefix, armature_object, parent_bone, grid):
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
            name = bone_name(prefix, column, row)
            if name in existing_names:
                raise ProxyBuildError(f"骨骼名称已存在：{name}")

def _create_bones(context, source_object, armature_object, prefix, grid, parent_bone):
    existing_names = set(armature_object.data.bones.keys())
    names = [
        bone_name(prefix, column, row)
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
                edit_bone = armature_object.data.edit_bones.new(bone_name(prefix, column, row))
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
    for name in names:
        pose_bone = armature_object.pose.bones.get(name)
        if pose_bone is None or not hasattr(pose_bone, "mmd_bone"):
            continue
        if not pose_bone.mmd_bone.name_j.strip():
            pose_bone.mmd_bone.name_j = name
        if not pose_bone.mmd_bone.name_e.strip():
            pose_bone.mmd_bone.name_e = name
    return names

def _write_weights(mesh_object, armature_object, selected_indices, prefix, grid, closed):
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
            name = bone_name(prefix, column, row)
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

class SPX_OT_CreateSkirtProxy(Operator):
    bl_idname = "surface_proxy.create_skirt_proxy"
    bl_label = "从选区创建裙面代理"
    bl_description = "从编辑模式选区拟合闭合面、开放面或单列代理线，创建纵列骨并重建选区 deform 权重"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        source_object = context.edit_object
        settings = context.scene.surface_proxy_creator
        prefix = settings.prefix.strip()
        if not prefix:
            self.report({"ERROR"}, "名称前缀不能为空")
            return {"CANCELLED"}

        try:
            selected_indices, vertices = _selected_geometry(source_object)
            requested_armature = _find_armature(source_object, settings.armature)
            deform_group_names = _deform_group_names(source_object, requested_armature)
            if settings.write_weights:
                for vertex_index in selected_indices:
                    if _locked_weight_sum(source_object, vertex_index, deform_group_names) > 1.000001:
                        raise ProxyBuildError(
                            f"顶点 {vertex_index} 的锁定 deform 权重之和超过 1"
                        )

            closed = settings.topology == "CLOSED" and settings.columns != 1
            grid = build_cylindrical_surface_grid(
                vertices,
                settings.columns,
                settings.rows,
                settings.radial_offset,
                closed=closed,
            )
            _preflight_output_names(
                prefix,
                requested_armature,
                settings.parent_bone.strip(),
                grid,
            )

            bpy.ops.object.mode_set(mode="OBJECT")
            proxy_object = _create_proxy_mesh(
                context,
                source_object,
                prefix,
                grid,
                closed,
            )
            armature_object, _created = _ensure_armature(
                context, source_object, requested_armature, prefix
            )
            _create_bones(
                context,
                source_object,
                armature_object,
                prefix,
                grid,
                settings.parent_bone.strip(),
            )
            initialize_proxy_identity(
                proxy_object,
                armature_object,
                prefix,
                grid,
                closed,
            )
            if settings.write_weights:
                _write_weights(
                    source_object,
                    armature_object,
                    selected_indices,
                    prefix,
                    grid,
                    closed,
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
            f"已创建 {settings.columns} 列{('闭合面' if closed else '开放代理')}、每列 {min(row_counts)}–{max(row_counts)} 个代理点，共 {bone_count} 根骨骼",
        )
        return {"FINISHED"}

class SPX_PT_SurfaceProxyCreator(Panel):
    bl_label = "裙面代理创建器"
    bl_idname = "SPX_PT_surface_proxy_creator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD代理"

    def draw(self, context):
        draw_physics_settings(
            self.layout,
            context.scene.surface_proxy_creator,
            context,
        )


class SPX_PT_MMDPhysicsBrowser(Panel):
    bl_label = "MMD 骨骼 / 刚体 / Joint 查看器"
    bl_idname = "SPX_PT_mmd_physics_browser"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD代理"

    def draw(self, context):
        draw_browser(self.layout, context.scene.surface_proxy_creator)


class SPX_PT_MMDPhysicsPreview(Panel):
    bl_label = "MMD 物理预览"
    bl_idname = "SPX_PT_mmd_physics_preview"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD代理"

    def draw(self, context):
        draw_preview(self.layout, context.scene.surface_proxy_creator)


CLASSES = (
    MMD_PHYSICS_CLASSES[0],
    SPX_Settings,
    *SYNC_CLASSES,
    *MMD_PHYSICS_CLASSES[1:],
    *BONE_PHYSICS_CREATOR_CLASSES,
    *MMD_ORDERING_CLASSES,
    *PHYSICS_PREVIEW_CLASSES,
    SPX_OT_CreateSkirtProxy,
    SPX_PT_SurfaceProxyCreator,
    SPX_PT_MMDPhysicsBrowser,
    SPX_PT_MMDPhysicsPreview,
)


def register():
    register_settings(SPX_Settings)
    register_preview_settings(SPX_Settings)
    register_bone_physics_creator_settings(SPX_Settings)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.surface_proxy_creator = PointerProperty(type=SPX_Settings)
    register_sync_services()
    register_browser_context_menu()


def unregister():
    unregister_preview_runtime()
    unregister_browser_context_menu()
    unregister_sync_services()
    del bpy.types.Scene.surface_proxy_creator
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
