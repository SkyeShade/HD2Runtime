# Fire modes

A weapon's fire modes are a small, fixed list in its own `WeaponDataComponentData` record. Runtime
edits that list directly: it can add, remove or reorder Automatic, Single and Burst, and set the
burst length.

```lua
-- JAR-5 Dominator: Single, Burst -> Single, Burst, Automatic (see examples/projects/JAR5FullAuto)
hd2.ensure({patch={id='jar5-full-auto',target=hd2.weapon('JAR-5 Dominator'),
    field=hd2.fields.fire_mode.modes,expect={'single','burst'},value={'single','burst','automatic'},
    allow_unverified_effect=true}})

-- R/40-K Hot-Shot (0.30.4): one mode and no selector -> Single and Automatic with the game's fire-mode selector bound
-- on the left input, one transaction (proof/UserRequestsProof, "Hot-Shot single/auto selector").
hd2.ensure({transaction={id='hotshot-selector',target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),
    allow_unverified_effect=true,changes={
    {field=hd2.fields.fire_mode.modes,expect={'single'},value={'single','automatic'}},
    {field=hd2.fields.weapon_function.left,expect='none',value='fire_mode'}}}})
```

## Native model

Every offset below is proven against the pinned type library: member name lengths, storage, and the
`FireMode` / `WeaponFunctionType` enum hashes.

| Offset | Member | Meaning |
| --- | --- | --- |
| +140 | `num_burst_rounds` (UINT32) | Rounds per burst. Weapon-wide; used only by Burst |
| +144 | `primary_fire_mode` (FireMode) | The default mode |
| +148, +152, +156 | secondary, tertiary and quaternary fire modes | Further modes, packed in order; `None` (0) marks an empty slot. The selector reaches +148 and +152 only: +156 is never read by it |
| +184 | `function_info {left, right}` (WeaponFunctionType) | The weapon function bound to each input; `Firemode` (3) is the in-game fire-mode selector |
| +160, +1040 | special fire-control structures | Set on a few weapons only; those weapons stay read-only |

Answers to "what does enabling full-auto mean":

- **It is an enum value added to a list.** Enabling full-auto writes `Automatic` into an empty
  mode slot. There is no flag, bitmask, reference or per-mode settings object.
- **The default mode** is the first slot. Reordering the list changes it.
- **Burst length** is one weapon-wide value. It applies whenever Burst is selected.
- **Rate of fire** is not per fire mode: every fire mode uses the weapon's current rate. The rate itself has three
  native slots and its own selector (the ROF weapon function): see [rate-of-fire modes](fire-rate-modes.md).
  `weapon.fire_rate` is the default slot.
- **Switching modes in game** needs the fire-mode selector bound to an input. A weapon without it has one mode;
  since 0.30.4 the selector can be bound on a free input in the same transaction as the extra modes (below).
  Otherwise the one mode is replaced (for example Single to Automatic).
- **At most three modes.** The selector counts and cycles only +144, +148 and +152; the quaternary slot (+156) is
  never selected and no weapon fills it natively, so `fire_mode.modes` takes up to three entries.

`FireMode` names are published only where the type library's alias length matches the reference
name: None (0), Automatic (1), Single (2), Burst (3). Values 4 to 8 are charge and safety states.
They stay unnamed and read-only, and they are never offered.

## Fields

| Field | Value | Notes |
| --- | --- | --- |
| `hd2.fields.fire_mode.modes` | ordered list of `'automatic'`, `'single'`, `'burst'` | First entry is the default. Up to 3 entries where a selector is bound or bound in the same transaction (`addable`), otherwise exactly 1 |
| `hd2.fields.weapon_function.left` / `.right` | `'fire_mode'` on an unbound input of an `addable` weapon | Binds the game's fire-mode selector (WeaponFunctionType Firemode, 3); only with two or three modes in the same transaction |
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

## Adding the selector (0.30.4)

Question from a player: "I cannot change the fire mode of the Hot-Shot: is that a limit in the game files?" It is not.
The R/40-K Hot-Shot lists one mode (Single) and binds nothing to either weapon-function input, so the game has no
selector to switch with. The selector itself is generic and data-driven
(`scripts/research_fire_mode_selector.py`, `research/fire-mode-selector-F5FEE03DCFDB.json`):

- **The press** of a weapon-function input (game.dll 0x7552D0) dispatches on the WeaponFunctionType the built weapon
  binds to it (copied from `function_info` at build). Type 2 runs the rate-of-fire cycle; type 3 (Firemode) runs the
  fire-mode cycle (0x75542B). Neither depends on the weapon or on the binding being native.
- **The cycle** counts the weapon's non-empty slots +144, +148 and +152 (0x755476), steps
  `index = (index + 1) mod count` in the weapon's state (bits 12-13, replicated), and maps the index to that slot's
  FireMode (0x7567F0), which becomes the weapon's current mode (0x755F90, replicated).
- So binding Firemode on a free input needs nothing else, like the rate-of-fire binding, which is live-proven on the
  AR-23 Liberator (`weapon_fire_rate_selector_added`).

**State `addable`.** A weapon with one mode and an unbound input: every former `single_mode` weapon. The MG-43,
MG-206, Stalwart and GL-28 keep their rate-of-fire selector on the right and take the fire-mode selector on the left.
Its `fire_mode.modes` takes up to three entries, but more than one only in the same transaction as
`weapon_function.left` or `.right` = `'fire_mode'`, and the binding only together with two or more modes
(`SELECTOR_REQUIRED` otherwise), so nothing written is ever dormant. `weapon:fire_modes().modeSet` and
`sdk/WeaponFireModeCapabilities.json` publish `bindableInputs` and the `binding`.

- **Acknowledgement.** `allow_unverified_effect` on both fields, until a live test.
- **When it applies.** The modes and the binding are copied into a weapon when the game builds it: equip the weapon
  after the write (or redeploy). The weapon starts on the first mode.
- **Multiplayer.** Weapon-local records, read on every machine when the weapon is built; the selected mode is
  replicated with the weapon. Every machine should run the same mod.
- **Not traced.** The weapon menu entry and the HUD icon of a weapon that never had a selector. Both read the generic
  weapon-function value; the rate binding's menu entry appeared live on the Liberator.

## Coverage

| State | Player | Support | Meaning |
| --- | ---: | ---: | --- |
| `selectable` | 31 | 3 | Up to three modes; the selector is bound |
| `addable` | 20 | 10 | One mode and a free input: replace it, or list two or three with the selector binding |
| `single_mode` | 0 | 0 | The single mode can be replaced; no free input |
| `blocked` | 29 | 20 | Read-only, with a reason |
| `absent` | 0 | 2 | No weapon data |

Full-auto can be given to every writable weapon: 64 in total. It is added where a selector exists or is bound in the
same transaction, and it replaces the single mode otherwise. 60 weapons already list Automatic natively.

**Blocked**, from native evidence:

- charge, wind-up, beam, arc, spray and melee weapons (from component ownership);
- weapons using charge or safety modes (4 to 8);
- weapons binding `ProgrammableAmmo` or `LaserGuide`, whose trigger is special;
- weapons with the special structures at +160 or +1040;
- the weapons shown as blocked for ambiguous identity in `sdk/WeaponFireModeCapabilities.json`.

## Validation

- `scripts/research_weapon_fire_modes.py` proves the layout and maps every weapon
  (`research/weapon-fire-modes-F5FEE03DCFDB.json`).
- `scripts/validate_fire_mode_authoring_snapshot.py` checks all 64 writable weapons on a
  copy-on-write overlay of the snapshot, for both fields. It covers the guarded no-op, a changed
  write with read-back (a mode added, removed, or the single mode replaced), rollback, CONFLICT on a
  third-party slot value, and the acknowledgement rejection. It also pins the JAR-5 write (only
  `tertiary_fire_mode` +152 changes, 0 to 1, 4 bytes), checks that blocked weapons refuse writes,
  and checks that the two overlapping fire-mode views cannot be combined. Since 0.30.4 it also gives every
  `addable` weapon a second mode with its Firemode binding (one transaction, exactly the second slot and the input
  written, exact rollback; the Hot-Shot is pinned: +148 0 -> 1 Automatic, +184 0 -> 3 Firemode), and refuses the
  modes alone, the binding alone and four modes.
- The packaged-runtime scenarios `fire-mode-jar5-full-auto` and `fire-mode-burst-and-automatic`
  apply from the built runtime ZIP and re-apply after a simulated reset. The second covers the
  Liberator's burst length and mode set, and the MG-43 made single-shot.
