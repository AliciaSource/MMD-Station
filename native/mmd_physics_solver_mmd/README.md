# MMD 9.32 x64 Physics Solver DLL

这是独立的 MMD 本体对齐分支，输出 `mmd_physics_solver_mmd_abi5.dll`。它不覆盖
`native/mmd_physics_solver/` 或 PMX Editor 对齐 DLL。

## 已确认的 MMD 9.32 x64 native 路径

- Bullet 2.75 快照：upstream commit `3da9c832aef0eea74ecc8221d834e9a879f43a43`（2009-09-16）。
- 该 revision 由 MMD 的 `STATIC_PLANE_PROXYTYPE == 26` 直接确认；下一提交
  `f65e829ca08c0856d1923e7008e2663486949493` 新增两个 2D shape type，使其变为 28，
  因而此前使用的后期 Bullet 2.75 source tree 并不匹配 MMD。
- `btDefaultCollisionConfiguration`、`btDiscreteDynamicsWorld`、`btDbvtBroadphase`、
  `btSequentialImpulseConstraintSolver` 及其默认 `btContactSolverInfo` 与 MMD 一致。
- MMD Joint 线性弹簧 Z 分量映射到 Bullet Z，不采用 PmxNLib 的 Z/Y 特殊映射。
- native C++ 固定使用 Visual C++ 2010 SP1 `cl.exe 16.00.40219.01`、`/fp:fast /Ox`。
- C ABI 版本为 5，与 Blender host adapter 保持一致，并提供刚体动态状态快照与修复引导。

源码 revision 证据另见：

`vendor/mmd-anim-physics-bullet/vendor/bullet-2.75/MMD_SOURCE_REVISION.txt`

## Raw bit parity 验证口径

`tests/mmd_raw_core_parity.py` 直接挂接双方的
`btDiscreteDynamicsWorld::stepSimulation`。Rossi 完整物理在以下输入完全一致时，
首个 clean positive step 的 339 个模型刚体全部通过：

- body / shape / constraint payload；
- ground + 339 bodies 的完整 pre-step state；
- broadphase body remove/reinsert 顺序与 handle 分配；
- pair 拓扑、solver configuration、timestep 与调用顺序。

验证结果为 `339/339` rigid-body transforms、`4068/4068` float32 components 逐 bit
相同，最大误差为 `0`。这个结论只证明 raw Bullet core；不把 Blender 骨架适配器或
MMD 每次播放产生的宿主层差异算作 native core parity。

## 构建

```powershell
.\build.ps1
```

`build.ps1` 要求：

- Visual C++ 2010 SP1 compiler update，默认路径：
  `%TEMP%\vc10sp1-portable\Program Files(64)\Microsoft Visual Studio 10.0`；
- Visual Studio 2010 RTM headers，默认路径：
  `%ProgramFiles(x86)%\Microsoft Visual Studio 10.0`；
- Windows SDK 7.1，默认路径：
  `%TEMP%\spx-winsdk71-portable\Program Files\Microsoft SDKs\Windows\v7.1`；
- 当前稳定版 Rust / Cargo 与 Visual Studio build environment。

可分别通过 `MMD_VC10_SP1_ROOT`、`MMD_VC10_ROOT`、`MMD_WINSDK71_ROOT`、
`MMD_VSDEVCMD` 覆盖路径。输出复制到：

`mmd_station\physics_preview\bin\win_amd64\mmd_physics_solver_mmd_abi5.dll`

PMX Editor 版本继续由 `native/mmd_physics_solver/` 构建并输出
`mmd_physics_solver_abi5.dll`。
