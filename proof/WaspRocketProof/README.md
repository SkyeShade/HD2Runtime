# WaspRocketProof

Development proof for HD2Runtime 0.30.4. The StA-X3 W.A.S.P. Launcher (and the FAF-14 Spear and P-33 Missile Pistol)
spawns a missile entity per shot. The missile flies by its own SeekingMissile record, now authored as `missile.*` /
`function_missile.*` (docs/support-weapon-api.md "Missiles", research/docs/wasp-rocket-F5FEE03DCFDB.md). Each test is
one toggle in the mod's options page (MODS tab).

Speed, lifetime and turning are read on every missile update, so they change rockets already in flight. The starting
speed applies to the next rocket. Toggles that edit the same field (slow and fast rockets) must not be on together: the
second is refused and logged (CONFLICT).

| Toggle (default) | Change | Expected |
|---|---|---|
| W.A.S.P. slow rockets (on) | preferred speed 100 -> 20, minimum 10 -> 5, starting 10 -> 5 m/s | rockets crawl (about a fifth of normal speed), still home in and explode |
| W.A.S.P. fast rockets (off; turn slow off first) | preferred speed 100 -> 300, acceleration 200 -> 2000 | rockets reach the target almost at once |
| W.A.S.P. rockets end after 1.5 s (off) | max lifetime 30 -> 1.5 s | a rocket fired at a far target ends after about 1.5 s. Report whether it explodes or just disappears |
| W.A.S.P. rockets do not turn (off) | turn rates 15 / 18 -> 0 / 0 | rockets fly straight where they were launched and miss a moving or off-axis target |
| W.A.S.P. guidance after 2 s (off) | guidance delay 0.01 -> 2 s | rockets fly unguided for about 2 s, then turn towards the target |
| W.A.S.P. big blast (off) | the carried row's impact explosion: radii 2.5 / 5 / 7 -> 6 / 12 / 16 | much bigger blasts where rockets hit (proves the missile explodes with projectile 43's row) |
| W.A.S.P. programmable missile slow (off) | function missile preferred 80 -> 20, minimum 10 -> 5 | only after switching the weapon function (ProgrammableAmmo): that missile crawls; the normal one is unchanged |
| Spear slow missile (off) | Spear preferred 100 -> 25, minimum 10 -> 5 | the Spear missile crawls |
| P-33 slow missiles (off) | P-33 preferred 100 -> 20, minimum 10 -> 5 | the P-33 missiles crawl |

Report each: what the rockets did, whether they still locked on, homed and exploded, and the log line of each toggle
(APPLIED, or the error). Also report anything that looked broken (rockets stuck, invisible, exploding at the launcher).

Solo first. Then, if you can, with a friend running the same mod. Then once with the friend not running it: the
friend's screen should show normal-speed rockets, but explosions where yours hit.
