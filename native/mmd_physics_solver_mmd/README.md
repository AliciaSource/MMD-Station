# MMD 9.32 x64 Physics Solver DLL

这是独立的 MMD 本体对齐分支。它输出 `mmd_physics_solver_mmd.dll`，不会覆盖
`native/mmd_physics_solver/` 或既有的 PMX Editor 对齐 DLL。

已确认并独立实现的 MMD 9.32 x64 路径：

- Bullet Physics 2.75（SVN r1754）；
- `btDefaultCollisionConfiguration`；
- `btDiscreteDynamicsWorld`；
- `btDbvtBroadphase` 与 `btSequentialImpulseConstraintSolver`；
- MMD Joint 线性弹簧 Z 分量映射到 Bullet Z，不采用 PmxNLib 的 Z/Y 特殊映射；
- C++ Bullet bridge 使用 Visual C++ 2008 SP1（VC9）`/fp:fast` 编译，并静态链接
  VC9 CRT 数学实现，避免运行时依赖 `MSVCR90.dll`；
- C ABI 版本为 4，与 Blender host adapter 保持一致。

构建：

```powershell
.\build.ps1
```

`build.ps1` 要求可用的 VC9 SP1 x64 toolchain。默认探测
`%TEMP%\vcpy27-portable`，也可通过 `MMD_V90_ROOT` 指定根目录。Rust 部分仍由
当前稳定版 Cargo 构建。

输出复制到：

`mmd_skirt_proxy_creator\physics_preview\bin\win_amd64\mmd_physics_solver_mmd.dll`

PMX Editor 版本继续由 `native/mmd_physics_solver/` 构建，并输出
`mmd_physics_solver.dll`。
