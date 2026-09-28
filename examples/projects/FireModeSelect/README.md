# FireModeSelect

Makes Semi Auto the default fire mode of the AR-23C Liberator Concussive. Its native fire-mode set is
Automatic, Single (the first entry is the default); the patch reorders it to Single, Automatic through
`hd2.fields.fire_mode.modes`. Both modes stay selectable. See `docs/fire-modes.md`.

The older `weapon.default_fire_mode` / `hd2.enums.fire_mode` form covers the same bytes and is no longer taught.
Requires HD2Runtime 0.26.0. Built only; not deployed automatically.
