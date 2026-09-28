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
capacity, generation, cooling, and heatsinks. Its three runtime roots are still ambiguous, so both
heat and beam writes remain blocked. EAT-17, MG-43, MG-206, M-105, B/FLAM-80, CQC-20, and CQC-72
are blocked for the same identity reason.

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
| `linked` | 32, including MS-11 Solo Silo (special: `deployable_silo`) |
| `unresolved_call_in` | SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool |
| `unresolved_delivery` | B/MD C4 Pack. Its call-in rack attaches a backpack and an unmapped thrower weapon, not the placed charge the catalog identifies as C4. |

Seven linked weapons have ambiguous runtime roots: MG-43, M-105, EAT-17, MG-206, LAS-98,
B/FLAM-80, and CQC-20. Their call-in links are known and their stratagem cooldowns stay writable.
The relationship never lifts support-weapon write blocking, so their weapon fields remain blocked.

Each relationship has a reference-only `deliveryGraph`. Its nodes name the owning view
(`stratagem` or `support_weapon`), the semantic ID, and the target path or attack role. An editor
uses these to select existing `fieldInstances`; no fields are copied. For Solo Silo the graph is
stratagem call-in (cooldown) -> deployable silo -> missile -> `detonation` and `impact`
explosions. Edits still persist through the original target types.
