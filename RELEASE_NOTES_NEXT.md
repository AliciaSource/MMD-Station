# MMD Station Release Notes

## Unreleased

### Fixed

- Load native physics libraries only on demand. Suspend live scene updates during native background bakes, defer Morph setup outside frame callbacks, and keep updater and parallel-solver workers away from Blender RNA. Preserve independent bone-animation and Cloth/Soft Body cache baking workflows.
