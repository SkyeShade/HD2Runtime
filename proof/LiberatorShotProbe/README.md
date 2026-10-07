# LiberatorShotProbe 0.1.0

The live test of per-shot modification (`hd2.projectiles.modify_shots`, docs/projectile-shots.md). The AR-23
Liberator's own shots get a damage multiplier on their own copy; the Liberator Carbine, the Stalwart and every other
weapon firing the same projectile stay vanilla. Development only, solo. Requires HD2Runtime r48 or later.

## How to test

1. Bring the **AR-23 Liberator** (not the Carbine) and start a **solo** mission.
2. Find one unarmoured enemy type (a Terminid scavenger or an Automaton trooper) and shoot its body at close range
   with single taps.
3. **F7** cycles the mode: `VANILLA` (x1) -> `HALF` (x0.5) -> `DOUBLE` (x2). Land about 10 hits per mode on the same
   enemy type and body part.
4. **Ctrl+F7** prints the summary (also printed at the mission's end).

## What the log shows

- `SHOT [mode] #n`: the shot's DamageInfo (vanilla Liberator: 90 standard / 22 durable, penetration 2/2/2/0), its own
  copies before and after the write (damage multiplier 1 -> 0.5 in HALF), its speed, gravity and drag, the distance
  it had travelled when written (0.00 m expected) and the damage EXPECTED at the muzzle.
- `HIT [mode] #n`: the health a victim lost to you.
- `RECORDED [mode]`: the damage the game recorded for the Liberator.
- `SUMMARY [mode]`: hits, mean damage per hit and its ratio to VANILLA (HALF should read about 0.5, DOUBLE about 2).

The first modified shot also logs a Runtime line: `shots (LiberatorShotProbe): first AR-23 Liberator shot modified`.
Weak spots, armour and range change the absolute numbers; the ratio between modes on the same target is the test.
