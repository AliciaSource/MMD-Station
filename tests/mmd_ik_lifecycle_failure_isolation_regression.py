import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator, lifecycle
from mmd_skirt_proxy_creator.physics_preview import runtime as preview_runtime


class SentinelError(RuntimeError):
    pass


events = []
fake_preview_session = type(
    "FakePreviewSession",
    (),
    {
        "root": object(),
        "root_name": "preview root",
    },
)()
second_preview_session = type(
    "SecondFakePreviewSession",
    (),
    {
        "root": object(),
        "root_name": "second preview root",
    },
)()

original_sessions = dict(evaluator._SESSIONS)
original_active_sessions = dict(preview_runtime._ACTIVE_SESSIONS)
original_native_suspend = lifecycle.suspend_sessions_for_undo_redo
original_native_resume = lifecycle.resume_sessions_after_undo_redo
original_native_detach = lifecycle.detach_all_sessions
original_native_rebuild = lifecycle.rebuild_enabled_sessions
original_capture = lifecycle.capture_physics_bindings
original_preview_is_running = preview_runtime.is_running
original_preview_suspend = preview_runtime.suspend_for_undo_redo
original_preview_resume = preview_runtime.resume_after_undo_redo
original_pending = lifecycle._UNDO_REDO_RESUME_PENDING


def fail(name):
    def callback(*_args, **_kwargs):
        events.append(name)
        raise SentinelError(name)

    return callback


try:
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS["native"] = object()
    preview_runtime._ACTIVE_SESSIONS.clear()
    preview_runtime._ACTIVE_SESSIONS["preview"] = fake_preview_session
    preview_runtime._ACTIVE_SESSIONS["second preview"] = second_preview_session
    preview_runtime.is_running = lambda: True

    lifecycle.suspend_sessions_for_undo_redo = fail("native suspend")
    preview_runtime.suspend_for_undo_redo = fail("preview suspend")
    lifecycle._undo_redo_pre(None)
    assert events == ["native suspend", "preview suspend"]
    assert lifecycle._UNDO_REDO_RESUME_PENDING

    events.clear()
    lifecycle.resume_sessions_after_undo_redo = fail("native resume")
    lifecycle.detach_all_sessions = fail("native detach")
    lifecycle.rebuild_enabled_sessions = fail("native rebuild")
    preview_runtime.resume_after_undo_redo = fail("preview resume")

    def capture_with_first_failure(_root, preview_session):
        events.append(f"preview capture {preview_session.root_name}")
        if preview_session is fake_preview_session:
            raise SentinelError("preview capture")

    lifecycle.capture_physics_bindings = capture_with_first_failure
    assert lifecycle._resume_undo_redo_timer() is None
    assert events == [
        "native resume",
        "native detach",
        "native rebuild",
        "preview resume",
        "preview capture preview root",
        "preview capture second preview root",
    ]
    assert not lifecycle._UNDO_REDO_RESUME_PENDING

    print(
        "MMD_IK_LIFECYCLE_FAILURE_ISOLATION_OK",
        f"phases={len(events)}",
        "pre_both_sides=1",
        "resume_cleanup_preview=1",
    )
finally:
    lifecycle.suspend_sessions_for_undo_redo = original_native_suspend
    lifecycle.resume_sessions_after_undo_redo = original_native_resume
    lifecycle.detach_all_sessions = original_native_detach
    lifecycle.rebuild_enabled_sessions = original_native_rebuild
    lifecycle.capture_physics_bindings = original_capture
    preview_runtime.is_running = original_preview_is_running
    preview_runtime.suspend_for_undo_redo = original_preview_suspend
    preview_runtime.resume_after_undo_redo = original_preview_resume
    lifecycle._UNDO_REDO_RESUME_PENDING = original_pending
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)
    preview_runtime._ACTIVE_SESSIONS.clear()
    preview_runtime._ACTIVE_SESSIONS.update(original_active_sessions)
