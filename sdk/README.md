# HD2Runtime SDK and shared runtime

For a first mod, use `HD2Runtime-ModTemplate-0.23.1.zip`. It is a standalone
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
`StratagemAuthoringCapabilities.json` is the canonical per-instance contract for
offensive, support-call-in, sentry, emplacement, and deferred mine authoring; see
`docs/stratagem-authoring.md`.

Attachment preset research is split into `AttachmentPresetGraph.json`,
`AttachmentSelectionCapabilities.json`, and `AttachmentEffectOwnership.json`.
These distinguish static resource defaults from current selections, saved
presets, and effect owners. Attachment selection is not writable. Magazine
ammo values are writable on the magazine attachment definitions themselves, with
`allow_shared` and `allow_unverified_effect`; `MagazineAttachmentCapabilities.json`
supersedes the older ammo-owner fields in `AttachmentOptionCapabilities.json`. See
`docs/magazine-attachments.md` and `docs/attachment-preset-research.md`.

Install Bingus Shared Loader v15+ / API 1, then import the separate
`HD2Runtime-0.23.1-runtime.zip` into your mod manager and enable it once. Each
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

Use `--template shield` for the proven four-field Shield Relay transaction or
`--template observer` for read-only Bastion/AMR observations. The default is the
JAR-5 AP4 ensured patch. These CLI templates use the original fixed-resource
catalog (short names such as `Bastion` and `Shield Relay`, and single reviewed
transitions). For other changes, use the full names and field constants from the
typed capability files, as the ModTemplate and example projects do. The generated entrypoint contains only public API calls;
the runtime owns all timers, resolution, memory access and protection changes.
Reusing a resource name intentionally reuses its stable mod GUID. Choose a unique
author/mod path for each independently distributed mod.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
return hd2.ensure({
    patch={
        id='jar5-ap4',
        target=hd2.weapon('JAR-5 Dominator'):projectile():damage(),
        field=hd2.fields.damage.armor_penetration,
        expect=3,
        value=4,
    },
})
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
descriptors remain valid.

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
fields, and `hd2.support_weapon` need 0.23.0; magazine attachments need 0.23.1. HD2Runtime's own declaration requires only Bingus.
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
