# ProjectileActionTest

Live test for `hd2.projectiles.spawn` (`docs/event-scripting.md`): **F6 fires one R-36 Eruptor shell from above your
head.**

## How it works

- `hd2.projectiles.spawn('R-36 Eruptor', {position = p, direction = d})` calls the game's own projectile function
  (game.dll `FireProjectile`, 0x13A8F50). It passes the template of the game's own AI fire helper (0x119E612): a
  plain projectile, no target. The research is in `research/event-actions-F5FEE03DCFDB.json`.
- Runtime re-proves the function's exact bytes, requires the game's projectile system to be active (a mission),
  checks that the projectile type's settings record carries that type (the game's own lookup has no bounds check),
  normalises the direction and loads the Eruptor's package first.
- Your avatar is the source and owner. Each projectile counts as a shot in your mission stats.
- Host only. At most 12 projectiles at once and 4 per second per mod.

## How to test

1. Host a mission. The log shows `mission started: R-36 Eruptor projectile assets ready` (or `waiting_for_assets`).
2. Press F6. The log shows `F6: R-36 Eruptor projectile from (x, y, z) along +X: requested`.
3. In game, a shell leaves from about 2.5 m above your head, flies horizontally and explodes where it lands.

Please report:

- whether the shell appeared, flew and exploded like an Eruptor shot, with its sound and trail;
- whether it damaged or killed enemies, and whether those kills count as yours (`player_kill_credited`);
- as a client: the log should read `refused HOST_ONLY`;
- whether other players saw it (unproven: no network send was found).
