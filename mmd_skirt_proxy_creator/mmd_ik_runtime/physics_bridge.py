import bpy

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

    def runtime_aware_session_init(self, scene, settings, root):
        return _ORIGINAL_SESSION_INIT(self, scene, settings, root)

    def runtime_aware_prepare_step(self):
        from .evaluator import (
            _SESSIONS,
            _transform_modal_active,
            evaluate_physics_pose,
            prepare_physics_targets,
            uses_exact_physics_targets,
        )

        native_session = _SESSIONS.get(self.root.name)
        if native_session is not None and _transform_modal_active():
            return _ORIGINAL_PREPARE_STEP(self)
        previous_suspended = (
            native_session.suspended if native_session is not None else False
        )
        if native_session is not None:
            native_session.suspended = True
        try:
            self.ik_motion_anchor = physics_runtime._model_motion_anchor(self.armature)
            operation_center = self.armature.pose.bones.get("操作中心")
            operation_center_matrix = (
                operation_center.matrix.copy() if operation_center is not None else None
            )
            native_pose_active = evaluate_physics_pose(self.root, self) is not None
            if operation_center is not None and operation_center_matrix is not None:
                operation_center.matrix = operation_center_matrix
                self.armature.update_tag(refresh={"OBJECT"})
                bpy.context.view_layer.update()
            exact_targets = uses_exact_physics_targets(self.root, self)
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
            if not exact_targets:
                prepare_physics_targets(self.root, self)
            return result
        finally:
            if native_session is not None:
                native_session.suspended = previous_suspended

    def runtime_aware_apply_step(self, transforms=None, bone_transforms=None, joint_states=None):
        if transforms is None:
            transforms = self.solver.transforms()
            bone_transforms = self.solver.bone_transforms()
            joint_states = self.solver.joint_states()
        from .evaluator import (
            _SESSIONS,
            _transform_modal_active,
            submit_physics_feedback,
        )

        native_session = _SESSIONS.get(self.root.name)
        if native_session is not None and _transform_modal_active():
            return _ORIGINAL_APPLY_STEP(
                self,
                transforms,
                bone_transforms,
                joint_states,
            )
        previous_suspended = (
            native_session.suspended if native_session is not None else False
        )
        if native_session is not None:
            native_session.suspended = True
        try:
            result = _ORIGINAL_APPLY_STEP(
                self,
                transforms,
                bone_transforms,
                joint_states,
            )
            submit_physics_feedback(self.root, self, transforms)
            return result
        finally:
            if native_session is not None:
                native_session.suspended = previous_suspended

    def runtime_aware_stop_preview(root=None, restore=True):
        roots = (
            tuple(session.root for session in physics_runtime._ACTIVE_SESSIONS.values())
            if root is None
            else (root,)
        )
        from .evaluator import capture_live_input, replay_live, restore_live_input

        inputs = {item.name: capture_live_input(item) for item in roots}
        result = _ORIGINAL_STOP_PREVIEW(root, restore)
        from .evaluator import clear_physics_feedback

        for item in roots:
            if restore_live_input(item, inputs.get(item.name)):
                replay_live(item)
            clear_physics_feedback(item)
        return result

    def runtime_aware_world_reset(self, prepared_session=None):
        from .evaluator import capture_physics_bindings, clear_physics_feedback

        for preview_session in self.sessions:
            clear_physics_feedback(preview_session.root)
        result = _ORIGINAL_WORLD_RESET(self, prepared_session=prepared_session)
        for preview_session in self.sessions:
            capture_physics_bindings(preview_session.root, preview_session)
        return result

    def runtime_aware_session_close(self, restore=True):
        from .evaluator import clear_physics_feedback

        clear_physics_feedback(self.root)
        return _ORIGINAL_SESSION_CLOSE(self, restore)

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
