# Development Log

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

## 2026-08-28 - V0.1.8 Group Morph Bone/UV 贡献归零复位

- 修复 Group Morph 从非零降到 `0` 时 Bone Morph 或 UV Morph 可能保持上一帧贡献、无法复位的问题。根因是 Group 更新路径只在当前有效权重中仍存在非零 Bone/UV 值时才调用 `_sync_placeholder_weights()`；当 Group 的最后一份 Bone/UV 贡献恰好归零，`needs_runtime` 变为假，已经存在的 mmd_tools 轻量 Runtime 因而没有收到新的零值，placeholder ShapeKey 和受驱动骨骼继续停在旧值。
- Group 更新与通用帧更新路径现在区分“是否需要首次创建 Runtime”和“Runtime 是否已经存在”：非零贡献仍按需首次绑定；一旦 Runtime 已存在，无论本次权重是否全部归零，都会同步全部 Bone/UV Morph 的当前有效权重，把消失的 Group 贡献显式写回 `0` 或剩余的直接滑条值。Material 与 Vertex Morph 路径未改。
- 回归用例将直接 Bone Morph 值保持为 `0.3`，再由 Group 叠加到 `2.7`，随后把 Group 从 `1` 拉回 `0`；断言作为骨骼 Runtime 驱动源的 placeholder Bone Morph 精确回到 `0.3`，不再残留 Group 的 `2.4` 贡献。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Bone Morph 转 Vertex Morph 权重范围收缩

- Morph 编辑器骨骼页的单个转换和批量转换入口不再直接调用 `mmd_tools` 的全模型转换，而由插件先读取当前 Bone Morph 的全部骨骼 offset，并将每个直接引用骨骼的全部递归子孙骨骼纳入影响范围；随后筛选同时满足两项条件的 Mesh：Armature Modifier 指向当前 MMD 骨架，并且至少一个影响范围内的骨骼顶点组包含非零权重。这样父骨 Morph 会正确覆盖仅由子骨或更深后代骨骼加权的网格，同时没有相关层级权重的 Mesh 不再创建 Basis 或目标 ShapeKey。
- 对命中的 Mesh 继续按顶点级权重裁剪结果：仅直接引用骨骼或其递归子孙骨骼顶点组中具有非零权重的顶点保留转换后坐标，其余顶点通过批量 `foreach_get` / `foreach_set` 强制恢复为 ShapeKey 的 Relative Key 坐标，避免其它当前 Pose 或 Armature 影响混入该 Vertex Morph。Blender ShapeKey 数据块在结构上仍必须为每个 Mesh 顶点保留一个坐标槽，无法变成真正的稀疏数组；本次保证的是无关顶点零差值，因此不会形成有效形变或 PMX Vertex Morph offset。
- 新增回归场景覆盖“Bone Morph 只移动父骨、Mesh 只有子骨顶点组权重”：四个同骨架 Mesh 中仅一个 Mesh 的一个顶点具有该子骨非零权重，另一个只有父骨同名空顶点组，第三个只有无关骨骼权重，第四个完全无组。实际转换只在首个 Mesh 创建 ShapeKey，且仅该子骨权重顶点产生非零差值，其余两个顶点严格等于 Basis，其它三个 Mesh 均不创建目标 ShapeKey；输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 与 MMD 查看器紧凑排序控件

- Morph 编辑器右侧排序列补齐“插入活动项前”和“插入活动项后”，完整顺序固定为：增加、删除、置顶、上移、下移、置底、插入活动项前、插入活动项后。视觉上以半行间距明确分成“增加/删除”“四个方向排序”“活动项前/后插入”三组。新增入口采用 Blender 4.4 原生 `ANCHOR_TOP` / `ANCHOR_BOTTOM` 图标，悬停文案说明实际动作；多个勾选 Morph 会保持原相对顺序作为一个块插入，蓝色活动行作为锚点，活动行同时被勾选时拒绝执行，避免插入位置歧义。
- MMD 查看器移除占宽的横向排序面板，把置顶、上移、下移、置底、插入活动项前、插入活动项后六个入口改为列表右侧单列小图标，并在四向排序和前后插入之间加入同样的半行分组间距；材质页的按钮列使用 `BLANK1` 空白图标行跳过表头高度：标准 UI 行高确保第一个按钮与第一条表格数据行对齐，图标宽度又将整列约束为窄列，避免空文本 `label` 撑粗或 `align=True` 折叠 `separator`。材质表头与列表保持在同一列，不会因右侧按钮挤压而错位。排序算法、勾选块语义和实际 PMX 顺序写回路径保持不变。
- Blender 4.4.3 headless 验证通过：`mmd_morph_editor_regression.py`、`mmd_ordering_user_control_regression.py`、`mmd_material_order_regression.py` 与完整 `headless_smoke.py`；完整 smoke 新增 MMD 查看器恰好绘制 6 个紧凑排序入口的断言，并输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-28 - V0.1.8 Morph 详情目标选择与 Vertex 物体定位

- Vertex Morph 详情中的每个命中 Mesh 行现包含独立复选框、可点击的 Mesh 名称按钮和原有真实 ShapeKey 滑条。点击名称会验证目标仍属于当前 MMD Root、退出可安全退出的编辑模式、取消当前 View Layer 内其它选择、取消目标的临时隐藏、独选并激活该 Mesh，同时把 `active_shape_key_index` 切到当前 Morph 的同名 ShapeKey；不创建 mmd_tools Vertex Binding，也不改变中央直接聚合求值方式。
- 为后续批处理建立了持久详情选择状态。Material、UV DATA、Bone、Group 的官方 Offset 列表改由插件包装 UIList 绘制，在完整保留 mmd_tools 原行内容与活动索引的同时，在每行最前增加 `spx_morph_detail_selected`；Vertex 与 UV Vertex Group 目标按 Mesh 分别使用 `spx_morph_vertex_target_selected`、`spx_morph_uv_target_selected`，避免切换分类时互相串选。当前只建立选择数据与 UI，不提前实现未经定义的批量操作。
- UV 详情补全两种数据模式的目标行：`DATA` 模式显示带复选框的 `UVMorphOffset` 列表；`VERTEX_GROUP` 模式按实际 Mesh 聚合对应 `UV_<Morph>[+-][XYZW]` Vertex Group，并显示独立 Mesh 复选框与 Axis 摘要。Material/Bone/Group Offset 的增删、参数编辑和 mmd_tools 辅助图标继续沿用既有入口。
- `tests/mmd_morph_editor_regression.py` 新增各 Offset 类型选择属性的可写/持久性、Vertex/UV Mesh 选择状态隔离，以及 Vertex 详情按钮独选指定 Mesh并激活同名 ShapeKey 的断言；Blender 4.4.3 headless 继续输出 `MMD_MORPH_EDITOR_REGRESSION_OK`，`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 VMD Morph 自动接管与有符号数值输入

- 本插件现在运行期挂载 `mmd_tools.import_vmd`，不修改 mmd_tools 源码。导入前为被选 MMD Root/模型 Mesh 补齐未绑定的 `.placeholder` Morph 名称，使 mmd_tools 能接收 PMX 中全部 Vertex/Material/Bone/UV/Group Morph 帧；导入结束后把 placeholder ShapeKey FCurve 迁移为 MMD Root 上稳定的 `spx_morph_states["UID"].value` 曲线，并删除 placeholder 与真实 Mesh 上的重复 Morph ShapeKey 曲线。普通 Action 会并入 Root 当前 Action，NLA 会复制对应 strip 时序与混合参数；Blender 4.4 的新 Action 先建立 FCurve、再挂到 Object，避免产生无有效 Action Slot、曲线存在却不播放的空 Layered Action。
- VMD 导入完成即递归分析所有已导入 Group Morph：若涉及 Bone/UV，立即建立轻量 mmd_tools Runtime；若涉及 Material，立即为实际目标材质安装本插件 Material Output Bridge，并仅在 Edge 通道有有效 Offset 时安装描边 Bridge。随后在当前帧统一求值，因此材质、Bone、UV 不再等播放第一次命中关键帧才初始化。`create_new_action` 同时把未包含在本次 VMD 中的本插件 Morph 状态复位为 `0`，而默认追加导入继续保留其它既有状态。
- 中央所有 Morph 状态移除 `-10～10` 硬范围，仅保留鼠标滑动的 `soft_min=0` / `soft_max=1`；点击数值框可键入负数或大于 `1` 的有符号值。Group、Material ADD/MULT、Bone、UV 与 Vertex 均按该有符号权重求值；真实 Vertex ShapeKey 在写入前动态放宽其 Blender `slider_min/slider_max`，避免常用负值或大于 `1` 的值被现有 ShapeKey 滑条截断。Material Alpha 最终仍按物理有效范围 `0～1` 输出，负 ADD 权重会在公式中反向为减法/加法；RGB 继续采用既定的近似 Output Bridge 表现。
- `tests/mmd_morph_editor_regression.py` 新增 FloatProperty 软/硬范围、Vertex `-2.5/3.25` 跨 Mesh 同步与实际 ShapeKey 范围扩展、负 Material ADD RGB、普通 Action/NLA VMD 曲线迁移、稳定 UID Data Path、源 ShapeKey FCurve 清理及导入 Runtime 预初始化断言，输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。另以原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\19.blend` 不保存导入真实 `Motion.vmd`：匹配 35 个 Morph，Root 生成 35 条稳定 UID 曲线，placeholder 残留 Morph 曲线为 0，Runtime Error 为空并输出 `SPX_REAL_VMD_IMPORT_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Vertex Morph 直接聚合与 UV 预览安全清理

- Vertex Morph 求值改为与 Velo Tools `VELO_ShapeKeyAggItem` 相同的直接聚合模型：以 PMX Vertex Morph 名称查找当前 MMD Root 下全部真实 Mesh 的同名 ShapeKey，并直接写入各自 `key_blocks[name].value`。不再把 Vertex 值写入 mmd_tools `.placeholder`，即使 Bone/UV 后续必须建立官方 Runtime，插件也会删除官方 bind 生成的 Vertex driver 与 `mmd_bind*` 辅助 ShapeKey、解除真实 ShapeKey 的 mute；用户因此可以进入任意单独网格直接调试真实 ShapeKey，下一次中央 Vertex/Group 值变化时再统一同步所有同名贡献对象。已有非 mmd_tools 用户 driver 保留且不由聚合器覆盖。
- Group Morph 继续由插件计算有效权重，但 Vertex 子项现直接写入真实 ShapeKey，只有 Bone/UV 子项进入 mmd_tools Runtime；纯 Vertex/Material Group 不再仅因自身是 Group 而创建 `.placeholder`。真实 `[HighHeels]` 的 `高跟足*` 在 5 个网格上直接同步为 `1`，官方 Group 与 Vertex slider 均保持 `0`，Bone `上移` 仍正确展开为 `2.400000095`；完整模型真实 Mesh 中不再残留 `mmd_bind*` ShapeKey，单独网格手改 Vertex 值可立即保留。
- Morph 编辑器 UV 详情的“查看/清除”不再调用 `mmd_tools.view_uv_morph` 与 `mmd_tools.clear_uv_morph_view`，不修改 mmd_tools 本体。插件新增自己的安全预览路径：按活动 UV Morph 创建 `__uv.*` 临时层；清理时先把 Mesh 切换到对应基础 UV 层并更新数据，再按名称快照删除临时层，避免直接删除 UI/UV Editor 当前持有的活动层；按钮 operator 通过 Blender timer 等当前 UI 事件返回后才执行创建或清理，规避 GUI 悬空 RNA。编辑/应用仍沿用 mmd_tools 的数据写回能力，本轮只替换用户报告会闪退的查看/清除入口。
- `tests/mmd_morph_editor_regression.py` 新增 Bone/UV Runtime 建立后无 Vertex driver/辅助键、单网格独立调试、中央值重新聚合、Group 跨网格直接 Vertex 同步，以及临时 UV 层安全创建/恢复/删除断言，继续输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。原 `19.blend` 临时副本不保存验证：`進肚條-` 可直接写入真实 ShapeKey并单网格改值，`[HighHeels]` 同步 5 个真实 ShapeKey、Bone 权重正确，`絲襪破` 在 `000_Body` 创建并清理 UV 预览后无残留且无 Runtime Error。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Group Morph 原生闪退与展开权重修复

- 修复真实工程拖动组合表情 `[HighHeels]` 时 Blender 4.4.3 直接 `EXCEPTION_ACCESS_VIOLATION`。用户现场 `19.crash.txt` 与复制工程独立复现均显示栈顶为 `IDP_GetPropertyFromGroup -> pyrna_struct_get -> bpy_prop_update_fn`，复制工程在该 Group 首次 `0 -> 0.1` 时确定性闪退。根因有两层：插件在 Property update 内调用 `mmd_tools.bind()` 后，仍继续使用绑定前缓存的 PMX Morph RNA；而 bind 会回写 Bone/Material Morph offset 的内部名称，使旧 RNA 指针失效。旧路径还把插件 Group 值再次写进 mmd_tools Group slider，使同一 Group 同时由官方驱动图和插件递归展开，存在重复求值。
- Group Morph 现只由插件递归展开为最终 Vertex/Bone/UV/Material 权重；官方 Runtime 只接收展开后的 Vertex/Bone/UV 目标值，Material 继续由插件 Output Bridge 求值，官方 Group 与 Material slider 均不写入。任何首次 bind 返回后立即丢弃绑定前 `morph_lookup` 并从 Root 重新查询，杜绝失效 PropertyGroup 访问。直接 Vertex/Bone/UV 值与 Group 贡献在同一有效权重中合并，Group 归零时也会把目标 Runtime 正确复位。
- 补充目标 Runtime slider 动态范围扩展。真实 `[HighHeels]` 含 `高跟足* x1`、`高跟鞋1+/2+ x1`、`上移 x2.4`；默认 ShapeKey slider 上限 `1.0` 会把 Bone 权重截断，因此现按实际展开值放宽 `slider_min/slider_max`。原 `19.blend` 的临时副本连续执行 41 个 `0 -> 1 -> 0` 采样不再闪退，后续中位耗时约 `31 ms`；峰值时官方 Group slider 保持 `0`、Vertex 目标为 `1`、Bone 目标为 `2.400000095`，复位后三者目标均为 `0`，原工程未保存。`tests/mmd_morph_editor_regression.py` 新增 Material + Vertex + Bone 混合 Group、官方 Group 不写入、直接值与 Group 权重叠加及大于 1 的 slider 范围断言，继续输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Morph 滑条实时性能与基础 Alpha 修复

- 修复 353 个 Morph 的真实工程中中央滑条持续拖动严重卡顿。旧路径每次采样都会完整校验/重建状态索引、扫描 243 个 Vertex Morph × 全部模型 Mesh、重新计算 PMX 材质顺序，并由无条件 depsgraph handler 对插件自身的节点/ShapeKey 更新再次执行全量求值；真实连续探针曾因此运行约 68 秒后触发 Blender `EXCEPTION_ACCESS_VIOLATION`。现按变更类型增量执行：Material 只重新聚合 Material/Group 权重，未绑定的 Vertex 只更新当前 UID 的同名 ShapeKey，Bone/UV 只同步当前官方 Runtime Slider，Group 才同时处理官方非材质 Runtime 与插件 Material 输出；帧切换仍执行完整动画求值。
- 删除无条件的 Morph depsgraph 全量重算，保留滑条 Property update 与 `frame_change_post` 两个明确入口；后期新增描边仍会在下一次相关滑条/关键帧求值时发现。Morph UID 查找改为每次建立一次字典；官方 Material Binding 清理和非材质 Runtime 完整性检查均增加已完成快速路径；Material Morph 目标材质不再调用只为 PMX 导出顺序服务的昂贵 `ordered_materials()`，改为直接遍历当前 Root Mesh 的实际材质，因为 Morph 求值只需要目标集合、不依赖导出顺序。
- 修复 ADD 显示类 Material Morph 无效果。真实 `19.blend` 的绳子、配饰、袜子等大量目标材质 authored base Alpha 为 `0`、Morph Offset 为 `ADD +1`；旧公式错误从固定 `1` 起算，导致滑条 `0→1` 的 Output Bridge 始终为 `1`。现按 PMX 基础值计算 `base_alpha × MULT + ADD`，复位也恢复 authored base Alpha；Edge Alpha 独立使用 `mmd_material.edge_color.a`。首次接管还会把直接上游 Shader（包括真实工程的 `mmd_shader`）未连接 Alpha 输入规范为 `1` 并保存原值，由 Output Bridge 独占最终透明度，否则基础 Alpha 为 `0` 的上游 Shader 已经全透明，输出端无法重新显示。
- 原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\19.blend` 不保存探针确认：Material 连续 21 次求值从单次约 `72–80 ms` 降至约 `9.5 ms`，Vertex 约 `6.9 ms`，Bone 首次建立官方 Runtime 约 `0.57 s`、后续约 `0.49 ms`；`繩子1/繩子1+` 的 base Alpha 均为 `0`，滑条 `0.375` 时两个 Bridge 均为 `0.375`、复位后均为 `0`，上游 `mmd_shader.Alpha` 已规范为 `1`，Runtime Error 为空。`tests/mmd_morph_editor_regression.py` 新增 base Alpha 0 + ADD 显示、上游 Alpha 规范化与复位回归并输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Morph 参数详情与描边独立求值

- Material Morph 详情不再把 RGBA/向量字段画成大块颜色选择器，改为复刻当前 `mmd_tools 4.5.5` Morph Tools 的数值参数布局：相关网格与材质选择、乘算/相加及 0/1 快速初始化、Diffuse RGBA、Specular、Shininess、Ambient、Edge RGBA、Edge Weight、Base/Sphere/Toon Texture Factor 均按独立通道直接编辑。
- UV 与 Bone 详情改按官方面板的数据模式和操作入口绘制。UV 提供查看/清除、编辑/应用，并根据 `VERTEX_GROUP` 或 Offset 模式显示 Scale/Offset 数量和 UV Index，不再错误地同时展示不适用的 Offset 列表；Bone 提供查看/应用/清除、转换为 Vertex Morph、Bone Offset 列表、Pose Bone 搜索、选择/编辑/更新，以及并列的 Location/Quaternion 数值。中央列表切换类型或活动行时同步官方 `active_morph_type/active_morph`，保证这些 `mmd_tools` operator 操作的是当前行。
- 描边材质取消“本体最终 Alpha × 描边最终 Alpha”的强制联动。Diffuse RGBA 只求值本体输出，Edge RGBA 只求值 `mmd_edge.*` 输出；只有 Edge 通道产生实际非中性结果时才首次安装描边 Output Bridge，已有描边 Bridge 在 Edge 通道复位时恢复中性。本体隐藏而 Edge Alpha 未设置时，描边保持自己的实际值；后期新增描边材质仍会在后续存在有效 Edge Morph 时被发现并接管。
- `tests/mmd_morph_editor_regression.py` 更新为断言官方活动 Morph 同步、本体与描边 Alpha 独立、无 Edge 变化不安装描边 Bridge、有效 Edge MULT 才按需安装，以及 Group Morph 不再让本体 Alpha 强制覆盖描边，输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\19.blend` 不保存 GUI 复测确认 Material 数值通道、UV 官方模式和 Bone 官方操作/参数区均正常显示且无面板异常。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 材质表头与编辑列对齐

- 修复材质查看器表头依靠多个无约束 `label` 自动分配宽度、而列表行依靠另一套 `split` 比例，导致“序号 / Blender 材质名 / MMD 名称 / MMD 英文名”与下方实际编辑框横向错位的问题。表头和每一行现统一调用同一套五列布局：勾选、序号及三列等宽名称；序号和四个表头显式居中，编辑框继续使用 Blender 原生可编辑文本控件。
- `python -m py_compile`、`git diff --check` 通过，Blender 4.4.3 focused regression 继续输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Morph 编辑器真实工程空白修复

- 修复真实旧工程进入 `Morph 编辑器` 后只显示 MMD 模型选择行、其余 UI 全部空白的问题。根因不是工程缺少 Morph，而是面板 `draw()` 每次都会无条件回写 `SPX_MorphState.morph_type/morph_name`；Blender 4.4 在 UI 绘制上下文禁止修改 ID 数据，因此以 `Writing to ID classes in this context is not allowed` 中断后续五类页签与列表绘制。
- 面板绘制现改为纯只读校验 Morph 与 Runtime State 的数量、顺序、稳定 UID、类型和名称；缓存缺失或失效时只登记一次 Blender timer，在当前绘制结束后安全刷新并重绘所有 3D View。`ensure_morph_states()` 同时避免对未变化的类型和名称重复赋值，首次打开尚无缓存的旧工程仍会自动加载，不要求用户手动点刷新。
- 对原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\19.blend` 进行不保存复现与 UI 验证：目标 Root `合并2` 实际含 Material 34、UV 16、Bone 25、Vertex 243、Group 35，共 353 个 Morph；修复前稳定抓到上述 `draw_morph_editor()` 异常，修复后相同窗口完整显示五类页签、名称开关、搜索、353 项列表及活动项详情，日志不再出现该异常。`tests/mmd_morph_editor_regression.py` 新增缓存新鲜/失效/重建断言并继续输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 Morph 编辑器与通用 Material Output 接管

- 在顶层 `MMD 查看器` 与 `物理预览` 之间新增 `Morph 编辑器`，直接读取当前 `mmd_tools 4.5.5` 支持的 Material、UV、Bone、Vertex、Group 五类 Morph。每类列表提供日文名/英文名开关、搜索、逐行勾选、全选/反选、稳定块置顶/上移/下移/置底、新增/删除、分类编辑和中央可动画滑条；活动项下方复用官方 Offset UIList 并直接编辑各类 Morph 数据。每个 Morph 在原 PropertyGroup 上获得稳定 UUID，MMD Root 保存具名 Runtime State，关键帧路径不依赖可变 Morph 名称；排序同步各类型 Collection 和“表情”Display Frame，使 UI 顺序继续参与实际 PMX Morph 提交顺序。
- Vertex Morph 中央滑条同步当前模型全部 Mesh 的同名 ShapeKey，不再要求用户逐物体调整。Bone/UV/Group 首次产生值时按需建立官方非材质 Runtime：临时阻止 `_MaterialMorph.setup_morph_nodes()`，保留 `mmd_tools` 的 Bone/UV/Group 驱动能力，同时移除可能已有的 `mmd_bind*` Material Morph 节点，避免官方每个 Offset 一条节点链与新后端重复求值。Group Morph 在插件侧递归展开到 Material Morph，循环引用安全停止；滑条和关键帧由 frame/depsgraph handler 继续求值。
- Material Morph 第一次实际影响某材质时，才在该材质每个已连接的 `Material Output.Surface` 前插入一个共享 `SPX_MaterialMorphOutput`；同一输出后续只更新输入，不反复增删节点。上游 Shader 保持原样，因此 MMD Shader、Principled BSDF、Emission 和用户自制 Shader Group 使用同一路径。所有非零 Material/Group Morph 先按材质聚合：`MULT` 乘积与 `ADD` 和分开累计后统一得到 Alpha，负 `ADD` 自然作为减法；RGB 映射为通用 Tint/Emission 视觉染色，不宣称精确 PMX 光照语义。
- `mmd_edge.<本体材质名>` 作为本体材质的附属描边处理：本体和已存在描边同步接管；描边未创建时不报错，后期创建、改名或重新生成后，下一次滑条、关键帧或 depsgraph 求值会通过本体稳定材质 ID + 当前名称重新发现并补装一次。描边最终 Alpha 固定为“本体最终 Alpha × 描边自身最终 Alpha”，本体隐藏时不会残留浮空轮廓。新增 `tests/mmd_morph_editor_regression.py`，覆盖具名关键帧路径、Morph 排序与 Facial Frame、三个 Mesh 同名 ShapeKey 同步、Principled 与自制 Shader Group 首次接管、节点不重复、Alpha `MULT+ADD`、RGB 输入、后建 Emission 描边自动补装、本体主导描边隐藏、关键帧帧切换、Bone/Group 轻量 Runtime 及官方 Material 节点未回流；输出 `MMD_MORPH_EDITOR_REGRESSION_OK`。现有 `mmd_material_order_regression.py` 与完整 `headless_smoke.py` 继续通过；版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 材质顺序增量自动校对

- 材质页在手动校对与按材质拆分旁新增“自动同步”开关，默认关闭。旧模型首次仍须执行一次完整“校对材质 ID 与物体编号”；初始化完成后，每次调整 PMX 材质顺序都会比较变更前后的完整顺序，只处理材质实际发生换位的 index。因此单材质移动、多个连续或非连续勾选材质作为稳定块置顶/上移/下移/置底/插入均使用同一逻辑，不依赖“只有一个材质在移动”的假设。
- 增量路径只改写变动 index 上材质的 `mmd_material.material_id`、这些材质及外部冲突材质的 Material Morph 引用，以及实际使用受影响材质的单材质 Mesh 三位前缀；顺序未变位置上的材质和单材质 Mesh 不重写，多材质 Mesh 名称始终不动。材质集合新增/移除或旧 ID 尚未完成首次校对时不猜测增量基线，保留新查看器顺序并要求手动完整校对。
- 扩展 `tests/mmd_material_order_regression.py`：在四材质顺序中同时勾选两个材质作为稳定块上移及下移，断言所有实际换位材质的 ID 与单材质物体前缀同步、未换位第四材质的故意自定义前缀不被重写、多材质守卫对象名称不变，并在移除临时第四材质后完整校对恢复原导出 fixture。Blender 4.4.3 headless 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，`mmd_ordering_user_control_regression.py` 输出 `MMD_ORDERING_USER_CONTROL_REGRESSION_OK`，完整 smoke 继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；`python -m py_compile`、`git diff --check` 与 UTF-8/no-BOM 检查通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 材质 ID、物体编号校对与定向拆分

- 澄清查看器顺序与 `mmd_material.material_id` 的语义差异：查看器和 PMX material table 都从 `000` / index `0` 开始；官方 `FnMaterial.material_id` 则是 Blender 文件内跨模型使用的全局材质关联 ID，旧导入材质保持 `-1` 属于尚未分配，第一次经官方属性访问时会从全局现有最大 ID 的下一位分配。因此查看器第 `009` 项出现 ID `19` 不是从 `10` 起算，也不是前一轮材质顺序代码写成 `19`，而是官方全局分配器此前已有 `0–18`。
- 材质页新增“校对材质 ID 与物体编号”：按当前查看器顺序把当前模型材质 ID 明确写成 0-based `0…N-1`，同时更新 Material Morph data 的关联 ID。首轮曾在其它模型或残留材质占用目标 ID 时整体取消，真实旧工程因此报告 `AnalHook.001` 等 `0–85` 冲突；现改为先把这些外部冲突材质迁移到全局现有最大 ID 之后，再同步所有 MMD Root 中指向它们的 Material Morph ID，当前模型仍可完成 `0…N-1` 校对且不制造全局重复 ID。模型内只对实际使用一个材质的 Mesh 调用官方 `MoveObject.set_index()` 写入三位前缀；使用多个材质的 Mesh 名称完全不动，其材质序号仍被单材质物体自然跳过，形成拆分用预留编号。
- 校对按钮旁新增“按材质拆分（保留法向）”：使用官方 `utils.separateByMaterials(..., keep_normals=True)`、ShapeKey 清理、UV Morph 清理和 Material Morph related-mesh 更新流程，但不调用官方会遍历并重编号全部模型 Mesh 的尾段。插件只识别活动目标 Mesh 本次保留下来的原对象和新拆出的对象，并按各自唯一材质的查看器顺序写入预留编号；其它 Mesh 名称不变。
- 扩展 `tests/mmd_material_order_regression.py`：用 `0/1/2` 断言当前模型材质 ID 校对，并用额外 `ID=0` 外部材质复现冲突、断言其被安全迁移到 `>=3`；同时验证单材质物体成为 `000_...`、多材质物体校对时保持原名、拆分后两个目标物体进入 `001_...` / `002_...`、其它物体名不变、临时 `mmd_normal` 属性已清除且导出/重导入顺序仍一致。Blender 4.4.3 headless 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，完整 `headless_smoke.py` 继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 PMX 材质真实顺序查看与导出接管

- 调查确认官方 `mmd_tools` 的默认 PMX 材质顺序不读取材质名前缀，也不直接读取 `mmd_material.material_id`：导出器先按 Blender Mesh 物体名排序，再按各 Mesh 中实际被面使用的材质槽索引遍历，同一材质第一次出现的位置决定最终 PMX 材质顺序。因此合并/拆分 Mesh、改变物体名或重排材质槽会让顺序漂移。
- 在 `MMD 查看器` 的骨骼左侧新增“材质”页。列表按插件维护并实际提交给 PMX 的顺序显示，每行提供勾选框、三位顺序编号以及可直接编辑的三列：Blender 材质名、MMD 名称、MMD 英文名；复用现有稳定块置顶/上移/下移/置底/插入操作。下方新增“Blender 名同步到 MMD 中/英文名”和“MMD 名同步到 Blender 材质名”两个模型级批量入口。
- 新增模型级持久材质身份与顺序。每个材质使用独立稳定 ID，MMD Root 保存该模型自己的 ID 顺序；插件挂载 `PMXImporter.__importMaterials`，在官方按 PMX material table 创建完材质时立即记录原文件顺序，而不是等用户合并 Mesh 后再从物体名猜测。材质改名、Mesh 合并/拆分或跨物体复用不会丢失顺序，新出现且实际被面使用的材质按官方当前默认顺序追加，已不再使用的材质自动从有效列表移除。
- 通过 monkey-patch 挂载接管官方 `mmd_tools` PMX 导入/导出，不修改其核心源码：官方完成 Mesh/材质收集后、导出 Material Morph 前，插件同步重排 PMX material 表与对应连续 face blocks，并关闭会覆盖手工顺序的官方距离式 `sort_materials`。新增 `tests/mmd_material_order_regression.py`，覆盖跨两个 Mesh 的默认首次出现顺序、材质页单材质置顶、材质改名后稳定身份、双向名称同步、以 `sort_materials=True` 调用官方导出仍得到插件指定 `PMX_B, PMX_C, PMX_A`，以及重新导入该 PMX 后自动保存同一顺序；Blender 4.4.3 headless 输出 `MMD_MATERIAL_ORDER_REGRESSION_OK`，完整 `headless_smoke.py` 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`，现有 `mmd_ordering_user_control_regression.py` 继续通过，`python -m py_compile` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 稳定中长裙横 Joint 位移锁定

- 修正内置“稳定中长裙”物理参数预设：横 Joint 的起始/末端三轴移动下限、移动上限和移动弹簧全部设为 `0`，同时关闭横 Joint 移动限制与移动弹簧的三轴补间。横 Joint 因此只保留既有旋转限制和旋转弹簧，不再允许刚体 A/B 沿 Joint 局部轴发生相对平移；纵 Joint、刚体及碰撞参数未改。
- 更新 Blender 4.4.3 headless smoke 的预设回归断言，确认横 Joint 移动上下限、移动弹簧及其末端值全部为零，两个补间开关均为三轴关闭；完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`，`python -m py_compile` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-27 - V0.1.8 横 Joint Y 轴正反面统一

- 修复“应用参数到当前代理”补建的规则横 Joint 在背面头发代理上 Y 轴与相连刚体及纵 Joint 相反的问题。横 Joint 的 X/Z 几何轴仍由代理网格计算，不复制刚体 rotation；Y 轴正反面优先读取两端刚体保存的 `surface_proxy_normal`，旧物理首次接管缺少该字段时才回退到刚体当前局部 Y。两端参考先统一方向并对 Z 正交化；若网格法线反向，则同时翻转 X/Y，保持 Z 纵向、正交关系和右手坐标系不变。纵 Joint 算法未改。
- 首次生成、应用时补建、应用时更新和“同步当前代理刚体和 Joint”现统一调用同一套横 Joint 轴构造。Blender 4.4.3 完整 headless smoke 新增背面网格与刚体正面参考相反时的定向回归，并验证横 Joint Y 与两端刚体保存法线同向、Z 不翻转、矩阵行列式为正，以及刚体 rotation 受保护且被任意改动时仍依据代理保存法线恢复；最终输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 从所选刚体创建手动 Joint

- 在 MMD 查看器的刚体页、列表操作区下方新增“根据所选刚体创建 Joint”。入口要求且只允许勾选两个属于当前代理的刚体；查看器活动项固定作为刚体 B，另一个勾选项作为刚体 A。通过两刚体绑定骨骼的祖先/后代关系判定类型：处于同一条骨链时创建纵 Joint，分属两条骨链时创建横 Joint；纵 Joint 直接使用刚体 B 名称，横 Joint 保留 `_H` 后缀。
- 手动 Joint 的位置不再直接取刚体 A/B 世界位置中点。横 Joint 读取两刚体局部 X 轴、纵 Joint 读取两刚体局部 Z 轴作为两端切线，统一朝向 A→B 后以刚体间距作为切线柄长度，构造三次 Hermite 曲线；Joint 位于曲线 `t=0.5`，横向 X 轴或纵向 Z 轴使用该点的曲线切线。两端朝向一致时，切线贡献在中点互相抵消，位置自然退化为直线中点；朝向不同时则按曲率向外偏移。Y 轴继续由两刚体局部 Y 轴同向平均后对曲线切线正交化，并以刚体 B 的正反面朝向为基准，再构造右手正交坐标系。最终转换回 Joint 父级的 Blender 局部坐标，不提前进行 MMD 坐标换轴。
- 新建对象写入 `surface_proxy_manual_joint` 标记和创建时的参数补间位置。“应用参数到当前代理”与“同步当前代理刚体和 Joint”会根据当前 A/B 刚体重新计算其曲线位置和轴线，并按纵/横 Joint 页参数更新限制与弹簧；横 Joint 自动补建/清理明确跳过手动标记，因此不合规则网格槽位的手动横 Joint不会被删除，而未标记的错误、重复或多余规则横 Joint仍沿用原清理逻辑。Blender 4.4.3 完整 headless smoke 覆盖同链纵 Joint、跨链非规则横 Joint、活动项=B、朝向不同产生非直线曲率中点、朝向一致退化为直线中点、曲线切线轴、Y 轴正反面、应用参数后保留，以及规则横 Joint 数量不变，输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；`python -m py_compile` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 应用保护跟随代理网格

- 将“应用保护（禁止更新）”的 10 个开关纳入代理网格自身保存的物理设置。执行“生成 MMD 刚体和 Joint”或“应用参数到当前代理”时，会把当前保护状态写入当前代理；切换“当前代理网格”时，会和质量、尺寸、Joint 参数等现有设置一起自动恢复该代理自己的保护状态，因此不同代理可以维持不同的勾选组合。旧代理或尚未保存保护字段的新代理按属性默认值恢复，即全部关闭。
- 保护状态使用独立的 `APPLY_PROTECTION_SETTING_NAMES` 合并到代理读写列表，没有加入自定义物理参数预设的 `PHYSICS_SETTING_NAMES`，因此加载/保存参数预设不会意外改变保护状态。Blender 4.4.3 完整 headless smoke 新增两个代理分别保存、切换并恢复相反保护组合的回归，随后复位测试状态并继续通过全部旧用例，输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；`python -m py_compile` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 横 Joint 纯代理网格轴线

- 横 Joint 不再读取任一刚体的 location 或 rotation，也不再直接套用单列纵向骨段坐标系。现完全使用代理网格四个控制点：两侧骨段中点连线作为横向 X 轴，两侧骨段方向的平均值作为纵向参考 Z 轴，正交化后叉乘得到 Y 轴；首次生成、应用参数时补建缺失横 Joint、更新既有横 Joint 三条路径统一使用该 Blender 局部坐标系。PMX 导出时仍由 `mmd_tools` 统一完成 MMD 坐标转换，插件不提前交换轴。
- 纵 Joint 与锚定 Joint 保持既有算法不变：由当前代理网格单列骨段方向、同层相邻列切线和朝外表面法线构建坐标系，本就不复制骨骼 roll 或刚体 rotation。只要“Joint 旋转保护”关闭，纵/横 Joint 都会分别按自身几何规则重算；刚体位置和刚体旋转即使同时受保护，也不会影响横 Joint 轴线更新。完整 Blender 4.4.3 headless smoke 覆盖刚体 A/B 的 location 与 rotation 同时被改乱并保护时横 Joint 仍恢复到原代理网格轴线，继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\12.blend` 非保存复测识别 36 个横 Joint，全部与纯代理网格期望旋转完全一致，最大旋转误差 `0`，48 个刚体最大矩阵变化 `0`，输出 `SPX_REAL_12_HORIZONTAL_GRID_AXES_OK`；版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 骨骼改名后重复识别代理修复

- 修复骨骼改名后“识别或恢复所选代理”可能第一次按位置恢复成功、再次点击却报“没有找到与所选网格匹配的代理骨链”的问题。根因是位置恢复会把代理保存的精确骨名更新为新名称；下一次识别判定这些名称全部有效后，旧代码却只在“保存身份无效”时加入位置恢复候选，没有为“保存身份有效”建立任何候选。现新增精确保存身份布局：按代理保存的列行数和骨名顺序直接恢复骨链，校验连续父子层级，并优先沿用有效顶点映射；只有精确身份失效时才回退到既有位置匹配。
- 完整 Blender 4.4.3 headless smoke 新增“骨骼改名后连续识别两次”回归并继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。对真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\12.blend` 的 `Bone_Hair_Surface` 做非保存复测：保存身份为 4 列、每列 14 个控制点、52 根 `Bone_Hair_A/B*.L/R` 骨骼，位置布局与精确身份路径均成功，最终输出 `IDENTIFY_OK Bone_Hair [14, 14, 14, 14]`。按用户要求完整撤销同轮尚未验收的横 Joint 旋转源码与测试改动；版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 骨骼名称同步到刚体与 Joint

- 在 MMD 查看器骨骼页的“补全并标准化 MMD 骨骼名称”区域新增“骨骼名同步到刚体”和“骨骼名同步到 Joint”。两个入口均只处理查看器已勾选骨骼：刚体按绑定骨骼重置 Blender 名称主体、MMD 名称和 MMD 英文名称；Joint 按刚体 B 绑定骨骼同步同三项。Blender 对象名沿用既有三位 PMX 顺序前缀，只将前缀后的主体复位为骨骼 Blender 名；骨骼的 MMD 日文或英文字段为空时，对应刚体/Joint 字段明确清空，不以其它名称回填。
- Joint 同步前会对当前代理重新执行既有物理关联：通过两端刚体 A/B 所绑定代理骨骼的列、行关系识别纵向、横向和锚定 Joint，因此旧 Joint 不要求由插件创建，也不依赖原有插件标记。横向 Joint 的 Blender 名称主体、非空 MMD 名称和非空 MMD 英文名称统一保留 `_H` 后缀；纵向和锚定 Joint 不追加。Blender 4.4.3 完整 headless smoke 删除横 Joint 元数据后验证自动重新识别，并覆盖 PMX 顺序前缀保留、刚体同步、横/锚 Joint 同步及空英文字段清空，输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK top_range=0.235911131 rigids=48 joints=96`；`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 刚体与 Joint 参数应用保护

- 在代理创建的“刚体”页签、“碰撞”区域下新增“应用保护（禁止更新）”，并在刚体、纵 Joint、横 Joint 三个页签共同显示。保护项按五行排列：刚体位置/旋转、Joint 位置/旋转、刚体形状/尺寸、刚体类型/刚体演算参数、碰撞设置/Joint 演算参数；其中 Joint 演算参数只保护移动/旋转限制及弹簧，位置与旋转由独立开关控制。保护默认关闭，只作用于底部“应用参数到当前代理”；首次生成与独立的刚体/Joint 同步路径保持原行为。
- “应用参数到当前代理”现在会在三个 Joint 保护均关闭时，根据“生成横向 Joint”补建缺失横 Joint或移除现有横 Joint，只调整当前代理的横向结构，不重建刚体和纵 Joint；任一 Joint 保护开启时保持现有 Joint 结构。旧物理对象不要求由插件创建：先按刚体绑定的代理骨骼恢复列/行，再通过 Joint 两端刚体 A/B 的同列相邻行或同行相邻列关系识别纵/横 Joint，端点反向同样支持；无法唯一识别的对象不猜测、不删除。对于代理网格有对应槽位、但旧物理缺少刚体端点的横 Joint，只跳过该位置并在结果中报告数量，不再中止其它参数应用。Blender 4.4.3 headless 回归覆盖无插件元数据的既有物理自动接管、保护开启时不移除、保护关闭后移除与重新补建，以及缺失刚体端点时跳过后继续、端点恢复后补建；真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\11.blend` 非保存探针确认 4 列代理各有 13 个刚体槽位，但旧物理每列缺末端第 13 个刚体，共 48/52 个刚体；非保存调用实际 operator 成功新增 31 个横 Joint、跳过最后一行 3 个无端点横 Joint，最终识别 36 个横 Joint，输出 `SPX_REAL_11_PARTIAL_HORIZONTAL_OK 36`。版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 下划线字母列号代理识别

- 修复从 MMD 查看器勾选骨骼创建代理时，将 `Bone_Hair_A1.L`、`Bone_Hair_B1.R` 中 `_A/_B` 列号误当作主体名称一部分的问题。名称符合 `主体_大写字母列号+数字行号` 时，现在统一提取 `主体` 作为代理前缀；无下划线的 `后发A1/后发B1` 仍保持为不同主体，避免放宽到不相关骨链。补充回归断言覆盖 A/B 左右骨链共同生成同一 `Bone_Hair` 主体；版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-26 - V0.1.8 撤回未通过验收的飘带预设

- 按用户决定移除“填入：轻盈复位飘带”按钮、专用 operator、参数函数及对应 smoke 断言。标准 PMX 刚体与 Joint 参数无法精确表达“静止严格保持原姿势、运动时才启用物理”，因此不保留容易产生错误预期的近似预设；既有“稳定中长裙”预设及本轮其它碰撞组、镜像命名等改动均不受影响。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 骨骼改名后按位置恢复代理

- 修复“识别或恢复所选代理”仍依赖 `<前缀>_Cxx_Rxx` 骨名的问题。代理保存的精确骨骼身份仍全部存在时继续优先使用该身份；只有保存骨名因改名而失效时，才将保存的控制顶点转换到 Armature 局部空间，并按每段 head/tail 位置与连续父子层级逐列重建真实骨链，恢复后把当前骨名重新写入代理元数据。多个骨链位置重合且无法唯一判断时拒绝猜测。
- 同时修复新建代理期间 depsgraph 自动识别可能抢在新骨创建完成前写入同位置旧骨名的问题：正式创建结束后始终保存 `_create_bones()` 返回的精确骨名。新增 headless 回归覆盖完整骨链改名、位置恢复、恢复后的代理驱动骨骼同步，以及两个位置相近代理的身份隔离；Blender 4.4.3 完整 smoke 输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。
- 使用真实 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\09.blend` 非保存调用面板同一 operator，`Bone_Piao_Surface.005` 成功按位置恢复为 `Bone_Piao228.L`、`Bone_Piao229.L`、`Bone_Piao228.R`、`Bone_Piao229.R`，输出 `SPX_REAL_09_RENAME_RESTORE_OK`。`python -m py_compile` 与 `git diff --check` 通过；版本保持 V0.1.8，源码 Junction 已直接生效，不保存工程、不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 快速选择按镜像加选

- 在骨骼、刚体和 Joint 查看器的“快速选组”中新增“按镜像加选另一边”。操作以当前全部勾选项为源，只追加镜像项、不清除或替换原勾选；可同时处理多项，并报告新增数与无匹配数。
- 骨骼配对同时检查 Blender 名、MMD 名称和英文名称，识别 `左/右` 前缀、`.L/.R` 与 `_L/_R`；刚体复用绑定骨骼镜像配对，Joint 通过两端刚体的镜像关系精确寻找对应项，避免 PMX 顺序前缀或重复显示名造成误选。Blender 4.4.3 完整 headless smoke 覆盖三种左右写法以及 Bone/Rigid/Joint 三个列表，分别输出 `已加选 3/1/1 个镜像项`，并继续通过 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`、`python -m py_compile` 与 `git diff --check`。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 刚体轴同步到 Joint 与镜像联动

- 在刚体查看器的镜像工具区新增“同步勾选刚体轴到关联 Joint”。操作保持 Joint 的世界位置与缩放不变，只把勾选刚体的当前世界旋转轴复制给以该刚体为 B 端点的关联 Joint；没有关联 Joint 时给出明确提示，不改其它对象。
- 既有“同步镜像刚体”路径本就会在“同时处理关联 Joint”开启时镜像复制刚体与关联 Joint 的完整世界变换，本轮补充操作顺序提示并加入端到端回归：先旋转左侧刚体，再同步源 Joint 轴，最后同步镜像，断言源 Joint 位置不变、轴向与刚体一致，右侧刚体与 Joint 均等于源侧的 Armature 局部 X 镜像。Blender 4.4.3 完整 headless smoke、`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 MMD 骨骼名称补全入口标准化

- 将骨骼查看器的“补全勾选”“补全全部”和活动项“补全当前”三个入口统一升级为全字段标准化：以 Blender 骨骼名的 `.L/.R`、`_L/_R` 为镜像侧权威来源，MMD 名称写成 `左/右 + 主体`，英文名称写成 `主体_L/_R`；非镜像骨骼正常按 Blender 骨骼名填写。普通已有字段也会重建，不再因非空而跳过。
- 对“中文 MMD 名称 + 英文名称”保留双方各自的主体，只移除旧的 `左/右`、`.L/.R`、`_L/_R` 标记并按 Blender 侧重新写入，避免把正式双语命名覆盖成同一个 Blender 名。完整 Blender 4.4.3 headless smoke 通过，原 `08.blend` 非保存探针确认 `Bone_Piao222.L`、`Bone_Piao231.L` 从 `Bone_Piao*_L/Bone_Piao*_L` 规范为 `左Bone_Piao*/Bone_Piao*_L`；`python -m py_compile` 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 二次 Clear + F9 仅选中重做错位修复候选

- 用户确认 `baseline-20260825-ik-physics-handoff` 的其余问题均已修复后，报告唯一剩余序列：启用 MMD IK 兼容，第一次 Clear 后在 F9 取消“仅选中”可正常归零；再次移动足 IK、第二次 Clear，再在 F9 勾回“仅选中”时，视口会闪回，IK 控制骨残留在移动位置，而 IK 链已按清空输入复位。先在用户原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\06.blend` 建立失败回归：目标 `足ＩＫ.L` 是 authored input control、并不属于 35 根 native output bones；重放 F9 最终时序中的“output 已恢复清空展示、selected control 仍残留 Undo 前矩阵”后，修复前稳定得到 `ik_input_error=0.0500000007`。
- 根因是 Undo/Redo resume 只保留一个隐式 `input_basis` 并在 post 阶段重新猜测 Clear：判断要求“所有保存输入为 identity，且当前选骨也为 identity”。F9 重做过程中 output closure 与 input-only IK control 可在不同 depsgraph 时刻落定；一旦当前 control 暂时仍是 Undo 前矩阵，旧逻辑便把该残留矩阵重新采集为 authored input，形成“控制器在旧位置、链条按清空状态复位”的混合帧。
- 新增显式 `UndoRedoPoseTransaction`，在 `undo_pre/redo_pre` 同时冻结 authored `input_basis`、完整 `presented_basis` 与选骨名称。resume 不再只看当前选骨：若 transaction 证明进入 Undo 前的输入已经全部清空，并且当前 native output closure 已回到 transaction 的清空展示，则以冻结的 authored input 为唯一真值，主动把 selected input controls 写回该基线，再重置 solver 并统一求值。普通 Undo/Redo 若 output presentation 没有回到清空快照，仍按当前 Blender pose 重建输入，不会被误判为 F9 Clear 重做。
- 新增 `tests/mmd_ik_clear_f9_second_cycle_regression.py`，在原 `06.blend` 完整覆盖“Clear Selected → F9 Clear All → 移动 IK → Clear All → F9 Clear Selected”，并显式注入真实视口观察到的最后一拍 stale selected replay。修复后 normal IK、IK+PMX、IK+MMD 三组均为 `ik_input_error=0`、`ik_display_error=0`、`chain_error=0`，移动量约 `0.0500 m`；`MMD_IK_PHYSICS_CLEAR_REPEAT_REGRESSION_OK`、Clear User Transforms、Transform modal、physics feedback/reset、IK/Physics handoff、35-bone scoped ownership、高跟鞋与 runtime smoke 均继续通过。版本保持 V0.1.8，不修改三个 DLL、不打包、不 push，真实 GUI F9 操作仍等待用户重启 Blender 后验收。

## 2026-08-25 - V0.1.8 镜像 `_L/_R` 已有刚体配对修复

- 镜像核心的后缀解析原本已支持 `.L/.R` 与 `_L/_R`，但当前真实 `05.blend` 非保存探针发现已有刚体配对仍有一处漏点：`Bone_Piao222_L` 能正确解析为左侧并映射到骨骼 `Bone_Piao222.R`，随后 `_rigid_names()` 却将候选日文名规范化为 `右Bone_Piao222`，导致实际已有的 `name_j = Bone_Piao222_R` 被过滤。现改为配对时同时接受原始后缀镜像名与规范化 MMD 名，排序时优先原始镜像名；创建新对象时的既有规范化命名规则不变。
- 新增 `tests/mirror_underscore_suffix_regression.py`，覆盖截图对应形式的 `Bone_Piao222_L/Bone_Piao222_R` 名称、`.L/.R` 绑定骨、双向已有刚体查找以及左右两侧同时勾选时只处理左侧一次，输出 `MIRROR_UNDERSCORE_SUFFIX_REGRESSION_OK`；再以原 `05.blend` 非保存验证真实对象成功配对，输出 `MIRROR_UNDERSCORE_SUFFIX_REAL_MODEL_OK Bone_Piao222_L Bone_Piao222.L Bone_Piao222_R Bone_Piao222.R`。面板同步明确标注两套后缀均受支持。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 碰撞组编号统一为 0–15

- 将“代理创建”“MMD 查看器活动项属性”与刚体浏览详情中的碰撞组显示统一为 MMD 内部索引 `0–15`：碰撞组数值不再额外显示为 `1–16`，两行“不碰撞组”按钮也改为 `0–15`。底层 `collision_group_number` / `collision_group_mask` 数据及 physics runtime 语义未改动；更新对应 headless UI 断言并完成针对性验证。版本保持 V0.1.8，源码 Junction 直接生效，不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 IK / Physics 所有权交接验收基线

- 用户在真实 Blender 4.4 工程中确认关闭 MMD IK 兼容时的 physics 原地 handoff、刚体/物理骨保持以及其余相关回归均已修复，批准当前实现晋升为本地安全基线 `baseline-20260825-ik-physics-handoff`。该基线保留 `input_basis` / IK-owned `output_basis` / full-pose `presented_basis` 三层所有权，以及不重启 physics world 的 `RuntimeAdapterHandoff`；仍明确不包含随后报告的二次 Clear + F9“仅选中”重做错位修复。

## 2026-08-25 - V0.1.8 全“骨骼+物理”骨链位置冻结修复

- 用户在原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\06.blend` 中发现：当连续骨链刚体全部为“骨骼+物理”（type 2）时，预览只更新旋转，骨骼位置停留在启动位置。根因位于 Blender adapter 的层级回写，而非 PMX/MMD DLL：DLL 按 MMD type 2 语义返回动画位置与物理旋转，但 `_resolve_hierarchical_bone_targets()` 又把每根子骨写回 DLL 的绝对动画位置，覆盖了父骨物理旋转对其局部偏移产生的层级位移。
- type 2 回写现改为保留已沿父级解算出的 `inherited.translation`，只从 DLL 采用物理旋转和原层级 scale。这样骨自身的平移仍由动画局部变换控制，但连续子骨会像 MMD/PMX Editor 一样跟随父骨物理旋转移动；type 1 的完整物理解算、type 0 目标提交、DLL、fixed frequency/substeps 与 MMD IK 路径均未改动。
- 新增最小两级全 type 2 回归 `tests/type2_chain_translation_regression.py`：修复前稳定失败，子骨保持 `(0, 1, 0)`；修复后随父骨 90° 旋转到约 `(-1, 0, 0)`，输出 `TYPE2_CHAIN_TRANSLATION_REGRESSION_OK error=1.40579497e-07`。同步把既有 type 2 断言从错误的“绝对位置等于 DLL 动画位置”改为“相对父骨的局部动画平移保持不变”。
- 新增真实工程回归 `tests/mmd_06_type2_chain_translation_regression.py`，以 Blender 4.4.3 无保存加载上述 `06.blend`，识别 17 组连续 type 2 父子骨并运行 120 tick：PMX 为 `local_error=2.27339956e-07, displacement=0.052140129`，MMD 为 `local_error=3.1676404e-07, displacement=0.0501235642`。PMX/MMD `PHYSICS_ROOT_OFFSET_REGRESSION_OK` 与完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK` 继续通过。版本保持 V0.1.8，源码 Junction 直接生效，不修改 DLL、不打包 ZIP、不 push；真实交互视口观感仍待用户重启/Reload Scripts 后确认。

## 2026-08-25 - V0.1.8 骨链曲率细分、层级重排与权重等分

- 在 MMD 查看器“PMX 实际顺序”下方新增“骨骼细分”区域，提供 `2–32` 的“细分段数”和“细分勾选骨骼”操作。段数表示每根源骨骼最终包含的总段数；操作使用查看器复选框范围，完成后原骨骼与全部新增段保持勾选。
- 用户明确要求不能照搬 Blender 原生骨骼细分的逐骨直线切割。实现会读取源骨骼、连续父骨和方向最连贯的延续子骨 rest-pose 节点，使用 centripetal Catmull–Rom 曲线生成密集采样，再按弧长重采样为等长曲线段；分叉时优先选择勾选链延续，其次选择方向最连续的子骨，只有没有任何邻接曲率信息的孤立骨骼才直线均分。各段按源骨 `z_axis` 对齐 roll，避免曲线转向时产生无关扭转。
- 同一勾选链不再使用会破坏代理主体名识别的 `_S02/_S03`；改为从首根骨的原数字开始紧凑连续重编号，左右配对链共用同一数字范围。例如 `Bone_Piao160–162` 各分三段后为 `Bone_Piao160–168`，Blender 骨名、MMD 日/英文名及顶点组一并同步。新骨继承 Bone Collection、deform/inherit-scale/envelope 及关键 MMD transform/fixed/local-axis 元数据；保留父子层级但强制 `use_connect=False`，head/tail 仅位置重合，Edit Mode 下可用 G 移动。原直接子骨重挂到最后一段并保持自身原 `use_connect`。
- 新骨骼按细分后的连续数字链紧邻写入真实 PMX `bone_id`，只在写入前初始化一次无效 `-1` ID，最终不再执行会覆盖用户结果的 hierarchy realignment。对 MMD Root 下所有非 Rigid Mesh，原顶点组的每个非零权重在源骨与新增段之间按段数等分，不做空间猜测、不改变该组拆分前后的权重总和。骨骼重命名利用 Blender 对相关 Armature 顶点组的原子同步，避免循环重命名时二次覆盖正确的连续编号。
- 新增 `tests/mmd_bone_curved_subdivision_regression.py`，由 Blender 4.4.3 直接打开原 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\05.blend`（不保存），真实刷新查看器并勾选左右 `Bone_Piao160–162` 六根连续骨骼，以三段模式调用正式 operator，随后不修改勾选直接调用“从勾选骨骼恢复或新建代理”。验证从 `742` 根增加到 `754` 根，左右骨名均连续为 `160–168`，全部新骨未 Connected、PMX ID 紧邻、原子骨重挂、链端点不变、内部节点相对原直线最大偏移 `0.0002935930`，以及 `10` 个实际带权顶点组拆分后的最大权重误差 `2.98e-08`；成功新建含 `18` 根骨的两列代理，输出 `ACTUAL_05_BLEND_CURVED_SUBDIVISION_PROXY_OK`。完整 `tests/headless_smoke.py` 继续输出 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`，既有自由排序回归输出 `MMD_ORDERING_USER_CONTROL_REGRESSION_OK`，`python -m py_compile`、UTF-8/no-BOM 与 `git diff --check` 通过。版本保持 V0.1.8，源码 Junction 直接生效，不保存原工程、不打包 ZIP、不 push。

## 2026-08-25 - V0.1.8 PMX 骨骼实际顺序恢复用户直接控制

- 用户指出“PMX 实际顺序”会错误阻止骨骼移动，且从未要求插件替用户限制父子骨顺序。根因是排序层自行扩展勾选范围：移动父骨会自动携带所有子级；随后又用父骨和追加变换依赖关系拒绝写入目标 `bone_id` 顺序。这两项都是插件策略，不是当前排序操作不可绕过的格式限制。
- 删除骨骼子级自动扩选与父子/追加变换顺序校验。随后真实 GUI 复测暴露第二层问题：`_apply_bone_order()` 在移动后调用 `FnModel.realign_bone_ids()`，该官方修复函数会按父子/追加变换依赖重新排序，导致刚写入的用户顺序立刻被还原。继续用截图对应原工程 `D:\MMD\模型\Alicia\鳴潮-達尼婭\達尼婭\05.blend` 实际复现后确认，目标 `Bone_Piao160_M` 及相邻新增骨骼的 `bone_id` 均为 `-1`；因此移动前的一次 realignment 仍必须保留，用于为尚无 ID 的骨骼初始化有效顺序，否则官方 `shift_bone_id()` 会直接拒绝。最终链路固定为“移动前初始化一次 → 严格应用用户目标顺序 → 移动后绝不再 hierarchy realignment”。置顶、上移、下移、置底以及插到活动项前后只处理用户明确勾选的骨骼；只有目标序列本来没有变化时才提示边界。同步更新面板说明与 `README.md`，不再宣称或显示父子依赖保护。
- 新增 `tests/mmd_ordering_user_control_regression.py`，使用初始 `bone_id=-1` 覆盖“子骨置顶越过父骨”和“父骨置底越过子骨”，断言初始化只发生一次、每次只影响一个明确勾选项、用户顺序写入后不会再被 realignment 回滚。最终另以 Blender 4.4.3 直接打开原 `05.blend`（不保存），刷新真实查看器、勾选 `Bone_Piao160_M` 并调用与面板按钮相同的 `surface_proxy.reorder_checked_mmd_items(action='UP')`：操作前 `(index=533, bone_id=-1)`，操作后 `(index=532, bone_id=532)`，输出 `ACTUAL_05_BLEND_OPERATOR_UP_OK`。改动严格限定于 MMD 查看器排序，不触及现有 MMD IK、Physics runtime、DLL、Rigid/Joint 排序或其它工作树改动。版本保持 V0.1.8，源码 Junction 继续直接生效，不打包 ZIP、不 push。

## 2026-08-24 - V0.1.8 MMD IK / Physics 显式所有权交接重构候选

- 用户确认 `baseline-20260824-parent-empty-same-tick` 对应的 Parent Empty 同 tick 修复可以晋升为基线；本轮从该 tag 后继续，专门处理“物理运行中关闭 MMD IK 兼容”导致跟踪刚体/物理骨恢复启动姿态，以及随后清空用户变换再次错位的问题。
- 根因不是 DLL 解算，而是关闭按钮把整个 physics preview 以 `restore=True` 停止后重新创建：旧 Session 的启动快照会先覆盖当前物理输出，新的 world 又丢失原 solver 连续状态。与此同时，IK `Session.close()` 把全 Armature 的 `input_basis` 写回，超出了 IK 实际拥有的 35-bone output closure；`output_basis` 还同时承担“IK-owned output”和“全姿态外部编辑检测”两种互相冲突的职责。
- 重构为显式三层姿态所有权：`input_basis` 仅表示 authored/native 输入，`output_basis` 只保存 `output_indices` 对应的 IK-owned closure，新增 `presented_basis` 独立保存上一份完整展示姿态用于检测外部编辑与 Clear。IK 停止、Undo/Redo suspend、frame restore 现在只恢复 IK 真正写过的 output bones，不再覆盖 physics-owned 或普通 mmd_tools bones。
- 新增 `RuntimeAdapterHandoff`：关闭兼容时只暂停当前 physics commit，保留同一个 `PreviewSession`、`PreviewWorld`、solver、generation、190 根 physics driver 输出和全部 Rigid 显示矩阵；恢复 mmd_tools constraints 后原地把 adapter 从 `MmdIkPhysicsAdapter` 切换为 `None`，重建 pose input cache 并只做一次 view-layer update。物理 world 不停止、不 Reset、不重建，也不丢速度/连续状态。
- 新增 `tests/mmd_ik_disable_physics_handoff_regression.py`，在原 `04.blend` 对 PMX/MMD 两条 physics path 验证关闭前后 Session/World/Solver/generation 对象身份保持、190 根 driver 与全部 Rigid 零位移误差、adapter 正确脱离；随后依次执行 Clear All、再次移动足 IK、Clear Selected，足 IK 与脚链回归误差均为 `0`，physics tick 无失败。两条路径均输出 `MMD_IK_DISABLE_PHYSICS_HANDOFF_REGRESSION_OK`。
- 回归继续通过：`MMD_IK_SCOPED_OWNERSHIP_REGRESSION_OK owned=35 outputs=35 constraints=49 high_heel_error=8.94e-08`、`MMD_IK_PHYSICS_CLEAR_REPEAT_REGRESSION_OK repeat_error=1.53e-07`、`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK exact_calls=12`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_IK_RUNTIME_SMOKE_OK`。无 IK 的 PMX/MMD Parent Empty、preview pipeline 与 rigid latency 六组回归继续通过；未修改三个 DLL、fixed frequency/substeps 或版本号，不打包、不 push，真实 Blender 4.4 继续通过源码 Junction 使用，等待 GUI 验收后再决定是否晋升新基线。

## 2026-08-24 - V0.1.8 Parent Empty 同 tick 物理输入修正候选

- 用户在真实 Blender 4.4 中确认 Parent Empty 连续拖动延迟已修复，批准该状态晋升为本地安全基线 `baseline-20260824-parent-empty-same-tick`；该基线只固化统一 PMX/MMD raw Object transform 检测，不包含后续 IK 关闭生命周期重构。
- 用户在真实 Blender 4.4 发现：PMX DLL 下直接移动 MMD 模型 Root Empty 时物理与刚体能同步，而 MMD DLL 下 Object Mode 移动会出现刚体延迟，进入 Armature Pose Mode 移动则正常。核查确认两条 DLL 的正常 Blender hot path 已共用 `_prepare_mmd_tools_step()` / `_submit_pose_targets()` / `_apply_mmd_tools_step()`，但 `PoseInputAdapter.raw_input_changes()` 只监视 evaluated `root.matrix_world` / `armature.matrix_world`；Object Mode Transform modal 存在原始 `matrix_basis` 已变化、depsgraph 尚未传播新 `matrix_world`、timer 已先运行的窗口，旧逻辑会错误复用上一 tick 输入。Pose Mode 更容易先触发 Armature evaluation，因此会掩盖该窗口。
- 修复保持 PMX/MMD 共用，不增加 MMD-only common-motion/world-delta 分支：Session 现在缓存并监视 MMD Root、Armature 及其完整父级 Object 链的原始 `matrix_basis`。发现任一父级 raw transform 改变时，即使 `matrix_world` 尚未刷新，也会让当前 tick 进入一次必要的 `_update_view_layer()`，随后提交已求值的同 tick world-space 刚体目标。这样既覆盖 Root 自身 Empty，也覆盖额外父级 Empty，并避免重新引入历史上已经导致双重位移的手工 motion-delta 补偿。
- 新增 `tests/mmd_04_parent_empty_latency_regression.py`，在原 `04.blend` 中故意修改 Root Empty 后不预先调用 `view_layer.update()`，分别验证 PMX/MMD 都能由当前 tick 检出 raw Object transform、完成一次输入求值并同步 59 个绑定 0 型刚体；两条路径均输出 `MMD_04_PARENT_EMPTY_LATENCY_OK ... max_error≈1.9e-08`。既有 `MMD_04_PREVIEW_PIPELINE_OK ... motion_rigid_error=0`、`MMD_04_RIGID_LATENCY_REGRESSION_OK ... max_error=0`、PMX/MMD `PHYSICS_ROOT_OFFSET_REGRESSION_OK` 继续通过。
- 性能回归保持：`CURRENT_PROXY + debug on` 的 PMX/MMD tick 中位分别约 `7.50/7.91 ms`，合计约 `20.85/20.97 ms`，新增父级链 raw 比较未形成可测的稳定开销。当前改动位于已验收基线 `baseline-20260824-physics-runtime-v2-phase1` 之后，版本保持 V0.1.8，不打包、不修改 DLL、不新建 baseline，等待真实 GUI 对 Parent Empty 连续拖动重新验收。

## 2026-08-24 - V0.1.8 Physics Runtime V2 第一阶段性能与路径隔离重构

- 用户在真实 Blender 4.4 原工程中按顺序完成 GUI 验收：PMX 无 IK、MMD 无 IK、仅 MMD IK、MMD IK + PMX、MMD IK + MMD 五项均通过；逐 tick Rigid/Joint 修正后未再观察到刚体显示延迟。最后一项 Clear All → F9 `仅选中` → 再移动 → 再清空仍未通过：偶发关闭 IK，或 IK 控制骨已复位但链条残留旧解算结果。该问题作为明确的未解决缺陷保留，不将其误记为已修复；用户批准当前状态晋升为新的本地安全基线 `baseline-20260824-physics-runtime-v2-phase1`。
- 用户决定停止继续堆叠清空变换局部补丁，要求优先重构 physics host、保持物理同步并把普通 `mmd_tools` 骨架路径与 MMD IK 兼容路径彻底分开。新增 `PHYSICS_RUNTIME_V2_ARCHITECTURE.md`，固定“simulation tick 不可跳、presentation frame 可 latest-wins”、无 30 FPS 代码上限、无超预算 1 ms 饥饿追赶、debug 与 Bone output 解耦以及三个 DLL 分阶段处理的边界。
- 复现确认原 `04.blend`、`CURRENT_PROXY`、60 Hz、10 substeps、未启用 MMD IK 时，PMX 路径约 `43.20 ms`、MMD 路径约 `32.50 ms`；native solver 约 `0.96-0.97 ms`，DLL output copy 约 `0.04 ms`。PMX 被硬性排除在 input cache 外，MMD presentation 又按 `preview_frequency / 30` 限频；`PreviewDeadlineScheduler` 超预算后仅让出 `1 ms`，共同造成“开启任一物理 DLL 即进入低帧模式”。
- `PoseInputAdapter` 现在对 PMX/MMD 的无 IK 单 Session 使用同一热路径，`CURRENT_PROXY` 与 `MODEL` 均可缓存。raw input backstop 从全 Armature 扫描收窄为物理输入骨、父级和同骨架 constraint target closure；用户已经完成的 depsgraph evaluation 可直接转换为 canonical physics input，正常拖动不再重复执行 prepare update。直接脚本未求值输入、不安全 constraint、多 Session 仍回退保守路径。
- 删除固定 30 FPS presentation cadence。基础 `mmd_tools` 路径仍逐 physics tick 提交全部 Bone output，但交互 timer 不再同步阻塞 `view_layer.update()`，只请求 VIEW_3D redraw，让 Blender 把已写入 physics output 与下一次自然 evaluation 合并；因此不跳 solver tick，也不靠降低 fixed frequency/substeps 换性能。首轮真实 GUI 验收发现把 Rigid/Joint debug 对象降到约 15 Hz 会直接造成“显示刚体运动”中的可见刚体更新延迟，验收不合格；现已改为启用显示时逐 solver tick 写入 Rigid/Joint，关闭时仍完全省去对象回写，并补入连续 Root 编辑下每一 tick 的刚体矩阵同步断言。对象写入仍不触发周期性强制 evaluation。
- timer 改为 cooperative deadline：callback 低于 `16.667 ms` 时返回扣除自身耗时后的 delay，继续维持目标 60 Hz；callback 超预算时返回完整 interval，禁止再次退化为 `work + 1 ms` 连续占满 Blender 主线程。`tests/time_driver_unit.py` 已锁定低于预算与超预算两种行为，timeline/wall-time 到 Bullet 固定子步的既有语义保持不变。
- 新增 `physics_preview/integration.py` 和显式 `MmdIkPhysicsAdapter`。普通 physics Session 在启动时只解析一次 adapter；没有 native IK Session 时 `runtime_adapter is None`，每 tick 不再经过 evaluator lookup、feedback 或 monkey-patch wrapper。MMD IK 兼容 Session 使用独立 adapter 保留 evaluate/feedback/reset/close 生命周期；删除此前对 `_model_armature`、`PreviewSession.prepare_step/apply_step/close`、`PreviewWorld.reset` 与 `stop_preview` 的运行期替换。runtime switch 与 Undo/Redo 会显式刷新 adapter。
- 新增 `tests/physics_runtime_v2_performance_regression.py`，在原 `04.blend` 对 PMX/MMD、CURRENT_PROXY/MODEL、debug on/off 记录 input cache、20/20 Bone commits、0/20 synchronous evaluations、逐 tick debug updates、median/p95 与分阶段耗时。Rigid/Joint authored scale 改为 Session 重绑时缓存，避免逐 tick 反复从数百个 Object 矩阵分解 scale。修正刚体显示同步后，CURRENT_PROXY + debug on：PMX tick 中位 `7.51 ms`、p95 `8.46 ms`、含连续 Root 输入合计 `20.77 ms`；MMD tick 中位 `7.87 ms`、p95 `8.11 ms`、合计 `20.80 ms`，其中 apply 约 `4.40–4.47 ms`。debug off 与 MODEL 数据仍沿用此前测试结果。相对本轮 PMX `43.20 ms` 与 MMD `32.50 ms` 起点仍有显著降低，因此三个 DLL 和 physics ABI 本轮均不修改，待真实 GUI 重新验收后再决定 Phase 2。
- 正确性回归通过：`MMD_04_PREVIEW_PIPELINE_OK ... commits=20/20 sync_evaluations=0/20 debug_updates=20/20 motion_rigid_error=0`，其中连续 Root 编辑期间每一 tick 的全部可见刚体均与 solver transform 同步；`MMD_04_RIGID_LATENCY_REGRESSION_OK max_error=0`、PMX/MMD × IK 关/开四组合 `MMD_07_ROOT_MOTION_REGRESSION_OK`、PMX/MMD `PHYSICS_ROOT_OFFSET_REGRESSION_OK`、`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`（并断言普通 Session 无 adapter、IK Session 使用显式 adapter）、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK`、`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_IK_PHYSICS_CLEAR_REPEAT_REGRESSION_OK`、`MMD_IK_SCOPED_OWNERSHIP_REGRESSION_OK`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_IK_RUNTIME_SMOKE_OK` 与完整 `MMD_SKIRT_PROXY_CREATOR_SMOKE_OK`。`python -m py_compile`、UTF-8/no-BOM 与 `git diff --check` 通过。版本保持 V0.1.8，不打包 ZIP、不修改三个 DLL、不 push；真实 Blender 4.4 继续通过现有 Junction 使用源码，等待用户最终 GUI 验收。

## 2026-08-24 - V0.1.8 MMD IK 清空重做隔离与物理甩飞回归修复

- 用户在原 `04.blend` 真实 Blender 4.4 视口确认：上一轮为连续切换“清空用户变换”的 `仅选中` 而加入的全局 pose 历史恢复污染了正常 `MMD IK + MMD DLL` 实时输入；开启兼容与物理后移动足 IK 会把裙子物理骨整片甩飞。已完整撤回该宽泛 pose 历史方案，不再从普通 depsgraph 更新记录或恢复历史输出，也不改动稳定运行中的 IK→物理 feedback 路径。
- 修复收窄到清空识别与 Undo/Redo 恢复边界：只有 canonical Armature 全部 `matrix_basis` 已归一且至少两个 solver 输出发生变化时，才把当前状态认作“清空全部”；F9 把同一操作从“全部”重做到“仅选中”时，仅在已保存输入全为 identity、当前确有选中映射骨且选中骨仍为 identity 的精确条件下保留清空输入。其它 Undo/Redo 仍按当前 Blender pose 重建输入，正常交互路径不受影响。
- 针对用户随后反馈的拖动不顺畅，对原 `04.blend` 的 `CURRENT_PROXY + MMD DLL + MMD IK` 连续足 IK 输入重新逐阶段计时：修改前单 tick 平均 `72.036 ms`、中位 `70.938 ms`，主要耗时仍是 Blender Pose/depsgraph，而不是 native/Bullet。将 physics-pose 阶段的 IK 输出改为只写入、不立即刷新，由紧接着的物理输入准备统一执行同一次 depsgraph evaluation；没有降低 `60 Hz`、没有减少 `10` substeps，也没有跳过骨骼输出。修改后同条件单 tick 平均 `57.752 ms`、中位 `57.383 ms`，host tick 约减少 `19.8%`。这是 background 性能证据，真实 GUI 操作手感仍需用户重新验收。
- 按用户确认的范围把 live MMD IK 兼容从“全骨架最终输出”收窄为“实际 IK 输出闭包”：启用时动态遍历当前 Armature 中指向自身的 `IK` constraints，按各自 `chain_count` 收集 link bones，并纳入相应 `mmd_ik_target_*` target bones 与连续的 mmd_tools generated parent dependencies，不写死足部、手部或特殊控制器名称；native solver 仍读取完整当前姿态以保留父级、追加变换和特殊链依赖，但只把解算结果写回该闭包，也只静音闭包骨上的 mmd_tools generated constraints。原 `04.blend` 实际从 503 根可映射骨收窄为 35 根输出骨、49 个受管约束，其余 generated constraints 保持各自原状态；动态集合同时覆盖左右足链、高跟鞋链以及 `AnalToy`、`PussyToy`、`UrethraToy`、振动/自动振动等 PMX 特殊 IK，不依赖模型专名硬编码。
- 用户在真实视口发现第一版 15-link scoped output 的高跟鞋 IK 链会漂移。复现确认：连续移动足 IK 时，native 已先改写足/足首 link，而高跟鞋 link 的 generated parent（`足D/ひざD/足首D` 一类）及 target 仍由下一次 Blender depsgraph 求值，导致子骨 basis 用旧 parent matrix 反解；左高跟鞋 link/target 相对同 tick native solver 的矩阵误差会由约 `0.0107` 增至 `0.0145`。修复后 `_apply_output()` 为 scoped outputs 预取 native ancestor matrices，并把 IK target 与连续 generated parents 纳入同一写回闭包；连续 10 次足 IK 位移中高跟鞋 link/target 最大矩阵误差降至 `5.47617674e-07`，不再随移动累积。
- 最终 35-bone 输出闭包下，同一 `04.blend`、同一 `CURRENT_PROXY + MMD DLL + MMD IK` 连续足 IK 20 tick 平均为 `51.070 ms`、中位 `50.796 ms`：相对本轮最初 `72.036 ms` 平均值降低约 `29.1%`，相对只合并重复 depsgraph refresh 的 `57.752 ms` 再降低约 `11.6%`。瓶颈仍以 Blender depsgraph evaluation 为主，因此该 background 数字不等于真实 GUI 已达到 60 FPS；需用户 Reload Scripts/重启 Blender 后验收实际拖动手感。
- 新增 `tests/mmd_ik_physics_clear_repeat_regression.py`，直接使用原 `04.blend` 的 `CURRENT_PROXY + MMD DLL + MMD IK`：移动足 IK `0.05 m` 后最大刚体位移为 `0.0557413652 m`，未发生整片甩飞；模拟 F9 从“清空全部”重做到“仅选中”并刷新 depsgraph 后，脚链相对清空结果最大误差为 `3.05566071e-07 m`，IK 输入保持 identity，物理 tick 无失败。输出 `MMD_IK_PHYSICS_CLEAR_REPEAT_REGRESSION_OK`。
- 新增 `tests/mmd_ik_scoped_ownership_regression.py`，在原 `04.blend` 断言动态 owned/output 集合、owned 与 non-owned constraint mute 边界、普通非 IK 骨不被写回、足 IK 与 `AnalToy` 特殊 IK 的 native output、高跟鞋链连续移动误差，以及关闭兼容后所有约束逐项恢复；输出 `MMD_IK_SCOPED_OWNERSHIP_REGRESSION_OK owned=35 outputs=35 constraints=49 links=ひざ.L,AnalToy速 high_heel_error=5.47617674e-07`。完整 `mmd_ik_runtime_smoke.py` 也按 scoped output contract 更新并通过：`MMD_IK_RUNTIME_SMOKE_OK solver=MMD meshes=4 modifiers=4 bone_morphs=23`。既有回归继续通过：`MMD_IK_CLEAR_USER_TRANSFORMS_REGRESSION_OK`、`MMD_IK_PHYSICS_FEEDBACK_REGRESSION_OK exact_calls=12 exact_min=202`、`MMD_IK_PHYSICS_RESET_REGRESSION_OK`、`MMD_IK_TRANSFORM_MODAL_REGRESSION_OK`、`MMD_04_RIGID_LATENCY_REGRESSION_OK ... max_error=0`；重复清空回归在最终范围实现下为 `rigid_motion=0.0557240016`、`repeat_error=1.52785164e-07`。`python -m py_compile` 与 `git diff --check` 通过。未修改两个 native DLL、物理 fixed frequency/substeps 或其它插件功能。版本保持 V0.1.8，不打包 ZIP、不 push；真实 Blender 4.4 继续通过现有源码 Junction 使用当前修复。

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

## 2026-08-22 - 活动顶点组原地拆分为左右镜像组

- 在 Mesh 数据属性的顶点组向下箭头菜单中，将“将所选顶点组转为镜像顶点组”精确插入 Blender 原生两项“镜像顶点组”命令之后；保留同一菜单其它插件的既有扩展顺序。
- 新增 `surface_proxy.convert_active_group_to_mirrored`：当前无左右后缀的活动组原地改名为 `.L`，新建 `.R` 并移动到其下一行；不会把结果留在列表底部，也不会保留无后缀源组。经实际模型方向校正，局部 `X > 0` 权重写入 `.L`，局部 `X < 0` 写入 `.R`，中心容差内的权重各分一半；源组锁定状态同步给两组。
- 若活动组已有 `.L/.R/_L/_R`，或目标 `.L/.R` 任一已存在，则取消并提示，不覆盖现有组。操作支持从 Edit Mode 调用并恢复原模式，不修改其它顶点组、活动对象或 Mesh 选择。
- 新增 `tests/mirror_vertex_group_conversion_smoke.py`，覆盖菜单顺序、正负 X 分流、中心与近中心权重对半、原位列表顺序、无残留源组、锁定状态、其它组权重不变、Edit Mode 恢复及名称冲突拒绝。Blender 4.4.3 输出 `MIRROR_VERTEX_GROUP_CONVERSION_OK`。
- 本轮未修改代理生成、MMD 物理、MMD IK 或 native DLL。版本保持 V0.1.8，未混合打包当前包含其它未提交工作的工作树；真实 Blender 4.4 继续通过现有源码 Junction 使用本轮代码。

## 2026-08-22 - 骨链代理禁止覆盖与主体名称修正

- 修复“从勾选骨骼恢复或新建代理”按派生名称查找同名对象并用新 Mesh 数据替换旧对象的问题；删除该替换路径，插件不再改写或删除既有代理 Mesh。
- 代理身份现在按 `Armature + 完整骨骼集合` 判定：同一段骨链已经存在代理时取消操作并提示“请先删除旧代理后再创建”；不同骨链即使派生出同一主体名称，也创建独立对象并由 Blender 使用 `.001`、`.002` 后缀，不触碰先前对象。
- 创建成功后不再自动写入“代理范围”、不再清空 MMD 查看器列表，也不再取消当前 3D 选择或把新代理设为活动对象；列表内容、勾选状态、活动行、原活动对象和选择集全部保持原样，新代理仅在 Outliner/场景中创建。
- 修正普通父子骨链的主体名称提取：只移除骨名末尾数字和 `.L/.R/_L/_R`，数字前的中文、英文和下划线全部保留为主体；例如 `Bone_Piao031.L → Bone_Piao_Surface`、`后发A1.L → 后发A_Surface`、`后发B1.R → 后发B_Surface`。一次勾选包含多个不同主体时拒绝合并并提示分别创建，不再擅自缩成共同前缀。
- 新增 `tests/proxy_creation_no_overwrite_smoke.py`，覆盖 `Bone_Piao031.L` 首链命名、`后发A/后发B` 主体提取与混选拒绝、同链二次创建阻断且旧对象/旧 Mesh/坐标不变、同主体的另一段骨链生成 `Bone_Piao_Surface.001`。Blender 4.4.3 输出 `PROXY_CREATION_NO_OVERWRITE_OK`；同步修正主 smoke 中旧的“原位覆盖恢复”预期。
- 本轮未修改 MMD 物理、MMD IK、native DLL 或既有代理物理对象。版本保持 V0.1.8，未混合打包当前包含其它未提交工作的工作树；真实 Blender 4.4 继续通过现有源码 Junction 使用本轮代码。

## 2026-08-22 - 锁定顶点组权重合并到新组

- 在 Mesh 数据属性的顶点组向下箭头菜单中，将“用锁定组的权重创建新组”固定插入 Blender 原生“反转全部锁定状态”正下方；即使其它插件也扩展同一菜单，本项仍保持在原生菜单末项之后。
- 新增 `surface_proxy.create_group_from_locked_weights`：读取当前活动 Mesh 中所有 `lock_weight=True` 的顶点组，逐顶点相加权重并创建 `锁定组权重`（重名时由 Blender 自动生成编号后缀）。源顶点组、锁定状态及原权重均不删除、不改写；结果超过 Blender 单组权重上限时按 Blender 原生行为保存为 `1.0`，并恢复调用前的 Object/Edit 等模式。
- 新增 `mmd_skirt_proxy_creator/vertex_group_tools.py` 与隔离回归 `tests/locked_vertex_group_weight_merge_smoke.py`。Blender 4.4.3 验证菜单插入顺序、Edit Mode 调用后模式恢复、锁定组求和、未锁定组排除、源权重不变、重名新组和权重上限，输出 `LOCKED_VERTEX_GROUP_WEIGHT_MERGE_OK`；真实 Blender 4.4 用户环境确认 Junction 指向当前源码、插件已启用且菜单回调索引为 `1`。
- 本轮未修改代理生成、MMD 物理、MMD IK 或 native DLL。工作树开始时已有其它未提交的物理与 smoke 修改，因此不把混合工作树打成新发布 ZIP、不递增 V0.1.8；真实 Blender 4.4 已通过现有源码 Junction 直接装载本功能，重启 Blender 或 Reload Scripts 后生效。

## 2026-08-22 - 锁定顶点组快速勾选骨骼

- 在 MMD 查看器的骨骼“快速选组”菜单新增“当前物体锁定顶点组”：读取当前活动 Mesh 的 `VertexGroup.lock_weight`，只勾选当前骨骼列表中与锁定顶点组同名的骨骼；没有对应骨骼的普通顶点组直接跳过，未锁定的同名骨骼组不会误选。现有勾选状态保留，不修改顶点组、骨骼选择或权重数据。
- 修改 `mmd_skirt_proxy_creator/mmd_physics.py`，并在 `tests/headless_smoke.py` 补入主 smoke 回归；另新增隔离的 `tests/locked_vertex_group_quick_select_smoke.py`，覆盖“锁定骨骼组命中、锁定普通组跳过、未锁定骨骼组不命中”，Blender 4.4.3 输出 `LOCKED_VERTEX_GROUP_QUICK_SELECT_OK`。
- `python -m py_compile` 与 `git diff --check` 通过。完整 `headless_smoke.py` 在运行到本功能前命中当前 `HEAD` 已有的 physics preview 恢复断言（`tests/headless_smoke.py:699`），未把该无关失败记作本功能通过；本轮未修改物理预览、MMD IK、PMX/MMD DLL 或代理生成链路。
- 版本保持 V0.1.8，未打包 ZIP；真实 Blender 4.4 继续通过源码 Junction 指向当前仓库插件目录，Reload Scripts 或重启 Blender 后即可使用。

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
