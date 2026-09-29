# ExplosiveProjectileSwap

Opt-in guarded validation of an `explosive_impact` selector replacement: the PLAS-1 Scorcher fires the CB-9 Exploding
Crossbow bolt. Both attacks fire their own ProjectileWeapon member (`attack:projectile_source()` reports
`ACTIVE_DIRECT`). Requires HD2Runtime 0.27.0: the Crossbow's package is loaded before the write, so nobody has to
carry the Crossbow. Build with `python build.py`; do not deploy automatically.

The first version replaced the GL-15 Evictor's projectile with the P-33 Missile Pistol's. Runtime no longer writes
that member: the Evictor is rounds-fed and carries its grenade in both ProjectileWeapon +0 and WeaponRounds, so which
one it fires is not proven (`UNPROVEN_PROJECTILE_SOURCE`, see `docs/attack-outputs.md`).
