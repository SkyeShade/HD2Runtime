# Guarded vehicle authoring

`hd2.vehicle(name)` edits vehicle durability and mounted-weapon references. The catalog is
`sdk/VehicleAuthoringCapabilities.json`. It covers the nine wiki vehicle stratagems (FRVs, Exosuits,
Bastion, and Maelstrom) plus two native-only vehicles: the Super Earth FRV variant and the GATER oil
rig. The legacy aliases `Bastion` and `Maelstrom` keep their old read-only behavior. Use the wiki names
for authoring, for example `TD-220 Bastion MK XVI`.

## Identity

Each stratagem vehicle is resolved from its call-in StratagemDefinition payload to a uniquely owned
vehicle entity. Its native main health, main armor, and cooldown must equal the scraped wiki values
exactly. The Maelstrom has no historical debug name, so it is resolved as the unique current
definition whose payload is the native `tank_storm` entity. Native-only vehicles are identified by
their native entity path.

Vehicles, zones, mount slots, and mounted weapons have stable semantic IDs (`vehicle/v1/...`,
`vehicle-zone/v1/...`, `mount-slot/v1/...`, and `mounted-weapon/v1/...`). The call-in link is published
in both directions: `vehicles[].callInStratagem` here, and `stratagems[].delivers` in the stratagem
catalog. The call-in cooldown stays on `hd2.stratagem(...)`.

## Durability

All vehicles share the typed `HealthComponent` schema:

| Target | Field | Meaning |
| --- | --- | --- |
| `hd2.vehicle(name)` | `entity.health`, `entity.armor` | Main health pool and default-zone armor |
| `vehicle:damage_zone(zone)` | `zone.armor` | Armor value of one damage zone |
| `vehicle:damage_zone(zone)` | `zone.health` | Health of one damage zone |
| `vehicle:damage_zone(zone)` | `zone.affects_main_health` | Share of zone damage forwarded to main health (0 to 1) |

Zones are addressed as `zone_N`, by their resolved native name, or by index. Only populated zones
(those with a native zone name) are exposed. Each zone also publishes its child zones, constitution,
and actor count as read-only structure. Distinct zones are never merged.

Every descriptor carries an evidence tier. Main health, armor, zone armor, and lunch-box forwarding
were gameplay-proven on the Bastion by BastionReArmored (`gameplay_proven`). The same typed members on
the Maelstrom, FRVs, and Exosuits are `schema_proven`: they share the schema, but no reference mod
tested them on those vehicles.

## Mounts

Every vehicle `MountComponent` holds up to five slots. Each slot's `Path` references the entity to
mount. `vehicle:mounts()` lists the slots. A slot is swappable only when its vanilla occupant is a
weapon entity, meaning one that owns `WeaponData` and exactly one attack component (projectile, spray,
beam, or arc). Replacements are limited to discovered mounted weapons of the same attack family. These
are entities already referenced by one of the 163 native mount records. Arbitrary identifiers,
resource hashes, and non-weapon references are rejected.

```lua
local gater=hd2.vehicle('GATER Oil Rig'):mount('turret'):current()
local gun=hd2.vehicle('M-102 Gunner FRV'):mount('gun')
hd2.patch({id='frv-gater',target=gun,field=hd2.fields.mount.weapon,
    expect=gun:current(),value=gun:candidate(gater.semanticId),allow_unverified_reference=true})
```

Mount swaps require `allow_unverified_reference=true`. FRVWeaponSwap verified the write live on the
FRV and Super Earth FRV (`live_write_verified`), but in-game firing and rendering are unconfirmed. Other
slots are `structural_reference`. When the replacement comes from another package that the catalog
knows, the runtime loads that package before the write (see `asset-loading.md`); vehicle-mount loading is
proven offline but not yet live-tested. Package loading does not make a mount swap compatible: firing and
rendering of a swapped mount remain unverified, so `allow_unverified_reference` stays required.

At write time the runtime re-resolves the vehicle's mount record ownership and requires the
replacement entity to be live with `WeaponData`. The slot must still hold the expected identity.

## Blocked

Zone constitution and death flags, zone explosive damage percentage (a gameplay test showed no
effect), unpopulated zone slots, and vehicle motion, collision, and seat components are not promoted.
