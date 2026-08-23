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
        self.deferred_output_pending = False
        self.force_presentation = True
        self.presentation_phase = 0
        self.cache_hits = 0
        self.fast_captures = 0
        self.input_evaluation_count = 0
        self.output_evaluation_count = 0
        self.refresh_bindings()

    def refresh_bindings(self):
        session = self.session
        self.all_pose_bones = tuple(session.armature.pose.bones)
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

    @property
    def fast_external_input_safe(self):
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
        self.force_presentation = True

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
            or len(self.all_pose_bones) != len(session.armature.pose.bones)
        ):
            return True, False
        changed = False
        driver_changed = False
        for pose_bone in self.all_pose_bones:
            if pose_bone.name in session.driver_pose_bones:
                expected = session.last_output_basis.get(pose_bone.name)
                if expected is None or pose_bone.matrix_basis != expected:
                    changed = True
                    driver_changed = True
            else:
                expected = self.cached_input_basis.get(pose_bone.name)
                if expected is None or pose_bone.matrix_basis != expected:
                    changed = True
        return changed, driver_changed

    def _remember_input_state(self):
        session = self.session
        self.cached_input_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.all_pose_bones
            if pose_bone.name not in session.driver_pose_bones
        }
        self.cached_root_matrix = session.root.matrix_world.copy()
        self.cached_armature_matrix = session.armature.matrix_world.copy()
        self.cached_frame = (
            session.scene.frame_current,
            session.scene.frame_subframe,
        )
        self.external_input_evaluated = False

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
            self.force_presentation = True

    def reuse_prepared_input(self):
        session = self.session
        session.pending_animation_pose = self.cached_animation_pose
        for index, target in self.cached_bone_targets:
            session.solver.set_bone_target(session.body_offset + index, target)
        self.cache_hits += 1

    def capture_evaluated_input(self):
        session = self.session
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
        animation_pose = {
            pose_bone.name: canonical_pose[pose_bone.name]
            for pose_bone in session.ordered_pose_bones
        }
        targets = session._submit_pose_targets(canonical_pose)
        self.cache_prepared_input(
            animation_pose,
            targets,
            force_presentation=False,
        )
        session.pending_animation_pose = self.cached_animation_pose
        self.fast_captures += 1

    def presentation_due(self, interactive, optimized):
        session = self.session
        if not interactive or not optimized:
            self.presentation_phase = 0
            return True
        if self.force_presentation:
            self.presentation_phase = 0
            return True
        divisor = max(1, int(session.settings.preview_frequency / 30))
        if divisor == 1:
            return True
        self.presentation_phase = (self.presentation_phase + 1) % divisor
        return self.presentation_phase == 0

    def mark_output(self, presented):
        if presented:
            self.output_evaluation_count += 1
            self.deferred_output_pending = False
            self.force_presentation = False
        else:
            self.deferred_output_pending = True
