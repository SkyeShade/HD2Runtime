# PelicanGatlingSupport 0.8.0: Pelican Gatling Support

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| Pelican Gatling Support | ←↓←←↑↑ (LEFT DOWN LEFT LEFT UP UP) | 300 s | 4 per mission |

> Calls down a Pelican for close air support. Hovers around the beacon for 90 seconds and bombards nearby enemies with its high fire rate machine gun.

Item traits: CUSTOM STRATAGEM, PELICAN, HEAVY ARMOR PENETRATING.

The Pelican CAS, made plain with its live-tested defaults: the MG-206's AP4 round at the Gatling Sentry's rate, 15 mrad, no aim recoil, aim 0.7 m above the feet, the Bastion HMG sound. The aim and explosive-round Mod Options are gone. New icon. 4 uses per mission, 300 s cooldown.

The log names this build: `PelicanGatlingSupport 0.8.0 BUILD`.

## What to look for in a live test

1. The chin gun fires continuously with the Bastion HMG sound.
2. After the fourth call the slot stays on cooldown for the rest of the mission (`USES: 4 of 4: SPENT`).
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

The Pelican family (live-proven with several players).

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
