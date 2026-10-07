# Player weapon composition research and authoring

## Fire modes

`WeaponDataComponentData` contains a three-member native mode vector at offsets 144, 148, and 152.
For conventional projectile consumers, values 1 and 2 correlate structurally and across the catalog
with Full Auto and Semi Auto. Values 3 and 5 remain family-specific diagnostics. HD2Runtime only
reorders 1 and 2 when both already occur in the uniquely owned weapon vector. JAR-5 remains
read-only because its vector is `[2, 3, 0]` and therefore does not prove Full Auto compatibility.

## Projectile objects and residency

An attack owns a projectile reference. ProjectileSettings, physics, DamageInfo, terminal actions,
and linked explosions belong to the referenced projectile object. After a swap, scalar resolution
follows the new reference. Editing the object is a shared definition write and requires
`allow_shared=true`; HD2Runtime has found no native weapon-local clone/override contract.

A projectile or explosion taken from another weapon lives in that weapon's loadout package. When
the source's package is known and differs from the target's, the operation records an asset dependency.
Runtime loads that package through the game's own package system before the write, and waits in
`waiting_for_assets`; see `asset-loading.md`. LAS-58 Talon was classified `SOURCE_WEAPON_REQUIRED` from the
reported gameplay control (invisible until the Talon is equipped). Its package (`laser_pistol`) is known, so
the swap is accepted and loads that package first. This was confirmed live: the Reprimand fired Talon
projectiles correctly with nobody carrying the Talon. Each attack's `residency` publishes:
- `classification`: `PACKAGE_AUTO_LOADED` or `DEPENDENCY_UNRESOLVED`;
- `package`;
- `packageResidency`: the proof level of the loading path;
- `liveTested`;
- `observedWithoutLoader`: the pre-0.27 observation.

A source observed as `SOURCE_WEAPON_REQUIRED` without a known package stays blocked. JAR-5 carries the
successful observed swap evidence.

Terminal explosion slots accept typed explosion handles or `terminal:no_explosion()`. Native zero
is never accepted as a raw public reference.

They also accept any catalogued explosion whose package is known, `hd2.explosion(name)` (docs/explosions.md;
0.30.0-dev, not live-tested): with `allow_unverified_reference` and `allow_unverified_effect`, its package loaded
before the write (none for the mission effects package), its live ExplosionSettings row re-proven, and a donor whose
shrapnel chain would release the written projectile again refused (`RECURSIVE_COMPOSITION`). Weapon explosion handles
keep their rules unchanged.

A reference replacement and scalar edits are intentionally separate operations. The existing
transaction model has one semantic target and cannot prove an atomic identity transition between
two objects. An attempted combined attack transaction is rejected with `COMPOSITION_TARGET_CHANGED`;
the author then targets the source projectile handle in a second guarded operation and explicitly
acknowledges its shared consumers.

This pass uses the build-bound `F5FEE03DCFDB-20260926T222226Z.hd2snap` and the
reviewed 80-player-weapon identity catalog. The research scan is bounded to those
resources, five relevant component types, and their already-linked projectile,
damage, and explosion records. Its result records `writes=0`,
`protectionChanges=0`, and `fixtureFallback=disabled`.

## Guarded projectile reference replacement

A projectile reference is writable only where the written member is the projectile the attack fires: its active
projectile source (`attack:projectile_source()`, `sdk/AttackOutputCapabilities.json` `projectileSources`, and
`docs/attack-outputs.md`). A live test showed why this matters: the same guarded write that makes the SMG-32
Reprimand fire Talon bolts lands cleanly on the AR-23 Liberator and changes nothing, because the Liberator's default
ammunition customization overwrites its ProjectileWeapon +0 whenever the weapon is built.

Of the 57 projectile attack selectors with unique weapon identity and owned selector storage, 37 are `ACTIVE_DIRECT`
and support typed reference replacement through the existing `patch`, `transaction`, and `ensure` machinery:

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

local target = hd2.weapon('SMG-32 Reprimand'):attack('primary')
local source = hd2.weapon('P-113 Verdict'):attack('primary'):projectile()

return hd2.ensure({
    patch = {
        id = 'reprimand-verdict-projectile',
        target = target,
        field = hd2.fields.attack.projectile,
        expect = target:projectile(),
        value = source,
    }
})
```

The other 20 are read-only with the reason:
- `DORMANT_PROJECTILE_REFERENCE` (5): a default ammunition delta patches the member at weapon build. The AR-23
  Liberator, JAR-5 Dominator, R-63 Diligence and SG-225 Breaker are written through `weapon:ammunition():projectile()`
  instead (`hd2.fields.ammunition.projectile`, with `allow_shared` and `allow_unverified_effect`). The SG-20 Halt's
  rounds ammunition is not offered.
- `UNPROVEN_PROJECTILE_SOURCE` (9): the MP-98 Knight (equippable ammunition), and rounds-fed weapons whose
  ProjectileWeapon +0 and WeaponRounds both carry a projectile.
- `PROJECTILE_SOURCE_BLOCKED` (6): weapons that fire a spawned entity, or charge or heat levels with their own
  projectiles.

The Runtime freshly resolves both weapon resources, both component records, the
source projectile type, and the source `ProjectileSettings` row. It validates the
expected target reference and compatibility class before opening page protection.
The operation writes only the target's four-byte selector. It never copies or
mutates the source `ProjectileSettings` record.

Raw numeric projectile IDs are rejected. The approved structural classes are
`conventional_plain`, `explosive_impact`, `explosive_impact_and_expiry`, and
`explosive_shrapnel`; source and target must have the same class. Status-bearing,
ambiguous, shared-target, customization-supplied, and cross-class swaps remain fail-closed.
Rounds-fed attacks use their reviewed `feed_primary` and `feed_alternate` selector
fields; `:attack('primary')` and `:attack('alternate')` resolve those aliases.

## Attachment and magazine options

The SDK contains all 419 normalized primary-weapon attachment rows: 195 optics,
117 underbarrel, 71 muzzle, and 36 magazine options. The snapshot proves 52 native
magazine/heatsink/canister identities and 20 native default relationships.
Thirteen of the 36 imported magazine rows can be tied to the native default option.
`WeaponCustomizationComponentData.DefaultCustomizations`
is a terminated list of eight-byte `(slot, optionId)` entries; slot tag `5` is the
magazine slot. The default option can be inspected with:

```lua
local weapon = hd2.weapon('AR-23 Liberator')
local default = weapon:default_magazine()
local options = weapon:magazine_options()
```

The bounded audit inspected all 191 occupied customization records, not only the
80 reviewed player roots. It found 20 catalog option IDs and six catalog AddPaths,
but no alternate allowed-option collection and no option-owned effect/ammo record.
This rules out guarded selection and effect editing for the current snapshot.

Use `weapon:attachment_options(category)` and `weapon:attachment(category, name)`
for the imported read-only catalog. The captured graph still does not link a native
allowed-options collection or an option-owned effect override record. Per-option
ammo, reload, ergonomics, optics, muzzle, and underbarrel effects therefore remain
read-only. The existing simple `hd2.fields.magazine.*` API remains writable
for the 33 directly owned single-magazine weapons, while the 15 rounds-fed weapons
continue to use `hd2.fields.rounds.*`.

## Heat and heatsinks

Component type `0x4C981CD9` is schema-labelled `WeaponHeatComponentData`. Seven
player weapons own records. Capacity (`+96`), shot heat (`+116`), continuous heat
(`+120`), base cooling (`+128`), starting heatsinks (`+84`), supply heatsinks
(`+88`), and spare heatsinks (`+92`) correlate across the complete energy cohort.
The neighboring `0.75` and `1.5` multipliers derive the cold and hot cooling rates.
Five uniquely resolved weapons expose 30 direct guarded field instances. LAS-5
Scythe and LAS-7 Dagger remain blocked by duplicate identities; Dagger also has
unresolved scale/count disagreements. The nine named heatsink attachment identities
do not expose option-owned override records in this snapshot.

The GL-28 `160 / 240 / 320` rate selector is a separate support-weapon rate vector;
it is not treated as semi/full/burst selection.

## Explosion and terminal-action authoring

Every one of the 67 player projectile branches exposes impact and expiry terminal
descriptors. Non-null typed references are guarded-writable for 12 impact and four
expiry actions:

```lua
local projectile = hd2.weapon('CB-9 Exploding Crossbow')
    :attack('primary'):projectile()
local impact = projectile:terminal_action('impact'):describe()
```

For the current snapshot, all 13 nonzero values at `ProjectileSettings + 144`
resolve to typed `ExplosionSettings` records. All five nonzero values at `+156`
also resolve to `ExplosionSettings`. Neighboring aligned nonzero values do not
resolve as explosion records. Raw IDs and null-target writes are rejected.

Thirteen distinct explosion records expose guarded inner, outer, and shockwave
radii plus their linked `DamageInfo` standard/durable damage, AP lanes,
demolition, stagger, and push values. Shared explosion or damage records require
`allow_shared=true`. Independent outer-radius damage was not found and is not
invented as a scalar.

The Eruptor record proves `ExplosionSettings +80` as shrapnel count `30` and `+84`
as projectile type `201`, whose complete projectile fingerprint matches AC-8 P2.
Both shrapnel fields remain read-only because this snapshot contains only one
correlated shrapnel instance.

The generated capability artifacts are:

- `sdk/PlayerWeaponMagazineOptionGraph.json`
- `sdk/PlayerWeaponProjectileReferenceGraph.json`
- `sdk/PlayerWeaponFireModeGraph.json`
- `sdk/PlayerWeaponTerminalActionGraph.json`
- `sdk/AttachmentOptionCapabilities.json`
- `sdk/ProjectileCompositionCapabilities.json`
- `sdk/ExplosionAuthoringCapabilities.json`
- `sdk/PlayerWeaponHeatCapabilities.json`

They contain no process addresses and are suitable for SDK inspection and future
GUI consumption without adding GUI-specific tables.

## Underbarrel weapons

An underbarrel is a separate weapon entity, not part of its host: `scripts/research_underbarrel_weapons.py` →
`research/underbarrel-weapons-F5FEE03DCFDB.json`.
- **The link.** The host's default underbarrel item names the underbarrel entity (its entity delta sets
  WeaponCustomization +192 `underbarrel_path`).
- **At setup.** The game creates the underbarrel as its own game object when the host weapon is set up.
- **The host** keeps its own records and carries none of the underbarrel's.

Three weapons have one:

| Host | Underbarrel | Fields (its own records) |
| --- | --- | --- |
| AR/GL-21 One-Two | grenade launcher | grenade spread 30 / 30 (`weapon.horizontal_spread` / `vertical_spread`), fire rate 900, loaded 1 (`rounds.feed_capacity_1`), spare grenades 5 (`rounds.spare_rounds`), resupply 5 (`rounds.rounds_from_supply`), starting 3 (`rounds.starting_rounds`) |
| AR-11 Arbitrator | shotgun | spread 150 / 130, fire rate 80, rounds 4 / 20 / 20 / 20 |
| SMG/FLAM-34 Stoker | flamer | spread 1 / 1 |

```lua
local launcher=hd2.weapon('AR/GL-21 One-Two'):underbarrel()
hd2.ensure({patch={id='one-two-grenades',target=launcher,field=hd2.fields.rounds.spare_rounds,expect=5,value=10,
    allow_unverified_effect=true}})
```

- **Proven members.** The fields are the same component members as those fields on every weapon. The records belong
  to the underbarrel alone.
- **Not live-tested.** Every write needs `allow_unverified_effect`, because whether a built underbarrel keeps copies is
  not proven.
- **Not exposed:**
  - the reload time (the reload ability's duration; WeaponReload +56 is 0);
  - WeaponRounds +92 / +104;
  - the projectile reference (ProjectileWeapon +0 and WeaponRounds +64 both hold the grenade; which one fires is
    unproven).
- **Shared rows.** The grenade's projectile and explosion rows are shared with the GP-31 Grenade Pistol.
- **Catalog correction pending.** The GP-31 Grenade Pistol and the P-72 Crisper list the One-Two launcher and the
  Stoker flamer as second runtime roots. Their duplicate identity stays fail-closed, with that reason, until they are
  re-mapped on their own roots (`catalogCorrections` in the research).
