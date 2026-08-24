import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import runtime


class FakePoseInput:
    def __init__(self):
        self.invalidate_calls = 0
        self.refresh_calls = 0

    def invalidate(self):
        self.invalidate_calls += 1

    def refresh_watch_bindings(self):
        self.refresh_calls += 1


def create_armature(scene, name, two_bones=False):
    data = bpy.data.armatures.new(f"{name} data")
    armature = bpy.data.objects.new(name, data)
    build_scene = bpy.context.scene
    build_scene.collection.objects.link(armature)
    build_view_layer = bpy.context.view_layer
    build_view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    parent = data.edit_bones.new("Parent")
    parent.head = (0.0, 0.0, 0.0)
    parent.tail = (0.0, 0.0, 1.0)
    if two_bones:
        driver = data.edit_bones.new("Driver")
        driver.head = parent.tail
        driver.tail = (0.0, 0.0, 2.0)
        driver.parent = parent
        driver.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    if scene is not build_scene:
        build_scene.collection.objects.unlink(armature)
        scene.collection.objects.link(armature)
        scene.view_layers[0].update()
    return armature


def context_state(scene, view_layer):
    active = view_layer.objects.active
    return (
        bpy.context.scene,
        active,
        active.mode if active is not None else "OBJECT",
        tuple(obj for obj in view_layer.objects if obj.select_get()),
    )


context_scene = bpy.context.scene
context_view_layer = bpy.context.view_layer
owner_scene = bpy.data.scenes.new("SPX owner context scene")
owner_view_layer = owner_scene.view_layers[0]
source_armature = None
context_armature = None
source_mesh = None
display_rig = None
created_objects = []

try:
    source_armature = create_armature(
        owner_scene,
        "SPX owner source armature",
        two_bones=True,
    )
    created_objects.append(source_armature)
    mesh_data = bpy.data.meshes.new("SPX owner source mesh data")
    mesh_data.from_pydata(
        ((-0.5, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.0, 1.0)),
        (),
        ((0, 1, 2),),
    )
    source_mesh = bpy.data.objects.new("SPX owner source mesh", mesh_data)
    owner_scene.collection.objects.link(source_mesh)
    created_objects.append(source_mesh)
    group = source_mesh.vertex_groups.new(name="Driver")
    group.add((0, 1, 2), 1.0, "REPLACE")
    modifier = source_mesh.modifiers.new("Armature", "ARMATURE")
    modifier.object = source_armature
    owner_view_layer.update()
    owner_view_layer.objects.active = source_mesh
    source_mesh.select_set(True, view_layer=owner_view_layer)
    owner_selection = tuple(
        obj for obj in owner_view_layer.objects if obj.select_get()
    )

    context_armature = create_armature(
        context_scene,
        "SPX foreign context armature",
    )
    created_objects.append(context_armature)
    context_view_layer.objects.active = context_armature
    context_armature.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    foreign_state = context_state(context_scene, context_view_layer)

    session = object.__new__(runtime.PreviewSession)
    session.scene = owner_scene
    session.scene_name = owner_scene.name
    session.view_layer_name = owner_view_layer.name
    session.root_name = "SPX owner context root"
    session.armature = source_armature
    session.armature_name = source_armature.name
    session.driver_pose_bones = {
        "Driver": source_armature.pose.bones["Driver"],
    }
    session.saved_bone_connections = {"Driver": True}
    session.saved_basis = {
        "Driver": source_armature.pose.bones["Driver"].matrix_basis.copy(),
    }
    session.canonical_output_dirty = False
    session.display_rig = None
    session.debug_batch = None
    session.display_rig_unavailable = False
    session._display_rig_validation_depth = 0
    session._display_rig_valid_cache = False
    session._direct_pose_bones_cache = ()
    session.isolated_output_was_active = False
    session.pose_input = FakePoseInput()
    session.last_output_basis = session._capture_driver_basis()
    session._activate_debug_batch = lambda: False

    session.update_view_layer()
    assert context_state(context_scene, context_view_layer) == foreign_state

    session.set_bone_connections({"Driver": False})
    assert not source_armature.data.bones["Driver"].use_connect
    assert context_state(context_scene, context_view_layer) == foreign_state
    assert owner_view_layer.objects.active is source_mesh
    assert tuple(
        obj for obj in owner_view_layer.objects if obj.select_get()
    ) == owner_selection

    session.saved_bone_connections = {"Driver": True}
    assert session._activate_display_rig()
    display_rig = session.display_rig
    assert display_rig is not None and display_rig.valid
    assert context_state(context_scene, context_view_layer) == foreign_state
    assert owner_view_layer.objects.active is source_mesh
    assert tuple(
        obj for obj in owner_view_layer.objects if obj.select_get()
    ) == owner_selection

    assert session._deactivate_display_rig(
        allow_retry=False,
        restore_source_connections=True,
    )
    display_rig = None
    assert session.display_rig is None
    assert source_armature.data.bones["Driver"].use_connect
    assert context_state(context_scene, context_view_layer) == foreign_state
    assert owner_view_layer.objects.active is source_mesh
    assert tuple(
        obj for obj in owner_view_layer.objects if obj.select_get()
    ) == owner_selection

    print(
        "PHYSICS_PREVIEW_OWNER_CONTEXT_OK",
        f"owner_scene={owner_scene.name}",
        f"context_scene={context_scene.name}",
        f"context_mode={context_armature.mode}",
        "update=1",
        "activate=1",
        "stop=1",
    )
finally:
    if display_rig is not None:
        try:
            display_rig.close()
        except Exception:
            pass
    if context_armature is not None and context_armature.mode != "OBJECT":
        context_view_layer.objects.active = context_armature
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in reversed(created_objects):
        try:
            data = obj.data
            if bpy.data.objects.get(obj.name) is obj:
                bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Armature):
                    bpy.data.armatures.remove(data)
                elif isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
        except ReferenceError:
            continue
    if bpy.data.scenes.get(owner_scene.name) is owner_scene:
        bpy.data.scenes.remove(owner_scene)
