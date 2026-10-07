# HD2Runtime SDK and shared runtime

For a first mod, use `HD2Runtime-ModTemplate-0.30.0-dev.zip` (the 0.30.0 development line). It is a standalone
open-folder Rider project with bundled stubs and a Windows builder; Python is not
required. The CLI workflow below remains available for advanced authors and
automated project generation. New authors should start with
[docs/getting-started.md](docs/getting-started.md).

The SDK includes generated attachment, projectile-composition, explosion,
fire-mode, and terminal-action capability catalogs. They describe typed reference
classes, linked settings, shared consumers, and shrapnel without runtime addresses;
see `docs/player-weapon-composition.md` for the guarded APIs.
`CompositionPlanCapabilities.json` describes multi-target grouping, ordered
phase dependencies, `target_from` paths, and per-operation shared scope. Field
editability remains canonical in `PlayerWeaponAuthoringCapabilities.json`.
`BoosterAuthoringCapabilities.json` publishes the 20 boosters (all uniquely identified from game.dll's
own enum-name table), their implementation mechanism, native relationship graph, 42 writable field
instances across 19 boosters with value ranges, and exact blocked reasons; see `docs/booster-authoring.md`.
`SupportWeaponAuthoringCapabilities.json` covers 31 writable support weapons with 970 field
instances, including `reload.duration`, `projectile.lifetime`, `projectile.penetration_slowdown`,
and Maxigun `windup.*`, plus `DELIVERY_RESOLVED` identities for MG-43, M-105, MG-206, and CQC-20;
see `docs/support-weapon-api.md`.
`StratagemAuthoringCapabilities.json` is the canonical per-instance contract for
offensive, support-call-in, sentry, emplacement, and deferred mine authoring; see
`docs/stratagem-authoring.md`.
`WeaponSoundCatalogue.json` (0.30.0-dev) lists the weapon firing sounds `hd2.sounds` names (a Pelican gun's
`sound`): each sound's name, label, kind (shot or loop), family, the stratagem whose package provides it or
resident-only, its designed rate and a heuristic range. No Wwise event, bank or package id; see `docs/weapon-sounds.md`.
`hd2.projectiles.homing(weapon, opts)` (0.30.0-dev, not live-tested) makes the local player's own shots of a weapon
home on enemies or other players in flight; see `docs/projectile-homing.md`.

Attachment preset research is split into `AttachmentPresetGraph.json`,
`AttachmentSelectionCapabilities.json`, and `AttachmentEffectOwnership.json`.
These distinguish static resource defaults from current selections, saved
presets, and effect owners. Attachment selection is not writable. Magazine
ammo values are writable on the magazine attachment definitions themselves, with
`allow_shared` and `allow_unverified_effect`; `MagazineAttachmentCapabilities.json`
supersedes the older ammo-owner fields in `AttachmentOptionCapabilities.json`. See
`docs/magazine-attachments.md` and `docs/attachment-preset-research.md`.

0.28.1 keeps SDK 0.27-era mods working: a field that gained `allow_unverified_effect` in 0.28.0 is accepted without
it, as a logged legacy operation, from a mod that declares an older SDK (`docs/legacy-sdk-compatibility.md`).
Mods that declare 0.28.0 or later keep the rule. `hd2.diagnostics.operations()` lists every registered operation
(`docs/diagnostics.md`). See `docs/releases/0.28.1.md`.

0.28.0 adds event-driven gameplay scripting (`EventCatalog.json`; `docs/event-scripting.md`, `docs/events.md`) and one
projectile system (`AttackOutputCapabilities.json`: hosts, donors, projectile builder slots and live-proven values;
`docs/attack-outputs.md`). It also adds:
- enemies and structures (`EnemyAuthoringCapabilities.json`) and statuses (`StatusEffectCatalog.json`);
- underbarrel sub-targets (`PlayerWeaponAuthoringCapabilities.json` `subweapons`);
- mounted projectile hosts (`VehicleWeaponCapabilities.json`);
- runtime diagnostics (`hd2.diagnostics`; `docs/diagnostics.md`);
- the live-evidence catalog (`LiveEvidenceCatalog.json`).

See `docs/releases/0.28.0.md`.

0.27.0 adds automatic asset loading for cross-package reference swaps (`hd2.require_assets`,
`hd2.asset_dependency`, `AssetDependencyCapabilities.json`; see `docs/asset-loading.md`) and throwable
authoring (`hd2.throwable`, `ThrowableAuthoringCapabilities.json`; see `docs/throwable-authoring.md`). Package
IDs never appear in the SDK. See `docs/releases/0.27.0.md`.

0.26.1 corrects the examples and templates to the current typed API and validates every shipped example against
this SDK on each release (see `docs/releases/0.26.1.md`). Damage and armor penetration belong to
`weapon:attack('primary'):projectile()`; `PlayerWeaponAuthoringCapabilities.json` now lists each field's Lua
constant in `apiFieldConstant`.

Also new in 0.28.0 (see `docs/fire-rate-modes.md`, `docs/weapon-feeds.md` and `docs/weapon-presentation.md`):

- **Rate-of-fire modes.** `WeaponFireRateCapabilities.json`: every weapon's three native rate slots in weapon-menu
  order `{X, Y, Z}` (each mode with its slot, menu position and selector presses), the selector binding, `maxModes`
  (3) and writability (60 writable). `hd2.fields.fire_rate.modes` with `hd2.fields.weapon_function.left/right`.
- **Feeds.** `WeaponFeedCapabilities.json`: rounds magazines (SG-20 Halt) and the ProgrammableAmmo projectile a
  weapon can host (`hd2.fields.function_ammo.projectile`), with the binding each needs and each feed's native mode
  label and icon. Mode labels and icons are written on attack outputs (`AttackOutputCapabilities.json`
  `modePresentation`: `hd2.fields.presentation.mode_label` / `mode_icon`), which also list the stratagem-owned EMS
  Mortar shell donor.
- **Presentation.** `WeaponPresentationCapabilities.json`: the armory trait labels, penetration display choices and
  per-weapon writability (`hd2.fields.presentation.armor_penetration`, `hd2.fields.presentation.traits`).
- **Output composition.** `OutputCompositionCapabilities.json`: why a projectile weapon cannot fire a beam, blocker
  by blocker.

New in 0.26.0 (see `docs/releases/0.26.0.md`):

- **Attachment catalog.** `WeaponAttachmentCatalog.json` holds read-only metadata for all 241 customization
  items. `MagazineAttachmentCapabilities.json` covers all 49 resolved magazine options, with reload and
  ergonomics fields.
- **Fire modes.** `WeaponFireModeCapabilities.json` has native fire-mode sets for 115 weapons (61 writable;
  `docs/fire-modes.md`). Third-person reticles are covered in `docs/weapon-reticles.md`.
- **Vehicle weapons.** `VehicleWeaponCapabilities.json` covers 18 vehicle and Exosuit weapon mounts
  (480 fields; `docs/vehicle-weapons.md`).
- **Stratagem uses.** `StratagemAuthoringCapabilities.json` publishes `maxUses` for 85 editable stratagems
  (`docs/stratagem-uses.md`).
- **Backpack ammo.** `BackpackAuthoringCapabilities.json` and `SupportWeaponAuthoringCapabilities.json` link
  the three backpack-fed weapons to their ammunition backpacks (`docs/backpack-ammo.md`).
- **Pod payloads.** `PodPayloadCapabilities.json` covers 56 hellpod racks (192 writable slots), the typed
  replacement pickup catalog, and package-risk metadata (`docs/pod-payloads.md`).

Install Bingus Shared Loader v15+ / API 1, then import the separate
`HD2Runtime-0.30.0-dev-runtime.zip` into your mod manager and enable it once. Each
gameplay mod is its own package. The runtime contains no enabled gameplay preset,
report addon or timer on load. It loads its guarded adapters only when requested.

The SDK ZIP is authoring software. Extract it outside the game's deployed data,
for example `HD2Tools/HD2RuntimeSDK`. Do not install it as a gameplay mod, copy its
stubs into a mod's `src`, or package it with every gameplay addon.

## Author a mod

Python 3.10+ is sufficient for the SDK tools; neither the game nor a Lua VM is
required to inspect, generate or build an independent project.

```powershell
python C:/HD2Tools/HD2RuntimeSDK/hd2.py new MyMod --name mods/my_author/my_mod
cd MyMod
python build.py
python -m unittest discover -s tests -v
```

The default template (`--template fire_rate`) is the ModTemplate's weapon fire-rate patch. Use
`--template projectile_damage` for the AR-23 Liberator projectile damage and armor-penetration
transaction. Both use the typed catalogs (full names and field constants from the capability files) and
are validated against the current SDK on every release, like the example projects. The generated entrypoint contains only public API calls;
the runtime owns all timers, resolution, memory access and protection changes.
Reusing a resource name intentionally reuses its stable mod GUID. Choose a unique
author/mod path for each independently distributed mod.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
-- Damage is owned by the projectile: weapon -> attack('primary') -> projectile().
local projectile=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()
return hd2.ensure({transaction={id='liberator-damage',target=projectile,allow_shared=true,changes={
    {field=hd2.fields.damage.player_standard_damage,expect=90,value=120},
    {field=hd2.fields.damage.player_durable_damage,expect=22,value=35},
    {field=hd2.fields.damage.ap_direct,expect=2,value=3},
    {field=hd2.fields.damage.ap_slight,expect=2,value=3},
    {field=hd2.fields.damage.ap_large,expect=2,value=3},
    {field=hd2.fields.damage.ap_extreme,expect=0,value=2},
}}})
```

Builds read Lua files only from that project's `src/`. The gameplay ZIP contains
only its own resource namespace, manager manifest, dependency metadata and docs.
No runtime implementation or SDK stubs are embedded. `src/addon.lua` is the entry;
other files become `mods/author/mod_name/<relative-path-without-extension>`.
Require your own extra files at the top of `addon.lua`: the game resolves mod
resources only during startup, so a first `require` from inside a callback that
runs later fails with "module not found".
The builder adds a small dependency check and duplicate-initialization guard.
Keep the source entry free of discovery headers; the builder adds the correct one.
Every build also writes `build/build-report.json` beside the ZIP: the artifact's name and SHA-256, and each
image's source digest and build status.

### Custom stratagems as data (development, 0.30.0-dev)

A project may describe its custom stratagems in `custom_stratagems.json` instead of Lua
(`docs/custom-stratagem-builder.md`). `py hd2.py build` validates it and compiles it into `src/addon.lua`. A
hand-written `src/addon.lua` is never overwritten.

```powershell
python C:/HD2Tools/HD2RuntimeSDK/hd2.py custom-stratagem validate MyMod
python C:/HD2Tools/HD2RuntimeSDK/hd2.py custom-stratagem compile MyMod
```

- `CustomStratagemSchema.json`: every field, its range and default, and the donor catalogues.
- `schemas/custom_stratagems.project.schema.json`: the JSON Schema of the project file.
- `fixtures/custom_stratagems/`: the example mods as project files.

## Inspect mapped fields

```powershell
python <SDK>/hd2.py inspect weapon "JAR-5 Dominator"
python <SDK>/hd2.py inspect type DamageProfile
python <SDK>/hd2.py inspect vehicle Bastion
python <SDK>/hd2.py inspect stratagem "Shield Relay" --json
```

On Windows, add the SDK directory to PATH to use `hd2 inspect ...` through
`hd2.cmd`. The CLI uses `metadata.json` only. Values are schema baselines, never
claimed current memory values. The complete field/evidence and partial enum
catalog is in [api.md](docs/api.md). Read/write access is per resource. The
original fixed-resource catalog retains its narrow contracts, including JAR-5
AP3→AP4 and read-only Orbital Laser fields. `inspect` covers that catalog and the
player-weapon catalog; for support weapons, stratagems, vehicles, backpacks, and
magazine attachments, read the matching `*Capabilities.json` directly. Their
`apiFieldConstant` gives the exact `hd2.fields` constant; for player weapons,
search the stub for the quoted `semanticFieldId`. Unknown semantic ranges are null;
partial enums do not claim completeness or introduce unproven names.

The 80-weapon authoring surface is described separately in
`PlayerWeaponAuthoringCapabilities.json`. It is intended for SDK tools and GUI
control generation, and includes editability, current reviewed defaults, native
backing storage, implementation family, provenance, derived markers, shared
write scope, semantic aliases, and the complete identical-backing collision audit.
Deprecated aliases have `editable=false`, `preferred=false`, an `aliasOf` target,
and an `acceptedForWrites` compatibility flag; GUI controls should render only
preferred editable fields. It contains no runtime addresses. `hd2 inspect weapon <name>` uses
this catalog for player weapons outside the original small live-read catalog.

## The game's HUD icons (r51)

```powershell
python <SDK>/tools/hd2_hud_icons.py <out folder> [--game <Helldivers 2 data folder>] [--kind stratagem|booster|all]
```

This extracts every stratagem's and booster's own HUD icon from the installed game, read-only and locally. It writes
`stratagem/<name>.png`, `booster/<name>.png` and `index.json`. `HudIconSprites.json` names each item's sprite: the
icon member of its StratagemInfo row, or of the native Booster table row. That covers the 94 stratagems with a call-in
and all 20 boosters, including those the loadout screen's vector library leaves unbound or empty (`uiIcon`).
SG-88 and CQC-72 have no call-in stratagem, so they have no icon.

- Stratagem icons are icon masks: R is the category-colour layer and G the white layer, the format `d:image` and
  `images/*.png` use. Booster icons are colour images with alpha.
- The tool uses the standard library only (BC1, BC3, BC4 and 8-bit RGBA pages). The artwork is Arrowhead's: use it in
  your own builds, and publish it only if you may redistribute it.

## Scan a captured process offline

The separate `HD2Runtime-SnapshotCapture-0.7.1.zip` package incrementally writes
a build-bound, read-only process snapshot during one manually started HD2
session. Do not install the SDK ZIP in the game. After capture, use the SDK to
run the production Primary Weapon Runtime Mapper against the saved address
space:

```powershell
python <SDK>/hd2.py snapshot scan-weapons <build>.hd2snap wiki_primary_weapons.json
```

For the combined 55-primary/25-secondary catalog, use:

```powershell
python <SDK>/hd2.py snapshot scan-player-weapons <build>.hd2snap wiki_player_weapons.json
```

This writes `PlayerWeaponRuntimeMap.json`,
`PlayerWeaponRuntimeMap.identity-candidates.json`, and
`player_weapon_identity_summary.json`. The compatibility `scan-weapons`
command continues to accept the original primary-only catalog.

For the graph-aware 35-support-weapon catalog, use:

```powershell
python <SDK>/hd2.py snapshot scan-support-weapons <build>.hd2snap wiki_support_weapons.json
```

This emits `SupportWeaponRuntimeMap.json`, its identity-candidate map, a compact identity summary,
and a log. Snapshot research remains read-only. The installed 0.20 runtime separately consumes
the reviewed `SupportWeaponAuthoringCapabilities.json` schema v2 contract for guarded writes.
GUI and code-generation clients should enumerate its canonical `fieldInstances` collection; the
per-weapon field-name lists are retained only as a compatibility lookup.

The SDK locates HD2's owned `bin/lua51.dll` through `HD2_GAME_ROOT`; pass
`--lua-dll <path>` when needed. The command rejects fingerprints that differ
from the bundled current-build profile. `--historical-analysis` is an explicit
schema research override and does not treat an old capture as current evidence.
See the capture ZIP README for the HD2SNAP v1 format, default output path, and
capture progress fields.

## Rider and Lua tooling

The generated `.luarc.json` points `workspace.library` at the shared SDK `stubs`
directory and selects LuaJIT. The stub uses LuaLS/LuaCATS `@meta`, `@class`,
`@field`, `@param`, `@return` and literal `@alias` annotations, using the shared
EmmyLua-style subset for domain declarations. `HD2Weapon:projectile()` returns
`HD2Projectile`, whose `:damage()` returns `HD2DamageProfile`. `hd2.fields`,
`hd2.enums` and `hd2.resources` provide discoverable constants. Existing string
descriptors remain valid. `hd2.resources.image(id)` names the mod's own image
(`images/<id>.png`, packed by `py hd2.py build`), a value for
`hd2.fields.stratagem.presentation_icon` (docs/custom-images.md).

In Rider, enable Lua language tooling and configure it to index the shared
stub directory. LuaLS integrations read `.luarc.json`; an EmmyLua plugin that
does not read that file needs the same directory added through its library or
content-root configuration. Rider alone does not provide this Lua type system.
This release verifies typed hovers for all 12 mapped domain classes and field /
method completion through the LuaLS 3.19.1 protocol. It does not claim a manually
verified Rider UI session or bundle a language-server binary.
Tooling references: [LuaLS definition files](https://luals.github.io/wiki/definition-files/),
[annotations](https://luals.github.io/wiki/annotations/), and
[workspace.library](https://luals.github.io/wiki/settings/#workspacelibrary).

If you move the SDK or project, regenerate only the local IDE/path settings:

```powershell
python <SDK>/hd2.py configure MyMod --sdk <SDK>
```

The helper preserves unrelated `.luarc.json` settings and other library paths.
Annotations cannot express every reviewed resource/value combination; the
runtime's existing strict validation is authoritative. An unavailable chain,
such as AMR projectile linkage, rejects rather than inventing a mapping.

## Dependencies and loading

`hd2runtime.json` declares `requires.bingus` (release ≥15, API 1) and
`requires.hd2runtime` (version matching the SDK-generated project, API 1, module
`mods/skyeshade/hd2runtime`). Raise `min_version` to the oldest runtime that has
every API your mod calls: vehicles, backpacks, relay shield and damage-zone
fields, and `hd2.support_weapon` need 0.23.0; magazine attachments need 0.23.1. Everything new in
0.26.0 needs 0.26.0:
- the `attachment.reload_duration` and `attachment.ergonomics_modifier` fields, and non-default magazine
  targeting;
- `weapon.third_person_reticle` and `fire_mode.*`;
- vehicle weapons (`vehicle:weapon`);
- writable `stratagem.max_uses`;
- `support_weapon:backpack()` and deposit writes;
- pod payloads (`hd2.pod_rack`, `hd2.pickup`, `payload.*`).
In-game options (`hd2.options`, option-bound `hd2.ensure`; see `docs/options.md`) need 0.25.1 (0.25.0 has no `fallback` and never falls back to defaults). CowboyBingus Mod Options Menu v1+ (with Bingus Shared Loader v18+) is an optional
dependency of such mods only; declare it under `optional.mod_options_menu` in `hd2runtime.json`.
Without the menu, one warning is logged and the operations bound to options run with their
declared defaults (or stay inactive for pages declared with `fallback='disable'`). Other operations, and mods without options, are unaffected.
Boosters and the 0.24 support-weapon fields and identities need 0.24.0 (see
`docs/releases/0.24.0.md`); the Booster `tuning()`, `explosion()`, `status_damage()`, and
`granted_stratagem()` targets need 0.25.0. Mods that use typed writes should require at least
0.23.2; in 0.23.0 and 0.23.1 those writes can fail in game after startup (see
`docs/releases/0.23.2.md`). HD2Runtime's own declaration requires only Bingus.
These are HD2Runtime SDK metadata, not new Bingus/Arsenal/HD2MM manifest fields.
Manager descriptions also state the requirements; managers do not install them
automatically. The generated Lua checks them before starting the mod.

The audited Bingus `docs/AUTHORING.md`, “Startup and compatibility”, explicitly
states there is no dependency ordering and tells addons to require dependencies.
Each mod therefore explicitly requires HD2Runtime. If the gameplay addon is
discovered first, that require initializes the runtime; subsequent runtime
discovery returns the same API. Do not assign arbitrary priority numbers to
gameplay mods. Bingus must remain the winning Wwise startup replacement if other
startup-replacement mods are installed, as documented by Bingus. HD2Runtime and
generated mods do not replace Wwise/startup resources.

Bingus discovers mods once at game startup and has no hot reload. After
rebuilding a mod, replace it in the manager, purge and redeploy, and restart the
game. Loader output is in
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\BingusSharedLoader.log`; the
runtime writes `HD2Runtime.log`, prefixed `[HD2Runtime]`, in the same folder.

The old standalone proof ZIPs bundled their runtime for testing. Use the separate
runtime plus dependent example ZIPs for this workflow; do not also enable an old
proof bundle that ships the same runtime resource identity.

## Runtime guarantees and evidence

The 0.4.0 proof was confirmed successful in live gameplay by the user. Version
0.14.1 routes the corrected ammo aliases through the same guarded `patch`,
`transaction`, and `ensure` engine and adds `magazine.*` and `rounds.*`
authoring constants.
`PlayerWeaponAmmoCapabilities.json` separates direct magazine values, rounds-fed
values, derived refills, customization defaults, sharedness, and fail-closed
reasons for all 80 player weapons. Ensure retains the three-update-second startup
and default 60-update-second recheck,
fresh resolution, expected/desired classification and terminal conflict behavior.
Transactions retain exact-width writes, stable rereads, page restoration and
guarded rollback; interference that prevents safe rollback is explicitly reported.

Structural candidate, schema-labelled, current-live ownership proven, gameplay
proven and native-consumer proven remain independent evidence categories. Saved
live confirmation is historical evidence; it never sets current ownership true.
No new native-consumer evidence or gameplay systems are introduced here.

For SDK maintainers, `schemas/sdk.json` and `schemas/player_weapon_fields.json`
are canonical. `python scripts/generate_weapon_authoring.py` generates the
runtime and GUI weapon capability views; `python scripts/generate_sdk.py`
generates constants, metadata, stubs, and the API reference. Physical layout
profiles remain in `schemas/current.lua`. Refreshing metadata never grants a new
write: the runtime resolver and write descriptors remain reviewed and tested.

`python scripts/build_release.py` verifies generated files, a clean commit,
installed file fingerprints, and the full offline regression suite before
building the runtime, SDK and independent examples. Nothing deploys or launches
HD2. No new live gameplay test is performed by the SDK build.

To repeat real language-server checks from the source project, run
`python scripts/check_sdk_luals.py --server <lua-language-server-executable>`.
The release builder accepts the same executable through `--luals` and embeds
its verification report. The checker starts only the language server, uses a
workspace inside `build`, and does not modify Rider settings.
