# Game sounds (`hd2.sounds`)

A mod finds the game's own sound events in a catalogue, loads their bank and plays them through the game's sound
engine, so they follow the game's volume settings and mix; it can pause, resume and query what it posted and set a
game parameter or switch on a sound's own source. Implementation: `runtime/sound_events.lua`,
`runtime/sound_catalogue.lua`, `runtime/wwise_plugin.lua`; API: `api/sounds.lua`. The weapon firing-sound catalogue
is [weapon-sounds.md](weapon-sounds.md); the research is
[research/sound-events-F5FEE03DCFDB.md](research/sound-events-F5FEE03DCFDB.md) and
[research/wwise-plugin-bindings-F5FEE03DCFDB.md](research/wwise-plugin-bindings-F5FEE03DCFDB.md).
**Offline-tested only; not live-tested yet.**

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

-- A UI click the loadout screen itself makes.
hd2.sounds.play('ui/generic_select')

-- Find an explosion a stratagem's bank holds (the first: the B/MD C4 Pack's), load its bank once, play it at the player.
local boom = hd2.sounds.list({catalogue = 'events', family = 'explosions', stratagem = true})[1]
hd2.require_assets({id = 'boom-bank', targets = {hd2.sounds.asset(boom.name)}})
local p = hd2.local_player():position()
local h = hd2.sounds.play(boom.name, {position = {p.x, p.y, p.z}})

-- A loop runs until stopped; it can be paused and asked about.
local loop = hd2.sounds.play('sentry/gatling', {position = {p.x, p.y, p.z}})
hd2.after(1, function() if loop then loop:pause() end end)
hd2.after(2, function() if loop then loop:resume() end end)
hd2.after(4, function() if loop then loop:stop() end end)
```

## The catalogue

Two catalogues, one namespace:

- **Weapon firing sounds** (`hd2.sounds.list()`, unchanged): 171 names such as `'sentry/gatling'`,
  `'support/mg206'` ([weapon-sounds.md](weapon-sounds.md)).
- **Every sound event of the build** (`hd2.sounds.list({catalogue = 'events'})`): 10 030 events in 416 banks, named
  `<family>/<bank>/<event>`. `<event>` is the event's own Wwise name where a string of the game's code or data hashes
  to its id (68 events: `'ambience/env_shared/env_sludge_bubbling'`), else its id as eight hex digits
  (`'stratagems/stratagems_orbital_380mm_he/4c725137'`, `'explosions/stratagem_c4_backpack/207000f9'`). Nothing is named from a guess.

| family | what (from the bank's content path) | events |
| --- | --- | --- |
| `weapons`, `throwables`, `melee` | `wep_*`, pistols, `wep_gre_*`, `wep_melee_*` banks | 1 739, 54, 146 |
| `explosions` | any bank's event whose sounds play on the game's own `explosion` mixer bus | 126 |
| `stratagems`, `vehicles` | `stratagems_*`, `vehicle_*` | 443, 330 |
| `enemies` | `bots_*`, `cyborg_*`, `bugs_*`, `illuminates_*`, the factions' weapons and foley (`faction` field) | 1 439 |
| `seaf`, `objectives`, `hazards` | `seaf_*`, `obj_*`, `haz_*` | 69, 1 064, 54 |
| `ambience`, `foley`, `gore` | `env_*`, `foley_*`, `gore_*` | 770, 228, 219 |
| `voice`, `ui`, `music` | `vo_*` and the exertion banks, `ui_*`, `music_*` | 1 789, 859, 169 |
| `cinematics`, `system`, `other` | cutscenes and tutorial, the Init banks, the rest | 135, 280, 117 |

```lua
for _, e in ipairs(hd2.sounds.list({catalogue = 'events', family = 'enemies', faction = 'automaton', kind = 'loop'})) do
    mod:log(e.name .. ' ' .. tostring(e.range_m))
end
local e = hd2.sounds.describe('ambience/env_shared/env_sludge_bubbling')
-- {name = 'ambience/env_shared/env_sludge_bubbling', catalogue = 'events', family = 'ambience', bank = 'env_shared',
--  banks = {'env_shared'}, kind = 'loop', range_m = 32, positional = true, bus = 'passthrough__master/environment',
--  effects = {}, wwise_name = 'env_sludge_bubbling', weapons = {}, resident_only = true,
--  parameters = {'occlusion', '0x18E562C4', '0xDEB3DCA2', 'obstruction'}, volume_parameters = {}, switch_groups = {},
--  state_groups = {'0x1C3CE268', '0x6ABF163E'}}
```

- `hd2.sounds.list(filter)`: without `catalogue` the weapon firing sounds, exactly as before. `{catalogue = 'events',
  family, kind ('one_shot' | 'loop' | 'unknown' | 'control'), bank, faction, bus (a part of the bus path), stratagem
  (true | a name), resident_only, named, weapon (true | a firing-sound name), global (has a global effect), text}`;
  `{catalogue = 'all'}` lists both (each with the keys it supports). An invalid filter raises an error naming it.
- `hd2.sounds.describe(name)`: a firing sound, else a sound event by its catalogue name or its own Wwise name.
- Fields of an event: `kind` from the game's own metadata (`loop` = infinite: stop it; `control` = it plays nothing:
  a stop, a state or a switch); `range_m` its maximum attenuation; `duration_s` a one-shot's longest duration;
  `positional` 3D or 2D; `bus` the named mixer bus; `weapons` the firing sounds that post it; `stratagem` / `item`
  the package that provides its bank, or `resident_only`; `parameters` (and `volume_parameters`, those that drive its
  volume), `switch_groups`, `state_groups` it reacts to; `global_effect` (below).
- `hd2.sounds.parameters()`, `switch_groups()`, `state_groups()`: the sound engine's 565 game parameters (RTPCs, 141
  named: `rounds_fired`, `occlusion`, `vehicle_rpm`, ...), 99 switch groups (`materials`, `avatar_armor_weight`,
  `hit_level`, ...) and 86 state groups, with their values; an unnamed one is `'0x<id>'`.
- `sdk/SoundEventCatalogue.json` holds the same for tools (ModBuilder).

## What can be played

| event | posts |
| --- | --- |
| a firing-sound name (`'support/mg206'`, `'sentry/gatling'`, ...) | a `shot` entry's per-shot event; a `loop` entry's loop start (stop it with `handle:stop()`) |
| a sound event's catalogue name | that event (its own Wwise name, or a generated name hashing to its id) |
| `'ui/<key>'` | the loadout screen's own events: `ui/stratagem_pick`, `ui/picker_close`, `ui/slot_select`, `ui/generic_select`, `ui/item_hover_select` |
| any Wwise event name | that event, hashed by the sound engine as it hashes every name |
| `{id = 0x...}` | the event with that 32-bit id |

- `hd2.sounds.available(event)`: whether the sound engine knows the event now (its bank is loaded); nothing is posted.
- `hd2.sounds.asset(name)`: a catalogue sound (either catalogue) as an asset target. `hd2.require_assets{targets =
  {...}}` loads its bank's package through the game's own package system: the call-in package of the stratagem the
  catalogue names (`stratagem`), else the loadout item's own package (`item`; for example a primary weapon's banks).
  A `resident_only` sound has no such package and is refused; it plays only while the game has a package listing its
  bank resident (an enemy's in a mission against that faction).
- A MIDI weapon's shot (`midi = true`) is played by its weapon as notes; posted as one event it may be silent or short.
- **Refused: events that would leave the sound engine changed.** 499 events set an engine-wide state, a global game
  parameter, or a global mix change or pause they do not undo themselves (`global_effect = 'persistent'`: most
  `system`, `music` and set-state events). `hd2.sounds.play` refuses them (`GLOBAL_EVENT`), whatever names them
  (catalogue name, Wwise name or id). 120 others only stop one element's instances everywhere
  (`global_effect = 'transient'`) and are allowed.

## Where it plays: `opts`

| opts | source | the sound |
| --- | --- | --- |
| none | the game world's own default source | 2D; shared with the game's own sounds on that source |
| `position = {x, y, z}` | a NEW position source for this post | 3D at that point; the source is this sound's own |
| `position` + `rotation = {x, y, z, w}` | the same, oriented (a quaternion, normalised) | for directional sounds |
| `unit = <engine Unit>` | that unit's own source (made or reused by the plugin) | follows the unit; shared with the game's sounds on that unit |

Sources are not leaked: the plugin's per-world update sweep (0x56000, "mark_delete_sources") frees a position
source in the first update after its last event ends, and a unit's source when the engine reports the unit gone; with
all 4096 source slots taken a post fails cleanly (`NOT_PLAYED`), never overwriting a live slot (research section
"Source lifetime"). Runtime never destroys a source itself.

A `unit` is an engine Unit value the mod holds (from the engine's own API, for example `stingray.World.units`):
Runtime hands out no Unit values, and maps none from its entity handles. The plugin type-tests the value itself (a
deleted unit is refused there); Runtime only checks it is a userdata (a number would be taken as a source id). Only
the unit's root node is used (an arbitrary node index is not range-checked by the plugin).

## Controls on a handle

| call | binding (plugin RVA; arguments read from its code) | on |
| --- | --- | --- |
| `handle:stop()` | `stop_event(world, playing)` 0xDB50 | this instance (the plugin's own id) |
| `handle:pause()`, `handle:resume()` | `pause_event` / `resume_event(world, engine id)` 0xDC70 / 0xDDC0 | this instance |
| `handle:is_playing()` | `is_playing(world, engine id)` 0xE1A0 | true until up to one update after it ends |
| `handle:elapsed()` | `get_playing_elapsed(world, engine id)` 0xE2B0 | seconds played (the engine's play position) |
| `handle:set_parameter(parameter, value)` | `set_source_parameter(world, source, name, value)` 0xD480 | this sound's own source |
| `handle:set_switch(group, switch)` | `set_switch(world, group, switch, source)` 0xE4A0 | this sound's own source |
| `handle:post_trigger(trigger)` | `post_trigger(world, source, name)` 0xE6A0 | this sound's own source |

- **The engine id.** `trigger_event` returns the plugin's own counter id, which `stop_event` takes; `pause_event`,
  `resume_event`, `is_playing` and `get_playing_elapsed` look the sound engine's playing id up instead. Right after the
  post, on the same thread, Runtime reads the plugin's counter map (`[plugin+0x5757E8] + 0x1CE70`, through the plugin's
  own hash; `runtime/wwise_plugin.lua`) and keeps the engine id only when the entry says the post ran now (state 0):
  the map has no lock and belongs to the thread that posts synchronously. A queued post, a shared instance or an
  unreadable record leaves these four refused (`UNPROVEN_ID`; `handle:describe().controls_reason` says why).
- **Own source only.** A game parameter, switch or trigger is set only on a position post's own source. The world's
  default source and a unit's source are shared with the game's own sounds and are refused (`SHARED_SOURCE`).
- Names or `{id = n}`: a parameter, switch group, switch or trigger by its name (any string: the plugin hashes it) or
  by id (posted through its own name when the catalogue has one, else a generated name hashing to the id).
- Changing calls (pause, resume, parameters, switches, triggers) share the mod's budget with posts (32 a second);
  `is_playing` and `elapsed` do not.

**Not offered, and why** (research/docs/wwise-plugin-bindings-F5FEE03DCFDB.md):

- `Wwise.set_state`, `WwiseWorld.set_global_parameter`: engine-wide (the game's music, mix and environment states and
  its global parameters); a mod's value would stay until the game sets its own, and nothing can restore the game's
  value. Read the groups with `hd2.sounds.state_groups()`; set game parameters per sound with `set_parameter`.
- `stop_all`, `pause_all`, `resume_all`, `set_environment`, `set_dry_environment`, `reset_aux_environment`,
  `add/remove_default_listeners`, `set_enabled`: every source of the Game World (the game's own sounds).
- `set_listener`, `set_language`, `load_bank` / `unload_bank`, `set_panning_rule`: the sound engine's listeners,
  language and banks.
- `make_auto_source` / `make_manual_source` / `destroy_manual_source`: a manual source must be destroyed by its owner
  and `destroy_manual_source` checks no source kind (it can destroy the world's default source); a position post
  already gives a sound its own source.
- A per-mod volume: no game parameter drives the volume of every event (property 0 curves exist per event: listed in
  `volume_parameters`, a lead whose direction is not read), and the sound engine's per-object output volume has no
  binding. Set a sound's own volume parameter with `set_parameter` where its event has one.

## How a post is made

The game's Wwise plugin (`bin/plugins/wwise_pluginw64_release.dll`, Wwise SDK 2024.1.9, read from the installed file)
registers the Lua calls (53 functions, 22 constants; registration 0xFD20):

- `stingray.WwiseWorld.trigger_event(wwise_world, name[, source])` (0xD9C0): the name is hashed by `0xD4A70`, the
  sound engine's `GetIDFromString` (FNV-1 32 of the lower-cased name). The source (resolver 0xA6C0): absent = the
  world's default source (an explicit nil counts as present and fails, so Runtime never passes one); a Unit; a
  Vector3 with an optional Quaternion = a new position source; a number = a source id. It returns the playing id and
  the source id.
- `stingray.Wwise.has_event(name)` (0xD810) asks the sound engine whether it knows the event.

Before any call: the world proven, the selector's pins (they cover the Game World offsets), the Game World matched (by
its position in the engine's world array, as `runtime/ui_sound.lua` does), and the **plugin proven**: its image size
and the exact bytes of 320 pinned instructions of every binding Runtime calls and of the counter map
(`domains/wwise_plugin.lua`, `scripts/generate_wwise_plugin.py`; they cover no relocated byte). A changed plugin is
refused (`UNSUPPORTED_BUILD`). Then `has_event` true and the per-mod rate limit.

**Events known only by id.** The binding takes a name, never a number (a number would be hashed as its decimal
text). An id is therefore posted through a name whose FNV-1 is that id: `'hd2runtime_'` and seven characters of
`[a-z0-9_]`, found by meet-in-the-middle (`runtime/wwise_names.lua`). The names of all 11 274 ids the catalogues hold
(every event, and every unnamed game parameter, switch and state) are generated at build time by running that same
code offline (`scripts/generate_sound_event_names.py` -> `domains/sound_event_names.lua`), so a catalogue sound never
searches in game; any other id takes about 40 ms the first time and is cached for the session.
`hd2.sounds.name_for(id)` returns the name.

## Banks

`Wwise.load_bank(name)` exists in the plugin (`0xB440`) but only loads a bank whose resource is already resident, by
its resource **name** (hashed with the resource system's 64-bit hash). So a bank is made available by loading a package
that lists it, which is what `hd2.sounds.asset` and `hd2.require_assets` do. Whether a package being resident always
means its bank is loaded into the sound engine is not live-proven yet; `hd2.sounds.available` answers it for one event.

## Results

`hd2.sounds.play(event, opts)` returns a handle `{state = 'playing', playing, event, name, kind, owner}` with the
methods above, or nil, a code and a reason, with nothing posted:

| code | why |
| --- | --- |
| `UNKNOWN_EVENT` | not a catalogue name, `ui/` key, event name or `{id}` |
| `GLOBAL_EVENT` | the event would leave the sound engine changed |
| `INVALID` | a bad position, rotation or unit, or a rotation without a position |
| `RATE_LIMITED` | more than 32 posts and changing calls in a second by this mod |
| `NO_API` | the engine's Wwise Lua API is missing |
| `UNAVAILABLE`, `UNSUPPORTED_BUILD`, `NO_WORLD` | the game world, its Game World or the plugin cannot be proven |
| `NO_EVENT` | the sound engine does not know the event (its bank is not loaded) |
| `NOT_PLAYED`, `FAILED` | the sound engine did not post it |

A handle's calls return true (or their value), or nil, a code and a reason: `STOPPED` (after `stop()`),
`SHARED_SOURCE`, `UNPROVEN_ID`, `INVALID`, `RATE_LIMITED`, `ENDED` (`elapsed()` of a sound the engine no longer
plays), and the codes above.

Tests: `tests/test_sound_events.py`, `tests/test_sound_catalogue.py`.
