import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from bpy.props import StringProperty


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator


class RecordedDepsgraph:
    def __init__(self, updated_ids, *updated_types):
        self.updates = tuple(SimpleNamespace(id=item) for item in updated_ids)
        self.updated_types = frozenset(updated_types)

    def id_type_updated(self, id_type):
        return id_type in self.updated_types


class FakeSession:
    def __init__(self, root, canonical, scene):
        self.root_ref = root
        self.root_name = root.name
        self.root_preview_id = evaluator._root_preview_id(root)
        self.root_pointer = evaluator._rna_pointer(root)
        self.runtime_ref = canonical
        self.runtime_name = canonical.name
        self.canonical_ref = canonical
        self.canonical_name = canonical.name
        self.scene_ref = scene
        self.scene_name = scene.name
        self.scene_pointer = evaluator._rna_pointer(scene)
        self.view_layer_name = scene.view_layers[0].name
        self.binding_object_pointer = evaluator._rna_pointer(canonical)
        self.binding_data_pointer = evaluator._rna_pointer(canonical.data)
        self.binding_rest_signature = evaluator._armature_rest_signature(canonical)
        self.binding_revision = 1
        self.binding_mode = canonical.mode
        self.identity_validated = False
        self.mapping = (canonical.pose.bones["Bone"],)
        self.live = True
        self.updating = False
        self.suspended = False
        self.input_signature = evaluator._live_input_signature(canonical, scene)
        self.action_identity = evaluator._action_identity(canonical)
        self.action_signature = evaluator._action_frame_signature(
            canonical,
            scene.frame_current,
        )
        self.rebuild_calls = 0
        self.evaluate_calls = 0
        self.repair_calls = 0
        self.close_calls = []

    def canonical_object(self):
        return evaluator._live_object(self.canonical_ref)

    def runtime_object(self):
        return evaluator._live_object(self.runtime_ref)

    def rebuild_bindings(self, canonical, rest_signature=None):
        pose_bone = canonical.pose.bones.get("Bone")
        if pose_bone is None:
            return False
        self.rebuild_calls += 1
        self.binding_revision += 1
        self.binding_object_pointer = evaluator._rna_pointer(canonical)
        self.binding_data_pointer = evaluator._rna_pointer(canonical.data)
        self.binding_rest_signature = (
            rest_signature
            if rest_signature is not None
            else evaluator._armature_rest_signature(canonical)
        )
        self.mapping = (pose_bone,)
        return True

    def evaluate_live(self, _scene, update=True):
        self.evaluate_calls += 1

    def repair_current_action_keys(self, _canonical, _frame):
        self.repair_calls += 1

    def close(self, restore=True):
        self.close_calls.append(bool(restore))
        self.live = False


scene = bpy.context.scene
created_objects = []
created_armatures = []
created_scenes = []
original_sessions = dict(evaluator._SESSIONS)
added_mmd_type = not hasattr(bpy.types.Object, "mmd_type")
if added_mmd_type:
    bpy.types.Object.mmd_type = StringProperty(default="NONE")


def create_model(stem, preview_id):
    root = bpy.data.objects.new(f"{stem} root", None)
    scene.collection.objects.link(root)
    root.mmd_type = "ROOT"
    created_objects.append(root)

    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.object.armature_add()
    canonical = bpy.context.object
    canonical.name = f"{stem} armature"
    canonical.data.name = f"{stem} armature data"
    canonical.parent = root
    created_objects.append(canonical)
    created_armatures.append(canonical.data)

    root["spx_mmd_preview_id"] = preview_id
    bpy.context.view_layer.objects.active = None
    canonical.select_set(False)
    bpy.context.view_layer.update()
    return root, canonical


def register_session(root, canonical, owner_scene=scene):
    session = FakeSession(root, canonical, owner_scene)
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS[root.name] = session
    return session


def cleanup_session():
    evaluator._SESSIONS.clear()


def cleanup_fixture():
    bpy.context.view_layer.objects.active = None
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except RuntimeError:
        pass
    for obj in reversed(created_objects):
        try:
            if bpy.data.objects.get(obj.name) is obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
    created_objects.clear()
    for armature in reversed(created_armatures):
        try:
            if bpy.data.armatures.get(armature.name) is armature and armature.users == 0:
                bpy.data.armatures.remove(armature)
        except ReferenceError:
            pass
    created_armatures.clear()
    for item in reversed(created_scenes):
        try:
            if bpy.data.scenes.get(item.name) is item:
                bpy.data.scenes.remove(item)
        except ReferenceError:
            pass
    created_scenes.clear()


def case_canonical_data_replacement():
    root, canonical = create_model("SPX identity data", 301)
    session = register_session(root, canonical)
    old_pose_pointer = session.mapping[0].as_pointer()
    replacement_data = canonical.data.copy()
    replacement_data.name = "SPX identity replacement armature data"
    created_armatures.append(replacement_data)
    canonical.data = replacement_data
    bpy.context.view_layer.update()

    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph(
            (canonical, replacement_data),
            "OBJECT",
            "ARMATURE",
        ),
    )

    assert session.rebuild_calls == 1, (
        "Object Mode canonical.data replacement did not rebuild bindings: "
        f"rebuild_calls={session.rebuild_calls}"
    )
    assert session.binding_data_pointer == evaluator._rna_pointer(replacement_data), (
        "Binding data pointer was not refreshed after canonical.data replacement"
    )
    assert session.mapping[0].as_pointer() == canonical.pose.bones["Bone"].as_pointer(), (
        "Mapping does not reference the replacement Armature PoseBone: "
        f"old={old_pose_pointer}, mapped={session.mapping[0].as_pointer()}, "
        f"current={canonical.pose.bones['Bone'].as_pointer()}"
    )


def case_incompatible_canonical_data_replacement():
    root, canonical = create_model("SPX identity incompatible data", 351)
    session = register_session(root, canonical)
    replacement_data = bpy.data.armatures.new(
        "SPX identity incompatible armature data"
    )
    created_armatures.append(replacement_data)
    canonical.data = replacement_data
    bpy.context.view_layer.update()

    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph(
            (canonical, replacement_data),
            "OBJECT",
            "ARMATURE",
        ),
    )

    assert session.rebuild_calls == 0
    assert session.close_calls == [False], (
        "Incompatible canonical.data replacement did not fail closed: "
        f"close_calls={session.close_calls}"
    )
    assert session not in evaluator._SESSIONS.values()


def case_preview_token_change():
    root, canonical = create_model("SPX identity token", 401)
    session = register_session(root, canonical)
    root["spx_mmd_preview_id"] = 402

    evaluator._depsgraph_update_post(
        scene,
        RecordedDepsgraph((root,), "OBJECT"),
    )

    assert session.close_calls == [False], (
        "Changed root preview token was adopted instead of invalidating the session: "
        f"close_calls={session.close_calls}, stored_token={session.root_preview_id}"
    )
    assert session not in evaluator._SESSIONS.values()


def case_unique_scene_migration():
    root, canonical = create_model("SPX identity scene", 501)
    session = register_session(root, canonical)
    owner_scene = session.scene_ref
    destination = bpy.data.scenes.new("SPX identity destination scene")
    created_scenes.append(destination)

    for collection in tuple(canonical.users_collection):
        collection.objects.unlink(canonical)
    for collection in tuple(root.users_collection):
        collection.objects.unlink(root)
    destination.collection.objects.link(root)
    destination.collection.objects.link(canonical)

    evaluator._depsgraph_update_post(
        destination,
        RecordedDepsgraph(
            (root, canonical, owner_scene, destination),
            "OBJECT",
            "COLLECTION",
            "SCENE",
        ),
    )

    assert session.close_calls == [False], (
        "Unique Scene migration was adopted instead of invalidating the session: "
        f"close_calls={session.close_calls}, owner={session.scene_name}"
    )
    assert session.scene_ref is owner_scene
    assert session not in evaluator._SESSIONS.values()


failures = []
try:
    for case in (
        case_canonical_data_replacement,
        case_incompatible_canonical_data_replacement,
        case_preview_token_change,
        case_unique_scene_migration,
    ):
        try:
            case()
            print(f"PASS {case.__name__}")
        except Exception as error:
            failures.append((case.__name__, error))
            print(f"FAIL {case.__name__}: {type(error).__name__}: {error}")
        finally:
            cleanup_session()
            cleanup_fixture()

    if failures:
        raise AssertionError(
            "MMD IK identity invalidation failures:\n"
            + "\n".join(
                f"- {name}: {type(error).__name__}: {error}"
                for name, error in failures
            )
        )

    print(
        "MMD_IK_IDENTITY_INVALIDATION_OK",
        "canonical_data_rebound=1",
        "incompatible_data_rejected=1",
        "preview_token_rejected=1",
        "scene_migration_rejected=1",
    )
finally:
    evaluator._SESSIONS.clear()
    cleanup_fixture()
    evaluator._SESSIONS.update(original_sessions)
    if added_mmd_type and hasattr(bpy.types.Object, "mmd_type"):
        del bpy.types.Object.mmd_type
