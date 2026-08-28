PROXY_COLLECTION_NAME = "MMD Station Proxies"
_PROXY_COLLECTION_MARKER = "mmd_station_proxy_collection"


def _move_to_collections(obj, target_collections):
    targets = tuple(dict.fromkeys(target_collections))
    for collection in targets:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
    for collection in tuple(obj.users_collection):
        if collection not in targets:
            collection.objects.unlink(obj)


def ensure_proxy_collection(scene):
    for collection in scene.collection.children:
        if collection.name == PROXY_COLLECTION_NAME or collection.get(
            _PROXY_COLLECTION_MARKER
        ):
            return collection

    import bpy

    collection = bpy.data.collections.new(PROXY_COLLECTION_NAME)
    collection[_PROXY_COLLECTION_MARKER] = True
    scene.collection.children.link(collection)
    return collection


def place_proxy_object(scene, obj):
    _move_to_collections(obj, (ensure_proxy_collection(scene),))


def place_mmd_objects(scene, root, objects):
    target_collections = tuple(root.users_collection) or (scene.collection,)
    for obj in objects:
        if obj is not None:
            _move_to_collections(obj, target_collections)
