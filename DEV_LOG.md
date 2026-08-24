# Development Log

## 2026-08-24 - V0.1.8 物理预览性能候选验收失败并回退

- 用户在原 `04.blend` 的真实 Blender 4.4 视口验收提交 `b226618` 时观察到多处严重姿态/物理显示异常，明确判定验收不合格；background 四象限与性能指标未能覆盖这些真实 GUI 回归，因此该候选不得晋升基线。
- 已通过提交 `97afcbf` 完整撤销 `b226618` 的 DisplayRig、DebugBatch、Native 批处理、相关 runtime/adapter 改动、DLL 与新增测试，插件生产源码和 DLL 恢复到已验收的 `baseline-20260823-mmd-preview-pose-pipeline` 内容。保留提交 `601de98` 的基线记录，不移动 tag。
- 当前工作树中既有的顶点组、代理创建和 `headless_smoke.py` 未提交修改均先备份后原样恢复，没有混入回退提交。版本保持 V0.1.8，不打包 ZIP、不 push；真实 Blender 4.4 继续通过源码 Junction 直接使用回退后的基线代码。

## 2026-08-23 - V0.1.8 物理预览 Pose I/O 双缓冲与交互调度重构

- 用户在真实 `04.blend` 视口确认上一轮刚体延迟已经修复，并批准将提交 `978339a` 标记为本地安全基线 `baseline-20260823-mmd-preview-latency-fixed`。本轮从该基线继续，只处理 `CURRENT_PROXY + MMD DLL + 未启用 MMD IK` 的操作手感；不修改已验收的 type 0、Root/Bone、MMD IK 数学或两个 native DLL。
- 对相同 `04.blend` 的 250 个 Rigid、374 个 Joint、190 根 physics driver 做逐阶段复测：基线 tick 中位约 `38.190 ms`，prepare/output 两次 `view_layer.update()` 分别约 `12.868 / 14.282 ms`，合计约 `27.15 ms`、占总耗时约 `71%`；Rust/Bullet step 仍约 `1 ms`。历史 revision 回放还确认近期性能回归来自 Blender host adapter 的重复 rebind、全骨扫描和 MMD IK modal 写回泄漏，而不是 MMD DLL；但今日 `04.blend` 创建于 2026-08-23，不能据此反推历史同名工程当时的实际帧率。
- 新增 `physics_preview/pose_pipeline.py:PoseInputAdapter`，把 authored Pose input、physics output、raw input signature、depsgraph self-write guard、cache invalidation 与 presentation cadence 从 `runtime.py` 的 solver/world 生命周期中分离。稳态输入不变时复用 immutable animation pose 与 native target payload，但仍逐 tick 调用 DLL `set_bone_target()`；40 tick fresh-process 对照中完整 prepare 与缓存路径的 solver + Bone output SHA256 均为 `5041a6ac6c84e3c3c8bd1511344c9694f1dbfd696554c9dc7c9cf99c221a713c`。
- 用户通过真实 Blender 操作产生的 depsgraph evaluation 现在可直接作为本 tick input snapshot：对非 physics driver 读取已求值 Pose，对 driver 分支从保存的 authored `matrix_basis` 重建 canonical hierarchy，不再重复执行 prepare update。全 868 骨 raw `matrix_basis` 检查作为直接脚本写入的 backstop；脚本尚未求值、driver 被直接编辑、约束结构不安全、MMD IK、PMX、MODEL 或多 Session 时全部回退完整双 update 路径。Undo/Redo、RNA rebind、reset 与 runtime switch 均明确清空缓存。
- Rust solver 继续按每次有效 tick 推进，未降低 fixed frequency 或 substeps；GUI 中阻塞式 output depsgraph evaluation 与 Rigid/Joint 调试对象投影最多 30 Hz，Bone output 仍逐 tick 写入并由 Blender 主循环合并。`PreviewDeadlineScheduler` 改用 absolute deadline，长 presentation tick 后可由短 tick 追回预算，同时将最大欠帧限制为一个 interval，避免无界 catch-up 饿死界面。headless、显式测试、MMD IK 与其它 fallback 路径仍每 tick同步 presentation。
- `04.blend` 新回归连续三轮：静止交互模拟平均约 `10.989-11.511 ms/tick`，连续 Root Bone 输入约 `13.621-14.198 ms/tick`，20 个 solver tick 只执行 10 次阻塞 presentation；相对 `38.190 ms` 基线，host callback 平均减少约 `64-71%`。`MMD_04_PREVIEW_PIPELINE_OK cache_hits=25 fast_captures=21 presentations=10/20 type0_error=0 motion_type0_error=0`；直接未求值的 Root Bone 修改仍强制完整 prepare，既有 `MMD_04_RIGID_LATENCY_REGRESSION_OK ... max_error=0` 保持通过。
- 回归通过：PMX/MMD 两套 `PHYSICS_ROOT_OFFSET_REGRESSION_OK`；`MMD_07_ROOT_MOTION_REGRESSION_OK` 的 PMX/MMD × MMD IK 关/开四组合；`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK exact_calls=12 exact_min=202`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_TIME_DRIVER_UNIT_OK`，以及完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。完整 smoke 的 traceback 仍是测试主动注入的恢复分支。
- 同步更新 `physics_preview/README.md` 的模块边界。版本保持 V0.1.8，不打包 ZIP、不 push；真实 Blender 4.4 继续通过源码 Junction 使用。用户随后在原 `04.blend` 真实视口确认本轮未观察到 bug，并批准将提交 `292dcb3` 晋升为本地安全基线 `baseline-20260823-mmd-preview-pose-pipeline`。用户同时确认实际操作仍约十几 FPS、尚未达到目标手感；后续 60 FPS 量级优化必须从该基线继续，不能牺牲已验收的 type 0、Root/Bone、MMD IK 与重置正确性。

## 2026-08-23 - V0.1.8 MMD DLL 刚体延迟回归与物理预览热路径重构

- 使用用户工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\04.blend` 对当前代理做逐阶段剖析：目标 Armature 共 868 根骨骼，当前代理含 250 个刚体、374 个 Joint；修改前单 tick 平均约为 prepare `29.568 ms`、Rust/Bullet `1.044 ms`、输出复制 `0.039 ms`、apply `22.578 ms`，实际瓶颈在 Blender/Python host adapter，而不是 Rust 求解器。60 Hz timer 还会在约 `53.149 ms` 回调后固定再等 `16.667 ms`，实际周期接近 `70 ms`。
- 确认近期 MMD IK 兼容桥接存在真实隔离回归：即使未启用 MMD IK Session，普通 `mmd_tools + MMD DLL` 仍会捕获/恢复 Transform modal 骨骼、提交 feedback 并额外执行一次 `view_layer.update()`。`physics_bridge.py` 现在没有对应 native Session 时立即委托原物理实现，兼容关闭路径不再进入任何 MMD IK pose/feedback 逻辑；测试明确断言 bridge 调用数为零。
- 同一桥接中还发现 exact-target 条件反写：旧代码只在 `exact_targets == False` 时调用 `prepare_physics_targets()`，而该函数在非 exact 模式必定立即返回，导致真正的 `MMD IK + MMD DLL` raw body target/basis 修正从未执行。条件已改为只在 exact 模式提交；回归记录 `exact_calls=12`、每次至少提交 202 个映射目标，PMX 路径调用数保持为零。
- 修复 MMD DLL 的同 tick 刚体延迟：物理输入先恢复动态骨骼基线并刷新 depsgraph，再采样 0 型刚体的最终 kinematic bone target，调用方即使没有预先 `view_layer.update()` 也不会提交上一 tick 的骨骼矩阵；物理写回完成后，再按最终 `Armature world × PoseBone × authored offset` 对绑定的 0 型显示刚体做一次精确同步，避免父级/约束在 apply 阶段更新后显示刚体仍落后一帧。已移除同一 0 型刚体在 apply 前后的重复对象写入。
- 重构 `physics_preview/runtime.py` 的稳态热路径：Session 建立或 RNA 生命周期重绑时一次性缓存 rigid mode、Rigid→PoseBone、driver PoseBone、骨骼深度及 driver ancestor closure；04 当前代理实际只需处理 195 根闭包骨骼，不再每 tick 扫描全部 868 根骨骼或执行约 2509 次按名 collection lookup。启动快照、输出快照与 reset probe 改为只处理物理 driver；Undo/Redo、runtime switch 和失效 RNA 恢复仍强制完整重绑。矩阵完全相等时 reset probe 走 C 层快速判定，再对真正变化项保留原 epsilon 检查。
- 预览运行期间暂停代理同步与 preview model-id 两个全场景 depsgraph handler；“显示刚体运动”关闭时同时停止 Joint 对象投影；生产 timer 改为扣除本次 callback 已花时间，超预算帧只保留 `1 ms` 最小调度间隔，不再额外固定空等一帧。最终同一 04 当前代理、显示刚体开启的 20 tick 均值为 prepare `14.209 ms`、Rust/Bullet `0.983 ms`、复制 `0.039 ms`、apply `17.847 ms`、合计 `33.078 ms`；稳态 host callback 约减至原来的 `62%`，预期调度周期约 `34 ms`，而 native 求解仍约 `1 ms`。
- 回归通过：`MMD_04_RIGID_LATENCY_REGRESSION_OK type0=59 target_motion=0.00999998093-0.0100000191 authored_motion=0.0100000202 max_error=0`；`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`；`MMD_07_ROOT_MOTION_REGRESSION_OK` 的 PMX/MMD × MMD IK 关/开四组合；PMX/MMD 两套 `PHYSICS_ROOT_OFFSET_REGRESSION_OK`；`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK exact_calls=12 exact_min=202`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_TIME_DRIVER_UNIT_OK`，以及完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。完整 smoke 中的 traceback 仍为测试主动注入的异常恢复分支，不是未处理失败。
- 本轮不修改 `mmd_physics_solver.dll`、`mmd_physics_solver_mmd.dll`、native ABI、固定频率或 substeps。版本保持 V0.1.8，不打包 ZIP、不 push；真实 Blender 4.4 继续通过现有源码 Junction 使用当前代码。用户随后在原 `04.blend` 真实视口确认刚体延迟已修复、流畅度较修改前略有改善，并批准将该状态晋升为 `baseline-20260823-mmd-preview-latency-fixed`；同时确认操作手感仍未达到优秀标准，后续性能重构须从此基线继续，不能牺牲本轮已验收的 type 0、Root/Bone 与 MMD IK 正确性。

## 2026-08-21 - MMD IK 首次启用与 Blender Undo/Redo 运行态重绑

- 使用未保存 MMD IK 状态、未运行物理 Session 的原始 `07.blend` 重新监测用户顺序：手动启用 MMD IK、启动物理、旋转、原生“清空用户变换”、F9 切换 `仅选中`。确认此前只为 `POSE_OT_user_transforms_clear` 设置的 fast path 依赖 `window_manager.operators[-1]`；Blender 开始 Adjust Last Operation 的 Undo 时 operator 栈会变化，判断因此漏失，插件转而关闭 native IK Session，物理 Session 随后继续持有已失效 RNA wrapper，表现为物理预览消失、立即重启报错、稍后自动恢复。
- 生命周期适配改为不再识别或替换具体 Blender operator：只要内存态 IK 或物理正在运行，所有 Blender Undo/Redo 都先暂停现有 Session，Undo/Redo 完成后按当前 RNA 名称重新绑定，并保留原 IK/physics Session、solver 与 world；只有 MMD 模型、运行状态或 PMX 来源确实不再兼容时才关闭并重建。原生“清空用户变换”、右键菜单、F9 面板及 mmd_tools 菜单均未修改。
- 修复干净工程首次启用 MMD IK 时缺少 `spx_mmd_ik_source_pmx` 而同步导出整份 PMX 的阻塞：若 `import_folder` 中恰有一个 PMX，直接复用该导入源并缓存路径；只有无法唯一解析来源时才保留原导出 fallback。真实 `07.blend` 的精确顺序 headless 计时为启用约 `0.136 s`、随后启动物理约 `0.237 s`。
- 启用顺序也改为对称兼容：若用户先启动物理再启用 MMD IK，只暂停并恢复现有物理 Session，不再 stop/start 整个物理 world；重新捕获 MMD physics bindings 后继续运行。回归测试同时修正多 MMD Root 工程中错误取第一个 PreviewSession 的测试缺陷。
- 性能探针显示 C++ `mmd_bone_solver.dll` 单次 evaluate 约 `0.7-1.5 ms`，Python/Blender pose 输出写回约 `14-17 ms`；本轮异常 Undo handler 自身仅为微秒级。C++ 骨骼求解器确有每帧临时 `std::vector` 与全骨骼 pass，可作为后续稳定帧率优化项，但不是本次 Session 消失或首次 PMX 导出阻塞的根因，因此未改 C++/Rust DLL，避免把未经证据支持的 native 重构叠加到生命周期修复上。
- `MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK` 均通过；其中 clear 回归覆盖通用 Undo/Redo suspend/rebind，physics reset 回归覆盖先物理后 MMD IK 且 Session/world/solver identity 不变。当前结论仍等待用户重启 Blender 后按真实 GUI 顺序验收；未增版本、未打包、未移动安全基线、未 push。

## 2026-08-21 - 清空用户变换 Redo 属性切换保留 native Session

- 用户完成上一轮 Transform modal 视口验收后，将提交 `48f7b3b` 晋升为新安全基线并标记 `baseline-20260821-mmd-ik-modal-chain-live`。本轮只在该基线上处理 MMD IK + MMD DLL 运行时切换“清空用户变换”的 `仅选中` 属性产生的停顿，不修改已验收的 modal `matrix_basis` 保护、PMX/MMD DLL 或物理核心。
- 真实可见 Blender 4.4 中按用户顺序启用 MMD IK 与 MMD DLL、旋转 `足D.L`、从右键菜单执行 `Clear User Transforms`，再通过 Adjust Last Operation 把 `only_selected` 从 `True` 改为 `False`。确认 Blender 的属性切换会触发 Undo/Redo handler；旧生命周期无条件执行 `detach_all_sessions()`，把当前 native IK solver 关闭并从 PMX 重新建立 Session，实际观察到 Session 数量 `1 → 0 → 1`。全骨清姿态与物理 broad-reset 本身不是这次额外停顿的主因。
- 对 `POSE_OT_user_transforms_clear` 的 operator repeat 增加窄 fast path：Undo/Redo 前只恢复 canonical 输入并挂起现有 live Session，不关闭 native solver；操作完成后重新按名称绑定当前 Armature/PoseBone，重新捕获最终整套 `matrix_basis`，清空旧输出/物理反馈缓存并 reset 同一个 solver。PMX 来源、模型状态或骨骼映射不再兼容时仍退回原完整关闭/重建路径；其它普通 Undo/Redo 行为保持不变。
- 修复后的同一真实 GUI 操作中 `only_selected=False` 已生效，Undo 前后 Session 始终为 `1`，同一个 native solver 未被卸载；点击到 `undo_pre` 约 `0.049 s`，恢复周期最大单次 UI/timer 间隔约 `0.254 s`，未再出现秒级等待。该结果是自动化真实 GUI 证据，最终体感仍等待用户在当前 Junction 源码上验收。
- `mmd_ik_clear_user_transforms_regression.py` 新增 operator-repeat 生命周期断言，要求 Session/solver identity 保持、全骨 input basis 正确清为 identity 且 MMD 物理继续运行。正常 `mmd_tools` 优先的 `MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`、`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK`、authoring Undo/Redo + save/reload 均通过。未增版本、未打包、未 push；本轮提交仅作为待用户视口验收的候选。
- 用户视口验收随后否定首个候选：首次取消 `仅选中` 仍长时间停顿，之后重新勾选也会再次停顿。按真实 F9 浮动面板重新复现后，属性切换完成即出现 `ReferenceError: StructRNA of type Object has been removed`；原因是 `d091006` 只保留并重绑 MMD IK Session，Undo/Redo 替换 Blender RNA 后，仍在运行的 MMD 物理预览 Session 继续持有旧 `root/settings/armature/rigids/joints` wrapper，下一次自然 timer 因此进入异常启动快照恢复。
- pose-clear repeat fast path 现在同时暂停物理 timer，并在 IK 恢复周期内按名称重绑物理 Session 的 Blender data；只更换失效 wrapper，不重建 native physics solver，原 broad-pose reset 语义不变。修复后的真实可见 Blender 4.4 完整执行：旋转 `足D.L` → 清空 → 取消 `仅选中`并自然运行 8 秒 → 再旋转/清空 → 再次取消并运行 8 秒 → 重新勾选并运行 8 秒。三段均保持相同 IK/physics Session 与 solver identity，physics world generation 始终为 1、tick failure 为 0、状态持续为“运行中：1 个模型”，未再触发 RNA 异常恢复。最终体感仍由用户视口验收决定。

## 2026-08-20 - MMD IK 模态控制骨保护、IK 链实时求值与正常 mmd_tools 物理连续运行

- 上一候选 `304bc4a` 错误地在共享 `physics_preview._timer_tick()` 检测到 `TRANSFORM_OT_*` 后暂停整个物理 tick；该判断不区分是否启用 MMD IK，导致正常 `mmd_tools` 骨架在 `G/R` 期间 Mesh 已移动而刚体和 Joint 停在旧 world 位置。已先恢复已验收安全基线 `93174c6`，并把失败提交保存为 `backup/failed-mmd-ik-modal-writeback-20260820`。
- 第一版窄隔离候选 `0bfd846` 保持正常 `mmd_tools` timer，但在 Transform modal 期间停止 MMD IK 求值，导致 `足ＩＫ.L` 控制骨可移动而 `足.L → ひざ.L → 足首.L` 骨链不更新。修正后不再暂停 native IK；`_apply_output()` 在每次 live / physics 求值前快照当前 Pose Mode 中所有选中骨骼的 pose matrix，写回 native 链结果后按层级恢复这些用户正在操作的骨骼。由此控制骨保持鼠标位置，未选中的 IK 链仍实时使用当前输入求解；取消操作的逆向 Pose 变化也会逐步还原 `input_basis`。
- 修复启用 MMD IK 后执行 `pose.user_transforms_clear(only_selected=False)` 导致骨架乱飞。该操作会在同一更新中把约 352 根映射骨骼中的 351 根 `matrix_basis` 清为 identity；旧逻辑却把每根骨骼都按“相对上次 native 输出的独立增量”折回 `input_basis`，把父子链输出差异错误累积成新输入。现在检测同帧、大范围、绝大多数变为 identity 的批量清姿态事件，直接把清除后的 canonical pose 快照作为整套新输入；普通单骨移动仍沿用增量捕获。live handler、PMX exact 路径和 MMD physics-before-step 路径均先捕获该事件，避免 timer 先于 depsgraph handler 到达时再次提交旧输入。
- 修复 MMD IK 与物理预览之间的输出反馈回路。物理 tick 过去在 native IK 输出之后再次写回物理骨骼，但 Session 仍保留 IK 写回前的 signature；下一 tick 会把上一 tick 的物理结果误判为用户新增输入并持续折回 `input_basis`，真实 `07.blend` 的单次 `0.001` 平移在无后续输入的 10 tick 内产生最高 `0.0504576` 的输入漂移。现在每次物理 apply 完成后同步 composite output basis/signature，物理运行期间 depsgraph handler 只捕获用户输入、统一由 timer 求值；同一回归在 PMX/MMD 两套 DLL 下均为严格 `0` 漂移。Transform modal 的选中骨矩阵保护同时覆盖完整物理 prepare/apply 周期，避免物理写回遮住鼠标中的移动并在左键确认后集中跳变。
- 性能路径删除了 `evaluate_live`、`evaluate_physics_pose` 与 operation-center 恢复后的重复 `view_layer.update()`，删除单 Session timer 对 `_rebind_blender_data()` 的重复扫描，并缓存未变化的 native solver matrices/Blender desired pose，只写实际变化或父级变化影响到的骨骼。启用操作不再创建大型场景 Undo 快照，首次 native 写回交给 Blender 正常 redraw，而不是在 operator 内同步强制完整 depsgraph。真实 `07.blend` headless PMX+MMD IK 稳态 tick 从历史记录约 `105.73 ms` 降至本轮 `73.29 ms`，首次启用从本轮修改前约 `175.68 ms` 降至 `124.47 ms`；清姿态整体 operator 调用约 `36.44 ms`，随后显式 handler 检查约 `1.75 ms`。这些是代码端性能证据，不替代真实视口体感验收。
- 用户随后在真实视口发现 Transform modal 期间仍只有 `matrix_basis` 发生变化，而延迟求值的 `pose_bone.matrix` 保持旧值；原保护逻辑快照并恢复 `.matrix`，因此会把鼠标中的 IK 输入遮住，直到左键确认才集中跳变。保护对象已改为 `.matrix_basis`，并覆盖 native IK 写回及完整 MMD 物理 prepare/apply 周期。真实可见 Blender 4.4 中实际发送 `G`、移动鼠标并左键确认后，`足ＩＫ.L`、`足.L`、`ひざ.L`、`足首.L` 在 modal 期间分别产生约 `0.003369`、`0.006836`、`0.005349`、`0.003719` 的变化，确认后无额外跳变；用户完成视口验收并批准晋升为新安全基线。
- `tests/mmd_ik_transform_modal_regression.py` 按验收顺序先验证正常 `mmd_tools + MMD DLL` 在 modal 中持续 step 且 type 0 刚体保持贴合，再验证 `足ＩＫ.L` 位移时控制骨不被覆盖、腿部三骨链同 tick 发生 native IK 响应、左键确认不跳变，以及 PMX 物理下确认/分阶段取消完整回到输入基线。`tests/mmd_ik_clear_user_transforms_regression.py` 使用真实 `07.blend` 复现 351 根批量 identity 清除，并覆盖 PMX live handler 与 MMD 物理 timer 抢先两条顺序；新增 `tests/mmd_ik_physics_feedback_regression.py` 覆盖 PMX/MMD 物理写回后 10 tick 不得反向污染输入。真实 `07.blend` 的 PMX/MMD × `mmd_tools`/MMD IK 四组合 Root motion 均通过，MMD IK authoring 保存/重载通过；上一轮完整 `mmd_ik_runtime_smoke.py` 超过 300 秒后终止，未将其计为通过。真实鼠标视口验收仍必须先从正常 `mmd_tools` 开始，再验证 MMD IK。
- 未修改 PMX/MMD DLL、物理求解器或现有安全基线标签；真实 Blender 4.4 继续通过源码 Junction 使用本轮代码。未递增版本、未打包、未 push。

## 2026-08-20 - PMX DLL 静态刚体旋转取消完整复位

- 修复 PMX DLL 中 0 型刚体的骨骼旋转取消路径。旧实现把“目标旋转等于启动旋转”一律当作纯平移，只调用 position-only setter；因此 `足D.L` 旋转后右键取消时，位置回到初始值，但 Bullet 中上一次写入的刚体旋转被保留。
- `BodyBinding` 现在只记录该刚体是否曾被骨骼旋转覆盖。正常纯平移继续走原 position-only 路径，保持既有 PMX root-motion bit-exact 行为；仅在旋转目标返回启动旋转的那个状态转换中写回完整初始刚体 transform，然后清除标记。未修改 Blender adapter、MMD IK、MMD DLL 或保护骨骼逻辑。
- 新增 Rust 回归 `canceled_static_bone_rotation_restores_initial_body_rotation`，并确认修复前失败、修复后与原 `translated_static_body_survives_the_next_step` 一起通过；VS2013 RTM LTCG release 全套 `12/12` tests 通过。真实 `07.blend` 中 `足D.L` 绑定的 `001_左足`、`002_左足2` 均先产生约 `0.5 rad` 旋转，取消后 rotation/position error 均为 `0`；`MMD_07_ROOT_MOTION_REGRESSION_OK solver=PMX ik=False` 通过。
- 仅重建并安装 `mmd_physics_solver.dll`，SHA256 由 `A00D61A22C219EC915A564C35D6358E85F3E01962AC5E2F431EFB55B1F36E0CD` 变为 `7BDC9006186D8AE92ADD80087664521B8493C629A9ABC40EACC07A036B416CC0`。`mmd_physics_solver_mmd.dll` 未修改，SHA256 保持 `73E19B4D1D407594391B8C2010CF58B6F713779F9EF4FA739DD99E8F6E801375`。继续使用真实 Blender 4.4 源码 Junction；未递增版本、未打包、未移动基线标签、未 push。

## 2026-08-20 - 将 MMD IK 物理桥接保护骨骼从全ての親转移到操作中心

- 以冻结基线 `fe7bf5d` 为开发起点，仅修改 `mmd_ik_runtime/physics_bridge.py` 中 MMD IK 求值前后的单骨骼矩阵保存/恢复对象：由 `全ての親` 改为 `操作中心`。
- `07.blend` 中 `操作中心` 无父子骨骼、无刚体、无 Constraint、无实际顶点权重，也未被其它骨骼引用；本轮不修改 evaluator、physics runtime 或 PMX/MMD DLL。
- 目标是让 `全ての親` 恢复为用户输入骨骼，并把现有单骨骼保护行为转移到低影响的 `操作中心`。Python compile、目标源码断言及真实 `07.blend` 的 `MMD_07_ROOT_MOTION_REGRESSION_OK solver=MMD ik=True` 通过；真实 Blender 视口中的模态移动行为等待用户逐步验收。版本未递增、未打包、未移动基线标签、未 push。

## 2026-08-19 - 更正 Root 物理漂移根因并完成 07.blend 四组合回归

- 对真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 重新做 30 tick、`Y=-0.182507 m` Empty 与 `全ての親` 两条路径，覆盖 PMX/MMD DLL 与 `mmd_tools`/MMD IK 四种组合。四组均通过 `MMD_07_ROOT_MOTION_REGRESSION_OK`，type 0 锚点误差约 `1e-7 m`，type 1 终态误差约 `1e-6 m`，裙环终态相对误差低于 `0.003 m`，`auto_reset_count=0`。
- 复核后否定此前“把 Root 运动剥离为固定参考系即可”的结论：共享 `physics_preview` adapter 曾每个 tick 对整套刚体执行 `apply_world_delta`，覆盖 Empty 的真实 solver 驱动，并使 `全ての親` 产生双重驱动。生产路径已移除该 world teleport，恢复当前骨骼 world target 语义。
- MMD IK 另有独立桥接错误：Blender 刚体列表索引被直接当作 native PMX rigid index；`07.blend` 实际为 367 个 Blender 刚体、406 个 PMX 刚体，仅 200 个名称可匹配，导致物理反馈写回错误链。现在建立按 MMD rigid name 的一对一映射；集合不完整时安全关闭 IK 物理反馈，但保留 Blender 刚体物理。
- `Session.capture_physics_bindings()` 对无源 PMX 的 `"<current model>"` 路径增加安全返回；新增 smoke 覆盖该分支。Python compile、`MMD_IK_RUNTIME_SMOKE_OK solver=MMD/PMX` 及四组合真实工程回归均通过。未修改 native DLL core；未增版本、未打包、未提交、未 push。

## 2026-08-19 - V0.1.8 恢复 Root/全ての親对物理链的真实驱动

- 使用真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 与历史提交 `18c3bd0`、`7fbd045` 做差分复现。确认当前共享 adapter 在输入端用 Root/global delta 抵消 `armature.matrix_world @ pose_bone.matrix`，输出端又把同一 delta 强制乘回刚体、骨骼和 Joint；因此 type 0 anchor 没有进入 solver，动态刚体只是被显示层整体搬运，正是 Empty 无物理反馈以及跟踪刚体/物理刚体失去 Joint 交互的根因。
- `physics_preview/runtime.py` 删除上述输入抵消和输出强制搬运，恢复与 `18c3bd0` 一致的 solver 驱动语义。MMD IK + MMD DLL 的 exact-target 分支另行加入 Armature 启动后的 world translation，避免该分支绕开普通 bone target 后再次吞掉 Empty 位移；没有修改 PMX/MMD native DLL。
- 新增 `tests/mmd_07_root_motion_regression.py`，真实工程覆盖 `mmd_tools / MMD IK` 两种骨架与 `PMX / MMD` 两种 DLL 的四种组合。30 step Empty `Y=-0.182507 m` 后，普通 PMX/MMD 的 type 0 anchor 均得到约 `-2.281337` native 位移，`202_Skirt_C01_R01` 与相邻 Joint 均表现为物理滞后而非复制 Root delta；`全ての親` 路径同样保留刚体、Joint 与骨骼之间的自然差值，四组合 marker 全部通过且 `auto_reset_count=0`。
- `PHYSICS_ROOT_OFFSET_REGRESSION_OK` 的 PMX/MMD 双路径、`MMD_IK_PHYSICS_RESET_REGRESSION_OK` 及 Python compile 通过。完整 `headless_smoke.py` 已越过本轮修改的物理对齐段，随后仍可能命中既有无关命名断言 `repair_pose_bone.mmd_bone.name_j == repair_pose_bone.name`，本轮未扩大范围处理。源码已由真实 Blender 4.4 的 Junction 直接使用；未增版本、未打包、未提交、未 push。

## 2026-08-18 - V0.1.8 修复 07.blend 根容器与全ての親双重平移

- 在真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 中复现：MMD/PMX 两个 DLL 的 `202_Skirt_C01_R01`（type 2）在 30 帧 `-0.182507 m` Empty 或 `全ての親` 移动后均出现约 `5–7 mm` 偏移；两者数值一致，根因在共享 adapter 的坐标时序，不是 DLL core。
- 根因是 solver 已在启动坐标系中接收骨骼/根容器的绝对 world target，而 Blender 层又通过 Root/Armature parent 叠加同一全局位移；`全ての親` 还会把全局骨骼位移再次作为动态刚体追拉。现在每步剥离纯模型级 `Root Empty` 或 `全ての親` delta 后提交 solver，再在输出写回时只叠加一次；局部骨骼运动仍保留给物理。
- 真实工程回归：MMD Empty 最大偏移 `1.36e-3 m`、`全ての親` `1.36e-3 m`；PMX 分别 `1.38e-3 m`、`1.36e-3 m`。两种路径的刚体位移均与骨骼约 `-0.182507 m` 对齐，不再出现约 `-0.365 m` 双倍漂移或 `7 mm` 弹簧式偏移。
- 修改 `physics_preview/runtime.py` 与 `tests/physics_root_offset_regression.py`；DLL 未修改、版本未递增、未打包 ZIP。验证使用 headless Blender 4.4 真实工程；未宣称视口人工验收。

## 2026-08-18 - V0.1.8 修复 Root 运动被固定物理参考系吞掉

- 用户反馈 PMX/MMD 物理预览共同出现“骨骼追踪刚体不追踪骨骼、微小移动后物理刚体漂移”的回归。新增回归断言后确认此前 `solver_armature_matrix` 固定参考系让 Root/Armature 位移只进入显示搬运，不进入 0 型刚体的 solver kinematic target；两套 DLL 在同一输入下均以约 `0.14` native unit 的误差复现，故根因在共享 Blender adapter，不在 DLL core。
- `physics_preview/runtime.py` 恢复每帧以当前 `armature.matrix_world @ pose_bone.matrix` 提交 bone target，并恢复当前 Armature world-space 输出/Joint 写回；移除逐帧 `last_kinematic_targets` 近似复用，避免吞掉真实的小幅骨骼运动。mode 0 刚体显示改为当前骨骼 world matrix 乘启动时 rigid-to-bone offset，避免 Bullet 的碰撞/约束回写覆盖骨骼追踪语义。保留既有 type 2 translation 写回修复与 MMD source payload 路径，不修改两个 native DLL。
- `tests/physics_root_offset_regression.py` 现在验证 Root 位移确实传播到 0 型 kinematic targets，并验证全部 mode 0 显示刚体都随 Root 平移；不再错误地要求 native frame 不变。`tests/headless_smoke.py` 同步按 mode 0 bone-offset 语义断言。PMX/MMD 均通过，`kinematic_target_pass_fraction=0.954545`、`display_frame_error=5.13e-8`，type 2 translation error 分别为 `6.01e-7 / 6.07e-7`；完整 smoke marker `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK` 通过。
- 未递增版本、未打包 ZIP。真实 Blender 4.4 仍使用源码 Junction；需要 Reload Scripts 或重启 Blender 后加载本轮 adapter。

## 2026-08-18 - V0.1.8 Root 固定物理参考系与 type 2 写回回归修复

- 否定并撤回同日上一条“逐帧减去 Armature world translation、输出端再补回”的实现。该实现只通过了单次 `+1` 平移、单刚体测试；在 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 连续 60 次微移中，浮点抵消的末位差会传播进完整 Joint/碰撞网络，PMX/MMD 都会出现弹簧式漂移，同时 0 型刚体没有真正跟随模型参考系。对应的 `depsgraph_update_post` 即时搬运和每 tick 对全部 Rigid/Joint 的矩阵快照也已删除。
- 明确区分 Blender 模型容器与 PMX 骨骼：Root Empty / Armature Object transform 现在只改变显示参考系；solver 输入使用启动或 Reset 时固定的 `solver_armature_matrix @ pose_bone.matrix`，solver 输出通过 `current_armature_matrix @ solver_armature_matrix^-1` 整体映回 Blender。因此移动 Empty 不再被错误解释成高速 0 型 kinematic motion，0/1/2 型刚体保持相对状态并整体跟随；`全ての親` 等 Pose Bone 仍进入 solver 并产生真实物理。
- 修复共用 Blender adapter 的 type 2 层级写回。旧代码用受物理父骨影响的 `inherited.translation`，导致“物理 + 骨骼”骨骼自身也随父级物理漂移；现在严格使用 DLL `bone_transforms()` 返回的 animation position，只采用物理 rotation。实际 `07.blend` 连续移动 `全ての親` 120 step 后，PMX/MMD 的 type 2 Blender translation 最大误差分别为 `5.99e-7 / 7.28e-7` Blender unit，均无自动 Reset。
- 为避免纯参考系移动时 Blender matrix 往返产生 1 ULP 的 0 型 target 抖动，adapter 只对相邻帧差不超过 `5e-7` 的 kinematic target 复用上一份 float32 payload；更大的真实骨骼运动不被吞掉。四个全新 Blender 进程分别运行实际 `07.blend` 的 PMX/MMD 静止对照与 60 次 Root 微移：两套 DLL 的全部 0/1/2 raw rigid transforms 均与对照逐 bit 相同，扣除 Root delta 后显示矩阵最大误差均为 `4.16e-8` Blender unit，Reset count 均为 `0`。
- 重写 `tests/physics_root_offset_regression.py`，覆盖固定 native frame、全部刚体的显示 frame 映射、PMX kinematic payload 稳定及 type 2 Pose Bone 位移。PMX/MMD marker 均通过，`display_frame_error=5.49795931e-08`、`type2_blender_error=5.26680826e-07`；`MMD_TIME_DRIVER_UNIT_OK`、`PMX_PHYSICS_READER_REGRESSION_OK`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_RAW_CORE_PARITY_OK` 通过。完整 smoke 已越过本轮修改的物理对齐断言，但随后在既有名称修复断言 `repair_pose_bone.mmd_bone.name_j == repair_pose_bone.name` 失败；该失败不在本轮物理范围，未擅自修改他人命名改动。
- 实际 `07.blend` 50-step 均值为 PMX `46.08 ms/tick`、MMD `49.83 ms/tick`，MMD 稳态约慢 `8.1%`；启动分别约 `66.5 ms / 712.7 ms`。本轮删除了错误补偿的逐 tick 大量矩阵复制，没有降低 fixed frequency/substeps。PMX DLL SHA256 仍为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`，MMD DLL仍为 `12EA03E1A1F1B4C88D5B83DCAB0484F1684611DDD55EF1FACCF6C374163078E7`；不递增版本、不打包 zip。
## 2026-08-18 - V0.1.8 预览交互平移回归、长帧物理冲击与 MMD 启动性能修复

- 复现并修正普通 `mmd_tools` 骨架下的模型平移回归。旧补偿只以 MMD Root Empty 的 translation 作为 solver 原点，因此单独移动 Armature Object 时会把整段位移作为 0 型刚体目标提交给 Bullet，动态刚体只能被 Joint 追拉；现在统一以 Armature world translation 作为模型平移原点，Root Empty 与 Armature Object 两条移动路径都会在输入端消除纯模型平移、输出端整体叠回，不重建 solver、不清零速度。`depsgraph_update_post` 同时只对发生 Root/Armature Object 变换的活动 Session 做显示矩阵平移，因此在 Blender modal 拖动期间即使 app timer 暂停，刚体仍会立即跟随，而不是等松开鼠标后才跳变。
- 修正交互操作阻塞 timer 后的超大 timestep。`PreviewTimeDriver` 过去保存了 `max_substeps` 却从未使用，拖动数秒后会把整段 wall delta 一次交给 Bullet，造成锚点瞬移、积压追帧和剧烈刚体冲击；现在 timeline/wall 两条路径都把单次 step 限制为 `fixed_step * preview_substeps`，默认上限为 `10 / 60 s`，并继续保留正常短帧的真实 wall delta。该修复同时作用于 PMX/MMD adapter，不修改任一 native Bullet core。
- 定位 MMD 首次启动慢的两个独立来源：MMD DLL/D3DX 的首次加载初始化，以及为了保留 raw PMX float/Euler 而用 `mmd_tools.pmx.load()` 完整解析大模型网格。插件注册时预热两套 DLL 和一个最小 MMD world；新增只顺序跳过 PMX mesh/bone/morph payload、仅读取 rigid/joint 原始字段的二进制 reader。Rossi 对照 `mmd_tools` 完整 reader 的 `339` rigid / `471` joint 全字段完全一致，fast reader 为约 `0.1056 s`。首次建 world 还移除了 `PreviewSession` 已生成 descriptors 后立即 restore + rebuild 的重复工作；Rossi MMD 预览启动从本轮复现的约 `3.10 s` 降到约 `0.815 s`。
- 性能剖析确认稳定 tick 的 DLL solve 本身没有显著 MMD 劣化。Rossi、显示刚体、10-step 去预热均值：普通骨架 PMX `42.04 ms/tick`、MMD `43.12 ms/tick`；MMD IK 兼容 PMX `105.73 ms/tick`、MMD `110.62 ms/tick`。MMD IK 的 frame/depsgraph handler 现在在 physics bridge 的 `suspended` 临界区入口直接跳过，不再先计算整骨架 signature；没有修改已验证的 IK/append/morph 求值数学。MMD 相对 PMX 的剩余实测差为普通约 `2.6%`、兼容约 `4.6%`，主要压力仍是 Blender pose/rigid/joint writeback，而不是 DLL step。
- 新增/扩展 `tests/pmx_physics_reader_regression.py`、`tests/physics_root_offset_regression.py` 与 `tests/time_driver_unit.py`。PMX/MMD 两条路径的 Root 与 Armature modal 前置反馈及 step 后显示位移均约为 `1.0`，solver 内动态刚体没有随模型平移约 `12.5` MMD unit；`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、完整 smoke marker 与 `MMD_RAW_CORE_PARITY_OK`（`339/339` transforms、`4068/4068` float components、`max_error=0`）通过。PMX DLL SHA256 仍为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`，MMD DLL仍为 `12EA03E1A1F1B4C88D5B83DCAB0484F1684611DDD55EF1FACCF6C374163078E7`；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-18 - V0.1.8 MMD DLL raw Bullet core 完全逐 bit 对齐

- 重新审计 MMD 9.32 x64 内嵌 Bullet 的真实 source revision。旧实现使用了较晚的 Bullet 2.75 development tree；该树的 `STATIC_PLANE_PROXYTYPE` 为 `28`，而直接挂接 MMD world 读取到的值为 `26`。上游提交 `f65e829ca08c0856d1923e7008e2663486949493` 恰好新增 `BOX_2D_SHAPE_PROXYTYPE` 与 `CONVEX_2D_SHAPE_PROXYTYPE`，使后续所有 shape type 顺延两位。因此将 MMD 分支 vendor source 精确切换到其前一提交 `3da9c832aef0eea74ecc8221d834e9a879f43a43`（2009-09-16）；`LinearMath`、`BulletCollision`、`BulletDynamics` 以及 vendor 内其余 `src` 文件均与该 upstream tree byte-for-byte 相同。
- 依据 MMD PE Rich Header 中占主导的 build `40219` 记录，恢复并固定 Visual C++ 2010 SP1 `cl.exe 16.00.40219.01`，使用 `/fp:fast /Ox` 构建 native C++。VC9 SP1 全量构建会让 clean pre-step 从 `339/339` 降到 `310/339`，已被 differential 实测否定；VC10 RTM 与 VC10 SP1 在错误 source revision 上都只能达到 `318/339`，说明根因不是单纯 compiler/LTCG，而是 Bullet snapshot 错配。
- 修正 raw differential 的隐藏输入差异：真实 MMD 在首个 positive step 前会 remove/reinsert 全部模型刚体，从而重新分配 broadphase handles；验证 hook 现在对 DLL world 执行同一顺序。修复后双方 ground + 339 bodies 的完整 pre-step state、body/shape/constraint payload、solver info、pair topology、timestep 与调用顺序一致。Rossi 完整 471 Joint + collision 首个 clean `1/60` step 得到 `339/339` rigid-body transforms、`4068/4068` float32 components 逐 bit 相同，`max_error = 0`，marker 为 `MMD_RAW_CORE_PARITY_OK`。
- 新增可重复回归 `tests/mmd_raw_core_parity.py`、`tests/tools/mmd_raw_trace_hook_generic.cpp` 与对应测试 hook DLL；验证对象直接是双方 `btDiscreteDynamicsWorld::stepSimulation` 的 raw transform，不经过 Blender matrix/quaternion writeback。该证据证明 MMD DLL native Bullet core 在 identical payload/state/call-order 范围内完全 bit-exact；不把 Blender 两种骨架适配器或 MMD 独立播放之间的宿主层非确定性提升为端到端 bit-exact 声明。
- `native/mmd_physics_solver_mmd/build.ps1` release tests `12/12` 通过；最终 MMD DLL SHA256 为 `12EA03E1A1F1B4C88D5B83DCAB0484F1684611DDD55EF1FACCF6C374163078E7`。PMX source/DLL 未修改，PMX DLL SHA256 仍为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`。本轮不递增插件版本、不打包 zip；生产 DLL 已由 build script 原地安装到源码 junction 使用的 `physics_preview/bin/win_amd64`。

## 2026-08-18 - V0.1.8 MMD 本体与 MMD DLL 原始刚体 step 逐 bit 验证

- 直接挂接 MMD 9.32 x64 与当前 `mmd_physics_solver_mmd.dll` 内各自的 `btDiscreteDynamicsWorld::stepSimulation`，使用 Rossi `Rossi Ver1.0.pmx`、Teo `m7_teo_0918.vmd`、60 Hz、`maxSubSteps=10` 采集 Bullet 原始状态。为排除 MMD 宿主层在模型载入与首个正时间步之间执行的刚体初始化，受控 oracle 在首个正时间步前恢复 authored 状态；随后逐对象验证 ground + 339 个模型刚体的 world/interpolation/motion-state transform、四组速度、activation state 与 collision flags。首步之前 `340/340` 个对象的完整 200-byte 记录逐 bit 相同，339 个模型刚体的 mass/inertia、damping、friction/restitution、shape margin/scaling/AABB、factor 与 collision filter payload 也全部逐 bit 相同。
- 在上述相同输入和相同首步状态下，首个 `1/60` step 后只有 `165/339` 个模型刚体的 3x3 basis + origin 完全一致（`48.672566%`），float32 分量为 `2282/4068`（`56.096362%`），最大单分量误差为 `0.0622847378` MMD unit；第一个分歧为刚体 120 `120_cape_base_L_a_01_jnt`。两次独立受控 MMD 本体运行在相同 startup calls 上则保持 `340/340` 个完整记录逐 bit 一致，排除了本次首步 oracle 自身随机抖动。
- 额外移除两侧全部 Joint 后重跑首步，MMD DLL 提升到 `314/339` 个刚体和 `3812/4068` 个 float32 分量完全一致，但仍未全等。这证明碰撞路径本身已经存在分歧，Joint 只会把该分歧继续传播到连接链；因此当前证据明确否决“MMD DLL 已通过真实 MMD raw step bit-exact 验证”的说法。验证证据保存在 `_archive/headless-validation-runs/mmd-raw-core-parity-20260818/`。
- 本轮只建立和执行验证，没有修改生产源码或两个物理 DLL，不递增版本、不打包。MMD DLL SHA256 保持 `E51C6E2B2045B87D9437888624F6EDF568198A829537808984C11FA2B850CD8C`；PMX DLL 未触碰，SHA256 保持 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`。

## 2026-08-18 - V0.1.8 Rossi 四组合全骨骼逐 bit 验证与声明边界纠正

- 使用 Rossi `Rossi Ver1.0.pmx` 与 `m7_teo_0918.vmd` 建立 60 Hz headless 差分验证，覆盖 `mmd_tools / MMD IK` 两种骨架与 `PMX / MMD` 两种物理 DLL 的全部四种组合。新增 `tests/rossi_four_way_bone_parity.py`，逐帧记录 680 根 PMX 骨骼的完整 4x4 矩阵；每个矩阵以 16 个 little-endian IEEE-754 float32 的原始 bit 保存，并分别统计完整矩阵、3x3 rotation 和 translation 的一致数及首个差异。
- 通过隐藏 MMD 9.32 + MMDBridge 以物理 trace mode 独立生成两份 frame 0-4 oracle。两次 MMD 本体运行自身仅有 `670/680, 673/680, 673/680, 673/680, 673/680` 根骨骼逐 bit 重复，差异集中在 `左高跟鞋1/2` 与 `左FootTie_01-08`；因此“任意独立运行的全部骨骼必然逐 bit 相同”本身不是成立的 MMD oracle 前提。
- 固定第一份真实 MMD oracle 后，`MMD IK + MMD DLL` 每帧仅 `349,349,349,346,349 / 680` 根骨骼完全一致；扫描 0-7 个 startup step 后最高仍为 `349/680`，排除单纯预热相位错一帧。`mmd_tools + MMD DLL` 每帧只有 `6/680` 完全一致。两个 PMX DLL 组合对 MMD oracle 的数值只作横向诊断，不作为 PMX Editor 验收。
- `tests/pmx_runtime_bone_parity.py` 复跑得到 `PMX_RUNTIME_BONE_PARITY_OK frames=5 bodies=339`，但该 marker 只证明相同 NativeBoneSolver payload 下两条 PMX adapter 路径的 PMX DLL body 输出一致；本轮没有构造出“真实 PmxNLib + 任意 VMD + 全 680 骨骼”的直接 oracle，因此不得把内部双路径一致升级表述为 PMX Editor 端到端全骨骼 bit 对齐。综合本轮证据，已确认的端到端 bit-exact 组合为 `0`，不是 `3`。
- 原始 oracle、四组合全部骨骼 bit、startup phase 扫描、PMX 内部 marker 与机器可读汇总保存在 `_archive/headless-validation-runs/rossi-four-way-bit-parity-20260818/`。本轮只新增验证测试和证据，没有修改任何生产实现或 DLL；PMX DLL SHA256 仍为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`，MMD DLL SHA256 为 `E51C6E2B2045B87D9437888624F6EDF568198A829537808984C11FA2B850CD8C`，不递增版本、不打包 zip。

## 2026-08-18 - V0.1.8 Root 偏移物理平移、PMX + MMD IK 重置与预览性能修复

- 在 Rossi `199_スカート_0_4` 上复现 Root 直接平移：该刚体属于含 0 型锚点的完整连通分量，并非模型缺 Joint 或自由漂浮链。旧适配器把 Root 位移只提交给骨骼/0 型刚体，动态刚体仍留在旧 solver world，Root 平移 1 Blender unit 后该刚体首步原生 X 从约 `1.083` 跳到 `14.255`，Joint 因瞬时约束冲量产生整组前漂；PMX/MMD 两个 DLL 都会发生，因此这是共享 Blender adapter 的 world-space 错误，不是两套 Bullet core 的 bit 对齐证据。
- `PreviewSession` 现在记录当前 solver 建立时的 Root translation。运行中直接平移 Root 时，提交骨骼目标前先映回 solver translation frame，读取刚体、骨骼和 Joint 输出后再叠回当前 Root translation；不重建 solver、不清零速度，也不修改旋转/重力语义。Rossi 回归中 Root X `+1` 后，PMX/MMD 原生刚体 X 仅自然变化 `0.00115895 / 0.00349438`，显示刚体 X 分别平移 `1.00009277 / 1.00027955`，不再以锚点瞬移拉扯动态链。
- 修复 MMD IK 兼容 + PMX DLL 每 tick 自动重置：native 骨架在 physics prepare 前写回 Pose 后，旧桥接仅对 MMD DLL 禁用了 broad-pose reset probe，PMX 路径把同一次插件内部写回误判成外部整姿态编辑。现在只要本帧存在 native pose 就临时屏蔽该 probe；仅 MMD exact-target 路径继续单独屏蔽普通 bone setter，PMX 路径仍正常提交 native 求值结果。Rossi 连续 4 step 的 reset count 从 `3` 降为 `0`。
- 性能剖析确认 MMD/PMX 在不开 MMD IK 时耗时接近，主要压力来自 MMD IK 的 `_apply_output()` 写骨骼触发 `depsgraph_update_post`，同一 physics tick 被递归重复求值。physics bridge 现在只在 prepare/apply 临界区把该 native Session 标记为 `suspended`，直接的 before/after-physics 求值仍执行，普通 handler 不再重入。Rossi 5-step headless 均值：PMX 从约 `275 ms/tick` 降至 `141 ms/tick`，MMD 从约 `333 ms/tick` 降至 `130 ms/tick`；没有减少固定频率、substeps、刚体反馈或 MMD before/after 阶段。
- 新增 `tests/physics_root_offset_regression.py`（PMX/MMD 双目标）与 `tests/mmd_ik_physics_reset_regression.py`。`PY_COMPILE_OK`、两个 Root offset marker、PMX + MMD IK reset marker和完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96` 均通过；完整 smoke 的 traceback 仍来自既有主动注入恢复分支。PMX DLL SHA256 保持 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`，MMD DLL保持 `E51C6E2B2045B87D9437888624F6EDF568198A829537808984C11FA2B850CD8C`；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - V0.1.8 MMD DLL 静止姿态颤抖修复与 bit 对齐边界纠正

- 重新以 Rossi 静止姿态同时采集 MMD/MMDBridge、Blender 普通 `mmd_tools` 骨架和内存态 MMD IK 骨架的长序列。确认此前“`339/339` bodies、`2373/2373` float bits”只证明相同 payload 下的隔离 Bullet step；fresh 端到端序列不存在完整刚体逐 bit 对齐，因此不再把该结果表述为 Blender 最终预览与 MMD 本体完全对齐。
- 根因位于 MMD 物理 DLL：`Solver::step()` 内硬编码了第 2-4 次调用时把全部刚体重放到 authored transform 并清零速度。真实 MMD 的启动回卷发生在宿主层、位于相邻 `stepSimulation` 调用之间；把该行为藏进 DLL 会在 Blender 已提交本帧骨骼目标后再次覆盖 solver 状态，并错误清除动态速度。已删除该 test-derived replay；PMX DLL、PMX native 源码和 MMD IK 实现均未修改。
- 新增 Rust 回归 `solver_steps_do_not_replay_authored_body_transforms`，要求携带 raw PMX Euler 的静态刚体在连续 5 个 step 中始终服从每步新目标，防止以后为了窄 oracle fixture 再把宿主初始化逻辑塞回 Bullet core。VC10 RTM `/fp:fast` + VC9 CRT LTCG 正式构建 `12/12` tests 通过；新 MMD DLL SHA256 为 `E51C6E2B2045B87D9437888624F6EDF568198A829537808984C11FA2B850CD8C`。
- Rossi 320 个固定 60 Hz step 回归：普通 `mmd_tools` 骨架 late bone peak 从旧 600-step 基线 `0.195745729` 降至 `0.052939421`；内存态 MMD IK 骨架从 `0.195272357` 降至 `0.042154452`。两条骨架路径均消除原先约 `0.195` 的持续尖峰，且 MMD IK 路径改善约 `78.4%`。完整 Blender 4.4.3 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。
- PMX DLL SHA256 复核仍为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`。继续使用源码 Junction，不递增版本、不打包 zip；真实视口主观平稳度仍需用户在当前模型上验收。

## 2026-08-17 - V0.1.8 MMD IK 严格内存态接管与零场景构件

- 将 MMD IK 兼容从“隐藏 Runtime Armature + `.MMD Native Output` 约束”改为严格内存态架构：Blender 中始终只有原 `mmd_tools` Armature，Mesh Armature Modifier 始终绑定原骨架；启用前后不新增 Object、Collection、Armature data、骨骼约束或特殊修改器。DLL 的骨架状态、输入 Pose 缓存与输出矩阵只存在于插件进程内存。
- 原骨架现在同时承担用户入口和最终显示，但输入/输出在内存中分离：Action/手动 Pose 作为输入快照，native DLL 输出直接写回同一骨架；帧切换采用 `frame_change_pre` 恢复输入、`frame_change_post` 求值并写回，避免把上一帧 native 输出再次当成输入。接管关闭时恢复原约束 mute 状态和输入 Pose，Blender/mmd_tools IK 结果立即返回。
- 补齐普通建模工作流的 Keying 事务：Pose Mode 的 `I` / `Alt+I` 由插件在内存中先恢复输入 Pose，再调用 Blender Keying Set，完成后立即恢复 DLL 输出；直接点击属性关键帧菱形或脚本调用 `PoseBone.keyframe_insert()` 时，Action watcher 会把误写的 DLL 输出值修正为缓存输入值。Action 首次被用户编辑后切换为持久 `action_input` 模式，后续切帧使用正常 Blender Action 插值作为 DLL 输入，不会返回只读原始 VMD 重放路径。
- 补齐 `.blend` 生命周期：`save_pre` 暂停接管并恢复输入/原约束，文件写入结束或失败后无条件恢复 DLL 输出；`load_post` 与插件重新注册会按隐藏 schema 状态自动重建内存 Session；`undo_pre/redo_pre` 先解除旧 RNA 引用，`undo_post/redo_post` 再按稳定对象名重建，避免 Undo 替换 data-block 后保留悬空 PoseBone。运行标记不再写入 Root Custom Properties，唯一持久 schema 注册为 `HIDDEN` Object RNA 属性。
- Runtime 状态升级为 schema 2。打开旧工程或插件更新后再次启用时，会自动迁移 schema 1：移除旧 `.MMD Native Output`、把误绑隐藏 Runtime 的 Mesh 恢复到 canonical Armature、删除旧 Runtime Object/Armature data，再以内存态重建。根对象只保留接管会话元数据，不保存第二套骨架数据。
- 物理预览与内存态骨骼接管可同时运行；物理停止/重放与 PMX 导出事务会先恢复缓存输入，结束后重新执行 native 求值，避免回放时把输出污染进输入。普通 UI 只保留启用/关闭接管，原始 PMX/VMD 精确重放 operator 继续不在默认界面显示。
- Rossi `Rossi Ver1.0.pmx` + Teo `m7_teo_0918.vmd` 在 MMD 9.32 x64 oracle frame 0-40 验收：Blender frame 41 启用时 native 输出 `680/680` bone matrices 逐 bit 一致；膝盖相对 Blender/mmd_tools IK 的切换差为 `0.034821432`，关闭后左右膝恢复残差分别为 `5.364418e-07`、`1.132488e-06`。测试同时确认启用物理期间可切换、同帧手动 Pose 会进入 live input、全程 Object/Collection/Armature/constraint 集合不变。
- 验证通过：`PY_COMPILE_OK`、`MMD_IK_AUTHORING_SAVE_OK 全ての親`、`MMD_IK_AUTHORING_RELOAD_OK Rossi Ver1.0 802`（覆盖普通 Keying Set、Property diamond、切帧、Undo、Redo、保存、重开与自动 Session 重建）、`MMD_IK_MEMORY_ONLY_ORACLE_OK 802 全ての親`、`MMD_IK_RUNTIME_SMOKE_OK solver=MMD meshes=4 modifiers=4 bone_morphs=23`（含 schema 1 自动迁移、帧播放、物理、导出 round-trip）以及 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。真实 Blender 4.4 继续通过源码 Junction 使用本轮代码；不递增版本、不打包 zip。

## 2026-08-17 - V0.1.8 物理 DLL 选择器位置与形态调整

- 将物理预览顶部的 `MMD 本体 / PMX Editor` 横向按钮组移到预览对象选择区下方、固定频率参数上方，并改为单行 `物理 DLL` 下拉选择器，替换原来的“DLL 已就绪”占位行；当前代理模式下因此紧邻“当前代理”，选择目标更明确。
- 保留运行期间禁止切换 DLL 的既有边界；所选 DLL 正常存在时不再重复显示就绪文案，文件缺失时仍额外显示错误提示。未修改 DLL 枚举值、默认目标、加载路径、world cache 或求解行为。
- `tests/headless_smoke.py` 增加选择器只绘制一次、位于固定频率之前以及运行时禁用的回归断言。Blender 4.4.3 完整 headless smoke 通过并输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；末尾 traceback 仍是测试主动注入的恢复路径。继续使用真实 Blender 4.4 源码 Junction，本轮不递增版本、不另打 zip。

## 2026-08-17 - V0.1.8 独立 MMD 骨骼求值、双骨架与双物理后端闭环

- 完成独立 VC9 C++ `mmd_bone_solver.dll`，生产运行时只读取原始 PMX/VMD bytes，不启动、不注入、不调用 MikuMikuDance/MMDBridge。核心实现 MMD float32 Bezier、定制 quaternion slerp、Bone Morph、Append Transform、自附加、fixed-axis、变形层级、IK 开关、CCD/link limits 以及 MMD/PMX 两套刚体反馈语义；最终 SHA256 为 `3B16FD66B3EAAB3CBB178F4C2D3677701322687F9FE832295F81C9A897973AE5`。
- `MMD IK` tab 完成 canonical/runtime 双骨架工作流：模型/骨架选择器、按材质分离后全 Mesh Armature Modifier 同步切换、物理运行期切换锁、移除 Runtime、原始 VMD SHA256 来源校验，以及 `mmd_tools` PMX 导出前临时切回 canonical、导出后无损恢复。Bone Morph/IK payload 的 PMX round-trip 与 Runtime 创建/删除前后 Bone Morph 绑定均一致。
- 接通 Runtime 骨架与两个物理 DLL。PMX backend 保留原 setter；MMD backend 使用 MMD 刚体静止位姿舍入、before/after-physics 分相和动态刚体世界矩阵反馈。Rossi 根平移 13 step 中 MMD backend 对 MMD oracle 为 `339/339` bodies、`2373/2373` float bits 每步一致；同一 Runtime 骨架进入 PMX backend 的 13 step 仍为 `PMX_RUNTIME_BONE_PARITY_OK`，既有 PMX DLL SHA256 保持 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`，MMD DLL SHA256 为 `FE055F0E384EB31063A08BAB55938BA8075AC45FDCC826F57A020EBFA6062552`。
- MMD 最终骨矩阵验收：Rossi 含半帧插值和物理反馈的 5 个输出帧达到 `680/680` matrices、`10880/10880` float bits。Alicia Laevatain 的 AnalToy/PussyToy/UrethraToy 均逐 bit 一致；`自動振動` 自引用链的 MMD 首帧相位取决于模型载入后到渲染开始前的空闲求值次数，同一 PMX/VMD 两次 headless MMD 首帧分别对应 native phase `593` 与 `597`，因此输入本身不存在唯一首帧 bit 值。相位对齐后，帧 1-30 的 `621/621` matrices、`9936/9936` float bits 每帧一致；这证明求值转移逐 bit 一致，同时不把 MMD 自身不确定的空闲首相位伪报成确定输入结果。
- Runtime 写入 native 精确矩阵后仍由 Blender depsgraph 正常叠加用户 constraint/driver；回归同时证明 native output bytes 不变而 pose 输出按公式和 `COPY_LOCATION` 约束变化。旧 mmd_tools 骨架只测 `センター` Root 位移时，相对 MMD 3 帧最大误差为 `2.98023223877e-08` Blender unit（`3.72529029846e-07` MMD unit），RMS 为 `1.9237316381e-08` Blender unit。
- 验收通过：MMD physics `11/11` Rust tests、`MMD_COORDINATE_ADAPTER_OK`、`MMD_RUNTIME_PHYSICS_ORACLE_OK`、`PMX_RUNTIME_BONE_PARITY_OK`、MMD/PMX 两套 `MMD_IK_RUNTIME_SMOKE_OK`（含按材质分离、自由切换、物理锁、overlay、导出事务、IK/Bone Morph round-trip）以及完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.8.zip`，真实 Blender 4.4 继续使用源码 Junction，安装状态已由 headless 注册与 smoke 验证。

## 2026-08-17 - raw PMX/VMD C++ 骨骼求值器与 MMD 逐 bit 差分闭环

- 新建 `native/mmd_bone_solver/`，使用与 MMD 9.32 x64 同代的 VC9 SP1、`/fp:fast`、`/GL`/LTCG 构建独立 `mmd_bone_solver.dll`。C ABI 直接接收原始 PMX/VMD bytes，不读取 `mmd_tools` 导入后的 Blender Action；当前已实现 PMX 2.0 骨骼/Bone Morph/Append/IK payload 解析、VMD bone/morph/IK 开关解析、基础 VMD interpolation、D3DX float32 矩阵路径和首版 CCD 求解骨架。
- 将 MMD 自动化严格迁移到 `tests/tools/` 开发 oracle：隔离复制、suspended hidden launch、headless hook、MMDBridge 原始 float32 bone world matrix 采集及 SHA256 来源校验均不进入生产插件。生产目录中旧的 `mmd_headless_hook.dll` 不再作为运行时方案保留。
- 新增 `tests/mmd_bone_solver_diff.py`、`tests/tools/pmx_ik_patch.py` 与 `tests/tools/mmd_fixture.py`，可以按 frame/bone 输出首差异、最大残差和逐骨 bit 结果。Rossi 空动作且 IK 关闭的基线曾达到 `680/680` bone matrices 逐 byte 一致，证明 PMX bone order、原始 world matrix 布局及 D3DX 基础路径正确；真实 Teo 动作仍在 Append/Toy cycle、IK link/local space、求值顺序和少量 VMD float grouping 处存在差异，当前不得标记为 bit-exact。
- 坐标处理改为独立验收边界：native 核心只输出 MMD 坐标系矩阵，后续 Blender adapter 必须另测静止姿态、单轴位移/旋转、父子链、左右非对称骨、矩阵转置/乘法顺序与 scale；不得用 Blender pose matrix 直接对比 MMD raw matrix。`mmd_tools` Action 路线继续冻结，必须等 raw PMX/VMD 路线全部 bit 对齐后再验证其导入转换是否有损。
- 本轮仍处于诊断/实现阶段，不递增版本、不打包 zip、不宣称完成；物理 DLL 与相邻物理调查文件未由本骨骼求值器修改。

## 2026-08-17 - 撤销 MMD 后台缓存方案，保留双骨架 UI 基础

- 撤销了以隐藏 MikuMikuDance/MMDBridge 生成矩阵缓存并在 Blender 播放的错误生产方案；插件源码不再包含 MMD 启动器、注入器、oracle cache 或 Python 近似骨骼求值器，面板也不再提供缓存生成/播放按钮。MMD 后续只能作为开发期外部 oracle，不能成为已安装插件的运行依赖。
- 保留 canonical/runtime 双骨架基础、MMD 模型与骨架选择器、全模型 Mesh Armature Modifier 同步切换、物理预览运行期切换锁、兼容骨架移除以及 mmd_tools 导出事务保护。这些属于后续独立 native 求值器需要的宿主基础，不代表求值核心已经完成。
- `MMD IK` tab 明确显示“独立 native 求值核心待实现”，不再宣称 MMD IK/Morph 已在 Blender 内独立 bit 级复刻。下一阶段需先确定 native DLL 技术路线，再实现 VMD interpolation、Bone Morph、Append Transform、PMX transform order、IK enable、CCD/link limits 和物理组合。
- 本轮不递增版本、不打包 zip；只保留 UI/双骨架基础，错误求值实现不作为交付结果。

## 2026-08-17 - MMD 9.32 独立 DLL 与双目标预览选择器

- 保留 `native/mmd_physics_solver/` 与 `mmd_physics_solver.dll` 作为既有 PMX Editor/PmxNLib 对齐实现，新增完全独立的 `native/mmd_physics_solver_mmd/` 与 `mmd_physics_solver_mmd.dll`。Blender 物理预览面板新增 `MMD 本体 / PMX Editor` 选择器，默认 `MMD 本体`；运行期间禁止切换，world cache 同时纳入对齐目标，避免两个 ABI 相同但语义不同的 DLL 共享 solver。
- 静态核对 MMD 9.32 x64 与 PmxNLib 2.5：MMD 使用 VC9 SP1、`btDefaultCollisionConfiguration`、`btDiscreteDynamicsWorld`；PmxNLib 使用 VS2013 RTM LTCG、`btSoftBodyRigidBodyCollisionConfiguration`、`btSoftRigidDynamicsWorld`。MMD 分支另恢复标准 Joint 线性弹簧 Z→Z 映射，不沿用 PmxNLib 的 Z/Y 特殊路径。
- MMD C++ bridge 改为 VC9 SP1 `/fp:fast` 构建，静态链接 VC9 `libcmt.lib` 的数学实现；Box inertia 恢复调用 Bullet 2.75 自身的 `calculateLocalInertia()`，不沿用为 VS2013/PmxNLib 运算分组定制的手写路径。最终 DLL 不依赖 `MSVCR90.dll`。ABI 保持 `4`，MMD 固定 quaternion bit 回归与全部 `11/11` Rust tests 通过。最终重建的 MMD DLL SHA256 为 `76BDAB12FDFC5D800092E8AF04C9592F5506DFCFE223BCC30E66AB61AE38FDC6`；既有 PMX DLL SHA256 保持 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`。
- 全部实际 MMD 验证均通过隐藏窗口的隔离副本和 MMDBridge 脚本 headless 运行，没有打开可见 MMD GUI。以 60 FPS、仅 `全ての親` 从 X=0 平移到 X=5、IK/Morph 不动，采集 Rossi `339/471`、达妮娅 blue `406/561`、Laevatain Body `115/79` 三模型的 MMD 本体三帧骨骼矩阵；同模型 Blender headless 同时跑 MMD/PMX 两 DLL。恢复 stock VC9 Box inertia 之前的 MMD 分支三帧平均位置残差分别为 `0.697 / 0.730 / 0.845` PMX unit，PMX DLL为 `1.357 / 1.294 / 1.072`，MMD 分支三者均更接近 MMD 本体；最终 stock-inertia build 完成 `11/11` native tests、ABI 双 DLL加载和 Blender 完整 smoke，但没有把旧数值冒充最终 build 的重新测量。矩阵仍未逐 bit 一致，不能把本轮标成 MMD bit-exact；剩余差异集中在 MMD 的帧前物理初始化/0 型刚体更新时序和 MMDBridge 渲染采样顺序，不再混同为 PMX Editor solver 差异。
- `tests/headless_smoke.py` 增加默认目标为 MMD、两个 DLL 文件名与 ABI 4 的回归。源码 Junction 保持不变，不递增插件版本、不打包 zip。

## 2026-08-17 - Blender 预览与 PMX Editor 根平移物理 bit 级对齐

- 本轮验收边界按实际工作流收窄为：不播放 IK/Morph、不改变骨骼旋转，只对模型根骨做平移；比较对象是 Blender 当前物理场景按 `mmd_tools` 实际导出的 PMX，在 PMX Editor 使用的 `PmxNLib.dll` 中运行后的物理刚体状态。MMD 本体以及任意 VMD/IK 最终骨骼顺序不在本轮结论内。
- Rust/Blender adapter 改为直接生成 PMX native 单位与坐标系的 Body/Joint 描述符，按 `mmd_tools` exporter 的 `mathutils.Vector` float32 运算顺序复现刚体尺寸和 Joint 位移限制。Rossi、达妮娅、Laevatain 三个实际模型的 adapter payload 与真正执行 `mmd_tools.export_pmx(scale=12.5)` 后重新读取出的物理 payload 逐 byte 一致，分别覆盖 `339/471`、`406/561`、`115/79` 个 Body/Joint。
- PMX Euler 转 quaternion 不再经过 Blender quaternion 近似路径；ABI 升到 `4`，native helper 复现 PMX Editor `SlimDX.Quaternion.RotationYawPitchRoll(Y, X, Z)` 的 float half-angle、`msvcr100` double `sin/cos` 和运算分组。三模型累计 `2487` 个 Body/Joint rotation 与 SlimDX 输出逐 bit 一致，并新增固定 bit 回归。
- 根骨平移时，0 型刚体使用 PMX Editor `SetData1` 对应的 position-only 路径：只更新 `btRigidBody` world transform 与 `btDefaultMotionState`，不额外修改 interpolation transform、activation 或 AABB。修复前首个差异出现在 frame 1；修复后同一 120-frame 平移曲线中，Rossi `2,603,520/2,603,520`、达妮娅 `3,118,080/3,118,080`、Laevatain `883,200/883,200` 个刚体 transform bytes 全部一致，首个差异均为 `None`。
- 同一 bone 由多个动态刚体回写时，driver 选择从“最大 mass”改为 PMX Editor BodyList 顺序的 last writer wins；Blender 输出位置仍在 adapter 边界乘回 import scale。新增静态刚体平移跨 step 保持测试，并更新完整 smoke 的 PMX-unit 断言。
- VS2013 RTM LTCG native build 的 `11/11` Rust tests 通过，DLL SHA256 为 `EDF5A6DCC445741FEA4C68A7CEE8D7C8B2D3C49E7B44C0F04D3E75A07E7D7537`；Blender 4.4.3 完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。首次 smoke 命中既有开放代理随机阈值波动，立即复跑通过；synthetic recovery traceback 是测试主动注入。继续使用真实 Blender 4.4 源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - 物理对象三层命名与 PMX 顺序编号统一

- 修正骨骼物理创建把 Blender bone name（如 `背蝴蝶结_0_1.L`）同时写入刚体/Joint 日文名和英文名的问题。创建时现在读取骨骼 MMD 元数据并统一侧向规则：MMD 日文名使用 `左/右` 前缀，英文名使用 `_L/_R` 后缀；只有 Blender 骨骼名保留 `.L/.R`，Rigid/Joint 的 Blender object name 使用 MMD 日文名。
- 新增集中命名模块 `mmd_skirt_proxy_creator/mmd_naming.py`，供骨骼创建、代理物理创建、镜像创建/同步、Joint 名称同步与诊断安全补名共同使用，避免不同入口再次各写一套左右命名规则。已有非空 MMD 字段不会由诊断修复无条件覆盖。
- 插件创建骨骼物理、代理物理或镜像物理后，立即调用官方 `mmd_tools.operators.misc.MoveObject.normalize_indices()` 对对应模型的 Rigid/Joint 实际顺序编号。Blender 名由此直接成为 `000_左...` / `000_J.左...`；后续使用“PMX 实际顺序”移动项目会继续自动重编号，而不是把编号当作静态字符串。同步刚体 B 名称或镜像参数时保留现有三位顺序前缀，不再把编号擦成无前缀的 `J.xxx`。
- `tests/bone_physics_creator_smoke.py` 新增 MMD 日/英文名、Rigid/Joint Blender object name、创建即编号、重排后编号和镜像命名回归；`tests/headless_smoke.py` 新增代理刚体/Joint 全量编号、Joint 同名时保留编号及精确镜像代理左右命名回归。Blender 4.4.3 独立 smoke 输出 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`，完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。
- 对 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 做不保存验证：删除左右 `背蝴蝶结_0_1.L/.R` 的原 Joint 后同时运行“基础 Joint”，新对象为 `502_J.右背蝴蝶结_0_1` / `503_J.左背蝴蝶结_0_1`，MMD 日文名分别使用右/左前缀，英文名分别为 `Skirt_0_1_R` / `Skirt_0_1_L`，标记 `MMD_07_NAMING_AND_ORDER_OK`。另把既有 `165_J.` 项临时改成旧式错误名称后执行同步，恢复为 `165_J.左背蝴蝶结_1_1 | 左背蝴蝶结_1_1 | Skirt_1_1_L`，标记 `MMD_07_EXISTING_JOINT_NAME_SYNC_OK`，证明可修旧 Joint 且不丢编号。临时脚本已删除；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - 全插件物理坐标系审计与回归加固

- 沿全部实际写入位置/旋转的路径审计骨骼物理创建、代理物理创建与更新、3D 同步、左右镜像及 Rust 物理预览。除上一条已修复的“基础 Joint 从 Blender bone roll 重建坐标系”外，没有发现第二处同类坐标系错误；其余路径分别使用明确的 armature/model-local 几何、完整 world matrix 镜像或 world-space solver 变换，不能统一替换成刚体 B rotation。
- 加固 `tests/bone_physics_creator_smoke.py`：骨骼生成刚体的局部 Z 必须沿骨骼方向且基底 determinant 为正；镜像刚体和 Joint 在带平移与旋转的非单位 Root 下，完整 4x4 world matrix 必须等于以 Armature 局部 X 平面反射的结果。验证覆盖创建与同步，而不再只比较 world X 位置。
- 加固 `tests/headless_smoke.py`：代理刚体必须保持右手基底且局部 Z 沿代理骨骼；锚点/纵向 Joint 必须与其刚体 B 同坐标基，横向 Joint 必须与其来源列刚体 A 同坐标基。横向 Joint 的规则是既有约束语义，不能因为基础 Joint 的 bug 而改成刚体 B。
- Blender 4.4.3 独立骨骼 smoke 输出 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`；完整 smoke 复跑输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。首次完整 smoke 在既有开放曲线位移阈值断言处出现一次波动，立即复跑通过，坐标系专项断言两次均已先通过；已有 synthetic recovery traceback 是测试刻意注入。继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - 基础 Joint 左右坐标系改用刚体 B 方向

- 复现“同时选择带 `.L/.R` 标识的左右骨骼后创建基础 Joint，左右坐标系与 PE 结果相反/错位”的问题。根因不是后缀配对或 Blender 显示：`bone_physics_creator.builder._create_joint()` 过去用 child bone 的 Blender roll/x-axis 重新构造 Joint rotation；导入 PMX 后的 Blender bone roll 并不保存 PE Joint 的坐标基，因此即使 Joint 位置与刚体 A/B 正确，局部轴仍可能接近翻转。
- 以 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 的 PE 原始左右蝴蝶结 Joint 做只读对照。旧 bone-derived rotation 与左右原 Joint 的 quaternion 角差均为 `177.246619°`；原 Joint 与各自刚体 B 的 rotation 角差均为 `0°`。这同时排除了“仅显示形状看起来不一样”和“左右后缀串位”。
- 基础 Joint 和“刚体 + 连接 Joint”现在以实际选中的刚体 B 的 MMD/model-local rotation 作为 Joint 坐标系，位置仍取 child bone head。对于现有 PE 刚体，这会保留其真正的左右镜像方向；对于本工具刚创建的刚体，Joint 与刚体 B 保持同一坐标基，不额外重复镜像。
- `tests/bone_physics_creator_smoke.py` 先加入任意非默认刚体 B rotation 回归并确认旧实现失败，修复后要求新 Joint quaternion 与刚体 B 严格一致。随后在 `07.blend` 中只读删除原左右 `背蝴蝶结_1_1.L/.R` Joint、同时重新运行“基础 Joint”，新建两侧的 rotation 与 PE 原 Joint 均在 `0.0001°` 内、位置误差小于 `1e-7`，标记 `MMD_07_BASE_JOINT_AXES_OK`；工程未保存，临时脚本已删除。
- Blender 4.4.3 完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`，独立骨骼物理 smoke 输出 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`。继续使用源码 Junction，不递增版本、不打包 zip；本修复不自动改写本轮修复前已经创建的 Joint，需要 Reload Scripts 后删除并重新创建这些 Joint。

## 2026-08-17 - 未锚定动态链跳转 Joint 与逐条安全修复

- 修正未锚定动态链诊断的跳转目标：连通分量内存在 Joint 时，不再跳到链首刚体，而是优先跳到稳定排序后的链首相邻 Joint，使用户可以直接编辑活动项中的刚体 A/B、限制和弹簧参数；只有整个自由分量连一个有效 Joint 都没有时，才退回刚体，因为此时不存在可跳转的 Joint。诊断搜索索引同步加入分量内全部 Joint 的 Blender/MMD 名称。
- 诊断列表每行在跳转按钮旁新增“尝试安全修复”按钮。修复采用 fail-closed：当前能够确定等价结果的“MMD 骨骼名称为空”会自动填入 Blender 骨骼名并立即刷新诊断；缺失 Joint 端点、重复 Bone ID、无锚动态链等无法从现有模型唯一推断原始目标的问题不会猜测、不会按距离乱连，而是报错要求跳转后手动处理。修复操作支持 Undo。
- 未锚链的处理指引现在明确要求检查跳转到的链首附近 Joint 的刚体 A/B；若原锚定 Joint 已被删除，应以该 Joint 为参照创建或恢复连接，而不是把整条链改为 0 型。测试新增两刚体自由链，验证诊断目标为 Joint、跳转后该 Joint 成为活动项、安全骨名修复后诊断行消失，以及不安全修复拒绝修改。
- Blender 4.4.3 完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`，独立骨骼物理 smoke 输出 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`。以 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 只读验证：搜索 `191_左背蝴蝶结_4_1` 的警告现在跳到实际 Joint `534_J.左背蝴蝶结_1_1`；尝试自动修复会明确拒绝且刚体 A/B 保持不变。工程未保存，临时脚本已删除；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - MMD 查看器名称前缀显示过滤

- 在“仅显示当前代理”右侧新增“按前缀过滤”复选框。启用后，骨骼、刚体和 Joint 列表只显示其可见 MMD 名称或 Blender 内部名称以当前“名称前缀”开头的项目；可与“仅显示当前代理”和搜索框叠加，关闭后立即恢复完整列表。
- 该功能直接复用现有 `browser_prefix` 输入框和 UIList 的显示过滤，不重建模型列表、不重扫诊断、不触发 depsgraph/timer，因此输入前缀和反复切换的成本仅为当前已缓存列表的一次轻量字符串判断，并保留勾选状态与活动项。前缀为空时视为不过滤，避免误把列表清空。
- 从诊断项跳转时会同时关闭“仅显示当前代理”和“按前缀过滤”并清空搜索，确保问题对象不会因为过滤条件而无法显示。扩展 `tests/headless_smoke.py`，验证默认状态、前缀筛选、与搜索条件求交集以及诊断跳转清除过滤；Blender 4.4.3 完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`，独立骨骼物理 smoke 输出 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`。继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - MMD 查看器架构级自动刷新与性能边界

- 新增统一的 `depsgraph_update_post` 自动刷新服务，不再要求每个旧操作或未来新增功能逐一记得调用诊断刷新。当前 MMD 模型的 Object、Armature data 或所属 Collection 发生结构/属性变化后，会把查看器标记为 dirty；位于 MMD 查看器时自动刷新，位于代理创建/物理预览页时只记录 dirty，返回查看器后再刷新。
- 自动刷新在后台始终重扫诊断集合，即使用户已经从诊断跳转到骨骼、刚体或 Joint Tab 修复问题，修好的诊断行也会直接从诊断数据中消失；当前可见的普通列表随后同步刷新，活动索引会安全收敛到剩余范围。手动刷新成功也会清除 dirty，避免紧接着重复扫描。
- 性能边界保持保守：只观察当前所选 MMD root 的对象父链、该 root 子树使用的 Armature data 与包含该 root 对象的 Collection；无关场景对象更新不会触发。连续编辑使用 `0.25 s` quiet-window debounce 合并为一次扫描，Rust 物理预览运行期间完全跳过，非查看器页不启动 timer，面板 draw 只负责在返回时安排一次延迟刷新，不在 draw 内直接扫描模型。
- `tests/headless_smoke.py` 增加 handler 注册、无关对象隔离、非查看器延迟、预览期间跳过、相关模型变更调度，以及“在 Joint Tab 修好刚体 B 后诊断行立即消失”的回归。Blender 4.4.3 完整 smoke 通过，输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；`BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3` 通过。已有 synthetic recovery traceback 是测试刻意注入。
- 以 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 做只读验证：在刚体 Tab 临时把 `187_左背蝴蝶结_0_1` 设为 0 型后，后台刷新会移除搜索 `191_左背蝴蝶结_4_1` 命中的未锚定链警告；恢复原类型后警告重新出现。工程未保存，临时脚本已删除；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-17 - 诊断 Tab 刚体–Joint 连通图与未锚定动态链检查

- 补上此前诊断只检查单项 RNA 字段、没有检查整体物理拓扑的缺口。诊断刷新现将当前 MMD 模型全部刚体按有效 Joint 端点拆成连通分量；只要一个含动态刚体的分量无法沿 Joint 到达任何 0 型刚体，就报告“未锚定动态链”警告。该规则与物理预览启动时的自由分量判定一致，但保留为 `WARNING`，因为独立自由物体也可能是作者有意设计。
- 每条图级警告以稳定排序后的链首/端点刚体作为跳转目标，显示动态刚体数量和“无法到达 0 型锚点”的原因；搜索索引额外包含该分量内全部刚体对象名、MMD 日/英文名及绑定骨骼名，因此搜索链尾 `191_左背蝴蝶结_4_1` 也能定位到整组问题并跳到真正需要修复的链首 `187_左背蝴蝶结_0_1`。处理指引要求恢复链首到 0 型刚体或其它已锚定物理链的 Joint，并明确禁止把整条链盲目改成 0 型。
- Blender 4.4.3 完整 `tests/headless_smoke.py` 通过，继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；回归临时创建单刚体自由分量，验证严重级别、跳转目标、全分量搜索文本和修复指引，结束后删除 fixture。
- 以 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 做只读 headless 复核：诊断现稳定报告 `3` 组未锚定动态链；搜索 `191_左背蝴蝶结_4_1` 命中“左背蝴蝶结_0_1，5 个动态刚体无法通过 Joint 到达 0 型锚点”，跳转目标为 `187_左背蝴蝶结_0_1`。未保存工程，临时探针已删除；不递增版本、不打包 zip。

## 2026-08-17 - Endfield Laevatain 第三角色全轨迹逐 bit 复核

- 使用 `D:\MMD\模型\Alicia\Endfield-Laevatain\Endfield-LaevatainVer1.04_By_Alicia` 的两个原始 PMX 做第三角色独立验证：`LaevatainVer1.04_ALL.pmx` 为 `305 bodies / 405 joints`，`LaevatainVer1.04_Body.pmx` 为 `115 bodies / 79 joints`；全部 Joint 均为受支持的 PMX Spring 6DOF，刚体引用全部有效。
- 两侧消费同一份未经 Blender 场景导入或二次量化的 native payload，以 Y-up、重力 `-98`、60 Hz、`maxSubSteps=10` 连续运行 120 帧。比较双方 Bullet 刚体的原始 64-byte `btTransform`（3x3 basis + origin）：ALL 共 `2,342,400/2,342,400` bytes 逐 bit 相同，Body 共 `883,200/883,200` bytes 逐 bit 相同；位置、旋转、Joint、碰撞及长期传播均未出现分叉。
- 验证使用当前生产 DLL SHA256 `29914B23889C3CB3E8D48BDC7A22089035D4BFF1E101DAA553F62CFEECE12405`，全程 headless；未修改求解器或 Blender adapter，不递增版本、不打包 zip。

## 2026-08-17 - 诊断 Tab 骨骼误报修正与处理指引

- 根据真实模型中一次出现 `203` 条错误的反馈，确认上一轮有两条诊断规则错误地把 `mmd_tools` 内部 UI/约束状态当成 PMX 结构损坏：`display_connection_type == BONE` 但未指定目标并非错误，exporter 会合法回退到骨尾 offset；`is_additional_transform_dirty` 默认即为 `True`，表示 Blender 追加变换约束待同步，不代表 PMX 追加变换引用失效。
- 删除“骨骼末端连接目标不存在”和仅由 `is_additional_transform_dirty` 触发的“追加变换引用无效”诊断。仍保留真正会被 exporter 自动禁用的情况：已经开启“旋转 + / 移动 +”但没有追加变换目标骨骼。模型、骨骼、刚体和 Joint 数据均未被自动改写，用户不需要逐条修复此前的 203 条误报。
- 诊断页新增明确边界说明与当前问题处理方法。每条保留问题现在携带对应修复指引，例如缺少刚体 B 时提示跳转后在活动项属性指定“刚体 B”；诊断跳转、搜索清空和活动项同步保持不变。
- 扩展 `tests/headless_smoke.py`，断言合法的空骨骼末端目标与 `is_additional_transform_dirty` 不再出现于诊断，并验证缺失刚体 B 的修复指引。Blender 4.4.3 完整 headless smoke 通过，标记 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；另以截图对应的 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 做只读 headless 扫描，模型 `鸣潮_达妮娅1.2（blue ver）` 刷新后为 `0 errors / 0 warnings`，未保存工程，临时脚本已删除。不递增版本、不打包 zip，真实 GUI 需 Reload Scripts 或重启 Blender 后刷新诊断页查看新结果。

## 2026-08-16 - PmxNLib 碰撞网络与 VS2013 RTM LTCG 全轨迹逐 bit 对齐

- 将 Rossi 完整物理的首个碰撞分叉缩减为只开放 body `62 下半身` Capsule 与 body `205 スカート_0_10` Box 碰撞的最小夹具。旧生产 DLL 在第 5 帧只出现一个 `5.960464477539063e-08` 的 float ULP 差异；逐帧读取双方 `btPersistentManifold` 后确认第 3 帧 contact 完全一致，第 4 帧开始只有 GJK witness point 的末位不同，因此误差不在重力、shape 参数、Joint、solver iterations 或模型特判。
- 反汇编 `btConvexConvexAlgorithm::processCollision` 确认 PmxNLib 使用 VS2013 RTM whole-program optimization 路径；仅用 VS2013 编译但交给新 linker 会改变 LTCG codegen。native Bullet 现在固定由 `cl.exe 18.00.21005.1` 以 `/fp:fast /GL` 编译，并由同版 VS2013 `link.exe /LTCG` 完成 code generation。`build.rs` 将 native static library 以 `static:-bundle` 直接交给最终 linker，避免 Rust rlib 隐藏旧 LTCG object；`build.ps1` 新增 exact toolchain 探测、版本硬检查与可配置的 `MMD_V120_*` 路径，不允许普通当前 MSVC 静默产出“近似版”生产 DLL。
- 同一份未经 Blender 二次转换的原始 PMX payload 在 PmxNLib 与生产 DLL 中以 Y-up、重力 `-98`、60 Hz、`maxSubSteps=10` 连续运行 120 帧。Rossi `339 bodies / 471 joints` 的 `2,603,520` 个原始 `btTransform` bytes 全部逐 bit 相同；达尼娅 `406 bodies / 561 joints` 的 `3,118,080` bytes 也全部逐 bit 相同。比较对象直接是每个 Bullet rigid body 的 3x3 basis 与 origin 共 64 bytes，不经过 matrix/quaternion 往返；因此同时证明位置、旋转、RGBA、普通裙子、完整 Joint 网络和碰撞长期传播对齐。
- 最小 Capsule/Box 夹具同样连续 120 帧逐 bit 相同。生产 DLL SHA256 更新为 `29914B23889C3CB3E8D48BDC7A22089035D4BFF1E101DAA553F62CFEECE12405`。Rust release tests `9/9`、`MMD_TIME_DRIVER_UNIT_OK`、`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96` 与 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3` 全部通过；已有 synthetic recovery traceback 是回归刻意注入。本轮全部验证为 headless，不操作 GUI、不递增版本、不打包 zip。

## 2026-08-16 - MMD 骨骼详细属性与模型诊断 Tab

- 补齐 `MMD 查看器 > 骨骼` 的活动项 Inspector：除日/英文名与变形开关外，现直接显示并可编辑 Bone ID、变形阶层、物理后变形、可控制/尖端骨骼、IK 角度、固定轴、局部轴、旋转/移动追加变换、追加目标与影响、骨骼末端连接类型和目标。字段直接绑定当前 `mmd_tools` 的 `mmd_bone` RNA，不复制其数据。
- 在骨骼、刚体、Joint 右侧新增“诊断”Tab。刷新时扫描当前选定 MMD 模型的空 MMD 骨名、重复 Bone ID、失效追加变换/末端连接、缺失 Rigid Body 数据、刚体绑定不存在骨骼、Joint 缺失 constraint/刚体 A/刚体 B、端点不属于当前模型以及 A/B 指向同一对象；结果按错误/警告汇总，不受“仅显示当前代理”限制。
- 每条可定位问题提供跳转按钮：自动清空搜索与代理过滤，切换到骨骼/刚体/Joint 对应 Tab，将问题项设为蓝色活动行，并同步为 Blender 的活动骨骼或活动对象。无法定位到具体对象的模型级问题只显示诊断，不提供伪跳转。
- 修改 `mmd_skirt_proxy_creator/mmd_physics.py`、属性组注册顺序 `mmd_skirt_proxy_creator/__init__.py` 与 `tests/headless_smoke.py`。Blender 4.4.3 完整 `headless_smoke.py` 通过，标记 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；独立 `bone_physics_creator_smoke.py` 通过，标记 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=9 joints=5 ordered=3`。验证覆盖骨骼详细字段、缺失刚体 B 的诊断和跳转行为；已有 synthetic recovery traceback 仍为回归刻意注入。继续使用源码 Junction，不递增版本、不打包 zip；未改动本轮开始前已有的 native solver/DLL 工作树修改。

## 2026-08-16 - Endfield Rossi 跨模型原始 PMX differential 验证

- 使用 `D:\MMD\模型\Alicia\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx` 做独立跨模型验证。仅以 headless `mmd_tools.core.pmx.load` 读取 PMX 二进制字段，不创建 Blender 场景对象；同一份 native payload 分别直连 PmxNLib 与生产 DLL，在原始 PMX 尺度、Y-up、重力 `-98`、60 Hz、`maxSubSteps=10` 下逐帧运行 120 帧。模型包含 339 bodies / 471 个 PMX Spring 6DOF Joint，Joint 引用全部有效；其中 RGBA graph 为 body `0..13`（10 个 dynamic body、18 Joint），普通裙子为 `スカート_*` 144 bodies / 288 个相关 Joint。
- 自由积分与完整 471 Joint-only 网络在全部 120 帧均为 `122040/122040` 个位置 float component 逐 bit 相同，进一步证明达尼娅结果不是角色特判。完整 collision + Joint 的第 1 帧同样为 `1017/1017` component 逐 bit 相同；RGBA 10 个 dynamic body 在完整物理的 120 帧轨迹中为 `3600/3600` component 逐 bit 相同，可观测角度残差上限约 `1.04e-5°`，处于 matrix/quaternion 换算噪声。
- 对完整模型连续 120 帧统计严格 bit 命中率：全 339 bodies 为 `69813/122040 = 57.205015%`，295 个非静态 bodies 为 `53973/106200 = 50.822034%`，裙子为 `5039/51840 = 9.720293%`。这说明此前约 99.92% 的说法只适用于达尼娅首帧 component，不能代表任意模型的长期轨迹；裙子网格中的极小碰撞差异会经 Joint 网络传播，使严格 bit 命中率快速下降。
- 严格 bit 下降并不等于同量级视觉误差。完整 120 帧中全模型位置最大残差为 `0.010181357` PMX unit（0.08 导入约 `0.815 mm`，body `tail_base_L_a__jnt21`，frame 71），第 120 帧最大为 `0.003556893` PMX unit（约 `0.285 mm`）；裙子轨迹最大为 `0.005213510` PMX unit（约 `0.417 mm`），第 120 帧最大约 `0.285 mm`、平均约 `0.081 mm`。裙子第 120 帧可观测角度残差平均 `0.089574°`、P95 `0.245584°`、最大 `0.693022°`，120 帧内瞬时最大 `1.51525°`。
- 隔离 collision-only 后，全部位置 component 的 120 帧 bit 命中率为 `97.009177%`，裙子为 `96.836420%`；Joint-only 则保持 100%。因此 Rossi 的剩余分叉同样来自 collision contact 的末位差异及其经 Joint 网络的长期传播，不是 RGBA/裙子参数特判。生产 DLL SHA256 保持 `4349BDEBE9489361216A76E996F531DFEB8E2C5D22DAA56F03F108400888C4E6`；本轮只做验证和记录，未修改求解器、Blender adapter、版本号或发布包。

## 2026-08-16 - PmxNLib 浮点构建路径与 Box inertia / 多约束逐 bit 对齐

- 对同一份 native payload 继续做对象级差分。最小 Joint 链 `(19, 35, 51)` 中，PmxNLib 与 Rust world 的 `btGeneric6DofSpringConstraint` frame、limit、spring 字段一致，首个分叉定位到 body `73` 的初始 inverse inertia，而不是 Joint 构造或 RGBA 特判。
- 反汇编确认 PmxNLib 的 `btBoxShape::calculateLocalInertia` 来自 VS2013 `/fp:fast` 算术顺序：使用 `mass * float(1/12)`，尺寸乘 `2.0f`；当前 MSVC 默认路径使用 `mass / 12` 与不同的加法顺序，产生 float ULP 差异。native wrapper 现显式复现该 Box inertia 运算，并补充 VS2013 对 `thread_local` 和 move 语义的兼容实现；没有加入模型、骨名、RGBA 或裙子特判。
- 达尼娅 `406` 个刚体的初始 local inverse inertia 已全部与 PmxNLib 逐 bit 相同：Sphere `71`、Box `219`、Capsule `116` 均零 mismatch。禁用 collision、启用全部 `561` 个 Joint 时，第 `1` 帧和第 `120` 帧的 `1218/1218` 个位置 float component 全部逐 bit 相同，修正了此前“复杂 Joint 网络必然因编译器版本累积分叉”的不精确判断。
- 使用 VS2013 Update 5 + `/fp:fast` 构建后，collision-only 第 `1` 帧仅 body `216` 的一个位置 component 不同，最大残差 `2.51248e-10` PMX unit；完整 561 Joint + collision 第 `1` 帧最大残差 `1.89175e-10` PMX unit。抽样 Capsule/Box、Box/Box 碰撞对在第 `1`、`120` 帧均逐 bit 相同；剩余最小分叉缩小到 Sphere/Box `(38, 216)` 的首帧约一个 ULP，随后在多接触网络中混沌放大。故 Joint-only 与初始 inertia 已 bit-exact，但不能宣称全部碰撞网络 120 帧 perfect；完整模型第 `120` 帧最大位置残差仍为 `0.046535836` PMX unit。
- 生产 DLL 改为 PmxNLib 同代的 VS2013 Update 5 `/fp:fast` 构建，SHA256 为 `4349BDEBE9489361216A76E996F531DFEB8E2C5D22DAA56F03F108400888C4E6`，依赖 `MSVCR120.dll` / `MSVCP120.dll`。`cargo test --release` 9 项、`MMD_TIME_DRIVER_UNIT_OK`、`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK` 与 `BONE_PHYSICS_CREATOR_SMOKE_OK` 全部通过；验证均为 headless，未修改 Blender adapter，不递增版本，不打包 zip。

## 2026-08-16 - PmxNLib 原生 world ground plane 对齐与 differential harness 更正

- 更正上一条原始 PMX differential harness 的两处问题：Quaternion 现严格调用与 `PmxEditor.TransformPhysics.WriteBody/WriteJoint` 相同的 `SlimDX.Quaternion.RotationYawPitchRoll(Y, X, Z)`，不再用 `mathutils.Euler('YXZ')` 近似；Rust `BodyDesc.collision_group` 传入 PMX 的组号 `0..15`，不再错误地预先传 `1 << group` 后又被 native backend 二次移位。禁用 collision/joint 的达尼娅 406 bodies、120 帧位置仍为 `1218/1218` float component 逐 bit 相同，确认更正后的同 payload 基线有效。
- 函数级反汇编确认 PmxNLib 创建每个 world 时都会先加入一个 `btStaticPlaneShape(normal=(0,1,0), constant=0)`，碰撞 group 为 `0x8000`、mask 为 `0xffff`。此前实验因为错误 collision group harness 得出“ground plane 会恶化”结论，现已推翻；生产 Bullet backend 按 PmxNLib 的创建顺序加入并持有同语义 ground shape/motion state/rigid body，销毁 world 前显式移除 ground body，避免悬空 world 引用。
- ground proxy 的插入顺序不仅提供 MMD 地面，也决定 `btDbvtBroadphase` proxy/overlap ordering。修复后，达尼娅 collision-only、无 Joint 的第 1 帧由最大 `0.000746976` PMX unit 收敛到 `0.000000188`，`1194/1218` 个位置 component 逐 bit 相同；完整 561 Joint 第 1 帧最大位置残差为 `0.000082379` PMX unit，`1087/1218` component 逐 bit 相同。逐一只启用单个 Joint 时均小于 `1e-7` PMX unit，剩余首帧误差来自多约束网络内的 float/codegen 累积，不是 RGBA/裙子/骨名特判。
- 同一份未经 Blender 场景转换的 PMX payload 连续逐帧运行 120 帧：Alicia RGBA body 5/11 的位置仍与 PmxNLib 完全相同，全模型最大位置残差仍为 `0.000108370` PMX unit；达尼娅完整模型最大位置残差为 `0.023246871` PMX unit（body `前链子_6_1`，0.08 导入约 `1.860 mm`），严格 `スカート_*` 176 bodies 最大为 `0.019432703` PMX unit（约 `1.555 mm`）。这比旧 harness 更接近且证明通用 world 语义缺口已修复，但复杂网络 120 帧仍未逐 bit 一致，不能宣称所有 MMD 物理 perfect/bit-exact。
- `/fp:fast` A/B 会把完整模型 120 帧最大残差扩大到 `0.113459010` PMX unit，已拒绝并恢复 MSVC 默认 precise 路径。新增 `mmd_ground_plane_supports_dynamic_bodies` 回归，并把通用 runtime smoke fixture 临时整体移到 ground plane 上方、结束后恢复，避免把地面接触混入原有 adapter 对齐断言；`cargo test --release` 9 项、`MMD_TIME_DRIVER_UNIT_OK`、`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK` 与 `BONE_PHYSICS_CREATOR_SMOKE_OK` 全部通过。生产 DLL SHA256 为 `C88E1602563386B8E7A03385D7A15B3FFB236D750C5F1CD70BE6622C7D3D2563`；未修改 Blender adapter、未加入模型参数补偿、不递增版本、不打包 zip。

## 2026-08-16 - 原始 PMX 直连 PmxNLib/Rust differential 审计

- 建立一次性 headless differential harness：仅用 `mmd_tools.core.pmx.load` 作为 PMX 二进制字段解析器，不创建 Blender 场景对象、不执行 mmd_tools 导入、不进入 PMX Editor/MMD GUI；同一组原始 body/joint 字段同时序列化为 `PmxNLib.SetObjects()` native payload 与 Rust C ABI descriptors，在原始 PMX 尺度、Y-up、重力 `-98`、60 Hz、`maxSubSteps=10` 下逐刚体运行 120 帧。RGBA 样本为 `D:\MMD\模型\Alicia\Body\Body_Ver4.23_26.6.20\Body_Ver4.23.pmx`（89 bodies / 50 joints），普通裙子样本为 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\鸣潮_达妮娅1.2（blue ver）.pmx`（406 bodies / 561 joints）；两者 joint kind 均全部为 PMX Spring 6DOF（`0`），无失效 body reference。
- Alicia RGBA 的 body 5/11 在 120 帧共 720 个位置 float component 上与 PmxNLib 全部逐 bit 相同；全模型最大位置残差为 `0.000108370` PMX unit（0.08 导入尺度约 `0.00867 mm`）。当前 ABI 只返回 quaternion，而 PmxNLib `GetData1` 返回 matrix，`quaternion -> matrix` 往返本身引入 float 舍入，因此本轮不能把旋转 matrix bit 统计冒充底层 basis 逐 bit 证明。
- 达尼娅严格日文名 `スカート_*` 的 176 个裙子刚体并未逐 bit 相同：120 帧最大位置残差为 `0.025766714` PMX unit（0.08 导入尺度约 `2.061 mm`），最大可观测旋转残差约 `3.65°`；包含链子、穗子、蝴蝶结和裙带等英文 `Skirt_*` 附件时，全组最大位置/旋转残差约 `0.040494747` PMX unit / `20.37°`。因此不能宣称所有物理均与 MMD/PmxNLib 逐 bit 相同。
- 隔离结果：禁用 collision 与 joint 后，达尼娅全部 406 bodies 的 120 帧位置逐 bit 相同，证明原始 body transform、shape、质量/阻尼、重力与自由积分路径一致；仅 dynamic-static collision 前 5 帧最大残差约 `8.63e-6` PMX unit；仅 dynamic-dynamic collision 第 1 帧即约 `0.02885` PMX unit，主要分叉位于复杂多接触的 broadphase/manifold/solver ordering，joint-only 则从约 `9.54e-7` PMX unit 开始累积。两个重叠 Sphere/Box/Capsule 的最小单接触夹具前 5 帧位置均逐 bit 相同，排除了通用 shape 尺寸或单接触公式错误。
- 对 PmxNLib 固有 `btStaticPlaneShape` 做了可回退 A/B：加入 Rust world 后 Alicia 不变、达尼娅最大位置残差反而增至 `0.045806259` PMX unit，故已撤销，生产源码不保留该实验。恢复后两组 120 帧 Rust 二进制输出与实验前 SHA256 完全一致。`cargo test` 8 项通过；因重新链接，生产 DLL SHA256 为 `A8A7EC47875FD05F22E4ED330D25C8423EEF7B8AAADEE0D850FEE9C303C4B7CF`。本轮未改 adapter/Rust 求解语义、不递增版本、不打包 zip。

## 2026-08-16 - 07.blend 裙摆 Box 刚体 Y/Z 尺寸轴修复与 PmxNLib 轨迹复核

- 用真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\07.blend` 建立只读 headless 差分环：导出临时 PMX，直接按 `PmxEditor.TransformPhysics.WriteBody/WriteJoint` 的 native payload 格式驱动 `PmxNLib.dll`，并让当前 Rust DLL 在同一静止姿态、60 Hz、面板重力 `-9.8`（native `-98`）、`maxSubSteps=10` 下运行 120 帧；同时分别验证原碰撞 mask 与全禁用碰撞。未启动或操控 MMD/Blender GUI，未保存或覆盖 `07.blend`。
- 根因不是裙子参数，而是通用 Box shape 的坐标基底转换遗漏：Blender/mmd_tools 在 Z-up 中保存 PMX Box 尺寸为 `X/Z/Y`，旧 DLL 已把 body 位置和旋转转换到 MMD Y-up，却把 Box half-extents 原样交给 Bullet。实际 `Skirt_C01_R01` 因而由 PMX/PmxNLib 的 `(0.220049, 0.376144, 0.102585)` 错建为 `(0.220049, 0.102585, 0.376144)`，造成竖向碰撞体被压扁、前后被加厚。
- Rust 现仅对 Box half-extents 执行 Blender Z-up → MMD Y-up 的 Y/Z 交换；Sphere 不变，Capsule 继续按 PMX 的 `radius/height` 字段及 Bullet 原生 Y-axis capsule 处理，避免把 shape 类型无差别转换。新增 `blender_box_half_extents_are_reordered_for_mmd_y_up_space` 回归测试。
- 修复前 `07.blend` 原碰撞 120 帧下半裙平均径向变化为 `-6.576808 mm`，PmxNLib 为 `-10.483351 mm`；修复后为 `-10.650660 mm`，残差收窄至约 `0.167309 mm`。最大外扩由修复前 `11.032579 mm` 变为 `12.642940 mm`，PmxNLib 为 `12.637069 mm`，残差约 `0.005871 mm`。全禁用碰撞时修复后下半裙平均径向残差约 `0.023104 mm`、最大外扩残差约 `0.127123 mm`。这证明截图中的主要异常来自 DLL Box 碰撞几何，而非可直接归咎于裙子参数；当前结果为近似 PmxNLib，不宣称所有模型/帧逐 bit 相同。
- `cargo test --release` 8 项、`MMD_TIME_DRIVER_UNIT_OK`、`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`、`BONE_PHYSICS_CREATOR_SMOKE_OK` 全部通过。生产 DLL SHA256 为 `C5A6D99D16429474E229B59CE5C587ED8DA1CA3FE4792265959500EC8C4BBED5`；本轮不递增版本、不打包 zip。

## 2026-08-16 - Blender 实时预览双时钟与 MMD 追帧语义（主工作区开发）

- 定位实时拖动比 MMD 更粘滞的 host 原因：旧 adapter 虽然让 DLL 固定使用 Bullet `1/60 s` 子步，却在每次 `bpy.app.timers` 回调时都硬传 `dt=1/preview_frequency`。Blender 交互、depsgraph 和界面刷新会让 timer 回调产生抖动，实际过去约 `30 ms` 时仍只推进 `16.67 ms`，因此物理时间落后于用户拖动；这不是 RGBA stiffness、阻尼或重力误差，本轮不改 DLL 求解参数。
- 新增独立 `PreviewTimeDriver`。动画播放时以 `(frame_current + frame_subframe) / scene_fps` 的 timeline 差值调用 `stepSimulation(delta, maxSubSteps, 1/60)`，同一动作轨迹不再受 GUI timer 抖动影响；暂停状态下使用 `time.perf_counter()` 的真实单调时间差，使手动拖动按真实经过时间推进。播放/暂停切换先重定基准而不虚构时间，倒放、暂停时跳帧和时钟回退会恢复启动快照；异常长间隔继续由 MMD 同值 `maxSubSteps=10` 在 Bullet 内限制实际追帧量。
- 多模型仍按 world 并行：一次 timer tick 只读取一次 wall clock，各 world 分别按自己的 scene/timeline 生成 dt，同交互组共享一个时间驱动与一次 solver step；`dt=0` 的 timeline 空闲 tick 不重复推进或写回。重置、RNA rebind 和异常恢复同步清空时间基准，下一步从固定 `1/60 s` 重新建立状态。
- 新增纯 Python 时间回归，临时生成含匀速、急停、停顿和反向段的 VMD，验证两组不同 wall-clock 抖动仍生成完全相同的 timeline dt，暂停拖动则保留 `16/33/8 ms` 实际间隔，临时 VMD 退出即删除。Blender 4.4.3 完整 headless smoke 实际导入另一份临时 VMD、驱动真实 Rust solver，确认 30 FPS 的帧差依次传入 `1/60、1/30、2/30、3/30、4/30` 且 `maxSubSteps=10`，物理输出有限并对动作产生响应；临时文件已删除。
- `MMD_TIME_DRIVER_UNIT_OK`、`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`、`BONE_PHYSICS_CREATOR_SMOKE_OK` 与 Rust `cargo test` 7 项全部通过。生产 DLL 未修改，SHA256 保持 `BB2645BD5B2F767A0FDCA4CE27825AA1147C01AC3E5C3D65C44ABCD9B28881D5`；验证均为 headless，未操作 Blender GUI，不递增版本、不打包 zip。完整导入动作与 PmxNLib 的逐帧 oracle 仍是独立验收边界，不能仅凭本轮 host 时间测试宣称所有 VMD 已逐帧 bit-identical。

## 2026-08-16 - MMD Y-up 原生求解基底与 PmxNLib Bullet 2.75 路径对齐（工作树开发）

- 对 `PmxNLib.dll` 的 native world、刚体与 `btGeneric6DofSpringConstraint` 构造路径做函数级反汇编，并用 `PmxPhysicsClass.PmxPhysics` 直接构造 body/joint buffer 作为无 GUI oracle。确认其使用 `btSoftRigidDynamicsWorld`、`btSoftBodyRigidBodyCollisionConfiguration`、`btDbvtBroadphase`、`btSequentialImpulseConstraintSolver`、默认 10 次 solver iterations、`stepSimulation(frameSeconds, 10, 1/60)` 和 `addConstraint(..., false)`。
- RGBA 主误差来自坐标基底而非重力或 stiffness：Blender 输入是 Z-up，PmxNLib/Bullet 原生数据是 Y-up，旧 DLL 却直接在 Blender 的反射基底中求解。线性量需要交换 Y/Z；旋转限制作为轴向量还必须翻转符号并交换 angular lower/upper。Rust DLL 现统一在 MMD Y-up 空间求解 body、bone、joint、gravity、线性限制/弹簧和角限制/弹簧，输出再映回 Blender；没有 RGBA、胸部、臀部或骨名特判。
- C ABI 到 Bullet 改为 quaternion 直传，删除 `Quaternion -> Euler -> Quaternion` 的有损往返。Joint 同步 PmxNLib 语义：线性 spring 仅非零轴启用，角 spring 三轴始终启用，始终执行 `setEquilibriumPoint()`，配置完成后再加入 world。Capsule 改回原生 Y 轴；合法 PMX 刚体参数不再额外 clamp，也不覆盖 Bullet 默认 sleeping thresholds。
- backend 改用 PmxNLib 相同的 soft-rigid world/configuration。vendored Bullet 2.75 的 `BulletSoftBody` 只为 MSVC C++17 构建兼容而把 `ZeroInitialize` 静态零值显式初始化为 `T()`，未改求解公式。PmxNLib 的 ground plane 本轮没有强塞进现有无 ground 开关的预览；实测它会把穿过 Y=0 的既有/测试刚体大幅顶开，应另设可验证选项，不能混入 RGBA 对齐。
- Alicia `Body_Ver4.23.pmx`、重力 `-9.8`、60 Hz、60 帧 headless：历史 PmxNLib oracle 的 RGBA body 5 为 `0.015328934 m / 3.120682°`，本轮 DLL 为 `0.015328781 m / 3.120192°`，残差约 `0.000153 mm / 0.000490°`；上一轮残差约为 `0.893677 mm / 0.904636°`。0.1 导入尺度得到 `0.019161066 m / 3.120192°`，与 0.08 严格保持 1.25 倍位移关系；body 27/31/62 仍为微米级位置对齐。当前标记为“近 bit 级”，不把剩余 float/编译路径差异宣称成逐 bit 相同。
- `cargo test` 7 项通过；Blender 4.4.3 完整 `--background --factory-startup` smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。全部验证均为 headless，未操作桌面 GUI。DLL SHA256 为 `BB2645BD5B2F767A0FDCA4CE27825AA1147C01AC3E5C3D65C44ABCD9B28881D5`；不递增版本、不打包 zip。

## 2026-08-16 - MMD/PMX Editor 全局求解语义、尺度实例与多模型并行审计（源码桥接开发）

- 验证范围从 RGBA 胸部扩展到整套 Rust/C++/Blender adapter：以 `D:\MMD\模型\Alicia\Body\Body_Ver4.23_26.6.20\Body_Ver4.23.pmx` 同时抽样 RGBA 胸部、普通腰/腹刚体与 2 型“物理 + 骨骼”刚体；全部通过 PMX Editor `PmxNLib.dll` native oracle、MMD 9.32/PmxNLib 静态反汇编和 Blender `--background` 执行，不操作桌面 GUI。此前日文读取错误框来自测试 loader，不是模型损坏，oracle 已改为直接构造 native payload。
- 修正时间语义：MMD/PmxNLib 使用 `stepSimulation(frameSeconds, 10, 1/60)`，其中 `10` 是 `maxSubSteps` 追帧容量，不是每帧拆成 10 个短步骤。Rust 固定 Bullet 步长为 `1/60 s`，面板字段改名“最大追帧步数”并默认 `10`；正常 60 FPS 下 `2` 与 `10` 轨迹相同，不再出现旧实现把 `2` 解释成 120 Hz 后导致 RGBA 翘起/失去回弹的问题。
- 重力与几何尺度解耦：面板保持 MMD 用户参数 `-9.8`，DLL 内固定按 MMD 语义换算为 Bullet `-98.0`，不再用 `-7.848 × 12.5` 伪装对齐。ABI 升至 `3`，`mmd_solver_create` 新增每实例 `world_scale`；`0.08` 模型使用 `12.5`，`0.1` 模型使用 `10.0`，多个 solver 不共享全局倍率。Alicia 在两种导入尺度下的 60 帧 MMD 空间轨迹一致，Blender 位移严格按 `0.08:0.1` 比例输出。
- 求解尺度按各 MMD Root 独立保存。面板只显示 `0.08/0.1` 两档：首次登记时从 `empty_display_size` 识别标准导入尺度并直接选中对应数值，无法识别或 Blender 内直接创建的 MMD Root 默认 `0.08`；用户可随时强制改档。强制把实际 `0.1` 模型按 `0.08` 求解会在 MMD/Bullet 空间形成 `1.25x` 尺寸，能够与其它 `0.08` world 交互，但明确属于自定义物理，不再作为原尺寸 bit 级对齐样本。刚体尺寸和 Joint 线性限位读取对象实际 world scale，因此整体缩放在 Apply 前后得到相同物理描述；非均匀或零缩放明确拒绝。
- 整个模型预览改为任意数量 MMD Root 复选集合，不再由单一模型选择器限制。每个模型首次出现时获得持久、单调递增编号并默认选择自己的编号；列表按编号而非名称排序，后导入模型稳定出现在底部。交互编号下拉列出所有现有模型编号，选择同一编号且求解尺度相同的模型合并到一个 world，保留跨模型 collision group/mask 交互，不同求解尺度仍隔离。“重新排序编号”可在停止预览时显式压缩删除模型留下的空号：模型编号按当前顺序重排为连续值，独立模型随自己的新编号迁移，已组队模型则继续指向原组长的新编号，不拆散现有组队关系。修复列表绘制时尺度探测写入 Blender ID 导致第二行开始抛错、后续模型及频率/步数/重力/按钮全部消失的问题：面板 draw 现为只读，且单模型行异常不会中断其余 UI。
- 修复编号服务导致源码 Junction 插件无法注册的问题：Blender 经 Add-ons 启用插件时 `bpy.data` 处于 `_RestrictData`，此前 `register_model_id_service()` 在 `register()` 内立即遍历 `bpy.data.scenes`，触发 `AttributeError`，表现为插件未加载而非 Junction 丢失。首次场景编号扫描现改为注册完成后的 deferred timer，load/depsgraph handlers 保持不变；卸载时同步注销尚未执行的 timer。真实 Blender 4.4 addons Junction 路径执行 `addon_enable`、模块路径断言和用户偏好保存均通过，模块最终解析到主工作区源码而非 `mmd-bit-align` worktree。
- 多模型活动列表继续保留每行右侧的循环箭头 Reset 和关闭按钮；主操作栏增加唯一的“重置全部”，按 world 各重建一次 solver 并恢复全部启动快照，共享同一 world 的交互模型不会被重复重置。活动列表标题行不重复放全局 Reset，并移除其中第二个“停止全部”；主操作栏固定按“启动已勾选模型 → 停止全部 → 重置全部”排列。headless 回归验证三个独立 world 的 solver 均被替换、活动 session 保持运行，并在停止与活动两种绘制状态下断言两个全局 operator 各只出现一次且顺序正确。
- 针对 Alicia 复杂 RGBA 约束网络复核了上一轮 Root 跟随改法：从当前 Blender 刚体/Joint 状态重建 solver 会引入不一致的约束初态，实际拖动 Root 时可能立即炸开，因此撤回 Root 变换侦测与运行中自动重建，不改 DLL、ABI 或求解参数，恢复此前“预览运行时可直接拖动 MMD Root”的路径。保留 Reset/异常恢复的 Root 相对快照：恢复刚体与 Joint 时应用“当前 Root × 启动 Root 逆矩阵”，因此模型移动后执行 Reset 会在当前位置恢复初始物理姿态，而非跳回旧世界坐标。最终只锁定正在预览模型的“交互编号”下拉框；停止该模型后方可换组并重新启动，避免运行中的 UI 编号与既有 Bullet world 脱节。求解尺度继续保持原先可编辑行为。
- 多 world 的 Blender RNA 读取和结果写回仍在主线程；纯 DLL `step` 由长期复用的 `ThreadPoolExecutor` 按 world 并行，Bullet 2.75 单个 world 内仍保持原生顺序。Alicia 120 帧纯求解 headless 基准：1 world 因线程调度为顺序的 `0.82x`，2 world 为 `1.81x`，4 world 为 `3.23x`；顺序/并行输出逐字节一致。生产 timer 只在多 world 时进入 worker pool，同一交互组只提交一次 step。
- 按 MMD 通用路径统一 Bullet 语义，而非加入 RGBA/胸部/臀部特判：Bullet 2.75、10 次 solver iterations、`m_additionalDamping=false`、`addConstraint(..., false)`、仅正刚度轴启用 spring、存在 spring 时设置 equilibrium、`setSynchronizeAllMotionStates(true)`、直接读取 rigid body world transform，并在 Windows 构建定义 `WIN32` 进入 Bullet 2.75 SSE 路径。0/1/2 型骨骼绑定、碰撞 mask、capsule Z 轴和 Joint 输入顺序均纳入审计。
- bit 级状态仍未达成：同 Alicia PMX、MMD 参数 `-9.8`（oracle 内部 `-98.0`）、60 Hz、60 帧，PMX Editor RGBA body 5 位移 `0.015328934 m`、旋转 `3.120682°`；当前 DLL 为 `0.016222611 m`、`4.025318°`，残差约 `0.893677 mm / 0.904636°`。普通 body 27/31/62 仍保持微米级位置对齐；iterations 5/8/9/11/12/20 的扫描均不能同时命中 RGBA 位移和旋转，故没有用全局迭代数或重力补偿过拟合。剩余工作继续定位 PmxNLib/MMD 的 Bullet 2.75 fork 或约束构造数值路径，本轮不宣称 perfect/bit-exact。
- Rust 单元测试现为 6 项，新增 `0.08/0.1` 独立实例 MMD 空间一致性；Blender 4.4.3 smoke 覆盖三个模型、持久编号、`#1/#3/#4 -> #1/#2/#3` 空号压缩、独立与已组队两种关系迁移、完整列表与控制区绘制、三个并行 world、同编号同尺度合并、同编号异尺度隔离、强制改档后合并、Apply Scale 前后描述一致、逐项/全部停止及异常恢复。另以 Alicia `body4.pmx` + `Body_Ver4.23.pmx` 实际双导入执行独立 headless UI 探针，确认两个模型分别显示为 `#1/#2`、均识别为 `0.08`、各自默认独立，频率/追帧步数/重力/启动按钮均存在；混合尺度探针进一步确认实际按 `0.08/0.1` 导入时分别识别为 `0.08/0.1`，同编号仍隔离，手动把后者切到 `0.08` 后显示为自定义 `0.08 ×12.5`。完整 headless smoke 通过；DLL 未改动，SHA256 仍为 `7A7DC27B6387A9CB47FA55DB007937F943014FDFD73AC007103B69FA696F778E`。继续使用源码 Junction，不递增版本、不打包 zip，真实 GUI 视觉验收按用户要求未执行。

## 2026-08-16 - 稳定中长裙实测参数与自适应四位数值栏（源码桥接开发）

- 将用户在实际高抬腿碰撞中确认稳定的三页参数固化进内置“稳定中长裙”：盒体深度 `0.15 -> 0.50`、质量 `2.00 -> 0.40`、双阻尼 `0.995 -> 0.99`、碰撞组显示 `6` 且屏蔽同组；纵 Joint 只补间 X 旋转 `±8° -> ±18°`；横 Joint 移动下限保持全零，仅允许 X 上限由 `0.02 -> 0.03`，用单向伸长释放抬腿拉扯而不允许静态收缩塌落。横向 X 移动弹簧为 `120 -> 40`，X 旋转限制为 `±10° -> ±18°`，X 旋转弹簧为 `0.8 -> 0.25`，其余数值按三张面板截图保存。
- 刚体、纵 Joint、横 Joint 的全部浮点编辑栏改为自适应文本数值层：至少显示两位小数，按实际需要最多显示四位并去掉无意义末尾零，例如 `2.00`、`0.99`、`0.995`、`0.1235`。角度栏继续以度数和 `°` 展示；输入会写回原 Float/FloatVector RNA，预设、参数应用和物理计算仍只读取原数值，不保存显示代理字段。
- Blender 4.4.3 headless smoke 更新为逐项断言三页内置参数、单向横向移动限制、碰撞组 mask、全部底层 RNA 四位最大精度，以及自适应格式化与写回；继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-16 - 碰撞组显示编号与同组屏蔽修正（源码桥接开发）

- 定位到近期刚体覆盖率提高后物理明显抖动、卡刚体的直接原因：代理的 165 个刚体内部碰撞组均为索引 `5`，但已保存的不碰撞掩码勾在索引 `4`。旧面板把碰撞组原始索引显示为 `0–15`，同时把不碰撞组按钮显示为 `1–16`；用户按界面看到的“碰撞组 5”勾选按钮“5”时，实际写入的是相邻内部组 `4`，同组自碰撞并未关闭。
- 生成设定中的碰撞组改为统一显示 `1–16`，写入时仍转换回 MMD 内部 `0–15`，不改变文件格式或 runtime ABI。新增“屏蔽同组碰撞”派生开关，始终读写当前内部碰撞组对应的正确 mask 位；活动刚体检查器继续展示原始 RNA，但标签明确为“内部 0–15”，避免混用两套编号。
- 使用同一个 `07.blend`、同一个生产 DLL 和同一组 165 个代理刚体执行 180 tick A/B：原保存 mask 的末段平均位移为 `0.00277614`、平均加速度为 `0.00302425`；只补上真实同组 mask 后分别降为 `8.93e-7` 与 `1.26e-6`。生产 DLL SHA256 仍为 `7FBF0B5560646700ED6DF879406A85A6560A0DAE6503354CEE7F13985165FFDF`，与 Git `HEAD` 跟踪对象完全一致，本轮未修改求解器。完整 Blender 4.4.3 headless smoke 覆盖显示编号换算、同组 mask 派生开关和刚体页实际绘制；继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-16 - 勾选刚体与 Joint 镜像创建/同步（源码桥接开发）

- MMD 查看器刚体页和 Joint 页新增只面向勾选源项的“创建镜像”与“同步镜像”。支持 `.L/.R`、`_L/_R`、`左/右`三类既有侧向标识；没有侧向标识的刚体或 Joint 使用 `_M` 后缀创建复制镜像，并可由原名与 `_M` 在后续双向识别为同一镜像组。无侧向骨名的镜像刚体继续绑定原骨骼，明确侧向骨名则必须解析到对应镜像骨骼。
- 镜像变换统一以 MMD Armature 局部 X=0 为对称面执行矩阵共轭，不直接复制/取反 Euler。Joint 移动限制按极向量换算，X 下上限变号并交换；旋转限制按轴向量换算，Y/Z 下上限变号并交换；X 旋转保持，弹簧强度保持。刚体形状、尺寸、类型、碰撞及动力学参数保持源值，骨骼绑定改到镜像骨骼。
- “同时处理关联 Joint”放在刚体页，默认启用。关联范围以 Joint 的刚体 B 为准，仅处理 B 属于勾选源刚体的 Joint；镜像 B 指向勾选刚体镜像体，A 优先使用已存在的左右或 `_M` 镜像刚体，无侧向标识且没有镜像体时共用原 A。不会创建未勾选的另一端刚体，也不会额外生成跨左右组的中间横 Joint；已有横 Joint 只按原 A/B 拓扑镜像。
- 修复同一对镜像骨骼已有其它刚体时误报“镜像已存在”的问题。旧识别只按镜像骨骼绑定挑选候选，例如已有`左足/右足`时，手工复制并命名的`左足2`会把普通`右足`误认为目标；现在目标必须同时匹配镜像骨骼与换算后的主要 MMD 名称，因而会正确新建`右足2`。回归在镜像骨骼上预先注入名称不匹配的干扰刚体，确认不会占用目标。
- 独立 Blender 4.4.3 骨骼物理 smoke 覆盖左右刚体和关联 Joint 创建、矩阵位置反射、Joint 线性/角度上下限换算、同步更新、无侧向刚体 `_M` 创建与回识别、锚定 A 在无 `_M` 时共用及存在 `_M` 时改接、Joint 页独立创建/同步。完整 headless smoke 同时验证两页按钮注册与绘制。继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-16 - 自动刚体搭接覆盖率（源码桥接开发）

- 修正自动盒体尺寸故意留缝造成的碰撞空洞。旧公式的横向全宽只是左右间距平均值的 `96%`，纵向总高只是骨段长的 `96%`，因此在规则网格上也必然有约 `4%` 缝隙，不等宽、弯曲或快速高抬腿时更明显。
- 自动横向基准改取到左右相邻列的较大距离，盒体半宽为其 `55%`，使相邻单元形成约 `10%` 搭接；纵向总高改为骨段长的 `110%`，上下刚体跨过共享 Joint 边界；自动厚度由局部较小跨度的 `16%` 提高到 `20%`。刚体中心、旋转、骨骼绑定与 Joint 位置不变，以尺寸搭接而非中心错位实现“交错”，避免破坏物理链拓扑。
- 调整只影响宽度/高度/深度比例为 `0` 的自动计算；非 `0` 手工值及其补间不变。回归新增不等列距的最大跨度、横向半宽、纵向半高和厚度公式断言。继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-16 - 当前代理物理完整重建（源码桥接开发）

- 保持按钮名称“生成 MMD 刚体和 Joint”不变，并扩展为创建/重建共用入口：当前代理尚无物理时正常创建；已有物理时按面板当前参数重新生成完整刚体和 Joint 图，从而补齐旧工程缺失的第一圈横 Joint 等不存在对象。悬停描述明确说明重建语义，完成报告区分“已创建”与“已重建”。
- 重建采用先创建新对象、成功后再删除当前代理旧对象的替换顺序；若新建过程失败，只清理本轮新对象并保留原物理。删除范围严格来自当前代理稳定关联 ID，Joint 先于刚体删除，不触及其它代理物理。
- 完整 Blender 4.4.3 headless smoke 新增重复点击生成按钮的回归：验证对象没有叠加、旧对象标记被替换、第一层横 Joint 存在，且另一代理的刚体保持原对象与原参数。`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK` 通过；继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-15 - 开放代理表面拟合、窄控制带与双侧镜像（源码桥接开发）

- 补齐第一圈刚体之间缺失的横 Joint。根因是横 Joint 生成循环从 `row=1` 开始，主动跳过了第 `0` 层；现在覆盖 `0..末层` 的全部刚体段，横 Joint 的参数补间也改按刚体层深计算，使新增第一圈取得起始参数、最末圈取得末端参数，不产生负补间系数。闭合、开放、左右分组及“连接左右”继续沿用原列配对边界。
- 缩短新建 Joint 名称并统一刚体 B 语义：纵 Joint 与顶层锚定 Joint 的 MMD 日文/英文名称直接取刚体 B 对应字段，横 Joint 在刚体 B 名称后追加 `_H` 以避免和纵向/锚定 Joint 重名；不再把代理前缀、`JOINT_HORIZONTAL`、列号和层号重复拼入名称。Joint 查看页新增“同步刚体 B 名称到 Joint”，分别提供“同步勾选”和“同步全部”，可批量修正已有长名称；缺少刚体 B 的 Joint 明确跳过。
- 刚体和 Joint 查看页补齐与骨骼页对应的“从 3D 视图同步选中刚体/Joint”。两者读取当前 Object selection，刷新查看器后严格以视图选中集覆盖列表勾选，并同步蓝色活动行；当前代理过滤隐藏了部分选中对象时报告匹配数量。回归覆盖第一圈数量、全层横 Joint 位置和补间、三类 Joint 新建命名、勾选/全部批量改名，以及刚体/Joint 双向选择同步。完整 headless smoke 通过。继续使用源码 Junction，本轮不递增版本、不打包 zip。
- 修正横 Joint 与纵 Joint 落在同一骨骼节点高度的问题。纵 Joint 继续位于上下刚体交界节点；横 Joint 改为左右相邻两段刚体中心的平均位置，因此自然落在该段半层高度并与纵 Joint 交错。新建物理、普通位置/旋转同步和“应用参数到当前代理”统一使用该位置定义；已有同层横 Joint 点击“应用参数到当前代理”即可自动纠正，同时按该功能原有职责重算刚体尺寸及全部物理参数。回归分别覆盖初次生成、旧位置注入后的参数应用纠正，以及代理变形后的普通同步，完整 headless smoke 通过。继续使用源码 Junction，本轮不递增版本、不打包 zip。
- 根据实际前后对比纠正物理同步职责：编辑代理后的手工同步和 `EDIT/SCULPT -> OBJECT` 自动同步不再调用 `_rigid_size()`，也不再写入 `mmd_rigid.size`。同步严格只更新刚体位置/旋转及 Joint 位置/旋转；刚体形状、物理类型、尺寸、质量、阻尼、碰撞和全部 Joint 参数保持原值。形状、类型和尺寸重算只保留在用户明确点击“应用参数到当前代理”的路径。
- 回归把原“代理变形后刚体尺寸应改变”断言反转为尺寸、shape、type 必须逐项不变，并同时断言附近刚体和纵 Joint 的位置、旋转确实随代理变化；任意骨名头发接管回归也分别验证手工同步和模式退出自动同步前后尺寸、shape、type 不变，而明确应用面板参数后仍允许重算并在后续同步中保持。面板提示与 README 同步修正，不再把自动尺寸描述为普通同步行为。
- 修复从现有骨骼恢复/新建代理后只同步骨骼、刚体与 Joint 报 `0/0` 的关联缺口。根因是反建代理只保存了真实骨名，没有给模型中早已存在的 MMD 物理对象写入代理 ID、列、层和角色；自动同步虽正常触发，但物理作用域查询不到任何对象。恢复时现在按真实骨名接管已有绑定刚体，并根据 Joint 两端识别同列相邻层的纵 Joint、相邻列同层的横 Joint及顶骨父刚体锚定 Joint；已存在的反建代理也会在首次手工或自动同步时惰性补齐关联，无需重建物理。
- 接管只处理当前 MMD 模型、当前代理精确骨名范围内且未属于其它代理的物理对象，不抢占其它代理；横 Joint 同时保存实际 following column。恢复完成报告会直接显示已关联刚体和 Joint 数量。基本页明确区分：同步只更新刚体与 Joint 的位置、旋转，不覆盖形状、类型、尺寸、动力学或 Joint 参数；刚体/纵 Joint/横 Joint 页修改后通过底部“应用参数到当前代理”写回接管对象。
- 回归先删除任意骨名头发代理全部物理关联元数据，验证手工同步可自动重新接管并更新 `8` 个刚体、`7` 个 Joint；再次删除关联后模拟 `SCULPT -> OBJECT` 模式边沿，验证自动同步同样补齐关联并移动刚体。随后修改面板质量、纵 Joint 旋转弹簧和横 Joint 旋转弹簧并执行“应用参数”，断言全部接管对象更新；再次同步变换后这些参数保持不变。完整 headless smoke 通过。继续使用源码 Junction，本轮不递增版本、不打包 zip。
- 重新设计“从勾选骨骼恢复或新建代理”的识别边界：保留旧式 `名称_Cxx_Rxx` 编号解析，同时允许任意统一前缀骨名。任意名称不再猜测列号，而是从 Armature 的真实父子关系提取不分叉纵链，以每根 Rest Bone 的 head/tail 重建控制列，并按根骨空间位置排序；`.L/.R` 与 `_L/_R` 都只作为侧向元数据。分叉选择会明确拒绝，避免把共享骨段重复映射到多列。
- 打开恢复区新增“连接左右”开关，默认关闭以保持原有左右裙摆边界。关闭时左右骨链在同一个代理 Mesh 内分别成面且中间不生成面或横 Joint；开启时所有左右列按空间顺序组成一个连续面，支持头发等必须跨中间连接的多列结构。闭合恢复不受该开关影响，仍按每个逻辑组分别闭环。
- 恢复代理新增逐段真实骨名元数据，骨骼同步、权重重算、刚体及 Joint 创建统一优先读取该映射，不再要求后续骨名符合 `_Cxx_Rxx`。headless 回归以 `后发A1.L/A2.L`、`后发B1_L/B2_L` 及对应右侧骨链覆盖左右分离、连接中缝、同 Mesh 原地恢复、`.L/.R` 与 `_L/_R` 混合识别、精确骨名同步和跨中间横 Joint；完整 smoke 与独立骨骼物理 smoke 均通过。继续使用源码 Junction，本轮不递增版本、不打包 zip。
- “补全勾选”“补全全部”及单项“补全当前空缺名称”统一加入侧向名称转换：Blender 骨骼名尾部 `.L/.R` 或 `_L/_R` 都视为镜像标识；MMD 日文名称写为`左/右 + 基础名`，英文名称写为`基础名_L/_R`，普通名称仍原样写入两个字段。只补空字段、不覆盖已有内容的边界不变。headless 回归覆盖 CHECKED 处理 `.R`、ALL 处理 `_L`、未勾选骨骼在 CHECKED 中保持空白，以及已有日文名称不被覆盖。
- MMD 查看器骨骼页的“快速选组”新增“已勾选骨骼及子级”：以当前所有已勾选骨骼为根，按各自 Armature 的真实父子层级递归勾选全部子孙骨骼；支持同时勾选多个不同分支，保留原有勾选，不再依赖蓝色活动行。无勾选时明确提示先勾选骨骼。headless 回归使用两个不同深度的骨链根，并把活动行故意指向第三根无关骨骼，断言最终勾选集合严格等于两个根及其全部子级。
- 根因确认后撤回前两轮全部推测性补丁，只保留 deferred registration 修复：蓝线恢复为仅当代理 Mesh 本身是 active object 且处于 Edit/Sculpt Mode 时绘制，恢复 topology signature 检查、2 px 半透明颜色和正常深度行为；不再从面板当前代理回退绘制，不在 Object Mode 显示。自动同步恢复直接调用 `sync_proxy_bones()`，删除 `VIEW_3D` context override、持久成功状态文案和相关测试；draw handler 注册恢复原有“仅缺失时添加”语义。
- 深度检查真实 Blender 4.4 用户配置启动链后，确认前两轮没有命中共同根因：`register_services()` 在 Blender add-on 受限注册阶段同步调用 `_load_proxy_identity()`，此时 `bpy.data` 是 `_RestrictData`，访问 `bpy.data.objects` 抛出 `AttributeError`。异常发生在 mode timer 与 `SpaceView3D` draw handler 注册之前；Panel/Class 已在此前完成注册，所以 UI 正常出现，但蓝线与自动同步两个后台服务均从未启动。现已移除注册阶段的数据扫描，改为 0.1 秒 deferred initialization；遇到受限数据会继续延迟，数据可用后才恢复代理身份。`load_post` 继续负责文件载入后的恢复。
- 使用真实 Blender 4.4 用户 profile 验证桥接：运行时模块路径明确来自 `C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\scripts\addons\mmd_skirt_proxy_creator` Junction，插件为 enabled，模式 timer 与 deferred initialization timer 均成功注册，启动输出不再包含 `_RestrictData` traceback。面板新增仅在异常时显示的服务自检：若 draw handler 或自动同步 timer 未注册，会明确显示“蓝线绘制服务未注册”或“自动同步服务未注册”，不再依赖用户从无效果反推注册失败。headless 回归新增受限 `bpy.data` 重试断言。
- 按真实 Sculpt 反馈撤销前两版 depsgraph/坐标签名 watchdog 方案，改为最直接的模式边沿触发：只记录每个代理上一次模式；一旦观察到 `EDIT/SCULPT -> OBJECT`，无条件立即调用与手工按钮相同的 `sync_proxy_bones()`，若启用物理同步再紧接着同步刚体与 Joint。不存在坐标比较、dirty 判定或等待 Blender 上报雕刻更新，因此每次退出代理编辑/雕刻都会主动提交一次。自动同步异常仍直接显示在代理编辑区。headless 回归真实进入 Sculpt Mode、移动中心控制点，断言 Sculpt 期间骨骼不动、退出 Object Mode 后单次模式检测即更新对应骨骼。
- 调整 MMD 查看器骨骼页操作顺序：将“从 3D 视图同步选中骨骼”从下方物理创建模块顶部移到“将勾选项选入 Blender”正下方，使“列表勾选 → 3D 选骨”与“3D 选骨 → 列表勾选”两个互逆入口紧邻显示；Operator 行为不变。
- 修复开放代理尤其是“圆周方向 = 1”时整条代理远离目标选区的问题。根因是开放模式复用了闭合裙面的极坐标圆柱拟合，并以单侧开放布片自身的包围中心冒充圆周轴心；单列随后取推算角跨度中点，得到的列位置并不在选中表面。
- 闭合模式保持原圆柱拟合不变；开放模式改为在本地 XY 平面计算选区主轴，沿主轴分列，并按横向位置与高度从邻近选中顶点加权采样实际 XY。单列使用选区主轴中位位置，因此骨链会贴合选区几何中线并可随表面弯曲，不再生成远处的推算半径直线。
- 根据连续真实界面反馈撤销变化不明显的“局部拉普拉斯平滑 + 仅修最后一点”方案。开放代理的每列原始 XY 轨迹现在整体拟合为顶部精确锚定的三次曲线；最后一个原始采样权重降为 `0.05`、倒数第二个降为 `0.5`，避免底部分叉或不对称尖角凭高杠杆继续拉偏整条末端。该处理同时作用于单列和多列开放代理，闭合代理不变。
- 拟合结果若可能超出选区 XY 范围，会以顶部锚点为中心统一缩放整条曲线，而不是逐点裁切造成新折角；最终末点再沿全局拟合轨迹的末端切线延伸到原高度，越界时沿同一方向等比缩短。顶部位置、连续曲线形状、末端方向和选区范围四个约束同时保留。
- 修复单列代理 Sculpt Mode 无法变形：根因是旧单列 Mesh 只有边、没有 polygon，而 Blender 雕刻只作用于面。单列现在保持中心控制点为前 `N` 个顶点，并在其周围生成 `±X/±Y` 四条极窄侧轨及四组纵向 quad，形成从任意视角都可命中的十字控制带；骨骼同步仍只读取中心 `surface_proxy_vertex_map`，所以物理拓扑仍是一列。根据实际使用反馈，控制带全宽由中位骨段长度的 `18%` 收窄为 `9%`，写入 `surface_proxy_sculpt_width`。
- 新增由名称触发的打开代理镜像模式：名称以`左`或`右`开头时，去掉该方向字作为实际基础名，并在 Mesh 局部 X=0 的另一侧识别对应布料区域。两侧控制带作为同一个代理 Mesh 内的两个不相连逻辑组一次创建，既不会在左右之间补面或生成横 Joint；完全对称网格会自动启用 Mesh X Mirror 编辑，非对称网格保持关闭以免错误配对。闭合代理继续保持原行为。
- 镜像骨链采用三套明确命名：Blender 骨骼为基础骨名加 `.L/.R`，MMD 日文名为`左/右`加基础骨名，MMD 英文名为基础骨名加 `_L/_R`。精确镜像网格直接反射已拟合控制链以保证左右位置严格一致；非精确镜像网格对另一侧实际顶点独立执行同一套拟合。两侧权重始终分别从各自原网格顶点计算，绝不把一侧权重直接复制到另一侧；重新算权重、骨骼同步、刚体和 Joint 更新也按左右逻辑组隔离。
- MMD 查看器骨骼页新增“从勾选骨骼恢复或新建代理”：通过快速前缀勾选同一 Armature 中名称符合 `前缀_Cxx_Rxx` 或 `前缀_Cxx_Rxx.L/.R` 的完整骨链后，可直接由 Rest Bone 的 head/tail 重建控制网格。`前缀_Surface` 已存在时原地替换 Mesh 数据并保留对象身份及物理关联 ID，不存在时新建；结果立即写回完整代理元数据，可继续同步骨骼、重算权重及生成物理。
- 左右后缀与打开/闭合拓扑改为完全独立。查看器恢复区直接提供“闭合/打开”选择；无左右后缀的裙骨可恢复为闭合面，带 `.L/.R` 的宽大桶袖等也可恢复成同一 Mesh 内两个分别闭合的逻辑组。两侧之间不补面、不建横 Joint；几何严格镜像时自动启用 Mesh X Mirror，否则保留同 Mesh 双侧编辑但关闭错误的自动镜像配对。
- 代理身份恢复不再要求 Mesh 顶点数必须恰好等于骨链控制点数，改为允许附加控制面顶点，并继续按骨端点最近匹配唯一中心点；拓扑签名仍覆盖全部控制带顶点与边，Dynamic Topology 改拓扑仍会被拒绝。面板同步改为提示单列可雕刻且必须关闭 Dynamic Topology。
- Blender 4.4.3 headless smoke 使用整体偏离原点且逐高度带交替褶皱的弯曲开放布片，分别覆盖四列开放面与 `12` 层单列开放控制带；逐点断言中心线留在选区 XY 范围内、最大离散曲率低于 `0.08`、末端方向点积大于 `0.9999`，并断言单列生成 `5N` 个顶点、`4(N-1)` 个面、控制带宽度低于中位骨段长度的 `10%`、可以进入 Sculpt Mode，中心点移动后仍只同步 `N-1` 根骨骼。镜像回归分别覆盖完全对称与非对称双侧布片，断言同 Mesh 双逻辑组、三套左右名称、精确反射/独立拟合分支、左右权重隔离，以及两条单列之间不创建横 Joint。骨骼反建回归覆盖现有普通闭合裙代理原地恢复，以及仅有 `.L/.R` 骨链时新建两个独立闭合桶袖代理组；断言对象身份保持、闭合面数量、X Mirror、左右面隔离和横 Joint 只在各自闭环内连接。另注入偏移 `0.65/-0.45` 的极端末点，断言全局拟合结果与该异常采样至少分离 `0.25`。完整回归通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`，独立骨骼/物理回归继续通过 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=4 joints=3 ordered=3`。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip、不修改 Rust DLL。

## 2026-08-15 - 三模块统一横向 Tab 工作区（源码桥接开发）

- 将 N 面板中原本各自折叠的“裙面代理创建器”“MMD 骨骼 / 刚体 / Joint 查看器”“MMD 物理预览”合并为单一顶层 `MMD 代理工具` Panel，顶部使用与 Velo Tools 一致的 `row.prop(..., expand=True)` 横向 Tab 导航。
- 新增 Scene 级 `workspace_tab`，提供“代理创建 / MMD 查看器 / 物理预览”三个页面并保存当前选择。切换时只调用对应模块原有的 `draw_physics_settings`、`draw_browser` 或 `draw_preview`，模块逻辑、Operator、Rust runtime 和内部“基本 / 刚体 / 纵 Joint / 横 Joint”二级页签均不改动。
- 删除另外两个独立 Panel 的注册，避免 N 面板同时保留重复折叠标题。完整 Blender 4.4.3 headless smoke 新增三页面独占绘制断言，并继续通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`。本轮不修改 Rust DLL、不递增版本、不打包 zip。

## 2026-08-15 - 私有 GitHub 仓库与本地 Git 基线

- 将独立项目根目录初始化为 Git 仓库，默认分支固定为 `main`；本地提交身份使用当前 GitHub 账号 `visaokc` 及其 GitHub noreply 地址，避免写入私人邮箱。
- 新增根 `.gitignore`：排除 Rust `target/`（约 278 MiB 构建缓存）、Python cache、Blender 工作文件、临时日志，以及本地 `_archive/` 中的历史 zip 与源码备份；保留插件源码、测试、Rust crate、vendored Bullet 2.75 源码、生产 DLL、README 与第三方声明。
- GitHub 远端使用私有仓库 `https://github.com/visaokc/MMD-Skirt-Proxy-Creator`，本地 remote 命名为 `origin`，首次提交推送到 `main`。本轮只建立版本管理与远端基线，不改变插件版本号、不重新打包 zip。

## 2026-08-15 - 清空全部用户姿态时原地重置 solver（源码桥接开发）

- 根据真实 GUI 反馈撤销“接受当前清理姿态、分别重算刚体/Joint”的复杂恢复分支。预览启动时现在一次性快照整个 Armature 的全部 Pose Bone，以及 MMD 模型的全部刚体和全部 Joint 世界矩阵；自动重置、手工重置、tick 异常和最终停止统一使用同一份启动快照。
- 再次根据真实截图定位到先前 headless 未覆盖的 Blender RNA 生命周期错误：`_restore_start_snapshot()` 在 `self.armature.pose` 抛出 `ReferenceError: StructRNA of type Object has been removed`。清空姿态/撤销系统可能重建 Blender 数据块，而旧 session 长期保存的 Armature、刚体和 Joint Python 引用随即失效；因此不是快照数值错误，而是恢复代码根本访问不到当前对象。
- 启动快照现在以 Armature、刚体和 Joint 的稳定名称作为权威身份，只保存普通矩阵值，不再以 Blender Object 引用作为快照键。每个 timer tick、手工重置、异常恢复和停止恢复都会从当前 `bpy.data.objects` 重新解析 root、Armature、全部 session 刚体与 Joint；一旦发现 RNA 实例已被替换，立即恢复启动快照并重建 solver。
- `_timer_tick` 遇到任何步进异常都会先恢复完整启动快照，再丢弃旧 solver 并创建新 solver；即使 solver 重建本身暂时失败，也不再调用 `stop_preview()`，而是保留 `_ACTIVE_SESSION`、timer 和 `preview_running`，下一 tick 继续重试。因此 Stop/Reset 按钮不会再因异常恢复失败变灰。
- 面板新增明确的运行状态文本：正常运行、自动姿态重置、异常后快照恢复或恢复失败重试都会直接显示。手工“重置物理预览”也固定恢复启动快照，不再把当前错位状态当成新的基准。
- 修复本条初版的 UI 回归：误把“开始物理预览”Operator 的参数改名为 `_context`，函数体仍调用 `start_preview(context)`，导致真实按钮直接抛出 `NameError`。此前 smoke 直接调用 runtime API，所以没有覆盖到 UI 边界。现已恢复 Start Operator 的 `context` 参数、只把不使用上下文的 Reset Operator 标为 `_context`，并将回归改为通过 `bpy.ops.surface_proxy.start_mmd_physics_preview/reset_mmd_physics_preview/stop_mmd_physics_preview` 执行全部三个实际按钮。
- `pose.user_transforms_clear(only_selected=False)` 的大范围姿态跳变仍作为自动恢复触发，但触发后的行为已简化为“恢复启动快照并重新开始物理”，不再保留清理过程中产生的局部中间状态。0 型、1 型、2 型刚体与全部 Joint 从同一个快照时刻重新建立世界。
- 完整 smoke 故意同时篡改骨骼、刚体、Joint 并注入 tick 异常，逐矩阵断言三类快照全部恢复；又注入 solver 重建失败，断言 session、timer 和运行标志仍保留，随后可成功重建并继续步进。结果通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`。
- 使用截图对应的 `06.blend` 只读 headless 精确执行 `pose.user_transforms_clear(only_selected=False)`，随后重新载入同一 `.blend` 主数据以强制让旧 Armature/刚体 RNA 引用失效；session 成功按名称重新绑定当前对象、恢复快照、继续 tick，并可正常执行停止恢复，通过 `RNA_REBIND_SNAPSHOT_OK`。完整 smoke 另以失效占位引用覆盖 root/Armature/刚体/Joint，断言 timer 自动重新绑定并替换 solver。未保存实际工程，不修改 Rust DLL，不递增版本、不打包 zip。

## 2026-08-14 - 预览期间清空骨骼变换后的完整姿态恢复（源码桥接开发）

- 修复物理预览运行中执行 Blender“清空骨骼变换”后角色肢体拉飞且停止也无法恢复的问题。根因是运行时只保存了被动态刚体直接驱动骨骼的 `matrix_basis`；被清空的操作骨、身体父骨、IK 骨或其它非动态骨不在快照中，停止时继续保留清零状态，整条层级因此永久错位。
- `PreviewSession` 现在在修改骨骼连接或创建 solver 之前快照当前 MMD Armature 的全部 Pose Bone。逐帧求解仍只重置动态驱动骨骼，保留既有的动画/操作骨带动物理能力；但停止、重置、异常退出和构造失败恢复都会写回完整启动姿态。刚体、Joint 矩阵及 `use_connect` 恢复路径不变。
- Blender 4.4.3 完整 headless 回归不再在停止前手工还原运动中的静态锚点骨，而是让停止路径恢复它，并断言动态骨、非动态父骨和无关刚体均返回启动值。继续使用源码 Junction；等待用户 UI 验收，不递增版本、不打包 zip，不修改 Rust DLL。

## 2026-08-14 - PMX 实际顺序与查看器多选块排序（源码桥接开发）

- 修复骨骼“上移/下移”看似成功但列表不变：截图中的 `006 下半身` 紧邻 `005 腰` 父骨和自己的 `007/008` 子骨，旧实现只移动单个父骨，随后被 `realign_bone_ids` 按 PMX 层级规则还原，却仍报告成功。现在移动父骨会自动携带全部非 shadow 子级作为稳定分支；例如“下半身”下移会让整条下半身分支越过下一个独立分支。若上移会越过自己的父骨，操作保持原顺序并明确报告依赖限制。
- 为 MMD 骨骼/刚体/Joint 查看器增加真实顺序编号和“PMX 实际顺序”操作区。查看器的复选框现在承担多选范围，不依赖 Blender `UIList` 不支持的 Shift/Ctrl 行多选；多个勾选项会保持彼此相对顺序，作为一个稳定块执行置顶、上移、下移、置底，或插到蓝色活动行前后。
- 排序直接修改 `mmd_tools` 实际导出键，而不是伪造查看器显示顺序：骨骼修改 `mmd_bone.bone_id`，并通过 `FnModel.shift_bone_id` / `realign_bone_ids` 同步 Bone Morph、附加变换等 ID 引用及父子依赖；刚体和 Joint 使用官方 `MoveObject.normalize_indices` 写入三位对象名前缀，因为 PMX exporter 正是按 Blender 对象名排序。MMD 日/英文名称保持不变。
- 查看器刷新改为与当前 PMX exporter 相同的排序语义：骨骼按有效 `bone_id` 后接名称，刚体与 Joint 按对象名；左侧显示零基实际索引。即使启用当前代理过滤，排序仍作用于整个 PMX 模型，避免把局部显示顺序误当成导出顺序。
- 扩展 Blender 4.4.3 headless 回归，覆盖父骨携带完整子链越过兄弟骨、两个非连续刚体组成稳定块插入、Joint 插入、重命名后勾选/活动行恢复及查看器索引；结果为 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=4 joints=3 ordered=3`。原完整回归继续通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`。继续使用源码 Junction；等待用户 UI 验收，不递增版本、不打包 zip。

## 2026-08-14 - 3D 选骨同步与 PMXEditor 式四模式物理创建（源码桥接开发）

- 修正上一轮只提交设计、没有实际交付 UI 的问题。骨骼查看页现已直接显示“从 3D 视图同步选中骨骼”按钮，支持当前 MMD Armature 的 Edit Mode 与 Pose Mode；同步会更新查看器勾选和活动行，不切换骨架模式，也不更改 3D 视图选骨。
- 新增独立 `bone_physics_creator/` 模块，包含选择桥接、刚体/Joint builder 与 UI。创建 Operator 直接读取执行瞬间的 3D 选骨，不依赖可能过期的查看器勾选；结束后恢复原 Edit/Pose 模式、活动骨骼和多选状态，模块不依赖裙摆代理拓扑或 Rust 预览器，便于后续拆成独立插件。
- 实现 PMXEditor 式四个入口：骨骼追踪刚体固定创建 type 0；物理刚体支持 type 1/type 2；基础 Joint 使用已有绑定刚体按直接父子骨骼连接；刚体 + 连接 Joint 创建或复用同类型刚体后连接父子 Joint。刚体按 Rest Pose 骨骼头尾生成，Joint 位于子骨头，分支骨链不按点击顺序错误串联；已有相同刚体对 Joint 会跳过。
- 新建刚体与 Joint 的 MMD 日文名、英文名统一直接取其对应骨骼名并截到最多 `16` 个字符，不再生成 `J_父骨_子骨` 长名称。创建后会主动清空查看器旧搜索、关闭只显示代理的范围过滤、切换到本次结果的刚体或 Joint 页，刷新并勾选新对象；修复“对象已创建但刷新后列表仍为空”的问题，该现象的直接原因是旧搜索文字和代理范围过滤仍然生效。
- 新增独立 Blender 4.4.3 headless 回归，覆盖 Pose/Edit 双模式同步、四个创建入口、type 0/1/2、父子 Joint、模式与选骨恢复，结果为 `BONE_PHYSICS_CREATOR_SMOKE_OK rigids=4 joints=3 checked=2`；原完整回归继续通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`。真实 Blender 4.4 的 addon 路径仍是指向当前源码的 Junction；本轮等待用户 UI 验收，不递增版本、不打包 zip。

## 2026-08-14 - type 2 父子层级传播与不可拉伸骨链（源码桥接开发）

- 纠正上一轮对“2 型保留动画骨骼位置”的不完整实现。Saba 的 `DynamicAndBoneMergeMotionState` 虽然对当前骨骼保留更新前的全局平移并采用物理旋转，但紧接着调用 `UpdateChildTransform()`；父骨旋转会先沿原局部偏移移动整条子链，子骨随后保留的是已经传播后的新位置。旧 host 把所有 2 型骨骼位置一次性独立冻结，遗漏这一步，因此出现逐骨原地旋转。
- 新增显式父到子层级解析：每帧保存动画 pose 层级，Rust/Bullet step 后先取物理骨骼朝向，再用已解析父矩阵乘以动画局部变换得到子骨继承位置。2 型以该继承位置和物理旋转组成最终矩阵；1 型仍采用完整物理变换。非物理中间骨也参与层级传播，多个刚体驱动同骨骼的质量优先规则不变。
- 不重新启用 Blender `use_connect` 作为实现手段；预览期间仍解除连接，链连续性由显式 MMD 层级语义保证，避免 Blender 约束掩盖错误。完整 headless smoke 已改为全部代理刚体使用 2 型，并逐帧断言每个子骨头等于父骨尾、物理旋转正确、刚体与 Joint 显示仍对应 Rust 输出。
- 实际 `04.blend` 只读强制全部代理刚体为 2 型连续解算 `300` 帧：`145` 对父子骨最大头尾间隙 `3.69e-7 m`，骨骼头最大移动 `0.100477 m`，证明不是原地旋转；物理旋转误差 `1.75e-7 rad`，刚体位置误差 `0`，Joint 中点误差 `0`。未保存或覆盖工程；本轮不递增版本、不打包 zip，不修改 Rust DLL。

## 2026-08-14 - 刚体与 Joint 统一全局深度补间（源码桥接开发）

- 修复线性补间按每列自身长度归一化的问题。旧算法会让前裙等短列在自己的末端提前达到质量 `0.5 kg` 和 Joint 末端软参数，造成同一圈层质量、阻尼、尺寸与约束参数不一致，并在短长列交界处形成凸起。
- 刚体全部补间项现在统一按当前代理最长列的刚体层数计算深度，包括宽度/高度/深度比例、质量、移动阻尼、旋转阻尼、弹性和摩擦；只有最长列末端达到末端值，短列末端保留其全局层深对应的中间值。
- 纵 Joint 与横 Joint 共用最长列的 Joint 层深。移动/旋转上下限、移动弹簧和旋转弹簧的所有已勾选轴都使用相同全局系数；`JOINT_ANCHOR` 继续固定使用起始值。创建、应用参数和骨骼变动后的尺寸同步共用这套规则。
- Blender 4.4.3 完整 headless smoke 通过。实际 `04.blend` 只读应用参数验证列深为 `7–12` 个点：最长列末端质量为 `0.5 kg`，最短列末端按全局深度得到 `1.25 kg`；全部刚体动力学标量最大误差 `4.8e-8`、尺寸误差 `0`、纵/横 Joint 六组参数误差 `0`。未保存或覆盖工程；本轮不递增版本、不打包 zip，不修改 Rust DLL。

## 2026-08-14 - Bullet 2.75、Rust ABI v2 与刚体/Joint/骨骼世界空间统一（源码桥接开发）

- 撤销上一条日志中的错误 type 2 方案：将动画骨骼的逐帧完整增量反向施加给动态刚体并不符合 Saba、nanoem、babylon-mmd 的常规 MMD 更新语义，也是上半身运动时整圈裙摆翘起的直接能量注入点。新路径只在 step 前同步 0 型运动学刚体；1 型完整读取物理骨骼变换；2 型动态刚体保持 Bullet 所有权，读取物理旋转并保留当前动画骨骼平移。
- Rust DLL ABI 从 v1 升到 v2。`BodyDesc` 新增 bind bone transform；Rust 内持有 `body_from_bone`、动画骨骼目标和 PMX 0/1/2 类型语义，并新增 bone transform 与 Joint 双侧 world frame 输出。Python host 不再自行拼 type 2 增量，而是把刚体、骨骼和 Joint 显示全部绑定到 Rust 返回的同一世界空间结果；停止时同时恢复刚体和 Joint 对象矩阵。
- 用 Bullet `2.75` 官方发布对应的 SVN r1754 源码替换运行 backend，不再以 Bullet 3.26 冒充 MMD 数值语义。保留 Z-axis capsule、additional damping、sleeping threshold、碰撞组/mask 和原版 `btGeneric6DofSpringConstraint`；移除 3.26 专用 `setUseFrameOffset`、`setEquilibriumPoint()` 以及先前自行添加的锁轴 ERP/CFM。
- 定位并修复 Blender 特有的位置覆盖：代理链原先使用 `use_connect=True`，Blender 会在 pose 更新时强制把动态子骨骼头部吸回父骨骼尾部，即使 Rust 输出正确也会出现最多厘米级的刚体/骨骼错位。新生成代理骨骼保持父级关系但不连接；旧工程预览期间临时解除动态骨骼连接，停止时原样恢复。
- 实际 `04.blend` 只读解算 600 帧通过硬对齐断言：`194` 刚体、`305` Joint，刚体显示位置相对 Rust 输出误差 `0`，骨骼位置最大误差 `7.49e-7 m`，Joint 显示相对 Rust 双 frame 中点误差 `0`，动态骨骼连接状态 `145 -> 0 -> 145` 完整恢复；最大刚体初始位移 `0.112421 m`，最大 Joint 双侧位置差 `0.002901 m`。另做上半身周期平移/旋转 180 帧，骨骼位置最大误差 `7.76e-7 m`、最大单帧刚体位移 `0.018942 m`，无非有限值或整体翻飞。骨骼回写使用 `Bone.convert_local_to_pose` 直接求 `matrix_basis`，不再为每层触发一次 depsgraph update。
- Rust 4 项单元测试与 Blender 4.4.3 完整 headless smoke 通过；smoke 现逐帧硬断言刚体显示、驱动骨骼位置和 Joint 显示均等于 Rust 输出。DLL SHA-256 为 `7fbf0b5560646700ed6df879406a85a6560a0dae6503354cee7f13985165ffdf`。继续使用源码 Junction；本轮不递增版本、不打包 zip，未保存或覆盖实际 `.blend`。

## 2026-08-14 - type 2 步进时序修正与真实工程离线解算（源码桥接开发）

- 按用户要求停止桌面/GUI 操作，直接以 Blender 4.4.3 background 载入实际 `04.blend`，由当前 Rust/Bullet DLL 连续解算 `600` 帧并离屏渲染第 `600` 帧；未保存或覆盖工程。
- 确认旧 host 的 `物理 + 骨骼`（type 2）时序错误：旧逻辑先推进 Bullet，再强制把 solver body 瞬移回动画骨骼位置，同时保留旧速度。静止姿势不一定立即发散，但运动中的上半身会由位置修正和旧速度产生反常冲量。
- 改为 step 前把 type 2 动画骨骼相对上一帧的完整变换增量施加给当前物理刚体，使上半身平移和旋转都能带动刚体、同时保留 Bullet 相对摆动；step 后只把物理旋转写回骨骼并保留动画骨骼位置，不再回写/瞬移 solver body。0 型运动学同步、1 型完整回写和当前代理作用域不变。
- 实际工程静止 `600` 帧结果：`165` 个动态刚体、`29` 个 0 型刚体、`305` 个 Joint，无 `NaN/Inf`；第 `600` 帧最大初始位移 `0.109752 m`，平均位移 `0.021054 m`，最大 Joint 锚点误差 `0.005335 m`。另对`上半身`施加 `±0.15 m` 位移和 `±20°` 周期旋转连续解算 `600` 帧，最大单帧刚体位移 `0.023586 m`、无非有限值、无飞散。
- 完整 Blender 4.4.3 headless 回归新增 type 2 随父骨运动的有限值和单帧位移断言并通过：`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK ... rigids=48 joints=84`。继续使用源码 Junction；本轮只改 Python host、测试及文档，不改 DLL、不递增版本、不打包 zip。

## 2026-08-14 - 当前代理物理预览作用域修正（源码桥接开发）

- 根据用户重启后的实际截图纠正上一轮错误验收：上一轮指标只统计 `Skirt_*` 骨骼，因此只能证明裙代理自身没有爆炸，却遗漏了预览器仍在释放整个角色的头发、飘带、穗子等动态刚体；“裙代理稳定”不能推出整张视口正确。
- 新增明确的“预览范围”：默认“当前代理”只把当前代理关联的动态刚体和 Joint 加入 solver，同时保留 MMD 模型全部 0 型刚体作为身体碰撞体和外部锚点；其它代理及原模型动态链完全不进入本次 session。“整个模型”保留为用户显式选择的独立模式。
- 实际 `04.blend` 只读验证当前代理 session 为 `165` 个动态刚体、`29` 个模型 0 型刚体、`0` 个外来动态刚体；连续运行 60 tick 不再顺带释放原模型物理。验证过程未保存或覆盖 `.blend`。
- Blender 4.4.3 完整 headless 回归通过：额外创建一个与当前代理无关的动态刚体，断言默认作用域不将其加入 solver、刚体矩阵不变；切换“整个模型”后则明确包含该刚体。继续使用源码 Junction；本轮只改 Python host，不改 DLL、不递增版本、不打包 zip。

## 2026-08-14 - MMD 帧语义、Bullet 尺度与 capsule 碰撞修复（源码桥接开发）

- 复现用户截图中的飞散：实际 `04.blend` 在旧 DLL 中开启碰撞后，第 2–3 tick 即出现约 `1.4–3 rad` 异常旋转；关闭碰撞后变换桥接稳定，确认主因不在 Blender/Rust 四元数转换，而在碰撞形状、求解尺度和帧回写语义。
- 修复 capsule 轴向硬错误：`mmd_tools` capsule 沿对象 local Z，旧 backend 却创建 Bullet 默认 local Y capsule，实际碰撞体与视口刚体相差 90°；现在改用 `btCapsuleShapeZ`。求解器内部同时按 `mmd_tools` 默认 `0.08` 导入比例使用 `12.5` MMD/Bullet 尺度，并等比换算位置、尺寸、线性限制、重力、运动学目标与输出。
- vendored `mmd-anim-physics-bullet 0.4.1` 到独立 native 模块，补齐 20 次 warm-start iteration、真实 `set_iterations`、constraint override、运动学 interpolation transform、activation、AABB 更新，以及线性锁定 Joint 的 STOP ERP `0.2` / CFM `0.0002`；构建不再依赖用户 Cargo registry 中不可复现的源码状态。
- 修正 Blender host 帧顺序：每 tick 先恢复启动时的动画基姿态，再同步 0 型运动学刚体、推进 Bullet、最后回写 1/2 型骨骼，避免把上一帧物理姿态再次当动画输入而逐帧正反馈。2 型保持骨骼位置并回正 solver body；父子骨按深度批量回写；同一骨骼多个动态刚体按 `mmd_tools` 规则只选择质量最大的主驱动。
- 实际 `04.blend` 只读反馈环重新生成 `165` 刚体 / `305` Joint；裙代理连续 60 tick 的最大骨骼偏移约 `2.6e-7 m`、无旋转翻折。模型原有的前穗穗和左右背蝴蝶结共 3 个全 1 型且无 0 型锚点的独立分量仍会按数据语义自由下落，预览器继续列名警告，不伪造约束。
- Rust 单元测试与 Blender 4.4.3 完整 headless 回归通过；稳定性断言从刚体位移 `< 2.0 m` 收紧为刚体位移和代理骨骼综合偏差均 `< 0.01`。DLL SHA-256 为 `e21d4a704ba146e22e73d8a6ae6d4b583bd6d293ea8e5cc73d505dccb16aaa63`。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 顶层锚定 Joint 与物理发散诊断（源码桥接开发）

- 修复每列第一圈刚体没有连回连接骨骼刚体的生成缺口。生成器现在追溯顶层代理骨骼的直接父骨骼，在同名 MMD 刚体中优先选择 0 型静态刚体，并为每列新增 `JOINT_ANCHOR`，连接“父骨骼刚体 → 第一圈代理刚体”。父骨骼没有 MMD 刚体时保持原有可生成行为，不伪造隐式锚点。
- `JOINT_ANCHOR` 纳入参数应用和骨骼/刚体/Joint 同步路径，使用纵 Joint 的顶层参数；重复应用参数或同步代理不会丢失或错位该连接。
- 对实际 `04.blend` 进行了 300 个固定步诊断。修复前新生成裙摆链无静态锚定并持续下坠；修复后生成结果为 `165` 刚体 / `305` Joint（新增 `20` 个顶层 Joint），裙摆刚体 300 步最大偏移约 `0.115`，不再发散。
- 诊断同时发现模型原有数据包含 `3` 组完全没有连接 0 型刚体的动态分量，其中 `229_前穗穗_0_1` 所在链是全模型继续下落的最大偏移来源。这类链在 MMD 刚体语义下就是自由体，预览器现在启动时列名警告，不擅自添加会改变 PMX 语义的隐式约束。
- 完整 Blender 4.4.3 headless 回归通过：新增每列顶层 Joint 端点断言、无对应父刚体的开放代理兼容断言、无未锚定动态分量断言，以及 180 固定步最大偏移 `< 2.0` 的稳定性回归。本轮不修改 Rust ABI/DLL，继续使用源码 Junction，不递增版本、不打包 zip。

## 2026-08-14 - 独立 Rust/Bullet MMD 物理预览竖切（源码桥接开发）

- 新增完全模块化的 `mmd_skirt_proxy_creator/physics_preview/`：`ffi.py` 只负责稳定 C ABI，`runtime.py` 负责 Blender MMD 数据提取、固定步长运行与 Pose Bone 回写，`ui.py` 只提供启动/停止/重置和频率、子步、重力设置；模块不引用裙面代理生成算法，后续可整体拆成独立插件。
- 新增 `native/mmd_physics_solver/` Rust `cdylib`。DLL 通过 `mmd-anim-physics-bullet 0.4.1` 静态链接 vendored Bullet3，接收 Sphere/Box/Capsule、碰撞组/mask、质量/阻尼/摩擦/弹性、按模型列表顺序传入的 `btGeneric6DofSpringConstraint` 参数；运行时不创建 Blender `RigidBodyWorld`，也不调用 `mmd_tools` 的预览或烘焙实现。
- 0 型刚体每步从当前 Pose Bone 更新运动学目标；1 型把完整 Bullet 变换回写骨骼；2 型按 MMD“物理 + 骨骼位置对齐”语义保留骨骼当前位置、采用物理旋转。停止预览会恢复启动前的动态骨骼 `matrix_basis` 和全部刚体对象矩阵。
- RGBA 式胸部结构所依赖的多辅助刚体、偏心 Joint、六轴限制/弹簧与 Joint 顺序不做骨名特判，完整交由 Bullet 图求解。当前完成的是可运行竖切，不把它误报为已证明的 MMD 逐帧一致：还缺同一 RGBA PMX/VMD 在 MMD 9.26 与本预览器之间的 oracle 轨迹对照。
- Rust 单元测试通过，覆盖 Bullet 动态刚体下落和按输入顺序建立 Joint；Blender 4.4.3 完整 headless 回归通过，覆盖 DLL ABI、48 刚体/72 Joint 建图、单步求解、停止恢复及原有代理/查看器流程。继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-14 - 推荐预设的 Joint 上紧下松补间（源码桥接开发）

- 将“稳定中长裙”从全层统一 Joint 参数改为逐层线性补间。纵 Joint 旋转范围从腰部 `X -8°..3° / YZ ±3°` 放宽到裙摆 `X -18°..8° / YZ ±7°`；移动弹簧 Y 从 `800 → 250`，旋转弹簧从 `(12,5,5) → (4,2,2)`，形成腰部稳定、末端柔软的梯度。
- 横 Joint 旋转范围从腰部 `X ±4° / Y ±3° / Z ±5°` 放宽到裙摆 `X ±8° / Y ±5° / Z ±12°`；移动弹簧从 `(300,80,150) → (120,30,60)`，旋转弹簧从 `(3,1.5,4) → (1,0.5,1.5)`。
- 纵/横移动限制仍固定为零且不启用补间，因为起始与末端相同，勾选不会改变结果。补间只启用在确有起止差异的旋转限制和弹簧轴上。
- 更新 headless 回归，验证起始值、末端值和逐轴补间开关；继续使用源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-14 - 内置物理方案与持久化自定义预设（源码桥接开发）

- 在 `MMD 刚体与 Joint` 顶部新增“物理参数预设”。“填入：稳定中长裙”会一次写入盒体、顶层物理+骨骼、下层物理、自动尺寸、`2.0 → 0.5` 质量、`0.995 → 0.98` 阻尼，以及独立的纵/横 Joint 限制和弹簧；碰撞组与不碰撞组保持当前模型设置，避免预设擅自覆盖模型分组规划。
- 内置预设只修改面板参数，不立即修改现有刚体或 Joint；用户仍通过底部“应用参数到当前代理”明确提交，保持当前代理作用域和其它代理隔离边界。
- 接入 Blender 原生 `AddPresetBase`：加号把当前全部物理、碰撞、纵/横 Joint、补间开关和末端值写入用户脚本目录的 `presets/mmd_skirt_proxy_creator/physics`，下拉菜单可跨 `.blend` 载入，减号只删除当前用户预设。
- 修正 Blender 4.4 原生 preset 删除对大小写显示名匹配失败的情况：删除路径限定为 Blender 用户 preset 目录，并以不区分大小写的显示名匹配，不扫描或删除安装目录中的文件。
- Blender 4.4.3 完整 headless 回归通过，覆盖内置预设数值、全部保存字段、四页面板绘制和原有物理生成链路；另在隔离的 `BLENDER_USER_SCRIPTS` 下验证自定义预设保存、载入、向量恢复和删除闭环。继续使用源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 回退刚体横轴水平锁定实验（源码桥接开发）

- 根据实际视口结果，完整撤销上一轮“局部 X 强制保持模型水平”的旋转实验；该方案虽然消除了跨列高度差带来的 roll，却破坏了刚体对代理曲面各列方向的贴合，实际效果比原算法更差。
- 恢复原有曲面局部坐标系：纵轴沿上下 Joint，相邻列三维中点连线投影为横轴，再由二者计算朝外法向。同步、尺寸自适配、默认刚体类型及其它物理参数逻辑不变。
- 删除仅服务于已撤销方案的水平横轴回归断言，并把 README 恢复为原曲面法向说明。继续使用源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 刚体横向 roll 稳定化（源码桥接开发）

- 修复自动旋转直接采用相邻代理列三维中点连线的问题。相邻列同层高度不一致时，该连线带有 Z 分量，会让刚体绕纵轴产生不必要的横向歪斜。
- 新朝向继续让局部 Z 精确连接上下 Joint，但把局部 X 稳定在模型局部水平面内的圆周方向，再由纵轴与横轴求出朝外的局部 Y 法向。因此保留骨链自身倾斜和曲面朝向，不再把跨列高度差转换为额外 roll。
- 完整 headless 回归新增所有生成刚体局部 X 轴 Z 分量小于 `1e-6` 的断言，同时继续验证局部 Y 与记录法向一致、纵 Joint 位于骨骼节点、多代理隔离和同步链路。实际 `04.blend` 只读检查发现保存态未包含关联刚体，因此未修改或保存该工程；当前未保存视口结果需在 Reload Scripts 后执行一次同步确认。
- 继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 刚体分层语义与新建默认类型（源码桥接开发）

- 明确“顶层类型”只控制每列第一层刚体，“下层类型”控制同列其余层刚体；为两个控件补充悬停说明，不改变既有的 `row == 0` 分层生成逻辑。
- 新建设置的默认值改为：刚体形状“盒体”、顶层类型“物理 + 骨骼”、下层类型“物理”。仅调整 RNA 新建默认值，不强制覆盖 `.blend` 或既有代理已经保存的参数。
- 增加三项默认值回归断言；继续使用真实 Blender 4.4 源码 Junction，本轮不递增版本、不打包 zip。

## 2026-08-14 - 曲面法向刚体、自适配覆盖与批量创建（源码桥接开发）

- 对实际 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\04.blend` 做只读 cProfile：原生成 `165` 刚体和 `285` Joint 耗时 `21.405285 s`，其中 `19.579 s` 消耗在 `902` 次 `_view_layer_update`；根因是每个对象分别调用 `bpy.ops.rigidbody.object_add` / `constraint_add`，不是 Python 数学计算。
- 改用官方 `mmd_tools` 已提供的 `new_rigid_body_objects` / `new_joint_objects` 批量复制路径：分别只创建一个模板对象，再以少量 `bpy.ops.object.duplicate` 扩展到目标数量，之后逐项写入 MMD 参数。相同 `04.blend` 只读复测耗时 `0.506560 s`，约快 `42.25` 倍；同时验证 `165` 个刚体 Mesh 数据互相独立。
- 物理布局改为“Joint 节点优先”：代理骨链的每个内部节点直接作为纵 Joint 位置；横 Joint 放在相邻列同层骨骼节点的中点；刚体位于两个相邻 Joint/端点之间，而不再从刚体中心反推 Joint。
- 每个刚体从代理邻域建立局部正交坐标系：局部 Z 沿纵向段，局部 X 沿相邻列切线，局部 Y 沿曲面外法向；闭合代理使用前后列，开放代理端点使用单侧邻列，单列代理使用轴向外侧作为法向提示。
- 尺寸字段为 `0` 时进入自动适配：横向半尺寸按相邻列单元宽度的 `48%`，纵向总覆盖按 Joint 间距的 `96%`，BOX 自动厚度按局部宽/高较小值的 `16%` 计算；CAPSULE 自动限制半径不超过纵向覆盖的 `45%`。非零值继续按用户设置的骨长比例覆盖，保持补间和倍加行为。
- `应用参数到当前代理`与自动同步共用同一几何求解。代理顶点同步到骨骼、或直接编辑代理骨骼后，会重新计算刚体位置、法向旋转和尺寸；同步逐属性比较，只写入实际变化的附近刚体/Joint，其余物理对象及其它代理保持不动。
- Blender 4.4.3 完整 headless 回归通过：验证刚体中心位于相邻节点中点、局部 Y 与记录曲面法向一致、纵 Joint 精确等于骨骼节点、全零尺寸能自动得到有效覆盖，以及移动开放代理局部顶点后附近刚体尺寸和 Joint 位置更新、远端刚体不动。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 一体化基本页、开放代理与单列骨链（源码桥接开发）

- 将原面板顶部独立的代理创建器和代理编辑区迁入 `MMD 刚体与 Joint > 基本`页，形成单一页签式工作流；MMD 模型、当前代理、物理参数页签及生成/应用入口仍固定可见。
- 新增`代理拓扑：闭合 / 打开`。闭合模式维持环形首尾连接；打开模式从选区角度范围建立开放列，只连接相邻列的网格面和横 Joint，不连接末列与首列。
- “圆周方向”允许设为 `1`。单列时无论拓扑选择为何都生成一列顶点、纵向边和连续骨链，不生成 polygon，也不会生成横 Joint；闭合模式的 `2` 列继续在创建前明确拒绝，避免退化闭合面。
- 开放代理的横向平滑、末端轮廓规整和层数规整改为非周期边界，不再让首尾两列互相影响；开放权重在相邻列线段间插值，单列权重全部归入唯一骨链。
- 为代理保存 `surface_proxy_closed` 身份；重新识别缺少该字段的代理时从首末列连边推断。生成和更新 MMD 物理均读取该身份，确保开放代理只拥有相邻列横 Joint。
- 刚体与 Joint 参数表的“补间”标题和普通复选框改为独立居中单元格，修正复选框相对列标题偏左的视觉问题。
- Blender 4.4.3 完整 headless 回归通过：原 `12` 列闭合代理保持 `48` 刚体/`72` Joint；新增 `4` 列开放代理验证 `16` 刚体/`21` Joint 且无首尾连接；新增 `1` 列代理验证 `0` 个面、`4` 条纵向边和 `4` 根骨骼。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - PMX 对齐的复选框、Joint 范围表与倍加尺寸（源码桥接开发）

- 将刚体、纵 Joint 和横 Joint 的参数表改为固定列数的 `grid_flow`，解决标签、线性补间开关和末端输入框错列；全部线性补间控件改为普通复选框，不再使用整格点亮式 toggle。
- 纵/横 Joint 的操作顺序改为接近 PMX 曲面自动设定插件：移动/旋转限制在同一 XYZ 行并列显示起始下限、起始上限、一个逐轴补间复选框、末端下限和末端上限；上下限共用该轴的补间开关。移动/旋转弹簧则按起始值、逐轴复选框、末端值排列。
- 刚体尺寸补齐独立深度比例，并为宽度和高度增加普通“倍加”复选框；启用后对应计算尺寸乘以 `2`，且仍可与逐层线性补间同时使用。
- 新建设置的刚体尺寸、动力学、Joint 限制、Joint 弹簧及各末端数值全部默认 `0`，避免插件预填物理参数；结构性选项与“骨骼变动后自动同步”仍保留合理默认值。
- 明确“应用参数到当前代理”的边界：可随时更新已生成且属于当前代理的刚体/Joint 参数与骨骼对齐变换，不补建缺失对象，不触及其它代理；operator 悬停说明已同步。
- Blender 4.4.3 完整 headless 双代理回归通过：验证全零默认值、BOX 宽/深/高尺寸、宽度倍加、刚体逐层插值、纵/横 Joint 共用逐轴补间开关、多代理隔离、自动同步、批量删除和骨骼清理。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - PMX 式线性补间与物理参数页重排（源码桥接开发）

- 移除`基本`页重复的“生成横向 Joint”，只在`横 Joint`页保留唯一开关；“骨骼变动后自动同步刚体与 Joint”默认值改为启用。
- 重排刚体页为“形状与类型 / 尺寸 / 物理演算参数 / 碰撞”四组。尺寸和物理参数使用统一的“参数 / 起始值 / 线性补间 / 末端值”行布局，替代原先缺少层次的连续属性堆叠。
- 新增真实的刚体逐层线性补间：半径/骨长、长度/骨长、质量、移动阻尼、旋转阻尼、弹性与摩擦均可独立启用，从每列顶层刚体插值到该列末层刚体。创建和“应用参数到当前代理”共用同一计算路径。
- 纵 Joint 与横 Joint 的移动上下限、旋转上下限、移动弹簧、旋转弹簧改为 XYZ 逐轴行布局；每个轴分别提供补间开关与末端值。纵向按本列 Joint 深度、横向按相邻列实际共享层数计算 `0..1` 插值因子，兼容各列层数不同的代理。
- 所有补间开关和末端值均纳入每代理独立参数保存；缩短新 IDProperty 键为 `spx_physics_*` 以满足 Blender 63 字符上限，并保留对已有短旧键的读取兼容。
- Blender 4.4.3 完整 headless 双代理回归通过：验证刚体质量 `1.0 → 3.0`、半径比例 `0.2 → 0.4`，纵/横 Joint 的 X/Z 轴补间与 Y 轴固定值，以及关闭补间后的统一更新、多代理隔离、自动变换同步、批量删除和骨骼清理。继续使用源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - 多代理物理作用域与骨骼联动同步（源码桥接开发）

- 新增明确的“当前代理网格”作用域。生成 MMD 刚体/Joint、应用参数、手工同步与自动同步不再依赖容易变化的活动对象，而是只处理当前代理；活动对象仅在尚未指定当前代理时作为一次性回退。
- 每个代理获得稳定的 `surface_proxy_physics_id`，关联刚体和 Joint 同步记录该 ID，并兼容迁移旧的 `surface_proxy_object` 名称关联。代理对象改名后，物理对象仍可按稳定 ID 找回；多个代理共用同一 MMD Armature 时互不串组。
- 各代理分别保存刚体、纵 Joint、横 Joint 参数。切换当前代理时恢复该代理上次应用的参数；自动变换同步不会套用面板中另一代理的参数，也不会覆盖质量、碰撞组、阻尼、Joint 限制等单项编辑。
- 新增“骨骼变动后自动同步刚体与 Joint”与“同步当前代理刚体和 Joint”。代理网格同步骨骼后，或用户编辑当前代理所属 Armature 并退出 Edit Mode 后，仅更新当前代理刚体的位置/旋转及按既有尺寸比例变化的大小，并更新其纵向/横向 Joint 位置；其它代理物理对象保持不动。
- MMD 查看器新增“代理范围”和“仅显示当前代理”，可只查看当前代理的骨骼、刚体或 Joint。
- 增加代理身份自修复：若对象保存的 `surface_proxy_prefix` 与实际骨链不一致，生成或筛选物理前会重新识别。实际 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\04.blend` 中 `Skirt_Surface` 的旧元数据为 `SkirtProxy`、实际骨链为 `Skirt`，现已在内存中正确恢复并成功生成 `165` 个刚体和 `285` 个 Joint；验证过程未保存、未覆盖原文件。
- Blender 4.4.3 headless 双代理回归通过：两个代理共用同一 Armature，各生成 `48` 个刚体与 `72` 个 Joint；参数切换、当前代理列表过滤、手工骨骼同步、Armature Edit Mode 延迟自动同步及“同步骨骼到代理”联动物理均验证只修改选定代理。继续使用真实 Blender 4.4 源码 Junction；本轮不递增版本、不打包 zip。

## 2026-08-14 - v0.1.7 创建面板默认值与连接骨骼列表

- 将裙面代理创建器的“名称前缀”默认值从 `SkirtProxy` 改为 `Skirt`；只改变新建设置的默认值，不强制覆盖 `.blend` 中已保存的用户输入。
- 选择“目标骨架”后，“连接骨骼”改用该 Armature 数据的 `bones` 可搜索选择框，可直接展开并搜索骨骼；未选择目标骨架时仍显示普通文本框，以保持自动创建骨架路径的现有行为。
- 修改仅涉及创建面板的默认值与输入控件，不改变代理拟合、骨骼生成、权重、刚体或 Joint 逻辑；Blender 4.4.3 完整 headless 回归通过，真实 Blender 4.4 源码 Junction 加载通过。
- 发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.7.zip`，SHA-256 为 `ab8f3aca53a6e12aa394ca6891d86a61aae0a19bbb780bad85f1f33185383cc5`。

## 2026-08-13 - v0.1.6 MMD 骨骼名称补全

- 修复裙面代理器创建的新骨骼缺少 MMD `名称` 与 `名称(英文)` 的问题：退出 Edit Mode 后，若 Pose Bone 具有 `mmd_bone` 属性，则以 Blender 骨骼名初始化两个空字段；非 MMD Armature 仍保持原行为。
- 在骨骼查看器增加“补全勾选”“补全全部”，并在活动骨骼属性区增加“补全当前空缺名称”；三个入口均只填写空白字段，不覆盖用户已有的日文名、英文名或其它自定义名称。
- Blender 4.4.3 完整 headless 回归通过：验证新建代理骨骼两项名称立即初始化、勾选范围只处理目标骨骼、全部范围补齐剩余空字段，并确认已有 `名称` 保持不变；其余 48 个刚体、72 个 Joint、批量删除与骨骼清理回归继续通过。
- 真实 Blender 4.4 继续通过源码 Junction 装载；发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.6.zip`，SHA-256 为 `3d4ab4977cc2d083311876a3a8de546fc26ea0eaf94430a3271f6181c9ed5cdb`。

## 2026-08-13 - v0.1.5 横向页签布局

- 修复 `physics_tab` 的 `expand=True` 直接绘制在纵向 `box` 容器中，导致 `基本 / 刚体 / 纵 Joint / 横 Joint` 四项被垂直展开的问题。
- 现在与 Velo Tools 的页签布局一致：先建立单行 `row(align=True)`，再在该行横向展开全部页签；参数页面和底部生成/应用按钮不变。
- Blender 4.4.3 完整 headless 回归继续通过。
- 真实 Blender 4.4 继续通过源码 Junction 装载；发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.5.zip`，SHA-256 为 `d520a5729aee21a931d6e8692e930721eb0965056f0648c35940d2901f24959c`。

## 2026-08-13 - v0.1.4 物理设定页签与编号碰撞组

- 重构过长的 `MMD 刚体与 Joint` 区域为 `基本 / 刚体 / 纵 Joint / 横 Joint` 四个 Blender 页签；MMD 模型选择与生成/应用按钮固定可见，当前页只显示对应参数。
- 纵向和横向 Joint 从原先共用一套参数改为独立的移动上下限、旋转上下限、移动弹簧与旋转弹簧。创建和“应用参数”均根据生成物的 `JOINT_VERTICAL` / `JOINT_HORIZONTAL` 身份读取对应页配置。
- 将生成设定和活动刚体检查器中的 `collision_group_mask` 从无编号的 Layer 控件改成两行 `1–8`、`9–16` 数字切换按钮；属性仍直接写入官方 `mmd_tools` 的 16 位 mask。
- Blender 4.4.3 headless 回归新增纵 Joint 旋转弹簧 `(3,4,5) -> (4,5,6)` 与横 Joint `(8,9,10) -> (9,10,11)` 的独立创建和更新断言；完整生成、查看、选组、删除、骨骼清理及权重归并回归继续通过。
- 真实 Blender 4.4 继续通过源码 Junction 装载；发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.4.zip`，SHA-256 为 `99999efdaacd1e7aefdd58cc0a3e8b0e91df9967c9488b40011d60d870955ced`。

## 2026-08-13 - v0.1.3 按名称前缀快速选组

- 为骨骼、刚体和 Joint 的“快速选组”统一新增“按名称前缀”。匹配同时检查列表可见名称与 Blender 对象名，使用 Unicode 安全的 `startswith()`，可覆盖 `スカート_0_1` 等非 ASCII MMD 命名。
- 查看器增加可编辑“名称前缀”字段及吸管按钮；吸管从活动项可见名称提取第一个数字之前的部分，例如 `スカート_0_1 -> スカート_`。用户仍可手动缩窄为任意精确前缀。
- Blender 4.4.3 headless 回归新增 `SmokeProxy_C12_` 精确选中 4 根骨骼，以及活动项自动提取 `SmokeProxy_C` 的断言；完整刚体、Joint、批量删除和权重归并回归继续通过。
- 真实 Blender 4.4 继续通过源码 Junction 装载；发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.3.zip`，SHA-256 为 `b51d4add2c1a5a0fb8f45f608e9b0327ddcfa8404a0e946bf4577158e0bf7a6c`。

## 2026-08-13 - v0.1.2 PMXEditor 风格批量编辑

- 将原先只能定位单项的查看器改为独立勾选式批量编辑表：每行具备批量勾选状态，支持全选、全不选、反选、Shift 扩展视口选择和“将勾选项选入 Blender”；切换骨骼/刚体/Joint 分类时自动刷新。
- 新增“快速选组”菜单和列表右键入口。骨骼支持选择当前分支或同列代理骨骼；刚体支持按碰撞组、刚体类型或 Joint 连通组件选择；Joint 支持选择连通组件。
- 新增骨骼安全清理：必须明确指定“权重归并骨骼”，预检目标不能在待删集合内或位于其子级；随后把全部模型 Mesh 中待删顶点组的权重原量归并到目标组，未删除子骨骼改挂目标骨骼，再删除骨骼、绑定刚体及相关 Joint。
- 新增刚体和 Joint 批量删除。删除刚体时自动同时删除以它为任一端点的 Joint，避免悬空约束；所有删除操作均带 Blender Undo 与确认框。
- 新增活动项属性检查器：骨骼可编辑 MMD 名称和 deform 状态；刚体可单独编辑 MMD 名称、绑定骨骼、类型、形状、尺寸、碰撞组/mask、质量、摩擦、弹性和阻尼；Joint 可单独编辑名称、两端刚体、六轴限制与弹簧。
- Blender 4.4.3 headless 回归覆盖：批量勾选/选入、按碰撞组快速选组、两刚体及四关联 Joint 删除、单骨骼权重 `0.3` 向目标既有 `0.2` 精确归并为 `0.5`、绑定刚体与三关联 Joint 清理，以及两 Joint 独立批量删除。
- 真实 Blender 4.4 继续通过源码 Junction 装载；发布包为 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.2.zip`，SHA-256 为 `c11c3b90cedf84938ec1f2a3fcaa66988620ee4f140491fa89bb950d5dbd166b`。

## 2026-08-13 - v0.1.1 MMD 刚体、Joint 与模型查看器

- 新增从裙面代理骨链生成官方 `mmd_tools` 刚体与 Joint 的路径：每根代理骨骼对应一个刚体，纵列相邻刚体生成纵向 Joint，并可为相邻列的动态层生成闭合环向 Joint。生成物记录代理、列、行和角色身份，重复生成会在任何新增对象前中止。
- 新增可调整参数：刚体形状、顶层/下层类型、半径与长度比例、碰撞组和 mask、质量、摩擦、弹性、移动/旋转阻尼，以及 Joint 的移动/旋转限制与弹簧；“应用参数到当前代理”会同步刚体到最新骨骼位置并批量更新物理参数。
- 新增独立的“MMD 骨骼 / 刚体 / Joint 查看器”面板，可指定或自动推断 MMD 根对象，分类刷新模型内容、搜索，并逐项快速选择骨骼、刚体或 Joint。
- Blender 4.4.3 headless 回归通过：合成 MMD 模型生成 `48` 个刚体、`72` 个 Joint，验证骨骼绑定、Joint 两端、参数更新、三类列表计数及三类快速选择；成功标记继续为 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。
- 真实 Blender 4.4 用户环境继续通过 Junction 加载当前源码，启动注册验证为 `v0.1.1`；发布包已写入 `_archive/zip-packages/MMD-Skirt-Proxy-Creator-V0.1.1.zip`，SHA-256 为 `e503fac95df329fd0199120fdc61bc26c9bbb9680b218e51e700fd6e49da1e85`。
- 改动限定在独立 `MMD-Skirt-Proxy-Creator`；未恢复或引用已放弃的 MMD-Nova 求解器、碰撞代理或 native runtime。

## 2026-08-13 - 完整撤回表面吸附实验

- 按用户要求完整移除所有 BVH 表面投射、面拓扑传递、内外层命中选择和向外约束；不再尝试把任何代理节点吸附到源 Mesh 表面。
- `core.py` 与 `tests/headless_smoke.py` 已按 SHA-256 确认恢复为 `_archive/source-backups/2026-08-13-before-three-quarter-fit` 基线；创建入口恢复为只把选中顶点交给原柱面平滑拟合，并由原算法直接应用 `径向偏移`。
- 下方“三视图裙面贴合修复”和“外层轮廓投射修正”记录均为已撤销失败实验，不代表当前行为。
- Blender 4.4.3 基线 smoke test 重新通过：`MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131`。当前只保留此前已经确认的逐列局部顶端高度修复。

## 2026-08-13 - 外层轮廓投射修正

- 撤销上一轮“从代理轴向外取第一次 BVH 命中”的错误判定。该方式在多层裙面、内衬或褶皱存在时会命中内侧表面，导致原本平顺的其它区域新增凹陷。
- 改为从裙面包围半径之外向轴心反向投射，取同一方向的最外层面；只有完全没有命中时才使用原平滑拟合。顶端局部高度、骨骼对齐和统一 `径向偏移` 行为不变。
- 新增双层封闭裙面回归：内层半径最低仅约 `0.35 m`，结果代理中间层最小半径仍为 `0.914602757 m`，证明不会再吸附到内层；中间层最大表面误差为 `0.000000500 m`，Blender 4.4.3 smoke test 通过。
- `00.blend` 继续只读 headless 检查且未保存；由于实际 Edit Mode 选区仍未写入文件，该检查只能验证保存态推断面片，不能替代用户当前未保存选区的视口验收。

## 2026-08-13 - 三视图裙面贴合修复

- 修复代理仅依据顶点半径采样并经过横向平滑，导致正面/侧面看似正常、斜视时中间层明显离开实际裙面的问题。
- 创建阶段现在保留完整选中面拓扑；先生成稳定的闭合代理，再将每列节点从代理轴径向投射到选中面 BVH。命中区域采用真实面插值半径，选区开口或超出面覆盖范围时才保留原拟合作为闭合桥接；`径向偏移` 在投射完成后统一应用，避免重复偏移。
- Blender 4.4.3 headless 回归使用带明显三向非圆形轮廓的合成裙面，代理中间层到源面的最大距离为 `0.000000248 m`；顶端局部高度范围为 `0.228201091 m`，根骨与对应代理顶点重合断言继续通过。
- 对 `D:\MMD\模型\Alicia\鳴潮-達尼婭\Test\00.blend` 做了只读 headless 检查。由于文件未保存当前 Edit Mode 选区，验证以活动 Mesh 的两个最大对称连通面片重建同参数选区：平均最近面距离由旧算法的 `0.020483379 m` 降至 `0.012863597 m`；剩余误差集中于选区没有径向表面的开口方向，由闭合回退承担。未保存或修改 `00.blend`。
- 改动前源码已备份到 `_archive/source-backups/2026-08-13-before-three-quarter-fit`；独立插件源码 Junction 保持启用，旧 `surface_proxy_creator` 仍不存在。

## 2026-08-13 - UTF-8 UI recovery and corrected development bridge

- 修复独立入口文件首次生成时经 PowerShell 管道发生的中文损坏；所有字面量 `?` 占位已恢复为原始简体中文 UI，并新增入口源码不得包含字面量 `?`、关键 RNA 标签必须精确匹配的 Blender 回归断言。
- 纠正安装边界：旧 `surface_proxy_creator` Junction 继续保持移除；新 `mmd_skirt_proxy_creator` 不再使用普通目录副本，而是以 Junction 持续桥接独立源码目录。这样后续 MMD 刚体与 Joint 开发可直接 Reload Scripts / 重启生效。
- 修复前入口已备份到 `_archive/source-backups/2026-08-13-before-utf8-junction-fix`。

## 2026-08-13 - v0.1.0 standalone extraction

- 从 `MMD-Nova-Rebuild` 仅提取裙面拟合、代理 Mesh、纵向骨链、权重写入及代理编辑/同步源码，建立独立 Blender 4.4 插件。
- 明确排除物理解算、Rust native DLL、物理节点、身体碰撞代理与预览运行时，为下一步 MMD 刚体和 Joint 适配保留干净边界。
- 修复顶端高度：删除所有列共用全局最高 Z 的旧行为。每列现在从自身角向邻域两侧分别选取最高支持顶点，再按角距离线性插值；该列代理顶点与根骨 head 共用相同局部顶端。
- 当前完整插件回归通过 `SURFACE_PROXY_HEADLESS_SMOKE_OK`。独立插件 Blender 4.4.3 smoke test 通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`，测试顶端高度范围为 `0.235911131 m`，并逐列断言根骨 head 与代理顶点重合。
- 已禁用并移除真实 Blender 4.4 中旧的 `surface_proxy_creator` Junction；独立插件启用为 `mmd_skirt_proxy_creator`，用户偏好已保存。该条原先记录的普通目录安装已由上方最新条目纠正为独立源码 Junction。
