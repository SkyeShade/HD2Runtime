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

## R-72 Censor controlled comparison

Two same-session, same-build snapshots compared Extended Magazine with Short
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

Required controls are AR-23C Extended â†’ Short â†’ saved â†’ re-equipped, AR-23C
Short â†’ Drum, one optic change, and one Sickle or Scythe heatsink change. A
field may be promoted only after those captures separate option selection from
saved preset state and copied effective component values, and re-equip shows
whether construction rebuilds those values.
