# Development Log

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
