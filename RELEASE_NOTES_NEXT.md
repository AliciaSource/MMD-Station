# MMD Station v1.0.3

## Unreleased

### Added

- Run on Blender 5.x: layered actions store keyframes in per-slot channelbags, so MMD Station now creates and links the matching animation slot instead of using the removed `Action.fcurves` API. Object, armature, NLA-strip and shape-key animation all keep playing back.

### Fixed

- Morph and shape-key animation on Blender 5.x, including VMD morph import and export, where new shape keys default to value `1.0` instead of `0.0`.
- Bone selection, IK runtime, physics preview baking and display-frame panels no longer raise attribute errors on Blender 5.x. Bone selection is read and written through one helper per Blender version, so Blender 4.4 and 4.5 keep using `Bone.select`.
- Enabling the add-on no longer fails when an outdated mmd_tools build sits on the add-on path. MMD Tools modules are now probed tolerantly, so a legacy copy that cannot even be imported on this Blender version is skipped instead of aborting registration with an `ActionFCurves` error.

### Compatibility

- Still requires MMD Tools. Validated in Blender 5.2.1 LTS with the packaged add-on enabled from a real user install directory, plus the offline headless smoke and regression suites. Blender 4.4 remains supported.
