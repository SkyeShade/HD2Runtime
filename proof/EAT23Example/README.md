# EAT23ExpendableEMS 0.1.0: EAT-23 Expendable EMS

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r29 build or later. Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| EAT-23 Expendable EMS | ↓↓←→→ (DOWN DOWN LEFT RIGHT RIGHT) | 70 s | unlimited |

> A single-use "compliance weapon" that comes down in pairs and modifies enemy behaviour. The EMS warhead stuns targets within the impact radius.

Item traits: CUSTOM STRATAGEM, SUPPORT WEAPON, ANTI-TANK, STUN, EXPENDABLE.

Two expendable EAT-17 clones from one pod; each rocket bursts into the Orbital EMS Strike's stun field on impact (as the EAT-40's bursts into gas). A clone on an unused EAT-700 or EAT-411, else the regular EAT-17 itself.

The log names this build: `EAT23ExpendableEMS 0.1.0 BUILD`.

## What to look for in a live test

1. Two launchers in the pod, with this name and icon.
2. A rocket impact leaves the blue EMS field and stuns enemies in it.
3. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

As the EAT-40 (the expendable family, live-proven with several players): every compatible machine converts its own copy of the rockets, whoever fires them.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
