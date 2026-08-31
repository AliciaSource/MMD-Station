import sys
import statistics
import time
from pathlib import Path

import bpy
from mathutils import Vector


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
sys.path.insert(0, str(REPO))

import mmd_station
from mmd_station.mmd_ik_runtime import evaluator
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
source_shape_names = tuple(
    key.name for key in source.data.shape_keys.key_blocks
)
source_group_names = {group.name for group in source.vertex_groups}


def update_median(target, samples=8):
    values = []
    for _index in range(3):
        target.update_tag(refresh={"OBJECT"})
        bpy.context.view_layer.update()
    for _index in range(samples):
        target.update_tag(refresh={"OBJECT"})
        started = time.perf_counter()
        bpy.context.view_layer.update()
        values.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(values)


def evaluated_diagonal(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    minimum = Vector(tuple(min(value[index] for value in corners) for index in range(3)))
    maximum = Vector(tuple(max(value[index] for value in corners) for index in range(3)))
    return (maximum - minimum).length


def tick_median(preview, samples=8):
    values = []
    for _index in range(4):
        preview.tick()
    for _index in range(samples):
        started = time.perf_counter()
        preview.tick()
        values.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(values)


def stage_medians(preview, samples=8):
    stages = ([], [], [])
    for _index in range(samples):
        started = time.perf_counter()
        preview.prepare_step()
        prepared = time.perf_counter()
        stepped = preview.step_solver()
        solved = time.perf_counter()
        if stepped:
            preview.apply_step(*preview.world.outputs())
        applied = time.perf_counter()
        stages[0].append((prepared - started) * 1000.0)
        stages[1].append((solved - prepared) * 1000.0)
        stages[2].append((applied - solved) * 1000.0)
    return tuple(statistics.median(values) for values in stages)


baseline_ms = update_median(armature)
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
root.spx_physics_preview_selected = True
baseline_preview = next(
    item for item in runtime.start_preview(bpy.context) if item.root == root
)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
baseline_tick_ms = tick_median(baseline_preview)
baseline_stages = stage_medians(baseline_preview)
runtime.stop_preview(root)

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
root.hide_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
preview = next(item for item in runtime.start_preview(bpy.context) if item.root == root)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
try:
    proxy = preview.presentation_proxy
    assert proxy is not None and proxy.merged, preview.presentation_proxy_error
    assert preview.output_armature is armature
    assert proxy.armature is armature
    assert len(proxy.meshes) == 1
    proxy_mesh = proxy.mesh
    assert proxy_mesh is not None
    assert len(proxy_mesh.data.vertices) == source_vertex_count
    assert tuple(key.name for key in proxy_mesh.data.shape_keys.key_blocks) == source_shape_names
    assert {group.name for group in proxy_mesh.vertex_groups} == source_group_names
    assert [
        modifier.object
        for modifier in proxy_mesh.modifiers
        if modifier.type == "ARMATURE"
    ] == [armature]
    linked_sources = [
        obj.name for obj in separated if obj.name in bpy.context.view_layer.objects
    ]
    assert not linked_sources, linked_sources
    assert not any(
        obj.type == "ARMATURE"
        for obj in bpy.data.collections[proxy.collection_name].objects
    )

    morph_binding = next(
        binding for binding in proxy.shape_bindings if binding[1] != "Basis"
    )
    proxy_name, key_name, source_name = morph_binding
    source_key = bpy.data.objects[source_name].data.shape_keys.key_blocks[key_name]
    proxy_key = bpy.data.objects[proxy_name].data.shape_keys.key_blocks[key_name]
    original_value = source_key.value
    source_key.value = min(source_key.slider_max, max(source_key.slider_min, 0.37))
    proxy.sync_from_canonical(armature)
    assert abs(proxy_key.value - source_key.value) < 1.0e-7
    source_key.value = original_value
    proxy.sync_from_canonical(armature)

    world = preview.world
    solver = preview.solver
    generation = world.generation
    settings.mmd_ik_root = root
    assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
    assert evaluator._SESSIONS[root.name].canonical_name == armature.name
    assert runtime._ACTIVE_SESSIONS[root.name] is preview
    assert preview.world is world and preview.solver is solver
    assert world.generation == generation
    assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}
    assert runtime._ACTIVE_SESSIONS[root.name] is preview
    assert preview.world is world and preview.solver is solver
    assert world.generation == generation

    chest_driver = armature.pose.bones["胸上2.L"]
    chest_child = armature.pose.bones["胸01.L"]
    foot = armature.pose.bones["足D.L"]
    assert len(chest_child.constraints) == 1
    assert len(foot.constraints) == 1
    chest_before = chest_driver.matrix.copy()
    child_before = chest_child.matrix.copy()
    for _index in range(12):
        preview.tick()
    chest_delta = (chest_driver.matrix.translation - chest_before.translation).length
    child_delta = (chest_child.matrix.translation - child_before.translation).length
    assert chest_delta > 1.0e-5, chest_delta
    assert child_delta > 1.0e-5, child_delta

    diagonal_before = evaluated_diagonal(proxy_mesh)
    foot.location += Vector((0.03, 0.0, 0.0))
    bpy.context.view_layer.update()
    for _index in range(4):
        preview.tick()
    diagonal_after = evaluated_diagonal(proxy_mesh)
    assert diagonal_after < diagonal_before * 1.5, (diagonal_before, diagonal_after)

    proxy_tick_ms = tick_median(preview)
    proxy_stages = stage_medians(preview)
    assert proxy_tick_ms < baseline_tick_ms * 1.3, (
        baseline_tick_ms,
        proxy_tick_ms,
        baseline_stages,
        proxy_stages,
    )
    proxy_ms = update_median(armature)
    assert proxy_ms < baseline_ms * 1.5, (baseline_ms, proxy_ms)
finally:
    runtime.stop_preview(root)

assert all(obj.name in bpy.context.view_layer.objects for obj in separated)

print(
    "MMD_00_SPLIT_MATERIAL_PHYSICS_REGRESSION_OK",
    f"meshes={len(separated)}",
    f"baseline_ms={baseline_ms:.3f}",
    f"proxy_ms={proxy_ms:.3f}",
    f"baseline_tick_ms={baseline_tick_ms:.3f}",
    f"proxy_tick_ms={proxy_tick_ms:.3f}",
    f"baseline_stages={','.join(f'{value:.3f}' for value in baseline_stages)}",
    f"proxy_stages={','.join(f'{value:.3f}' for value in proxy_stages)}",
    f"chest_delta={chest_delta:.9g}",
    f"child_delta={child_delta:.9g}",
    f"diagonal_ratio={diagonal_after / diagonal_before:.6f}",
)
