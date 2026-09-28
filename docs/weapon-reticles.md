# Third-person reticle

`hd2.fields.weapon.third_person_reticle` turns a weapon's third-person aiming reticle on or off. It is
available on player weapons (`hd2.weapon`) and support weapons (`hd2.support_weapon`) wherever
Runtime proves the setting exists.

```lua
-- Recreates ReticleAmr: the APW-1 shows the normal reticle in third person.
hd2.ensure({patch={id='reticle-amr',target=hd2.support_weapon('APW-1 Anti-Materiel Rifle'),
    field=hd2.fields.weapon.third_person_reticle,expect=false,value=true}})
```

## Native owner

Each weapon owns a `WeaponDataComponentData` record. Member `+400` is `crosshair_type`, an
`ENUM_UINT32` of `CrosshairWeaponType`, as proven by the pinned type library (enum hash and
14-character member name). The field is weapon-local: no other weapon shares the record.

The boolean is a view over that enum:

| Reticle | Native value |
| --- | --- |
| off | `CrosshairDamageIndicatorOnly` (3): damage indicator only, no aiming reticle |
| on | the weapon's own crosshair style, or `AssaultRifle` (4) where the baseline is off |

`expect` is always the weapon's reviewed baseline, and `value` is the other state. Scope and ADS
behavior are separate, and this field does not change them.

## Coverage

Coverage comes from native values, not weapon names (`research/weapon-reticles-F5FEE03DCFDB.json`):

| Weapons | Baseline | Writable |
| --- | --- | --- |
| APW-1 Anti-Materiel Rifle | off | yes |
| 70 player and 13 support weapons with a named crosshair style | on | yes |
| 7 player and 18 support weapons whose value is `Default`, `CrosshairNever`, `CrosshairAlways` or an unnamed member, or whose roots disagree | none | no: listed with a reason (player `fields`; support `blockedFields` where the weapon's identity is resolved) |
| 2 support items without a `WeaponDataComponentData` record | none | the field is absent |

Three player weapons and one support item (CQC-72) with a mapped style are still read-only,
because their runtime identity is ambiguous.

**Member names.** They come from the Filediver reference list. A name is published only where its
length equals the type library's alias length for that value. Value 3,
`CrosshairDamageIndicatorOnly`, is named by ReticleAmr's version-labelled export. Values whose
length matches no reference name stay unnamed.

## Acknowledgement

- **APW-1, off to on** (3 to 4) is gameplay-proven by ReticleAmr and needs no acknowledgement.
- **Every other change** requires `allow_unverified_effect=true`. The owner, the bytes and the enum
  semantics are proven, but that weapon's in-game result has not been tested.

## Validation

- `scripts/validate_reticle_authoring_snapshot.py` checks all 84 writable fields on a copy-on-write
  overlay of the snapshot: guarded no-op, a changed write with read-back of the exact enum bytes,
  rollback, CONFLICT on a third-party value, and the acknowledgement rejection.
- `examples/projects/ReticleAmrRecreation` passes the reference validator. Its physical write set
  equals ReticleAmr's pinned patch: record 354, `+0x190`, 3 to 4.
- The packaged-runtime scenarios `support-weapon-reticle` (APW-1) and `player-weapon-reticle`
  (R-63 Diligence) apply from the built runtime ZIP and re-apply after a simulated reset.
