# Projectile homing

`hd2.projectiles.homing(weapon, opts)` makes the local player's own shots of a weapon home while they fly. An EAT-17
rocket fired past an enemy curves into it; a P-11 stim fired near a teammate curves into that teammate.

```lua
local rockets = hd2.projectiles.homing('EAT-17 Expendable Anti-Tank', {target = 'enemy', turn_rate = 120, cone = 30})
local stims = hd2.projectiles.homing('P-11 Stim Pistol', {target = 'friendly', multiplayer = true})
-- later
rockets:stop()
```

Status: **offline-proven, not live-tested** (0.30.0). The steering path is proven on the game's code and on the
retained mission snapshot (`validation/projectile-homing-snapshot.json`). Whether a steered shot flies and hits as the
proofs say still needs a live test (`examples/projects/ProjectileHomingTest`).

## What changes, and what never does

Each update, a shot that is homing has its own velocity (3 x f32, the projectile's flight record +0x0C) turned toward
its target by at most `turn_rate` x the update time, at the same speed. That is one guarded write of that one
projectile. Nothing else is written:

- not the weapon;
- not its projectile row or any other shared definition;
- not any other projectile;
- not any other member of the shot.

Gravity, drag, ricochets, penetration and the impact stay the game's own. The next step simply starts from the turned
vector.

Why this is enough (research `research/projectile-homing-F5FEE03DCFDB.json`):

1. The projectile update hands exactly that vector to the ballistic integrator (`0x13AB55A`). The integrator loads it,
   adds gravity and drag, integrates the position from it and stores it back (`0x13AAE30`).
2. Each step is hit-tested from where the shot was to where it went (`0x13AB48E`, `0x13AB7B5`). A steered shot therefore
   hits what its new path meets.
3. The game ends a shot that slows below a fraction of its spawn speed (`0x13AB6D5`). Homing keeps the speed, so that
   rule never triggers because of a turn.
4. The census covers every pool-relative velocity store in game.dll, plus the update's and the integrator's own: spawn,
   the integrator, the unit-driven path, the hit path, the network impact handlers and one store outside the projectile
   system. Each of them sets the velocity outright or continues from it; none needs the vector Runtime wrote to be the
   one it expects.

Every write is a guarded transaction:

- It is planned over the shot's records as read in that same update: its flight record, its hit record, its type
  entry and its flags.
- It writes to private read-write memory only.
- The expected bytes are exactly the velocity just read.
- Every other byte is checked unchanged, and the write is read back.

A shot whose records no longer describe the same projectile is dropped and never written again. That covers another
type, another owner or creditor, a shot no longer in flight, a requested impact, a stopped shot, a unit driving it, or a
shorter distance travelled than last time (its pool slot was reused).

A Lua update runs before the game update that steps projectiles, so the turned vector is the one that step uses.

## Which shots

- **The weapon.** A name from `hd2.projectiles.homing_list()`, case-insensitive. A catalogued projectile output id
  (`output/v1/projectile/...`) works too.
  - The list holds every named owner of a projectile type in `research/projectile-identities-F5FEE03DCFDB.json`.
    These are player weapons and their underbarrels, support weapons, vehicle and exosuit weapons, mounted weapons,
    stratagem payloads (Eagles, orbitals) and deployed entities (sentries, emplacements): 173 names.
  - Enemy weapons are left out: their shots are never this player's.
  - Beams, arcs, sprays and melee are not projectiles and cannot home.
- **The projectile types.** Every type the weapon fires is followed: its rounds, every charge or heat level, each
  ammunition kind. A weapon with several types gets one configuration per type; `stop()` and `stats()` cover them all.
- **Fired by that weapon.** A shot counts only when its source is one of the weapon's own entity types. The same
  projectile type fired by another weapon is counted (`other_sources`) and never touched.
- **Only the local player's own shots.** A shot credited to another player, or an enemy's shot of the same type, is
  never looked at further (`others`).
- **Not unit-driven.** A projectile whose movement a unit drives is refused (`UNIT_DRIVEN`): the game recomputes its
  velocity from that unit every step.

## Options

| Option | Default | Meaning |
|---|---|---|
| `target` | `'enemy'` | `'enemy'`: a living catalogued enemy. `'friendly'`: another player's living Helldiver (never the shooter). |
| `turn_rate` | 90 | Degrees per second the shot may turn (1..1440). Bullets at 900 m/s need a high rate to curve noticeably. |
| `cone` | 30 | Half angle in degrees around the shot's direction a target must be inside to be acquired (1..180). |
| `range` | 100 | Metres from the shot a target may be (1..500). |
| `arm_distance` | 2 | Metres the shot flies straight before it steers (0..100). |
| `aim_height` | 1 | Metres above the target's root (its feet) the shot aims at (-5..10). |
| `retarget` | true | When the target dies, acquire another. `false`: fly straight on. |
| `multiplayer` | false | Also steer while other players are in the game (experimental, see below). |
| `label` | owner and weapon | The name used in the log (at most 64 characters). |
| `owner` | the calling mod | Mod id. |

**Acquisition.** A shot acquires the target with the smallest angle off its current direction, inside the cone and the
range. While it has none it looks again every 0.1 s. It keeps that target while it lives (`retarget` decides what
happens next). It turns toward the target's current aim point every update; there is no lead.

**Targets.**
- Enemies come from the game's health records, read the way the health event source reads them: catalogued kind
  `enemy`, alive. The list is built incrementally (512 hash slots and 12 positions per update), and only while it can
  be needed: the local player holds a configured weapon, or a configured shot flew in the last 5 s.
- Players come from the player list: avatars that are not this machine's, alive.

**Limits.**
- At most 16 shots are steered at once; more fly straight (`BUSY`).
- A shot is followed for at most 10 s.
- Each mod configures a weapon once: a second call by the same mod replaces the first. Another mod's call for a weapon
  that already homes is refused (`ALREADY_HOMING`).

## Handles

`hd2.projectiles.homing` never raises for a refusal. The handle's `status` is `'active'`, or `'refused'` with `code`
and `reason`:

- `UNKNOWN_WEAPON`
- `INVALID_OPTION`
- `ALREADY_HOMING`
- `LIMIT`

A configuration lasts until `handle:stop()` or the end of the session, across missions.

`handle:stats()` reports this mission so far:

| Count | Meaning |
|---|---|
| `shots` | Own shots seen |
| `steered` | Shots with at least one write |
| `writes` | Steering writes |
| `locks` | Targets acquired |
| `others` | Shots that are not this player's |
| `other_sources` | This player's same-type shots from another weapon |
| `no_target` | Acquisitions that found nothing |
| `refused` | Why shots flew straight, as `{CODE = n}` |

`hd2.projectiles.homing_status()` lists every active configuration.

## Several players (experimental)

Without `multiplayer = true`, shots fly straight whenever another player is in the game, and the log says why once per
weapon (`NOT_SOLO`). With it:

- **Only your own shots are steered, on your machine.** Every machine simulates its own copy of a shot. Runtime only
  ever writes this machine's copy of this machine's player's shot. A friend's shots are never touched by your game.
- **Your shot decides where it hits.** The game's impact message makes every other machine explode its copy at your
  shot's impact position (research proof 8: handlers `0xB9E0C0` / `0xBBADE0`, traced). The damage comes from your
  machine's hit, as the Gas EAT's live result showed (the owning machine's explosion is the one that damages).
- **Other players see the shot fly straight**, with the hit drawn where it homed. Unless they also run the mod, their
  copy is not steered.

Public matchmaking is off while HD2Runtime runs (research/docs/matchmaking-safety-F5FEE03DCFDB.md), so this only
happens in your own lobby.

## Log

| When | Line |
|---|---|
| Each configuration | `projectile homing (<mod>): <weapon> shots (projectile type N) home on enemies: turn ..., cone ..., range ..., armed after ...` |
| Each weapon's first lock | `homing (<label>): <weapon> shot in pool slot S locked on <enemy> at D m (...)` |
| Each weapon's first write | `homing (<label>): first steering write: pool slot S velocity turned X deg toward <enemy> (1 write, 12 bytes; non-target bytes unchanged true; protection restored true; speed kept V m/s)` |
| Each reason a shot flies straight (once per weapon) | `homing (<label>): <weapon> shot in pool slot S flies straight: CODE: reason` |
| Mission end, per weapon and type that fired | `... own shots seen, ... steered (... writes, ... locks, ...), ... untouched; flew straight: CODE x n` |
| A pin that does not prove | `homing UNAVAILABLE: every homing shot flies straight: ...` (nothing is written) |

Per-shot lines (each further lock, each shot's end) are written with the diagnostics switch
(`hd2.custom_stratagem.verbose(true)`).

## Proof and validation

- `scripts/research_projectile_homing.py` (`--check`) proves 53 instruction pins and the velocity store census on the
  game.dll image and all four retained mission snapshots.
- `scripts/generate_projectile_homing.py` builds `domains/projectile_homing.lua`: the pins, the flight members and the
  weapon list.
- `scripts/validate_projectile_homing_snapshot.py` runs the production module on a copy-on-write overlay of the
  mission snapshot. It plants the local player's own shot of the weapon in hand in the next pool slot, 20 degrees off a
  living enemy, and checks the following:
  - the incremental enemy scan lists the snapshot's living enemies;
  - the shot locks on the enemy with the smallest angle;
  - each update turns it by exactly turn_rate x dt at the same speed, in one guarded transaction with no protection
    change, and every other byte of its records stays as it was;
  - it converges and then stops writing;
  - another peer's shot, a unit-driven shot, the same type from another entity, a shot with no target in its cone, a
    friendly target alone, a reused slot and a changed pin all leave every shot alone.
- `tests/test_projectile_homing.py` pins all of the above and the API's refusals.

Unproven: the live flight and hit of a steered shot, the multiplayer picture on another machine, and one velocity store
outside the projectile system (`0x8A580C`, not traced).
