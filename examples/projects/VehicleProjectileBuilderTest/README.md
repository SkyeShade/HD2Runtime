# VehicleProjectileBuilderTest

Live test for mounted weapons in the one projectile system. Uses the MODS tab (page **Vehicle Projectile Builder**).

The EXO-45 Patriot Exosuit's minigun is a projectile host by the same rule as player and support weapons:
- it is magazine-fed;
- every shot is its own ProjectileWeapon +0;
- that record belongs to the Patriot alone.

| Option | Default | What it does |
| --- | --- | --- |
| Patriot minigun projectile | Vanilla | EAT-17 rocket, LAS-58 Talon bolt, PLAS-1 Scorcher plasma, or a status bullet: Incendiary (R-4 Hyena, fire), Stun (AR-32 Pacifier), Gas (P-35 Re-Educator) |
| Own-bullet impact effect | None | an explosion where the minigun's **own** bullet hits: Grenade blast (GL-21), Gas cloud (Speargun), EMS field (EMS Mortar), Napalm (EAT-700) |
| Talon bolt impact (donor row) | off | a GL-21 grenade blast on the LAS-58 Talon bolt row: the minigun while it fires Talon, and the Talon sidearm |

- **One projectile at a time.** The projectile choice is one field: the minigun fires exactly one projectile.
- **The own-bullet effect is shared.** The minigun bullet row is fired by 10 entities (39 references), among them the
  Gatling and machine-gun sentries (packages `gatling_turret`, `turret_machinegun_gpmg`) and the `machinegun`
  package. The effect therefore needs `allow_shared` and changes them too.
- **Packages.** Runtime loads each donor's package before writing.
- **Fresh Exosuit.** The projectile is copied into the Patriot when it is built: call in a **fresh** Exosuit after
  APPLY. An impact effect is on a bullet row, read when a bullet hits.

## A swap and a slot are separate operations

The projectile choice and the impact effect write different things:
- **The swap** changes which projectile row the minigun fires. It re-points the Patriot's own ProjectileWeapon +0
  (row 148) to the donor's row: EAT-17 row 132, Talon row 144, Scorcher row 142.
- **The impact effect** edits one row's impact explosion: the Patriot bullet row, 148.

They do not compose automatically. With a donor selected, the minigun fires the donor's row, which has its own
effects, and the row 148 edit no longer reaches the minigun. The sentries still fire row 148 and still show it.
Runtime logs a `note:` line when a slot write applies while its row's owner fires another projectile.

To give a swapped projectile an effect, edit the **donor's** row explicitly: **Talon bolt impact** targets
`hd2.attack_output('LAS-58 Talon')`. That changes every entity firing the Talon row: the Talon sidearm, and the
minigun while it fires Talon. An effect on the minigun's swapped projectile alone would need a row of its own. The
Runtime-owned projectile registry would provide that, and 0.28 does not have it.

## How to test

1. Check the log: `ensure patriot-minigun-projectile` and `patriot-minigun-impact` (Vanilla / None write nothing).
2. **Projectile**:
   1. Pick **EAT-17**, APPLY, and call in a fresh Patriot.
   2. Every minigun shot should be an EAT-17 rocket.
   3. Try **Talon**, **Scorcher**, then **Incendiary**, **Stun** and **Gas**. Enemies hit should burn, be stunned or
      be gassed.
3. **Own-bullet impact effect**:
   1. Set the projectile back to **Vanilla**.
   2. Pick **Grenade blast**, APPLY. No fresh Exosuit is needed for the effect, but try one if nothing changes.
   3. Each bullet should explode where it hits.
   4. Try **Gas cloud**, **EMS field** and **Napalm**. Stay away from the fields: they affect you too.
4. **Talon bolt impact** (the donor-row composition):
   1. Projectile **Talon**, own-bullet effect **None**, **Talon bolt impact** on, APPLY, and call in a fresh Patriot.
   2. Each minigun Talon bolt should explode like a GL-21 grenade where it hits.
   3. Equip the LAS-58 Talon sidearm: its bolts should explode too (the same row).
   4. With projectile **Vanilla** the minigun bullets should not explode (row 148 is unchanged).
5. For each choice, confirm:
   - the projectile or effect visibly changed;
   - the explosion or status happens per hit;
   - the fire rate is unchanged;
   - ammo consumption is unchanged;
   - the Exosuit still moves, aims and fires normally;
   - the Exosuit does not crash or desync during sustained fire.
6. With an own-bullet effect on, call in a Gatling or Machine Gun Sentry: its bullets should show the same effect (the
   shared row). Other weapons should not change.
7. Everything back to Vanilla / None / off, APPLY, fresh Exosuit: vanilla.

Report:
- which choices worked;
- anything that crashed or desynced;
- whether the sentries showed the own-bullet effect;
- whether the Talon bolt impact reached the minigun and the sidearm.

## Live result (2026-09-30)

**PASS for mounted projectile swapping.**
- **Swaps.** EAT-17, Talon and Scorcher worked on the minigun, and the vanilla projectile path worked.
- **Stability.** The Exosuit stayed functional and nothing crashed.
- **Own-bullet effect.** It worked while the minigun fired its own bullet and did not follow a donor projectile, as
  described above.

**Live-proven** (`vehicle_projectile_reference`, `projectile_slot_composition`):
- the three swaps (Patriot minigun ← EAT-17, Talon, Scorcher);
- the four own-bullet impact explosions on row 148, and back to none.

**Follow-up (2026-09-30): PASS.** With the projectile on **Talon** and **Talon bolt impact** on, the minigun's Talon
bolts exploded like GL-21 grenades. The explicit donor-row composition (`donor_row_slot_composition`) is live-proven
for exactly this tuple: the Talon row with the GL-21 impact explosion.

**Still unproven, and acknowledged in the mod:**
- the status bullets;
- the sentries;
- the Talon sidearm firing the edited row (not reported);
- every other donor row, effect, mount or donor.
