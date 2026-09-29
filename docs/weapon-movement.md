# Weapon movement restrictions

The M-1000 Maxigun stops its wielder while firing, while ordinary weapons do not restrict movement. This page
describes what the game represents as data, what HD2Runtime lets you change, and what is code-driven.

## What the game stores

- **`weapon.stationary_while_firing`** (WeaponDataComponent +387, a boolean). Only the Maxigun sets it. game.dll
  reads it while the wielder fires. When it is set, firing does three things:
  - it sends the weapon's firing-start wielder animation event (the Maxigun's is `brace`);
  - it arms the firing-stop event (`brace_exit`);
  - it raises one bit (bit 55) in the wielder's action mask.

  This is the only data-driven movement restriction on any player or support weapon.
- **Firing-stance events** (WeaponDataComponent +388/+392). Only the Maxigun and the GL-28 Belt-Fed Grenade
  Launcher carry `brace` / `brace_exit`. The only code reader found sends them only while
  `stationary_while_firing` is set. They are published read-only.
- **Per-shot wielder animation** (for example `fire_rifle`, `fire_mg`, `fire_minigun`, `fire_flamethrower`). This is
  published read-only. Whether a per-shot animation slows the wielder is animation-graph behaviour.

There is **no movement-speed multiplier** in any weapon record. A differential over every member of every component
owned by any resolved player or support weapon finds none. Diving, sprinting and walking are not separately
represented in weapon data.

## What you can change

`weapon.stationary_while_firing` is writable on every resolved player and support weapon: 105 weapons, each with its
own WeaponData record. Every write requires `allow_unverified_effect=true`, because the in-game effect of changing
it has not been confirmed yet.

```lua
-- Let the Maxigun move while firing.
local maxigun = hd2.support_weapon('M-1000 Maxigun')
return hd2.ensure({patch={id='maxigun-mobile-firing', target=maxigun,
    field=hd2.fields.weapon.stationary_while_firing, expect=true, value=false,
    allow_unverified_effect=true}})
```

| Goal | How | Status |
| --- | --- | --- |
| Remove the Maxigun's stationary restriction | `stationary_while_firing` true → false | Supported (unverified effect) |
| Give the Maxigun GL-28-style behaviour | the same write; afterwards the Maxigun's movement-related weapon data equals the GL-28's | Supported (unverified effect) |
| Make another weapon stationary while firing | false → true | Supported (unverified effect); weapons without firing-stance events get no brace animation |
| Remove the Cremator's slowdown | — | Not available: no data owner found |
| Change a movement multiplier | — | Not available: none exists in weapon data |
| Ban only diving or only sprinting | — | Not available: not separately represented |

`sdk/WeaponMovementCapabilities.json` (contract `hd2runtime.weapon_movement.v1`) lists every weapon's baseline,
writability, firing stance and per-shot animation.

## Code-driven or unresolved

- **Slowdown magnitude.** No data field; code- or animation-driven.
- **GL-28 slowdown.** Its brace events exist, but the only reader found does not send them for the GL-28. Its
  per-shot animation (`fire_minigun`, shared with the Maxigun) is a candidate, not proven.
- **Cremator slowdown.** Its one exclusive WeaponData flag (+1220) is read only by the weapon audio update, between
  the `rounds_remaining` and `weapon_rpm` sound parameters. It is not a movement flag.
- **Action bit 55.** Which actions it blocks (movement, diving) is decided in code.

## Evidence and safety

- The research (`scripts/research_weapon_movement.py`) re-proves on every run:
  - the WeaponData layout fingerprint (member offsets, sizes, storage and hidden-name lengths);
  - the unique game.dll reader of +387 and its action-bit write;
  - the audio-only reader of +1220;
  - the Maxigun-only baseline.
- Writes go through the normal guarded player/support weapon path: fresh ownership proof, `expect` guard,
  rollback on failure.
- The game-update migration tracks the field like every other WeaponData field.
