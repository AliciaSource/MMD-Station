import csv
import io
import math
from dataclasses import dataclass, field

import bpy
from mathutils import Euler, Quaternion


MORPH_TYPE_BY_PMX = {
    0: "group_morphs",
    1: "vertex_morphs",
    2: "bone_morphs",
    3: "uv_morphs",
    4: "uv_morphs",
    5: "uv_morphs",
    6: "uv_morphs",
    7: "uv_morphs",
    8: "material_morphs",
}
PMX_TYPE_BY_MORPH = {
    "group_morphs": 0,
    "vertex_morphs": 1,
    "bone_morphs": 2,
    "material_morphs": 8,
}
CATEGORY_BY_PMX = {
    0: "SYSTEM",
    1: "EYEBROW",
    2: "EYE",
    3: "MOUTH",
    4: "OTHER",
}
PMX_BY_CATEGORY = {value: key for key, value in CATEGORY_BY_PMX.items()}
PORTABLE_MORPH_TYPES = {"material_morphs", "bone_morphs", "group_morphs"}

MORPH_HEADER = (
    ";Morph,モーフ名,モーフ名(英),"
    "パネル(0:無効/1:眉(左下)/2:目(左上)/3:口(右上)/4:その他(右下)),"
    "モーフ種類(0:グループモーフ/1:頂点モーフ/2:ボーンモーフ/"
    "3:UV(Tex)モーフ/4:追加UV1モーフ/5:追加UV2モーフ/"
    "6:追加UV3モーフ/7:追加UV4モーフ/8:材質モーフ/"
    "9:フリップモーフ/10:インパルスモーフ)"
)
GROUP_HEADER = ";GroupMorph(フリップモーフ共用),親モーフ名,モーフ名,影響度"
BONE_HEADER = (
    ";BoneMorph,親モーフ名,ボーン名,移動量_x,移動量_y,移動量_z,"
    "回転量_x[deg],回転量_y[deg],回転量_z[deg]"
)
MATERIAL_HEADER = (
    ";MaterialMorph,親モーフ名,材質名,演算タイプ(0:乗算/1:加算),"
    "拡散色_R,拡散色_G,拡散色_B,拡散色_A(非透過度),"
    "反射色_R,反射色_G,反射色_B,反射強度,環境色_R,環境色_G,環境色_B,"
    "エッジサイズ,エッジ色_R,エッジ色_G,エッジ色_B,エッジ色_A,"
    "Tex_R,Tex_G,Tex_B,Tex_A,スフィア_R,スフィア_G,スフィア_B,"
    "スフィア_A,Toon_R,Toon_G,Toon_B,Toon_A"
)
VERTEX_HEADER = ";VertexMorph,親モーフ名,頂点Index,位置オフセット_x,位置オフセット_y,位置オフセット_z"
UV_HEADER = ";UVMorph,親モーフ名,頂点Index,UVオフセット_x,UVオフセット_y,UVオフセット_z,UVオフセット_w"


@dataclass
class ClipboardMorph:
    name: str
    name_e: str
    category: int
    pmx_type: int
    details: list[list[str]] = field(default_factory=list)

    @property
    def morph_type(self):
        return MORPH_TYPE_BY_PMX.get(self.pmx_type, "")


def _csv_line(values):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="").writerow(values)
    return stream.getvalue()


def _float_text(value):
    value = float(value)
    if abs(value) < 5.0e-12:
        value = 0.0
    return f"{value:.9g}"


def _float_row(values):
    return [_float_text(value) for value in values]


def parse_pmx_editor_morph_csv(text):
    if not text or "Morph" not in text:
        raise ValueError("剪贴板中没有 PMX Editor Morph CSV")
    records = []
    by_name = {}
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0] or row[0].startswith(";"):
            continue
        kind = row[0].strip()
        if kind == "Morph":
            if len(row) < 5:
                raise ValueError("Morph 行字段不足")
            try:
                category = int(row[3])
                pmx_type = int(row[4])
            except ValueError as exc:
                raise ValueError("Morph 类型或面板编号无效") from exc
            record = ClipboardMorph(row[1], row[2], category, pmx_type)
            records.append(record)
            by_name.setdefault(record.name, []).append(record)
            continue
        if kind not in {
            "GroupMorph",
            "VertexMorph",
            "BoneMorph",
            "UVMorph",
            "MaterialMorph",
        }:
            continue
        if len(row) < 2:
            continue
        candidates = by_name.get(row[1], ())
        expected = {
            "GroupMorph": 0,
            "VertexMorph": 1,
            "BoneMorph": 2,
            "UVMorph": (3, 4, 5, 6, 7),
            "MaterialMorph": 8,
        }[kind]
        if not isinstance(expected, tuple):
            expected = (expected,)
        target = next(
            (record for record in reversed(candidates) if record.pmx_type in expected),
            None,
        )
        if target is not None:
            target.details.append(row)
    if not records:
        raise ValueError("剪贴板中没有 Morph 数据行")
    return records


def _bone_japanese_name(root, bone_name):
    from bl_ext.blender_org.mmd_tools.core.model import FnModel

    armature = FnModel.find_armature_object(root)
    pose_bone = armature.pose.bones.get(bone_name) if armature else None
    if pose_bone is None:
        return bone_name
    return pose_bone.mmd_bone.name_j or pose_bone.name


def _material_japanese_name(material_name):
    material = bpy.data.materials.get(material_name)
    if material is None:
        return material_name
    return material.mmd_material.name_j or material.name


def _bone_to_pmx_values(root, data):
    from bl_ext.blender_org.mmd_tools.core.model import FnModel
    from bl_ext.blender_org.mmd_tools.core.vmd.importer import BoneConverter

    armature = FnModel.find_armature_object(root)
    pose_bone = armature.pose.bones.get(data.bone) if armature else None
    if pose_bone is None:
        return None
    converter = BoneConverter(pose_bone, 12.5, invert=True)
    location = converter.convert_location(data.location)
    rw, rx, ry, rz = data.rotation
    rw, rx, ry, rz = converter.convert_rotation((rx, ry, rz, rw))
    rotation = Quaternion((rw, rx, ry, rz)).to_euler("XYZ")
    return (
        _bone_japanese_name(root, data.bone),
        tuple(location),
        tuple(math.degrees(value) for value in rotation),
    )


def serialize_pmx_editor_morphs(root, typed_morphs):
    lines = [MORPH_HEADER]
    copied = 0
    skipped = []
    for morph_type, morph in typed_morphs:
        if morph_type == "vertex_morphs":
            skipped.append(morph.name)
            continue
        pmx_type = PMX_TYPE_BY_MORPH.get(morph_type)
        if morph_type == "uv_morphs":
            if morph.data_type != "DATA":
                skipped.append(morph.name)
                continue
            pmx_type = 3 + int(morph.uv_index)
        if pmx_type is None:
            skipped.append(morph.name)
            continue
        lines.append(
            _csv_line(
                (
                    "Morph",
                    morph.name,
                    morph.name_e,
                    PMX_BY_CATEGORY.get(morph.category, 4),
                    pmx_type,
                )
            )
        )
        if morph_type == "group_morphs":
            lines.append(GROUP_HEADER)
            for data in morph.data:
                lines.append(
                    _csv_line(
                        ("GroupMorph", morph.name, data.name, _float_text(data.factor))
                    )
                )
        elif morph_type == "bone_morphs":
            lines.append(BONE_HEADER)
            for data in morph.data:
                converted = _bone_to_pmx_values(root, data)
                if converted is None:
                    continue
                bone_name, location, rotation = converted
                lines.append(
                    _csv_line(
                        ("BoneMorph", morph.name, bone_name)
                        + tuple(_float_row(location + rotation))
                    )
                )
        elif morph_type == "material_morphs":
            lines.append(MATERIAL_HEADER)
            for data in morph.data:
                values = (
                    tuple(data.diffuse_color)
                    + tuple(data.specular_color)
                    + (data.shininess,)
                    + tuple(data.ambient_color)
                    + (data.edge_weight,)
                    + tuple(data.edge_color)
                    + tuple(data.texture_factor)
                    + tuple(data.sphere_texture_factor)
                    + tuple(data.toon_texture_factor)
                )
                lines.append(
                    _csv_line(
                        (
                            "MaterialMorph",
                            morph.name,
                            _material_japanese_name(data.material),
                            0 if data.offset_type == "MULT" else 1,
                        )
                        + tuple(_float_row(values))
                    )
                )
        elif morph_type == "uv_morphs":
            lines.append(UV_HEADER)
            for data in morph.data:
                lines.append(
                    _csv_line(
                        ("UVMorph", morph.name, int(data.index))
                        + tuple(_float_row(data.offset))
                    )
                )
        copied += 1
    return "\r\n".join(lines) + "\r\n", copied, skipped


def _resolve_bone(root, pmx_name):
    from bl_ext.blender_org.mmd_tools.core.model import FnModel

    armature = FnModel.find_armature_object(root)
    if armature is None:
        return None
    exact = armature.pose.bones.get(pmx_name)
    if exact is not None:
        return exact
    return next(
        (
            bone
            for bone in armature.pose.bones
            if pmx_name in {bone.mmd_bone.name_j, bone.mmd_bone.name_e}
        ),
        None,
    )


def _resolve_material(root, pmx_name):
    from bl_ext.blender_org.mmd_tools.core.model import FnModel

    if pmx_name in {"", "-1", "全材質", "全ての材質"}:
        return None
    for mesh in FnModel.iterate_mesh_objects(root):
        for material in mesh.data.materials:
            if material is None:
                continue
            if pmx_name in {
                material.name,
                material.mmd_material.name_j,
                material.mmd_material.name_e,
            }:
                return material
    return None


def _clear_collection(collection):
    while collection:
        collection.remove(len(collection) - 1)


def _morph_name_types(root, records):
    result = {}
    for record in records:
        if record.morph_type:
            result.setdefault(record.name, []).append(record.morph_type)
    for morph_type in (
        "material_morphs",
        "uv_morphs",
        "bone_morphs",
        "vertex_morphs",
        "group_morphs",
    ):
        for morph in getattr(root.mmd_root, morph_type):
            result.setdefault(morph.name, []).append(morph_type)
    return result


def _apply_bone_details(root, morph, record, unresolved):
    from bl_ext.blender_org.mmd_tools.core.vmd.importer import BoneConverter

    for row in record.details:
        if len(row) < 9:
            unresolved.append(f"{record.name}: BoneMorph 字段不足")
            continue
        pose_bone = _resolve_bone(root, row[2])
        if pose_bone is None:
            unresolved.append(f"{record.name}: 找不到骨骼 {row[2]}")
            continue
        try:
            location = tuple(float(value) for value in row[3:6])
            rotation = tuple(math.radians(float(value)) for value in row[6:9])
        except ValueError:
            unresolved.append(f"{record.name}: 骨骼数值无效")
            continue
        converter = BoneConverter(pose_bone, 0.08)
        quaternion = Euler(rotation, "XYZ").to_quaternion()
        data = morph.data.add()
        data.bone = pose_bone.name
        data.location = converter.convert_location(location)
        data.rotation = converter.convert_rotation(
            (quaternion.x, quaternion.y, quaternion.z, quaternion.w)
        )


def _apply_material_details(root, morph, record, unresolved):
    for row in record.details:
        if len(row) < 32:
            unresolved.append(f"{record.name}: MaterialMorph 字段不足")
            continue
        material = _resolve_material(root, row[2])
        all_materials = row[2] in {"", "-1", "全材質", "全ての材質"}
        if material is None and not all_materials:
            unresolved.append(f"{record.name}: 找不到材质 {row[2]}")
            continue
        try:
            values = [float(value) for value in row[4:32]]
            offset_type = "MULT" if int(row[3]) == 0 else "ADD"
        except ValueError:
            unresolved.append(f"{record.name}: 材质数值无效")
            continue
        data = morph.data.add()
        if material is not None:
            data.material = material.name
        data.offset_type = offset_type
        data.diffuse_color = values[0:4]
        data.specular_color = values[4:7]
        data.shininess = values[7]
        data.ambient_color = values[8:11]
        data.edge_weight = values[11]
        data.edge_color = values[12:16]
        data.texture_factor = values[16:20]
        data.sphere_texture_factor = values[20:24]
        data.toon_texture_factor = values[24:28]


def _apply_group_details(morph, record, name_types):
    for row in record.details:
        if len(row) < 4:
            continue
        data = morph.data.add()
        data.name = row[2]
        candidates = name_types.get(row[2], ())
        data.morph_type = candidates[0] if candidates else "vertex_morphs"
        try:
            data.factor = float(row[3])
        except ValueError:
            data.factor = 1.0


def apply_pmx_editor_morphs(root, records):
    result = {
        "created": 0,
        "updated": 0,
        "skipped": [],
        "unresolved": [],
        "applied": [],
    }
    name_types = _morph_name_types(root, records)
    pending = []
    for record in records:
        morph_type = record.morph_type
        if morph_type not in PORTABLE_MORPH_TYPES:
            result["skipped"].append(record.name)
            continue
        collection = getattr(root.mmd_root, morph_type)
        morph = collection.get(record.name)
        if morph is None:
            morph = collection.add()
            morph.name = record.name
            result["created"] += 1
        else:
            result["updated"] += 1
        morph.name_e = record.name_e
        morph.category = CATEGORY_BY_PMX.get(record.category, "OTHER")
        _clear_collection(morph.data)
        pending.append((morph_type, morph, record))
        result["applied"].append((morph_type, morph.name))

    for morph_type, morph, record in pending:
        if morph_type == "bone_morphs":
            _apply_bone_details(root, morph, record, result["unresolved"])
        elif morph_type == "material_morphs":
            _apply_material_details(root, morph, record, result["unresolved"])
        else:
            _apply_group_details(morph, record, name_types)
    return result
