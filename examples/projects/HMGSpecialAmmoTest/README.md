# HMGSpecialAmmoTest

Live test for special ammunition on the MG-206 Heavy Machine Gun, built with the projectile builder
(`weapon:programmable_ammo()`). Uses the MODS tab (page **HMG Special Ammo**).

| Option | Default | What it does |
| --- | --- | --- |
| Special ammunition mode | on | adds a second weapon-function mode that fires status bullets |
| Special ammunition | Incendiary | Incendiary (R-4 Hyena bullet, fire), Stun (AR-32 Pacifier bullet), Gas (P-35 Re-Educator bullet) |
| Mode labels | on | names the modes STANDARD and INCENDIARY / STUN / GAS |

Why donor bullets (research/projectile-builder-F5FEE03DCFDB.json):

- The HMG's right weapon-function input selects its rate of fire; the left one is free, so the ProgrammableAmmo
  function is bound there.
- The HMG's own bullet row is named by 15 typed references across 6 entities (the frv_mg and heavy_mg packages
  among them) and no native row is an unreferenced twin of it. Giving the HMG's own bullet a status would change
  all of them (`allow_shared`), so this test does not do it.
- The mode fires another weapon's ballistic bullet that already applies the status on a direct hit. Same class as the
  HMG bullet, so no cross-class acknowledgement is needed. The flight and damage are the donor's (the Hyena bullet hits
  harder than the Pacifier's).
- No native acid-on-hit bullet is catalogued, so there is no acid option.
- Each donor's label is written on that donor's own row: only that weapon fires it, and it has no weapon-function
  menu. STANDARD is written on the HMG's shared row (`allow_shared`); it changes only a label and icon the other
  entities never show.

## How to test

1. Check the log: `transaction hmg-special-mode APPLIED` and the `hmg-labels-*` transactions.
2. Call in a **fresh** HMG after APPLY.
3. Open the weapon-function menu: **STANDARD** and **INCENDIARY** (plain round icons), next to the rate of fire.
4. INCENDIARY: enemies hit should catch fire. Switch **Special ammunition** to Stun, APPLY, fresh HMG: enemies hit
   should be stunned (mode label STUN, stun icon). Gas: enemies hit should be gassed and confused.
5. STANDARD: the normal HMG bullet, no status.
6. Everything off, APPLY, fresh HMG: vanilla (no mode menu besides the rate of fire).

Report whether each status applied on hit, whether the menu showed the labels and icons, and whether the rate of fire
selector still worked. `allow_unverified_effect` / `allow_unverified_reference` are set: this mode is mapped
offline, not yet shown in game.
