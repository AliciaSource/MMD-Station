import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import display_rig


def fake_window(scene, *operator_names):
    return SimpleNamespace(
        scene=scene,
        modal_operators=tuple(
            SimpleNamespace(bl_idname=name) for name in operator_names
        ),
    )


scene_a = object()
scene_b = object()
manager = SimpleNamespace(
    windows=(
        fake_window(scene_a, "VIEW3D_OT_select"),
        fake_window(scene_b, "TRANSFORM_OT_rotate"),
    )
)

assert not display_rig._transform_modal_active(
    scene=scene_a,
    window_manager=manager,
)
assert display_rig._transform_modal_active(
    scene=scene_b,
    window_manager=manager,
)
assert display_rig._transform_modal_active(window_manager=manager)

manager.windows = (
    fake_window(scene_a),
    fake_window(scene_a, "TRANSFORM_OT_translate"),
)
assert display_rig._transform_modal_active(
    scene=scene_a,
    window_manager=manager,
)

real_manager = bpy.context.window_manager
assert real_manager is not None
assert all(hasattr(window, "modal_operators") for window in real_manager.windows)
assert not display_rig._transform_modal_active(window_manager=real_manager)

rig = display_rig.PreviewDisplayRig.__new__(display_rig.PreviewDisplayRig)
rig.force_normal_update = False

assert not rig._normal_update_due(False)
assert not rig._normal_update_due(True)
assert rig.force_normal_update
assert rig._normal_update_due(False)
assert not rig.force_normal_update
assert not rig._normal_update_due(False)

print("SPX_DISPLAY_RIG_NORMAL_DEFER_UNIT_OK")
