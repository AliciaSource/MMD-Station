# MMD Station Project Rules

## Localization

- MMD Station is architecturally bilingual. Blender locales `zh_HANS`,
  `zh_HANT`, `zh_CN`, and `zh_TW` use the existing Chinese UI. Every other
  Blender locale uses the shared English catalog.
- Every new user-facing label, tooltip, enum label, status message, warning,
  and error must be added to `mmd_station/i18n/catalog.py` in the same change.
  Do not add a separate catalog for each non-Chinese locale.
- Static Blender RNA and layout strings may remain Chinese source msgids.
  Runtime-composed layout text must pass through `i18n.iface()`, and operator
  reports must use `i18n.report()`.
- Run `python -m pytest -q tests/test_i18n_catalog.py` after any UI change. The
  coverage gate must stay green; do not bypass it by excluding a module or
  user-facing string.
- Run `tests/i18n_blender_smoke.py` in Blender 4.4 when changing the catalog,
  translation lifecycle, locale policy, or UI boundary helpers.

## Compatibility

- Keep the product and package identity exactly `MMD Station` / `mmd_station`.
- Preserve legacy `surface_proxy.*` operators, Scene property names, custom
  properties, and saved `.blend` persistence identifiers.
- Whenever a new feature design or an adjustment to existing behavior involves
  Blender APIs, automatically review cross-version compatibility without waiting
  for the user to request it. Prefer the shared `blender_compat.py` helpers;
  check API availability, signatures, defaults, and runtime behavior across the
  supported Blender versions. Run risk-appropriate multi-version regressions
  using the current 4.4.x, 4.5 LTS, and 5.2.x matrix, and update that matrix when
  supported versions change. Passing on one version is not evidence of general
  compatibility; record any untested versions or version-specific limitations.

## Credential and private endpoint protection

- AI translation API keys, access tokens, passwords, client secrets, and real
  AI translation service URLs are local-only data. Never place them in source,
  tests, fixtures, documentation, logs, Git commits/tags, GitHub metadata,
  generated ZIPs, or Release assets. `morph_ai_api_url` and
  `morph_ai_api_key` must have empty source defaults; users enter both only in
  Blender preferences stored outside this repository.
- Before every push, run `python tools/security_scan.py --ref HEAD`. Never use
  `git push --no-verify` to bypass the repository pre-push gate. Every clone
  used for pushing must first run `tools/install_git_hooks.ps1`, which sets
  `core.hooksPath=.githooks`.
- `pack.ps1` must run the same security gate against the selected Git ref or
  working-tree package and then scan the finished ZIP. A failed scan is a hard
  stop: do not push, tag, upload, publish, or retain the rejected ZIP.
- Placeholder endpoints under reserved example domains may appear only in
  tests. Actual service endpoints and credential values must never be used as
  fixtures. If a real credential is ever detected in a cloud-accessible
  object, remove the object/history and revoke or rotate the credential before
  continuing release work.

## Post-release development workflow

- The first local modification after every stable release must automatically
  reopen development mode before feature or bug-fix work continues. Do not wait
  for the user to ask for a dev build separately.
- Run `tools/dev_link.ps1` so the real Blender 4.4 add-on path
  `%APPDATA%\Blender Foundation\Blender\4.4\scripts\addons\mmd_station` is a
  directory Junction to this repository's `mmd_station/` directory. Source
  edits then take effect after Reload Scripts or a Blender restart.
- Change `bl_info["version"]` from the last stable `X.Y.Z` to the next patch
  `X.Y.(Z+1)` and set `_version.py` to `PRERELEASE = "dev"`. The panel and the
  newest `DEV_LOG.md` heading must use the same `vX.Y.(Z+1)-dev` version. Do not
  choose a minor or major increase unless the user explicitly requests it.
- Reset `RELEASE_NOTES_NEXT.md` to an English `## Unreleased` section at the
  start of the new development cycle. Merge later work on the same feature or
  bug into one concise user-facing entry instead of appending duplicates.
- Development uses the Junction and does not produce iterative ZIP packages.
  Only a stable release sets `PRERELEASE = None`, packages from its exact tag,
  and attaches that ZIP to the matching GitHub Release.
- Local commits remain automatic after risk-appropriate validation. Push, tag,
  and GitHub Release still require explicit user approval.
