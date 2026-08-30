import importlib


_EXPORTER_MODULE = "bl_ext.blender_org.mmd_tools.core.pmx.exporter"
_original_method = None
_patched_class = None
_patched_name = None


def _method_name(exporter_class):
    return next(
        (
            name
            for name in exporter_class.__dict__
            if name.endswith("__get_pmx_morph_map")
        ),
        None,
    )


def _morph_key(exporter, morph):
    return exporter.MORPH_TYPES[type(morph)], morph.name


def relative_morph_order(exporter, root):
    model = getattr(exporter, "_PmxExporter__model", None)
    if model is None:
        return []

    source_order = []
    existing = set()
    for morph in model.morphs:
        key = _morph_key(exporter, morph)
        if key not in existing:
            existing.add(key)
            source_order.append(key)

    facial_frame = next(
        (
            frame
            for frame in root.mmd_root.display_item_frames
            if frame.name == "表情"
        ),
        None,
    )
    registered = []
    registered_set = set()
    if facial_frame is not None:
        for item in facial_frame.data:
            key = (item.morph_type, item.name)
            if item.type == "MORPH" and key in existing and key not in registered_set:
                registered.append(key)
                registered_set.add(key)

    before = {key: [] for key in registered}
    after = {key: [] for key in registered}
    unattached = []
    morph_types = dict.fromkeys(key[0] for key in source_order)
    for morph_type in morph_types:
        pending = []
        last_registered = None
        for key in (key for key in source_order if key[0] == morph_type):
            if key in registered_set:
                before[key].extend(pending)
                pending.clear()
                last_registered = key
            else:
                pending.append(key)
        if last_registered is None:
            unattached.extend(pending)
        else:
            after[last_registered].extend(pending)

    ordered = []
    for key in registered:
        ordered.extend(before[key])
        ordered.append(key)
        ordered.extend(after[key])
    ordered.extend(unattached)
    return ordered


def register_export_hook():
    global _original_method, _patched_class, _patched_name
    if _original_method is not None:
        return
    exporter_module = importlib.import_module(_EXPORTER_MODULE)
    exporter_class = getattr(exporter_module, "__PmxExporter")
    method_name = _method_name(exporter_class)
    if method_name is None:
        return
    original = getattr(exporter_class, method_name)

    def get_pmx_morph_map(self, root):
        ordered = relative_morph_order(self, root)
        if not ordered:
            return original(self, root)
        return {key: index for index, key in enumerate(ordered)}

    _original_method = original
    _patched_class = exporter_class
    _patched_name = method_name
    setattr(exporter_class, method_name, get_pmx_morph_map)


def unregister_export_hook():
    global _original_method, _patched_class, _patched_name
    if _original_method is None:
        return
    setattr(_patched_class, _patched_name, _original_method)
    _original_method = None
    _patched_class = None
    _patched_name = None
