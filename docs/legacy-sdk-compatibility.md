# Legacy SDK compatibility (HD2Runtime 0.28.1+)

A mod built with an older SDK was valid when it was written: its operations carry every acknowledgement that SDK
asked for. HD2Runtime 0.28.0 added `allow_unverified_effect` to fields that 0.27.0 let mods write without it, so
0.28.0 refused operations that worked on 0.27.0. From 0.28.1, Runtime decides by the SDK version each mod declares.
0.30.0 adds the acknowledgement to 30 PLAS-45 Epoch fields the same way (below).

## The rule

An operation may leave out `allow_unverified_effect` on a field **only** when all of these hold:

1. the field requires `allow_unverified_effect` now;
2. the field gained that requirement in a later SDK than the one the registering mod declares
   (`schemas/legacy_acknowledgements.json`);
3. Runtime could read the mod's declared SDK version (see below).

Such an operation is applied as it was on the older SDK, and it is logged as a **legacy SDK operation**. Every other
case keeps the current rule:

| Mod declares | Field | Without `allow_unverified_effect` |
| --- | --- | --- |
| SDK 0.27.x or older | gained the acknowledgement in 0.28.0 | applied, logged as a legacy operation |
| SDK 0.27.x or older | already needed it in 0.27.0, or is new in 0.28 | refused, as before |
| SDK 0.28.0 or later | gained it in 0.28.0, or any other field that needs it | refused, as in 0.28.0 |
| SDK older than 0.30.0 (0.28.x included) | gained the acknowledgement in 0.30.0 (the Epoch fields below) | applied, logged as a legacy operation |
| SDK 0.30.0 or later | any field that needs it | refused |
| unknown (not readable) | any field that needs it | refused |

Nothing else changes: `allow_shared`, `allow_unverified_reference`, live proof, reviewed ranges, expected baselines,
read-only fields and the guarded write are the same for every mod. A field that 0.28.0 made read-only (for example
the AR-23 Liberator's dormant `attack.primary.projectile`, or the SH-20 Ballistic Shield's default-zone armor after
its live failure) stays read-only for every mod, because the write does not change the game.

Only the MAJOR.MINOR.PATCH core of a version is compared. An SDK 0.28.0 prerelease already carried the new
acknowledgements, so it counts as 0.28.0.

## Fields that gained `allow_unverified_effect` in 0.28.0

146 fields, listed with their reasons in `schemas/legacy_acknowledgements.json`
(`scripts/generate_legacy_acknowledgements.py --research v0.27.0 0.28.0` compares the SDK catalogs published at
v0.27.0 with 0.28.0; the runtime lookup is `domains/legacy_acknowledgements.lua`):

| Target | Fields | Why 0.28.0 asks for the acknowledgement |
| --- | ---: | --- |
| PLAS-101 Purifier | 28 | Only the charge levels that name this row fire it; the others fire projectile 129. |
| PLAS-15 Loyalist | 28 | Every charge level fires another projectile (70, 341); the weapon never fires this row, which it shares with the PLAS-1 Scorcher in part. |
| P-34 Breacher | 28 | The weapon fires a spawned entity, so the row is not established as what it fires. |
| P-33 Missile Pistol | 28 | The weapon fires a spawned entity, so the row is not established as what it fires. |
| P-92 Warrant | 16 | The weapon fires a spawned entity, so the row is not established as what it fires. |
| LAS-17 Double-Edge Sickle | 16 | Every heat level fires another projectile (185, 219, 25); its projectile fields write the LAS-16 Sickle's row. |
| SH-51 Directional Shield (backpack) | 2 | `entity.health` and `entity.armor` are the backpack body's, not the energy barrier's; not yet shown in game. |

The player weapon fields are each weapon's projectile, damage, explosion and terminal-explosion fields
(`projectile.*`, `damage.*`, `explosion.*`, `terminal.*`). The exact reason for each field is its
`acknowledgementReason` in the SDK catalogs.

## Fields that gained `allow_unverified_effect` in 0.30.0

30 fields of the PLAS-45 Epoch support weapon (`scripts/generate_legacy_acknowledgements.py --research v0.28.1 0.30.0`
compares the SDK catalogs published at v0.28.1 with the current ones; support-weapon entries are keyed by the
attack-qualified field id, for example `explosion.primary_impact.inner_radius`):

| Target | Fields | Why 0.30.0 asks for the acknowledgement |
| --- | ---: | --- |
| PLAS-45 Epoch | 30 | `attack('primary')` and `attack('primary_impact')` are only the **partial-charge** shot and its explosion: the Epoch fires them when released between 1 s and 2.5 s. Full-charge and overcharged shots fire another row (`attack('full_charge')`), which these fields never changed. The same rule as the PLAS-101 Purifier: a row only some charge levels fire needs the acknowledgement. |

They are the partial-charge shot's projectile (`projectile.primary.*`, 7), its direct-hit damage and status slot
(`damage.primary.*`, 11) and its explosion's radii and damage (`explosion.primary_impact.*`, 12); the explosion's status
slot already needed the acknowledgement. The research is `research/charge-explosions-F5FEE03DCFDB.json`
([support weapons, charge-level shots and explosions](support-weapon-api.md#charge-level-shots-and-explosions)). The
new roles (`full_charge`, `full_charge_impact`, `overcharge_explosion`) are new in 0.30.0: no older SDK wrote them, so
they have no legacy rule.

The AyakaMods weaponry rebalance (SDK 0.27.0, `tests/fixtures/user-reports/ayakamods-weaponry-rebalance`) is such a
mod: its Epoch plan (partial-charge explosion radii and damage, partial-charge projectile velocity) applies as a legacy
operation and logs one line per field.

## How Runtime reads the declared SDK version

Mods do not pass their SDK version to Runtime. Every published addon wrapper keeps the version its mod was built
for in a local variable of its main chunk while it runs the mod's startup, and a generated mod registers every
operation inside that startup:

- **ModBuilder** (`ModExporter.Wrap`, every version) and the **ModTemplate** (`build.ps1`):
  `local x,y,z=version('<sdk>')`. ModBuilder writes the project's bound SDK version here.
- **SDK** (`py hd2.py build`, `wrap_addon`): `local minimum='<min_version>'`.

Both sit next to `local key='HD2RuntimeMod:<resource>'` and `local function start()`. When a mod registers an
operation (`hd2.patch`, `hd2.transaction`, `hd2.plan`, `hd2.ensure`), Runtime reads these locals from the call
stack with `debug.getlocal`. It only reads values; it calls nothing and changes nothing. It recognises only these
wrapper shapes. The declaration is remembered per mod resource, so an operation that the same mod registers later
from a callback, timer or keybind uses it too. An option change that re-validates an `hd2.ensure` keeps the
declaration of the mod that registered it.

A mod whose declaration cannot be read is **unknown**, and the current rule applies. This covers a bare addon
without a wrapper, a hand-written wrapper, and a game Lua environment without the `debug` library. A refusal then
says so:

```
[HD2Runtime] ensure my-op rejected: field requires allow_unverified_effect=true: projectile.drag (...)
[required since SDK 0.28.0; Runtime could not read the SDK version of unknown, so the 0.28.0 rule applies]
```

The declared version is what the mod's author promised to support. A ModTemplate mod that keeps `min_version`
0.25.0 while using newer SDK documentation is treated as a 0.25.0 mod.

## Diagnostics

Each legacy use is logged once per operation and field, when the operation registers:

```
[HD2Runtime] ensure gui-object-64f6c65514d7e06d97274943: legacy SDK 0.27.0 operation from
mods/nephelym/nephelym_s_weaponry_rebalance: PLAS-101 Purifier projectile.drag needs allow_unverified_effect=true
since SDK 0.28.0 and is applied without it, as SDK 0.27.0 allowed. Rebind the project to SDK 0.28.0 or later and
re-export it, or add allow_unverified_effect=true to the operation. Why it is needed: ...
```

`hd2.diagnostics.operations()` lists every registered operation, refused ones included, with the mod, its declared
SDK (`sdk`, and `sdk_source`: `wrapper`, `mod` or `unknown`) and a `legacy` list of `{target, field,
acknowledgement, since}` for each legacy use (see `docs/diagnostics.md`).

**What to do.** In ModBuilder, rebind the project to SDK 0.28.0 or later and export it again: ModBuilder 1.4.x
adds the acknowledgement where the catalog asks for it. By hand, add `allow_unverified_effect=true` to the
operation and raise `min_version`. The legacy path exists so that published mods keep working. It does not prove
the effect: a Purifier row edit still changes only the charge levels that fire that row.
