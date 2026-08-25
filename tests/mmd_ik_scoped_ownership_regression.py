import sys
from pathlib import Path

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
ROOT_NAME = "\u5408\u5e762"
ARMATURE_NAME = "\u5408\u5e762_arm"
CONTROLLERS = ("\u8db3\uff29\uff2b.L", "AnalToy\u901f\uff29\uff2b")
HIGH_HEEL_CONTROLLER = "\u9ad8\u8ddf\u978b\uff29\uff2b.L"

sys.path[:0] = [str(MMD_TOOLS), str(REPO)]

import mmd_tools

mmd_tools.register()

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime.coordinates import blender_pose_matrix
from mmd_skirt_proxy_creator.mmd_ik_runtime.runtime import (
    _is_generated_constraint,
    runtime_state,
)

mmd_skirt_proxy_creator.register()

root = bpy.data.objects[ROOT_NAME]
armature = bpy.data.objects[ARMATURE_NAME]
settings = bpy.context.scene.surface_proxy_creator
settings.mmd_ik_root = root


def constraint_snapshot():
    return {
        (pose_bone.name, constraint.name): bool(constraint.mute)
        for pose_bone in armature.pose.bones
        for constraint in pose_bone.constraints
    }


def discovered_ik_outputs():
    names = set()
    for pose_bone in armature.pose.bones:
        for constraint in pose_bone.constraints:
            if constraint.type != "IK" or constraint.target != armature:
                continue
            link = pose_bone
            remaining = int(constraint.chain_count)
            while link is not None and (remaining > 0 or constraint.chain_count == 0):
                names.add(link.name)
                link = link.parent
                remaining -= 1
            target_names = {pose_bone.name, constraint.subtarget}
            for target_bone in armature.pose.bones:
                if any(
                    target_constraint.name.lower().startswith("mmd_ik_target_")
                    and getattr(target_constraint, "target", None) == armature
                    and target_constraint.subtarget in target_names
                    for target_constraint in target_bone.constraints
                ):
                    names.add(target_bone.name)
    for bone_name in tuple(names):
        parent = armature.pose.bones[bone_name].parent
        while parent is not None:
            if parent.name in names:
                parent = parent.parent
                continue
            if not any(
                constraint.name.lower().startswith("mmd_")
                for constraint in parent.constraints
            ):
                break
            names.add(parent.name)
            parent = parent.parent
    return frozenset(names)


def assert_solver_output(session, bone_name):
    index = session.bone_indices[bone_name]
    pose_bone = armature.pose.bones[bone_name]
    expected = blender_pose_matrix(
        session.solver.matrix(index),
        session.scale,
        pose_bone.bone.matrix_local,
    )
    error = max(
        abs(pose_bone.matrix[row][column] - expected[row][column])
        for row in range(4)
        for column in range(4)
    )
    assert error < 1.0e-5, (bone_name, error)
    return error


before_constraints = constraint_snapshot()
expected_owned = discovered_ik_outputs()
assert expected_owned

assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
session = evaluator._SESSIONS[root.name]
state = runtime_state(root)
actual_owned = frozenset(state["owned_bones"])
output_bones = frozenset(session.mapping[index].name for index in session.output_indices)
mapped_owned = frozenset(name for name in expected_owned if name in session.bone_indices)
assert actual_owned == expected_owned
assert output_bones == mapped_owned
assert frozenset(session.output_basis) == output_bones
assert frozenset(session.presented_basis) == frozenset(
    pose_bone.name for pose_bone in armature.pose.bones
)

after_constraints = constraint_snapshot()
owned_constraint_keys = {
    (pose_bone.name, constraint.name)
    for pose_bone in armature.pose.bones
    if pose_bone.name in expected_owned
    for constraint in pose_bone.constraints
    if _is_generated_constraint(constraint, armature)
}
assert owned_constraint_keys
for key, previous in before_constraints.items():
    if key in owned_constraint_keys:
        assert after_constraints[key]
    else:
        assert after_constraints[key] == previous, key

non_owned_basis = {
    pose_bone.name: pose_bone.matrix_basis.copy()
    for pose_bone in armature.pose.bones
    if pose_bone.name not in expected_owned
}
tested_links = []
maximum_high_heel_error = 0.0
for controller_name in CONTROLLERS:
    controller = armature.pose.bones.get(controller_name)
    assert controller is not None, controller_name
    constraint_owner = next(
        pose_bone
        for pose_bone in armature.pose.bones
        for constraint in pose_bone.constraints
        if constraint.type == "IK"
        and constraint.target == armature
        and constraint.subtarget == controller_name
    )
    controller.matrix_basis = controller.matrix_basis @ Matrix.Translation(
        (0.01, 0.0, 0.0)
    )
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    bpy.context.view_layer.update()
    assert_solver_output(session, constraint_owner.name)
    tested_links.append(constraint_owner.name)
    if controller_name == CONTROLLERS[0]:
        high_heel_owner = next(
            pose_bone
            for pose_bone in armature.pose.bones
            for constraint in pose_bone.constraints
            if constraint.type == "IK"
            and constraint.target == armature
            and constraint.subtarget == HIGH_HEEL_CONTROLLER
        )
        high_heel_target = next(
            pose_bone
            for pose_bone in armature.pose.bones
            if any(
                constraint.name.lower().startswith("mmd_ik_target_")
                and getattr(constraint, "target", None) == armature
                and constraint.subtarget == high_heel_owner.name
                for constraint in pose_bone.constraints
            )
        )
        for _step in range(9):
            controller.matrix_basis = controller.matrix_basis @ Matrix.Translation(
                (0.01, 0.0, 0.0)
            )
            bpy.context.view_layer.update()
            evaluator._depsgraph_update_post(bpy.context.scene)
            bpy.context.view_layer.update()
            maximum_high_heel_error = max(
                maximum_high_heel_error,
                assert_solver_output(session, high_heel_owner.name),
                assert_solver_output(session, high_heel_target.name),
            )

for name, previous in non_owned_basis.items():
    if name in CONTROLLERS:
        continue
    assert armature.pose.bones[name].matrix_basis == previous, name

assert bpy.ops.surface_proxy.remove_mmd_ik_runtime() == {"FINISHED"}
assert constraint_snapshot() == before_constraints
print(
    "MMD_IK_SCOPED_OWNERSHIP_REGRESSION_OK",
    f"owned={len(expected_owned)}",
    f"outputs={len(output_bones)}",
    f"constraints={len(owned_constraint_keys)}",
    f"links={','.join(tested_links)}",
    f"high_heel_error={maximum_high_heel_error:.9g}",
)
