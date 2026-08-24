import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.physics_preview import runtime as preview_runtime


class FakeDepsgraph:
    def __init__(self, *updated_types):
        self.updated_types = frozenset(updated_types)

    def id_type_updated(self, id_type):
        return id_type in self.updated_types


class RecordedDepsgraph(FakeDepsgraph):
    def __init__(self, updated_ids, *updated_types):
        super().__init__(*updated_types)
        self.updates = tuple(SimpleNamespace(id=item) for item in updated_ids)


class FakeSession:
    def __init__(self, root, canonical, scene):
        self.root_name = root.name
        self.runtime_name = canonical.name
        self.canonical_name = canonical.name
        self.root_ref = root
        self.runtime_ref = canonical
        self.canonical_ref = canonical
        self.root_preview_id = evaluator._root_preview_id(root)
        self.root_pointer = evaluator._rna_pointer(root)
        self.scene_name = scene.name
        self.scene_ref = scene
        self.scene_pointer = evaluator._rna_pointer(scene)
        self.binding_object_pointer = evaluator._rna_pointer(canonical)
        self.binding_data_pointer = evaluator._rna_pointer(canonical.data)
        self.identity_validated = False
        self.binding_mode = canonical.mode
        self.live = True
        self.updating = False
        self.suspended = False
        self.input_signature = (
            int(scene.frame_current),
            float(scene.frame_subframe),
            0,
        )
        self.action_signature = ()
        self.action_identity = 0
        self.action_input = False
        self.source_vmd = False
        self.output_basis = {}
        self.input_basis = {}
        self.pose_override = False
        self.live_input_dirty = False
        self.pending_input_signature = ()
        self.direct_input_isolated = False
        self.partial_input_basis = False
        self.blender_override_cache = None
        self.blender_override_modal_active = False
        self.bone_indices = {"SPX": 0}
        self.capture_signatures = []
        self.capture_direct_inputs = []
        self.evaluate_calls = 0
        self.repair_calls = 0
        self.close_calls = 0

    def canonical_object(self):
        return evaluator._live_object(self.canonical_ref)

    def runtime_object(self):
        return evaluator._live_object(self.runtime_ref)

    def _capture_external_pose(
        self,
        canonical,
        scene,
        known_signature=None,
        direct_input=False,
        basis_updates=None,
    ):
        self.capture_signatures.append(known_signature)
        self.capture_direct_inputs.append(direct_input)
        return evaluator.Session._capture_external_pose(
            self,
            canonical,
            scene,
            known_signature=known_signature,
            direct_input=direct_input,
            basis_updates=basis_updates,
        )

    def evaluate_live(self, _scene, update=True):
        self.evaluate_calls += 1

    def repair_current_action_keys(self, canonical, frame):
        self.repair_calls += 1
        return evaluator.Session.repair_current_action_keys(
            self,
            canonical,
            frame,
        )

    def close(self, restore=True):
        self.close_calls += 1


class FakeLiveSolver:
    def __init__(self):
        self.begin_calls = 0
        self.legacy_calls = []
        self.flat_calls = []

    def begin_live_input(self):
        self.begin_calls += 1

    def set_live_matrices(self, entries):
        self.legacy_calls.append(tuple(entries))

    def set_live_matrix_buffers(self, prepared_indices, positions, bases):
        self.flat_calls.append((prepared_indices, positions, bases))


scene = bpy.context.scene
root = bpy.data.objects.new("SPX depsgraph gate root", None)
canonical_data = bpy.data.armatures.new("SPX depsgraph gate armature data")
canonical = bpy.data.objects.new("SPX depsgraph gate armature", canonical_data)
scene.collection.objects.link(root)
scene.collection.objects.link(canonical)
bpy.context.view_layer.objects.active = canonical
canonical.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
edit_bone = canonical_data.edit_bones.new("SPX")
edit_bone.head = (0.0, 0.0, 0.0)
edit_bone.tail = (0.0, 0.0, 1.0)
bpy.ops.object.mode_set(mode="OBJECT")
canonical.select_set(False)
session = FakeSession(root, canonical, scene)

original_sessions = dict(evaluator._SESSIONS)
original_live_signature = evaluator._live_input_signature
original_action_signature = evaluator._action_frame_signature
original_rebind = evaluator.rebind_session_names
original_model_armature = evaluator._model_armature
original_set_action_input = evaluator.set_action_input
original_transform_modal_pose = evaluator._transform_modal_pose_matrices
original_is_running = preview_runtime.is_running
signature_value = [session.input_signature]
signature_calls = []
action_signature_calls = []
rebind_calls = []
action_input_calls = []
action = None
foreign_armature = None
foreign_data = None


def tracked_live_signature(_canonical, _scene):
    signature_calls.append(signature_value[0])
    return signature_value[0]


def tracked_action_signature(target, frame):
    action_signature_calls.append((target, frame))
    return original_action_signature(target, frame)


def tracked_rebind(*args, **kwargs):
    rebind_calls.append((args, kwargs))
    return original_rebind(*args, **kwargs)


try:
    assert evaluator._depsgraph_type_updated(SimpleNamespace(updates=()), "OBJECT")
    assert not evaluator._depsgraph_id_updated(
        SimpleNamespace(updates=None),
        canonical,
    )
    evaluated_id = SimpleNamespace(original=canonical, as_pointer=lambda: 0)
    assert evaluator._depsgraph_id_updated(
        SimpleNamespace(updates=(SimpleNamespace(id=evaluated_id),)),
        canonical,
    )
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS[root.name] = session
    evaluator._live_input_signature = tracked_live_signature
    evaluator._action_frame_signature = tracked_action_signature
    evaluator.rebind_session_names = tracked_rebind
    evaluator._model_armature = lambda candidate: (
        canonical if candidate is root else None
    )
    evaluator.set_action_input = lambda target, enabled: action_input_calls.append(
        (target, enabled)
    )
    preview_runtime.is_running = lambda _root: True

    evaluator._depsgraph_update_post(scene, FakeDepsgraph("OBJECT"))
    assert not signature_calls
    assert not action_signature_calls
    assert not session.capture_signatures
    assert not rebind_calls

    foreign_data = bpy.data.armatures.new("SPX foreign armature data")
    foreign_armature = bpy.data.objects.new("SPX foreign armature", foreign_data)
    scene.collection.objects.link(foreign_armature)
    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph(
            (foreign_armature, foreign_data),
            "OBJECT",
            "ARMATURE",
        ),
    )
    assert not signature_calls
    assert not action_signature_calls
    assert not session.capture_signatures
    assert not rebind_calls

    signature_value[0] = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        1,
    )
    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph(
            (canonical,),
            "OBJECT",
        ),
    )
    assert signature_calls == [signature_value[0]]
    assert not action_signature_calls
    assert session.capture_signatures == [signature_value[0]]
    assert session.capture_direct_inputs == [False]
    assert session.input_signature == signature_value[0]
    assert not rebind_calls

    signature_value[0] = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        101,
    )
    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph(
            (canonical.data,),
            "ARMATURE",
        ),
    )
    assert signature_calls[-1] == signature_value[0]
    assert session.capture_signatures[-1] == signature_value[0]
    assert session.input_signature == signature_value[0]

    canonical.animation_data_create()
    action = bpy.data.actions.new("SPX depsgraph gate action")
    curve = action.fcurves.new(
        data_path='pose.bones["SPX"].location',
        index=0,
    )
    point = curve.keyframe_points.insert(scene.frame_current, 1.0)
    canonical.animation_data.action = action
    session.action_identity = evaluator._action_identity(canonical)
    session.action_signature = original_action_signature(
        canonical,
        scene.frame_current,
    )
    point.co.y = 2.0
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("ACTION"))
    assert session.repair_calls == 1
    assert session.action_input
    assert action_input_calls[-1] == (root, True)

    previous_repair_calls = session.repair_calls
    canonical.animation_data.action = None
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("OBJECT"))
    assert session.repair_calls == previous_repair_calls + 1
    assert session.action_identity == 0
    assert session.action_signature == ()

    session.direct_input_isolated = True
    session.input_basis = {
        "SPX": canonical.pose.bones["SPX"].matrix_basis.copy(),
        "sentinel": Matrix.Translation((7.0, 0.0, 0.0)),
    }
    signature_calls.clear()
    session.capture_signatures.clear()
    session.capture_direct_inputs.clear()
    pose_bone = canonical.pose.bones["SPX"]
    pose_bone.location.x = 0.125
    evaluator._transform_modal_pose_matrices = lambda _canonical: {
        "SPX": pose_bone.matrix_basis.copy()
    }
    signature_value[0] = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        2,
    )
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("ARMATURE"))
    assert signature_calls == [signature_value[0]]
    assert session.capture_signatures == [signature_value[0]]
    assert session.capture_direct_inputs == [True]
    assert session.pending_input_signature == signature_value[0]
    assert session.partial_input_basis
    assert "sentinel" in session.input_basis
    captured_basis = session.input_basis["SPX"].copy()
    evaluator.Session._refresh_live_frame_input(
        session,
        canonical,
        scene,
        direct_input=True,
    )
    assert signature_calls == [signature_value[0]]
    assert session.pending_input_signature == ()
    assert session.input_basis["SPX"] == captured_basis
    evaluator._transform_modal_pose_matrices = lambda _canonical: {}
    session.live_input_dirty = False
    session.pose_override = False
    session.pending_input_signature = ("stale",)
    pose_bone.location.x = 0.25
    signature_value[0] = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        3,
    )
    evaluator.Session.reconcile_input_basis(
        session,
        canonical,
        scene,
        signature=signature_value[0],
    )
    assert not session.partial_input_basis
    assert "sentinel" not in session.input_basis
    assert session.input_signature == signature_value[0]
    assert session.pending_input_signature == ()
    assert session.live_input_dirty
    assert session.pose_override

    session.input_basis["sentinel"] = Matrix.Translation((9.0, 0.0, 0.0))
    pose_bone.location.x = 0.375
    provided_basis = pose_bone.matrix_basis.copy()
    signature_value[0] = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        4,
    )
    evaluator._transform_modal_pose_matrices = lambda _canonical: (_ for _ in ()).throw(
        AssertionError("cached modal basis was not reused")
    )
    evaluator.Session._refresh_live_frame_input(
        session,
        canonical,
        scene,
        direct_input=True,
        basis_updates={"SPX": provided_basis},
    )
    assert session.partial_input_basis
    assert session.input_basis["SPX"] == provided_basis
    assert "sentinel" in session.input_basis

    session.blender_override_cache = None
    assert not evaluator.Session.has_blender_overrides(
        session,
        use_cache=False,
    )
    constraint = pose_bone.constraints.new("COPY_LOCATION")
    try:
        assert evaluator.Session.has_blender_overrides(
            session,
            use_cache=True,
        )
        pose_bone.constraints.remove(constraint)
        constraint = None
        assert evaluator.Session.has_blender_overrides(
            session,
            use_cache=True,
        )
    finally:
        if constraint is not None:
            pose_bone.constraints.remove(constraint)
    assert not evaluator.Session.has_blender_overrides(
        session,
        use_cache=False,
    )
    assert not session.blender_override_modal_active

    sentinel = object()
    output_basis = {"sentinel": sentinel}
    session.output_basis = output_basis
    session.output_signature = ()
    action_signature_calls.clear()
    assert evaluator.Session.sync_output_pose(
        session,
        canonical,
        scene,
        known_signature=signature_value[0],
        direct_input=True,
    )
    assert session.output_basis is output_basis
    assert session.output_basis == {"sentinel": sentinel}
    assert not action_signature_calls

    fallback_signature = (
        int(scene.frame_current),
        float(scene.frame_subframe),
        5,
    )
    assert evaluator.Session.sync_output_pose(
        session,
        canonical,
        scene,
        known_signature=fallback_signature,
        direct_input=False,
    )
    assert set(session.output_basis) == {"SPX"}
    assert len(action_signature_calls) == 1
    session.direct_input_isolated = False
    session.pending_input_signature = ()

    live_solver = FakeLiveSolver()
    live_session = type("FakeLiveSession", (), {})()
    live_session.live_input_dirty = True
    live_session.live_input_frame = None
    live_session.input_basis = {"SPX": pose_bone.matrix_basis.copy()}
    live_session.mapped_order = ((0, pose_bone),)
    live_session.live_bindings = ((0, "SPX", Matrix.Identity(4)),)
    live_session.direct_live_bindings = ((0, pose_bone, Matrix.Identity(4)),)
    live_session.live_index_buffer = object()
    live_session.direct_input_isolated = False
    live_session.scale = 1.0
    live_session.solver = live_solver
    raw_pose_calls = []
    original_raw_pose_matrices = evaluator._raw_pose_matrices

    def tracked_raw_pose_matrices(*args, **kwargs):
        raw_pose_calls.append((args, kwargs))
        return original_raw_pose_matrices(*args, **kwargs)

    evaluator._raw_pose_matrices = tracked_raw_pose_matrices
    try:
        assert evaluator._submit_live_pose(
            live_session,
            canonical,
            scene,
            direct_input=False,
        )
        live_session.live_input_dirty = True
        live_session.live_input_frame = None
        assert evaluator._submit_live_pose(
            live_session,
            canonical,
            scene,
            direct_input=True,
        )
        live_session.live_input_dirty = True
        live_session.live_input_frame = None
        live_session.direct_input_isolated = True
        assert evaluator._submit_live_pose(
            live_session,
            canonical,
            scene,
            direct_input=True,
        )
        assert not live_session.live_input_dirty
        assert evaluator.Session.set_direct_input_isolated(
            live_session,
            False,
        )
        assert live_session.live_input_dirty
        assert evaluator._submit_live_pose(
            live_session,
            canonical,
            scene,
            direct_input=False,
        )
    finally:
        evaluator._raw_pose_matrices = original_raw_pose_matrices
    assert len(raw_pose_calls) == 3
    assert len(live_solver.legacy_calls) == 3
    assert len(live_solver.flat_calls) == 1
    assert live_solver.begin_calls == 4
    flat_prepared, flat_positions, flat_bases = live_solver.flat_calls[0]
    assert flat_prepared is live_session.live_index_buffer
    assert len(flat_positions) == 3
    assert len(flat_bases) == 9

    signature_calls.clear()
    previous_root_name = root.name
    root.name = f"{previous_root_name} renamed"
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("OBJECT"))
    assert evaluator._SESSIONS.get(root.name) is session
    assert previous_root_name not in evaluator._SESSIONS
    assert session.root_name == root.name
    assert rebind_calls
    assert not signature_calls

    signature_calls.clear()
    previous_rebind_count = len(rebind_calls)
    canonical.name = f"{canonical.name} renamed"
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("OBJECT"))
    assert session.canonical_name == canonical.name
    assert session.runtime_name == canonical.name
    assert len(rebind_calls) == previous_rebind_count + 1
    assert not signature_calls

    bpy.data.objects.remove(canonical, do_unlink=True)
    canonical = None
    evaluator._depsgraph_update_post(scene, FakeDepsgraph("OBJECT"))
    assert session.close_calls == 1
    assert session not in evaluator._SESSIONS.values()

    print(
        "MMD_IK_DEPSGRAPH_GATE_REGRESSION_OK",
        f"signature_calls={len(signature_calls)}",
        f"action_signature_calls={len(action_signature_calls)}",
        f"capture_calls={len(session.capture_signatures)}",
        f"repair_calls={session.repair_calls}",
        f"rebind_calls={len(rebind_calls)}",
        f"close_calls={session.close_calls}",
        f"legacy_live_calls={len(live_solver.legacy_calls)}",
        f"flat_live_calls={len(live_solver.flat_calls)}",
    )
finally:
    evaluator._live_input_signature = original_live_signature
    evaluator._action_frame_signature = original_action_signature
    evaluator.rebind_session_names = original_rebind
    evaluator._model_armature = original_model_armature
    evaluator.set_action_input = original_set_action_input
    evaluator._transform_modal_pose_matrices = original_transform_modal_pose
    preview_runtime.is_running = original_is_running
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)
    if canonical is not None and bpy.data.objects.get(canonical.name) is canonical:
        bpy.data.objects.remove(canonical, do_unlink=True)
    if (
        foreign_armature is not None
        and bpy.data.objects.get(foreign_armature.name) is foreign_armature
    ):
        bpy.data.objects.remove(foreign_armature, do_unlink=True)
    if bpy.data.objects.get(root.name) is root:
        bpy.data.objects.remove(root, do_unlink=True)
    if action is not None and action.users == 0:
        bpy.data.actions.remove(action)
    if canonical_data.users == 0:
        bpy.data.armatures.remove(canonical_data)
    if foreign_data is not None and foreign_data.users == 0:
        bpy.data.armatures.remove(foreign_data)
