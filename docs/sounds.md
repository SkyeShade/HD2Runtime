# Playing game sounds (`hd2.sounds.play`)

A mod plays the game's own sound events through the game's sound engine, so they follow the game's volume settings
and mix. Implementation: `runtime/sound_events.lua`; API: `api/sounds.lua`. The weapon firing-sound catalogue the
names come from is [weapon-sounds.md](weapon-sounds.md). **Offline-tested only; not live-tested yet.**

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

-- A UI click the loadout screen itself makes.
hd2.sounds.play('ui/generic_select')

-- A weapon's shot at a world position (its bank must be loaded: warm it up once).
hd2.require_assets({id = 'arcade-sounds', targets = {hd2.sounds.asset('support/ac8')}})
local p = hd2.local_player():position()
hd2.sounds.play('support/ac8', {position = {p.x, p.y, p.z}})

-- A loop runs until stopped.
local loop = hd2.sounds.play('sentry/gatling')
hd2.after(2, function() if loop then loop:stop() end end)
```

## What can be played

| event | posts |
| --- | --- |
| a catalogue name (`'support/mg206'`, `'sentry/gatling'`, ...) | a `shot` entry's per-shot event; a `loop` entry's loop start (stop it with `handle:stop()`) |
| `'ui/<key>'` | the loadout screen's own events: `ui/stratagem_pick`, `ui/picker_close`, `ui/slot_select`, `ui/generic_select`, `ui/item_hover_select` |
| any Wwise event name | that event, hashed by the sound engine as it hashes every name |
| `{id = 0x...}` | the event with that 32-bit id (below) |

- `hd2.sounds.available(event)`: whether the sound engine knows the event now (its bank is loaded); nothing is posted.
- `hd2.sounds.asset(name)`: a catalogue sound as an asset target. `hd2.require_assets{targets = {...}}` loads its
  bank's package through the game's own package system: the call-in package of the stratagem the catalogue names for
  it (`stratagem` in `hd2.sounds.describe`). A `resident_only` sound has no such package and is refused; it plays only
  while the game has a package listing it resident.
- A MIDI weapon's shot (`midi = true`) is played by its weapon as notes; posted as one event it may be silent or
  short. Prefer `shot` entries without MIDI, or loops, for one-off sounds.

## How a post is made

The game's Wwise plugin (`bin/plugins/wwise_pluginw64_release.dll`, read from the installed file) registers the Lua
calls the Runtime's own UI sounds already use:

- `stingray.WwiseWorld.trigger_event(wwise_world, name[, position])` (plugin `0xD9C0`): the name is hashed by
  `0xD4A70`, the sound engine's `GetIDFromString` (FNV-1 32 of the lower-cased name). Without a position the event
  plays on the world's own default source (2D); a `Vector3` position makes it a 3D sound there (the source resolver
  `0xA6C0` also takes a unit). It returns the playing id.
- `stingray.WwiseWorld.stop_event(wwise_world, playing_id)` (`0xDB50`) stops one playing instance.
- `stingray.Wwise.has_event(name)` (`0xD810`) asks the sound engine whether it knows the event.

Every post goes to the WwiseWorld of the game's own Game World (matched by its position in the engine's world array,
as `runtime/ui_sound.lua` does), only after the build's pins prove, the API is callable and `has_event` is true. Each
mod may post at most 32 sounds a second.

**Events known only by id.** The binding takes a name, never a number (a number would be hashed as its decimal
text). An event id is therefore posted through a name whose FNV-1 is that id: `'hd2runtime_'` and seven characters of
`[a-z0-9_]`, found by meet-in-the-middle (the states three characters forward from the prefix against four characters
backward from the id; about 22 matches expected, the first in alphabet order taken, so the name is stable;
`runtime/wwise_names.lua`). The names of all 182 events the catalogue holds are generated at build time by running
that same code offline (`scripts/generate_sound_event_names.py` -> `domains/sound_event_names.lua`), so a catalogue
sound never searches in game; any other id takes about 40 ms the first time and is cached for the session.
`hd2.sounds.name_for(id)` returns the name. The Runtime's UI sounds were posted this way already
(`hd2runtime_u64dawv` is the pick sound's id).

## Banks

`Wwise.load_bank(name)` exists in the plugin (`0xB440`) but only loads a bank whose resource is already resident, by
its resource **name** (hashed with the resource system's 64-bit hash); the game's bank names are not recoverable from
its data. So a bank is made available by loading a package that lists it, which is what `hd2.sounds.asset` and
`hd2.require_assets` do. Whether a package being resident always means its bank is loaded into the sound engine is
not live-proven yet; `hd2.sounds.available` answers it for one event.

## Results

`hd2.sounds.play(event, opts)` returns a handle `{state = 'playing', playing, event, name, kind, owner}` with
`handle:stop()`, or nil, a code and a reason, with nothing posted:

| code | why |
| --- | --- |
| `UNKNOWN_EVENT` | not a catalogue name, `ui/` key, event name or `{id}` |
| `INVALID` | a bad position |
| `RATE_LIMITED` | more than 32 posts in a second by this mod |
| `NO_API` | the engine's Wwise Lua API is missing |
| `UNAVAILABLE`, `UNSUPPORTED_BUILD`, `NO_WORLD` | the game world or its Game World cannot be proven |
| `NO_EVENT` | the sound engine does not know the event (its bank is not loaded) |
| `NOT_PLAYED`, `FAILED` | the sound engine did not post it |

Tests: `tests/test_sound_events.py`.
