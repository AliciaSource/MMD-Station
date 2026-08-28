from types import SimpleNamespace

import mmd_station
from mmd_station.mirror_physics import (
    _canonical_sources,
    _find_mirror_rigid,
    _source_side,
    mirrored_name,
)


class Rigid:
    def __init__(self, name, bone, name_j, name_e=""):
        self.name = name
        self.mmd_type = "RIGID_BODY"
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
armature = SimpleNamespace(
    data=SimpleNamespace(bones={"Bone_Piao222.L": left_bone, "Bone_Piao222.R": right_bone}),
    pose=SimpleNamespace(bones={"Bone_Piao222.L": left_bone, "Bone_Piao222.R": right_bone}),
)
left = Rigid("263_Bone_Piao222_L", "Bone_Piao222.L", "Bone_Piao222_L")
right = Rigid("268_Bone_Piao222_R", "Bone_Piao222.R", "Bone_Piao222_R")

assert mirrored_name(left.mmd_rigid.name_j) == right.mmd_rigid.name_j
assert _source_side(left) == "L"
assert _source_side(right) == "R"
assert _find_mirror_rigid(left, [left, right], armature) is right
assert _find_mirror_rigid(right, [left, right], armature) is left
assert _canonical_sources([right, left], lambda item: _find_mirror_rigid(item, [left, right], armature)) == [left]

print("MIRROR_UNDERSCORE_SUFFIX_REGRESSION_OK")

mmd_station.unregister()
