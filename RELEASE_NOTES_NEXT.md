# MMD Station Release Notes

## Unreleased

### Fixed

- Fixed physics-bake initialization so scene evaluation, solver startup, and
  restored checkpoints use the same source-frame state.
- Made repair bakes replay their original simulation chain instead of resuming
  from an incomplete Bullet snapshot, and apply smooth Action-space repair
  deltas without destabilizing connected rigid-body chains.
- Added a safe-pose recovery control that restores selected physics bones from
  the last clean pose at the start of the repair range before manual adjustment.
- Fully isolated MMD IK compatibility from physics preview ownership, so IK can
  be toggled without rebuilding or feeding back into the active physics world.
- Added a temporary clean presentation rig for MODEL physics preview, reducing
  dependency-graph overhead from heavily split character meshes without changing
  the authored model.
