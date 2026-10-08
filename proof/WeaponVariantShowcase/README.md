# WeaponVariantShowcase 0.1.0

The live test of weapon **variants** beyond the M-1000 Maxigun (`delivery={family='weapon'}`,
docs/custom-stratagem-api.md). A variant converts a support weapon's **own type** for one mission: its name and icon,
and, for a weapon that fires projectiles, its round. Development only. Test solo, as host, first.

| Custom stratagem | Code | Weapon | What changes |
| --- | --- | --- | --- |
| AC-8N NAPALM AUTOCANNON | ← ↑ ↓ → ← ↑ | AC-8 Autocannon | fires the EAT-700's napalm round |
| GR-8L LEVELLER RECOILLESS | → ↓ ↑ ← → ↓ | GR-8 Recoilless Rifle | fires the EAT-411 Leveller's round |
| MG-206X ANTI-MATERIEL HMG | ↑ ← ↓ → ↑ ← | MG-206 Heavy Machine Gun | fires the APW-1 Anti-Materiel Rifle's round |
| LAS-98S RENAMED LASER CANNON | ↓ → ↑ ← ↓ → | LAS-98 Laser Cannon | name and icon only (a beam: no round); a shared type |

## How to test

1. Install the r56 runtime and this mod. Do **not** bring the vanilla AC-8, GR-8, MG-206 or LAS-98: while one is
   picked natively, its variant is unavailable. While a variant is selected, its vanilla weapon is blocked in the
   native picker.
2. In the custom panel, select the variants (up to four slots).
3. Start a solo mission and call each one with its code. Its own beacon and pod bring the weapon (the AC-8 and the
   GR-8 with their backpacks).
4. Pick each up and fire it:
   - the pickup prompt, the map label and the weapon panel show the custom name;
   - the AC-8N's shells burst into napalm fire;
   - the GR-8L's rockets have the Leveller's much larger blast;
   - the MG-206X hits with anti-materiel rounds.
5. Back aboard the ship everything is restored. A vanilla AC-8 in a later mission is a normal AC-8.

## What to report

For each variant:
- whether the name showed (prompt, panel, map);
- whether the round changed (or, for the LAS-98S, that the beam stayed the same);
- anything odd: reload, backpack, crashes.

Also send the log (`DELIVERED ...`, `weapon clone APPLIED ... VARIANT ...`, `RESTORED`).

## Known limits

- **Shared type.** World loot also brings the LAS-98. A Laser Cannon you find is renamed too, and if one already lies
  in the world when the mission starts, the conversion is refused (`CARRIER_PRESENT`). The log says so, and the
  weapon stays vanilla.
- **The icon** is the Laser Maxigun's test image for all four.
- **Not tried with several players.**
