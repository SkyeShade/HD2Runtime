# LiberatorShotProbe 0.2.0

The live test of per-shot modification (`hd2.projectiles.modify_shots`, docs/projectile-shots.md). The AR-23
Liberator's own shots get a damage multiplier on their own copy; the Liberator Carbine, the Stalwart and every other
weapon firing the same projectile stay vanilla. Development only, solo. Requires HD2Runtime r49 or later.

## How to test

1. Bring the **AR-23 Liberator** (not the Carbine) and start a **solo** mission. Leave sentries and stratagems out.
2. Shoot small unarmoured enemies (Scavengers, Hunters, Automaton troopers) at close range with single taps.
3. **F7** cycles the mode: `VANILLA` (x1) -> `HALF` (x0.5) -> `DOUBLE` (x2). Land about 15 hits per mode.
4. **Ctrl+F7** prints the summary (also printed at the mission's end).

## What the log shows

- `SHOT [mode] #n`: the shot's DamageInfo (vanilla Liberator: 90 standard / 22 durable, penetration 2/2/2/0), its own
  copies before and after the write (damage multiplier 1 -> 0.5 in HALF), its speed, gravity and drag, the distance
  it had travelled when written (0.00 m expected) and the damage EXPECTED at the muzzle.
- `RECORDED [mode]`: the damage the game recorded for the Liberator since its last check (one value per tap).
- `ANY DAMAGE [mode] #n`: the health a victim lost to anything credited to you (sentries, Pelicans and stratagems
  count too: context only).
- `SUMMARY [mode]`: the Liberator's hits as the game counts them, the damage it recorded, the damage per hit and its
  ratio to VANILLA (HALF about 0.5, DOUBLE about 2 on standard damage), and the most common values per check.

## 0.2.0

The first live run (r48, 2026-10-07) averaged every damage credited to the player (an HMG sentry's hits included) and
shot a big Terminid warrior's durable parts. Its per-weapon numbers suggest the multiplier scales the standard damage
(90 -> about 175 at x2) and not the durable damage (about 22 stayed about 22 at x0.5); 0.2.0 measures with the game's
per-weapon stats only.
