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
