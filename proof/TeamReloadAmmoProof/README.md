# TeamReloadAmmoProof

Development proof for HD2Runtime 0.30.4: team-reload weapons carrying spares of their own, and bigger team-reload
backpacks (docs/support-weapon-api.md "Team-reload weapons", docs/backpack-ammo.md "Team-reload backpacks"). The game
code (research/team-reload-ammo-F5FEE03DCFDB.json) uses the weapon's own spares first and the worn backpack only once
they are spent; a teammate's reload always uses a backpack. Each test is one toggle in the mod's options page (MODS
tab). Call a new weapon in after a change: the counts are set when the weapon and backpack spawn.

| Toggle (default) | Change | Expected |
|---|---|---|
| GR-8 carries 3 spare rockets of its own (on) | GR-8 own spares: maximum 0 -> 3, start 0 -> 3, from supply 6 -> 3 | Without picking up the backpack: fire, reload alone 3 times (4 shots), then no reload. With the backpack: the first 3 reloads leave the backpack full, then it counts down |
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
