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
