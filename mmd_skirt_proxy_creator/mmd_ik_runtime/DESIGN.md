# MMD IK Runtime

## Accepted boundary

The production add-on must evaluate PMX/VMD bones independently. It must not
launch, inject, automate, call, or require MikuMikuDance or MMDBridge.

The retained Python layer currently owns only:

- canonical/runtime armature separation;
- model and armature selectors;
- synchronized Armature Modifier switching for all model meshes;
- switching locks while physics preview is running;
- transactional canonical binding during `mmd_tools` PMX export;
- source IK and Bone Morph payload preservation during export.

The native C++ evaluator directly consumes original PMX/VMD bytes and implements
VMD interpolation, Bone Morph, Append Transform, PMX transform-level ordering,
IK enable tracks, CCD IK, fixed axes, IK link limits, and after-physics feedback.
MMD is used only by development tests as an external oracle; it is never part
of the installed runtime path.

An Action imported by `mmd_tools` is used only to recover the original VMD path,
start frame, and SHA-256. Exact evaluation never consumes Blender-converted
quaternion curves. A changed source file is rejected until the VMD is imported
again or a different raw VMD is explicitly selected.

## Physics order

The order is native bone evaluation, runtime armature input, selected PMX or MMD
physics solver, dynamic-bone writeback, and mesh deformation. The bone evaluator
is not disabled for the PMX backend. With no Blender overrides, the MMD backend
uses exact raw float32 targets; user constraints or drivers intentionally route
the evaluated Blender pose into either backend. The canonical `mmd_tools`
armature remains untouched.
