# HD2Runtime on HellForge

HellForge (an offline, modded Helldivers 2 on a pinned game build) has its own engine for mods: code mods, a live
field editor (F8) and event hooks. When the Runtime runs in a HellForge session it finds HellForge's **Lua bridge**
(`hellforge_modloader.dll`, HellForge's `docs/lua-bridge.md`) and writes nothing itself: HellForge makes every change.
A mod made for the Runtime runs unchanged; the API is the same.

`runtime/hellforge.lua` decides it once: the session's `HELLFORGE_MODLOADER` environment variable, then the loaded DLL
and its bridge version (this Runtime speaks bridge 3). Outside HellForge neither is there and every module keeps its own
path. In a HellForge session whose bridge cannot be used (an older HellForge), writes are refused with
`HELLFORGE_UNAVAILABLE` and the reason, never made by the Runtime itself. `hd2.hellforge` tells a mod:
`{active, bridge, sdk, build, unavailable, events_unavailable}` (or `{active = false, reason}`). The release's
`hd2runtime.json` names the bridge it is made for (`"hellforge": {"bridge": 3}`), which HellForge's Mods page checks.

## Writes

`hd2.patch`, `hd2.transaction`, `hd2.plan` and `hd2.ensure` validate exactly as before (targets, reviewed ranges,
acknowledgements, `expect`). Then, instead of the guarded write, each change becomes a HellForge live edit of the same
native value (`runtime/hellforge_writes.lua`):

- a component record field: by the record's entity (HellForge finds it from the record index), with `HF_LIVE_SHARED`
  when other entities share the record; a stratagem payload's component (the Orbital Laser's) by its payload entity;
- a settings row field (projectile, damage, explosion, status, arc, beam): by the row's id (`recordType` or
  `nativeIdentity`), never its position in the table;
- a stratagem definition (its name and icon members too) by its stable id; a booster's own row; the rows a booster's
  target names (its explosion, damage, status and granted stratagem) by their ids;
- an attachment's entity delta, a mission timer's delta and a booster status's multiplier through HellForge's
  `set_stat`; a mission director's timer as a component field;
- an armor perk's value as a row of HellForge's `PassiveModifier` or `PassiveStat` tables;
- the G-109 Urchin's pulse explosion through HellForge's `copy_row` (its final discharge row follows);
- a calldown code through HellForge's `set_code`. A code changed during a mission shows in the HUD from the next one.

HellForge resolves each field through the game's tables every time (a mod entity's own records, tables HellForge moved)
and keeps the edit when the game reloads its data. Its F8 editor shows the value with the mod's name (`lua.<mod>`). A
Lua mod's edit sits over HellForge code mods' and under the player's own F8 changes.

A change back to the reviewed value (`value == expect`, and an `ensure` restoring its baseline) removes the mod's edit:
HellForge puts back what is under it, another mod's value or the game's. A transaction or plan with one refused change
undoes what it changed in that run. A field HellForge cannot take yet is refused with `HELLFORGE_UNSUPPORTED`: a mod's
own icon image, and values a domain works out while it applies (projectile and explosion swaps, beam conversion). Enemy
fields answer `HELLFORGE_UNAVAILABLE` until HellForge maps enemies.

An `ensure` has no byte check on HellForge: it re-sends the same edit each interval, which HellForge takes as no change.

## Events

`runtime/hellforge_events.lua` drives the event sources from HellForge's hooks. The payloads are built the same way, from
the same reads:

| Events | From |
|---|---|
| `mission_started`, `mission_ended` | HellForge's game state |
| `player_spawned`, `player_died` | HellForge's player lifecycle |
| `entity_spawned` | HellForge's spawner (entities with health only, as before) |
| `entity_died`, `entity_killed` | HellForge's kill dispatch (`observed = 'kill'`) |
| `entity_damaged`, `player_damaged` | HellForge's damage consumer |
| `player_healed` | HellForge's heal event (every player's Helldiver) |
| `player_fired`, `player_kill_credited`, `player_hit`, `player_damage_dealt` | HellForge's stat event (the local player's mission stats, by source; at most five sources each) |
| `weapon_equipped`, `weapon_unequipped`, `weapon_changed` | HellForge's weapon event |
| `explosion` | HellForge's explosion request hook: every request, mods' and the Runtime's own included (`observed = 'queue'`) |
| `bughole_destroyed` | HellForge's bug hole event |
| `key_down`, `key_up` | the Runtime's own (the keyboard) |

`entity_damaged.damage` is the hit as the game queues it, before armour and multipliers (the Runtime's own source
measured the health lost); `health` is read after. Every event the Runtime has comes from HellForge.

The world proof (`runtime/event_world.lua`) skips the pins in code HellForge rewrites (`hellforge_lua_rewrites`: the
instructions it points at its moved tables, the functions it hooks) and proves every other one.

## Actions

`runtime/hellforge_actions.lua`. The calls keep their checks, rate limits and answers; their last step, the game call
or write the Runtime made, is HellForge's engine action of the same kind (HellForge's SDK 11, the same game functions on
the game thread). A refusal answers `HELLFORGE_REFUSED` and HellForge's reason.

| Call | HellForge |
|---|---|
| `heal`, `heal_limb`, `heal_limbs`, `injure`, `add_velocity` | its `heal`, `heal_limb`, `injure`, `add_velocity` (the local Helldiver) |
| `hd2.status.apply` | its `apply_status` (host) |
| `resupply_from_pack` | its `resupply_from_pack` (the Supply Pack's self-use) |
| `hd2.explosions.spawn`, `hd2.projectiles.spawn` | its `spawn_explosion`, `spawn_projectile` (host); packages through its package loader |
| `hd2.projectiles.homing`, `modify_shots` | its shot rules (one per projectile type); `on_shot` callbacks are not called |
| `hd2.pelican.spawn` | its `spawn_pelican`, which holds the hover too; the Runtime follows the stages as before |
| `hd2.ownership.credit_to_player` | its `credit_to_player` (solo host) |
| `hd2.freeze_mission_timer` | its `freeze_mission_timer` (host); clients do not follow it (the lobby sync is off) |

Every package the Runtime requests (a mod's assets, an explosion's) goes through HellForge's package loader.

## Unavailable areas

`runtime/hellforge_api.lua`. Each call answers `HELLFORGE_UNAVAILABLE` (a rejected handle, or nil, code and reason) and
the log says so once per area; catalogue reads (`hd2.explosions.list`, `hd2.projectiles.list`, ...) stay.

| Area | Why |
|---|---|
| `hd2.custom_stratagem` | Custom stratagems are HellForge stratagem mods (its stratagem registry), for good |
| `hd2.enemies.spawn_weight`, `spawn_list`, `spawn_status` | HellForge has not mapped enemies yet |

`hd2.player_passives.set` goes through HellForge's armor passive override (`set_passives`). UI overlays, the F10 panel,
sounds, game text, options, `hd2.store`, timers and input are the Runtime's own, as everywhere. The lobby sync modules
(synced assets, beam conversions, the mission timer) and the public matchmaking check stay off: HellForge's session has
its own co-op and network block.

## Tests

`tests/test_hellforge_bridge.py` runs the API against a fake bridge (`runtime/hellforge.lua` `set_backend`): a weapon
field as a live edit and its removal, shared records, the wait for the entity data, settings rows, a refused
transaction undone, the unsupported fields, enemies, plans, the unavailable areas, passives, the actions and every
event source.
