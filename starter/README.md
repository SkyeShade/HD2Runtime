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

`requires.hd2runtime.min_version` is `0.25.0`. This starter ships with 0.50.0. Raise it:
- to `0.25.1` for in-game options (see below);
- to `0.26.0` for anything new in 0.26.0: magazine reload and ergonomics, reticles, fire modes, vehicle weapons,
  stratagem mission uses, backpack ammo and pod payloads;
- to `0.27.0` for throwables (`hd2.throwable`), `hd2.require_assets`, or a reference swap that relies on automatic
  asset loading (an item nobody carries);
- to `0.28.0` for anything new in 0.28.0 (`docs/releases/0.28.0.md`):
  - events and actions (`hd2.events`, `hd2.mod`, timers, keys, `hd2.actions`);
  - `hd2.attack_output`, projectile sources and slots, programmable ammo;
  - rate-of-fire modes, feeds, presentation;
  - underbarrels, enemies and structures, sentries and minefields, equipment packs and Guard Dogs, status slots;
  - `hd2.diagnostics`;
  - projectile lifetime and penetration slowdown on player weapons;
  - the SG-20 Halt's generic feed fields;
- to `0.28.1` for `hd2.diagnostics.operations()`;
- to `0.30.0` for anything new in 0.30.0 (`docs/releases/0.30.0.md`): custom stratagems (`hd2.custom_stratagem`),
  weapon variants, armor stats and passives (`hd2.armor_stats`, `hd2.player_passives`), `hd2.helldiver()`, the
  explosion catalogue, game sounds and icons, screen overlays and the other fields and services new in 0.30.0;
- to `0.31.0` for anything new in 0.31.0 (`docs/releases/0.31.0.md`): `hd2.inspect`, status effect stats
  (`hd2.status_effect`), `hd2.ui.unsupported`, beam swaps and beam conversion, the wind-up and beam pulse fields,
  missile fields, team-reload ammunition, mounted spread and the EXO-55 Breakthrough shield arm, the Breaching Hammer
  blast, stratagem charges (`stratagem.rearm_pool`), orbital targeting and the fire-mode selector on single-mode
  weapons;
- to `0.31.1` for anything new in 0.31.1 (`docs/releases/0.31.1.md`): the `bughole_destroyed` event,
  `hd2.ui.open_settings` / `close_settings` / `settings_open` / `language`, the P-2 Peacemaker and P-19 Redeemer
  rounds, missile direct-hit damage (Spear, Commando, W.A.S.P.) and the AC-8 flak, GR-8 HE and RL-77 cluster rows;
- to `0.31.2` for anything new in 0.31.2 (`docs/releases/0.31.2.md`): `hd2.text` and `target:display_name()`, every
  empty status slot up to slot 4, impact and expiry payloads on support weapons, the payload options
  (`hd2.explosions.payload_options`, `terminal:payload_options`), `hd2.attack_output(id):stats()` /
  `:owner_projectile()`, `heat.cool_per_second_overheated`, the LAS-99 Quasar and RS-422 Railgun projectile swaps,
  the `acid_storm` status, the RL-77 `bomblet` explosion alias and custom stratagem texts in every language. Above the
  ammunition maxima (2047 rounds, 31 magazines), a mod that declares 0.31.2 is refused, not clamped;
- to `0.31.3` for anything new in 0.31.3 (`docs/releases/0.31.3.md`): the LAS-22 Shear (`hd2.weapon('LAS-22 Shear')`),
  the EXO-55 Breakthrough cannon's `rounds.*` fields and the FX-12 Shield Generator Relay's `shield.recharge_rate`,
  `recharge_delay` and `broken_recharge_delay`. A mod that declares 0.31.3 needs `allow_shared=true` for the LAS-5
  Scythe's `beam.length`, `beam.radius` and `damage.*` fields (shared with the Shear);
- to `0.40.0` for anything new in 0.40.0 (`docs/releases/0.40.0.md`): enemy controls and spawning (`hd2.enemies`),
  mission timers (`hd2.mission`, `hd2.freeze_mission_timer`), reload, heat and melee (`hd2.melee`) controls, throwable
  statuses, armor perks and `hd2.input.bind(..., {native = ...})`;
- to `0.40.1` for anything new in 0.40.1 (`docs/releases/0.40.1.md`): more than 16 custom stratagems and
  `hd2.diagnostics.save_application_optimizations`. In 0.40.1 the armor class tables and damage curve are read only.
- 0.50.0 adds no API: it runs the same mods on HellForge (`docs/releases/0.50.0.md`), so no mod needs to raise it.

`min_version` is also the SDK version your mod declares. HD2Runtime 0.28.1 and later accept a field that gained an
acknowledgement in a later SDK without it, as a logged legacy operation, when your mod declares an older version
(`docs/legacy-sdk-compatibility.md`). Raise `min_version` and add the acknowledgements the SDK catalogs ask for to
get the current rule.

In-game options (`hd2.options`) and the Booster `tuning()`, `explosion()`,
`status_damage()` and `granted_stratagem()` targets need 0.25.0. Boosters
(`hd2.booster`), the `reload.*`, `windup.*`, `projectile.lifetime`,
and `projectile.penetration_slowdown` fields on support weapons, and writes to MG-43, M-105, MG-206,
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

This needs HD2Runtime 0.25.1+ (raise `min_version`). CowboyBingus Mod Options Menu v1+
(which needs Bingus Shared Loader v18+) is an optional dependency. Add

```json
"optional": {"mod_options_menu": {"min_version": "1.0.0", "api": 1, "bingus_min_release": 18}}
```

to `hd2runtime.json` and leave `requires` unchanged. Players without the menu get one
warning, and the operation bound to the option runs with its declared default (use
`fallback='disable'` on the options page to keep it inactive instead); operations without options
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

The finished package is written to `build/<name>-<VERSION>.zip`. When a
double-clicked build fails, its window stays open on the error until you press
a key. `build.cmd` starts Windows PowerShell with a process-scoped execution-policy bypass; it does
not change the machine policy. The builder reads only `src/addon.lua` and creates
one gameplay resource. It does not package `stubs`, build scripts, Python, or any
HD2Runtime implementation.

## Install and dependencies

Players install and enable three packages:

1. Bingus Shared Loader v15 or newer / API 1.
2. HD2Runtime 0.25.0 or newer / API 1 (0.50.0 recommended; on HellForge, 0.50.0 is needed), installed once.
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
