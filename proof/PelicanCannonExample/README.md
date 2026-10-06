# PelicanCannonSupport 0.1.0: Pelican Cannon Support

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| Pelican Cannon Support | ←↓←↑←↑ (LEFT DOWN LEFT UP LEFT UP) | 300 s | 3 per mission |

> Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and bombards nearby enemies with a heavy burst autocannon.

Item traits: CUSTOM STRATAGEM, PELICAN, ANTI-TANK, EXPLOSIVE.

A Pelican holds over the beacon for 90 s and orbits it 85 s, fighting with its own chin autocannon and its own burst AI (the vanilla gun: round = native, nothing else changed; its kills credit the caller). 3 uses per mission, 300 s cooldown.

The log names this build: `PelicanCannonSupport 0.1.0 BUILD`.

## What to look for in a live test

1. The Pelican's own autocannon bursts.
2. After the third call the slot stays on cooldown for the rest of the mission; the log says `USES: 3 of 3: SPENT`.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

The Pelican family (live-proven with several players): the session host spawns it for whoever called it.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
