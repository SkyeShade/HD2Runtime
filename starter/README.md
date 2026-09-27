# HD2Runtime standalone mod starter

This folder is ready to open directly in Rider. It builds a Helldivers 2 gameplay
mod with Windows PowerShell and the .NET Framework already included with Windows.
Python, the HD2Runtime source checkout, and a local game installation are not
needed. The default example safely requests the gameplay-proven JAR-5 AP3 to AP4
patch through an external HD2Runtime installation.

## First setup

Before distributing your mod, edit these exact values:

1. In `hd2runtime.json`, change `name` from `My HD2 Mod` to the display name.
2. In `hd2runtime.json`, change `resource` from
   `mods/your_name/my_hd2_mod` to a globally unique `mods/author/mod_id`.
   Use only ASCII letters, digits, and underscores in each segment. This is the
   mod ID and must stay unchanged across releases.
3. In `src/addon.lua`, change `id='my-hd2-mod-jar5-ap4'` to a short identifier
   unique within your mod. Replace the example declaration with your own public
   HD2Runtime calls when ready.
4. Update `VERSION` for releases using `major.minor.patch`, starting at `0.1.0`.

`guid` defaults to `auto`; the builder derives a stable manager GUID from the
resource ID, so it changes when you rename the resource and remains stable after
that. You may replace `auto` with your own non-zero UUID, then keep it forever.
Do not change `requires` unless HD2Runtime publishes a newer API contract.

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
2. HD2Runtime 0.15.0 or newer / API 1, installed once.
3. Your built gameplay mod ZIP.

The generated manifest description and `hd2runtime.json` state both dependencies.
The generated Lua checks them before starting and explicitly requires HD2Runtime,
so gameplay mods do not need manual priority ordering among themselves. Current
mod managers do not automatically download these dependencies.

The starter contains no deployment command and does not launch HD2. Import the
finished ZIP through the mod manager workflow you already use. Do not install the
starter project or its `stubs` folder into the game.

Advanced authors can use the separate HD2Runtime SDK CLI for offline inspection,
project generation, multi-file projects, and automated builds. This standalone
starter is the recommended beginner path.
