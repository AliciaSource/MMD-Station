"""Blender 5.x API compatibility helpers for MMD Station.

Blender 5.0 replaced the legacy ``Action.fcurves`` API with layered actions
(``Action.layers`` -> ``ActionKeyframeStrip`` -> ``ActionChannelbag``).
Curve access is scoped to the owning ID or NLA strip. Copied Actions preserve
slot identifiers, while ambiguous multi-owner access is rejected. Single-slot
legacy Actions retain their native API where available.

Blender 5.0 also removed the ``Bone.select`` flag in favour of
``PoseBone.select``, so bone selection goes through :func:`select_bones`.
"""

from __future__ import annotations

import importlib

import bpy


IS_BLENDER_50_UP = bpy.app.version >= (5, 0)


def import_optional_module(module_name):
    """Import ``module_name``, returning ``None`` when it is unusable.

    A stale mmd_tools build can sit on the add-on path and still fail to import
    on a newer Blender, for example the Blender 5.0 removal of
    ``bpy.types.ActionFCurves`` breaks ``mmd_tools.core.vmd.importer`` at import
    time. Probing for mmd_tools must therefore treat every failure as "not
    available" instead of letting it abort add-on registration.
    """
    try:
        return importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 - probing an optional third-party module
        return None


_ANIMATABLE_COLLECTIONS = (
    "objects",
    "shape_keys",
    "materials",
    "worlds",
    "scenes",
    "cameras",
    "lights",
    "curves",
    "meshes",
    "lattices",
    "node_groups",
    "particles",
)


def _same(first, second):
    """Compare two ``bpy_struct`` references without relying on identity."""
    if first is second:
        return True
    if first is None or second is None:
        return False
    try:
        return first.as_pointer() == second.as_pointer()
    except (AttributeError, ReferenceError, TypeError):
        return False


def _animation_owners():
    """Yield ``(animation_data, owner)`` for every animated data-block."""
    for collection_name in _ANIMATABLE_COLLECTIONS:
        collection = getattr(bpy.data, collection_name, None)
        if collection is None:
            continue
        for owner in collection:
            animation_data = getattr(owner, "animation_data", None)
            if animation_data is not None:
                yield animation_data, owner


def _owner_id_type(owner):
    """Return the slot ``id_type`` a data-block accepts (``OBJECT``, ``KEY``...)."""
    if owner is None:
        return ""
    return getattr(owner, "id_type", "") or "OBJECT"


def _id_type_for_data_path(data_path):
    """Guess the slot ``id_type`` a data path belongs to."""
    if data_path.startswith("key_blocks["):
        return "KEY"
    return ""


def _animation_data_owner(animation_data):
    owner = getattr(animation_data, "id_data", None)
    if owner is not None:
        return owner
    for candidate, owner in _animation_owners():
        if _same(candidate, animation_data):
            return owner
    return None


def _action_owner(action):
    """Return the data-block currently driving ``action``, if any."""
    for animation_data, owner in _animation_owners():
        if _same(animation_data.action, action):
            return owner
    return None


def _set_slot(target, slot):
    """Link ``slot`` onto ``target``, ignoring type mismatches."""
    try:
        target.action_slot = slot
    except (AttributeError, RuntimeError, TypeError):
        return False
    return True


def _slot_curve_count(action, slot):
    """Number of F-Curves stored in ``action`` for ``slot``."""
    total = 0
    for layer in getattr(action, "layers", None) or ():
        for strip in getattr(layer, "strips", None) or ():
            for channelbag in getattr(strip, "channelbags", None) or ():
                if _same(getattr(channelbag, "slot", None), slot):
                    total += len(channelbag.fcurves)
    return total


def _link_slot(action, slot):
    """Link a freshly created ``slot`` to whichever owner holds ``action``."""
    slot_type = getattr(slot, "target_id_type", "")
    for animation_data, owner in _animation_owners():
        if not _same(animation_data.action, action):
            continue
        if animation_data.action_slot is not None:
            continue
        if slot_type not in ("", "UNSPECIFIED", _owner_id_type(owner)):
            continue
        _set_slot(animation_data, slot)


def _linked_slot(action):
    linked = {}
    for animation_data, _owner in _animation_owners():
        if _same(animation_data.action, action) and animation_data.action_slot is not None:
            slot = animation_data.action_slot
            linked[slot.identifier] = slot
    return next(iter(linked.values())) if len(linked) == 1 else None


def _owner_slot(action, owner):
    """Resolve an owner's exact slot, including the matching slot in a copy."""
    target = getattr(owner, "animation_data", owner)
    current = getattr(target, "action_slot", None)
    if current is not None:
        for slot in action.slots:
            if slot.identifier == current.identifier:
                return slot
    return None


class _LayeredFCurves:
    """Expose a legacy ``Action.fcurves`` view on a layered Blender 5.0+ action."""

    def __init__(self, action, owner=None):
        self._action = action
        self._owner = owner

    def _slot(self):
        """Slot this view addresses, without ever creating a new one."""
        slots = getattr(self._action, "slots", None)
        if not slots:
            return None
        if self._owner is not None:
            linked = _owner_slot(self._action, self._owner)
            if linked is not None:
                return linked
        if len(slots) == 1:
            owner = self._owner
            if owner is not None and not hasattr(owner, "animation_data"):
                owner = getattr(owner, "id_data", owner)
            if owner is not None and slots[0].target_id_type not in ("", "UNSPECIFIED", _owner_id_type(owner)):
                return None
            return slots[0]
        linked = _linked_slot(self._action) if self._owner is None else None
        if linked is not None:
            return linked
        raise RuntimeError("动作包含多个槽位：请指定动画所属对象")

    def _ensure_slot(self, fallback_id_type="OBJECT"):
        """Slot that can actually drive the owner, creating one when needed."""
        slots = getattr(self._action, "slots", None)
        if slots is None:
            return None
        linked = self._slot() if slots else None
        if linked is not None:
            return linked
        owner = self._owner or _action_owner(self._action)
        if owner is not None and not hasattr(owner, "animation_data"):
            owner = getattr(owner, "id_data", owner)
        id_type = _owner_id_type(owner) or fallback_id_type
        for slot in slots:
            if slot.target_id_type in ("", "UNSPECIFIED", id_type):
                return slot
        name = owner.name if owner is not None else (self._action.name or "Slot")
        return slots.new(id_type=id_type, name=name or "Slot")

    def _channelbag(self, ensure=False, fallback_id_type="OBJECT"):
        action = self._action
        layers = getattr(action, "layers", None)
        if layers is None:
            return None
        if len(layers):
            layer = layers[0]
        elif ensure:
            layer = layers.new("Layer")
        else:
            return None
        strips = getattr(layer, "strips", None)
        if strips is None:
            return None
        if len(strips):
            strip = strips[0]
        elif ensure:
            strip = strips.new(type="KEYFRAME")
        else:
            return None
        channelbags = getattr(strip, "channelbags", None)
        if channelbags is None:
            return None
        slot = self._ensure_slot(fallback_id_type) if ensure else self._slot()
        if slot is None:
            return None
        for channelbag in channelbags:
            if _same(getattr(channelbag, "slot", None), slot):
                return channelbag
        if not ensure:
            return None
        channelbag = strip.channelbag(slot, ensure=True)
        _link_slot(action, slot)
        return channelbag

    def new(self, data_path, index=0, group_name="", action_group="", id_type=""):
        channelbag = self._channelbag(
            ensure=True,
            fallback_id_type=id_type or _id_type_for_data_path(data_path) or "OBJECT",
        )
        if channelbag is None:
            raise RuntimeError("无法为动作创建 F-Curve：分层动作通道不可用")
        if action_group and not group_name:
            group_name = action_group
        existing = channelbag.fcurves.find(data_path, index=index)
        if existing is not None:
            return existing
        if "group_name" in channelbag.fcurves.bl_rna.functions["new"].parameters:
            return channelbag.fcurves.new(data_path, index=index, group_name=group_name)
        curve = channelbag.fcurves.new(data_path, index=index)
        if group_name and len(self._action.slots) == 1 and hasattr(self._action, "groups"):
            group = self._action.groups.get(group_name) or self._action.groups.new(group_name)
            curve.group = group
        return curve

    def find(self, data_path, index=0):
        channelbag = self._channelbag()
        if channelbag is None:
            return None
        return channelbag.fcurves.find(data_path, index=index)

    def remove(self, fcurve):
        channelbag = self._channelbag()
        if channelbag is not None:
            channelbag.fcurves.remove(fcurve)

    def clear(self):
        channelbag = self._channelbag()
        if channelbag is not None:
            channelbag.fcurves.clear()

    def __iter__(self):
        channelbag = self._channelbag()
        return iter(channelbag.fcurves) if channelbag is not None else iter(())

    def __len__(self):
        channelbag = self._channelbag()
        return len(channelbag.fcurves) if channelbag is not None else 0

    def __getitem__(self, key):
        channelbag = self._channelbag()
        if channelbag is None:
            raise IndexError(key)
        return channelbag.fcurves[key]


def action_fcurves(action, owner=None):
    """Return an ``Action.fcurves``-compatible view for the running Blender."""
    if action is None:
        return ()
    can_use_layers = (
        not getattr(action, "is_action_legacy", False)
        or getattr(action, "is_empty", False)
    )
    needs_scoped_view = owner is not None or len(getattr(action, "slots", ())) > 1
    if IS_BLENDER_50_UP or can_use_layers and needs_scoped_view:
        return _LayeredFCurves(action, owner)
    return action.fcurves


def assign_action(animation_data, action, slot=None):
    """Assign ``action`` and link the layered slot that drives its owner."""
    previous = slot if slot is not None else getattr(animation_data, "action_slot", None)
    identifier = previous.identifier if previous is not None else ""
    animation_data.action = action
    if action is None or not hasattr(animation_data, "action_slot"):
        return
    if identifier:
        for slot in action.slots:
            if slot.identifier == identifier:
                _set_slot(animation_data, slot)
                return
    if animation_data.action_slot is not None:
        return
    slots = getattr(action, "slots", None)
    if not slots:
        return
    owner = _animation_data_owner(animation_data)
    id_type = _owner_id_type(owner)
    name = owner.name if owner is not None else ""
    suitable = [
        slot
        for slot in (getattr(animation_data, "action_suitable_slots", None) or ())
        if not id_type or slot.target_id_type in ("", "UNSPECIFIED", id_type)
    ]
    if not suitable:
        if not id_type:
            return
        try:
            slot = slots.new(id_type=id_type, name=name or action.name or "Slot")
        except (RuntimeError, TypeError):
            return
        _set_slot(animation_data, slot)
        return
    last_identifier = getattr(animation_data, "last_slot_identifier", "") or ""
    for slot in suitable:
        if last_identifier and slot.identifier == last_identifier:
            _set_slot(animation_data, slot)
            return
    for slot in suitable:
        if name and slot.name_display == name:
            _set_slot(animation_data, slot)
            return
    if len(suitable) > 1:
        for slot in suitable:
            if _slot_curve_count(action, slot):
                _set_slot(animation_data, slot)
                return
    _set_slot(animation_data, suitable[0])


def link_strip_action(strip, action, owner=None):
    """Link the layered action slot of a newly created NLA strip."""
    if action is None:
        return
    if owner is not None:
        slot = _owner_slot(action, owner)
        if slot is not None:
            _set_slot(strip, slot)
            return
    if not hasattr(strip, "action_slot") or strip.action_slot is not None:
        return
    suitable = list(getattr(strip, "action_suitable_slots", None) or ())
    if suitable:
        _set_slot(strip, suitable[0])
        return
    slots = getattr(action, "slots", None)
    if slots and len(slots) == 1:
        _set_slot(strip, slots[0])


def _selectable_bones(armature):
    """Return the bones whose ``select`` flag drives viewport selection."""
    if IS_BLENDER_50_UP:
        return armature.pose.bones
    return armature.data.bones


def select_bones(armature, names):
    """Select exactly the bones named in ``names`` on ``armature``."""
    selected = set(names)
    for bone in _selectable_bones(armature):
        bone.select = bone.name in selected


def select_bone(armature, name, value=True):
    """Set the selection flag of one bone, returning it when it exists."""
    bone = _selectable_bones(armature).get(name)
    if bone is not None:
        bone.select = value
    return bone


def bone_selected(pose_bone):
    """Whether ``pose_bone`` is selected; 5.0 moved the flag off ``Bone``."""
    if IS_BLENDER_50_UP:
        return bool(pose_bone.select)
    return bool(pose_bone.bone.select)


def selected_bone_names(armature):
    """Names of the bones currently selected on ``armature``."""
    return {bone.name for bone in _selectable_bones(armature) if bone.select}


def bone_hidden(armature, bone):
    """Read viewport visibility without confusing Blender 5 edit-bone hiding."""
    if IS_BLENDER_50_UP and armature.mode != "EDIT":
        return armature.pose.bones[bone.name].hide
    return bone.hide


def set_uv_selection(mesh, uv_layer, index, value):
    """Write UV vertex selection using Blender 5's shared corner attribute."""
    if IS_BLENDER_50_UP:
        # Blender only imports shared UV selection into BMesh when all three
        # selection attributes exist, even if edge/face selection is empty.
        for name, domain in ((".uv_select_edge", "CORNER"), (".uv_select_face", "FACE")):
            if mesh.attributes.get(name) is None:
                mesh.attributes.new(name, "BOOLEAN", domain)
        attribute = mesh.attributes.get(".uv_select_vert")
        if attribute is None:
            attribute = mesh.attributes.new(".uv_select_vert", "BOOLEAN", "CORNER")
        attribute.data[index].value = value
    else:
        uv_layer.data[index].select = value
