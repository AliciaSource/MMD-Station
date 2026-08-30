# MMD Station Release Notes

## Unreleased

### Added

- Added a host-level auto-updater that follows published
  `AliciaSource/MMD-Station` GitHub Releases, supports stable and opt-in
  pre-release channels, creates a rollback backup, and reports live update
  progress in Blender.
- Added an in-panel GitHub shortcut and development-aware version display.
- Added a release-ready English README and a pure `pack.ps1` packaging command.

### Changed

- Renamed and consolidated the add-on identity as `MMD Station` / `mmd_station`
  while preserving legacy `surface_proxy.*` operators and saved `.blend`
  property identifiers for compatibility.
- Kept development commits invisible to the updater; only GitHub Releases with
  an attached installable ZIP can be offered to users.

### Fixed

- Deferred the initial physics-cache sidecar scan until Blender data is
  available, preventing add-on registration from failing during `.blend` file
  startup.
