# LiberatorFireStatus

Live test: AR-23 Liberator bullets set targets on fire.

The status is written into the first empty status slot of the Liberator's bullet DamageInfo row: type Fire,
strength 2. The AR-2 Coyote applies exactly this through the same slot of its own bullet row. Magazine, fire modes,
projectile and direct damage are unchanged.

What to verify: shoot Scavengers or Troopers. Vanilla, nothing burns. With this mod, targets should catch fire
(flames on the body and burn damage ticking for about 3 seconds, Fire's duration) after a few hits.

Not gameplay-proven until tested. The same bullet DamageInfo row is also used by the AR-23A Liberator Carbine and
the StA-52 Assault Rifle, so they set targets on fire too (allow_shared). Built only.
