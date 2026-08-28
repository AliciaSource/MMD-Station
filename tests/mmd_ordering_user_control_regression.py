from types import SimpleNamespace

from mmd_skirt_proxy_creator import mmd_ordering


class Bone:
    def __init__(self, name, bone_id):
        self.name = name
        self.parent = None
        self.children = []
        self.is_mmd_shadow_bone = False
        self.mmd_bone = SimpleNamespace(
            bone_id=bone_id,
            additional_transform_bone_id=-1,
            transform_after_dynamics=False,
            transform_order=0,
        )


class PoseBones(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            return next(bone for bone in self if bone.name == key)
        return super().__getitem__(key)


class FakeFnModel:
    armature = None
    realign_count = 0

    @classmethod
    def find_armature_object(cls, _root):
        return cls.armature

    @staticmethod
    def shift_bone_id(old_bone_id, new_bone_id, _bone_morphs, pose_bones):
        ordered = sorted(pose_bones, key=lambda bone: bone.mmd_bone.bone_id)
        fixed_ids = [bone.mmd_bone.bone_id for bone in ordered]
        moving = next(bone for bone in ordered if bone.mmd_bone.bone_id == old_bone_id)
        old_index = ordered.index(moving)
        new_index = fixed_ids.index(new_bone_id)
        ordered.pop(old_index)
        ordered.insert(new_index, moving)
        for bone, bone_id in zip(ordered, fixed_ids):
            bone.mmd_bone.bone_id = bone_id

    @staticmethod
    def realign_bone_ids(_offset, _bone_morphs, pose_bones):
        FakeFnModel.realign_count += 1
        if FakeFnModel.realign_count > 1:
            raise AssertionError("User ordering must not realign after applying the order")
        ordered = sorted(
            pose_bones,
            key=lambda bone: (bone.parent is not None, bone.name),
        )
        for bone_id, bone in enumerate(ordered):
            bone.mmd_bone.bone_id = bone_id


def run_case(selected_name, action, expected_names):
    parent = Bone("AParent", -1)
    child = Bone("BChild", -1)
    sibling = Bone("CSibling", -1)
    child.parent = parent
    parent.children.append(child)
    pose_bones = PoseBones([parent, child, sibling])
    FakeFnModel.armature = SimpleNamespace(pose=SimpleNamespace(bones=pose_bones))
    FakeFnModel.realign_count = 0
    root = SimpleNamespace(mmd_root=SimpleNamespace(bone_morphs=[]))
    current = mmd_ordering._bone_order(FakeFnModel, root)[1]
    by_name = {bone.name: bone for bone in current}

    original_resolve_items = mmd_ordering._resolve_items
    try:
        mmd_ordering._resolve_items = lambda *_args: (
            FakeFnModel,
            object(),
            root,
            list(current),
            [by_name[selected_name]],
            None,
        )
        moved, active, changed, affected_count = mmd_ordering.reorder_mmd_items(
            SimpleNamespace(),
            "BONE",
            [selected_name],
            action,
        )
    finally:
        mmd_ordering._resolve_items = original_resolve_items

    assert [bone.name for bone in mmd_ordering._bone_order(FakeFnModel, root)[1]] == expected_names
    assert moved == [selected_name]
    assert active is None
    assert changed
    assert affected_count == 1


run_case("BChild", "TOP", ["BChild", "AParent", "CSibling"])
run_case("AParent", "BOTTOM", ["BChild", "CSibling", "AParent"])
print("MMD_ORDERING_USER_CONTROL_REGRESSION_OK")
