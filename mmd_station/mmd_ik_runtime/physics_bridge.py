import bpy

from .runtime import selected_armature


_INSTALLED = False


class MmdIkPhysicsAdapter:
    def __init__(self, physics_session, native_session):
        self.physics_session = physics_session
        self.native_session = native_session

    def prepare_step(self, prepare_mmd_tools_step):
        from ..physics_preview import runtime as physics_runtime
        from .evaluator import (
            _transform_modal_pose_matrices,
            evaluate_physics_pose,
            prepare_physics_targets,
            uses_exact_physics_targets,
        )

        session = self.physics_session
        native_session = self.native_session
        previous_suspended = native_session.suspended
        native_session.suspended = True
        session._mmd_ik_modal_pose_matrices = _transform_modal_pose_matrices(
            session.armature
        )
        try:
            session.ik_motion_anchor = physics_runtime._model_motion_anchor(
                session.armature
            )
            operation_center = session.armature.pose.bones.get("操作中心")
            operation_center_matrix = (
                operation_center.matrix.copy() if operation_center is not None else None
            )
            native_pose_active = evaluate_physics_pose(session.root, session) is not None
            if operation_center is not None and operation_center_matrix is not None:
                operation_center.matrix = operation_center_matrix
            exact_targets = uses_exact_physics_targets(session.root, session)
            reset_probe = (
                session._broad_pose_reset_detected if native_pose_active else None
            )
            if native_pose_active:
                session._broad_pose_reset_detected = lambda: False
            try:
                result = prepare_mmd_tools_step()
            finally:
                if native_pose_active:
                    session._broad_pose_reset_detected = reset_probe
            if exact_targets:
                prepare_physics_targets(session.root, session)
            return result
        finally:
            native_session.suspended = previous_suspended

    def apply_step(
        self,
        apply_mmd_tools_step,
        transforms=None,
        bone_transforms=None,
        joint_states=None,
        present_output=True,
        update_debug=None,
    ):
        from .evaluator import submit_physics_feedback

        session = self.physics_session
        native_session = self.native_session
        if transforms is None:
            transforms = session.solver.transforms()
            bone_transforms = session.solver.bone_transforms()
            joint_states = session.solver.joint_states()
        previous_suspended = native_session.suspended
        native_session.suspended = True
        try:
            result = apply_mmd_tools_step(
                transforms,
                bone_transforms,
                joint_states,
                present_output=present_output,
                update_debug=update_debug,
            )
            submit_physics_feedback(session.root, session, transforms)
            preserved = getattr(session, "_mmd_ik_modal_pose_matrices", {})
            for name, matrix in sorted(
                preserved.items(),
                key=lambda item: len(
                    session.armature.pose.bones[item[0]].parent_recursive
                ),
            ):
                pose_bone = session.armature.pose.bones.get(name)
                if pose_bone is not None:
                    pose_bone.matrix_basis = matrix
            if preserved:
                session.armature.update_tag(refresh={"OBJECT"})
                bpy.context.view_layer.update()
            native_session.sync_output_pose(session.armature, session.scene)
            return result
        finally:
            native_session.suspended = previous_suspended

    def before_world_reset(self):
        from .evaluator import clear_physics_feedback

        clear_physics_feedback(self.physics_session.root)

    def after_world_reset(self):
        from .evaluator import capture_physics_bindings

        capture_physics_bindings(
            self.physics_session.root,
            self.physics_session,
        )

    def before_close(self, _restore):
        from .evaluator import capture_live_input

        return capture_live_input(self.physics_session.root)

    def after_close(self, live_input):
        from .evaluator import (
            clear_physics_feedback,
            replay_live,
            restore_live_input,
        )

        root = self.physics_session.root
        if restore_live_input(root, live_input):
            replay_live(root)
        clear_physics_feedback(root)


def _resolve_model_armature(root):
    return selected_armature(root)


def _create_session_adapter(physics_session):
    from .evaluator import _SESSIONS

    native_session = _SESSIONS.get(physics_session.root_name)
    if native_session is None:
        return None
    return MmdIkPhysicsAdapter(physics_session, native_session)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    from ..physics_preview import integration

    integration.install(_resolve_model_armature, _create_session_adapter)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    from ..physics_preview import integration

    integration.uninstall(_resolve_model_armature, _create_session_adapter)
    _INSTALLED = False
