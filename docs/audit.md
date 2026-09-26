# Sibling audit

Only existing source, retained decoded inputs, and saved evidence were used.
No game decompilation, new-system research, deployment, or game launch was done.
All project writes are within HD2Runtime. Existing mods remain regression sources.

| Requested project | Local project and useful infrastructure |
| --- | --- |
| Jar5AP4 | `Jar-5_buff`: bounded entity/projectile/damage discovery, grouped LDLD parsing, typed joins, unique owners, complete stable captures, 12-byte transaction and guarded rollback |
| BastionReArmored | Exact resource membership, relative/relocated membership normalization, segmented guarded reads, HealthComponentData records and 38 zones, page-scoped multi-field transactions |
| Maelstrom tank | Present in BastionReArmored: independent resource `0xB0C9FAF4AF8903F9`, health record 427. No separate Maelstrom project was found. |
| StrongerOrbitalLaser | Payload/OrbitalAbilityComponentData to DamageInfo linkage, generated settings framing, verified 60/60 damage and 0.1 interval, allocation-size bands, independent damage root |
| ShieldRelayImprovements | Shield, payload and health resource ownership, relocated membership, checked game.dll-relative stratagem root and runtime table, package/payload join, saved current cooldown capture |
| JumpPackImprovements | Two-component validation, startup callback handling, recharge and movement field evidence, transaction rollback and protection checks |
| ReticleAmr | Read-only Win32 capability, disk module SHA-256, typed WeaponDataComponentData mapping, enum context and stable read, one-field patch with full-record/page verification |

`360BastionTurret` and `HD2ModAPI` exist as sibling directories but had no relevant
source in the initial file listing. No systems were inferred from those names.

The common runtime build fingerprint is EXE
`F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06`
and game.dll
`2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E`.
Encoded installed files and decoded retained data have different hashes; they are
separately recorded and must not be substituted for each other.

Reusable code was extracted as small binary readers, a read-only native adapter,
schema descriptors, ownership validators and a scheduler. Gameplay entrypoints,
experiment selectors, release presets, native research and gameplay writers were
not copied into the runtime. Platform bindings and the small offline Lua runner
were adapted from ReticleAmr. Generic decoded format readers and the archive
writer came from Jar-5_buff. HD2Runtime's resolver and declarative domains are new.

## Findings that affect correctness

* JAR-5's projectile link belongs to **ProjectileWeaponComponentData**; AMR's
  reticle enum belongs to **WeaponDataComponentData**. They are different schemas.
* Bastion and Maelstrom have different resource owners and health records even
  though the preset logic and most health-zone structure are shared.
* The entity allocation can have a writable tail in the same allocation. The
  reader validates each segment it uses, without assuming the tail's extent.
* Resource IDs remain 64-bit hex strings. Converting arbitrary IDs to a Lua
  number loses precision. Runtime pointers are only accepted within exact integer
  range and within their validated owner.
* Shield's historical stratagem type 21 differs from the saved current type 22.
  The runtime validates type 22, ID, package, payload, group/row, all runtime-table
  pointers and the complete grouped extent. It does not blindly use the old row.
* Some older research files deliberately say “unproven” although later gameplay
  reports exist. Provenance points to the appropriate later evidence; schema
  offsets alone never establish gameplay semantics.
* JAR-5's standard/durable values have structural/schema evidence in the audited
  project. That project calls its AP4 artifact a gameplay test; HD2Runtime does
  not invent a returned gameplay confirmation.
* Maelstrom support is structurally extracted from the release. Its individual
  field gameplay flags remain conservative because the reviewed proof history
  does not independently establish every Maelstrom behavior.

## Regression inputs

`scripts/import_fixtures.py` is an explicit audit refresh tool. It reads siblings,
checks reviewed decoded entity/library hashes, writes sparse fixtures, and records
source SHA-256 values. Normal build and tests have no sibling dependency. The
stratagem fixture contains the saved current 400-byte relay row with its payload
pointer relocated into synthetic grouped tables; the other stratagem rows are
test scaffolding, not captured game data. This exercises the joins and rejection
paths without pretending to reproduce a complete current-process snapshot.
