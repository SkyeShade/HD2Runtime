# OrbitalEmsBarrage 0.1.0: Orbital EMS Barrage

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| Orbital EMS Barrage | →↓↑→←↓ (RIGHT DOWN UP RIGHT LEFT DOWN) | 60 s | unlimited |

> A prolonged "compliance barrage" to modify enemy behavior in a wide area. Stuns enemies in a large area.

Item traits: CUSTOM STRATAGEM, ORBITAL, ANTI-TANK, STUN.

The Orbital 120mm HE Barrage's own barrage (5 salvos of 3 shells), each shell bursting into the Orbital EMS Strike's stun field instead of its blast: the Orbital Gas Barrage's technique with the EMS field.

The log names this build: `OrbitalEmsBarrage 0.1.0 BUILD`.

## What to look for in a live test

1. Fifteen shells over the beacon, each leaving a blue EMS field; enemies in them are stunned.
2. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

As the Orbital Gas Barrage (native orbitals, live-proven with several players): every machine fires the donor's own barrage and converts its own copies of the shells.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
