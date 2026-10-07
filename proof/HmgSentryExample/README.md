# HeavyMgSentry 0.3.1: A/MG-101 Heavy MG Sentry

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| A/MG-101 Heavy MG Sentry | ↓↑→→→← (DOWN UP RIGHT RIGHT RIGHT LEFT) | 150 s | unlimited |

> An automated sentry turret firing with the prowess of an heavy machine gun. More sluggish than lighter variants. Hazardous to Helldivers in the crossfire.

Item traits: CUSTOM STRATAGEM, SENTRY, HEAVY ARMOR PENETRATING.

An A/MG-43 Machine Gun Sentry from its own pod, its own weapon only firing the MG-206 heavy machine gun's armor-piercing round at 400 rounds a minute, 5 mrad spread, 300 rounds (live-proven solo on 2026-10-04 as A/HMG-206).

The log names this build: `HeavyMgSentry 0.3.1 BUILD`. 0.3.1: the icon is the user's own HMG Sentry art (2026-10-04),
replacing the placeholder.

## What to look for in a live test

1. The sentry fires slowly (400 RPM) with heavy rounds that pierce heavy armor.
2. The log: `DELIVERED: pod N: sentry N` and `CONFIGURED (... sentry N)`; with several players also `CUSTOM MP ITEMS: sentry network id N` on the caller and `REMOTE CUSTOM SENTRY` on every other machine.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

NEW (not live-tested): a client runs its own sentry call. The machine that created the sentry configures it whole; every other compatible Runtime mirrors its round, spread and recoil on its own copy, so every player should see the heavy rounds.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
