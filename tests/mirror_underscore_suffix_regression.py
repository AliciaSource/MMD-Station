from types import SimpleNamespace

from mathutils import Matrix

import mmd_station
from mmd_station.mirror_physics import (
    _canonical_sources,
    _find_mirror_rigid,
    _source_side,
    mirrored_name,
)


class Rigid:
    def __init__(self, name, bone, name_j, name_e="", x=0.0):
        self.name = name
        self.mmd_type = "RIGID_BODY"
        self.matrix_world = Matrix.Translation((x, 0.0, 0.0))
        self.mmd_rigid = SimpleNamespace(
            bone=bone,
            name_j=name_j,
            name_e=name_e,
            type=1,
            shape="BOX",
        )


try:
    mmd_station.register()
except Exception:
    pass

left_bone = SimpleNamespace(
    mmd_bone=SimpleNamespace(name_j="左Bone_Piao222", name_e="Bone_Piao222_L")
)
right_bone = SimpleNamespace(
    mmd_bone=SimpleNamespace(name_j="右Bone_Piao222", name_e="Bone_Piao222_R")
)
center_bone = SimpleNamespace(
    mmd_bone=SimpleNamespace(name_j="Bone_Piao014_M", name_e="Bone_Piao014_M")
)
armature = SimpleNamespace(
    matrix_world=Matrix.Identity(4),
    data=SimpleNamespace(
        bones={
            "Bone_Piao222.L": left_bone,
            "Bone_Piao222.R": right_bone,
            "Bone_Piao014_M": center_bone,
        }
    ),
    pose=SimpleNamespace(
        bones={
            "Bone_Piao222.L": left_bone,
            "Bone_Piao222.R": right_bone,
            "Bone_Piao014_M": center_bone,
        }
    ),
)
left = Rigid("263_Bone_Piao222_L", "Bone_Piao222.L", "Bone_Piao222_L")
right = Rigid("268_Bone_Piao222_R", "Bone_Piao222.R", "Bone_Piao222_R")
center = Rigid("095_Bone_Piao014_M", "Bone_Piao014_M", "Bone_Piao014_M", x=-1.0e-6)
off_center_copy = Rigid("095_Bone_Piao014_M", "Bone_Piao014_M", "Bone_Piao014_M", x=0.1)

assert mirrored_name(left.mmd_rigid.name_j) == right.mmd_rigid.name_j
assert _source_side(left) == "L"
assert _source_side(right) == "R"
assert _find_mirror_rigid(left, [left, right], armature) is right
assert _find_mirror_rigid(right, [left, right], armature) is left
assert _canonical_sources([right, left], lambda item: _find_mirror_rigid(item, [left, right], armature)) == [left]
assert _source_side(center) == "M"
assert _find_mirror_rigid(center, [center], armature, allow_shared=True) is center
assert _find_mirror_rigid(center, [center], armature, allow_shared=False) is None
assert _find_mirror_rigid(off_center_copy, [off_center_copy], armature, allow_shared=True) is None

print("MIRROR_UNDERSCORE_SUFFIX_REGRESSION_OK")

mmd_station.unregister()
