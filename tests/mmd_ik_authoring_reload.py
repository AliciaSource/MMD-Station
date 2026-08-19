import os
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
sys.path.insert(0, str(MMD_TOOLS_PARENT))
sys.path.insert(0, str(REPO))

import mmd_tools

if not hasattr(bpy.types.Object, "mmd_type"):
    mmd_tools.register()

import mmd_skirt_proxy_creator

if not hasattr(bpy.types.Scene, "surface_proxy_creator"):
    mmd_skirt_proxy_creator.register()

from mmd_skirt_proxy_creator.mmd_ik_runtime.evaluator import _SESSIONS, is_active
from mmd_skirt_proxy_creator.mmd_ik_runtime.lifecycle import _rebuild_timer
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import runtime_state


_rebuild_timer()
root = next(obj for obj in bpy.data.objects if getattr(obj, "mmd_type", "") == "ROOT")
state = runtime_state(root)
assert state["schema"] == 2 and state["enabled"] and state["action_input"]
assert is_active(root)
session = _SESSIONS[root.name]
assert session.live and session.action_input
assert not any(obj.name.startswith("MMDIK") for obj in bpy.data.objects)
assert not any(constraint.name == ".MMD Native Output" for bone in bpy.data.objects[state["canonical_armature"]].pose.bones for constraint in bone.constraints)
print("MMD_IK_AUTHORING_RELOAD_OK", root.name, len(session.input_basis))
