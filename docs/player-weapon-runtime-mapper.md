# Offline Player Weapon Runtime Mapper

HD2Runtime 0.9.0 accepts the normalized 80-weapon player catalog containing 55
primary and 25 secondary weapons. The scanner enumerates structurally owned
`ProjectileWeaponComponentData` resources once and resolves their linked
`ProjectileSettings` and `DamageInfo` records. Matching happens offline after
those records have been read from a build-bound snapshot.

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

The matcher first requires a compatible runtime attack kind. It then selects
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

Capacity remains unmapped. Runtime projectile type, damage type, and crosshair
type are preserved as structural evidence, but they are not compared to a wiki
ID that the catalog does not provide.

The command uses `SnapshotMemoryReader`, enforces the captured fingerprints,
and reports `writes=0`, `protectionChanges=0`, and
`fixtureFallback="disabled"`.
