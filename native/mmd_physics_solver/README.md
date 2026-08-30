# MMD Physics Solver DLL

这是独立的 Rust `cdylib` 求解器边界。Blender 模块只通过版本化 C ABI 传入刚体、Joint、运动学目标与固定步长，不创建 Blender `RigidBodyWorld`，也不调用 `mmd_tools` 的物理预览流程。

求解内核使用项目内 vendored 的 `mmd-anim-physics-bullet 0.4.1` 和 Bullet Physics `2.75`（SVN r1754）。项目只维护 MMD 预览所需的轻量桥接，不引入另一套 Blender 物理框架：

- Sphere / Box / Z-axis Capsule 刚体；
- 碰撞组与 mask；
- `btGeneric6DofSpringConstraint`；
- 固定 timestep 与子步；
- `mmd_tools` 默认 `0.08` 导入尺度到 MMD/Bullet 尺度的内部换算；
- additional damping、20 次 warm-start iteration 与运动学 interpolation/AABB 同步；
- C ABI v5 在 Rust 内持有 bind offset、0/1/2 类型语义、Joint 两侧局部 frame、刚体动态状态快照与修复引导；
- 0 型在 step 前跟随骨骼，1 型输出完整物理骨骼变换，2 型输出物理旋转与层级传播前的动画骨骼位置，不把动态刚体反向瞬移到动画姿态。最终 2 型父子链位置由 host adapter 按父到子顺序传播动画局部偏移，以复刻 MMD 更新父骨后立即更新子变换的行为。

构建：

```powershell
.\build.ps1
```

输出会复制到：

`mmd_station\physics_preview\bin\win_amd64\mmd_physics_solver_abi5.dll`

未来拆成独立插件时，只需移动 `physics_preview/`、本 crate 与 DLL，不依赖裙面代理生成逻辑。
