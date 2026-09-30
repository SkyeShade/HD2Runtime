# UnifiedProjectileSwapTest

Live test for the unified projectile donor pool. Uses the MODS tab (page **Unified Projectile Swap**).

A projectile host is any weapon whose fired projectile Runtime can write (`weapon:projectile_source().writable`). That
is its own ProjectileWeapon +0 for primaries, secondaries and (new) magazine-fed support weapons, or its default
ammunition for the Liberator. A donor is any catalogued projectile output (`hd2.attack_output(name)`) or another
weapon's attack projectile handle, whatever loadout slot it comes from. Beam, arc, spray and melee outputs are refused.

| Option | Default | Host <- donor | Class | Acknowledgements |
| --- | --- | --- | --- | --- |
| EAT-17 fires Scorcher plasma | on | support EAT-17 <- primary PLAS-1 Scorcher | same (explosive impact) | allow_unverified_effect (support host path not yet live-proven) |
| Reprimand fires EAT-700 napalm | on | primary SMG-32 Reprimand <- support EAT-700 | cross | allow_unverified_effect, allow_unverified_reference |
| Liberator fires Talon lasers | on | Liberator ammunition <- LAS-58 Talon | same | allow_shared (live-proven path) |
| Stalwart fires AMR rounds | off | support M-105 Stalwart <- support APW-1 | same (plain) | allow_unverified_effect |

Support component hosts: APW-1, EAT-17, EAT-411, EAT-700, GL-21, M-105 Stalwart, MG-206 HMG and S-11 Speargun.
They follow the same rule as player hosts: magazine-fed, and every shot is their own ProjectileWeapon +0. The other
support weapons are read-only, and `projectile_source()` gives the reason:

- another selector owns the projectile (AC-8, GL-52, FAF-14, MG-43 and more);
- the weapon is not magazine-fed (GL-28, Quasar, Maxigun, Railgun);
- a weapon function switches the projectile (GR-8, RL-77).

## How to test

1. Check the log: `transaction eat-scorcher APPLIED`, `reprimand-napalm APPLIED`, `liberator-talon APPLIED`, each
   after `assets ... resident`.
2. Call in a **fresh** EAT-17 and re-equip the Reprimand and the Liberator after APPLY.
3. EAT-17: fires the blue Scorcher plasma bolt (small explosion) instead of the rocket.
4. Reprimand: fires EAT-700 napalm rockets.
5. Liberator: fires Talon laser bolts.
6. Turn **Stalwart fires AMR rounds** on, APPLY, fresh Stalwart: its bullets should hit like the AMR (much higher
   damage and penetration per round).
7. Everything off, APPLY, fresh weapons: vanilla.

Report, per host, whether the fired projectile changed (or not) and whether the weapon still fired and reloaded
normally.

**Live result (2026-09-30): PASS** for all four:
- EAT-17 ← Scorcher and Stalwart ← APW-1 (`support_projectile_reference`);
- Reprimand ← EAT-700 (`attack_output_cross_class`);
- Liberator ← Talon.

Only these exact pairs are promoted; other support hosts and donors keep their acknowledgements.
