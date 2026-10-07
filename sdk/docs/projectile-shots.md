# Per-shot modification (development)

`hd2.projectiles.modify_shots` changes the stats of the local player's own shots of one weapon, each shot on its own
copy. The weapon keeps firing its own vanilla projectile: the game's aim, spread, fire rate, recoil and networking are
untouched. Everything that shares the projectile stays vanilla: the projectile row, its DamageInfo row and every other
weapon that fires the same projectile type (the AR-23A Liberator Carbine and the M-105 Stalwart fire the AR-23
Liberator's 276).

```lua
local shots = hd2.projectiles.modify_shots('AR-23 Liberator', {damage = 0.5, gravity = 0.25,
    on_shot = function(e) hd2.mod():log(('shot %d: damage x%g'):format(e.slot, e.after.damage_multiplier)) end})
shots:set({damage = 2})   -- the next shots
shots:stop()
```

**Status: development, solo, not live-tested.** The live test is `proof/LiberatorShotProbe`.

## Options

Every option is a multiplier of the shot's own copy (the value it spawned with, times the option):

| Option | The shot's own member | Range | Notes |
| --- | --- | --- | --- |
| `damage` | hit record +0x34, the damage multiplier (1.0 at spawn) | 0.01..100 | Each direct hit's damage. Explosions are a separate path and are not scaled. |
| `armor_penetration` | hit record +0x38, the penetration multiplier | 0.1..10 | Each direct hit's four penetration lanes, rounded by the game. |
| `speed` | flight record +0x0C velocity and +0x2C reference speed | 0.1..10 | Both together: the game ends a shot below 0.1 x its reference speed and scales a direct hit by 0.25 + 0.75 (speed / reference)^2, so the damage factor stays the game's. |
| `gravity` | flight record +0x1C | 0..20 | 0: no drop. |
| `drag` | flight record +0x28, the drag constant | 0..20 | 0: no slowdown. |

`opts.on_shot(event)` is called for every shot of the weapon this player fires: `event.kind` is `modified` or
`untouched` (every multiplier 1); `event.before` and `event.after` hold the shot's `damage_multiplier`,
`penetration_multiplier`, `speed`, `reference_speed`, `gravity`, `drag`, `distance` (travelled when written) and
`damage = {id, standard, durable, armor_penetration}` (its direct hit's DamageInfo, read only).

A mod's second call for the same weapon replaces its first; another mod's is refused (`ALREADY_MODIFIED`).
`hd2.projectiles.modify_shots_status()` lists every active configuration.

## How it works

SpawnProjectile copies the row's stats into the shot's own pool records, and the projectile update, the ballistic
integrator and hit processing read those copies, never the row again (`research/projectile-ballistics-F5FEE03DCFDB.json`,
`scripts/research_projectile_ballistics.py`: 178 instruction pins identical in every retained snapshot). Each Runtime
update reads the projectiles spawned since its last look and, for each of this player's shots of the weapon (its
projectile type, fired by the weapon's entity type, credited to the local peer, in flight, not driven by a unit), writes
its members once in one guarded transaction over its records, with a read-back. The damage multiplier is applied at
0x13AD524 (`mulss xmm0, [hit+0x34]`) to the direct hit's damage event before the damage values are built.

## Live evidence

- **r48, 2026-10-07 (solo, LiberatorShotProbe 0.1.0):** every shot was written before it moved (0.00 m travelled;
  133 modified, 45 untouched in VANILLA, read back true). The game's per-weapon damage per tap was about 24 (x1),
  about 22 (x0.5) and about 147-175 (x2; 2 x 90 x the speed factor) on mixed targets, mostly a big Terminid warrior's
  durable parts. This suggests `damage` scales the **standard** damage only, not the **durable** damage (the warrior's
  durable parts take the DamageInfo's 22 either way). Under research; LiberatorShotProbe 0.2.0 re-measures on
  unarmoured targets with the per-weapon stats only.

## Limits

- **Solo only.** With several players every machine simulates its own copy of a shot, and which copy decides the
  damage is not established: shots stay vanilla (`NOT_SOLO`).
- **Not live-tested:** the write's effect in game, any clamp further down the damage path (one damage-kind builder is
  not traced), the timing (a Lua update runs before the game update that steps projectiles; the distance travelled at
  the write is reported).
- Direct hits only for `damage` / `armor_penetration`; a weapon's explosions are changed through the impact explosion
  instead. Visual effects, the model, the pellet count and the lifetime variance are fixed at spawn.
