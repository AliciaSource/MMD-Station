# Development Log

## 2026-09-12 - v1.0.3-dev IK 清除与撤销状态修复及多版本设计规则

- `evaluator.py` 修复无持久 PMX 的当前模型 live session 在 undo/redo 时被无条件关闭重建：记录不保留 RNA 指针的骨架/IK/Morph 定义签名及 authoring session ID，普通姿态撤销/F9 保持同一 session 和 solver，骨骼 rest/层级、IK 限制、附加变换、Morph 定义或会话身份变化仍重建。没有放宽原 F9 `<1e-6` / 链位置 `<1e-5` 门槛。
- 原 clear-user 用例的旧 import folder 已不存在；明确采用已有当前模型回退后，又复现了约 0.065973386 的输入旋转误差。`physics_preview/runtime.py` 仅在 live IK 启用且全骨骼清除触发自动重置时保留本模型已清除输入，不让旧的已求解启动姿态反灌 IK；仍恢复刚体/关节快照，未启用 live IK、显式手动重置和其它模型恢复规则不变；完整 smoke 已捕获并排除初版对非 IK 重置的影响。
- 原 `Basis.001` 失败重新归类为拆分输入与测试基线不一致：未启用 MMD Station 时，4.5.13 原生材质拆分已在新 Mesh 添加额外 key。没有更改代理合并生产代码或删除用户 ShapeKey；改测实际拆分输入的完整名称并集，并新增原始顶点 ID、162 个原 ShapeKey 全顶点坐标 SHA256、一切拆分源停止预览前后坐标一致性断言。性能门槛保持不变。
- 新增不依赖私有资产的 `mmd_ik_memory_undo_regression.py`：实际 `ed.undo` RNA 重建、清除/非零姿态撤销、定义变更重建、禁用会话、自动/显式快照恢复及 PMX 显式/唯一/歧义/缺失来源；F9 和重复清除增加同一会话身份断言，clear-user 增加 PMX 后端组合。同步 `AGENTS.md` / `CLAUDE.md`，涉及 Blender API 的功能设计或调整须主动检查并回归 4.4.x / 4.5 LTS / 5.2.x，未测版本须明示。
- 全量运行发现旧 authoring 测试在真实 undo/redo 后手动执行了错误的 load/rebuild timer，未跑实际调度的 undo-resume timer，导致 4.5 失效 RNA 映射。用例修正恢复入口并增加双向 undo/redo 的 session/solver 身份断言，三版本保存/重开通过。
- 本轮完整矩阵及定向复跑最终 321/321 个 Blender 配置通过：三版本主依赖各通用 29 + 原生烘焙 9 + 真实资产 31；MMD Tools 4.5.14 各通用 29 + 原生烘焙 9。离线 pytest 29/29，总计 350/350；不重复计诊断及复跑。F9/重复清除/clear-user 的原输入及姿态误差均为 0。两个性能波动用例预先固定三次独立串行复跑共 6/6，原门槛不改，原失败和最终数值均在验证报告中保留。三版本真实 undo 与 Morph 行选择保持会话、源码 AST、暂存树安全扫描通过。真实 4.4 Junction 启用/属性/导出 hook/卸载通过；用户配置的三项第三方 unregister 异常另行记录，不作为 MMD Station 功能通过证据。
- 继续 v1.0.3-dev，真实 Blender 4.4 使用已有源码 Junction；未保存输入工程或用户偏好，未改上游 mmd_tools、DLL、PMX 协议或所有权隔离。既存 ABI5 DLL 原样排除提交。本地提交后不 push/tag/打包/发布；临时产物仅在本项目 `_temporary_cleanup/ik-proxy-fixes-20260912/` 内；删除命令在进程执行前被策略拒绝，文件仍保留供用户手动清理，上轮 `pr1-compat-20260912/` 也仍保留。

## 2026-09-12 - v1.0.3-dev 本地合并 Blender 5.x PR 与三版本全量自动化验证

- 原日志已有版本条目超出工作区上限；本轮按规则保留最新 100 条，较旧的 55 条仍可从合并第一父提交或备份引用查回，不影响任何源码提交。
- 本地非快进合并 PR #1（e8c387c），保留本机 28bc2bb / f833b46 / 2d34f4b 三个领先提交；合并前引用 refs/backup/pr1-pre-merge-20260912 保留原状态。DEV_LOG、英文简报、i18n 冲突同时保留两侧有效内容；未 push、未 tag、未发布或打包。
- 新增 blender_compat.py 并将 Morph、VMD、IK、物理烘焙/缓存与骨骼选择接入兼容层。合并审阅额外修复 PR 首 channelbag 跨 owner 误取：ID/AnimData/NLA 精确 slot、复制和恢复保留 slot 标识、歧义拒绝、OBJECT/KEY 隔离、4.4 无 group_name 参数及旧 API 的 UNSPECIFIED slot。Morph 迁移按 action+slot 去重，烘焙修复只改所属槽位。
- Blender 5.x UV 选择准备 vert/edge/face 三个共享属性并经独立 BMesh 读回验证；显示帧隐藏状态使用 PoseBone.hide。本机新骨骼转换中新建 ShapeKey 显式为 0、已有值不改；缩放 sidecar hooks 保留 wrapper 元数据、依赖预探测与重复注册保护。不改上游 mmd_tools、DLL 或 PMX 协议。
- 新增永久兼容回归、旧模块故障探测、隔离 Blender bootstrap、三版本 runner 与 native bake manifest。修正测试中跨 Edit Mode/collection 删除的失效 RNA 引用、材质实际连接 shader、已过时的骨骼整子树排序/物理反灌 IK 期望；现有完整行为断言、数值门槛和下述失败用例未放宽。
- Blender 4.4.3 / 4.5.13 LTS / 5.2.1 LTS 实跑：MMD Tools 4.5.13、4.5.14 各自通用 28 项+原生烘焙 9 组，共 222/222；主依赖 4.5.13 的真实资产/运行时每版本 28 组，共 74/84。PMX/VMD 实际往返、MMD/PMX 两后端、authoring 保存重开、13 帧 PMX parity 通过；单进程性能门槛保持原值。离线 pytest 29/29（含 i18n 5 项），源码 AST、安全扫描和 diff 检查通过。
- 不记作全绿：三版本的 F9 第二轮清除误差 0.05000000074505806、重复清除误差 0.029427503803922683、clear-user-transforms 前置路径断言共 9 个失败；Blender 4.5.13 的材质拆分代理额外 Basis.001 再计 1 个失败。前三项用合并前源码在 4.4.3 复现，最后一项用合并前源码在 4.5.13 复现；没有为合并通过而修改这些生产行为或断言。
- 完整版本矩阵、失败对照、测试清单与复跑入口见 docs/blender-compatibility-validation.md。未执行 GUI INVOKE 后台锁时序、MMD 外部 oracle 或 5.0/5.1 实机测试；headless 不代替这些边界。
- 继续 1.0.3-dev；真实 Blender 4.4 addons Junction 经实际路径重新启用、属性/导出 hook 烟测通过，不改用户偏好或关闭用户窗口。原工程不保存；本轮临时下载/测试工程/导出/日志全部集中在 _temporary_cleanup/pr1-compat-20260912/，删除调用被执行策略拒绝，保留待手动清理，不纳入 Git 或发布。原有未提交 ABI5 DLL 的 SHA256 保持不变并排除本轮提交。

## 2026-09-09 - v1.0.3-dev 骨骼转顶点表情隔离

- 修复 Bone Morph 转 Vertex Morph 依赖当前场景求值导致的串入，以及调用 mmd_tools 嵌套 BIND/UNBIND 时活动对象丢失触发 AssertionError。合成 Blender 4.4 回归先失败：期望 `(0, 2, 2)`，旧路径为 `(0, 1, 9)`，复现姿势/驱动污染和缩放遗漏；原用户截图的上下文条件未直接复现，改为完全不调用这条嵌套 operator 链。
- 新增 `mmd_bone_conversion.py`：临时复制骨架与网格，清除副本动画、驱动、约束、ShapeKey 混合和非目标骨架修改器，重置骨骼局部姿势，仅施加指定 Morph 的位移/旋转/缩放，以原 Basis 采样；保留骨骼层级和权重。当前手工姿态、其他骨骼/顶点/组合表情及 IK/外部约束不进入结果；不修改原姿势、约束、动画、表情值、模式和活动对象。不新增物理或 IK 烘焙能力。
- `mmd_morph_editor.py` 单个/批量转换共用隔离路径，保留受影响骨骼及子孙权重过滤，排除已移出模型所在 Scene 的孤立网格；继续创建/更新 Vertex Morph、沿用源名加 B 和显示框行为，保留英文名及分类。删除本轮替代后无调用的旧顶点裁剪 helper，不修改 mmd_tools 上游。
- 所有网格先完成采样才写 ShapeKey；副本在 finally 清理，ShapeKey 写入异常恢复已更新坐标/relative_key 并撤销新增 ShapeKey。原工程未打开、未保存；不存在本轮临时 blend/导出文件。
- 新增永久 `tests/bone_conversion_isolation_blender.py`，覆盖非零其他 ShapeKey、Pose/driver/constraint、宿主骨骼/顶点/组合 Morph 同时开启（实际顶点值 1.5）、目标旋转+缩放+位移、无权重顶点、重复转换、Pose 模式、无活动对象、异常清理与写回回滚；Blender 4.4.3 通过。既有 Morph 编辑器及骨骼缩放回归通过，本地化 5 项通过。未做用户工程 GUI 点击验收；真实 Blender 用户环境的既有无关 addon 退出异常不计为本功能验收。
- 继续 v1.0.3-dev，已核实真实 Blender 4.4 addon Junction 指向仓库，重启生效；仅本地提交、不 push/tag/打包，既存 ABI5 DLL 修改保留且排除提交。

## 2026-09-09 - v1.0.3-dev 材质列表孤立对象、强制名称同步与 Morph 引用恢复

- 真实工程不保存复现：刷新前后均为 45 项、103 个材质 datablock，额外项来自仍 parent 到模型骨架但已不属于任何 Scene 的旧 Mesh，并非刷新新建材质。旧材质占据 MMD 原名，现用材质直接改名被 Blender 追加后缀；多个材质 Morph 仍指向旧材质与旧 Mesh，现有运行时只按模型内 pointer/Blender 名匹配而失效。
- `mmd_material_order.py` 与 Morph 的模型材质收集排除不属于模型所在 Scene 的 Mesh；正常隐藏、渲染关闭和其它 View Layer 内仍链接到 Scene 的对象不因可见性被排除。只修正收集边界，不删除孤立 Mesh、旧材质或用户其它资产。
- MMD → Blender 名称同步使用 Blender 4.4 `ID.rename(mode="ALWAYS")`，现用目标材质优先取得完整 MMD 日文名；原占名材质保留并由 Blender 改为可用后缀名。多个同步目标请求同名时只有首项能使用完整名，不能违反 Blender 全局唯一名称约束。同步前先恢复本模型 Morph 引用，不让占名者改名破坏旧引用线索。
- `mmd_morph_editor.py` 优先保持模型内有效材质 pointer；失效引用按 Blender 名或旧材质 MMD 日文名在本模型内唯一匹配。多义匹配不猜测，明确的未解析材质 ID 不降级为“全部材质”。查看器刷新、Morph 编辑器刷新及名称同步修复 pointer、material ID 和相关 Mesh，运行时匹配也支持此规则。材质 Morph 详情新增 MMD 材质名行，可查看/修改目标材质的 MMD 名；原 Blender 材质选择行保留。
- 新增 `tests/material_identity_blender.py` 覆盖孤立对象过滤、连续刷新零材质新增、旧引用恢复、Alpha 1/0 实际输出桥切换、强制占名及保留旧材质、再次改名保持 pointer、MMD 名兜底、歧义不绑定、全部材质哨兵和正常隐藏对象保留。真实工程回归刷新稳定 44 项，所有非空 Morph 材质引用唯一恢复，44 个材质同步后均使用完整 MMD 名；对应显示 Morph 的输出桥 Opacity 从 `[0,0]` 变为 `[1,1]`。原工程未保存。
- 本地化 5 项通过，Blender 4.4.3 新增材质 identity 回归、既有材质顺序及 Morph 编辑器回归通过；i18n 与骨骼缩放回归亦通过。未进行 GUI 点击验收；临时探针删除命令被运行环境拒绝，已集中留在 `_temporary_cleanup/material-diagnosis/`，永久合成回归保留。继续使用真实 Blender 4.4 的 1.0.3-dev Junction；不打包、不 push、不发布，既存 ABI5 DLL 修改原样排除。

## 2026-09-09 - v1.0.3-dev 骨骼 Morph 姿态与缩放附属文件

- 新增宿主模块 `mmd_bone_morph_scale.py` 与独立 JSON 协议模块 `morph_sidecar.py`；不改 mmd_tools 源码、PMX 骨骼二进制布局或模型注释，不修改任何 DLL。保留工作树原有未提交 ABI5 DLL，绝不纳入本轮提交。
- 骨骼 Tab 新增“将当前活动姿势保存”、缩放 XYZ 与“导入骨骼 Morph 缩放”。一键收集非默认局部位移/旋转/缩放，父级优先，同名更新；不抓取操作历史或仅由父级/constraint 产生的求值变化。普通加号捕获活动骨骼全部变换并更新已有同名条目，无活动骨骼仍可加空项；更新、编辑、查看、应用与清除配套支持缩放。RNA 扩展保存于 `.blend`，旧条目默认为 `(1,1,1)`。
- 缩放预览使用独立 TRANSFORM constraint，单 Morph 为 `1 + weight * (scale - 1)`，多 Morph 按乘法组合；复用现有 bind 目标，但不改原 bind bone 的缩放，不写用户 Pose scale/Action。群组有效权重接入原有求值路径，帧回调仅更新已存在约束；结构增删遵守安全 timer 门禁，卸载删除自有约束并恢复 hooks。已有 runtime 下新增/删除骨骼条目会重建绑定，操作后恢复原活动对象、骨骼及 Pose 模式。
- PMX 成功导出后按最终序列化的 Morph/骨骼身份生成 `<文件主名>.Morph.json`，仅保存非单位缩放。完整与 Shadow 快速导出均支持，覆盖写入采用同目录临时文件+原子替换；无扩展时删除已有本协议 JSON，拒绝误删其它格式文件。PMX 写入失败不更新 JSON；JSON 更新失败明确报出 PMX 已保存。
- 导入 PMX 自动查找同名 JSON；手动补导入允许任意名字/路径。按日文名及英文名共同唯一匹配 Morph/骨骼，索引仅留作导出证据，不依赖索引猜测重排后的对象；重复/缺失匹配跳过，非法 JSON 整体拒绝但自动导入不阻断标准模型。未涉及的缩放、位移/旋转和模型说明不改动。骨骼 Tab 展示自动补导入结果。
- 验证：21 项 sidecar/catalog/updater pytest 通过；Blender 4.4.3 新增 `bone_morph_scale_blender.py` 覆盖层级/去重、Euler 保存、加号/更新/编辑/查看/清除、半权重/负权重/负缩放/群组、Pose 通道无污染、完整与实际 fast Shadow 导出、JSON 覆盖/清理、同步改名自动回读、任意名重复补导入/错误匹配/非法格式、标准位移旋转和注释不变、blend 重开持久化及卸载/重注册。既有 Morph regression、headless smoke、i18n smoke、updater smoke 全部通过；未进行 MMD/PMX Editor GUI 实机测试。测试生成文件由 TemporaryDirectory 清理。
- 发布/安装：版本从正式 1.0.2 切换为 1.0.3-dev，真实 Blender 4.4 恢复源码 Junction，保留之前正式安装备份；重启/Reload Scripts 后生效。同步英文简报和双语手册，本轮仅本地提交，不打 ZIP、不 tag、不 push、不发布。

## 2026-09-07 - v1.0.2 正式版发布

- 按用户当前授权向 AliciaSource/MMD-Station 推送并发布正式 v1.0.2；将 PRERELEASE 设为 None，保留 1.0.2 版本及现有双语手册，英文 Release notes 描述按需 DLL、原生后台烘焙隔离、Morph 延迟结构初始化与线程 RNA 隔离，并明确第三方覆盖边界。
- 发布前重新通过 21 项离线回归与 HEAD 安全扫描。实现轮的 16 组预览/顺序网格烘焙及 mmd_tools 原生刚体 GUI 入口已通过；正式 tag 打包后另作安装与烘焙验证。
- 从精确 v1.0.2 tag 打包并上传 Release ZIP；本地真实 Blender 4.4 安装切换为独立正式版目录，不在发布完成后自动开启下一版 dev，不改其它插件或用户工程。既存未提交 ABI5 DLL 改动仍留仓库、不纳入 Release。

## 2026-09-07 - v1.0.2-dev 原生烘焙隔离与 DLL 按需加载

- 取消 register 阶段的双后端 DLL preload/预热；仅在实际启动对应 MMD/PMX 求解时加载该后端，普通插件启用和 mmd_tools 原生刚体烘焙均不加载自带求解 DLL。未改任何 DLL 或 ABI；既存未提交 ABI5 改动保持原样。
- 新增 execution_guard：先检查 Python 主线程，再读取 WindowManager.is_interface_locked。原生后台烘焙锁定期间，物理预览、IK frame/depsgraph 回调、代理同步、Morph 迁移/刷新/UV 预览、模型 ID 初始化等避免访问或写回场景；预览保留 session，恢复时重置时间采样基准而非把烘焙耗时补进模拟。自身 modal bake 在外部锁定期间暂停，骨骼 Action 与网格 Point Cache 仍分开、顺序执行。
- Morph frame handler 只使用已准备的绑定/材质桥，首次结构初始化排到安全 timer；Shadow 缓存遇到不安全回调只作 Python 缓存失效。更新检查回调经队列回到主线程，pre-release 偏好预先采样为 bool；多模型求解线程同样只接收主线程采样的 substeps，不读取 RNA。
- 新增 native_bake_isolation_blender.py：同一 MMD 模型、带 Armature modifier 和完整顶点权重的 Cloth/Soft Body 网格，覆盖 MMD/PMX 两后端、实时预览开启与骨骼烘焙后再烘焙网格两种顺序。8 组 headless 与 8 组真实 GUI INVOKE_DEFAULT 后台烘焙通过；GUI 每组 preview 均观察到 2-4 次 locked timer，锁定时零 preview tick，之后恢复；断言 cache.is_baked、Action 曲线不变、Modifier 不变、停止预览不清除网格缓存。另用 mmd_tools.ptcache_rigid_body_bake 真实 GUI 入口验证原生刚体缓存通过且 DLL 加载列表为空。
- 21 项离线回归通过；真实 Blender 4.4.3 的 headless_smoke、mmd_morph_editor_regression、physics_bake_regression、updater_blender_smoke、i18n_blender_smoke 均通过。测试最初的 factory-startup Morph 用例依赖中文 locale，随后在真实用户偏好进程重跑通过，未保存偏好或关闭用户窗口。临时 JSON/场景与本轮 sidecar 已清理。
- 真实 Blender 4.4 安装改为 v1.0.2-dev Junction，原 v1.0.1 独立安装已由 dev_link 备份。源码测试不等于覆盖所有第三方自定义烘焙或原反馈工程；未自动发布、未 tag、未 push、未打新 ZIP。用户保存工程并重启 Blender 后加载本次修复。

## 2026-09-07 - v1.0.1 真实 Blender 正式版安装

- 用户要求本地 Blender 使用正式版而非 dev：移除真实 Blender 4.4 addons/mmd_station 的 Junction，仅删除链接本身，随后安装已发布的 mmd_station-1.0.1.zip；仓库源码与既存 ABI5 改动保持不变。
- ZIP SHA256 与已发布 asset digest 一致，安装文件逐字节匹配 ZIP；真实用户环境 headless 验证加载路径为独立 addons 安装目录、v1.0.1/PRERELEASE=None、插件已启用、面板注册及 MMD/PMX ABI6 加载成功，输出 MMD_STATION_STABLE_INSTALL_OK。
- 未关闭用户正在运行的 Blender、未修改其它插件或保存偏好；当前 GUI 进程须保存工程后重启才能加载正式版。仓库仍保留 v1.0.2-dev，但已不桥接到 Blender；未 push、未重发 Release。

## 2026-09-07 - v1.0.2-dev 发布完成并重启开发桥接

- AliciaSource 已发布正式 v1.0.1，main/tag 指向 fab2d7b；Release 非 draft、非 prerelease，安装资产 mmd_station-1.0.1.zip，SHA256 cea7127b45512e4a791ba9e70ebf4d81585f3dd251bc0b3dbf56336343d34ce2，与 GitHub asset digest 一致。
- 精确 tag ZIP 已逐文件核对（文本允许 Git archive 的 CRLF 转换，二进制逐字节一致），并在独立解包路径断言真实加载位置、stable 版本及 ABI6；headless、updater、i18n 三项均通过。测试临时目录已清理；未执行 GUI 手动测试、未修改真实用户偏好。
- 按既有规则自动切换 v1.0.2-dev、重置 Unreleased 简报、恢复真实 Blender 4.4 源码 Junction。开发迭代仅本地 commit，不追加推送；既存 ABI5 DLL 未提交改动保持原样。

## 2026-09-07 - v1.0.1 正式发布准备

- 按用户授权发布到 AliciaSource/MMD-Station；版本设为 1.0.1 stable，保留英文与简体中文手册，更新器 smoke 改为根据版本元数据验证，避免硬编码 dev 版本。
- 发布前 13 项 catalog/updater/security 单测、安全扫描及 Blender 4.4.3 headless、updater、i18n、材质顺序回归通过。真实用户环境已启用插件，手工 register 型测试须先在当前测试进程 disable，未保存或修改用户偏好。未执行 GUI 手工验收。
- 既存未提交 mmd_physics_solver_mmd_abi5.dll 原样保留且不纳入发布；当前运行路径使用已提交 ABI6。从精确 v1.0.1 tag 打包，发布前验证隔离安装与 ZIP 安全扫描。

## 2026-09-03 - V1.0.1-dev 合并网格跨 View Layer 修复与乱序预合并回归

- 复现用户截图中的原始异常：MMD Root 层级仍包含 Mesh、但对象已脱离当前 View Layer 时，`mmd_tools.join_meshes` 会在 `FnContext.select_objects` 内对该对象执行 `select_set(True)`，并抛出“can't be selected because it is not in View Layer”。修复后，若当前模型正在运行物理 presentation proxy，先正常停止该模型预览并恢复被临时移出的源 Mesh；随后把仍不在当前 View Layer 的模型 Mesh 补链到 MMD Root 所在的可见 Collection，再委托原版 Join，不跳过任何模型部件。
- 强化 `tests/mmd_material_order_regression.py`：首个 Mesh 模拟已经手动合并的多材质部件，其实际槽位/面顺序为 `C, A`，其它对象提供 `B, D`，其中 `D` 对象主动从全部 Collection unlink 以稳定复现截图报错；MMD Station 保存顺序设为 `B, A, D, C`。修复前得到相同 View Layer traceback，修复后合并为一个 Mesh，材质槽严格重排成 `B, A, D, C`，四种面材质映射完整，预览临时材质仍被清除。
- Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，完整 `tests/headless_smoke.py` 输出 `MMD_STATION_SMOKE_OK`；`tests/test_i18n_catalog.py` 为 `5 passed`，`compileall` 与 `git diff --check` 通过。开发 Junction 已生效；未制作 ZIP、未 tag、未 push。

## 2026-09-03 - V1.0.1-dev 材质工具四等分布局

- 把同一行的“校对材质 ID 与物体编号”“按材质拆分（保留法向）”“合并”“形态键清理阈值”改为严格四等分；自动同步图标固定紧跟校对按钮，两者合计占第一组 `1/4`，不再夹在拆分与合并之间。
- 更新 `tests/mmd_material_order_regression.py` 的布局树契约，逐层断言 `1/4 → 剩余区域 1/3 → 剩余区域 1/2` 的四等分结构，并确认同步属性位于校对按钮右侧。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`；`tests/test_i18n_catalog.py` 为 `5 passed`，`compileall` 与 `git diff --check` 通过。开发 Junction 已生效；未制作 ZIP、未 tag、未 push。

## 2026-09-03 - V1.0.1-dev 移植 mmd_tools 合并网格并保持 PMX 材质顺序

- 在材质工具行加入“合并”按钮；该入口只要求 MMD 查看器选择一个 MMD 模型，不增加活动 Mesh、选中数量、材质数量等额外拦截。`sort_shape_keys` 继续暴露为 Operator 重做属性，实际合并仍委托官方 `mmd_tools.join_meshes`，保留其 ShapeKey 排序、Material Morph 关联刷新和无用 Mesh 数据清理。
- 材质顺序在合并发生前处理：先调用官方 `clear_temp_materials` / `clear_uv_morph_view` 清除材质与 UV Morph 预览临时数据，再把官方将选作合并目标的首个 Mesh 材质槽预置为 MMD Station 保存的 PMX 顺序，同时同步原面片材质索引；随后让原版 Join 完成唯一一次网格合并。合并后不再重排材质槽，避免二次改写 `polygon.material_index`。
- `tests/mmd_material_order_regression.py` 新增真实 Operator 回归，构造与 Mesh 名称顺序不同的 `B, A, C` PMX 材质顺序和 `_temp_material_morphs` 预览材质，断言合并后只剩一个 Mesh、材质槽为 `B, A, C`、三种面材质映射完整且临时材质已由 mmd_tools 清除；同时覆盖新按钮布局。Blender 4.4.3 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，完整 `tests/headless_smoke.py` 输出 `MMD_STATION_SMOKE_OK`；`tests/test_i18n_catalog.py` 为 `5 passed`，`compileall` 与 `git diff --check` 通过。开发 Junction 已生效；未制作 ZIP、未 tag、未 push。

## 2026-09-03 - V1.0.1-dev 按材质拆分解除 MMD Root 与多实用材质限制

- 修正对 `mmd_tools` 原版功能的过度限制：“按材质拆分（保留法向）”现在只要求活动对象是 Mesh，不再要求 MMD 查看器已选择模型、活动 Mesh 属于该模型，也不再预判至少有两个被面实际使用的材质。普通 Mesh 直接进入 `mmd_tools` 同款拆分路径；若来自 P 分离且仅一种材质被面引用、材质槽仍残留多项，该路径会继续清除未使用槽而不是提前取消。
- 只有活动 Mesh 实际属于某个 MMD Root 时，才执行 Morph unbind、临时材质/UV 预览清理、PMX 材质顺序编号、UV Morph 空组清理和 Material Morph 关联刷新；无 MMD Root 时安全跳过这些模型专属后处理，ShapeKey 清理与保留法向拆分仍正常执行。若查看器选择了其它模型，也以活动 Mesh 自身的实际 Root 为准，不再形成无关耦合。
- `tests/mmd_material_order_regression.py` 新增无 MMD Root、一个实际使用材质、三个残余材质槽的真实 Operator 回归：修复前稳定报“活动 Mesh 不属于当前 MMD 模型”，修复后返回 `FINISHED` 且材质槽收敛为唯一被面使用的材质。Blender 4.4.3 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，完整 `tests/headless_smoke.py` 输出 `MMD_STATION_SMOKE_OK`；`tests/test_i18n_catalog.py` 为 `5 passed`，`compileall` 与 `git diff --check` 通过。开发 Junction 已生效；未制作 ZIP、未 tag、未 push。

## 2026-09-03 - V1.0.1-dev Morph ShapeKey 范围按需扩展

- Morph Runtime 建立前保存模型内各 ShapeKey 的现有 `slider_min` / `slider_max`，并在 `mmd_tools` 完成轻量绑定后原值恢复，避免其 `bind()` 将所有匹配 Vertex Morph 的 ShapeKey 统一永久改成 `-10～10`。既有自定义范围同样保留，不强制覆盖成默认值。
- Morph 面板继续使用 `0～1` 软范围，点击数值仍可输入任意有符号值；只有实际计算值越过某个相关 ShapeKey 当前边界时才把该边界精确扩展到输入/展开后的值，且累计保留另一侧历史边界，例如 `0～1 → -2.5～1 → -2.5～3.25`。未涉及的 ShapeKey 不变，不触及 Morph 权重计算、MMD I/O、材质、物理或 IK。
- `tests/mmd_morph_editor_regression.py` 增加 Runtime 初始化后仍保持 `0～1`、负向与正向精确累计扩展的断言，Blender 4.4.3 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`；完整 `tests/headless_smoke.py` 输出 `MMD_STATION_SMOKE_OK`，`compileall` 与 `git diff --check` 通过。开发 Junction 已生效；未制作 ZIP、未 tag、未 push。

## 2026-08-31 - V1.0.1-dev 动作跳帧物理爆炸与穿模修复

- 用真实 `New Folder/00.blend` 导入 `TOMBOY.vmd`，执行“更新刚体 / Joint 到当前姿态”后建立跳帧播放探针。严格逐帧时 MMD DLL 的动态刚体单步位移峰值为 `3.6921`、Joint 两端分离峰值为 `3.2726`；模拟 GUI 每次跳 2 帧后分别放大到 `17.1097` 与 `13.8382`。同条件 PMX DLL 未爆炸但直接传送骨骼追踪刚体，缺少中间碰撞姿态，符合用户观察到的穿模。
- 根因在两个 Rust/Bullet 求解器的运动目标推进，而不是 IK、动作导入、姿态对齐或展示代理。之前一帧只提交骨骼追踪刚体终点，再让 Bullet 一次执行多个 fixed substep；MMD 分支由 motion state 推导出的跨帧角速度会向 Joint 链注入过大冲量，PMX 分支则把完整 transform 直接传送。现在两套 DLL 都缓存上次已应用目标与本次目标，在每个 Bullet 子步前对位置和 quaternion 做插值；Root world delta、snapshot restore 与 MMD 精确目标写入同步维护该缓存。
- Native ABI 升至 v6，运行时改用 `mmd_physics_solver_abi6.dll` / `mmd_physics_solver_mmd_abi6.dll`，避免旧进程误载 ABI v5。新增两套 Rust 回归，要求跳过一帧的一次 `1/30` 推进与两个连续 `1/60` 运动目标得到一致的 Joint 链结果。
- 真实动作回归：MMD DLL 跳 2 帧后的位移/Joint 峰值降至 `3.2321` / `2.5173`；极端跳 5 帧播放至 650 帧时 MMD 为 `6.0014` / `2.5662`，PMX 为 `5.3590` / `2.6575`，均未爆炸。Rust 两分支各 `14 passed`；`MMD_TIME_DRIVER_UNIT_OK`、Python `13 passed`、`MMD_STATION_SMOKE_OK`、`MMD_00_IK_PHYSICS_ISOLATION_OK`、`MMD_PHYSICS_POSE_ALIGNMENT_OK`、`MMD_PHYSICS_BAKE_REGRESSION_OK` 以及 PMX/MMD 双分支 `PHYSICS_ROOT_OFFSET_REGRESSION_OK` 通过。当前机器缺少项目正式构建要求的 VS2013 RTM `cl.exe 18.00.21005.1`，因此本轮 ABI v6 DLL 是供开发 Junction 验证的当前 MSVC release build，未冒充正式兼容构建；发布前必须在具备固定工具链的环境重建。未制作 ZIP、未 tag、未 push。

## 2026-08-31 - V1.0.1-dev ??????? depsgraph ????

- ?????? `New Folder/00.blend` ? `01.blend` ?????????????? 294632 ???452226 polygons?98 ????????????? 162 ? ShapeKey?solver?Pose prepare?????? ShapeKey ???????????????? depsgraph ?????? Mesh ? `11.0 ms`?98 ???????? `17.4 ms`?????????????????? modifier??????? Scene/View Layer??????? depsgraph ? UI Outliner/draw-manager ???
- ???????????? Mesh ?????? Scene ????? Collection????? Collection ??????????????????? modifier ??/????????????? Scene ?????????? datablock ???? ShapeKey??????????????? Collection????????? modifier ?????????? Collection?????????? Mesh ????????
- ?? `00.blend` ??????? 98 ???? MMD physics tick ????? `35.5 ms` ?? `25.985 ms`?????? Mesh ??? `26.546 ms`????????? 30% ??? 20%?RGBA ???? D?IK ???ShapeKey ??????????????????????????? `36.blend` ?? 74/97 ???? Mesh ????????depsgraph ?? `18.836 ms -> 9.764 ms`??? Junction ???????????????? ZIP?? tag?? push?

## 2026-08-31 - V1.0.1-dev mmd_tools ??????????????

- ???? mmd_tools????????`mmd_edge_preview` Solidify ????????? modifier???????????????????????????????????????????????????????????????
- `mmd_edge_preview` ???????????????? Mesh ?????? Join?????????? Mesh ????? mmd_tools ????????????????? polygon material index ???? `mmd_edge.*` ????`mmd_edge_preview` Vertex Group ??? Solidify?`material_offset` ??????????????? Solidify ??? modifier ???????????
- ????? `New Folder/00.blend` ???????????? 5 ??? Join ???????????????/????????94 ?? Mesh?294632 ??????? 1 ??? Mesh?98 ????????? 98 ??????????????? polygon ??????????????? mmd_tools ?????? `mmd_edge_scale` ????????????????? modifier ??/??????????????????????????????????????? Junction ???????????????? ZIP?? tag?? push?

## 2026-08-31 - V1.0.1-dev 分材质预览物理语义与性能回归修复

- 用真实 `New Folder/00.blend` 在内存中执行 Blender 原生“按材质分离”，从 1 个 Mesh 生成 98 个 Mesh 后复现上一版展示代理错误。根因不是 IK：临时第二 Armature 删除了原骨架 constraint/driver，physics 只写临时父骨，RGBA 胸部依赖的 `胸01.L` 等辅助约束链仍停在 canonical 静态姿态；`足D`/`足D++` 混合链也因此可能产生错误层级变形。上一版只测 physics driver 与干净骨架成本，没有验证最终 deform bone/网格语义，结论不充分。
- 删除 physics presentation Armature。IK、constraint/driver 和 physics output 现在始终留在同一原生 Armature，通过 IK closure 与 physics driver ownership 隔离，而不是靠复制骨架隔离。MODEL 优化仅处理 Mesh：全部只有原生 Armature modifier、没有对象动画/约束的兼容分片直接 Join 为一个代理 Mesh，不同 ShapeKey 子集恢复为并集并从对应源对象同步值。源分片仍留在原 Collection，但预览期间同时关闭小眼睛、小相机以及全部 modifier 的视图/渲染开关；停止时逐对象恢复原值。含 `UV_WARP`、额外 modifier、对象动画或约束的 Mesh 不参与不安全合并。
- 真实 `00.blend` 分材质回归保持 294632 顶点、完整 ShapeKey/Vertex Group 与唯一原 Armature modifier；98 个分片只生成 1 个代理 Mesh。MMD physics 下 `胸上2.L` 位移 `0.0112585583`、约束子骨 `胸01.L` 位移 `0.00328183009`，足 D 移动后的展示包围盒比例 `0.996803`，不再静止或炸权重。单 Mesh 与98分片代理的 depsgraph 中位为 `8.194 ms -> 8.064 ms`，完整 tick 仍处于同一性能区间。
- 真实 `36.blend` 把可证明兼容的 74/97 个源 Mesh 合并为 1 个代理 Mesh，其余复杂管线保持原样；read-only depsgraph 中位 `15.543 ms -> 11.071 ms`。该路线不再用简化 rig 换取错误数字，并保留 RGBA、UV Morph、constraint/driver 与对象级行为。开发 Junction 直接生效；真实工程均未保存，未制作 ZIP、未 tag、未 push。

## 2026-08-31 - V1.0.1-dev Morph AI 设置宿主冲突修复

- 修复 Morph AI“设置”按钮点击后报 `MMD_STATION_AddonUpdaterPreferences` 缺少 `morph_ai_api_url` 的问题。根因是 Morph AI 与宿主更新器各自注册了一套相同 `bl_idname = "mmd_station"` 的 `AddonPreferences`，后注册的更新器类成为真实 Preferences 宿主，AI 代码却仍按另一套类读取属性。
- 删除重复的 `SPX_MorphAIAddonPreferences`，把 `morph_ai_api_url`、`morph_ai_api_key`、`morph_ai_model` 合并到唯一的 `MMD_STATION_AddonUpdaterPreferences`；URL、Key 与模型源码默认值均为空，已保存的 Blender 用户首选项仍沿用相同属性标识。`_addon_preferences()` 同时增加属性契约检查，未来宿主异常时返回可读错误而不是 `AttributeError`。
- Add-ons 首选项保留 Morph AI 与更新器两组设置；更新 Blender smoke 覆盖真实生效 Preferences 的三个 AI 属性。行为边界不改变 AI 请求协议或凭据本地保存位置，不触及 Morph 翻译结果、物理、IK、MMD I/O 或更新器下载逻辑。

## 2026-08-31 - V1.0.0 GitHub AI 翻译凭据与私有端点清理

- 审计公开 GitHub 默认分支、全部可达历史、tag、Release 文本与 `mmd_station-1.0.0.zip`：未发现实际 API Key 值，但确认 Morph AI 默认服务 URL 已进入源码历史与 Release ZIP。将该 URL 从全部可达历史移除，`morph_ai_api_url` / `morph_ai_api_key` 源码默认值均保持为空，并重建同版本 Release 资产。
- 新增 `tools/security_scan.py`、仓库自带 pre-push hook 与 `tools/install_git_hooks.ps1`。每次 push 会扫描全部可达 Git blob；`pack.ps1` 会在打包前扫描 Git ref 或工作树，并在打包后再次扫描 ZIP。命中凭据或真实 AI 翻译端点时硬阻断且不保留被拒 ZIP。
- `AGENTS.md` / `CLAUDE.md` 同步加入长期规则；`.gitignore` 增加本地 secret 文件边界。行为边界仅涉及安全审计、发布/推送门禁和 AI URL 空默认值，不改变 Morph AI 请求协议、Morph 编辑、物理、IK、MMD I/O 或更新器行为。

## 2026-08-31 - V1.0.1-dev MMD IK + MMD DLL Root 快移延迟与预览重复求值修复

## 2026-08-31 - V1.0.1-dev IK/物理彻底隔离与真实预览展示代理重构

- 删除 `MmdIkPhysicsAdapter`、`physics_bridge.py`、`physics_preview/integration.py` 及全部 physics feedback/handoff 路径。MMD IK 只读取并写回自身 IK dependency closure；物理预览只从 canonical Armature 读取 authored pose，并按刚体类型驱动 physics output。开关 IK 不再暂停、切换或重建当前 `PreviewSession`、`PreviewWorld`、solver 与 generation，MMD/PMX DLL 也不再知道当前骨骼是否由 IK 兼容接管。
- MODEL 物理预览新增临时 `PhysicsPresentationProxy`：canonical Armature 始终作为动画/IK 输入；预览期间建立无 Action、无 constraint、无 driver 的干净展示 Armature，物理输出只写入该骨架，结束后删除全部临时数据并原样恢复源 Mesh。安全模型会把同骨架 Mesh 合并为单个展示 Mesh；`36.blend` 含 `UV_WARP`、ShapeKey 与对象级管线，盲目 Join 会破坏语义，因此自动保留临时分片，但仍让 97 个 Mesh 共用一副干净展示骨架。第二副骨架只在预览期间存在，不保存到工程。
- 对真实 `36.blend/合并2` 进行当前模型内逐项剖析：97 个可见 Mesh、276292 顶点、127 个 modifier、71 个 ShapeKey Mesh；额外隐藏对象不是主因。临时展示代理保持全部源顶点、材质、Vertex Group、29 个 `UV_WARP`、162 个 ShapeKey 与对象级行为，且源模型不被 Join 或改写。相同 read-only depsgraph 探针中位数由 `20.734 ms` 降至 `10.027 ms`，约降低 52%；这是 headless 直接求值证据，不冒充 GUI FPS 保证。
- 回归覆盖真实 `00.blend` 的 MMD physics + IK 开关原地隔离、MMD/PMX 两个 solver 的 IK 响应、Root Empty 快移 type-0 同 tick 追踪、真实 `07.blend` Root motion，以及真实 `36.blend` 的展示代理形态同步、canonical physics bone 零污染和完整清理恢复。开发期 Junction 直接生效；未制作 ZIP、未 tag、未 push，真实工程均未保存。

## 2026-08-30 - V1.0.1-dev 物理修复爆炸与乱飞骨骼安全姿态修复

- 修复从物理快照直接开始修复烘焙仍会整条刚体链爆炸的问题。真实 `36.blend + TOMBOY.vmd` 证明 `.mspc` 虽保存刚体变换、速度与激活状态，但不包含 Bullet contact manifold、constraint warm-start impulse 等内部求解缓存；复杂衣物链无法仅靠该快照确定性热恢复。修复烘焙现在从所属独立段的原始 `simulation_start + simulation_preroll` 完整静默重放，且禁止一个修复范围跨越两个独立烘焙状态。
- 取消把单根修正骨骼直接回灌 Bullet 刚体的高风险路径。真实模型上仅 `0.02 m` 的单骨修正就可把相邻袖摆骨放大到约 `11.4 m` 偏差；无论硬改 Transform 还是速度牵引都不足以保证高密度 Joint 链稳定。修复层现作为平滑 Action-space 姿态增量应用到确定性重放结果，首尾保持零修正，并将按钮改名为“应用修复并衔接”，不再暗示手工修正已经参与碰撞反馈。
- 物理修复层新增“恢复所选到安全姿态”：在修复范围内选择乱飞的动态物理骨骼后，插件直接取修复起点的最后干净已烘焙姿态作为安全参考；即使后续整段都已卡住或乱飞，也不会把坏掉的结束姿态再次插值回来。用户只需在附近微调再记录，无需从远处手工拖回。该操作只改当前 Pose，不覆盖原 Action，也不改刚体/Joint 对象。
- 验证：`python -m pytest -q tests/test_i18n_catalog.py` 为 `5 passed`；Blender 4.4.3 合成回归输出 `MMD_PHYSICS_BAKE_REGRESSION_OK`，覆盖安全姿态恢复、完整重放、修正记录和首尾衔接；真实 `36.blend + TOMBOY.vmd` 不保存回归中，`1–300` 烘焙后修复 `180–220`、第 `200` 帧添加 `0.02 m` 修正，全部物理骨最大位置差由爆炸时约 `11.4 m` 降到 `0.01999998 m`。开发期 Junction 直接生效；未制作 ZIP、未 tag、未 push，真实工程未保存。

## 2026-08-30 - V1.0.1-dev 正式版后自动开启开发模式与 Junction 桥接

- 建立并写入 `AGENTS.md` / `CLAUDE.md` 同步规则：每次稳定版发布后的首次本地修改，必须自动将版本切到下一 patch 的 `-dev`，重置英文 `RELEASE_NOTES_NEXT.md`，并执行 `tools/dev_link.ps1` 开启真实 Blender 4.4 开发桥接；不得等待用户再次提醒。
- 本轮以 `v1.0.0` 为稳定基线，将 `bl_info["version"]` 改为 `(1, 0, 1)`、`PRERELEASE = "dev"`，面板显示统一为 `v1.0.1-dev`。新增安全的 Junction 管理脚本：创建时保留既有真实安装为时间戳备份，移除时拒绝删除非 Junction 目录。
- `RELEASE_NOTES_NEXT.md` 已恢复为英文 `## Unreleased`，并记录本轮既有 physics-bake 初始化状态修复；开发期不产出 ZIP，不创建 tag，不进行 GitHub Release。
- 行为边界：仅改变开发版本状态、开发安装方式和维护规则；除上一笔独立提交中的 physics-bake 修复外，不改变 MMD I/O、代理、Morph、物理、IK 或更新器功能语义。
- 验证：真实 Blender 4.4 插件路径已确认为指向仓库源码的 Junction，源路径与安装路径 `_version.py` SHA-256 一致；`compileall`、`git diff --check` 通过，本地化/更新器测试为 `11 passed`，Blender 4.4.3 输出 `MMD_STATION_UPDATER_SMOKE_OK` 与 `MMD_PHYSICS_BAKE_REGRESSION_OK`，`AGENTS.md` / `CLAUDE.md` 哈希一致。

## 2026-08-30 - V1.0.0 ??????????????????

- ?????????????????????????????????????????????????????? solver ???? Scene ??????????? `simulation_start`????????????????????????????????????????????? solver?
- ????????? checkpoint ????????????? DLL ?????/Joint ?????? Armature ????????????????????? Physics Bake Action ???? checkpoint ??????????? PoseInput ????? checkpoint ???????????????????????????????
- ????????? `252` ?????? solver ???? `1` ????? UI ???????????? job ??????????? checkpoint ??? Action ????????`python -m compileall -q mmd_station`?`python -m pytest -q tests/test_i18n_catalog.py`?`5 passed`??Blender 4.4.3 `tests/physics_bake_regression.py`?`MMD_PHYSICS_BAKE_REGRESSION_OK`?? `git diff --check` ????????????? ABI??????????

## 2026-08-30 - V1.0.0 首个正式版定版与双语使用手册

- 将 `bl_info["version"]` 正式定为 `(1, 0, 0)`，`PRERELEASE=None`，面板显示 `v1.0.0`。README 改为正式 Release ZIP 安装流程，不再保留“尚无稳定版”或开发安装主路径，并加入中英使用手册入口。
- 新增 `docs/user-manual.en.md` 与 `docs/user-manual.zh-CN.md`：两份手册均提供快速目录、安装与 MMD Tools 强依赖说明、活动项/批量勾选规则、PMX/VMD/VPD I/O、代理创建与恢复、代理物理、MMD 查看器五类页面、Morph 五类编辑、显示枠、原生物理预览、分段烘焙与修复、MMD IK、自动更新、常用完整流程及故障排除。所有相对链接和目录锚点均通过脚本校验。
- `RELEASE_NOTES_NEXT.md` 定稿为英文 `v1.0.0` 首发简报，补充双语手册和 MMD Tools 必需依赖；更新器 Blender 烟测同步断言正式版本显示。
- 验证：`compileall`、`git diff --check` 通过；本地化/更新器 `pytest` 为 `11 passed`；Blender 4.4.3 输出 `MMD_STATION_I18N_BLENDER_SMOKE_OK`、`MMD_STATION_UPDATER_SMOKE_OK`、`MMD_STATION_SMOKE_OK`；working-tree ZIP 为 60 项，包含 i18n catalog 与 ABI5 native DLL 且不含 `__pycache__` / `.pyc` / runtime updater state；隔离解包安装输出 `MMD_STATION_V1_ISOLATED_INSTALL_OK`。
- 发布边界：正式资产必须从 `v1.0.0` tag 重新运行 `pack.ps1` 生成并附加到 AliciaSource GitHub Release，确保自动更新器取得的是 tag 对应 ZIP；不得使用 GitHub 自动 source archive 代替安装包。

## 2026-08-30 - V0.1.8-dev README 依赖说明修正

- 移除 README 顶部 GitHub 灰底引用样式的开发状态提示，不再把内部开发阶段作为项目首页重点展示。
- 将 MMD Tools 从“兼容安装”明确改为 MMD Station 的必需依赖，说明其承担 MMD 数据 API 与 PMX/VMD/VPD 导入导出，并加入 Blender Extensions 官方页面及 `MMD-Blender/blender_mmd_tools` GitHub 源码链接；安装步骤同步要求先安装并启用 MMD Tools。
- 仅修改英文 README 与开发日志，不改插件源码、功能、版本号或发布状态；链接已对照 MMD Tools 官方 GitHub README 当前提供的 Blender Extensions 地址确认。

## 2026-08-30 - V0.1.8-dev 架构级中英双语 UI

- 新增中央 `mmd_station/i18n/` 本地化层：保留现有中文 msgid 与全部兼容标识，通过 Blender 原生 translations 生命周期统一提供英文 catalog。`zh_HANS` / `zh_HANT`（并兼容 `zh_CN` / `zh_TW` 别名）保持当前中文 UI，其它所有 Blender locale 复用同一套英文 UI，不按语言复制功能代码或维护多套非中文界面。
- 静态 RNA 标签、按钮、enum 与 hover description 由 Blender 原生翻译；所有运行期拼接的面板文字统一经过 `iface()`，全部 operator 状态、警告与错误统一经过 `report()`。本轮只改 UI 表达边界，不改 operator id、Scene 属性、custom property、数据模型、导入导出、Morph、物理、IK 或更新器功能语义。
- 新增 `tests/test_i18n_catalog.py` 覆盖门禁：扫描整个 package 的中文字符串，任何未来 UI 新文案若缺少英文 catalog 条目会直接失败；同时禁止动态 UI 绕开 `iface()` 或 operator 直接调用 `self.report()`。新增 Blender 4.4 四 locale 烟测，实测 `zh_HANS` / `zh_HANT` 为中文、`en_US` / `ja_JP` 为英文，并覆盖静态标签、operator context、悬停描述与动态状态消息。
- 新增同步的 `AGENTS.md` / `CLAUDE.md` 项目规则与 README 英文本地化说明，确保以后新增功能默认同时完成双语，不依赖用户再次提醒；`RELEASE_NOTES_NEXT.md` 同步写入英文更新简报。版本保持 `v0.1.8-dev`，不制作正式版、不 tag、不 push。
- 验证：`python -m pytest -q tests/test_i18n_catalog.py tests/test_host_updater.py` 为 `11 passed`；Blender 4.4.3 `tests/i18n_blender_smoke.py` 输出 `MMD_STATION_I18N_BLENDER_SMOKE_OK`；综合 `tests/headless_smoke.py` 输出 `MMD_STATION_SMOKE_OK`；显示枠、物理烘焙、姿态对齐、MMD I/O、材质顺序及用户排序六项 focused regression 均输出各自 `*_OK`。`mmd_morph_editor_regression.py` 在本轮基线 commit `35a1a28` 与当前树均于同一既有 Alpha 断言失败，已用独立 worktree 对照确认不是本地化改造引入；本轮未扩大到修改既有 Morph 行为。

## 2026-08-30 - V0.1.8-dev GitHub 发布准备与宿主级自动更新器

- 新增与 Velo Tools 同路线的宿主级 `updater/`：只读取 `AliciaSource/MMD-Station` 已发布的 GitHub Releases，普通 `main` commit 不会成为更新；稳定版默认接收，pre-release 需用户显式开启。更新过程保留单份 rollback backup，支持进度反馈，并把 `*.dll` 纳入覆盖规则，避免 native solver 停留在旧版。
- MMD Station 顶层面板新增“`MMD 模型制作工具` + GitHub 按钮 + `v0.1.8-dev`”信息区；`bl_info["doc_url"]` 固定指向 Alicia 账号仓库。新增 `_version.py`，当前保持开发标记，不创建 tag 或正式 Release。
- 将根 `README.md` 改为英文，新增英文 `RELEASE_NOTES_NEXT.md`、GPL-3.0 `LICENSE` 与纯打包 `pack.ps1`；自动更新只接受未来 Release 附带的 `mmd_station-X.Y.Z.zip`。本轮不实现 UI 国际化，只在 README 明确记录当前中文 UI 与下一阶段边界。
- 验证：`tests/test_host_updater.py` 6 项通过，`python -m compileall -q mmd_station` 通过，Blender 4.4.3 `tests/updater_blender_smoke.py` 输出 `MMD_STATION_UPDATER_SMOKE_OK`，working-tree package 内容校验为 58 项且不含 runtime updater state/`__pycache__`。未制作正式 ZIP、未 tag、未创建 Release。

## 2026-08-30 - V0.1.8 Blender 文件启动阶段 N 面板注册恢复

- 修复启用 MMD Station 后 N 面板整体消失的问题。新增的物理缓存服务在 Blender 从用户偏好自动注册插件、但当前 `.blend` 尚未完成载入时立即遍历 `bpy.data.actions`；此时 `bpy.data` 是受限的 `_RestrictData`，异常会中断 `mmd_station.register()`，导致包括 Morph 编辑器在内的全部面板与属性均未注册。
- `physics_preview/cache.py` 现在仍将 sidecar 扫描挂到 `load_post`，同时把“已打开工程中启用插件”的首次扫描改为可重试 Timer；遇到 `_RestrictData` 时延后 `0.1 s`，其它 `AttributeError` 仍正常抛出。卸载插件时同步注销未执行的 Timer，避免残留回调。
- `py_compile` 通过；以正常用户启动路径无保存加载 `D:\MMD\模型\Alicia\鳴潮-達妮婭\Show\00.blend`，输出 `MMD_STATION_PANEL_REGISTERED=True`，且不再出现 MMD Station 注册异常。源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 ???????????????

- ??????????? Action ????????????????????????????????????? 10 ??????????? world/interpolation transform??????force/torque?activation state ???????????Action ???? cache ID?????????????????? `<??>.blend.mmd_station_cache\physics\<cache-id>.mspc`?`Save`?`Save As` ? `load_post` ?????/????????? Blender ????????????????????????????????????Action????????/Joint ???? Action ?????????????????????????????????? `.blend`?????????????? 9 ?????????????? `.blend` ????????????
- Native PMX ? MMD ??? ABI ????? v5??? opaque snapshot size/write/restore ? body guide ???Bullet ?????????????????????? broadphase/AABB????????? Blender ??? DLL??????? ABI ?????? `mmd_physics_solver_abi5.dll` / `mmd_physics_solver_mmd_abi5.dll`?? ABI ????????????????????/?????? ABI v5?PMX VS2013 RTM ? MMD VC10 SP1 ??????SHA256 ??? `0EDB4E89F8019366F2C8A0C77C409A4836AE2ACBD6944CB0315B6A13463D84F6`?`73F9A52348686A37CA820FE1B97C8033C9DC91B157463B781CBDC628899D9D22`?
- ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????? modal ??????????????????????????????????
- `tests/physics_bake_regression.py` ??????????/?????????????????Pose Mode ????????????????????????????? UI?PMX/MMD ?? DLL????? `Save -> open_mainfile` ?? sidecar ????????? `MMD_PHYSICS_BAKE_REGRESSION_OK`??? Rust release ??? `13/13` ???`MMD_PHYSICS_POSE_ALIGNMENT_OK` ? `PHYSICS_ROOT_OFFSET_REGRESSION_OK` ?????????????????????????????????????????? Bullet manifold/constraint warm-start ?? bit ?? world ???????? V0.1.8??? Blender 4.4 ?????? Junction???? ZIP?? push?????????? DLL ? Blender ? Reload Scripts ?????? ABI v5?


## 2026-08-30 - V0.1.8 描边材质被普通材质复位覆盖的 Alpha 修复

- 修复 Material Morph 已明确提供 `edge_color[3] = -1`，但自动补入 `Morph Output` 的 `mmd_edge.*` 描边材质最终仍显示 `Opacity = 1` 的问题。根因是 `_model_materials()` 把 MMD edge preview Mesh 使用的 `mmd_edge.*` 材质也收进普通基础材质集合：同一轮先按对应基础材质的 Edge Alpha 把描边更新为 `0`，随后普通材质的中性复位路径又把同一描边覆盖回 `1`。
- `_model_materials()` 现在排除以 `mmd_edge.` 命名或持有 `spx_morph_edge_parent_uid` 的描边预览材质。基础材质继续按 `diffuse_color[3]` 独立计算，描边继续按 `edge_color[3]` 独立计算；已撤销本轮早先错误加入的“描边透明度不得高于本体透明度”约束，不再用 Diffuse Alpha 干预 Edge Alpha。
- `tests/mmd_morph_editor_regression.py` 现在把描边材质也放入模型材质槽，复现真实工程中的二次复位覆盖，并同时断言 `diffuse A=-1 / edge A=-1` 各自生效及 `diffuse A=-1 / edge A=0` 时描边保持可见。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 通过。对 `D:\MMD\模型\Alicia\鳴潮-達妮婭\Show\00.blend` 做了不保存的内存验证：`袖子-*` 的 `袖子1` 数据确认为 Diffuse/Edge Alpha 均 `-1`，滑块置 `1` 后本体与 `mmd_edge.袖子1` 的 `Morph Output / Opacity` 均为 `0`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 重复姿态对齐的物理烘焙回灌与刚体世界覆盖修复

- 修复“第 1 帧更新刚体 / Joint 正常，切到其它帧再次更新后位置爆炸”。问题不是第二次矩阵在第一次结果上累乘，而是当前活动 Action 已经是 `· Physics Bake` 时，旧实现又把烘焙得到的动态骨骼姿态当成物理输入：一份骨骼 Action 并不保存每个刚体的完整求解状态，尤其是多个刚体、交叉 Joint 与同骨骼绑定关系无法从烘焙骨骼反推出唯一且满足全部约束的刚体图；直接逐骨骼回灌会形成二次物理变换和互相冲突的 Joint 框架。切回源 Action 时，Blender 还会保留源 Action 未写曲线的动态骨骼通道，导致烘焙姿态残留；同时场景已有的 Blender `RigidBodyWorld` 会在 depsgraph 更新后重新覆盖刚写入的对象矩阵。
- `align_model_physics_to_pose()` 现在检测 MMD Station 生成的物理烘焙 Action，并通过 `mmd_station_physics_source_uid` 自动切回对应源 Action；切换前清空动态刚体绑定骨骼的 `matrix_basis`，随后在同一帧重新求值源 Action，因此源 Action 中确实存在的手工关键帧会重新应用，而烘焙 Action 独有的物理通道不会残留。若源 Action 已被删除则直接终止，不再拿不完整的烘焙结果冒险重建物理图。
- Rest 参考矩阵不再读取可能已被 Bullet/约束求值污染的 `Object.matrix_world`，而是沿对象父级用 `matrix_basis + matrix_parent_inverse` 重建作者态世界矩阵；这保留模型原始刚体与 Joint 的偏心、偏转和尺寸关系，也不会把当前帧 Blender 刚体缓存误存成新的 Rest。若场景已有启用的 Blender `RigidBodyWorld`，操作会将其停用并保持停用，避免下一次刷新再次抢回刚体控制权；MMD Station 的 Rust 预览/烘焙不依赖该 world。Operator 完成提示会明确说明“已切回源 Action”和“已停用 Blender Rigid Body World”。
- `tests/physics_pose_alignment_regression.py` 新增生成物理烘焙 Action、故意污染动态骨骼曲线、在两个帧重复点击、自动回源、源关键帧重新求值及 Blender world 停用回归。Blender 4.4.3 输出 `MMD_PHYSICS_POSE_ALIGNMENT_OK`。真实 `36.blend + TOMBOY.vmd` 另做不保存验证：快速烘焙 `1–250` 后分别在帧 `1` 与 `250` 从烘焙 Action 重复执行更新，均自动回到 `TOMBOY_bone`；修复前帧 `250` 两端推算的 Joint 框架最大位置/旋转冲突达到 `6.4655 m / 5.6894 rad`，修复后帧 `1` 为 `1.1203e-6 m / 0 rad`、帧 `250` 为 `6.7501e-7 m / 0 rad`，场景 Blender world 保持停用。版本保持 V0.1.8，真实工程未保存，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 Rest Pose 到当前 Pose 的刚体与 Joint 对齐

- 物理预览面板新增“更新刚体 / Joint 到当前姿态”按钮。整个模型模式按现有勾选模型批量执行，当前代理模式作用于其 MMD Root；物理预览或物理烘焙运行时禁用，避免在 solver 使用对象矩阵期间改写输入。
- 对齐不是把刚体中心强制吸到骨骼中心：插件先在 Armature `REST` 状态取得并持久保存每个刚体、Joint 的参考世界矩阵，再用 `Pose Bone World × Rest Bone World⁻¹` 得到骨骼姿态增量；带骨骼刚体应用该增量，因此完整保留原有平移、旋转与尺度偏移。Joint 沿用 MMD/mmd_tools 的确定性语义，优先跟随 `object1` 的姿态增量、不可用时跟随 `object2`，同样保留原始 Joint 框架偏移；无有效骨骼的刚体和两端均无有效增量的 Joint 保持不变。
- 首次执行会把 Rest 参考矩阵写入对象自定义属性，后续切换动作或修改 Keyframe 后再次点击仍从同一 Rest Pose 计算，不会在上一次 Pose 结果上累积漂移；若 Armature 当前明确处于 `REST`，再次执行会刷新参考矩阵。已有 Blender RigidBodyWorld 时会在矩阵写入期间暂时停用并原样恢复 world，以清除旧求值缓存，防止动态刚体在 depsgraph 更新后弹回旧位置，不改变 MMD 刚体类型。
- 新增 `tests/physics_pose_alignment_regression.py`，覆盖偏心/偏转刚体、Joint、无骨骼刚体、二次换姿态无累积以及真实 Operator 注册。Blender 4.4.3 输出 `MMD_PHYSICS_POSE_ALIGNMENT_OK`、`MMD_PHYSICS_BAKE_REGRESSION_OK` 与 `MMD_TIME_DRIVER_UNIT_OK`。
- 对真实 `D:\MMD\模型\Alicia\鳴潮-達妮婭\達妮婭\36.blend` + `TOMBOY.vmd` 帧 `1` 做不保存验证：更新 `508` 个刚体与 `701` 个 Joint，全部对象实际发生 Pose 位移；刚体世界矩阵最大误差 `4.35114e-06`、骨骼相对偏移最大误差 `4.52623e-06`、Joint 最大误差 `2.65241e-06`，Armature Pose 与 Action 未被修改。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不保存测试工程、不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 续接物理烘焙初态与预热重放修复

- 修复“续接上一段”从首个新帧开始爆炸的问题。根因有两处：快速烘焙副本此前继承了当前输出 Action 已求解的动态骨骼姿态；同时续接虽然从最早 `simulation_start` 重放，却遗漏首段独立烘焙的预热步数，导致续接求解器状态与首段末尾状态并不一致。快速烘焙现在会先把副本中全部动态刚体绑定骨骼恢复为确定性初态，再应用源 Action；续接会继承并完整重放首段 `simulation_preroll`，不再把带速度状态的物理链仅按末帧姿态硬接。
- 临时模型复制不再把当前 depsgraph 求值后的 `matrix_world` 强写回副本对象；保留 `Object.copy()` 得到的本地变换、父级逆矩阵和重映射后的副本层级，避免把上一段当前帧的刚体/Joint 求值旋转固化成下一次 solver 的初始对象变换。新 segment 持久记录 `simulation_preroll`，旧 segment 则从最早独立段的既有 `preroll` 向后兼容恢复，因此已有正常的 `1–250` 首段无需删除。
- `tests/physics_bake_regression.py` 新增无源 Action 曲线的动态物理骨、故意污染本体物理姿态、预热继承及“分段续接结果等于一次性整段结果”的回归。Blender 4.4.3 合成回归输出 `MMD_PHYSICS_BAKE_REGRESSION_OK`，`MMD_TIME_DRIVER_UNIT_OK`、`compileall` 与 `git diff --check` 通过。
- 对真实 `D:\MMD\模型\Alicia\鳴潮-達妮婭\達妮婭\36.blend` + `TOMBOY.vmd` 做不保存验证：`1–250` 独立快速烘焙（预热 `30`）后续接 `251–300`，再与一次性 `1–300` 的 oracle 逐值比较；`439` 个动态骨骼、`153650` 个 location/rotation 分量最大差值为 `0.0`，续接副本初态污染从 `0.466153` 归零为 `0.0`。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不保存测试工程、不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 VMD Morph 滑块原生动画颜色修复

- 修复 VMD Morph 已联动但中央滑块始终保持蓝色的问题。根因是导入桥此前把 F-Curve 写到可求值的稳定 UID 路径 `spx_morph_states["uid"].value`，而 Blender 4.4 的 UI animation decoration 实际只按该 `CollectionProperty` 项目的原生索引路径 `spx_morph_states[index].value` 判断绿色、黄色与橘色状态；所以动画数值会变化，UI 却不认为当前滑块拥有 F-Curve，只有用户手动按 `I` 生成索引路径后才变色。
- 中央 Morph 动画现统一使用 `state.path_from_id("value")` 返回的 Blender 原生索引路径；Morph 新增、删除、排序或刷新导致状态索引变化时，会按稳定 UID 把 Root 当前 Action 与 NLA Action 中的 F-Curve 重映射到新索引。升级前已存在的 UID 路径和用户后来手动 `I` 生成的索引路径会自动合并为一条 UI 原生曲线，同帧以用户手动键值为准，避免重复 F-Curve 或关键帧错绑到其它 Morph。
- 插件注册、Reload Scripts 与 `.blend` `load_post` 现在都会扫描并接管当前工程中已存在的 VMD Morph 动画；无需重新导入即可把旧 UID 曲线转换成会变色的滑块曲线，仍留在 mmd_tools ShapeKey Action 的旧动画也会迁移后清除重复源曲线。回归覆盖 Keyframe 当前帧黄色、非 Keyframe 动画帧绿色、手动偏离曲线值橘色，以及旧 UID 曲线 + 手动索引曲线合并。
- Blender 4.4.3 对真实 `D:\MMD\模型\Alicia\鳴潮-達妮婭\達妮婭\36.blend` 和 `TOMBOY.vmd` 做不保存验证：生产 hook 为 `_import_vmd_execute`，导入得到 `32` 条中央 Morph F-Curve；`まばたき` 的 UI 原生路径为 `spx_morph_states[228].value`，成功取得 `502` 个 Keyframe，并逐项确认帧 `1` 为黄色条件、帧 `2` 为绿色条件、手动偏移后为橘色条件。`MMD_MORPH_EDITOR_REGRESSION_OK`、全包 `compileall` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不保存测试工程、不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 VMD Morph 滑块双向关键帧桥接

- MMD Station 注册时会立即安装 VMD I/O hook（仅在 `mmd_tools` 尚不可导入时才定时重试），并在 VMD 导入后把 `mmd_tools` 生成的 ShapeKey F-Curve 自动迁移到 MMD Root 的稳定 UID 路径 `spx_morph_states["..."].value`，因此中央 Morph 滑块会直接显示并编辑导入的 Keyframe；在数值滑块上按 `I` 新增的关键帧也使用同一条曲线，Vertex、Material、Bone、UV 与 Group Morph 共用一致入口。
- 新增 VMD 导出反向桥接：调用原 `mmd_tools.export_vmd` 前，把当前 Root Action 中的中央滑块曲线临时映射为 exporter 原生识别的 ShapeKey `value` F-Curve，保留帧值、插值、Handle、Easing 与 F-Curve Modifier；导出后恢复原 Action、占位 ShapeKey mute 状态并清除临时 Action/临时 ShapeKey，不修改上游源码，也不在 `.blend` 中留下双份动画数据。Root 活动时保留原版“骨骼 + Morph”语义，模型 Mesh 活动时保留“Morph only”，Armature 活动时仍只导出骨骼。
- `tests/mmd_morph_editor_regression.py` 新增真实 `mmd_tools` 双向往返：五类 Morph 的中央曲线导出 VMD、重新导入中央滑块、再次导出，逐 Morph 比较帧号与权重完全一致，并断言 ShapeKey Action、mute 和临时 Action 均恢复。Blender 4.4.3 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`、`MMD_IO_REGRESSION_OK`；全包 `compileall` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 ?????????????

- ????????? Pose ???????????????`????` ?????????? MMD ???????? Root ???????Armature ???? data?Mesh ?????? data????????????? Object/Pose constraint ? `target` / `pole_target`????? Joint `rigid_body_constraint.object1/object2` ?????????Action ?????? Pose ?????/Joint ????????????????? Pose ???????????????????
- ??????? Action ????? Physics Bake Action????????????????????? F-Curve ??????? Action????????????????? solver??????? Object/Armature data/Collection?????????? Pose ????????`????` ?????????????????????
- ??????????????????????????????? modal ???? `250 ms` ???????????????????????????????????????????
- `tests/physics_bake_regression.py` ???? Armature Action ????? Pose ????????????? Collection/Objects ??????????????? `36.blend + TOMBOY.vmd`?Root `??2` ??? MMD DLL ???????? `1314` ? Object?session ? `508` ?? / `701` Joint / `701` ?? Joint descriptor????? `1.5858 s`?`60` ??? `4.5228 s`?? `13.27 ?/?`?????????? Pose ??????? `0.0`?? Joint ?????????? `.MMD Station Bake*` ?? Collection?`MMD_PHYSICS_BAKE_REGRESSION_OK`?`MMD_TIME_DRIVER_UNIT_OK`?`compileall` ? `git diff --check` ??????? V0.1.8??? Junction ???????? ZIP?? push?

## 2026-08-30 - V0.1.8 ????????????

- ???????????????? MMD ??????????????????? Root?Armature?Mesh???? Joint ????????????????????????????? Pose/Object matrix ????? View3D ?????????????????????`????` ?????????????????????
- ?????????????????? depsgraph ???????????????? `view_layer.update()` ? `scene.frame_set()`????? `250 ms` ?????? `1 s`????????????????????????????????
- `tests/physics_bake_regression.py` ?????????? Root/Armature ??????? `36.blend + TOMBOY.vmd`?Root `??2`?`508` ?? / `701` Joint????? modal ????`60` ?????4 ?????????? `4.9097 s`?? `12.22 ?/?`??????????????? Pose ????????`MMD_PHYSICS_BAKE_REGRESSION_OK`?`MMD_TIME_DRIVER_UNIT_OK`?`compileall` ? `git diff --check` ??????? V0.1.8??? Junction ???????? ZIP?? push?

## 2026-08-30 - V0.1.8 MMD 导出路径与文件名记忆修复

- 修复 MMD Station 的 PMX/VMD/VPD 导出代理在二次调用 `mmd_tools` 文件选择器时丢失目标 operator 上一次 `filepath` 的问题；导出按钮现在会从 Blender 的 `operator_properties_last()` 读取对应 `mmd_tools` 导出记录，并在打开文件浏览器时回填非空路径，因此同一 Blender 会话内再次导出会沿用上一次目录与文件名，而不是重置为当前 `.blend` 名。
- 导入代理保持原行为，不跨类型复用路径；未找到历史导出记录时仍由上游 `ExportHelper` 使用默认初始化。`tests/mmd_io_regression.py` 覆盖三个导出入口、非空路径回填、空历史回退与导入隔离，Blender 4.4.3 输出 `MMD_IO_REGRESSION_OK`；全包 `compileall` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 ????????????????????

- ?????????????????????????????? `scene.frame_set()`???????? Action ? F-Curve ?????? Armature??????????? MMD Root ???????????? `250 ms` ?????????????????????????????????????????????????
- ??????????????????????? `1`??? `30` ??? `-29?0`??? VMD/MMD IK ??????????????????????????????????????????????????????segment ? `simulation_start` ?????????????????????????????
- ?? Esc/?????????????BakeJob ?????????? Root/Armature matrix??? Pose Bone `matrix_basis`???/Joint matrix?? Action???? View Layer ???????????????????????????? Action?????? MMD IK bridge ?????????????????????????? Pose ?????????????? VMD frame?
- ?????????????????????????????????????????? `0?2 ?/?`?????????? Armature ???? Action ??????? depsgraph ???
- `tests/physics_bake_regression.py` ???????????? Action ?????? Pose/Action/?/????????Blender 4.4.3 ?? `MMD_PHYSICS_BAKE_REGRESSION_OK`?`MMD_TIME_DRIVER_UNIT_OK`?`compileall`?`git diff --check` ??????????? `36.blend`?`TOMBOY.vmd`?Root `??2`?`508` ?? / `701` Joint????????? MMD DLL ???`60` ?????? `4.6249 s`?? `12.97 ?/?`?????????? `1?30`??? `30`?`simulation_start=1`??? Action/segment ?????????????????? V0.1.8??? Blender 4.4 ???? Junction ???????????????? ZIP?? push?

## 2026-08-30 - V0.1.8 未收录空 Morph 导出相对位置修复

- 修复 `mmd_tools` PMX 导出按“表情”显示枠重排后，把所有未收录 Morph 统一追加到 Morph 列表底部的问题。MMD Station 现在仍以显示枠顺序作为已收录 Morph 的主顺序，但会按各 Morph 类型的原始 collection 顺序把未收录项重新锚定：位于两个已收录项之间的空分隔 Morph 跟随其后方 Morph，位于末尾的未收录项跟随该类型最后一个已收录项；因此 `--衣服消失--` 这类空分隔项无需加入显示枠，也能继续位于对应 `袖子-*` 一类条目的上方。
- 新增独立导出代理 `mmd_export_morph_order.py`，只挂载 `mmd_tools` 的 Morph 索引映射，不修改上游源码、不改变 Blender 内 Morph collection 或显示枠成员；同一规则同时覆盖常规完整 PMX 导出、Group Morph 引用、显示枠引用及 MMD Station PMX Shadow 快速导出。完全没有同类型显示枠锚点的 Morph 继续按原顺序保守放在已锚定项之后。
- `tests/mmd_shadow_regression.py` 新增反向显示枠顺序与中间空分隔项回归，PMX 回读确认完整导出和 Shadow 快速导出均保持 `Skirt1-* < --Section-- < Sleeve-*`；Blender 4.4.3 输出 `MMD_SHADOW_REGRESSION_OK`、`MMD_DISPLAY_FRAME_REGRESSION_OK`、`MMD_EXPORT_PROFILE_REGRESSION_OK`，全包 `py_compile` 与 `git diff --check` 通过。另对截图对应的 `D:\MMD\模型\Alicia\鳴潮-達妮婭\達妮婭\36.blend` 做不保存的真实完整导出，PMX 回读确认 `--衣服消失--` 为索引 `25`、`袖子-*` 为索引 `26`，相邻顺序为 `見開く < --衣服消失-- < 袖子-* < 裙子1-*`。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-30 - V0.1.8 分 Action 分段物理烘焙与非阻塞双模式

- 物理预览页新增 `快速烘焙` 与 `播放烘焙`：前者关闭刚体/Joint 调试回写和 View3D redraw，并以最多约 `40 ms` 的主线程时间片连续求解后主动归还 UI；后者按场景 FPS 逐帧推进、显示最终物理姿态并同步采样，机器不足目标帧率时只降低播放速度、不跳过待烘焙帧。两者均使用持续进度框显示阶段、当前帧、已完成帧、平均速度与 ETA，支持 `Esc` / 右键取消；取消或失败会恢复原 Action、原时间帧和启动姿态，不提交半成品。
- 每个源 Action 通过稳定 UID 绑定独立的 `<源动作> · Physics Bake` 输出 Action，原 Action 不写入；只采样实际物理驱动骨骼的 `location` 与当前 rotation mode，Quaternion 连续修正符号，最后按 F-Curve 批量重建并写入每帧 `LINEAR` keyframe。输出 Action 持久记录已完成区间、模式、衔接方式、预热、速度与骨骼清单；UI 可逐段删除或清空当前动作全部烘焙，不同源 Action 的结果互不混用。
- 支持“独立烘焙”和“续接上一段”。独立段默认预热 `30` 帧且预热只求解不写键；续接段要求上一有效区间恰好结束于新起点前一帧，并从该链最早的 `simulation_start` 确定性静默重放后再写新范围，避免仅恢复末尾骨骼姿势而丢失刚体速度。删除或替换前段后，依赖它的后续续接段标记为“已过期”；当前 native ABI 尚无完整 Bullet state snapshot，因此跨会话续接优先正确性而不是伪快照。
- 新增 `tests/physics_bake_regression.py`，以真实 `mmd_tools` MMD Root、静态/动态刚体和 PMX/MMD 两套 DLL 覆盖快速/播放两种核心步进、Action 隔离、批量 F-Curve、`1–3` 独立段 + `4–5` 续接重放、区间绘制、逐段删除后过期传播及清空恢复源 Action，Blender 4.4.3 输出 `MMD_PHYSICS_BAKE_REGRESSION_OK`；`MMD_TIME_DRIVER_UNIT_OK`、全包 `py_compile` 与 `git diff --check` 通过。
- 对未保存的 `D:\MMD\模型\Alicia\Endfield-Rossi\洛茜\07.blend` 做 30 帧快速烘焙基准：Root `合并`、`339` 刚体、`471` Joint，包含 session 建立和最终批量写 Action 的总耗时 `1.3058 s`，即 `22.974 帧/秒`；烘焙区间自身记录 `24.66 帧/秒`。这是 headless PMX DLL 证据，不冒充播放烘焙的真实 GUI 体感。版本保持 V0.1.8，真实 Blender 4.4 继续通过源码 Junction 生效，不打包 ZIP、不 push。

## 2026-08-29 - V0.1.8 运行时 PMX Shadow 快速覆盖与另存为

- 新增 `mmd_shadow.py`，第一次完整 PMX 导出时直接保留 `mmd_tools` 已构建的 `pmx.Model`、骨骼/材质索引映射及安全签名，不再从磁盘重新解析旧 PMX。Shadow 只存在于当前 Blender 进程内，不在 `.blend` 同目录、导出目录或用户配置目录写缓存文件；关闭 Blender、切换 `.blend`、Reload Scripts 或禁用 MMD Station 后立即清空，因此每次新会话第一次导出仍是完整导出并重新建立 Shadow。
- 同一会话后续覆盖原路径或另存为新路径时，只要 Root、Mesh/Armature/ShapeKey/材质内容、导出结构选项和刚体/Joint 对象集合仍兼容，直接复用既有顶点、面、材质与骨骼数据，仅重建模型信息、显示枠、刚体、Joint、Bone/Material/Group Morph；支持这些 Morph 的新增、修改、删除，并支持既有 Vertex/UV Morph 改名与分类。Vertex/UV Morph 增删或类型变化、Mesh/权重/Modifier/材质/骨骼结构变化以及无法证明安全的状态会自动回退完整导出并重建 Shadow。
- 对受监控 datablock 的 depsgraph 更新先计算内容 fingerprint，避免 Morph 元数据或模型信息更新引起的无效完整导出，同时确保顶点坐标、拓扑、UV、ShapeKey 坐标、权重、Modifier、材质与骨骼内容变化不会误走快速路径。快速写盘使用同目录临时文件加 `os.replace()` 原子替换；准备或写盘失败会回滚内存模型并自动执行原完整导出，不留下半写 PMX。
- 使用完成工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\36.blend` 的 Root `合并2` 做真实验证：第一次完整导出 `35.106s`；微调刚体质量后覆盖同一路径 `2.045s`；新增 Group Morph 后另存为新路径 `1.961s`，两次均确认命中 Shadow，约比该工程此前 `26.710s` 的常规覆盖快 `13.1x–13.6x`。两个结果均经 `pmx.load()` 回读并验证刚体与新增 Morph，正式 `合并2.pmx` SHA256 保持 `3F45DC755DD322B7B2CD22C91BA4604B3B66E9336156CEEB5545C344145BDAC4` 不变。
- 新增 `tests/mmd_shadow_regression.py`，覆盖首次完整建立 Shadow、快速另存为、Bone/Material/Group Morph 新增与改名、模型名更新、Mesh 实改自动完整回退以及运行时清空。Blender 4.4.3 输出 `MMD_SHADOW_REGRESSION_OK`、`MMD_EXPORT_PROFILE_REGRESSION_OK`、`MMD_IO_REGRESSION_OK`；`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 仍通过源码 Junction 生效，不打包 ZIP、不 push。

## 2026-08-29 - V0.1.8 PMX 完整导出分阶段性能基线

- 新增 `mmd_export_profile.py`，由 MMD Station 在注册时挂载 `mmd_tools` PMX exporter 顶层入口，并只在单次导出期间临时计时 Bones、逐 Mesh 数据读取、顶点/面/材质构建、各类 Morph、显示枠、刚体、Joint、贴图处理和 PMX serialization；不修改上游 `mmd_tools` 源码，导出结束或异常时都会恢复原方法，同时保留最近一次结构化结果供后续快速覆盖实现和回归使用。
- 使用完成工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\36.blend` 的当前 Root `合并2` 做真实基准：98 个 Mesh、294632 个导出顶点、452226 个三角面、747 个骨骼、258 个 Morph、508 个刚体、701 个 Joint。关闭贴图复制后，临时 PMX 新增导出耗时 `28.244s`，紧接着覆盖同一文件耗时 `26.710s`，热缓存覆盖仅快约 `5.4%`；正式 `合并2.pmx` 的 SHA256 保持不变。
- 覆盖导出的主要耗时为逐 Mesh 数据读取 `20.229s / 75.7%`、顶点/面/材质构建 `2.768s / 10.4%`、PMX serialization `1.869s / 7.0%`；刚体与 Joint 生成合计仅约 `0.008s / 0.03%`。同一 30.25 MB PMX 的完整解析实测 `6.225s` 和 `7.097s`，因此第一版“加载旧 PMX、仅替换刚体/Joint、重新写盘”的保守预期约 `8–10s`，已可避开约 `86%` 的 Mesh 重算；后续若记录节区偏移和稳定索引映射，可再研究不构建完整旧 PMX 对象的原始节区复用。
- 新增 `tests/mmd_export_profile_regression.py`，覆盖阶段累计、调用次数、模型计数、serialization、输出大小、最近结果副本以及实际 hook 注册。Blender 4.4.3 focused regression 输出 `MMD_EXPORT_PROFILE_REGRESSION_OK`；真实新增/覆盖导出均成功，生成 PMX 又经 `pmx.load()` 解析验证。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push；基准临时 PMX、脚本和日志在本轮结束前清理。

## 2026-08-29 - V0.1.8 MMD I/O 快捷入口与自有代理层

- 在 MMD Station 六个功能 Tab 上方增加固定 I/O 快捷区，按“模型 / 运动 / 姿态”三列提供导入、导出按钮，覆盖 PMD/PMX 模型、VMD 运动与 VPD 姿态；切换代理创建、MMD 查看器、Morph 编辑器、显示枠、物理预览或 MMD IK 时入口始终保留。
- 新增六个 `mmd_station.*` 自有 I/O operator。当前代理层完整转交给 `mmd_tools.import_model/export_pmx/import_vmd/export_vmd/import_vpd/export_vpd`，保持原文件选择器、参数面板与上下文规则；UI 不再直接依赖上游 operator id，后续可只替换 MMD Station 的 PMX 导出实现来做性能定制。
- 新增 `tests/mmd_io_regression.py`，覆盖六个自有 operator 的注册与上游映射、三列按钮顺序，以及快捷区确实绘制在功能 Tab 之前。Blender 4.4.3 真实用户配置 focused regression 输出 `MMD_IO_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8；真实 Blender 4.4 安装目录仍是源码 Junction，改动已直接生效，不打包 ZIP、不 push；本轮未执行真实文件导入/导出，也未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 Morph 三段式滑块与 Group 详情实时刷新

- Morph 编辑器五类 Tab 共用的主列表数值区改为 `0 | 滑块 | 1`：两侧端点按钮通过同一个 `SPX_MorphState.value` 将值直接切到 `0` 或 `1`，各自固定为 `1 UI unit` 宽的正方形，不随面板横向拉伸；中间仍是原生可伸缩滑块，并独占 Keyframe 装饰，因此按钮切值后插帧仍写入原 `value` 动画路径，没有新增第二套状态或动画数据。
- 修复 Group Morph 已激活时直接编辑详情权重不立即更新的问题。原因是 `mmd_tools` 原生 `GroupMorphOffset.factor` 没有 MMD Station 求值回调；现在仅为 MMD Station 的 Group 详情 UI 增加无副本的实时代理属性，读写仍落到原生 `factor`，写入后立即对所属 Root 调用现有 `evaluate_morph_root()`。主详情列表与下方权重字段都走该入口，不修改上游 `mmd_tools` 属性定义，也不影响 PMX 数据存储格式。
- `tests/mmd_morph_editor_regression.py` 新增三段布局、固定端点宽度、中央 Keyframe 属性归属、按钮实际切值及 Group 权重实时重算回归。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8；真实 Blender 4.4 安装目录仍是源码 Junction，改动已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 诊断一键修复

- 诊断 Tab 在诊断列表上方右侧新增“一键修复”按钮。执行时先冻结当前诊断清单，再依次调用既有的确定性安全修复：材质描边 Alpha 同步、可折算的刚体 Scale 修复、空 MMD 骨骼名称补齐；没有安全修复路径、目标已失效或修复失败的项目只计为跳过，不会中断后续项目。
- 批处理结束后统一重新扫描诊断，并在状态栏报告已修复、已跳过与剩余项数；没有诊断项时按钮禁用。逐行右侧原有的单项安全修复入口保持不变，`RIGID_SCALE_UNFIXABLE` 等无法保证结果的诊断不会被一键修复误处理。
- `tests/mmd_material_order_regression.py` 新增按钮真实布局与批处理回归，在同一清单中放入 2 个可修的材质描边 Alpha 问题和 1 个仅可手动处理的项目，确认输出“已修复 2 项，跳过 1 项，剩余 0 项”且两种材质值均正确同步。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 描边关闭时不诊断 Alpha

- 修正材质描边 Alpha 诊断的入口条件：现在无论材质 Alpha 是否为 `0`，都必须先确认“卡通边缘”已启用；描边关闭时描边 Alpha 不参与实际渲染，因此即使它与材质 Alpha 不一致也不报告。上一轮只在透明材质分支检查开关，导致 `Alpha 1 / 描边 0.5 / 卡通边缘关闭` 被误报，本轮已移除该错误行为。
- 卡通边缘启用时规则保持不变：透明材质的描边 Alpha 应归零，非透明材质的描边 Alpha 应与材质 Alpha 一致；自动修复仍只同步描边 Alpha，不改变 RGB、材质 Alpha 或卡通边缘开关。
- `tests/mmd_material_order_regression.py` 现在显式覆盖 `Alpha 1 / 描边 0.5 / 卡通边缘关闭` 与 `Alpha 0 / 描边 1 / 卡通边缘关闭` 均不误报，并让两种应报告案例都启用卡通边缘。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 材质描边 Alpha 诊断与修复

- 诊断 Tab 新增材质描边 Alpha 一致性规则：材质 Alpha 为 `0` 时，仅在“卡通边缘”已启用且描边 Alpha 非 `0` 时报告；材质 Alpha 非 `0` 时，只要描边 Alpha 与材质 Alpha 不一致便报告。比较使用 `1e-6` 绝对容差，避免浮点存储微差产生误报；材质 Alpha 为 `0` 且卡通边缘未启用时不因无效描边值报警。
- 诊断项以 `MATERIAL_EDGE_ALPHA_SYNC` 标识并可直接跳转到对应材质。安全修复统一读取修复时的当前材质 Alpha，再只改写 `mmd_material.edge_color[3]`：透明材质会把描边 Alpha 归零，非透明材质会把描边 Alpha 同步成材质 Alpha；RGB、材质 Alpha、卡通边缘开关和其它材质字段均不改动，修复后立即重新扫描诊断。
- `tests/mmd_material_order_regression.py` 新增三种材质回归：`Alpha 0 / 描边 1 / 卡通边缘开启`、`Alpha 1 / 描边 0.5` 均进入诊断并分别修复为 `0 / 1`，`Alpha 1 / 描边 1` 不误报；同时断言修复后两项诊断自动消失。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 材质详情折叠栏恢复

- MMD 查看器材质 Tab 的内嵌详情恢复为两个独立可折叠区域：“MMD 纹理”和“MMD 材质”标题现在使用原生三角箭头显示展开/收起状态，点击整段标题即可切换；两个区域分别保存展开状态，默认保持展开，因此不改变现有首次显示内容。
- 收起时只停止绘制对应详情控件，不修改活动材质、纹理节点、MMD 材质字段、勾选状态或批量同步逻辑；再次展开后继续显示原有完整字段。改动仅涉及材质详情布局和两个 Scene 布尔状态，不影响其它查看器 Tab。
- `tests/mmd_morph_editor_regression.py` 新增双区域默认展开、分别具备折叠状态及同时收起后详情字段和 Operator 均不再绘制的回归。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 PMX Editor Morph 剪贴板互通

- Morph 编辑器在五类 Tab 上方新增独立剪贴板操作区：“复制勾选 Morph”将勾选项（无勾选时回退活动项）写成 PMX Editor 的 Morph CSV 文本，“从剪贴板粘贴 Morph”读取 PMX Editor 复制内容并按原生 `material_morphs`、`bone_morphs`、`group_morphs` collection 自动归类；同类型同名 Morph 采用 PMX Editor 的追加/更新语义覆盖详情，不改变其它 Morph。
- 跨模型粘贴按 MMD 日文名、英文名及 Blender 名称解析骨骼与材质。Group Morph 的每一条引用都会原样保留：当前模型不存在目标 Morph 时也不丢弃该详情，继续由现有 Group 列表显示三角感叹号，用户可在详情区手动改成正确的 Morph；若剪贴板或当前模型能判定目标类型则自动填写，否则保守落到 Vertex 类型以保留名称。Vertex Morph 与 UV Morph 的 PMX 顶点索引依赖源模型拓扑，粘贴时明确安全跳过；复制同样跳过 Vertex 与顶点组型 UV，只允许可直接表达为 PMX Editor 索引行的旧式 `DATA` UV。
- `tests/mmd_morph_editor_regression.py` 覆盖 Material、UV、Bone、Vertex、Group 五类 CSV 识别，三类可移植 Morph 的写入/序列化回读、Vertex/UV 跳过、缺失 Group 引用保留及按钮真实布局；`tests/fixtures/pmx_editor_morph_clipboard.csv` 固化用户提供的 PMX Editor 样本。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`；另对 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\合并5.pmx` 确认五类 Morph 均存在，并在 `34.blend` 的 `合并2` Root 内存中粘贴样本，4 个 Morph 均更新成功、Group 的 5 条引用及 Material/Bone 详情数量正确，工程未保存。`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 智能重排序跳过隐藏 Morph

- “智能重排序表情枠”现在把 `mmd_tools` 中 `category == "SYSTEM"`（UI 显示为 Hidden/隐藏）的 Morph 与空 Morph 一样排除：即使隐藏 Morph 具备有效 Material/UV/Bone/Vertex/Group 详情，也不会被自动收录。该过滤仅作用于智能重排序；不删除或移动 Morph，不改变 Morph 编辑器顺序，也不限制用户通过显示枠页加号手动收录隐藏 Morph。
- `tests/mmd_display_frame_regression.py` 新增具有效 Material 详情的 `SYSTEM` Morph，断言智能重排序保留原 Morph 定义但不把它写入表情枠，同时继续覆盖五类非隐藏有效 Morph 与各类空 Morph。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 材质同步与校对范围修复

- 修复 MMD 查看器材质页两个名称同步按钮和“校对材质 ID 与物体编号”无视查看器选择范围、始终处理全部材质的问题。三项操作现在统一遵守同一范围规则：存在勾选项时只处理勾选材质；没有任何勾选项时只处理当前活动材质；不会再以“无勾选”解释为“全部”。没有有效活动材质时操作会取消并给出提示。
- 名称同步的两个方向都只读写目标范围；校对只为目标材质写入其全局 PMX 顺序对应的 0-based ID，只重命名使用目标材质的单材质物体，并只同步这些材质对应的 Material Morph ID。包含目标材质的多材质物体继续只统计、不改名；未处理材质保持原 ID、名称和物体编号，模型的“已完整校对”标记也会按全体材质的真实状态重新计算，而不是在局部校对后误标完成。
- `tests/mmd_material_order_regression.py` 新增无勾选时仅处理活动材质、勾选两项时仅处理两项的双向名称同步与分阶段校对回归，并继续覆盖完整校对、自动顺序同步、按材质拆分和 PMX round-trip。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 材质拆分形态键阈值与紧凑工具栏

- MMD 查看器材质页的“按材质拆分（保留法向）”现在接入与 Velo Tools 相同语义的形态键清理阈值：默认 `0.0001 m`，拆分后逐个子网格比较各形态键相对 Basis 的最大局部坐标位移，最大位移不超过阈值时删除该近零形态键；超过阈值的有效形态键保持不变。既有 `mmd_tools` 拆分、法向保留、材质编号校对、UV Morph 顶点组清理与材质 Morph 关联刷新流程均保持不变。
- 材质工具栏改为三个等宽区域：左侧“校对材质 ID 与物体编号”，中间“按材质拆分（保留法向）+ 自动同步图标”，右侧“形态键清理阈值”。自动同步仍是原有可保存的开关，只隐藏文字、保留 `FILE_REFRESH` 图标和悬停说明；阈值是可保存的 Scene 属性并真实传入拆分清理逻辑。
- `tests/mmd_material_order_regression.py` 新增三等分布局树、自动同步图标化、阈值默认值、`0.00005 m` 近零形态键删除及 `0.0002 m` 有效形态键保留回归。Blender 4.4.3 focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；未进行人工 GUI 视觉验收。

## 2026-08-29 - V0.1.8 Morph 顺序与显示枠彻底单向解耦

- 纠正 Morph 编辑器与“表情”显示枠之间错误的双向排序设计：Morph 编辑器的状态顺序现在只读取并写回各类原生 Morph collection，不再读取显示枠顺序；Morph 的新增、删除和六种排序操作也不再清空、补全或重排“表情”枠。显示枠只由显示枠页的显式添加、删除、排序与“智能重排序”操作改变；其中智能重排序继续只收录有有效详情的 Morph、跳过用于分段的空 Morph。
- Morph 日文主名称改变时仍只更新已经存在的显示项引用，以避免引用失效；该引用维护不改变 Morph collection 顺序、显示枠成员或显示枠顺序。回归加入反向排列的显示枠和位于 Morph collection 中间的空 `--Separator--`，断言被动刷新、Morph 新增与 Morph 排序均保持显示枠不变，空分隔 Morph 保持原位。
- 对用户工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\33.blend` 进行了不保存的只读验证：`合并2` 的 44 个 Material Morph 中，`--衣服消失--`、`--BDSM--`、`----------` 原始索引为 `0 / 19 / 32`；模拟切换 Morph Tab 后 Morph collection 与 253 项表情枠均逐项不变，编辑器状态顺序重新服从 Morph collection，三个空分隔项仍位于 `0 / 19 / 32`。
- Blender 4.4.3 回归输出 `MMD_MORPH_EDITOR_REGRESSION_OK` 与 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；真实工程未保存，未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 切换 Morph Tab 不再改写表情显示枠

- 修复从显示枠切到 Morph 编辑器再切回时，Morph 编辑器的被动状态刷新误调用完整 `_sync_morph_order()`，清空并用全部 Morph 重建“表情”枠的问题。被动刷新现在只重排编辑器状态缓存；若 Morph 确实被改名，只更新已经收录该 Morph 的显示项引用，不新增、删除或重排任何显示项。显式新增/删除/排序 Morph 与显示枠“智能重排序”的既有写回行为保持不变。
- 对用户工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\33.blend` 进行了不保存的只读复现：`合并2` 的表情枠为 253 项、Morph 状态为 256 项，未收录的 3 项均为空 Material Morph（`--衣服消失--`、`--BDSM--`、`----------`）；修复后执行同一被动刷新仍为 253 项，逐项内容不变且新增 0 项。
- `tests/mmd_morph_editor_regression.py` 新增“只保留一个已收录 Morph”的被动刷新与改名引用回归，防止未收录/空 Morph 再被自动补入。Blender 4.4.3 回归输出 `MMD_MORPH_EDITOR_REGRESSION_OK` 与 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；真实工程未保存，未进行人工 GUI 点击验收。

## 2026-08-29 - V0.1.8 UV Morph 改名 Runtime 失效与完整删除修复

- 修复已建立 Runtime 的顶点组型 UV Morph 在修改日文主名称后失效的问题：`mmd_tools` 会同步改名 `.placeholder` slider 与 `UV_<Morph名>±X/Y/Z/W` 顶点组，但既有 dummy-armature driver 的 `vertex_group_scale` 仍指向旧 Morph collection key。MMD Station 现在在稳定 UID 元数据刷新检测到 UV Morph 改名时强制重建轻量 Runtime，并清理由重建遗留的无效 driver；英文名仍只是导出名称，不触碰 Runtime。
- Morph 编辑器标题栏的刷新按钮不再只重建列表缓存：检测到模型已有已绑定 `.placeholder` 时，会无条件重建 Bone/UV Runtime 并重新同步当前 Morph 值，因而可以修复“旧工程已保存新 Morph 名、但 driver 仍指向改名前 collection key”的状态；从未建立 Runtime 的模型仍保持按需绑定，不因刷新提前生成 Runtime。
- UV Tab 主列表的减号现在不再只删除 Morph 元数据：删除前会在模型全部 Mesh 中精确移除该 Morph 的 `UV_<Morph名>±X/Y/Z/W` 附属顶点组及引用它们的 `UV_WARP` modifier，同时删除 `.placeholder` 同名 slider，并在已有 Runtime 时重建绑定以清理 dummy-armature 残留。不会按模糊前缀误删名称相近的其它 UV Morph 顶点组。
- `tests/mmd_morph_editor_regression.py` 新增已绑定 UV Morph 改名后的新 `vertex_group_scale` driver 路径、旧路径清除、旧工程式“名称已一致但 driver 仍旧”的刷新修复、附属顶点组保留，以及双 Mesh UV Morph 经减号删除后的元数据、顶点组、modifier、placeholder slider 全链路清理回归。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。
- 对用户工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\33.blend` 做了不保存的只读修复验证：`合并2 / Morph2切換` 的 `UV_Morph2切換+X` 顶点组原本仍存在，但 Runtime scale path 错误残留为 `mmd_root.uv_morphs["新建 Morph"].vertex_group_scale`；执行刷新 Operator 后变为 `mmd_root.uv_morphs["Morph2切換"].vertex_group_scale`，旧路径消失、Runtime Error 为空。工程未被保存。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；本轮未进行人工 GUI 视觉验收。

## 2026-08-29 - V0.1.8 活动显示枠 Morph / 骨骼统计

- 在显示枠编辑器的活动显示枠明细列表下方新增实时统计行，显示该枠的总项数、Morph 项数与骨骼项数；统计仅基于当前活动显示枠，不改变显示项选择、排序、清理、智能补充或 PMX 数据。
- `tests/mmd_display_frame_regression.py` 新增表情枠纯 Morph 与普通枠纯骨骼两种统计回归。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；本轮未进行人工 GUI 视觉验收。

## 2026-08-28 - V0.1.8 复制材质身份冲突与查看器漏项修复

- 修复 Blender 复制材质时连同 MMD Station 的 `surface_proxy_pmx_material_id` 自定义属性一起复制，导致 MMD 查看器按身份建表时由复制材质覆盖原材质的问题。`ordered_materials()` 现在会在当前模型实际使用的材质中检测重复身份：较早创建的原材质保留既有身份，后续复制材质获得新的唯一身份，并紧跟原身份插入现有 PMX 排序；不修改 `mmd_material.material_id`、材质内容或工程中的对象关系。
- 对用户工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\31.blend` 进行了不保存的只读检查：模型 `合并2` 实际有 96 个材质，存储排序只有 95 个身份；`手套` 与 `手套+` 共用身份 `fdf32d357d4545dc8a19fb22dbe30519`，修复后内存排序恢复为 96 项，`手套` 位于 73、`手套+` 位于 74 且身份已分离。测试工程未被保存。
- `tests/mmd_material_order_regression.py` 新增真实复制语义回归，覆盖复制项继承自定义属性、原材质身份保留、复制项身份修复、两项同时进入查看器以及删除复制项后的排序收敛。Blender 4.4.3 回归输出 `MMD_MATERIAL_ORDER_REGRESSION_OK` 与 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 MMD 材质详情恢复原版紧凑排列

- 将 MMD 查看器内嵌的“MMD 材质”从逐字段纵向堆叠恢复为 `mmd_tools` 原面板的紧凑横向组合：漫射颜色与 Alpha 同行、高光颜色与反射同行、双面与地面阴影同行、自身阴影贴图与自身阴影同行、边缘颜色与边权重同行；MMD 纹理区的“使用共用的卡通纹理”和共用编号也恢复同行。字段右侧的勾选材质批量复制小图标继续保留，不改变批量写回范围。
- `tests/mmd_morph_editor_regression.py` 继续覆盖完整 Material Tab 绘制路径、字段及批量复制按钮；Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；本轮未进行人工 GUI 视觉验收。

## 2026-08-28 - V0.1.8 MMD 查看器材质详情实际挂载与勾选批量字段同步

- 修复此前虽实现“MMD 纹理 / MMD 材质”绘制函数、但 Material Tab 在 `draw_material_name_sync()` 后提前 `return`，导致真实 MMD Station 面板完全不显示详情的接线错误。Material 分支现在先绘制活动材质的两块详情面板再返回；回归直接执行完整 `draw_browser()` Material 路径，防止只测私有绘制函数却再次漏接真实入口。
- Blender 原生 `layout.prop` 的 Alt+左键传播只识别当前 UI 上下文中的 Blender selection，不会把 MMD 查看器自定义 UIList 复选框视为 selected datablock，Python API 也不提供属性控件自身的 Alt 点击事件回调。因此采用确定性入口：所有可批量的 MMD Material 字段及球体/Toon 设置右侧新增 `COPYDOWN` 小图标，将活动材质的该字段复制到查看器中全部已勾选材质；`material_id` 保持唯一性，不提供批量复制。没有勾选材质时明确取消，不读取 3D 视图物体选择。
- `tests/mmd_morph_editor_regression.py` 覆盖真实 Material Tab 到详情面板的调用链、标量 `alpha` 与数组 `diffuse_color` 的勾选批量复制、空勾选拒绝及复制图标绘制。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；本轮未进行人工 GUI 视觉验收。

## 2026-08-28 - V0.1.8 Material Morph 详情按真实 PMX 材质顺序添加

- 修正 Material Morph 详情 `+` 在多选 Mesh 时按活动物体优先、再按 `context.selected_objects`/材质槽遍历而导致顺序偏离 PMX 的问题。现在先汇总所选 Mesh 涉及的材质集合，再复用 MMD 查看器与导出链路的 `ordered_materials()` 真实 PMX 顺序过滤候选材质；共享材质仍只添加一次，已存在于当前 Morph 的材质仍跳过。没有实际 PMX 顺序的未使用材质槽保留原能力，但统一追加在具真实顺序的材质之后。
- `tests/mmd_morph_editor_regression.py` 通过刻意打乱所选对象与材质顺序，断言新增详情严格服从存储的 PMX 材质顺序，同时验证 `related_mesh` 仍指向包含该材质的所选 Mesh。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，材质导出/回读回归输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`；`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 详情减号批量删除语义

- 修正 Material、UV、Bone、Group Morph Offset 详情列表的减号行为：存在任意勾选详情行时，批量删除全部勾选项，不再误删蓝色活动行；没有勾选项时才回退删除蓝色活动行。删除后活动索引落在首个删除位置对应的有效邻近行，并立即重新计算当前 Morph Root。Vertex 详情行是模型中实时汇总的 Mesh/ShapeKey 命中结果，不是独立 Offset 数据，因此仍不显示减号。
- `tests/mmd_morph_editor_regression.py` 覆盖“勾选优先于活动行”的非连续批量删除，以及清空勾选后的活动行回退删除。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 详情区间选组补齐

- Morph 详情列表的选择工具栏在“全选 / 全不选 / 反选”后补齐“区间选组”。Material、UV、Bone、Group 的 Offset 详情行与 Vertex Morph 的 Mesh/ShapeKey 命中行共用相同语义：以当前详情列表中最前、最后两个已勾选行为端点，补选两者之间的全部详情行；只有一个端点时取消操作并保持原选择不变。
- 实现复用 `surface_proxy.select_morph_details`，未新增重复 Operator；`tests/mmd_morph_editor_regression.py` 覆盖五行 Material 详情的区间补选/单端点拒绝，以及 Vertex 详情的 Mesh 顺序区间补选/单端点拒绝。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 显示框同步入口、Morph 阈值清理与材质详情补齐

- 将普通骨骼显示框的“将勾选项选入 Blender”由整行大按钮收纳为选择工具栏末尾的 `RESTRICT_SELECT_OFF` 小图标；作用域与既有行为不变，仍只同步当前显示框中已勾选且有效的骨骼，表情框不显示该入口。
- Morph 编辑器 Vertex Tab 新增与 Velo Tools 同语义、同默认值的“形态键清理阈值”（默认 `0.000100 m`）。执行“清理”时，先逐 Mesh 计算勾选 Vertex Morph 的 ShapeKey 相对 Basis 的最大局部空间欧氏位移；不超过阈值的 ShapeKey 会被移除，只有当所有模型 Mesh 均不再保留同名有效 ShapeKey 时才继续删除空 Morph 元数据，避免局部空键误删仍有实际变形的 Morph。
- MMD 查看器 Material Tab 的活动材质详情区补齐“MMD 纹理”和“MMD 材质”两块内嵌面板，覆盖主纹理、球体纹理、Toon 纹理、MMD 名称/ID/注释、颜色、阴影和描边参数。纹理增删通过显式材质名操作，不依赖 Properties 编辑器当前活动材质，避免查看器列表活动行与 Blender 活动物体不一致时改错材质。
- 关键文件为 `mmd_station/mmd_display_frame.py`、`mmd_station/mmd_morph_editor.py`、`mmd_station/mmd_physics.py` 与 `tests/mmd_morph_editor_regression.py`。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`、`MMD_MORPH_EDITOR_REGRESSION_OK`、`MMD_MATERIAL_ORDER_REGRESSION_OK` 与 `MMD_ORDERING_USER_CONTROL_REGRESSION_OK`；`py_compile`、`git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push；本轮未进行人工 GUI 视觉验收。

## 2026-08-28 - V0.1.8 显示枠骨骼跳转与勾选同步

- 普通骨骼显示枠的每个 `BONE` 显示项行右侧新增与 MMD 查看器相同的 `RESTRICT_SELECT_OFF` 跳转按钮，并直接复用 `surface_proxy.select_mmd_item`：单击切入对应 Armature 的 Pose Mode 并独选该骨骼，按住 Shift 单击可扩展选择。表情枠以及 Morph 显示项不显示该骨骼跳转入口。
- 普通显示枠新增“将勾选项选入 Blender”，把当前枠内已勾选且仍有效的骨骼同步为 Blender Pose Mode 选择，并将最后一根有效骨骼设为活动骨骼；失效引用会被跳过，全部失效时提示先执行清理。`tests/mmd_display_frame_regression.py` 覆盖双骨骼勾选同步、模式切换与活动选择。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 显示枠失效项目清理

- 在当前显示枠的显示项选择工具条末尾新增“清理”按钮，批量移除因骨骼或 Morph 改名/删除而找不到真实目标的残余显示项。清理仅作用于当前显示枠的失效引用，不删除 Armature Bone、Morph 定义或任何仍可解析的显示项；若模型 Armature 本身不可用则拒绝清理，避免把全部 Bone 引用误判为残余。
- `tests/mmd_display_frame_regression.py` 覆盖失效 Bone、失效 Morph 与有效 Bone 保留。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 显示枠区间选组补齐

- 补齐显示枠编辑器首版遗漏的“区间选组”：显示枠列表与当前显示项列表的选择工具条现在都与 Morph 编辑器一致，在“全选 / 全不选 / 反选”后提供“区间选组”，以首尾两个已勾选项为端点补选中间全部项目；不足两个端点时明确提示且不改动选择。
- `tests/mmd_display_frame_regression.py` 同时覆盖显示枠和显示项的区间补选。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 PMX 显示枠编辑器与智能整理

- MMD Station 新增独立“显示枠”功能页，直接编辑 `mmd_tools` 原生 `display_item_frames`，提供显示枠日文名/英文名同屏编辑、特殊枠锁定、显示项详情编辑，以及显示枠与显示项两级复选框、加减、稳定块排序、全选/全不选/反选；普通显示枠的加号可把当前 Armature 在 Edit/Pose Mode 中所选骨骼批量写入，表情枠则接收 Morph 编辑器已勾选项。
- 新增“智能补充未收录的可见骨骼”：只向当前普通显示枠追加尚未出现在任何显示枠中的骨骼，保持 Armature 顺序，并排除 `Bone.hide` 或仅属于不可见 Bone Collection 的骨骼。新增“智能重排序表情枠”：只收录存在详情行/实际 ShapeKey 或 UV Vertex Group 的 Morph，按 Group → Material → UV → Bone → Vertex 重建表情枠；空 Morph 定义本身不删除，仍可保留作分段。
- 关键文件为 `mmd_station/mmd_display_frame.py`、`mmd_station/__init__.py` 与 `tests/mmd_display_frame_regression.py`；未修改 `mmd_tools` PMX 导入/导出核心，导入导出仍直接消费同一原生数据。Blender 4.4.3 focused regression 输出 `MMD_DISPLAY_FRAME_REGRESSION_OK`，既有 Morph 回归单进程重跑输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，真实 Blender 4.4 Junction 装载输出 `MMD_STATION_REAL_ADDON_SMOKE_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 `_M` 父子骨链代理恢复误拦截修复

- 修复 MMD 查看器从勾选骨骼恢复代理时，把 `Bone_Piao130_M -> Bone_Piao131_M` 这类明确父子骨链误判为“主体名称不一致”的问题。根因是中心后缀 `_M` 未被名称解析器识别，导致末尾编号没有被剥离；现在 `_M` 按无左右侧的中心后缀处理。
- 非旧式命名的代理恢复现在先以真实 Armature 父子拓扑拆分骨链，代理前缀只从每条独立骨链的根骨骼推导。因此同一条已确认连续的父子链不再因子骨骼名称解析差异被拒绝；多条互不连接的骨链仍需具有兼容主体名称，防止把无关主体误合成一个代理。
- `tests/proxy_creation_no_overwrite_smoke.py` 新增 `_M` 前缀解析和 `Bone_Piao130_M -> Bone_Piao131_M` 实际父子链创建回归。Blender 4.4.3 headless 输出 `PROXY_CREATION_NO_OVERWRITE_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 的源码 Junction 已直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 “稳定中长裙”实测参数同步

- 按真实裙摆物理验收结果更新内置“稳定中长裙”预设：刚体深度由 `0.10` 补间到 `0.40`，质量由 `12.00` 补间到 `1.00`，移动阻尼由 `0.99` 补间到 `0.9999`，旋转阻尼由 `0.9999` 补间到 `0.99`，摩擦起始值改为 `0.00`；盒体、刚体类型、碰撞组与屏蔽组保持既有设置。
- 纵 Joint 的移动/旋转限制及移动弹簧统一归零并关闭补间，但按用户要求保留旋转弹簧 `12/5/5 -> 4/2/2` 三轴补间，以兼容可能依赖该组参数的特殊情况。横 Joint 保持旋转限制与旋转弹簧设置，移动限制仍归零；按面板实测数据保留未启用补间的末端 Y 移动弹簧值 `40.00`。
- `tests/headless_smoke.py` 已同步精确预设断言。Blender 4.4.3 focused regression 输出 `STABLE_LONG_SKIRT_PRESET_FOCUSED_OK`，`py_compile` 与 `git diff --check` 通过；完整 `headless_smoke.py` 已通过本轮全部预设断言，随后在既有的骨骼名称修复断言（第 2204 行）失败，该失败不在本轮预设改动路径内，未扩张范围处理。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Vertex Morph 刷新与真实 ShapeKey 删除

- 修正 Morph 编辑器“刷新”只重建面板缓存、不会从模型恢复缺失顶点 Morph 的问题。刷新现在扫描当前 MMD Root 的实际模型 Mesh ShapeKeys，按 `mmd_tools` 规则跳过 Basis 与 `mmd_` 内部键，并为面板中不存在的 ShapeKey 补建同名 Vertex Morph；Root 下的 `.placeholder` 不属于模型 Mesh，因此其中仅作为运行时滑块的孤立键不会被误补回面板。
- 顶点 Tab 的减号现在在删除 Vertex Morph 元数据前，同步移除当前勾选项（无勾选时为活动项）在全部模型 Mesh 及 `.placeholder` 中的同名 ShapeKey；其它 Morph Tab 的删除语义保持不变。`tests/mmd_morph_editor_regression.py` 覆盖双 Mesh 恢复、`.placeholder` 排除、无勾选活动项删除及实际/代理 ShapeKey 一并移除。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，真实 Blender 4.4 使用源码 Junction，未打包 ZIP、未 push。

## 2026-08-28 - V0.1.8 全局活动项快捷移动

- 统一 MMD Station 的列表移动规则：Morph 主列表、Morph 详情列表及 MMD 查看器的“置顶 / 上移 / 下移 / 置底”在没有任何勾选项时，直接作用于蓝色活动项；存在勾选项时仍按原有稳定块逻辑移动全部勾选项。三处悬停说明同步标明未勾选回退行为。
- 三处最后两个“插入活动项前 / 后”保持原边界，仍必须至少显式勾选一个项目作为待移动块，不会把活动项本身当作隐式待移动项。`tests/mmd_morph_editor_regression.py` 覆盖 Morph 主列表与详情列表的四向回退及锚点拒绝；`tests/mmd_ordering_user_control_regression.py` 覆盖 MMD 查看器的通用排序规则。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK` 与 `MMD_ORDERING_USER_CONTROL_REGRESSION_OK`，`py_compile` 和 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Group Morph 失效详情参与清理

- 扩展 Morph 编辑器“清理”的 Group Morph 判定：详情行引用的目标 Morph 已从其它 Tab 删除、并在详情列表显示三角感叹号时，该行不再算作有效详情；已勾选 Group Morph 的全部详情均失效时会被清理。混合包含有效引用与失效引用的 Group Morph 仍整体保留，避免因单条坏引用误删仍有用途的群组。
- `tests/mmd_morph_editor_regression.py` 新增“Vertex Morph 先清理后 Group 引用变为失效”的顺序回归，并覆盖全失效 Group 可清理、有效与失效混合 Group 保留。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`；`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 当前 Tab 空详情清理

- Morph 编辑器的材质、UV、骨骼、顶点、群组五个 Tab 在勾选操作行统一新增“清理”按钮；操作范围严格限定为当前 Tab 的已勾选项，只移除详情为空的 Morph，不再像普通删除按钮那样在无勾选时回退删除活动行。有详情的勾选项保持不变：材质/骨骼/群组按 offset 行判断，顶点按模型中的同名 ShapeKey 判断，UV 同时支持 offset 数据与 `VERTEX_GROUP` 模式下的对应 UV Vertex Group。
- `tests/mmd_morph_editor_regression.py` 新增五个 Tab 的空项清理、后续 Tab 不被提前波及、有详情项保留、无勾选及无空项拒绝执行的回归覆盖。Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`；`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 中线 `_M` 刚体参与镜像 Joint

- 修复“创建镜像 Joint / 同步镜像 Joint”在一端为中线 `_M` 刚体时直接计为跳过的问题。`_M` 仍保留为普通无左右名称的镜像副本标记；但当该刚体确实位于骨架局部 X 中线时，Joint 镜像端点解析现在允许左右两侧共享它，不再因为 `_source_side == "M"` 错误拒绝已有的另一侧端点。
- `tests/mirror_underscore_suffix_regression.py` 新增中线 `_M` 可共享、非中线 `_M` 不可误共享的边界回归。Blender 4.4.3 focused regression 输出 `MIRROR_UNDERSCORE_SUFFIX_REGRESSION_OK`；另以 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\24.blend` 只读载入并在内存中验证 `左Bone_Piao210`：创建得到右侧 Joint，随后同步成功，两个阶段均 `skipped=0`，未保存测试工程。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 单目标 Material Morph 预设免勾选

- 调整 Morph 编辑器材质详情中的“预设：隐藏 / 预设：显示”：当前 Material Morph 只有一个目标时，即使详情行未勾选也会直接对唯一目标应用预设；有两个或以上目标时仍必须至少勾选一行，未勾选会保持原警告并取消操作。按钮悬停说明同步明确单目标与多目标边界。
- `tests/mmd_morph_editor_regression.py` 新增单目标未勾选时隐藏、显示两个预设均成功，以及双目标全部未勾选时仍拒绝执行的回归覆盖；Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 ??? MMD ?????????

- ???? Tab ? MMD ????????????????????? `_create_proxy_mesh()`????? Mesh ??????????? `MMD Station Proxies` Collection???????????? Armature ?????? Armature ????? Collection??? MMD Armature ????
- ????????????????????????? Joint????????? Joint???????? MMD Root ?? Collection?`rigidbodies` / `joints` ?? Empty ??????? `collection_organization.py` ???? Collection ????? `mmd_tools` ?????? Collection ??????????? MMD Root ??
- ?? `tests/collection_organization_regression.py`?? MMD Root Collection ????? Collection ?????????????????????????????????? `COLLECTION_ORGANIZATION_REGRESSION_OK`?`tests/proxy_creation_no_overwrite_smoke.py` ????????? Collection ????? `PROXY_CREATION_NO_OVERWRITE_OK`?`py_compile` ? `git diff --check` ??????? `headless_smoke.py` ???????????????????????????? `KeyError`?`bone_physics_creator_smoke.py` ????????????????????????? V0.1.8??? Junction ???????? ZIP?? push?

## 2026-08-28 - V0.1.8 Morph 改名面板闪烁与顺序保护

- 修复在 Morph 编辑器列表或详情区改名时整个插件内容消失一帧再刷新的问题。旧 `draw_morph_editor()` 把名称缓存或“表情”Display Frame 的短暂过期与 Morph 增删等结构失效混为一类，统一显示“正在读取 Morph…”并提前结束绘制；现在会独立验证稳定 UID、类型和数量结构，仅名称过期时继续完整绘制，后台 timer 再同步名称，因此文本编辑期间不再撤掉面板。
- 名称刷新路径不再先依据含旧名称的 Display Frame 重建状态顺序，而是保留现有稳定 UID 顺序、更新 `morph_name` 后再同步各类型 Collection 与“表情”Display Frame，避免改名项被暂时当成新 Morph 并漂到末尾。真正的 Morph 增删、UID 缺失或类型结构变化仍保留“正在读取 Morph…”保护。`tests/mmd_morph_editor_regression.py` 新增改名前后结构可绘制、UID 顺序不变、材质 Collection 位置不变与 Display Frame 名称同步回归；Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Group Morph 收集其它 Tab 勾选项

- Group Morph 详情区域的 `全选 / 全不选 / 反选` 下方新增“将其它 Tab 勾选 Morph 加入当前组”。按钮读取材质、UV、骨骼、顶点四个 Tab 中当前已勾选的 Morph，按编辑器状态顺序批量加入当前活动 Group Morph，每个新 offset 的默认权重为 `1.0`；Group Tab 自身不参与收集，避免引入 Group 嵌套和循环。
- 已存在于当前组内的相同 `morph_type + name` 自动跳过，防止重复叠加；新块插入当前活动详情行下方并激活第一条新增项。无勾选项或勾选项已全部存在时取消并给出明确提示。`tests/mmd_morph_editor_regression.py` 覆盖四类跨 Tab 收集、默认权重、重复去重及二次调用拒绝；Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 新增项跟随活动行插入

- 修复 Morph 编辑器右侧 `+` 只调用 Collection `.add()`、导致新 Morph 永远追加到当前类型末尾的问题。新增前现在会记录当前类型的蓝色活动行；创建后将新 Morph 插入该活动项正下方，并把新项设为活动行。没有当前类型的有效活动项时仍安全追加到底部。
- 插入后继续同步插件状态顺序、各类型 Morph Collection 与“表情”Display Frame，避免界面顺序和实际 PMX Morph 提交顺序分离。`tests/mmd_morph_editor_regression.py` 新增“活动 Material Morph 下方插入、新项激活、Collection/Display Frame 同序及清理恢复”回归；Blender 4.4.3 focused regression 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 MMD 查看器材质名称单击选中、双击编辑

- MMD 查看器材质 Tab 的“Blender 材质名”和“MMD 名称”改为与 Morph 编辑器日文名相同的标签式属性绘制：单击交由 `UIList` 激活整行，双击才进入文本编辑，避免用户想切换活动材质时意外改名；“MMD 英文名”保持现有直接编辑行为，其它选择、排序与 3D 视图定位逻辑均未改动。
- `tests/mmd_material_order_regression.py` 新增 UI 绘制契约断言，确认前两列使用 `emboss=False`、英文名列保持原行为；Blender 4.4.3 `--factory-startup` focused regression 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 项目正式更名为 MMD Station

- 插件产品名、N 面板标题与分类统一改为 `MMD Station`；本地项目目录由 `MMD-Skirt-Proxy-Creator` 改为 `MMD-Station`，Python package 由 `mmd_skirt_proxy_creator` 改为 `mmd_station`，README、native build 脚本和测试入口同步使用新路径。为保护旧 `.blend` 工程兼容性，既有 `surface_proxy.*` operator id、`Scene.surface_proxy_creator` 与 `surface_proxy_*` IDProperty 均保持不变。
- 真实 Blender 4.4 开发安装已迁移为 `addons\mmd_station` Junction，并移除旧 `addons\mmd_skirt_proxy_creator` Junction；原 Morph AI 的基础地址、API Key、模型设置已迁入新 AddonPreferences 并保存，物理预设复制到 `presets\mmd_station\physics`，旧预设目录保留作回退备份。
- 真实用户配置安装验证输出 `MMD_STATION_INSTALLED_ADDON_OK`，并通过材质顺序、Morph 编辑器、用户排序、刚体缩放诊断、代理创建、镜像命名与完整 headless smoke 等选定回归，最终输出 `MMD_STATION_SELECTED_REGRESSIONS_OK`。版本保持 V0.1.8，不打包 ZIP、不 push；GitHub remote 仓库名仍保持 `MMD-Skirt-Proxy-Creator`，等待单独授权后再改。

## 2026-08-28 - V0.1.8 MMD 查看器材质与 3D 视图双向选择

- MMD 查看器材质 Tab 的每一行新增与骨骼 Tab 一致的右侧箭头。点击后会在当前 MMD 模型内定位并以 Object Mode 选中所有实际使用该材质的 Mesh，最后一个目标材质同时成为活动 Mesh 的 active material slot；列表活动行同步高亮。表头与材质行共用的列布局同时加入箭头占位，既有序号、Blender 材质名、MMD 名称和 MMD 英文名仍保持对齐。
- 批量选择区下方新增“将勾选项选入 Blender”和“从 3D 视图同步选中材质”。前者只操作 Mesh Object 选择，不进入 Edit Mode、不改面选择；后者从 3D 视图中已选 Mesh 收集其实际被面使用的全部材质，并将 active material 对应列表行设为活动行。所有查找都限制在当前 MMD Root，避免同名或外部 Mesh 干扰。
- Blender 4.4.3 回归覆盖单材质箭头定位、多材质 Mesh 的 Object Mode 批量选择与反向同步，`MMD_MATERIAL_ORDER_REGRESSION_OK` 通过；全量 Python `py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 物理预览刚体缩放诊断与安全修复

- MMD 查看器诊断页现在复用物理预览的同一套世界缩放判定，逐个报告会让预览启动失败的非均匀或零缩放刚体，显示实际 Scale，并区分 `RIGID_SCALE_BAKE` 可安全折算与 `RIGID_SCALE_UNFIXABLE` 不可精确表示两类。另补充 `RIGID_SCALE_NORMALIZE` 警告：对象本地 Scale 为均匀非 1（例如 `(1.092, 1.092, 1.092)`）时不会阻止预览，但仍会进入诊断并可一键折算归一。修复完成后自动重跑诊断；因此不会再出现缩放已被手动改动、诊断页却完全不显示的缺口。
- 安全修复会把对象缩放无损折算进 `mmd_rigid.size`，再把刚体对象 Scale 归一：Box 支持逐轴折算；Capsule 仅在 X/Y 径向缩放一致且能够得到有效 Radius/Height 时折算；Sphere 仅允许均匀缩放。零缩放、父级非均匀缩放、椭球 Sphere、X/Y 径向不同的 Capsule 均只诊断并明确解释原因，不用近似值伪修复。物理预览的 `_uniform_world_scale` 已改为调用同一共享模块，诊断与启动条件不会漂移。
- 对用户截图对应的 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\20.blend` 做了不保存的只读与内存修复验证：唯一两项阻断异常是 `078_左ひざ2`、`083_右ひざ2`，均为可精确折算的 Capsule Scale `(约 1.057822, 1.057822, 1.0)`；修复后 495 个刚体均能生成物理预览 BodyDesc，标记 `ACTUAL_20_BLEND_RIGID_SCALE_REPAIR_OK 495`。独立 Blender 4.4.3 回归同时覆盖截图中的均匀 `(1.092, 1.092, 1.092)` Box 警告与无损归一、修复前后世界空间边界一致、非均匀 Capsule 折算，以及椭球 Sphere 拒绝，标记 `MMD_RIGID_SCALE_DIAGNOSTIC_REGRESSION_OK`。未保存用户工程，版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 MMD 查看器骨骼 AI 三轨命名

- MMD 查看器骨骼 Tab 的“补全并标准化 MMD 骨骼名称”区域新增 `AI翻译勾选骨骼日文名` 与共用设置图标。操作读取勾选骨骼当前 `mmd_bone.name_j` 的名称主体并复用 Morph / 材质 AI 的同一份全局 `AddonPreferences`、基础地址、API Key、模型和 OpenAI-compatible 请求实现；骨骼专用 Prompt 不让模型生成左右标记，由本地规则统一落地，避免三套命名约定互相冲突。
- 输入中的 `左` / `右` 前缀、`.L/.R`、`_L/_R` 与英文 `Left/Right` 前后缀都会先解析为骨骼侧向。翻译后 MMD 日文区域改为仅保留 `左` / `右` 前缀的英文主体（如 `左UpperArm`），MMD 英文名使用 `_L/_R`（如 `UpperArm_L`），Blender 骨骼名使用 `.L/.R`（如 `UpperArm.L`）；无侧向骨骼三处均使用同一英文主体。英文主体上限为 14 字符，确保追加侧向后最终名称仍不超过 16 字符。
- Blender 骨骼批量改名在写入前检查重复名、未选骨骼冲突与顶点组冲突，再通过临时名完成交换安全的两阶段重命名。该路径沿用 mmd_tools `Model.renameBone`，同步显示枠与顶点组；Bone Morph 等基于 Bone ID 的引用继续指向改名后的骨骼。Blender 4.4.3 回归以模拟 API 验证 `左上臂` 与 `袖子A1.R` 生成三套目标名称，同时确认两个网格顶点组、两个 Bone Morph 引用和查看器勾选状态均保持正确。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 MMD 查看器材质 AI 翻译

- MMD 查看器材质 Tab 的名称同步区域新增 `AI翻译勾选材质日文名` 与相邻设置图标。操作按查看器列表顺序收集已勾选且不重复的材质，读取 `mmd_material.name_j`，将翻译结果写回 `mmd_material.name_e`；空日文名不会用 Blender 材质名代替，而是明确跳过并在结果中报告。未勾选材质或全部为空时取消且不改名。
- 材质翻译直接复用 Morph AI 的同一份全局 `AddonPreferences`、OpenAI-compatible 请求、JSON 整批校验、16 字符上限、紧凑 PascalCase、符号保留以及 `_L/_R/_Up/_Down` 方向后缀规范；材质页设置图标打开的也是同一个全局设置弹窗，因此两处不需要重复填写。Blender 4.4.3 回归以模拟 API 验证两个已勾选材质从 MMD 日文名读取并回填 MMD 英文名，不发送真实网络请求。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph AI 方向后缀缩写

- Morph AI 英文名规范不再拼写完整 `Left` / `Right`，左右方向统一使用 `_L` / `_R`，上下方向统一使用 `_Up` / `_Down`；左右或上下即使位于源名称前缀，翻译时也必须移动为后缀。同时存在上下与左右时固定先上下、后左右，例如 `Pupil_Up_R`。Prompt 给出该规则，API 返回后插件再本地提取完整方向词或已有方向后缀并规范化：`LeftEye` → `Eye_L`、`RightEye` → `Eye_R`、`Emo3Left` → `Emo3_L`、`PupilUpRight` → `Pupil_Up_R`、`LeftPupilDown` → `Pupil_Down_L`。
- 方向缩写会按规范新增下划线，因此符号硬校验从“源与结果符号完全相等”调整为“源名称中的数字、标点和符号必须按原顺序全部保留”，允许结果额外加入方向分隔 `_`，但原有 `+` 被替换为 `-` 等破坏仍会整批拒绝。规范化完成后继续执行最多 16 字符限制。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 与 MMD 查看器区间补选

- Morph 编辑器五个 Tab 的共享选择行均在 `反选` 右侧新增 `区间选组`。当前可见列表至少勾选两个 Morph 后，操作以最前与最后一个已勾选项为端点，将两者之间所有可见行补为勾选；端点外已有勾选保持不变。搜索过滤存在时只沿当前可见结果计算区间，隐藏行不会被意外勾选；少于两个可见端点时取消并提示。
- MMD 查看器的材质、骨骼、刚体、Joint 页同样在 `反选` 右侧提供 `区间选组`，并复用与 UIList 完全一致的搜索和名称前缀可见性判定；诊断页没有批量勾选列表，因此不显示无效入口。回归覆盖 Morph 完整区间、单端点拒绝，以及 MMD 查看器过滤列表中隐藏行不被补选。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph AI 紧凑 PascalCase 英文名

- Morph AI 翻译要求改为不使用空格、每个英文单词首字母大写的紧凑 PascalCase 风格，以在 16 字符限制内保留更多语义。除 Prompt 约束外，插件会在 API 返回后本地将每段连续英文词首字母大写并删除全部空白，再执行既有的符号序列与最大长度硬校验；例如 `cross eyed` 规范为 `CrossEyed`，`+lower eyes` 规范为 `+LowerEyes`，`cross-eyed` 在保留连字符的同时规范为 `Cross-Eyed`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph AI 翻译长度与符号硬校验

- Morph AI 翻译 Prompt 新增硬要求：英文名尽量简短，包含空格和符号在内最多 16 个 Unicode 字符。API 返回后插件再次逐项检查实际长度，并提取原名称与翻译结果中的数字、标点和符号序列进行一致性校验；任何一项超过 16 字符或丢失、替换、调换原符号时，整批翻译取消且不覆盖任何 `name_e`。回归覆盖合法短名称、超长名称拒绝和 `+` 被错误改成 `-` 时的符号拒绝。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph AI 基础地址自动补全 V1

- Morph AI 设置中的地址字段改为只填写服务端基础地址，例如 `https://api.example.com`；插件请求时固定自动追加 `/v1/chat/completions`，用户不再填写 `/v1`。设置弹窗打开与确认保存时会把旧配置末尾的 `/v1` 规范化移除；请求构造仍兼容尚未重新保存的旧 `/v1` 配置，保证不会产生重复的 `/v1/v1`。回归覆盖纯基础地址与旧 `/v1/` 地址均生成同一个最终 endpoint。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph AI 英文名批量翻译

- Morph 编辑器名称批处理行新增 `AI翻译` 和相邻的设置图标。设置弹窗提供 OpenAI-compatible API 请求地址、隐藏显示的 API Key 与用户自填模型名；地址只填写到 `/v1`，插件调用时自动追加 `/chat/completions`。三项配置存储在插件 `AddonPreferences` 而非 Scene，并在确认设置时保存 Blender 用户首选项，因此不会随新建或切换 `.blend` 工程丢失；相同设置也可在 Blender Add-ons 首选项中编辑。
- `AI翻译` 只读取当前 Morph 类型 Tab 中已勾选项，将日文或中文 `name` 一次批量提交，并要求模型返回与输入严格等长、顺序一致的 JSON 字符串数组。提示词明确要求保留原名称中的符号、数字、空格、下划线、括号与正负号；仅在整批响应可解析且数量完全匹配时才统一覆盖 `name_e`，避免部分失败或错位污染名称。HTTP、连接、JSON 和数量错误都会保留原英文名并在面板提示。
- Blender 4.4.3 回归以隔离的模拟 API 覆盖当前 Tab 多选翻译、英文名回填、空选择拒绝及带 Markdown code fence 的 JSON 解析，不发出真实网络请求；`mmd_morph_editor_regression.py` 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。另以真实安装入口在 `--factory-startup` 下启用插件，确认全局 `AddonPreferences` 及 URL/API Key/模型三项属性可读取，输出 `MORPH_AI_GLOBAL_PREFS_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 日文名批量同步到英文名

- Morph 编辑器在当前页的 `全选 / 全不选 / 反选` 下方新增 `日文名同步到英文名` 批处理按钮。操作只处理当前 Morph 类型 Tab 中已勾选的行，将每项 `name` 覆盖写入 `name_e`；未勾选任何 Morph 时取消并提示，不影响其它 Tab 或未勾选项。操作支持 Undo。Blender 4.4.3 回归覆盖多项同步与空选择拒绝，`mmd_morph_editor_regression.py` 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`；`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 详情列表默认八行高度

- Material、UV、Bone、Group 的 Morph Offset 详情列表默认可见行数由 4 行调整为 8 行，使列表主体高度与右侧“增加、删除、置顶、上移、下移、置底、插入活动项前、插入活动项后”八个按钮对齐；三组按钮之间的半行间距保持不变。Vertex 详情不是 Offset `template_list`，不受本次调整影响。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 详情智能材质添加与完整排序

- Material Morph 详情列表的 `+` 改为智能添加：读取当前 MMD Root 内全部已选 Mesh，活动 Mesh 优先，并按每个物体的材质槽顺序收集所有非空材质；共享材质与当前 Morph 已存在材质按材质 datablock 去重，避免重复 offset 造成叠加。新增项写入对应 `related_mesh` / `material`，作为连续块插入蓝色活动详情行下方，并将第一条新增项设为活动行。未选中本模型 Mesh 或没有可新增材质时明确取消并提示。UV、Bone、Group 详情页的 `+` 仍保持新增空 offset 的原逻辑。
- Material、UV、Bone、Group 的详情列表右侧统一补齐六个移动入口：置顶、上移、下移、置底、插入活动项前、插入活动项后；与主 Morph 列表一致分为“增加/删除”“四向排序”“活动项前后插入”三组。排序只处理已勾选详情行，保持多选块内部顺序与蓝色活动行，活动行属于勾选块时拒绝前后插入。Vertex 详情行是按模型实时汇总的 Mesh/ShapeKey 命中结果，不是可写回 PMX 的 offset 集合，因此不显示无语义的增删/排序入口。
- Blender 4.4.3 headless 回归覆盖：多选 Mesh 的多材质槽收集、共享材质去重、活动行后插入、重复添加拒绝、其它 Tab 保留空 offset 添加，以及六种详情排序和活动行保护；`mmd_morph_editor_regression.py` 输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，完整 `headless_smoke.py` 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Material Morph 详情批量显隐预设

- 在 Material Morph 详情面板的运算模式控件上方新增并排的 `预设：隐藏` 与 `预设：显示`，仅批量处理当前 Material Morph 详情列表中已勾选的 offset 行；没有勾选时明确取消并提示，不修改蓝色活动行或其它未勾选行。所有详情列表统一新增 `全选 / 全不选 / 反选`：Material、UV、Bone、Group 操作当前 Morph 的 offset 行，Vertex 操作当前 Morph 命中的 Mesh 行。
- 两个预设都把运算模式设为 `ADD`，并完整清零 Specular RGB、Shininess、Ambient RGB、Edge Weight、Base/Sphere/Toon Texture RGBA，避免旧参数残留；`隐藏`将 Diffuse Alpha 与 Edge Alpha 设为 `-1`，`显示`将两者设为 `1`，Diffuse/Edge RGB 均为 `0`。应用后立即重新计算当前 Morph Root，使非零滑条下的材质输出同步更新。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 列表统计与选择按钮统一

- 在 Morph 编辑器列表和选择按钮之间新增统计行，显示全部五类 Morph 的总数量、当前类型 Tab 的 Morph 数量，以及当前 Tab 内已勾选数量；统计直接读取现有 `spx_morph_states` 缓存，不触发额外模型扫描或 Runtime 更新。
- 三个选择按钮与 MMD 查看器统一为相同顺序和文案：`全选 / 全不选 / 反选`。按钮仍只作用于当前 Morph 类型 Tab，因而“已勾选”统计与实际按钮作用范围保持一致。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。
