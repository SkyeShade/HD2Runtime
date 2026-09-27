# Player weapon composition research and authoring

This pass uses the build-bound `F5FEE03DCFDB-20260926T222226Z.hd2snap` and the
reviewed 80-player-weapon identity catalog. The research scan is bounded to those
resources, five relevant component types, and their already-linked projectile,
damage, and explosion records. Its result records `writes=0`,
`protectionChanges=0`, and `fixtureFallback=disabled`.

## Guarded projectile reference replacement

Forty-five conventional projectile attack selectors have unique weapon identity,
owned selector storage, and a `conventional_plain` projectile class. They support
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

Raw numeric projectile IDs are rejected. Explosive, status-bearing, ambiguous,
shared-target, customization-supplied, and cross-family swaps remain fail-closed.
Rounds-fed attacks use their reviewed `feed_primary` and `feed_alternate` selector
fields; `:attack('primary')` and `:attack('alternate')` resolve those aliases.

## Magazine options

The snapshot proves 52 magazine/heatsink/canister option identities and 19 native
default relationships. `WeaponCustomizationComponentData.DefaultCustomizations`
is a terminated list of eight-byte `(slot, optionId)` entries; slot tag `5` is the
magazine slot. The default option can be inspected with:

```lua
local weapon = hd2.weapon('AR-23 Liberator')
local default = weapon:default_magazine()
local options = weapon:magazine_options()
```

The captured graph still does not link an allowed-options collection or an
option-owned ammo override record. Per-option capacity/reserve values therefore
remain read-only. The existing simple `hd2.fields.magazine.*` API remains writable
for the 33 directly owned single-magazine weapons, while the 15 rounds-fed weapons
continue to use `hd2.fields.rounds.*`.

## Fire modes

`WeaponDataComponentData + 144` supplies one schema-labelled native value for all
80 weapons. The snapshot contains values `1`, `2`, `3`, and `5`, but it does not
prove their semantic names, an allowed-mode list, a default selector separate from
the current selection, or native compatibility rules. `weapon:fire_modes()` exposes
that evidence read-only. JAR-5 Full Auto remains blocked.

The GL-28 `160 / 240 / 320` rate selector is a separate support-weapon rate vector;
it is not treated as semi/full/burst selection.

## Projectile terminal actions

Every one of the 67 player projectile branches exposes read-only impact and expiry
terminal descriptors through:

```lua
local projectile = hd2.weapon('CB-9 Exploding Crossbow')
    :attack('primary'):projectile()
local impact = projectile:terminal_action('impact'):describe()
```

For the current snapshot, all 13 nonzero values at `ProjectileSettings + 144`
resolve to typed `ExplosionSettings` records. All five nonzero values at `+156`
also resolve to `ExplosionSettings`. Neighboring aligned nonzero values do not
resolve as explosion records. Impact is schema-labelled as
`ProjectileInfo.ExplosionType`; the expiry consumer label is incomplete, so both
references remain read-only pending native consumer or gameplay confirmation.

The generated capability artifacts are:

- `sdk/PlayerWeaponMagazineOptionGraph.json`
- `sdk/PlayerWeaponProjectileReferenceGraph.json`
- `sdk/PlayerWeaponFireModeGraph.json`
- `sdk/PlayerWeaponTerminalActionGraph.json`

They contain no process addresses and are suitable for SDK inspection and future
GUI consumption without adding GUI-specific tables.
