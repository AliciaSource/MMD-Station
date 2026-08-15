import math
import pathlib
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")

import mmd_skirt_proxy_creator
from mmd_skirt_proxy_creator import sync as proxy_sync
from mmd_skirt_proxy_creator.core import grid_faces
from mmd_skirt_proxy_creator.mmd_physics import (
    PHYSICS_SETTING_NAMES,
    SPX_OT_AddPhysicsPreset,
    _joint_interpolation_factor,
    _mmd_api,
    _rigid_interpolation_factor,
    draw_physics_settings,
)
from mmd_skirt_proxy_creator.physics_preview.ffi import ABI_VERSION, SolverLibrary
import mmd_skirt_proxy_creator.physics_preview.runtime as preview_runtime
from mmd_skirt_proxy_creator.physics_preview.runtime import (
    transform_to_components,
)
from bl_ext.blender_org.mmd_tools.core.model import Model


entry_source = pathlib.Path(mmd_skirt_proxy_creator.__file__).read_text(encoding="utf-8")
assert "?" not in entry_source
assert mmd_skirt_proxy_creator.SPX_PT_SurfaceProxyCreator.bl_label == "\u88d9\u9762\u4ee3\u7406\u521b\u5efa\u5668"


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


mmd_skirt_proxy_creator.register()
model = Model.create("MMDProxySmoke", add_root_bone=True)
model_root = model.rootObject()
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
assert settings.rigid_shape == "BOX"
assert settings.top_rigid_type == "2"
assert settings.body_rigid_type == "1"
assert settings.topology == "CLOSED"
assert settings.bl_rna.properties["columns"].hard_min == 1
assert settings.auto_sync_physics
assert settings.rigid_radius_ratio == 0.0
assert settings.rigid_length_ratio == 0.0
assert settings.rigid_depth_ratio == 0.0
assert settings.mass == 0.0
assert settings.friction == 0.0
assert tuple(settings.limit_angular_lower) == (0.0, 0.0, 0.0)
assert tuple(settings.spring_angular) == (0.0, 0.0, 0.0)
assert bpy.ops.surface_proxy.apply_stable_long_skirt_preset() == {"FINISHED"}
assert settings.rigid_shape == "BOX"
assert settings.mass == 2.0
assert settings.mass_interpolate
assert settings.mass_end == 0.5
assert math.isclose(settings.linear_damping, 0.995, abs_tol=1.0e-7)
assert math.isclose(settings.linear_damping_end, 0.98, abs_tol=1.0e-7)
assert tuple(round(math.degrees(value)) for value in settings.limit_angular_lower) == (-8, -3, -3)
assert tuple(round(math.degrees(value)) for value in settings.limit_angular_lower_end) == (-18, -7, -7)
assert tuple(settings.limit_angular_interpolate) == (True, True, True)
assert tuple(settings.spring_linear) == (0.0, 800.0, 0.0)
assert tuple(settings.spring_linear_end) == (0.0, 250.0, 0.0)
assert tuple(settings.spring_linear_interpolate) == (False, True, False)
assert tuple(round(math.degrees(value)) for value in settings.horizontal_limit_angular_upper) == (4, 3, 5)
assert tuple(round(math.degrees(value)) for value in settings.horizontal_limit_angular_upper_end) == (8, 5, 12)
assert tuple(settings.horizontal_limit_angular_interpolate) == (True, True, True)
assert tuple(settings.horizontal_spring_angular) == (3.0, 1.5, 4.0)
assert tuple(settings.horizontal_spring_angular_end) == (1.0, 0.5, 1.5)
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
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
first_bone = armature.pose.bones["SmokeProxy_C02_R01"]
second_bone = armature.pose.bones["SmokeProxy_C02_R02"]
first_bone.mmd_bone.name_j = ""
first_bone.mmd_bone.name_e = ""
second_bone.mmd_bone.name_j = "保留名称"
second_bone.mmd_bone.name_e = ""
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
next(
    item
    for item in settings.browser_items
    if item.target_name == first_bone.name
).selected = True
assert bpy.ops.surface_proxy.fill_missing_mmd_bone_names(scope="CHECKED") == {"FINISHED"}
assert first_bone.mmd_bone.name_j == first_bone.name
assert first_bone.mmd_bone.name_e == first_bone.name
assert second_bone.mmd_bone.name_j == "保留名称"
assert second_bone.mmd_bone.name_e == ""
assert bpy.ops.surface_proxy.fill_missing_mmd_bone_names(scope="ALL") == {"FINISHED"}
assert second_bone.mmd_bone.name_j == "保留名称"
assert second_bone.mmd_bone.name_e == second_bone.name
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
    max(min(row_counts[column], row_counts[(column + 1) % len(row_counts)]) - 2, 0)
    for column in range(len(row_counts))
)
assert len(rigids) == expected_rigids, (len(rigids), expected_rigids)
assert settings.preview_scope == "CURRENT_PROXY"
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
preview_library = SolverLibrary()
assert preview_library.dll.mmd_solver_abi_version() == ABI_VERSION
settings.preview_frequency = 60
settings.preview_substeps = 2
settings.top_rigid_type = "2"
settings.body_rigid_type = "2"
assert bpy.ops.surface_proxy.update_mmd_physics() == {"FINISHED"}
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
preview_session = preview_runtime._ACTIVE_SESSION
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
assert preview_runtime._ACTIVE_SESSION is preview_session
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


original_create_solver = preview_session._create_solver
preview_session.tick = fail_preview_tick_once
preview_session._create_solver = fail_solver_rebuild
assert preview_runtime._timer_tick() is not None
assert preview_runtime._ACTIVE_SESSION is preview_session
assert settings.preview_running
assert settings.preview_status.startswith("运行中：启动快照恢复失败，将继续重试")
assert bpy.app.timers.is_registered(preview_runtime._timer_tick)
preview_session.tick = original_tick
preview_session._create_solver = original_create_solver
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
assert preview_runtime._ACTIVE_SESSION is preview_session
assert settings.preview_running
reset_count_before_clear = preview_session.auto_reset_count


def assert_preview_alignment(session):
    body_transforms = session.solver.transforms()
    bone_transforms = session.solver.bone_transforms()
    for index, rigid in enumerate(session.rigids):
        body_position, _body_rotation = transform_to_components(body_transforms[index])
        assert (rigid.matrix_world.translation - Vector(body_position)).length < 1.0e-6
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
            assert (bone_world.translation - Vector(bone_position)).length < 1.0e-5
    for pose_bone in generated_bones:
        parent = pose_bone.parent
        if parent is None or parent.name not in session.bone_drivers:
            continue
        driver = session.rigids[session.bone_drivers[pose_bone.name]]
        parent_driver = session.rigids[session.bone_drivers[parent.name]]
        if int(driver.mmd_rigid.type) != 2 or int(parent_driver.mmd_rigid.type) != 2:
            continue
        parent_tail = parent.matrix @ Vector((0.0, parent.length, 0.0))
        assert (pose_bone.matrix.translation - parent_tail).length < 1.0e-5
    for joint, state in zip(session.joints, session.solver.joint_states()):
        position_a, _rotation_a = transform_to_components(state.frame_a)
        position_b, _rotation_b = transform_to_components(state.frame_b)
        midpoint = (Vector(position_a) + Vector(position_b)) * 0.5
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
assert preview_max_displacement < 0.01, preview_max_displacement
assert preview_max_bone_deviation < 0.01, preview_max_bone_deviation
solver_before_clear = preview_session.solver
for pose_bone in model_armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()
preview_session.tick()
assert preview_session.auto_reset_count == reset_count_before_clear + 1
assert preview_session.solver is not solver_before_clear
assert preview_runtime._ACTIVE_SESSION is preview_session
assert settings.preview_running
assert_preview_alignment(preview_session)
solver_before_manual_reset = preview_session.solver
assert bpy.ops.surface_proxy.reset_mmd_physics_preview() == {"FINISHED"}
assert preview_runtime._ACTIVE_SESSION is preview_session
assert preview_session.solver is not solver_before_manual_reset

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
assert preview_runtime._ACTIVE_SESSION is None
assert preview_bone.matrix_basis == preview_basis
assert anchor_pose_bone.matrix_basis == anchor_basis
assert all(
    model_armature.pose.bones[name].matrix_basis == matrix_basis
    for name, matrix_basis in preview_saved_pose.items()
)
assert unrelated_rigid.matrix_world == unrelated_matrix
settings.preview_scope = "MODEL"
assert bpy.ops.surface_proxy.start_mmd_physics_preview() == {"FINISHED"}
model_preview_session = preview_runtime._ACTIVE_SESSION
assert model_preview_session is not None
assert unrelated_rigid in model_preview_session.rigids
assert model_preview_session.dynamic_rigid_count == expected_rigids + 1
assert bpy.ops.surface_proxy.stop_mmd_physics_preview() == {"FINISHED"}
assert preview_runtime._ACTIVE_SESSION is None
settings.preview_scope = "CURRENT_PROXY"
unrelated_mesh = unrelated_rigid.data
bpy.data.objects.remove(unrelated_rigid, do_unlink=True)
if unrelated_mesh.users == 0:
    bpy.data.meshes.remove(unrelated_mesh)
assert len(joints) == expected_anchors + expected_vertical + expected_horizontal, (
    len(joints),
    expected_anchors + expected_vertical + expected_horizontal,
)
assert all(obj.mmd_rigid.bone in armature.data.bones for obj in rigids)
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
    normal = Vector(rigid["surface_proxy_normal"])
    assert (rigid.rotation_euler.to_matrix() @ Vector((0.0, 1.0, 0.0))).dot(normal) > 0.9999
vertical_joints = [
    obj for obj in joints if obj.get("surface_proxy_role") == "JOINT_VERTICAL"
]
horizontal_joints = [
    obj for obj in joints if obj.get("surface_proxy_role") == "JOINT_HORIZONTAL"
]
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
        expected_x = settings.horizontal_spring_angular[0] + (
            settings.horizontal_spring_angular_end[0]
            - settings.horizontal_spring_angular[0]
        ) * factor
    assert abs(joint.mmd_joint.spring_angular[0] - expected_x) < 1.0e-7, (
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
    and obj.get("surface_proxy_row") == 1
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
result = bpy.ops.surface_proxy.update_mmd_physics()
assert result == {"FINISHED"}, result
assert all(abs(obj.rigid_body.mass - 2.5) < 1.0e-7 for obj in rigids)
assert all(tuple(obj.mmd_joint.spring_angular) == (4.0, 5.0, 6.0) for obj in vertical_joints)
assert all(tuple(obj.mmd_joint.spring_angular) == (9.0, 10.0, 11.0) for obj in horizontal_joints)

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
settings.mmd_root = model_root
settings.mass = 7.0
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
    def __init__(self, records=None):
        self.records = records if records is not None else []
        self.enabled = True

    def box(self):
        return LayoutProbe(self.records)

    def row(self, **_kwargs):
        return LayoutProbe(self.records)

    def column(self, **_kwargs):
        return LayoutProbe(self.records)

    def grid_flow(self, **_kwargs):
        return LayoutProbe(self.records)

    def label(self, **_kwargs):
        return None

    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), name
        self.records.append((name, kwargs.get("index"), kwargs.get("text")))

    def prop_search(self, data, name, *_args, **kwargs):
        self.prop(data, name, **kwargs)

    def operator(self, *_args, **_kwargs):
        return type("OperatorProbe", (), {})()

    def menu(self, *_args, **_kwargs):
        return None


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
        numbered = [
            (index, text)
            for name, index, text in probe.records
            if name == "collision_group_mask"
        ]
        assert numbered == [(index, str(index + 1)) for index in range(16)]

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
settings.browser_kind = "BONE"
assert bpy.ops.surface_proxy.refresh_mmd_browser() == {"FINISHED"}
assert bpy.ops.surface_proxy.set_mmd_browser_checks(action="NONE") == {"FINISHED"}
settings.browser_prefix = "SmokeProxy_C12_"
assert bpy.ops.surface_proxy.quick_check_mmd_group(mode="PREFIX") == {"FINISHED"}
assert sum(item.selected for item in settings.browser_items) == 4
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
settings.browser_items[0].selected = True
settings.browser_items[1].selected = True
assert bpy.ops.surface_proxy.delete_checked_mmd_items() == {"FINISHED"}
assert all(name not in bpy.data.objects for name in joint_names_to_delete)

open_source = build_source_mesh("MMDProxyOpenSource")
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
    max(min(open_rows[column], open_rows[column + 1]) - 2, 0)
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
far_location = far_rigid.location.copy()
bpy.ops.object.select_all(action="DESELECT")
open_proxy.hide_set(False)
open_proxy.select_set(True)
bpy.context.view_layer.objects.active = open_proxy
open_vertex = open_proxy["surface_proxy_vertex_map"][open_rows[0] + 1]
open_proxy.data.vertices[open_vertex].co.x += 0.08
assert bpy.ops.surface_proxy.sync_proxy_bones() == {"FINISHED"}
assert (Vector(near_rigid.mmd_rigid.size) - near_size).length > 1.0e-5
assert (far_rigid.location - far_location).length < 1.0e-7
near_joint = next(
    obj
    for obj in open_vertical
    if obj.get("surface_proxy_column") == 1 and obj.get("surface_proxy_row") == 1
)
near_bone = model_armature.data.bones["OpenProxy_C02_R02"]
assert (near_joint.location - near_bone.head_local).length < 1.0e-7

line_source = build_source_mesh("MMDProxyLineSource")
line_source.parent = model_root
modifier = line_source.modifiers.new(name="MMDProxyLineArmature", type="ARMATURE")
modifier.object = model_armature
bpy.ops.object.select_all(action="DESELECT")
line_source.select_set(True)
bpy.context.view_layer.objects.active = line_source
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
settings.topology = "CLOSED"
settings.columns = 1
settings.rows = 5
settings.prefix = "LineProxy"
settings.armature = model_armature
settings.write_weights = False
assert bpy.ops.surface_proxy.create_skirt_proxy() == {"FINISHED"}
line_proxy = bpy.data.objects["LineProxy_Surface"]
line_rows = list(line_proxy["surface_proxy_column_rows"])
assert len(line_rows) == 1
assert not line_proxy["surface_proxy_closed"]
assert len(line_proxy.data.polygons) == 0
assert len(line_proxy.data.edges) == line_rows[0] - 1
assert sum(bone.name.startswith("LineProxy_C01_") for bone in model_armature.data.bones) == line_rows[0] - 1

for forbidden in (
    "mmd_skirt_proxy_creator.solver",
    "mmd_skirt_proxy_creator.native_solver",
    "mmd_skirt_proxy_creator.physics_nodes",
    "mmd_skirt_proxy_creator.colliders",
):
    assert forbidden not in sys.modules

print(
    f"MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range={top_range:.9f} "
    f"rigids={len(rigids)} joints={len(joints)}"
)
mmd_skirt_proxy_creator.unregister()
