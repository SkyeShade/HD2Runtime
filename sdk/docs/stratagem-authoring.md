# Guarded stratagem authoring

HD2Runtime 0.22 extends the 0.21 `hd2.stratagem(name)` graph with deployed entities
for 10 sentries, four conventional emplacements, and four mine deployment systems.
The 20 imported offensive stratagems and 33 uniquely correlated support-weapon
call-ins remain available. The canonical GUI contract is
`sdk/StratagemAuthoringCapabilities.json`. It publishes one descriptor per semantic
field instance and never exposes native addresses, offsets, record indices, or
native resource identifiers.

```lua
local precision = hd2.stratagem("Orbital Precision Strike")

hd2.patch({
    id = "precision_cooldown",
    target = precision,
    field = hd2.fields.stratagem.definition_cooldown,
    expect = 80,
    value = 40,
})
```

Defensive stratagems keep the stratagem definition, deployed entity, mounted
weapon, and attack settings as separate semantic targets:

```lua
local emplacement = hd2.stratagem("E/AT-12 Anti-Tank Emplacement")
local entity = emplacement:deployed_entity()
local cannon = entity:weapon("primary")
local projectile = cannon:attack("primary"):projectile()

return hd2.plan({
    id = "anti_tank_emplacement",
    operations = {
        { id = "health", target = entity,
          field = hd2.fields.entity.health, expect = 300, value = 600 },
        { id = "mass", target = projectile, allow_shared = true,
          field = hd2.fields.projectile.mass, expect = 6500, value = 7000 },
    },
})
```

`stratagem:attacks()` returns each reviewed native backing object in the delivery
graph. A field descriptor identifies its attack role, exact baseline, backing
object, target-specific operation group, reviewed shared consumer scope, and plan
group. A transaction may contain fields from one operation group. Use `hd2.plan`
to coordinate an entity, mounted weapon, ProjectileSettings, DamageInfo,
ExplosionSettings, explosion DamageInfo, status, beam, arc, and heat objects.

All 18 deployment entities expose guarded health and armor authoring. Twelve
mounted weapons expose the safely resolved subset of ammo, fire rate, heat,
projectile, damage, explosion, beam, arc, and status fields. These APIs reuse the
same field constants and settings primitives as player and support weapons.

Mine stratagems currently resolve the deployment system only. Individual mine
entities, distribution, triggers, explosion/status ownership, targeting fields,
and deployed lifetime remain blocked. Projectile lifetime and penetration slowdown
also remain blocked because no shared schema-labelled native fields are proven.

Eagle definitions keep three separate concepts: ordinary stratagem cooldown,
per-stratagem uses before rearm, and the shared Eagle rearm definition. Editing
`eagle.rearm_time` requires `allow_shared = true` and affects all eight reviewed
Eagle offensive stratagems.

`stratagem.max_uses` remains readable metadata. Its finite value and unlimited
sentinel are structurally resolved, but mutation is blocked until definition-write
semantics are gameplay-proven. Barrage delivery arrays are preserved as delivery
structure; the SDK does not invent scalar shell or volley counts from them.

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
| `linked` | 33, including MS-11 Solo Silo (`deployable_silo`) and B/MD C4 Pack (`placed_item`) |
| `no_call_in` | SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool (`rootResolution` `NO_CALL_IN`) |

B/MD C4 Pack links to the placed charge through native loadout identity. The charge's loadout
item id is the call-in id, and the call-in package is owned only by the rack, the detonator, the
backpack, and the charge. The rack-delivered detonator (`thrower`) and backpack are published as
companion deliveries. SG-88 and CQC-72 have no StratagemDefinition at all: no stratagem carries
their loadout item ids or packages, and nothing native delivers them. See
[support-weapon authoring](support-weapon-api.md).

Seven linked weapons have ambiguous runtime roots: MG-43, M-105, EAT-17, MG-206, LAS-98,
B/FLAM-80, and CQC-20. Their call-in links are known and their stratagem cooldowns stay writable.
The relationship never lifts support-weapon write blocking, so their weapon fields remain blocked.

Each relationship has a reference-only `deliveryGraph`. Its nodes name the owning view
(`stratagem` or `support_weapon`), the semantic ID, and the target path or attack role. An editor
uses these to select existing `fieldInstances`; no fields are copied. For Solo Silo the graph is
stratagem call-in (cooldown) -> deployable silo -> missile -> `detonation` and `impact`
explosions. Edits still persist through the original target types.

## Shield Generator Relay shield and damage zones

Since 0.23.0 the FX-12 Shield Generator Relay exposes its shield projector separately from the
physical base. Both are components of the same deployed entity. The spawned runtime shield instance
remains unresolved, so the shield is authored through its typed configuration.

| Target | Field | Constant | Baseline |
| --- | --- | --- | --- |
| `deployed_entity():shield()` | `shield.radius` | `hd2.fields.shield.entity_radius` | 15 |
| `deployed_entity():shield()` | `shield.durability` | `hd2.fields.shield.entity_durability` | 4000 |
| `deployed_entity()` | `payload.lifetime` | `hd2.fields.payload.entity_lifetime` | 40 |
| `deployed_entity()` | `entity.health` / `entity.armor` | `hd2.fields.entity.*` | 450 / 2 |
| `deployed_entity():damage_zone('body_front')` | `zone.health`, `zone.armor`, `zone.affects_main_health` | `hd2.fields.zone.*` | 450 / 2 / 1 |

The `entity_` prefix avoids a clash with the legacy `hd2.fields.shield.radius` constants, which still
drive the unchanged 0.4 `ShieldRelay` proof. ShieldRelayImprovements proved radius, shield health,
lifetime, cooldown, and physical health in gameplay. The recharge delay and rate members are not
promoted, because their labels come only from an external export.

Every deployed entity also exposes its populated damage zones through `damage_zones()` and
`damage_zone(id)`, using the shared `HealthComponent` zone schema described in
[vehicle authoring](vehicle-authoring.md).

## Vehicle and backpack call-in definitions

Nine vehicle and 13 backpack StratagemDefinitions are listed with writable cooldowns. Each carries a
`delivers` link to the `hd2.vehicle` or `hd2.backpack` semantic ID of the entity it delivers.
