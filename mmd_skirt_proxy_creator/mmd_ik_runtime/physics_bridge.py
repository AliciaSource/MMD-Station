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
        from .evaluator import is_active
        from .runtime import _export_pose_matrix, runtime_armature

        runtime = runtime_armature(root) if is_active(root) else None
        if runtime is None:
            return _ORIGINAL_SESSION_INIT(self, scene, settings, root)
        saved_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in runtime.pose.bones
        }
        try:
            for pose_bone in runtime.pose.bones:
                matrix = _export_pose_matrix(runtime, pose_bone.name)
                if matrix is not None:
                    pose_bone.matrix = matrix
            bpy.context.view_layer.update()
            return _ORIGINAL_SESSION_INIT(self, scene, settings, root)
        finally:
            for bone_name, matrix_basis in saved_basis.items():
                pose_bone = runtime.pose.bones.get(bone_name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix_basis
            bpy.context.view_layer.update()

    def runtime_aware_prepare_step(self):
        from .evaluator import (
            evaluate_physics_pose,
            prepare_physics_targets,
            uses_exact_physics_targets,
        )

        evaluate_physics_pose(self.root, self)
        if uses_exact_physics_targets(self.root, self):
            solver_type = type(self.solver)
            setter = solver_type.set_bone_target
            reset_probe = self._broad_pose_reset_detected
            solver_type.set_bone_target = lambda _solver, _index, _matrix: None
            self._broad_pose_reset_detected = lambda: False
            try:
                result = _ORIGINAL_PREPARE_STEP(self)
            finally:
                self._broad_pose_reset_detected = reset_probe
                solver_type.set_bone_target = setter
        else:
            result = _ORIGINAL_PREPARE_STEP(self)
        prepare_physics_targets(self.root, self)
        return result

    def runtime_aware_apply_step(self, transforms=None, bone_transforms=None, joint_states=None):
        if transforms is None:
            transforms = self.solver.transforms()
            bone_transforms = self.solver.bone_transforms()
            joint_states = self.solver.joint_states()
        result = _ORIGINAL_APPLY_STEP(self, transforms, bone_transforms, joint_states)
        from .evaluator import submit_physics_feedback

        submit_physics_feedback(self.root, self, transforms)
        return result

    def runtime_aware_stop_preview(root=None, restore=True):
        roots = (
            tuple(session.root for session in physics_runtime._ACTIVE_SESSIONS.values())
            if root is None
            else (root,)
        )
        result = _ORIGINAL_STOP_PREVIEW(root, restore)
        from .evaluator import clear_physics_feedback

        for item in roots:
            clear_physics_feedback(item)
        return result

    def runtime_aware_world_reset(self):
        from .evaluator import capture_physics_bindings, clear_physics_feedback

        for preview_session in self.sessions:
            clear_physics_feedback(preview_session.root)
        result = _ORIGINAL_WORLD_RESET(self)
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
