# Attachment preset research

The current snapshot proves the static `WeaponCustomizationComponentData`
default-definition list. It does not prove the current player selection or the
saved preset owner. The 4,872-byte component begins with up to ten terminated
eight-byte `(slot, optionId)` entries. Slot `5` is the default magazine. These
entries belong to the generated weapon resource and must not be treated as a
mutable player preset without lifecycle evidence.

The SDK publishes three separate read-only contracts:

- `AttachmentPresetGraph.json` distinguishes resource defaults, current
  selection, saved preset state, and effect application.
- `AttachmentSelectionCapabilities.json` lists typed catalog handles and every
  missing ownership condition that blocks selection writes.
- `AttachmentEffectOwnership.json` preserves normalized effect fingerprints
  without claiming a native owner.

No attachment selection or option effect is writable in this pass. Direct
magazine, rounds-feed, heat, and heatsink fields retain their existing guarded
APIs because their effective component owners are independently proven.

Since 0.23.1, magazine ammo values are writable on the magazine attachment
definitions that own them; see `magazine-attachments.md`. Selection and the other
option effects remain unwritable.

## R-72 Censor controlled comparison

Two controlled, same-build snapshots compared Extended Magazine with Short
Magazine while holding the other attachment choices constant. The bounded pass
found no changed bytes in any reviewed player-weapon record. Censor owns
`WeaponCustomizationComponentData` record 127 (4,872 bytes),
`WeaponMagazineComponentData` record 224 (160 bytes), and
`WeaponDataComponentData` record 301 (1,232 bytes); all three records have the
same complete SHA-256 in both captures. Censor has no
`WeaponRoundsComponentData` or `WeaponHeatComponentData` record in either
capture. The exact changed-range list is therefore empty.

The native catalog identifies Extended as option `0x536662C0`, AddPath
`0x37C2891774B38C87`, and Short as option `0x33EAAA65`, AddPath
`0x986E6696B34B8902`. None of those four identities occurs in Censor's reviewed
records. The controlled catalog effects are Extended: ergonomics -8, capacity
30, four starting magazines, six maximum magazines, 2.9-second full reload and
1.67-second partial reload; Short: ergonomics +3, capacity 20, six starting
magazines, eight maximum magazines, 2.5-second full reload and 1.5-second partial
reload. The catalog does not state a supply-magazine value for either choice.
No corresponding capacity, magazine-count, reload-time, or handling delta was
copied into the reviewed records.

The fallback examined only aligned absolute pointers and entity-allocation-relative
candidates encoded directly in those three Censor records. It excluded the known
customization option table and rejected 32-bit option/scalar values that merely
overlap a committed address range. No valid reference remained, so there was no
directly referenced allocation to follow. No wider address or numeric scan was
performed.

This pair proves that current selection and applied effects are outside the
reviewed weapon-resource records and their direct references. It does not prove
whether another system stores a scalar option ID, an AddPath, or a coordinated
set of values. There is therefore no stable weapon-local owner to guard with
expect/value semantics, and neither a scalar write nor an `hd2.plan` can be
selected safely. Magazine attachment selection remains read-only for Censor and
cannot yet be generalized to other primary weapons.

## Exact-value preset and loadout pivot

The follow-up scan searched all captured region payloads for only the two known
option IDs and two known AddPaths. It scanned 11.0 GiB in each snapshot and
mapped each file hit back to its virtual address, allocation, region, and
protection. It did not perform an unrestricted semantic or numeric scan. The
full occurrence sets and aligned contexts are in
`research/attachment-selection-candidates-F5FEE03DCFDB.json`.

The raw occurrence counts are:

| Identity | Extended snapshot | Short snapshot |
| --- | ---: | ---: |
| Extended option ID | 24 | 4 |
| Short option ID | 2 | 2 |
| Extended AddPath | 45 | 9 |
| Short AddPath | 9 | 9 |

No identity retained the same absolute VA because the relevant allocations were
rebased or recreated. Six allocation layouts nevertheless matched across the
captures by allocation-relative hit signature. The strongest match is an option
table at allocation `0x0000021ED03A0000` in the Extended capture and
`0x000002579B680000` in the Short capture. Both use the same relative layout:

- Extended descriptor start `+0x3CD8`, option ID `+0x3CE0`, AddPath `+0x3CF8`.
- Short descriptor start `+0x3D30`, option ID `+0x3D38`, AddPath `+0x3D50`.
- Each option ID is at descriptor offset `+0x08`, each AddPath is at `+0x20`,
  and adjacent descriptors have a `0x58` stride.

Both choices coexist in this table in both captures, so it is an option-definition
table rather than current selection state. Exact U64 searches for references to
the descriptor starts, option fields, and AddPath fields returned zero hits in
both snapshots. Values from the first descriptor field occur in copied rows,
but they do not point back to a selected descriptor.

Two Extended-only private, read/write allocations initially looked relevant.
Allocation `0x0000021EC4D40000` is `0x201000` bytes and contains 15 complete
Standard-then-Extended descriptor pairs. Allocation `0x0000021F510D0000` is
`0x10000` bytes and contains one such pair. The Short snapshot contains no
symmetric Standard-then-Short allocation. Neither candidate contains the Censor
resource `0xF0338468DCDB6A6C`, an adjacent small-slot/option-ID pair, a Short
descriptor, or evidence of another attachment category. They are asymmetric
copies of option-definition rows and cannot distinguish current, saved,
loadout, or construction state.

A final one-hop pass searched for exact U64 references to both candidate
allocation bases and all 16 complete descriptor starts. It found zero raw or
aligned hits, so neither cache exposes a captured parent preset/loadout object.

The exact-value pass therefore does not identify a player preset or loadout
owner. A low-entropy index search would be unbounded without a preset/loadout
root, so it was not performed. Selection persistence and expect/value semantics
remain unproven, and no scalar or coordinated write path is promoted. The next
required anchor is a stable player preset/loadout root or a symmetric reference
transition captured at the same lifecycle point.

## Targeted state comparison

Create one process snapshot for each state in the same game session, then run
the bounded attachment extractor. It resolves the entity table once per capture
and reads only five reviewed components on the 80 player-weapon roots. It does
not open projectile/support domains or search arbitrary memory values:

```powershell
py -3 -B scripts/research_attachment_presets.py `
  --snapshot-state ar23c_extended_equipped=<extended.hd2snap> `
  --snapshot-state ar23c_short_selected=<short-selected.hd2snap> `
  --state-output-dir build/attachment-states
```

Compare those files in lifecycle order:

```powershell
py -3 -B scripts/research_attachment_presets.py `
  --snapshot-state ar23c_extended_equipped=<extended.hd2snap> `
  --snapshot-state ar23c_short_selected=<short-selected.hd2snap> `
  --snapshot-state ar23c_short_saved=<short-saved.hd2snap> `
  --snapshot-state ar23c_short_reequipped=<short-reequipped.hd2snap>
```

The differ is limited to `WeaponCustomizationComponentData`,
`WeaponMagazineComponentData`, `WeaponRoundsComponentData`,
`WeaponDataComponentData`, and `WeaponHeatComponentData` on the reviewed 80
player-weapon roots. It reports exact changed byte ranges with aligned U32/FP32
views. It does not search arbitrary process memory.

Required controls are AR-23C Extended → Short → saved → re-equipped, AR-23C
Short → Drum, one optic change, and one Sickle or Scythe heatsink change. A
field may be promoted only after those captures separate option selection from
saved preset state and copied effective component values, and re-equip shows
whether construction rebuilds those values.
