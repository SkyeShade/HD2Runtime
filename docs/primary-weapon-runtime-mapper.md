# Primary Weapon Runtime Mapper

The mapper is a separate read-only diagnostic mod for HD2Runtime 0.9.0. Install
Bingus Shared Loader and HD2Runtime once, then install the mapper package for one
diagnostic session. It never writes game memory and its archive contains no
HD2Runtime implementation, native memory adapter, page-protection function, or
fixture fallback.

The shared runtime performs one fingerprinted allocation discovery pass. It
parses the reviewed entity map and the `ProjectileWeaponComponentData` and
`WeaponDataComponentData` indices once, then reuses the parsed projectile and
damage settings tables for every candidate. One candidate is processed per
update tick. A candidate failure is captured in that candidate's diagnostics
and does not end the scan. A stable reread closes the scan.

Current runtime fingerprints are standard damage, durable damage, all four AP
lanes, demolition, stagger force, push force, projectile type, linked damage
type/group/row, crosshair type where `WeaponDataComponentData` is present, fire
rate, pellet count, projectile velocity, mass, drag, and gravity. The latter six
fields are structural/correlation-proven from the build-bound snapshot and are
explicitly pending gameplay confirmation. Capacity remains unmapped; the mapper
does not guess an offset for it.

Matching compares only fields present on both sides. Exact integer fields use
exact equality. Wiki-rounded velocity uses a 2 m/s tolerance, fire rate uses a
1 RPM tolerance, projectile mass uses 0.1 g, and drag/gravity use 0.01. Each
field has a fixed evidence weight. Scores are evidence points, not percentages.

States are deterministic:

- `EXACT`: at least five compared fields and three high-value matches, no
  mismatch, at least 50 evidence points, and a 12-point lead.
- `STRONG`: at least four compared fields and two high-value matches, no
  high-value mismatch, at least 30 points, and a 10-point lead.
- `AMBIGUOUS`: some plausible evidence exists but the stronger thresholds or
  score margin are absent.
- `UNMATCHED`: no candidate reaches 15 points with a high-value match.

The first normalized attack is the identity fingerprint. Secondary explosions,
statuses, sprays, beams, melee attacks, and underbarrel chains remain attached
to the embedded wiki record but never replace the primary identity. Runtime
secondary attacks are recorded only if a reviewed generic linkage resolves
them; version 0.9.0 resolves the projectile chain and the offline player-catalog
matcher considers every compatible attack branch.

After completion, the mapper writes these files under
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs`:

- `PrimaryWeaponRuntimeMap.json`
- `PrimaryWeaponRuntimeMap.log`
- `weapon_identity_candidates.json`

Typical log lines are:

```text
[HD2Runtime] PRIMARY_WEAPON_MAP resource=0x... entity_row=... status=EXACT resolution=RESOLVED
[HD2Runtime] PRIMARY_WEAPON_MAP resource=0x... rank=1 wiki="JAR-5 Dominator" score=75 matched=9 mismatched=0
[HD2Runtime] PRIMARY_WEAPON_MAP complete candidates=... failures=... writes=0 protection_changes=0 fixture_fallback=disabled
```

Build the package from a clean commit with:

```powershell
py -3.14 -B scripts/build_primary_weapon_mapper.py
```

The build does not deploy the package or launch HD2.
