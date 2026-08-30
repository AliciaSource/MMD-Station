import math
import pathlib
import re
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

bpy.context.preferences.view.language = "zh_HANS"


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_station
import mmd_station.mmd_physics as mmd_physics_module
from mmd_station import sync as proxy_sync
from mmd_station.core import _smooth_open_column, grid_faces
from mmd_station.mmd_physics import (
    AUTO_RIGID_DEPTH_SPAN,
    AUTO_RIGID_LENGTH_SPAN,
    AUTO_RIGID_WIDTH_HALF_SPAN,
    PHYSICS_SETTING_NAMES,
    SPX_OT_AddPhysicsPreset,
    SPX_UL_MMDItems,
    _adaptive_number_text,
    _draw_active_mmd_inspector,
    _joint_interpolation_factor,
    _mmd_browser_depsgraph_update,
    _mmd_api,
    _refresh_mmd_browser_from_changes,
    _rigid_size,
    _rigid_interpolation_factor,
    _segment_geometry,
    draw_physics_settings,
)
from mmd_station.mmd_naming import standardized_bone_mmd_names
from mmd_station.mirror_physics import mirrored_name, mirrored_world_matrix
from mmd_station.physics_preview.ffi import (
    ABI_VERSION,
    SolverLibrary,
    library_path,
)
import mmd_station.physics_preview.runtime as preview_runtime
from mmd_station.physics_preview.runtime import (
    transform_to_components,
)
from bl_ext.blender_org.mmd_tools.core.model import Model
from bl_ext.blender_org.mmd_tools.core.vmd.importer import VMDImporter


def write_temporary_motion(path, bone_name, frames):
    payload = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0"))
    payload.extend(b"TimeDriverFixture".ljust(20, b"\0"))
    payload.extend(struct.pack("<I", len(frames)))
    interpolation = bytes((20, 20, 107, 107)) * 16
    encoded_bone_name = bone_name.encode("shift_jis")
    assert len(encoded_bone_name) <= 15
    for frame, location in frames:
        payload.extend(encoded_bone_name.ljust(15, b"\0"))
        payload.extend(
            struct.pack(
                "<I3f4f",
                frame,
                *location,
                0.0,
                0.0,
                0.0,
                1.0,
            )
        )
        payload.extend(interpolation)
    for _section in range(5):
        payload.extend(struct.pack("<I", 0))
    path.write_bytes(payload)


entry_source = pathlib.Path(mmd_station.__file__).read_text(encoding="utf-8")
assert "?" not in entry_source
assert mmd_station.SPX_PT_SurfaceProxyCreator.bl_label == "MMD Station"
assert mmd_station.SPX_PT_SurfaceProxyCreator.bl_category == "MMD Station"
assert not hasattr(mmd_station, "SPX_PT_MMDPhysicsBrowser")
assert not hasattr(mmd_station, "SPX_PT_MMDPhysicsPreview")

terminal_outlier_column = [
    (0.08 * factor * factor, 0.03 * factor, 1.0 - factor)
    for factor in (index / 11 for index in range(12))
]
terminal_outlier_column[-1] = (0.65, -0.45, 0.0)
fitted_terminal_column = _smooth_open_column(
    terminal_outlier_column,
    (-1.0, 1.0, -1.0, 1.0),
)
assert fitted_terminal_column[0] == terminal_outlier_column[0]
assert (
    Vector(fitted_terminal_column[-1]).xy
    - Vector(terminal_outlier_column[-1]).xy
).length > 0.25
fitted_previous_direction = (
    Vector(fitted_terminal_column[-2]).xy
    - Vector(fitted_terminal_column[-3]).xy
)
fitted_terminal_direction = (
    Vector(fitted_terminal_column[-1]).xy
    - Vector(fitted_terminal_column[-2]).xy
)
assert fitted_previous_direction.normalized().dot(
    fitted_terminal_direction.normalized()
) > 0.9999
empty_mmd_bone = SimpleNamespace(mmd_bone=SimpleNamespace(name_j="", name_e=""))
assert standardized_bone_mmd_names(empty_mmd_bone, "后发A1.R") == ("右后发A1", "后发A1_R")
assert standardized_bone_mmd_names(empty_mmd_bone, "后发A1_L") == ("左后发A1", "后发A1_L")
assert standardized_bone_mmd_names(empty_mmd_bone, "后发A1") == ("后发A1", "后发A1")


def build_source_mesh(name="MMDProxySmokeSource"):
    columns = 24
    rows = 6
    vertices = []
    faces = []
    for column in range(columns):
        angle = math.tau * column / columns
        top = 1.0 + math.sin(angle) * 0.12
        for row in range(rows):
            factor = row / (rows - 1)
            radius = 1.0 + factor * 0.35
            z = top - factor * 1.8
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
    for column in range(columns):
        following = (column + 1) % columns
        for row in range(rows - 1):
            first = column * rows + row
            second = following * rows + row
            faces.append((first, second, second + 1, first + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def build_open_source_mesh(name):
    columns = 7
    rows = 6
    vertices = []
    faces = []
    for column in range(columns):
        factor_x = column / (columns - 1)
        base_x = 3.6 + factor_x * 1.4
        base_y = 1.7 + 0.22 * math.sin((factor_x - 0.5) * math.pi)
        top = 1.1 + 0.12 * factor_x
        for row in range(rows):
            factor_z = row / (rows - 1)
            fold = math.sin(row * 2.15) * 0.16
            vertices.append(
                (
                    base_x + fold,
                    base_y + 0.05 * factor_z - fold * 0.45,
                    top - factor_z * 1.9,
                )
            )
    for column in range(columns - 1):
        for row in range(rows - 1):
            first = column * rows + row
            second = (column + 1) * rows + row
            faces.append((first, second, second + 1, first + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def build_mirror_source_mesh(name, asymmetric=False):
    columns = 4
    rows = 6
    left_vertices = []
    faces = []
    for column in range(columns):
        for row in range(rows):
            factor = row / (rows - 1)
            left_vertices.append(
                (
                    0.65 + column * 0.16 + 0.04 * math.sin(row),
                    0.28 + column * 0.05 + 0.03 * math.cos(row),
                    1.1 - factor * 1.9,
                )
            )
    vertices = left_vertices + [
        (
            -x - (0.035 * math.sin(index * 0.7) if asymmetric else 0.0),
            y + (0.025 * math.cos(index * 0.4) if asymmetric else 0.0),
            z,
        )
        for index, (x, y, z) in enumerate(left_vertices)
    ]
    side_size = len(left_vertices)
    for offset in (0, side_size):
        for column in range(columns - 1):
            for row in range(rows - 1):
                first = offset + column * rows + row
                second = offset + (column + 1) * rows + row
                faces.append((first, second, second + 1, first + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj, side_size


mmd_station.register()
assert _mmd_browser_depsgraph_update in bpy.app.handlers.depsgraph_update_post
model = Model.create("MMDProxySmoke", add_root_bone=True)
model_root = model.rootObject()
model_root.empty_display_size = 0.4
model_armature = model.armature()
anchor_bone = next(iter(model_armature.data.bones))
FnModel, FnRigidBody, rigid_module = _mmd_api()
anchor_group = FnModel.ensure_rigid_group_object(bpy.context, model_root)
anchor_rigid = FnRigidBody.new_rigid_body_objects(bpy.context, anchor_group, 1)[0]
anchor_rigid = FnRigidBody.setup_rigid_body_object(
    obj=anchor_rigid,
    shape_type=rigid_module.shapeType("BOX"),
    location=anchor_bone.head_local,
    rotation=(0.0, 0.0, 0.0),
    size=(0.2, 0.2, 0.2),
    dynamics_type=0,
    name="SmokeAnchor",
    name_e="SmokeAnchor",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=anchor_bone.name,
)
source = build_source_mesh()
source.parent = model_root
modifier = source.modifiers.new(name="MMDProxySmokeArmature", type="ARMATURE")
modifier.object = model_armature
source.select_set(True)
bpy.context.view_layer.objects.active = source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")

settings = bpy.context.scene.surface_proxy_creator
assert settings.bl_rna.properties["columns"].name == "\u5706\u5468\u65b9\u5411"
assert settings.bl_rna.properties["rows"].name == "\u6700\u5927\u9ad8\u5ea6\u5c42\u6570"
assert settings.bl_rna.properties["prefix"].default == "Skirt"
assert settings.preview_substeps == 10
assert tuple(round(value, 6) for value in settings.preview_gravity) == (0.0, 0.0, -9.8)
assert settings.rigid_shape == "BOX"
assert settings.top_rigid_type == "2"
assert settings.body_rigid_type == "1"
assert settings.topology == "CLOSED"
assert not settings.browser_filter_by_prefix
assert settings.bl_rna.properties["columns"].hard_min == 1
assert settings.auto_sync_physics
assert settings.rigid_radius_ratio == 0.0
assert settings.rigid_length_ratio == 0.0
assert settings.rigid_depth_ratio == 0.0
auto_grid = [
    [Vector((x, 0.0, 0.0)), Vector((x, 0.0, 2.0))]
    for x in (0.0, 1.0, 3.0)
]
auto_geometry = _segment_geometry(auto_grid, 1, 0, False)
auto_size = _rigid_size("BOX", auto_geometry, settings, 0.0)
assert math.isclose(auto_geometry["width"], 2.0, abs_tol=1.0e-7)
assert math.isclose(
    auto_geometry["depth"],
    min(auto_geometry["width"], auto_geometry["length"]) * AUTO_RIGID_DEPTH_SPAN,
    abs_tol=1.0e-7,
)
assert math.isclose(
    auto_size.x,
    auto_geometry["width"] * AUTO_RIGID_WIDTH_HALF_SPAN,
    abs_tol=1.0e-7,
)
assert math.isclose(
    auto_size.y,
    auto_geometry["depth"] * 0.5,
    abs_tol=1.0e-7,
)
assert math.isclose(
    auto_size.z,
    auto_geometry["length"] * AUTO_RIGID_LENGTH_SPAN * 0.5,
    abs_tol=1.0e-7,
)
assert settings.mass == 0.0
assert settings.friction == 0.0
assert tuple(settings.limit_angular_lower) == (0.0, 0.0, 0.0)
assert tuple(settings.spring_angular) == (0.0, 0.0, 0.0)
assert bpy.ops.surface_proxy.apply_stable_long_skirt_preset() == {"FINISHED"}
assert settings.rigid_shape == "BOX"
assert settings.mass == 12.0
assert settings.mass_interpolate
assert math.isclose(settings.mass_end, 1.0, abs_tol=1.0e-7)
assert math.isclose(settings.rigid_depth_ratio, 0.1, abs_tol=1.0e-7)
assert settings.rigid_depth_ratio_interpolate
assert math.isclose(settings.rigid_depth_ratio_end, 0.4, abs_tol=1.0e-7)
assert math.isclose(settings.linear_damping, 0.99, abs_tol=1.0e-7)
assert math.isclose(settings.linear_damping_end, 0.9999, abs_tol=1.0e-7)
assert math.isclose(settings.angular_damping, 0.9999, abs_tol=1.0e-7)
assert math.isclose(settings.angular_damping_end, 0.99, abs_tol=1.0e-7)
assert math.isclose(settings.friction, 0.0, abs_tol=1.0e-7)
assert math.isclose(settings.friction_end, 0.3, abs_tol=1.0e-7)
assert settings.bl_rna.properties["linear_damping"].precision == 4
assert settings.bl_rna.properties["linear_damping_end"].precision == 4
assert settings.bl_rna.properties["angular_damping"].precision == 4
assert settings.bl_rna.properties["angular_damping_end"].precision == 4
for property_name in (
    "rigid_radius_ratio",
    "rigid_length_ratio",
    "rigid_depth_ratio",
    "mass",
    "friction",
    "restitution",
    "limit_linear_lower",
    "limit_angular_lower",
    "spring_linear",
    "spring_angular",
    "horizontal_limit_linear_lower",
    "horizontal_limit_angular_lower",
    "horizontal_spring_linear",
    "horizontal_spring_angular",
):
    assert settings.bl_rna.properties[property_name].precision == 4
assert _adaptive_number_text(2.0) == "2.00"
assert _adaptive_number_text(0.99) == "0.99"
assert _adaptive_number_text(0.995) == "0.995"
assert _adaptive_number_text(0.12345) == "0.1235"
assert settings.adaptive_number_linear_damping == "0.99"
assert settings.adaptive_number_linear_damping_end == "0.9999"
settings.adaptive_number_linear_damping = "0.9876"
assert math.isclose(settings.linear_damping, 0.9876, abs_tol=1.0e-7)
settings.linear_damping = 0.99
assert settings.adaptive_number_limit_angular_lower_0 == "0.00°"
settings.adaptive_number_limit_angular_lower_0 = "-8.125°"
assert math.isclose(
    math.degrees(settings.limit_angular_lower[0]), -8.125, abs_tol=1.0e-4
)
settings.limit_angular_lower[0] = 0.0
assert settings.collision_group_number == 5
assert settings.collision_group_mask[5]
assert sum(bool(value) for value in settings.collision_group_mask) == 1
assert tuple(settings.limit_angular_lower) == (0.0, 0.0, 0.0)
assert tuple(settings.limit_angular_upper) == (0.0, 0.0, 0.0)
assert tuple(settings.limit_angular_lower_end) == (0.0, 0.0, 0.0)
assert tuple(settings.limit_angular_upper_end) == (0.0, 0.0, 0.0)
assert tuple(settings.limit_angular_interpolate) == (False, False, False)
assert tuple(settings.spring_linear) == (0.0, 0.0, 0.0)
assert tuple(settings.spring_linear_end) == (0.0, 0.0, 0.0)
assert tuple(settings.spring_linear_interpolate) == (False, False, False)
assert tuple(settings.spring_angular) == (12.0, 5.0, 5.0)
assert tuple(settings.spring_angular_end) == (4.0, 2.0, 2.0)
assert tuple(settings.spring_angular_interpolate) == (True, True, True)
assert tuple(settings.horizontal_limit_linear_lower) == (0.0, 0.0, 0.0)
assert tuple(settings.horizontal_limit_linear_upper) == (0.0, 0.0, 0.0)
assert tuple(settings.horizontal_limit_linear_lower_end) == (0.0, 0.0, 0.0)
assert tuple(settings.horizontal_limit_linear_upper_end) == (0.0, 0.0, 0.0)
assert tuple(settings.horizontal_limit_linear_interpolate) == (False, False, False)
assert tuple(round(math.degrees(value)) for value in settings.horizontal_limit_angular_upper) == (10, 3, 5)
assert tuple(round(math.degrees(value)) for value in settings.horizontal_limit_angular_upper_end) == (18, 5, 12)
assert tuple(settings.horizontal_limit_angular_interpolate) == (True, True, True)
assert tuple(settings.horizontal_spring_linear) == (0.0, 0.0, 0.0)
assert tuple(settings.horizontal_spring_linear_end) == (0.0, 40.0, 0.0)
assert tuple(settings.horizontal_spring_linear_interpolate) == (False, False, False)
assert tuple(round(value, 4) for value in settings.horizontal_spring_angular) == (0.8, 1.5, 4.0)
assert tuple(round(value, 4) for value in settings.horizontal_spring_angular_end) == (0.25, 0.5, 1.5)
assert SPX_OT_AddPhysicsPreset.preset_values == [
    f"settings.{name}" for name in PHYSICS_SETTING_NAMES
]
for name in PHYSICS_SETTING_NAMES:
    settings.property_unset(name)
settings.columns = 12
settings.rows = 5
settings.prefix = "SmokeProxy"
settings.armature = model_armature
settings.parent_bone = anchor_bone.name
settings.write_weights = False
result = bpy.ops.surface_proxy.create_skirt_proxy()
assert result == {"FINISHED"}, result

proxy = bpy.data.objects["SmokeProxy_Surface"]
proxy_collection = bpy.data.collections["MMD Station Proxies"]
assert tuple(proxy.users_collection) == (proxy_collection,)
armature = bpy.data.objects[proxy["surface_proxy_armature"]]
generated_bones = [
    pose_bone
    for pose_bone in armature.pose.bones
    if pose_bone.name.startswith("SmokeProxy_C")
]
assert generated_bones
assert all(pose_bone.mmd_bone.name_j == pose_bone.name for pose_bone in generated_bones)
assert all(pose_bone.mmd_bone.name_e == pose_bone.name for pose_bone in generated_bones)
row_counts = list(proxy["surface_proxy_column_rows"])
top_vertices = []
offset = 0
for column, count in enumerate(row_counts):
    top = proxy.data.vertices[offset].co.copy()
    top_vertices.append(top)
    root_bone = armature.data.bones[f"SmokeProxy_C{column + 1:02d}_R01"]
    assert (root_bone.head_local - top).length < 1.0e-7
    offset += count

top_range = max(vertex.z for vertex in top_vertices) - min(
    vertex.z for vertex in top_vertices
)
assert top_range > 0.20, top_range
assert not hasattr(bpy.types.Object, "mmd_nova_physics_tree")

bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.objects.active = proxy
settings.mmd_root = model_root
settings.browser_kind = "BONE"


class _FakeDepsgraphUpdate:
    def __init__(self, data):
        self.id = data


class _FakeDepsgraph:
    def __init__(self, *data_blocks):
        self.updates = [_FakeDepsgraphUpdate(data) for data in data_blocks]


unrelated_refresh_probe = bpy.data.objects.new("UnrelatedRefreshProbe", None)
bpy.context.collection.objects.link(unrelated_refresh_probe)
mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY = False
settings.workspace_tab = "BROWSER"
_mmd_browser_depsgraph_update(
    bpy.context.scene,
    _FakeDepsgraph(unrelated_refresh_probe),
)
assert not mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY
assert not bpy.app.timers.is_registered(
    mmd_physics_module._run_mmd_browser_auto_refresh
)

settings.workspace_tab = "PROXY"
_mmd_browser_depsgraph_update(
    bpy.context.scene,
    _FakeDepsgraph(model_armature.data),
)
assert mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY
assert not bpy.app.timers.is_registered(
    mmd_physics_module._run_mmd_browser_auto_refresh
)

mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY = False
settings.preview_running = True
settings.workspace_tab = "BROWSER"
_mmd_browser_depsgraph_update(
    bpy.context.scene,
    _FakeDepsgraph(model_armature),
)
assert not mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY
assert not bpy.app.timers.is_registered(
    mmd_physics_module._run_mmd_browser_auto_refresh
)

settings.preview_running = False
_mmd_browser_depsgraph_update(
    bpy.context.scene,
    _FakeDepsgraph(model_armature),
)
assert mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY
assert bpy.app.timers.is_registered(
    mmd_physics_module._run_mmd_browser_auto_refresh
)
bpy.app.timers.unregister(mmd_physics_module._run_mmd_browser_auto_refresh)
mmd_physics_module._BROWSER_AUTO_REFRESH_DIRTY = False
settings.workspace_tab = "PROXY"
bpy.data.objects.remove(unrelated_refresh_probe, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
assert bpy.ops.object.mode_set(mode="EDIT") == {"FINISHED"}
dot_side_bone = armature.data.edit_bones.new("后发测试.R")
dot_side_bone.head = (0.0, 0.0, 2.0)
dot_side_bone.tail = (0.0, 0.0, 2.1)
dot_mirror_bone = armature.data.edit_bones.new("后发测试.L")
dot_mirror_bone.head = (-0.1, 0.0, 2.0)
dot_mirror_bone.tail = (-0.1, 0.0, 2.1)
underscore_side_bone = armature.data.edit_bones.new("后发测试_L")
underscore_side_bone.head = (0.1, 0.0, 2.0)
underscore_side_bone.tail = (0.1, 0.0, 2.1)
underscore_mirror_bone = armature.data.edit_bones.new("后发测试_R")
underscore_mirror_bone.head = (0.2, 0.0, 2.0)
underscore_mirror_bone.tail = (0.2, 0.0, 2.1)
prefix_left_bone = armature.data.edit_bones.new("前缀测试A")
prefix_left_bone.head = (0.3, 0.0, 2.0)
prefix_left_bone.tail = (0.3, 0.0, 2.1)
prefix_right_bone = armature.data.edit_bones.new("前缀测试B")
prefix_right_bone.head = (0.4, 0.0, 2.0)
prefix_right_bone.tail = (0.4, 0.0, 2.1)
assert bpy.ops.object.mode_set(mode="OBJECT") == {"FINISHED"}
anchor_bone = model_armature.data.bones[anchor_rigid.mmd_rigid.bone]
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
first_bone = armature.pose.bones["SmokeProxy_C02_R01"]
second_bone = armature.pose.bones["SmokeProxy_C02_R02"]
dot_side_bone = armature.pose.bones["后发测试.R"]
dot_mirror_bone = armature.pose.bones["后发测试.L"]
underscore_side_bone = armature.pose.bones["后发测试_L"]
underscore_mirror_bone = armature.pose.bones["后发测试_R"]
prefix_left_bone = armature.pose.bones["前缀测试A"]
prefix_right_bone = armature.pose.bones["前缀测试B"]
first_bone.mmd_bone.name_j = ""
first_bone.mmd_bone.name_e = ""
second_bone.mmd_bone.name_j = "保留名称"
second_bone.mmd_bone.name_e = "PreservedName"
dot_side_bone.mmd_bone.name_j = ""
dot_side_bone.mmd_bone.name_e = ""
underscore_side_bone.mmd_bone.name_j = "WrongName_R"
underscore_side_bone.mmd_bone.name_e = "WrongName.R"
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
for item in settings.browser_items:
    item.selected = item.target_name in {first_bone.name, dot_side_bone.name}
assert bpy.ops.surface_proxy.fill_missing_mmd_bone_names(scope="CHECKED") == {"FINISHED"}
assert first_bone.mmd_bone.name_j == first_bone.name
assert first_bone.mmd_bone.name_e == first_bone.name
assert dot_side_bone.mmd_bone.name_j == "右后发测试"
assert dot_side_bone.mmd_bone.name_e == "后发测试_R"
assert underscore_side_bone.mmd_bone.name_j == "WrongName_R"
assert underscore_side_bone.mmd_bone.name_e == "WrongName.R"
assert second_bone.mmd_bone.name_j == "保留名称"
assert second_bone.mmd_bone.name_e == "PreservedName"
assert bpy.ops.surface_proxy.fill_missing_mmd_bone_names(scope="ALL") == {"FINISHED"}
assert second_bone.mmd_bone.name_j == "保留名称"
assert second_bone.mmd_bone.name_e == "PreservedName"
assert underscore_side_bone.mmd_bone.name_j == "左后发测试"
assert underscore_side_bone.mmd_bone.name_e == "后发测试_L"
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == dot_side_bone.name
)
dot_side_bone.mmd_bone.name_j = "左髪_L"
dot_side_bone.mmd_bone.name_e = "Hair_L"
assert bpy.ops.surface_proxy.fill_missing_mmd_bone_names(scope="ACTIVE") == {"FINISHED"}
assert dot_side_bone.mmd_bone.name_j == "右髪"
assert dot_side_bone.mmd_bone.name_e == "Hair_R"
prefix_left_bone.mmd_bone.name_j = "左前缀测试"
prefix_left_bone.mmd_bone.name_e = "PrefixTest_L"
prefix_right_bone.mmd_bone.name_j = "右前缀测试"
prefix_right_bone.mmd_bone.name_e = "PrefixTest_R"
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
mirror_sources = {
    dot_side_bone.name,
    underscore_side_bone.name,
    prefix_left_bone.name,
}
for item in settings.browser_items:
    item.selected = item.target_name in mirror_sources
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="MIRROR") == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == mirror_sources | {
    dot_mirror_bone.name,
    underscore_mirror_bone.name,
    prefix_right_bone.name,
}
settings.create_horizontal_joints = True
settings.rigid_shape = "BOX"
settings.rigid_radius_ratio = 0.2
settings.rigid_radius_ratio_interpolate = True
settings.rigid_radius_ratio_end = 0.4
settings.rigid_radius_multiply = True
settings.rigid_length_ratio = 0.5
settings.rigid_depth_ratio = 0.1
settings.mass = 1.0
settings.mass_interpolate = True
settings.mass_end = 3.0
settings.spring_angular = (3.0, 4.0, 5.0)
settings.spring_angular_interpolate = (True, False, True)
settings.spring_angular_end = (6.0, 8.0, 10.0)
settings.horizontal_spring_angular = (8.0, 9.0, 10.0)
settings.horizontal_spring_angular_interpolate = (True, False, True)
settings.horizontal_spring_angular_end = (12.0, 14.0, 16.0)
result = bpy.ops.surface_proxy.create_mmd_physics()
assert result == {"FINISHED"}, result
physics_objects = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == proxy.name
]
rigids = [obj for obj in physics_objects if obj.mmd_type == "RIGID_BODY"]
joints = [obj for obj in physics_objects if obj.mmd_type == "JOINT"]
assert all(not model_armature.data.bones[obj.mmd_rigid.bone].use_connect for obj in rigids)
expected_rigids = sum(count - 1 for count in row_counts)
expected_vertical = sum(max(count - 2, 0) for count in row_counts)
expected_anchors = len(row_counts)
expected_horizontal = sum(
    max(min(row_counts[column], row_counts[(column + 1) % len(row_counts)]) - 1, 0)
    for column in range(len(row_counts))
)
assert len(rigids) == expected_rigids, (len(rigids), expected_rigids)
assert settings.preview_scope == "CURRENT_PROXY"
assert settings.preview_solver_target == "MMD"
unrelated_rigid = FnRigidBody.new_rigid_body_objects(
    bpy.context,
    anchor_group,
    1,
)[0]
unrelated_rigid = FnRigidBody.setup_rigid_body_object(
    obj=unrelated_rigid,
    shape_type=rigid_module.shapeType("SPHERE"),
    location=anchor_bone.head_local + Vector((0.0, 0.0, 3.0)),
    rotation=(0.0, 0.0, 0.0),
    size=(0.2, 0.0, 0.0),
    dynamics_type=1,
    name="UnrelatedDynamicRigid",
    name_e="UnrelatedDynamicRigid",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=anchor_bone.name,
)
bpy.context.view_layer.update()
unrelated_matrix = unrelated_rigid.matrix_world.copy()
preview_library = SolverLibrary(target="MMD")
pmx_preview_library = SolverLibrary(target="PMX")
assert library_path("MMD").name == "mmd_physics_solver_mmd_abi5.dll"
assert library_path("PMX").name == "mmd_physics_solver_abi5.dll"
assert preview_library.dll.mmd_solver_abi_version() == ABI_VERSION
assert pmx_preview_library.dll.mmd_solver_abi_version() == ABI_VERSION
settings.preview_frequency = 60
settings.preview_substeps = 2
settings.top_rigid_type = "2"
settings.body_rigid_type = "2"
for obj in physics_objects:
    for key in [name for name in obj.keys() if name.startswith("surface_proxy_")]:
        del obj[key]
protected_rigid = rigids[0]
protected_location = protected_rigid.location + Vector((0.12, -0.08, 0.04))
protected_rotation = Euler((0.11, -0.22, 0.33), "XYZ")
protected_size_input = Vector((0.31, 0.27, 0.43))
protected_mask_input = [index in {2, 7, 11} for index in range(16)]
protected_rigid.location = protected_location
protected_rigid.rotation_euler = protected_rotation
protected_rigid.mmd_rigid.shape = "SPHERE"
protected_rigid.mmd_rigid.size = protected_size_input
protected_rigid.mmd_rigid.type = "0"
protected_rigid.mmd_rigid.collision_group_number = 11
protected_rigid.mmd_rigid.collision_group_mask = protected_mask_input
protected_rigid.rigid_body.mass = 9.25
protected_rigid.rigid_body.friction = 0.17
protected_rigid.rigid_body.restitution = 0.23
protected_rigid.rigid_body.linear_damping = 0.37
protected_rigid.rigid_body.angular_damping = 0.41
protected_joint = joints[0]
protected_joint.location += Vector((-0.09, 0.07, 0.13))
protected_joint.rotation_euler = Euler((-0.14, 0.19, -0.27), "XYZ")
protected_constraint = protected_joint.rigid_body_constraint
protected_constraint.limit_lin_x_lower = -0.12
protected_constraint.limit_lin_x_upper = 0.23
protected_constraint.limit_ang_z_lower = -0.34
protected_constraint.limit_ang_z_upper = 0.45
protected_joint.mmd_joint.spring_linear = (7.1, 7.2, 7.3)
protected_joint.mmd_joint.spring_angular = (8.1, 8.2, 8.3)
bpy.context.view_layer.update()
protected_location = protected_rigid.location.copy()
protected_rotation = protected_rigid.rotation_euler.copy()
protected_size = Vector(protected_rigid.mmd_rigid.size)
protected_mask = list(protected_rigid.mmd_rigid.collision_group_mask)
protected_joint_location = protected_joint.location.copy()
protected_joint_rotation = protected_joint.rotation_euler.copy()
protected_joint_limits = (
    protected_constraint.limit_lin_x_lower,
    protected_constraint.limit_lin_x_upper,
    protected_constraint.limit_ang_z_lower,
    protected_constraint.limit_ang_z_upper,
)
protected_joint_spring_linear = tuple(protected_joint.mmd_joint.spring_linear)
protected_joint_spring_angular = tuple(protected_joint.mmd_joint.spring_angular)
for name in (
    "protect_apply_location",
    "protect_apply_rotation",
    "protect_apply_joint_location",
    "protect_apply_joint_rotation",
    "protect_apply_shape",
    "protect_apply_size",
    "protect_apply_type",
    "protect_apply_dynamics",
    "protect_apply_collision",
    "protect_apply_joint_parameters",
):
    setattr(settings, name, True)
settings.create_horizontal_joints = False
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert sum(
    obj.get("surface_proxy_object") == proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    for obj in bpy.data.objects
) == expected_horizontal
assert (protected_rigid.location - protected_location).length < 1.0e-7
assert all(
    abs(first - second) < 1.0e-7
    for first, second in zip(protected_rigid.rotation_euler, protected_rotation)
)
assert protected_rigid.mmd_rigid.shape == "SPHERE"
assert (Vector(protected_rigid.mmd_rigid.size) - protected_size).length < 1.0e-7
assert int(protected_rigid.mmd_rigid.type) == 0
assert protected_rigid.mmd_rigid.collision_group_number == 11
assert list(protected_rigid.mmd_rigid.collision_group_mask) == protected_mask
assert abs(protected_rigid.rigid_body.mass - 9.25) < 1.0e-7
assert abs(protected_rigid.rigid_body.friction - 0.17) < 1.0e-7
assert abs(protected_rigid.rigid_body.restitution - 0.23) < 1.0e-7
assert abs(protected_rigid.rigid_body.linear_damping - 0.37) < 1.0e-7
assert abs(protected_rigid.rigid_body.angular_damping - 0.41) < 1.0e-7
assert (protected_joint.location - protected_joint_location).length < 1.0e-7
assert all(
    abs(first - second) < 1.0e-7
    for first, second in zip(
        protected_joint.rotation_euler,
        protected_joint_rotation,
    )
)
assert (
    protected_constraint.limit_lin_x_lower,
    protected_constraint.limit_lin_x_upper,
    protected_constraint.limit_ang_z_lower,
    protected_constraint.limit_ang_z_upper,
) == protected_joint_limits
assert tuple(protected_joint.mmd_joint.spring_linear) == protected_joint_spring_linear
assert tuple(protected_joint.mmd_joint.spring_angular) == protected_joint_spring_angular
for name in (
    "protect_apply_location",
    "protect_apply_rotation",
    "protect_apply_joint_location",
    "protect_apply_joint_rotation",
    "protect_apply_shape",
    "protect_apply_size",
    "protect_apply_type",
    "protect_apply_dynamics",
    "protect_apply_collision",
    "protect_apply_joint_parameters",
):
    setattr(settings, name, False)
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert not any(
    obj.get("surface_proxy_object") == proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    for obj in bpy.data.objects
)
assert (protected_rigid.location - protected_location).length > 1.0e-4
assert protected_rigid.mmd_rigid.shape == "BOX"
assert int(protected_rigid.mmd_rigid.type) == 2
assert abs(protected_rigid.rigid_body.mass - 1.0) < 1.0e-7
assert (protected_joint.location - protected_joint_location).length > 1.0e-4
assert tuple(protected_joint.mmd_joint.spring_angular) != protected_joint_spring_angular
settings.create_horizontal_joints = True
missing_endpoint_rigid = max(
    (
        obj
        for obj in rigids
        if obj.get("surface_proxy_role") == "RIGID"
        and int(obj.get("surface_proxy_column", -1)) == 0
    ),
    key=lambda obj: int(obj.get("surface_proxy_row", -1)),
)
missing_endpoint_bone = missing_endpoint_rigid.mmd_rigid.bone
for key in [
    name for name in missing_endpoint_rigid.keys() if name.startswith("surface_proxy_")
]:
    del missing_endpoint_rigid[key]
missing_endpoint_rigid.mmd_rigid.bone = ""
missing_horizontal_count = sum(
    0 in pair
    for pair in mmd_physics_module._column_pairs(
        mmd_physics_module._column_groups(proxy, len(row_counts)),
        bool(proxy.get("surface_proxy_closed", True)),
    )
)
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert sum(
    obj.get("surface_proxy_object") == proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    for obj in bpy.data.objects
) == expected_horizontal - missing_horizontal_count
missing_endpoint_rigid.mmd_rigid.bone = missing_endpoint_bone
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert sum(
    obj.get("surface_proxy_object") == proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    for obj in bpy.data.objects
) == expected_horizontal
physics_objects = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == proxy.name
]
rigids = [obj for obj in physics_objects if obj.mmd_type == "RIGID_BODY"]
joints = [obj for obj in physics_objects if obj.mmd_type == "JOINT"]
# Keep this runtime-alignment fixture above MMD's native Y=0 ground plane.
preview_fixture_root_matrix = model_root.matrix_world.copy()
model_root.location.z += 2.0
bpy.context.view_layer.update()
unrelated_matrix = unrelated_rigid.matrix_world.copy()
preview_bone = model_armature.pose.bones[rigids[-1].mmd_rigid.bone]
preview_basis = preview_bone.matrix_basis.copy()
anchor_pose_bone = model_armature.pose.bones[anchor_bone.name]
anchor_pose_bone.matrix_basis = Matrix.Translation(Vector((0.001, 0.0, 0.0)))
bpy.context.view_layer.update()
anchor_basis = anchor_pose_bone.matrix_basis.copy()
preview_initial_bones = {
    pose_bone.name: pose_bone.matrix.copy()
    for pose_bone in generated_bones
}
preview_initial_positions = {
    rigid.name: rigid.matrix_world.translation.copy() for rigid in rigids
}
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
preview_session = preview_runtime._ACTIVE_SESSIONS[model_root.name]
assert preview_session is not None
assert len(preview_session.rigids) == expected_rigids + 1
assert preview_session.dynamic_rigid_count == expected_rigids
assert unrelated_rigid not in preview_session.rigids
assert preview_session.unanchored_dynamic_components == ()

original_tick = preview_session.tick
snapshot_pose = {
    name: matrix.copy()
    for name, matrix in preview_session.saved_pose_basis.items()
}
snapshot_rigids = {
    name: matrix.copy()
    for name, matrix in preview_session.saved_rigid_matrices.items()
}
snapshot_joints = {
    name: matrix.copy()
    for name, matrix in preview_session.saved_joint_matrices.items()
}
assert unrelated_rigid.name in snapshot_rigids

anchor_pose_bone.matrix_basis = Matrix.Translation(Vector((2.0, 0.0, 0.0)))
preview_session.rigids[-1].matrix_world.translation += Vector((3.0, 0.0, 0.0))
preview_session.joints[-1].matrix_world.translation += Vector((4.0, 0.0, 0.0))
bpy.context.view_layer.update()


def fail_preview_tick_once():
    raise RuntimeError("synthetic recoverable tick failure")


preview_session.tick = fail_preview_tick_once
assert preview_runtime._timer_tick() is not None
assert preview_runtime._ACTIVE_SESSIONS[model_root.name] is preview_session
assert settings.preview_running
assert settings.preview_status.startswith("运行中：异常后已恢复启动快照")
assert all(
    model_armature.pose.bones[name].matrix_basis == matrix
    for name, matrix in snapshot_pose.items()
)
rigid_snapshot_errors = {
    name: max(
        abs(bpy.data.objects[name].matrix_world[row][column] - matrix[row][column])
        for row in range(4)
        for column in range(4)
    )
    for name, matrix in snapshot_rigids.items()
}
joint_snapshot_errors = {
    name: max(
        abs(bpy.data.objects[name].matrix_world[row][column] - matrix[row][column])
        for row in range(4)
        for column in range(4)
    )
    for name, matrix in snapshot_joints.items()
}
assert max(rigid_snapshot_errors.values()) < 1.0e-6, sorted(
    rigid_snapshot_errors.items(), key=lambda item: item[1], reverse=True
)[:5]
assert max(joint_snapshot_errors.values()) < 1.0e-6, sorted(
    joint_snapshot_errors.items(), key=lambda item: item[1], reverse=True
)[:5]
preview_session.tick = original_tick
assert preview_runtime._timer_tick() is not None
assert preview_session.consecutive_tick_failures == 0


def fail_solver_rebuild():
    raise RuntimeError("synthetic snapshot rebuild failure")


original_world_reset = preview_session.world.reset
preview_session.tick = fail_preview_tick_once
preview_session.world.reset = fail_solver_rebuild
assert preview_runtime._timer_tick() is not None
assert preview_runtime._ACTIVE_SESSIONS[model_root.name] is preview_session
assert settings.preview_running
assert settings.preview_status.startswith("运行中：启动快照恢复失败，将继续重试")
assert bpy.app.timers.is_registered(preview_runtime._timer_tick)
preview_session.tick = original_tick
preview_session.world.reset = original_world_reset
assert preview_runtime._timer_tick() is not None
assert not preview_session.snapshot_reset_pending
assert settings.preview_status.startswith("运行中：已恢复启动快照并继续物理")

solver_before_rna_rebind = preview_session.solver
preview_session.root = object()
preview_session.armature = object()
preview_session.rigids = [object() for _name in preview_session.rigid_names]
preview_session.joints = [object() for _name in preview_session.joint_names]
assert preview_runtime._timer_tick() is not None
assert preview_session.root is bpy.data.objects[preview_session.root_name]
assert preview_session.armature is bpy.data.objects[preview_session.armature_name]
assert all(
    rigid is bpy.data.objects[name]
    for rigid, name in zip(preview_session.rigids, preview_session.rigid_names)
)
assert all(
    joint is bpy.data.objects[name]
    for joint, name in zip(preview_session.joints, preview_session.joint_names)
)
assert preview_session.solver is not solver_before_rna_rebind
assert preview_runtime._ACTIVE_SESSIONS[model_root.name] is preview_session
assert settings.preview_running
reset_count_before_clear = preview_session.auto_reset_count


def assert_preview_alignment(session):
    body_transforms = session.solver.transforms()
    bone_transforms = session.solver.bone_transforms()
    for index, rigid in enumerate(session.rigids):
        body_position, _body_rotation = transform_to_components(body_transforms[index])
        expected_body_position = Vector(body_position) * session.import_scale
        pose_bone = session.armature.pose.bones.get(rigid.mmd_rigid.bone)
        assert (rigid.matrix_world.translation - expected_body_position).length < 1.0e-6
        if session.bone_drivers.get(rigid.mmd_rigid.bone) != index:
            continue
        pose_bone = session.armature.pose.bones.get(rigid.mmd_rigid.bone)
        if pose_bone is None:
            continue
        bone_position, bone_rotation = transform_to_components(bone_transforms[index])
        bone_world = session.armature.matrix_world @ pose_bone.matrix
        if int(rigid.mmd_rigid.type) == 2:
            expected_rotation = Quaternion(bone_rotation)
            rotation_error = bone_world.to_quaternion().rotation_difference(expected_rotation).angle
            rotation_error = min(rotation_error, abs(math.tau - rotation_error))
            assert rotation_error < 2.0e-3, (pose_bone.name, rotation_error)
        else:
            expected_bone_position = Vector(bone_position) * session.import_scale
            assert (bone_world.translation - expected_bone_position).length < 1.0e-5
    for joint, state in zip(session.joints, session.solver.joint_states()):
        position_a, _rotation_a = transform_to_components(state.frame_a)
        position_b, _rotation_b = transform_to_components(state.frame_b)
        midpoint = (
            (Vector(position_a) + Vector(position_b))
            * (0.5 * session.import_scale)
        )
        assert (joint.matrix_world.translation - midpoint).length < 1.0e-6


for _step in range(180):
    preview_session.tick()
    assert_preview_alignment(preview_session)
preview_max_displacement = max(
    (rigid.matrix_world.translation - preview_initial_positions[rigid.name]).length
    for rigid in rigids
)
preview_max_bone_deviation = max(
    (
        preview_initial_bones[pose_bone.name].inverted_safe()
        @ pose_bone.matrix
    ).translation.length
    + (
        preview_initial_bones[pose_bone.name].inverted_safe()
        @ pose_bone.matrix
    ).to_quaternion().angle
    for pose_bone in generated_bones
)
assert preview_max_displacement < 0.2, preview_max_displacement
assert preview_max_bone_deviation < 0.5, preview_max_bone_deviation
solver_before_clear = preview_session.solver
for pose_bone in model_armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()
preview_session.tick()
assert preview_session.auto_reset_count == reset_count_before_clear + 1
assert preview_session.solver is not solver_before_clear
assert preview_runtime._ACTIVE_SESSIONS[model_root.name] is preview_session
assert settings.preview_running
assert_preview_alignment(preview_session)
solver_before_manual_reset = preview_session.solver
assert bpy.ops.surface_proxy.reset_mmd_physics_preview() == {"FINISHED"}
assert preview_runtime._ACTIVE_SESSIONS[model_root.name] is preview_session
assert preview_session.solver is not solver_before_manual_reset

root_matrix_before_move = model_root.matrix_world.copy()
root_delta = Matrix.Translation(Vector((0.75, -0.4, 0.25))) @ Matrix.Rotation(
    math.radians(20.0),
    4,
    "Z",
)
model_root.matrix_world = root_delta @ root_matrix_before_move
bpy.context.view_layer.update()
assert bpy.ops.surface_proxy.reset_mmd_physics_preview() == {"FINISHED"}
expected_root_delta = (
    model_root.matrix_world @ preview_session.saved_root_matrix.inverted_safe()
)
assert max(
    max(
        abs(
            rigid.matrix_world[row][column]
            - (expected_root_delta @ preview_session.saved_rigid_matrices[rigid.name])[row][column]
        )
        for row in range(4)
        for column in range(4)
    )
    for rigid in preview_session.rigids
) < 1.0e-5
assert max(
    max(
        abs(
            joint.matrix_world[row][column]
            - (expected_root_delta @ preview_session.saved_joint_matrices[joint.name])[row][column]
        )
        for row in range(4)
        for column in range(4)
    )
    for joint in preview_session.joints
) < 1.0e-5
model_root.matrix_world = root_matrix_before_move
bpy.context.view_layer.update()
assert bpy.ops.surface_proxy.reset_mmd_physics_preview() == {"FINISHED"}

saved_frame = bpy.context.scene.frame_current
saved_fps = bpy.context.scene.render.fps
saved_fps_base = bpy.context.scene.render.fps_base
saved_action = (
    model_armature.animation_data.action
    if model_armature.animation_data is not None
    else None
)
saved_is_playing = preview_runtime._scene_is_playing
motion_frames = (
    (0, (0.0, 0.0, 0.0)),
    (1, (0.02, 0.0, 0.0)),
    (3, (0.08, 0.0, 0.0)),
    (6, (0.08, 0.0, 0.0)),
    (10, (-0.04, 0.0, 0.0)),
)


def run_imported_motion(wall_times):
    preview_session.world.reset()
    original_broad_pose_reset = preview_session._broad_pose_reset_detected
    preview_session._broad_pose_reset_detected = lambda: False
    recorded_steps = []
    solver = preview_session.world.solver

    class RecordingSolver:
        def __getattr__(self, name):
            return getattr(solver, name)

        def step(self, step_seconds, max_substeps):
            recorded_steps.append((step_seconds, max_substeps))
            return solver.step(step_seconds, max_substeps)

    recording_solver = RecordingSolver()
    preview_session.world.solver = recording_solver
    preview_session.solver = recording_solver
    bpy.context.scene.frame_set(-1)
    bpy.context.scene.frame_set(0)
    trajectory = []
    for (frame, _location), wall_seconds in zip(motion_frames, wall_times):
        bpy.context.scene.frame_set(frame)
        assert preview_runtime._timer_tick(wall_seconds) is not None
        trajectory.append(
            tuple(
                tuple(transform_to_components(transform)[0])
                + tuple(transform_to_components(transform)[1])
                for transform in recording_solver.transforms()
            )
        )
    preview_session._broad_pose_reset_detected = original_broad_pose_reset
    return tuple(recorded_steps), tuple(trajectory)


with tempfile.TemporaryDirectory(prefix="mmd-preview-vmd-") as temporary_directory:
    motion_path = pathlib.Path(temporary_directory) / "time_driver_fixture.vmd"
    write_temporary_motion(motion_path, anchor_pose_bone.name, motion_frames)
    bpy.context.scene.frame_set(0)
    bpy.context.scene.render.fps = 30
    bpy.context.scene.render.fps_base = 1.0
    VMDImporter(
        filepath=str(motion_path),
        scale=1.0,
        frame_margin=0,
    ).assign(model_armature, action_name="TimeDriverFixture")
    preview_runtime._scene_is_playing = lambda _scene: True
    settings.preview_substeps = 10
    first_steps, first_trajectory = run_imported_motion(
        (10.000, 10.004, 10.071, 10.076, 10.200)
    )
    expected_steps = (1.0 / 60.0, 1.0 / 30.0, 2.0 / 30.0, 3.0 / 30.0, 4.0 / 30.0)
    assert all(max_substeps == 10 for _seconds, max_substeps in first_steps)
    assert all(
        abs(actual[0] - expected) < 1.0e-7
        for actual, expected in zip(first_steps, expected_steps)
    )
    assert all(
        math.isfinite(value)
        for frame in first_trajectory
        for body in frame
        for value in body
    )
    motion_response = max(
        abs(first_value - last_value)
        for first_body, last_body in zip(first_trajectory[0], first_trajectory[-1])
        for first_value, last_value in zip(first_body[:3], last_body[:3])
    )
    assert motion_response > 1.0e-5, motion_response
    assert motion_path.exists()

assert not motion_path.exists()
preview_runtime._scene_is_playing = saved_is_playing
settings.preview_substeps = 2
bpy.context.scene.render.fps = saved_fps
bpy.context.scene.render.fps_base = saved_fps_base
bpy.context.scene.frame_set(saved_frame)
if model_armature.animation_data is not None:
    test_action = model_armature.animation_data.action
    model_armature.animation_data.action = saved_action
    if test_action is not None and test_action is not saved_action:
        bpy.data.actions.remove(test_action)
preview_session.world.reset()

anchor_rigid_index = next(
    index
    for index, rigid in enumerate(preview_session.rigids)
    if int(rigid.mmd_rigid.type) == 0
    and rigid.mmd_rigid.bone == anchor_pose_bone.name
)
anchor_pose_bone.matrix_basis = anchor_basis @ Matrix.Translation(
    Vector((0.02, 0.0, 0.0))
)
bpy.context.view_layer.update()
expected_anchor_rigid = (
    model_armature.matrix_world
    @ anchor_pose_bone.matrix
    @ preview_session.bone_offsets[anchor_rigid_index]
)
preview_session.tick()
assert (
    preview_session.rigids[anchor_rigid_index].matrix_world.translation
    - expected_anchor_rigid.translation
).length < 1.0e-5
previous_positions = [rigid.matrix_world.translation.copy() for rigid in rigids]
preview_max_step = 0.0
for step in range(120):
    phase = 2.0 * math.pi * step / 60.0
    anchor_pose_bone.matrix_basis = anchor_basis @ Matrix.Translation(
        Vector((0.05 * math.sin(phase), 0.0, 0.0))
    )
    preview_session.tick()
    assert_preview_alignment(preview_session)
    current_positions = [rigid.matrix_world.translation.copy() for rigid in rigids]
    preview_max_step = max(
        preview_max_step,
        *(
            (current - previous).length
            for current, previous in zip(current_positions, previous_positions)
        ),
    )
    assert all(
        math.isfinite(value)
        for position in current_positions
        for value in position
    )
    previous_positions = current_positions
assert preview_max_step < 0.1, preview_max_step
preview_saved_pose = {
    name: matrix_basis.copy()
    for name, matrix_basis in preview_session.saved_pose_basis.items()
}
for pose_bone in model_armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()
assert bpy.ops.surface_proxy.stop_mmd_physics_preview() == {"FINISHED"}
assert not preview_runtime._ACTIVE_SESSIONS
assert preview_bone.matrix_basis == preview_basis
assert anchor_pose_bone.matrix_basis == anchor_basis
assert all(
    model_armature.pose.bones[name].matrix_basis == matrix_basis
    for name, matrix_basis in preview_saved_pose.items()
)
assert unrelated_rigid.matrix_world == unrelated_matrix
settings.preview_scope = "MODEL"
model_root.spx_physics_preview_selected = True
second_model = Model.create("MMDProxySmoke010", add_root_bone=True)
second_root = second_model.rootObject()
second_root.empty_display_size = 0.5
second_armature = second_model.armature()
second_bone = next(iter(second_armature.data.bones))
second_group = FnModel.ensure_rigid_group_object(bpy.context, second_root)
second_rigid = FnRigidBody.new_rigid_body_objects(bpy.context, second_group, 1)[0]
FnRigidBody.setup_rigid_body_object(
    obj=second_rigid,
    shape_type=rigid_module.shapeType("BOX"),
    location=second_bone.head_local,
    rotation=(0.0, 0.0, 0.0),
    size=(0.02, 0.02, 0.02),
    dynamics_type=0,
    name="SmokeAnchor010",
    name_e="SmokeAnchor010",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=second_bone.name,
)
second_root.spx_physics_preview_selected = True
assert preview_runtime.model_scale_info(second_root) == (0.1, 10.0, False)
second_root.spx_mmd_import_scale_override = "0.08"
assert preview_runtime.model_scale_info(second_root) == (0.08, 12.5, True)
second_root.spx_mmd_import_scale_override = "0.1"
second_root.scale = (2.0, 2.0, 2.0)
bpy.context.view_layer.update()
second_before_apply = preview_runtime._body_desc(second_rigid, second_armature)
bpy.ops.object.select_all(action="DESELECT")
second_root.select_set(True)
bpy.context.view_layer.objects.active = second_root
assert bpy.ops.object.transform_apply(location=False, rotation=False, scale=True) == {"FINISHED"}
bpy.context.view_layer.update()
second_after_apply = preview_runtime._body_desc(second_rigid, second_armature)
assert preview_runtime.model_scale_info(second_root) == (0.1, 10.0, False)
assert (
    second_before_apply.size.x,
    second_before_apply.size.y,
    second_before_apply.size.z,
) == (
    second_after_apply.size.x,
    second_after_apply.size.y,
    second_after_apply.size.z,
)
assert (
    Vector(transform_to_components(second_before_apply.transform)[0])
    - Vector(transform_to_components(second_after_apply.transform)[0])
).length < 1.0e-6
third_model = Model.create("MMDProxySmoke008B", add_root_bone=True)
third_root = third_model.rootObject()
third_root.empty_display_size = 0.4
third_armature = third_model.armature()
third_bone = next(iter(third_armature.data.bones))
third_group = FnModel.ensure_rigid_group_object(bpy.context, third_root)
third_rigid = FnRigidBody.new_rigid_body_objects(bpy.context, third_group, 1)[0]
FnRigidBody.setup_rigid_body_object(
    obj=third_rigid,
    shape_type=rigid_module.shapeType("BOX"),
    location=third_bone.head_local,
    rotation=(0.0, 0.0, 0.0),
    size=(0.016, 0.016, 0.016),
    dynamics_type=0,
    name="SmokeAnchor008B",
    name_e="SmokeAnchor008B",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=third_bone.name,
)
third_root.spx_physics_preview_selected = True
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
assert len(preview_runtime._ACTIVE_SESSIONS) == 3
assert len(preview_runtime._ACTIVE_WORLDS) == 3
model_preview_session = preview_runtime._ACTIVE_SESSIONS[model_root.name]
second_preview_session = preview_runtime._ACTIVE_SESSIONS[second_root.name]
third_preview_session = preview_runtime._ACTIVE_SESSIONS[third_root.name]
assert model_preview_session is not None
assert math.isclose(model_preview_session.import_scale, 0.08)
assert math.isclose(model_preview_session.world_scale, 12.5)
assert math.isclose(second_preview_session.import_scale, 0.1)
assert math.isclose(second_preview_session.world_scale, 10.0)
assert model_preview_session.world is not third_preview_session.world
assert model_preview_session.solver is not third_preview_session.solver
assert model_preview_session.world is not second_preview_session.world
assert unrelated_rigid in model_preview_session.rigids
assert model_preview_session.dynamic_rigid_count == expected_rigids + 1
solvers_before_reset_all = {
    world: world.solver for world in preview_runtime._ACTIVE_WORLDS.values()
}
assert bpy.ops.surface_proxy.reset_all_mmd_physics_previews() == {"FINISHED"}
assert len(preview_runtime._ACTIVE_SESSIONS) == 3
assert all(
    world.solver is not solver
    for world, solver in solvers_before_reset_all.items()
)
parallel_barrier = threading.Barrier(3)
parallel_threads = set()
original_parallel_steps = {
    world: world.step
    for world in (
        model_preview_session.world,
        second_preview_session.world,
        third_preview_session.world,
    )
}


def parallel_step(original):
    def run():
        parallel_threads.add(threading.current_thread().name)
        parallel_barrier.wait(timeout=5.0)
        original()

    return run


for world, original in original_parallel_steps.items():
    world.step = parallel_step(original)
assert preview_runtime._timer_tick() is not None
assert len(parallel_threads) == 3
assert all(name.startswith("mmd-physics") for name in parallel_threads)
for world, original in original_parallel_steps.items():
    world.step = original
assert bpy.ops.surface_proxy.stop_mmd_physics_preview(root_name=second_root.name) == {"FINISHED"}
assert set(preview_runtime._ACTIVE_SESSIONS) == {model_root.name, third_root.name}
assert len(preview_runtime._ACTIVE_WORLDS) == 2
assert bpy.ops.surface_proxy.stop_all_mmd_physics_previews() == {"FINISHED"}
assert not preview_runtime._ACTIVE_SESSIONS
preview_runtime.ensure_preview_model_ids(bpy.context.scene)
ordered_roots = preview_runtime.preview_roots(bpy.context.scene)
for root, model_id in zip(ordered_roots, (1, 3, 4)):
    root["spx_mmd_preview_id"] = model_id
for root, group_id in zip(ordered_roots, ("1", "3", "4")):
    root.spx_mmd_interaction_group_id = group_id
bpy.context.scene["spx_mmd_next_preview_id"] = 5
preview_runtime.renumber_preview_models(bpy.context.scene)
assert [preview_runtime.preview_model_id(root) for root in ordered_roots] == [1, 2, 3]
assert [root.spx_mmd_interaction_group_id for root in ordered_roots] == ["1", "2", "3"]
for root, model_id in zip(ordered_roots, (1, 3, 4)):
    root["spx_mmd_preview_id"] = model_id
for root, group_id in zip(ordered_roots, ("1", "1", "4")):
    root.spx_mmd_interaction_group_id = group_id
bpy.context.scene["spx_mmd_next_preview_id"] = 5
preview_runtime.renumber_preview_models(bpy.context.scene)
assert [preview_runtime.preview_model_id(root) for root in ordered_roots] == [1, 2, 3]
assert [root.spx_mmd_interaction_group_id for root in ordered_roots] == ["1", "1", "3"]
for root in ordered_roots:
    root.spx_mmd_interaction_group_id = str(preview_runtime.preview_model_id(root))
model_ids = {
    preview_runtime.preview_model_id(root)
    for root in (model_root, second_root, third_root)
}
assert len(model_ids) == 3
assert all(model_id > 0 for model_id in model_ids)
shared_group_id = model_root.spx_mmd_interaction_group_id
third_root.spx_mmd_interaction_group_id = shared_group_id
second_root.spx_physics_preview_selected = False
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
assert len(preview_runtime._ACTIVE_SESSIONS) == 2
assert len(preview_runtime._ACTIVE_WORLDS) == 1
assert (
    preview_runtime._ACTIVE_SESSIONS[model_root.name].solver
    is preview_runtime._ACTIVE_SESSIONS[third_root.name].solver
)
assert bpy.ops.surface_proxy.stop_all_mmd_physics_previews() == {"FINISHED"}
assert not preview_runtime._ACTIVE_SESSIONS
second_root.spx_physics_preview_selected = True
second_root.spx_mmd_interaction_group_id = shared_group_id
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
assert len(preview_runtime._ACTIVE_SESSIONS) == 3
assert len(preview_runtime._ACTIVE_WORLDS) == 2
assert bpy.ops.surface_proxy.stop_all_mmd_physics_previews() == {"FINISHED"}
second_root.spx_mmd_import_scale_override = "0.08"
assert preview_runtime.model_scale_info(second_root) == (0.08, 12.5, True)
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
assert len(preview_runtime._ACTIVE_SESSIONS) == 3
assert len(preview_runtime._ACTIVE_WORLDS) == 1
assert bpy.ops.surface_proxy.stop_all_mmd_physics_previews() == {"FINISHED"}
second_root.spx_mmd_import_scale_override = "0.1"
settings.preview_scope = "CURRENT_PROXY"
model_root.matrix_world = preview_fixture_root_matrix
bpy.context.view_layer.update()
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
unrelated_mesh = unrelated_rigid.data
bpy.data.objects.remove(unrelated_rigid, do_unlink=True)
if unrelated_mesh.users == 0:
    bpy.data.meshes.remove(unrelated_mesh)
assert len(joints) == expected_anchors + expected_vertical + expected_horizontal, (
    len(joints),
    expected_anchors + expected_vertical + expected_horizontal,
)
assert all(obj.mmd_rigid.bone in armature.data.bones for obj in rigids)
assert all(re.match(r"^\d{3}_", obj.name) for obj in rigids)
assert all(re.match(r"^\d{3}_J\.", obj.name) for obj in joints)
anchor_joints = [
    obj for obj in joints if obj.get("surface_proxy_role") == "JOINT_ANCHOR"
]
assert len(anchor_joints) == expected_anchors
assert all(obj.rigid_body_constraint.object1 == anchor_rigid for obj in anchor_joints)
assert all(obj.rigid_body_constraint.object2 in rigids for obj in anchor_joints)
assert all(
    obj.rigid_body_constraint.object1 in [anchor_rigid, *rigids]
    and obj.rigid_body_constraint.object2 in rigids
    for obj in joints
)
for rigid in rigids:
    bone = armature.data.bones[rigid.mmd_rigid.bone]
    assert (rigid.location - (bone.head_local + bone.tail_local) * 0.5).length < 1.0e-7
    direction = (bone.tail_local - bone.head_local).normalized()
    basis = rigid.rotation_euler.to_matrix()
    assert (basis @ Vector((0.0, 0.0, 1.0))).dot(direction) > 0.9999
    assert basis.determinant() > 0.9999
    normal = Vector(rigid["surface_proxy_normal"])
    assert (rigid.rotation_euler.to_matrix() @ Vector((0.0, 1.0, 0.0))).dot(normal) > 0.9999
vertical_joints = [
    obj for obj in joints if obj.get("surface_proxy_role") == "JOINT_VERTICAL"
]
horizontal_joints = [
    obj for obj in joints if obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
assert sum(
    int(joint["surface_proxy_row"]) == 0 for joint in horizontal_joints
) == len(row_counts)
for joint in [*anchor_joints, *vertical_joints, *horizontal_joints]:
    rigid_b = joint.rigid_body_constraint.object2
    suffix = "_H" if joint.get("surface_proxy_role") == "JOINT_HORIZONTAL" else ""
    expected_name_j = (rigid_b.mmd_rigid.name_j or rigid_b.name) + suffix
    expected_name_e = (rigid_b.mmd_rigid.name_e or rigid_b.name) + suffix
    assert joint.mmd_joint.name_j == expected_name_j
    assert joint.mmd_joint.name_e == expected_name_e
    assert "JOINT_" not in joint.mmd_joint.name_j
for joint in [*anchor_joints, *vertical_joints]:
    assert (
        joint.rotation_euler.to_quaternion().rotation_difference(
            joint.rigid_body_constraint.object2.rotation_euler.to_quaternion()
        ).angle
        < 1.0e-6
    )
for joint in horizontal_joints:
    rigid_a = joint.rigid_body_constraint.object1
    rigid_b = joint.rigid_body_constraint.object2
    horizontal_axis = joint.rotation_euler.to_matrix() @ Vector((1.0, 0.0, 0.0))
    joint_normal = joint.rotation_euler.to_matrix() @ Vector((0.0, 1.0, 0.0))
    connection_axis = (rigid_b.location - rigid_a.location).normalized()
    assert abs(horizontal_axis.dot(connection_axis)) > 0.9999
    normal_a = Vector(rigid_a["surface_proxy_normal"])
    normal_b = Vector(rigid_b["surface_proxy_normal"])
    if normal_a.dot(normal_b) < 0.0:
        normal_a.negate()
    normal_reference = (normal_a + normal_b).normalized()
    assert joint_normal.dot(normal_reference) > 0.0
    expected_location = (rigid_a.location + rigid_b.location) * 0.5
    assert (joint.location - expected_location).length < 1.0e-6, (
        joint.name,
        tuple(joint.location),
        tuple(expected_location),
    )

back_reference = SimpleNamespace(
    get=lambda name, default=None: (
        (0.0, 1.0, 0.0) if name == "surface_proxy_normal" else default
    ),
    rotation_euler=Euler((0.0, 0.0, 0.0), "XYZ"),
)
back_grid = [
    [Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, -1.0))],
    [Vector((1.0, 0.0, 0.0)), Vector((1.0, 0.0, -1.0))],
]
back_rotation = mmd_physics_module._horizontal_joint_rotation(
    back_grid,
    0,
    1,
    0,
    back_reference,
    back_reference,
)
back_basis = back_rotation.to_matrix()
assert (back_basis @ Vector((0.0, 1.0, 0.0))).dot(
    Vector((0.0, 1.0, 0.0))
) > 0.9999
assert (back_basis @ Vector((0.0, 0.0, 1.0))).dot(
    Vector((0.0, 0.0, -1.0))
) > 0.9999
assert back_basis.determinant() > 0.9999
independent_axis_joint = horizontal_joints[0]
independent_rigid_a = independent_axis_joint.rigid_body_constraint.object1
independent_rigid_b = independent_axis_joint.rigid_body_constraint.object2
expected_grid_rotation = independent_axis_joint.rotation_euler.copy()
independent_rigid_a.location += Vector((0.13, -0.08, 0.06))
independent_rigid_b.location += Vector((-0.09, 0.11, -0.04))
independent_rigid_a.rotation_euler = Euler((0.31, -0.22, 0.47), "XYZ")
independent_rigid_b.rotation_euler = Euler((-0.26, 0.38, -0.19), "XYZ")
independent_axis_joint.rotation_euler = Euler((0.77, -0.61, 0.53), "XYZ")
preserved_rigid_a_location = independent_rigid_a.location.copy()
preserved_rigid_b_location = independent_rigid_b.location.copy()
preserved_rigid_a_rotation = independent_rigid_a.rotation_euler.copy()
preserved_rigid_b_rotation = independent_rigid_b.rotation_euler.copy()
stale_joint_rotation = independent_axis_joint.rotation_euler.copy()
settings.protect_apply_location = True
settings.protect_apply_rotation = True
settings.protect_apply_joint_rotation = False
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert (independent_rigid_a.location - preserved_rigid_a_location).length < 1.0e-7
assert (independent_rigid_b.location - preserved_rigid_b_location).length < 1.0e-7
assert (
    independent_rigid_a.rotation_euler.to_quaternion().rotation_difference(
        preserved_rigid_a_rotation.to_quaternion()
    ).angle
    < 1.0e-6
)
assert (
    independent_rigid_b.rotation_euler.to_quaternion().rotation_difference(
        preserved_rigid_b_rotation.to_quaternion()
    ).angle
    < 1.0e-6
)
assert (
    independent_axis_joint.rotation_euler.to_quaternion().rotation_difference(
        stale_joint_rotation.to_quaternion()
    ).angle
    > 0.1
)
assert (
    independent_axis_joint.rotation_euler.to_quaternion().rotation_difference(
        expected_grid_rotation.to_quaternion()
    ).angle
    < 1.0e-6
)
settings.protect_apply_location = False
settings.protect_apply_rotation = False
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
checked_name_joint = vertical_joints[0]
unchecked_name_joint = horizontal_joints[0]
checked_rigid_b = checked_name_joint.rigid_body_constraint.object2
unchecked_rigid_b = unchecked_name_joint.rigid_body_constraint.object2
checked_order_prefix = checked_name_joint.name.split("_", 1)[0]
unchecked_order_prefix = unchecked_name_joint.name.split("_", 1)[0]
checked_name_joint.name = f"{checked_order_prefix}_J.BadCheckedJointName"
checked_name_joint.mmd_joint.name_j = "BadCheckedJointName"
checked_name_joint.mmd_joint.name_e = "BadCheckedJointName"
unchecked_name_joint.name = f"{unchecked_order_prefix}_J.BadUncheckedJointName"
unchecked_name_joint.mmd_joint.name_j = "BadUncheckedJointName"
unchecked_name_joint.mmd_joint.name_e = "BadUncheckedJointName"
settings.browser_kind = "JOINT"
settings.browser_current_proxy_only = True
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item
    for item in settings.browser_items
    if item.target_name == checked_name_joint.name
).selected = True
assert bpy.ops.surface_proxy.sync_joint_names_from_rigid_b(scope="CHECKED") == {
    "FINISHED"
}
assert checked_name_joint.mmd_joint.name_j == checked_rigid_b.mmd_rigid.name_j
assert checked_name_joint.mmd_joint.name_e == checked_rigid_b.mmd_rigid.name_e
assert checked_name_joint.name.startswith(f"{checked_order_prefix}_J.")
assert unchecked_name_joint.mmd_joint.name_j == "BadUncheckedJointName"
assert bpy.ops.surface_proxy.sync_joint_names_from_rigid_b(scope="ALL") == {
    "FINISHED"
}
assert (
    unchecked_name_joint.mmd_joint.name_j
    == f"{unchecked_rigid_b.mmd_rigid.name_j}_H"
)
assert (
    unchecked_name_joint.mmd_joint.name_e
    == f"{unchecked_rigid_b.mmd_rigid.name_e}_H"
)
bone_sync_horizontal = next(
    joint
    for joint in horizontal_joints
    if int(joint["surface_proxy_row"]) == 0
)
bone_sync_rigid = bone_sync_horizontal.rigid_body_constraint.object2
bone_sync_plain = next(
    joint
    for joint in anchor_joints
    if joint.rigid_body_constraint.object2 == bone_sync_rigid
)
bone_sync_bone = armature.pose.bones[bone_sync_rigid.mmd_rigid.bone]
bone_sync_bone.mmd_bone.name_j = "同步骨"
bone_sync_bone.mmd_bone.name_e = "SyncedBone"
bone_sync_rigid.name = "987_StaleRigidName"
bone_sync_rigid.mmd_rigid.name_j = "StaleRigidName"
bone_sync_rigid.mmd_rigid.name_e = "StaleRigidName"
settings.browser_kind = "BONE"
settings.browser_current_proxy_only = True
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item
    for item in settings.browser_items
    if item.target_name == bone_sync_bone.name
).selected = True
assert bpy.ops.surface_proxy.sync_bone_names_to_rigids() == {"FINISHED"}
assert bone_sync_rigid.name == f"987_{bone_sync_bone.name}"
assert bone_sync_rigid.mmd_rigid.name_j == "同步骨"
assert bone_sync_rigid.mmd_rigid.name_e == "SyncedBone"
for joint in (bone_sync_plain, bone_sync_horizontal):
    joint.mmd_joint.name_j = "StaleJointName"
    joint.mmd_joint.name_e = "StaleJointName"
for key in list(bone_sync_horizontal.keys()):
    if key.startswith("surface_proxy_"):
        del bone_sync_horizontal[key]
assert bpy.ops.surface_proxy.sync_bone_names_to_joints() == {"FINISHED"}
assert bone_sync_horizontal.get("surface_proxy_role") == "JOINT_HORIZONTAL"
assert re.sub(r"^[0-9A-Z]{3}_", "", bone_sync_horizontal.name) == (
    f"J.{bone_sync_bone.name}_H"
)
assert bone_sync_horizontal.mmd_joint.name_j == "同步骨_H"
assert bone_sync_horizontal.mmd_joint.name_e == "SyncedBone_H"
assert re.sub(r"^[0-9A-Z]{3}_", "", bone_sync_plain.name) == (
    f"J.{bone_sync_bone.name}"
)
assert bone_sync_plain.mmd_joint.name_j == "同步骨"
assert bone_sync_plain.mmd_joint.name_e == "SyncedBone"
bone_sync_bone.mmd_bone.name_e = ""
bone_sync_plain.mmd_joint.name_e = "StaleJointName"
bone_sync_horizontal.mmd_joint.name_e = "StaleJointName"
assert bpy.ops.surface_proxy.sync_bone_names_to_joints() == {"FINISHED"}
assert bone_sync_plain.mmd_joint.name_e == ""
assert bone_sync_horizontal.mmd_joint.name_e == ""
settings.browser_current_proxy_only = False
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
max_point_count = max(row_counts)
global_rigid_count = max_point_count - 1
global_joint_count = max_point_count - 2
for rigid in rigids:
    row = int(rigid["surface_proxy_row"])
    factor = row / (global_rigid_count - 1) if global_rigid_count > 1 else 0.0
    expected_mass = settings.mass + (settings.mass_end - settings.mass) * factor
    assert abs(rigid.rigid_body.mass - expected_mass) < 1.0e-7, (
        rigid.name,
        rigid.rigid_body.mass,
        expected_mass,
    )
for joint in [*vertical_joints, *horizontal_joints]:
    row = int(joint["surface_proxy_row"])
    factor = (row - 1) / (global_joint_count - 1) if global_joint_count > 1 else 0.0
    expected_x = settings.spring_angular[0] + (
        settings.spring_angular_end[0] - settings.spring_angular[0]
    ) * factor
    if joint.get("surface_proxy_role") == "JOINT_HORIZONTAL":
        factor = row / (global_rigid_count - 1) if global_rigid_count > 1 else 0.0
        expected_x = settings.horizontal_spring_angular[0] + (
            settings.horizontal_spring_angular_end[0]
            - settings.horizontal_spring_angular[0]
        ) * factor
    assert abs(joint.mmd_joint.spring_angular[0] - expected_x) < 1.0e-6, (
        joint.name,
        joint.mmd_joint.spring_angular[0],
        expected_x,
    )
uneven_rows = [6, 4]
assert abs(_rigid_interpolation_factor(2, uneven_rows) - 0.5) < 1.0e-7
assert abs(_joint_interpolation_factor(2, uneven_rows) - (1.0 / 3.0)) < 1.0e-7
top_rigid = next(
    obj
    for obj in rigids
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == 0
)
bottom_rigid = next(
    obj
    for obj in rigids
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == row_counts[0] - 2
)
assert abs(top_rigid.rigid_body.mass - 1.0) < 1.0e-7
assert abs(bottom_rigid.rigid_body.mass - 3.0) < 1.0e-7
assert abs(top_rigid.mmd_rigid.size[0] / armature.data.bones[top_rigid.mmd_rigid.bone].length - 0.4) < 1.0e-7
assert abs(bottom_rigid.mmd_rigid.size[0] / armature.data.bones[bottom_rigid.mmd_rigid.bone].length - 0.8) < 1.0e-7
assert abs(top_rigid.mmd_rigid.size[1] / armature.data.bones[top_rigid.mmd_rigid.bone].length - 0.1) < 1.0e-7
assert abs(top_rigid.mmd_rigid.size[2] / armature.data.bones[top_rigid.mmd_rigid.bone].length - 0.25) < 1.0e-7
top_vertical = next(
    obj
    for obj in vertical_joints
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == 1
)
bottom_vertical = next(
    obj
    for obj in vertical_joints
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == row_counts[0] - 2
)
assert tuple(top_vertical.mmd_joint.spring_angular) == (3.0, 4.0, 5.0)
assert tuple(bottom_vertical.mmd_joint.spring_angular) == (6.0, 4.0, 10.0)
shared_bones = min(row_counts[0], row_counts[1]) - 1
top_horizontal = next(
    obj
    for obj in horizontal_joints
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == 0
)
bottom_horizontal = next(
    obj
    for obj in horizontal_joints
    if obj.get("surface_proxy_column") == 0
    and obj.get("surface_proxy_row") == shared_bones - 1
)
assert tuple(top_horizontal.mmd_joint.spring_angular) == (8.0, 9.0, 10.0)
assert tuple(bottom_horizontal.mmd_joint.spring_angular) == (12.0, 9.0, 16.0)

settings.mass = 2.5
settings.mass_interpolate = False
settings.spring_angular = (4.0, 5.0, 6.0)
settings.spring_angular_interpolate = (False, False, False)
settings.horizontal_spring_angular = (9.0, 10.0, 11.0)
settings.horizontal_spring_angular_interpolate = (False, False, False)
top_horizontal_rigid_a = top_horizontal.rigid_body_constraint.object1
top_horizontal_rigid_b = top_horizontal.rigid_body_constraint.object2
top_horizontal_bone_a = armature.data.bones[top_horizontal_rigid_a.mmd_rigid.bone]
top_horizontal_bone_b = armature.data.bones[top_horizontal_rigid_b.mmd_rigid.bone]
old_horizontal_location = (
    top_horizontal_bone_a.head_local + top_horizontal_bone_b.head_local
) * 0.5
expected_horizontal_location = (
    top_horizontal_rigid_a.location + top_horizontal_rigid_b.location
) * 0.5
assert (old_horizontal_location - expected_horizontal_location).length > 1.0e-5
top_horizontal.location = old_horizontal_location
result = bpy.ops.surface_proxy.update_mmd_physics()
assert result == {"FINISHED"}, result
assert all(abs(obj.rigid_body.mass - 2.5) < 1.0e-7 for obj in rigids)
assert all(tuple(obj.mmd_joint.spring_angular) == (4.0, 5.0, 6.0) for obj in vertical_joints)
assert all(tuple(obj.mmd_joint.spring_angular) == (9.0, 10.0, 11.0) for obj in horizontal_joints)
assert (top_horizontal.location - expected_horizontal_location).length < 1.0e-6

first_protection_values = {
    "protect_apply_location": True,
    "protect_apply_rotation": False,
    "protect_apply_joint_location": True,
    "protect_apply_joint_rotation": False,
    "protect_apply_shape": True,
    "protect_apply_size": False,
    "protect_apply_type": True,
    "protect_apply_dynamics": False,
    "protect_apply_collision": True,
    "protect_apply_joint_parameters": False,
}
for name, value in first_protection_values.items():
    setattr(settings, name, value)
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}

second_source = build_source_mesh("MMDProxySmokeSourceB")
second_source.parent = model_root
modifier = second_source.modifiers.new(name="MMDProxySmokeArmatureB", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
second_source.select_set(True)
bpy.context.view_layer.objects.active = second_source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
settings.prefix = "SmokeProxyB"
settings.armature = model_armature
settings.write_weights = False
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
second_proxy = bpy.data.objects["SmokeProxyB_Surface"]
assert settings.physics_proxy == second_proxy
for name in first_protection_values:
    assert getattr(settings, name) is False
settings.mmd_root = model_root
settings.mass = 7.0
second_protection_values = {
    name: not value for name, value in first_protection_values.items()
}
for name, value in second_protection_values.items():
    setattr(settings, name, value)
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
second_physics = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_physics_id")
    == second_proxy.get("surface_proxy_physics_id")
]
second_rigids = [obj for obj in second_physics if obj.mmd_type == "RIGID_BODY"]
second_joints = [obj for obj in second_physics if obj.mmd_type == "JOINT"]
assert len(second_rigids) == expected_rigids
assert len(second_joints) == expected_anchors + expected_vertical + expected_horizontal
assert all(abs(obj.rigid_body.mass - 7.0) < 1.0e-7 for obj in second_rigids)

settings.physics_proxy = proxy
assert abs(settings.mass - 2.5) < 1.0e-7
for name, value in first_protection_values.items():
    assert getattr(settings, name) is value
settings.physics_proxy = second_proxy
for name, value in second_protection_values.items():
    assert getattr(settings, name) is value
for name in second_protection_values:
    setattr(settings, name, False)
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
settings.physics_proxy = proxy
for name in first_protection_values:
    setattr(settings, name, False)
bpy.context.view_layer.objects.active = second_proxy
settings.mass = 3.5
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert all(abs(obj.rigid_body.mass - 3.5) < 1.0e-7 for obj in rigids)
assert all(abs(obj.rigid_body.mass - 7.0) < 1.0e-7 for obj in second_rigids)

first_rigid = next(
    obj for obj in rigids if obj.get("surface_proxy_column") == 0 and obj.get("surface_proxy_row") == 0
)
second_location = second_rigids[0].location.copy()
old_location = first_rigid.location.copy()
bpy.ops.object.select_all(action="DESELECT")
model_armature.select_set(True)
bpy.context.view_layer.objects.active = model_armature
bpy.ops.object.mode_set(mode="EDIT")
edited_bone = model_armature.data.edit_bones["SmokeProxy_C01_R01"]
edited_bone.head.x += 0.2
edited_bone.tail.x += 0.2
bpy.ops.object.mode_set(mode="OBJECT")
assert bpy.ops.surface_proxy.sync_mmd_physics() == {"FINISHED"}
assert (first_rigid.location - old_location).length > 0.09
assert (second_rigids[0].location - second_location).length < 1.0e-7
assert abs(first_rigid.rigid_body.mass - 3.5) < 1.0e-7

settings.auto_sync_physics = True
old_location = first_rigid.location.copy()
bpy.ops.object.mode_set(mode="EDIT")
edited_bone = model_armature.data.edit_bones["SmokeProxy_C01_R01"]
edited_bone.head.x += 0.15
edited_bone.tail.x += 0.15
fake_update = type("Update", (), {"id": model_armature.data})()
fake_depsgraph = type("Depsgraph", (), {"updates": [fake_update]})()
proxy_sync._depsgraph_proxy_update(bpy.context.scene, fake_depsgraph)
assert proxy.name in proxy_sync._DIRTY_PHYSICS_PROXIES
bpy.ops.object.mode_set(mode="OBJECT")
assert proxy_sync._run_pending_sync() is None
assert (first_rigid.location - old_location).length > 0.07
assert (second_rigids[0].location - second_location).length < 1.0e-7
assert abs(first_rigid.rigid_body.mass - 3.5) < 1.0e-7

bpy.ops.object.select_all(action="DESELECT")
proxy.select_set(True)
bpy.context.view_layer.objects.active = proxy
old_location = first_rigid.location.copy()
first_vertex = proxy["surface_proxy_vertex_map"][0]
proxy.data.vertices[first_vertex].co.x += 0.1
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
assert (first_rigid.location - old_location).length > 0.01
assert (second_rigids[0].location - second_location).length < 1.0e-7

settings.browser_current_proxy_only = True
settings.browser_kind = "RIGID"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert len(settings.browser_items) == len(rigids)
assert {
    item.target_name for item in settings.browser_items
} == {obj.name for obj in rigids}
settings.browser_current_proxy_only = False
all_rigids = [anchor_rigid, *rigids, *second_rigids]
all_joints = joints + second_joints


class LayoutProbe:
    def __init__(self, records=None, operators=None, prop_states=None):
        self.records = records if records is not None else []
        self.operators = operators if operators is not None else []
        self.prop_states = prop_states if prop_states is not None else []
        self.enabled = True

    def box(self):
        return LayoutProbe(self.records, self.operators, self.prop_states)

    def row(self, **_kwargs):
        return LayoutProbe(self.records, self.operators, self.prop_states)

    def column(self, **_kwargs):
        return LayoutProbe(self.records, self.operators, self.prop_states)

    def grid_flow(self, **_kwargs):
        return LayoutProbe(self.records, self.operators, self.prop_states)

    def label(self, **_kwargs):
        return None

    def separator(self, **kwargs):
        self.records.append(("__separator__", kwargs.get("factor"), None))

    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), name
        self.records.append((name, kwargs.get("index"), kwargs.get("text")))
        self.prop_states.append((name, self.enabled))

    def prop_search(self, data, name, *_args, **kwargs):
        self.prop(data, name, **kwargs)

    def operator(self, operator_id, **_kwargs):
        self.operators.append(operator_id)
        return type("OperatorProbe", (), {})()

    def menu(self, *_args, **_kwargs):
        return None

    def template_list(self, *_args, **_kwargs):
        return None


workspace_draw_calls = []
original_draw_physics_settings = mmd_station.draw_physics_settings
original_draw_browser = mmd_station.draw_browser
original_draw_preview = mmd_station.draw_preview
try:
    mmd_station.draw_physics_settings = (
        lambda _layout, _settings, _context=None: workspace_draw_calls.append("PROXY")
    )
    mmd_station.draw_browser = (
        lambda _layout, _settings: workspace_draw_calls.append("BROWSER")
    )
    mmd_station.draw_preview = (
        lambda _layout, _settings: workspace_draw_calls.append("PREVIEW")
    )
    for workspace_tab in ("PROXY", "BROWSER", "PREVIEW"):
        settings.workspace_tab = workspace_tab
        workspace_draw_calls.clear()
        probe = LayoutProbe()
        mmd_station.draw_workspace(probe, bpy.context)
        assert workspace_draw_calls == [workspace_tab]
        assert any(name == "workspace_tab" for name, _index, _text in probe.records)
finally:
    mmd_station.draw_physics_settings = original_draw_physics_settings
    mmd_station.draw_browser = original_draw_browser
    mmd_station.draw_preview = original_draw_preview


settings.preview_scope = "MODEL"
preview_runtime.ensure_preview_model_ids(bpy.context.scene)
preview_probe = LayoutProbe()
original_draw_preview(preview_probe, settings)
assert sum(
    name == "spx_physics_preview_selected"
    for name, _index, _text in preview_probe.records
) == 3
assert sum(
    name == "spx_mmd_interaction_group_id"
    for name, _index, _text in preview_probe.records
) == 3
assert any(name == "preview_frequency" for name, _index, _text in preview_probe.records)
assert any(name == "preview_substeps" for name, _index, _text in preview_probe.records)
assert any(name == "preview_gravity" for name, _index, _text in preview_probe.records)
assert sum(
    name == "preview_solver_target"
    for name, _index, _text in preview_probe.records
) == 1
assert next(
    index
    for index, (name, _item_index, _text) in enumerate(preview_probe.records)
    if name == "preview_solver_target"
) < next(
    index
    for index, (name, _item_index, _text) in enumerate(preview_probe.records)
    if name == "preview_frequency"
)
assert "surface_proxy.start_mmd_physics_preview" in preview_probe.operators
assert "surface_proxy.renumber_mmd_physics_preview_models" in preview_probe.operators
assert preview_probe.operators.count("surface_proxy.reset_all_mmd_physics_previews") == 1
assert preview_probe.operators.count("surface_proxy.stop_all_mmd_physics_previews") == 1
assert preview_probe.operators.index(
    "surface_proxy.stop_all_mmd_physics_previews"
) < preview_probe.operators.index("surface_proxy.reset_all_mmd_physics_previews")
import mmd_station.physics_preview.ui as preview_ui

original_active_session_info = preview_ui.active_session_info
original_preview_is_running = preview_ui.is_running
try:
    preview_ui.active_session_info = lambda: (("Model", 0.08, 12.5, "1", "MMD"),)
    preview_ui.is_running = lambda _root=None: True
    active_preview_probe = LayoutProbe()
    original_draw_preview(active_preview_probe, settings)
    assert active_preview_probe.operators.count(
        "surface_proxy.stop_all_mmd_physics_previews"
    ) == 1
    assert active_preview_probe.operators.count(
        "surface_proxy.reset_all_mmd_physics_previews"
    ) == 1
    interaction_states = [
        enabled
        for name, enabled in active_preview_probe.prop_states
        if name == "spx_mmd_interaction_group_id"
    ]
    scale_states = [
        enabled
        for name, enabled in active_preview_probe.prop_states
        if name == "spx_mmd_import_scale_override"
    ]
    assert interaction_states and not any(interaction_states)
    assert scale_states and all(scale_states)
    target_states = [
        enabled
        for name, enabled in active_preview_probe.prop_states
        if name == "preview_solver_target"
    ]
    assert target_states == [False]
finally:
    preview_ui.active_session_info = original_active_session_info
    preview_ui.is_running = original_preview_is_running


for physics_tab in ("BASIC", "RIGID", "VERTICAL", "HORIZONTAL"):
    settings.physics_tab = physics_tab
    probe = LayoutProbe()
    draw_physics_settings(probe, settings)
    if physics_tab == "BASIC":
        assert not any(name == "create_horizontal_joints" for name, _index, _text in probe.records)
        assert any(name == "topology" for name, _index, _text in probe.records)
        assert any(name == "columns" for name, _index, _text in probe.records)
    if physics_tab == "HORIZONTAL":
        assert any(name == "create_horizontal_joints" for name, _index, _text in probe.records)
    if physics_tab == "RIGID":
        assert any(
            name == "adaptive_number_mass" for name, _index, _text in probe.records
        )
        assert any(
            name == "adaptive_number_linear_damping_end"
            for name, _index, _text in probe.records
        )
        assert not any(name == "mass" for name, _index, _text in probe.records)
        assert any(
            name == "collision_group_display" for name, _index, _text in probe.records
        )
        assert any(
            name == "block_same_collision_group" for name, _index, _text in probe.records
        )
        numbered = [
            (index, text)
            for name, index, text in probe.records
            if name == "collision_group_mask"
        ]
        assert numbered == [(index, str(index)) for index in range(16)]
    if physics_tab == "VERTICAL":
        assert any(
            name == "adaptive_number_limit_angular_lower_0"
            for name, _index, _text in probe.records
        )
        assert any(
            name == "adaptive_number_spring_angular_end_2"
            for name, _index, _text in probe.records
        )
    if physics_tab == "HORIZONTAL":
        assert any(
            name == "adaptive_number_horizontal_limit_linear_upper_0"
            for name, _index, _text in probe.records
        )
        assert any(
            name == "adaptive_number_horizontal_spring_angular_end_2"
            for name, _index, _text in probe.records
        )

settings.collision_group_number = 5
assert settings.collision_group_display == 5
settings.collision_group_mask = [False] * 16
assert not settings.block_same_collision_group
settings.block_same_collision_group = True
assert settings.collision_group_mask[5]
assert sum(bool(value) for value in settings.collision_group_mask) == 1
settings.collision_group_display = 5
assert settings.collision_group_number == 5

settings.browser_kind = "BONE"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == first_bone.name
)
bone_inspector_probe = LayoutProbe()
_draw_active_mmd_inspector(bone_inspector_probe, settings)
bone_detail_properties = {
    name for name, _index, _text in bone_inspector_probe.records
}
assert {
    "bone_id",
    "name_j",
    "name_e",
    "transform_order",
    "transform_after_dynamics",
    "is_controllable",
    "is_tip",
    "enabled_fixed_axis",
    "fixed_axis",
    "enabled_local_axes",
    "local_axis_x",
    "local_axis_z",
    "has_additional_rotation",
    "has_additional_location",
    "additional_transform_bone",
    "additional_transform_influence",
    "display_connection_type",
    "use_deform",
} <= bone_detail_properties

diagnostic_unanchored = FnRigidBody.new_rigid_body_objects(
    bpy.context,
    anchor_group,
    1,
)[0]
diagnostic_unanchored = FnRigidBody.setup_rigid_body_object(
    obj=diagnostic_unanchored,
    shape_type=rigid_module.shapeType("SPHERE"),
    location=anchor_bone.head_local + Vector((0.0, 0.0, 4.0)),
    rotation=(0.0, 0.0, 0.0),
    size=(0.2, 0.0, 0.0),
    dynamics_type=1,
    name="DiagnosticUnanchoredRigid",
    name_e="DiagnosticUnanchoredRigid",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=anchor_bone.name,
)
diagnostic_unanchored_second = FnRigidBody.new_rigid_body_objects(
    bpy.context,
    anchor_group,
    1,
)[0]
diagnostic_unanchored_second = FnRigidBody.setup_rigid_body_object(
    obj=diagnostic_unanchored_second,
    shape_type=rigid_module.shapeType("SPHERE"),
    location=anchor_bone.head_local + Vector((0.0, 0.0, 4.5)),
    rotation=(0.0, 0.0, 0.0),
    size=(0.2, 0.0, 0.0),
    dynamics_type=1,
    name="DiagnosticUnanchoredRigidSecond",
    name_e="DiagnosticUnanchoredRigidSecond",
    collision_group_number=0,
    collision_group_mask=[False] * 16,
    mass=1.0,
    friction=0.5,
    bounce=0.0,
    linear_damping=0.5,
    angular_damping=0.5,
    bone=anchor_bone.name,
)
diagnostic_joint_group = FnModel.ensure_joint_group_object(bpy.context, model_root)
diagnostic_unanchored_joint = FnRigidBody.new_joint_objects(
    bpy.context,
    diagnostic_joint_group,
    1,
    FnModel.get_empty_display_size(model_root),
)[0]
diagnostic_unanchored_joint = FnRigidBody.setup_joint_object(
    obj=diagnostic_unanchored_joint,
    name="DiagnosticUnanchoredJoint",
    name_e="DiagnosticUnanchoredJoint",
    location=anchor_bone.head_local + Vector((0.0, 0.0, 4.25)),
    rotation=(0.0, 0.0, 0.0),
    rigid_a=diagnostic_unanchored,
    rigid_b=diagnostic_unanchored_second,
    maximum_location=Vector((0.0, 0.0, 0.0)),
    minimum_location=Vector((0.0, 0.0, 0.0)),
    maximum_rotation=Vector((0.0, 0.0, 0.0)),
    minimum_rotation=Vector((0.0, 0.0, 0.0)),
    spring_angular=Vector((0.0, 0.0, 0.0)),
    spring_linear=Vector((0.0, 0.0, 0.0)),
)
bpy.context.view_layer.update()
diagnostic_joint = all_joints[0]
saved_rigid_b = diagnostic_joint.rigid_body_constraint.object2
diagnostic_joint.rigid_body_constraint.object2 = None
repair_pose_bone = model_armature.pose.bones[anchor_bone.name]
saved_repair_bone_name = repair_pose_bone.mmd_bone.name_j
repair_pose_bone.mmd_bone.name_j = ""
settings.browser_kind = "DIAGNOSTIC"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
repair_name_issue = next(
    item
    for item in settings.browser_diagnostics
    if item.target_kind == "BONE"
    and item.target_name == repair_pose_bone.name
    and item.message == "MMD 名称为空"
)
assert repair_name_issue.code == "BONE_NAME_EMPTY"
assert bpy.ops.surface_proxy.repair_mmd_diagnostic(
    code=repair_name_issue.code,
    target_kind=repair_name_issue.target_kind,
    target_name=repair_name_issue.target_name,
    armature_name=repair_name_issue.armature_name,
    diagnostic_message=repair_name_issue.message,
) == {"FINISHED"}
assert repair_pose_bone.mmd_bone.name_j == repair_pose_bone.name
assert all(
    item.target_name != repair_pose_bone.name or item.message != "MMD 名称为空"
    for item in settings.browser_diagnostics
)
repair_pose_bone.mmd_bone.name_j = saved_repair_bone_name
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
diagnostic_messages = {
    (item.target_kind, item.target_name, item.message)
    for item in settings.browser_diagnostics
}
assert (
    "JOINT",
    diagnostic_joint.name,
    "缺少连接的刚体 B",
) in diagnostic_messages
assert next(
    item
    for item in settings.browser_diagnostics
    if item.target_name == diagnostic_joint.name
    and item.message == "缺少连接的刚体 B"
).solution == "跳转后在活动项属性的“刚体 B”中选择正确刚体。"
settings.browser_filter_by_prefix = True
assert bpy.ops.surface_proxy.jump_to_mmd_diagnostic(
    target_kind="JOINT",
    target_name=diagnostic_joint.name,
    armature_name="",
) == {"FINISHED"}
assert settings.browser_kind == "JOINT"
assert not settings.browser_filter_by_prefix
assert settings.browser_items[settings.browser_index].target_name == diagnostic_joint.name
assert bpy.context.active_object == diagnostic_joint
diagnostic_joint.rigid_body_constraint.object2 = saved_rigid_b
assert settings.browser_kind == "JOINT"
assert _refresh_mmd_browser_from_changes()
assert all(
    item.target_name != diagnostic_joint.name or item.message != "缺少连接的刚体 B"
    for item in settings.browser_diagnostics
)
settings.browser_kind = "DIAGNOSTIC"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert all(
    item.target_name != diagnostic_joint.name or item.message != "缺少连接的刚体 B"
    for item in settings.browser_diagnostics
)
assert all(
    item.message
    not in {"骨骼末端连接目标不存在", "追加变换引用无效"}
    for item in settings.browser_diagnostics
)
unanchored_issue = next(
    item
    for item in settings.browser_diagnostics
    if item.target_name == diagnostic_unanchored_joint.name
    and "无法通过 Joint 到达 0 型锚点" in item.message
)
assert unanchored_issue.severity == "WARNING"
assert unanchored_issue.target_kind == "JOINT"
assert diagnostic_unanchored.name in unanchored_issue.search_text
assert diagnostic_unanchored_joint.name in unanchored_issue.search_text
assert "检查链首附近 Joint 的刚体 A/B" in unanchored_issue.solution
assert "不要把整条链全部改成 0 型" in unanchored_issue.solution
try:
    bpy.ops.surface_proxy.repair_mmd_diagnostic(
        code=unanchored_issue.code,
        target_kind=unanchored_issue.target_kind,
        target_name=unanchored_issue.target_name,
        armature_name=unanchored_issue.armature_name,
        diagnostic_message=unanchored_issue.message,
    )
except RuntimeError as error:
    assert "无法安全自动修复" in str(error)
else:
    raise AssertionError("Unsafe diagnostic repair must fail closed")
assert bpy.ops.surface_proxy.jump_to_mmd_diagnostic(
    target_kind=unanchored_issue.target_kind,
    target_name=unanchored_issue.target_name,
    armature_name="",
) == {"FINISHED"}
assert settings.browser_kind == "JOINT"
assert bpy.context.active_object == diagnostic_unanchored_joint
settings.browser_kind = "DIAGNOSTIC"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
diagnostic_unanchored_joint_mesh = diagnostic_unanchored_joint.data
diagnostic_unanchored_second_mesh = diagnostic_unanchored_second.data
diagnostic_unanchored_mesh = diagnostic_unanchored.data
if diagnostic_unanchored_joint.name in bpy.data.objects:
    bpy.data.objects.remove(diagnostic_unanchored_joint, do_unlink=True)
if diagnostic_unanchored_joint_mesh is not None:
    bpy.data.meshes.remove(diagnostic_unanchored_joint_mesh)
if diagnostic_unanchored_second.name in bpy.data.objects:
    bpy.data.objects.remove(diagnostic_unanchored_second, do_unlink=True)
bpy.data.meshes.remove(diagnostic_unanchored_second_mesh)
bpy.data.objects.remove(diagnostic_unanchored, do_unlink=True)
bpy.data.meshes.remove(diagnostic_unanchored_mesh)

for browser_kind in ("RIGID", "JOINT"):
    settings.browser_kind = browser_kind
    assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
    probe = LayoutProbe()
    original_draw_browser(probe, settings)
    assert probe.operators.count("surface_proxy.reorder_checked_mmd_items") == 6
    assert probe.records.count(("__separator__", 0.5, None)) == 1
    assert "surface_proxy.sync_selected_mmd_objects_to_browser" in probe.operators
    assert "surface_proxy.create_mirrored_mmd_items" in probe.operators
    assert "surface_proxy.sync_mirrored_mmd_items" in probe.operators
    if browser_kind == "RIGID":
        assert "surface_proxy.sync_joint_axes_from_rigids" in probe.operators
        assert "surface_proxy.create_joint_from_checked_rigids" in probe.operators
    else:
        assert "surface_proxy.sync_joint_names_from_rigid_b" in probe.operators

settings.physics_proxy = proxy
settings.browser_current_proxy_only = True
settings.browser_kind = "RIGID"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}


def expected_manual_curve_midpoint(rigid_a, rigid_b, local_axis):
    position_a = rigid_a.matrix_world.translation
    position_b = rigid_b.matrix_world.translation
    connection = position_b - position_a
    span = connection.length
    connection.normalize()
    tangent_a = (
        rigid_a.matrix_world.to_3x3().normalized() @ local_axis
    ).normalized()
    tangent_b = (
        rigid_b.matrix_world.to_3x3().normalized() @ local_axis
    ).normalized()
    if tangent_a.dot(connection) < 0.0:
        tangent_a.negate()
    if tangent_b.dot(connection) < 0.0:
        tangent_b.negate()
    handle_a = tangent_a * span
    handle_b = tangent_b * span
    position = (position_a + position_b) * 0.5 + (handle_a - handle_b) * 0.125
    tangent = (position_b - position_a) * 1.5 - (handle_a + handle_b) * 0.25
    tangent.normalize()
    return position, tangent


manual_vertical_a = next(
    rigid
    for rigid in rigids
    if int(rigid["surface_proxy_column"]) == 0
    and int(rigid["surface_proxy_row"]) == 0
)
manual_vertical_b = next(
    rigid
    for rigid in rigids
    if int(rigid["surface_proxy_column"]) == 0
    and int(rigid["surface_proxy_row"]) == 2
)
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
for index, item in enumerate(settings.browser_items):
    if item.target_name in {manual_vertical_a.name, manual_vertical_b.name}:
        item.selected = True
    if item.target_name == manual_vertical_b.name:
        settings.browser_index = index
assert bpy.ops.surface_proxy.create_joint_from_checked_rigids() == {"FINISHED"}
manual_vertical = bpy.context.active_object
assert manual_vertical.get("surface_proxy_manual_joint") is True
assert manual_vertical.get("surface_proxy_role") == "JOINT_VERTICAL"
assert manual_vertical.rigid_body_constraint.object1 == manual_vertical_a
assert manual_vertical.rigid_body_constraint.object2 == manual_vertical_b
expected_vertical_position, expected_vertical_tangent = expected_manual_curve_midpoint(
    manual_vertical_a,
    manual_vertical_b,
    Vector((0.0, 0.0, 1.0)),
)
assert (
    manual_vertical.matrix_world.translation
    - expected_vertical_position
).length < 1.0e-6
manual_vertical_axis_z = (
    manual_vertical.matrix_world.to_3x3().normalized()
    @ Vector((0.0, 0.0, 1.0))
).normalized()
assert manual_vertical_axis_z.dot(expected_vertical_tangent) > 0.999999
bpy.data.objects.remove(manual_vertical, do_unlink=True)

manual_horizontal_a = next(
    rigid
    for rigid in rigids
    if int(rigid["surface_proxy_column"]) == 0
    and int(rigid["surface_proxy_row"]) == 0
)
manual_horizontal_b = next(
    rigid
    for rigid in rigids
    if int(rigid["surface_proxy_column"]) == 2
    and int(rigid["surface_proxy_row"]) == 2
)
same_orientation_matrix = manual_horizontal_a.matrix_world.copy()
same_orientation_matrix.translation = manual_horizontal_b.matrix_world.translation
original_horizontal_b_matrix = manual_horizontal_b.matrix_world.copy()
manual_horizontal_b.matrix_world = same_orientation_matrix
bpy.context.view_layer.update()
same_orientation_location, _same_orientation_rotation = (
    mmd_physics_module._manual_joint_transform(
        manual_horizontal_a,
        manual_horizontal_b,
        "JOINT_HORIZONTAL",
        joints[0].parent,
    )
)
same_orientation_world_location = joints[0].parent.matrix_world @ same_orientation_location
same_orientation_midpoint = (
    manual_horizontal_a.matrix_world.translation
    + manual_horizontal_b.matrix_world.translation
) * 0.5
assert (
    same_orientation_world_location - same_orientation_midpoint
).length < 1.0e-6
manual_horizontal_b.matrix_world = original_horizontal_b_matrix
bpy.context.view_layer.update()
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
for index, item in enumerate(settings.browser_items):
    if item.target_name in {manual_horizontal_a.name, manual_horizontal_b.name}:
        item.selected = True
    if item.target_name == manual_horizontal_b.name:
        settings.browser_index = index
assert bpy.ops.surface_proxy.create_joint_from_checked_rigids() == {"FINISHED"}
manual_horizontal = bpy.context.active_object
manual_horizontal_name = manual_horizontal.name
assert manual_horizontal.get("surface_proxy_manual_joint") is True
assert manual_horizontal.get("surface_proxy_role") == "JOINT_HORIZONTAL"
assert manual_horizontal.rigid_body_constraint.object1 == manual_horizontal_a
assert manual_horizontal.rigid_body_constraint.object2 == manual_horizontal_b
assert manual_horizontal.mmd_joint.name_j.endswith("_H")
manual_horizontal.location += Vector((0.31, -0.27, 0.19))
manual_horizontal.rotation_euler = Euler((0.8, -0.6, 0.4), "YXZ")
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert manual_horizontal_name in bpy.data.objects
manual_horizontal = bpy.data.objects[manual_horizontal_name]
expected_manual_midpoint = (
    manual_horizontal_a.matrix_world.translation
    + manual_horizontal_b.matrix_world.translation
) * 0.5
expected_manual_position, expected_manual_tangent = expected_manual_curve_midpoint(
    manual_horizontal_a,
    manual_horizontal_b,
    Vector((1.0, 0.0, 0.0)),
)
assert (
    manual_horizontal.matrix_world.translation - expected_manual_position
).length < 1.0e-6
assert (expected_manual_position - expected_manual_midpoint).length > 1.0e-5
manual_connection = (
    manual_horizontal_b.matrix_world.translation
    - manual_horizontal_a.matrix_world.translation
).normalized()
manual_axis_x = (
    manual_horizontal.matrix_world.to_3x3().normalized()
    @ Vector((1.0, 0.0, 0.0))
).normalized()
manual_axis_y = (
    manual_horizontal.matrix_world.to_3x3().normalized()
    @ Vector((0.0, 1.0, 0.0))
).normalized()
manual_b_axis_y = (
    manual_horizontal_b.matrix_world.to_3x3().normalized()
    @ Vector((0.0, 1.0, 0.0))
).normalized()
assert manual_axis_x.dot(expected_manual_tangent) > 0.999999
assert manual_axis_x.dot(manual_connection) > 0.0
assert abs(manual_axis_y.dot(manual_axis_x)) < 1.0e-6
assert manual_axis_y.dot(manual_b_axis_y) > 0.0
assert sum(
    obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    and not obj.get("surface_proxy_manual_joint")
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == proxy.name
) == expected_horizontal
bpy.data.objects.remove(manual_horizontal, do_unlink=True)
settings.browser_current_proxy_only = False

for kind, expected in (
    ("BONE", len(model_armature.data.bones)),
    ("RIGID", len(all_rigids)),
    ("JOINT", len(all_joints)),
):
    settings.browser_kind = kind
    result = bpy.ops.surface_proxy.refresh_mmd_browser()
    assert result == {"FINISHED"}, (kind, result)
    assert len(settings.browser_items) == expected, (
        kind,
        len(settings.browser_items),
        expected,
    )
    first_item = settings.browser_items[0]
    target_name = first_item.target_name
    armature_name = first_item.armature_name
    result = bpy.ops.surface_proxy.select_mmd_item(
        kind=kind,
        target_name=target_name,
        armature_name=armature_name,
    )
    assert result == {"FINISHED"}, (kind, result)
    if kind == "BONE":
        assert bpy.context.active_object == model_armature
        assert model_armature.data.bones.active.name == target_name
    else:
        assert bpy.context.active_object.name == target_name

settings.browser_kind = "RIGID"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
settings.browser_items[0].selected = True
settings.browser_items[1].selected = True
checked_rigid_names = {
    settings.browser_items[0].target_name,
    settings.browser_items[1].target_name,
}
assert bpy.ops.surface_proxy.select_checked_mmd_items() == {"FINISHED"}
assert checked_rigid_names == {obj.name for obj in bpy.context.selected_objects}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
assert bpy.ops.surface_proxy.sync_selected_mmd_objects_to_browser() == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == checked_rigid_names

settings.browser_index = 0
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="RIGID_GROUP") == {"FINISHED"}
assert all(item.selected for item in settings.browser_items)
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
for item in settings.browser_items[:2]:
    item.selected = True
deleted_rigid_names = {item.target_name for item in settings.browser_items[:2]}
deleted_rigids = {bpy.data.objects[name] for name in deleted_rigid_names}
linked_joint_names = {
    joint.name
    for joint in joints
    if joint.rigid_body_constraint.object1 in deleted_rigids
    or joint.rigid_body_constraint.object2 in deleted_rigids
}
assert bpy.ops.surface_proxy.delete_checked_mmd_items() == {"FINISHED"}
assert all(name not in bpy.data.objects for name in deleted_rigid_names)
assert all(name not in bpy.data.objects for name in linked_joint_names)

cleanup_target = "SmokeProxy_C12_R01"
cleanup_bone = "SmokeProxy_C12_R04"
target_group = source.vertex_groups.new(name=cleanup_target)
cleanup_group = source.vertex_groups.new(name=cleanup_bone)
target_group.add([0], 0.2, "REPLACE")
cleanup_group.add([0], 0.3, "REPLACE")
cleanup_group.lock_weight = True
ordinary_locked_group = source.vertex_groups.new(name="SmokeOrdinaryLocked")
ordinary_locked_group.lock_weight = True
settings.browser_kind = "BONE"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
bpy.ops.object.select_all(action="DESELECT")
source.hide_set(False)
source.select_set(True)
bpy.context.view_layer.objects.active = source
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="LOCKED_VERTEX_GROUPS") == {
    "FINISHED"
}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == {cleanup_bone}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
settings.browser_prefix = "SmokeProxy_C12_"
settings.browser_filter_by_prefix = True


class _BrowserFilterProbe:
    bitflag_filter_item = 1


prefix_flags, _prefix_order = SPX_UL_MMDItems.filter_items(
    _BrowserFilterProbe(),
    bpy.context,
    settings,
    "browser_items",
)
assert sum(bool(flag) for flag in prefix_flags) == 4
settings.browser_search = "R04"
combined_flags, _combined_order = SPX_UL_MMDItems.filter_items(
    _BrowserFilterProbe(),
    bpy.context,
    settings,
    "browser_items",
)
assert sum(bool(flag) for flag in combined_flags) == 1
settings.browser_search = ""
settings.browser_filter_by_prefix = False
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="PREFIX") == {"FINISHED"}
assert sum(item.selected for item in settings.browser_items) == 4
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
branch_roots = {"SmokeProxy_C01_R02", "SmokeProxy_C02_R03"}
for item in settings.browser_items:
    item.selected = item.target_name in branch_roots
expected_branch = set()
for root_name in branch_roots:
    pending = [model_armature.data.bones[root_name]]
    while pending:
        current = pending.pop()
        expected_branch.add(current.name)
        pending.extend(current.children)
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == cleanup_bone
)
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="BONE_BRANCH") == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == expected_branch
settings.browser_index = next(
    index
    for index, item in enumerate(settings.browser_items)
    if item.target_name == cleanup_bone
)
assert bpy.ops.surface_proxy.prefix_from_active_mmd_item() == {"FINISHED"}
assert settings.browser_prefix == "SmokeProxy_C"
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
cleanup_item = next(
    item for item in settings.browser_items if item.target_name == cleanup_bone
)
cleanup_item.selected = True
settings.cleanup_root_bone = cleanup_target
rigid_for_cleanup = next(
    obj for obj in bpy.data.objects if obj.mmd_type == "RIGID_BODY" and obj.mmd_rigid.bone == cleanup_bone
)
rigid_name_for_cleanup = rigid_for_cleanup.name
assert bpy.ops.surface_proxy.cleanup_checked_bones() == {"FINISHED"}
assert cleanup_bone not in model_armature.data.bones
assert source.vertex_groups.get(cleanup_bone) is None
assert abs(source.vertex_groups[cleanup_target].weight(0) - 0.5) < 1.0e-7
assert rigid_name_for_cleanup not in bpy.data.objects

settings.browser_kind = "JOINT"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
joint_names_to_delete = {
    settings.browser_items[0].target_name,
    settings.browser_items[1].target_name,
}
bpy.ops.object.select_all(action="DESELECT")
for joint_name in joint_names_to_delete:
    bpy.data.objects[joint_name].select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects[next(iter(joint_names_to_delete))]
assert bpy.ops.surface_proxy.sync_selected_mmd_objects_to_browser() == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == joint_names_to_delete
assert bpy.ops.surface_proxy.delete_checked_mmd_items() == {"FINISHED"}
assert all(name not in bpy.data.objects for name in joint_names_to_delete)

open_source = build_open_source_mesh("MMDProxyOpenSource")
open_source.parent = model_root
modifier = open_source.modifiers.new(name="MMDProxyOpenArmature", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
open_source.select_set(True)
bpy.context.view_layer.objects.active = open_source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
settings.topology = "OPEN"
settings.columns = 4
settings.rows = 5
settings.prefix = "OpenProxy"
settings.armature = model_armature
settings.write_weights = False
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
open_proxy = bpy.data.objects["OpenProxy_Surface"]
open_rows = list(open_proxy["surface_proxy_column_rows"])
assert not open_proxy["surface_proxy_closed"]
open_source_x = [vertex.co.x for vertex in open_source.data.vertices]
open_source_y = [vertex.co.y for vertex in open_source.data.vertices]
assert all(
    min(open_source_x) <= vertex.co.x <= max(open_source_x)
    and min(open_source_y) <= vertex.co.y <= max(open_source_y)
    for vertex in open_proxy.data.vertices
)
assert len(open_proxy.data.polygons) == len(grid_faces([
    [None] * count for count in open_rows
], closed=False))
open_first = set(range(open_rows[0]))
open_last_offset = sum(open_rows[:-1])
open_last = set(range(open_last_offset, open_last_offset + open_rows[-1]))
assert not any(
    {edge.vertices[0], edge.vertices[1]} & open_first
    and {edge.vertices[0], edge.vertices[1]} & open_last
    for edge in open_proxy.data.edges
)
settings.mmd_root = model_root
settings.physics_proxy = open_proxy
settings.create_horizontal_joints = True
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
open_physics = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == open_proxy.name
]
open_horizontal = [
    obj
    for obj in open_physics
    if obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
expected_open_horizontal = sum(
    max(min(open_rows[column], open_rows[column + 1]) - 1, 0)
    for column in range(len(open_rows) - 1)
)
assert len(open_horizontal) == expected_open_horizontal
open_rigids = [obj for obj in open_physics if obj.mmd_type == "RIGID_BODY"]
open_vertical = [
    obj
    for obj in open_physics
    if obj.get("surface_proxy_role") == "JOINT_VERTICAL"
]
open_anchors = [
    obj
    for obj in open_physics
    if obj.get("surface_proxy_role") == "JOINT_ANCHOR"
]
assert len(open_anchors) == 0
assert all(obj.mmd_rigid.size[0] > 0.001 for obj in open_rigids)
assert all(
    obj.mmd_rigid.shape == "SPHERE" or obj.mmd_rigid.size[1] >= 0.001
    for obj in open_rigids
)
for joint in open_vertical:
    column = int(joint["surface_proxy_column"])
    row = int(joint["surface_proxy_row"])
    bone = model_armature.data.bones[f"OpenProxy_C{column + 1:02d}_R{row + 1:02d}"]
    assert (joint.location - bone.head_local).length < 1.0e-7

near_rigid = next(
    obj
    for obj in open_rigids
    if obj.get("surface_proxy_column") == 1 and obj.get("surface_proxy_row") == 0
)
far_rigid = next(
    obj
    for obj in open_rigids
    if obj.get("surface_proxy_column") == 3 and obj.get("surface_proxy_row") == 3
)
near_size = Vector(near_rigid.mmd_rigid.size)
near_shape = near_rigid.mmd_rigid.shape
near_type = int(near_rigid.mmd_rigid.type)
near_location = near_rigid.location.copy()
near_rotation = Vector(near_rigid.rotation_euler)
far_location = far_rigid.location.copy()
near_joint = next(
    obj
    for obj in open_vertical
    if obj.get("surface_proxy_column") == 1 and obj.get("surface_proxy_row") == 1
)
near_joint_location = near_joint.location.copy()
near_joint_rotation = Vector(near_joint.rotation_euler)
near_horizontal = next(
    obj
    for obj in open_horizontal
    if obj.get("surface_proxy_column") == 1
    and obj.get("surface_proxy_row") == 1
)
near_horizontal_location = near_horizontal.location.copy()
bpy.ops.object.select_all(action="DESELECT")
open_proxy.hide_set(False)
open_proxy.select_set(True)
bpy.context.view_layer.objects.active = open_proxy
open_vertex = open_proxy["surface_proxy_vertex_map"][open_rows[0] + 1]
open_proxy.data.vertices[open_vertex].co.x += 0.08
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
assert (Vector(near_rigid.mmd_rigid.size) - near_size).length < 1.0e-7
assert near_rigid.mmd_rigid.shape == near_shape
assert int(near_rigid.mmd_rigid.type) == near_type
assert (near_rigid.location - near_location).length > 1.0e-5
assert (Vector(near_rigid.rotation_euler) - near_rotation).length > 1.0e-5
assert (far_rigid.location - far_location).length < 1.0e-7
assert (near_joint.location - near_joint_location).length > 1.0e-5
assert (Vector(near_joint.rotation_euler) - near_joint_rotation).length > 1.0e-5
near_bone = model_armature.data.bones["OpenProxy_C02_R02"]
assert (near_joint.location - near_bone.head_local).length < 1.0e-7
assert (near_horizontal.location - near_horizontal_location).length > 1.0e-5
expected_near_horizontal_location = (
    near_horizontal.rigid_body_constraint.object1.location
    + near_horizontal.rigid_body_constraint.object2.location
) * 0.5
assert (
    near_horizontal.location - expected_near_horizontal_location
).length < 1.0e-6

mirror_source, mirror_side_size = build_mirror_source_mesh("MMDProxyMirrorSource")
mirror_source.parent = model_root
modifier = mirror_source.modifiers.new(name="MMDProxyMirrorArmature", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
mirror_source.select_set(True)
bpy.context.view_layer.objects.active = mirror_source
bpy.ops.object.mode_set(mode="EDIT")
mirror_bm = bmesh.from_edit_mesh(mirror_source.data)
mirror_bm.verts.ensure_lookup_table()
for vertex in mirror_bm.verts:
    vertex.select = vertex.index < mirror_side_size
bmesh.update_edit_mesh(mirror_source.data)
settings.topology = "OPEN"
settings.columns = 1
settings.rows = 12
settings.prefix = "左MirrorProxy"
settings.armature = model_armature
settings.write_weights = True
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
mirror_proxy = bpy.data.objects["MirrorProxy_Surface"]
mirror_rows = list(mirror_proxy["surface_proxy_column_rows"])
assert mirror_rows == [12, 12]
assert list(mirror_proxy["surface_proxy_column_groups"]) == [0, 1]
assert list(mirror_proxy["surface_proxy_column_sides"]) == ["L", "R"]
assert list(mirror_proxy["surface_proxy_column_local_indices"]) == [0, 0]
assert mirror_proxy["surface_proxy_mirror_mode"]
assert mirror_proxy["surface_proxy_mirror_exact"]
assert mirror_proxy.data.use_mirror_x
left_name = "MirrorProxy_C01_R01.L"
right_name = "MirrorProxy_C01_R01.R"
assert left_name in model_armature.data.bones
assert right_name in model_armature.data.bones
assert model_armature.pose.bones[left_name].mmd_bone.name_j == "左MirrorProxy_C01_R01"
assert model_armature.pose.bones[left_name].mmd_bone.name_e == "MirrorProxy_C01_R01_L"
assert model_armature.pose.bones[right_name].mmd_bone.name_j == "右MirrorProxy_C01_R01"
assert model_armature.pose.bones[right_name].mmd_bone.name_e == "MirrorProxy_C01_R01_R"
mirror_vertex_map = list(mirror_proxy["surface_proxy_vertex_map"])
for row in range(mirror_rows[0]):
    left = mirror_proxy.data.vertices[mirror_vertex_map[row]].co
    right = mirror_proxy.data.vertices[
        mirror_vertex_map[mirror_rows[0] + row]
    ].co
    assert abs(left.x + right.x) < 1.0e-7
    assert abs(left.y - right.y) < 1.0e-7
    assert abs(left.z - right.z) < 1.0e-7
left_group_names = {
    group.name for group in mirror_source.vertex_groups if group.name.endswith(".L")
}
right_group_names = {
    group.name for group in mirror_source.vertex_groups if group.name.endswith(".R")
}
assert left_group_names and right_group_names
for vertex in mirror_source.data.vertices[:mirror_side_size]:
    names = {
        mirror_source.vertex_groups[item.group].name
        for item in vertex.groups
        if item.weight > 1.0e-8
    }
    assert names & left_group_names
    assert not names & right_group_names
for vertex in mirror_source.data.vertices[mirror_side_size:]:
    names = {
        mirror_source.vertex_groups[item.group].name
        for item in vertex.groups
        if item.weight > 1.0e-8
    }
    assert names & right_group_names
    assert not names & left_group_names
mirror_left_bone = model_armature.data.bones["MirrorProxy_C01_R04.L"]
mirror_right_bone = model_armature.data.bones["MirrorProxy_C01_R04.R"]
mirror_left_head = mirror_left_bone.head_local.copy()
mirror_right_head = mirror_right_bone.head_local.copy()
mirror_proxy.data.vertices[mirror_vertex_map[3]].co.y += 0.025
bpy.context.view_layer.objects.active = mirror_proxy
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
mirror_left_bone = model_armature.data.bones["MirrorProxy_C01_R04.L"]
mirror_right_bone = model_armature.data.bones["MirrorProxy_C01_R04.R"]
assert (mirror_left_bone.head_local - mirror_left_head).length > 0.02
assert (mirror_right_bone.head_local - mirror_right_head).length < 1.0e-7
settings.physics_proxy = mirror_proxy
settings.create_horizontal_joints = True
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
mirror_horizontal = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == mirror_proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
assert not mirror_horizontal
mirror_rigids = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == mirror_proxy.name
    and obj.get("surface_proxy_role") == "RIGID"
]
mirror_joints = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == mirror_proxy.name
    and str(obj.get("surface_proxy_role", "")).startswith("JOINT_")
]
mirror_left_rigid = next(
    obj for obj in mirror_rigids if obj.mmd_rigid.bone.endswith(".L")
)
mirror_right_rigid = next(
    obj for obj in mirror_rigids if obj.mmd_rigid.bone.endswith(".R")
)
assert mirror_left_rigid.mmd_rigid.name_j.startswith("左")
assert mirror_left_rigid.mmd_rigid.name_e.endswith("_L")
assert mirror_right_rigid.mmd_rigid.name_j.startswith("右")
assert mirror_right_rigid.mmd_rigid.name_e.endswith("_R")
assert all(re.match(r"^\d{3}_", obj.name) for obj in mirror_rigids)
assert all(re.match(r"^\d{3}_J\.", obj.name) for obj in mirror_joints)
mirror_left_joint = next(
    joint
    for joint in mirror_joints
    if joint.rigid_body_constraint.object2.mmd_rigid.bone.endswith(".L")
)
mirror_left_rigid = mirror_left_joint.rigid_body_constraint.object2
mirror_right_rigid = next(
    rigid
    for rigid in mirror_rigids
    if rigid.mmd_rigid.bone == mirrored_name(mirror_left_rigid.mmd_rigid.bone)
)
mirror_right_joint = next(
    joint
    for joint in mirror_joints
    if joint.rigid_body_constraint.object2 == mirror_right_rigid
    and joint.mmd_joint.name_e == mirrored_name(mirror_left_joint.mmd_joint.name_e)
)
mirror_left_joint_location = mirror_left_joint.matrix_world.translation.copy()
mirror_left_rigid.rotation_euler = Euler((0.41, -0.28, 0.73), "YXZ")
bpy.context.view_layer.update()
settings.browser_kind = "RIGID"
settings.browser_current_proxy_only = False
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item for item in settings.browser_items if item.target_name == mirror_left_rigid.name
).selected = True
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="MIRROR") == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == {mirror_left_rigid.name, mirror_right_rigid.name}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item for item in settings.browser_items if item.target_name == mirror_left_rigid.name
).selected = True
assert bpy.ops.surface_proxy.sync_joint_axes_from_rigids() == {"FINISHED"}
assert (mirror_left_joint.matrix_world.translation - mirror_left_joint_location).length < 1.0e-7
left_joint_axes = mirror_left_joint.matrix_world.to_3x3().normalized()
left_rigid_axes = mirror_left_rigid.matrix_world.to_3x3().normalized()
assert max(
    abs(left_joint_axes[row][column] - left_rigid_axes[row][column])
    for row in range(3)
    for column in range(3)
) < 1.0e-6
settings.mirror_include_joints = True
assert bpy.ops.surface_proxy.sync_mirrored_mmd_items() == {"FINISHED"}
expected_right_rigid = mirrored_world_matrix(mirror_left_rigid, model_armature)
expected_right_joint = mirrored_world_matrix(mirror_left_joint, model_armature)
assert max(
    abs(mirror_right_rigid.matrix_world[row][column] - expected_right_rigid[row][column])
    for row in range(4)
    for column in range(4)
) < 1.0e-6
assert max(
    abs(mirror_right_joint.matrix_world[row][column] - expected_right_joint[row][column])
    for row in range(4)
    for column in range(4)
) < 1.0e-6
settings.browser_kind = "JOINT"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item for item in settings.browser_items if item.target_name == mirror_left_joint.name
).selected = True
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="MIRROR") == {"FINISHED"}
assert {
    item.target_name for item in settings.browser_items if item.selected
} == {mirror_left_joint.name, mirror_right_joint.name}
assert bpy.ops.surface_proxy.rebind_proxy_weights() == {"FINISHED"}
for vertex in mirror_source.data.vertices[:mirror_side_size]:
    names = {
        mirror_source.vertex_groups[item.group].name
        for item in vertex.groups
        if item.weight > 1.0e-8
    }
    assert not names & right_group_names
for vertex in mirror_source.data.vertices[mirror_side_size:]:
    names = {
        mirror_source.vertex_groups[item.group].name
        for item in vertex.groups
        if item.weight > 1.0e-8
    }
    assert not names & left_group_names

asym_source, asym_side_size = build_mirror_source_mesh(
    "MMDProxyAsymSource", asymmetric=True
)
asym_source.parent = model_root
modifier = asym_source.modifiers.new(name="MMDProxyAsymArmature", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
asym_source.select_set(True)
bpy.context.view_layer.objects.active = asym_source
bpy.ops.object.mode_set(mode="EDIT")
asym_bm = bmesh.from_edit_mesh(asym_source.data)
asym_bm.verts.ensure_lookup_table()
for vertex in asym_bm.verts:
    vertex.select = vertex.index >= asym_side_size
bmesh.update_edit_mesh(asym_source.data)
settings.topology = "OPEN"
settings.columns = 1
settings.rows = 10
settings.prefix = "右AsymProxy"
settings.write_weights = True
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
asym_proxy = bpy.data.objects["AsymProxy_Surface"]
assert asym_proxy["surface_proxy_mirror_mode"]
assert not asym_proxy["surface_proxy_mirror_exact"]
assert not asym_proxy.data.use_mirror_x
asym_rows = list(asym_proxy["surface_proxy_column_rows"])
asym_map = list(asym_proxy["surface_proxy_vertex_map"])
assert any(
    abs(
        asym_proxy.data.vertices[asym_map[row]].co.x
        + asym_proxy.data.vertices[asym_map[asym_rows[0] + row]].co.x
    )
    > 1.0e-4
    for row in range(asym_rows[0])
)
assert "AsymProxy_C01_R01.L" in model_armature.data.bones
assert "AsymProxy_C01_R01.R" in model_armature.data.bones
assert any(group.name.endswith(".L") for group in asym_source.vertex_groups)
assert any(group.name.endswith(".R") for group in asym_source.vertex_groups)

line_source = build_open_source_mesh("MMDProxyLineSource")
line_source.parent = model_root
modifier = line_source.modifiers.new(name="MMDProxyLineArmature", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
line_source.select_set(True)
bpy.context.view_layer.objects.active = line_source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
settings.topology = "OPEN"
settings.columns = 1
settings.rows = 12
settings.prefix = "LineProxy"
settings.armature = model_armature
settings.write_weights = False
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
line_proxy = bpy.data.objects["LineProxy_Surface"]
line_rows = list(line_proxy["surface_proxy_column_rows"])
assert len(line_rows) == 1
assert not line_proxy["surface_proxy_closed"]
assert len(line_proxy.data.polygons) == 4 * (line_rows[0] - 1)
assert len(line_proxy.data.vertices) == 5 * line_rows[0]
assert line_proxy["surface_proxy_sculpt_width"] > 0.0
line_source_x = [vertex.co.x for vertex in line_source.data.vertices]
line_source_y = [vertex.co.y for vertex in line_source.data.vertices]
line_vertex_map = list(line_proxy["surface_proxy_vertex_map"])
assert line_vertex_map == list(range(line_rows[0]))
line_center_vertices = [line_proxy.data.vertices[index] for index in line_vertex_map]
assert all(
    min(line_source_x) <= vertex.co.x <= max(line_source_x)
    and min(line_source_y) <= vertex.co.y <= max(line_source_y)
    for vertex in line_center_vertices
)
assert abs(
    sum(vertex.co.x for vertex in line_center_vertices) / len(line_center_vertices)
    - (min(line_source_x) + max(line_source_x)) * 0.5
) < 0.2
line_points = [vertex.co for vertex in line_center_vertices]
line_segments = [
    (line_points[index + 1] - line_points[index]).length
    for index in range(len(line_points) - 1)
]
assert line_proxy["surface_proxy_sculpt_width"] < sorted(line_segments)[len(line_segments) // 2] * 0.1
line_curvature = max(
    (
        line_points[index - 1].xy
        - line_points[index].xy * 2.0
        + line_points[index + 1].xy
    ).length
    for index in range(1, len(line_points) - 1)
)
assert line_curvature < 0.08, line_curvature
previous_direction = line_points[-2].xy - line_points[-3].xy
terminal_direction = line_points[-1].xy - line_points[-2].xy
assert previous_direction.length > 1.0e-7
assert terminal_direction.length > 1.0e-7
terminal_alignment = previous_direction.normalized().dot(terminal_direction.normalized())
assert terminal_alignment > 0.9999, terminal_alignment
assert sum(bone.name.startswith("LineProxy_C01_") for bone in model_armature.data.bones) == line_rows[0] - 1
line_middle_row = line_rows[0] // 2
line_middle_bone = model_armature.data.bones[
    f"LineProxy_C01_R{line_middle_row + 1:02d}"
]
line_middle_head = line_middle_bone.head_local.copy()
bpy.context.view_layer.objects.active = line_proxy
line_proxy.select_set(True)
assert bpy.ops.object.mode_set(mode="SCULPT") == {"FINISHED"}
assert line_proxy.mode == "SCULPT"
assert bpy.ops.object.mode_set(mode="OBJECT") == {"FINISHED"}
line_proxy.data.vertices[line_vertex_map[line_middle_row]].co.x += 0.1
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
assert (line_middle_bone.head_local - line_middle_head).length > 0.09

line_middle_bone = model_armature.data.bones[
    f"LineProxy_C01_R{line_middle_row + 1:02d}"
]
auto_sync_head = line_middle_bone.head_local.copy()
bpy.ops.object.select_all(action="DESELECT")
line_proxy.select_set(True)
bpy.context.view_layer.objects.active = line_proxy
settings.auto_sync = True
proxy_sync._DIRTY_PHYSICS_PROXIES.clear()
assert proxy_sync._sync_on_proxy_mode_exit() == 0.1
assert bpy.ops.object.mode_set(mode="SCULPT") == {"FINISHED"}
assert proxy_sync._sync_on_proxy_mode_exit() == 0.1
line_proxy.data.vertices[line_vertex_map[line_middle_row]].co.y += 0.075
line_proxy.data.update()
line_middle_bone = model_armature.data.bones[
    f"LineProxy_C01_R{line_middle_row + 1:02d}"
]
assert (line_middle_bone.head_local - auto_sync_head).length < 1.0e-7
assert bpy.ops.object.mode_set(mode="OBJECT") == {"FINISHED"}
assert proxy_sync._sync_on_proxy_mode_exit() == 0.1
line_middle_bone = model_armature.data.bones[
    f"LineProxy_C01_R{line_middle_row + 1:02d}"
]
assert (line_middle_bone.head_local - auto_sync_head).length > 0.07
original_load_proxy_identity = proxy_sync._load_proxy_identity
proxy_sync._load_proxy_identity = lambda _unused: (_ for _ in ()).throw(
    AttributeError("'_RestrictData' object has no attribute 'objects'")
)
assert proxy_sync._initialize_proxy_services() == 0.1
proxy_sync._load_proxy_identity = original_load_proxy_identity
assert proxy_sync._initialize_proxy_services() is None

line_old_bone_names = list(line_proxy["surface_proxy_bone_names"])
line_new_bone_names = []
for index, old_name in enumerate(line_old_bone_names):
    bone = model_armature.data.bones[old_name]
    bone.name = f"RenamedLineBone{index + 1:02d}"
    line_new_bone_names.append(bone.name)
assert list(line_proxy["surface_proxy_bone_names"]) == line_old_bone_names
recovered_armature, recovered_prefix, recovered_rows, recovered_map = (
    proxy_sync.identify_proxy(line_proxy)
)
assert recovered_armature == model_armature
assert recovered_prefix == "LineProxy"
assert recovered_rows == line_rows
assert recovered_map == line_vertex_map
assert list(line_proxy["surface_proxy_bone_names"]) == line_new_bone_names
second_recovered_armature, second_recovered_prefix, second_recovered_rows, second_recovered_map = (
    proxy_sync.identify_proxy(line_proxy)
)
assert second_recovered_armature == model_armature
assert second_recovered_prefix == "LineProxy"
assert second_recovered_rows == line_rows
assert second_recovered_map == line_vertex_map
recovered_middle_bone = model_armature.data.bones[
    line_new_bone_names[line_middle_row]
]
recovered_middle_head = recovered_middle_bone.head_local.copy()
line_proxy.data.vertices[line_vertex_map[line_middle_row]].co.x += 0.05
assert proxy_sync.sync_proxy_bones(bpy.context, line_proxy) == len(line_new_bone_names)
assert (recovered_middle_bone.head_local - recovered_middle_head).length > 0.04

settings.browser_items.clear()
for bone in model_armature.data.bones:
    if bone.name.startswith("SmokeProxyB_C"):
        item = settings.browser_items.add()
        item.kind = "BONE"
        item.target_name = bone.name
        item.armature_name = model_armature.name
        item.selected = True
settings.topology = "CLOSED"
second_proxy = bpy.data.objects["SmokeProxyB_Surface"]
second_proxy.data.vertices[0].co += Vector((0.4, -0.3, 0.2))
second_proxy_identity = second_proxy.as_pointer()
modified_coordinate = second_proxy.data.vertices[0].co.copy()
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"CANCELLED"}
second_proxy = bpy.data.objects["SmokeProxyB_Surface"]
assert second_proxy.as_pointer() == second_proxy_identity
assert second_proxy.data.vertices[0].co == modified_coordinate
assert bpy.data.objects.get("SmokeProxyB_Surface.001") is None
assert second_proxy["surface_proxy_closed"]
assert not second_proxy["surface_proxy_mirror_mode"]

bpy.ops.object.select_all(action="DESELECT")
model_armature.select_set(True)
bpy.context.view_layer.objects.active = model_armature
bpy.ops.object.mode_set(mode="EDIT")
for side, sign in (("L", 1.0), ("R", -1.0)):
    for column in range(4):
        angle = math.tau * column / 4
        x = sign * (1.8 + 0.2 * math.cos(angle))
        y = 0.2 * math.sin(angle)
        for row in range(2):
            bone = model_armature.data.edit_bones.new(
                f"Sleeve_C{column + 1:02d}_R{row + 1:02d}.{side}"
            )
            bone.head = (x, y, 1.0 - row * 0.5)
            bone.tail = (x, y, 0.5 - row * 0.5)
bpy.ops.object.mode_set(mode="OBJECT")
settings.browser_items.clear()
for bone in model_armature.data.bones:
    if bone.name.startswith("Sleeve_C"):
        item = settings.browser_items.add()
        item.kind = "BONE"
        item.target_name = bone.name
        item.armature_name = model_armature.name
        item.selected = True
settings.topology = "CLOSED"
assert bpy.data.objects.get("Sleeve_Surface") is None
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
sleeve_proxy = bpy.data.objects["Sleeve_Surface"]
assert sleeve_proxy["surface_proxy_closed"]
assert sleeve_proxy["surface_proxy_mirror_mode"]
assert sleeve_proxy["surface_proxy_mirror_exact"]
assert sleeve_proxy.data.use_mirror_x
assert list(sleeve_proxy["surface_proxy_column_groups"]) == [0, 0, 0, 0, 1, 1, 1, 1]
assert list(sleeve_proxy["surface_proxy_column_sides"]) == ["L", "L", "L", "L", "R", "R", "R", "R"]
assert len(sleeve_proxy.data.vertices) == 24
assert len(sleeve_proxy.data.polygons) == 16
assert all(
    all(vertex < 12 for vertex in polygon.vertices)
    or all(vertex >= 12 for vertex in polygon.vertices)
    for polygon in sleeve_proxy.data.polygons
)
settings.physics_proxy = sleeve_proxy
settings.mmd_root = model_root
settings.create_horizontal_joints = True
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
sleeve_horizontal = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == sleeve_proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
assert len(sleeve_horizontal) == 16
assert all(
    int(joint["surface_proxy_column"]) // 4
    == int(joint["surface_proxy_following_column"]) // 4
    for joint in sleeve_horizontal
)

bpy.ops.object.select_all(action="DESELECT")
model_armature.select_set(True)
bpy.context.view_layer.objects.active = model_armature
bpy.ops.object.mode_set(mode="EDIT")
hair_chains = (
    (("后发01.L", "后发02.L"), -1.5),
    (("后发11_L", "后发12_L"), -0.5),
    (("后发11_R", "后发12_R"), 0.5),
    (("后发01.R", "后发02.R"), 1.5),
)
for names, x in hair_chains:
    parent = None
    for row, name in enumerate(names):
        bone = model_armature.data.edit_bones.new(name)
        bone.head = (x, 0.25 * abs(x), 2.0 - row * 0.6)
        bone.tail = (x, 0.25 * abs(x), 1.4 - row * 0.6)
        bone.parent = parent
        bone.use_connect = parent is not None
        parent = bone
bpy.ops.object.mode_set(mode="OBJECT")
settings.browser_items.clear()
for names, _x in hair_chains:
    for name in names:
        item = settings.browser_items.add()
        item.kind = "BONE"
        item.target_name = name
        item.armature_name = model_armature.name
        item.selected = True
settings.topology = "OPEN"
settings.restore_connect_sides = False
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
hair_proxy = bpy.data.objects["后发_Surface"]
assert list(hair_proxy["surface_proxy_column_groups"]) == [0, 0, 1, 1]
assert list(hair_proxy["surface_proxy_column_sides"]) == ["L", "L", "R", "R"]
assert len(hair_proxy.data.polygons) == 4
assert all(
    all(vertex < 6 for vertex in polygon.vertices)
    or all(vertex >= 6 for vertex in polygon.vertices)
    for polygon in hair_proxy.data.polygons
)

settings.browser_items.clear()
for names, _x in hair_chains:
    for name in names:
        item = settings.browser_items.add()
        item.kind = "BONE"
        item.target_name = name
        item.armature_name = model_armature.name
        item.selected = True
settings.restore_connect_sides = True
bpy.data.objects.remove(hair_proxy, do_unlink=True)
assert bpy.ops.surface_proxy.restore_proxy_from_checked_bones() == {"FINISHED"}
hair_proxy = bpy.data.objects["后发_Surface"]
assert list(hair_proxy["surface_proxy_column_groups"]) == [0, 0, 0, 0]
assert list(hair_proxy["surface_proxy_bone_names"]) == [
    "后发01.L",
    "后发02.L",
    "后发11_L",
    "后发12_L",
    "后发11_R",
    "后发12_R",
    "后发01.R",
    "后发02.R",
]
assert len(hair_proxy.data.polygons) == 6
assert any(
    any(vertex < 6 for vertex in polygon.vertices)
    and any(vertex >= 6 for vertex in polygon.vertices)
    for polygon in hair_proxy.data.polygons
)
settings.physics_proxy = hair_proxy
hair_bone = model_armature.data.bones["后发11_R"]
hair_head = hair_bone.head_local.copy()
hair_vertex_map = list(hair_proxy["surface_proxy_vertex_map"])
hair_proxy.data.vertices[hair_vertex_map[6]].co.y += 0.12
bpy.context.view_layer.objects.active = hair_proxy
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
hair_bone = model_armature.data.bones["后发11_R"]
assert (hair_bone.head_local - hair_head).length > 0.1
settings.mmd_root = model_root
settings.create_horizontal_joints = True
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
hair_horizontal = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == hair_proxy.name
    and obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
assert len(hair_horizontal) == 6
assert any(
    int(joint["surface_proxy_column"]) == 1
    and int(joint["surface_proxy_following_column"]) == 2
    for joint in hair_horizontal
)
hair_physics = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == hair_proxy.name
]
hair_rigid = next(
    obj
    for obj in hair_physics
    if obj.mmd_type == "RIGID_BODY" and obj.mmd_rigid.bone == "后发01.L"
)
hair_rigid_size = Vector(hair_rigid.mmd_rigid.size)
hair_rigid_shape = hair_rigid.mmd_rigid.shape
hair_rigid_type = int(hair_rigid.mmd_rigid.type)
for obj in hair_physics:
    for key in [name for name in obj.keys() if name.startswith("surface_proxy_")]:
        del obj[key]
settings.auto_sync_physics = False
hair_rigid_location = hair_rigid.location.copy()
hair_proxy.data.vertices[hair_vertex_map[0]].co.y += 0.16
bpy.context.view_layer.objects.active = hair_proxy
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
assert (hair_rigid.location - hair_rigid_location).length < 1.0e-7
assert bpy.ops.surface_proxy.sync_mmd_physics() == {"FINISHED"}
assert (hair_rigid.location - hair_rigid_location).length > 0.05
assert (Vector(hair_rigid.mmd_rigid.size) - hair_rigid_size).length < 1.0e-7
assert hair_rigid.mmd_rigid.shape == hair_rigid_shape
assert int(hair_rigid.mmd_rigid.type) == hair_rigid_type
assert sum(
    obj.get("surface_proxy_object") == hair_proxy.name
    and obj.mmd_type == "RIGID_BODY"
    for obj in hair_physics
) == 8
assert sum(
    obj.get("surface_proxy_object") == hair_proxy.name
    and obj.mmd_type == "JOINT"
    for obj in hair_physics
) == 10
settings.mass = 6.25
settings.mass_interpolate = False
settings.spring_angular = (2.0, 3.0, 4.0)
settings.spring_angular_interpolate = (False, False, False)
settings.horizontal_spring_angular = (5.0, 6.0, 7.0)
settings.horizontal_spring_angular_interpolate = (False, False, False)
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
assert all(
    abs(obj.rigid_body.mass - 6.25) < 1.0e-7
    for obj in hair_physics
    if obj.mmd_type == "RIGID_BODY"
)
assert all(
    tuple(obj.mmd_joint.spring_angular) == (2.0, 3.0, 4.0)
    for obj in hair_physics
    if obj.get("surface_proxy_role") == "JOINT_VERTICAL"
)
assert all(
    tuple(obj.mmd_joint.spring_angular) == (5.0, 6.0, 7.0)
    for obj in hair_physics
    if obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
)
applied_hair_rigid_size = Vector(hair_rigid.mmd_rigid.size)
applied_hair_rigid_shape = hair_rigid.mmd_rigid.shape
applied_hair_rigid_type = int(hair_rigid.mmd_rigid.type)
for obj in hair_physics:
    for key in [name for name in obj.keys() if name.startswith("surface_proxy_")]:
        del obj[key]
settings.auto_sync_physics = True
settings.auto_sync = True
hair_rigid_location = hair_rigid.location.copy()
hair_proxy.data.vertices[hair_vertex_map[0]].co.y += 0.12
hair_proxy.data.update()
proxy_sync._PROXY_MODES[hair_proxy.name] = "SCULPT"
assert proxy_sync._sync_on_proxy_mode_exit() == 0.1
assert (hair_rigid.location - hair_rigid_location).length > 0.04
assert sum(
    obj.get("surface_proxy_object") == hair_proxy.name
    and obj.mmd_type == "RIGID_BODY"
    for obj in hair_physics
) == 8
assert sum(
    obj.get("surface_proxy_object") == hair_proxy.name
    and obj.mmd_type == "JOINT"
    for obj in hair_physics
) == 10
assert (
    Vector(hair_rigid.mmd_rigid.size) - applied_hair_rigid_size
).length < 1.0e-7
assert hair_rigid.mmd_rigid.shape == applied_hair_rigid_shape
assert int(hair_rigid.mmd_rigid.type) == applied_hair_rigid_type
assert all(
    abs(obj.rigid_body.mass - 6.25) < 1.0e-7
    for obj in hair_physics
    if obj.mmd_type == "RIGID_BODY"
)
assert all(
    tuple(obj.mmd_joint.spring_angular) == (2.0, 3.0, 4.0)
    for obj in hair_physics
    if obj.get("surface_proxy_role") == "JOINT_VERTICAL"
)
assert all(
    tuple(obj.mmd_joint.spring_angular) == (5.0, 6.0, 7.0)
    for obj in hair_physics
    if obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
)

hair_physics[0]["surface_proxy_rebuild_sentinel"] = True
unrelated_proxy_rigid = next(
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == second_proxy.name
    and obj.mmd_type == "RIGID_BODY"
)
unrelated_proxy_rigid_name = unrelated_proxy_rigid.name
unrelated_proxy_rigid_mass = unrelated_proxy_rigid.rigid_body.mass
settings.physics_proxy = hair_proxy
settings.mmd_root = model_root
assert bpy.ops.surface_proxy.create_mmd_physics() == {"FINISHED"}
rebuilt_hair_physics = [
    obj
    for obj in bpy.data.objects
    if obj.get("surface_proxy_object") == hair_proxy.name
]
rebuilt_hair_rigids = [
    obj for obj in rebuilt_hair_physics if obj.mmd_type == "RIGID_BODY"
]
rebuilt_hair_joints = [
    obj for obj in rebuilt_hair_physics if obj.mmd_type == "JOINT"
]
assert len(rebuilt_hair_rigids) == 8
assert len(rebuilt_hair_joints) == 10
assert not any(obj.get("surface_proxy_rebuild_sentinel") for obj in bpy.data.objects)
assert sum(
    obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
    and int(obj.get("surface_proxy_row", -1)) == 0
    for obj in rebuilt_hair_joints
) == 3
assert unrelated_proxy_rigid_name in bpy.data.objects
assert (
    abs(
        bpy.data.objects[unrelated_proxy_rigid_name].rigid_body.mass
        - unrelated_proxy_rigid_mass
    )
    < 1.0e-7
)

for forbidden in (
    "mmd_station.solver",
    "mmd_station.native_solver",
    "mmd_station.physics_nodes",
    "mmd_station.colliders",
):
    assert forbidden not in sys.modules

print(
    f"MMD_STATION_SMOKE_OK top_range={top_range:.9f} "
    f"rigids={len(rigids)} joints={len(joints)}"
)
mmd_station.unregister()
assert _mmd_browser_depsgraph_update not in bpy.app.handlers.depsgraph_update_post
assert not bpy.app.timers.is_registered(
    mmd_physics_module._run_mmd_browser_auto_refresh
)
