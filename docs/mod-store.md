# Saved mod data (`hd2.store`)

A small key/value table each mod keeps between game sessions: high scores, a wallet, settings that are not Mod
Options Menu options. Implementation: `runtime/mod_store.lua`.

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
local store = hd2.store()                  -- or hd2.mod():store()

local best = store:get('high_score', 0)
store:set('high_score', math.max(best, score))
store:set('wallet', {credits = 120, history = {5, 10, 105}})
store:save()                               -- optional: writes now instead of a second later
```

- **One file per mod**: `%LOCALAPPDATA%\HD2Runtime\mod_data\<mod id with / as _>.json` (for example
  `mods_author_arcade.json`). A mod only ever opens its own store: the owner is read the way `hd2.mod()` reads it
  (the SDK wrapper's scope, the running callback's mod, or the mod's own chunk). Called where no mod can be told, it
  raises.
- **Values**: booleans, finite numbers, strings, and tables of those: arrays (1..n) or string-keyed maps, no cycles,
  at most 16 deep. `set(key, nil)` removes a key. A value that cannot be saved raises at `set` and changes nothing.
  Keys are 1-128 characters.
- **Copies**: a table is copied on `set` and on `get`, so the saved data changes only through `set`.
- **Saving**: `set` and `clear` save the store about one second later (one write for a burst of changes); `save()`
  writes at once and returns `true`, or `false` and the reason (logged; the previous file is kept). The file is
  written to `<name>.tmp` and then moved over the old file, so a crash mid-write keeps the previous save; a `.tmp` left
  behind is used only when the file itself is missing.
- **Limits**: 1 MiB per file, 4096 keys.
- **A damaged file** (not valid JSON) is moved aside to `<name>.corrupt`, logged once, and the store starts empty.
- `store:keys()`, `store:clear()`, `store:describe()` (`{owner, keys, dirty, saved, file, load_error}`).

The files are plain JSON: a mod's data can be inspected or reset by deleting its file while the game is closed.

Tests: `tests/test_scripting_services.py`.
