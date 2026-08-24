# 独立 MMD 物理预览模块

模块边界：

- `ffi.py`：稳定 C ABI 和 DLL 生命周期；
- `runtime.py`：从 Blender 当前 MMD 模型提取刚体/Joint，管理 Session/World 生命周期，并按 MMD 时间语义驱动固定子步求解；
- `pose_pipeline.py`：隔离 authored Pose 输入、physics output、dirty state 与 Blender depsgraph 投影；
- `display_rig.py`：为满足条件的单模型当前代理在所属 Scene 创建隐藏的精简 Armature，并让共享源 Mesh datablock 的显示 Object 通过原 Armature modifier 配置读取物理 Pose；
- `debug_batch.py`：把原始 Rigid/Joint Object 停放到隐藏 Collection，并按 kinematic、slow、static 更新域合成 5 个显示 Mesh；
- `time_driver.py`：把 Blender timeline 或暂停交互的单调时钟转换为 Bullet `frameSeconds`，并按绝对 deadline 调度 GUI timer；
- `ui.py`：启动、停止、重置和少量运行参数；
- `bin/win_amd64/mmd_physics_solver.dll`：Rust `cdylib`，内部静态链接 Bullet；
- `native/mmd_physics_solver/`：DLL 源码和可重复构建入口。

`mmd_tools` 在这里仅提供导入模型后已经存在的 RNA 数据字段；求解循环不使用其 Blender Rigid Body World、烘焙或预览实现。

`CURRENT_PROXY + 单 Session` 在没有 linked data、多 Scene 共享、B-Bone、额外约束或不兼容 Modifier 栈时使用隔离显示热路径，覆盖 PMX/MMD DLL 与 MMD IK 关闭/开启四种组合。canonical Armature 只保存用户控制输入；MMD IK 开启时由 Native PoseProvider 在内存中解析最终骨骼层级；物理 solver 读取该 Pose。`DisplayRig` 在同一 Scene 中复制并裁剪 Armature data，把精简 Armature 隐藏；显示 Object 使用 `source.copy()`，与源 Object 共用原 Mesh datablock 并保留唯一的 Armature modifier，只把 modifier 目标改为精简 Armature，源 Object 在会话期间设为 `hide_viewport=True`。每个物理 tick 因而只提交精简骨架 Pose，不复制顶点、不重建 Mesh、也不手工同步 custom normals。任一资格条件变化时立即恢复源 Object 并回退 canonical 路径，不用错误的快速路径勉强继续。

`PreviewDebugBatch` 只在 Armature Pose Mode 启用：它把原始 Rigid/Joint Object 从原 Collection 移入隐藏 parking Collection，再创建 `kinematic rigid / slow rigid / static rigid / slow joint / static joint` 5 个 helper Mesh。0 型 Rigid 跟随骨骼的同 tick 显示更新不降频；动态 Rigid 与活动 Joint 按调试显示 cadence 更新；静态分区只在启动、重建、恢复或明确数据事件时更新。Joint `ARROWS` 使用保持 `empty_display_size` 的 +X/+Y/+Z 定向 Mesh 轮廓；其它 Empty 显示类型在改变 Scene 前 fail closed，继续使用原逐 Object 显示。helper Mesh 使用复用的 NumPy/flat buffer 做 `foreach_set`，depsgraph watcher 只在外部身份、几何、Collection 或显示属性变化时请求完整验证，helper 自写不触发周期性全量扫描。离开 Pose Mode 会强制一次最终 slow-debug 输出、把缓存矩阵写回源对象并完成一次 owner ViewLayer 求值，然后再按 owner token 恢复原对象、隐藏/选择状态和 Collection；停止、Undo/Redo、保存、异常回退与启动残留清理也使用同一隔离恢复边界。

启动预览会在修改连接状态和创建 solver 之前建立唯一的启动快照：整个 MMD Armature 的全部 Pose Bone、模型全部刚体对象矩阵和全部 Joint 对象矩阵。矩阵是与 RNA 生命周期无关的普通副本；运行态身份同时使用 live RNA 引用、稳定名称与 MMD Root preview ID，真实重命名时会迁移快照键，停止时还会恢复动态骨骼连接状态。

运行时会对比上一求解输出与当前动态骨姿态。Blender `pose.user_transforms_clear(only_selected=False)` 造成大范围姿态跳变时，固定恢复完整启动快照，丢弃旧 Bullet world、从该快照创建新 solver，然后继续同一预览会话。手工“重置物理预览”和 tick 异常复用完全相同的恢复路径，不再接受当前局部状态或分别推导刚体/Joint 位置。0 型刚体在重建后继续每步读取骨骼目标。当前输出属于运行期预览，不写关键帧、不保存烘焙结果。

GUI timer 遇到普通步进异常会立即恢复启动快照并重建 solver；本次恢复失败时保留 session、timer 和运行标志，在下一 tick 重试，面板状态行显示原因。若当前 Root、Armature、刚体或 Joint 已永久删除、已脱离原 Scene，或稳定身份发生不可消解冲突，则把它视为终止性失效，完整关闭并移除对应 Session/World，而不是无限重试失效引用。

GUI timer 只负责唤醒预览，不再假定每次回调严格等于一个 `1/60 s` 物理步。动画播放时以 Blender timeline 的实际时间差作为 `frameSeconds`；暂停播放并手动拖动时以 `time.perf_counter()` 的实际间隔作为 `frameSeconds`。DLL 仍固定使用 `1/60 s` Bullet 子步和面板指定的 `maxSubSteps`，默认 `10` 与 MMD/PmxNLib 一致。播放状态切换只重建时钟基准；倒放、暂停时跳帧或时钟回退会走启动快照重置路径。

Blender 的姿态清理或撤销系统可能替换 RNA 数据块，使先前持有的 `bpy.types.Object` 引用变成 `StructRNA ... has been removed`。稳态 tick 直接使用已验证的 live bindings；depsgraph handler 用精确 update ID 区分 canonical Pose 输入和 DisplayRig/DebugBatch 输出自写，Undo/Redo、对象数量变化、恢复和停止入口再按 Root preview ID、RNA pointer、唯一所属 Scene 与 Armature data identity 解析当前绑定。检测到实例替换时，先恢复启动快照，再创建只引用当前数据的新 solver；身份不可消解时 fail closed 并只清理所属 owner，不波及其它健康 Session。

Rust ABI v4 提供刚体、物理骨骼朝向和 Joint frame 的世界空间结果；host adapter 再按 MMD 骨骼层级完成回写。PMX/MMD 两个 DLL 还提供可选的 PMX-Euler 骨骼目标批量入口：Python 继续执行原 `Matrix.decompose()`、`Quaternion.to_euler("YXZ")`、轴序与 scale 计算，只把复用的 indices/position/Euler flat buffers 一次提交给 native；旧 DLL 自动回退到 Transform batch 或 scalar setter。1 型采用完整物理骨骼变换；2 型采用物理旋转，但其位置不是逐骨固定在动画原点，而是按父到子顺序沿动画局部偏移传播，等价于父骨更新后立即更新子链，因此骨骼连续且不可拉伸。代理动态骨骼在预览期间临时解除 Blender `use_connect`，只为避免 Blender 自身约束覆盖求解结果；链长保持来自显式层级计算，不依赖 `use_connect` 制造假象。

## RGBA 式胸部物理

RGBA 式结构依赖多个辅助刚体、按列表顺序建立的 Joint、偏心 Joint frame、六轴限制/弹簧以及 Bullet 的约束行为。模块不会按骨名特判胸部：它保持模型中的刚体与 Joint 顺序并把完整图交给 Bullet，因此同一机制也适用于裙、发、饰品与 RGBA 式胸部链。

“与 MMD 一致”必须用同一 PMX、同一 VMD、同一重力与固定 timestep 做逐帧 oracle 比较。本模块目前已完成 DLL/Blender 闭环和结构回归，但尚未生成 RGBA fixture 的 MMD 逐帧 oracle，因此不能把视觉近似写成已证明的逐帧一致。
