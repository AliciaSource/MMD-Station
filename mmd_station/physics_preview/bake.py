import json
import time
import uuid

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import runtime


BAKE_SCHEMA = 1
_ACTIVE_JOB = None


def _action_uid(action):
    uid = str(action.get("mmd_station_action_uid", ""))
    if not uid:
        if action.library is not None:
            raise RuntimeError("源 Action 来自只读 Library，无法建立烘焙身份")
        uid = uuid.uuid4().hex
        action["mmd_station_action_uid"] = uid
    return uid


def _source_action(armature):
    animation_data = armature.animation_data
    action = animation_data.action if animation_data is not None else None
    if action is None:
        raise RuntimeError("当前 MMD Armature 没有活动 Action")
    source_uid = str(action.get("mmd_station_physics_source_uid", ""))
    if source_uid:
        for candidate in bpy.data.actions:
            if (
                not candidate.get("mmd_station_physics_generated", False)
                and str(candidate.get("mmd_station_action_uid", "")) == source_uid
            ):
                return candidate
        raise RuntimeError("烘焙 Action 对应的源 Action 已不存在")
    return action


def _output_action(root, source_action):
    source_uid = str(source_action.get("mmd_station_action_uid", ""))
    if not source_uid:
        return None
    for action in bpy.data.actions:
        if (
            action.get("mmd_station_physics_generated", False)
            and str(action.get("mmd_station_physics_source_uid", "")) == source_uid
            and str(action.get("mmd_station_physics_root", "")) == root.name
        ):
            return action
    return None


def _segments(action):
    if action is None:
        return []
    try:
        value = json.loads(str(action.get("mmd_station_physics_segments", "[]")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _store_segments(action, segments):
    action["mmd_station_physics_segments"] = json.dumps(
        segments,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def current_bake_set(settings):
    root = settings.mmd_root
    if root is None:
        return None, None, []
    armature = runtime._model_armature(root)
    if armature is None or armature.animation_data is None:
        return None, None, []
    try:
        source = _source_action(armature)
    except RuntimeError:
        return None, None, []
    try:
        output = _output_action(root, source)
    except RuntimeError:
        return source, None, []
    return source, output, _segments(output)


def active_progress():
    job = _ACTIVE_JOB
    if job is None:
        return None
    elapsed = max(time.perf_counter() - job.solve_started_at, 1.0e-6)
    completed = job.output_frames_completed
    simulation_completed = job.frame_index
    speed = simulation_completed / elapsed
    remaining = max(len(job.steps) - simulation_completed, 0)
    return {
        "mode": job.mode,
        "frame": job.current_frame,
        "start": job.start,
        "end": job.end,
        "completed": completed,
        "total": job.output_frame_count,
        "factor": completed / max(job.output_frame_count, 1),
        "speed": speed,
        "eta": remaining / speed if speed > 1.0e-6 else 0.0,
        "phase": job.phase,
    }


def _escape_bone_name(name):
    return bpy.utils.escape_identifier(name)


def _rotation_sample(pose_bone, previous):
    mode = pose_bone.rotation_mode
    if mode == "QUATERNION":
        value = pose_bone.matrix_basis.to_quaternion()
        if previous is not None and value.dot(previous) < 0.0:
            value.negate()
        return "rotation_quaternion", tuple(value), value.copy()
    if mode == "AXIS_ANGLE":
        quaternion = pose_bone.matrix_basis.to_quaternion()
        axis, angle = quaternion.to_axis_angle()
        return "rotation_axis_angle", (angle, *axis), quaternion
    euler = pose_bone.matrix_basis.to_euler(mode, previous)
    return "rotation_euler", tuple(euler), euler.copy()


def _capture_pose(session, previous_rotations):
    result = {}
    for name, pose_bone in session.driver_pose_bones.items():
        if pose_bone is None:
            continue
        location = tuple(pose_bone.matrix_basis.to_translation())
        rotation_path, rotation, previous = _rotation_sample(
            pose_bone,
            previous_rotations.get(name),
        )
        previous_rotations[name] = previous
        result[name] = (location, rotation_path, rotation)
    return result


def _point_snapshot(point):
    return {
        "co": tuple(point.co),
        "interpolation": point.interpolation,
        "easing": point.easing,
        "handle_left_type": point.handle_left_type,
        "handle_right_type": point.handle_right_type,
        "handle_left": tuple(point.handle_left),
        "handle_right": tuple(point.handle_right),
    }


def _replace_curve_range(action, data_path, index, group, start, end, samples):
    curve = action.fcurves.find(data_path, index=index)
    if curve is None:
        curve = action.fcurves.new(data_path, index=index, action_group=group)
    retained = [
        _point_snapshot(point)
        for point in curve.keyframe_points
        if float(point.co.x) < start or float(point.co.x) > end
    ]
    points = retained + [
        {
            "co": (float(frame), float(value)),
            "interpolation": "LINEAR",
            "easing": "AUTO",
            "handle_left_type": "VECTOR",
            "handle_right_type": "VECTOR",
            "handle_left": (float(frame), float(value)),
            "handle_right": (float(frame), float(value)),
        }
        for frame, value in samples
    ]
    _rebuild_curve_points(curve, points)


def _rebuild_curve_points(curve, points):
    points.sort(key=lambda item: item["co"][0])
    while curve.keyframe_points:
        curve.keyframe_points.remove(curve.keyframe_points[-1], fast=True)
    curve.keyframe_points.add(len(points))
    coordinates = [component for item in points for component in item["co"]]
    curve.keyframe_points.foreach_set("co", coordinates)
    for point, item in zip(curve.keyframe_points, points, strict=True):
        point.interpolation = item["interpolation"]
        point.easing = item["easing"]
        point.handle_left_type = item["handle_left_type"]
        point.handle_right_type = item["handle_right_type"]
        if item["interpolation"] != "LINEAR":
            point.handle_left = item["handle_left"]
            point.handle_right = item["handle_right"]
    curve.update()


def _restore_curve_range(output, source, data_path, index, start, end):
    output_curve = output.fcurves.find(data_path, index=index)
    if output_curve is None:
        return
    source_curve = source.fcurves.find(data_path, index=index)
    retained = [
        _point_snapshot(point)
        for point in output_curve.keyframe_points
        if float(point.co.x) < start or float(point.co.x) > end
    ]
    restored = [] if source_curve is None else [
        _point_snapshot(point)
        for point in source_curve.keyframe_points
        if start <= float(point.co.x) <= end
    ]
    if not retained and not restored:
        output.fcurves.remove(output_curve)
        return
    _rebuild_curve_points(output_curve, retained + restored)


def _restore_segment_curves(output, source, segment, armature):
    bone_names = segment.get("bones") or [bone.name for bone in armature.data.bones]
    start = int(segment["start"])
    end = int(segment["end"])
    for bone_name in bone_names:
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone is None:
            continue
        escaped = _escape_bone_name(bone_name)
        paths = ((f'pose.bones["{escaped}"].location', 3),)
        if pose_bone.rotation_mode == "QUATERNION":
            paths += ((f'pose.bones["{escaped}"].rotation_quaternion', 4),)
        elif pose_bone.rotation_mode == "AXIS_ANGLE":
            paths += ((f'pose.bones["{escaped}"].rotation_axis_angle', 4),)
        else:
            paths += ((f'pose.bones["{escaped}"].rotation_euler', 3),)
        for data_path, size in paths:
            for index in range(size):
                _restore_curve_range(output, source, data_path, index, start, end)


def _write_samples(action, frames, samples_by_bone, start, end):
    for bone_name, poses in samples_by_bone.items():
        escaped = _escape_bone_name(bone_name)
        location_path = f'pose.bones["{escaped}"].location'
        rotation_path = poses[0][1]
        rotation_data_path = f'pose.bones["{escaped}"].{rotation_path}'
        for index in range(3):
            values = [(frame, pose[0][index]) for frame, pose in zip(frames, poses)]
            _replace_curve_range(
                action,
                location_path,
                index,
                bone_name,
                start,
                end,
                values,
            )
        rotation_size = len(poses[0][2])
        for index in range(rotation_size):
            values = [(frame, pose[2][index]) for frame, pose in zip(frames, poses)]
            _replace_curve_range(
                action,
                rotation_data_path,
                index,
                bone_name,
                start,
                end,
                values,
            )


def _new_output_action(root, source_action):
    action = source_action.copy()
    action.name = source_action.name + " · Physics Bake"
    action["mmd_station_physics_generated"] = True
    action["mmd_station_physics_schema"] = BAKE_SCHEMA
    action["mmd_station_physics_source_uid"] = _action_uid(source_action)
    action["mmd_station_physics_source_name"] = source_action.name
    action["mmd_station_physics_root"] = root.name
    action.pop("mmd_station_action_uid", None)
    _store_segments(action, [])
    return action


def _upsert_segment(segments, segment):
    start = segment["start"]
    end = segment["end"]
    kept = [
        item
        for item in segments
        if int(item.get("end", -1)) < start or int(item.get("start", 0)) > end
    ]
    for item in kept:
        if (
            item.get("continuity") == "CONTINUE"
            and int(item.get("start", 0)) > end
            and int(item.get("simulation_start", item["start"])) <= end
        ):
            item["status"] = "STALE"
    kept.append(segment)
    kept.sort(key=lambda item: (int(item["start"]), int(item["end"])))
    return kept


def _continuation_origin(segments, start):
    previous = next(
        (item for item in segments if int(item.get("end", -1)) == start - 1),
        None,
    )
    if previous is None:
        raise RuntimeError("续接烘焙要求已有区间恰好结束于起始帧的前一帧")
    if previous.get("status") == "STALE":
        raise RuntimeError("上一烘焙区间已过期，请先重新烘焙该区间")
    return int(previous.get("simulation_start", previous["start"]))


class BakeJob:
    def __init__(self, context, mode):
        self.context = context
        self.scene = context.scene
        self.settings = self.scene.surface_proxy_creator
        self.root = self.settings.mmd_root
        if self.root is None:
            raise RuntimeError("请先选择一个 MMD 模型")
        if runtime.is_running():
            runtime.stop_preview(restore=True)
        self.armature = runtime._model_armature(self.root)
        if self.armature is None:
            raise RuntimeError("所选 MMD 模型没有 Armature")
        self.source_action = _source_action(self.armature)
        _action_uid(self.source_action)
        self.output_action = _output_action(self.root, self.source_action)
        self.existing_segments = _segments(self.output_action)
        self.start = int(self.settings.physics_bake_start)
        self.end = int(self.settings.physics_bake_end)
        if self.end < self.start:
            raise RuntimeError("烘焙结束帧不能早于起始帧")
        self.mode = mode
        self.continuation = self.settings.physics_bake_continuity
        self.preroll = int(self.settings.physics_bake_preroll)
        if self.continuation == "CONTINUE":
            self.simulation_start = _continuation_origin(
                self.existing_segments,
                self.start,
            )
            self.steps = [
                (frame, frame >= self.start)
                for frame in range(self.simulation_start, self.end + 1)
            ]
        else:
            self.simulation_start = self.start
            self.steps = [
                *((self.start, False) for _index in range(self.preroll)),
                *((frame, True) for frame in range(self.start, self.end + 1)),
            ]
        self.frame_index = 0
        self.current_frame = self.simulation_start
        self.output_frames_completed = 0
        self.output_frame_count = self.end - self.start + 1
        self.output_frames = []
        self.samples_by_bone = {}
        self.previous_rotations = {}
        self.started_at = time.perf_counter()
        self.next_playback_time = self.started_at
        self.phase = "准备物理"
        self.original_frame = self.scene.frame_current
        self.original_action = self.armature.animation_data.action
        self.original_root_matrix = self.root.matrix_world.copy()
        self.original_armature_matrix = self.armature.matrix_world.copy()
        self.original_pose_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.armature.pose.bones
        }
        self.original_rigid_matrices = {
            obj.name: obj.matrix_world.copy()
            for obj in runtime._rigid_objects(self.root)
        }
        self.original_joint_matrices = {
            obj.name: obj.matrix_world.copy()
            for obj in runtime._joint_objects(self.root)
        }
        self.original_visibility = {
            obj.name: obj.hide_get()
            for obj in (self.root, *self.root.children_recursive)
            if obj.name in self.context.view_layer.objects
        }
        self.work_collection = None
        self.work_objects = []
        self.work_data = []
        self.work_root = self.root
        self.work_armature = self.armature
        self.action_bindings = ()
        self.session = None
        self.world = None
        self.closed = False
        try:
            if self.mode == "FAST":
                self._create_working_copy()
            self.action_bindings = self._build_action_bindings()
            self._prepare()
        except Exception:
            if self.world is not None:
                self.world.close()
            if self.session is not None:
                self.session.close(restore=True)
            self.restore_display_state()
            self.restore_visibility()
            self._remove_working_copy()
            raise
        self.solve_started_at = time.perf_counter()
        self.settings.physics_bake_progress = 0.0

    def _prepare(self):
        self.work_armature.animation_data_create()
        self.work_armature.animation_data.action = self.source_action
        if self.mode == "FAST":
            self._evaluate_source_action(self.simulation_start)
        else:
            self.scene.frame_set(self.simulation_start)
        self.context.view_layer.update()
        self.session = runtime.PreviewSession(
            self.scene,
            self.settings,
            self.work_root,
            armature=self.work_armature,
        )
        self.session.suppress_redraw = self.mode == "FAST"
        self.session.offline_bake = True
        self.world = runtime.PreviewWorld(
            ("bake", self.work_root.name, id(self)),
            self.session.import_scale,
            self.session.solver_target,
            self.session.library,
        )
        self.world.add(self.session)
        self.world.reset(prepared_session=self.session)
        self.phase = "预热" if self.preroll and self.continuation == "INDEPENDENT" else "烘焙"

    def _create_working_copy(self):
        collection = bpy.data.collections.new(
            f".MMD Station Bake {uuid.uuid4().hex[:8]}"
        )
        self.scene.collection.children.link(collection)
        self.work_collection = collection
        sources = (self.root, *self.root.children_recursive)
        copies = {}
        for source in sources:
            duplicate = source.copy()
            if source.type == "ARMATURE":
                duplicate.data = source.data.copy()
                self.work_data.append(duplicate.data)
            collection.objects.link(duplicate)
            copies[source] = duplicate
            self.work_objects.append(duplicate)
        for source, duplicate in copies.items():
            duplicate.parent = copies.get(source.parent)
            duplicate.matrix_parent_inverse = source.matrix_parent_inverse.copy()
            duplicate.matrix_world = source.matrix_world.copy()
            self._remap_constraint_targets(duplicate.constraints, copies)
            if duplicate.rigid_body_constraint is not None:
                source_constraint = source.rigid_body_constraint
                duplicate.rigid_body_constraint.object1 = copies.get(
                    source_constraint.object1,
                    source_constraint.object1,
                )
                duplicate.rigid_body_constraint.object2 = copies.get(
                    source_constraint.object2,
                    source_constraint.object2,
                )
            if duplicate.type == "ARMATURE":
                for pose_bone in duplicate.pose.bones:
                    self._remap_constraint_targets(pose_bone.constraints, copies)
            duplicate.hide_set(True)
            duplicate.hide_render = True
        self.work_root = copies[self.root]
        self.work_armature = copies[self.armature]

    @staticmethod
    def _remap_constraint_targets(constraints, copies):
        for constraint in constraints:
            for property_name in ("target", "pole_target"):
                if not hasattr(constraint, property_name):
                    continue
                target = getattr(constraint, property_name)
                duplicate = copies.get(target)
                if duplicate is not None:
                    setattr(constraint, property_name, duplicate)

    def _remove_working_copy(self):
        for obj in reversed(self.work_objects):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        self.work_objects.clear()
        for data in self.work_data:
            if data.users == 0 and data.name in bpy.data.armatures:
                bpy.data.armatures.remove(data)
        self.work_data.clear()
        if (
            self.work_collection is not None
            and self.work_collection.name in bpy.data.collections
        ):
            bpy.data.collections.remove(self.work_collection)
        self.work_collection = None

    def _build_action_bindings(self):
        bindings = []
        for curve in self.source_action.fcurves:
            if curve.mute or not curve.is_valid:
                continue
            owner_path, separator, property_name = curve.data_path.rpartition(".")
            try:
                owner = (
                    self.work_armature.path_resolve(owner_path)
                    if separator
                    else self.work_armature
                )
                value = getattr(owner, property_name)
            except (AttributeError, ValueError):
                continue
            value_kind = (
                "ARRAY"
                if hasattr(value, "__len__")
                else "BOOLEAN"
                if isinstance(value, bool)
                else "INTEGER"
                if isinstance(value, int)
                else "FLOAT"
            )
            bindings.append((curve, owner, property_name, value_kind))
        return tuple(bindings)

    def _evaluate_source_action(self, frame):
        for curve, owner, property_name, value_kind in self.action_bindings:
            value = curve.evaluate(frame)
            if value_kind == "ARRAY":
                getattr(owner, property_name)[curve.array_index] = value
            elif value_kind == "BOOLEAN":
                setattr(owner, property_name, value >= 0.5)
            elif value_kind == "INTEGER":
                setattr(owner, property_name, round(value))
            else:
                setattr(owner, property_name, value)
        self.work_armature.update_tag(refresh={"OBJECT"})
        if self.session is not None:
            self.session.offline_frame = frame

    def restore_display_state(self):
        self.armature.animation_data.action = self.original_action
        if self.mode != "FAST":
            self.scene.frame_set(self.original_frame)
            self.context.view_layer.update()
        self.root.matrix_world = self.original_root_matrix
        self.armature.matrix_world = self.original_armature_matrix
        for name, matrix_basis in self.original_pose_basis.items():
            pose_bone = self.armature.pose.bones.get(name)
            if pose_bone is not None:
                pose_bone.matrix_basis = matrix_basis
        for name, matrix_world in self.original_rigid_matrices.items():
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.matrix_world = matrix_world
        for name, matrix_world in self.original_joint_matrices.items():
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.matrix_world = matrix_world

    def restore_visibility(self):
        for name, hidden in self.original_visibility.items():
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_set(hidden)

    def step(self):
        if self.frame_index >= len(self.steps):
            return False
        frame, store_output = self.steps[self.frame_index]
        self.current_frame = frame
        if self.work_armature.animation_data.action is not self.source_action:
            self.work_armature.animation_data.action = self.source_action
        if self.mode == "FAST":
            self._evaluate_source_action(frame)
        else:
            self.scene.frame_set(frame)
        self.session.prepare_step()
        fps = self.scene.render.fps / max(self.scene.render.fps_base, 1.0e-6)
        self.world.pending_step_seconds = 1.0 / max(fps, 1.0e-6)
        if self.world.step():
            self.session.apply_step(
                *self.world.outputs(),
                present_output=self.mode == "PLAYBACK",
                update_debug=False,
            )
        pose = _capture_pose(self.session, self.previous_rotations)
        if store_output:
            for bone_name, sample in pose.items():
                self.samples_by_bone.setdefault(bone_name, []).append(sample)
            self.output_frames.append(frame)
            self.output_frames_completed += 1
            self.settings.physics_bake_progress = (
                self.output_frames_completed / max(self.output_frame_count, 1)
            )
            self.phase = "烘焙"
        self.frame_index += 1
        return self.frame_index < len(self.steps)

    def finish(self):
        self.phase = "写入 Action"
        previous_output = self.output_action
        output = (
            previous_output.copy()
            if previous_output is not None
            else _new_output_action(self.root, self.source_action)
        )
        final_name = (
            previous_output.name
            if previous_output is not None
            else output.name
        )
        output.name = final_name + ".tmp"
        elapsed = max(time.perf_counter() - self.started_at, 0.0)
        segment = {
            "id": uuid.uuid4().hex,
            "start": self.start,
            "end": self.end,
            "simulation_start": self.simulation_start,
            "continuity": self.continuation,
            "mode": self.mode,
            "preroll": self.preroll if self.continuation == "INDEPENDENT" else 0,
            "seconds": round(elapsed, 6),
            "frames_per_second": round(self.output_frame_count / max(elapsed, 1.0e-6), 3),
            "bones": sorted(self.samples_by_bone),
        }
        try:
            _write_samples(
                output,
                self.output_frames,
                self.samples_by_bone,
                self.start,
                self.end,
            )
            _store_segments(output, _upsert_segment(self.existing_segments, segment))
        except Exception:
            bpy.data.actions.remove(output, do_unlink=True)
            raise
        if previous_output is not None:
            if previous_output.users == 0:
                bpy.data.actions.remove(previous_output)
            else:
                previous_output["mmd_station_physics_generated"] = False
                previous_output["mmd_station_physics_superseded"] = True
                previous_output.name = final_name + " · Previous"
        output.name = final_name
        self.armature.animation_data.action = output
        self.output_action = output
        self.close(restore_action=False)
        return segment

    def close(self, restore_action=True):
        if self.closed:
            return
        self.closed = True
        try:
            if self.world is not None:
                self.world.close()
            if self.session is not None:
                self.session.close(restore=True)
        finally:
            self._remove_working_copy()
            if restore_action and self.armature is not None:
                self.restore_display_state()
            else:
                self.scene.frame_set(self.original_frame)
            self.restore_visibility()


def _redraw(context):
    if context.area is not None:
        context.area.tag_redraw()


class SPX_OT_BakeMMDPhysics(Operator):
    bl_idname = "surface_proxy.bake_mmd_physics"
    bl_label = "烘焙 MMD 物理"
    bl_options = {"REGISTER"}

    mode: EnumProperty(
        items=(
            ("FAST", "快速烘焙", "在临时复制体上求解，本体保持原姿势且不播放时间轴"),
            ("PLAYBACK", "播放烘焙", "逐帧显示物理结果并同步写入烘焙数据"),
        ),
        options={"HIDDEN"},
    )

    def invoke(self, context, _event):
        global _ACTIVE_JOB
        if _ACTIVE_JOB is not None:
            self.report({"ERROR"}, "已有物理烘焙正在运行")
            return {"CANCELLED"}
        try:
            _ACTIVE_JOB = BakeJob(context, self.mode)
        except (RuntimeError, OSError, ValueError) as error:
            _ACTIVE_JOB = None
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self._timer = context.window_manager.event_timer_add(
            0.001,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        context.window_manager.progress_begin(0, _ACTIVE_JOB.output_frame_count)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global _ACTIVE_JOB
        job = _ACTIVE_JOB
        if job is None:
            return {"CANCELLED"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            self._cancel(context, "已取消物理烘焙")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if job.mode == "PLAYBACK" and time.perf_counter() < job.next_playback_time:
            return {"RUNNING_MODAL"}
        try:
            running = True
            deadline = time.perf_counter() + (0.25 if job.mode == "FAST" else 0.0)
            while running:
                running = job.step()
                if job.mode != "FAST" or time.perf_counter() >= deadline:
                    break
            if job.mode == "PLAYBACK":
                fps = context.scene.render.fps / max(
                    context.scene.render.fps_base,
                    1.0e-6,
                )
                scheduled = job.next_playback_time + 1.0 / max(fps, 1.0e-6)
                job.next_playback_time = max(scheduled, time.perf_counter())
            context.window_manager.progress_update(job.output_frames_completed)
            _redraw(context)
            if running:
                return {"RUNNING_MODAL"}
            segment = job.finish()
        except Exception as error:
            self._cancel(context, f"物理烘焙失败：{error}")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self._finish_modal(context)
        _ACTIVE_JOB = None
        self.report(
            {"INFO"},
            f"已烘焙 {segment['start']}–{segment['end']}，"
            f"平均 {segment['frames_per_second']:.1f} 帧/秒",
        )
        return {"FINISHED"}

    def _finish_modal(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.window_manager.progress_end()
        _redraw(context)

    def _cancel(self, context, message):
        global _ACTIVE_JOB
        if _ACTIVE_JOB is not None:
            _ACTIVE_JOB.close(restore_action=True)
        _ACTIVE_JOB = None
        self._finish_modal(context)
        self.report({"WARNING"}, message)


class SPX_OT_ClearMMDPhysicsBake(Operator):
    bl_idname = "surface_proxy.clear_mmd_physics_bake"
    bl_label = "清空当前动作烘焙"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        source, output, segments = current_bake_set(settings)
        if source is None or output is None or not segments:
            self.report({"WARNING"}, "当前动作没有物理烘焙")
            return {"CANCELLED"}
        root = settings.mmd_root
        armature = runtime._model_armature(root)
        if armature.animation_data is not None and armature.animation_data.action is output:
            armature.animation_data.action = source
        bpy.data.actions.remove(output, do_unlink=True)
        return {"FINISHED"}


class SPX_OT_DeleteMMDPhysicsBakeSegment(Operator):
    bl_idname = "surface_proxy.delete_mmd_physics_bake_segment"
    bl_label = "删除烘焙区间"
    bl_options = {"REGISTER", "UNDO"}

    segment_id: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        source, output, segments = current_bake_set(settings)
        segment = next(
            (item for item in segments if item.get("id") == self.segment_id),
            None,
        )
        if source is None or output is None or segment is None:
            self.report({"WARNING"}, "烘焙区间已不存在")
            return {"CANCELLED"}
        armature = runtime._model_armature(settings.mmd_root)
        _restore_segment_curves(output, source, segment, armature)
        remaining = [item for item in segments if item is not segment]
        deleted_end = int(segment["end"])
        for item in remaining:
            if (
                item.get("continuity") == "CONTINUE"
                and int(item.get("start", 0)) > deleted_end
            ):
                item["status"] = "STALE"
        _store_segments(output, remaining)
        return {"FINISHED"}


def register_settings(cls):
    annotations = cls.__annotations__
    annotations["physics_bake_start"] = IntProperty(name="起始", default=1)
    annotations["physics_bake_end"] = IntProperty(name="结束", default=250)
    annotations["physics_bake_preroll"] = IntProperty(
        name="预热",
        description="独立烘焙正式写入前只求解、不写关键帧的帧数",
        default=30,
        min=0,
    )
    annotations["physics_bake_continuity"] = EnumProperty(
        name="衔接方式",
        items=(
            ("INDEPENDENT", "独立烘焙", "从预热区间建立新的物理状态"),
            ("CONTINUE", "续接上一段", "重放相邻已完成区间并从其末尾继续"),
        ),
        default="INDEPENDENT",
    )
    annotations["physics_bake_progress"] = FloatProperty(
        name="烘焙进度",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        options={"HIDDEN", "SKIP_SAVE"},
    )


def draw_bake(layout, settings):
    box = layout.box()
    box.label(text="物理动画烘焙", icon="ACTION")
    root_row = box.row()
    root_row.enabled = _ACTIVE_JOB is None
    root_row.prop(settings, "mmd_root")
    range_row = box.row(align=True)
    range_row.enabled = _ACTIVE_JOB is None
    range_row.prop(settings, "physics_bake_start")
    range_row.prop(settings, "physics_bake_end")
    range_row.prop(settings, "physics_bake_preroll")
    continuity_row = box.row()
    continuity_row.enabled = _ACTIVE_JOB is None
    continuity_row.prop(settings, "physics_bake_continuity", expand=True)

    progress = active_progress()
    if progress is not None:
        progress_box = box.box()
        mode = "快速烘焙" if progress["mode"] == "FAST" else "播放烘焙"
        progress_box.label(text=f"{mode}：{progress['phase']}", icon="TIME")
        progress_row = progress_box.row()
        progress_row.enabled = False
        progress_row.prop(
            settings,
            "physics_bake_progress",
            text=f"{progress['completed']} / {progress['total']}",
            slider=True,
        )
        progress_box.label(
            text=(
                f"当前帧 {progress['frame']}  ·  "
                f"{progress['speed']:.1f} 帧/秒  ·  "
                f"预计剩余 {progress['eta']:.1f} 秒"
            )
        )
        progress_box.label(text="按 Esc 或鼠标右键取消", icon="INFO")
    else:
        buttons = box.row(align=True)
        fast = buttons.operator(
            SPX_OT_BakeMMDPhysics.bl_idname,
            text="快速烘焙",
            icon="FF",
        )
        fast.mode = "FAST"
        playback = buttons.operator(
            SPX_OT_BakeMMDPhysics.bl_idname,
            text="播放烘焙",
            icon="PLAY",
        )
        playback.mode = "PLAYBACK"

    source, output, segments = current_bake_set(settings)
    if source is not None:
        box.label(text=f"源动作：{source.name}", icon="ACTION")
    if output is not None:
        box.label(text=f"输出动作：{output.name}")
    if segments:
        completed = box.box()
        header = completed.row(align=True)
        header.label(text="已完成烘焙区间", icon="CHECKMARK")
        clear = header.row(align=True)
        clear.enabled = _ACTIVE_JOB is None
        clear.operator(SPX_OT_ClearMMDPhysicsBake.bl_idname, text="清空")
        for segment in segments:
            mode = "快速" if segment.get("mode") == "FAST" else "播放"
            continuity = (
                "续接" if segment.get("continuity") == "CONTINUE" else "独立"
            )
            segment_row = completed.row(align=True)
            status = "  ·  已过期" if segment.get("status") == "STALE" else ""
            segment_row.label(
                text=(
                    f"{int(segment['start'])}–{int(segment['end'])}  ·  "
                    f"{continuity}  ·  {mode}  ·  "
                    f"{float(segment.get('frames_per_second', 0.0)):.1f} 帧/秒{status}"
                )
            )
            delete = segment_row.operator(
                SPX_OT_DeleteMMDPhysicsBakeSegment.bl_idname,
                text="",
                icon="X",
            )
            delete.segment_id = str(segment.get("id", ""))


def cancel_active_bake():
    global _ACTIVE_JOB
    if _ACTIVE_JOB is not None:
        _ACTIVE_JOB.close(restore_action=True)
        _ACTIVE_JOB = None


CLASSES = (
    SPX_OT_BakeMMDPhysics,
    SPX_OT_ClearMMDPhysicsBake,
    SPX_OT_DeleteMMDPhysicsBakeSegment,
)
