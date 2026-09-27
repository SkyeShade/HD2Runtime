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
