# MMD Station Release Notes

## Unreleased

### Fixed

- Preserved each ShapeKey's existing slider range during Morph runtime setup,
  expanding only affected keys to the exact out-of-range value entered in the
  Morph editor.
- Fixed the Morph AI settings dialog by consolidating its fields into the
  add-on's single updater-backed Preferences host.
- Fixed physics-bake initialization so scene evaluation, solver startup, and
  restored checkpoints use the same source-frame state.
- Made repair bakes replay their original simulation chain instead of resuming
  from an incomplete Bullet snapshot, and apply smooth Action-space repair
  deltas without destabilizing connected rigid-body chains.
- Added a safe-pose recovery control that restores selected physics bones from
  the last clean pose at the start of the repair range before manual adjustment.
- Fully isolated MMD IK compatibility from physics preview ownership, so IK can
  be toggled without rebuilding or feeding back into the active physics world.
- Added a temporary mesh-only presentation proxy for compatible material-split
  and mixed multi-material models, preserving the original rig, constraints,
  drivers, physics behavior, and near-merged dependency-graph performance. The
  proxy also rebuilds mmd_tools edge-preview materials, weights, and Solidify
  settings against the final merged material layout, while temporarily removing
  replaced source meshes from the active scene and dependency graph.
- Interpolated bone-tracking rigid-body targets across Bullet substeps in both
  physics backends, preventing MMD-chain explosions during skipped playback
  frames and reducing PMX collision tunneling during fast animated motion.
