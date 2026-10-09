# BeamSwapProof

Development proof for HD2Runtime 0.30.4 beam swaps (docs/attack-outputs.md "Beam swaps" and "Lasers everywhere";
research/beam-outputs-F5FEE03DCFDB.json). A beam weapon's BeamType reference, on its active beam source, takes another
weapon's beam: its BeamSettings row (length, damage, hit effects and visuals). The host keeps its own fire mode, rate,
heat and sounds. Each test is one toggle in the mod's options page (MODS tab); re-equip the weapon, resupply or call a
new one in after a change (the beam is copied into a weapon when it is built).

| Toggle (default) | Change | Expected |
|---|---|---|
| Scythe fires the Trident beam (on) | LAS-5 Scythe, its default muzzle (Laser. Standard Prism) beam: BeamType 8 -> 6 | a continuous Scythe beam that reaches only 200 m and looks / hits like the Trident's |
| LAS-98 fires the Meltagun beam (on) | LAS-98 Laser Cannon BeamWeapon +0: 1 -> 18 | a 15 m melta beam from the LAS-98 (still the LAS-98's heat and continuous fire) |
| Laser Sentry fires the Trident beam (on) | A/LAS-98 Laser Sentry BeamWeapon +0: 10 -> 6 | the sentry's beam reaches only 200 m and looks like the Trident's |
| Liberator fires Talon laser bolts (on) | AR-23 Liberator default ammunition: its bullet -> the LAS-58 Talon bolt | laser BOLTS (a projectile swap); the control that a projectile weapon fires laser projectiles, never a beam |
| Dagger fires the LAS-98 beam (off) | LAS-7 Dagger BeamWeapon +0: 11 -> 1 | the Dagger fires the LAS-98's beam (its damage and look) |
| Trident fires the Scythe beam (off) | LAS-13 Trident BeamWeapon +0: 6 -> 8 | the Trident's pulses use the Scythe's beam row (1000 m, Scythe damage) |

Also note, with the first toggle on, an **AX/LAS-5 Rover**: its drone gun defaults to the same muzzle, so if its beam
also changes (shorter, Trident-like), the game applies default muzzles to drone weapons too (Runtime lists the Rover's
beam source as unproven until this is seen). If it does not change, say so.

Report each: what you saw, whether anything looked broken, and the log lines (`... -> APPLIED`). Solo first; then, if
you can, a friend in the lobby with and without the mod (what the beam looks like on their screen).

Credit: the laser research these tests check started from [Bans](https://ayakamods.com/members/bans.388863/)'s [True Lasgun Beam Overhaul](https://ayakamods.com/mods/true-lasgun-beam-overhaul.4681/).
