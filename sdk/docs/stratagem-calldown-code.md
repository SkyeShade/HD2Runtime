# Stratagem calldown codes

`hd2.fields.stratagem.calldown_code` sets the code (the arrow sequence) a player enters to call a stratagem in. It is
an ordinary guarded stratagem field: it works with `hd2.patch`, `hd2.transaction`, `hd2.plan` and `hd2.ensure`, in
the same operation group as `hd2.fields.stratagem.definition_cooldown`.

```lua
-- Orbital 120mm HE Barrage: Right Right Down Left Right Down -> Up Up Down Down
hd2.ensure({patch={id='barrage-code',target=hd2.stratagem('Orbital 120mm HE Barrage'),
    field=hd2.fields.stratagem.calldown_code,
    expect={'right','right','down','left','right','down'},
    value={'up','up','down','down'}}})

-- The code and the cooldown of one stratagem, applied and restored together
hd2.ensure({transaction={id='precision',target=hd2.stratagem('Orbital Precision Strike'),changes={
    {field=hd2.fields.stratagem.definition_cooldown,expect=80,value=60},
    {field=hd2.fields.stratagem.calldown_code,expect={'right','right','up'},value={'right','up','right','up'}}}}})
```

## Values

- **A code** is a plain list of 1 to 9 directions, each `'up'`, `'right'`, `'down'` or `'left'`. The game's own codes
  are 3 to 9 directions long; 9 is the longest the game's code readers take.
- **`expect`** must equal the stratagem's native code, published as `currentDefault` (and as
  `calldownCapability.value`) in `sdk/StratagemAuthoringCapabilities.json`.
- **Equal codes:** a `value` equal to another stratagem's native code requires `allow_unverified_effect=true`. Which
  stratagem the game calls in when two equipped stratagems share a code is not proven.
- **Codes that start like another** need no acknowledgement. Up Up Down Down, for example, starts the Cargo
  Container's Up Up Down Down Right Down. The game's own data has such a pair: a reward resupply's Down Down Up Left and
  the LAS-99 Quasar Cannon's Down Down Up Left Right. Read statically (not live-proven), the game's matcher selects
  the first available stratagem whose whole code has been entered, at that arrow. So while both are equipped and the
  shorter one is available, the longer one cannot be called (docs/custom-stratagems.md, "Payload stage A"). Check the
  stratagems a mission can grant before choosing such a code.
- **Refused at registration:** an empty list, more than 9 directions, a direction name other than the four, a table
  that is not a plain list, a wrong `expect`.

## Coverage

All 94 catalogued stratagems that have a call-in StratagemDefinition: every offensive, support-weapon, vehicle,
backpack, defensive and mission stratagem in the catalogue (exactly the stratagems whose `definition_cooldown` is
writable). Each is found through its catalogued identity (its StratagemDefinition id and package), never a native
type number.

Not available:

| Stratagem | Reason |
| --- | --- |
| SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool | No call-in StratagemDefinition: equipment found during missions (`calldownCapability.reason`). |
| Mission objective stratagems (Reinforce, SOS Beacon, Hellbomb, Eagle Rearm, data uploads, the SEAF Artillery) | Not in the stratagem catalogue, so `hd2.stratagem(name)` does not resolve them. |

## What the Runtime does

- **The write.** A StratagemInfo row holds its code as a pointer to an array of directions and their count. A changed
  code is an immutable array the Runtime owns, one per distinct code, kept for the life of the Lua state. The guarded
  write changes only the row's pointer and, when the length changes, its count: one or two writes, the count first
  unless the code grows, so every reader sees a whole code at every moment. The game's own arrays are never written.
- **The HUD.** The mission HUD's stratagem list draws a slot's arrows once and does not redraw them when the code
  changes. The Runtime keeps it in step automatically:
  - whenever a row it changed holds a code the HUD has not drawn yet (after an apply, an ensure re-apply, a rollback
    or a restore, and in every new mission), it redraws only that stratagem's slot;
  - it uses the same data the game's own redraw writes, through the guarded transaction, once per change, never every
    frame;
  - aboard the ship there is no list, so it waits. A slot the list builds after the change already shows the new code,
    so it needs no redraw. A stratagem not in the loadout has no slot and is never drawn.

  A refused redraw never undoes the code. The log then shows `stratagem calldown <name>: calldown applied; HUD refresh
  refused: <code>: <reason>` once, and the redraw is retried. A HUD whose code the research does not cover is never
  written.
- **Restore.** Restoring (an `hd2.ensure` option turned off, a rolled-back transaction or plan) puts the native
  pointer and count back and redraws the slot. Before the Lua state (and its arrays) goes
  away, every row that still points to a Runtime array gets its native pointer and count back, then its slot is
  redrawn.

## Guards

- **The build.** The native code readers (the code matcher and both code copies) must match their reviewed bytes on
  the loaded game.dll, or the write is refused with `calldown code unavailable on this game build`.
- **The row.**
  - It resolves through the catalogued id, package and payloads under the same structural checks as every
    stratagem field.
  - Its current pointer and count must be the native array, inside the StratagemSettings allocation with 1 to 9
    directions, or one of the Runtime's own arrays for that row. The padding after the count must be zero.
  - The native code must equal `expect`. The current code must be the native code, the desired code, or the code this
    same operation wrote earlier: a code another writer put there is not taken over.
  - Anything else is a precise `CONFLICT`, and nothing is written.
- **Exactly the planned bytes.** Only the row's pointer and count change, through the guarded transaction (exact
  expected bytes, the row as context, protection checked, rollback on failure).
- **The HUD redraw.** It is refused, and the HUD left untouched, unless:
  - its own code pins prove;
  - the HUD is set up in a mission;
  - the slot of exactly that stratagem type is found through the local player's stratagem record;
  - every sprite, layout parent and flag matches the research.
  It writes only that slot's arrow sprites, their layout parents and the slot's relayout flag. It never changes the
  slot's stratagem type, the scrambler state or another slot.

## Metadata

`sdk/StratagemAuthoringCapabilities.json`:

- **The field descriptor** (one per stratagem): `type: "calldown_code"`, `unit: "directions"`, `currentDefault`
  (the native code), `minLength` 1, `maxLength` 9, `directions`, `hudSynchronization` and `acknowledgementRule`.
- **`calldownCapability`** (one per stratagem): `value`, `writable`, `field`, the length limits, `directions`,
  `hudSynchronization: "automatic"`, and `liveEvidence` where proven. The two unavailable entries carry `reason`
  instead.
- **The summary** counts them as `calldownWritable`.

Like the cooldown, the field needs no acknowledgement except for an equal code.

## Live evidence and limits

- **Live-proven** (`stratagem_calldown_code`, CustomStratagemP0Proof, 2026-10-01, solo host): the Orbital 120mm HE
  Barrage's code Up Up Down Down.
  - The game accepted the new code and no longer the old one.
  - The call-in and barrage stayed vanilla.
  - The restore brought the original back.
  - The HUD slot showed the new code after the automatic redraw, and the original after the restore.
  - The same again through this public field and `hd2.ensure` alone (CustomStratagemP0Proof 0.5.1): the write, the
    automatic HUD sync, the matcher, and the normal call-in and barrage.
- **Live-proven, field and HUD only:** the GR-8 Recoilless Rifle's code Down Down Down Down through the public field.
  - The guarded write applied, and the automatic HUD sync redrew its slot.
  - The Runtime reported the new code active.
  - Its call-in with the new code was not in the reported log, so it is not claimed.
- **Other stratagems** use the same members and readers but are not individually tested.
- **Not proven:**
  - two equipped stratagems with equal codes (hence the acknowledgement), or one code starting another;
  - multiplayer. Code entry is local and only this machine's row changes; what a host does with a client's call-in
    entered with a changed code has not been tested.

Validation: `tests/test_stratagem_calldown_code.py`, `scripts/validate_stratagem_calldown_snapshot.py` (every
stratagem on every retained snapshot, with the HUD in the mission snapshots) and the packaged-runtime scenario
`stratagem-calldown-code`. The research behind the field and the HUD is in `docs/custom-stratagems.md`.
