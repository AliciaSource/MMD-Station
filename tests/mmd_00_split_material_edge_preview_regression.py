import sys
from collections import Counter
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
_EDGE_PREVIEW_NAME = "mmd_edge_preview"
sys.path.insert(0, str(REPO))

import mmd_station
from mmd_station.mmd_ik_runtime.runtime import _iter_model_meshes
from mmd_station.physics_preview import runtime


if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_station.register()

root = next(
    obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", "") == "ROOT"
)
armature = runtime._model_armature(root)
source = next(
    obj
    for obj in _iter_model_meshes(root)
    if obj.name in bpy.context.view_layer.objects and not obj.hide_get()
)
source_vertex_count = len(source.data.vertices)

bpy.ops.object.select_all(action="DESELECT")
source.select_set(True)
bpy.context.view_layer.objects.active = source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
assert bpy.ops.mesh.separate(type="MATERIAL") == {"FINISHED"}
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.update()
separated = [
    obj
    for obj in _iter_model_meshes(root)
    if obj.name in bpy.context.view_layer.objects and not obj.hide_get()
]
assert len(separated) > 1
assert sum(len(obj.data.vertices) for obj in separated) == source_vertex_count

bpy.ops.object.select_all(action="DESELECT")
for obj in separated[:5]:
    obj.select_set(True)
bpy.context.view_layer.objects.active = separated[0]
assert bpy.ops.object.join() == {"FINISHED"}
bpy.context.view_layer.update()
separated = [
    obj
    for obj in _iter_model_meshes(root)
    if obj.name in bpy.context.view_layer.objects and not obj.hide_get()
]
assert len(separated) > 1
assert sum(len(obj.data.vertices) for obj in separated) == source_vertex_count
assert any(len(obj.data.materials) > 1 for obj in separated)


def polygon_material_counts(objects):
    counts = Counter()
    for obj in objects:
        materials = obj.data.materials
        for polygon in obj.data.polygons:
            material = materials[polygon.material_index]
            counts[material.name if material is not None else None] += 1
    return counts


source_material_counts = polygon_material_counts(separated)

bpy.ops.object.select_all(action="DESELECT")
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
assert bpy.ops.mmd_tools.edge_preview_setup(action="CREATE") == {"FINISHED"}
bpy.context.view_layer.update()

edge_sources = [
    obj for obj in separated if obj.modifiers.get("mmd_edge_preview") is not None
]
assert edge_sources
source_states = {
    obj.name: (
        obj.hide_get(),
        obj.hide_render,
        tuple(
            (modifier.name, modifier.show_viewport, modifier.show_render)
            for modifier in obj.modifiers
        ),
    )
    for obj in separated
}

settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
root.spx_physics_preview_selected = True

preview = next(item for item in runtime.start_preview(bpy.context) if item.root == root)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
try:
    proxy = preview.presentation_proxy
    assert proxy is not None and proxy.merged, preview.presentation_proxy_error
    assert len(proxy.meshes) == 1
    proxy_mesh = proxy.mesh
    assert proxy_mesh is not None
    assert len(proxy_mesh.data.vertices) == source_vertex_count

    edge_modifier = proxy_mesh.modifiers.get("mmd_edge_preview")
    assert edge_modifier is not None
    assert edge_modifier.type == "SOLIDIFY"
    assert edge_modifier.show_viewport and edge_modifier.show_render
    assert edge_modifier.vertex_group == "mmd_edge_preview"
    assert proxy_mesh.vertex_groups.get("mmd_edge_preview") is not None

    materials = tuple(proxy_mesh.data.materials)
    base_count = edge_modifier.material_offset
    assert 0 < base_count < len(materials)
    assert all(
        material is None or not material.name.startswith("mmd_edge.")
        for material in materials[:base_count]
    )
    assert all(
        material is not None and material.name.startswith("mmd_edge.")
        for material in materials[base_count:]
    )
    assert len(materials) == base_count * 2
    for index, material in enumerate(materials[:base_count]):
        edge_material = materials[base_count + index]
        expected_name = (
            f"mmd_edge.{material.name}"
            if material is not None and material.mmd_material.enabled_toon_edge
            else "mmd_edge.disabled"
        )
        assert edge_material.name == expected_name, (
            index,
            material.name if material is not None else None,
            edge_material.name,
            expected_name,
        )
    assert all(
        polygon.material_index < base_count for polygon in proxy_mesh.data.polygons
    )
    assert polygon_material_counts((proxy_mesh,)) == source_material_counts

    edge_group_index = proxy_mesh.vertex_groups[_EDGE_PREVIEW_NAME].index
    scale_group_index = proxy_mesh.vertex_groups.find("mmd_edge_scale")
    scale_by_vertex = {}
    if scale_group_index >= 0:
        scale_by_vertex = {
            vertex.index: assignment.weight
            for vertex in proxy_mesh.data.vertices
            for assignment in vertex.groups
            if assignment.group == scale_group_index
        }
    material_by_vertex = {
        vertex_index: polygon.material_index
        for polygon in reversed(proxy_mesh.data.polygons)
        for vertex_index in polygon.vertices
    }
    assert len(material_by_vertex) == len(proxy_mesh.data.vertices)
    for vertex in proxy_mesh.data.vertices:
        actual_weight = next(
            assignment.weight
            for assignment in vertex.groups
            if assignment.group == edge_group_index
        )
        material = materials[material_by_vertex[vertex.index]]
        expected_weight = (
            scale_by_vertex.get(vertex.index, 1.0)
            * (material.mmd_material.edge_weight if material is not None else 1.0)
            * 0.02
        )
        assert abs(actual_weight - expected_weight) < 1.0e-6

    assert all(obj.hide_get() and obj.hide_render for obj in separated)
    assert all(
        not modifier.show_viewport and not modifier.show_render
        for obj in separated
        for modifier in obj.modifiers
    )
finally:
    runtime.stop_preview(root)

for obj in separated:
    hidden, hide_render, modifier_states = source_states[obj.name]
    assert obj.hide_get() == hidden
    assert obj.hide_render == hide_render
    expected = {
        name: (show_viewport, show_render)
        for name, show_viewport, show_render in modifier_states
    }
    assert all(
        (modifier.show_viewport, modifier.show_render) == expected[modifier.name]
        for modifier in obj.modifiers
    )

print(
    "MMD_00_SPLIT_MATERIAL_EDGE_PREVIEW_REGRESSION_OK",
    f"sources={len(separated)}",
    f"edge_sources={len(edge_sources)}",
    f"materials={len(materials)}",
    f"base_materials={base_count}",
)
