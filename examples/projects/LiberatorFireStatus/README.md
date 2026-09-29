# LiberatorFireStatus

Live test: AR-23 Liberator bullets set targets on fire (Fire, strength 2, the AR-2 Coyote value). Magazine, fire modes,
projectile and direct damage are unchanged. The bullet row is shared with the AR-23A Liberator Carbine and the StA-52
Assault Rifle, so they burn targets too.

**Result: live-proven (2026-09-29).** Liberator bullets set enemies on fire while the ballistic attack otherwise
behaves normally. Status references on player and support weapon projectile (direct-hit) rows no longer need
`allow_unverified_effect`.

What to verify: shoot Scavengers or Troopers and watch them catch fire after a few hits.
