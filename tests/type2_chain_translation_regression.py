import math
import sys
from pathlib import Path

from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview.runtime import (
    _resolve_hierarchical_bone_targets,
)


class PoseBone:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent


class Pose:
    def __init__(self, bones):
        self.bones = bones


class Armature:
    def __init__(self, bones):
        self.pose = Pose(bones)


parent = PoseBone("Parent")
child = PoseBone("Child", parent)
armature = Armature((parent, child))

parent_animation = Matrix.Identity(4)
child_animation = Matrix.Translation((0.0, 1.0, 0.0))
parent_physics = Matrix.Rotation(math.radians(90.0), 4, "Z")
child_physics = Matrix.LocRotScale(
    child_animation.translation,
    Matrix.Identity(4).to_quaternion(),
    (1.0, 1.0, 1.0),
)

resolved = _resolve_hierarchical_bone_targets(
    armature,
    {
        parent.name: parent_animation,
        child.name: child_animation,
    },
    {
        parent.name: (2, parent_physics),
        child.name: (2, child_physics),
    },
    ordered_bones=(parent, child),
)

expected_child_position = (parent_physics @ child_animation).translation
actual_child_position = resolved[child.name].translation
error = (actual_child_position - expected_child_position).length
assert error < 5.0e-7, (tuple(actual_child_position), tuple(expected_child_position))

print("TYPE2_CHAIN_TRANSLATION_REGRESSION_OK", f"error={error:.9g}")
