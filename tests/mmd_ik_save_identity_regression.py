import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator, lifecycle


scene = bpy.context.scene
created = []
original_sessions = dict(evaluator._SESSIONS)
original_transactions = list(lifecycle._SAVE_TRANSACTIONS)
original_resolver = lifecycle._registered_session_objects
original_switch = lifecycle.export_switch_to_canonical
original_restore = lifecycle.export_restore_runtime
events = []


def create_object(name):
    obj = bpy.data.objects.new(name, None)
    scene.collection.objects.link(obj)
    created.append(obj)
    return obj


def remove_object(obj):
    if obj is None:
        return
    try:
        if bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    except ReferenceError:
        pass


try:
    evaluator._SESSIONS.clear()
    lifecycle._SAVE_TRANSACTIONS.clear()
    root = create_object("SPX save owned root")
    canonical = create_object("SPX save canonical")
    session = SimpleNamespace(root_ref=root, canonical_ref=canonical)
    evaluator._SESSIONS["registered owner"] = session

    def resolve(registered_name, candidate):
        events.append(("resolve", registered_name, candidate))
        if candidate is session:
            return root, canonical
        return None, None

    lifecycle._registered_session_objects = resolve
    lifecycle.export_switch_to_canonical = lambda candidate: (
        events.append(("switch", candidate)) or {"token": 1}
    )
    lifecycle.export_restore_runtime = lambda candidate, transaction: events.append(
        ("restore", candidate, transaction)
    )

    lifecycle._save_pre(None)
    assert lifecycle._SAVE_TRANSACTIONS == [(root, {"token": 1})]
    assert ("switch", root) in events

    old_name = root.name
    root.name = "SPX save renamed root"
    foreign = create_object(old_name)
    lifecycle._save_post(None)
    restore_events = [event for event in events if event[0] == "restore"]
    assert restore_events == [("restore", root, {"token": 1})]
    assert restore_events[0][1] is not foreign

    events.clear()
    lifecycle._SAVE_TRANSACTIONS.append((root, {"token": 2}))
    remove_object(root)
    replacement = create_object("SPX save renamed root")
    lifecycle._save_post_fail(None)
    assert not [event for event in events if event[0] == "restore"]
    assert replacement is not foreign

    events.clear()
    lifecycle._registered_session_objects = lambda *_args: (None, None)
    lifecycle._save_pre(None)
    assert not [event for event in events if event[0] == "switch"]
    assert not lifecycle._SAVE_TRANSACTIONS

    first_root = create_object("SPX save isolation first")
    second_root = create_object("SPX save isolation second")
    restored = []

    def restore_with_failure(candidate, transaction):
        restored.append((candidate, transaction))
        if candidate is second_root:
            raise RuntimeError("save restore sentinel")

    lifecycle.export_restore_runtime = restore_with_failure
    lifecycle._SAVE_TRANSACTIONS.extend(
        (
            (first_root, {"token": "first"}),
            (second_root, {"token": "second"}),
        )
    )
    try:
        lifecycle._finish_save_transactions()
    except RuntimeError as error:
        assert str(error) == "save restore sentinel"
    else:
        raise AssertionError("The first restore failure must be reported")
    assert restored == [
        (second_root, {"token": "second"}),
        (first_root, {"token": "first"}),
    ]
    assert not lifecycle._SAVE_TRANSACTIONS

    print(
        "MMD_IK_SAVE_IDENTITY_OK",
        "resolved_session=1",
        "rename_restored_direct=1",
        "deleted_root_rejected=1",
        "foreign_lookup=0",
        "restore_isolation=1",
    )
finally:
    lifecycle._registered_session_objects = original_resolver
    lifecycle.export_switch_to_canonical = original_switch
    lifecycle.export_restore_runtime = original_restore
    lifecycle._SAVE_TRANSACTIONS.clear()
    lifecycle._SAVE_TRANSACTIONS.extend(original_transactions)
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)
    for obj in reversed(created):
        remove_object(obj)
