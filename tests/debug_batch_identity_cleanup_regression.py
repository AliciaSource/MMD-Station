import json
import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview import debug_batch


scene = bpy.context.scene
old_collection = None
new_collection = None
source = None
old_owner = "spx-old-debug-owner"
new_owner = "spx-new-debug-owner"

try:
    old_collection = bpy.data.collections.new("SPX old debug collection")
    new_collection = bpy.data.collections.new("SPX new debug collection")
    scene.collection.children.link(old_collection)
    scene.collection.children.link(new_collection)
    source = bpy.data.objects.new("SPX reowned debug source", None)
    new_collection.objects.link(source)
    source.hide_viewport = True
    source[debug_batch._OWNER_KEY] = new_owner
    source[debug_batch._KIND_KEY] = "source"
    source[debug_batch._SCENE_KEY] = scene.name
    source[debug_batch._SOURCE_COLLECTIONS_KEY] = json.dumps(
        (new_collection.name,)
    )
    source[debug_batch._SOURCE_HIDE_VIEWPORT_KEY] = True

    state = debug_batch._SourceState(
        source,
        (old_collection,),
        (old_collection.name,),
        False,
    )
    stale = debug_batch.PreviewDebugBatch.__new__(
        debug_batch.PreviewDebugBatch
    )
    stale.source_states = (state,)
    stale.scene = scene
    stale.owner_token = old_owner
    stale.closed = False
    debug_batch._LIVE_BATCHES[old_owner] = stale

    stale.close()

    assert stale.closed
    assert old_owner not in debug_batch._LIVE_BATCHES
    assert source.hide_viewport
    assert tuple(source.users_collection) == (new_collection,)
    assert source.get(debug_batch._OWNER_KEY, "") == new_owner
    assert source.get(debug_batch._KIND_KEY, "") == "source"
    assert source.get(debug_batch._SCENE_KEY, "") == scene.name
    assert json.loads(source.get(debug_batch._SOURCE_COLLECTIONS_KEY, "[]")) == [
        new_collection.name
    ]
    assert bool(source.get(debug_batch._SOURCE_HIDE_VIEWPORT_KEY, False))
    current_state = debug_batch._SourceState(
        source,
        (new_collection,),
        (new_collection.name,),
        False,
    )
    assert debug_batch._restore_source_state(current_state, scene, new_owner)
    assert not source.hide_viewport
    assert tuple(source.users_collection) == (new_collection,)
    assert debug_batch._OWNER_KEY not in source
    assert debug_batch._KIND_KEY not in source
    assert debug_batch._SCENE_KEY not in source
    assert debug_batch._SOURCE_COLLECTIONS_KEY not in source
    assert debug_batch._SOURCE_HIDE_VIEWPORT_KEY not in source

    print(
        "DEBUG_BATCH_IDENTITY_CLEANUP_OK",
        "reowned_source_untouched=1",
        "owned_source_restored=1",
    )
finally:
    debug_batch._LIVE_BATCHES.pop(old_owner, None)
    if source is not None:
        try:
            if bpy.data.objects.get(source.name) is source:
                bpy.data.objects.remove(source, do_unlink=True)
        except ReferenceError:
            pass
    for collection in (new_collection, old_collection):
        if collection is None:
            continue
        try:
            if bpy.data.collections.get(collection.name) is collection:
                bpy.data.collections.remove(collection)
        except ReferenceError:
            pass
