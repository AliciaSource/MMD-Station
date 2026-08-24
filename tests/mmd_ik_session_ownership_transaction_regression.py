import sys
import tempfile
from pathlib import Path

import bpy
from bpy.props import StringProperty


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator


class SentinelError(RuntimeError):
    pass


class FakeSolver:
    names = ("Bone",)
    rest_positions = ((0.0, 1.0, 0.0),)
    count = 1

    def __init__(self, *_args, **_kwargs):
        self.close_calls = 0
        self.reset_calls = 0
        self.clear_calls = 0

    def prepare_live_matrix_indices(self, indices):
        return tuple(indices)

    def close(self):
        self.close_calls += 1

    def reset(self):
        self.reset_calls += 1

    def clear_external_transforms(self):
        self.clear_calls += 1


def create_model(scene, root_name, armature_name, preview_id):
    root = bpy.data.objects.new(root_name, None)
    armature_data = bpy.data.armatures.new(f"{armature_name} data")
    armature = bpy.data.objects.new(armature_name, armature_data)
    build_scene = bpy.context.scene
    build_scene.collection.objects.link(root)
    build_scene.collection.objects.link(armature)
    root.mmd_type = "ROOT"
    root["spx_mmd_preview_id"] = preview_id
    armature.parent = root
    view_layer = bpy.context.view_layer
    view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = armature_data.edit_bones.new("Bone")
    bone.head = (0.0, 0.0, 1.0)
    bone.tail = (0.0, 0.0, 2.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    if scene is not build_scene:
        build_scene.collection.objects.unlink(armature)
        build_scene.collection.objects.unlink(root)
        scene.collection.objects.link(root)
        scene.collection.objects.link(armature)
        scene.view_layers[0].update()
    return root, armature


def remove_model(root, armature):
    armature_data = armature.data if armature is not None else None
    if armature is not None and bpy.data.objects.get(armature.name) is armature:
        bpy.data.objects.remove(armature, do_unlink=True)
    if root is not None and bpy.data.objects.get(root.name) is root:
        bpy.data.objects.remove(root, do_unlink=True)
    if armature_data is not None and armature_data.users == 0:
        bpy.data.armatures.remove(armature_data)


context_scene = bpy.context.scene
context_scene.frame_set(3)
owner_scene = bpy.data.scenes.new("SPX evaluator owner scene")
owner_scene.frame_set(47)
foreign_scene = bpy.data.scenes.new("SPX evaluator stale scene")
root = None
armature = None
stale_root = None
stale_armature = None
added_mmd_type = not hasattr(bpy.types.Object, "mmd_type")
if added_mmd_type:
    bpy.types.Object.mmd_type = StringProperty(default="NONE")

original_sessions = dict(evaluator._SESSIONS)
original_solver = evaluator.NativeBoneSolver
original_runtime_state = evaluator.runtime_state
original_canonical_armature = evaluator.canonical_armature
original_refresh_bindings = evaluator.refresh_bindings
original_evaluate_to = evaluator.Session.evaluate_to
original_evaluate_live = evaluator.Session.evaluate_live
solvers = []
current_armature = [None]


def solver_factory(*args, **kwargs):
    solver = FakeSolver(*args, **kwargs)
    solvers.append(solver)
    return solver


try:
    evaluator._SESSIONS.clear()
    root, armature = create_model(
        owner_scene,
        "SPX owned root",
        "SPX owned armature",
        42,
    )
    current_armature[0] = armature
    constraint = armature.pose.bones["Bone"].constraints.new("COPY_LOCATION")
    constraint.name = "mmd_transaction_constraint"
    constraint.mute = False
    evaluator.NativeBoneSolver = solver_factory
    evaluator.runtime_state = lambda _root: {
        "enabled": True,
        "action_input": False,
    }
    evaluator.canonical_armature = lambda _root, _state=None: current_armature[0]

    with tempfile.TemporaryDirectory(prefix="spx-evaluator-transaction-") as directory:
        pmx = Path(directory) / "model.pmx"
        vmd = Path(directory) / "motion.vmd"
        pmx.write_bytes(b"pmx")
        vmd.write_bytes(b"vmd")
        observed_scenes = []

        def fail_evaluate_to(session, scene):
            observed_scenes.append(scene)
            assert scene is owner_scene
            assert constraint.mute
            session.runtime_ref.pose.bones["Bone"].location.x = 2.0
            raise SentinelError("start evaluate")

        evaluator.Session.evaluate_to = fail_evaluate_to
        try:
            evaluator.start(root, pmx, vmd)
        except SentinelError as error:
            assert str(error) == "start evaluate"
        else:
            raise AssertionError("start() must propagate the evaluation failure")
        assert observed_scenes == [owner_scene]
        assert not evaluator._SESSIONS
        assert solvers[-1].close_calls == 1
        assert not constraint.mute
        assert abs(armature.pose.bones["Bone"].location.x) < 1.0e-7
        assert "spx_mmd_ik_source_pmx" not in root

        evaluator.Session.evaluate_to = lambda _session, scene: observed_scenes.append(
            scene
        )
        evaluator.start(root, pmx, vmd)
        start_session = evaluator._SESSIONS[root.name]
        assert observed_scenes[-1] is owner_scene
        assert start_session.scene_ref is owner_scene
        assert start_session.scene_name == owner_scene.name
        assert start_session.view_layer_name == owner_scene.view_layers[0].name
        evaluator.stop(root)
        assert not constraint.mute

        live_scenes = []

        def fail_evaluate_live(session, scene, update=True):
            live_scenes.append((scene, update))
            assert scene is owner_scene
            session.canonical_ref.pose.bones["Bone"].location.x = 3.0
            raise SentinelError("start live evaluate")

        evaluator.Session.evaluate_live = fail_evaluate_live
        try:
            evaluator.start_live(root, update=False)
        except SentinelError as error:
            assert str(error) == "start live evaluate"
        else:
            raise AssertionError("start_live() must propagate the evaluation failure")
        assert live_scenes == [(owner_scene, False)]
        assert not evaluator._SESSIONS
        assert solvers[-1].close_calls == 1
        assert abs(armature.pose.bones["Bone"].location.x) < 1.0e-7

        evaluator.Session.evaluate_live = (
            lambda _session, scene, update=True: live_scenes.append((scene, update))
        )
        evaluator.start_live(root, update=False)
        session = evaluator._SESSIONS[root.name]
        assert live_scenes[-1] == (owner_scene, False)
        assert session.scene_ref is owner_scene

        duplicate_root, duplicate_armature = create_model(
            owner_scene,
            "SPX duplicate preview root",
            "SPX duplicate preview armature",
            42,
        )
        assert evaluator._session_for_root(duplicate_root) is None
        remove_model(duplicate_root, duplicate_armature)

        root_name = root.name
        armature_name = armature.name
        remove_model(root, armature)
        root = None
        armature = None
        current_armature[0] = None

        stale_root, stale_armature = create_model(
            foreign_scene,
            root_name,
            armature_name,
            999,
        )
        assert evaluator._session_root(root_name, session) is None
        assert session.runtime_object() is None
        assert session.canonical_object() is None
        assert evaluator._session_for_root(stale_root) is None
        remove_model(stale_root, stale_armature)
        stale_root = None
        stale_armature = None

        root, armature = create_model(
            owner_scene,
            root_name,
            armature_name,
            42,
        )
        current_armature[0] = armature
        rebound_root, rebound_armature = evaluator._registered_session_objects(
            root_name,
            session,
        )
        assert rebound_root is None
        assert rebound_armature is None
        rebound_root, rebound_armature = evaluator._registered_session_objects(
            root_name,
            session,
            allow_recreated=True,
        )
        assert rebound_root is root
        assert rebound_armature is armature
        assert session.root_ref is root
        assert session.runtime_ref is armature
        assert session.canonical_ref is armature
        assert evaluator._session_for_root(root) is session
        assert session.binding_revision >= 2

        evaluator.stop(root)
        assert solvers[-1].close_calls == 1

        remove_model(root, armature)
        root = None
        armature = None
        root, armature = create_model(
            owner_scene,
            "SPX zero id root",
            "SPX zero id armature",
            0,
        )
        current_armature[0] = armature
        root["spx_mmd_ik_source_pmx"] = str(pmx)
        evaluator.start_live(root, update=False)
        orphan_session = evaluator._SESSIONS[root.name]
        orphan_solver = orphan_session.solver
        zero_root_name = root.name
        zero_armature_name = armature.name
        remove_model(root, armature)
        root = None
        armature = None
        root, armature = create_model(
            owner_scene,
            zero_root_name,
            zero_armature_name,
            0,
        )
        current_armature[0] = armature
        root["spx_mmd_ik_source_pmx"] = str(pmx)
        evaluator.refresh_bindings = lambda _root: None
        rebuilt = evaluator.rebuild_enabled_sessions()
        assert rebuilt == (root.name,)
        assert orphan_solver.close_calls == 1
        assert orphan_session not in evaluator._SESSIONS.values()
        replacement_session = evaluator._SESSIONS[root.name]
        assert replacement_session is not orphan_session
        evaluator.stop(root)
        assert replacement_session.solver.close_calls == 1

    assert bpy.context.scene is context_scene
    assert context_scene.frame_current == 3
    print(
        "MMD_IK_SESSION_OWNERSHIP_TRANSACTION_OK",
        f"owner_frame={owner_scene.frame_current}",
        f"context_frame={context_scene.frame_current}",
        f"solver_instances={len(solvers)}",
        "stale_rejected=1",
        "undo_rebound=1",
        "zero_id_collision_closed=1",
    )
finally:
    evaluator.NativeBoneSolver = original_solver
    evaluator.runtime_state = original_runtime_state
    evaluator.canonical_armature = original_canonical_armature
    evaluator.refresh_bindings = original_refresh_bindings
    evaluator.Session.evaluate_to = original_evaluate_to
    evaluator.Session.evaluate_live = original_evaluate_live
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)
    remove_model(stale_root, stale_armature)
    remove_model(root, armature)
    for scene in (owner_scene, foreign_scene):
        if bpy.data.scenes.get(scene.name) is scene:
            bpy.data.scenes.remove(scene)
    if added_mmd_type and hasattr(bpy.types.Object, "mmd_type"):
        del bpy.types.Object.mmd_type
