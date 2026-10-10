# TeamReloadAmmoProof

Development proof for HD2Runtime 0.31.0 (0.2.0, built for rc2; log banner `0.2.0 AC-8 OWN ROUNDS`): team-reload
weapons carrying spares of their own (the AC-8's own rounds included), and bigger team-reload backpacks (docs/support-weapon-api.md "Team-reload weapons", docs/backpack-ammo.md "Team-reload backpacks"). The game
code (research/team-reload-ammo-F5FEE03DCFDB.json) uses the weapon's own spares first and the worn backpack only once
they are spent; a teammate's reload always uses a backpack. Each test is one toggle in the mod's options page (MODS
tab). Call a new weapon in after a change: the counts are set when the weapon and backpack spawn.

| Toggle (default) | Change | Expected |
|---|---|---|
| GR-8 carries 3 spare rockets of its own (on) | GR-8 own spares: maximum 0 -> 3, start 0 -> 3, from supply 6 -> 3 | Without picking up the backpack: fire, reload alone 3 times (4 shots), then no reload. With the backpack: the first 3 reloads leave the backpack full, then it counts down |
| AC-8 carries 20 rounds of its own (on) | AC-8 own rounds: maximum 0 -> 20, start 0 -> 20, from supply 0 -> 20 | Without the backpack: empty the 10-round magazine, then reload alone 4 times (5-round clips: 30 shots in all), then no reload. With the backpack: the first 4 reloads leave it full (10 clips), then it counts down. A resupply restores the 20 |
| AC-8 carries 23 rounds of its own (off; turn the one above off) | the same with 23 | 4 clips of 5, then one more full clip of 5 from the last 3 rounds (the count ends at 0; the game clamps it), then the backpack. A resupply refills to 25 (the game rounds the maximum up to whole clips). Report whether the HUD ever shows a negative or odd count |
| Recoilless backpack holds 12 (on) | GR-8 backpack capacity 5 -> 12 (start stays -1 = full) | the backpack starts with 12 rockets; with the toggle above, 1 + 3 + 12 = 16 shots |
| AC-8 backpack holds 20 magazines (on) | AC-8 backpack capacity 10 -> 20, supply 5 -> 10 | 20 reloads (5-round clips) from the backpack; a resupply adds 10 |
| Recoilless backpack starts with 2 (off) | GR-8 backpack start -1 (full) -> 2 | a new GR-8 backpack holds 2 (of 12 with the toggle above, else of 5) |
| W.A.S.P. carries 2 magazines of its own (off) | StA-X3 own spares: maximum 0 -> 2, start 0 -> 2 | 2 reloads of 7 rockets without the backpack |
| Spear backpack holds 8 (off) | FAF-14 backpack capacity 4 -> 8 | the Spear backpack starts with 8 missiles |

Report each: the shot and reload counts, what the HUD showed for spares (the HUD readout of a weapon's own spares is not
traced), what a resupply added (the GR-8 should regain up to 3 own spares and its backpack 3 rockets), and whether
anything looked broken. The backpack shows at most its 5 rocket models; above that all stay visible.

Solo first. Then, if you can, with a friend: one of you reloads the other (a team reload uses the backpack, never the
weapon's own spares), and once with the friend not running the mod (the counts must match on both screens).
