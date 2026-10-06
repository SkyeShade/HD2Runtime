# LiberatorConcussiveFireModeProof (development only)

ReprimandFireModeProof applied to the AR-23C Liberator Concussive: a Normal / Custom projectile mode, three fire rates
and a 50-round magazine. The Custom mode fires `dev/talon_combined` through the weapon projectile replacement
(`docs/custom-projectile-rows.md#weapon-projectile-replacement`). It is **not** a public mod: it calls Runtime
internals that may change. The addon is the same file as ReprimandFireModeProof except its `CONFIG` block (a test
checks it), so see `proof/ReprimandFireModeProof/README.md` for the mechanism, keys and log lines.

Build with `py scripts/build_custom_projectile_proof.py` and install the development runtime and
`LiberatorConcussiveFireModeProof-0.1.0.zip` from `build/test-artifacts/`. **Install one fire-mode proof at a time,
and not ReprimandCustomProjectileProof**: they all bind the same carrier, so the last one bound wins (a warning is
logged).

## What it configures

| Setting | Field (`hd2.fields.`) | Native member | Value |
| --- | --- | --- | --- |
| Mode selector | `weapon_function.left` | WeaponDataComponent +184 | `none` -> `programmable_ammo` (the right input keeps the native Automatic / Single selector) |
| Custom mode projectile | `function_ammo.projectile` | ProjectileWeaponComponent +576 | `none` -> the carrier (type 324) |
| Normal mode projectile | unchanged | ProjectileWeaponComponent +0 | the Concussive round (`output/v1/projectile/ar-23c-liberator-concussive`) |
| Fire rate | `weapon.fire_rate` | ProjectileWeaponComponent +8 (f32, rpm) | 400 -> a Mod Options choice: 400 (the Concussive's own), 640 (the AR-23 Liberator's own), **1500** (default) |
| Magazine | `attachment.magazine_capacity` on `weapon:magazine_attachment()` | the Rifle 5,5x50mm. Drum attachment's capacity, applied to WeaponMagazine +136 when the weapon is built | 60 -> 50, behind its own Mod Options toggle |
| Mode labels | `presentation.mode_label`, `presentation.mode_icon` | ProjectileInfo +12, +16 | Normal `standard` (plain round), Custom `he` (HE icon); a Mod Options toggle |

Differences from the Reprimand:

- **Projectile source.** The Concussive is `ACTIVE_DIRECT`: no ammunition delta patches its projectile, so the Normal
  mode is its own round. (The base AR-23 is different: its ammunition owns +0.) The function projectile +576 is
  patched by no customization on either weapon.
- **Magazine.** `magazine.capacity` is not writable on the Concussive: its default Drum magazine attachment owns the
  effective capacity (60). The proof edits the Drum's own capacity instead. The Drum is a shared definition: the
  Concussive is built with it, and the AR-23, AR-23A, AR-23C, AR-23P and AR-59 can equip it in the armory, so each of
  them changes while the toggle is on (`allow_shared`). 50 is 10 fewer than the native 60; turn the toggle off to keep
  60.
- **Labels.** The Concussive round is also fired by two other entities (one is `assault_rifle_exp`), so its STANDARD
  label shows wherever they list it in a mode menu (`allow_shared`, given explicitly in `CONFIG`).
- **Fire modes.** Native Automatic and Single (no Burst).

1500 rpm is one shot every 40 ms: 50 rounds in 1.96 s. The replacement allows 30 per second, so it never drops a shot.

## Live test

The checklist in `docs/custom-projectile-rows.md#live-test-reprimand-fire-modes`, on the Concussive: the native rates
are 400 / 640 / 1500, and the magazine reads 50 (toggle on) or 60 (toggle off).
