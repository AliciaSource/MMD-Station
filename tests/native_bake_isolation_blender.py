"""Native mesh-cache bake with live MMD preview, or after a bone bake.

Run in a separate Blender process with --factory-startup. Arguments after --:
CLOTH|SOFT_BODY|RIGID_BODY preview|sequential|idle MMD|PMX result.json [gui].
"""

import ctypes
import json
import pathlib
import sys
import time
import traceback

import addon_utils
import bpy


kind, mode, backend, result_path, *options = sys.argv[sys.argv.index("--") + 1:]
gui = "gui" in options
result_path = pathlib.Path(result_path)
loads = []
original_cdll = ctypes.CDLL


def tracked_cdll(path, *args, **kwargs):
    if "mmd_" in str(path):
        loads.append(str(path))
    return original_cdll(path, *args, **kwargs)


ctypes.CDLL = tracked_cdll
addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=False)
addon_utils.enable("mmd_station", default_set=False)
assert not loads, loads
from mmd_station.mmd_physics import _mmd_api
from mmd_station.physics_preview import runtime
from mmd_station.physics_preview import cache as physics_cache
from mmd_station.physics_preview.bake import BakeJob
from bl_ext.blender_org.mmd_tools.core.model import Model

# Keep all generated solver sidecars inside the runner-owned temporary directory.
physics_cache._cache_directory = lambda blend_path=None: result_path.parent / "physics-cache"

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 30
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
model = Model.create("NativeBakeIsolation", add_root_bone=True)
root = model.rootObject()
root.empty_display_size = 0.4
armature = model.armature()
bone = next(iter(armature.data.bones))
bpy.ops.object.mode_set(mode="OBJECT")
FnModel, FnRigidBody, rigid_module = _mmd_api()
group = FnModel.ensure_rigid_group_object(bpy.context, root)
rigid = FnRigidBody.new_rigid_body_objects(bpy.context, group, 1)[0]
FnRigidBody.setup_rigid_body_object(
    obj=rigid, shape_type=rigid_module.shapeType("SPHERE"),
    location=(0, 0, 0), rotation=(0, 0, 0), size=(0.1, 0.1, 0.1),
    dynamics_type=1, name="Dynamic", name_e="Dynamic",
    collision_group_number=0, collision_group_mask=[False] * 16,
    mass=1, friction=0.5, bounce=0, linear_damping=0.5,
    angular_damping=0.5, bone=bone.name,
)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=24, y_subdivisions=24, location=(0, 0, 2))
mesh = bpy.context.object
mesh.parent = armature
weights = mesh.vertex_groups.new(name=bone.name)
weights.add(list(range(len(mesh.data.vertices))), 1.0, "REPLACE")
modifier = mesh.modifiers.new("Armature", "ARMATURE")
modifier.object = armature
if kind == "RIGID_BODY":
    model.build()
    cache = scene.rigidbody_world.point_cache
else:
    native = mesh.modifiers.new(kind, kind)
    if kind == "SOFT_BODY":
        native.settings.use_goal = False
    cache = native.point_cache
cache.frame_start = 1
cache.frame_end = 30
settings = scene.surface_proxy_creator
settings.mmd_root = root
settings.preview_scope = "MODEL"
root.spx_physics_preview_selected = True
settings.preview_solver_target = backend
settings.preview_update_rigids = False
settings.physics_bake_start = 1
settings.physics_bake_end = 30
settings.physics_bake_preroll = 0
settings.physics_bake_continuity = "INDEPENDENT"
source = bpy.data.actions.new("Source")
armature.animation_data_create().action = source
assert not loads, loads
stats = {"kind": kind, "mode": mode, "backend": backend, "locked_ticks": 0, "preview_ticks": 0}
session = None
started = time.monotonic()
original_timer = runtime._timer_tick


def observed_timer():
    locked = bpy.context.window_manager.is_interface_locked
    if locked:
        stats["locked_ticks"] += 1
    before = stats["preview_ticks"]
    result = original_timer()
    if locked:
        assert stats["preview_ticks"] == before
    return result


def action_signature():
    action = armature.animation_data.action
    return (action.name, [
        (curve.data_path, curve.array_index, [tuple(p.co) for p in curve.keyframe_points])
        for curve in action.fcurves
    ])


def complete(error=None):
    if error:
        stats["error"] = error
    stats["ok"] = error is None
    result_path.write_text(json.dumps(stats), encoding="utf-8")
    if gui:
        bpy.ops.wm.quit_blender()


def begin():
    global session, saved_action, saved_modifiers, resume_ticks
    try:
        if mode == "sequential":
            job = BakeJob(bpy.context, "FAST")
            try:
                while job.step():
                    pass
                job.finish()
            finally:
                job.close()
            assert armature.animation_data.action.get("mmd_station_physics_generated")
        elif mode == "preview":
            runtime._timer_tick = observed_timer
            session = runtime.start_preview(bpy.context)[0]
            original_tick = session.tick

            def tick():
                assert not bpy.context.window_manager.is_interface_locked
                stats["preview_ticks"] += 1
                return original_tick()

            session.tick = tick
            observed_timer()
        expected = "mmd_physics_solver_mmd_abi6.dll" if backend == "MMD" else "mmd_physics_solver_abi6.dll"
        if mode == "idle":
            assert not loads, loads
        else:
            assert loads and all(pathlib.Path(p).name == expected for p in loads), loads
        assert mesh.name in scene.objects
        saved_modifiers = [(m.name, m.type, m.show_viewport) for m in mesh.modifiers]
        saved_action = action_signature()
        scene.frame_set(1)
        with bpy.context.temp_override(scene=scene, object=mesh, active_object=mesh, point_cache=cache):
            if kind == "RIGID_BODY" and gui:
                result = bpy.ops.mmd_tools.ptcache_rigid_body_bake()
            else:
                result = bpy.ops.ptcache.bake("INVOKE_DEFAULT" if gui else "EXEC_DEFAULT", bake=True)
        assert result in ({"RUNNING_MODAL"}, {"FINISHED"}), result
        resume_ticks = stats["preview_ticks"]
        if gui:
            bpy.app.timers.register(poll, first_interval=0.1)
        else:
            verify()
            complete()
    except Exception:
        complete(traceback.format_exc())
    return None


def verify():
    assert cache.is_baked
    assert action_signature() == saved_action
    assert [(m.name, m.type, m.show_viewport) for m in mesh.modifiers] == saved_modifiers
    if session is not None:
        assert settings.preview_running
        assert runtime._ACTIVE_SESSIONS[root.name] is session
        observed_timer()
        assert stats["preview_ticks"] > resume_ticks
        assert cache.is_baked
        runtime.stop_preview(root=root, restore=True)
        assert cache.is_baked
    stats["cache_baked"] = cache.is_baked
    stats["action_preserved"] = True
    stats["lazy_loads"] = loads


def poll():
    try:
        if time.monotonic() - started > 90:
            raise AssertionError("Native bake timeout")
        if bpy.context.window_manager.is_interface_locked or not cache.is_baked:
            return 0.1
        verify()
        if mode == "preview":
            assert stats["locked_ticks"] > 0, stats
        complete()
    except Exception:
        complete(traceback.format_exc())
    return None


if gui:
    bpy.app.timers.register(begin, first_interval=0.5)
else:
    begin()
    assert stats["ok"], stats
    print("NATIVE_BAKE_ISOLATION_OK", stats)
