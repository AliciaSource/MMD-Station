from .export_hook import install as install_export_hook
from .export_hook import uninstall as uninstall_export_hook
from .evaluator import install_handler, uninstall_handler
from .physics_bridge import install as install_physics_bridge
from .physics_bridge import uninstall as uninstall_physics_bridge
from .vmd_hook import install as install_vmd_hook
from .vmd_hook import uninstall as uninstall_vmd_hook
from .ui import CLASSES, draw, register_settings


def register_services():
    install_export_hook()
    install_handler()
    install_physics_bridge()
    install_vmd_hook()


def unregister_services():
    uninstall_vmd_hook()
    uninstall_physics_bridge()
    uninstall_handler()
    uninstall_export_hook()


__all__ = (
    "CLASSES",
    "draw",
    "register_services",
    "register_settings",
    "unregister_services",
)
