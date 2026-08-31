import statistics
import sys
import time
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Station")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_station
from mmd_station.mmd_ik_runtime.runtime import _iter_model_meshes
from mmd_station.physics_preview import runtime

mmd_station.register()

root = bpy.data.objects[ROOT_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_solver_target = "MMD"
settings.preview_scope = "MODEL"
settings.preview_frequency = 60
settings.preview_substeps = 10
settings.preview_update_rigids = True
root.spx_physics_preview_selected = True
armature = runtime._model_armature(root)
sources = [
    obj
    for obj in _iter_model_meshes(root)
    if obj.name in bpy.context.view_layer.objects and not obj.hide_get()
]
source_states = {
    obj.name: (
        obj.hide_get(),
        tuple((modifier.name, modifier.show_viewport) for modifier in obj.modifiers),
    )
    for obj in sources
}


def update_median(target, samples=14):
    values = []
    for _index in range(4):
        target.update_tag(refresh={"OBJECT"})
        bpy.context.view_layer.update()
    for _index in range(samples):
        target.update_tag(refresh={"OBJECT"})
        started = time.perf_counter()
        bpy.context.view_layer.update()
        values.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(values)


baseline_ms = update_median(armature)
preview = next(item for item in runtime.start_preview(bpy.context) if item.root == root)
if bpy.app.timers.is_registered(runtime._timer_tick):
    bpy.app.timers.unregister(runtime._timer_tick)
proxy = preview.presentation_proxy
assert proxy is not None and proxy.merged, preview.presentation_proxy_error
assert preview.output_armature is armature
assert proxy.armature is armature
assert not any(
    obj.type == "ARMATURE"
    for obj in bpy.data.collections[proxy.collection_name].objects
)

proxied_sources = [bpy.data.objects[state.name] for state in proxy.source_states]
unproxied_sources = [obj for obj in sources if obj not in proxied_sources]
assert len(proxied_sources) >= 2
assert len(proxied_sources) < len(sources)
assert all(obj.name not in bpy.context.view_layer.objects for obj in proxied_sources)
assert all(obj.name in bpy.context.view_layer.objects for obj in unproxied_sources)
assert all(
    [
        modifier.object
        for modifier in proxy_mesh.modifiers
        if modifier.type == "ARMATURE"
    ]
    == [armature]
    for proxy_mesh in proxy.meshes
)
proxy_vertices = sum(len(obj.data.vertices) for obj in proxy.meshes)
proxy_mesh_count = len(proxy.meshes)
source_vertices = sum(len(obj.data.vertices) for obj in proxied_sources)
assert proxy_vertices == source_vertices

driver_basis = {
    name: pose_bone.matrix_basis.copy()
    for name, pose_bone in preview.driver_pose_bones.items()
    if pose_bone is not None
}
for _index in range(8):
    preview.tick()
assert preview.consecutive_tick_failures == 0
driver_change = max(
    (
        preview.driver_pose_bones[name].matrix_basis.translation
        - matrix.translation
    ).length
    for name, matrix in driver_basis.items()
)
assert driver_change > 1.0e-7, driver_change
proxy_ms = update_median(armature)
assert proxy_ms < baseline_ms, (baseline_ms, proxy_ms)

proxy_names = tuple(obj.name for obj in proxy.meshes)
runtime.stop_preview(root)
assert all(bpy.data.objects.get(name) is None for name in proxy_names)
for source in sources:
    hidden, visibility = source_states[source.name]
    assert source.name in bpy.context.view_layer.objects
    assert source.hide_get() == hidden
    expected = dict(visibility)
    assert all(
        modifier.show_viewport == expected[modifier.name]
        for modifier in source.modifiers
        if modifier.name in expected
    )

print(
    "MMD_36_PHYSICS_PRESENTATION_PROXY_OK",
    f"sources={len(sources)}",
    f"proxied={len(proxied_sources)}",
    f"proxy_meshes={proxy_mesh_count}",
    f"vertices={proxy_vertices}",
    f"baseline_ms={baseline_ms:.3f}",
    f"proxy_ms={proxy_ms:.3f}",
    f"driver_change={driver_change:.9g}",
)
