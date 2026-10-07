# Research scanner toolkit (`scripts/scan`)

Offline, read-only research tooling. Nothing here runs in game or writes game memory. The toolkit makes field
discovery systematic: compare whole families of entities, cluster members by correlated role, tie candidates to the
native code that reads them, and separate shared type data from per-instance state. Its output is **candidate
reports**. Promotion to the public API is still a reviewed step in each feature's own research script, under the
naming-proof standard: owner, layout, hidden-name length, active source, sharing, lifecycle and safety.

## Audit of the tooling before this pass

| Area | Existing tooling | Gap this pass closes |
| --- | --- | --- |
| Catalogue scanners | One `research_*.py` per feature, each with hand-picked components (for example `research_equipment_coverage.py` with its own `_flat` member flattener) | One typed view of **all 270 component tables** (`scan.tables`) and an inventory of every table (`research_component_catalogue.py`) |
| Component-data scanners | `StrongerOrbitalLaser/scripts/research/entity_report.py` and `probe_components.py` (one entity at a time), `research_entity_authoring.Native` | Any table, any entity, record ownership maps, regex entity selection, flattened paths with bitfields and vectors |
| Structured record diff | `migration/engine.py` (build-to-build structural re-identification); `research_attachment_selection_candidates.py` (two snapshots, caller-supplied values) | `scan.compare.Family`: side-by-side matrices across a whole family, variant diffs (`_mk2`, `_elite`, `_01`, ...) |
| Snapshot comparison | `snapshot_image.Snapshot`, `research_event_state.Mem`, `snapshot_regions.region_bytes`, per-feature validators | `scan.instances`: locate a loaded type table in a snapshot, find per-instance copies, classify copy members as copied type data or instance state, multi-snapshot diffs |
| Field clustering / fingerprinting | Layout fingerprints hard-coded per script (`TURRET_FINGERPRINT`, `MINEFIELD_FINGERPRINT`, ...), `correlate_primary_weapon_fields.py` (wiki vs snapshot for primaries) | `Family.clusters()` (members whose variation partitions coincide, plus numeric correlation); `EntityTables.fingerprint(component)` for any table |
| Donor comparison | Per-feature donor lists (custom payloads, projectile composition) | `compare.find_value` (reverse lookup of a published number across every table), `compare.presence` (components only some entities own = archetype markers) |
| Native call / reference scanners | `research_event_combat.Image` (`.pdata` map, memory-light RIP search), `research_event_state.Image` (pins, sweeps) | `scan.xref.CodeImage` for game.dll **and** the executable: global accessors, rel32 callers, immediates, strings, **field accesses per function with float use**, pins |
| Generated research JSON / domains | `generate_*.py` from research JSON; `regenerate_domains.py` | Common candidate format (`scan.report`, schema `hd2runtime.scan.candidates/1`) with one confidence vocabulary |
| Retained mission / ship snapshots | Seven retained snapshots; feature validators overlay writes | Bounded heap searches over the 12 GB captures (a full pass takes about 20 s once cached by the OS) |
| Community leads | Filediver Go structs read by hand | `scan.golib`: Go structs parsed with their binary layout and aligned to the type library; a lead is STRONG only when offset, size and hidden-name length all fit |

## Modules

| Module | Purpose |
| --- | --- |
| `scan/tables.py` | `tables.pinned()`: every component table, flattened member paths (`160[3].8`), hidden-name lengths, bitfields (`path:shift`), vectors, decoding, record owners, entity membership, resource and thin-hash names (leads) |
| `scan/compare.py` | `Family`, `presence`, `variant_groups` / `variant_diff`, `shared_type_report`, `find_value`, value-shape hints (leads, never names) |
| `scan/settings.py` | `SettingsView`: projectile, damage, explosion, arc and beam rows by native type, with the same flattened member paths |
| `scan/strides.py` | Array and struct-stride discovery in raw bytes (`score_strides`, `columns`, `runs`) for memory the type library does not describe |
| `scan/xref.py` | `CodeImage.from_snapshot('game.dll' / 'exe')`, cached under `build/scan-cache` |
| `scan/literals.py` | Identities that live in code: `CallLiterals` (the literal an argument register holds at every call site of a function, from the straight-line block before the call), `Dispatcher` (a BehaviorId / AbilityId jump table: handlers and stubs), `Attribution` (the dispatcher ids that run a call site, through up to three caller levels). Used by `research_explosion_identities.py` for explosion types passed as literals |
| `scan/instances.py` | `SnapshotReader`, `locate_records`, `find_copies`, `compare_copy`, `diff_snapshots` |
| `scan/golib.py` | `GoLibrary`, `align`, `align_tree`, `leads_for` |
| `scan/report.py` | `candidate`, `document`, `confidence`, `write`, Markdown tables |
| `scan/cli.py` | Command line over all of the above |

The protected modules no longer name their code section. `CodeImage` takes the code range from the exception
directory's functions below the protector's first section (game.dll `0x42B0..0x2110E8C`).

## Confidence vocabulary

| Label | Evidence |
| --- | --- |
| CONFIRMED | The native code that reads the member, and an exact published value or a passed live test |
| STRONG | A native read or an exact published value, plus a consistent hidden-name length and family differential |
| PLAUSIBLE | Layout, hidden-name length and differential agree; no active source shown |
| UNKNOWN | Layout only |

`report.confidence(evidence)` applies these rules mechanically. A research script may record more evidence (owner
counts, lifecycle), but it never labels above what the evidence supports.

## Typical workflow

```
py scripts/scan/cli.py family TurretComponentData --match "gatling_turret|rocket_turret|mortar_turret"
py scripts/scan/cli.py value 6.0 --kinds float            # where does a published value live?
py scripts/scan/cli.py golib WeaponChargeComponent        # community leads, with name-length fit
py scripts/scan/cli.py xref-global 0x3326688              # code that touches a component manager
py scripts/scan/cli.py xref-fields 0x38ADD0 --offsets 20,412
```

1. Select the family with `EntityTables.find` / `with_component`; check `presence` for archetype-only components.
2. `Family.describe()` gives the varying members, clusters and ownership (shared records need `allow_shared`).
3. Use `find_value` with published numbers. Exact agreement on several independent entities is strong evidence.
4. Find the reading code: the component manager's accessors, then `field_accesses` for the candidate offsets.
5. Check the lifecycle with `instances`: is the type record read live, or copied into a per-instance block?
6. Write a candidate report. Promote only what the feature's research script proves.

## Outputs of this pass

- `research/component-catalogue-F5FEE03DCFDB.json` (`scripts/research_component_catalogue.py`, `--check`
  supported): every table with its members, value statistics, sharing and Filediver leads.
- The feature reports in `research/*-components-F5FEE03DCFDB.json` (sentry, Eagle, vehicle/mech, hover pack) and
  the railgun, injury, gib-threshold and matchmaking reports. These are built on the toolkit.

Tests: `tests/test_scan_toolkit.py`. The algorithms use synthetic fixtures. The pinned-data checks skip when the
datalibrary or the retained snapshot is absent.
