import bpy

from .ffi import preload_libraries
from .runtime import stop_preview, unregister_model_id_service
from .bake import (
    CLASSES as BAKE_CLASSES,
    cancel_active_bake,
    draw_bake,
    register_settings as register_bake_settings,
)
from .ui import CLASSES, draw_preview, register_settings

CLASSES = (*CLASSES, *BAKE_CLASSES)


def unregister_runtime():
    cancel_active_bake()
    stop_preview(restore=True)
    unregister_model_id_service()
    if hasattr(bpy.types.Object, "spx_physics_preview_selected"):
        del bpy.types.Object.spx_physics_preview_selected
    if hasattr(bpy.types.Object, "spx_mmd_import_scale_override"):
        del bpy.types.Object.spx_mmd_import_scale_override
    if hasattr(bpy.types.Object, "spx_mmd_interaction_group_id"):
        del bpy.types.Object.spx_mmd_interaction_group_id


__all__ = (
    "CLASSES",
    "draw_preview",
    "draw_bake",
    "preload_libraries",
    "register_settings",
    "register_bake_settings",
    "unregister_runtime",
)
