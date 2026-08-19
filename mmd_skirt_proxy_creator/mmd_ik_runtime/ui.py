import hashlib
from pathlib import Path

import bpy
from bpy.props import IntProperty, PointerProperty, StringProperty
from bpy.types import Operator

from . import export_hook
from .evaluator import is_active as evaluator_is_active
from .evaluator import start as start_evaluator
from .evaluator import stop as stop_evaluator
from .runtime import (
    MMDIKRuntimeError,
    create_runtime,
    reenable_bindings,
    refresh_bindings,
    resolve_root,
    restore_bindings,
    runtime_armature,
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
        runtime = runtime_armature(root, state)
        return obj == canonical or obj == runtime
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
        description="需要创建 MMD IK Runtime 的 mmd_tools 模型根对象",
        type=bpy.types.Object,
        poll=_root_poll,
        update=_root_updated,
    )
    settings_cls.__annotations__["mmd_ik_armature"] = PointerProperty(
        name="骨架",
        description="切换当前模型全部 Mesh 使用的 mmd_tools 原骨架或 MMD IK 兼容骨架",
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
    bl_description = "创建独立 Runtime Armature，并切换当前 MMD 模型的全部 Armature Modifier"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        export_hook.install()
        install_vmd_hook()
        root = _selected_root(context)
        _require_physics_stopped(root)
        runtime, count, created = create_runtime(context, root)
        _set_armature_selector(context.scene.surface_proxy_creator, runtime)
        action = "已创建" if created else "已刷新"
        return f"{action} {runtime.name}，切换 {count} 个 Armature Modifier"


class SPX_OT_RefreshMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.refresh_mmd_ik_runtime"
    bl_label = "刷新模型物体"
    bl_description = "扫描材质分离或新增的 Mesh，并切换其 Armature Modifier"
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
    bl_description = "将当前模型全部 Runtime Armature Modifier 无损恢复到 mmd_tools 原骨架"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        count = restore_bindings(root, keep_runtime=True)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已复原 {count} 个 Armature Modifier"


class SPX_OT_ReenableMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.reenable_mmd_ik_runtime"
    bl_label = "重新启用运行骨架"
    bl_description = "重新把当前模型的 Armature Modifier 切换到已有 Runtime Armature"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        count = reenable_bindings(root)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已重新启用并切换 {count} 个 Armature Modifier"


class SPX_OT_RemoveMMDIKRuntime(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.remove_mmd_ik_runtime"
    bl_label = "移除 MMD IK 兼容骨架"
    bl_description = "将全部 Mesh 切回 mmd_tools 原骨架，并移除插件生成的兼容骨架"
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        root = _selected_root(context)
        _require_physics_stopped(root)
        stop_evaluator(root)
        count = restore_bindings(root, keep_runtime=False)
        _set_armature_selector(context.scene.surface_proxy_creator, selected_armature(root))
        return f"已切回原骨架并同步 {count} 个 Armature Modifier，兼容骨架已移除"


class SPX_OT_StartMMDIKEvaluator(_RuntimeOperator, Operator):
    bl_idname = "surface_proxy.start_mmd_ik_evaluator"
    bl_label = "启动原生 VMD 求值"
    bl_description = "使用插件内 C++ DLL 直接读取原始 PMX/VMD 并驱动 Runtime Armature"
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
    bl_description = "停止 C++ 骨骼求值并恢复 Runtime Armature 原有 Action 与约束状态"
    bl_options = {"REGISTER"}

    def run(self, context):
        root = _selected_root(context)
        stop_evaluator(root)
        return "MMD 骨骼求值已停止"


def draw(layout, settings, context):
    layout.prop(settings, "mmd_ik_root")
    root = settings.mmd_ik_root
    physics_running = _physics_running(root)
    armature_row = layout.row()
    armature_row.enabled = not physics_running
    armature_row.prop(settings, "mmd_ik_armature")
    if physics_running:
        layout.label(text="物理预览运行中，骨架切换已锁定", icon="LOCKED")
    state = runtime_state(root) if root is not None else None
    runtime = runtime_armature(root, state) if state else None
    box = layout.box()
    if not state:
        box.label(text="状态：尚未创建运行骨架", icon="INFO")
        row = box.row()
        row.enabled = not physics_running
        row.operator("surface_proxy.create_mmd_ik_runtime", icon="ARMATURE_DATA")
        return
    if runtime is None:
        box.label(text="状态：Runtime Armature 已丢失", icon="ERROR")
    elif state.get("enabled"):
        box.label(text=f"状态：运行中 · {runtime.name}", icon="PLAY")
    else:
        box.label(text=f"状态：已复原 · {runtime.name}", icon="PAUSE")
    row = box.row(align=True)
    row.enabled = not physics_running
    row.operator("surface_proxy.refresh_mmd_ik_runtime", icon="FILE_REFRESH")
    row.operator("surface_proxy.remove_mmd_ik_runtime", icon="TRASH")

    solver = layout.box()
    solver.label(text="插件内独立 MMD 骨骼求值", icon="ANIM")
    solver.prop(settings, "mmd_ik_pmx_path")
    solver.prop(settings, "mmd_ik_vmd_path")
    solver.prop(settings, "mmd_ik_action")
    row = solver.row(align=True)
    row.prop(settings, "mmd_ik_vmd_start_frame")
    row.prop(settings, "mmd_ik_start_frame")
    active = evaluator_is_active(root)
    solver.label(
        text="状态：原生 VMD 求值运行中" if active else "状态：已停止",
        icon="PLAY" if active else "PAUSE",
    )
    row = solver.row(align=True)
    row.operator("surface_proxy.start_mmd_ik_evaluator", icon="PLAY")
    row.operator("surface_proxy.stop_mmd_ik_evaluator", icon="PAUSE")
    layout.label(text="生产运行时不会启动、调用或依赖 MikuMikuDance", icon="CHECKMARK")
    layout.label(text="PMX 导出时临时切回原骨架，完成后自动恢复", icon="LOCKED")


CLASSES = (
    SPX_OT_CreateMMDIKRuntime,
    SPX_OT_RefreshMMDIKRuntime,
    SPX_OT_RestoreMMDIKRuntime,
    SPX_OT_ReenableMMDIKRuntime,
    SPX_OT_RemoveMMDIKRuntime,
    SPX_OT_StartMMDIKEvaluator,
    SPX_OT_StopMMDIKEvaluator,
)
