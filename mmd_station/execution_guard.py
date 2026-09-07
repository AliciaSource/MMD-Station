"""Keep background jobs and native worker callbacks away from scene mutations."""

import threading

import bpy


def scene_access_allowed():
    # Check Python thread identity before touching any Blender RNA.
    if threading.current_thread() is not threading.main_thread():
        return False
    manager = getattr(bpy.context, "window_manager", None)
    return not bool(manager and manager.is_interface_locked)
