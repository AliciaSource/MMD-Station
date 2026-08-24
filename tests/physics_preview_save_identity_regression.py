import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import runtime


scene = bpy.context.scene
root = bpy.data.objects.new("SPX preview save owned root", None)
replacement = bpy.data.objects.new("SPX preview save replacement root", None)
scene.collection.objects.link(root)
scene.collection.objects.link(replacement)
original_sessions = dict(runtime._ACTIVE_SESSIONS)
original_suspension = runtime._DISPLAY_RIG_SAVE_SUSPENSION
original_runtime_suspended = runtime._RUNTIME_SUSPENDED
original_set_connections = runtime._set_session_bone_connections
events = []


def make_session(bound_root, label):
    return SimpleNamespace(
        root=bound_root,
        saved_bone_connections={"Bone": True},
        display_rig_unavailable=True,
        pose_input=SimpleNamespace(
            invalidate=lambda: events.append((label, "invalidate"))
        ),
        snapshot_reset_pending=False,
        _restore_debug_state=lambda state: events.append(
            (label, "restore", state)
        ),
    )


try:
    owned = make_session(root, "owned")
    foreign = make_session(replacement, "foreign")
    runtime._set_session_bone_connections = (
        lambda session, values: events.append((session, "connections", values))
    )

    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS[root.name] = foreign
    runtime._DISPLAY_RIG_SAVE_SUSPENSION = (
        False,
        [(owned, root, "debug-state")],
    )
    runtime._RUNTIME_SUSPENDED = True
    runtime._resume_display_rigs_after_save(None)
    assert not events

    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS[root.name] = owned
    owned.root = replacement
    runtime._DISPLAY_RIG_SAVE_SUSPENSION = (
        False,
        [(owned, root, "debug-state")],
    )
    runtime._RUNTIME_SUSPENDED = True
    runtime._resume_display_rigs_after_save(None)
    assert not events

    owned.root = root
    runtime._DISPLAY_RIG_SAVE_SUSPENSION = (
        False,
        [(owned, root, "debug-state")],
    )
    runtime._RUNTIME_SUSPENDED = True
    runtime._resume_display_rigs_after_save(None)
    assert ("owned", "restore", "debug-state") in events
    assert ("owned", "invalidate") in events
    assert any(event[0] is owned and event[1] == "connections" for event in events)

    print(
        "PHYSICS_PREVIEW_SAVE_IDENTITY_OK",
        "foreign_session_rejected=1",
        "replacement_root_rejected=1",
        "direct_identity_restored=1",
    )
finally:
    runtime._set_session_bone_connections = original_set_connections
    runtime._ACTIVE_SESSIONS.clear()
    runtime._ACTIVE_SESSIONS.update(original_sessions)
    runtime._DISPLAY_RIG_SAVE_SUSPENSION = original_suspension
    runtime._RUNTIME_SUSPENDED = original_runtime_suspended
    for obj in (replacement, root):
        if bpy.data.objects.get(obj.name) is obj:
            bpy.data.objects.remove(obj, do_unlink=True)
