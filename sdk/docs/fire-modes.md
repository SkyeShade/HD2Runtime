# Fire modes

A weapon's fire modes are a small, fixed list in its own `WeaponDataComponentData` record. Runtime
edits that list directly: it can add, remove or reorder Automatic, Single and Burst, and set the
burst length.

```lua
-- JAR-5 Dominator: Single, Burst -> Single, Burst, Automatic (see examples/projects/JAR5FullAuto)
hd2.ensure({patch={id='jar5-full-auto',target=hd2.weapon('JAR-5 Dominator'),
    field=hd2.fields.fire_mode.modes,expect={'single','burst'},value={'single','burst','automatic'},
    allow_unverified_effect=true}})
```

## Native model

Every offset below is proven against the pinned type library: member name lengths, storage, and the
`FireMode` / `WeaponFunctionType` enum hashes.

| Offset | Member | Meaning |
| --- | --- | --- |
| +140 | `num_burst_rounds` (UINT32) | Rounds per burst. Weapon-wide; used only by Burst |
| +144 | `primary_fire_mode` (FireMode) | The default mode |
| +148, +152, +156 | secondary, tertiary and quaternary fire modes | Further selectable modes, packed in order; `None` (0) marks an empty slot |
| +184 | `function_info {left, right}` (WeaponFunctionType) | The weapon function bound to each input; `Firemode` (3) is the in-game fire-mode selector |
| +160, +1040 | special fire-control structures | Set on a few weapons only; those weapons stay read-only |

Answers to "what does enabling full-auto mean":

- **It is an enum value added to a list.** Enabling full-auto writes `Automatic` into an empty
  mode slot. There is no flag, bitmask, reference or per-mode settings object.
- **The default mode** is the first slot. Reordering the list changes it.
- **Burst length** is one weapon-wide value. It applies whenever Burst is selected.
- **Rate of fire** is one value per weapon (`weapon.fire_rate`), shared by every mode. There is no
  per-mode rate.
- **Switching modes in game** needs the fire-mode selector bound to an input. Weapons without it can
  only have one mode, so for them the one mode is replaced (for example Single to Automatic).

`FireMode` names are published only where the type library's alias length matches the reference
name: None (0), Automatic (1), Single (2), Burst (3). Values 4 to 8 are charge and safety states.
They stay unnamed and read-only, and they are never offered.

## Fields

| Field | Value | Notes |
| --- | --- | --- |
| `hd2.fields.fire_mode.modes` | ordered list of `'automatic'`, `'single'`, `'burst'` | First entry is the default. Up to 4 entries where a selector is bound, otherwise exactly 1 |
| `hd2.fields.fire_mode.burst_rounds` | integer, 1 to 10 | Burst length |

- **Acknowledgement.** Both fields require `allow_unverified_effect=true`. The owner, the bytes and
  the enum meaning are proven, but adding or removing a mode has not been gameplay-tested.
- **Scope.** Both are weapon-local: every record has one owner, so `allow_shared` is never needed.
- **Writing.** The mode set is written as its four aligned slots in one atomic transaction. Every
  slot is conflict-checked, and only the changed slots are written.
- **Older field.** `weapon.default_fire_mode` (reordering within the native vector) still works. It
  covers the same bytes, so it cannot be combined with `fire_mode.modes` in one plan.

`weapon:fire_modes().modeSet` and `hd2.support_weapon(name):fire_modes().modeSet` describe a weapon
in full: modes, default, selector, `maxModes`, burst rounds, whether it is writable, and the reason
if not. `sdk/WeaponFireModeCapabilities.json` publishes the same information for every weapon, so a
GUI can show checkboxes and a default selector without guessing from names.

## Coverage

| State | Player | Support | Meaning |
| --- | ---: | ---: | --- |
| `selectable` | 30 | 3 | Up to four modes; the selector is bound |
| `single_mode` | 19 | 9 | The single mode can be replaced |
| `blocked` | 31 | 21 | Read-only, with a reason |
| `absent` | 0 | 2 | No weapon data |

Full-auto can be given to every writable weapon: 61 in total. It is added where a selector exists and
replaces the single mode where it does not. 60 weapons already list Automatic natively.

**Blocked**, from native evidence:

- charge, wind-up, beam, arc, spray and melee weapons (from component ownership);
- weapons using charge or safety modes (4 to 8);
- weapons binding `ProgrammableAmmo` or `LaserGuide`, whose trigger is special;
- weapons with the special structures at +160 or +1040;
- the weapons shown as blocked for ambiguous identity in `sdk/WeaponFireModeCapabilities.json`.

## Validation

- `scripts/research_weapon_fire_modes.py` proves the layout and maps every weapon
  (`research/weapon-fire-modes-F5FEE03DCFDB.json`).
- `scripts/validate_fire_mode_authoring_snapshot.py` checks all 61 writable weapons on a
  copy-on-write overlay of the snapshot, for both fields. It covers the guarded no-op, a changed
  write with read-back (a mode added, removed, or the single mode replaced), rollback, CONFLICT on a
  third-party slot value, and the acknowledgement rejection. It also pins the JAR-5 write (only
  `tertiary_fire_mode` +152 changes, 0 to 1, 4 bytes), checks that blocked weapons refuse writes,
  and checks that the two overlapping fire-mode views cannot be combined.
- The packaged-runtime scenarios `fire-mode-jar5-full-auto` and `fire-mode-burst-and-automatic`
  apply from the built runtime ZIP and re-apply after a simulated reset. The second covers the
  Liberator's burst length and mode set, and the MG-43 made single-shot.
