# 独立 MMD 物理预览模块

模块边界：

- `ffi.py`：稳定 C ABI 和 DLL 生命周期；
- `runtime.py`：从 Blender 当前 MMD 模型提取刚体/Joint，固定步长求解并非破坏性地回写 Pose Bone；
- `ui.py`：启动、停止、重置和少量运行参数；
- `bin/win_amd64/mmd_physics_solver.dll`：Rust `cdylib`，内部静态链接 Bullet；
- `native/mmd_physics_solver/`：DLL 源码和可重复构建入口。

`mmd_tools` 在这里仅提供导入模型后已经存在的 RNA 数据字段；求解循环不使用其 Blender Rigid Body World、烘焙或预览实现。

启动预览会在修改连接状态和创建 solver 之前建立唯一的启动快照：整个 MMD Armature 的全部 Pose Bone、模型全部刚体对象矩阵和全部 Joint 对象矩阵。对象身份以 Blender 数据名称保存，矩阵是与 RNA 生命周期无关的普通副本；停止时还会恢复动态骨骼连接状态。

运行时会对比上一求解输出与当前动态骨姿态。Blender `pose.user_transforms_clear(only_selected=False)` 造成大范围姿态跳变时，固定恢复完整启动快照，丢弃旧 Bullet world、从该快照创建新 solver，然后继续同一预览会话。手工“重置物理预览”和 tick 异常复用完全相同的恢复路径，不再接受当前局部状态或分别推导刚体/Joint 位置。0 型刚体在重建后继续每步读取骨骼目标。当前输出属于运行期预览，不写关键帧、不保存烘焙结果。

GUI timer 遇到步进异常会立即恢复启动快照并重建 solver。即使本次重建失败，也保留 session、timer 和运行标志并在下一 tick 重试，不会自动调用停止；面板状态行会显示快照恢复或继续重试的原因。

Blender 的姿态清理或撤销系统可能替换 RNA 数据块，使先前持有的 `bpy.types.Object` 引用变成 `StructRNA ... has been removed`。运行时因此在每个 tick、恢复和停止入口按名称重新解析当前 root、Armature、刚体与 Joint；检测到实例替换时，先恢复启动快照，再创建只引用当前数据的新 solver。

Rust ABI v2 提供刚体、物理骨骼朝向和 Joint frame 的世界空间结果；host adapter 再按 MMD 骨骼层级完成回写。1 型采用完整物理骨骼变换；2 型采用物理旋转，但其位置不是逐骨固定在动画原点，而是按父到子顺序沿动画局部偏移传播，等价于父骨更新后立即更新子链，因此骨骼连续且不可拉伸。代理动态骨骼在预览期间临时解除 Blender `use_connect`，只为避免 Blender 自身约束覆盖求解结果；链长保持来自显式层级计算，不依赖 `use_connect` 制造假象。

## RGBA 式胸部物理

RGBA 式结构依赖多个辅助刚体、按列表顺序建立的 Joint、偏心 Joint frame、六轴限制/弹簧以及 Bullet 的约束行为。模块不会按骨名特判胸部：它保持模型中的刚体与 Joint 顺序并把完整图交给 Bullet，因此同一机制也适用于裙、发、饰品与 RGBA 式胸部链。

“与 MMD 一致”必须用同一 PMX、同一 VMD、同一重力与固定 timestep 做逐帧 oracle 比较。本模块目前已完成 DLL/Blender 闭环和结构回归，但尚未生成 RGBA fixture 的 MMD 逐帧 oracle，因此不能把视觉近似写成已证明的逐帧一致。
