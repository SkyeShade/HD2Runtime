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
the swap is accepted and loads that package first. A `SOURCE_WEAPON_REQUIRED` source without a known package
stays blocked. JAR-5 carries the successful observed swap evidence.

Terminal explosion slots accept typed explosion handles or `terminal:no_explosion()`. Native zero
is never accepted as a raw public reference.

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

Fifty-seven projectile attack selectors have unique weapon identity and owned
selector storage. They support
typed reference replacement through the existing `patch`, `transaction`, and
`ensure` machinery:

```lua
local hd2 = require('mods/skyeshade/hd2runtime')

local target = hd2.weapon('JAR-5 Dominator'):attack('primary')
local source = hd2.weapon('P-113 Verdict'):attack('primary'):projectile()

return hd2.ensure({
    patch = {
        id = 'jar5-verdict-projectile',
        target = target,
        field = hd2.fields.attack.projectile,
        expect = target:projectile(),
        value = source,
    }
})
```

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
