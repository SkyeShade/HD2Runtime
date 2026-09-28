# Guarded support-weapon authoring

HD2Runtime 0.20 keeps the graph-aware 35-weapon inspection catalog and enables guarded
authoring for the 27 uniquely resolved runtime identities. The eight duplicate groups remain
visible through `describe()` and `attacks()`, but patch, transaction, and plan validation rejects
them before runtime discovery. No duplicate root is chosen by score or list order.

The normal semantic field constants are reused. A projectile target can edit `projectile.*` and
linked `damage.*` fields, while an explosion target can edit `explosion.*` and
`explosion.damage_*` fields. Definitions are shared runtime objects, so settings edits require
`allow_shared=true`.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local explosion=gr8:attack('primary_impact'):explosion()

return hd2.ensure({
    plan={
        id='recoilless-proof',
        operations={
            {id='physics',target=projectile,allow_shared=true,
                field=hd2.fields.projectile.velocity,expect=250,value=500},
            {id='blast-radius',target=explosion,allow_shared=true,
                field=hd2.fields.explosion.outer_radius,expect=3,value=12},
            {id='blast-damage',target=explosion,allow_shared=true,
                field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000},
        },
    },
})
```

`ARC-3 Arc Thrower` exposes `arc.*`, `damage.*`, `status.*`, and `charge.*`. Its native fire-rate
value is the `-1` charge-controlled sentinel, so `weapon.fire_rate` is intentionally absent.
`RS-422 Railgun` exposes the resolved primary projectile and charge component; the catalog's
intentional Max Charge unknown branch remains unresolved. Spray and melee attacks expose their
owned DamageInfo fields, and resolved status branches expose strength and duration.

C4 resolves through `ExplosiveComponentData` to its detonation `ExplosionSettings`. Solo Silo
keeps the full stratagem payload -> `HellpodRackComponentData` -> missile entity chain. Every Solo
Silo write freshly verifies that chain, then resolves the independently owned detonation or impact
explosion. The handheld or delivery root is never treated as the damage owner.

Weapon-side magazine and rounds-feed fields are independent of backpack storage. Backpack ammo
stays read-only until its entity/package storage owner and semantics are proven. Known
`WeaponLinkedAmmoComponentData` ownership is reported as classification evidence only.

LAS-98 uses the 0.18 `WeaponHeatComponentData` layout in the retained snapshot, including heat
capacity, generation, cooling, and heatsinks. Its runtime roots are still unresolved (see below),
so both heat and beam writes remain blocked.

## 0.24 coverage

Evidence: `research/support-weapon-coverage-F5FEE03DCFDB.json`, produced by
`scripts/research_support_weapon_coverage.py`. The live snapshot proves every relied-on native
table is byte-identical to the pinned reference; scraped values are fingerprints only.

| Field | Native owner | Evidence | Writable where |
| --- | --- | --- | --- |
| `projectile.lifetime` | `ProjectileInfo` +52 | Type-library member name length 9 (`life_time`); 5/5 exact scraped matches, 0/5 at the competing +56 | Native lifetime is non-zero (LAS-99, PLAS-45, RL-77, RS-422, S-11). A 0 lifetime means "no explicit limit" and stays read-only. |
| `projectile.penetration_slowdown` | `ProjectileInfo` +64 | Name length 20; 27/27 exact matches, 1/27 at +56 | Every resolved projectile branch |
| `reload.duration` | `WeaponReloadComponentData` +56 | Name length 8 (`duration`); scraped reload times agree only approximately | Native duration is non-zero (14 weapons). **Requires `allow_unverified_effect=true`.** A 0 duration means the reload ability's default applies and stays read-only. |
| `windup.wind_up_seconds` | `WeaponWindUpComponentData` +0 | Name length 12; exact scraped match (Maxigun 0.5 s) | M-1000 Maxigun |
| `windup.wind_down_seconds` | `WeaponWindUpComponentData` +4 | Name length 14; no scraped value | M-1000 Maxigun. **Requires `allow_unverified_effect=true`.** |

Projectile fields live on shared definitions and need `allow_shared=true`, like the other
`projectile.*` fields. Filediver labels +56 as `LifeTime`; the type library and the correlation
both contradict that for this build.

```lua
local mg43=hd2.support_weapon('MG-43 Machine Gun')
hd2.ensure({patch={id='mg43-reload',target=mg43,allow_unverified_effect=true,
    field=hd2.fields.reload.duration,expect=4.5,value=3}})
```

### Delivery-resolved identities

Duplicate groups used to be blocked as a whole. Each root in these groups owns separate component
records, so the only open question was which root the player receives. A group is now resolved
(`identityStatus` `DELIVERY_RESOLVED`) only when both are true:

1. The linked call-in StratagemDefinition's hellpod rack attaches exactly one candidate root.
2. That root's native magazine tuple (capacity, starting, from supply, spare) alone matches the
   scraped values, and the other roots differ.

| Weapon | Result |
| --- | --- |
| MG-43 Machine Gun | Resolved. Delivered root 175/2/2/3 matches; the other root is 175/30/6/12. |
| M-105 Stalwart | Resolved. Delivered root 250/2/2/3 matches; three other roots are 150/0/0/0. |
| MG-206 Heavy Machine Gun | Resolved. Delivered root 100/1/2/2 matches; the FRV gun and another root differ. |
| CQC-20 Breaching Hammer | Resolved. Delivered root 1/7/7/7 matches; the other root has no magazine. |
| EAT-17 Expendable Anti-Tank | Blocked. Delivery is unique, but both roots are byte-identical in magazine and fire rate. |
| LAS-98 Laser Cannon | Blocked. Delivery is unique, but the delivered root's reload (5.0 s) conflicts with the scraped 3.65 s. |
| B/FLAM-80 Cremator | Blocked. Delivery is unique, but the scraped 500 capacity matches the Exosuit root, not the handheld. |
| CQC-72 Entrenchment Tool | Blocked. Its two native roots share one package and matching melee records; one is a `SupportWeapon` loadout item and the other a `SidearmWeapon` item. It has no call-in (state `no_call_in`). |

Resolved weapons reuse the Solo Silo chain check: every write re-proves live that the call-in
StratagemDefinition payload is the rack and that the rack attaches the delivered root. Fields
edit only the delivered weapon. Other native roots with the same catalog name (vehicle,
emplacement, or mission variants) keep their own records, although shared settings rows still
require `allow_shared`.

The GUI-facing `SupportWeaponAuthoringCapabilities.json` schema v2 reports every weapon, catalog
branch, writable fields by domain, shared scopes, blocked fields and exact reasons, backpack
dependency, and linked stratagem status. Its canonical `fieldInstances` collection contains one
entry for every internal authoring descriptor. Each entry includes the exact baseline, API field
constant, attack-qualified target, semantic backing-object key, complete reviewed consumer scope,
shared acknowledgement key, and transaction/plan grouping keys. `backingObjects` and
`operationGroups` provide deduplicated joins for building one transaction per accepted Runtime
backing scope and one plan across related objects.

The older `weapons[].writableFieldsByDomain` lookup remains available as a deduplicated
compatibility view. It must not be used to enumerate authoring instances because equal field names
on different attacks or backing objects intentionally remain separate in `fieldInstances`.

Semantic object and instance keys are stable opaque digests of reviewed identities. The artifact
contains no runtime addresses, offsets, record IDs, resource hashes, projectile IDs, or explosion
IDs. The older `SupportWeaponCapabilities.json` remains as the detailed inspection/evidence
artifact.

Snapshot validation resolves all promoted fields through production ownership chains and applies
their current values as guarded no-ops. The checked result must be `ALREADY_DESIRED`, with zero
writes, zero protection changes, stable rereads, and fixture fallback disabled.

## Support call-in linkage

Support weapons and their call-in stratagems remain separate authoring targets:
`hd2.support_weapon(...)` edits the delivered weapon, and `hd2.stratagem(...)` edits the call-in
definition. Since 0.22.1, both capability catalogs publish the reviewed relationship between them,
so tools can present one merged view without matching display names or using private tables.

Every support weapon has a stable `semanticId` (`support-weapon/v1/...`) and every stratagem has a
stable `semanticId` (`stratagem/v1/...`). These IDs are opaque digests of semantic identity and are
safe to persist. `weapons[].linkedStratagem` holds the forward link and support
`stratagems[].delivers` holds the reverse link. Both catalogs carry the same
`supportCallInLinks.relationships` collection. Use its `relationshipId`
(`support-callin/v1/...`) as the merge key.

Links are proven structurally. Either the call-in StratagemDefinition's primary payload is the
support weapon's own runtime root, or it is a hellpod rack that attaches one of the weapon's runtime
resources. The historical stratagem debug-name table is only a cross-check, and generation fails if
the two disagree. The generator also fails on any one-way link.

| State | Support weapons |
| --- | --- |
| `linked` | 33, including MS-11 Solo Silo (special: `deployable_silo`) and B/MD C4 Pack (special: `placed_item`) |
| `no_call_in` | SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool |
| `unresolved_call_in`, `unresolved_delivery` | none |

A second, independent native identity corroborates the payload graph. Each loadout item's
`LoadoutEntryComponent` carries an item id and a `LoadoutItemType`. For 29 of the 33 linked
support weapons the item id is the id of the call-in StratagemDefinition. The generator fails if
an item id ever names a different call-in than the structural link.

- **B/MD C4 Pack** (`placed_item`). The call-in rack attaches the detonator (the thrower) and the
  backpack; the backpack's deposit refills the detonator. The placed charge, which the catalog
  identifies as C4, is linked because both of these hold: its loadout item id is the C4 call-in
  id, and the call-in's package is its package. That package is owned only by the rack, the
  detonator, the backpack, and the charge. The `deliveryGraph` keeps them separate: call-in
  (cooldown) -> rack items `thrower` and `backpack` (native-only nodes, no authoring view) ->
  placed charge (the support-weapon view) -> `detonation` explosion.
- **SG-88 and CQC-72** (`no_call_in`). No StratagemDefinition carries their loadout item ids or
  names their packages. No rack, deposit, entity delta, or other entity record references them.
  `noCallIn` gives the reason, the root `loadoutItemTypes`, and a catalog-sourced
  `acquisition` of `world_pickup` with `nativeDeliveryProven=false`: only the absence of a call-in
  is native. On the stratagem side their `rootResolution` is `NO_CALL_IN`.

Three linked weapons still have unresolved runtime roots: EAT-17, LAS-98, and B/FLAM-80. Their
call-in links are known and their stratagem cooldowns stay writable. A relationship alone never
lifts support-weapon write blocking; MG-43, M-105, MG-206, and CQC-20 are resolved only because
scraped fingerprints independently confirm the delivered root (see "Delivery-resolved identities").

Each relationship has a reference-only `deliveryGraph`. Its nodes name the owning view
(`stratagem` or `support_weapon`), the semantic ID, and the target path or attack role. An editor
uses these to select existing `fieldInstances`; no fields are copied. For Solo Silo the graph is
stratagem call-in (cooldown) -> deployable silo -> missile -> `detonation` and `impact`
explosions. Edits still persist through the original target types.
