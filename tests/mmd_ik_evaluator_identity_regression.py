import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator


class FakeClosableSession:
    def __init__(self, root):
        self.root_ref = root
        self.close_calls = []

    def close(self, restore=True):
        self.close_calls.append(bool(restore))


scene = bpy.context.scene
second_scene = bpy.data.scenes.new("SPX evaluator identity second scene")
created = []
original_sessions = dict(evaluator._SESSIONS)
original_model_armature = evaluator._model_armature


def create_object(name, data=None):
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    created.append(obj)
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


try:
    assert evaluator._live_object(object()) is None
    assert evaluator._live_scene(object()) is None
    assert evaluator._session_for_root(object()) is None
    root = create_object("SPX evaluator identity root")
    root["spx_mmd_preview_id"] = 91
    canonical = create_object(
        "SPX evaluator canonical armature",
        bpy.data.armatures.new("SPX evaluator canonical armature data"),
    )
    foreign_armature = create_object(
        "SPX evaluator foreign armature",
        bpy.data.armatures.new("SPX evaluator foreign armature data"),
    )
    evaluator._model_armature = lambda candidate: (
        canonical if candidate is root else None
    )

    session = object.__new__(evaluator.Session)
    session.root_ref = root
    session.root_name = root.name
    session.root_preview_id = 91
    session.root_pointer = evaluator._rna_pointer(root)
    session.scene_ref = scene
    session.scene_name = scene.name
    session.scene_pointer = evaluator._rna_pointer(scene)
    session.runtime_ref = foreign_armature
    session.runtime_name = foreign_armature.name
    session.canonical_ref = foreign_armature
    session.canonical_name = foreign_armature.name
    assert session.runtime_object() is None
    assert session.canonical_object() is None

    session.runtime_ref = canonical
    session.runtime_name = canonical.name
    session.canonical_ref = canonical
    session.canonical_name = canonical.name
    assert session.runtime_object() is canonical
    assert session.canonical_object() is canonical

    second_scene.collection.objects.link(root)
    second_scene.collection.objects.link(canonical)
    rebound_root, rebound_armature = evaluator._registered_session_objects(
        root.name,
        session,
    )
    assert rebound_root is None
    assert rebound_armature is None
    second_scene.collection.objects.unlink(canonical)
    second_scene.collection.objects.unlink(root)

    evaluator._SESSIONS.clear()
    evaluator._SESSIONS[root.name] = session
    duplicate = create_object("SPX evaluator duplicate preview root")
    duplicate["spx_mmd_preview_id"] = 91
    assert evaluator._session_for_root(duplicate) is None
    assert session.root_ref is root

    stale_name = "SPX evaluator discarded root"
    stale_root = create_object(stale_name)
    old_session = FakeClosableSession(stale_root)
    remove_object(stale_root)
    replacement_root = create_object(stale_name)
    new_session = FakeClosableSession(replacement_root)
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS["stale identity key"] = old_session
    evaluator._SESSIONS[stale_name] = new_session
    assert evaluator.discard_session(
        root=stale_root,
        previous_root_name=stale_name,
    )
    assert old_session.close_calls == [False]
    assert new_session.close_calls == []
    assert evaluator._SESSIONS == {stale_name: new_session}

    evaluator._SESSIONS.clear()
    evaluator._SESSIONS[stale_name] = old_session
    evaluator.uninstall_handler()
    assert not evaluator._SESSIONS
    assert old_session.close_calls == [False, True]
    assert bpy.data.objects.get(stale_name) is replacement_root

    print(
        "MMD_IK_EVALUATOR_IDENTITY_OK",
        "strict_canonical=1",
        "multi_scene_rejected=1",
        "duplicate_preview_rejected=1",
        "discard_identity=1",
        "uninstall_identity=1",
        "non_rna_rejected=1",
    )
finally:
    evaluator._model_armature = original_model_armature
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)
    for obj in reversed(created):
        remove_object(obj)
    if bpy.data.scenes.get(second_scene.name) is second_scene:
        bpy.data.scenes.remove(second_scene)
