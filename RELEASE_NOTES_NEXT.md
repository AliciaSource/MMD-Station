# MMD Station Release Notes

## v1.0.0

MMD Station 1.0.0 is the first stable release.

### Added

- Added a host-level auto-updater that follows published
  `AliciaSource/MMD-Station` GitHub Releases, supports stable and opt-in
  pre-release channels, creates a rollback backup, and reports live update
  progress in Blender.
- Added an in-panel GitHub shortcut and development-aware version display.
- Added a release-ready English README and a pure `pack.ps1` packaging command.
- Added automatic Chinese/English interface selection based on Blender's
  language, including labels, hover descriptions, enum text, runtime status
  messages, warnings, and errors.
- Added a localization coverage gate so future UI additions must include their
  English catalog entry and use the shared runtime translation boundary.
- Added complete English and Simplified Chinese user manuals with quick
  navigation, beginner workflows, feature-by-feature instructions, and
  troubleshooting.

### Changed

- Renamed and consolidated the add-on identity as `MMD Station` / `mmd_station`
  while preserving legacy `surface_proxy.*` operators and saved `.blend`
  property identifiers for compatibility.
- Kept development commits invisible to the updater; only GitHub Releases with
  an attached installable ZIP can be offered to users.
- Documented MMD Tools as a required dependency and linked both its official
  Blender Extensions page and GitHub repository.

### Fixed

- Deferred the initial physics-cache sidecar scan until Blender data is
  available, preventing add-on registration from failing during `.blend` file
  startup.
