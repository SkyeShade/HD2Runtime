# ReprimandFireModeProof (development only)

An SMG-32 Reprimand with two selectable projectile modes, three fire rates and a 50-round magazine. The Custom mode
fires `dev/talon_combined` through the live-verified weapon projectile replacement
(`docs/custom-projectile-rows.md#weapon-projectile-replacement`). It is **not** a public mod: it calls Runtime
internals that may change.

Build with `py scripts/build_custom_projectile_proof.py` (it also builds the matching development runtime into
`build/test-artifacts/`). Install the development `HD2Runtime-<version>-runtime.zip` and
`ReprimandFireModeProof-0.1.0.zip` from there. **Uninstall ReprimandCustomProjectileProof first**, and install one fire-mode
proof at a time (LiberatorConcussiveFireModeProof uses the same carrier). ReprimandCustomProjectileProof swaps the
Reprimand's normal projectile to the carrier and binds the same carrier, so both modes would fire it. With both
installed, this mod logs a warning when it binds.

## What it configures

| Setting | Field (`hd2.fields.`) | Native member | Value |
| --- | --- | --- | --- |
| Mode selector | `weapon_function.left` | WeaponDataComponent +184 | `none` -> `programmable_ammo` |
| Custom mode projectile | `function_ammo.projectile` | ProjectileWeaponComponent +576 | `none` -> the carrier, `hd2.attack_output('output/v1/projectile/td-110-maelstrom-slot-2')` (type 324) |
| Normal mode projectile | unchanged | ProjectileWeaponComponent +0 | the Reprimand's own bullet (type 123) |
| Fire rate | `weapon.fire_rate` | ProjectileWeaponComponent +8 (f32, rounds per minute) | 490 -> a Mod Options choice: 490 (the Reprimand's own), 872 (the M7S SMG's own), **1500** (default) |
| Magazine | `magazine.capacity` | WeaponMagazineComponent +136 (u32, rounds) | 25 -> 50; reserve unchanged |
| Mode labels | `presentation.mode_label`, `presentation.mode_icon` on the two projectiles | ProjectileInfo +12, +16 | Normal `standard` (plain round), Custom `he` (HE icon); a Mod Options toggle |

The modes are the game's own ProgrammableAmmo weapon function: while it is on, the fire path fires +576 instead of the
weapon's projectile (`docs/weapon-feeds.md#programmable-ammunition`). So the Custom mode fires the carrier, and only
the carrier, and Runtime replaces exactly those shots. The Normal mode fires the native bullet, which Runtime counts
and logs but never replaces. The right input keeps the native fire-mode selector (Automatic / Single / Burst).

Everything is copied into a Reprimand when the game builds it: after APPLY (or a Mod Options change), take a fresh
Reprimand from your loadout or a call-in.

### Why the fire rate is a Mod Options choice

The Reprimand has two weapon-function inputs. The right one is the native fire-mode selector, which Runtime does not
rebind (`weapon_function.right` is read-only). The left one is free, and it can take **either** the ProgrammableAmmo
selector **or** the rate-of-fire selector, not both. This proof gives it the projectile modes. Three in-game rates
(`fire_rate.modes`) would need that same input, so the rate is chosen in Mod Options instead and applies to the next
Reprimand the game builds. Without the Mod Options Menu, the default (1500 rpm) applies.

### The 1500 rpm arithmetic

`weapon.fire_rate` is in rounds per minute: the Reprimand's stored 490.0 equals its catalogued 490 rpm, and the field
matches 33 of 37 weapons exactly (`schemas/weapon_mapper.lua`). 1500 rpm is 25 shots per second, one every 40 ms; a
50-round magazine empties in 49 x 40 ms = 1.96 s. Replacement allows 30 per second (a burst of 40) and 24 per update,
so 25 per second never drops a shot.

## Keys (host, in a mission)

- **F12**: custom replacement on / off. Off, Custom mode fires the invisible, harmless carrier alone; Normal mode is
  unchanged.
- **F9**: counts (replaced, dropped, refused, not yours; Normal shots not replaced), the mode of the last shot, the
  last burst's shot count and measured rpm, and the configured rate and magazine.

The selected mode is not read from the game (Runtime has no reader of the selector state). F9 reports the mode of the
last shot fired instead, from the projectile it fired.

## What the log shows

At startup: the configured modes, fields and values. At mission start:

```
mission started: custom replacement binding: Custom mode carrier output/v1/projectile/td-110-maelstrom-slot-2 ->
  dev/talon_combined; Normal mode output/v1/projectile/smg-32-reprimand -> no replacement: bound
```

Every shot is logged:

```
projectile replacement: custom mode: TD-110 Maelstrom / slot_2 shot N: carrier slot S (type 324) at (...) travelled
  D m (...); owner A, source W (SMG-32 Reprimand); custom dev/talon_combined from (...) along (...) -> slot M ...
projectile replacement: normal mode: SMG-32 Reprimand shot N: native projectile slot S (type 123) at (...) travelled
  D m; owner A, source W (SMG-32 Reprimand) -> no replacement
```

After each burst (0.3 s without a shot):

```
projectile replacement: SMG-32 Reprimand burst: 50 shots (50 custom, 0 normal) over 1.96 s = 1500 rpm
```

The measured rpm counts each shot at the update that first saw it, so it is exact to about one frame at each end of the
burst (about 1 to 2 % over a 2 s burst at 60 fps).

## Live test

See `docs/custom-projectile-rows.md#live-test-reprimand-fire-modes`.
