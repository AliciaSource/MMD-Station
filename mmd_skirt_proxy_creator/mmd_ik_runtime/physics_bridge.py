from .runtime import selected_armature


_ORIGINAL_MODEL_ARMATURE = None
_ORIGINAL_SESSION_INIT = None
_ORIGINAL_PREPARE_STEP = None
_ORIGINAL_APPLY_STEP = None
_ORIGINAL_STOP_PREVIEW = None
_ORIGINAL_WORLD_RESET = None
_ORIGINAL_SESSION_CLOSE = None


def install():
    global _ORIGINAL_MODEL_ARMATURE, _ORIGINAL_SESSION_INIT, _ORIGINAL_PREPARE_STEP, _ORIGINAL_APPLY_STEP, _ORIGINAL_STOP_PREVIEW, _ORIGINAL_WORLD_RESET, _ORIGINAL_SESSION_CLOSE
    if _ORIGINAL_MODEL_ARMATURE is not None:
        return
    from ..physics_preview import runtime as physics_runtime

    _ORIGINAL_MODEL_ARMATURE = physics_runtime._model_armature
    _ORIGINAL_SESSION_INIT = physics_runtime.PreviewSession.__init__
    _ORIGINAL_PREPARE_STEP = physics_runtime.PreviewSession.prepare_step
    _ORIGINAL_APPLY_STEP = physics_runtime.PreviewSession.apply_step
    _ORIGINAL_STOP_PREVIEW = physics_runtime.stop_preview
    _ORIGINAL_WORLD_RESET = physics_runtime.PreviewWorld.reset
    _ORIGINAL_SESSION_CLOSE = physics_runtime.PreviewSession.close

    def runtime_aware_model_armature(root):
        armature = selected_armature(root)
        return armature if armature is not None else _ORIGINAL_MODEL_ARMATURE(root)

    def direct_resolved_pose(preview_session, native_session):
        basis_overrides = {}
        for name, matrix_basis in preview_session.saved_basis.items():
            if name in native_session.mapped_pose_names:
                continue
            if name in preview_session.driver_pose_bones:
                basis_overrides[name] = matrix_basis
        basis_overrides.update(preview_session._mmd_ik_modal_pose_matrices)
        operation_center = preview_session.armature.pose.bones.get("操作中心")
        matrix_overrides = (
            {operation_center.name: operation_center.matrix.copy()}
            if operation_center is not None
            else None
        )
        return native_session.resolved_output_pose(
            preview_session.armature,
            preview_session.direct_input_pose_bones(),
            basis_overrides=basis_overrides,
            matrix_overrides=matrix_overrides,
        )

    def runtime_aware_session_init(self, scene, settings, root):
        return _ORIGINAL_SESSION_INIT(self, scene, settings, root)

    def runtime_aware_prepare_step(self):
        from .evaluator import _session_for_root

        try:
            native_session = _session_for_root(self.root)
        except (AttributeError, ReferenceError):
            self._native_pose_provider_compatible = False
            self._mmd_ik_direct_pose_active = False
            return _ORIGINAL_PREPARE_STEP(self)
        if native_session is None:
            self.pose_input.set_native_input_active(False)
            self._native_pose_provider_compatible = False
            self._mmd_ik_direct_pose_active = False
            return _ORIGINAL_PREPARE_STEP(self)
        self.pose_input.set_native_input_active(True)
        from .evaluator import (
            _transform_modal_pose_matrices,
            capture_physics_bindings,
            evaluate_physics_pose,
            prepare_physics_targets,
            uses_direct_pose_input,
        )

        if getattr(native_session, "physics_bindings_dirty", False):
            capture_physics_bindings(self.root, self)
        modal_pose_matrices = _transform_modal_pose_matrices(self.armature)
        if not modal_pose_matrices and native_session.partial_input_basis:
            native_session.reconcile_input_basis(self.armature, self.scene)
        self._native_pose_provider_compatible = uses_direct_pose_input(
            self.root,
            self,
            use_cached_overrides=bool(modal_pose_matrices),
        )
        self._mmd_ik_direct_pose_active = False
        previous_suspended = native_session.suspended
        native_session.suspended = True
        try:
            self._mmd_ik_modal_pose_matrices = modal_pose_matrices
            self.ik_motion_anchor = physics_runtime._model_motion_anchor(self.armature)
            operation_center = self.armature.pose.bones.get("操作中心")
            operation_center_matrix = (
                operation_center.matrix.copy() if operation_center is not None else None
            )
            exact_targets = bool(
                self.solver_target == "MMD"
                and self._native_pose_provider_compatible
            )
            direct_pose_input = bool(
                self._native_pose_provider_compatible
                and self.isolated_output_active
            )
            native_session.set_direct_input_isolated(direct_pose_input)
            if not direct_pose_input:
                native_session.pending_input_signature = ()
            native_pose_active = (
                evaluate_physics_pose(
                    self.root,
                    self,
                    update=False,
                    apply_output=not direct_pose_input,
                    sync_state=False,
                    direct_input=direct_pose_input,
                    basis_updates=modal_pose_matrices,
                )
                is not None
            )
            if (
                not direct_pose_input
                and operation_center is not None
                and operation_center_matrix is not None
            ):
                operation_center.matrix = operation_center_matrix
            direct_pose_prepared = False
            if direct_pose_input:
                pose_matrices = direct_resolved_pose(self, native_session)
                if pose_matrices is not None:
                    exact_target_indices = (
                        frozenset(
                            binding[0]
                            for binding in native_session.physics_target_bindings
                        )
                        if exact_targets
                        else ()
                    )
                    direct_pose_prepared = self.prepare_step_from_pose(
                        pose_matrices,
                        excluded_target_indices=exact_target_indices,
                    )
            if direct_pose_prepared:
                self._mmd_ik_direct_pose_active = True
                if exact_targets:
                    prepare_physics_targets(
                        self.root,
                        self,
                        exact_targets=True,
                    )
                return None
            if direct_pose_input:
                native_session.set_direct_input_isolated(False)
                native_session.pending_input_signature = ()
                native_session._apply_output(
                    self.armature,
                    self.scene,
                    update=False,
                    sync_state=False,
                )
                if operation_center is not None and operation_center_matrix is not None:
                    operation_center.matrix = operation_center_matrix
            reset_probe = (
                self._broad_pose_reset_detected if native_pose_active else None
            )
            if native_pose_active:
                self._broad_pose_reset_detected = lambda: False
            try:
                result = _ORIGINAL_PREPARE_STEP(self)
            finally:
                if native_pose_active:
                    self._broad_pose_reset_detected = reset_probe
            if exact_targets:
                prepare_physics_targets(
                    self.root,
                    self,
                    exact_targets=True,
                )
            return result
        finally:
            native_session.suspended = previous_suspended

    def runtime_aware_apply_step(
        self,
        transforms=None,
        bone_transforms=None,
        joint_states=None,
        present_output=True,
    ):
        from .evaluator import _session_for_root

        try:
            native_session = _session_for_root(self.root)
        except (AttributeError, ReferenceError):
            return _ORIGINAL_APPLY_STEP(
                self,
                transforms,
                bone_transforms,
                joint_states,
                present_output=present_output,
            )
        if native_session is None:
            return _ORIGINAL_APPLY_STEP(
                self,
                transforms,
                bone_transforms,
                joint_states,
                present_output=present_output,
            )
        if transforms is None:
            transforms = self.solver.transforms()
        if bone_transforms is None:
            bone_transforms = self.solver.bone_transforms()
        from .evaluator import submit_physics_feedback

        previous_suspended = native_session.suspended
        previous_deferred = getattr(self, "_defer_presentation_update", False)
        direct_pose_active = bool(
            getattr(self, "_mmd_ik_direct_pose_active", False)
            and self.isolated_output_active
        )
        native_session.suspended = True
        self._defer_presentation_update = True
        try:
            feedback_submitted = 0
            if direct_pose_active:
                feedback_submitted = submit_physics_feedback(
                    self.root,
                    self,
                    transforms,
                    update=False,
                    apply_output=False,
                    sync_state=False,
                )
                if feedback_submitted:
                    post_physics_pose = direct_resolved_pose(self, native_session)
                    self.pending_animation_pose = post_physics_pose
                    self.display_rig.input_pose = post_physics_pose
            result = _ORIGINAL_APPLY_STEP(
                self,
                transforms,
                bone_transforms,
                joint_states,
                present_output=present_output,
            )
            if not direct_pose_active:
                submit_physics_feedback(
                    self.root,
                    self,
                    transforms,
                    update=False,
                    apply_output=present_output,
                    sync_state=False,
                )
            if not present_output:
                return result
            if not direct_pose_active:
                preserved = getattr(self, "_mmd_ik_modal_pose_matrices", {})
                for name, matrix in sorted(
                    preserved.items(),
                    key=lambda item: len(
                        self.armature.pose.bones[item[0]].parent_recursive
                    ),
                ):
                    pose_bone = self.armature.pose.bones.get(name)
                    if pose_bone is not None:
                        pose_bone.matrix_basis = matrix
                if preserved:
                    self.armature.update_tag(refresh={"OBJECT"})
                if not (
                    previous_deferred
                    or getattr(self, "_asynchronous_presentation", False)
                ):
                    self.update_view_layer()
            native_session.sync_output_pose(
                self.armature,
                self.scene,
                known_signature=(
                    native_session.input_signature
                    if direct_pose_active
                    and native_session.input_signature[:2]
                    == (
                        int(self.scene.frame_current),
                        float(self.scene.frame_subframe),
                    )
                    else None
                ),
                direct_input=direct_pose_active,
            )
            return result
        finally:
            self._mmd_ik_direct_pose_active = False
            self._defer_presentation_update = previous_deferred
            native_session.suspended = previous_suspended

    def runtime_aware_stop_preview(root=None, restore=True):
        if root is None:
            sessions = tuple(
                dict.fromkeys(physics_runtime._ACTIVE_SESSIONS.values())
            )
        else:
            session = physics_runtime._session_for_root(root)
            sessions = (session,) if session is not None else ()
        from .evaluator import (
            _session_for_root,
            capture_live_input,
            replay_live,
            restore_live_input,
        )

        records = []
        for session in sessions:
            item = physics_runtime._live_object(session.root)
            snapshot = None
            if item is not None:
                try:
                    snapshot = capture_live_input(item)
                except Exception:
                    snapshot = None
            native_session = _session_for_root(item) if item is not None else None
            records.append((session, item, snapshot, native_session))
        result = None
        try:
            result = _ORIGINAL_STOP_PREVIEW(root, restore)
        finally:
            from .evaluator import clear_physics_feedback, discard_session

            for session, previous_root, snapshot, native_session in records:
                item = physics_runtime._live_object(session.root) or previous_root
                if physics_runtime._live_object(item) is None:
                    discard_session(expected_session=native_session)
                    continue
                try:
                    if restore_live_input(item, snapshot):
                        replay_live(item, scene=session.scene)
                except Exception:
                    pass
                try:
                    clear_physics_feedback(item)
                except Exception:
                    pass
        return result

    def runtime_aware_world_reset(
        self,
        prepared_session=None,
        *,
        restore_snapshots=True,
    ):
        from .evaluator import capture_physics_bindings, clear_physics_feedback

        errors = []
        for preview_session in self.sessions:
            try:
                clear_physics_feedback(preview_session.root)
            except Exception as error:
                errors.append(error)
        result = _ORIGINAL_WORLD_RESET(
            self,
            prepared_session=prepared_session,
            restore_snapshots=restore_snapshots,
        )
        for preview_session in self.sessions:
            try:
                capture_physics_bindings(preview_session.root, preview_session)
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]
        return result

    def runtime_aware_session_close(self, restore=True):
        from .evaluator import clear_physics_feedback

        clear_error = None
        try:
            clear_physics_feedback(self.root)
        except Exception as error:
            clear_error = error
        result = _ORIGINAL_SESSION_CLOSE(self, restore)
        if clear_error is not None:
            raise clear_error
        return result

    physics_runtime._model_armature = runtime_aware_model_armature
    physics_runtime.PreviewSession.__init__ = runtime_aware_session_init
    physics_runtime.PreviewSession.prepare_step = runtime_aware_prepare_step
    physics_runtime.PreviewSession.apply_step = runtime_aware_apply_step
    physics_runtime.stop_preview = runtime_aware_stop_preview
    physics_runtime.PreviewWorld.reset = runtime_aware_world_reset
    physics_runtime.PreviewSession.close = runtime_aware_session_close


def uninstall():
    global _ORIGINAL_MODEL_ARMATURE, _ORIGINAL_SESSION_INIT, _ORIGINAL_PREPARE_STEP, _ORIGINAL_APPLY_STEP, _ORIGINAL_STOP_PREVIEW, _ORIGINAL_WORLD_RESET, _ORIGINAL_SESSION_CLOSE
    if _ORIGINAL_MODEL_ARMATURE is None:
        return
    from ..physics_preview import runtime as physics_runtime

    physics_runtime._model_armature = _ORIGINAL_MODEL_ARMATURE
    physics_runtime.PreviewSession.__init__ = _ORIGINAL_SESSION_INIT
    physics_runtime.PreviewSession.prepare_step = _ORIGINAL_PREPARE_STEP
    physics_runtime.PreviewSession.apply_step = _ORIGINAL_APPLY_STEP
    physics_runtime.stop_preview = _ORIGINAL_STOP_PREVIEW
    physics_runtime.PreviewWorld.reset = _ORIGINAL_WORLD_RESET
    physics_runtime.PreviewSession.close = _ORIGINAL_SESSION_CLOSE
    _ORIGINAL_MODEL_ARMATURE = None
    _ORIGINAL_SESSION_INIT = None
    _ORIGINAL_PREPARE_STEP = None
    _ORIGINAL_APPLY_STEP = None
    _ORIGINAL_STOP_PREVIEW = None
    _ORIGINAL_WORLD_RESET = None
    _ORIGINAL_SESSION_CLOSE = None
