# Release Notes

## Unreleased

- Capture bone Morph poses in hierarchy order, including local scale. Preserve scale through optional `<model>.Morph.json` sidecars with automatic and manual import while keeping PMX data and model comments standard.

- Exclude detached meshes from material lists, prioritize exact MMD names during Blender material naming, and recover stale material Morph references through unique in-model Blender/MMD names.

- Isolate bone-to-vertex morph conversion from active poses, other bone/vertex/group morphs and animation drivers; include bone scale and avoid context-dependent morph slider operators.
