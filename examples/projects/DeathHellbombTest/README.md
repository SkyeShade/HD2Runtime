# DeathHellbombTest

Integration test for death events (`docs/events.md`): **when the local player dies, request a Hellbomb detonation at
the death position.**

## Status: explosion step blocked

Runtime does **not** spawn the explosion in this build, and says so in the log. Research found the game's local
explosion request (game.dll `0x13C0A80`: a 256-entry queue drained in the game's own update, the call the hellpod
impact explosions use), but two things are not proven:

- **The Hellbomb explosion's identity.** The Hellbomb entity (`content/fac_helldivers/hellpod/hellbomb/hellbomb`) has
  no explosive component naming an ExplosionType; its detonation goes through components Runtime has not decoded.
- **The request's arguments.** Beyond the position and type, the request takes a source entity, a 64-bit id, a
  pointer to a constant block and several flags whose meaning is not established.

Runtime does not guess a 15-argument native call, and it will not fake the effect by editing another explosion's
definition. See `docs/events.md#explosions`.

## What this test proves now

- `player_died` for the local player, with a **death-position snapshot** read while the avatar existed.
- The snapshot is plain data: 3 s later (after the avatar may be destroyed) it still reads the same.
- The host flag (`hd2.game_state().host`), which a future explosion request will require.
- The recursion guard: a death caused by a mod's action is not reacted to.

## How to test

Die in a mission. The log shows `local player died at (x, y, z); host true|false`, the blocked-explosion line, and
3 s later `the death snapshot still reads (x, y, z)`. Report whether the position looks right (not (0,0,0), not
missing) and whether `player spawned at` appears after reinforcement.
