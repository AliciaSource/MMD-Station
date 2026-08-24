import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import display_rig, runtime


scene = bpy.context.scene
healthy_owner = "spx-display-healthy-owner"
created = []


class FailingDisplayRig:
    def __init__(self, owner_token, *, fail_apply=False):
        self.owner_token = owner_token
        self.fail_apply = fail_apply

    def apply_input_pose(self):
        if self.fail_apply:
            raise RuntimeError("injected DisplayRig activation failure")

    def close(self):
        raise RuntimeError("injected DisplayRig close failure")


class PoseInputStub:
    def invalidate(self):
        pass

    def refresh_watch_bindings(self):
        pass


def create_owner(owner_token, label):
    source_token = f"{owner_token}-source"
    source_mesh = bpy.data.meshes.new(f"SPX {label} source data")
    source = bpy.data.objects.new(f"SPX {label} source", source_mesh)
    scene.collection.objects.link(source)
    source.hide_viewport = True
    source[display_rig._SOURCE_OWNER_KEY] = owner_token
    source[display_rig._SOURCE_TOKEN_KEY] = source_token
    source[display_rig._SOURCE_HIDE_VIEWPORT_KEY] = False

    output_mesh = bpy.data.meshes.new(f"SPX {label} output data")
    output = bpy.data.objects.new(f"SPX {label} output", output_mesh)
    scene.collection.objects.link(output)
    output[display_rig._RUNTIME_MARKER] = owner_token
    output[display_rig._RUNTIME_KIND_KEY] = "output"
    output[display_rig._SOURCE_OBJECT_KEY] = source.name
    output[display_rig._SOURCE_TOKEN_KEY] = source_token
    output[display_rig._SOURCE_HIDE_VIEWPORT_KEY] = False
    output_mesh[display_rig._RUNTIME_MARKER] = owner_token
    created.append((source, source_mesh, output, output_mesh))
    return source, output


def assert_healthy(source, output):
    assert bpy.data.objects.get(source.name) is source
    assert bpy.data.objects.get(output.name) is output
    assert source.hide_viewport
    assert source.get(display_rig._SOURCE_OWNER_KEY, "") == healthy_owner
    assert output.get(display_rig._RUNTIME_MARKER, "") == healthy_owner


def session_stub(display):
    armature = SimpleNamespace(
        data=SimpleNamespace(bones={}),
        update_tag=lambda **_kwargs: None,
    )
    return SimpleNamespace(
        isolated_output_active=False,
        display_rig_unavailable=False,
        display_rig=display,
        debug_batch=None,
        saved_basis={},
        driver_pose_bones={},
        saved_bone_connections={},
        canonical_output_dirty=False,
        pose_input=PoseInputStub(),
        armature=armature,
        _display_rig_valid_cache=True,
        _direct_pose_bones_cache=(),
        _capture_driver_basis=lambda: {},
        _deactivate_debug_batch=lambda: False,
        set_bone_connections=lambda _values: None,
        update_view_layer=lambda: None,
    )


def fail_session_close(restore=False):
    raise RuntimeError("injected terminal session failure")


healthy_source = None
healthy_output = None
original_plan = runtime.PreviewDisplayRig.__dict__["plan"]
original_create = runtime.PreviewDisplayRig.__dict__["create"]
original_print_exc = runtime.traceback.print_exc

try:
    healthy_source, healthy_output = create_owner(healthy_owner, "healthy")
    assert display_rig.cleanup_display_rig("") is False

    activation_owner = "spx-display-failed-activation"
    activation_source, activation_output = create_owner(
        activation_owner,
        "failed activation",
    )
    activation_rig = FailingDisplayRig(activation_owner, fail_apply=True)
    activation_session = session_stub(None)
    activation_output_name = activation_output.name
    runtime.PreviewDisplayRig.plan = classmethod(
        lambda _cls, _session: object()
    )
    runtime.PreviewDisplayRig.create = classmethod(
        lambda _cls, _session, _plan=None: activation_rig
    )
    runtime.traceback.print_exc = lambda: None
    assert runtime.PreviewSession._activate_display_rig(activation_session)
    assert bpy.data.objects.get(activation_output_name) is None
    assert not activation_source.hide_viewport
    assert_healthy(healthy_source, healthy_output)

    deactivation_owner = "spx-display-failed-deactivation"
    deactivation_source, deactivation_output = create_owner(
        deactivation_owner,
        "failed deactivation",
    )
    deactivation_session = session_stub(FailingDisplayRig(deactivation_owner))
    deactivation_output_name = deactivation_output.name
    assert runtime.PreviewSession._deactivate_display_rig(deactivation_session)
    assert bpy.data.objects.get(deactivation_output_name) is None
    assert not deactivation_source.hide_viewport
    assert_healthy(healthy_source, healthy_output)

    discard_owner = "spx-display-failed-discard"
    discard_source, discard_output = create_owner(
        discard_owner,
        "failed discard",
    )
    discard_session = SimpleNamespace(
        world=None,
        display_rig=FailingDisplayRig(discard_owner),
        debug_batch=None,
        close=fail_session_close,
    )
    discard_output_name = discard_output.name
    runtime._discard_unbound_session(discard_session)
    assert bpy.data.objects.get(discard_output_name) is None
    assert not discard_source.hide_viewport
    assert_healthy(healthy_source, healthy_output)

    print(
        "DISPLAY_RIG_FAILURE_ISOLATION_OK",
        "activation_scoped=1",
        "deactivation_scoped=1",
        "terminal_discard_scoped=1",
        "healthy_owner_preserved=1",
    )
finally:
    runtime.PreviewDisplayRig.plan = original_plan
    runtime.PreviewDisplayRig.create = original_create
    runtime.traceback.print_exc = original_print_exc
    for owner_token in (
        "spx-display-failed-activation",
        "spx-display-failed-deactivation",
        "spx-display-failed-discard",
        healthy_owner,
    ):
        try:
            display_rig.cleanup_display_rig(owner_token)
        except Exception:
            pass
    for source, source_mesh, output, output_mesh in reversed(created):
        for obj in (output, source):
            try:
                if bpy.data.objects.get(obj.name) is obj:
                    bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
        for mesh in (output_mesh, source_mesh):
            try:
                if bpy.data.meshes.get(mesh.name) is mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            except ReferenceError:
                pass
