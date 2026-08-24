import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import display_rig


scene = bpy.context.scene
owner_token = "spx-tokenless-cleanup-owner"
foreign = None
output = None
reowned = None

try:
    foreign_mesh = bpy.data.meshes.new("SPX tokenless foreign mesh data")
    foreign = bpy.data.objects.new("SPX tokenless foreign mesh", foreign_mesh)
    scene.collection.objects.link(foreign)
    foreign.hide_viewport = True

    output_mesh = bpy.data.meshes.new("SPX tokenless output mesh data")
    output = bpy.data.objects.new("SPX tokenless stale output", output_mesh)
    scene.collection.objects.link(output)
    output[display_rig._RUNTIME_MARKER] = owner_token
    output[display_rig._RUNTIME_KIND_KEY] = "output"
    output[display_rig._SOURCE_OBJECT_KEY] = foreign.name
    output[display_rig._SOURCE_HIDE_VIEWPORT_KEY] = False

    display_rig._cleanup_owner(owner_token)
    assert bpy.data.objects.get(foreign.name) is foreign
    assert foreign.hide_viewport
    assert bpy.data.objects.get("SPX tokenless stale output") is None

    reowned_mesh = bpy.data.meshes.new("SPX reowned source mesh data")
    reowned = bpy.data.objects.new("SPX reowned source mesh", reowned_mesh)
    scene.collection.objects.link(reowned)
    reowned.hide_viewport = True
    reowned[display_rig._SOURCE_OWNER_KEY] = "spx-new-display-owner"
    reowned[display_rig._SOURCE_TOKEN_KEY] = "spx-new-source-token"
    reowned[display_rig._SOURCE_HIDE_VIEWPORT_KEY] = True
    binding = display_rig.DisplayMeshBinding(
        reowned,
        reowned.name,
        "spx-old-source-token",
        None,
        (scene.collection,),
        display_rig._mesh_topology_signature(reowned.data),
        False,
    )
    stale = display_rig.PreviewDisplayRig.__new__(
        display_rig.PreviewDisplayRig
    )
    stale.mesh_bindings = (binding,)
    stale.owner_token = "spx-old-display-owner"
    stale.closed = False
    stale.close()
    assert stale.closed
    assert reowned.hide_viewport
    assert (
        reowned.get(display_rig._SOURCE_OWNER_KEY, "")
        == "spx-new-display-owner"
    )
    assert (
        reowned.get(display_rig._SOURCE_TOKEN_KEY, "")
        == "spx-new-source-token"
    )
    assert bool(reowned.get(display_rig._SOURCE_HIDE_VIEWPORT_KEY, False))
    assert display_rig._restore_source(
        reowned,
        False,
        "spx-new-display-owner",
        "spx-new-source-token",
    )
    assert not reowned.hide_viewport
    assert display_rig._SOURCE_OWNER_KEY not in reowned
    assert display_rig._SOURCE_TOKEN_KEY not in reowned
    assert display_rig._SOURCE_HIDE_VIEWPORT_KEY not in reowned

    print(
        "DISPLAY_RIG_IDENTITY_CLEANUP_OK",
        "tokenless_foreign_untouched=1",
        "reowned_source_untouched=1",
        "owned_source_restored=1",
        "stale_output_removed=1",
    )
finally:
    for obj in (output, foreign, reowned):
        if obj is None:
            continue
        try:
            data = obj.data
            if bpy.data.objects.get(obj.name) is obj:
                bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
        except ReferenceError:
            pass
