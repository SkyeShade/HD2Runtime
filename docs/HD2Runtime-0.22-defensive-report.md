# HD2Runtime 0.22 defensive authoring report

The 0.22 pass uses the non offensive importer graph from commit `0b0c9fca9866be5f0841dc4aec19d01ece134db9` and the retained F5FEE03DCFDB snapshot. Research completed with `researchWrites=0`, `protectionChanges=0`, `fixtureFallback=disabled`; no launch or deployment was performed.

## Stratagems

- Sentries resolved: 10/10.
- Conventional emplacements resolved: 4/4.
- Mines/deployables resolved: 4/4 at stratagem and deployment-entity level. Individual mine entities, triggers, distribution, and attack objects remain unresolved.
- Cooldown writable: 71 catalog instances, including all 18 defensive roots.

## Entities

- Deployed entities resolved: 18.
- Health writable: 18.
- Armor writable: 18.
- Every promoted health/armor baseline exactly matches the importer value and every reviewed `HealthComponentData` record has one owner in the retained component index.
- No shared entity definition or multi-weapon entity was found in this graph slice.

## Weapons and attacks

- Mounted weapon branches: 12.
- Ammo writable instances: 44 across 11 mounted weapons; fire rate writable instances: 9. Arc velocity and beam radius are not labeled as fire rate.
- Defensive branches: 9 ProjectileSettings, 19 DamageInfo, and 7 ExplosionSettings.
- Defensive unusual branches: 1 BeamSettings, 1 ArcSettings, and 8 StatusEffectSettings. The full stratagem catalog totals remain 42 projectile, 83 DamageInfo, 39 explosion, 2 beam, 1 arc, and 21 status branches.
- Heat writable instances: 4. Spray settings were retained as a blocked family where no safe writable settings owner was proven.

The principal regression anchor is E/AT-12 Anti-Tank Emplacement. Its catalog records health 300, armor 2, primary cannon capacity 30, projectile mass 6500, velocity 625, drag 0.75, gravity 1, and linked impact explosion radii 3/6/7. All are exposed through the existing semantic primitives and guarded by exact baselines.

## Metadata and proof packages

The public catalog contains 1,382 canonical field instances, 226 physical backing objects, and 327 target-specific operation groups. An exact instance audit proves that every internal promoted descriptor has one published canonical instance. Each instance retains its deployed entity, weapon, and attack path, exact baseline, writable state, reviewed shared acknowledgement scope, operation group, plan group, units, and provenance without publishing native record identities.

The release builder generates the public-API-only example packages `AntiTankEmplacementProof`, `ConventionalSentryProof`, `ExplosiveSentryProof`, and `UnusualSentryProof`. No `MineProof` is generated because individual mine attack ownership is not proven. They are built as release artifacts and are never loaded or deployed by the builder.

## Blockers

Target range, traverse, tracking speed, firing arc, projectile lifetime, penetration slowdown, and deployed lifetime remain blocked because ownership is not unambiguous in the retained evidence. Mine instances and trigger/distribution internals remain deferred. The Grenadier Battlement's imported mounted weapon has no proven native component-to-attack chain. Max uses remains read only pending mutation proof. The unusual family has beam, arc, and status metadata where settings ownership is established; spray has no promoted settings write in this pass.

## Validation

The generated catalogs are checked for freshness, canonical instance uniqueness, absence of raw native identifiers, deployed entity API paths, exact baseline validation, shared settings acknowledgement, and multi object `hd2.plan` composition. The full test suite is the release gate; no game launch or deployment step is part of this pass.
