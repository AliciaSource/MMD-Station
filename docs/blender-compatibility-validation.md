# Blender 4.x / 5.x 本地合并验证

日期：2026-09-12。开发版本：`1.0.3-dev`。

## 合并后追加修复与最终复测（2026-09-12）

下方原合并矩阵保留为历史基线；本节记录用户要求继续修复后的结果，不把原来的失败追写成当时已通过。

- **当前模型 IK 的撤销/F9**：内存生成的 PMX 定义原先因没有持久文件路径，在每次 undo/redo 时被视为失效，关闭并重建 solver，丢失清除事务。现在通过不依赖 RNA 指针的骨架/IK/Morph 定义签名与 authoring session ID 判断能否重用；姿态撤销保留同一 session/solver，rest pose、层级、IK 限制、附加变换或 Morph 定义改变仍重建。
- **清除姿态后的物理自动重置**：解决旧 PMX 路径前置条件后，原 clear-user 测试进一步暴露约 `0.065973386` 的输入旋转误差。启用 live IK 时，全骨骼 identity 清除触发物理恢复不再将启动时已求解姿态写回骨骼、误当作新的 IK 用户输入。只保留本次清除发起模型的输入；未启用 live IK、显式手动重置、其它模型和刚体/关节启动快照恢复规则不变。完整 smoke 捕获了初版改动影响非 IK 重置的问题，最终通过上述作用域限制消除。
- **旧测试 PMX 路径**：输入 `.blend` 的 import folder 已失效，文件不存在。用例明确覆盖已有的当前模型回退，不跳过后面的 IK/物理清除与 session 身份断言；独立合成回归另测显式源、唯一源、歧义目录和缺失源。
- **拆分 ShapeKey 归类修正**：未启用 MMD Station 的独立探针，在 Blender 4.5.13 原生 `mesh.separate(type="MATERIAL")` 后同样观察到 97 个新拆分 Mesh 各有额外 `Basis.001`，原 Mesh 仍为 162 keys。因此此前“代理添加了 ShapeKey”的推断不成立。代理未改生产逻辑、没有删除任何 key；回归改为与实际拆分输入的完整有序名称并集严格比较，并新增原始顶点 ID 跟踪、162 个原 key 全顶点坐标 SHA256 一致、停止预览后所有拆分源 ShapeKey 坐标不变检查。误差和性能门槛不放宽。
- 新增 `mmd_ik_memory_undo_regression`：无需本机资产，实际调用 `ed.undo` 验证 RNA 重建后的会话复用，同时覆盖正常非零姿态撤销、结构变更重建、关闭会话，以及自动/显式物理快照恢复边界。默认通用矩阵从 28 项增为 29 项。
- 完整矩阵发现旧 `mmd_ik_authoring_lifecycle` 用例在实际 undo/redo 后错误手动执行 load/rebuild timer，没有执行 UI 真正调度的 undo-resume timer，留下失效 RNA 映射。测试现在调用实际调度的恢复回调，增加 undo 和 redo 后同一 session/solver 断言；三版本 authoring 保存与重开已通过，不靠失效 RNA 内存恰好尚未覆盖的偶然结果。
- 同步 `AGENTS.md` / `CLAUDE.md`：凡新功能设计或旧功能调整涉及 Blender API，自动检查支持版本的 API 可用性、签名、默认值和运行行为，并按风险运行 4.4.x / 4.5 LTS / 5.2.x 回归。已有兼容层不是未来所有新 API 无条件自动兼容的保证。

本次重新运行完整矩阵，再针对发现的问题复跑相关用例；同一配置的重复诊断不重复计数。最终共 **321/321 个 Blender 配置用例通过**，另有 **29/29 离线 pytest**（其中包含 5 项 i18n），合计 **350/350**。

| 最终测试组 | Blender 4.4.3 | Blender 4.5.13 LTS | Blender 5.2.1 LTS |
| --- | ---: | ---: | ---: |
| 通用回归，MMD Tools 4.5.13 | 29/29 | 29/29 | 29/29 |
| 原生烘焙，MMD Tools 4.5.13 | 9/9 | 9/9 | 9/9 |
| 实际资产及运行时，MMD Tools 4.5.13 | 31/31 | 31/31 | 31/31 |
| 通用回归，MMD Tools 4.5.14 | 29/29 | 29/29 | 29/29 |
| 原生烘焙，MMD Tools 4.5.14 | 9/9 | 9/9 | 9/9 |

实际资产矩阵在原 28 组上增加 F9 的 MMD/PMX 两种物理组合及 clear-user 的 PMX 组合。三版本全部 F9 组合的输入/显示/链位置误差为 0，重复清除误差为 0，clear-user 两后端输入误差为 0。两种依赖的三版本合成回归均覆盖真实 undo 和 Morph 行选择不重建 native 定义。

性能测量存在运行波动：4.4 的 tick median 一次为 `9.176 ms`，5.2 的代理 update 一次为 `11.295 / 8.512 ms`，未通过原门槛；另一次 5.2 运行与追加诊断进程重叠，不取作串行验收。没有改门槛或一直重试到遇到一次成功，而是预先固定两个波动用例各三次独立串行复跑，结果 **6/6 通过**：4.4 tick median 为 `6.175 / 6.240 / 6.118 ms`、p95 为 `7.674 / 7.718 / 6.915 ms`，三个 pose SHA256 相同；5.2 proxy update 为 `9.481 / 8.781 / 9.439 ms`，对应原模型基线为 `11.119 / 10.959 / 11.708 ms`，三次 tick 和 update 的相对门槛均通过。其它性能配置也通过独立串行矩阵，未以并跑数据替代。

源码 AST、暂存树安全扫描、diff 空白检查和两层项目规则同步检查通过。没有修改 DLL、上游 mmd_tools 或输入工程；保持 `1.0.3-dev`，仅本地提交，不 push/tag/打包/发布。本轮临时日志、导出和隔离配置均集中于 `_temporary_cleanup/ik-proxy-fixes-20260912/`；删除命令在创建进程前被执行策略拒绝，故文件仍保留待手动清理，未声称已删除。上轮 `pr1-compat-20260912/` 仍保留；两者均被 Git 忽略，不进入发布包。所有本轮矩阵 runner 已结束。

真实 Blender 4.4 Junction 装载再次通过启用、版本、属性、导出 hook 和卸载断言；未保存偏好。该用户配置退出时仍出现 RetopoPlanes、SeparateMaterial、SymmetricTranslation 各自的 unregister 异常，不来自本次 MMD Station 调用栈，也不据此声称整个第三方插件环境无异常。

## 原合并范围与结论（历史基线）

- 本地非快进合并 [PR #1](https://github.com/AliciaSource/MMD-Station/pull/1)，PR 提交为 `e8c387c0fac0db698dc5e61b308958817a504a66`。
- 第一父提交保留本机 `28bc2bb`，以及其前面的 `f833b46`、`2d34f4b`；没有用远端代码覆盖本机的 Morph 隔离、材质 identity 或骨骼缩放 sidecar 功能。
- DEV_LOG 原有版本条目超限；按工作区规则保留最新 100 条，其余 55 条可从第一父提交或备份引用恢复，未改写历史。
- 合并前备份引用：`refs/backup/pr1-pre-merge-20260912`。不 push、不 tag、不发布或生成发布 ZIP。
- **不是全绿验收**：本轮矩阵发现四个既有失败用例。三条 IK 用例在合并前的 Blender 4.4.3 对照中同样失败；额外的代理 ShapeKey 用例在合并前的 Blender 4.5.13 对照中也复现。没有放宽这些断言或在报告中把它们记作通过。

## 环境与统计

Windows x64；每例使用独立 Blender 进程和隔离配置。主矩阵固定使用现有 MMD Tools **4.5.13**；另用 **4.5.14** 复测通用功能与原生烘焙，不把后一组称为完整资产矩阵。

| 测试组 | Blender 4.4.3 | Blender 4.5.13 LTS | Blender 5.2.1 LTS |
| --- | ---: | ---: | ---: |
| 通用回归，MMD Tools 4.5.13 | 28/28 | 28/28 | 28/28 |
| 原生烘焙组合，MMD Tools 4.5.13 | 9/9 | 9/9 | 9/9 |
| 实际资产及运行时，MMD Tools 4.5.13 | 25/28 | 24/28 | 25/28 |
| 通用回归，MMD Tools 4.5.14 | 28/28 | 28/28 | 28/28 |
| 原生烘焙组合，MMD Tools 4.5.14 | 9/9 | 9/9 | 9/9 |

表中数字是通过数/执行数。重复诊断、A/B 基线、失败后修复重跑不重复计数：共 **306 个 Blender 配置用例，296 通过、10 失败**；另有 **29/29** 离线 pytest 通过。本地化 5 项包含在这 29 项内，不另行加总。源码 56 个 Python 模块的 AST 解析、暂存树安全扫描及 diff 空白检查通过。

没有实跑 Blender 5.0、5.1 或 4.4 以前版本；插件最低版本仍为 4.4。5.2 的结果不等于每个 5.x 小版本均已验证。

## 覆盖清单

### 通用回归：每个版本 28 项

合并提交 `61624a7` 中 `run_blender_matrix.py` 的默认 CASES 列表为本次历史基线的 28 项清单，覆盖：

- 新增兼容回归：多对象/多 slot Action、非首槽位求值、复制/绑定/恢复、NLA、F-Curve 创建/查找/删除/清空、OBJECT/KEY 隔离、Blender 4.x UNSPECIFIED 旧槽位、ShapeKey 初值与已有值保留、UV 选择的独立 BMesh 读回、卸载/重新注册。
- 缺失及抛 AttributeError 的旧式 `mmd_tools` 包探测；有效的官方扩展仍是前提，未声称没有 MMD Tools 也可使用全部宿主功能。
- 本机领先的骨骼转顶点 Morph 隔离、缩放 sidecar 往返、材质 identity 三个回归。
- 总体 headless smoke、骨骼物理创建、集合组织、锁定组选择/权重合并、镜像命名/顶点组、坐标、显示帧、导出分析、IO、材质顺序、Morph 编辑器、用户排序、刚体缩放诊断、Shadow、物理 Action 烘焙/姿势对齐、代理不覆盖、时间驱动、Type2 链平移、更新器和 i18n。

### 原生烘焙：每个版本、每个依赖版本 9 组

永久清单在 `tests/blender_matrix_native.json`：

- CLOTH / SOFT_BODY × preview / sequential × MMD / PMX，共 8 组。
- 原生 RIGID_BODY idle 烘焙 1 组，确认不加载 MMD Station 自带求解 DLL。
- 检查真实 `cache.is_baked`、Action 曲线保持、modifier 保持、停止预览不清空网格缓存，以及 ABI6 按后端惰性加载。
- 这是 headless EXEC 烘焙，不是 GUI `INVOKE_DEFAULT` 后台作业或界面锁时序验收。

### 实际资产与运行时：每个版本 28 组

使用本机现有输入资产，只在内存及临时目录中操作：

- `mmd_00_ik_mmd_parent_empty_latency_regression`
- `mmd_00_ik_physics_isolation_regression`
- `mmd_00_split_material_edge_preview_regression`
- `mmd_00_split_material_physics_regression`
- `mmd_04_parent_empty_latency_regression`
- `mmd_04_preview_pipeline_regression`
- `mmd_04_rigid_latency_regression`
- `mmd_ik_clear_f9_second_cycle_regression`
- `mmd_ik_disable_physics_handoff_regression`
- `mmd_ik_physics_clear_repeat_regression`
- `physics_runtime_v2_performance_regression`
- `mmd_bone_curved_subdivision_regression`
- `mmd_06_type2_chain_translation_regression`
- `mmd_07_root_motion_regression`
- `mmd_ik_clear_user_transforms_regression`
- `mmd_ik_physics_feedback_regression`
- `mmd_ik_physics_reset_regression`
- `mmd_ik_scoped_ownership_regression`
- `mmd_ik_transform_modal_regression`
- `mmd_36_physics_presentation_proxy_regression`
- `mmd_ik_runtime_smoke` × MMD / PMX
- `physics_root_offset_regression` × MMD / PMX
- `pmx_physics_reader_regression`
- `mmd_ik_authoring_lifecycle` 与 `mmd_ik_authoring_reload`
- `pmx_runtime_bone_parity`，13 帧。

实际 PMX/VMD 导入、当前模型 live runtime、PMX 导出 IK/Bone Morph payload 位级往返断言，以及保存并重开临时 authoring 工程均执行通过。不是仅做 register/poll 检查。

## 保留的失败及合并前对照

| 用例 | 合并后 | 合并前源码对照 | 分类 |
| --- | --- | --- | --- |
| `mmd_ik_clear_f9_second_cycle_regression` | 三版本均在第二轮 F9 后显示误差断言失败，误差 `0.05000000074505806`，门槛 `< 1e-6` | 4.4.3 同值失败 | 既有 IK 行为失败 |
| `mmd_ik_physics_clear_repeat_regression` | 三版本均在重复清除断言失败，误差 `0.029427503803922683`，门槛 `< 1e-5` | 4.4.3 同值失败 | 既有 IK 行为失败 |
| `mmd_ik_clear_user_transforms_regression` | 三版本均在 `_resolve_live_source_path` 的输入 PMX 路径前置断言失败 | 4.4.3 同一断言失败 | 既有用例前置失败，后续清除行为未完成验证 |
| `mmd_00_split_material_physics_regression` | 4.5.13 单进程及追加复跑均发现代理多出 `Basis.001`，ShapeKey 名序不等；4.4.3、5.2.1 单进程通过 | 4.5.13 原源码同样多出 `Basis.001` | 既有代理 ShapeKey 问题，不放宽名称断言 |

基线使用合并前 Git archive 的真实源码，不是从历史 DEV_LOG 推断；没有对旧源码应用本轮兼容补丁。最后一项使用相同诊断增强用例、只切换插件源码作 A/B。

性能用例最初受多版本并跑影响出现超时限；所有重判均改成 `--jobs 1`，没有增大门槛。`physics_runtime_v2_performance_regression` 的单进程 tick median / p95 分别为：4.4.3 **7.518 / 12.457 ms**，4.5.13 **6.936 / 8.810 ms**，5.2.1 **7.253 / 8.952 ms**，均满足原门槛；三者 pose SHA256 相同。4.5.13 的材质拆分用例则在计时前已经命中上述 ShapeKey 失败，不能以其它版本的性能通过替代它。

## 合并时额外修复

- 不采用 PR 的全局首个 channelbag：按 ID / AnimData / NLA strip 保持精确 slot，并拒绝多 owner 歧义。兼容 4.4 的无 `group_name` F-Curve 创建参数、旧 API 生成的 UNSPECIFIED slot，以及不同 ID 类型的隔离。
- Morph 路径重映射、NLA 迁移/清理、VMD 临时桥、物理烘焙/修复/缓存和 IK 曲线读取统一传递所属绑定；临时 VMD Action 恢复原 Action 及原 slot。
- Blender 5.x UV 选择同时准备三个共享选择属性，避免只写顶点属性却无法进入 BMesh；显示帧可见性正确读取 PoseBone.hide。
- 本机新加入的骨骼转顶点转换明确初始化新 ShapeKey 为 0，既有 key 的值不改变。缩放 sidecar hooks 保留 wrapper 元数据并防止重复注册，未改 mmd_tools 上游或任何 DLL。
- 回归脚本重新获取跨 Edit Mode / collection 删除后失效的 RNA 引用，隐藏材质测试使用实际连接的 shader；骨骼排序按既有“只移动勾选行”契约断言，IK smoke 按既有独立反馈回归验证“物理不反灌 IK”。没有删除上述四项失败的行为要求。

Blender API 依据：[5.0 Python API release notes](https://developer.blender.org/docs/release_notes/5.0/python_api/)；UV 三属性条件另核对 [Blender BMesh 导入实现](https://github.com/blender/blender/blob/blender-v5.2-release/source/blender/bmesh/intern/bmesh_mesh_convert.cc)。

## 复跑入口与边界

先指定 `$B44`、`$B45`、`$B52` 为待测 exe 路径，`$EXT` 为含有效 `mmd_tools` 扩展目录的父目录；在仓库根运行：

```powershell
python -m pytest tests -q -o python_files=test_*.py
python tests/run_blender_matrix.py --blender "$B44" --blender "$B45" --blender "$B52" --extensions "$EXT" --output _temporary_cleanup/compat/core
python tests/run_blender_matrix.py --blender "$B44" --blender "$B45" --blender "$B52" --extensions "$EXT" --output _temporary_cleanup/compat/native --manifest tests/blender_matrix_native.json
```

外部资产用 JSON manifest 指定 `script`、`blend`、`env`、`args`，结果文件可用 `result` 校验 `ok: true`；可用 `{temporary}`、`{version_dir}` 占位符。性能 manifest 必须加 `--jobs 1`。资产脚本仍依赖其现有私有工程/模型，不随仓库分发。

未执行依赖外部 MMD 实机 oracle 的开发诊断：`mmd_bone_physics_diff`、`mmd_bone_self_append_phase_diff`、`mmd_bone_solver_diff`、`mmd_bone_solver_phase_diff`、`mmd_ik_live_toggle_oracle`、`mmd_runtime_bone_oracle`、`mmd_runtime_physics_oracle`、`mmd_tools_root_motion_metric`、`rossi_four_way_bone_parity`；旧 DLL 名称/旧 hook 原始轨迹的 `mmd_raw_core_parity` 也不作为本轮 ABI6 兼容验收。没有用插件自身生成的结果伪装外部 oracle。

真实 Blender 4.4 用户 addons 的 Junction 仍指向本仓库；经该实际安装路径重新启用、验证版本/属性/导出 hook、卸载通过。未保存用户偏好、未关闭用户 Blender 窗口、未将 5.x 隔离测试当作装入其真实用户配置。已有 GUI 进程需重新加载脚本或重启才会加载合并代码。

原有未提交 ABI5 DLL 保持原样且不纳入合并提交，SHA256 为 `4E86841E1FC0BA29876C7306B930C3E08F84D786F62F734B815ABA22D603D65D`。输入工程未保存。

临时运行时、依赖源码、导出文件和原始日志已全部集中在 `_temporary_cleanup/pr1-compat-20260912/`；删除命令被执行策略拒绝，因此该目录仍保留，需手动清理。它没有被 Git 跟踪，不进入发布包；本轮 Blender 测试进程均已结束。目录内的 `extensions13/mmd_tools` 是指向真实 MMD Tools 安装的 Junction，清理时只删除该联接本身，不删除其真实安装目标。
