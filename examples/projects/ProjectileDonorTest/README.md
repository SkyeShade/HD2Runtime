# ProjectileDonorTest 0.1.0

Live test of the more projectile donors (`docs/attack-outputs.md`, "More donors"): projectiles that only stratagems,
emplacements or another weapon mode fired, swapped into ordinary weapons. Needs HD2Runtime 0.30.0
and the Mod Options Menu. Not live-tested yet.

| Option (Mod Options > Projectile Donor Test) | Default | Swap |
|---|---|---|
| Reprimand fires 500kg bombs | on | SMG-32 Reprimand ← Eagle 500kg Bomb (projectile 239) |
| Stalwart fires precision shells | on | M-105 Stalwart ← Orbital Precision Strike shell (projectile 100) |
| Arbitrator fires HMG rounds | on | AR-11 Arbitrator ← E/MG-101 HMG Emplacement round (projectile 83, same class) |
| APW-1 fires AC-8 flak | off | APW-1 ← AC-8 Autocannon's second projectile (projectile 284) |
| HMG fires orbital gatling rounds | off | MG-206 ← Orbital Gatling Barrage round (projectile 77) |
| Amendment fires the railcannon round | off | R-2 Amendment ← Orbital Railcannon Strike round (projectile 277) |

## What to look for

1. The log names the build: `ProjectileDonorTest 0.1.0 MORE DONORS BUILD`.
2. For each enabled swap: `assets for <id> requested` then `resident`, then `patch <id> APPLIED`.
3. Bring the weapon (or call a fresh one in): it fires the donor. The Reprimand drops 500kg bomb blasts where its
   rounds land, and the Stalwart's rounds make the precision strike's explosion. The weapon keeps its own fire rate,
   magazine and sounds.
4. Whether the projectile is visible in flight (its own model and trail), whether the explosion effects play, and
   whether anything looks or sounds missing (a missing package would show here).
5. With an option turned off, the weapon fires its own projectile again (re-equip after the change).
