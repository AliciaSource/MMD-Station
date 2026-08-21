import bpy
from bpy.app.handlers import persistent

from .evaluator import (
    _SESSIONS,
    detach_all_sessions,
    rebuild_enabled_sessions,
    resume_sessions_after_pose_clear_repeat,
    suspend_sessions_for_pose_clear_repeat,
)
from .runtime import export_restore_runtime, export_switch_to_canonical


_SAVE_TRANSACTIONS = []
_REBUILD_TIMER_PENDING = False
_POSE_CLEAR_REPEAT_PENDING = False


def _finish_save_transactions():
    while _SAVE_TRANSACTIONS:
        root_name, transaction = _SAVE_TRANSACTIONS.pop()
        root = bpy.data.objects.get(root_name)
        if root is not None:
            export_restore_runtime(root, transaction)


@persistent
def _save_pre(_filepath):
    _finish_save_transactions()
    for root_name in tuple(_SESSIONS):
        root = bpy.data.objects.get(root_name)
        if root is None:
            continue
        transaction = export_switch_to_canonical(root)
        if transaction:
            _SAVE_TRANSACTIONS.append((root.name, transaction))


@persistent
def _save_post(_filepath):
    _finish_save_transactions()


@persistent
def _save_post_fail(_filepath):
    _finish_save_transactions()


def _rebuild_timer():
    global _REBUILD_TIMER_PENDING
    _REBUILD_TIMER_PENDING = False
    try:
        rebuild_enabled_sessions()
    except Exception as error:
        print(f"MMD native live evaluator automatic rebuild failed: {error}")
    return None


def schedule_rebuild():
    global _REBUILD_TIMER_PENDING
    if _REBUILD_TIMER_PENDING:
        return
    _REBUILD_TIMER_PENDING = True
    bpy.app.timers.register(_rebuild_timer, first_interval=0.1)


def _pose_clear_repeat_active():
    operators = getattr(bpy.context.window_manager, "operators", ())
    return bool(
        operators
        and getattr(operators[-1], "bl_idname", "")
        == "POSE_OT_user_transforms_clear"
    )


def _resume_pose_clear_repeat_timer():
    global _POSE_CLEAR_REPEAT_PENDING
    _POSE_CLEAR_REPEAT_PENDING = False
    from ..physics_preview import runtime as preview_runtime

    try:
        resume_sessions_after_pose_clear_repeat()
    except Exception as error:
        print(f"MMD native pose-clear repeat resume failed: {error}")
        detach_all_sessions()
        rebuild_enabled_sessions()
    try:
        preview_runtime.resume_after_pose_clear_repeat()
    except Exception as error:
        print(f"MMD physics pose-clear repeat rebind failed: {error}")
    return None


def schedule_pose_clear_repeat_resume():
    if bpy.app.timers.is_registered(_resume_pose_clear_repeat_timer):
        return
    bpy.app.timers.register(_resume_pose_clear_repeat_timer, first_interval=0.01)


@persistent
def _load_pre(_filepath):
    _SAVE_TRANSACTIONS.clear()
    detach_all_sessions()


@persistent
def _load_post(_filepath):
    schedule_rebuild()


@persistent
def _undo_redo_pre(_scene):
    global _POSE_CLEAR_REPEAT_PENDING
    from ..physics_preview import runtime as preview_runtime

    _SAVE_TRANSACTIONS.clear()
    if _pose_clear_repeat_active() and (_SESSIONS or preview_runtime.is_running()):
        _POSE_CLEAR_REPEAT_PENDING = True
        suspend_sessions_for_pose_clear_repeat()
        preview_runtime.suspend_for_pose_clear_repeat()
        return
    _POSE_CLEAR_REPEAT_PENDING = False
    detach_all_sessions()


@persistent
def _undo_redo_post(_scene):
    if _POSE_CLEAR_REPEAT_PENDING:
        schedule_pose_clear_repeat_resume()
        return
    schedule_rebuild()


_HANDLERS = (
    (bpy.app.handlers.save_pre, _save_pre),
    (bpy.app.handlers.save_post, _save_post),
    (bpy.app.handlers.save_post_fail, _save_post_fail),
    (bpy.app.handlers.load_pre, _load_pre),
    (bpy.app.handlers.load_post, _load_post),
    (bpy.app.handlers.undo_pre, _undo_redo_pre),
    (bpy.app.handlers.undo_post, _undo_redo_post),
    (bpy.app.handlers.redo_pre, _undo_redo_pre),
    (bpy.app.handlers.redo_post, _undo_redo_post),
)


def install():
    for handlers, callback in _HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    schedule_rebuild()


def uninstall():
    global _REBUILD_TIMER_PENDING, _POSE_CLEAR_REPEAT_PENDING
    _finish_save_transactions()
    for handlers, callback in _HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    if bpy.app.timers.is_registered(_rebuild_timer):
        bpy.app.timers.unregister(_rebuild_timer)
    if bpy.app.timers.is_registered(_resume_pose_clear_repeat_timer):
        bpy.app.timers.unregister(_resume_pose_clear_repeat_timer)
    _REBUILD_TIMER_PENDING = False
    _POSE_CLEAR_REPEAT_PENDING = False
