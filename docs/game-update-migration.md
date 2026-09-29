# Helldivers 2 updated — what do I do?

A game update can move, resize, renumber or remove every native table that HD2Runtime writes. The runtime
refuses to write on an unknown build: `fingerprint.require` checks the executable and game.dll hashes.
Nothing unsafe happens in game. However, every mapping stays unavailable until it is re-proven for the new
build.

The migration tooling does that re-proving. It starts from the previous release's generated tables:

- semantic IDs, native identities and reviewed baselines;
- chains, relationships and shared scope.

It then re-identifies each field in the new build from structural evidence only. Names and addresses are
never used as proof. Safe mappings are recovered automatically. Anything it cannot prove is downgraded to
read-only, with the evidence a reviewer needs. It never carries a stale write forward.

All of this is offline developer tooling under `scripts/`. None of it ships in the runtime ZIP or runs in game.

## The eight steps

Run everything from the HD2Runtime checkout. `<new>` below means the new build ID: the first 12 hex digits of
the new `helldivers2.exe` SHA-256.

### 1. Capture a snapshot of the new build

1. Install the current HD2Runtime runtime ZIP, plus `HD2Runtime-SnapshotCapture-<version>.zip` (built by
   `py scripts/build_snapshot_capture.py`).
2. Start the game and enter the ship.
3. Wait for the capture. It starts 60 seconds after load; see `docs/snapshots.md`.

The snapshot is written to:

```text
%LOCALAPPDATA%\HD2Runtime\local_research\snapshots\<new>-<timestamp>.hd2snap
```

Also extract the new build's Filediver datalibrary:

- `generated_*.dl_bin`
- `dl_library.dl_typelib`
- `hashes/hashes.txt`, if available

The type library is not in process memory. When game.dll changed, the runtime profile cannot yet locate the
tables in the snapshot, so the datalibrary also supplies the table contents.

### 2. Migrate

```powershell
py scripts/migrate_build.py --from-runtime 0.26.1 `
  --snapshot "$env:LOCALAPPDATA\HD2Runtime\local_research\snapshots\<new>-<timestamp>.hd2snap" `
  --datalibrary <path-to-new>\datalibrary
```

- `--from-runtime` accepts a release version, a git revision, or `current` (the working tree).
- The previous release is evaluated in the build it was generated for, read from that build's reference
  snapshot in `schemas/build_profile.json`.
- With only a datalibrary (no snapshot), pass the fingerprints instead: `--exe-sha <sha> --dll-sha <sha>`.
  `--build <id>` also works when the build is already in `schemas/build_profile.json`.
- `--label` adds a suffix to the output directory, which is needed for same-build runs.
- `--no-cache` forces snapshot re-extraction.

The output goes to `validation/migrations/<new>/`. Per-field fingerprints for both builds are recorded under
`research/build-history/` (see "Historical fingerprints" below).

### 3. Inspect the report

Open `validation/migrations/<new>/human-report.md`. It lists:

- source and target fingerprints, inputs and cache provenance;
- the confidence summary;
- totals per state;
- recovered counts per category;
- **PREVIOUSLY SUPPORTED BUT NO LONGER SAFELY WRITABLE**;
- changed baselines;
- ambiguous, lost, blocked and unchecked fields;
- relationships;
- new candidates.

The machine-readable files are:

| File | Contents |
| --- | --- |
| `summary.json` | fingerprints, totals, per-category recovery, confidence percentages |
| `exact.json` … `unchecked.json` | one file per state; every non-exact field with evidence, source and target coordinates, and its decision |
| `writable-diff.json` | every previously writable field whose write support changes |
| `relationships.json` | every relationship, with its state and the fields it guards |
| `new-candidates.json` | unreviewed new entities, settings rows, stratagem IDs and attachment deltas |
| `plan.json` | what `apply_migration.py` consumes |

Each field ends in exactly one state:

| State | Meaning | Auto-apply |
| --- | --- | --- |
| EXACT | Identity, location, layout, scope and baseline bytes all unchanged | Carried forward |
| MOVED | Identity proven; record index, index row, settings row or delta data offset changed | Rebound to the new coordinates, if identity is structural |
| BASELINE_CHANGED | Identity proven; the reviewed default changed (old → new recorded) | Rebound with the new default, only with structural identity |
| LAYOUT_CHANGED | The member moved inside its record, proven by a unique type-library signature or an aligned run of neighbours | Rebound to the new offset; a match found only by counting equal signatures ("ordinal") is downgraded |
| AMBIGUOUS | More than one candidate fits the evidence | Read-only |
| LOST | The owner, record, member or delta entry no longer exists | Read-only |
| BLOCKED | Identity found, but a guard fails: shared scope widened, member type changed, a relationship the field depends on broke, or a type-only settings row changed | Read-only |
| UNCHECKED | These inputs cannot decide, e.g. game.dll-resident booster tables or stratagem rows under a new game.dll | Read-only |
| NEW (candidate) | Present only in the new build | Never written; needs a reviewed mapping |

When several states apply, the report shows the worst, in the order LOST > BLOCKED > AMBIGUOUS > UNCHECKED >
LAYOUT_CHANGED > BASELINE_CHANGED > MOVED > EXACT.

#### How identity is proven

| Backing | Evidence |
| --- | --- |
| Component records | The owning resource hash still owns a record of that component type. The record's owner set did not gain owners; an unreviewed new co-owner widens the write scope and blocks the field. |
| Settings rows | The runtime's own native links are followed from the owning weapon: ProjectileWeapon → projectile → damage and impact/expiry explosion → explosion damage, plus the arc, beam, spray, melee, explosive and WeaponRounds links. Every source path must reach the same row in the new build. Rows with no weapon chain are proven through every source-build consumer that reaches them. Rows with no consumer at all fall back to their record type, and are accepted only when the row content is byte-identical. |
| Magazine attachment deltas | The delta resource, its component (type indices are remapped by component name) and the member offset. |
| Stratagem rows | The stratagem ID, and only under an identical game.dll. |
| Layouts | Member signatures from each build's own type library: storage, atom, count, hidden-name length and size. Nested structs match by type hash. Both the 72-byte (current) and 52-byte (older) member formats are read. |

### 4. Resolve the review items

Every AMBIGUOUS, LOST, BLOCKED or UNCHECKED field has a `review` block with:

- the previous semantic key, native identity and baseline;
- candidates and why each matched (new resources owning the same components with an identical record,
  target members sharing the signature, rows with identical content under a new type, and so on);
- which evidence failed;
- what extra evidence would tell the candidates apart.

Decide each one:

- **Leave it read-only.** This is always safe, and it is the default.
- **Fix the source research.** Re-run the domain's research script against the new snapshot, for example
  `research_weapon_composition.py`, `research_stratagem_authoring.py`, `research_booster_native.py` or
  `research_vehicle_weapons.py`. Correct any reviewed identity it cannot re-derive. The generators then
  produce proven tables for the new build directly.
- **Re-run step 2** after adding evidence. Candidates are never promoted automatically. NEW entities are
  unnamed and stay unwritable until a reviewed mapping names them.

### 5. Apply

```powershell
py scripts/apply_migration.py validation/migrations/<new> --dry-run
py scripts/apply_migration.py validation/migrations/<new>
```

This writes `schemas/build_migration.json`. It holds one guarded patch per changed field:

- rebind to the proven coordinates;
- update the reviewed default;
- or set `editable=false` (for pod racks, `writable=false`) with the migration reason.

The runtime checks that flag before writing, for magazine attachments and boosters too. Before writing, the
patches are simulated on the current generated tables. Any field that would stay writable without proven
target coordinates aborts the apply ("unsafe stale writes"). The result is recorded in
`validation/migrations/<new>/apply-report.json`.

### 6. Regenerate

1. Add the new build to `schemas/build_profile.json`:
   - `exeSha256` and `gameDllSha256`;
   - `referenceSnapshot`;
   - the `datalibrary` path and SHAs.

   Make it `active`. Research and validation scripts read the build identity and reference snapshot from
   there.
2. Refresh the runtime profile `schemas/current.lua` for the new build with `scripts/import_fixtures.py`.
   This step is still manual: update its pinned datalibrary, fingerprints and table descriptors.
3. Regenerate every domain table and SDK file:

   ```powershell
   py scripts/regenerate_domains.py
   ```

   Each generator applies `schemas/build_migration.json` only while `schemas/current.lua` is the overlay's
   target build. For any other build the overlay is ignored, so a migration can never be applied to the
   wrong build. Every patch also re-checks its guard, and a stale overlay fails loudly.

### 7. Validate

```powershell
py scripts/migrate_build.py --from-runtime 0.26.1 --snapshot <new snapshot> --label post-profile
py scripts/validate_migration.py validation/migrations/<new>
```

With the runtime profile in place, the first command re-checks what needed the new game.dll: stratagem rows,
status settings and stratagem relationships.

`validate_migration.py` checks, and records in `post-validation.json`:

- migration safety: 0 unsafe stale writes, and nothing writable behind a broken relationship;
- the overlay targets the active build;
- generator freshness;
- every snapshot validator against the new reference snapshot;
- examples;
- SDK, migration and full tests.

It then prints the confidence summary:

```text
Recovered automatically: …%
Downgraded to read-only: …%
Needing manual review:   …%
Unsafe stale writes carried forward: 0
```

### 8. Build

1. Bump `VERSION` and write `docs/releases/<version>.md`.
2. Commit, then run:

```powershell
py scripts/build_release.py
py scripts/validate_packaged_runtime.py build/HD2Runtime-<version>-runtime.zip
py scripts/validate_migration.py validation/migrations/<new> --runtime-zip build/HD2Runtime-<version>-runtime.zip
```

The packaged validation runs the shipped archive on the game's `lua51.dll` with late resource lookups disabled.
Do not tag or publish until it passes.

## Caching and provenance

Snapshot extraction is cached under `build/migration-cache/<exe12>-<dll12>/<key>/`. The key hashes:

- the snapshot header (fingerprints, capture time and region index);
- the file size;
- the extractor version.

A different capture, or a changed extractor, can therefore never reuse another capture's tables. Every
cached table's SHA-256 is re-verified on load. The report records whether the cache was reused, with its key.
Datalibrary inputs are not cached; their entity and type-library hashes are recorded instead.

## Historical fingerprints

`research/build-history/<build>.json` records one compact line per semantic field per build:

```text
"<field key>": "component|WeaponDataComponentData|0x…|<recordIndex>/<indexRow>/<ownerCount>|+<offset>|<baseline>"
"<field key>": "settings|damage|<recordType>|<group>/<row>|+<offset>|<baseline>"
"<field key>": "delta|0x…|<componentIndex>+<componentOffset>|<dataOffset>|<baseline>"
```

Fields whose identity is not proven in a build are `null`. These files are evidence for reviewers and future
migrations. The runtime never reads them.

## Real migrations run for 0.26.1

- **Same build, different capture** (`F5FEE03DCFDB-20260927T155654Z` and `…160033Z`): all 7,539 fields are
  EXACT, and every relationship is intact or unchecked.
- **Cross-build** (0.26.1 on F5FEE03DCFDB against the previous build D8E23968D141, from its retained
  datalibrary). Every release so far targets F5FEE03DCFDB, so this runs backwards in time, but the structural
  delta is real:
  - WeaponDataComponent is 16 bytes larger and WeaponRounds 4 bytes larger;
  - component type indices are shifted;
  - settings record types are renumbered;
  - the type-library member format differs;
  - weapons and vehicles are added.

  Results:
  - 78.6% of the 6,652 writable fields are recovered automatically (439 carried, 4,792 rebound);
  - 21.4% are downgraded;
  - 0 unsafe stale writes.

  The downgrades break down as:
  - fields of the AR-11 Arbitrator and TD-110 Maelstrom, which do not exist in that build (LOST);
  - game.dll-resident booster tables (UNCHECKED);
  - stratagem rows under a different game.dll (UNCHECKED);
  - stratagem settings rows that no weapon chain reaches and whose content changed (BLOCKED);
  - ordinal-only layout matches.

  The executable/game.dll pairing of that datalibrary is inferred from project history (see
  `schemas/build_profile.json`).

## What still needs a person

- Refreshing `schemas/current.lua` (the runtime profile's native table descriptors and stratagem RVAs) for a
  new game.dll.
- game.dll-resident booster tables: re-run `scripts/research_booster_native.py`.
- Automatic asset loading (`domains/package_residency.lua`): re-run `scripts/research_package_residency.py`
  against a new-build snapshot, then `scripts/regenerate_domains.py`. The research re-derives the loader
  functions and engine layout from code patterns. Until then, `core/assets` fails closed: the loader's
  code-byte proofs fail, and reference swaps that need another package are rejected with
  `ASSET_UNAVAILABLE`, keeping the vanilla reference. Writes without a package dependency are unaffected.
  Live evidence (`research/package-residency-live-evidence.json`) is recorded against build F5FEE03DCFDB;
  re-run the live asset tests on the new build before relying on it.
- Stratagem settings rows that no weapon or entity chain reaches (eagle and orbital payloads). They are proven
  only when their content is unchanged.
- Customization-catalog and unlock-list attachment compatibility, and stratagem icons. The migration reads
  neither, so they stay UNCHECKED.
- Naming and reviewing NEW candidates.
