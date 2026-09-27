# R-72 Censor attachment-selection candidates

This report compares the controlled Extended and Short snapshots with an
exact-value-only scan of captured regions. The machine-readable report contains
every hit, VA, allocation, region, aligned U32/U64 context, and bounded pointer
observation:
`research/attachment-selection-candidates-F5FEE03DCFDB.json`.

## Exact occurrence sets

| Identity | Extended snapshot | Short snapshot |
| --- | ---: | ---: |
| Extended option `0x536662C0` | 24 | 4 |
| Short option `0x33EAAA65` | 2 | 2 |
| Extended AddPath `0x37C2891774B38C87` | 45 | 9 |
| Short AddPath `0x986E6696B34B8902` | 9 | 9 |

All absolute hit VAs differ between captures because the identity-bearing
allocations were rebased or recreated. Six allocation-relative hit layouts
match across captures.

## Stable option-definition table

The strongest structural match contains both choices in both snapshots:

| State | Allocation | Extended record / ID / AddPath | Short record / ID / AddPath |
| --- | --- | --- | --- |
| Extended capture | `0x0000021ED03A0000` | `+0x3CD8` / `+0x3CE0` / `+0x3CF8` | `+0x3D30` / `+0x3D38` / `+0x3D50` |
| Short capture | `0x000002579B680000` | `+0x3CD8` / `+0x3CE0` / `+0x3CF8` | `+0x3D30` / `+0x3D38` / `+0x3D50` |

Each descriptor is `0x58` bytes. Its option ID is at `+0x08` and AddPath at
`+0x20`. Coexistence in both states identifies this as an option-definition
table, not the current selection.

Exact U64 searches found no references to either descriptor start, option-ID
field, or AddPath field. The first U64 in copied descriptors points to nearby
objects in the canonical table, which identifies shallow option-definition
copies rather than a reference to the selected row.

## State-only candidates

| Allocation / region | Complete rows | Nearby pattern | Structural result |
| --- | ---: | --- | --- |
| `0x0000021EC4D40000`, region 5369, `0x201000` bytes, private RW | 15 Extended | 15 Standard then Extended pairs at `0x58` stride | No Short row, Censor resource, slot/option pair, second category, or incoming reference |
| `0x0000021F510D0000`, region 12851, `0x10000` bytes, private RW | 1 Extended | One Standard then Extended pair at `0x58` stride | No Short row, Censor resource, slot/option pair, second category, or incoming reference |

The 15 descriptor starts in the first allocation are:

`0x0000021EC4D50650`, `0x0000021EC4D521B8`,
`0x0000021EC4D55980`, `0x0000021EC4D57438`,
`0x0000021EC4D5ACB0`, `0x0000021EC4D5C710`,
`0x0000021EC4D619E8`, `0x0000021EC4D66CC0`,
`0x0000021EC4D6BF98`, `0x0000021EC4D71270`,
`0x0000021EC4D76548`, `0x0000021EC4D7B878`,
`0x0000021EC4D85E80`, `0x0000021EC4D9FCB8`, and
`0x0000021EC4DB9B48`. The second allocation's descriptor starts at
`0x0000021F510DA950`.

Representative outgoing pointers from both candidates target the canonical
option allocation at offsets `+0x47EC`, `+0x4808`, `+0x480C`, `+0x4828`, and
`+0x6130`. A final exact one-hop search for both candidate allocation bases and
all 16 descriptor starts found zero raw hits and zero aligned pointer hits.

## Decision

No stable current-selection, saved-preset, loadout, or weapon-construction owner
is proven. The Short capture has no symmetric Standard-then-Short candidate.
Searching low-entropy indices without an owner anchor would exceed the bounded
scope, so no index scan was performed. Persistence and expect/value semantics
remain unproven, and no scalar or coordinated attachment write is promoted.

Safety remained `researchWrites=0`, `protectionChanges=0`, and
`fixtureFallback=disabled`.
