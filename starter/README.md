# HD2Runtime standalone mod starter

This folder is ready to open directly in Rider. It builds a Helldivers 2 gameplay
mod with Windows PowerShell and the .NET Framework already included with Windows.
Python, the HD2Runtime source checkout, and a local game installation are not
needed. The default example uses the typed player-weapon API to raise the
AR-23C Liberator Concussive fire rate from 400 to 1100 through an external
HD2Runtime installation.

New to HD2Runtime? Read `docs/getting-started.md` in the HD2Runtime SDK ZIP first.
It walks through targets, fields, `expect`, safety flags, and logs step by step.

## First setup

Before distributing your mod, edit these exact values:

1. In `hd2runtime.json`, change `name` from `My HD2 Mod` to the display name.
2. In `hd2runtime.json`, change `resource` from
   `mods/your_name/my_hd2_mod` to a globally unique `mods/author/mod_id`.
   Use only ASCII letters, digits, and underscores in each segment. This is the
   mod ID and must stay unchanged across releases.
3. In `src/addon.lua`, change `id='my-hd2-mod-fire-rate'` to a short identifier
   unique within your mod. Replace the example declaration with your own public
   HD2Runtime calls when ready.
4. Update `VERSION` for releases using `major.minor.patch`, starting at `0.1.0`.

`guid` defaults to `auto`; the builder derives a stable manager GUID from the
resource ID, so it changes when you rename the resource and remains stable after
that. You may replace `auto` with your own non-zero UUID, then keep it forever.

`requires.hd2runtime.min_version` is `0.25.0`, the release this starter ships
with. In-game options (`hd2.options`) and the Booster `tuning()`, `explosion()`,
`status_damage()` and `granted_stratagem()` targets need 0.25.0. Boosters
(`hd2.booster`), the `reload.*`, `windup.*`, `projectile.lifetime`,
and `projectile.penetration_slowdown` fields, and writes to MG-43, M-105, MG-206,
and CQC-20 need 0.24.0. A mod that uses none of these may lower it to `0.23.2`,
but never below: in 0.23.0 and 0.23.1, typed writes can fail in game with "module
not found". Do not change the `bingus` block or the `api`/`module` values.

## In-game options

To let players tune your mod from the in-game MODS tab, declare options with
`hd2.options` and pass a slider as the ensured `value` (or a toggle as `enabled`):

```lua
local options=hd2.options({id='my_hd2_mod',title='My HD2 Mod'})
local rate=options:slider({id='rate',label='Fire Rate',min=400,max=1100,step=50,default=1100})
return hd2.ensure({patch={id='my-hd2-mod-fire-rate',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=rate}})
```

This needs HD2Runtime 0.25.0+ (raise `min_version`). CowboyBingus Mod Options Menu v1+
(which needs Bingus Shared Loader v18+) is an optional dependency. Add

```json
"optional": {"mod_options_menu": {"min_version": "1.0.0", "api": 1, "bingus_min_release": 18}}
```

to `hd2runtime.json` and leave `requires` unchanged. Players without the menu get one
warning, and the operation bound to the option stays inactive; operations without options
still run. `expect` stays the vanilla value, and safety flags are still required. See
`docs/options.md` in the SDK ZIP.

## Open in Rider

Open this extracted folder itself, not its parent. The checked-in `.luarc.json`
points Lua language tooling at `./stubs`. The bundled authoring-only stub provides
autocomplete for all currently mapped HD2Runtime domain types, builder chains,
`hd2.fields.*`, enums, request types, and public APIs.

Rider needs Lua language tooling enabled. LuaLS integrations read `.luarc.json`
directly. If an EmmyLua-style plugin does not, mark the `stubs` directory as a
library/content root in Rider. The stub is metadata and must remain outside `src`.
It is never included in the built gameplay ZIP.

## Edit and build

Edit only `src/addon.lua` for normal gameplay work. The runtime dependency stays:

```lua
local hd2=require('mods/skyeshade/hd2runtime')
```

Take weapon, vehicle, stratagem, and backpack names, field constants, and
`expect` values from the SDK capability files (`*Capabilities.json`). `expect`
is the reviewed vanilla value (`currentDefault`); never guess it. Add
`allow_shared`, `allow_unverified_effect`, or `allow_unverified_reference` only
when the capability file says that field requires it.

Build by double-clicking `build.cmd`, or from a terminal:

```powershell
.\build.cmd
# or
.\build.ps1
```

The finished package is written to `build/<name>-<VERSION>.zip`. `build.cmd`
starts Windows PowerShell with a process-scoped execution-policy bypass; it does
not change the machine policy. The builder reads only `src/addon.lua` and creates
one gameplay resource. It does not package `stubs`, build scripts, Python, or any
HD2Runtime implementation.

## Install and dependencies

Players install and enable three packages:

1. Bingus Shared Loader v15 or newer / API 1.
2. HD2Runtime 0.25.0 or newer / API 1, installed once.
3. Your built gameplay mod ZIP.

The generated manifest description and `hd2runtime.json` state both dependencies.
The generated Lua checks them before starting and explicitly requires HD2Runtime,
so gameplay mods do not need manual priority ordering among themselves. Current
mod managers do not automatically download these dependencies.

The starter contains no deployment command and does not launch HD2. Import the
finished ZIP through the mod manager workflow you already use. Do not install the
starter project or its `stubs` folder into the game.

## Test a rebuild

Bingus Shared Loader discovers mods once, at game startup, and has no hot reload.
After every rebuild:

1. Import the new ZIP into your mod manager, replacing the old one.
2. Purge and redeploy.
3. Restart Helldivers 2.

Logs are written to `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\`:

- `BingusSharedLoader.log` shows whether your mod was discovered and started, and
  any error raised while it loads (including requests the runtime rejects).
- `HD2Runtime.log` shows what the runtime did. Look for lines such as
  `ensure my-hd2-mod-fire-rate verified status=APPLIED` or
  `REJECTED code=CONFLICT`.

Advanced authors can use the separate HD2Runtime SDK CLI for offline inspection,
project generation, multi-file projects, and automated builds. This standalone
starter is the recommended beginner path.
