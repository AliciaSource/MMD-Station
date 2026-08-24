import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from bpy.props import StringProperty
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import runtime


class FakeBatch:
    valid = True

    def __init__(self):
        self.rigids = None
        self.joints = None

    def update_all(self, rigids, joints, visible=True):
        assert visible
        self.rigids = dict(rigids)
        self.joints = dict(joints)


def create_object(scene, name, data=None):
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    return obj


def remove_object(obj):
    if obj is None:
        return
    try:
        data = obj.data
        if bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Armature) and data.users == 0:
            bpy.data.armatures.remove(data)
    except ReferenceError:
        pass


scene = bpy.context.scene
added_mmd_type = not hasattr(bpy.types.Object, "mmd_type")
if added_mmd_type:
    bpy.types.Object.mmd_type = StringProperty(default="NONE")

created = []
original_sessions = dict(runtime._ACTIVE_SESSIONS)
original_model_armature = runtime._model_armature
original_rigid_objects = runtime._rigid_objects
original_joint_objects = runtime._joint_objects

try:
    runtime._ACTIVE_SESSIONS.clear()
    assert runtime._live_object(object()) is None
    assert runtime._live_scene(object()) is None
    assert runtime._session_for_root(object()) is None

    owned_root = create_object(scene, "SPX identity owned root")
    foreign_root = create_object(scene, "SPX identity foreign root")
    created.extend((owned_root, foreign_root))
    owned_root.mmd_type = "ROOT"
    foreign_root.mmd_type = "ROOT"
    stale_session = SimpleNamespace(root=owned_root)
    runtime._ACTIVE_SESSIONS[foreign_root.name] = stale_session
    assert runtime._session_for_root(foreign_root) is None
    assert runtime._session_for_root(owned_root) is stale_session

    recreated_name = "SPX identity recreated root"
    original_root = create_object(scene, recreated_name)
    original_root.mmd_type = "ROOT"
    original_root["spx_mmd_preview_id"] = 73
    root_session = object.__new__(runtime.PreviewSession)
    root_session.root = original_root
    root_session.root_name = recreated_name
    root_session.root_preview_id = 73
    remove_object(original_root)
    replacement_root = create_object(scene, recreated_name)
    created.append(replacement_root)
    replacement_root.mmd_type = "ROOT"
    replacement_root["spx_mmd_preview_id"] = 73
    try:
        root_session._resolve_root_object(scene)
    except runtime.PreviewSessionInvalidError:
        pass
    else:
        raise AssertionError("Normal runtime must reject a recreated root ID")
    assert root_session._resolve_root_object(
        scene,
        allow_recreated=True,
    ) is replacement_root

    authoritative = create_object(scene, "SPX authoritative rigid")
    foreign = create_object(scene, "SPX foreign rigid")
    created.extend((authoritative, foreign))
    binding_session = object.__new__(runtime.PreviewSession)
    try:
        binding_session._resolve_bound_object(
            foreign,
            foreign.name,
            scene,
            "rigid",
            (authoritative,),
        )
    except runtime.PreviewSessionInvalidError:
        pass
    else:
        raise AssertionError("A live foreign object must not bypass model membership")
    assert binding_session._resolve_bound_object(
        authoritative,
        authoritative.name,
        scene,
        "rigid",
        (authoritative,),
    ) is authoritative

    armature_data = bpy.data.armatures.new("SPX identity armature data")
    canonical_armature = create_object(
        scene,
        "SPX identity canonical armature",
        armature_data,
    )
    foreign_armature = create_object(
        scene,
        "SPX identity foreign armature",
        bpy.data.armatures.new("SPX identity foreign armature data"),
    )
    created.extend((canonical_armature, foreign_armature))
    binding_session.armature = foreign_armature
    binding_session.armature_name = foreign_armature.name
    runtime._model_armature = lambda root: (
        canonical_armature if root is replacement_root else None
    )
    assert binding_session._resolve_armature_object(
        replacement_root,
        scene,
    ) is canonical_armature

    authoritative_joint = create_object(scene, "SPX authoritative joint")
    foreign_joint = create_object(scene, "SPX foreign joint")
    created.extend((authoritative_joint, foreign_joint))
    runtime._rigid_objects = lambda _root: [authoritative]
    runtime._joint_objects = lambda _root: [authoritative_joint]
    batch = FakeBatch()
    debug_session = object.__new__(runtime.PreviewSession)
    debug_session.root = replacement_root
    debug_session.debug_batch = batch
    debug_session._debug_rigid_matrices = {
        authoritative: Matrix.Identity(4),
        foreign: Matrix.Translation((1.0, 0.0, 0.0)),
    }
    debug_session._debug_joint_matrices = {
        authoritative_joint: Matrix.Identity(4),
        foreign_joint: Matrix.Translation((0.0, 1.0, 0.0)),
    }
    debug_session.settings = SimpleNamespace(preview_update_rigids=True)
    debug_session.update_view_layer = lambda: None
    debug_session._restore_debug_state(({}, {}))
    assert set(debug_session._debug_rigid_matrices) == {authoritative}
    assert set(debug_session._debug_joint_matrices) == {authoritative_joint}
    assert set(batch.rigids) == {authoritative}
    assert set(batch.joints) == {authoritative_joint}

    print(
        "PHYSICS_PREVIEW_BINDING_IDENTITY_OK",
        "session_key=1",
        "normal_recreate_rejected=1",
        "undo_recreate_allowed=1",
        "foreign_members=0",
        "non_rna_rejected=1",
    )
finally:
    runtime._model_armature = original_model_armature
    runtime._rigid_objects = original_rigid_objects
    runtime._joint_objects = original_joint_objects
    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS.update(original_sessions)
    for obj in reversed(created):
        remove_object(obj)
    if added_mmd_type:
        del bpy.types.Object.mmd_type
