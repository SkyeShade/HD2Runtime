# OrbitalGasBarrage 0.2.0: Orbital Gas Barrage

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| Orbital Gas Barrage | →→↓←↓← (RIGHT RIGHT DOWN LEFT DOWN LEFT) | 60 s | unlimited |

> A prolonged caustic barrage, spreading corrosive gas over a large area. Causes confusion and blindness on those affected. Breathing it in is not advised.

Item traits: CUSTOM STRATAGEM, ORBITAL, ANTI-TANK, CAUSTIC.

The Orbital 120mm HE Barrage's own barrage with each shell bursting into the Orbital Gas Strike's cloud (unchanged from 0.1.7 but for the code, text and traits).

The log names this build: `OrbitalGasBarrage 0.2.0 BUILD`.

## What to look for in a live test

1. Fifteen shells over the beacon, each leaving a gas cloud.
2. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

Live-proven with several players (native orbitals).

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
