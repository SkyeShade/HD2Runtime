# HD2Runtime 0.22 defensive authoring report

The 0.22 pass uses the non offensive importer graph from commit `0b0c9fca9866be5f0841dc4aec19d01ece134db9` and the retained F5FEE03DCFDB snapshot. Research completed with `researchWrites=0`, `protectionChanges=0`, `fixtureFallback=disabled`; no launch or deployment was performed.

## Stratagems

- Sentries resolved: 10/10.
- Conventional emplacements resolved: 4/4.
- Mines/deployables resolved: 4/4 at stratagem and deployed entity level; mine trigger and distribution authoring is deferred.
- Cooldown writable: 71 catalog instances, including all 18 defensive roots.

## Entities

- Deployed entities resolved: 18.
- Health writable: 18.
- Armor writable: 18.
- Shared entity definitions: canonical backing object metadata is published per field instance; no multi weapon entity was found in this graph slice.

## Weapons and attacks

- Mounted weapon branches: 12.
- Ammo writable instances: 44; fire rate writable instances: 11.
- Projectile branches: 42; DamageInfo branches: 83; explosion branches: 39.
- Beam branches: 2; arc branches: 1; status branches: 21.
- Heat writable instances: 4. Spray settings were retained as a blocked family where no safe writable settings owner was proven.

The principal regression anchor is E/AT-12 Anti-Tank Emplacement. Its catalog records health 300, armor 2, primary cannon capacity 30, projectile mass 6500, velocity 625, drag 0.75, gravity 1, and linked impact explosion radii 3/6/7. All are exposed through the existing semantic primitives and guarded by exact baselines.

## Metadata and proof packages

The public catalog contains 1,384 canonical field instances, 228 backing objects, and 228 operation groups. Each instance retains its deployed entity, weapon, and attack path, exact baseline, writable state, shared acknowledgement scope, operation group, plan group, units, and provenance without publishing native record identities.

Generated proof packages are under [`proof/`](../proof/): `anti_tank_emplacement.lua`, `conventional_sentry.lua`, `explosive_sentry.lua`, `unusual_sentry.lua`, and the deferred `mine.lua` record. They are not loaded by the runtime launcher.

## Blockers

Target range, traverse, tracking speed, firing arc, and deployed lifetime remain blocked because ownership is not unambiguous in the retained evidence. Mine trigger/distribution internals remain deferred. Max uses remains read only pending mutation proof. The unusual family has beam, arc, and status metadata where settings ownership is established; spray has no promoted settings write in this pass.

## Validation

The generated catalogs are checked for freshness, canonical instance uniqueness, absence of raw native identifiers, deployed entity API paths, exact baseline validation, shared settings acknowledgement, and multi object `hd2.plan` composition. The full test suite is the release gate; no game launch or deployment step is part of this pass.
