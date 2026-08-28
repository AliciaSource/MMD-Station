import importlib
import json
import uuid

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator


ROOT_ORDER_PROPERTY = "surface_proxy_pmx_material_order"
MATERIAL_ID_PROPERTY = "surface_proxy_pmx_material_id"
CALIBRATED_PROPERTY = "surface_proxy_pmx_material_ids_calibrated"


def material_identity(material):
    identity = str(material.get(MATERIAL_ID_PROPERTY, "")).strip()
    if not identity:
        identity = uuid.uuid4().hex
        material[MATERIAL_ID_PROPERTY] = identity
    return identity


def _model_materials_in_native_export_order(root, FnModel=None):
    if FnModel is None:
        model_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.model"
        )
        FnModel = model_module.FnModel
    materials = []
    seen = set()
    mesh_objects = sorted(FnModel.iterate_mesh_objects(root), key=lambda obj: obj.name)
    for mesh_object in mesh_objects:
        mesh = mesh_object.data
        used_indices = sorted({polygon.material_index for polygon in mesh.polygons})
        for index in used_indices:
            if index >= len(mesh.materials):
                continue
            material = mesh.materials[index]
            if material is None or material in seen:
                continue
            seen.add(material)
            materials.append(material)
    return materials


def _read_stored_order(root):
    raw = root.get(ROOT_ORDER_PROPERTY, "")
    if not isinstance(raw, str) or not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [str(identity) for identity in value if identity]


def ordered_materials(root, FnModel=None):
    native = _model_materials_in_native_export_order(root, FnModel)
    by_identity = {material_identity(material): material for material in native}
    stored = _read_stored_order(root)
    identities = [identity for identity in stored if identity in by_identity]
    identities.extend(identity for identity in by_identity if identity not in identities)
    encoded = json.dumps(identities, ensure_ascii=True, separators=(",", ":"))
    if root.get(ROOT_ORDER_PROPERTY, "") != encoded:
        root[ROOT_ORDER_PROPERTY] = encoded
        root[CALIBRATED_PROPERTY] = False
    return [by_identity[identity] for identity in identities]


def set_material_order(root, materials):
    identities = [material_identity(material) for material in materials]
    root[ROOT_ORDER_PROPERTY] = json.dumps(
        identities,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _used_materials(mesh_object):
    mesh = mesh_object.data
    used_indices = sorted({polygon.material_index for polygon in mesh.polygons})
    materials = []
    seen = set()
    for index in used_indices:
        if index >= len(mesh.materials):
            continue
        material = mesh.materials[index]
        if material is None or material in seen:
            continue
        seen.add(material)
        materials.append(material)
    return materials


def _relocate_external_id_conflicts(material_set, reserved_ids):
    conflicts = [
        material
        for material in bpy.data.materials
        if material not in material_set
        and material.mmd_material.material_id in reserved_ids
    ]
    used_external_ids = {
        material.mmd_material.material_id
        for material in bpy.data.materials
        if material not in material_set
        and material not in conflicts
        and material.mmd_material.material_id >= 0
    }
    next_id = max(
        [max(reserved_ids, default=-1), *used_external_ids],
        default=max(reserved_ids, default=-1),
    ) + 1
    moved = set()
    for material in conflicts:
        while next_id in used_external_ids:
            next_id += 1
        material.mmd_material.material_id = next_id
        used_external_ids.add(next_id)
        moved.add(material)
        next_id += 1
    return moved


def _sync_material_morph_ids(changed_materials):
    for model_root in bpy.data.objects:
        if getattr(model_root, "mmd_type", "") != "ROOT":
            continue
        for morph in model_root.mmd_root.material_morphs:
            for data in morph.data:
                material = getattr(data, "material_data", None)
                if material in changed_materials:
                    data.material_id = material.mmd_material.material_id


def material_ids_are_calibrated(root, materials=None):
    materials = ordered_materials(root) if materials is None else materials
    calibrated = all(
        material.mmd_material.material_id == index
        for index, material in enumerate(materials)
    )
    root[CALIBRATED_PROPERTY] = calibrated
    return calibrated


def sync_changed_material_order(root, previous, current, FnModel=None):
    if FnModel is None:
        model_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.model"
        )
        FnModel = model_module.FnModel
    if not material_ids_are_calibrated(root, previous):
        return False, 0, 0, 0
    if len(previous) != len(current) or set(previous) != set(current):
        root[CALIBRATED_PROPERTY] = False
        return False, 0, 0, 0
    changed_indices = [
        index
        for index, (old_material, new_material) in enumerate(
            zip(previous, current, strict=False)
        )
        if old_material != new_material
    ]
    if not changed_indices:
        return True, 0, 0, 0
    changed_order = {current[index]: index for index in changed_indices}
    changed_materials = set(changed_order)
    material_set = set(current)
    moved_conflicts = _relocate_external_id_conflicts(
        material_set,
        set(changed_indices),
    )
    for index in changed_indices:
        current[index].mmd_material.material_id = index
    _sync_material_morph_ids(changed_materials | moved_conflicts)

    misc_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.operators.misc"
    )
    renamed = 0
    for mesh_object in FnModel.iterate_mesh_objects(root):
        used = _used_materials(mesh_object)
        if len(used) == 1 and used[0] in changed_materials:
            misc_module.MoveObject.set_index(
                mesh_object,
                changed_order[used[0]],
            )
            renamed += 1
    root[CALIBRATED_PROPERTY] = True
    return True, len(changed_materials), renamed, len(moved_conflicts)


def calibrate_material_ids_and_object_names(root):
    model_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.model"
    )
    misc_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.operators.misc"
    )
    FnModel = model_module.FnModel
    MoveObject = misc_module.MoveObject
    materials = ordered_materials(root, FnModel)
    material_set = set(materials)
    reserved_ids = set(range(len(materials)))
    moved_conflicts = _relocate_external_id_conflicts(
        material_set,
        reserved_ids,
    )

    order_by_material = {material: index for index, material in enumerate(materials)}
    for material, index in order_by_material.items():
        material.mmd_material.material_id = index

    _sync_material_morph_ids(material_set | moved_conflicts)

    renamed = 0
    multi_material = 0
    for mesh_object in FnModel.iterate_mesh_objects(root):
        used = [
            material
            for material in _used_materials(mesh_object)
            if material in order_by_material
        ]
        if len(used) == 1:
            MoveObject.set_index(mesh_object, order_by_material[used[0]])
            renamed += 1
        elif len(used) > 1:
            multi_material += 1
    root[CALIBRATED_PROPERTY] = True
    return len(materials), renamed, multi_material, len(moved_conflicts)


def _reorder_exported_material_blocks(exporter, material_names):
    model = getattr(exporter, "_PmxExporter__model")
    name_table = getattr(exporter, "_PmxExporter__material_name_table")
    if not model.materials or len(model.materials) != len(name_table):
        return
    rank = {name: index for index, name in enumerate(material_names)}
    entries = []
    face_offset = 0
    for original_index, (material, name) in enumerate(
        zip(model.materials, name_table, strict=False)
    ):
        face_count = int(material.vertex_count / 3)
        entries.append(
            (
                rank.get(name, len(rank) + original_index),
                original_index,
                material,
                name,
                model.faces[face_offset : face_offset + face_count],
            )
        )
        face_offset += face_count
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    model.materials = [entry[2] for entry in entries]
    model.faces = [face for entry in entries for face in entry[4]]
    name_table[:] = [entry[3] for entry in entries]


def register_export_hook():
    try:
        exporter_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.pmx.exporter"
        )
        importer_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.pmx.importer"
        )
    except ImportError:
        return False
    exporter_class = getattr(exporter_module, "__PmxExporter")
    export_meshes_name = next(
        name for name in exporter_class.__dict__ if name.endswith("__exportMeshes")
    )

    execute = exporter_class.execute
    original_execute = getattr(execute, "_surface_proxy_original", execute)
    export_meshes = getattr(exporter_class, export_meshes_name)
    original_export_meshes = getattr(
        export_meshes,
        "_surface_proxy_original",
        export_meshes,
    )

    def execute_with_material_order(self, filepath, **args):
        root = args.get("root")
        material_names = []
        if root is not None:
            material_names = [material.name for material in ordered_materials(root)]
        self._surface_proxy_material_order_names = material_names
        if material_names:
            args = dict(args)
            args["sort_materials"] = False
        return original_execute(self, filepath, **args)

    def export_meshes_with_material_order(self, meshes, bone_map):
        result = original_export_meshes(self, meshes, bone_map)
        material_names = getattr(
            self,
            "_surface_proxy_material_order_names",
            (),
        )
        if material_names:
            _reorder_exported_material_blocks(self, material_names)
        return result

    execute_with_material_order._surface_proxy_original = original_execute
    export_meshes_with_material_order._surface_proxy_original = original_export_meshes
    exporter_class.execute = execute_with_material_order
    setattr(exporter_class, export_meshes_name, export_meshes_with_material_order)

    importer_class = importer_module.PMXImporter
    import_materials_name = next(
        name for name in importer_class.__dict__ if name.endswith("__importMaterials")
    )
    import_materials = getattr(importer_class, import_materials_name)
    original_import_materials = getattr(
        import_materials,
        "_surface_proxy_original",
        import_materials,
    )

    def import_materials_with_order(self):
        result = original_import_materials(self)
        root = getattr(self, "_PMXImporter__root", None)
        materials = getattr(self, "_PMXImporter__materialTable", ())
        if root is not None and materials:
            set_material_order(root, materials)
            root[CALIBRATED_PROPERTY] = False
        return result

    import_materials_with_order._surface_proxy_original = original_import_materials
    setattr(importer_class, import_materials_name, import_materials_with_order)
    return True


def unregister_export_hook():
    try:
        exporter_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.pmx.exporter"
        )
        importer_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.pmx.importer"
        )
    except ImportError:
        return
    exporter_class = getattr(exporter_module, "__PmxExporter")
    export_meshes_name = next(
        name for name in exporter_class.__dict__ if name.endswith("__exportMeshes")
    )
    execute = exporter_class.execute
    original_execute = getattr(execute, "_surface_proxy_original", None)
    if original_execute is not None:
        exporter_class.execute = original_execute
    export_meshes = getattr(exporter_class, export_meshes_name)
    original_export_meshes = getattr(
        export_meshes,
        "_surface_proxy_original",
        None,
    )
    if original_export_meshes is not None:
        setattr(exporter_class, export_meshes_name, original_export_meshes)
    importer_class = importer_module.PMXImporter
    import_materials_name = next(
        name for name in importer_class.__dict__ if name.endswith("__importMaterials")
    )
    import_materials = getattr(importer_class, import_materials_name)
    original_import_materials = getattr(
        import_materials,
        "_surface_proxy_original",
        None,
    )
    if original_import_materials is not None:
        setattr(importer_class, import_materials_name, original_import_materials)


class SPX_OT_SyncMaterialNames(Operator):
    bl_idname = "surface_proxy.sync_material_names"
    bl_label = "同步材质名称"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=(
            ("BLENDER_TO_MMD", "Blender → MMD", ""),
            ("MMD_TO_BLENDER", "MMD → Blender", ""),
        ),
        options={"HIDDEN"},
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = settings.mmd_root
        if root is None:
            self.report({"ERROR"}, "请先选择 MMD 模型")
            return {"CANCELLED"}
        materials = ordered_materials(root)
        for material in materials:
            if self.direction == "BLENDER_TO_MMD":
                material.mmd_material.name_j = material.name
                material.mmd_material.name_e = material.name
            else:
                name = material.mmd_material.name_j.strip()
                if name:
                    material.name = name
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report({"INFO"}, f"已同步 {len(materials)} 个材质名称")
        return {"FINISHED"}


class SPX_OT_TranslateSelectedMaterialNamesWithAI(Operator):
    bl_idname = "surface_proxy.translate_selected_material_names_with_ai"
    bl_label = "AI翻译勾选材质"
    bl_description = "将 MMD 查看器中已勾选材质的日文名翻译并写入 MMD 英文名"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        materials = []
        seen = set()
        skipped_empty = 0
        for item in settings.browser_items:
            material = item.material
            if not item.selected or item.kind != "MATERIAL" or material is None:
                continue
            pointer = material.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            if not material.mmd_material.name_j.strip():
                skipped_empty += 1
                continue
            materials.append(material)
        if not materials:
            message = "勾选材质没有可翻译的 MMD 日文名" if skipped_empty else "请先勾选材质"
            self.report({"WARNING"}, message)
            return {"CANCELLED"}

        from .mmd_morph_editor import (
            _addon_preferences,
            _request_morph_name_translations,
        )

        preferences = _addon_preferences(context)
        if preferences is None:
            self.report({"ERROR"}, "无法读取插件全局 AI 设置")
            return {"CANCELLED"}
        try:
            translations = _request_morph_name_translations(
                preferences,
                [material.mmd_material.name_j for material in materials],
            )
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for material, translation in zip(materials, translations, strict=True):
            material.mmd_material.name_e = translation
        message = f"已翻译并填写 {len(materials)} 个材质的 MMD 英文名"
        if skipped_empty:
            message += f"；跳过 {skipped_empty} 个空日文名"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_CalibrateMaterialOrder(Operator):
    bl_idname = "surface_proxy.calibrate_material_order"
    bl_label = "校对材质 ID 与物体编号"
    bl_description = "按查看器的 0-based PMX 顺序写入材质 ID，并只校对单材质物体的三位编号前缀"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = settings.mmd_root
        if root is None:
            self.report({"ERROR"}, "请先选择 MMD 模型")
            return {"CANCELLED"}
        try:
            material_count, renamed, multi_material, moved_conflicts = (
                calibrate_material_ids_and_object_names(root)
            )
        except (ImportError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report(
            {"INFO"},
            f"已校对 {material_count} 个材质 ID、{renamed} 个单材质物体；保留 {multi_material} 个多材质物体名称；迁移 {moved_conflicts} 个外部冲突 ID",
        )
        return {"FINISHED"}


class SPX_OT_SeparateActiveMeshByMaterials(Operator):
    bl_idname = "surface_proxy.separate_active_mesh_by_materials"
    bl_label = "按材质拆分（保留法向）"
    bl_description = "使用 mmd_tools 同款拆分逻辑处理活动 Mesh，并只把拆出的物体放入其材质顺序对应的预留编号"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        requested_root = settings.mmd_root
        target = context.active_object
        try:
            model_module = importlib.import_module(
                "bl_ext.blender_org.mmd_tools.core.model"
            )
            morph_module = importlib.import_module(
                "bl_ext.blender_org.mmd_tools.core.morph"
            )
            misc_module = importlib.import_module(
                "bl_ext.blender_org.mmd_tools.operators.misc"
            )
            utils_module = importlib.import_module(
                "bl_ext.blender_org.mmd_tools.utils"
            )
        except ImportError:
            self.report({"ERROR"}, "需要先启用官方 mmd_tools 插件")
            return {"CANCELLED"}

        FnModel = model_module.FnModel
        Model = model_module.Model
        FnMorph = morph_module.FnMorph
        MoveObject = misc_module.MoveObject
        root = FnModel.find_root_object(target)
        if root is None or root != FnModel.find_root_object(requested_root):
            self.report({"ERROR"}, "活动 Mesh 不属于当前 MMD 模型")
            return {"CANCELLED"}
        source_materials = _used_materials(target)
        if len(source_materials) < 2:
            self.report({"WARNING"}, "活动 Mesh 没有至少两个实际使用的材质")
            return {"CANCELLED"}

        materials = ordered_materials(root, FnModel)
        order_by_material = {
            material: index for index, material in enumerate(materials)
        }
        before = set(FnModel.iterate_mesh_objects(root))
        rig = Model(root)
        rig.morph_slider.unbind()
        bpy.ops.mmd_tools.clear_temp_materials()
        bpy.ops.mmd_tools.clear_uv_morph_view()
        utils_module.separateByMaterials(target, keep_normals=True)
        bpy.ops.mmd_tools.clean_shape_keys()

        after = set(FnModel.iterate_mesh_objects(root))
        results = [
            mesh_object
            for mesh_object in after
            if mesh_object is target or mesh_object not in before
        ]
        renamed = 0
        for mesh_object in results:
            used = _used_materials(mesh_object)
            if len(used) == 1 and used[0] in order_by_material:
                MoveObject.set_index(mesh_object, order_by_material[used[0]])
                renamed += 1
            FnMorph.clean_uv_morph_vertex_groups(mesh_object)
        for morph in root.mmd_root.material_morphs:
            FnMorph(morph, rig).update_mat_related_mesh()
        utils_module.clearUnusedMeshes()
        bpy.ops.surface_proxy.refresh_mmd_browser()
        self.report(
            {"INFO"},
            f"已按材质拆分为 {len(results)} 个物体，并校对其中 {renamed} 个编号；其它物体名称未改",
        )
        return {"FINISHED"}


def draw_name_sync(layout, settings):
    row = layout.row(align=True)
    row.operator(
        SPX_OT_CalibrateMaterialOrder.bl_idname,
        text="校对材质 ID 与物体编号",
        icon="CHECKMARK",
    )
    row.operator(
        SPX_OT_SeparateActiveMeshByMaterials.bl_idname,
        text="按材质拆分（保留法向）",
        icon="MOD_EXPLODE",
    )
    row.prop(
        settings,
        "material_order_auto_sync",
        text="自动同步",
        toggle=True,
        icon="FILE_REFRESH",
    )
    layout.label(text="材质 ID 和单材质物体前缀均从 000 开始；多材质物体只预留编号", icon="INFO")
    layout.label(text="首次先手动校对；自动同步只更新顺序实际变化的位置，支持多材质成块移动", icon="INFO")
    row = layout.row(align=True)
    operator = row.operator(
        SPX_OT_SyncMaterialNames.bl_idname,
        text="Blender 名同步到 MMD 中/英文名",
        icon="FORWARD",
    )
    operator.direction = "BLENDER_TO_MMD"
    operator = row.operator(
        SPX_OT_SyncMaterialNames.bl_idname,
        text="MMD 名同步到 Blender 材质名",
        icon="BACK",
    )
    operator.direction = "MMD_TO_BLENDER"
    row = layout.row(align=True)
    row.operator(
        SPX_OT_TranslateSelectedMaterialNamesWithAI.bl_idname,
        text="AI翻译勾选材质日文名",
        icon="WORLD",
    )
    row.operator(
        "surface_proxy.morph_ai_settings",
        text="",
        icon="PREFERENCES",
    )


CLASSES = (
    SPX_OT_SyncMaterialNames,
    SPX_OT_TranslateSelectedMaterialNamesWithAI,
    SPX_OT_CalibrateMaterialOrder,
    SPX_OT_SeparateActiveMeshByMaterials,
)
