# MaxigunStun

Live test: M-1000 Maxigun bullets apply Stun Medium on hit.

The status is written into the first empty status slot of the Maxigun's bullet DamageInfo row: type Stun Medium,
strength 2. The AR-32 Pacifier and SMG-72 Pummeler apply exactly this status and strength through the same slot of
their own bullet rows. Damage, projectile, fire rate and ammunition are unchanged.

What to verify: fire short bursts at a Hunter, a Berserker or a Devastator. Vanilla, they keep moving and attacking.
With this mod they should freeze in the stun pose for about 3 seconds (Stun Medium's duration) after being hit.
Watch the blue electric stun effect on the target.

Not gameplay-proven until tested. No other mapped weapon uses the Maxigun's bullet DamageInfo row; the operation
still passes allow_shared because settings rows are global definitions. Built only.
