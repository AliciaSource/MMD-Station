import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime as preview_runtime


class FakeSolver:
    names = ("Bone",)
    rest_positions = ((0.0, 1.0, 0.0),)

    def __init__(self):
        self.reset_calls = 0
        self.clear_calls = 0
        self.close_calls = 0
        self.prepared = []

    def prepare_live_matrix_indices(self, indices):
        prepared = tuple(indices)
        self.prepared.append(prepared)
        return prepared

    def reset(self):
        self.reset_calls += 1

    def clear_external_transforms(self):
        self.clear_calls += 1

    def close(self):
        self.close_calls += 1


def create_armature(scene, object_name, data_name, head_z, tail):
    data = bpy.data.armatures.new(data_name)
    armature = bpy.data.objects.new(object_name, data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = data.edit_bones.new("Bone")
    bone.head = (0.0, 0.0, head_z)
    bone.tail = tail
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    return armature


scene = bpy.context.scene
scene.frame_set(17)
root = bpy.data.objects.new("SPX rebind root", None)
scene.collection.objects.link(root)
armature = create_armature(
    scene,
    "SPX rebind armature",
    "SPX rebind armature data",
    1.0,
    (0.0, 0.0, 2.0),
)
armature.parent = root
solver = FakeSolver()
session = evaluator.Session(
    root_name=root.name,
    runtime_name=armature.name,
    pmx_path="",
    vmd_path="",
    blender_start=1,
    vmd_start=0,
    solver=solver,
    mapping=(armature.pose.bones["Bone"],),
    scale=1.0,
    muted_constraints=[],
    original_action=None,
    canonical_name=armature.name,
    live=True,
    input_basis={
        "Bone": armature.pose.bones["Bone"].matrix_basis.copy(),
    },
    root_ref=root,
    runtime_ref=armature,
    canonical_ref=armature,
    root_pointer=evaluator._rna_pointer(root),
    scene_name=scene.name,
    scene_pointer=evaluator._rna_pointer(scene),
)
session.refresh_hotpath_bindings(armature)
evaluator._SESSIONS[root.name] = session
preview_session = object.__new__(preview_runtime.PreviewSession)
preview_session.root_name = root.name
preview_session.armature_name = armature.name
preview_session.rigid_names = []
preview_session.joint_names = []
preview_session.display_rig = None

fast_path_counts = {
    "rest_signature": 0,
    "bone_map": 0,
    "refresh_hotpath": 0,
    "rebuild_bindings": 0,
    "rebind_names": 0,
}
original_rest_signature = evaluator._armature_rest_signature
original_bone_map = evaluator._bone_map
original_rebind_names = evaluator.rebind_session_names
original_refresh_hotpath = session.refresh_hotpath_bindings
original_rebuild_bindings = session.rebuild_bindings


def counted_rest_signature(*args, **kwargs):
    fast_path_counts["rest_signature"] += 1
    return original_rest_signature(*args, **kwargs)


def counted_bone_map(*args, **kwargs):
    fast_path_counts["bone_map"] += 1
    return original_bone_map(*args, **kwargs)


def counted_rebind_names(*args, **kwargs):
    fast_path_counts["rebind_names"] += 1
    return original_rebind_names(*args, **kwargs)


def counted_refresh_hotpath(*args, **kwargs):
    fast_path_counts["refresh_hotpath"] += 1
    return original_refresh_hotpath(*args, **kwargs)


def counted_rebuild_bindings(*args, **kwargs):
    fast_path_counts["rebuild_bindings"] += 1
    return original_rebuild_bindings(*args, **kwargs)


evaluator._armature_rest_signature = counted_rest_signature
evaluator._bone_map = counted_bone_map
evaluator.rebind_session_names = counted_rebind_names
session.refresh_hotpath_bindings = counted_refresh_hotpath
session.rebuild_bindings = counted_rebuild_bindings

foreign_scene = bpy.data.scenes.new("SPX rebind foreign scene")
foreign_scene.frame_set(93)
try:
    initial_revision = session.binding_revision
    initial_solver_identity = id(session.solver)
    initial_live_buffer = session.live_index_buffer
    for _index in range(4):
        assert not evaluator.refresh_session_bindings(root, armature)
    assert session.binding_revision == initial_revision
    assert session.live_index_buffer is initial_live_buffer
    assert solver.reset_calls == 0
    assert fast_path_counts == {
        "rest_signature": 0,
        "bone_map": 0,
        "refresh_hotpath": 0,
        "rebuild_bindings": 0,
        "rebind_names": 0,
    }

    previous_root_name = root.name
    rebinds_before_rename = fast_path_counts["rebind_names"]
    root.name = "SPX rebind root renamed"
    armature.name = "SPX rebind armature renamed"
    assert not evaluator.refresh_session_bindings(root, armature)
    assert fast_path_counts["rebind_names"] == rebinds_before_rename + 1
    assert fast_path_counts["rest_signature"] == 0
    assert fast_path_counts["bone_map"] == 0
    assert fast_path_counts["refresh_hotpath"] == 0
    assert fast_path_counts["rebuild_bindings"] == 0
    assert previous_root_name not in evaluator._SESSIONS
    assert evaluator._SESSIONS[root.name] is session
    assert session.binding_revision == initial_revision
    assert session.live_index_buffer is initial_live_buffer
    assert solver.reset_calls == 0
    assert id(session.solver) == initial_solver_identity

    original_desired = session._desired_output_matrices
    session._desired_output_matrices = lambda _pose_names=None: {
        "Bone": armature.pose.bones["Bone"].matrix.copy(),
    }
    with bpy.context.temp_override(
        scene=foreign_scene,
        view_layer=foreign_scene.view_layers[0],
    ):
        session._apply_output(
            armature,
            scene,
            update=True,
            sync_state=True,
        )
    session._desired_output_matrices = original_desired
    assert session.input_signature[:2] == (17, 0.0)
    assert session.output_signature[:2] == (17, 0.0)
    cross_scene_frame = session.input_signature[:2]

    old_armature = armature
    old_armature_name = old_armature.name
    bpy.data.objects.remove(old_armature, do_unlink=True)
    armature = create_armature(
        scene,
        old_armature_name,
        "SPX replacement armature data",
        2.0,
        (0.0, 0.0, 3.0),
    )
    armature.parent = root
    revision_before_identity = session.binding_revision
    preview_session._migrate_cached_names(root, armature, (), ())
    assert session.binding_revision == revision_before_identity + 1
    assert solver.reset_calls == 1
    assert solver.clear_calls == 1
    assert id(session.solver) == initial_solver_identity
    assert (
        session.mapping[0].as_pointer()
        == armature.pose.bones["Bone"].as_pointer()
    )
    assert (
        session.direct_live_bindings[0][1].as_pointer()
        == armature.pose.bones["Bone"].as_pointer()
    )
    assert abs(session.scale - 2.0) < 1.0e-6

    replacement_data = bpy.data.armatures.new("SPX same object replacement data")
    armature.data = replacement_data
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    replacement_bone = replacement_data.edit_bones.new("Bone")
    replacement_bone.head = (0.0, 0.0, 3.0)
    replacement_bone.tail = (0.0, 0.0, 4.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    revision_before_data = session.binding_revision
    preview_session._migrate_cached_names(root, armature, (), ())
    assert session.binding_revision == revision_before_data + 1
    assert solver.reset_calls == 2
    assert (
        session.mapping[0].as_pointer()
        == armature.pose.bones["Bone"].as_pointer()
    )
    assert abs(session.scale - 3.0) < 1.0e-6

    rest_signature_before = session.binding_rest_signature
    rest_inverse_before = session.direct_live_bindings[0][2].copy()
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    replacement_data.edit_bones["Bone"].tail = (1.0, 0.0, 4.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    revision_before_rest = session.binding_revision
    assert evaluator.refresh_session_bindings(
        root,
        armature,
        check_rest=True,
    )
    assert session.binding_revision == revision_before_rest + 1
    assert solver.reset_calls == 3
    assert session.binding_rest_signature != rest_signature_before
    assert session.direct_live_bindings[0][2] != rest_inverse_before

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    session.binding_mode = "EDIT"
    replacement_data.edit_bones["Bone"].tail = (-1.0, 0.0, 4.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    revision_before_depsgraph = session.binding_revision
    evaluate_calls = []
    original_evaluate_live = session.evaluate_live
    session.evaluate_live = lambda target_scene, update=True: evaluate_calls.append(
        (target_scene, update)
    )
    depsgraph = type(
        "FakeDepsgraph",
        (),
        {
            "updates": (
                type("FakeUpdate", (), {"id": replacement_data})(),
            ),
            "id_type_updated": lambda _self, id_type: id_type == "ARMATURE",
        },
    )()
    evaluator._depsgraph_update_post(scene, depsgraph)
    session.evaluate_live = original_evaluate_live
    assert session.binding_revision == revision_before_depsgraph + 1
    assert evaluate_calls == [(scene, False)]

    session.live_input_dirty = False
    session.live_input_frame = (17, 0.0)
    assert session.set_direct_input_isolated(True)
    assert session.direct_input_isolated
    assert session.live_input_dirty
    assert session.live_input_frame is None
    session.live_input_dirty = False
    assert not session.set_direct_input_isolated(True)
    assert not session.live_input_dirty
    assert session.set_direct_input_isolated(False)

    generated = armature.pose.bones["Bone"].constraints.new("COPY_LOCATION")
    generated.name = "mmd_generated_test"
    generated.mute = False
    assert session.has_blender_overrides()
    generated.mute = True
    assert not session.has_blender_overrides()

    print(
        "MMD_IK_EVALUATOR_REBIND_OK",
        f"binding_revision={session.binding_revision}",
        f"solver_resets={solver.reset_calls}",
        f"scale={session.scale:.6f}",
        f"scene_frame={cross_scene_frame}",
        "fast_noop_calls=4",
    )
finally:
    evaluator._armature_rest_signature = original_rest_signature
    evaluator._bone_map = original_bone_map
    evaluator.rebind_session_names = original_rebind_names
    session.refresh_hotpath_bindings = original_refresh_hotpath
    session.rebuild_bindings = original_rebuild_bindings
    evaluator._SESSIONS.clear()
    session.live = False
    session.close()
    bpy.data.scenes.remove(foreign_scene)
    for item in (root, armature):
        if item is not None and bpy.data.objects.get(item.name) is item:
            bpy.data.objects.remove(item, do_unlink=True)
