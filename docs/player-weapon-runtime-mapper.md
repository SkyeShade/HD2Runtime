# Offline Player Weapon Runtime Mapper

HD2Runtime 0.11.0 accepts the normalized 80-weapon player catalog containing 55
primary and 25 secondary weapons. The scanner enumerates structurally owned
weapon resources once. It treats entity/component composition as the identity
root and resolves compatible attacks through Projectile, Arc, Beam, Spray,
Melee, and round-feed paths. Matching happens offline after those records have
been read from a build-bound snapshot.

Run the packaged SDK command:

```powershell
py -B hd2.py snapshot scan-player-weapons <snapshot.hd2snap> wiki_player_weapons.json
```

Use `--output` and `--summary-output` to select paths. Defaults are
`PlayerWeaponRuntimeMap.json` and `player_weapon_identity_summary.json`; the
identity catalog is written beside the report as
`PlayerWeaponRuntimeMap.identity-candidates.json`.

The catalog transform retains slot, category, traits, every attack, attack
kind, projectile/beam/area/charge data, explosion links, and normalized damage,
penetration, projectile, and force fields. Projectile, explosion, status,
melee, beam, arc, and spray attacks remain separate branches.

The matcher first requires a compatible runtime attack kind and enforces the
reviewed primary/secondary slot whenever it is present. It then selects
the best damage and projectile evidence branches inside each weapon. When those
branches differ, both are reported with `branchMode="composite"`; this does not
merge identities across weapons. The PLAS-101 runtime chain is the known
example: damage matches `P`, while its 350 m/s projectile settings match
`PLAS-101 P`.

`EXACT`, `STRONG`, `AMBIGUOUS`, and `UNMATCHED` remain deterministic evidence
states. A catalog identity is `UNIQUE` only when one EXACT/STRONG runtime
candidate supports it. Equal resources remain `DUPLICATE`, and close wiki
identities remain explicit in `credibleWikiIdentities`. Slot and category are
reported metadata and do not override contradictory gameplay fields.

The current-build mapper also reads two weapon-level properties. A
`LoadoutPackageComponentData.BundleTag` maps to `primary` or `secondary` only
for the two reviewed tag values. Unknown or absent tags remain unclassified.
Capacity comes from `WeaponMagazineComponentData.Capacity`, or from
`WeaponRoundsComponentData.MagazineCapacity[0]` for round-fed weapons. The
catalog capacity excludes a separately reported chambered round. If a nonzero
default Magazine customization is present, effective capacity remains
unresolved because its attachment AddPath has not been mapped; the mapper
reports the base value but does not compare it as effective capacity.

These mappings are schema-labelled and correlation/structural-proven against
the unique snapshot identities. They remain pending gameplay and native
consumer confirmation. Runtime projectile type, damage type, and crosshair
type remain structural evidence without corresponding wiki IDs.

The current build has reviewed structural adapters for:

- `ArcWeaponComponentData.Type` to `ArcSettings`, then
  `ArcInfo.DamageInfoType`;
- `BeamWeaponComponentData.Type` to `BeamSettings`, then
  `BeamInfo.DamageInfoType`;
- `SprayWeaponComponentData.DamageInfoType`;
- `MeleeWeaponComponentData.DamageInfoType`;
- `WeaponRoundsComponentData` primary and alternate projectile types.

`WeaponDataComponentData` ownership and record identity are reported even when
the projectile is shared or supplied by an unresolved customization. Its
schema-labelled spread, sway, ergonomics, fire-mode context, and crosshair data
are weapon-level evidence. Shared projectile/settings groups retain each
distinct resource and WeaponData record; a shared projectile never collapses
the resources into one identity.

All new family links are schema-labelled structural evidence pending gameplay
and native-consumer confirmation. The build-bound evidence and shared-projectile
analysis are in `research/weapon-family-expansion-F5FEE03DCFDB.json`.

The command uses `SnapshotMemoryReader`, enforces the captured fingerprints,
and reports `writes=0`, `protectionChanges=0`, and
`fixtureFallback="disabled"`.
