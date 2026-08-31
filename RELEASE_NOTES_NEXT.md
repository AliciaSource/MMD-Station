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
- Fixed one-step Root-motion latency in MMD DLL previews with MMD IK enabled and
  coalesced intermediate pose evaluation before presenting the final physics pose.
