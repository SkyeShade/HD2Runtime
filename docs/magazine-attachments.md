# Magazine attachments

On weapons with selectable magazines, the round count belongs to the **magazine attachment
definition**, not to the weapon. Runtime exposes those definitions as typed targets:
`hd2.weapon_attachment(...)` and `weapon:magazine_attachments()`. The catalog is
`sdk/MagazineAttachmentCapabilities.json`.

## Ownership chain

```
weapon WeaponCustomizationComponentData.DefaultCustomizations[slot 5]   (resource default only)
  -> WeaponCustomizableItem in the weapon customization settings table    (option ID, AddPath)
  -> entity delta keyed by that AddPath                                   (ComponentEntityDeltaStorage)
  -> component patch for WeaponMagazineComponentData
       +136 capacity, +140 starting magazines, +144 from supply, +148 spare magazines
```

The same delta also carries the attachment's other effects: reload (`WeaponReloadComponentData`),
handling (`WeaponDataComponentData`), and the visual magazine unit
(`WeaponCustomizationComponentData`). Those are not promoted yet.

The live delta table is one private, read-only allocation. It is identical to the pinned
`generated_entity_deltas.dl_bin` except that its five header offsets are relocated to absolute
pointers. Delta data bytes are never shared between deltas.

## Why the weapon field is not the capacity

For 14 attachment weapons, the weapon record's own `WeaponMagazineComponentData` capacity is a
placeholder of 30. Their default magazine's delta carries the value the game shows: Concussive
60, Breaker 16, Peacemaker 15, Knight 50, and so on. `weapon.capacity` therefore stays read-only on
these weapons and is never aliased to an attachment.

## Separate layers

| Layer | Status |
| --- | --- |
| Attachment definition values (`attachment.*`) | Writable, guarded. Proven native owner and live bytes |
| Weapon base record capacity | Read-only on attachment weapons (placeholder) |
| Rounds currently loaded, and the reserve during a mission | Not exposed; this is runtime instance state |
| Resource default magazine (`DefaultCustomizations`) | Read-only. It is not the player's selection |
| Player preset or current selection | Unresolved. Selection changes did not alter any reviewed weapon record (R-72 Censor diff) |
| Weapon-to-attachment compatibility | Unresolved natively. Only resource defaults are proven; catalog options are correlated by exact published effects |

## Writing

```lua
local drum=hd2.weapon('AR-23C Liberator Concussive'):magazine_attachment()   -- native default
hd2.ensure({patch={id='drum',target=drum,field=hd2.fields.attachment.magazine_capacity,
    expect=60,value=90,allow_shared=true,allow_unverified_effect=true}})
```

- **`allow_shared=true`** is required. An attachment definition applies to every weapon that equips
  it, and that consumer set is not natively complete.
- **`allow_unverified_effect=true`** is required. The owner, live bytes, and effective value are
  proven. Whether an edited delta is re-applied the next time a weapon is constructed, rather than
  cached at load, has not been gameplay-tested.
- **Guards.** Each write re-proves the whole delta chain inside the live allocation: header
  relocations and counts, hashmap row, settings entry, component row, delta row, and reviewed data
  offset. It then writes 4 bytes through the guarded transaction core. 52 of the 172 fields are
  byte-packed (unaligned) in the delta data; those use an explicit packed write that must stay
  within one page.

## Weapon mapping

`weapon:magazine_attachments()` returns the native default, plus any catalog options whose published
capacity, starting magazines, and maximum magazines match exactly one native attachment. When several
native attachments share those effects (for example `Standard` and `Standard Fastreload`), the
option is listed with its candidates and a blocker instead of being guessed. Every attachment
definition can still be targeted directly by semantic ID or unique native name.

## Validation

- `scripts/research_magazine_attachments.py` decodes both tables and proves the live allocations.
  Output: `research/magazine-attachments-F5FEE03DCFDB.json`.
- `scripts/validate_attachment_authoring_snapshot.py` checks all 172 fields as guarded no-ops against
  the snapshot. Output: `validation/magazine-attachment-snapshot.json`.
- `examples/projects/ConcussiveDrumMagazine` changes the Concussive drum from 60 to 90. It passes
  the reference validator (exact write) and the steady-state audit (real transaction apply, idle
  steady state, reapplication after reset).
