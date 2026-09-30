# VehicleProjectileBuilderTest

Live test for mounted weapons in the one projectile system. Uses the MODS tab (page **Vehicle Projectile Builder**).

The EXO-45 Patriot Exosuit's minigun is a projectile host by the same rule as player and support weapons:
- it is magazine-fed;
- every shot is its own ProjectileWeapon +0;
- that record belongs to the Patriot alone.

| Option | Default | What it does |
| --- | --- | --- |
| Patriot minigun projectile | Vanilla | EAT-17 rocket, LAS-58 Talon bolt, PLAS-1 Scorcher plasma, or a status bullet: Incendiary (R-4 Hyena, fire), Stun (AR-32 Pacifier), Gas (P-35 Re-Educator) |
| Minigun impact effect | None | an explosion where the minigun's own bullet hits: Grenade blast (GL-21), Gas cloud (Speargun), EMS field (EMS Mortar), Napalm (EAT-700) |

- **One projectile at a time.** The projectile choice is one field: the minigun fires exactly one projectile.
- **The impact effect is shared.** The minigun bullet row is fired by 10 entities (39 references), among them the
  Gatling and machine-gun sentries (packages `gatling_turret`, `turret_machinegun_gpmg`) and the `machinegun`
  package. The effect therefore needs `allow_shared` and changes them too. It shows while the minigun fires its own
  bullet (projectile **Vanilla**); a donor projectile keeps its own effects.
- **Packages.** Runtime loads each donor's package before writing.
- **Fresh Exosuit.** The projectile is copied into the Patriot when it is built: call in a **fresh** Exosuit after
  APPLY. The impact effect is on the bullet row, read when a bullet hits.
- **Not live-tested.** `allow_unverified_effect` / `allow_unverified_reference` are set.

## How to test

1. Check the log: `ensure patriot-minigun-projectile` and `patriot-minigun-impact` (Vanilla / None write nothing).
2. **Projectile**:
   1. Pick **EAT-17**, APPLY, and call in a fresh Patriot.
   2. Every minigun shot should be an EAT-17 rocket.
   3. Try **Talon**, **Scorcher**, then **Incendiary**, **Stun** and **Gas**. Enemies hit should burn, be stunned or
      be gassed.
3. **Impact effect**:
   1. Set the projectile back to **Vanilla**.
   2. Pick **Grenade blast**, APPLY. No fresh Exosuit is needed for the effect, but try one if nothing changes.
   3. Each bullet should explode where it hits.
   4. Try **Gas cloud**, **EMS field** and **Napalm**. Stay away from the fields: they affect you too.
4. For each choice, confirm:
   - the projectile or effect visibly changed;
   - the explosion or status happens per hit;
   - the fire rate is unchanged;
   - ammo consumption is unchanged;
   - the Exosuit still moves, aims and fires normally;
   - the Exosuit does not crash or desync during sustained fire.
5. With an impact effect on, call in a Gatling or Machine Gun Sentry: its bullets should show the same effect (the
   shared row). Other weapons should not change.
6. Everything back to Vanilla / None, APPLY, fresh Exosuit: vanilla.

Report which choices worked, anything that crashed or desynced, and whether the sentries showed the impact effect.
