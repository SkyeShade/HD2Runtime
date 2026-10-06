# PelicanGasSupport 0.3.0: Pelican Gas Support

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| Pelican Gas Support | ←↓←→↓→ (LEFT DOWN LEFT RIGHT DOWN RIGHT) | 300 s | 4 per mission |

> Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and assists Helldivers with a gas bombardment, causing confusion and blindness in hit enemies.

Item traits: CUSTOM STRATAGEM, PELICAN, CAUSTIC.

A Pelican fires its chin round once a second (the Gatling Sentry's AI); each round bursts into a gas grenade's cloud. 4 uses per mission, 300 s cooldown.

The log names this build: `PelicanGasSupport 0.3.0 BUILD`.

## What to look for in a live test

1. A shot a second with the gas mortar sound, a gas cloud at each impact.
2. After the fourth call the slot stays on cooldown for the rest of the mission.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

The Pelican family (live-proven with several players).

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
