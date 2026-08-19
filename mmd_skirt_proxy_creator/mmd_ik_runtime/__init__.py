from .export_hook import install as install_export_hook
from .export_hook import uninstall as uninstall_export_hook
from .evaluator import install_handler, uninstall_handler
from .keying import CLASSES as KEYING_CLASSES
from .keying import install_keymaps, uninstall_keymaps
from .lifecycle import install as install_lifecycle
from .lifecycle import uninstall as uninstall_lifecycle
from .physics_bridge import install as install_physics_bridge
from .physics_bridge import uninstall as uninstall_physics_bridge
from .pmx_hook import install as install_pmx_hook
from .pmx_hook import uninstall as uninstall_pmx_hook
from .runtime import register_state_property, unregister_state_property
from .vmd_hook import install as install_vmd_hook
from .vmd_hook import uninstall as uninstall_vmd_hook
from .ui import CLASSES, draw, register_settings


def register_services():
    register_state_property()
    install_export_hook()
    install_handler()
    install_physics_bridge()
    install_pmx_hook()
    install_vmd_hook()
    install_keymaps()
    install_lifecycle()


def unregister_services():
    uninstall_lifecycle()
    uninstall_keymaps()
    uninstall_vmd_hook()
    uninstall_pmx_hook()
    uninstall_physics_bridge()
    uninstall_handler()
    uninstall_export_hook()
    unregister_state_property()


__all__ = (
    "CLASSES",
    "draw",
    "register_services",
    "register_settings",
    "unregister_services",
)


CLASSES = (*CLASSES, *KEYING_CLASSES)
