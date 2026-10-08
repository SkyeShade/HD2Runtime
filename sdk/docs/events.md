# Gameplay scripting: events, handles, timers and keybinds

This is the reference: how each event is observed, what is proven and what is not. For writing a mod, start with
[event-scripting.md](event-scripting.md) (payload lifetime, identities, timers, ownership, actions, examples).

Internal design notes for the first event-driven scripting layer. Public release notes are not written yet.

## Why events are polled

Runtime patches no game code: no detours, no `.text` writes (the Bingus community convention, and the game ships
GameGuard). It already runs inside the game's LuaJIT, chained into the global `update(dt)` callback on the main
thread. Events are therefore **observed**: once per update tick, each active *source* reads proven game state
(through `ReadProcessMemory` on the game's own process, so an unmapped address fails the read instead of
faulting), compares it with the previous tick and queues what changed. Everything queued in a tick is dispatched
after every source has been polled.

Consequences that shape the whole API:

- **Every native event is `post`.** The game already applied the change. A payload is a snapshot; changing it
  changes nothing in the game.
- **Latency is one update tick** (about 16 ms at 60 fps). Several changes inside one tick are seen together.
- **No pre-event can run in time.** A callback that must run *before* the game applies damage would need a hook
  inside the native damage path; see [Damage](#damage).
- A source that cannot prove its native structures on this build is `unavailable`: its events never fire, and the
  reason is logged once and reported by `hd2.events.status()`. A source started before the game modules are loaded
  waits (`retry`, logged once) and tries again every 5 s.

The event catalog is `schemas/events.json` (generated into `domains/events_catalog.lua`, `sdk/EventCatalog.json`
and the LuaLS stubs). Subscribing to a name that is not in it, or to a `blocked` event, is refused with the reason.

## Events

| Event | Source | Phase | Payload highlights |
| --- | --- | --- | --- |
| `mission_started` / `mission_ended` | game_state | state | `mission` epoch, `host`, `mode`; `duration` on end |
| `player_spawned` / `player_died` | players | post | `player`, `local_player`, `avatar`, `avatar_id`, `avatar_semantic_id`, `position` (death: last position read alive), `observed` on death |
| `entity_spawned` | health | post | `entity`, `entity_id`, `type`, `semantic_id`, `name`, `display_name`, `enemy`, `faction`, `kind`, `avatar`, `unit_id`, `network_id` |
| `entity_died` | health | post | the above + `killer`, `local_killer`, `killer_peer`, `position`, `max_health`, `observed` (`dead_state` or `corpse`), `corpse_id` |
| `entity_killed` | health | post | `entity_died` with a creditor (a player the game credits) |
| `entity_damaged` / `player_damaged` | health | post | `damage` (health lost this tick), `health`, `attacker`, `local_attacker`, `downed` |
| `player_healed` | health | post | `amount`, `health`; `cause` names the mod when Runtime performed the heal |
| `player_fired` | stats | post | local player only: `shots` since the last check (10 per second), `total`, `sources` (shots per weapon), `unattributed` |
| `player_kill_credited` | stats | post | local player only: `kills` the game credited since the last check, `total`, `sources` (kills per weapon, throwable or stratagem), `unattributed` |
| `player_hit` | stats | post | local player only: projectile `hits` since the last check (the projectile system adds one per projectile that hits), `total`, `sources` (hits per weapon), `unattributed` |
| `player_damage_dealt` | stats | post | local player only: `damage` the game recorded since the last check, `total`, `sources` (damage per weapon, throwable or stratagem), `unattributed` |
| `explosion` | explosions | post | `name`, `position`, `observed` (`queue` or `request`), `source_id` / `source_type` / `source_name`, `owner_id` / `owner_type` / `owner_name`, `creditor_peer`, `player`, `local_player`; see [Explosions](#explosions). Not live-tested |
| `key_down` / `key_up` | input | post | `binding`, `key`, `owner` |
| `entity_damage_pre` | — | blocked | see [Damage](#damage) |

Every payload also carries `event` (its name), `time`, `frame`, `mission` and `cause`. Every health event carries the
entity identity fields listed for `entity_spawned`. Positions are read-only `HD2Position` snapshots.

**Identity.** `semantic_id` is the stable identity of the entity type (`domains/event_entities.lua`,
`scripts/generate_event_entities.py`): the enemy catalog's semantic id for its 177 classes
(`enemy/v1/<faction>/<class>`), else `entity/v1/<faction or folder>/<path leaf>` for a known resource path, else
`entity/v1/unresolved/<type hash>`. `display_name` is the wiki name only where the enemy catalog proves a one-to-one
match (21 classes); `name` is the catalogued class or path name. Identity is resolved once per entity when it is first
seen, from a table keyed by type: no catalog scan per event.

## Native sources

All structures come from `domains/event_natives.lua`, generated by `scripts/generate_event_natives.py` from the
research outputs `research/event-combat-F5FEE03DCFDB.json` (`scripts/research_event_combat.py`),
`research/event-state-F5FEE03DCFDB.json` (`scripts/research_event_state.py`) and
`research/event-mission-F5FEE03DCFDB.json` (`scripts/research_event_mission.py`, the in-mission captures),
`research/event-actions-F5FEE03DCFDB.json` (`scripts/research_event_actions.py`),
`research/event-wielder-F5FEE03DCFDB.json` (`scripts/research_event_wielder.py`) and
`research/event-explosions-F5FEE03DCFDB.json` (`scripts/research_event_explosions.py`). The
generator accepts a value only if a pinned instruction in the research uses exactly that value (for example
`mov r9d, dword ptr [r10 + 0x1038]` for the health hash capacity). At runtime `runtime/event_world.lua` checks the
build fingerprint, both image sizes and every pinned instruction (272 in game.dll and the executable) once per loaded
module before any source reads anything; `scripts/validate_event_world_snapshot.py` runs the same proof and the
production readers on all seven retained snapshots (three aboard the ship, four in one hosted mission) at different
module bases.

| Source | What it reads each tick | Notes |
| --- | --- | --- |
| `game_state` | The Game object's state (`+0xAC21C`: 3 Ship, 4 Mission, 6 PrepareMission, ...), the `game_mode` object count, its descriptor's authority bit (host) and mode type | mission = state 4 with a game_mode object |
| `players` | The player list (peer ids, lifecycle state, avatar network id), each avatar through the game's network-id map, its health record and unit position | positions only while `player_died` / `player_spawned` have subscribers |
| `health` | One bulk read each of the health manager header, its entity hash (entity → record index), the records (0x1B8 each), the ext records (0x1C) and the descriptor pointers | a descriptor is read only when an entity is first seen or its descriptor pointer changes; the corpse manager only in a tick where a tracked record disappeared |
| `stats` | The local player's `projectiles_fired`, `dealt_kills`, `projectiles_hit` and `dealt_damage` (only those with subscribers): main table plus the 64 source blocks (as the game's own `get_stat` sums them), per source type, 10 times per second | one bulk read of the source blocks for all four |
| `weapons` | The local avatar's wielder slot 0 (the entity in hand), the inventory selection and the held entity's descriptor type, 10 times per second | the local player only |
| `explosions` | The explosion queue's count (and its entries only when some are queued), and the explosions Runtime requested since the last tick | an idle tick is two reads; see [Explosions](#explosions) |
| `input` | Bound keys only, while the game window has focus | |

Health record fields used (all pinned): current health `+0x14` (stored as `max(health, -Constitution)`), life state
`+0x19C` (0 alive, 1 downed, 2 dead; only ever raised), last-hit creditor `+0x38` (a u64 peer id; the value every
health-manager kill dispatch passes as the killer), creditor at downing `+0x50`; ext record maximum health `+0x14`;
descriptor `{u64 type, u32 entity, u32 unit, u32 network id, u32 flags}` with flag bit 0 = owned by this peer.

**Kill attribution** is the game's own: the dead record's creditor peer id is compared with the local peer id
(`session +0xB398`) and the player list. No creditor means an environmental or unattributed death (`killer=nil`).

**Deaths the game has already replaced.** In a mission the game does not keep a dead enemy: it destroys the entity
(through its deferred destroy list, which removes the health record with it) and spawns a corpse entity of the same
type that takes over the dead entity's unit and stores the dead entity's full id (corpse manager `game+0x3326920`:
count `+0x18`, descriptors `+0x40`, 0x48-byte records `+0x48`, origin `+0x3C`; all pinned). None of the in-mission
captures held an enemy record in the dead state, so a poll can miss that state. When a tracked record disappears
before its dead state was seen, the health source therefore reads the corpse manager once: a corpse that names the
entity and owns its unit reports the death (`observed='corpse'`, `corpse_id`), with the creditor and maximum health
read on the last poll before it. A record that disappears without such a corpse (a despawn, or an entity destroyed
outright) is not a death. A death seen in the dead state is reported from there (`observed='dead_state'`) and never
again when the corpse appears.

**Enemy** means what the game counts as an enemy kill: the victim type's HealthComponentData `KillScore` (`+0x30`)
is positive (the kill-credit listener adds `dealt_kills` only then). `domains/event_entities.lua`
(`scripts/generate_event_entities.py`) holds it for all 501 health-owning entity types (129 count as kills), with the
catalogued name and faction. Peer ids are compared as two 32-bit halves: they exceed 2^53.

**Weapons** (`research/event-wielder-F5FEE03DCFDB.json`, `scripts/research_event_wielder.py`):

- **Wielder.** The wielder manager (`game+0x3326420`) maps an entity to its instance through the game's own hash
  (buckets `+0x30`, capacity `+0x38`, empty key `+0x3C`, multiplier `+0x40`). The instance's five 0x50-byte slot
  records are at `ptr(+0x60) + instance * 0x1D0`. The first u32 of slot 0 is the entity in hand. `wield` (0x785DE0)
  writes it; unwield writes 0.
- **Inventory.** The inventory manager (`game+0x3326738`, which the game's own callers pass to the weapon switch)
  maps the avatar to a 0x30-byte record whose `+0x1C` is the selected slot. The switch (0x9AAA50) writes the
  selection and wields the new item in one call. Selections 1 (primary) and 2 (secondary) are proven by the
  switch's jump table; 3 (support), 4 and 5 (held item) and 6 are inferred.
- **Type.** The held entity's type is the u64 of its descriptor, reached through the entity map of the entity
  manager (`+0xF1AEB0`; descriptor `+0xF32F18 + 24 * index`, which must name the same entity). A weapon's type is its
  resource.
- **Snapshots.** In the two mission snapshots before the death the local avatar holds its R-36 Eruptor (selection 1);
  aboard the ship nothing is held. After the reinforcement the new avatar's selection 5 matches its slot 0, but the
  (non-atomic) capture recorded that entity before the entity table saw it, so the reader reports nothing held
  instead of guessing.

**Live-proven** (`examples/projects/EquippedWeaponEventTest`): primary and secondary switches were detected correctly,
`weapon_equipped`, `weapon_unequipped` and `weapon_changed` matched the actual switches, and uncatalogued held items
were reported as uncatalogued (no name). Still inferred: the `support`, `held_item` and `unknown` slot labels
(`slot_proven = false`); not reported: death and reinforce transitions.

Only the local player is read: the switch wields with `replicate = 0`, so whether other players' wielders are kept
on this machine is not proven. The kill listener receives a source entity, but no record keeps it, so which weapon
made a particular kill is still unavailable.

## Explosions

`explosion` reports an explosion this machine's game is about to detonate. It reads the game's own explosion queue
(the queue `hd2.explosions.spawn` appends to); nothing is hooked. **Not live-tested.**

**What the game does each frame** (`research/event-explosions-F5FEE03DCFDB.json`, `scripts/research_event_explosions.py`;
every instruction below is pinned and re-proven at startup):

- The queue is the explosion system at Game + 0x1C9DAF8 (`game+0x3326340` is the Game object); the queue global
  `game+0x346D558` points at it in all seven retained snapshots. Count `+0x20`, kicked count `+0x24`, 256 entries of
  0x98 bytes from `+0x28` (position, ExplosionType, source entity, owner entity, creditor peer: the request's pinned
  stores). `RequestExplosion` (0x13C0A80) appends at index count.
- The world update (0xAB5000, run by the plugin update 0x4EE6C0) **kicks** first (0xAB55AF -> 0x13F73F0 -> 0x13C5420):
  kicked = min(count, 8). Then come the projectile kick (impacts), the entity and component updates, and much later
  the **gather** (0xAB5FBF -> 0x13C6180): it processes entries 0 .. kicked - 1 in order (0x13C0D10 each), moves the
  rest to the front, and sets count = count - kicked, kicked = 0. Then the projectile gather (more impacts).
- So the queue is first in, first out, at most 8 explosions are detonated a frame, and a request leaves the queue
  only when a gather processes it. Entries are never cleared: the bytes of processed requests stay until a later
  request overwrites their slot (`runtime/custom_silos.lua` reads them that way), which is why the event only
  trusts the entries below the count.

**What one read per tick sees.** A request made after the frame's kick is still queued when the world update returns,
and the next frame's gather is the first that can process it, so the poll of the Lua update in between sees it. That
covers the projectile system's impacts (the projectile kick after the explosion kick, and the projectile gather),
the gather's own chained explosions (a blast's damage requests more: 0x13C0D10 -> 0x12B06C0 -> 0x12B02B0), and the
entity and component updates between kick and gather (explosives, behaviors, abilities). A request made after a poll
and before the next kick is processed in that frame and is never queued at a poll, unless more than 8 are pending:

- **Runtime's own requests** (`hd2.explosions.spawn`, a custom stratagem's blast) are made in the Lua update. The
  event reports them from the request instead (`observed = 'request'`), at the next poll, and a queued entry equal to
  one of them (type, entities, creditor, position) is not reported again.
- **Engine callbacks before the world update, and indirect calls before its kick.** No direct call path from the
  world update before the kick reaches the request (3559 functions checked by `scripts/research_event_explosions.py`),
  but its 14 indirect calls (engine API) and engine callbacks outside it are not followed. Unproven in particular: when
  the network impact handlers (0xB9E0C0 / 0xBBADE0) that make a peer explode its copy of another player's shot run.
- Where the Lua update runs relative to the world update is inferred (outside it: the projectile spawn timing), not
  traced.

**Reported once.** Each poll reads the count and, only when it is not 0, the first 64 entries (later ones are read
once the queue moves them up). The previous poll's entries still queued are the longest suffix of the previous read
that equals, byte for byte, a prefix of this one: with one world update in between that is everything past the 8
processed, with none it is all of them, with several it is fewer. Everything after that prefix is new. Two distinct
requests identical in all 0x98 bytes at the same place in two consecutive reads would be reported once.

**Payload.** `name` names the explosion **type** through a pluggable lookup (`runtime/explosion_names.lua`): by default
the types `domains/event_natives.lua` catalogues (each weapon's own explosion, named by its weapon; the NUX-223 and
B-100 Hellbombs; the Cyborg Production Unit), else `nil`; a fuller explosion catalogue can install a resolver. A type
requested by something else (a mission objective requesting 242, a custom projectile using a donor's explosion) gets
the same name. The raw ExplosionType is not in the payload. `source_id` and `owner_id` are the entities the request
names; `source_type` / `owner_type` come from the game's entity map when the poll reads them (an explosive is often
gone by then: `nil`), and `source_name` / `owner_name` from the stat-source and entity catalogues (an Eruptor shell's
source is the R-36 Eruptor). `creditor_peer` is the peer the request credits, `player` / `local_player` that player.
`cause` is `native` for queued requests; for Runtime's requests it is the requester's cause when it passes one, else
the mod whose callback, timer or scope is running (`{source='mod', mod, kind='explosion', depth, parent}`; no action
id), else `{source='runtime'}`.

**Every machine.** The queue is this machine's own explosion system (no network send in the drain). A client queues
the explosions it simulates itself: live 2026-10-07, a client's queue held the silo missiles' own detonations, the
host's and its own. Which other players' explosions a machine queues, and when, is not traced.

**Cost.** An idle tick reads the queue pointer and the count (two reads); a tick with queued requests reads their
entries once and resolves each new entry's two entity types once per mission. Validated on the seven snapshots
(drained queue: count and kicked 0, no event) and on the offline fixture (`tests/test_event_sources.py`,
`tests/test_event_scripting.py`).

## Handles

A handle holds identity, never an address. `runtime/handles.lua`:

- **`HD2EntityHandle`** (`id`, `type`, `name`, `faction`, `enemy`, `avatar`): every live query (`is_valid`,
  `is_alive`, `is_downed`, `health`, `max_health`, `position`, `describe`) re-resolves the entity through the game's
  health hash and checks it is still the same object: the same mission epoch, the same type and the same descriptor
  pointer. After the mission ends, after the entity is removed, or once its id names another object, live queries
  return `nil` / `false` (`describe().reason` says why). `is_enemy` and the static fields stay readable.
- **`HD2PlayerHandle`** (`peer`, `slot`, `is_local`): valid while the peer is in the player list. `avatar()`
  resolves the current avatar through the game's own network-id map (the avatar changes on every respawn);
  `health`, `max_health`, `position` and `is_alive` go through it. `heal(amount)`: local player only, see
  [Actions](#actions).
- **Positions** come from the engine's unit registry (exe): the unit must still be registered with the same 8-bit
  generation, its object must still carry the unit id, and its scene-graph accessor must be the reviewed method
  (`lea rax,[rcx+0x60]; ret`). The engine increments an entity's generation when it destroys it
  (`entity_exists` checks it), so a stale id can never be read as live.
- **Death snapshots**: `player_died.position` is read at death while the unit still exists, else the last position
  read while alive; it is plain data and stays valid after the avatar is destroyed.

### Entity lifetime in a mission

Observed on four captures of one hosted mission (alive, after a death and reinforce, mission end;
`research/event-mission-F5FEE03DCFDB.json`):

- **Mission start and end.** In the mission the game state is 4 with one game_mode entity (the authority bit set on
  the host). At the end the state moves to 5 (PrepareShip) and the mission population goes with it: no game_mode, no
  health records, no corpses, the player's avatar network id is cleared (0x7FFF), and the game_mode entity's id no
  longer exists. The mission stats stay readable (kills and deaths are still there).
- **A dead Helldiver** keeps its avatar and its health record in the dead state while the player waits to be
  reinforced. On reinforce the game destroys the dead avatar (its generation advances, so a handle to it is invalid:
  "the engine destroyed the entity"), a corpse entity takes over its unit and names it as its origin, and a new
  avatar with a new network id and entity id appears; `Player:avatar()` resolves to the new one.
- **Enemies** are replaced by corpses as described under [Native sources](#native-sources); the corpse keeps the unit,
  so the death position stays readable after the record is gone.
- The avatar's loadout weapons are separate entities spawned with it and replaced by corpses with it (the avatar's
  InventoryComponent lists them: primary, secondary, more); the weapon currently wielded is not decoded.

`hd2.players()`, `hd2.local_player()` and `hd2.game_state()` return fresh handles or snapshots.

### Is this the right game build? `hd2.build()`

```lua
local status, info = hd2.build()   -- 'matched' | 'mismatched' | 'not_ready', {pinned, reason}
if status == 'mismatched' then mod:log('HD2Runtime does not support this game update yet (pinned ' .. info.pinned .. ')') end
local state, why = hd2.game_state()   -- nil and the reason when unreadable
```

- `matched`: the running executable and game.dll are the build this Runtime is pinned to (`info.pinned`: the first
  12 hex digits of its executable hash). `mismatched`: another build; every write and native read refuses.
  `not_ready`: the modules are not loaded yet or could not be hashed (`info.reason`).
- It never raises, proves no pins and reads no game memory. Cheap to poll: the two files (~30 MB) are hashed once per
  loaded module, a wrong build included (before this, every call on a wrong build hashed them again).
- `hd2.game_state()` returns its reason as a second value: `unsupported build fingerprint`, `TARGET_UNAVAILABLE: game
  modules not ready`, a changed native structure, or `game state unreadable`.
- The local avatar's entity id: `hd2.local_player():avatar()`. Which menu is open and which ship station a player
  uses are not mapped (see [Not mapped yet](#not-mapped-yet)).

### Not mapped yet

Asked for by mod authors and not available, because no retained snapshot or native code reading proves them yet:

- **A general "a menu is open" state** (the UI presenter). Only the loadout screen is read (the stratagem selector's
  own detection), and only internally.
- **Ship stations** (who uses the Stratagem Hero cabinet or another terminal; "the local player started / stopped
  using a station").
- **Positions of entities without health** (a cabinet, a terminal): `entity:position()` reads the health manager's
  record, so it answers only for entities with health. The engine's unit position read exists internally, but no
  public handle names such an entity yet.

Each needs snapshots taken in those exact states (menu open and closed; at the cabinet and away) before a field can be
named; see [field-naming rules](evidence.md).

## Damage

`entity_damaged` / `player_damaged` are **observational**: the health lost since the previous tick (every hit in that
tick summed), with the last hit's creditor. They cannot change the damage.

**`entity_damage_pre` is blocked.** A callback that changes one hit would have to run inside game.dll's damage
application (`0x9235F0`) before it writes health. Runtime patches no game code, and the research found nothing read
at damage time that could scale one attacker's or one weapon's damage: the Vitality booster scalar, the relation
table and mission modifiers are global, and element multipliers, the acceptance mask and the attribute lookups belong
to the **target**. Editing a shared DamageInfo definition would change every shot of every weapon using it, so it is
not offered as a pre-damage event.

**Weapon attribution comes from the game's own stats, per player, not per death.** The kill-credit listener adds each
stat to the credited player under the type of its source entity (AddStat `0x62C930`, source resolved through
`0xFD9D40`), and the player's stat record keeps one block per source type. In a mission, guns are keyed by their
weapon entity (R-36 Eruptor, P-113 Verdict), stratagems by their payload (Eagle Strafing Run, Orbital EMS Strike) and
throwables by the throwable; the main table holds the part the game records without a source (aboard the ship the
shooting range's shots were keyed by the avatar type). `player_fired` and `player_kill_credited` report that growth
per source for the local player, named from `domains/event_entities.lua` (`sources`: player and support weapons,
throwables and single-stratagem payloads; a payload shared by several stratagems, such as the hellpod, is not named).
A single death still carries no weapon: `entity_killed` names the credited player only, and the persisted
`event+0x60` value is not proven to be the DamageInfoType.

## Damage and hit attribution

`player_damage_dealt` and `player_hit` attribute damage and hits exactly, without inferring anything from timing. They
read the game's own accounting: the per-player mission stats, which keep one block per **source type**
(`research/event-state-F5FEE03DCFDB.json` derives the stat keys, the call sites below come from its `addStatCallSites`).

| Stat | Added by | Amount | Source block |
| --- | --- | --- | --- |
| `projectiles_hit` (0x897A5551) | the projectile system (game.dll 0x13AE275), once per projectile that hits | 1 | the weapon that fired it |
| `dealt_damage` (0x5C7A2930) | the damage-stats function 0x12A0F50 (`AddStat` at 0x12A11F2) when damage is applied | the damage the game recorded | the source entity of the damage |
| `dealt_team_damage` | the same call, for team damage | | not reported |

`AddStat(stats, creditor peer, key, amount, source entity)` resolves the source entity to its type (0xFD9D40), exactly
as it does for `dealt_kills`. The retained in-mission snapshots hold, for the local player (validated by
`scripts/validate_event_world_snapshot.py` on the production readers):

| Source | Fired | Hits | Damage |
| --- | --- | --- | --- |
| R-36 Eruptor | 8 | 6 | 9592 |
| P-113 Verdict | 20 | 13 | 1721 |
| Eagle Strafing Run | | | 29097 |
| (main table, no source) | | | 300 |

**Source taxonomy.** Each `sources[]` entry is `{type, name, hits|damage}`. `type` is the entity type the game recorded
the stat under; `name` comes from `domains/event_entities.lua`:

| Kind | What the game keys it by | Named |
| --- | --- | --- |
| weapon | the weapon entity (primary, secondary, support) | yes |
| throwable | the throwable itself (the K-2 Throwing Knife is `F7B35A9C5AE340B6`) | yes |
| stratagem | the stratagem payload | yes, when one stratagem owns the payload |
| unnamed | an entity type the catalog does not name, for example a payload shared by several stratagems, or the local avatar (Runtime's own `hd2.explosions.spawn` names the avatar as source) | no (`name = nil`) |
| unattributed | damage the game recorded without a source (the main table); which damage lands there is not proven | `unattributed` |

Not claimed, for lack of proof:

- **Direct vs follow-up damage.** `dealt_damage` counts everything the game credits to the source, including its
  explosions and statuses. `player_hit` counts only projectile hits.
- **The victim.** The stats hold no victim. `entity_damaged` still names the victim, with the last hit's creditor
  only.
- **Other players.** Only the local player is read.
- **Damage a target's armor stops completely.** It records nothing, so it is not a "hit" for `player_damage_dealt`.
- **Thrown entities.** The K-2 knife is a sticky thrown entity, not a projectile-system projectile, so it appears in
  `player_damage_dealt`, never in `player_hit`.

The events are polled 10 times per second: one event sums everything recorded since the previous check. Two sources
in the same check stay separate entries, and unattributed damage is never assigned to one of them.
`examples/projects/VampiricThrowingKnivesTest` heals the local player on K-2 damage (a fixed 25, or a proportion of the
recorded damage).

**Live-proven (2026-09-30, VampiricThrowingKnivesTest):**
- K-2 knife damage is attributed to the knife exactly: misses record nothing, other weapons report under their own
  source (`event_damage_source_attribution`);
- `hd2.actions.heal(25)` from that handler heals the local player (`event_action_heal`).

Still offline-proven only: the damage-proportional heal, other throwables and other sources.

**Cost.** A check is one bulk read of the player's 64 source blocks, whatever the number of hits, victims or
entities: no world scan. On the offline benchmark (`py scripts/bench_events.py --stats`, 400 entities, every native
event subscribed, all 64 blocks filled) a check costs 0.05 ms on average and 0.36 ms at most (10 sources changing).
The steady tick goes from 0.061 to 0.071 ms.

## Actions

**Heal** (`player:heal(amount)`): the game's own `AddHealthFraction(health manager, entity, fraction)` (game.dll
`0x91E920`), called from the update callback on the main thread through one adapter function
(`runtime/windows_write.lua` `native_heal`) after:

- the function's exact 12-instruction prologue is re-read and matches;
- the entity is a Helldiver avatar owned by this machine (descriptor flag bit 0), alive (life state 0) and below its
  maximum; the fraction is `min(amount, missing) / maximum`.

The game clamps to maximum health, heals the zones, updates synced health and sends its own network messages because
this machine owns the avatar. A downed or dead avatar is refused (the function would revive a downed one). The heal is
matched to the next observed `player_healed` of that avatar, which then carries the mod's cause. A direct write of
the health field is never used: it would skip synced health and the network messages.

**Explosions** (`hd2.explosions.spawn(weapon, {position = ...})`): the game's own explosion request, game.dll
`0x13C0A80`, called from the update callback through one adapter function (`runtime/windows_write.lua`
`native_explosion`). `research/event-actions-F5FEE03DCFDB.json` (`scripts/research_event_actions.py`) proves:

- **The request.** It appends one explosion to the game's queue (`game+0x346D558`: count `+0x20`, 256 entries of
  0x98 bytes from `+0x28`) and refuses a full queue itself. Arguments 1..6 are the queue, a pointer to the position,
  the ExplosionType, the source entity, the owner entity and the creditor peer id (pinned stores into the entry).
- **The template.** Runtime passes arguments 7..15 as 0, null, 1, 0, null, null, null, 0, 0: six of the game's 31
  call sites pass exactly this, and most others differ only in optional arrays and pointers.
- **The identity.** The queue drain resolves the type through the settings table `game+0x37CC920` (bounded by
  0x1A7). In all four mission snapshots (and the three ship snapshots, `validation/event-world-snapshot.json`) the
  entry of each of the 13 catalogued weapon explosions points at a record carrying that type, damage type and radii.
- **The semantics.** The snapshots hold a stale R-36 Eruptor request: type 158 (its catalogued explosion), source =
  the Eruptor weapon entity, owner = the local avatar, creditor = the local peer.

Before each call Runtime re-proves the request's exact prologue bytes, reads the queue count, checks that the type's
settings record carries that type, and checks the position and the entities. The API accepts only the 13 catalogued
weapon explosions and the two named Hellbomb explosions, each with a known package (`hd2.explosions.list()`), loads that package through the proven asset gate
when it is not resident, and requires a mission and host authority (a client's request would be local, and the
host's synced health overwrites it). Source and owner are the local avatar and the creditor the local peer, like a
shot of the player's own weapon. Requests are rate-limited per mod (6 at once, 1 per second): the game does not say
which explosion killed an entity, so a chain of explosions and deaths cannot be traced by cause. No network message
call was found in the drain; whether other machines see the effect is unproven. Live-proven on host only for the
NUX-223 Hellbomb (below); the weapon explosions use the same request but are not live-tested.

**Named explosions: the Hellbombs.** Neither Hellbomb names its explosion in data. The type is a code literal in the
behavior of the entity that detonates, passed through two wrappers (game.dll 0x4C89C0, then 0x13C6D30) to the request.
That is why no direct call site showed it.

- **NUX-223 Hellbomb.** Its entity (`content/fac_helldivers/hellpod/hellbomb/hellbomb`, the payload of StratagemType 42
  `DropoffHellbomb`) is the only owner of BehaviorId 224. The behavior dispatcher's table entry 223 calls 0x288360.
  Its "explode" event (thin hash 0xB3FD1AFF) enters state 3, which requests **ExplosionType 242** at the "nuke" node
  (`0x288817 mov edx, 0xF2`).
- **B-100 Portable Hellbomb.** Its entity (`bomb_backpack`, the only owner of BehaviorId 8) requests **ExplosionType
  125** the same way (`0xC3305 mov edx, 0x7D`).

Both settings rows (17 / 25 / 45 m, damage type 479 = 10000 damage) match in every snapshot.

Runtime pins the literal, the explode compare, the wrapper call and the wrapper chain with the other event pins, so a
changed build disables the action instead of requesting a wrong type. The assets are the delivering stratagem's
package (`packages/generated/loadout/hellbomb`, `packages/generated/loadout/hellbomb_backpack`), loaded through the
asset gate like any other.

`hd2.explosions.spawn('Hellbomb', ...)` (alias of `'NUX-223 Hellbomb'`) requests type 242.

Type 242 is also requested by several mission objectives (for example `cy_control_tower` and `refinery_terminal`).
Requesting it changes nothing about them, but editing ExplosionSettings[242] would change them all. Runtime still
never fakes an explosion by editing another explosion's definition. Inferred, not traced: who sends the "explode"
event.

**Live-proven on host** (`examples/projects/DeathHellbombTest`, `docs/live-evidence.md`): dying in a real mission
detonated the NUX-223 Hellbomb at the saved death position. The avatar-removal death reported before the mission
started was refused with `NOT_IN_MISSION`, as designed. Not promoted: the B-100 Portable Hellbomb (type 125), what
other players see, and client requests (refused `HOST_ONLY`).

**Projectiles** (`hd2.projectiles.spawn(weapon, {position, direction})`): the game's own scalar projectile wrapper,
game.dll `0x13A8F50` `FireProjectile(ignored, type, const float pos[3], const float dir[3], entity, target,
entity_path)`, called through one adapter function (`runtime/windows_write.lua` `native_projectile`). The research
(`research/event-actions-F5FEE03DCFDB.json`) proves:

- **The template.** The game's AI fire helper calls it at `0x119E612` with the projectile system, a zero
  `entity_path` and a target. With a zero `entity_path` the wrapper builds a plain projectile: source = owner = the
  entity, creditor from the entity's owner, kind 2. It inserts it into the system's 2048-slot pool (`0x13A9830`).
- **The gate.** It returns at once unless the projectile system (`game+0x347CEA8`) is active (`+0x28 = 1`). The flag
  is 1 in all three in-mission snapshots before the end, and 0 at the mission end transition and aboard the ship.
- **The identity.** The wrapper indexes the settings pointer table `game+0x37C7670` by type **without a bounds or null
  check**. In every mission snapshot the entry of each of the 67 catalogued weapon projectile types points at a
  record carrying that type; entry 0 and entry 351 are null.
- **Timing.** The engine calls the Lua `update(dt)` before the game update on the same thread, and the game's
  projectile kick/gather pair runs inside the game update. So a spawn from a callback is picked up by the next kick,
  like every in-game spawner.

Before each call Runtime re-proves the wrapper's exact prologue bytes and the active flag, checks the type's record,
normalises the direction, checks the position and the firing entity (the local avatar), and loads the weapon's
package first. The spawn creates the projectile's effects immediately, so an unloaded package is never allowed.
Host only, rate-limited per mod (12 at once, 4 per second).

Side effects, as the game's own: each projectile counts as a shot in the owner's stats, and a full pool reuses its
oldest slot. Unproven:

- the creditor derivation is an engine ownership call (inferred to be the local peer);
- damage authority after a hit (a client spawn is refused);
- whether other machines see the projectile (no network send was found).

**Live-proven on host for the R-36 Eruptor** (`examples/projects/ProjectileActionTest`): F6 fired it, repeatedly.
Every other projectile type, what other players see, and client requests stay unproven.

**Status effects** (`hd2.status.apply(entity, status, {buildup})`): the game's own status request queue, game.dll
`0x129F170` `QueueStatusRequest(ignored, type, target, float buildup, instigator, variant)`, called through one
adapter function (`native_status`). The research proves:

- **The queue.** Global `game+0x347CF38`; count `+0x201134`, capacity 0x1000, 0x1C-byte entries from `+0x195120`.
  The function refuses the invalid entity, a target without a status instance, a type the target cannot receive
  (`0x6994F0`) and a full queue.
- **Routing.** The world update drains it every frame (`0x13F7D5E` -> `0x12A6EF0`). Each request is applied here when
  this machine owns the target (`0xB894B0`, then `ApplyStatusEffect` `0x699E40`), or sent to the owner
  (`0xBEBDE0`).
- **The template.** The game's own stun callers (`0x864ED2`, `0xB72069`) pass variant 0, an entity instigator and
  100.0.
- **The identity.** The status settings table `game+0x37C5C50` holds records that carry their type. Neither
  `0x6994F0` nor `ApplyStatusEffect` bounds the type: a type of 128 or more corrupts the stack.
- **The meaning of the float.** It is buildup: each request adds it, and the status triggers when buildup reaches the
  target's susceptibility threshold. Strength and duration come from the status settings; applying again refreshes,
  and only poison vulnerability stacks.

Runtime offers only the 11 statuses a player weapon applies through a DamageInfo slot
(`research/status-effects-F5FEE03DCFDB.json`, `weaponSlotUsers > 0`), and checks that each one's settings record
carries its type in every mission snapshot. Before each call it re-proves the prologue bytes, the queue headroom, the
manager, the record, the buildup (0 < buildup <= 1000) and that the target and the instigator (the local avatar)
exist. Host only, rate-limited per mod (10 at once, 5 per second) and per target (4 at once, 2 per second).

Unproven:

- the drain was never observed running (the queue was empty in every snapshot);
- client routing and what other players see;
- that the statuses' visual effect resources (three 64-bit hashes in each settings record) are always resident.
  They are expected to be, because enemies and environments apply the same statuses whatever the players carry.

**Live-proven on host for `fire`** (`examples/projects/StatusActionTest`): the status visibly applied to a live
enemy. The other 10 allowlisted statuses, client routing, and what other players see stay unproven.

## Script values: event-driven definition changes

`mod:value({id, min, max, step, default})` is a number a mod sets from its own code and binds as an `hd2.ensure`
field value, exactly like a Mod Options slider: the ensure validates `min`, `max`, the default and one step through
the operation's normal guards when it is declared, and re-applies (debounced, 0.5 s) whenever `value:set(n)` changes
it. It changes a **definition**, so every consumer of that definition sees it; it is the honest substitute for a
per-hit modifier until one exists (`examples/projects/KillStackDamageTest`).

`mod:choice({id, values, default, labels})` (r50) does the same for any value a field takes: booleans, strings
(`'unlimited'`, a status name), reference handles and plain tables such as a calldown code. See
[options.md](options.md#script-choices-r50).

## Subscriptions

```lua
local mod = hd2.mod()                               -- this mod's context; same object on every call
local sub = hd2.events.on('player_died', function(event)
    mod:log('died at ' .. tostring(event.position))
end, {id = 'announce'})                            -- id: idempotent registration
sub:disable(); sub:enable(); sub:unsubscribe()
```

**Ownership** (`runtime/events.lua` `M.owner`), most specific first: an explicit `opts.owner` or a mod context's id;
the mod scope entered with `hd2.events.run_as(id, fn)` (the SDK addon wrapper runs every mod's startup as its
resource id); the mod whose callback, timer or keybind is running (a registration made inside a callback); the
calling chunk when it is a mod resource; else `unknown`. `hd2.mod()` without an id uses the same rule and refuses
`unknown`. Every subscription, timer, keybind and action therefore names its mod in logs, failures and causes.

| Option | Meaning |
| --- | --- |
| `id` | Registration is idempotent per owner, event and id: running the mod's startup again replaces the callback of the same subscription instead of adding a second one. |
| `priority` | Higher runs first (−1000..1000, default 0). Ties run in subscription order. |
| `scope` | `'mission'`: removed automatically when the mission ends. |
| `max_failures` | Consecutive failures before the subscription is disabled (default 25, `0` = never). |

**Ordering is deterministic:** sources in a fixed order, events in the order observed, subscribers by priority then
subscription order. Subscriber lists are copy-on-write: a subscription added during a dispatch starts with the next
event; one removed during a dispatch is not called again, even later in the same dispatch.

**Registration never raises.** An unknown event, a blocked event, a bad callback or bad options are logged
(`[HD2Runtime] event subscription <event> (<mod>) rejected: <reason>`) and return an inert handle with
`state='rejected'`, so one mistake cannot abort a mod's startup (the same rule as `hd2.ensure`).

## Callback isolation

Every callback (event, timer, keybind) runs through `xpcall`. A failure:

- is logged with the mod, the event and the error:
  `[HD2Runtime] event entity_died callback failed (mod mods/author/my_mod, subscription 12): <error> [<frame>]`;
- never stops the remaining subscribers of that event, other events, timers or sources;
- is logged in full three times per subscription, then every 100th time with a count;
- after `max_failures` consecutive failures (default 25) disables that subscription, with one log line. `enable()`
  re-arms it.

A source whose own poll fails is retried; after 30 consecutive failures it stops and reports `unavailable`.
Dispatch nested deeper than 8 levels is dropped and logged.

## Timers

```lua
local t = mod:after(2.5, function() ... end)                  -- once
local r = mod:every(1, function() ... end, {scope = 'mission'}) -- repeating; cancelled when the mission ends
t:cancel(); r:remaining()
```

- Game time: the sum of update `dt`. It pauses while the game does not update.
- `after(0, ...)` runs on the next tick. `every` needs at least 0.05 s; per-frame work uses `hd2.on_frame`.
- Missed intervals (a long frame) are skipped, never replayed in a burst.
- Timers live in a binary heap keyed by due time: a tick with nothing due costs one comparison.
- Timer callbacks are isolated exactly like event callbacks. `id` replaces an earlier timer with the same id.
- A timer started from inside a callback keeps that callback's event as its origin, so an action it performs is
  still attributed (see [Causes](#causes-and-recursion)).

### Every frame: `hd2.on_frame`

```lua
local frame = hd2.on_frame(function(dt, handle)   -- or mod:on_frame(...)
    game:update(dt)                                -- dt: the tick's game seconds
end, {id = 'arcade', scope = 'session'})
frame:disable(); frame:enable(); frame:cancel()
```

- Runs on every update tick, after the events and timers of that tick, in registration order. One registered from
  inside a frame callback first runs on the next tick.
- The official replacement for wrapping the global `update` function: the same owner, `id` (a second callback with
  the same id replaces the first), `scope = 'mission'` and failure isolation as a timer (25 failures in a row disable
  it, logged as `frame callback failed (mod ...)`).
- It costs nothing while no mod registers one. Keep the work small: it runs every frame.

## Keybinds

```lua
mod:bind('my_mod.detonate', {key = 'F6', on_press = function() ... end, on_release = function() ... end})
```

- Only bound keys are polled (`GetAsyncKeyState`), once per tick, and only while the game window has the keyboard
  focus (`GetForegroundWindow` belongs to the game process). Losing focus releases held bindings.
- Ids are namespaced (`author_mod.action`). The first mod to register an id owns it; another mod reusing it is
  refused (logged). The owner registering it again (a repeated startup) updates it in place.
- One chord belongs to one binding. A binding asking for a chord already in use is registered in state `conflict`
  with no key and logged; it never takes the key over silently. `binding:rebind('F7')` resolves it.
- Chords match their exact modifiers: `F6` does not fire while Ctrl is held; `Ctrl+F6` does.
- `key_down` / `key_up` events report bound presses on the bus. There is no raw keyboard event: polling every key
  every frame would cost for nothing.
- Limits: Runtime cannot see the game's own bindings or whether the chat box has focus. Prefer keys the game
  leaves unbound (F5–F12, Insert, Home, End, Page Up/Down). The Mod Options Menu can later expose `rebind`.

### Any key's state: `hd2.input.down / pressed / released`

For a mod that needs more than a few chords (a game, a menu):

```lua
hd2.on_frame(function(dt)
    if hd2.input.pressed('W') then cursor_up() end        -- the one tick the key went down
    if hd2.input.down('Space') then charge(dt) end         -- held
    if hd2.input.released('MOUSE1') then fire() end
end)
```

- Every name of `hd2.input.keys(true)`: the chord keys plus `CTRL`, `SHIFT`, `ALT`, `MOUSE1` and `MOUSE2`; aliases
  `Esc`, `Return`, `PgUp`, `PgDn`, `Ins`, `Del`, `Control`. An unknown name raises.
- A key is followed from its first query on and then sampled once per update tick, before that tick's events,
  timers and frame callbacks, so every callback of one tick sees the same state, and `pressed` / `released` hold for
  exactly that tick.
- Only while the game window has the keyboard focus: unfocused, every key reads up. A key already held when the
  focus comes back is not a press. `hd2.input.focused()` tells which; `hd2.input.mouse()` gives the cursor
  `{x, y, w, h, left}` in client pixels from the top-left.
- `hd2.input.wheel()` is the mouse wheel this tick in notches (experimental, r51; see
  [ui-overlay.md](ui-overlay.md#the-mouse-wheel-experimental-r51)).
- **Reading consumes nothing.** The game receives every key a mod reads, so `W` still moves the Helldiver, unless a
  mod window asks the game to ignore input while it is open (`hd2.input.block`, below).
  Blocking a key from the game needs a hook in the game's input code, which the Runtime does not install (see
  [Input blocking](#input-blocking-not-available)).

### Keeping input from the game while a mod window is open (r52, experimental)

```lua
mod:on_frame(function()
    if editor_open then hd2.input.block({keyboard = true, mouse = true}) end   -- renew every update
end)
hd2.input.block(false)                                                      -- stop at once
```

The game takes its keyboard and mouse input from the window messages of its own window thread. While a mod renews the
block, the Runtime's native message hook (docs/ui-overlay.md "The mouse wheel") turns these into `WM_NULL` before the
game's window procedure sees them. **Since 0.30.2 the hook is off unless the player turns it on** (MODS > HD2Runtime >
*Native mouse wheel / input hook*); off, `hd2.input.block()` returns `false` and the reason and blocks nothing.

- **`keyboard`:** key presses and characters (`WM_KEYDOWN`, `WM_SYSKEYDOWN`, `WM_CHAR`, `WM_SYSCHAR`, raw keyboard
  makes). Key releases always pass, so a key held when a window opens is not left down.
- **`mouse`:** button presses and double clicks (legacy and raw) and the wheel, after the wheel is counted for
  `hd2.input.wheel`. Movement passes.
- **A lease, not a switch.** Each call holds for 0.5 s (GetTickCount64, checked in the native procedure). If the mod
  stops calling, or Lua stops running, the game gets its input back within half a second; `false` stops at once, and
  removing the hook clears it.
- **Mods still read everything:** keys and buttons through `GetAsyncKeyState` and the cursor through `GetCursorPos`,
  which blocking does not touch, so `hd2.input.pressed`, keybinds and `overlay:mouse()` keep working.
- `hd2.input.wheel_status()` reports `blocking` (the flags) and `blocked` (messages blocked so far).
- **Not live-tested.** If the game reads a device another way (DirectInput, polling), that input still reaches it;
  the live test checks Escape (the pause menu), Tab and Delete with a mod window open.

## Mod contexts and state

`hd2.mod(id)` returns one context per id, holding:

- `mod.session`: a table kept for the game session;
- `mod.mission`: a table cleared **in place** when a mission starts and when it ends (a mod may keep a reference);
- `on`, `once`, `after`, `every`, `on_frame`, `bind`, `log`, `in_mission`, `subscriptions`: every registration is
  attributed to the mod;
- `mod:store()`: the mod's saved key/value data, kept between game sessions ([mod-store.md](mod-store.md)).

Each mod has its own tables; nothing is shared between mods.

## Mission scope

`mission_started` and `mission_ended` bracket a mission. When a mission ends:

1. `mission_ended` subscribers run (they can still read the mission's state);
2. mission-scoped subscriptions and timers end (`state='expired'`);
3. every mod's `mission` table is cleared;
4. the mission epoch advances: every handle captured during that mission becomes invalid.

## Causes and recursion

Every payload carries `cause`:

- native gameplay: `{source='native'}`;
- produced by an action a mod performed through Runtime: `{source='mod', mod=..., action='heal#12', kind='heal',
  depth=n, parent={event=..., cause=...}}`;
- requested by Runtime itself outside any mod callback (a custom stratagem's blast, reported by `explosion`):
  `{source='runtime', kind='explosion'}`.

An action records the mod and the event it was reacting to (directly or through a timer it started). `depth`
counts mod-caused links: reacting to native gameplay is depth 1; reacting to an event a mod caused is that event's
depth + 1. Runtime refuses actions deeper than 4 links, which stops chains such as *death → explosion → kills →
explosions → ...* from running away. A mod can also ignore its own effects: `if event.cause.mod == mod.id then
return end`.

Only effects Runtime can prove come from an action carry a mod cause; anything else stays `native`.

## Performance

Measured by `scripts/bench_events.py` on the game's own LuaJIT (offline, the sources' real FFI path with memcpy in
place of `ReadProcessMemory`), every native event subscribed, one local player:

| Entities with health | Steady tick | Busy tick (10 deaths, 20 damage changes, dispatch) |
| ---: | ---: | ---: |
| 100 | 0.033 ms | 0.062 ms |
| 400 | 0.052 ms | 0.115 ms |
| 1000 | 0.099 ms | 0.360 ms |

In game, add the `ReadProcessMemory` calls themselves: about 6 bulk reads for the health scan (≈ 0.2 MB at 400
entities), about 7 for the game state, and about 15 per player for the players source, i.e. well under half a
millisecond per tick at 60 fps with a full squad. The stats source reads 21 KB ten times a second.

Re-measured after the identity snapshots (400 entities, interleaved with the previous build on the same, busier
machine): steady ticks 0.087-0.115 ms against 0.080-0.116 ms; busy ticks after warm-up 0.10-0.36 ms against
0.09-0.33 ms. A busy tick allocates about 40% more (53 KB against 38 KB for 30 events: the identity fields and the
read-only positions), and the first busy ticks of a session include the JIT compiling the new payload paths
(0.7-0.9 ms, once). An unchanged entity costs one comparison per tick; its identity and handle are built once, when it
first produces an event.

- Nothing polls until a mod subscribes, starts a timer or binds a key; the update watch detaches when the last one
  is gone. A mod context (`hd2.mod`) keeps the game-state source running so its `mission` table resets on real
  mission boundaries.
- A source runs only while one of its events has a subscriber. A tick with no subscribers for an event builds no
  payload for it.
- Dispatch allocates nothing per subscriber (copy-on-write lists, no per-call closures).
- Hot sources read whole arrays into reusable FFI buffers (`runtime/native_view.lua`): one `ReadProcessMemory` per
  array per tick instead of one per entity, and no Lua strings per entity.
- `hd2.metrics()` reports `events.tick` (total and worst duration), `events.dispatched`,
  `events.callback_failures`, `events.health_scans`, `events.native_heals` and `events.handle_lookups`.

## Tests

- `tests/test_events.py`: subscribe / unsubscribe / order / once, isolation and auto-disable, copy-on-write dispatch,
  idempotent ids and the singleton, refusals, mission scope, timers, causes, owner inference, script values, keybinds
  (press / release / modifiers / focus / conflicts / ownership) and the real Win32 input backend.
- `tests/test_event_sources.py` on `tests/event_world_fixture.lua` (an offline world laid out as the native table
  says, with every pinned instruction): proof and tamper refusal, waiting for the game modules, mission boundaries
  and handle invalidation, kill attribution (local, other player, environment, non-enemy), the KillHeal flow with its
  cause, destruction and id reuse, the death-position snapshot, deaths seen through the corpse (reported once, with
  the last creditor and the corpse's position; a despawn or a corpse on another unit is not a death), damage,
  `player_fired` and `player_kill_credited` per source, the FFI read path, and constant reads per tick.
- `tests/test_event_scripting.py`: hand-written scripting on the fixture world: a corpse-observed death keeps its
  identity and read-only position for a timer that fires after the entity is destroyed (with zero game reads),
  mission cleanup cancels delayed callbacks for good, per-mod ownership of subscriptions, timers, keybinds and
  callback-started timers, isolation between mods, per-source names and an unnamed shared source, every guard of the
  explosion action (unknown or raw ids, unknown packages, no mission, not host, full queue, rate limit, cause depth,
  changed request function, asset wait), and the example mods run exactly as their built ZIPs wrap them.
- `scripts/validate_event_world_snapshot.py` (`validation/event-world-snapshot.json`): the production modules on all
  seven retained snapshots, including the reinforced avatar, the corpse that replaced the first one, the invalid
  handle to it, the per-source stats, the mission-end teardown and one poll of the explosion source.
- `tests/test_event_sources.py` and `tests/test_event_scripting.py` (explosions): each queued request reported once
  (no update between two polls, one, several, more than 8 queued, a request after the kick), names and their
  pluggable lookup, entity types and the credited player, Runtime's requests with their cause and never twice, and the
  idle cost.
- `scripts/validate_packaged_runtime.py` runs the four acceptance mods from the built ZIP on real snapshot memory:
  every pin proven, the ship state, the local player, avatar, health and position, the isolation behaviour, and the
  script value driving real guarded writes.

## APPLIED versus event-time changes

`hd2.patch` / `hd2.ensure` change **definitions** (a weapon's damage row, a stratagem's cooldown); `APPLIED` means
the guarded write of that definition was verified. Event-driven actions act on **one live object** at one moment
(heal this player now). They are separate capabilities with separate proofs; an action never edits a shared
definition to fake a per-event effect.
