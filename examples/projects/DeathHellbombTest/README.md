# DeathHellbombTest

Integration test for death events and the explosion action (`docs/event-scripting.md`): **when the local player dies,
a Hellbomb detonates at the death position.**

## The Hellbomb explosion

`hd2.explosions.spawn('Hellbomb', {position = ...})` requests the NUX-223 Hellbomb's own detonation, ExplosionType 242
(`research/event-actions-F5FEE03DCFDB.json`). The Hellbomb names no explosion type in its data, so the identity comes
from code:

- The Hellbomb entity (`content/fac_helldivers/hellpod/hellbomb/hellbomb`, the payload of the Hellbomb stratagem) is
  the only entity with BehaviorId 224.
- That behavior's "explode" event requests ExplosionType 242 as a code literal (game.dll `0x288817 mov edx, 0xF2`).
  Two wrappers pass it unchanged to the game's explosion request.
- Runtime re-proves those instructions in game.dll at startup, together with every other event pin, and checks that
  the settings record for type 242 carries that type.

The explosion's effects come with the Hellbomb stratagem's package (`packages/generated/loadout/hellbomb`). When a
mission starts, this test loads that package (`hd2.explosions.prepare('Hellbomb')`), so the detonation needs no
wait.

Type 242 is also used by some mission objectives. Requesting it changes nothing about them; only editing its
settings would.

## What this test proves

- `player_died` for the local player, with a read-only **death-position snapshot** and how it was observed.
- The Hellbomb detonation at that position: its assets are loaded at mission start, then the explosion is requested
  (host only).
- The snapshot is plain data: 3 s later (after the avatar may be destroyed) it still reads the same.
- The host flag (`hd2.game_state().host`).
- The recursion guard: a death caused by a mod's action is not reacted to.

## How to test

1. Host a mission. The log shows `mission started: Hellbomb explosion assets ready` (or `waiting_for_assets`, then
   nothing more is needed).
2. Die: stand still, or throw a grenade at your feet.
3. The log shows `local player died at (x, y, z) (observed dead_state|avatar_removed); host true`, then
   `Hellbomb detonation at (x, y, z): requested`.
4. In game, a full Hellbomb explosion (fireball, shockwave, sound) goes off where you died and damages enemies in its
   17 / 25 / 45 m radii.
5. 3 s later the log shows `the death snapshot still reads (x, y, z)`.

Please report:

- whether the explosion appeared, looked and sounded like a Hellbomb, and was centred on the death position;
- whether enemies nearby died;
- whether the Hellbomb's sound and visuals played in full (missing effects would mean missing assets);
- as a client (not host): the log should read `refused HOST_ONLY`.
