# IncendiaryFire

Widens the G-10 Incendiary's explosion (outer radius 7 m to 9 m) and raises the fire it applies per hit from 50 to 80.

The radius is on the grenade's ExplosionSettings row, and the fire amount is status slot 1 of its explosion DamageInfo. These are two records, so the example is a plan. The shared fire status definition (`status.duration`, used by every fire source) is deliberately left unchanged.

Requires allow_unverified_effect because no throwable edit is gameplay-proven. Built only; never deployed or launched.
