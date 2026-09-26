# Current-build stratagem payload descriptor fix

The live Shield Relay validation failed at `core/stratagem.lua` with
`payload list bounds/count`. The resource, ShieldComponentData and
HellpodPayloadComponentData reads had already passed. The failure was confined to
the generic StratagemInfo payload descriptor.

## Root cause

The generic parser treated the eight bytes at StratagemInfo `+0xA0` (`+160`) as
a `uint64` payload count and required it to equal one. The current schema and the
working ShieldRelayImprovements parser use this 16-byte descriptor:

| Offset | Width | Meaning | Current relay value |
| --- | ---: | --- | --- |
| `+0x98` / 152 | 8 | payload-list pointer | relocated absolute pointer inside group 3 |
| `+0xA0` / 160 | 4 | payload count | `2` |
| `+0xA4` / 164 | 4 | reserved | `0` |

The saved live capture resolves two entries:

1. `0xED13DDC480EC6910` — Shield Relay entity
2. `0x73F8498BFFDCF415` — second reviewed payload entry

Consequently, interpreting `+160..167` as a 64-bit count was structurally wrong,
even though the reserved high word happened to be zero. Requiring one entry was
also inconsistent with the previously successful live diagnostic.

## Parser behavior

`core/stratagem.lua` now parses both the group record-array descriptor and each
record's payload-list descriptor with their actual widths. Counts are bounded
`uint32` values and the adjacent reserved word must be zero. Shield Relay's
current profile pins its count to two. Exactly one list entry must equal the
target entity; absence or duplication rejects the record.

Array pointers accept only the two reviewed DL representations:

* a relocated absolute pointer whose entire array lies inside the owning group;
* a serialized offset relative to the owning group's root whose entire array lies
  inside that same group.

The bounds checks use subtraction before addition, reject ambiguous pointer
interpretations, and retain all LDLD version/type, group extent, record stride,
runtime pointer-table, unique type, ID, package, group/row and total-record checks.
The profile now pins StratagemSettings version 1, StratagemInfo type
`0x7BD60854`, 400-byte records, and a maximum payload count of 16.

## Regression coverage

`tests/fixtures/stratagem_records.json` contains the exact saved Shield Relay
record and its two captured payload identities. It also contains the audited
Orbital Laser ID/package/payload identity. The focused parser fixture exercises:

* Shield Relay with absolute relocated row and two-entry payload pointers;
* Orbital Laser with serialized group-relative row and payload pointers;
* 32-bit count/reserved validation;
* pinned Shield payload count;
* group bounds, pointer bounds, target-payload uniqueness, record version and
  StratagemInfo schema identity.

The Orbital Laser record bytes around its pointer descriptor are synthetic test
framing around audited identity values; they are not represented as a new live
capture. The Shield Relay record is the saved current live record. Runtime code
contains no fixture fallback.

The validation package remains read-only: `writes=0`, `protection_changes=0`,
and `fixture_fallback=disabled` remain mandatory report fields.
