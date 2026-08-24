from typing import NamedTuple


class PresentationPlan(NamedTuple):
    write_output: bool
    asynchronous: bool
    update_debug: bool
    update_kinematic_debug: bool


def _matrix_changed(first, second, epsilon=1.0e-5):
    if first == second:
        return False
    return any(
        abs(first[row][column] - second[row][column]) > epsilon
        for row in range(4)
        for column in range(4)
    )


class PoseInputAdapter:
    def __init__(self, session):
        self.session = session
        self.native_input_active = False
        self.cached_animation_pose = None
        self.cached_bone_targets = ()
        self.cached_input_basis = {}
        self.cached_root_matrix = None
        self.cached_armature_matrix = None
        self.cached_frame = None
        self.external_input_evaluated = False
        self.self_write_pending = False
        self.force_debug_update = True
        self.debug_ticks_since_update = 0
        self._last_debug_visible = None
        self.cache_hits = 0
        self.fast_captures = 0
        self.input_evaluation_count = 0
        self.output_evaluation_count = 0
        self.output_write_count = 0
        self.skipped_output_count = 0
        self.debug_update_count = 0
        self.kinematic_debug_update_count = 0
        self.refresh_bindings()

    def refresh_bindings(self):
        session = self.session
        self.all_pose_bones = tuple(session.armature.pose.bones)
        self.all_pose_bone_count = len(self.all_pose_bones)
        input_pose_bones = {}
        for pose_bone in session.rigid_pose_bones:
            while pose_bone is not None:
                input_pose_bones[pose_bone.name] = pose_bone
                pose_bone = pose_bone.parent
        self.ordered_input_pose_bones = tuple(
            sorted(input_pose_bones.values(), key=lambda bone: len(bone.parent_recursive))
        )
        reconstructed_names = set()
        driver_names = set(session.driver_pose_bones)
        for pose_bone in self.ordered_input_pose_bones:
            if (
                pose_bone.name in driver_names
                or pose_bone.parent is not None
                and pose_bone.parent.name in reconstructed_names
            ):
                reconstructed_names.add(pose_bone.name)
        self.reconstructed_input_names = frozenset(reconstructed_names)
        self.type_zero_input_safe = not any(
            session.rigid_modes[index] == 0
            and pose_bone is not None
            and pose_bone.name in self.reconstructed_input_names
            for index, pose_bone in enumerate(session.rigid_pose_bones)
        )
        self.refresh_watch_bindings()

    def refresh_watch_bindings(self):
        session = self.session
        display_rig = getattr(session, "display_rig", None)
        if display_rig is None or not getattr(
            session, "_display_rig_valid_cache", False
        ):
            self.watched_pose_bones = self.all_pose_bones
            return
        watched = {
            pose_bone.name: pose_bone
            for pose_bone in self.ordered_input_pose_bones
        }
        watched.update(
            (pose_bone.name, pose_bone)
            for pose_bone in display_rig.source_pose_bones
        )
        self.watched_pose_bones = tuple(watched.values())

    @property
    def fast_external_input_safe(self):
        if getattr(self.session, "isolated_output_active", False):
            return True
        return self.type_zero_input_safe and not any(
            pose_bone.constraints
            for pose_bone in self.ordered_input_pose_bones
            if pose_bone.name in self.reconstructed_input_names
        )

    def set_native_input_active(self, active):
        active = bool(active)
        if active == self.native_input_active:
            return
        self.native_input_active = active
        self.invalidate()

    def invalidate(self):
        self.cached_animation_pose = None
        self.cached_bone_targets = ()
        self.cached_input_basis = {}
        self.cached_root_matrix = None
        self.cached_armature_matrix = None
        self.cached_frame = None
        self.external_input_evaluated = False
        self.self_write_pending = False
        self.force_debug_update = True
        self.debug_ticks_since_update = 0

    def raw_input_changes(self):
        session = self.session
        if self.cached_animation_pose is None:
            return True, False
        current_frame = (session.scene.frame_current, session.scene.frame_subframe)
        if (
            self.cached_frame != current_frame
            or self.cached_root_matrix is None
            or session.root.matrix_world != self.cached_root_matrix
            or self.cached_armature_matrix is None
            or session.armature.matrix_world != self.cached_armature_matrix
            or self.all_pose_bone_count != len(session.armature.pose.bones)
        ):
            return True, False
        changed = False
        driver_changed = False
        isolated_output = getattr(session, "isolated_output_active", False)
        for pose_bone in self.watched_pose_bones:
            if pose_bone.name in session.driver_pose_bones and not isolated_output:
                expected = session.last_output_basis.get(pose_bone.name)
                if expected is None or _matrix_changed(
                    pose_bone.matrix_basis,
                    expected,
                ):
                    changed = True
                    driver_changed = True
            else:
                expected = self.cached_input_basis.get(pose_bone.name)
                if expected is None or _matrix_changed(
                    pose_bone.matrix_basis,
                    expected,
                ):
                    changed = True
                    if pose_bone.name in session.driver_pose_bones:
                        driver_changed = True
        return changed, driver_changed

    def _remember_input_state(self):
        session = self.session
        isolated_output = bool(
            getattr(session, "_display_rig_valid_cache", False)
        )
        self.cached_input_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.watched_pose_bones
            if (
                isolated_output
                or pose_bone.name not in session.driver_pose_bones
            )
        }
        self.cached_root_matrix = session.root.matrix_world.copy()
        self.cached_armature_matrix = session.armature.matrix_world.copy()
        self.cached_frame = (
            session.scene.frame_current,
            session.scene.frame_subframe,
        )
        self.external_input_evaluated = False
        display_rig = getattr(session, "display_rig", None)
        if display_rig is not None and isolated_output:
            display_rig.capture_input_pose()

    def cache_prepared_input(
        self,
        animation_pose,
        targets,
        force_presentation=True,
    ):
        self.cached_animation_pose = {
            name: matrix.copy() for name, matrix in animation_pose.items()
        }
        self.cached_bone_targets = tuple(targets)
        self._remember_input_state()
        if force_presentation:
            self.force_debug_update = True

    def reuse_prepared_input(self):
        session = self.session
        session.pending_animation_pose = self.cached_animation_pose
        session.solver.set_bone_targets(
            (session.body_offset + index, target)
            for index, target in self.cached_bone_targets
        )
        self.cache_hits += 1

    def capture_evaluated_input(self):
        session = self.session
        if getattr(session, "isolated_output_active", False):
            canonical_pose = {
                pose_bone.name: pose_bone.matrix.copy()
                for pose_bone in self.ordered_input_pose_bones
            }
            animation_pose = canonical_pose
            targets = session._submit_pose_targets(canonical_pose)
            self.cache_prepared_input(
                animation_pose,
                targets,
                force_presentation=False,
            )
            session.pending_animation_pose = self.cached_animation_pose
            self.fast_captures += 1
            return
        canonical_pose = {}
        for pose_bone in self.ordered_input_pose_bones:
            if pose_bone.name not in self.reconstructed_input_names:
                canonical_pose[pose_bone.name] = pose_bone.matrix.copy()
                continue
            basis = session.saved_basis.get(pose_bone.name, pose_bone.matrix_basis)
            parent = pose_bone.parent
            if parent is None:
                canonical_pose[pose_bone.name] = pose_bone.bone.convert_local_to_pose(
                    basis,
                    pose_bone.bone.matrix_local,
                )
            else:
                canonical_pose[pose_bone.name] = pose_bone.bone.convert_local_to_pose(
                    basis,
                    pose_bone.bone.matrix_local,
                    parent_matrix=canonical_pose[parent.name],
                    parent_matrix_local=parent.bone.matrix_local,
                )
        animation_pose = canonical_pose
        targets = session._submit_pose_targets(canonical_pose)
        self.cache_prepared_input(
            animation_pose,
            targets,
            force_presentation=False,
        )
        session.pending_animation_pose = self.cached_animation_pose
        self.fast_captures += 1

    def presentation_plan(self, interactive, optimized):
        session = self.session
        debug_visible = bool(session.settings.preview_update_rigids)
        if debug_visible and self._last_debug_visible is False:
            self.force_debug_update = True
        self._last_debug_visible = debug_visible
        isolated_output = getattr(session, "isolated_output_active", False)
        if not interactive:
            return PresentationPlan(
                True,
                False,
                debug_visible,
                debug_visible,
            )

        self.debug_ticks_since_update += 1
        debug_divisor = max(
            1,
            round(float(session.settings.preview_frequency) / 15.0),
        )
        update_debug = bool(
            debug_visible
            and (
                self.force_debug_update
                or self.debug_ticks_since_update >= debug_divisor
            )
        )
        if not optimized or not self.type_zero_input_safe and not isolated_output:
            return PresentationPlan(True, True, update_debug, debug_visible)
        if (
            self.self_write_pending
            and not self.native_input_active
            and not isolated_output
        ):
            return PresentationPlan(False, False, False, False)
        return PresentationPlan(True, True, update_debug, debug_visible)

    def mark_output(
        self,
        written,
        asynchronous=False,
        debug_updated=False,
        kinematic_debug_updated=False,
    ):
        if written:
            self.output_write_count += 1
            if kinematic_debug_updated:
                self.kinematic_debug_update_count += 1
            if debug_updated:
                self.debug_update_count += 1
                self.debug_ticks_since_update = 0
                self.force_debug_update = False
            if asynchronous:
                self.self_write_pending = True
            else:
                self.output_evaluation_count += 1
                self.self_write_pending = False
        else:
            self.skipped_output_count += 1

    def acknowledge_self_write(self):
        if not self.self_write_pending:
            return False
        self.self_write_pending = False
        self.output_evaluation_count += 1
        return True

    def acknowledge_synchronous_evaluation(self):
        if self.self_write_pending:
            self.output_evaluation_count += 1
            self.self_write_pending = False
