# Release Notes

## Unreleased

- Capture bone Morph poses in hierarchy order, including local scale. Preserve scale through optional `<model>.Morph.json` sidecars with automatic and manual import while keeping PMX data and model comments standard.

- Exclude detached meshes from material lists, prioritize exact MMD names during Blender material naming, and recover stale material Morph references through unique in-model Blender/MMD names.

- Isolate bone-to-vertex morph conversion from active poses, other bone/vertex/group morphs and animation drivers; include bone scale and avoid context-dependent morph slider operators.

- Support Blender 5.x layered Actions, owner-scoped animation slots, bone selection/visibility and UV selection across Morph, IK, VMD and physics workflows while preserving Blender 4.4/4.5 support. Preserve slot identity during Action copies and restoration, and skip unusable legacy MMD Tools probes while retaining the valid official extension dependency.

- Preserve native IK clear/undo state for current-model sessions while rebuilding changed native definitions, and prevent automatic physics resets from restoring solved poses as user input.
