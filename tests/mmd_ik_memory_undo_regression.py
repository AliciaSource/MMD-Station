"""Exercise current-model native IK undo without machine-specific PMX assets."""

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bl_ext.blender_org.mmd_tools.core.model import Model
import mmd_station
from mmd_station.blender_compat import select_bones
from mmd_station.mmd_ik_runtime import evaluator, lifecycle, runtime
from mmd_station.physics_preview.runtime import PreviewSession


def finish_undo():
    lifecycle._undo_redo_post(bpy.context.scene)
    if bpy.app.timers.is_registered(lifecycle._resume_undo_redo_timer):
        bpy.app.timers.unregister(lifecycle._resume_undo_redo_timer)
    lifecycle._resume_undo_redo_timer()
    bpy.context.view_layer.update()


def main():
    mmd_station.register()
    model = Model.create("MemoryUndo", add_root_bone=True)
    root, armature = model.rootObject(), model.armature()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        root["import_folder"] = str(folder)
        root["spx_mmd_ik_source_pmx"] = str(folder / "missing.pmx")
        assert not evaluator._resolve_live_source_path(root).is_file()
        first = folder / "first.pmx"
        first.touch()
        assert evaluator._resolve_live_source_path(root) == first
        second = folder / "second.pmx"
        second.touch()
        assert evaluator._resolve_live_source_path(root) == first
        root.pop("spx_mmd_ik_source_pmx")
        assert not evaluator._resolve_live_source_path(root).is_file()
        root["spx_mmd_ik_source_pmx"] = str(second)
        assert evaluator._resolve_live_source_path(root) == second
    root.pop("spx_mmd_ik_source_pmx", None)
    assert not evaluator._resolve_live_source_path(root).is_file()

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    parent = armature.data.edit_bones[0]
    upper = armature.data.edit_bones.new("Upper")
    upper.head, upper.tail, upper.parent = (0, 0, 2), (0, 0.1, 1), parent
    lower = armature.data.edit_bones.new("Lower")
    lower.head, lower.tail, lower.parent = upper.tail, (0, 0, 0.2), upper
    foot = armature.data.edit_bones.new("Foot")
    foot.head, foot.tail, foot.parent = lower.tail, (0, -0.2, 0.2), lower
    control = armature.data.edit_bones.new("Control")
    control.head, control.tail, control.parent = lower.tail, (0, 0, 0.5), parent
    bpy.ops.object.mode_set(mode="OBJECT")
    constraint = armature.pose.bones["Lower"].constraints.new("IK")
    constraint.name = "LegIK"
    constraint.target, constraint.subtarget, constraint.chain_count = armature, "Control", 2
    mesh = bpy.data.meshes.new("MemoryUndoMesh")
    mesh.from_pydata(((0, 0, 1), (0.1, 0, 1), (0, 0.1, 1)), (), ((0, 1, 2),))
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    mesh.materials.append(bpy.data.materials.new("MemoryUndoMaterial"))
    obj.modifiers.new("mmd_armature", "ARMATURE").object = armature
    obj.vertex_groups.new(name="Lower").add((0, 1, 2), 1.0, "REPLACE")

    bpy.context.scene.surface_proxy_creator.mmd_ik_root = root
    assert bpy.ops.surface_proxy.create_mmd_ik_runtime() == {"FINISHED"}
    original = evaluator._SESSIONS[root.name]
    assert original.pmx_path == "<current model>"
    solver = original.solver
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    select_bones(armature, ("Control",))
    control = armature.pose.bones["Control"]
    original.suspended = True
    bpy.ops.pose.user_transforms_clear(only_selected=False)
    bpy.context.view_layer.update()
    original.suspended = False
    evaluator._depsgraph_update_post(bpy.context.scene)
    # The automatic physics reset must not write its old solved startup pose
    # over a clear before native IK can observe the identity input.
    snapshot = PreviewSession.__new__(PreviewSession)
    snapshot._rebind_blender_data = lambda force=False: False
    snapshot.pose_input = SimpleNamespace(invalidate=lambda: None)
    snapshot.root, snapshot.armature = root, armature
    snapshot.saved_root_matrix = root.matrix_world.copy()
    snapshot.saved_pose_basis = {"Control": Matrix.Translation((0.2, 0, 0))}
    snapshot.saved_rigid_matrices, snapshot.saved_joint_matrices = {}, {}
    original.suspended = True
    bpy.ops.pose.user_transforms_clear(only_selected=False)
    bpy.context.view_layer.update()
    original.suspended = False
    snapshot._restore_start_snapshot(preserve_pose=True)
    assert evaluator._matrix_near_identity(control.matrix_basis)
    assert all(evaluator._matrix_near_identity(value) for value in original.input_basis.values())
    lifecycle._undo_redo_pre(bpy.context.scene)
    bpy.ops.pose.user_transforms_clear(only_selected=False)
    finish_undo()
    assert evaluator._SESSIONS[root.name] is original
    assert original.solver is solver
    assert all(evaluator._matrix_near_identity(value) for value in original.input_basis.values())

    # Ordinary pose undo must not be mistaken for the cleared-input transaction.
    control.matrix_basis = Matrix.Translation((0.1, 0, 0))
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    lifecycle._undo_redo_pre(bpy.context.scene)
    control.matrix_basis = Matrix.Translation((0.03, 0, 0))
    finish_undo()
    assert evaluator._SESSIONS[root.name] is original
    assert abs(original.input_basis["Control"].translation.x - 0.03) < 1.0e-6

    # Use the real undo stack too: its RNA objects may be recreated even when
    # the native definition is unchanged. Keep no old pose-bone references.
    root_name, armature_name = root.name, armature.name
    bpy.ops.ed.undo_push(message="Memory IK pose before")
    control.matrix_basis = Matrix.Translation((0.07, 0, 0))
    bpy.context.view_layer.update()
    evaluator._depsgraph_update_post(bpy.context.scene)
    bpy.ops.ed.undo_push(message="Memory IK pose after")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    if bpy.app.timers.is_registered(lifecycle._resume_undo_redo_timer):
        bpy.app.timers.unregister(lifecycle._resume_undo_redo_timer)
    lifecycle._resume_undo_redo_timer()
    root, armature = bpy.data.objects[root_name], bpy.data.objects[armature_name]
    control = armature.pose.bones["Control"]
    snapshot.root, snapshot.armature = root, armature
    assert evaluator._SESSIONS[root.name] is original
    assert original.solver is solver
    assert abs(original.input_basis["Control"].translation.x - 0.03) < 1.0e-6

    def expect_rebuild(change):
        previous = evaluator._SESSIONS[root.name]
        lifecycle._undo_redo_pre(bpy.context.scene)
        change()
        finish_undo()
        current = evaluator._SESSIONS[root.name]
        assert current is not previous
        assert current.solver is not previous.solver
        assert not current.suspended
        return current

    def change_rest():
        bpy.ops.object.mode_set(mode="EDIT")
        armature.data.edit_bones["Upper"].head.x += 0.01
        bpy.ops.object.mode_set(mode="POSE")

    expect_rebuild(change_rest)
    expect_rebuild(lambda: setattr(armature.pose.bones["Lower"].constraints["LegIK"], "chain_count", 1))
    expect_rebuild(lambda: setattr(armature.pose.bones["Lower"], "use_ik_limit_x", True))
    expect_rebuild(lambda: setattr(armature.pose.bones["Upper"].mmd_bone, "transform_order", 2))

    def change_hierarchy():
        bpy.ops.object.mode_set(mode="EDIT")
        extra = armature.data.edit_bones.new("Extra")
        extra.head, extra.tail = (1, 0, 0), (1, 0, 1)
        armature.data.edit_bones["Control"].parent = extra
        bpy.ops.object.mode_set(mode="POSE")

    expect_rebuild(change_hierarchy)

    def change_morph():
        morph = root.mmd_root.bone_morphs.add()
        morph.name = "Offset"
        item = morph.data.add()
        item.bone = "Upper"
        item.location = (0.01, 0, 0)

    expect_rebuild(change_morph)
    # Selecting a Morph row changes UI state, not the exported definition.
    previous = evaluator._SESSIONS[root.name]
    lifecycle._undo_redo_pre(bpy.context.scene)
    root.mmd_root.bone_morphs[-1].active_data = 1
    finish_undo()
    assert evaluator._SESSIONS[root.name] is previous

    def change_epoch():
        state = runtime.runtime_state(root)
        state["session_id"] = "new-authoring-session"
        runtime._save_state(root, state)

    expect_rebuild(change_epoch)
    # Disabling during undo must close the native session, not resurrect it.
    lifecycle._undo_redo_pre(bpy.context.scene)
    state = runtime.runtime_state(root)
    state["enabled"] = False
    runtime._save_state(root, state)
    finish_undo()
    assert root.name not in evaluator._SESSIONS
    snapshot._restore_start_snapshot()
    assert abs(control.matrix_basis.translation.x - 0.2) < 1.0e-6
    bpy.ops.object.mode_set(mode="OBJECT")
    mmd_station.unregister()
    print("MMD_IK_MEMORY_UNDO_REGRESSION_OK")


main()
