# EAT40ExpendableGas 0.3.0: EAT-40 Expendable Gas

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| EAT-40 Expendable Gas | ↓↓←↓→ (DOWN DOWN LEFT DOWN RIGHT) | 70 s | unlimited |

> A single-use weapon that comes down in pairs. Outfitted with a caustic warhead that causes confusion and blindness in those affected.

Item traits: CUSTOM STRATAGEM, SUPPORT WEAPON, ANTI-TANK, CAUSTIC, EXPENDABLE.

The EAT-17G renamed: two EAT-17 clones from one pod whose rockets burst into the Orbital Gas Strike's cloud on impact. The clone-level Mod Options choice is gone (always the full clone, the live-tested level).

The log names this build: `EAT40ExpendableGas 0.3.0 BUILD`.

## What to look for in a live test

1. Two launchers in the pod, with this name and icon.
2. A rocket impact leaves the gas cloud.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

Live-proven with several players as the EAT-17G (the same definition).

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
