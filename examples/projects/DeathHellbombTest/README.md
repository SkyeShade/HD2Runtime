# DeathHellbombTest

Integration test for death events and the explosion action (`docs/event-scripting.md`): **when the local player dies,
request a Hellbomb detonation at the death position.**

## Status: the Hellbomb is refused (expected)

Runtime can request the game's own explosions now (`hd2.explosions.spawn`, see `docs/events.md#actions`), but only
explosions whose identity is proven. The Hellbomb's is not: no Hellbomb request was captured, and the Hellbomb entity
(`content/fac_helldivers/hellpod/hellbomb/hellbomb`) names no explosion type. So the request is refused with
`UNKNOWN_EXPLOSION`, and Runtime does not fake the effect by editing another explosion's definition. A working
explosion is tested by `HeavyDevastatorDelayedExplosionTest`.

## What this test proves

- `player_died` for the local player, with a read-only **death-position snapshot** and how it was observed.
- The snapshot is plain data: 3 s later (after the avatar may be destroyed) it still reads the same.
- The host flag (`hd2.game_state().host`).
- The explosion action's fail-closed refusal of an unproven explosion.
- The recursion guard: a death caused by a mod's action is not reacted to.

## How to test

Die in a mission. The log shows `local player died at (x, y, z) (observed dead_state|avatar_removed); host
true|false`, then `Hellbomb detonation at (x, y, z): refused UNKNOWN_EXPLOSION: no catalogued explosion for B-100
Portable Hellbomb ...`, and 3 s later `the death snapshot still reads (x, y, z)`. Report whether the position looks
right (not (0,0,0), not missing) and whether `player spawned at` appears after reinforcement.
