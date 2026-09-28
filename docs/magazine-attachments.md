# Magazine attachments

On weapons with selectable magazines, the magazine's values belong to the **magazine attachment
definition**, not to the weapon. Every magazine definition can be edited on its own, not only the
one a weapon equips by default. Runtime exposes the definitions as typed targets:
`weapon:magazine_attachment(...)`, `weapon:magazine_attachments()` and `hd2.weapon_attachment(...)`.
The catalog is `sdk/MagazineAttachmentCapabilities.json`.

Editing a definition never changes which magazine the player has equipped. Selection and presets
remain unresolved and read-only.

## Ownership chain

```
weapon customizable item (generated_weapon_customization_settings)       (option ID, AddPath)
  -> entity delta keyed by that AddPath (ComponentEntityDeltaStorage)
       WeaponMagazineComponentData  +136 capacity, +140 starting, +144 from supply, +148 spare
       WeaponReloadComponentData    +56 duration (reload seconds)
       WeaponDataComponentData      +956 weapon_stat_modifiers: {Add_Ergonomics, value}
       WeaponCustomizationComponentData  magazine unit, adjusting nodes   (not writable)
       WeaponReloadComponentData    reload animation events               (not writable)
```

Every component index and member is proven against the pinned type library. That includes the
`WeaponStatModifierType` names, whose 19 alias lengths all match. The live delta table is one
private, read-only allocation. Its data bytes are identical to the pinned
`generated_entity_deltas.dl_bin`; only its five header offsets are relocated. Delta data bytes are
never shared between definitions.

## Fields

| Field | Unit | Instances | Range |
| --- | --- | ---: | --- |
| `attachment.magazine_capacity` | rounds | 43 | non-negative integer |
| `attachment.starting_magazines` | magazines | 43 | non-negative integer |
| `attachment.magazines_from_supply` | magazines | 43 | non-negative integer |
| `attachment.spare_magazines` | magazines | 43 | non-negative integer |
| `attachment.reload_duration` | seconds | 37 | 0.1 to 20 |
| `attachment.ergonomics_modifier` | ergonomics | 24 | -100 to 100 |

- **Reload duration** exists only where the definition patches it; 6 definitions keep the weapon's
  own reload.
- **Ergonomics modifier** is the definition's `Add_Ergonomics` stat modifier. Each write also
  re-proves that the modifier's type word is still `Add_Ergonomics`.
- **Not writable:** visual magazine units and reload animation events are resource references.

## Which options belong to which weapon

`weapon:magazine_attachments()` returns every option resolved for the weapon. Each option names its
relationship, strongest first:

| Relationship | Evidence |
| --- | --- |
| `native_resource_default` | The weapon resource's `DefaultCustomizations[magazine]` names it |
| `catalog_effects_unique` | Exactly one definition carries every published effect: capacity, starting and maximum magazines, reload time, and ergonomics |
| `catalog_effects_unlock_list` | Several definitions carry the published effects; exactly one is in the weapon's own unlock list |
| `unlock_listed` | In the weapon's unlock list, but no catalog option names it |

Look-alike definitions that share their ammo counts are separated by their other patches.
`Standard` and `Standard Fastreload` differ in reload (2.5 s against 2.0 s). The Liberator `Drum`
and the `Whisper` drum are separated by the Liberator's unlock list.

**Unlock lists** (`research/attachment-unlock-lists-F5FEE03DCFDB.json`) are per-weapon option lists
the game keeps in memory, keyed by each weapon's own loadout item id (`LoadoutEntryComponent.id`).
52 player weapons have one. They list unlockable options (not free slot defaults), and they can list
more than the weapon catalog shows; the Liberator's, for example, includes `Extended Fastreload`.
They are published as observed evidence and never lift a guard.

## Sharing scope

Each definition publishes `compatibleWeapons`, the union of the three sources above. For example:

```
Rifle 5,5x50mm. Drum
  AR-23 Liberator, AR-23A Liberator Carbine, AR-23C Liberator Concussive,
  AR-23P Liberator Penetrator, AR-59 Suppressor
```

The set is not proven complete: the unlock list is runtime state, and nothing proves that no other
weapon equips a definition. **`allow_shared=true` therefore stays required.**

## Writing

```lua
local liberator=hd2.weapon('AR-23 Liberator')
local drum=liberator:magazine_attachment('Drum Magazine')   -- catalog name, semantic id, or native name
hd2.ensure({transaction={id='liberator-drum',target=drum,allow_shared=true,allow_unverified_effect=true,
    changes={{field=hd2.fields.attachment.magazine_capacity,expect=60,value=75},
             {field=hd2.fields.attachment.reload_duration,expect=3.5,value=3},
             {field=hd2.fields.attachment.ergonomics_modifier,expect=-15,value=-5}}}})
```

- **`weapon:magazine_attachment()`** with no argument returns the native default.
- **`allow_shared=true`** is required: a definition applies to every weapon that equips it.
- **`allow_unverified_effect=true`** is required. The owner, the live bytes and the effective value
  are proven. Whether an edited delta is re-applied when a weapon is next constructed, rather than
  cached at load, has not been gameplay-tested.
- **Guards.** Each write re-proves the whole delta chain inside the live allocation: header
  relocations and counts, hashmap row, settings entry, the patched component's delta rows, and the
  reviewed data offset. It then writes 4 bytes through the guarded transaction core. 70 of the 233
  fields are byte-packed (unaligned); those use an explicit packed write that must stay within one
  page.

## Why the weapon field is not the capacity

For 14 attachment weapons, the weapon record's own `WeaponMagazineComponentData` capacity is a
placeholder of 30. Their default magazine's delta carries the value the game shows: Concussive 60,
Breaker 16, Peacemaker 15, Knight 50, and so on. `weapon.capacity` therefore stays read-only on
these weapons and is never aliased to an attachment.

## Other attachment slots

`sdk/WeaponAttachmentCatalog.json` publishes read-only metadata for all 241 customization items:
magazines, muzzles, optics, underbarrels, ammo types, paint schemes, internals and triggers. For
each it gives the slot, the patched components and offsets, decoded stat modifiers, and known
consumer weapons. Magazine entries link to their writable definition here.

## Validation

- `scripts/research_magazine_attachments.py` decodes both tables, proves the live allocations, and
  correlates the options (`research/magazine-attachments-F5FEE03DCFDB.json`).
- `scripts/research_attachment_unlock_lists.py` captures the unlock lists from the retained snapshot.
- `scripts/validate_attachment_authoring_snapshot.py` runs every one of the 233 fields on a
  copy-on-write overlay of the snapshot. It checks the guarded no-op, a changed write with
  read-back, that no other definition's bytes change, rollback, CONFLICT on a third-party value, the
  acknowledgement and range rejections, and the `Add_Ergonomics` guard. It also proves that the
  Liberator's Short, Extended and Drum magazines are three separate records that can be edited
  independently. Output: `validation/magazine-attachment-snapshot.json`.
- The packaged-runtime scenarios `magazine-attachment` and `magazine-attachment-options` apply
  edits from the built runtime ZIP and re-apply them after a simulated reset.
