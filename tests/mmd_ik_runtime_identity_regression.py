import json
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime import runtime


class FakeModelAPI:
    canonical = None
    meshes = ()

    @classmethod
    def find_armature_object(cls, _root):
        return cls.canonical

    @classmethod
    def iterate_mesh_objects(cls, _root):
        return iter(cls.meshes)


scene = bpy.context.scene
created = []
original_model_api = runtime.mmd_model_api
original_restore_mutes = runtime._restore_constraint_mutes
original_canonical_armature = runtime.canonical_armature
original_mute_constraints = runtime._mute_constraints
original_discard = evaluator.discard_session


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
    root = create_object("SPX legacy identity root")
    canonical = create_object(
        "SPX legacy canonical",
        bpy.data.armatures.new("SPX legacy canonical data"),
    )
    foreign = create_object(
        "SPX legacy foreign runtime",
        bpy.data.armatures.new("SPX legacy foreign runtime data"),
    )
    FakeModelAPI.canonical = canonical
    FakeModelAPI.meshes = ()
    runtime.mmd_model_api = lambda: FakeModelAPI
    runtime._restore_constraint_mutes = lambda *_args: None
    root[runtime.STATE_KEY] = json.dumps(
        {
            "schema": 1,
            "canonical_armature": canonical.name,
            "runtime_armature": foreign.name,
            "enabled": True,
            "muted_constraints": [],
        }
    )
    try:
        runtime._load_state(root)
    except runtime.MMDIKRuntimeError:
        pass
    else:
        raise AssertionError("Unwitnessed legacy runtime must fail closed")
    assert bpy.data.objects.get(foreign.name) is foreign
    assert runtime.STATE_KEY in root

    root[runtime.STATE_KEY] = json.dumps(
        {
            "schema": 99,
            "runtime_armature": foreign.name,
        }
    )
    try:
        runtime._load_state(root)
    except runtime.MMDIKRuntimeError:
        pass
    else:
        raise AssertionError("Unknown runtime schema must fail closed")
    assert bpy.data.objects.get(foreign.name) is foreign

    replacement = create_object(
        "SPX save replacement canonical",
        bpy.data.armatures.new("SPX save replacement canonical data"),
    )
    state = {
        "schema": runtime.SCHEMA,
        "session_id": "identity-session",
        "canonical_armature": replacement.name,
        "enabled": True,
        "muted_constraints": [],
    }
    root[runtime.STATE_KEY] = json.dumps(state)
    runtime.canonical_armature = lambda _root, _state=None: replacement
    mute_calls = []
    discard_calls = []
    runtime._mute_constraints = lambda candidate: mute_calls.append(candidate) or []
    evaluator.discard_session = lambda **kwargs: discard_calls.append(kwargs) or True
    result = runtime.export_restore_runtime(
        root,
        {
            "state": dict(state),
            "canonical": canonical,
        },
    )
    assert result == 0
    assert not mute_calls
    assert discard_calls == [{"root": root}]

    print(
        "MMD_IK_RUNTIME_IDENTITY_OK",
        "legacy_foreign_preserved=1",
        "unknown_schema_rejected=1",
        "save_canonical_swap_rejected=1",
    )
finally:
    runtime.mmd_model_api = original_model_api
    runtime._restore_constraint_mutes = original_restore_mutes
    runtime.canonical_armature = original_canonical_armature
    runtime._mute_constraints = original_mute_constraints
    evaluator.discard_session = original_discard
    for obj in reversed(created):
        remove_object(obj)
