import bpy
from bpy.app.handlers import persistent

from .evaluator import (
    _SESSIONS,
    detach_all_sessions,
    rebuild_enabled_sessions,
    resume_sessions_after_undo_redo,
    suspend_sessions_for_undo_redo,
)
from .runtime import export_restore_runtime, export_switch_to_canonical


_SAVE_TRANSACTIONS = []
_REBUILD_TIMER_PENDING = False
_UNDO_REDO_RESUME_PENDING = False


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


def _resume_undo_redo_timer():
    global _UNDO_REDO_RESUME_PENDING
    _UNDO_REDO_RESUME_PENDING = False
    from ..physics_preview import runtime as preview_runtime

    try:
        resume_sessions_after_undo_redo()
    except Exception as error:
        print(f"MMD native Undo/Redo resume failed: {error}")
        detach_all_sessions()
        rebuild_enabled_sessions()
    try:
        preview_runtime.resume_after_undo_redo()
    except Exception as error:
        print(f"MMD physics Undo/Redo rebind failed: {error}")
    return None


def schedule_undo_redo_resume():
    if bpy.app.timers.is_registered(_resume_undo_redo_timer):
        return
    bpy.app.timers.register(_resume_undo_redo_timer, first_interval=0.01)


@persistent
def _load_pre(_filepath):
    _SAVE_TRANSACTIONS.clear()
    detach_all_sessions()


@persistent
def _load_post(_filepath):
    schedule_rebuild()


@persistent
def _undo_redo_pre(_scene):
    global _UNDO_REDO_RESUME_PENDING
    from ..physics_preview import runtime as preview_runtime

    _SAVE_TRANSACTIONS.clear()
    if _SESSIONS or preview_runtime.is_running():
        _UNDO_REDO_RESUME_PENDING = True
        suspend_sessions_for_undo_redo()
        preview_runtime.suspend_for_undo_redo()
        return
    _UNDO_REDO_RESUME_PENDING = False
    detach_all_sessions()


@persistent
def _undo_redo_post(_scene):
    if _UNDO_REDO_RESUME_PENDING:
        schedule_undo_redo_resume()
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
    global _REBUILD_TIMER_PENDING, _UNDO_REDO_RESUME_PENDING
    _finish_save_transactions()
    for handlers, callback in _HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    if bpy.app.timers.is_registered(_rebuild_timer):
        bpy.app.timers.unregister(_rebuild_timer)
    if bpy.app.timers.is_registered(_resume_undo_redo_timer):
        bpy.app.timers.unregister(_resume_undo_redo_timer)
    _REBUILD_TIMER_PENDING = False
    _UNDO_REDO_RESUME_PENDING = False
