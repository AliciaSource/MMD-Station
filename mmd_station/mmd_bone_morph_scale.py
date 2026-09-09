"""Host-owned bone scale editing and PMX sidecars; upstream PMX stays standard."""

import importlib
import logging

import bpy
from bpy.props import FloatVectorProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .execution_guard import scene_access_allowed
from .i18n import iface, report
from .morph_sidecar import non_unit, read_payload, sidecar_path, write_payload

SCALE = "spx_scale"
PREFIX = "morph_scale."
_PATCHES = []
_DATA_CLASS = None
_BATCH = False


def api():
    from .mmd_morph_editor import _mmd_api
    return _mmd_api()


def editor_target(context):
    from .mmd_morph_editor import _find_root, _active_morph
    root = _find_root(context, context.scene.surface_proxy_creator)
    morph = _active_morph(root)
    if root is None or root.mmd_root.active_morph_type != "bone_morphs":
        return root, None, None
    return root, morph, api()[1](root).armature()


def store_pose(data, bone):
    data.bone = bone.name
    data.location = bone.location
    if bone.rotation_mode == "QUATERNION":
        rotation = bone.rotation_quaternion.copy()
    elif bone.rotation_mode == "AXIS_ANGLE":
        from mathutils import Quaternion
        rotation = Quaternion(bone.rotation_axis_angle[1:], bone.rotation_axis_angle[0])
    else:
        rotation = bone.rotation_euler.to_quaternion()
    data.rotation = rotation
    data.spx_scale = bone.scale


def hierarchy(armature):
    result = []
    stack = list(reversed([b for b in armature.pose.bones if b.parent is None]))
    while stack:
        bone = stack.pop()
        result.append(bone)
        stack.extend(reversed(list(bone.children)))
    return result


def refresh_bindings(root):
    from .mmd_morph_editor import _bound_placeholder, _ensure_lightweight_bind, evaluate_morph_root
    context = bpy.context
    active = context.view_layer.objects.active
    mode = active.mode if active is not None else None
    selected = tuple(context.selected_objects)
    active_bone = active.data.bones.active.name if active is not None and active.type == "ARMATURE" and active.data.bones.active else None
    try:
        if _bound_placeholder(root) is not None:
            _ensure_lightweight_bind(root, force_rebind=True)
        evaluate_morph_root(root)
    finally:
        if active is not None and mode in {"POSE", "OBJECT"}:
            if context.object is not None and context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = active
            if mode == "POSE":
                bpy.ops.object.mode_set(mode="POSE")
            if active_bone is not None:
                active.data.bones.active = active.data.bones.get(active_bone)


def save_pose(morph, armature, replace=False):
    global _BATCH
    _BATCH = True
    try:
        bones = [b for b in hierarchy(armature) if not b.is_mmd_shadow_bone]
        changed = [b for b in bones if b.location.length > 1.0e-6 or non_unit(b.scale)
                   or abs(abs(b.matrix_basis.to_quaternion().w) - 1.0) > 1.0e-8]
        if replace:
            morph.data.clear()
        for bone in changed:
            offsets = [d for d in morph.data if d.bone == bone.name]
            data = offsets[0] if offsets else morph.data.add()
            store_pose(data, bone)
        order = {b.name: i for i, b in enumerate(bones)}
        desired = sorted(list(morph.data), key=lambda d: order.get(d.bone, len(order)))
        for index, data in enumerate(desired):
            current = next(i for i, d in enumerate(morph.data) if d.as_pointer() == data.as_pointer())
            morph.data.move(current, index)
        morph.active_data = 0
    finally:
        _BATCH = False
    refresh_bindings(morph.id_data)
    return len(changed)


def _scale_updated(data, context):
    if not _BATCH and scene_access_allowed():
        from .mmd_morph_editor import evaluate_morph_root
        evaluate_morph_root(data.id_data)


def sync_scale_constraints(root, weights, allow_structure=True):
    """Multiply evaluated scale without overwriting authored pose or Action channels."""
    from .mmd_morph_editor import MORPH_UID_PROPERTY, _DeferredMorphSetup
    armature = api()[1](root).armature()
    if armature is None:
        return
    wanted = set()
    for morph in root.mmd_root.bone_morphs:
        weight = weights.get(("bone_morphs", morph.get(MORPH_UID_PROPERTY)), 0.0)
        for data in morph.data:
            if not non_unit(data.spx_scale):
                continue
            bone = armature.pose.bones.get(data.bone)
            if bone is None:
                continue
            binding = bone.constraints.get(data.name + ".LOC")
            if binding is None or binding.target is None:
                continue
            helper = binding.target.pose.bones.get(binding.subtarget)
            if helper is None:
                continue
            name = PREFIX + data.name
            wanted.add((bone.name, name))
            constraint = bone.constraints.get(name)
            if constraint is None:
                if not allow_structure:
                    raise _DeferredMorphSetup()
                constraint = bone.constraints.new("TRANSFORM")
                constraint.name = name
                constraint.target = binding.target
                constraint.subtarget = binding.subtarget
                constraint.target_space = "LOCAL"
                constraint.owner_space = "LOCAL"
                constraint.map_from = "LOCATION"
                constraint.map_to = "SCALE"
                constraint.mix_mode_scale = "MULTIPLY"
                constraint.use_motion_extrapolate = True
                for axis in "xyz":
                    setattr(constraint, "from_min_" + axis, 0.0)
                    setattr(constraint, "from_max_" + axis, 1.0)
            constraint.mute = False
            for axis_index, axis in enumerate("xyz"):
                value = 1.0 + weight * (data.spx_scale[axis_index] - 1.0)
                for bound in ("min", "max"):
                    attr = "to_" + bound + "_" + axis + "_scale"
                    if abs(getattr(constraint, attr) - value) > 1.0e-7:
                        setattr(constraint, attr, value)
    if not wanted and not root.get("spx_scale_runtime", False):
        return
    root["spx_scale_runtime"] = bool(wanted)
    for bone in armature.pose.bones:
        for constraint in list(bone.constraints):
            if constraint.name.startswith(PREFIX) and (bone.name, constraint.name) not in wanted:
                if not allow_structure:
                    constraint.mute = True
                    raise _DeferredMorphSetup()
                bone.constraints.remove(constraint)


def identity(item):
    return {"name": item.name, "name_e": item.name_e}


def bone_identity(bone):
    return {"name": bone.mmd_bone.name_j or bone.name, "name_e": bone.mmd_bone.name_e}


def unique_match(items, target, identify):
    matches = [item for item in items if identify(item) == {k: target[k] for k in ("name", "name_e")}]
    return matches[0] if len(matches) == 1 else None


def export_entries(root, model):
    armature = api()[1](root).armature()
    if armature is None:
        return []
    entries = []
    for mi, pm in enumerate(model.morphs):
        if pm.type_index() != 2:
            continue
        morph = unique_match(root.mmd_root.bone_morphs, identity(pm), identity)
        if morph is None:
            continue
        for offset in pm.offsets:
            pb = model.bones[offset.index]
            bone = unique_match(armature.pose.bones, identity(pb), bone_identity)
            if bone is None:
                continue
            offsets = [d for d in morph.data if d.bone == bone.name]
            if len(offsets) > 1 and any(non_unit(d.spx_scale) for d in offsets):
                raise ValueError(f"Ambiguous duplicate bone scale offsets: {morph.name} / {bone.name}")
            if len(offsets) != 1 or not non_unit(offsets[0].spx_scale):
                continue
            entries.append({"morph": {**identity(pm), "index": mi},
                            "bone": {**identity(pb), "index": offset.index},
                            "scale": list(offsets[0].spx_scale)})
    return entries


def import_scales(root, filepath):
    global _BATCH
    payload = read_payload(filepath)
    armature = api()[1](root).armature()
    updates = []
    keys = [(e["morph"]["name"], e["morph"]["name_e"], e["bone"]["name"], e["bone"]["name_e"])
            for e in payload["entries"]]
    from collections import Counter
    counts = Counter(keys)
    for key, entry in zip(keys, payload["entries"]):
        if armature is None or counts[key] != 1:
            continue
        morph = unique_match(root.mmd_root.bone_morphs, entry["morph"], identity)
        bone = unique_match(armature.pose.bones, entry["bone"], bone_identity)
        if morph is None or bone is None:
            continue
        offsets = [d for d in morph.data if d.bone == bone.name]
        if len(offsets) == 1:
            updates.append((offsets[0], entry["scale"]))
    _BATCH = True
    try:
        for data, scale in updates:
            data.spx_scale = scale
    finally:
        _BATCH = False
    from .mmd_morph_editor import evaluate_morph_root
    evaluate_morph_root(root)
    skipped = len(payload["entries"]) - len(updates)
    root["spx_scale_import_status"] = "OK"
    root["spx_scale_imported"] = len(updates)
    root["spx_scale_skipped"] = skipped
    return len(updates), skipped


class SPX_OT_SaveBoneMorphPose(Operator):
    bl_idname = "surface_proxy.save_bone_morph_pose"
    bl_label = "将当前活动姿势保存"
    bl_description = "按父子层级将当前局部姿态变化保存到活动骨骼 Morph，包含缩放"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root, morph, armature = editor_target(context)
        return morph is not None and armature is not None and context.object == armature and context.mode == "POSE"

    def execute(self, context):
        root, morph, armature = editor_target(context)
        count = save_pose(morph, armature)
        report(self, {"INFO"}, iface("已保存 {count} 根骨骼的姿态").format(count=count))
        return {"FINISHED"}


class SPX_OT_ImportBoneMorphScale(Operator, ImportHelper):
    bl_idname = "surface_proxy.import_bone_morph_scale"
    bl_label = "导入骨骼 Morph 缩放"
    bl_description = "选择任意文件名的 Morph JSON，为当前模型补入骨骼表情缩放"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    target_root: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return editor_target(context)[0] is not None

    def invoke(self, context, event):
        self.target_root = editor_target(context)[0].name
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        root = bpy.data.objects.get(self.target_root) if self.target_root else editor_target(context)[0]
        if root is None:
            return {"CANCELLED"}
        try:
            imported, skipped = import_scales(root, self.filepath)
        except (OSError, ValueError) as error:
            report(self, {"ERROR"}, iface("缩放 JSON 读取失败：{error}").format(error=error))
            return {"CANCELLED"}
        report(self, {"INFO"}, iface("已导入 {imported} 项缩放；跳过 {skipped} 项").format(imported=imported, skipped=skipped))
        return {"FINISHED"}


def patch(target, name, replacement):
    _PATCHES.append((target, name, getattr(target, name), replacement))
    setattr(target, name, replacement)


def register_services():
    global _DATA_CLASS
    module = importlib.import_module("bl_ext.blender_org.mmd_tools.properties.morph")
    _DATA_CLASS = module.BoneMorphData
    _DATA_CLASS.spx_scale = FloatVectorProperty(name="缩放", size=3, default=(1, 1, 1),
                                               min=-1.0e6, max=1.0e6, update=_scale_updated)
    ops = importlib.import_module("bl_ext.blender_org.mmd_tools.operators.morph")
    for class_name in ("ViewBoneMorph", "EditBoneOffset", "ApplyBoneOffset", "ApplyBoneMorph", "AddMorphOffset"):
        cls = getattr(ops, class_name)
        original = cls.execute

        def make_execute(_original, _kind):
            def execute(operator, context):
                root = api()[0].find_root_object(context.active_object)
                if root is None or root.mmd_root.active_morph_type != "bone_morphs":
                    return _original(operator, context)
                morphs = root.mmd_root.bone_morphs
                index = root.mmd_root.active_morph
                if not 0 <= index < len(morphs):
                    return {"CANCELLED"}
                morph = morphs[index]
                armature = api()[1](root).armature()
                if _kind == "ApplyBoneMorph":
                    save_pose(morph, armature, replace=True)
                    return {"FINISHED"}
                result = _original(operator, context)
                if "FINISHED" not in result:
                    return result
                if _kind == "ViewBoneMorph":
                    for data in morph.data:
                        bone = armature.pose.bones.get(data.bone)
                        if bone is not None:
                            bone.scale = tuple(a * b for a, b in zip(bone.scale, data.spx_scale))
                elif morph.data:
                    data = morph.data[morph.active_data]
                    bone = armature.pose.bones.get(data.bone)
                    if bone is not None:
                        if _kind == "EditBoneOffset":
                            bone.scale = data.spx_scale
                        else:
                            store_pose(data, bone)
                            refresh_bindings(root)
                return result
            return execute
        patch(cls, "execute", make_execute(original, class_name))

    exporter = importlib.import_module("bl_ext.blender_org.mmd_tools.core.pmx.exporter")
    original_export = exporter.export

    def export(filepath, **kwargs):
        captured = []
        original_save = exporter.pmx.save

        def save(path, model, **options):
            entries = export_entries(kwargs["root"], model) if kwargs.get("root") is not None else None
            result = original_save(path, model, **options)
            captured[:] = [entries] if entries is not None else []
            return result
        exporter.pmx.save = save
        try:
            result = original_export(filepath, **kwargs)
        finally:
            exporter.pmx.save = original_save
        if captured:
            try:
                write_payload(filepath, captured[0])
            except (OSError, ValueError) as error:
                raise OSError(f"PMX saved, but Morph JSON could not be updated: {error}") from error
        return result
    patch(exporter, "export", export)

    importer = importlib.import_module("bl_ext.blender_org.mmd_tools.core.pmx.importer")
    original_import = importer.PMXImporter.execute

    def execute_import(instance, **kwargs):
        result = original_import(instance, **kwargs)
        path = kwargs.get("filepath")
        if path and sidecar_path(path).is_file():
            root = getattr(instance, "_PMXImporter__root", None)
            try:
                import_scales(root, sidecar_path(path))
            except (OSError, ValueError) as error:
                root["spx_scale_import_status"] = str(error)
                logging.getLogger(__name__).warning("Morph scale sidecar skipped: %s", error)
        return result
    patch(importer.PMXImporter, "execute", execute_import)


def unregister_services():
    global _DATA_CLASS
    if scene_access_allowed():
        for obj in bpy.data.objects:
            if obj.type == "ARMATURE":
                for bone in obj.pose.bones:
                    for constraint in list(bone.constraints):
                        if constraint.name.startswith(PREFIX):
                            bone.constraints.remove(constraint)
    for target, name, original, replacement in reversed(_PATCHES):
        if getattr(target, name) is replacement:
            setattr(target, name, original)
    _PATCHES.clear()
    if _DATA_CLASS is not None and hasattr(_DATA_CLASS, SCALE):
        delattr(_DATA_CLASS, SCALE)
    _DATA_CLASS = None


CLASSES = (SPX_OT_SaveBoneMorphPose, SPX_OT_ImportBoneMorphScale)
