# StatusActionTest

Live test for `hd2.status.apply` (`docs/event-scripting.md`): **every enemy you damage catches fire.**

## How it works

- `hd2.status.apply(event.entity, 'fire', {buildup = 100})` appends one request to the game's own status request
  queue (game.dll `QueueStatusRequest`, 0x129F170). The game's own stun callers use the same queue with the same
  template (variant 0, an entity instigator, 100.0).
- The game drains the queue every frame. It checks that the target has a status instance and can have that status,
  then applies it here if this machine owns the target, or sends it to the owner.
- The amount is **buildup**, not strength: the status starts when the enemy's buildup reaches its susceptibility.
  Strength and duration are the game's own. Applying again refreshes the duration; it does not stack.
- Only statuses that a player weapon already applies through its damage are offered (`hd2.status.list()`): fire,
  fire panic, heavy burning, three stuns, four gases, and flamer slow.
- Host only. At most one request per enemy every 3 s in this test; Runtime also limits 10 at once and 5 per second
  per mod, and 4 at once per target.
- Not proven: that the status's visual effects are always loaded. The same statuses are applied by enemies and
  environments whatever the players carry (inference). Report any missing flames.

## How to test

1. Host a mission. Shoot an enemy with a weapon that does not set fire (for example the AR-23 Liberator).
2. The log shows `fire on enemy/v1/... (id): requested`.
3. In game, the enemy catches fire (flames, burn damage over time).

Please report whether enemies burned, whether fire-immune enemies stayed unaffected, and whether the flames looked
normal.
