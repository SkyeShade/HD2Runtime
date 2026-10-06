# Enemy spawn weights

`hd2.enemies.spawn_weight(enemy, multiplier, opts)` changes how often an enemy type is picked when the game spawns
enemies: more Hive Guards among the warriors, no Bile Titans, no Watchers.

```lua
local guards = hd2.enemies.spawn_weight('Hive Guard', 5, {allow_unverified_effect = true})
local no_titans = hd2.enemies.spawn_weight('Bile Titan', 0, {allow_unverified_effect = true})
-- later
no_titans:stop()   -- the vanilla weights again
```

Status: **offline-proven, not live-tested** (0.30.0-dev). Every call needs `allow_unverified_effect = true` until the
live test (`examples/projects/EnemySpawnMixTest`) passes.

## What it changes, and what it does not

The game keeps one enemy **roster** per faction (Terminids 45 rows, Illuminate 46, Automatons 61) in game.dll. Each
row is one enemy type in one **spawn group**, with ten **weights**, one per difficulty (1..10).

When a spawn needs an enemy from a group, the game's own pick (`PickEnemy`, 0x953150, used by all 14 spawn call sites)
does the following:
1. It keeps that group's rows whose subfaction is active.
2. It drops the rows whose weight at the mission's difficulty is 0.
3. It picks one of the rest with probability **weight / sum of the group's weights**.

A multiplier writes, in every row of that enemy type, each weight as its vanilla value × the multiplier:

- **× 0**: the type is never picked. A group made only of that type (the Bile Titan's, the Watcher's) then produces
  nothing; a group of several types (both Hunter tiers share one) needs each of them at 0.
- **× k > 1**: the type is picked more often *within the groups it shares* with other types. For example, Hive Guards
  with ×5 replace more of the warriors in the warrior groups. In a group where it is the only type, it is already
  picked every time, so nothing changes.
- **0 < k < 1**: the type is picked less often within its shared groups.
- **A type whose vanilla weight is 0 at a difficulty stays 0 there.** At difficulty 10 the tier-1 Charger's weight is
  0 (the game uses `charger_tier2` instead). `hd2.enemies.spawn_list({enemy = ...})` shows every row's ten weights.

It changes **which** enemy types spawn, not **how many** enemies a spawn makes. Counts come from the spawn systems'
own templates (each template entry is a group and a count) and from their budgets; those are not written. More of a
type means the others in its groups get less.

The pick model on the retained Terminid mission snapshot (`validation/enemy-spawn-weights-snapshot.json`):

| Charger ×2 | Difficulty 1–6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|
| Its share of its group, vanilla | 1.00 (alone) | 0.50 | 0.33 | 0.23 | 0 |
| With ×2 | 1.00 | 0.67 | 0.50 | 0.38 | 0 |

## Naming an enemy

- **Names:** a display name (`'Charger'`, `'Bile Titan'`, `'Hive Guard'`), a native name (`'warrior_tier_1'`,
  `'charger_tier2'`, `'berserker'`), a catalogue id (`'enemy/v1/terminids/charger'`) or the 16-hex entity type. Names are
  case-insensitive.
- **Several types under one name:** a name that several entity types share configures each of them, and the handle
  covers them all.
- **Listing the rows:** `hd2.enemies.spawn_list({faction = 'terminids'})` or `hd2.enemies.spawn_list({enemy = 'Charger'})`
  lists the rows: enemy, entity, faction, group and the ten vanilla weights.
- **Variants are separate types:** `Charger`, `charger_tier2`, `Spore Charger`, `charger_bull` and `Rupture Charger` are
  five different entities. Multiply each one you mean.

## Options

| Option | Meaning |
|---|---|
| `allow_unverified_effect` | Required (`true`) until the live test passes. |
| `difficulties` | Only these difficulties, for example `{7, 8, 9, 10}`. Default: all ten. |
| `owner` | Mod id. Defaults to the calling mod. |
| `label` | The name used in the log. |

`multiplier` is a number from 0 to 10.

**Who owns a type.** One mod owns a type's weights: another mod's call for the same type is refused (`ALREADY_SET`).
The same mod calling again replaces its own setting, moving from its bytes to the new ones in one transaction.

## Handles

`hd2.enemies.spawn_weight` never raises. The handle's `status` is live:

| Status | Meaning |
|---|---|
| `applied` | Written. |
| `pending` | Waiting for the game to be readable. |
| `deferred` | Waiting until no mission is running (see below). |
| `stopping` | Restoring, deferred. |
| `stopped` | Restored. |
| `refused` | Refused, with `code` and `reason`. |
| `conflict` | Another writer changed a row. It is never overwritten. |
| `unavailable` | A pin did not prove. Nothing is written. |

The refusal codes are `ACKNOWLEDGEMENT_REQUIRED`, `UNKNOWN_ENEMY`, `INVALID_MULTIPLIER`, `INVALID_OPTION`,
`ALREADY_SET` and `NOT_IN_A_ROSTER`.

- `handle:stop()` writes the vanilla weights back.
- `handle:describe()` lists each type with its status.
- `hd2.enemies.spawn_status()` lists every active setting.

The rosters are process-wide: a setting lasts until `stop()` or the end of the session, across missions.

## When it applies: what a mission has loaded

A mission loads the packages of the enemies whose weight at its difficulty is above 0 (0xABD6AC, in the mission's
package selection). So a weight never goes from 0 to positive while a mission, or its loading, runs: the enemy's
models and effects may not be loaded.

Which changes apply at once and which wait:
- **Apply at once:** a multiplier above 0 (it never changes which weights are above 0) and × 0 (it only removes
  candidates).
- **Wait until you're back aboard the ship:** restoring a × 0 type with `stop()`, or changing a × 0 to a positive
  multiplier. The handle says `deferred` / `stopping` until then.

Set the multipliers aboard the ship before you deploy so the whole mission uses them.

## Several players

Enemies are spawned by the mission host's AI.
- **You host:** your multipliers decide.
- **Someone else hosts:** your multipliers do nothing (the log says so once); theirs decide.

Public matchmaking is off while HD2Runtime runs.

## Guards

Every write is a guarded transaction over the enemy type's rows as read now:
- each whole 128-byte row is a context;
- it writes to game.dll image memory, read-write only;
- the expected bytes are exactly the vanilla weights, or this setting's own;
- each change is read back, and every other byte must be unchanged.

The pins are proven before any write:
- the faction installer and the per-faction lookup;
- PickEnemy's group, tag, difficulty, weight, zero-skip and random-walk instructions;
- each faction's roster descriptor, which must point at its rows with its row count.

An applied setting is re-read every second: a row another writer changed is a `conflict`.

## Proof and validation

- `scripts/research_enemy_spawn_weights.py` (`--check`) is the research. It covers:
  - 36 pins;
  - the three rosters, byte-identical in all five retained snapshots (ship and mission);
  - the census: no instruction stores into a roster; every weight reader (PickEnemy, the composition estimate and the
    package selection); the 14 pick sites.
- `scripts/generate_enemy_spawn_weights.py` builds `domains/enemy_spawn_weights.lua`.
- `scripts/validate_enemy_spawn_weights_snapshot.py` runs the production module on a copy-on-write overlay of the
  mission snapshot. It covers:
  - exact ×2, ×3 and ×0 writes, with no other roster byte changed;
  - the deferred restore during the mission, done on the ship;
  - the difficulties option and conflict detection;
  - every refusal, and a changed pin.
- `tests/test_enemy_spawn_weights.py` pins all of the above.

**Unproven:**
- Live: how often a changed type actually spawns.
- How many enemies a spawn makes. Each spawn system's template counts need their own proof, for example that a larger
  count stays within that system's fixed unit limits.
- The meaning of the other row members.
