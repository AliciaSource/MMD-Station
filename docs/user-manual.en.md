# MMD Station User Manual

[简体中文](user-manual.zh-CN.md) | **English**

MMD Station is a Blender 4.4 workspace for editing, validating, previewing,
and exporting MikuMikuDance models. It extends the official MMD Tools add-on;
MMD Tools must be installed and enabled.

## Quick navigation

- [1. Install and open MMD Station](#1-install-and-open-mmd-station)
- [2. Learn the interface](#2-learn-the-interface)
- [3. Import and export PMX, VMD, and VPD](#3-import-and-export-pmx-vmd-and-vpd)
- [4. Create and edit surface proxies](#4-create-and-edit-surface-proxies)
- [5. Generate proxy physics](#5-generate-proxy-physics)
- [6. Use the MMD Viewer](#6-use-the-mmd-viewer)
  - [Materials](#61-materials)
  - [Bones](#62-bones)
  - [Rigid bodies](#63-rigid-bodies)
  - [Joints](#64-joints)
  - [Diagnostics](#65-diagnostics)
- [7. Edit Morphs](#7-edit-morphs)
- [8. Edit display frames](#8-edit-display-frames)
- [9. Preview physics](#9-preview-physics)
- [10. Bake and repair physics animation](#10-bake-and-repair-physics-animation)
- [11. Enable MMD-compatible IK](#11-enable-mmd-compatible-ik)
- [12. Updates and interface language](#12-updates-and-interface-language)
- [13. Common workflows](#13-common-workflows)
- [14. Troubleshooting](#14-troubleshooting)

## 1. Install and open MMD Station

### Requirements

- Blender 4.4.
- Windows x64 for the bundled native physics and IK libraries.
- **MMD Tools is required.**
  - [Official Blender Extensions page](https://extensions.blender.org/add-ons/mmd-tools/)
  - [Official GitHub repository](https://github.com/MMD-Blender/blender_mmd_tools)

### Installation

1. In Blender, open **Edit > Preferences > Get Extensions**.
2. Search for **MMD Tools**, install it, and make sure it is enabled.
3. Install the `mmd_station-X.Y.Z.zip` file through
   **Edit > Preferences > Add-ons > Install from Disk**.
4. Enable **MMD Station**.
5. Open a 3D Viewport, press `N`, and select the **MMD Station** tab.

If MMD Tools is missing, PMX/VMD/VPD operations and MMD data access cannot
work. Install MMD Tools before troubleshooting MMD Station.

## 2. Learn the interface

The top of the panel contains:

- Model, motion, and pose import/export shortcuts.
- The current MMD Station version.
- A **GitHub** button.
- Six workspaces: **Proxy Creation**, **MMD Viewer**, **Morph Editor**,
  **Display Frames**, **Physics Preview**, and **MMD IK**.

### Active row versus checked rows

Many lists use two different concepts:

- The highlighted row is the **active item**. Its properties appear below the
  list.
- Checkboxes define a **batch selection**. Delete, reorder, copy, mirror, and
  other batch tools act on checked rows.

When a list contains only one valid target, some tools apply directly. When
there are multiple targets, check the rows explicitly before running a batch
operation.

### Selecting the MMD model

Most workspaces contain an **MMD Model** field. You can select the MMD Root
directly, or select an object inside a model and use Refresh. If a list looks
stale after an external MMD Tools operation, click its refresh button.

## 3. Import and export PMX, VMD, and VPD

The shortcuts at the top call the corresponding MMD Tools file browser.

### Model

- **Import** imports PMD or PMX through MMD Tools.
- **Export** exports PMX. Select an object belonging to the intended MMD model
  before exporting.

The first complete PMX export in a Blender session builds a Shadow Model.
Later compatible changes may use a faster overwrite path. Structural changes
that are not safe for the Shadow path automatically fall back to a complete
MMD Tools export. The previous export directory and filename are remembered
within the Blender session.

### Motion

- **Import** imports VMD through MMD Tools. Imported Morph animation is bridged
  to the central MMD Station Morph sliders.
- **Export** exports VMD. MMD Station temporarily supplies the animation form
  expected by MMD Tools and restores the Blender state afterward.

### Pose

- **Import** imports a VPD pose.
- **Export** exports the current pose as VPD and remembers the last destination
  in the current Blender session.

## 4. Create and edit surface proxies

Surface proxies are editable Mesh control surfaces used to create regular bone
chains, weights, rigid bodies, and Joints for skirts, hair, ribbons, sleeves,
and similar parts.

### 4.1 Prepare a selection

1. Select a model Mesh and enter **Edit Mode**.
2. Select the vertices that describe the intended surface.
3. Open **Proxy Creation > Basic > Proxy Creation**.
4. Choose the topology:
   - **Closed** for a loop such as a skirt.
   - **Open** for a sheet such as hair or a ribbon.
5. Set the number of columns and the maximum number of height levels.
6. Enter a unique name prefix.
7. Optionally choose a target Armature and parent bone.
8. Keep **Generate and normalize weights** enabled when the selected Mesh
   should be weighted to the generated bones.
9. Click **Create Skirt Surface Proxy from Selection**.

Closed proxies require at least three columns. A one-column proxy creates a
sculptable control strip but still generates one physical chain. Keep Dynamic
Topology disabled while sculpting that strip.

If the prefix begins with a recognized left/right marker, MMD Station creates
a two-sided mirror layout in one Mesh. The mirror can use exact geometry or
independent fitting, depending on the selection.

### 4.2 Proxy parameters

- **Radial Offset** moves the fitted proxy away from or toward the selected
  surface.
- **Target Armature** controls where generated bones are created.
- **Parent Bone** connects the top of the generated chains to an existing
  model bone.
- **Auto Sync after leaving Edit/Sculpt Mode** updates generated bones when
  proxy geometry changes.

### 4.3 Edit or recover a proxy

The **Proxy Editing** box provides:

- **Sync Bones to Proxy**: moves generated bone endpoints to current proxy
  vertices without renaming bones or changing weights.
- **Recalculate Weights from Proxy**: recalculates only vertices already
  influenced by the proxy chains and preserves locked deform weights.
- **Identify or Restore Selected Proxy**: restores proxy metadata after safe
  renaming or object relinking.

You can also recover a missing proxy from **MMD Viewer > Bones**:

1. Check one or more continuous proxy bone chains.
2. Choose Open or Closed. For an open proxy, choose whether the two sides
   should be connected.
3. Click **Restore or Create Proxy from Checked Bones**.

Normal names, `.L/.R`, and `_L/_R` chains are supported.

## 5. Generate proxy physics

The lower section of **Proxy Creation** generates MMD rigid bodies and Joints
from the current proxy.

### 5.1 Basic workflow

1. Select the **MMD Root** and the **Physics Proxy**.
2. Use the **Basic**, **Rigid Body**, **Vertical Joint**, and
   **Horizontal Joint** tabs to review parameters.
3. Optionally click **Fill: Stable Midi-Length Skirt** or choose a custom
   preset. A preset only fills the panel; it does not modify existing physics.
4. Click **Generate MMD Rigid Bodies and Joints** for a new setup.
5. After changing parameters, click **Apply Parameters to Current Proxy**.

### 5.2 Rigid body settings

- Choose Sphere, Box, or Capsule.
- Set the top and lower-chain rigid body types.
- A size value of `0` means automatic fitting from the proxy cell. A non-zero
  value overrides it as a bone-length ratio.
- Start/end interpolation can vary size, mass, damping, restitution, and
  friction along the chain.
- Set the collision group and disabled collision groups. **Block same group**
  is useful for adjacent skirt chains that should not collide with themselves.

### 5.3 Joint settings

Vertical Joints connect bodies down each chain. Horizontal Joints connect
neighboring columns. You can configure:

- Linear and angular lower/upper limits.
- Linear and angular springs.
- Interpolation from the top to the bottom of the proxy.
- Whether Horizontal Joints are generated at all.

The protection checkboxes decide which groups of existing values may be
overwritten by **Apply Parameters**.

### 5.4 Synchronize after editing

- **Synchronize Current Proxy Rigid Bodies and Joints** updates only position
  and rotation from the proxy bones.
- **Auto-sync after bone changes** performs the same positional maintenance
  automatically.
- Synchronization does not change body shape, type, size, physical parameters,
  or collision settings.

## 6. Use the MMD Viewer

The Viewer provides five tabs: Materials, Bones, Rigid Bodies, Joints, and
Diagnostics. Use Search, name-prefix filtering, and **Current Proxy Only** to
reduce large lists. The eyedropper copies a prefix from the active row.

Common list controls:

- **Select All**, **Select None**, **Invert**, and **Range Select**.
- Top, Up, Down, Bottom, Before, and After ordering tools change the actual PMX
  order where supported.
- **Select Checked Items in Blender** synchronizes the list selection to the
  3D Viewport.
- **Sync Selected from 3D View** performs the reverse operation.

### 6.1 Materials

The material table shows PMX order, Blender name, MMD name, and English name.

- Reorder checked materials to control exported PMX material order.
- Synchronize material names and calibrate material IDs/object number prefixes.
- Split the active multi-material Mesh using MMD Tools-compatible logic while
  preserving normals and cleaning near-zero ShapeKeys.
- Expand **MMD Textures** to add/remove main and sphere textures, choose sphere
  texture mode, and configure shared or custom Toon textures.
- Expand **MMD Material** to edit ID, names, comment, diffuse/alpha, specular,
  ambient, shadow flags, edge color, and edge size.
- The copy icon beside a field copies that field to all checked materials.

### 6.2 Bones

The bone list can synchronize selected Edit/Pose bones from the 3D Viewport.
The active bone inspector edits:

- Bone ID, MMD Japanese/English names, and deform status.
- Transform order and after-physics evaluation.
- Controllable/tip flags and IK rotation limits.
- Fixed/local axes.
- Additional rotation/location target and influence.
- Bone-tail connection.

Additional tools:

- **AI Translate Checked Bone Japanese Names** uses the shared AI settings.
- **Complete Checked/All** fills and normalizes missing MMD names and mirror
  suffixes.
- Synchronize bone names to bound rigid bodies or Joints.
- **Bone Subdivision** resamples checked bone chains, creates continuous IDs,
  and divides original vertex-group weights among the new segments.
- **Create MMD Physics from Selected Bones** can create tracking bodies,
  physical bodies, parent-child Joints, or both bodies and connecting Joints.
- **Batch Clean Bones** first merges weights into the chosen target bone, then
  removes checked bones and their bound rigid bodies/Joints.

### 6.3 Rigid bodies

The active inspector edits names, bound bone, type, shape, size, collision
groups, mass, friction, restitution, and damping.

Batch tools can:

- Delete checked bodies together with relevant Joints.
- Create a Joint from exactly two checked bodies. The active row is rigid body
  B; the other checked row is A.
- Create mirrored bodies or synchronize checked source parameters to existing
  mirrored bodies.
- Synchronize the selected rigid body's current axes to Joints where it is the
  B endpoint.

### 6.4 Joints

The active inspector edits names, body A/B endpoints, XYZ linear/angular
limits, and springs.

- Delete checked Joints.
- Mirror or synchronize checked Joints.
- Synchronize names from rigid body B. Vertical/anchor Joints use the body name
  directly; horizontal Joints receive the `_H` suffix.

### 6.5 Diagnostics

Diagnostics reports confirmable model-structure problems rather than judging
artistic physics values.

1. Select a row to read the problem and suggested resolution.
2. Use the arrow button to jump to the affected object or data.
3. Use the tool button to attempt a deterministic repair.
4. **Repair All** processes only repairs with a safe, unambiguous result and
   skips anything that needs human judgment.

## 7. Edit Morphs

Select an MMD model and use the Material, UV, Bone, Vertex, and Group tabs.
The central value column previews a Morph and supports animation keyframes.

### 7.1 List operations

- Show/hide Japanese and English names and filter with Search.
- Add, delete, clean empty Morphs, and reorder checked rows.
- **Range Select** checks every visible row between the first and last checked
  rows.
- **Japanese Name to English Name** copies names without translation.
- **AI Translate** translates checked Japanese/Chinese Morph names.

### 7.2 AI translation settings

Open the gear button and enter:

- API base URL only; MMD Station appends `/v1/chat/completions`.
- API key.
- A model name supported by that OpenAI-compatible service.

These settings are stored in Blender add-on preferences. Review AI-generated
names before export, especially symbols and left/right naming.

### 7.3 Copy and paste

**Copy Checked Morphs** writes PMX Editor-compatible CSV to the clipboard.
**Paste Morphs from Clipboard** reads the same structure.

Bone, Material, and Group Morphs can be copied between compatible models.
Vertex Morphs and vertex-group-based UV Morphs are model-topology dependent and
are deliberately skipped when cross-model copying would be unsafe.

### 7.4 Detail editors

- **Material Morph**: add/remove/reorder material rows; batch-select detail
  rows; use Hide/Show presets; edit multiply/add factors, diffuse, edge,
  specular, texture, sphere, and Toon factors.
- **UV Morph**: choose UV through UV4, manage affected Mesh/vertex-group
  details, and preview or clear the UV deformation.
- **Bone Morph**: edit target bone translation, rotation, and weight. A weighted
  Bone Morph can be converted to Vertex Morphs only on Meshes influenced by
  that bone hierarchy.
- **Vertex Morph**: select and jump to the target Mesh/ShapeKey. Cleaning uses
  the displayed local-space displacement threshold.
- **Group Morph**: add checked Morphs from the other tabs and edit each member's
  weight.

VMD import and export are connected to these central sliders. Keyframes added
with `I` on a slider remain visible and editable in Blender's animation tools.

## 8. Edit display frames

Display frames control PMX/MMD menu grouping.

1. Select an MMD model.
2. Use the upper list to add, delete, select, and reorder frames.
3. Use the lower list to add, delete, select, and reorder items in the active
   frame.

For a normal frame, select bones in Edit/Pose Mode and click **Add Selected
Content**. **Smart Fill Unlisted Visible Bones** adds visible bones that are not
already in any frame.

For the **Facial** frame, check Morphs in Morph Editor first, then add them.
**Smart Reorder Facial Frame** sorts valid non-empty Morphs as Group, Material,
UV, Bone, and Vertex.

Other tools:

- Range-select frames or items.
- Clean stale items whose target bone/Morph no longer exists.
- Select checked display bones in Blender.
- Edit the active frame/item details below the lists.

## 9. Preview physics

MMD Station uses its bundled native solver and does not create a Blender Rigid
Body World.

### 9.1 Choose scope

- **Current Proxy** previews the selected proxy within one model.
- **Whole Model** previews checked MMD models. Each model normally uses its own
  interaction number and runs independently.

Models with the same solver scale and interaction number share one collision
world. Use that only when models must collide with each other.

### 9.2 Solver controls

- **Solver Scale** is normally detected from the imported model. Override it
  only when automatic detection is wrong; forcing a different scale changes
  MMD-space dimensions.
- Choose the **MMD** or **PMX Editor** DLL target.
- Set fixed frequency, substeps, gravity, and optional rigid-body debug motion.
- **Update Rigid Bodies / Joints to Current Pose** transforms physics from Rest
  Pose to the current Action pose while preserving authored offsets.

### 9.3 Start, reset, and stop

- Start the current proxy or all checked models.
- **Reset** restores the startup snapshot while keeping the preview running.
- **Stop** restores the original pose and ends the corresponding session.

If a model is moved, its Action changes, or the physics structure is edited,
reset or restart the preview so the solver receives a clean snapshot.

## 10. Bake and repair physics animation

Physics baking writes a separate `<Source Action> · Physics Bake` Action. The
source Action is not overwritten.

### 10.1 Bake a range

1. Select the MMD Root and its source Action.
2. Set Start, End, and Pre-roll.
3. Choose **Independent Bake** for a self-contained range or
   **Continue Previous Segment** to continue a previously completed segment.
4. Choose:
   - **Fast Bake** for time-sliced solving without real-time playback.
   - **Playback Bake** to show each solved frame at scene playback speed.
5. Watch frame, speed, and ETA. Press `Esc` or right-click to cancel.

Cancellation restores the original Action, frame, and starting pose and does
not commit a partial segment.

Completed segments list their range, continuity mode, bake mode, and speed.
Delete one segment with its `X`, or use **Clear** to remove the current Action's
entire bake result.

Physics snapshots are stored beside the `.blend` file and migrate when an
unsaved project is saved for the first time. If a snapshot file is missing,
rebake the affected range.

### 10.2 Repair a baked range

1. Switch to the generated Physics Bake Action.
2. Set the repair start/end inside a completed bake range.
3. At any intermediate frame, enter Pose Mode and adjust one or more dynamic
   physics bones.
4. Click **Record Current Frame Correction**. Record as many anchors as needed.
5. Click **Re-solve and Connect**.

The repair layer automatically uses zero correction at its two endpoints and
smoothly incorporates the recorded intermediate corrections. The trash button
clears the current repair guide.

## 11. Enable MMD-compatible IK

The **MMD IK** workspace keeps the original MMD Tools Armature as the only
visible and bound Armature while the native runtime takes over compatible MMD
IK chains in memory.

1. Select the MMD model.
2. Click **Enable MMD IK Compatibility**.
3. Play or scrub the animation and create keyframes on the original Armature as
   usual.
4. Click **Disable MMD IK Compatibility** to stop native takeover and restore
   Blender/MMD Tools evaluation.

The runtime does not add export bones or modify the PMX skeleton. If model
objects change, refresh/re-enable the runtime before evaluating again.

## 12. Updates and interface language

### Automatic updates

Update options are in **Edit > Preferences > Add-ons > MMD Station**.

- Stable GitHub Releases are checked by default.
- Pre-releases are opt-in.
- **Update Now** downloads the ZIP attached to the selected GitHub Release,
  keeps one rollback backup, and asks for a Blender restart after replacement.
- Ordinary commits on `main` are never offered as updates.

### Interface language

MMD Station follows Blender's interface language:

- Simplified and Traditional Chinese locales use Chinese.
- Every other Blender locale uses English.

Change it under **Edit > Preferences > Interface > Translation > Language**.

## 13. Common workflows

### Create skirt physics from a Mesh

1. Select the skirt vertices in Edit Mode.
2. Create a Closed proxy with enough columns and height levels.
3. Inspect and sculpt the proxy; leave Edit/Sculpt Mode to sync bones.
4. Apply the Stable Midi-Length Skirt preset.
5. Generate rigid bodies and Joints.
6. Use Diagnostics, then preview physics.
7. Tune parameters, Apply Parameters, reset preview, and compare again.
8. Bake only after the live preview is satisfactory.

### Create physics from an existing bone chain

1. In MMD Viewer > Bones, sync selected Pose/Edit bones from the 3D Viewport.
2. Use **Create MMD Physics from Selected Bones** for tracking bodies,
   physical bodies, Joints, or the combined route.
3. Inspect the generated bodies and Joints in their Viewer tabs.
4. Preview and adjust.

### Prepare a model for PMX export

1. Run Diagnostics and resolve confirmable structural errors.
2. Review material order, names, IDs, and texture paths.
3. Review bone names and PMX order.
4. Clean empty Morphs and review the Facial display frame.
5. Export PMX from the top shortcut and inspect the result in the target MMD
   application.

## 14. Troubleshooting

### The MMD Station tab is missing

- Confirm Blender is version 4.4.
- Confirm both MMD Tools and MMD Station are enabled.
- Restart Blender after installing or updating.

### Import/export buttons are disabled or fail

- Install and enable MMD Tools first.
- Select an object belonging to an MMD model for export.
- Use a file format supported by the selected MMD Tools operation.

### A list does not contain the expected item

- Clear Search and prefix filtering.
- Disable **Current Proxy Only**.
- Select the correct MMD Root and click Refresh.

### Proxy creation fails

- Work in Mesh Edit Mode with selected vertices.
- Use at least three columns for a Closed proxy.
- Use a unique prefix, or intentionally restore the existing proxy instead.

### Preview does not start

- Windows x64 is required for the bundled DLLs.
- Select a valid MMD Root and proxy/model scope.
- Confirm rigid bodies and Joints exist and are structurally valid.
- Stop an active bake before starting preview.

### English/Chinese UI is not switching

- Change Blender's interface language, not only the operating-system language.
- Make sure interface translation is enabled in Blender Preferences.
- Restart Blender or reload scripts after changing the installed add-on files.

