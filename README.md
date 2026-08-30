# MMD Station

MMD Station is a Blender 4.4 add-on for editing, validating, previewing, and
exporting MikuMikuDance models in one workspace.

## Highlights

- MMD model, VMD, and VPD import/export shortcuts backed by `mmd_tools`.
- PMX-aware bone, rigid body, Joint, Morph, material-order, and display-frame
  editing.
- Surface-proxy authoring for skirts, hair, ribbons, and similar physics chains.
- Rigid body and Joint generation, mirroring, parameter presets, and pose
  alignment.
- Native Windows x64 Bullet physics preview and non-destructive physics baking.
- MMD-compatible IK authoring and runtime preview without polluting PMX export.
- Session-local Shadow Model acceleration for repeated compatible PMX exports,
  with automatic fallback to a complete export when structural data changes.
- In-panel version display, GitHub shortcut, release notifications, rollback
  backup, and self-update support.

## Requirements

- Blender 4.4
- **MMD Tools is a required dependency.** Install and enable it before MMD
  Station. MMD Station relies on MMD Tools for the MMD model data API and
  PMX/VMD/VPD import and export workflows.
  - [Official MMD Tools page on Blender Extensions](https://extensions.blender.org/add-ons/mmd-tools/)
  - [MMD Tools source code on GitHub](https://github.com/MMD-Blender/blender_mmd_tools)
- Windows x64 for the bundled native physics and IK libraries

## Installation

There is no stable release package yet. For development use:

1. Install and enable [MMD Tools](https://extensions.blender.org/add-ons/mmd-tools/).
2. Clone this repository.
3. Copy or link the `mmd_station` directory into Blender's add-on directory:
   `%APPDATA%\Blender Foundation\Blender\4.4\scripts\addons\mmd_station`
4. In Blender, open **Edit > Preferences > Add-ons** and enable **MMD Station**.
5. Open the 3D Viewport sidebar and select the **MMD Station** tab.

When stable releases begin, install the `mmd_station-X.Y.Z.zip` asset attached
to the matching GitHub Release. The built-in updater intentionally follows
published Releases only; development commits on `main` are never offered as
updates.

## Main Workspaces

- **Proxy Creation** — create or recover proxy surfaces, bones, weights, rigid
  bodies, and Joints.
- **MMD Viewer** — inspect and edit bones, rigid bodies, Joints, Morphs, and
  display frames.
- **Morph Editor** — edit, order, preview, keyframe, copy, and paste MMD Morphs.
- **Physics Preview** — preview, align, cache, and bake MMD physics.
- **MMD IK** — author and preview MMD-compatible IK behavior.

## Updating

Update settings are available in the MMD Station add-on preferences. By
default, MMD Station checks stable GitHub Releases once per day and shows a
banner at the top of its panel when an update is available. Pre-release builds
are opt-in. Installation creates one rollback backup and requires Blender to be
closed and reopened after files are replaced.

## Interface Language

MMD Station follows Blender's selected interface language automatically.
Simplified Chinese and Traditional Chinese locales use the Chinese interface;
every other locale uses English. Labels, hover descriptions, enum choices,
runtime status text, warnings, and errors share one bilingual catalog and do
not require separate implementations for each Blender language.

The localization coverage test is a required development gate. A new
user-facing Chinese source string without an English catalog entry fails the
test, while runtime-composed UI text and operator reports must pass through the
central localization boundary. This keeps future features bilingual by
default instead of relying on a release-time translation pass.

## Building a Release Package

`pack.ps1` is a pure packager. It does not change the version, create a commit,
push, tag, or publish a Release.

```powershell
.\pack.ps1 -Ref v0.1.8
```

The resulting ZIP is written to `dist\` and must be attached to the matching
GitHub Release for the built-in updater to use it.

## License and Third-Party Software

MMD Station is distributed under the GNU General Public License v3.0. The
vendored add-on updater is derived from the GPL-licensed
[`CGCookie/blender-addon-updater`](https://github.com/CGCookie/blender-addon-updater).
The native solver directories include their own third-party notices and license
files for Bullet Physics and related components.
