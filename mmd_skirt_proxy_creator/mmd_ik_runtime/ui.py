import hashlib
from pathlib import Path

import bpy
from bpy.props import IntProperty, PointerProperty, StringProperty
from bpy.types import Operator

from . import export_hook
from .evaluator import is_active as evaluator_is_active
from .evaluator import capture_physics_bindings
from .evaluator import replay_live
from .evaluator import start as start_evaluator
from .evaluator import start_live
from .evaluator import stop as stop_evaluator
from .runtime import (
    MMDIKRuntimeError,
    create_runtime,
    reenable_bindings,
    refresh_bindings,
    resolve_root,
    restore_bindings,
    runtime_state,
    select_armature,
    selected_armature,
)
from .vmd_hook import SOURCE_FRAME_KEY, SOURCE_SHA256_KEY, SOURCE_VMD_KEY
from .vmd_hook import install as install_vmd_hook


_ARMATURE_SELECTOR_UPDATING = False


def _root_poll(_self, obj):
    return obj is not None and getattr(obj, "mmd_type", "") == "ROOT"


def _armature_poll(self, obj):
    root = self.mmd_ik_root
    if root is None or obj is None or obj.type != "ARMATURE":
        return False
    state = runtime_state(root)
    canonical = selected_armature(root) if not state else None
    if state:
        from .runtime import canonical_armature

        canonical = canonical_armature(root, state)
        return obj == canonical
    return obj == canonical


def _set_armature_selector(settings, armature):
    global _ARMATURE_SELECTOR_UPDATING
    _ARMATURE_SELECTOR_UPDATING = True
    try:
        settings.mmd_ik_armature = armature
    finally:
        _ARMATURE_SELECTOR_UPDATING = False


def _root_updated(settings, _context):
    root = settings.mmd_ik_root
    _set_armature_selector(settings, selected_armature(root) if root is not None else None)


def _armature_updated(settings, _context):
    if _ARMATURE_SELECTOR_UPDATING:
        return
    root = settings.mmd_ik_root
    if root is None:
        _set_armature_selector(settings, None)
        return
    requested = settings.mmd_ik_armature
    if requested is None:
        _set_armature_selector(settings, selected_armature(root))
        return
    try:
        select_armature(root, requested)
    except Exception:
        _set_armature_selector(settings, selected_armature(root))
        raise


def _action_updated(settings, _context):
    action = settings.mmd_ik_action
    if action is None:
        return
    source = action.get(SOURCE_VMD_KEY, "")
    if source:
        settings.mmd_ik_vmd_path = source
        settings.mmd_ik_vmd_start_frame = int(action.get(SOURCE_FRAME_KEY, 0))


def _physics_running(root):
    if root is None:
        return False
    from ..physics_preview.runtime import is_running

    return is_running(root)


def _validate_action_vmd(action, vmd_path):
    if action is None:
        return
    source = str(action.get(SOURCE_VMD_KEY, ""))
    expected = str(action.get(SOURCE_SHA256_KEY, ""))
    if not source or not expected:
        return
    selected = Path(bpy.path.abspath(str(vmd_path))).resolve()
    if selected != Path(source).resolve() or not selected.is_file():
        return
    actual = hashlib.sha256(selected.read_bytes()).hexdigest()
    if actual != expected:
        raise MMDIKRuntimeError(
            "mmd_tools Action 记录的源 VMD 已被修改；请重新导入该 VMD，或选择未变更的原始文件"
        )


def _require_physics_stopped(root):
    if _physics_running(root):
        raise MMDIKRuntimeError("物理预览运行时不能创建、切换或移除 MMD IK 骨架；请先停止物理预览")


def register_settings(settings_cls):
    settings_cls.__annotations__["mmd_ik_root"] = PointerProperty(
        name="MMD 模型",
        description="需要启用或关闭 MMD 原生骨骼接管的 mmd_tools 模型",
        type=bpy.types.Object,
        poll=_root_poll,
        update=_root_updated,
    )
    settings_cls.__annotations__["mmd_ik_armature"] = PointerProperty(
        name="骨架",
        description="用户始终编辑且 Mesh 始终绑定的原 mmd_tools 骨架",
        type=bpy.types.Object,
        poll=_armature_poll,
        update=_armature_updated,
    )
    settings_cls.__annotations__["mmd_ik_pmx_path"] = StringProperty(
        name="源 PMX",
        description="读取骨骼、变形层级、Append Transform 与 IK 原始定义，不会调用 MMD",
        subtype="FILE_PATH",
    )
    settings_cls.__annotations__["mmd_ik_vmd_path"] = StringProperty(
        name="VMD 动作",
        description="由插件内部独立解析并求值的 VMD 动作，不会调用 MMD",
        subtype="FILE_PATH",
    )
    settings_cls.__annotations__["mmd_ik_action"] = PointerProperty(
        name="mmd_tools Action",
        description="选择由 mmd_tools 导入且保留源 VMD 路径的 Action；精确模式仍读取原始 VMD bytes",
        type=bpy.types.Action,
        update=_action_updated,
    )
    settings_cls.__annotations__["mmd_ik_vmd_start_frame"] = IntProperty(
        name="VMD 开始帧",
        default=0,
        min=0,
    )
    settings_cls.__annotations__["mmd_ik_start_frame"] = IntProperty(
        name="Blender 起始帧",
        description="MMD 开始帧对应的 Blender 帧",
        default=1,
    )


def _selected_root(context):
    settings = context.scene.surface_proxy_creator
    root = resolve_root(context, settings.mmd_ik_root)
    settings.mmd_ik_root = root
    return root


class _RuntimeOperator:
    def run(self, context):
        raise NotImplementedError

    def execute(self, context):
        try:
            message = self.run(context)
        except (MMDIKRuntimeError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_CreateMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.create_mmd_ik_runtime"
    bl_label = "启用 MMD IK 兼容"
    bl_description = "让 native DLL 只接管原 mmd_tools 骨架中的 MMD IK 链，不改变 Mesh 骨架绑定"
    bl_options = {"REGISTER"}

    def run(self, context):
        export_hook.install()
        install_vmd_hook()
        root = _selected_root(context)
        from ..physics_preview import runtime as physics_runtime

        runtime_switch = physics_runtime.suspend_for_runtime_switch(root)
        started = False
        created = False
        try:
            canonical = selected_armature(root)
            input_basis = {
                pose_bone.name: pose_bone.matrix_basis.copy()
                for pose_bone in canonical.pose.bones
            }
            _canonical, count, created = create_runtime(context, root)
            matched, total, _scale = start_live(
                root,
                input_basis=input_basis,
                update=False,
            )
            started = True
        except Exception:
            restore_bindings(root, keep_runtime=False)
            raise
        finally:
            if runtime_switch is not None:
                try:
                    preview_session, _previous_suspended = runtime_switch
                    if started:
                        capture_physics_bindings(root, preview_session)
                        replay_live(root, context.scene)
                finally:
                    physics_runtime.resume_after_runtime_switch(runtime_switch)
        _set_armature_selector(
            context.scene.surface_proxy_creator, selected_armature(root)
        )
        action = "已启用" if created else "已刷新"
        return f"{action} MMD 原生骨骼接管：匹配 {matched}/{total} 根骨骼，保持 {count} 个 Mesh 绑定原骨架"


class SPX_OT_RefreshMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.refresh_mmd_ik_runtime"
    bl_label = "刷新模型物体"
    bl_description = "刷新内存态 MMD 骨骼接管，不改变任何 Armature Modifier"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        count = refresh_bindings(root)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已切换 {count} 个新增 Armature Modifier"


class SPX_OT_RestoreMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.restore_mmd_ik_runtime"
    bl_label = "复原原始骨架"
    bl_description = "暂停内存态 MMD 骨骼接管并恢复 Blender/mmd_tools 求值"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        count = restore_bindings(root, keep_runtime=True)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已复原 {count} 个 Armature Modifier"


class SPX_OT_ReenableMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.reenable_mmd_ik_runtime"
    bl_label = "重新启用 MMD IK 接管"
    bl_description = "重新建立内存态 MMD 骨骼接管，不改变 Armature Modifier"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        count = reenable_bindings(root)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已重新启用 MMD 骨骼接管，{count} 个 Mesh 保持绑定原骨架"


class SPX_OT_RemoveMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.remove_mmd_ik_runtime"
    bl_label = "关闭 MMD IK 兼容"
    bl_description = "停止 native IK 链接管并恢复 mmd_tools 原有 IK 结果"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        from ..physics_preview import runtime as physics_runtime

        restart_physics = physics_runtime.is_running(root)
        if restart_physics:
            physics_runtime.stop_preview(root, restore=True)
        try:
            stop_evaluator(root)
            count = restore_bindings(root, keep_runtime=False)
        finally:
            if restart_physics:
                physics_runtime.start_preview(context)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已关闭 MMD 原生 IK 链接管，{count} 个 Mesh 继续使用原骨架"


class SPX_OT_StartMMDIKEvaluator(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.start_mmd_ik_evaluator"
    bl_label = "启动原生 VMD 求值"
    bl_description = "使用插件内 C++ DLL 直接读取原始 PMX/VMD 并驱动原 mmd_tools 骨架"
    bl_options = {"REGISTER"}

    def run(self, context):
        settings = context.scene.surface_proxy_creator
        root = _selected_root(context)
        _validate_action_vmd(settings.mmd_ik_action, settings.mmd_ik_vmd_path)
        matched, total, scale = start_evaluator(
            root,
            settings.mmd_ik_pmx_path,
            settings.mmd_ik_vmd_path,
            settings.mmd_ik_start_frame,
            settings.mmd_ik_vmd_start_frame,
        )
        return f"MMD 骨骼求值已启动：匹配 {matched}/{total} 根骨骼，导入缩放 {scale:g}"


class SPX_OT_StopMMDIKEvaluator(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.stop_mmd_ik_evaluator"
    bl_label = "停止骨骼求值"
    bl_description = "停止 C++ 骨骼求值并恢复原骨架的 Action 与约束状态"
    bl_options = {"REGISTER"}

    def run(self, context):
        root = _selected_root(context)
        stop_evaluator(root)
        return "MMD 骨骼求值已停止"


def draw(layout, settings, context):
    layout.prop(settings, "mmd_ik_root")
    root = settings.mmd_ik_root
    state = runtime_state(root) if root is not None else None
    box = layout.box()
    if not state:
        box.label(text="状态：使用 Blender/mmd_tools 骨骼求值", icon="INFO")
        box.operator("surface_proxy.create_mmd_ik_runtime", icon="PLAY")
        return
    active = evaluator_is_active(root)
    box.label(
        text="状态：MMD 原生 IK 链已自动接管" if active else "状态：接管已停止",
        icon="CHECKMARK" if active else "ERROR",
    )
    box.label(text="原 mmd_tools 骨架保持为唯一可见、唯一绑定骨架", icon="INFO")
    box.operator("surface_proxy.remove_mmd_ik_runtime", icon="PAUSE")


CLASSES = (
    SPX_OT_CreateMMDIKRuntime,
    SPX_OT_RefreshMMDIKRuntime,
    SPX_OT_RestoreMMDIKRuntime,
    SPX_OT_ReenableMMDIKRuntime,
    SPX_OT_RemoveMMDIKRuntime,
    SPX_OT_StartMMDIKEvaluator,
    SPX_OT_StopMMDIKEvaluator,
)
