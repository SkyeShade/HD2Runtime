# Muzzle, optics and underbarrel attachments

A muzzle, sight or underbarrel changes a weapon's handling through **stat modifiers** carried by the
attachment definition, not by the weapon. These are the same `{WeaponStatModifierType, value}` pairs the magazine
definitions use for ergonomics (see `magazine-attachments.md`). Runtime exposes the modifiers of every muzzle,
optics and underbarrel definition as writable fields of that **shared definition**. The catalog is
`sdk/WeaponAttachmentModifierCapabilities.json`.

Editing a definition never changes which attachment a player has equipped. Selection and presets stay
unresolved and read-only, as for magazines.

## Ownership chain

```
weapon customizable item (generated_weapon_customization_settings)    slot Muzzle (4), Optics (2), Underbarrel (1)
  -> entity delta keyed by its AddPath (ComponentEntityDeltaStorage)
       WeaponDataComponentData +956 weapon_stat_modifiers: eight {WeaponStatModifierType u32, value f32}, stride 8
       other patched members                                              (read-only, see below)
```

The slot names come from the `WeaponCustomizationSlot` enum and the 19 `WeaponStatModifierType` names; both are
checked against the type library's name lengths. The pair layout (`ENUM_UINT32` at +0, `FP32` at +4, an inline
array of 8 at +956) is checked against the pinned type library too. Every modifier pair in every definition
sits in its own two 4-byte delta rows, one for the type word and one for the value. No two of the table's 6,040
delta rows share data bytes, so an edit of one definition can never reach another. The live delta table is the
private read-only allocation already proven for magazines; its data bytes are identical to the pinned file.

`scripts/research_weapon_attachments.py` decodes every item of every slot with the magazine decoder. The output
is `research/weapon-attachments-F5FEE03DCFDB.json` (`statModifierRows`, `hashmapSlot`, `settingsIndex`). The
generator checks that this decoding agrees with the magazine research on every magazine definition.

## Fields

One field per modifier type that occurs in these slots. The value is the definition's own number. A `Mul_*` value
multiplies the weapon's stat, and `Add_Ergonomics` is added to the weapon's ergonomics.

| Field | Modifier | Unit | Instances | Range |
| --- | --- | --- | ---: | --- |
| `attachment.ergonomics_modifier` | `Add_Ergonomics` | ergonomics | 38 | -100 to 100 |
| `attachment.modifier.sway` | `Mul_Sway` | multiplier | 24 | 0 to 10 |
| `attachment.modifier.recoil_horizontal` | `Mul_RecoilHorizontal` | multiplier | 16 | 0 to 10 |
| `attachment.modifier.recoil_vertical` | `Mul_RecoilVertical` | multiplier | 13 | 0 to 10 |
| `attachment.modifier.climb_horizontal` | `Mul_ClimbHorizontal` | multiplier | 15 | 0 to 10 |
| `attachment.modifier.climb_vertical` | `Mul_ClimbVertical` | multiplier | 14 | 0 to 10 |
| `attachment.modifier.spread_horizontal` | `Mul_SpreadHorizontal` | multiplier | 6 | 0 to 10 |
| `attachment.modifier.spread_vertical` | `Mul_SpreadVertical` | multiplier | 6 | 0 to 10 |

That is 132 writable fields on 44 definitions: 28 muzzles (99 fields), 6 optics (6) and 10 underbarrels (27).
- **Ergonomics keeps its magazine name.** `Add_Ergonomics` is `attachment.ergonomics_modifier` in every slot. The
  schema has no field aliases, so there is no second `attachment.modifier.ergonomics` id for the same bytes.
- **Only modifiers a definition carries are editable.** Adding a pair is not supported. A write of a modifier a
  definition does not carry is refused and the error lists the ones it does carry. The drift and `Alt` modifier
  types occur in no muzzle, optics or underbarrel definition, so they have no field.
- **One modifier is read-only.** The `Mul_ClimbHorizontal` value of `8mm. Muzzle break` is byte-packed across a
  page boundary of the live allocation, and guarded writes never cross a page. Its blocker is published.
- **Type guard.** Each write re-proves the whole delta chain, as for magazines. It also re-reads the pair's type
  word and refuses the write when it no longer names the reviewed modifier.

## Sharing scope

One definition serves every weapon that equips it. Editing `TUBE REDDOT 2x` changes the sight on all 29 weapons
that list it, and the `Vertical Grip` edit reaches 26. Each definition publishes `compatibleWeapons`, the union
of the weapons whose resource default names it and the weapons whose unlock list (observed in memory) lists it.
That set is not proven complete. **`allow_shared=true` is therefore required**, together with
**`allow_unverified_effect=true`** (see below).

## API

```lua
local liberator=hd2.weapon('AR-23 Liberator')
liberator:attachments('muzzle')                      -- 'magazine' | 'muzzle' | 'optics' | 'underbarrel'
local flash=liberator:attachment_definition('muzzle','5,5mm. Flash Hider')   -- native name or semantic id
liberator:attachment_definition('optics')            -- no identity: the native resource default (TUBE REDDOT 2x)
hd2.weapon_attachment('Vertical Grip')               -- any slot, by semantic id or unique native name
hd2.ensure({transaction={id='liberator-flash-hider',target=flash,allow_shared=true,allow_unverified_effect=true,
    changes={{field=hd2.fields.attachment.modifier_recoil_horizontal,expect=0.8,value=0.5},
             {field=hd2.fields.attachment.modifier_recoil_vertical,expect=0.9,value=0.6},
             {field=hd2.fields.attachment.ergonomics_modifier,expect=-3,value=0}}}})
```

- **Handles.** A handle is `{resource='weapon_attachment', attachment=<semantic id>, path=<slot>}`. For the
  magazine slot, `attachments('magazine')` and `attachment_definition('magazine', id)` are
  `magazine_attachments()` and `magazine_attachment(id)`, which are unchanged.
- **Options.** `weapon:attachments(slot)` returns the native default first, then the unlock-listed definitions.
  The relationship is `native_resource_default` or `unlock_listed`.
- **`describe()`** returns:
  - the slot, the relationship and `compatibleWeapons`;
  - every modifier with its current value, its field and whether it is writable;
  - the editable fields with their ranges;
  - `readOnlyPatches`.
- **Writes.** They go through the guarded attachment write path that magazines use, with `hd2.patch`,
  `hd2.transaction`, `hd2.plan` or `hd2.ensure`. A handle whose path is not the definition's slot is refused.

## Read-only patches (unproven)

A definition's delta also patches other members. They are published in `readOnlyPatches` and in `describe()`, and
none is writable:
- **Resource references** (`status='resource_reference'`): the muzzle unit, the optics unit and the underbarrel
  entity.
- **Unproven members** (`status='unproven'`): the owner, offset and size are known, but nothing is proven against
  the type library. The leads below are research guesses only; they are not names.

| Slot | Member | Size | Definitions | Unproven lead |
| --- | --- | ---: | ---: | --- |
| optics | `WeaponDataComponentData` +116 | 12 | 16 | aim zoom (vec3) |
| optics | `WeaponDataComponentData` +316 | 12 | 9 | |
| optics | `WeaponDataComponentData` +340 | 12 | 6 | scope zeroing |
| optics | `WeaponDataComponentData` +352 | 1 | 8 | |
| optics | `WeaponCustomizationComponentData` +168 | 8 | 14 | crosshair parameters |
| muzzle | `ProjectileWeaponComponentData` +224 | 8 | 33 | |
| muzzle | `WeaponDataComponentData` +136 | 4 | 4 | visibility modifier |
| muzzle | `WeaponDataComponentData` +84, +88; `ProjectileWeaponComponentData` +4 | 4, 4, 12 | 1 each | |
| muzzle | `BeamWeaponComponentData` +0 to +96 (8 members) | 4 or 8 | 2 | |
| underbarrel | `WeaponCustomizationComponentData` +4852, +4856 | 4 | 10, 7 | |
| underbarrel | `WeaponDataComponentData` +156 | 4 | 3 | a fourth fire mode |
| underbarrel | `MeleeAttackComponentData` +0 | 4 | 2 | (bayonets) |

## What is proven and what is not

- **Proven offline:** the owner chain, the live bytes and each written value on the retained snapshot.
  `scripts/validate_attachment_modifier_snapshot.py` runs every one of the 132 fields on a copy-on-write overlay
  (output: `validation/weapon-attachment-modifier-snapshot.json`). For each field it checks:
  - the guarded no-op;
  - a changed write with read-back, isolated from all 365 reviewed attachment locations (magazines included);
  - rollback, and CONFLICT on a third-party value;
  - the type-word guard;
  - the acknowledgement and range rejections, and a target path of another slot.
  It also refuses every absent modifier on all 73 definitions and the page-straddling one. One transaction edits
  all six Flash Hider modifiers and rolls them back.
- **Packaged runtime:** the scenario `weapon-attachment-modifiers` applies a Flash Hider transaction, the
  Liberator's default sight and the Vertical Grip from the built runtime ZIP, and re-applies them after a reset.
- **Not live-tested:** whether an edited delta is re-applied when a weapon is next built (for example, in the
  armory or at mission start), rather than cached at load. That is why `allow_unverified_effect` is required. It
  is also not proven that a `Mul_*` value scales the stat its name gives. That needs a gameplay test with strongly
  different values, for example Flash Hider horizontal recoil 0.8 against 3.
