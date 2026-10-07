# ShredderSilo 0.2.0: MS-N223 Shredder Silo

One custom stratagem, defined as data in `custom_stratagems.json` (the format a builder writes; `hd2.py build` compiles it into `src/addon.lua`). Needs the HD2Runtime 0.30.0-dev r45 build or later (`max_per_player`). Not live-tested in this form.

| Stratagem | Code | Cooldown | Uses |
|---|---|---|---|
| MS-N223 Shredder Silo | ↓↑→↑↓↓→ (DOWN UP RIGHT UP DOWN DOWN RIGHT) | 180 s | 1 per mission |

Each player may pick it into at most ONE loadout slot (`max_per_player = 1`): a second pick is refused and its tile shows why. One call per mission (`uses = 1`): the game's own use counter on its slot shows 1, then 0.

> A silo that fits one single, tactical nuclear missile. Possible side effects include shell shock, mutation, and/or death. A laser targetting remote is provided.

Item traits: CUSTOM STRATAGEM, SUPPORT WEAPON, EXPLOSIVE, ANTI-TANK, EXPENDABLE.

The MS-11 Solo Silo from its own pod, with its laser remote. Where exactly this call's missile detonates, the Runtime also requests the Cyborg Production Unit's self-destruct explosion (the Halt Cyborg Production objective's blast: 10,000 damage, demolition 60, a 50 m inner and 100 m outer radius; the missile's own blast still goes off). Its effect and sound ship only in two Automaton objective packages (about 300 MB together), loaded at mission start before the stratagem can be called. If they are not resident on the host at the detonation, the NUX-223 Hellbomb's explosion is requested instead. Stay more than 100 m away: the blast kills Helldivers too. No launch countdown: the launch timing is the game's code, not data.

The log names this build: `ShredderSilo 0.2.0 BUILD`.

**0.2.0:** at most one per player, one use per mission (0.1.0: unlimited uses, any number of slots).

## What to look for in a live test

1. The silo and remote arrive in the Solo Silo's own pod; fire it at a target more than 100 m away.
2. At the impact, a second, much larger explosion with the Cyborg Production Unit's effect and sound; the log: `missile N LAUNCHED`, then `missile N DETONATED at (...) (its own detonation in the explosion queue ...): Cyborg Production Unit explosion requested there on this machine (requested)`.
3. At mission start the log says `assets for custom-stratagem-shredder_silo requested: 4 package(s)` and, once loaded, `resident`; note how long that takes and whether the game hitches.
4. It destroys structures (demolition 60, the Hellbomb's) within its radius.
5. The custom panel's details show the code in arrows, the stats above and these item traits.

## Several players

A client runs its own silo call and publishes its missile (`CUSTOM MP ITEMS: missile network id N`); every other compatible Runtime watches its own copy of that missile (`REMOTE CUSTOM SILO`). Every machine requests the blast where the missile detonates, from its own copy, as the game requests the missile's own blast (`explosion Cyborg Production Unit mirrored at (...) on this machine`), attributed as the game attributes that detonation, so its kills credit the caller. (Runtime r32; r30 requested it on the host only, and a client drew nothing.) Not live-tested in this form.

Every machine needs the same mods and the same Runtime build (the definitions are part of the custom stratagem registry hash).
