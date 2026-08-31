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
assert proxy is not None
proxy_armature = proxy.armature
proxy_mesh = proxy.mesh
assert proxy_armature is not None and proxy_mesh is not None
proxy_meshes = proxy.meshes
assert preview.output_armature == proxy_armature
assert preview.armature == armature
assert proxy_armature.animation_data is None
assert not any(pose_bone.constraints for pose_bone in proxy_armature.pose.bones)
assert not proxy.merged
assert all(
    len(
        [
            modifier
            for modifier in obj.modifiers
            if modifier.type == "ARMATURE" and modifier.object == proxy_armature
        ]
    )
    == 1
    for obj in proxy_meshes
)
proxied_sources = [bpy.data.objects[state.name] for state in proxy.source_states]
assert {obj.name for obj in proxied_sources} == {obj.name for obj in sources}
assert len(proxied_sources) >= 2
assert all(obj.hide_get() for obj in proxied_sources)
assert all(
    not modifier.show_viewport
    for obj in proxied_sources
    for modifier in obj.modifiers
)
proxy_armature_name = proxy.proxy_armature_name
proxy_mesh_name = proxy.proxy_mesh_name
proxy_vertices = sum(len(obj.data.vertices) for obj in proxy_meshes)
canonical_driver_basis = {
    name: pose_bone.matrix_basis.copy()
    for name, pose_bone in preview.driver_pose_bones.items()
    if pose_bone is not None
}

morph_binding = next(
    (
        (proxy_name, key_name, source_name)
        for proxy_name, key_name, source_name in proxy.shape_bindings
        if key_name != "Basis"
    ),
    None,
)
assert morph_binding is not None
proxy_name, key_name, source_name = morph_binding
source_key = bpy.data.objects[source_name].data.shape_keys.key_blocks[key_name]
proxy_key = bpy.data.objects[proxy_name].data.shape_keys.key_blocks[key_name]
original_morph_value = source_key.value
source_key.value = min(source_key.slider_max, max(source_key.slider_min, 0.37))
proxy.sync_from_canonical(armature)
assert abs(proxy_key.value - source_key.value) < 1.0e-7
source_key.value = original_morph_value
proxy.sync_from_canonical(armature)

for _index in range(8):
    preview.tick(interactive=True)
assert preview.consecutive_tick_failures == 0
canonical_driver_error = max(
    (
        preview.driver_pose_bones[name].matrix_basis.translation
        - matrix.translation
    ).length
    for name, matrix in canonical_driver_basis.items()
)
assert canonical_driver_error < 1.0e-7, canonical_driver_error
proxy_ms = update_median(proxy_armature)
assert proxy_ms < baseline_ms * 0.9, (baseline_ms, proxy_ms)

runtime.stop_preview(root)
assert bpy.data.objects.get(proxy_armature_name) is None
assert bpy.data.objects.get(proxy_mesh_name) is None
for source in proxied_sources:
    hidden, visibility = source_states[source.name]
    assert source.hide_get() == hidden
    expected = dict(visibility)
    assert all(
        modifier.show_viewport == expected[modifier.name]
        for modifier in source.modifiers
        if modifier.name in expected
    )

print(
    "MMD_36_PHYSICS_PRESENTATION_PROXY_OK",
    f"sources={len(proxied_sources)}",
    f"vertices={proxy_vertices}",
    f"baseline_ms={baseline_ms:.3f}",
    f"proxy_ms={proxy_ms:.3f}",
    f"canonical_driver_error={canonical_driver_error:.9g}",
)
