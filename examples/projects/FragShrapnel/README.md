# FragShrapnel

Raises the G-6 Frag's shrapnel pieces per detonation from 35 to 45 and its starting count from 4 to 6.

The shrapnel count is `+80` of the frag's ExplosionSettings row, reached from the grenade's ExplosiveComponent. The row is a shared settings definition, so the write needs `allow_shared`. The shrapnel projectile itself (`frag:shrapnel()`) is shared by 11 native entities, including the TM-1 Lure Mine, and is left unchanged. The starting count is the grenade's own ThrowableComponent.

Requires allow_unverified_effect because no throwable edit is gameplay-proven. Built only; never deployed or launched.
