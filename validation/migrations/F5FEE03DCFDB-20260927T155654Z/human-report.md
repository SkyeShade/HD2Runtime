# HD2Runtime build migration report

Source: HD2Runtime 0.26.1 (0.26.1 @ ccc9b4f86e3a), build F5FEE03DCFDB
Target: build F5FEE03DCFDB — snapshot F5FEE03DCFDB-20260927T155654Z.hd2snap captured 2026-09-27T15:57:52Z

| | Source | Target |
|---|---|---|
| Executable SHA-256 | `F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06` | `F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06` |
| game.dll SHA-256 | `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` | `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` |
| Build profile | F5FEE03DCFDB | F5FEE03DCFDB |

Target inputs: snapshot `F5FEE03DCFDB-20260927T155654Z.hd2snap`. Snapshot extraction cache: reused (build\migration-cache\F5FEE03DCFDB-2E2C3B7C2500\6E679EF36A8907267C840612, key 6E679EF36A8907267C840612).

## Confidence summary

- Previously writable fields: 6652
- Recovered automatically: 100.0% (6652 carried, 0 rebound)
- Downgraded to read-only: 0.0% (0)
- Needing manual review: 0.0% (0)
- Unsafe stale writes carried forward: 0

## Totals

| State | Fields |
|---|---|
| EXACT | 7539 |
| MOVED | 0 |
| BASELINE_CHANGED | 0 |
| LAYOUT_CHANGED | 0 |
| AMBIGUOUS | 0 |
| LOST | 0 |
| BLOCKED | 0 |
| UNCHECKED | 0 |

## Recovered per category

| Category | Fields | Previously writable | Recovered | States |
|---|---|---|---|---|
| Magazine attachments | 233 | 233 | 233 | EXACT 233 |
| Boosters | 42 | 42 | 42 | EXACT 42 |
| Vehicles and backpacks | 758 | 736 | 736 | EXACT 758 |
| Player weapons | 3306 | 2457 | 2457 | EXACT 3306 |
| Drop-pod payloads | 248 | 240 | 240 | EXACT 248 |
| Stratagems | 1464 | 1456 | 1456 | EXACT 1464 |
| Support weapons | 1008 | 1008 | 1008 | EXACT 1008 |
| Vehicle weapons | 480 | 480 | 480 | EXACT 480 |

## PREVIOUSLY SUPPORTED BUT NO LONGER SAFELY WRITABLE

None. Every previously writable field was re-proven.

## Changed baselines

None.

## Ambiguous (0)

None.

## Lost (0)

None.

## Blocked (0)

None.

## Unchecked (inputs cannot prove either way) (0)

None.

## Relationships

INTACT 289, UNCHECKED 130

- UNCHECKED: attachment_compatibility 37, stratagem_icon 93

## New candidates (unreviewed, not writable)

- Entities: 0 ()
- Settings rows: 0
- Stratagem ids: 0
- Entity deltas (attachments): 0
- Component types: none

Next steps: docs/game-update-migration.md.
