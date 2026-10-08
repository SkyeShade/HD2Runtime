# Helldiver fields (type-wide; not live-tested)

`hd2.helldiver()` is the Helldiver type (`avatar_helldiver`): its movement speeds, its stamina and the damage values of
its six body zones.
- Research: `scripts/research_avatar_fields.py` → `research/avatar-fields-F5FEE03DCFDB.json`
  (summary: `research/docs/avatar-fields-F5FEE03DCFDB.md`). 146 pinned instructions, byte-identical in all seven
  retained snapshots.
- Runtime: `domains/helldiver_writes.lua`, generated data `domains/helldiver_fields.lua`
  (`scripts/generate_helldiver_fields.py`, naming layer `schemas/helldiver_fields.json`).
- Public catalog: `sdk/HelldiverFieldCapabilities.json` (contract `hd2runtime.helldiver.type_fields.v1`).
- Snapshot validation: `scripts/validate_helldiver_fields_snapshot.py` → `validation/helldiver-fields-snapshot.json`.

**Scope: every Helldiver this machine simulates.** These are TYPE records, not one player's values. Every Helldiver
avatar this machine simulates reads them: in practice the local player, in a mission and aboard the ship. This is an
interim, accepted by the user: a per-player version needs per-avatar records that the game does not keep. Therefore:
- every write needs `allow_shared=true`;
- nothing here is live-tested, so every write also needs `allow_unverified_effect=true`.

Multiplayer:
- Movement and stamina are simulated only for the avatars this machine owns. A write therefore changes the local
  player, not the other players' Helldivers.
- Which machine builds a hit on a remote avatar is not traced, so the zone fields' effect on other players is unknown.

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local F = hd2.fields
hd2.ensure({transaction = {id = 'fast-helldiver', target = hd2.helldiver(),
    allow_shared = true, allow_unverified_effect = true, changes = {
        {field = F.helldiver.speed_jog, expect = 3.2, value = 4.5},
        {field = F.helldiver.speed_sprint, expect = 5.5, value = 8},
        {field = F.helldiver.stamina_recover_delay, expect = 1.5, value = 0.5}}}})
hd2.ensure({patch = {id = 'armoured-head', target = hd2.helldiver():zone('head'),
    allow_shared = true, allow_unverified_effect = true,
    field = F.zone.damage_multiplier, expect = 'normal', value = 'reduced'}})
```

`hd2.ensure{enabled = toggle, ...}` restores the vanilla values when disabled, like every ensure.

## Movement speeds (AvatarComponentData record 0)

The movement update (`0xA6C700`) reads the record every frame, for every avatar this machine simulates. A write
therefore applies at the next frame.

The game caps the target speed at 10 m/s (`min(10.0, speed)` at `0xA6D0DE`), so the reviewed range ends at 10. The slow
speeds (aim, walk, crouch aim, crouch walk, prone) are scaled by the direction factor: 1 moving forwards, down to the
factor moving backwards. The absolute speeds (jog, sprint, exhausted sprint, crouch jog, crouch sprint, swim) are not.

| Field (`hd2.fields.helldiver.`) | Offset | Vanilla | Range | Grade | Live semantics |
| --- | --- | --- | --- | --- | --- |
| `speed_direction_factor` | +4 | 0.75 | 0..1 | STRONG | Factor of the slow speeds when moving against the facing. Its name is not proven (lead: `movement_info`). |
| `speed_aim` | +8 | 2.0 | 0..10 | STRONG | Standing while aiming (state bit 82, inferred) × direction factor. |
| `speed_walk` | +12 | 2.0 | 0..10 | STRONG | Standing, no jog or sprint action, not aiming × direction factor. |
| `speed_jog` | +16 | 3.2 | 0..10 | CONFIRMED | Standing with the jog action. |
| `speed_sprint` | +20 | 5.5 | 0..10 | CONFIRMED | Standing with the sprint action and stamina above 0 (or Death March). |
| `speed_sprint_exhausted` | +24 | 4.25 | 0..10 | CONFIRMED | Sprinting at empty stamina without Death March (the native lead name is `sprint_exerted`). |
| `speed_crouch_aim` | +28 | 1.2 | 0..10 | STRONG | Crouched (state bit 77) while aiming × direction factor. |
| `speed_crouch_walk` | +32 | 1.5 | 0..10 | STRONG | Crouched, otherwise × direction factor. |
| `speed_crouch_jog` | +36 | 2.25 | 0..10 | CONFIRMED | Crouched with the jog action. |
| `speed_crouch_sprint` | +40 | 4.0 | 0..10 | CONFIRMED | Crouched with the sprint action. |
| `speed_prone` | +44 | 1.5 | 0..10 | STRONG | Prone (state bit 78) × direction factor. |
| `speed_swim` | +48 | 1.5 | 0..10 | STRONG | Swimming (state bit 95). |

Grades:
- **CONFIRMED.** The reader and its branch are pinned.
- **STRONG.** The reader is pinned, but the meaning of the state bit that selects it (aim, crouch, prone, swim) is
  inferred from the code, not proven.

Both are exposed the same way, with `allow_unverified_effect`.

## Stamina (AvatarComponentData record 0)

Stamina is a fraction from 0 to 1. Drains and costs are multiplied by a per-avatar cost multiplier: 0.75 in every
snapshot, set by the game, not by this record.

| Field (`hd2.fields.helldiver.`) | Offset | Vanilla | Range | Grade | Lifecycle | Live semantics |
| --- | --- | --- | --- | --- | --- | --- |
| `stamina_sprint_duration` | +52 | 23 | 1..3600 | CONFIRMED | every frame | Seconds to empty a full bar: stamina −= multiplier × dt / this (÷ 1.3 with modifier 2), while sprinting, sliding, or jogging on sand, mud or snow. 0 would empty the bar at once, so it is refused. |
| `stamina_recover_time_standing` | +60 | 7 | 0.5..600 | CONFIRMED | every frame | Seconds to refill an empty bar standing: stamina += regen multiplier × dt / this, capped at 1. |
| `stamina_recover_time_crouching` | +64 | 6 | 0.5..600 | CONFIRMED | every frame | The same, crouched. |
| `stamina_recover_time_prone` | +68 | 5 | 0.5..600 | CONFIRMED | every frame | The same, prone. |
| `stamina_recover_delay` | +72 | 1.5 | 0..60 | CONFIRMED | each drain and action | Seconds without regen after a drain or an action. It is copied into the avatar's timer each time; Stim Stamina skips it. |
| `stamina_cost_jump` | +76 | 0.2 | 0..1 | CONFIRMED | each jump | Fraction of the bar per jump, × the cost multiplier. |
| `stamina_cost_dodge` | +80 | 0.1 | 0..1 | CONFIRMED | each dive | Fraction of the bar per dive (`0xA50890`), × the cost multiplier. |
| `stamina_cost_climb` | +88 | 0 | 0..1 | CONFIRMED | each climb | Fraction of the bar per climb. |
| `stamina_cost_slide` | +92 | 0.05 | 0..1 | CONFIRMED | each slide | Fraction of the bar per slide start, × the cost multiplier. |

Not exposed, because no reader was found:
- `jog_stamina_decay_duration` (+56, 300; the terrain jog drain uses +52);
- the vault cost (+84);
- ExertionLevelInfo (+340..+388).

## Body zones (HealthComponentData record 76)

`hd2.helldiver():zone(name)` takes `head`, `body`, `arm_left`, `arm_right`, `leg_left` or `leg_right` (or the index,
0 to 5). Any other name is refused (`UNKNOWN_ZONE`).

| Field | Zone offset | Vanilla | Range | Lifecycle | Live semantics |
| --- | --- | --- | --- | --- | --- |
| `hd2.fields.zone.damage_multiplier` | +0xC4 | `'normal'` | a name | every hit, TYPE record | Damage × the multiplier: `'none'` ×0 (the zone takes no damage), `'critical'` ×1.5, `'normal'` ×1, `'reduced'` ×0.75, `'symbolic'` ×0.25. Every hit kind uses it. |
| `hd2.fields.zone.damage_multiplier_dps` | +0xC8 | `'normal'` | a name | every damage-over-time hit, TYPE record | For damage-over-time hits it replaces `damage_multiplier`, unless it is `'inherit'` (native 0), which means use `damage_multiplier`. `'none'` is refused here, because the native 0 does not mean immune: to make a zone immune, set `damage_multiplier` to `'none'`. |
| `hd2.fields.zone.durable_resistance` | +0xCC | 0 | 0..1 | every hit, TYPE record | The durable share d: damage = standard × (1 − d) + durable × d. The research calls it the durable fraction; it is the same member and id as on enemies. |
| `hd2.fields.zone.affects_main_health` | +0xF8 | head 1.5, body 1.0, limbs 0.85 | 0..10 | every hit | Share of the hit forwarded to main health: main loss = round(D × this), only when the share is above 0. The reader is CONFIRMED; the exact D is STRONG. |
| `hd2.fields.zone.health` | +0xE8 | 85 / 60 / 35 / 35 / 45 / 45 | 1..100000 | **from the next spawn** | Copied into the avatar when it spawns. A Helldiver already alive keeps its current zone health. The record value is also read again when a dead limb is restored, and on one main-health cap path, so a write changes those for living Helldivers too. |

| Field (on `hd2.helldiver()`) | Offset | Vanilla | Range | Lifecycle | Live semantics |
| --- | --- | --- | --- | --- | --- |
| `hd2.fields.entity.explosive_damage_percentage` | +388 (default zone) | 0.5 | 0..10 | every hit | Share of explosion damage that every zone takes: no avatar zone sets affected_by_explosions, so explosions use the default zone's value. Corpses skip it. |

Every zone field is CONFIRMED.

- **Names, not numbers.** `damage_multiplier` and `damage_multiplier_dps` take names for `expect` and `value`
  (case-insensitive). An unknown name, or a number, is refused (`UNKNOWN_DAMAGE_MULTIPLIER`).
- **Not exposed.** A zone's own explosive percentage (+0x144) is dormant: explosions never read it, because no avatar
  zone is affected by explosions.

## Private copies

Every avatar reader resolves the record through `0x508DB0`. If the avatar carries a **private copy**, the reader uses
it. Otherwise it uses the type record.
- **Where copies come from.** The game makes a private copy only at spawn, from an entity delta. The copy is the whole
  record, frozen as it was then.
- **Aboard the ship.** The ship's avatar always has one: delta `0x73012E9238B6E3B9` sets walk 1.5 and jog 4.08. A type
  write therefore does not reach the Helldiver on the ship.
- **In a mission.** None of the retained mission avatars has a copy, so writes reach them at the next frame.
- **Health.** The zone reads that are override-aware (`affects_main_health`, the spawn copy of zone `health`, the
  explosive percentage) use a private HealthComponentData copy the same way. `damage_multiplier`,
  `damage_multiplier_dps` and the durable share are read from the type record on every hit, copy or not.

Runtime never writes a private copy. Instead:
- Each write checks the Helldivers this machine simulates, read-only, through the avatar manager's own maps. The
  pinned layout is proven first.
- When one of them holds a copy that keeps the fields being written, the write logs a note with the result, for
  example: `note: fast-helldiver: entity 249 (the local player) carries a private AvatarComponentData copy ...`.
- `hd2.helldiver():private_copies()` returns the same check:
  `{status='checked', simulated, avatars={{entity, local, avatar_copy, health_copy}}}`, or
  `{status='unavailable', reason}`.

Which customizations carry the other two AvatarComponentData deltas (sprint decay 4 and recover 18/16/14; long-throw
power 1.85) is not resolved.

## Guards

Before any memory is touched, every write proves, on the live tables:
- **The build.** It is the build the research covers (`HELLDIVER_BUILD_CHANGED` otherwise).
- **The entity owner.** `avatar_helldiver` owns exactly one entity row, and its component list holds the component.
- **The record.** Its index row, record index and single owner:
  - AvatarComponentData: index row 1, record 0, of a 2-row table.
  - HealthComponentData: index row 443, record 76, which no other row selects.
- **The zone.** For a zone field, the zone's name hash (zone +96).
- **The current bytes.** They hold the reviewed vanilla value (or the desired one). Anything else is a `CONFLICT`
  naming who holds the bytes.

`expect` must be the reviewed vanilla value. Values outside the reviewed range, non-finite values, a non-integer zone
health and a missing acknowledgement are refused before anything is read.

The tables live in the loaded entity file, a read-only allocation. The write uses the guarded page-protection path
that every type-record write uses, and restores the protection.

## Not live-tested

Nothing here has been tried in game. Strongly differentiated values make a live test easy to read, for example:
- jog 3.2 → 8;
- `stamina_sprint_duration` 23 → 3;
- the head's `damage_multiplier` `'normal'` → `'none'`.

Test in a mission: aboard the ship, the private copy hides speed changes.
