# MMD Station v1.0.2

## Fixed

- Load native physics libraries on demand instead of preloading both backends when the add-on is enabled.
- Pause live scene writes during native background bakes and resume preview afterward without clearing Cloth or Soft Body caches. Keep bone-animation baking and mesh-cache baking as separate, sequential workflows.
- Defer structural Morph setup outside frame callbacks and protect scene-update timers during locked background jobs.
- Dispatch updater UI callbacks on the main thread, snapshot update preferences before worker use, and keep parallel physics workers away from Blender RNA.

## Compatibility

Validated in Blender 4.4.3 with MMD and PMX backends, Cloth and Soft Body caches, live preview enabled, sequential bone-to-mesh baking, and the mmd_tools native rigid-body bake entry point. This does not establish compatibility with every third-party bake implementation.

Install the attached `mmd_station-1.0.2.zip`. MMD Tools remains required. Save your work and restart Blender after updating.
