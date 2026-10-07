# Custom stratagems: P0, a Runtime-owned calldown sequence

Status: **research and development proof**. Build F5FEE03DCFDB. The calldown code itself is now the public field
`hd2.fields.stratagem.calldown_code` for every call-in stratagem, with the HUD kept in step automatically (see
[Stratagem calldown codes](stratagem-calldown-code.md) and [The public field](#the-public-field)). Everything else in
this document stays development-only.

- **P0 gameplay is live-verified** (2026-10-01, solo host, three runs): the guarded write, the matcher accepting the
  custom code, the old code no longer matching, the normal call-in and barrage, and the restore at mission end.
- **A full UI rebuild draws the custom code** (2026-10-01, a language change and back), so the HUD's stored arrows
  are the only stale copy.
- **The HUD redraw is live-verified** (2026-10-01, proof 0.3.0). The HUD draws a slot's arrows once, on the first
  frame the Helldiver exists, before even an early write lands. The development redraw of only the 120mm's slot
  (`runtime/stratagem_hud.lua`, then on Ctrl+F9) drew Up Up Down Down in 29 guarded writes. After the restore it drew
  the original again (see [The HUD refresh](#the-hud-refresh-development)).
- **The automatic redraw is live-verified** (2026-10-01, proof 0.4.0): after P0 applies, once the slot resolves, and
  after a restore, without a key press.

P0 gives the already-selected vanilla **Orbital 120mm HE Barrage** the calldown sequence **Up, Up, Down, Down** in a
solo or hosted mission. Everything else about the stratagem stays vanilla: name, icon, payload, cooldown, timing,
beacon and category. The barrage it calls in is the native one.

```
StratagemInfo row of the 120mm (found by its catalogue id, never a hard-coded type)
  +0x40  pointer to its u32 directions  ->  a block the Runtime owns: {1, 1, 3, 3}
  +0x48  their count                    ->  4
```

| Piece | File | Role |
| --- | --- | --- |
| Research | `scripts/research_stratagem_calldown.py` -> `research/stratagem-calldown-F5FEE03DCFDB.json` | the members, directions, readers, the HUD's stratagem list and the P0 target (read-only) |
| Domain | `scripts/generate_stratagem_calldown.py` -> `domains/stratagem_calldown.lua` | generated: offsets, directions, maximum length, reader pins, the P0 target |
| Write | `runtime/custom_stratagem.lua` (not exported by `hd2`) | resolve the row, guard, write through `core/guarded_transaction.lua`, restore |
| HUD refresh | `runtime/stratagem_hud.lua` (development; `custom_stratagem.refresh_hud()`) | redraw only the P0 stratagem's slot in the HUD's stratagem list from the row |
| Proof | `proof/CustomStratagemP0Proof` | development-only live test; since 0.5.0 of the public field through `hd2.ensure`, not of this module |
| Snapshot validation | `scripts/validate_custom_stratagem_snapshot.py` -> `validation/custom-stratagem-snapshot.json` | apply and restore on the real row of every retained snapshot, with and without the Helldiver (writes to an overlay) |

## Evidence (research/stratagem-calldown-F5FEE03DCFDB.json)

- **The members.** Every StratagemInfo row (400 bytes, through the runtime table `game+0x37CB600`) holds its code as
  a pointer at +0x40 to u32 directions and their count at +0x48; +0x4C is zero. In all seven retained snapshots all
  149 rows hold 3 to 9 directions, every value 1 to 4, every array inside the StratagemSettings allocation (one private
  read-write allocation).
- **The directions.** 1 Up, 2 Right, 3 Down, 4 Left. The 120mm row (StratagemType 136, native name OrbitalStrike,
  catalogue id 1063322614) holds 2, 2, 3, 4, 2, 3: Right Right Down Left Right Down, its in-game code. Independently,
  33 support weapons whose wiki page gives a stratagem code match their rows exactly.
- **The readers** (pinned; re-proven before every write on a newly loaded game.dll):
  - the calldown matcher (`0x597FC0`): for each slot, count = row +0x48; while the slot's progress is below it, the
    input direction is compared with row +0x40[progress];
  - a copy helper (`0xA106C0`): count out = row +0x48, then memcpy(out, row +0x40, count x 4);
  - a copy-and-compare reader (`0x66D8C0`): the same copy, compared with an input buffer.

  Each reads the live row every time. The copies go into caller buffers, so a custom sequence is at most 9 directions
  long, the longest native one. The HUD is the one place that keeps a drawn copy: see [The HUD](#the-hud).

## The HUD

The in-mission stratagem list does not draw from the row each frame. It draws from sprites it built earlier. All
addresses below are game.dll RVAs, proven in the research's `hud` section (evidence only, not pins of the write).

- **Construction.** When the game enters its Mission state, StateGame's enter handler (`0xAC5D40`) runs the HUD
  setup (`0x12F0920`). With the state member +0xAC21C at 4, the setup builds the mission HUD. Its stratagem list has
  16 slots of 0x3760 bytes, each starting with stratagem type 0 (`0x18359A1`).
- **The avatar gate.** The HUD update first asks for the local player's avatar (`0x606630`: the player manager's
  avatar network id at +0x3A8 + slot x 0x20, resolved through the network-id map `0xFD9BA0`). Until that resolves,
  the update returns before the stratagem list (`0x1833663`). This is the same member the Runtime reads for the local
  avatar.
- **Each frame with an avatar,** each slot:
  - takes its stratagem type from the player's per-peer stratagem record (`game+0x347CE50`) into slot +0x374C;
  - copies the row's live code through the copy helper (`0x1836C8E`);
  - stores the displayed type (the scrambler's result) in slot +0x3754.
- **The redraw.** A slot rebuilds its 10 arrow sprites (slot +0x2980, 0x158 apart) in only three cases: its type
  changed, its displayed type changed, or the scrambler is animating it (`0x1836CFE`..`0x1836D22`). The code and
  count are never compared. Otherwise the fresh copy is discarded. A sprite's image region is direction x 0.2 in a
  five-cell arrow image, and it is visible when its index is below the count.
- **In the snapshots.** In the three mission snapshots, the list's 13 slot types equal the player record's entries.
  Each slot's visible sprites spell exactly its row's code (13 of 13). After reinforcement the avatar network id
  changed (470 to 715), while the list was the same object with the same types.

So the arrows show the code the row held on **the first frame the local avatar existed**. A code written later is
matched but not drawn. Opening or closing the menu changes nothing, because nothing on that path resets a slot's type.
Death and reinforcement are not expected to either. A slot only redraws for:

- a change of its stratagem type;
- the scrambler;
- the entry count dropping below its index;
- a rebuild of the whole HUD (mission start). From the code alone, a language change also rebuilds it: `0x12FF050`
  reads text_language, then `0xB4FD90` calls `0x12F0920`. That path is not live-tested.

P0 does not write any of these, by design.

### Is there a clean refresh? (research, 2026-10-01)

No narrower mechanism exists, and the Runtime cannot trigger the one full rebuild harmlessly. Read from game.dll
F5FEE03DCFDB:

- **The slot updater.** Every path through it (`0x1836510`) reaches one gate. The arrows rebuild when this frame's
  record entry type differs from last frame's, when the displayed (scrambler) type changes, or while the scrambler
  animates. A slot also resets to type 0 when its index is at or past the record's entry count (`0x18365FC`). The
  availability, cooldown and uses block only sets the slot's status visuals. The only writers of the slot's type are
  the constructor, that reset, and the per-frame copy from the record.
- **The player's stratagem record** (`game+0x347CE50`) has four operations:
  - append at the end (`0x4DBBF0`);
  - remove one entry and shift the rest down (`0x4DBDD0`, `0x66F4C0`);
  - reset and refill in one call (`0x66EFD0`, from the ship state and two other callers).

  A refill with the same loadout is invisible to the HUD, because the count never reads 0 between frames. A removal
  redraws only the slots whose entries shifted, and changes the stratagem list itself. The append and remove
  functions have no static or heap reference.
- **Opening and closing the menu** (`0x1835630`) only sets per-slot open flags and animation.
- **Death and reinforcement** change nothing. While there is no avatar the update returns early (the avatar gate),
  and the per-peer record and the list's types are unchanged afterwards (snapshots before and after reinforcement).
- **Full UI reconstruction.** Apart from mission start, the only static path is a text-language change:
  1. Options (`0x14EE9C0`, `nui_language_text`) calls the language setter (`0x12FF6B0`); for the current language it
     returns at once.
  2. The setter tears down every registered UI system, the HUD included (`0xB61A30`: `0x12F0720`, `0x12F1540`).
  3. `0x12FF050` (`text_language`) / `0xB4FD90` rebuilds them; for the HUD, in the ship or Mission state, through
     `0x12F0920`.

  A rebuilt list starts with empty slots, so it would draw the row's current code. A suspend/resume pair
  (`0x12F1A40` / `0x12F1AE0`) also rebuilds the HUD, but it has no static or heap reference; its trigger is unknown.

So the game rebuilds an unchanged slot's arrows only through a whole-UI reconstruction after a user language change,
or through changes to the stratagem list, its type or the scrambler. P0 changes none of these.

### The HUD refresh (development)

`runtime/stratagem_hud.lua` redraws one slot with exactly the data the game's own redraw writes. It is called through
`custom_stratagem.refresh_hud()`; the proof's key is Ctrl+F9. It is pinned by the research's `hud` groups: path,
record, rebuild and sprite. That is 100 instructions plus 2 data constants, byte-identical in all seven snapshots,
and proven on the loaded game.dll before any write.

- **Finding the slot.** The list is at `[game+0x346D538] + 0x396250`. The chain is: the HUD system global (the HUD
  update's object), then the mission HUD (+0x24E340, game mode 4), the panel (+0x146DC0), the list (+0x1040) and
  slot 0 (+0x110), with slots 0x3760 apart. The address is this pinned chain, never a hard-coded address. In all three
  mission snapshots it lands exactly on the list.
  - The slot must hold the stratagem's type, and the local player's record (keyed by the local peer) must hold that
    type at the slot's index.
  - It must not be scrambled: displayed type equal to its type, flag clear, animation timers zero.
- **Checking the drawn code.** Every one of the 10 sprites must have:
  - no flag parent;
  - the next sprite as sibling;
  - the slot's row container as layout parent.

  The visible sprites must be contiguous from 0, and each must hold exactly a cell's image region and its derived
  region. The layout parents must run from the row container through the slot and the list to the root. Every touched
  element must be in the HUD system's private read-write allocation. The drawn code must be the original or the
  custom code.
- **The writes, as the game's redraw makes them:**
  - **image region** (+0x114): per sprite whose region changes. The cell is the direction, u0 = cell x 0.2f,
    u1 = u0 + 0.2f, v from 0 to 1.
  - **derived region** (+0x124): computed through the sprite's sub-rect (+0x134) in float32. In all three mission
    snapshots, all 64 visible sprites match this float32 maths bit for bit.
  - **flags:** 0x2 on a sprite whose region changed. On a sprite whose visibility changes: 0x10 set or cleared, 0x20,
    +0xB8 bit 0x800 and 0x4.
  - **layout parents:** 0x8 after a region change and 0x4 after a visibility change, on each ancestor up the +0xF0
    chain until one already has the bit.
  - **slot:** +0x36F1 = 1, so the list lays the slot out again.

  Invisible sprites keep their region. The game writes stale stack values there, which nothing draws.
- **Never written:** the slot's type, displayed type, index, timers and scrambler flag; the other slots; the record;
  the row. Everything is read and written in one update tick through the guarded transaction. Each touched element is
  its own context, and a difference rolls back.
- **Reversal.** After a restore, the same call draws the original code. Called again it reports `current` and writes
  nothing.

For P0 (Right Right Down Left Right Down to Up Up Down Down) the redraw is 29 writes, live-verified:

- sprites 0, 1 and 3: u0 and u1 of the image and derived regions, plus flags;
- sprites 4 and 5: flags and +0xB8;
- the nine layout parents below the first that already has both bits;
- the relayout flag.

### Automatic redraw (proof 0.4.0)

The redraw is a separate stage from P0, run by the proof, and once per P0 application or restore.

- **After P0 applies.** P0 still applies at mission start without waiting for anything. The proof then marks a HUD
  redraw pending and tries it at once. While it is pending, the proof's existing 0.1 s check asks the redraw's own
  read-only resolver (`stratagem_hud.locate`) for the 120mm's slot:
  - no HUD, or no slot for the type yet: it waits;
  - any other refusal: logged once per reason, nothing written, P0 left as it is, retried at the next check;
  - `HUD_UNAVAILABLE`, a game.dll the research does not cover: it stops.

  Once the slot resolves, it calls `custom_stratagem.refresh_hud()`, the redraw live-verified on Ctrl+F9, unchanged.
  After one `refreshed` or `current`, the stage ends.
- **After a restore** in a mission (Ctrl+F12), the same stage draws the original code.
- **At mission end**, nothing is redrawn: the mission HUD goes with the mission, and the next one builds its slots
  from the restored row.
- **If the Lua state closes while P0 is applied,** the Runtime's finalizer restores the row as before. Then, if
  `refresh_hud()` last drew the custom code, it runs the same guarded redraw with the original code. That redraw
  refuses and writes nothing if the HUD is gone. `refresh_hud()` records which code it drew for this purpose.
- **Ctrl+F9** stays as a manual diagnostic.

Neither the redraw (`runtime/stratagem_hud.lua`) nor the P0 row write changed.

## When P0 applies

Ordering in a mission:

1. The game enters its Mission state and builds the mission HUD: 16 empty slots.
2. The Runtime sees the Mission state with a game mode: `mission_started` (`runtime/event_sources.lua`, the same state
   member). The host flag comes from the game mode.
3. **P0 applies.** The job settles in about 5 update ticks on real memory (measured on a mission snapshot).
4. The local Helldiver exists: its avatar network id resolves. On that frame the HUD fills its slots and draws each
   one from its row, so the 120mm draws Up Up Down Down.

The first P0 waited for a local avatar, polled every 0.5 s, and then needed several ticks. It always wrote after step
4, which is why the HUD kept the original arrows. How long steps 2 to 4 take in a live mission is not proven yet. The
proof logs it in seconds and frames, and it warns when the Helldiver already existed at the write.

## The write

`runtime/custom_stratagem.lua` `apply()` runs as a small job inside the game update. It fails closed unless all of these
hold:

- a mission (the Mission state with a game mode; never aboard the ship);
- the host (solo counts);
- every calldown reader pin matches;
- the 120mm row resolves from its catalogue id and package (`core/stratagem.lua` validates the whole
  StratagemSettings allocation);
- the row carries its identity, its count is 1 to 9, its array is inside the allocation, and it holds exactly the
  researched native code.

It no longer requires a local avatar. That requirement came from the proof's first design (apply once the mission is
playable). Removing it is safe for these reasons:

- **The write never used the avatar.** Resolve, guard, transaction and read-back use the catalogue, the
  StratagemSettings allocation and the row. The snapshot validation shows it: with the avatar network id overlaid as
  none, P0 applies with exactly the same two writes and restores byte-identical, in every mission snapshot.
- **The StratagemSettings rows are static data.** They are loaded before the ship: the 120mm row sits at the same
  offset in all seven snapshots, ship and mission.
- **No calldown can be in progress before the avatar exists.** Code entry needs the Helldiver, so the count cannot
  shrink under a partly entered code. A late write could still do that.
- **Mission and host remain required.** Aboard the ship and as a client P0 is still refused (`NOT_IN_MISSION`,
  `HOST_ONLY`), with or without an avatar.

The job reports `avatar = {present, id}`, read in the same tick as the write (the transaction does not yield).
`present` is false when the HUD had not filled its slots yet, and nil when the local player is not in the player list.

Then:

1. **The block.** A 40-byte Runtime-owned block (`owned_block`: room for 10 directions, the rest zero) receives
   {1, 1, 3, 3} and is read back. It is allocated once and kept, with the adapter that owns it, for the life of the Lua
   state.
2. **The transaction.** One guarded transaction on the row, using the whole 400-byte row as its captured context. It
   writes +0x48 = 4 (from the exact original count), then +0x40 = the block (from the exact original pointer). It
   checks the allocation's region and protection, writes each change with read-back, verifies every other byte of the
   row, and rolls back on any failure (`GUARD_REJECTED`).
3. **The read-back.** The row is re-read: the block, 4, Up Up Down Down.

The original pointer and count are kept. `restore()` writes the pointer back first, then the count, so a count never
exceeds the array it describes, from the exact values P0 wrote. The proof restores at mission end. If the Lua state
closes while applied, a finalizer restores too. Nothing else is written: no other member of the row, no other row,
no account item, no ship picker, no registry, no stratagem type, scrambler or loadout state, no HUD, no code.

## Collisions

No stratagem has the code Up Up Down Down. Three mission-objective stratagems have codes that start with it:

| Type | Native name | Code |
| --- | --- | --- |
| 71 | DropoffCargoContainer | Up Up Down Down Right Down |
| 102 | MobileCommsRelay | Up Up Down Down Right Right Down |
| 123 | CallInDestroyer | Up Up Down Down Left Right Left Right |

When one of them is available in the same mission, how the matcher resolves the shorter code against them is unknown.
Test in a mission without these objectives. The game itself already has identical codes for different types (for
example Resupply and type 109). How identical codes resolve is also unknown.

## Validation

- `tests/test_custom_stratagem.py`, on the offline fixture with a framed StratagemSettings buffer, covers:
  - the encoding, the length and the direction values;
  - exactly two writes (count, then pointer) through the real guarded transaction;
  - the original pointer and count preserved;
  - no other settings byte changed;
  - an unexpected original refused before the transaction (`ROW_CHANGED`) and inside it (`GUARD_REJECTED`, nothing
    written);
  - a restore that writes the originals back and leaves the settings byte-identical;
  - a block that outlives the restore and is reused;
  - mission, host and reader pins required;
  - P0 applied before the local avatar exists (reported `present = false`), after it exists (`present = true`), and
    with the local player missing from the list (unknown);
  - the proof addon end to end:
    - applied at mission start before the Helldiver, with the ordering logged;
    - the Helldiver appearing after it;
    - the late case (Helldiver already there) with its warning;
    - the client case, never applied.
- `scripts/validate_custom_stratagem_snapshot.py` runs apply and restore on the real 120mm row of every retained
  snapshot:
  - in the three mission snapshots it applies with exactly those two writes, reads back Up Up Down Down, changes
    nothing else, and restores byte-identical, both as the snapshot is and with the local avatar network id overlaid
    as none (before the Helldiver);
  - aboard the ship and at the mission end transition it is refused (`NOT_IN_MISSION`) with no write, in both cases.
- The HUD refresh (`tests/test_custom_stratagem.py` `HudRefreshTests`, on a fixture list built from the real HUD's
  bytes):
  - every cell's image and derived region bit for bit, and float32 rounding;
  - the slot found through the player's record and its 11 layout parents;
  - P0's redraw as exactly the 29 writes above, each address and byte checked, with no other byte of the HUD
    allocation, the record or the settings written, and the redraw back to the original;
  - the Lua-state close:
    - restore only, when never redrawn;
    - restore, then the slot back, when redrawn;
    - restore with the slot refused and untouched, when the HUD is gone;
  - refusals that write nothing:
    - no P0, aboard the ship, the HUD torn down;
    - the record holding another type, no slot, two slots;
    - scrambled, another displayed type, a running animation;
    - a wrong slot index, flag parent or sibling, a derived region one bit off, a gap in the arrows;
    - a third drawn code, a changed pin;
  - a sprite changed between the read and the write (`GUARD_REJECTED`, rolled back);
  - the proof end to end:
    - P0 applied before any HUD exists, the redraw waiting;
    - a HUD whose structure differs: refused once, nothing written, P0 intact;
    - the slot as researched: the 29-write redraw exactly once, and not repeated over 100 more ticks;
    - Ctrl+F9 finding nothing to do;
    - Ctrl+F12 restoring with the original redrawn automatically, then re-applying with the custom one redrawn;
    - mission end with no redraw;
    - the Runtime started mid-mission (redrawn at once);
    - a client (nothing written).
- `scripts/validate_custom_stratagem_snapshot.py` also redraws a slot on the real list of each mission snapshot. The
  120mm is not in those loadouts, so it uses Resupply, slot 2:
  - P0's own apply gives that row Up Up Down Down;
  - the redraw makes 30 guarded writes, none outside that slot's sprites, its 11 layout parents and its relayout flag;
  - the slot reads back Up Up Down Down;
  - after the restore it redraws Down Down Up Right (16 writes), then reports `current`.

  Aboard the ship and at the mission end it is refused (`NOT_IN_MISSION`).
- The packaged-runtime scenarios require the module after startup from the built ZIP, prove the readers, read the
  real 120mm row (type 136, its native code) and see P0 refused aboard the ship. They also require the HUD refresh,
  prove its pins, and see it refused aboard the ship.

## Live results

**2026-10-01, P0 first run** (solo host, applied after the Helldiver existed; runtime `HD2Runtime-0.28.0-runtime.zip`
6EF926CA...), as reported:

- the 120mm resolved from the catalogue, and its row changed from Right Right Down Left Right Down to Up Up Down Down;
- the matcher accepted Up Up Down Down, and the 120mm was called in;
- the barrage was the vanilla one: 18 shells over 19.2 s;
- the original code no longer called the 120mm;
- the mission-end restore wrote the original pointer and count back;
- **the HUD kept showing the original arrows.** This is explained in [The HUD](#the-hud).

Live-proven by this run: the guarded write and restore, the matcher reading the custom code, the old code no longer
matching, and the native call-in and barrage. Not proven: the HUD arrows. The next run tests the timing change.

**2026-10-01, second run: still the old proof build.** The log said "P0 applies once your Helldiver exists" and had
none of the timing lines, so the 0.1.0 proof that waits for the avatar was running. The matcher accepted Up Up Down
Down, the 120mm fired normally, and the HUD still showed Right Right Down Left Right Down. That is consistent with a
write after the HUD's first slot population. This run did not test the timing change.

**2026-10-01, third run: the early-application proof 0.2.0** (`CustomStratagemP0Proof-0.2.0.zip` D5D6ECA5..., runtime
BCA96F7C...), as reported:

- mission started at t=+0.00;
- the local Helldiver existed at t=+0.02 s, frame +2;
- P0 was written at t=+0.04 s, frame +4;
- the HUD filled the 120mm slot before P0 could change the row, and kept showing Right Right Down Left Right Down;
- the matcher accepted Up Up Down Down, and the 120mm call-in worked normally.

The Helldiver exists about two frames after the Mission state is first seen, before a guarded write can land, so the
timing approach is not viable and is not pursued further. The proof still applies at mission start; that is harmless
but does not fix the HUD.

**2026-10-01, fourth run: a full UI rebuild draws the custom code** (same artifacts), as reported:

- after P0 applied, the HUD showed the old arrows;
- then, in Options, the text language was changed to another language and back;
- the game's normal UI rebuild ran, and the 120mm's HUD arrows immediately changed to Up Up Down Down;
- F9 still read `active code Up Up Down Down (Runtime-owned)`, not restored;
- the matcher kept accepting Up Up Down Down;
- the call-in stayed vanilla: 18 shells over 19.2 s.

This confirms the HUD's stored arrows are the only stale copy, and that the game's own rebuild draws the row's
current code. A language change is not an acceptable way to refresh it, so it is not used.

**P0 gameplay is live-verified:**

- the guarded two-write change;
- the Runtime-owned code array;
- the matcher accepting the custom code;
- the old code no longer matching;
- the normal 120mm call-in and barrage;
- the restore.

Only the HUD presentation is unresolved.

**2026-10-01, fifth run: the direct HUD redraw** (proof 0.3.0 `CustomStratagemP0Proof-0.3.0.zip` 918DE153..., runtime
6A007142...), as reported:

- P0 changed the 120mm's code to Up Up Down Down, the matcher used it, and the normal barrage fired;
- the HUD first kept the old arrows;
- Ctrl+F9 redrew only the 120mm's slot, Right Right Down Left Right Down to Up Up Down Down:
  - 29 writes;
  - non-target bytes unchanged true, protection restored true;
  - type, loadout, scrambler and row untouched;
- Ctrl+F12 restored P0, and the slot's arrows returned to the vanilla code.

The 29 writes are the 23 the fixture predicted plus six more layout parents. The real list has 11 layout parents
above the arrow row, and the first nine get the bits. The Resupply case in the snapshot validation counts the same
nine.

**The direct HUD redraw is live-verified:** it draws the row's code in the slot and back, and the renderer keeps
drawing it.

**2026-10-01, sixth run: the automatic redraw** (proof 0.4.0), as reported:

- Right Right Down Left Right Down -> Up Up Down Down; the matcher accepted the new code, and the native 120mm call-in
  and barrage ran;
- the HUD slot was redrawn automatically, without a key press, in the same 29 writes: only the 120mm's slot (arrow
  regions, derived regions, flags, the layout parents, the relayout flag); type, displayed type, scrambler state,
  loadout and StratagemInfo untouched, and no HUD rebuild;
- the restore wrote the original pointer and count back, and the slot was redrawn with the original arrows
  automatically, without Ctrl+F9.

**P0 is fully live-verified, HUD included.** It is the reference implementation of the public field.

To keep the builds apart, the early-application proof is now 0.2.0 (`CustomStratagemP0Proof-0.2.0.zip`):

- its first log line names `0.2.0 EARLY-APPLICATION`;
- every `P0 written` line says whether the Helldiver existed at the moment of the write;
- the build refuses to ship a proof ZIP whose packed Lua is not the current source.

## The public field

`hd2.fields.stratagem.calldown_code` ([Stratagem calldown codes](stratagem-calldown-code.md)) is P0 generalised. It
writes the same two members with the same guards, and keeps the HUD in step with the same redraw.

| P0 (development) | The field (0.29.0 development) |
| --- | --- |
| `runtime/custom_stratagem.lua`, one hard-wired target | `domains/stratagem_writes.lua`: every catalogued call-in stratagem through patch, transaction, plan and ensure |
| One Runtime-owned block | `runtime/calldown_codes.lua`: one immutable array per distinct code, kept for the life of the Lua state |
| Mission and host gate | none, like every stratagem field: the row is local data and applies aboard the ship too; the HUD redraw waits for a mission |
| Redraw after apply and restore (the proof's 0.1 s check) | `runtime/calldown_codes.lua` checks every 0.25 s while a changed row or a pending redraw exists and redraws once per change, whichever path wrote the row |
| Ctrl+F9 manual redraw | none: the HUD sync is automatic |

The redraw is the same unchanged `runtime/stratagem_hud.lua` (now also `populated()`, a read-only check). Offline,
the field reproduces P0's live-verified bytes exactly: two row writes and the 29 HUD writes
(`tests/test_stratagem_calldown_code.py`).

### The proof on the public field (0.5.x, live-tested 2026-10-01)

`proof/CustomStratagemP0Proof` 0.5.0 no longer uses the private P0 module. It registers one `hd2.ensure` with
`hd2.fields.stratagem.calldown_code` on the 120mm (Right Right Down Left Right Down -> Up Up Down Down), once a
mission is active and this machine is the host. Its development-only parts are:

- logging;
- that registration scope;
- F9;
- read-only observers of the HUD sync's state and of the barrage's shells.

The restore is the public ensure's own: its `enabled` toggle on the MODS tab (Mod Options Menu), switched off. The
public API has no way for a mod to restore an ensure from code. So, unlike P0:

- there is no restore key;
- nothing is restored at mission end: the field keeps the code until the toggle is off, or the game closes and the
  Runtime's finalizer restores it.

The proof's own guide is `proof/CustomStratagemP0Proof/README.md`. Earlier builds (0.1.0 to 0.4.0) used the private
P0 module, and their results above are P0's. 0.5.1 added the GR-8 Recoilless Rifle (Down Down Down Down) through a
second ensure.

**2026-10-01, seventh run: the public field** (runtime ADDF4716, CustomStratagemP0Proof 0.5.1 E4FEE2A8), as reported:

- **Orbital 120mm HE Barrage** (Right Right Down Left Right Down -> Up Up Down Down):
  - it ran through the public `hd2.fields.stratagem.calldown_code` and `hd2.ensure`, with the guarded native write;
  - the automatic HUD sync made the HUD show Up Up Down Down;
  - the matcher accepted Up Up Down Down;
  - the normal 120mm call-in worked and the vanilla barrage executed.
- **GR-8 Recoilless Rifle** (Down Left Right Right Left -> Down Down Down Down):
  - it ran through the public field, with the guarded native write;
  - the automatic HUD sync redrew HUD slot 5;
  - the Runtime reported the new code active.
  - The log ended before its call-in, so the Recoilless delivery with the new code is not claimed.

The public field is live-proven for both targets (the Recoilless for the write and the HUD only;
`schemas/live_evidence.json`, session `public-calldown-field-2026-10-01`).

## Selectable custom stratagem: research (2026-10-01, offline)

Build F5FEE03DCFDB. Evidence comes from offline disassembly of game.dll from the retained snapshots, plus reads of
the retained snapshot files. Nothing was written. Addresses are game.dll RVAs.

Labels:
- **[C]** confirmed in code;
- **[O]** observed in snapshot data;
- **[I]** inferred;
- **[U]** unknown.

**Correction to earlier research.** `0x1923d60` is not the loadout picker. It builds the stratagem **StoreFront**,
the purchase list:
- its items come from the server's `GET %s/StoreFront` response;
- its confirm action POSTs `%s/StoreFront/buy {salesId, warId, expectedCost}` [C].

### The loadout picker (MenuScreenLoadout)

| Step | Code | What happens |
| --- | --- | --- |
| Slot clicked | `0x146e0a0` / `0x146d370` -> `0x146d9b0` -> `0x146e9d0` -> `0x18d8710` | The candidate grid is rebuilt on every slot click: a loop over types 1 to 149, keeping every type for which `0x136fc20` is true [C] |
| `0x136fc20(catalogue, type)` | | row = table[type]. Requires row +0xC0 bit 0 (enabled), row +0x80 bit 1 (selectable), and an item-catalogue record (kind-10 index range) whose +8 equals row +4 (the stable id) and whose definition state (+0x14) is 2 or 4, or whose parent item's state is 2 or 4 (owned) [C] |
| Stratagem picked | `0x189d050` -> `0x11f2490` -> `0x1893600` | The panel stores the **numeric type** [C] |
| Screen left | `0x1751350` | The preset is saved to the local save store `[0x347CDD8]` +0x4C as {stable id, uses} x 32. There is no backend loadout endpoint [C] |
| Screen left | `0x1467790` -> `0x66f190` | The local player record's slots are written, and `rpc_sync_stratagems` (0xB2E77CAE) is sent to the peers with raw u32 types [C] |
| Next session | `0x17514c0` | The saved pairs are restored: stable id -> type by a row scan, at most 4 slots by row +0xBC. **No availability, ownership or selectable check** [C] |
| Mission | `rpc_sync_player_history` (0xC953DB6D), `rpc_sync_stratagems`, `rpc_sync_stratagem_changes` -> `0x11e82d0` | Each player record's slots are written with the raw types. The only check is the sender's record key: no ownership, selectable or enabled check [C] |
| Reports | `0x135ceb0` / `0x135afd0`, from `0x1347a10` (mission_end / mission_reward) and the StateGame loadout logs | The slots whose row has +0x80 bit 1 are serialized **by enum name** as `"stratagems":[...]` [C]. Whether that record leaves the machine is [I/U]. `Operation/Mission/Start` carries no stratagems [C] |

### The account item -> StratagemInfo mapping

The item catalogue lives at `[0x347CEF8]` [C]:
- definitions: stride 0xB8 at +0x1CE4 (+4 mixId, +0xC kind, +0x14 state, +0xB0 amount);
- records: stride 0x18 at +0xB9CE4 (+4 mixId, +8 reference id, +0x10 offset back to the parent, +0x14 child count).

A kind-11 item's child is a kind-10 record whose +8 is the StratagemInfo +4 stable id [C/O]. There are 98 kind-11
items, all resolving to a type, and 91 of them are owned [O].

How it is filled [C]:
- the catalogue comes from `Progression/items`;
- ownership comes from `Progression/inventory`, once per session;
- after that, only incremental updates arrive (purchases, warbond unlocks, rewards).

Nothing re-validates ownership against the server before the picker or the loadout uses it [C].

### Carrier options

| Option | What the picker shows | What the loadout stores | What is displaced | Risk |
| --- | --- | --- | --- | --- |
| **A. Borrow an owned selectable type** | The carrier's entry, with the name, description, icon and category read from its row | Its own type, and its stable id in the save | The carrier's vanilla meaning, on this machine, while it is applied | None beyond the row edit: the save and the network carry a normal type |
| A'. Set +0x80 bit 1 on type 5 (Orbital Illumination Flare) | A new entry (the account owns its top-level catalogue record) [O] | Type 5 | Nothing | It persists: the save restores type 5 without the mod, sends it to hosts, and it appears in the `"stratagems"` report by name |
| B. Redirect a catalogue record's +8 | Another stratagem in place of an owned one | The other type | The redirected item | It edits account progression data (about 80 readers, including the buy pre-check), the server's next response overwrites it, and it can show unowned content |
| C. Write an in-mission slot | Nothing (not selectable) | Only the mission record | | A hidden replacement, not the goal |
| D. B + presentation | as B | as B | as B | as B. A + presentation does the same without the risk |

Only types 5 and 124 (Reinforce) have an owned top-level record without being selectable [O].

### Presentation

**The loadout screen and the in-mission menu read all of it from the row** [C]:

| Item | Source | Read |
| --- | --- | --- |
| Name | +0x28 / +0x2C (localization ids) | Live in the mission menu; the loadout details are cached by item |
| Description | +0x30 | Live in the loadout details |
| Icon | +0xB0 (an image resource hash) | Loadout slots: live. HUD slot widget: cached by type |
| Category and colour | +0xB8 (0 to 4 only) | |
| Beacon colour | +0xD4 (1 to 3) | Read once per beacon |

The in-mission menu icon is **not** type-keyed XAML. Only the Acquisitions screen (`0x14d8690`) uses the
StratagemType enum template and the +0x18 / +0x20 key strings.

Custom text still needs new localization entries. Existing ids and icon hashes can be borrowed as data.

### First selectable proof (CustomStratagemP0Proof 0.6.0, not yet live-tested)

Option A, with the Orbital 120mm HE Barrage as the carrier. The proof follows the normal selection pipeline read-only
and writes nothing but the public field:

- **`runtime/stratagem_loadout.lua`** (development, read-only) reads two things:
  - the saved ship loadout from the save store (`loadout` in `domains/stratagem_calldown.lua`, with 16 pins on the
    save and restore routines);
  - the local player's record (the HUD research's pins).
- **The 120mm is found by its stable id**, from the catalogue root; its type is looked up on the running build.
- **The HUD slot is matched** by `stratagem_hud.locate`. The slot carries its record index, and the record entry
  holds the same type.
- **Snapshot validation:**
  - `scripts/validate_stratagem_calldown_snapshot.py` reads the saved loadout on all 7 snapshots;
  - in the 3 mission snapshots, each saved stratagem is the record entry of the same type (entries 4 to 7), drawn by
    the HUD slot of the same index.

### First selectable proof: live-verified (2026-10-01)

CustomStratagemP0Proof 0.6.0 (runtime B90B81CB, proof 52AF67D7). The 120mm was selected normally in the ship loadout
screen. The proof followed it through:

- the saved loadout, by stable id;
- the mission player record;
- the matching HUD slot;
- the public `calldown_code` ensure;
- the automatic HUD refresh;
- the custom calldown being accepted;
- the normal 120mm call-in.

No account item, inventory, catalogue, saved-loadout or stratagem-registry write was made. **The 120mm is a proven
selectable carrier** (`schemas/live_evidence.json`, session `selectable-carrier-2026-10-01`).

## Presentation (borrowed vanilla resources)

The carrier can look like another stratagem while it stays the carrier. Offline research, build F5FEE03DCFDB:
`research/stratagem-calldown-*.json` `presentation`, with 13 reader pins proven on all 7 snapshots.

### What reads the presentation [C]

| Member | Value | Readers |
| --- | --- | --- |
| +0x28 name, +0x2C cased name | u32 localization id | Mission menu name: `0x66d559`, read live. Loadout details name: `0x179d95d` / `0x179d962`; its widget is keyed by the stable id (`0x189fbba`) |
| +0x30 description | u32 localization id | Loadout details: `0x189fbd0` |
| +0xB0 icon | 64-bit image hash | Loadout slot: `0x1893650`, set through `0x1450160`. HUD slot widget: `0x183a1e5`. Plus the loadout grid and tooltip builders `0x18d7360` and `0x191dfb0` |

### The HUD cache [C]

The HUD slot widget compares the record entry's type with its cached type (`0x183a05b`, +0x14C8). It rebuilds the
visual, including the icon, only when they differ. A presentation written after the slot was built is therefore drawn
in the next mission. Apply it aboard the ship, before the mission: the normal construction path then consumes the
modified row. No HUD cache is written.

### Excluded members

| Member | Why it is excluded |
| --- | --- |
| +0x10, +0x18, +0x20 | String pointers (the debug name, and the Acquisitions title and description keys). Copying them would share another row's strings |
| +0x34, +0x38 | No reader found. +0x38 is one value per stratagem family |
| +0xB8 | The category. It also selects the loadout tab, the HUD colour set and the category label |
| +0xD4 | The beacon colour index, which the game does not bounds-check |

For the 120mm and the Gas Strike, +0xB8 (0) and +0xD4 (1) are already equal.

### The proof (CustomStratagemP0Proof 0.7.0, not yet live-tested)

`runtime/stratagem_presentation.lua` borrows the Orbital Gas Strike's name, cased name, description and icon for the
120mm:

- 4 guarded writes, from the reviewed native values to the donor's reviewed values;
- the type and stable id never change;
- restore writes the exact native values;
- a finalizer restores before the Lua state closes;
- the build and reader pins are proven first;
- any other member is refused.

Validation:
- the unit tests in `tests/test_stratagem_presentation.py` and `tests/test_stratagem_calldown_code.py`;
- `scripts/validate_stratagem_calldown_snapshot.py`: on all 7 snapshots, 4 writes, nothing outside the four members,
  type 136 and stable id 1063322614 unchanged, and the restore byte-identical;
- the packaged scenario `proof-calldown-public-field`.

What still needs a resource mechanism:
- truly custom text: new localization entries;
- custom icons: an image resource with its own hash.

The row only holds ids and hashes.

### Public presentation fields (0.29.0 development)

The live-verified presentation is now public. `hd2.fields.stratagem.presentation_name`, `presentation_name_cased`,
`presentation_description` and `presentation_icon` ([Stratagem presentation](stratagem-presentation.md)) work for every
call-in stratagem through patch, transaction, plan and ensure. A value names a catalogued stratagem, an existing
vanilla resource. CustomStratagemP0Proof 0.8.0 exercises them on the 120mm carrier.

One source is refused: the LIFT-860 Hover Pack's cased name. Its localization id is in no registered strings
resource, so it would display blank.

## Custom presentation resources: research (2026-10-01, offline)

The question: can a mod provide its own name, description and icon, never overwriting a vanilla entry or texture?
Evidence: the helldivers2.exe and game.dll images from the retained snapshots, the installed game data (read-only),
and snapshot memory. The labels are those of the research above.

### Text

The row's u32 is resolved by the engine's localizer (API slot +0x3E8, exe 0x321c40) [C]:

- **Storage:** a list of registered strings resources at exe 0x1a101e0. Each resource holds a sorted language-hash
  array, a sorted id array and an offset table. The first registered resource that has the id wins.
- **Missing id:** an empty string, shown blank. No crash.
- **Id:** the upper 32 bits of MurmurHash64A (seed 0) of the key without its `nui_` prefix. For example
  `stratagem_orbital_gas_name` gives 0x34DEFEED. All six example ids match.
- **Format:** reproduced byte for byte for all 264 vanilla resources: `0x3E85F3AE`, the language count, the id count,
  the sorted language hashes, the sorted ids, the per-language offsets, and NUL-terminated UTF-8.
  - Type `strings` is 0x0D972BAB10B40FD3.
  - All the resources live in the boot archive (`packages/boot`, 0x9BA626AFA44A3AA3).
  - There are 15 text languages, and no per-id fallback to another language.
- **Registration is the catch** [C]. At every language change, exe 0x12fedc0 registers a hard-coded list of 17
  `localization/<base>_<language>` names, and nothing else.
  - A resource that is merely loaded, even by a package, is never consulted.
  - Two listed names do not exist in this build: `temp_strings_<lang>` and `strings_enemyvoiceovers_<lang>`.
- **Two routes:**
  - **B.** Ship `localization/temp_strings_<lang>` in a boot patch, and the game registers it itself. But it is one
    slot shared by every mod, and a future build could ship it.
  - **C.** The Runtime registers a uniquely named resource itself, through API slot +0x3D0. This needs native-call
    proofs, a re-registration after every language change (the list is cleared), and an answer on the thread safety
    of the list.
  - Either way, the resource must stay resident for the session: the list holds raw pointers.

### Icon

The row's u64 is a resource name hash. The image setter `0x1450160` resolves it immediately and does not retry later
[C]:

- **Atlas sprite first.** It looks the hash up in the engine's sprite-atlas map. Every vanilla stratagem icon is a
  256x256 sprite on a 4096x4096 BC1 atlas page in `packages/content/atlas_shared`, which is resident aboard the ship
  and in missions [O].
- **Standalone texture otherwise.** On an atlas miss it binds a standalone texture (type `texture`,
  0xCD4238C6A0C69E32) by that name, using the full UV.
- **Missing texture:** the engine's yellow and purple placeholder (`core/fallback_resources/missing_texture`), not a
  crash.
- **What a mod would ship:**
  - a standalone texture, named under its own namespace, in a boot patch archive (where the Runtime already ships its
    Lua), loaded with the boot package at startup;
  - the vanilla icon layout: the 0xC0 header, DDS and DX10 headers, BC1 256x256 with 9 mips, red and green mask
    pixels, tinted by the category colour, and the pixel data in `.gpu_resources`;
  - `+0xB0 = MurmurHash64A(name)`.

  No native call and no package request are needed. A sample archive was built and parsed back in research scratch.

### Verdict and next capability

Custom resources are not part of this release. Both are feasible, but neither fits safely now:

- **The icon** needs:
  - a texture-capable archive writer (several types, `.gpu_resources`, the vanilla size fields);
  - SDK build support so that a mod project ships its images;
  - a read-only residency check (a resource-manager reader, under the field-proof rules).
- **The text** needs route C's native registration (pins for 0x321aa0, 0x321c40 and the API slots, re-registration
  after language changes, thread safety) or route B's shared slot.

Proposed order, each a separate proof so that two uncertain systems never fail together:

1. **The custom icon** (a standalone texture in the proof's boot patch).
2. **The custom text** (route C).

Proposed public API, hiding hashes, archives and residency:

- **Project declaration.** The mod declares its resources in its project, so the SDK packs them into the mod's
  archive:

  ```json
  "resources": {"images": {"gas_barrage": "icons/gas_barrage.png"},
                "text": {"gas_barrage_name": {"us": "ORBITAL GAS BARRAGE"}}}
  ```

- **Lua references.** `hd2.resources.image('gas_barrage')` and `hd2.resources.text('gas_barrage_name')` return
  handles.
- **Use.** A handle is a `value` of the matching presentation field, alongside the stratagem-name values.
- **Guards.** The Runtime checks the resource type and that it is resident before writing, and refuses otherwise.

## Custom images: live test crashed (2026-10-01); refused

Author-facing summary: [Custom images](custom-images.md). Evidence:
- `research/image-resources-F5FEE03DCFDB.json` (format, archive, residency);
- `research/stratagem-icon-consumers-F5FEE03DCFDB.json` (the icon consumers and the crash).

**What held:**
- **Format [O]:** the texture's main part is byte for byte the 120mm icon texture's.
- **Archive [O]:** `make_resource_archive` reproduces vanilla archive tables.
- **Loading [S, L]:** boot patch parts are resident all session. In game, the proof's texture was found loaded.
- **The guarded write [L]:** exactly 1 write; identity, name and description unchanged.

**What failed [L, C]:** about 45 s after the write, opening a slot in the loadout screen crashed the game.
- **Minidump:** access violation reading 0x38 at `helldivers2.exe+0x341D1A`, with `rdx` = 0.
- **Windows event:** `ntdll+0x7E907` `0xC000000D`. That is the game's crash handler ending the process; the same
  signature closes earlier sessions that had unrelated exit-time faults.
- **Unwound chain:**
  1. slot click `0x146ED65`;
  2. grid `0x18D8710`;
  3. entry builder `0x18CAFB0`, which writes a style descriptor `{name = StratagemInfo +0xB0, kind 2}` (`0x18CB533`,
     `0x18CB541`);
  4. `0x18DC5D0`, `0x1943650`, `0x1943D10`;
  5. kind 2 calls `0x144F800` (set material by name);
  6. `0x143F210` → `0x12EE1E0`: the GUI material cache, else GUI API +0x230 = exe `0x264620` (looks the name up as a
     material resource; "Material not found." → null);
  7. `0x143F0B0`, which calls `0x1449400` with the pointer even when it is null;
  8. GUI API +0x240 = exe `0x341CE0` (clone a material instance), which reads `material+0x38` without a check.
- **Stack evidence:** the custom image's name hash was on that stack; the 120mm's native icon hash was not.

**The missed contract [S, C]:**
- **One value, three resources:** an icon value names a GUI material, an atlas sprite and a texture of one name.
  - All 111 vanilla icon values are a loaded material and atlas sprite in all seven snapshots; none is a loaded
    standalone texture.
  - Their materials are one 160-byte UI material, differing only in the image property `0x3AA8B87E` at +0x8C (the
    icon's own name).
- **Consumers of +0xB0 (13 sites, pinned):**
  - material descriptors: `0x18CB541` and `0x18CBE2B`, plus the same `{name, 2}` shape at `0xFFC703` and
    `0x13D14E4`;
  - image widgets with an atlas → texture → fallback chain: `0x1893650`, `0x1922F43`, `0x19242EB`, `0x19B9779`,
    `0x17EF941`, `0x17EFBD6`, `0x18277AB`;
  - a getter: `0x18DCF27`.
- **Why the earlier research missed it:** it followed only the image widget path (`0x1450160`).
- **The two loadout grid readers are not among the presentation reader pins.** Vanilla values are safe there: every
  vanilla icon has its material.

**Decision:** `presentation_icon` refuses custom images when the operation is registered. `hd2.resources.image` is
not public. The texture reader and the SDK image packing stay as development infrastructure. A custom icon needs a
Runtime-owned GUI material next to the texture, which is a separate proof (see [Custom images](custom-images.md)).

## Icon resource family: offline research (2026-10-02); custom icons still refused

Evidence: `research/stratagem-icon-family-F5FEE03DCFDB.json` (`scripts/research_stratagem_icon_family.py`).

**Resource type handlers [S]:** read from the resource manager's type handler table.
- **texture:** loader `0x4D6310`.
- **material:** loader `0x168100`, online callback `0x168700` → `0x4F2F60` ("Initializing material").
- **texture_atlas:** no loader; online callbacks `0x4C0FA0` / `0x4C1010`.

**The GUI material format [C, O, S]:**
- **Header (0x18 bytes):** `{0x120, kind, 0x18, 0x7C}`, plus a dependent count at +0x10. Kind 0 is a material set,
  which GUIs refuse.
- **Body:**
  - +0x00 parent name;
  - +0x08 the material object (a loader fix-up);
  - +0x18 / +0x20 pointers to the slot ids (u32) and slot names (u64) at +0x70 (loader fix-ups);
  - +0x28 slot count;
  - +0x68 shader id.
- **Every vanilla icon material** is kind 1, shader `0x3461FF0D`, with no parent, no dependents and one slot
  `0x3AA8B87E` naming the icon itself. They are 160 bytes, identical apart from that name, in the archives. In memory
  they also match, apart from the three fix-ups, with an object {magic `0xD92A8333`, body, shader, name}.

**From slot name to pixels [C]:**
- **Material instances:** a material instance (`0x4F2DD0`) resolves each slot name as a texture by name, with the
  missing-texture fallback.
- **Material-mode widgets (all eight widget-kind handlers of `0x144F800`):**
  - they get the material from the GUI material cache (`0x264620`: has-resource, else null) and clone it without a
    null check;
  - two handlers then ask GUI API +0x350 for an atlas sprite among the material's slot names. Found: the atlas page and
    the sprite's UV rectangle. Not found: the full rectangle and the slot texture bound by name;
  - the other six use the instance's slot texture.
- **Image widgets:** they ask GUI API +0x348 for an atlas sprite of the name. Not found: the full rectangle and the
  texture by name (`0x30F1B0`: sprite redirect, else the texture, else the missing-texture fallback).

**Dependency graph:**

```
StratagemInfo +0xB0 = N
 ├─ material readers   0x18CB541, 0x18CBE2B (loadout grid), 0xFFC703, 0x13D14E4 ({N, kind 2})
 │    └─ GUI material N   REQUIRED (no fallback)
 │         └─ pixels: atlas sprite N if any, else the slot texture N by name
 ├─ material-slot images   0x17EF941, 0x17EFBD6, 0x18277AB
 │    └─ material N (fallback: missing_material) → slot texture name → texture by name
 ├─ image widgets   0x1893650, 0x1922F43, 0x19242EB, 0x19B9779
 │    └─ atlas sprite N if any, else texture N (fallback: missing_texture)
 └─ getter 0x18DCF27 (no static caller; returns N unresolved)

vanilla icon = GUI material N + atlas sprite N        (no loaded texture N)
custom icon  = GUI material N + texture N             (no sprite needed)
```

**Offline proof:**
- **Build:** the SDK ships the custom family (texture + material) in the mod's archive.
- **Material bytes:** byte for byte the vanilla template apart from the name.
- **Archive:** the vanilla icon-material package's archive table is reproduced. Index numbering is reported separately:
  vanilla archives may skip an index.
- **Names:** no collision with any game resource; one family per mod.
- **Runtime family reader:** accepts only the texture plus the exact loaded material with no sprite of that name.
  - Offline, it refuses texture-only (the crash condition), material-only, wrong shader, a material set, extra slots,
    another name, missing fix-ups and a wrong material object.
  - On all seven snapshots it reads 111/111 vanilla icon values as their exact GUI material plus an atlas sprite.
- **Packaged runtime:** the shipped artifact reproduces this on the snapshot. With the proof's texture loaded,
  `presentation_icon` still refuses, with 0 writes.

**Not established:** the game drawing a custom family. Live behaviour of the material's shader with a 256 x 256
standalone texture is untested; vanilla binds the 4096 x 4096 atlas page in the same slot.

**Vanilla presentation_icon guard (separate from custom icons):** the vanilla field is safe on this build.
- **Why it is safe:** every source is a reviewed vanilla icon whose GUI material and sprite are loaded in all seven
  snapshots. The build fingerprint refuses any other build.
- **Recommended separate change:** add the four material readers (`0x18CB533`/`0x18CB541`, `0x18CBE2B`, `0xFFC703`,
  `0x13D14E4`) and the material path's no-fallback code (`0x264743`, `0x341D1A`) to the presentation reader pins.
  Also make snapshot validation require that every presentation source icon is a loaded GUI material.
- **Why it matters:** together these let a build migration catch a change in how the loadout grid consumes the icon.
  Behaviour is unchanged.

## Custom icons: live-verified (2026-10-02) and public

- **The live tests:** CustomStratagemP0Proof 0.10.0 (read-only probe, PASS), then 0.11.0, which wrote the complete
  family to the 120mm's icon member aboard the ship (LIVE VERIFIED).
- **What the user saw:** the loadout UI, including the loadout grid that crashed 0.9.0, drew the custom icon. The 120mm
  kept its type, stable id, name and description, the mission loadout stayed valid, the restore worked, and nothing
  crashed.
- **Not hot-swapped:** a change is not drawn into a mission HUD that is already built. That is the documented behaviour.

**Now public:** `hd2.resources.image(id)` is a `presentation_icon` value ([Custom images](custom-images.md)).
- **Guards:** `image_resources.icon_ready` checks the guards of the live-verified write: every +0xB0 consumer pinned,
  the complete family loaded and exact, and its slot resolving to the custom texture. Otherwise the field refuses with
  `ASSET_UNAVAILABLE` before anything is written.
- **Retired:** the development `apply_icon` path.
- **Evidence:** live evidence family `stratagem_presentation_custom_image`; the 0.9.0 failure stays on record,
  superseded.

## Custom text: researched, implemented and live-verified (2026-10-02); not public yet

Author-facing details: [Custom text](custom-text.md). Evidence: `research/stratagem-text-F5FEE03DCFDB.json`.

**What the research settled [C, O]:**
- **One lookup:** every displayed stratagem text id resolves through `helldivers2.exe 0x321C40`, the only reader of
  the text registry `[exe+0x1A101E0]`. It walks the registered tables in order; the first that holds (language, id)
  wins.
- **One registrar:** only `game.dll 0x12FEDC0` writes the registry: at startup, and on every language change, where it
  clears the registry and registers its own tables again.
- **Headroom:** every retained snapshot holds 17 tables in an array of capacity 18.
- **The format:** reproduced byte for byte for all 264 game text resources.

**Route taken:** neither route B nor route C from the 2026-10-01 research.
- **The table:** one Runtime-owned table holds every mod's texts in all 15 languages.
- **The registration:** two guarded writes append it after the game's tables in spare capacity: the slot, then the
  count. There is no native call, no reallocation, and no game table or entry is changed.
- **Language changes:** the Runtime registers it again after the game drops it.
- **The memory:** read-only and never freed.

**The development proof:** `runtime/stratagem_presentation.lua` `apply_text` writes the carrier's name, cased name and
description to the Runtime ids. CustomStratagemP0Proof 0.12.0 combines it with the public custom icon and the public
calldown code (Up Up Down Down) on the 120mm carrier, which still fires the normal 120mm barrage.
- **Validated offline:** unit tests; every retained snapshot (registered as the 18th table, exact, restored); and the
  shipped artifact on the snapshot's real registry.
- **Live-verified (2026-10-02):** the custom name, cased name, description and icon showed in the ship loadout and the
  mission, Up Up Down Down called in the normal 120mm barrage, and the text was registered again after language changes.
  The 120mm stayed type 136, stable id 1063322614. No account, inventory, catalogue or loadout identity was modified.
- **Not yet:** a public text API.

## A genuinely new selectable stratagem: research (2026-10-02, offline)

Evidence: `research/stratagem-identity-F5FEE03DCFDB.json` (`scripts/research_stratagem_identity.py`). It uses game.dll
and all seven retained snapshots of build F5FEE03DCFDB, which is the installed build. Nothing was written.

Three concepts, kept apart:
- **A.** A new numeric StratagemInfo identity (a new type).
- **B.** A new selectable ship-loadout entry.
- **C.** Custom presentation, calldown and payload on an existing owned carrier. Presentation and calldown are
  live-proven.

### The registry [C, O]

**A fixed array.** The registry is `game.dll +0x37CB600`, a static array of exactly 150 row pointers, indexed by type.

**One writer.** Its only writer is `0x11F2080`:
1. it loads the game's own `generated_stratagem_settings.dl_bin`;
2. it zeroes the array (0x4B0 bytes, 150 pointers);
3. it stores `table[row.type] = row` for every row of that resource, with no bounds check.

**No other code stores into it.** The research scanned all 286 instructions that address the array, in 178 functions.
- There is no second registry, no registration call and no stable-id index.
- The only stable-id lookups are linear scans of types 1 to 149.

**Every type is taken.** In every snapshot:
- `table[0]` is empty: type 0 means none, and maps to the static default row `0x37CB470`;
- types 1 to 149 are all filled, each row carrying its own type, all inside the settings buffer.

**The enum is fixed too.** The StratagemType enum-name table (`0x21D4AA0`) holds 150 names followed by `Count`. The
enum is compiled with Count = 150.

**The readers trust the type.** Only 12 of the 286 references have a 0x95 / 0x96 compare earlier in their function.

**The only alternate resolution found:** the mission menu takes type 128's name (UploadDiscovery, a mission objective)
from a mission object (`0x6F24D0`) before its row. It is keyed by that vanilla type and is not an extension mechanism.

### The ship picker [C]

The grid (`0x18D8710`) is rebuilt on every slot click. It works in three steps:
1. it loops types 1 to 149;
2. it keeps each type the availability check `0x136FC20` accepts, in a stack-local array;
3. it joins each kept row to its account-catalogue record by stable id.

**What a grid entry requires (all of these):**
- a type 1 to 149 with a row;
- row +0xC0 bit 0 (enabled);
- row +0x80 bit 1 (selectable);
- an account-catalogue record whose +8 is the row's stable id, owned (definition state 2 or 4, or a parent item's).

**The type loop is the grid's only source of entries.** No UI model, mod resource, local list or Runtime-owned row
feeds it.

### Selection, persistence and the network [C]

| Step | What is carried |
| --- | --- |
| Picked in the grid | the numeric type (`0x1893600`) |
| Local preset (screen left, `0x1751350`) | {stable id, uses} pairs in the local save store; no backend endpoint |
| Next session (`0x17514C0`) | stable id -> type by a scan of types 1 to 149; no ownership or availability check; **a stable id no row carries is dropped**; at most 4 slots by row +0xBC |
| Mission loadout | the player record's slots: raw types |
| Network (`rpc_sync_stratagems`, `rpc_sync_player_history` -> `0x11E82D0`) | raw u32 types. Each receiving machine writes them into its player record and indexes the registry **unchecked**, then reads row +0x94 |
| Mission report | each selectable slot by its enum name, indexed by type |

### Determinations

| | Possible? | Why |
| --- | --- | --- |
| **A. New numeric identity** | **No** (not safely) | The array, the enum (Count = 150) and the picker loop all end at 149, and all 149 types are taken. Type 0 means none. A type of 150 or more would be outside the array on every machine that received it in a loadout sync: it is indexed unchecked. |
| **B. New selectable entry** | **No**, without a type | The grid's only entries are accepted types 1 to 149, and acceptance needs an owned catalogue record carrying the row's stable id. Even a second grid entry for an existing type could not be told apart downstream: the loadout, the save, the mission record and the network carry only the type or its stable id. |
| **Without account or catalogue writes** | **No** | Every route to a new entry needs one of three things: a catalogue or ownership change, a vanilla type made selectable (type 5 or 124, which persists without the mod), or code patches. All three are excluded. |
| **C. Carrier** | **Yes**, live-proven | |

**True new selectable StratagemInfo identities are not supported safely by the current game architecture.**

### The supported custom-stratagem model

```
owned, selectable vanilla carrier   (its type and stable id never change)
  + Runtime presentation            (name, cased name, description: Runtime text; icon: Runtime image)
  + Runtime calldown                (public calldown_code)
  + Runtime payload                 (next)
```

**What it is and isn't:**
- The player selects the carrier in the normal ship loadout, which requires owning the carrier.
- The save, the mission record and the network carry the carrier's own type and stable id. So removing the mod leaves a
  valid vanilla loadout.
- It is a custom stratagem built on a vanilla identity. It is not a new native identity, and is never presented as one.
- The carrier's vanilla meaning is displaced on this machine while it is applied.

**Multiplayer: not supported.** Other machines receive the carrier's type and see the carrier's own presentation.
How a custom payload behaves when the carrier is called on another player's machine, or by a client, is not traced.
Until it is proven, any payload work stays gated to solo or host development.

### The smallest next step toward the Orbital Gas Barrage

Offline research of the payload, before any write:
- the 120mm's call-in chain: its payload, its BombardmentComponentData shells and their projectile and explosion rows;
- the Orbital Gas Strike's chain: what makes the gas (projectile, explosion, status effect, area);
- which existing guarded mechanisms can make the 120mm's barrage deliver gas.

**Mechanisms to evaluate:**
- the stratagem's projectile and explosion reference fields;
- the custom projectile hybrid rows (docs/custom-projectile-rows.md);
- the projectile builder.

Each must be on the carrier's own rows: no vanilla row is shared with another stratagem. Today the 120mm exposes 85
writable value fields (projectile, explosion, damage, stratagem) but no projectile or status reference field. So the
first question is where a gas payload can attach.

## Duplicate slots and virtual stratagems: research (2026-10-02, offline)

**The question:** can two loadout slots hold the same vanilla type, with the Runtime treating one of them as a
virtual custom stratagem? For example, slot A the native Precision Strike, and slot B the "Orbital Gas Barrage", also
type X, with its own presentation, code and payload.

Evidence: `research/stratagem-duplicates-F5FEE03DCFDB.json` (`scripts/research_stratagem_duplicates.py`). It holds 35
pinned instructions, identical on all seven snapshots. The installed Stratagem MultiSelect mod was read as a lead only.
Nothing was written.

### How Stratagem MultiSelect does it [lead, confirmed in code]

- **Core:** every 3 frames, it re-enables each loadout card that the grid greyed because its stratagem was already
  selected. It does this through the game's own per-card enable helper (`0x18D1440`), found by a byte signature.
- **Vehicles:** it clears the category bits 0x00100000 / 0x00200000 / 0x00400000 of StratagemInfo +0x104 on every row.
  That is a global write to vanilla rows, which the Runtime rules exclude.
- **Untouched:** the save, the mission record, the HUD, the matcher and executable code. It does call native UI code.

### The pipeline with two slots of one type [C]

| Stage | Two slots of one type | Slot identity |
| --- | --- | --- |
| Picker grid (`0x18D8710`) | A card whose type is already in a slot is **greyed** (`0x18D8BEC`); the only duplicate refusal | |
| Selection | Refuses a second vehicle of a category (`0x146E5BF`); the pick (`0x189D050`) sets slot widget *n* to the type and draws **the type's row** icon (`0x1893600`) | the slot index |
| Save (`0x1751350`) | One {stable id, uses} pair per slot, in order; no duplicate check | slot order |
| Restore (`0x17514C0`) | Appends the pairs in order; no duplicate check | slot order |
| Peer sync (`0x11E82D0`) | Writes slots by index | the index |
| HUD | One slot per record entry, taking its type | entry = slot |
| Per-slot state | Uses (+0x18C), cooldown end (+0x1A0), in-flight beacons keyed by (peer, slot index) (`0x66D200`) | the index |
| **Matcher (`0x66D8C0`)** | Compares the input with **the slot's type's code** (`0xA106C0`). Keeps **one candidate per type** (a type-indexed map, `0x66DC10`). A second matching slot of the same type replaces the first only with more uses (`0x66D3D0`) or when the first is not ready | **lost**: the game chooses between two slots of one type |
| Code, presentation, payload | All read from **the type's row** | per type |

The per-player scrambler (`0x66DDA3`) remaps the type, never the slot.

### Determinations

| | Answer |
| --- | --- |
| Duplicates coexist | **Yes in game logic.** Only the picker UI greys a selected card. Getting past that needs a write to the loadout UI state (the card's enabled flag) or a native UI call, as MultiSelect makes. No account or catalogue write is needed. |
| Survive into the mission | **Yes.** Save, restore, the mission record, the peer sync and the HUD keep both slots, by index. |
| Slot identity | **Kept** by the record, the save order, the HUD and the per-slot uses, cooldown and in-flight beacons. |
| The matcher returns a distinguishable slot | **No**, for two slots of one type. The result is a slot index, but the type-keyed candidate map has already chosen it by uses and readiness. |
| Deduplicated before matching | **Yes, during matching:** one candidate per type. The HUD still shows both slots. |
| Different codes for the two slots | **No.** The code is read from the type's row, and no per-slot code exists. |
| Slot-specific presentation | **No.** The loadout slot widget, the HUD slot and the menu name read the type's row. Changing the row changes both slots. The only alternative is writing UI widget state, a HUD hot-swap, which is excluded. |
| Runtime virtual-stratagem registry | **Not feasible without executable hooks.** Code, candidate choice, presentation and payload are all per type. |

**The invariant that prevents it:** a StratagemInfo row is the unit of code, presentation and payload, and the matcher
deduplicates candidates by type. Two slots of one type are interchangeable to the game. It keeps only their uses,
cooldowns and in-flight beacons apart, and it picks between them by itself.

**What it would take:** native hooks, which the rules exclude:
- per-slot codes in the matcher's code copy;
- a slot-keyed candidate map;
- per-slot presentation in the loadout and HUD builders;
- per-slot payload at the call-in.

**No proof is built.** A duplicate-slot proof would only show that two interchangeable slots coexist, which the code
already shows.

**The route within the rules:** to have a custom stratagem next to a native one, use **a different owned carrier**.
Each custom stratagem gets its own type, row, code, presentation and payload; the carrier model already supports that.

**Multiplayer:** unsupported. Peers receive both slots' types by index, and their matchers apply the same per-type
deduplication.

## Mission-time slot conversion: researched (2026-10-02, offline) and live-verified (2026-10-02)

**The idea:** a duplicate native stratagem is only a **selection token**. The ship saves two Orbital Precision
Strikes. In the mission, the Runtime changes **only the later one's type** in the local player's mission record to an
owned, unselected vanilla carrier, the Orbital 120mm HE Barrage. The game then sees two different, legitimate vanilla
stratagems, and the carrier's own row provides presentation, code, payload and cooldown. A virtual custom stratagem
would then customise the carrier.

Evidence: `research/stratagem-slot-conversion-F5FEE03DCFDB.json` (`scripts/research_stratagem_slot_conversion.py`). It
holds 75 pinned instructions, identical on all seven snapshots, and was checked against the game's bundle database.
Nothing was written.

### The record [C, O]

**Where it is:** `[game+0x347CE50]` holds the per-peer stratagem records: {u64 peer, ...}, 0x1690 bytes each, count at
+0x2D200.
- A record's stratagem state at +0x38 holds up to 16 entries of 0x30 bytes at +0x188, and their count at +0x788.
- **The entry:** +0 type, +4 uses, +9 granted flag (1 for defaults and mission grants, 0 for loadout picks), +0x18
  cooldown end. The call-in key is at state +0x9E8.

**Who writes it:**
- `0x66EFD0` clears a record and appends the mission's default stratagems.
- `0x66F190` appends entries.
- **The rebuilds:** the ship's sync (StateShip on_synchronized_tasks_done), a loadout handler (`0xAD9020`) and the
  loadout screen's exit.
- **Grants:** mission systems append granted stratagems (`0x856FE0`).
- **Peers:** the peer sync writes received entries.

**No writer checks ownership, or that a type was in the saved loadout.**

**The order:** in the mission snapshots the local record's loadout entries are the save, in order.

**At the mission end transition** the record is already rebuilt for the ship: the loadout only, in **reverse** order.
So the game itself discards a mission-time conversion.

### The readers [C]

| Reader | With a converted entry |
| --- | --- |
| HUD | Each slot takes its entry's type every frame (`0x183675C`). It rebuilds its arrows on a type change (`0x1836D09`) and its icon when the type differs from the remembered one (`0x183A05B`): **the vanilla HUD refreshes the slot, with no HUD write** |
| Matcher (`0x66D8C0`) | Reads each entry's type and that type's code (`0xA106C0`), one candidate per type: **the carrier is its own candidate, with its own code** |
| Its result | The matched **type** (`0x66E1E3` → input +0x14), which activation (`0x671440`) maps to the type's row: **the carrier's call-in** |
| Uses, cooldown, in-flight call-ins | Stay with the entry: +4, +0x18, and (key, slot index) (`0x66D200`) |

### Assets [O]

- **In every mission snapshot** the game holds the root package of every record entry's type, plus carried equipment.
- **Aboard the ship** it holds none.
- **The unselected 120mm's package** is resident in **no** snapshot.

So a converted slot's carrier package must be loaded **first**. The Runtime now resolves a stratagem's call-in package
by stable id (`core/assets.lua` `dependency_for_stratagem`, `domains/stratagem_slots.lua`). It loads it through the
same gate and native system as reference swaps. The live test loaded the 120mm's package this way before the write
(the conversion is refused while it is not resident); no other stratagem package is live-proven.

### Reports [C]

- **Mission start:** the "on_mission_start … loadout: %s" log (StateGame sync done) records the loadout before any
  conversion.
- **Mission end:** the `mission_end` / `mission_reward` events (`0x1347A10`, from the state change `0xAB3350`)
  serialize the record's selectable entries by enum name. A slot still converted at the mission end appears there under
  the carrier's (owned) name.
- **Unknown:** whether those events leave the machine.
- **No pre-exit restore:** none is possible from known signals. The game's state change happens before the Runtime can
  see it.

### Determinations

| | Answer |
| --- | --- |
| Conversion possible | **Yes:** one 4-byte write of the local entry's type, after the mission's last rebuild and before the slot is used |
| Field and guards | Entry +0. See the guard list in `runtime/stratagem_slot_conversion.lua` and `proof/VirtualSlotProof/README.md` |
| HUD refreshes naturally | **Yes,** from code: its own type-change path |
| Matcher distinguishes the slots | **Yes:** two types are two candidates; the carrier's code comes from its row |
| Normal carrier call-in | **Yes, if its call-in package is resident** (the Runtime loads it first) |
| Unselected but owned carrier accepted | **Yes:** no record path checks ownership or the saved loadout. Runtime policy still requires an owned carrier. |
| Saved token untouched | **Yes:** the save store and the loadout screen are never written; the game rebuilds the record at the mission end |
| Solo / host | **Solo only.** A direct write sends nothing, so peers keep the token. Gated to one record, as host. |
| MultiSelect needed | For a **duplicate** token, yes, or a Runtime equivalent: re-enabling the greyed card through the game's per-card helper `0x18D1440`, a UI call. A non-duplicate token (any owned selectable stratagem chosen as the token) needs nothing. A Runtime-presented picker card is not feasible: see "A virtual card in the ship loadout picker". |
| A basis for virtual custom stratagems | **Yes, live-verified** for the Precision Strike token and the 120mm carrier: native types only, no hooks, no account or save writes. |

**The vehicle "replace" rule is not a conversion.** Picking an exosuit, FRV or tank while a slot holds the same vehicle
category (StratagemInfo +0x104 bits) sends the pick into **that** slot (`0x146E3F0` → `0x146E5EA`). It is a ship-UI
redirect and offers nothing at mission time.

### The development proof: VirtualSlotProof 0.1.0 (live-verified 2026-10-02)

- `runtime/stratagem_slot_conversion.lua` (development; not public) does the guarded conversion and restore.
- `proof/VirtualSlotProof` converts the second Precision Strike to the 120mm in a solo mission, with no custom
  presentation, code or payload. It reads the HUD's follow-up without writing it.
- **Validated offline:**
  - unit tests;
  - all three mission snapshots: a seeded duplicate token is converted (1 write), the carrier's package is requested
    first, nothing else in the record changes, and the restore is exact;
  - the shipped artifact aboard the ship: nothing written.
- **Live-verified (2026-10-02, solo host;** `schemas/live_evidence.json` session `virtual-slot-2026-10-02`, family
  `stratagem_mission_slot_conversion`**):**
  - ship loadout: two Orbital Precision Strikes, the duplicate selected with Stratagem MultiSelect;
  - in the mission the second entry became the 120mm (type 118 → 136): only the local mission-record slot type was
    written, and the saved loadout stayed untouched;
  - the vanilla HUD refreshed the slot by itself, and it was a normal 120mm slot.
- **Not promoted:** any other token or carrier, a duplicate token without Stratagem MultiSelect, the mission-end
  events' content with a converted slot, multiplayer.

## The custom stratagem in a mission (GasBarrageMissionProof, development)

**The chain:** custom stratagem selector → virtual slot `orbital_gas_barrage` → the saved vanilla token (Orbital
Precision Strike) → mission → mission-time slot conversion → the carrier (Orbital 120mm HE Barrage) → its custom
presentation → the 120mm's own calldown code and payload (unchanged in this first proof).

**What the game stores:** only the Precision Strike token, in the save and the loadout. The Runtime keeps the identity
(`slot N = orbital_gas_barrage`) in its own record (`stratagem_selector.virtual_slots`). That record lives in memory
for the game session and is reconstructed from the saved order.

### The conversion by identity [C]

`stratagem_selector.convert_virtual(id)` builds the exact spec from the Runtime's own record
(`stratagem_selector.conversion_spec`): the loadout slots holding instances of the definition with its token, and the
loadout order they were recorded in (stable ids). It hands that spec to
`stratagem_slot_conversion.convert_virtual`, which reuses the live-proven conversion unchanged:
- **The same write and the same guards.** One guarded transaction writes each entry's 4-byte type, with the record's
  peer id and whole entry block as context, after the carrier's call-in package is resident. The guards are:
  - in a mission, as host, solo;
  - the carrier catalogued, enabled, selectable, owned, with unlimited uses and in no entry;
  - each converted entry holding the token with unlimited uses and no call-in in flight;
  - the pins of the reviewed build.
- **The same aftermath.** The vanilla HUD refreshes each slot from its type change. The game rebuilds the record for
  the ship at the mission end, which discards the conversion; nothing is restored by hand. A finalizer restores before
  the Lua state closes.
- **The identity rule replaces the duplicate rule.**
  - The mission record's loadout entries (non-granted, in order: the save's order) must be **exactly** the recorded
    order, by stable id.
  - Each virtual slot's entry must hold the token.
  - Exactly those entries convert, all in **one** transaction. A natively picked Precision Strike stays.
  - Any difference refuses with nothing written (`IDENTITY_CHANGED`, `NOT_TOKEN`), and no other slot is ever chosen.
  - A single virtual slot needs no duplicate token.
- **Several virtual slots become several carrier entries.** The carrier guard ("in no entry") is checked before the
  write, so a native 120mm still refuses. Two entries of one type coexist in game logic ("Duplicate slots and virtual
  stratagems" above): each keeps its own uses, cooldown and in-flight beacons. The matcher keeps one candidate per
  type and picks the ready one with the most uses. So **the game chooses which converted slot fires**; they are
  interchangeable instances of one definition.
- **The duplicate conversion (`convert`)** is unchanged, with its live-tested wording.


### Presentation [C]

**Only the carrier is re-presented, before the mission.** The Orbital 120mm HE Barrage presents as Orbital Gas Barrage
aboard the ship:
- the masked Gas Barrage icon through the public `presentation_icon` field;
- the name, cased name and description as Runtime text through the development path (`apply_text`), the live-verified
  custom text path, which is not public yet.

This is acceptable because the carrier is not in the player's loadout; it occupies no selected slot. Its type, stable
id, code, payload and cooldown are never written.

**The token (Orbital Precision Strike) is never re-presented.** Every report checks that its row still holds its
reviewed name, cased name, description and icon.

The mission HUD builds the converted slot from the carrier's row when the type changes, so no HUD write or hot-swap is
involved.

**The carrier must not be in the loadout.** While the proof runs, the carrier's own native picker card looks like
Orbital Gas Barrage too. A natively picked 120mm is the carrier itself, so:
- the proof's pre-mission check refuses the test;
- the conversion refuses as well (`CARRIER_IN_RECORD`).

The mission HUD overlay stays disabled. The live test first shows what the converted slot displays through the
presentation alone.

### The 0.1.0 live run and the identity (2026-10-02)

**What happened (user report).**
- **The architecture was not tested.** The Orbital 120mm HE Barrage was in the saved loadout and the mission record,
  and the Runtime's virtual identity was gone before the mission (`virtual slot ... no longer holds its token`,
  `no virtual slot remains`).
- **The conversion correctly refused.** The live evidence records it as not tested (family
  `stratagem_virtual_carrier_conversion`).

**The trace [C].** Both log lines come from `stratagem_selector.track`. It ran on every change of the loadout screen's
record, in any game state, while the screen's UI object existed. Three paths drop the identity:
1. **The virtual slot itself replaced natively.** This is the most likely cause, consistent with both symptoms: picking
   the 120mm's card (presented as Gas Barrage) over the virtual slot. The drop is correct; the slot is no longer the
   token.
2. **A record not filled yet when the screen opened.** 0.1.0 had added a check on `opened`, and an empty or partly
   filled record compared as "every slot changed".
3. **A record the game rewrites at the launch, in a transition or in the mission.** This is not the player's edit.

**The fixes [C].**
- **`track` judges only the player's edit:** the loadout aboard the ship (game state Ship) before it is readied or
  launched. In any other state the identity is left as it is.
- **The panel calls `track` only on a settled record.** Each change restarts a 0.5 s wait, so no frame of a native
  pick, a fill or a rebuild is judged.
- **The `opened` check is removed.** The mission conversion checks the exact recorded order itself
  (`IDENTITY_CHANGED`).
- **A drop now logs what the slot holds and the old and new orders.**

**`tests/test_custom_stratagem_panel.py`** (`VirtualIdentityTests`) keeps the identity through each of these:
- three native picks into other slots, and an in-place native replacement;
- the selector opened and closed on every other slot;
- the screen closed and reopened with its record empty for a few frames;
- a readied and launched loadout rewritten;
- the mission rewriting the screen's record.

Only the virtual slot replaced by the 120mm drops it, with
`it now holds Orbital 120mm HE Barrage`.

### The proof (0.2.0)

`proof/GasBarrageMissionProof` (0.2.0, `0.2.0 CARRIER PIPELINE`). It contains:
- the 0.7.0 panel;
- the carrier's presentation;
- a **PRE-MISSION CHECK**, read-only, logged whenever the saved loadout, the virtual slots or a row's look changes, and
  on F9. It reports:
  - the virtual Gas Barrage slots;
  - the saved tokens;
  - `120mm present in saved loadout`;
  - whether the saved order matches the identity;
  - the Precision Strike row native;
  - the 120mm's look;
  - then `READY`, or `NOT READY`/`TEST REFUSED` with the reasons.
- **At mission start:** the test is refused (nothing converted) with the 120mm in the saved loadout or the record.
  Otherwise the virtual slots convert once the HUD list is filled (+5 s).
- **Reports:**
  - `IDENTITY` (the Runtime's record still naming the converted slot);
  - `PRESENTATION`;
  - `HUD`;
  - `CALL-IN`;
  - `MISSION END`.

**Validated offline:**
- **`tests/test_stratagem_slot_conversion.py`:** the identity conversion's own cases (exact slots, one transaction, a
  native Precision Strike untouched, refusals writing nothing, the mission-end rebuild), with the duplicate
  conversion's tests unchanged.
- **`tests/test_gas_barrage_mission_proof.py`:** the proof's own addon end to end.
  - The first live test: [GAS, three native stratagems], with the selector opened and closed on the other slots and
    the screen closed.
  - The pre-mission check `READY` with `120mm present in saved loadout = false`.
  - The carrier's package requested and loaded through the asset gate (simulated loader).
  - Only loadout slot 0 converted (1 write), every other entry unchanged, `IDENTITY ... kept`.
  - The HUD report and a call-in.
  - The mission-end rebuild removing the conversion, and the identity reconstructed.
  - The Precision Strike row byte-identical throughout; the 120mm row changed only in its presentation members.
  - A native Precision Strike next to the virtual one staying a Precision Strike.
  - The 120mm in the loadout refusing the test, with nothing written.
  - A changed loadout refused.
- **`scripts/validate_stratagem_calldown_snapshot.py`, on every retained snapshot:**
  - on the three mission snapshots, a seeded virtual Precision Strike and a seeded native one: the identity
    conversion runs first and requests and loads the 120mm's package itself, converts only the virtual entry (1
    write) and restores exactly, with the native one staying a Precision Strike;
  - a different recorded order is refused with nothing written;
  - aboard the ship and at the mission end it refuses.
- **The built runtime ZIP** (`proof-gas-barrage-mission`, on the ship snapshot):
  - the carrier's presentation writes only (6, the 120mm's presentation members);
  - the Precision Strike row byte-identical;
  - the pre-mission check against the snapshot's saved loadout (no 120mm, no virtual slot: not ready);
  - the identity conversion refused, with nothing written;
  - the toggle restoring the 120mm.

**Not proven:** everything in a live mission:
- the conversion from the selector's saved loadout;
- the converted slot's look;
- the 120mm call-in from a converted slot;
- the mission-end rebuild;
- the reconstruction after a mission.

### Carrier identity and gameplay donor (0.3.0; research 2026-10-02, offline)

**The 0.2.0 live test.** The 120mm is the wrong carrier identity. Its presentation is row-global, so the native 120mm
card itself became "Orbital Gas Barrage" while the proof ran (live evidence: an observation on
`stratagem_virtual_carrier_conversion`).

**The architecture now separates the two:**
- **The carrier identity** is a different vanilla type. It is not otherwise in the mission, and it alone carries the
  custom presentation.
- **The gameplay logic** is the donor's (the 120mm, later the gas payload), redirected onto the carrier. The carrier
  keeps its own type and stable id.

**The invariant:** the game believes the slot is vanilla stratagem X, while the Runtime makes X present and behave as
the custom stratagem.

**The carrier catalogue [O, C].** 62 types pass the hard filters on all seven snapshots: owned, enabled, selectable,
unlimited uses (row +0x50 = -1), and a known call-in package. Excluded:
- Eagles (row max uses 1–4, plus rearm), the Orbital Laser and the exosuits, which have limited uses;
- mission and objective types, which are not selectable;
- unowned types;
- vehicles, backpacks, support weapons, sentries, emplacements and mines, which are hellpod or equipment deliveries.

The safe catalogue, best first, is the orbital bombardments with the 120mm's call-in machinery (the components
LoadoutPackage, OrbitalShip, StratagemFiresupport and Bombardment):

| Rank | Carrier | Stable id | Type | Why |
| --- | --- | --- | --- | --- |
| 1 | Orbital Napalm Barrage | 2902516083 | 106 | Closest to the 120mm (6 bombardment words differ, the same spawn time, call-in type and firesupport hash); its shells used by no other stratagem; in no snapshot loadout |
| 2 | Orbital 380mm HE Barrage | 3108516875 | 125 | 6 words differ; its shell rows shared with Walking Barrage |
| 3 | Orbital Walking Barrage | 3279813377 | 21 | 7 words differ; shared shells; often in the player's loadout |
| 4 | Orbital Airburst Strike | 1560416221 | 83 | A strike (one shell entry), not a barrage |
| 5 | Orbital Gatling Barrage | 2084654169 | 4 | 17 words differ |

None of their packages is resident on the ship or in the snapshot missions [O]. The conversion loads the carrier's
package first. The scan of the 131 functions that read the stratagem table finds per-type compares only for Reinforce
(124) and UploadDiscovery (128) [C]. The Gas Strike would match the theme but is often in the loadout.

**The choice [C].** A definition lists candidate carriers (`mission = {carriers = {...}}`).
`stratagem_selector.choose_carrier` (`stratagem_slot_conversion.choose_carrier`, read-only) takes the first one that:
- passes every carrier guard (catalogued and not the token; enabled, selectable, owned; token and carrier unlimited;
  a known package);
- is not in the loadout.

The conversion then takes that carrier. `tests/test_stratagem_slot_conversion.py` (`CarrierChoiceTests`) covers the
choice and its refusals. On the three mission snapshots, `scripts/validate_stratagem_calldown_snapshot.py` checks that:
- the choice is the Orbital Napalm Barrage;
- its package is requested and loaded;
- only the virtual entry becomes type 106;
- the native Precision Strike stays;
- the restore is exact.

**Presentation timing: applying it in the mission [C, research].** Applying the carrier's presentation at mission start,
before the conversion, and restoring it aboard the ship would avoid the ship UI change. It is equivalent for the
converted slot:
- **The icon is read only on a type change.** The HUD slot icon (`0x1839FD0`, per frame per slot from `0x18375F6`)
  re-reads row +0xB0 (`0x183A1E5`, `0x183A2C4`) only when the record entry's type differs from the slot's remembered
  type (+0x14C8; `0x183A05B`).
- **The name is read on rebuild events.** The slot name (`0x66D4B0` → +0x28) is read on a type or scramble change
  (`0x1836E66`–`0x1836E75`, `0x1837046`), when the slot leaves state 7/8 (`0x1838D49`) and on the glitch timer
  (`0x1837DDC`). It is copied into the slot.
- **The description has no in-mission reader.**
- **Nothing captures a non-loadout type's look at mission load.** The HUD build resets each slot's remembered type
  (`0x1839584`). The snapshots hold presentation copies only for loadout types.

Three conditions apply:
1. **Apply everything before the conversion write**, and wait for the result: the text table registered and resolving,
   the icon written. A missing text resolves to an empty string that stays baked into the slot.
2. **Keep it applied for the whole mission.** The game re-reads the row on rebuild events.
3. **Restore only after the mission HUD is torn down**, aboard the ship.

Text registration and the icon in a mission are not live-proven. This proof keeps the proven ship-side timing. The
in-mission timing is the next proof, with the pins above. It is implemented by GasBarragePayloadProof 0.2.1 ("The carrier
presentation lifecycle" below), pending its live test.

**The gameplay donor [C, O; research].** The call-in chain is:

    row payload list (+0x98, read live at delivery) -> the payload entity -> its BombardmentComponentData (192 bytes;
    a per-entity copy, else the shared record by payload hash) -> each shell: the type at +0x40 + idx*4 ->
    SpawnProjectile -> the shell's impact explosion (ProjectileInfo +0x90) -> the explosion's damage row -> statuses

| | 120mm (donor) | Gas Strike | Napalm (carrier) |
| --- | --- | --- | --- |
| Payload entity | 0x2D3BD00B1ED411B1 | 0x05F3C83A91075766 | 0xA16AB4FF66AE6970 |
| Shells (+0x40) | 194, 137, 137 | 197 | 234, 238, 238 |
| Impact explosion | 213 / 176 | 82 (a 15 s gas volume, radius 15) | 63 / 74 |
| Status | none | gas 6 s, gas_confusion 5 s | fire, burning_heavy |

No existing public Runtime field reaches the bombardment record:
- the `orbital.*` fields belong to OrbitalAbility (Laser, Railcannon);
- the record is read-only to the stratagem writes;
- stratagem shells have no reference fields.

The research recommends one new guarded write: **copy the donor's bombardment pattern onto the carrier's own record.**
- **For the Napalm:** 6 words, among them the shell list 194/137/137, plus its cooldown.
- **Its guards:**
  - the carrier's record matches its vanilla bytes outside the written words;
  - the donor's record is re-proven;
  - no per-entity copy exists;
  - the carrier row has no delta lists;
  - it is written before the call-in, never during an active barrage.
- **What it touches:** nothing shared. The record belongs to the carrier alone, and the donor's shells are only
  referenced.
- **Stage 3 (gas):** the same shell list pointed at the Gas Strike's shell (197), which brings its explosion, gas
  volume and statuses.

Writing the carrier's payload hash instead would change the identity the stratagem writes re-prove, and would expose
the donor's payload to the other readers of that list. That is not recommended. Neither stage is in 0.3.0.

### The 0.3.0 live test and carrier discovery (0.4.0)

**The 0.3.0 live test: carrier conversion not tested.** The proof chose from the five-name list above, and every
candidate read `CARRIER_NOT_OWNED`. No carrier was chosen, and the mission correctly refused (live evidence:
`stratagem_virtual_carrier_conversion`, NOT_TESTED).

The snapshots of this machine's account show all five owned under the same rule [O]. 0.3.0 read ownership once, at the
first chance after load, and never again, so the account catalogue was most likely read before it was filled [I].

The user then ruled out any fixed list: **the carrier is discovered from what the current account owns.**

**The discovery [C]** (`stratagem_slot_conversion.discover_carriers`, read-only; `stratagem_selector.discover_carrier`
for a definition with `mission = {discover = true, exclude = {...}}`). Every catalogued stratagem with a row is checked.
A carrier must be:
- catalogued and resolved by stable id;
- not the token, and not an excluded stratagem (the donor);
- selectable, enabled, owned (the availability check's rule, with its evidence: the catalogue state, the parent's,
  or "not in the catalogue range") and with unlimited uses;
- a normal player-facing call-in class (catalogue family and root component); never a mission/objective type, a
  vehicle or exosuit (not proven) or an eagle (limited uses, rearm);
- backed by a known call-in package, a reviewed native presentation and a native code (1–8 directions);
- not in the saved loadout.

The ranking is by class, then by name:
1. orbital bombardments (`BombardmentComponentData`, the donor's machinery);
2. other orbitals;
3. sentries, emplacements and mines;
4. support weapons and backpacks.

**Nothing is trusted until the catalogue shows the token itself as owned** (`ready`). The Precision Strike is a
starter stratagem, and the player has just selected its token.

**On every retained snapshot of this account** (`scripts/validate_stratagem_calldown_snapshot.py`):
- the discovery is ready, with 54–55 eligible carriers;
- it chooses the Orbital 380mm HE Barrage (class 1, not in the saved loadout);
- on the three mission snapshots, only the virtual entry becomes that carrier (type 125) after its package is
  requested and loaded; the native Precision Strike stays, and the restore is exact.

The eligible orbitals on the ship snapshots are the 380mm, Airburst, EMS, Gatling, Napalm and Smoke. The mission
snapshots also list the Gas Strike, Walking Barrage and Railcannon, because the mission loadout differs.

**The proof (0.4.0, `0.4.0 CARRIER DISCOVERY`).**
- **When it discovers.** Only once a virtual Gas Barrage slot exists and the saved loadout is the one it was recorded
  in. It retries while not ready, and again when the saved loadout changes while nothing is eligible.
- **What it logs.** Every candidate (`CARRIER CANDIDATE: ... owned=... selectable=... -> SELECTED / eligible /
  rejected: ...`), then `CARRIER: ... SELECTED` with its own code and the warning not to select it natively.
- **After the choice.** The carrier is fixed for the session, and only it gets the Gas Barrage look, aboard the ship.
- **The pre-mission check** reports the virtual slots, the saved tokens, the carrier, whether the carrier or the
  120mm is in the saved loadout, and the Precision Strike's and the 120mm's rows native.
- **At mission start**, it refuses the test (nothing written) without a carrier, with the carrier in the loadout or
  the record, or with the carrier's look not applied.

**Also fixed: a quick exit after a native pick.** Leaving the loadout screen within the identity's 0.5 s settle used to
drop the pending follow, leaving the recorded order stale. The pending follow is now applied to the last record seen
while the screen was open.

**Validated offline:**
- **`tests/test_stratagem_slot_conversion.py`:** the discovery checks, its readiness, the donor's exclusion, the ranking,
  and the rejections with their evidence.
- **`tests/test_gas_barrage_mission_proof.py`:** the proof end to end.
  - The discovery after the save.
  - The carrier SELECTED and logged.
  - Its look only, with the token's and donor's rows byte-identical.
  - `READY`.
  - Only the virtual slot converted after the carrier's package loaded.
  - The HUD and call-in reports.
  - The mission-end rebuild and the reconstruction.
  - Waiting while the catalogue is not filled.
  - A native Precision Strike staying.
  - The carrier in the loadout refusing the test.
  - No eligible carrier refusing safely.
  - A changed loadout refused.
- **`tests/test_custom_stratagem_panel.py`:** the quick exit.
- **The built runtime ZIP** (`proof-gas-barrage-mission`, on the ship snapshot):
  - the proof idle with no virtual slot (0 writes);
  - the proof's discovery ready and choosing an orbital bombardment outside the saved loadout;
  - the Runtime text applied to that carrier only and restored;
  - the token's and the donor's rows byte-identical.

**Not proven:** the discovery on the live account, the conversion to a discovered carrier, its HUD look, and its own
call-in in a live mission.

### The 0.4.0 live test: the carrier identity is live-proven (2026-10-02)

The user reported 0.4.0 PASSED (runtime 92950C4D, GasBarrageMissionProof 0.4.0 57B16182,
`build/test-artifacts/live-2026-10-02-gas-barrage-mission-0.4.0-CARRIER-IDENTITY-VERIFIED`):

    saved virtual Gas Barrage -> Orbital Precision Strike token -> mission start -> dynamically discovered owned
    carrier (Orbital 380mm HE Barrage) -> the carrier type replaced ONLY the virtual slot -> the carrier's own
    presentation showed Gas Barrage -> its own package loaded and its own normal call-in executed

The Orbital Precision Strike and the 120mm donor stayed native. `stratagem_virtual_carrier_conversion` is live-proven
for that scope. Not promoted: other carriers, the mission-end discard (not separately reported), and multiplayer. The
user fixed this architecture; the remaining work is the carrier's gameplay logic, staged:
- **A.** the carrier and a custom calldown code, with its normal payload;
- **B.** + the 120mm's bombardment pattern with the 120mm's shells;
- **C.** + the Orbital Gas Strike's shell;
- **D.** the final presentation, code and payload.

Each stage has its own guarded validation. The carrier keeps its own type and stable id. Donor rows and records
(Precision Strike, 120mm, Gas Strike) and anything shared are never written; the carrier is only redirected to them.

### Payload stage A: the custom calldown code (0.5.0)

**The code: Up Up Down Down, through the public field.** One `hd2.ensure` with
`hd2.fields.stratagem.calldown_code` on the discovered carrier only.
- **Read first.** The carrier's native code is read from its row and must equal the reviewed native code (the field's
  `expect`).
- **Restored afterwards.** The ensure's toggle off restores it; the Runtime restores it when the Lua state closes.
- **Never written:** the token's and the donor's codes. Every report checks them native (`code native = true`).

**How the game matches a code [C] (research 2026-10-02, `strat/pay/C`; static, not live-proven).**
- **The loop.** The call-in update `0xa8ec20` takes arrows only while nothing is selected (`0xa8ee89`). `0xa900d0`
  appends each arrow to one shared input buffer (up to 16) and calls the matcher `0x66d8c0` for every arrow.
- **The matcher** walks the local record's entries in order on every arrow, from scratch (there is no per-slot
  progress), and keeps the entries:
  - whose (scrambler-applied) code agrees with every arrow so far;
  - that pass the availability checks (`0x66d200`: cooldown, a pending ball and others; `0x66c880`: uses left).
- **The selection.** It drops the candidates whose length differs from the arrows entered (`0x66dcf0`-`0x66de1f`,
  swap-removal) and selects the first remaining one (`0x66de32`).
- **What follows:**
  - **A shorter code is selected the moment its last arrow is entered.** Arrow input then stops: a longer code that
    starts with it cannot be entered while the shorter one's stratagem is available.
  - **Two equal codes:** the first candidate left after the swap-removal wins, usually but not always the earlier slot.
  - So an equal code is ambiguous, a code that is the start of another makes that other uncallable, and a code that
    extends another is never reached.
- **A correction to the calldown pins.** The pin labelled "calldown matcher" (`0x598074`, in `0x597fc0`) is the
  completion handler of another component (`0x5970d0`, one code per entity). Its compare at `0x598091` tests "the next
  direction is 0" (code complete), not the input direction. It is still a valid reader of +0x40/+0x48, so the guard
  stands; the label overstates it.

**Up Up Down Down on this build [O]** (all 150 rows, all seven snapshots):
- no row's code equals it, and none is its start;
- three rows start with it, all mission-only (not selectable):
  - 71 DropoffCargoContainer (UUDDRD) and 102 MobileCommsRelay (UUDDRRD), granted by mission objective ids;
  - 123 CallInDestroyer (UUDDLRLR), in the mission preset of category-8 missions.

These are added when the record is built at mission start (`0x1467790` from the loadout screen's exit, `0xb4eec0`,
`0x5dbcc0` objectives, `0x6ae1f0` presets) [C]. No path adding them mid-mission was found [U]; a host sync replaces the
whole record [I]. They are in none of the snapshots' records. With the user's test loadout and the four mission
snapshots' granted entries, Up Up Down Down relates to nothing. Every 4-arrow code with no relation to any native row
is listed in the research (158 codes; Up Up Up Down, for example).

**The guards in the proof:**
1. **At registration:** any relation (equal, start, extension) with a stratagem a player can select refuses the code
   (no acknowledgement is given). Relations with mission-only stratagems are listed and guarded.
2. **Aboard the ship:** a saved stratagem whose code relates refuses the test (`NOT READY`).
3. **At mission start, before the conversion:** a related entry anywhere in the mission record (granted ones included,
   live row codes) refuses the test. Nothing is converted, so the objective stays callable.
4. **After the conversion:** the record is watched. A related entry appearing returns the virtual slot to its token
   through the conversion's own guarded restore (1 write; retried while a call-in is in flight).

**The converted slot's arrows.** The HUD rebuilds a slot from the row when its record entry's type changes. The carrier
row already holds the code before the conversion, so the rebuilt slot should draw it with no Runtime HUD write. The
proof reads the drawn arrows (`stratagem_hud.locate`, read-only) and reports them.

**Validated offline:**
- **`tests/test_gas_barrage_mission_proof.py`:**
  - the code checked, applied to the carrier only (its native code read first) and restored by the toggle (2 writes,
    pointer first);
  - the token's and the donor's rows byte-identical throughout;
  - the HUD drawing Up Up Down Down after the conversion;
  - the call-in;
  - refusals: a saved stratagem related to the code; a mission-granted one; an equal native code; a selectable
    related one;
  - a related entry appearing after the conversion returning the slot to its token (1 write).
- **`tests/test_stratagem_calldown_code.py`:** `calldown_codes.relation` and `native_relations`.
- **`scripts/validate_stratagem_calldown_snapshot.py`,** on all seven snapshots:
  - the discovered carrier (the 380mm) gets the code through the production write path: 2 writes, only its
    +0x40..+0x4C changed;
  - the token's and the donor's codes stay native, and no record entry relates to the code;
  - on the mission snapshots, the converted entry calls in with Up Up Down Down;
  - the restore is exact.
- **The built runtime ZIP** (`proof-gas-barrage-mission`, ship snapshot), from the archive:
  - the code check on the real rows: the three related stratagems are not selectable;
  - the public ensure on the discovered carrier: 2 writes, nothing else in its row;
  - the restore is exact (2 writes).

**Live-proven (0.5.0, 2026-10-02; below):** the code in a live mission (the matcher, the HUD arrows, the carrier's call-in
with the new code). **Not proven:** the mid-mission return, and a mission that grants one of the three objectives.

### Payload stages B and C: research (2026-10-02, offline; nothing written)

Read-only research on game.dll, all seven retained snapshots and the installed game data (scratch: `strat/pay/A`
bombardment record, `strat/pay/B` gas chain; each has a `findings.json`). The live carrier is the Orbital 380mm HE
Barrage (stable id 3108516875, type 125 on this build). No field is named beyond what its readers prove.

**The data flow [C]:**
1. Delivery `0x6abdb0` spawns the payload through `0xfd9710`, which first collects any active variant deltas for the
   payload hash (`0x12e5590`).
2. Creation `0x8547e0` stores the shells per salvo, the salvo count, the target, the angle and a seed, and sends those
   five over the network. The record itself is not networked.
3. Barrage start `0x8518f0` sets up the per-barrage state and counts the shell list.
4. The per-frame update `0x852170` re-reads the record (`0x5043c0`) for every active barrage and fires each shell
   through `0x13a9830`.

**1–2. The BombardmentComponentData record (192 bytes), the carrier's and the 120mm's [C, O].** The 380mm and the
120mm share one layout. All 23 records and the 44-slot index are byte-identical on all seven snapshots.

| Offset | Type | What the code does with it | 120mm | 380mm |
| --- | --- | --- | --- | --- |
| +0x00 | f32 | Delay before the first shell when the first salvo starts at once (`0x8518f0`); also in the duration estimates | 0 | 0 |
| +0x04 | u32 | Shells per salvo, read at creation (`0x8547e0`), after upgrade-tag modifiers (`0xB6C2D0`); networked | 3 | 3 |
| +0x08, +0x0C | f32 | Delay to the next shell = +0x08 + (2r-1) x +0x0C (`0x852170`) | 0.75, 0 | **1.5**, 0 |
| +0x10, +0x14 | f32 | A random walk of the aim point for every shell after the first in a salvo | 0, 0 | 0, 0 |
| +0x18 | u32 | Salvo count, read at creation after upgrade tags; networked | 5 | 5 |
| +0x1C, +0x20 | f32 | Delay between salvos = +0x1C + (2r-1) x +0x20 | 2, 0 | **3**, 0 |
| +0x24 | f32 | Per-shell square scatter half-width (`0x853bf0`, times a per-entity multiplier) | 27 | **36** |
| +0x28 | f32 | Scatter of the salvo centre from salvo 2 on | 0 | 0 |
| +0x2C..+0x38 | f32 | The shell origin's distance and a direction offset | same | same |
| +0x3C | u8 | Origin and direction from `0xA0AE00` / `0x13B2490` | 1 | 1 |
| +0x40..+0x5C | u32[8] | **The shell list** (ProjectileInfo types) | **194, 137, 137** | **80, 266, 266** |
| +0x60 | f32 | Drift speed of the barrage centre (the Walking Barrage's 3) | 0 | 0 |
| +0x68..+0xBC | mixed | Optional engine objects, angle and grid offsets, fire keys, per-shell audio overrides (non-zero only on the Gatling) | same | same |

Not found to be read: +0x64 and +0x9C [U].

**3. What differs (380mm -> 120mm): exactly 6 words [O].** +0x08 1.5 -> 0.75; +0x1C 3 -> 2; +0x24 36 -> 27; +0x40,
+0x44, +0x48: 80, 266, 266 -> 194, 137, 137. Outside the record:
- **Already equal:** the upgrade tags (the same 8, so the same shell and salvo counts under upgrades), row +0x3C (5),
  +0x104, +0x58/+0x5C/+0x74, and OrbitalShip.
- **Left alone:**
  - row +0x54 (6 against 5), the base of the call-in ETA (`0x879900`): it moves when the barrage begins, not its
    pattern;
  - the cooldown (+0x68);
  - StratagemFiresupport (`0xF33924F9` against `0x2A1A029C`), only sent to listeners (`0x6b03f0`), effect [U];
  - the LoadoutPackage (the carrier's own).

**4. Ownership [C, O].**
- **The lookup:** `0x5043c0` returns a per-entity private copy (`[0x3326ce8]+0x70`, copy at +0xB0) if one exists, else
  the shared record by payload hash (`0x503dc0`: hash mod 44, linear probe).
- **One owner per record.** Each record has exactly one index entry:
  - record #9 belongs only to payload `0xEF66B417EDC3B1D6` (row 125, the 380mm);
  - #18 only to `0x2D3BD00B1ED411B1` (row 136, the 120mm).

  A full memory scan of a ship and a mission snapshot finds the 380mm's hash only in its component indices, row 125's
  payload list and two variant groups. Nothing points to a single record.
- **Private copies** are made only when a variant delta applies to one spawned entity (`0x5740b0` -> `0x856610`). 11
  deltas target bombardment records (2 for the 380mm, 1 for the 120mm). None is active, and no private copy or active
  barrage exists, in any snapshot.
- **So:** the 380mm's record is used by no other stratagem, and the 120mm's record belongs to the 120mm alone. But a
  shared record is **per-type global**: every instance of that payload reads it, another player's real 380mm in the
  same session included. Writing it is carrier-exclusive only in solo, with no instance alive and no peer holding the
  carrier type.

**5. The shell list [C].**
- **Layout:** 8 u32 entries at +0x40..+0x5C. Barrage start counts the non-zero entries (not the leading run) and fixes
  that count for the barrage.
- **Cycling:** each shell uses `+0x40 + idx*4`, read live, then idx = (idx+1) mod count (`0x852591`). idx resets to 0
  every salvo (`0x853946`), so the 120mm fires 194, 137, 137 in each salvo.
- **Zero entries:** a zero inside the counted range fires the empty default row (`0x37C7560`) and drops the entries
  after it. An all-zero list divides by zero (`0x85259D`): a crash.
- **Changes during a barrage:** a non-zero swap takes effect on the next shell; a shrink fires empty rows; a growth is
  ignored until the next barrage.
- **The +0xF0 bit 12 branch:** a shell with ProjectileInfo +0xF0 bit 12 makes barrage start create a "bombardment
  attack" object. It is clear on 80, 266, 194, 137 and 197. The Gatling's 77 has it, which corrects the earlier note.

**6. The 120mm's shells [O].** 194 (impact explosion 213) and 137 (impact explosion 176). Both hit for direct damage 262
(3500) and explode with damage 445 (1200), with no shrapnel and no lingering volume. No other row uses 262, 213, 176 or
445; two inactive variant deltas name them.

**7–8. The Orbital Gas Strike's shell and its chain [C, O].** The Gas Strike's record (#10) holds one shell: **197**.

    carrier record +0x40[idx] = 197                     0x852596 (record from 0x5043c0)
     -> ProjectileInfo 197                              0x8525BA; SpawnProjectile 0x13A9830 (0x852E14)
          +0x3C = 261: direct hit 300, no status
          +0x90 = 82: impact explosion                  on impact 0x13AD7FD -> RequestExplosion 0x13C0A80
     -> ExplosionInfo 82 (radii 1 / 15 / 20)           processed in 0x13C0D10
          +0x04 = 447 -> the damage pass 0x13C29E0: gas x100 and gas_confusion x100, ONCE at detonation
          +0x64 = 16 ("Gas"), +0x68 = 15 s -> 0x13CD320 creates a status effect volume (a record, not an entity)
     -> volume template 16: gas x3.0, gas_confusion x3.0 PER TICK for 15 s, falloff-weighted
          (0x6963E0 -> 0x13CF3E0 / 0x13CE680 -> 0x696820 -> 0x699E40); it expires by itself (0x13CC050)
     -> status gas (6 s, tick damage 532) and gas_confusion (5 s)

- **The gas behaviour is the single reference record +0x40.. = 197.** None of the start, per-shell, spawn, explosion,
  volume or listener functions reads the StratagemInfo table. Their inputs are the shell's row, the carrier's record
  and runtime entity ids.
- **What the Gas Strike's own record adds is pattern only:** 1 x 1 shell, +-1 m, 0.35 s. Its "+16, +20, +40 = 1"
  words are an unused random walk and the salvo-centre scatter.
- **Assets.** Shell 197's spawn effect, explosion 82's particles and the gas sound bank are in the Gas Strike's
  package `packages/generated/loadout/orbital_gas` (0x6369816737A36A40). The shell unit is in
  `packages/content/effects_mission`, resident in every mission snapshot. The rows themselves are always present.
  Without the package the gas gameplay should still work, with visuals and sound lost [I].
  `core/assets.dependency_for_stratagem(3193297673)` already loads it.

**9. The Gas Strike shell in the carrier's list, no donor written: yes [C].**
- **What is written:** only the carrier's record words. 197, 82, 447, template 16 and the two statuses are referenced,
  never written.
- **Template 16 and the statuses are shared** (gas mines, the gas mortar, the gas grenade, the Eagle Gas Strike, the
  Speargun and others): another reason never to write them.
- **Nothing assumes a strike.** A strike is a 1 x 1 barrage in the same code, and no shell-specific branch fires for
  197.
- **With the 120mm's pattern:** [197, 197, 197] gives 3 x 5 = 15 gas shells with scatter 27, so 15 overlapping 15 s
  clouds. Overlapping clouds stack (`0x13CF203`).
- **Source and credit:** the carrier's bombardment entity, so friendly fire and credit behave as vanilla gas, with
  the carrier as source [I].
- **Modifiers:** the ship upgrades and spread multipliers come from the carrier.

**10. The guards a carrier-local bombardment write needs.**
1. **The build:** the fingerprint and the component framing (the header, 44 index slots, 23 records, stride 192).
2. **The carrier's identity:** `find_root`, the unique index entry -> its record, one owner.
3. **No other row** (types 1–149) lists the carrier's payload hash.
4. **The donors re-proven:** the 120mm's record (#18) and shells 194/137, then the Gas Strike's record (#10) and shell
   197, against their reviewed bytes.
5. **The carrier's record** equals its vanilla bytes, or exactly the bytes this operation wrote; anything else is a
   conflict.
6. **The shell list stays packed:** at least one and at most 8 entries, no gap, valid after every single write (with
   the same count, an in-place swap).
7. **No private copy and no active instance:** the per-entity manager and the barrage manager.
8. **No active variant group** names the carrier's payload hash.
9. **Solo host, and no participant's record holds the carrier type** (the record is per-type global).
10. **The packages resident:** the 120mm's for stage B, the Gas Strike's for stage C.
11. **Timing:** written after the conversion, before the carrier's first call-in. Restored after the mission with no
    instance alive, and only if the bytes are still the ones written.

**What the Runtime would have to learn:**
- `validate_graph` (`domains/stratagem_writes.lua`) must accept the operation-owned list next to the reviewed root
  projectiles, or every later carrier write fails "bombardment projectile list changed".
- While the redirect is applied, attack writes on the carrier are refused: its own shells 80/266 are no longer fired
  and are shared with the Walking Barrage.
- The entity catalogue needs new reads of the per-entity manager (`[0x3326ce8]`) and the variant groups
  (`[0x347cdd0]`).

**Which carriers can take the 120mm's pattern [C].** The bombardment code never branches on the stratagem type, so the
record alone sets the pattern:

| Carrier | Verdict |
| --- | --- |
| Orbital 380mm HE Barrage | Yes: 6 words; the best parity (the same upgrade tags and row branches as the 120mm) |
| Orbital Napalm Barrage | Yes: 6 words; the same salvo-upgrade tag, other tags differ |
| Orbital Walking Barrage | Yes: 7 words (+0x60 drift set to 0) |
| Orbital Gatling Barrage | Yes by code, but 17 words, including its extra fire keys and audio overrides |
| Airburst, Smoke, EMS Strike | The record path works, but row +0x3C is 1 (another delivery and ETA branch) and they have no salvo-upgrade tag: not the 120mm's behaviour |
| Gas Strike, Precision Strike | Donor and token: never written |
| Railcannon, Laser | No BombardmentComponentData: excluded |

So the pattern is portable within the BombardmentComponentData barrages; strikes differ through their row. Stage B
turns this into the payload-compatible carrier filter (below).

**Not yet answered [U]:**
- The variant groups' purpose and gate.
- The source of the scatter multiplier.
- The +0xF0 bit 3 consumer (set on 197 and the smoke and EMS shells).
- The 120mm package's exact contents. The bundle files are not parsed; it is assumed needed [I] and already loadable.
- How remote clients would see it: per-shell words are read locally, so clients would mix the host's counts with their
  own record. Solo only.

### The 0.5.0 live test: the custom calldown is live-proven (2026-10-02)

The user reported 0.5.0 PASSED (runtime A2922CBF, GasBarrageMissionProof 0.5.0 01CAA5DB,
`build/test-artifacts/live-2026-10-02-gas-barrage-mission-0.5.0-CUSTOM-CALLDOWN-VERIFIED`):
- **The carrier** received Up Up Down Down through the public field; its native code was replaced only on the carrier.
- **The HUD** showed the custom code naturally (the type-change rebuild; no Runtime HUD write).
- **The call-in:** the carrier's own native call-in executed.
- **The mission:** only the virtual slot converted, the carrier package loaded, and the carrier kept its own type and
  stable id. Native Precision Strike slots stayed untouched; the Precision Strike and the 120mm stayed vanilla.

Identity, presentation, calldown and mission conversion are fixed now. The next work is the carrier's gameplay logic.

### Payload stage B: the 120mm pattern on the carrier (GasBarragePayloadProof 0.1.0, development)

**The goal:** carrier identity + the custom calldown + a CARRIER-LOCAL 120mm bombardment pattern, with the 120mm's own
shells (194, 137, 137). It is deliberately not gas: stage C (the Gas Strike's shell 197) comes only after B passes.

**Stage A at run time: the actual carrier's record [C].** The research above covers this account's snapshots. The
selected carrier depends on the account, so the proof reports it read-only (`PAYLOAD RECORD`, aboard the ship, again
after the write and after the restore), through `runtime/bombardment_payload.lua` `inspect`:
- **where it is:** its address by the game's own lookup (`0x503DC0`), its record index and index slot against the
  reviewed ones, and its 192-byte size;
- **who owns it:** the index owners and the rows listing its payload;
- **what it holds:**
  - the shell list at +0x40 and its count;
  - shells per salvo and salvos;
  - the delays between shells and between salvos, the scatter, the aim walk, the salvo-centre scatter and the drift;
  - every word that differs from the 120mm's, with its role.

`research/bombardment-payload-F5FEE03DCFDB.json` (`scripts/research_bombardment_payload.py`, 57 pins) holds every
reviewed orbital bombardment record. They are identical on all seven snapshots, each owned by one index slot and by its
own row only, with no instance, private copy or active variant. `domains/bombardment_payload.lua` is generated from it
(`scripts/generate_bombardment_payload.py`).

**The payload-compatible carrier filter.** Once a payload is involved, the generic carrier filter is not enough: a
definition with `payload = {donor = 'Orbital 120mm HE Barrage'}` makes the discovery
(`stratagem_slot_conversion.discover_carriers` with `opts.payload`) accept only carriers that:
- have a reviewed BombardmentComponentData record;
- have the donor's row delivery value (+0x3C);
- differ from the donor's record only in the code-proven pattern words.

These are ranked by the number of words the pattern changes, then by name. The definition also lets the selector's
conversion spec refuse an incompatible discovered carrier.

| Carrier (this build) | Payload-compatible | Words written |
| --- | --- | --- |
| Orbital 380mm HE Barrage | yes | 6: +0x08 1.5 -> 0.75, +0x1C 3 -> 2, +0x24 36 -> 27, shells 80/266/266 -> 194/137/137 |
| Orbital Napalm Barrage | yes | 6: +0x04 5 -> 3, +0x08 0.5 -> 0.75, +0x24 25 -> 27, shells 234/238/238 -> 194/137/137 |
| Orbital Walking Barrage | yes | 7: the 380mm's six and +0x60 drift 3 -> 0 |
| Orbital Gatling Barrage | no | its fire keys and audio overrides (+0x94..+0xBC) differ outside the pattern |
| Airburst, EMS, Smoke, Precision, Gas Strike | no | strikes: row +0x3C is 1, the donor's 5 |
| Sentries, mines, backpacks, support weapons | no | no BombardmentComponentData record |

On this account the live 0.4.0 carrier, the 380mm, is the first compatible one. A strike such as the Orbital Airburst
Strike passes the generic filter but never this one.

**The write [C]** (`runtime/bombardment_payload.lua` `apply`; `stratagem_selector.apply_payload`). Right after the
mission-time conversion and before the carrier's first call-in, one guarded transaction writes only the differing words
onto the carrier's own record:
- each word's exact vanilla bytes are the expectation, and the whole record is the context;
- the shell list stays packed after every single write (no gap, at least one entry).

Every guard is re-checked in the tick of the write; any failure writes nothing:
- **the build:** game.dll as researched, every pinned reader;
- **the pair:** the carrier payload-compatible with the 120mm; the 120mm's record exactly vanilla and its shells
  (194, 137) their reviewed ProjectileInfo rows;
- **the session:** a mission, the host, solo (one stratagem record);
- **after the conversion:** the carrier is the conversion's current carrier, and has not been called since: each
  converted entry's cooldown end is exactly the value the conversion recorded, not above the game clock, and has no
  call-in in flight (0.1.1; see below why it is not "cooldown end 0");
- **ownership:** the framing as reviewed, the reviewed slot and record, one index owner, no StratagemInfo row but the
  carrier's listing its payload, and the carrier row's payloads its catalogued ones;
- **the bytes:** the carrier's record exactly vanilla;
- **no barrage:**
  - no instance of the carrier's payload (the manager's handles);
  - no barrage at all while writing (waited for, then refused);
  - no active variant naming the carrier's payload (it would give a spawned carrier a private copy);
- **assets:** the 120mm's call-in package resident (loaded first through the Runtime's loader).

The entity region is read-only memory. The transaction opens the page, writes, verifies, and restores its protection.

**The restore and the lifecycle [C].** The records are static data, identical aboard the ship and in a mission; a
barrage instance lives only in the mission. So:
- **At the mission end, aboard the ship,** the proof restores the record. The restore runs only:
  - from exactly the written bytes (another writer's bytes are refused, `CONFLICT`, and reported);
  - with no instance of the carrier's payload (retried while one runs).

  It then verifies the whole record against its vanilla bytes (`exact`).
- **Mid-mission:** when the virtual slot returns to its token (a code conflict), the record is restored as well.
- **When the Lua state closes:** a finalizer restores the record under the same guards.
- **Never left modified silently:** no retained snapshot holds a bombardment instance aboard the ship or at the
  mission end transition [O], so the restore aboard is expected to be reachable. Any case where it would not be safe (a
  conflict, an instance) is refused, logged and retried, never forced.

Solo only: the record is per payload type, so another player's real carrier would read it too.

**What it never writes:** the 120mm's record, the Gas Strike's record, the Precision Strike, any shell, explosion or
status row, the StratagemInfo registry, the account catalogue and the save.

**Validated offline:**
- **`tests/test_bombardment_payload.py`:**
  - the research and its domain;
  - the write only after the conversion (refused before, nothing written), exactly the six words, the restore exact;
  - the wrong family and unsupported carriers refused;
  - ownership (a second index owner, another row listing the payload), the exact vanilla fingerprint, the donors'
    records and shell rows, the framing and the pins;
  - solo, host, mission, a call-in in flight, already called;
  - a running barrage of the carrier, another barrage (waited for), an active variant;
  - the donor's package requested and loaded first;
  - the restore refusing another writer's bytes and a running barrage; the Lua close restoring;
  - the definition's donor and the selector;
  - the payload-compatible discovery.
- **`tests/test_gas_barrage_payload_proof.py`:** the proof end to end:
  - the discovery taking only a compatible carrier (the Napalm Barrage in that fixture);
  - its record reported, READY;
  - the conversion, then the 6 writes;
  - the 120mm-style call-in expectation;
  - the restore at the mission end;
  - the pattern toggle off (no write);
  - a running barrage (refused, the mission goes on).
- **`scripts/validate_bombardment_payload_snapshot.py`**, on all seven snapshots:
  - every orbital record found by the game's lookup, one owner, its row only, vanilla; the compatible set;
  - aboard the ship refused;
  - in the mission snapshots:
    - refused before the conversion;
    - the payload discovery choosing the 380mm;
    - the conversion;
    - the wrong family refused;
    - a seeded carrier barrage refusing the write and the restore;
    - the 6 writes only inside the record (the pages opened and restored), the 120mm pattern, the donors vanilla;
    - the restore byte-exact.
- **The built runtime ZIP** (`proof-gas-barrage-payload`):
  - aboard the ship: the module loaded at startup from the archive, the record report, the compatible discovery, the
    write refused, 0 writes;
  - on the mission snapshot (a validation-only seed of a fresh token entry): the conversion, the 120mm package
    requested and loaded, the 6 writes through the read-only pages, the restore byte-exact, the conversion undone
    (14 overlay writes).

**Not proven:** the write, the barrage and the restore in a live mission.

### The stage B 0.1.0 live test and the atomic step (0.1.1)

**The 0.1.0 live test (2026-10-03): the 120mm pattern was not tested.** Runtime A62FCF62, GasBarragePayloadProof 0.1.0
6BFB6071; the artifacts and the live log are in
`build/test-artifacts/live-2026-10-03-gas-barrage-payload-0.1.0-PAYLOAD-REFUSED-NOT-TESTED`.
- **What happened:** the conversion applied (carrier Orbital 380mm HE Barrage). Right after it, before any call-in, the
  payload was refused, `ALREADY_CALLED`, and nothing was written. The carrier then fired its normal 380mm barrage.
  Live evidence: `stratagem_carrier_bombardment_pattern`, NOT_TESTED.
- **The order in the live log:** the conversion; the refusal before any donor-package request (the first check); the
  call-in; and only then `cooldown changed`.
- **The loadout** was [120mm, Orbital Laser, Precision Strike, virtual Gas Barrage]. That is harmless, because the
  donor's record is only read.

**The cause: the guard's evidence [C, O].**
- **The code [C]:** an entry is unavailable while its cooldown end (entry +0x18, u64) is above the game clock
  `[[game+0x3326348]+0x18]` (`0x66D24A`-`0x66D25C`, an unsigned compare). The value is an absolute time.
- **The snapshots [O]:** at mission start every entry holds one shared, non-zero time, 110331400 in all four mission
  snapshots, granted entries that are never called included. A call sets a new value (240661532, 455341259 and others
  later). The record build's own 0 (`0x66F2E0`) does not survive to the mission.
- **So** "cooldown end 0 = never called" refused a fresh slot. The offline validators had hidden it: their validation
  seed zeroed the cooldown end ("a fresh entry"), which made the false premise pass. That seed is gone.

**The guard now (not weakened).**
- **The evidence:** the conversion records each converted entry's cooldown end. The payload refuses `ALREADY_CALLED` if
  that value changed since, or if a call-in of the entry is in flight.
- **Before the conversion:** it refuses `ON_COOLDOWN` if the entry's cooldown end is above the game clock; the token was
  called before the conversion and is still cooling down. The clock reader's four instructions are pinned.
- **Final for the conversion:** a detected call is never retried in that mission, even if the value came back.

Every carrier call changes the cooldown end or is in flight, so every carrier call is still caught. Only a slot that was
never called stops being refused.

**The ordering: the carrier is never callable without its payload.** In 0.1.0 the payload job could still wait for the
donor's package after the conversion, leaving the carrier callable with Up Up Down Down in between.
`stratagem_selector.convert_with_payload` (0.1.1) prepares while the virtual slot is still its token, then writes both
in one tick:
1. **Preparation (yields allowed; the carrier not in the record, so not callable):**
   - both call-in packages resident: the carrier's and the donor's;
   - every payload guard that does not need the conversion (`bombardment_payload.preflight`), with no barrage running
     (waited for).
2. **One tick, no yield:** the conversion (`stratagem_slot_conversion.convert_virtual_body` with `atomic`: a package not
   resident refuses instead of waiting), then the payload (`apply_body` with `atomic`).
3. **A refused payload** undoes the conversion in that same tick (`restore_body`). The slot stays the token.

The proof logs `NOT READY: carrier payload is still being applied (...)` during the preparation, then
`MISSION START: conversion APPLIED`, `PAYLOAD: APPLIED` and `READY TO CALL`, in that order, from one tick.

**Validated offline (0.1.1).** Every test and validator now uses live-like cooldown ends, a shared non-zero time on
every entry. The previously zeroed ones would have hidden the bug.
- **`tests/test_bombardment_payload.py`:**
  - **the live regression:** a non-zero cooldown end on a fresh entry; the payload applies;
  - **a call after the conversion:** `ALREADY_CALLED`, never retried; a token still cooling down is refused
    (`ON_COOLDOWN`);
  - **the requested sequence:** the packages absent; the step pending (`packages`), with the slot still the token, the
    carrier not in the record and nothing written; the packages released; the conversion and the payload in one tick
    (7 writes);
  - **the per-tick watch:** "the carrier in the record means its record holds the pattern", never violated;
  - **the negative control:** the same watch catches 0.1.0's two-step order (at least one tick without the payload);
  - **a payload refused in the conversion's tick:** the conversion undone in that tick, the carrier never seen;
  - **a running barrage:** waited for while the slot is still the token.
- **`tests/test_gas_barrage_payload_proof.py`:** the proof's log order `NOT READY` > `MISSION START: conversion
  APPLIED` > `PAYLOAD: APPLIED` > `READY TO CALL`, the same watch, and a running barrage refused before anything is
  converted.
- **`scripts/validate_bombardment_payload_snapshot.py`** (all seven snapshots), with the snapshot's own non-zero cooldown
  end (110331400):
  - the separate apply applies;
  - the proof's combined step (the proof's definition, the virtual-slot record) writes 7 in one tick;
  - the carrier is never seen without its pattern;
  - the restore is exact.
- **The built runtime ZIP** (`proof-gas-barrage-payload` on a mission snapshot): the combined step from the archive.

**Not proven:** the pattern, the barrage and the restore in a live mission.

### The stage B 0.1.1 live test: the carrier-local 120mm pattern is live-proven (2026-10-03)

The user reported 0.1.1 PASSED (runtime 37D41938, GasBarragePayloadProof 0.1.1 5F7B5646,
`build/test-artifacts/live-2026-10-03-gas-barrage-payload-0.1.1-STAGE-B-VERIFIED`):
- **the write:** the carrier conversion succeeded, and the carrier's own BombardmentComponentData was modified with
  exactly 6 pattern words;
- **the pattern:** the shell list became 194, 137, 137, and the 120mm timing and scatter pattern was applied;
- **the ordering:** `PAYLOAD: APPLIED` came before `READY TO CALL`, and the carrier was never callable without the
  payload;
- **the call-in:** the carrier was called with Up Up Down Down.

`stratagem_carrier_bombardment_pattern` is live-proven. Not promoted:
- the other compatible carriers (the Napalm and the Walking Barrage);
- the mission-end restore (not separately reported; the live log was overwritten before it was copied);
- another shell list;
- multiplayer.

### Payload stage C: the Gas Strike shell on the 120mm pattern (GasBarragePayloadProof 0.2.0, development)

**The goal:** 120mm delivery pattern + the Orbital Gas Strike's shell 197 = Gas Barrage, from existing game systems
only. Stage B and the carrier architecture are unchanged. Only the carrier's own shell list changes:
194, 137, 137 -> 197, 197, 197. The pattern stays the 120mm's: 5 salvos, 3 shells per salvo, 0.75 s between shells,
2 s between salvos, scatter 27.

**The gas chain, re-verified [C, O]** (`scripts/research_bombardment_payload.py`, now 69 pins; group `gasChain`; all
seven snapshots):

    the Gas Strike's record (#10): its one shell is 197
    shell 197 (ProjectileInfo table game+0x37C7670): direct damage 261; impact explosion 82 at +0x90
        SpawnProjectile copies it (0x13AA646); the impact uses the copy (0x13AD7FD) -> RequestExplosion (0x13B0A00)
    explosion 82 (ExplosionInfo table game+0x37CC920, 0x13C0DC0): damage 447 at +4 (0x13C2AF8; DamageInfo table
        game+0x37C60C0, 0x13C2B2B); radii 1 / 15 / 20; volume template 16 at +0x64 for 15 s (+0x68)
        (template table game+0x37C5E90, 0x13C28F0; the status effect volume 0x13CD320, 0x13C2967)
    damage 447: statuses 42 (gas) and 44 (gas_confusion), 100 each, once at each impact
    template 16 ("Gas"): statuses 42 and 44, 3.0 each, every tick while the 15 s, 15 m cloud lasts

- **Identical on all seven snapshots:** every row (explosion 82, damage 447, template 16, statuses 42 and 44), except the
  words holding relocated pointers (explosion +0x28; the statuses' +0x08). Those are masked, and are recorded in
  `domains/bombardment_payload.lua` (`gasChainRows`).
- **The carrier only points at 197.** No chain row is copied or written, and no new gas data is created.

**The write [C]** (`bombardment_payload.apply_body` with `spec.shells = 'Orbital Gas Strike'`; a definition with
`payload = {donor = 'Orbital 120mm HE Barrage', shells = 'Orbital Gas Strike'}`; `stratagem_selector.convert_with_payload`).
- **The plan:** the 120mm's pattern words, not its shells (for the 380mm: +0x08, +0x1C, +0x24), then a shell list of
  the shell donor's shells, in turn, to the pattern donor's shell count: [197, 197, 197].
- **In the conversion's tick:**
  1. the conversion;
  2. the pattern transaction, verified: the record is exactly the vanilla record with the 120mm's pattern;
  3. the shell transaction on that established pattern, verified: packed, exactly 3 entries, all 197, the whole record
     as planned.

  If the shell list is refused, the pattern is rolled back; if the payload fails, the conversion is undone. The
  carrier never becomes callable with a partial or unverified shell list.

**The guards, on top of all of stage B's:**
- the Gas Strike's package is resident before anything is written (the combined step's preparation loads it with the
  carrier's and the 120mm's);
- the Gas Strike's record is exactly vanilla;
- its shell row and its whole chain are exactly as reviewed, masked words excepted;
- only the researched shell donor is accepted (the Gas Strike).

**The restore.** It writes back every word this operation wrote: the shells, then the pattern. It verifies the whole
record against its vanilla bytes, and reports the 120mm's and the Gas Strike's records vanilla. It waits while a
barrage of the carrier runs.

**Validated offline:**
- **`tests/test_bombardment_payload.py`:**
  - the pattern then the shells (offsets 8, 28, 36, then 64, 68, 72), the record `197, 197, 197` on the 120mm pattern,
    and the exact restore;
  - the Gas Strike's record, shell row, explosion, damage, template and status each changed refuses (a masked pointer
    word may differ), and another shell donor is refused;
  - a refused shell list rolls the pattern back;
  - the combined step waits for the Gas Strike's package with the slot still the token, then 7 writes in one tick;
  - a per-tick watch (the carrier in the record means its record holds the stage C payload) is never violated;
  - a refused shell list in the conversion's tick undoes the conversion.
- **`tests/test_gas_barrage_payload_proof.py`:** the proof's order `NOT READY` > conversion > `120mm pattern applied`
  > `Gas Strike shell 197 applied` > `PAYLOAD: APPLIED` > `READY TO CALL`; `shell list = 197, 197, 197`, `shell donor =
  Orbital Gas Strike`, both donors unchanged; the restore `exact vanilla carrier record = true`.
- **`scripts/validate_bombardment_payload_snapshot.py`,** on the three mission snapshots:
  - the stage C combined step writes 7, with shells [197, 197, 197], 3 per salvo, 5 salvos, 0.75 / 2 / 27;
  - the carrier is never seen without its payload;
  - the 120mm, the Gas Strike and the chain are unchanged;
  - the restore is exact.
- **The built runtime ZIP** (`proof-gas-barrage-payload` on a mission snapshot): the same, from the archive.

**Not proven** (before the 0.2.0 live test below): the gas barrage in a live mission (the shells, the clouds, the
statuses, the timing), and the restore.

### The stage C 0.2.0 live test: the Gas Barrage is live-proven, and a lifecycle bug (2026-10-03)

**The result.** The user reported that the Gas Barrage fired (runtime 4A4A67E5, GasBarragePayloadProof 0.2.0 9F5EA0BF,
`build/test-artifacts/live-2026-10-03-gas-barrage-payload-0.2.0-STAGE-C-GAS-BARRAGE-VERIFIED`, with the live log). The
carrier was the Orbital Napalm Barrage:

    virtual Gas Barrage -> Precision Strike save token -> discovered carrier -> Gas Barrage presentation -> UP UP DOWN DOWN
    -> the carrier-local 120mm pattern -> the carrier-local shell list 197, 197, 197 -> the Gas Strike's gas chain

The 120mm and Gas Strike donor records stayed unchanged, and the first mission's restore was exact.
`stratagem_carrier_shell_redirect` is live-proven (`docs/live-evidence.md`).

**The lifecycle bug.** After the mission, back aboard the ship, the native loadout picker still showed the carrier's own
card as Orbital Gas Barrage. The cause: 0.2.0 applied the carrier's Gas Barrage look and code ABOARD THE SHIP, through
public `hd2.ensure` operations, and kept them for the whole session. Only their toggles restore those ensures.

### The carrier presentation lifecycle (GasBarragePayloadProof 0.2.1, development)

**The rule (the user's decision, 2026-10-03):**

| Phase | The carrier |
| --- | --- |
| Ship | NATIVE: its own name, cased name, description, icon and calldown code; its own card in the picker. Selecting the custom Gas Barrage only records the virtual slot (the saved Precision Strike token). |
| Mission start | Verified native, then the Gas Barrage text, icon and code applied and verified, then the packages, the conversion and the payload (unchanged), then `READY TO CALL`. It is never callable without the look and code. |
| Mission | Keeps them for the whole mission (the game re-reads the row on HUD rebuild events). |
| Mission end | The payload is restored as before. |
| Return to the ship | The look and code are restored from the exact bytes captured at mission start, before the loadout UI can use the carrier. |
| The loadout screen opening | The hard safety boundary: any stale look or code is restored before the native loadout UI settles; idempotent on every opening. |

This is the in-mission timing the presentation research described ("Presentation timing: applying it in the mission"
above): apply everything before the conversion and wait for the result; keep it for the whole mission; restore only
after the mission HUD is torn down.

**The module [C]** (`runtime/carrier_presentation.lua`; development, not exported; no SDK field):
- **`apply(spec)`** (a job), at mission start:
  1. it reads the carrier row by its catalogue identity and refuses with `NOT_NATIVE` (nothing written) unless its
     name, cased name, description, icon and calldown code are exactly the reviewed native values;
  2. it captures every byte it could change: the four presentation members, the code pointer and count;
  3. the text: `stratagem_presentation.apply_text` (the guarded text path, which registers the Runtime text table);
  4. the icon and the code: ONE guarded transaction through the stratagem write domain. It uses the same validation,
     capture and plan as the public `presentation_icon` and `calldown_code` fields, so the calldown module records the
     row as it does for the public field;
  5. it verifies what the game reads: the Runtime text resolving, the custom icon, the code, the identity, and every
     member not given still native.

  If any step is refused, everything already written is restored, and nothing stays written.
- **`restore()`** (a job, aboard the ship) and **`restore_now()`** (one tick, for the loadout-screen boundary) write
  back exactly the captured bytes:
  - **the icon and the code:** a guarded transaction whose expected bytes are what this module wrote, built on the
    row's freshly read bytes. If another writer has changed any of those bytes, the part is refused with `CONFLICT`
    and nothing is overwritten (the rule of `core/ownership.lua` and the guarded transaction);
  - **the text:** through the presentation module, and only while its state is the one this module applied (another
    Runtime presentation owning the text is a `CONFLICT`).

  Then every member is verified against its captured bytes (`exact`), against its reviewed native value (`native`), and
  the identity. A refused part stays recorded and is retried later. The state is never deleted to "unlink" the
  override. A second restore is `NOT_APPLIED` and writes nothing. `restore_now` supersedes a restore job still in
  flight; every write is one tick with no yield, so nothing is half written. A finalizer restores before the Lua state
  closes.
- **Never a target:** the token (the Precision Strike), the donors and every other row. The account catalogue, the save,
  the HUD and the native UI are never written.

**The proof (0.2.1) [C]:**
- **Aboard the ship:** the discovery, the code check (read-only) and the payload record are unchanged. The proof writes
  nothing. The `PRE-MISSION CHECK` requires the carrier row native.
- **At mission start:** after every check (carrier chosen, native, not in the saved loadout or the record, no code
  conflict with the record, conversion on):
  - `MISSION START: carrier presentation APPLIED`;
  - then `stratagem_selector.convert_with_payload`, unchanged.

  A refused presentation refuses the test with nothing converted. A refused conversion or payload restores the look and
  code at once (the carrier is not in the record).
- **On the return to the ship:** `RETURN TO SHIP: carrier presentation RESTORED ... exact = true; native = true`. It runs
  as soon as `stratagem_hud.populated` is no longer true, or 5 s after the mission end at the latest, whether or not the
  loadout screen is ever opened. The retained snapshots show the HUD `false` (empty) aboard the ship and `nil` (not set
  up) in the mission-end transition, so this restore normally runs in the transition, before the ship is reachable.
- **At the loadout screen:** `stratagem_selector.watch` sees each opening (and each picker opening on a slot) in the
  frame it happens:
  - a stale look still applied is restored then, logged as `LOADOUT OPEN #n: a STALE carrier presentation was found and
    RESTORED in this frame`;
  - otherwise the opening logs `LOADOUT OPEN #n: ... -> NATIVE: nothing to restore`.
- **The toggles** (look, code) are read at mission start. Aboard the ship the carrier is always native.

**Validated offline:**
- **`tests/test_carrier_presentation.py`** (8 tests):
  - applied exactly, then restored with the whole carrier row byte-identical to its row before, and the token
    (Precision Strike) and the donor byte-identical;
  - repeated restores write nothing, and no Runtime text table stays registered;
  - three apply and restore rounds;
  - a carrier that is not native (icon, code) is refused with nothing written;
  - another writer's icon is never overwritten (the text, still this module's, is restored; the rest restores once the
    bytes are this module's again);
  - text owned by another presentation is not restored;
  - a refused icon (family not loaded) leaves nothing written;
  - `restore_now` supersedes a job in flight;
  - the Lua-state finalizer restores.
- **`tests/test_gas_barrage_payload_proof.py`** (9 tests), the user's cases:
  - aboard the ship the carrier row is byte-identical to its native row;
  - the order `carrier presentation APPLIED` > `NOT READY` > conversion > `PAYLOAD: APPLIED` > `READY TO CALL`;
  - a per-tick watch: the carrier in the record always holds the look and code;
  - kept for the mission;
  - the HUD torn down: `RETURN TO SHIP ... RESTORED`, with the whole row byte-identical, the token byte-identical and
    the text table unregistered;
  - (1) the loadout opened: native, nothing written, the native UI's paint never sees a non-native carrier;
  - (2) opened at once with the HUD not torn down: restored in that frame, before the native UI's paint in that frame;
  - (3) never opened: the deadline restores;
  - (4, 5) reopened and closed repeatedly, and the picker opened on each slot: nothing to restore, nothing written;
  - (6) a native stratagem picked into a slot and back: still native;
  - (7) a second mission: applied, kept, restored again with the payload;
  - another writer's icon is never overwritten, and the next mission is refused (carrier not native);
  - a refused presentation (text registry full) refuses the test with nothing converted;
  - a refused payload restores the look and code at once.
- **The built runtime ZIP** (`scripts/validate_packaged_runtime.py`, scenario `proof-gas-barrage-payload`): the module
  is loaded at startup from the archive.
  - On the ship snapshot, the proof writes nothing; the module's round trip on the real carrier row and real text
    registry restores the whole carrier row and the token row byte-identical (15 overlay writes).
  - On the three mission snapshots: look and code, conversion and payload, payload restore, conversion undone, look and
    code restored; both rows byte-identical (29 overlay writes).

**Not proven (needs the live test):**
- the in-mission text registration and icon on a live HUD, which the conversion's type change makes the HUD build from
  the row;
- the restore timing aboard the live ship;
- what the loadout screen shows after it.

The same-frame boundary is proven only against the fixture's ordering. Whether the live game's native UI builds a widget
earlier in the frame the Runtime first sees the screen open cannot be shown offline. That is why the restore normally
runs in the mission-end transition, long before the loadout can be opened.

### The 0.2.1 live test: the presentation lifecycle is live-proven (2026-10-03)

The user reported 0.2.1 LIVE-PROVEN (runtime 73125D59, GasBarragePayloadProof 0.2.1 2AF452A8,
`build/test-artifacts/live-2026-10-03-gas-barrage-payload-0.2.1-LIFECYCLE-VERIFIED`, with the live log). In the first
mission, everything worked:
- **the carrier:** the Orbital 380mm HE Barrage was discovered, with the Napalm as an eligible fallback;
- **the presentation:** applied in the mission only. The HUD slot drew the Gas Barrage icon and UP UP DOWN DOWN;
- **the payload:** the conversion, the 120mm pattern and the Gas Strike shell 197. The Gas Barrage fired;
- **the restores:** the payload was restored exactly, then the carrier presentation exactly (`RETURN TO SHIP`);
- **the loadout:** the loadout screen and the picker, reopened, showed the native carrier.

Recorded: `stratagem_carrier_presentation_lifecycle` is live-proven, and the 380mm is a live-proven stage C carrier
(`docs/live-evidence.md`). Not promoted:
- the loadout-opening restore of a stale look (not exercised: the ship-side restore ran first);
- a second mission's apply.

**The carrier-selection bug.** Before a second mission in the same session, the user put the cached carrier (the
380mm) in the loadout. The pre-mission check detected it, and the mission start refused the test with nothing written.
That was safe, but not the wanted behaviour: the proof had discovered the carrier once and kept it for the session.

### Carrier revalidation (GasBarragePayloadProof 0.2.2, development)

**The rule (the user's decision, 2026-10-03):** the discovered carrier is a cache, never trusted. It is revalidated
against the CURRENT loadout and state immediately before every mission. If it fails for any reason:

    cached carrier -> validation fails -> CARRIER INVALIDATED: <carrier> reason: <codes> -> the cache discarded
    -> the discovery runs again at once -> CARRIER: <first currently eligible carrier> SELECTED

Refused only when no carrier is eligible; never merely because the previous carrier became invalid. No rediscovery
every frame.

**The validation [C]** (`stratagem_slot_conversion.validate_carrier`, `stratagem_selector.validate_carrier`):
- **The same guards as the discovery.** The per-candidate checks of `discover_carriers` are now one function shared
  by both, so a cached carrier is accepted exactly when the discovery would choose it as eligible.
- **The codes,** each with its reason:

  | Code | Meaning |
  | --- | --- |
  | `in_loadout` | the carrier is in the current loadout |
  | `not_owned` | not owned |
  | `not_selectable` | not selectable |
  | `disabled` | not enabled |
  | `limited_use` | limited uses |
  | `package_unavailable` | no known call-in package |
  | `special_case` | a mission, vehicle, exosuit or eagle type |
  | `no_call_in_class` | no normal call-in class |
  | `no_reviewed_presentation`, `no_native_code` | no reviewed presentation or native code |
  | `not_payload_compatible` | not compatible with the donor's pattern |
  | `donor` | the 120mm donor |
  | `token`, `not_catalogued`, `no_row` | the token itself, not catalogued, no row on this build |

- **Not ready** (the same preconditions as the discovery, e.g. the account catalogue not filled yet): no verdict.

**The proof (0.2.2) [C]:**
- **When it validates:**
  - aboard the ship, whenever the saved loadout changes and every 5 s;
  - at mission start, the final check, against the saved loadout and the mission record (the current loadout in a
    mission). There, a carrier that cannot be validated refuses the test, and if no carrier is eligible after the
    rediscovery, the test is refused.
- **When it does not:** never while the previous carrier's mission presentation or payload is still applied (the
  0.2.1 restores come first).
- **No virtual slot:** a mission with no virtual Gas Barrage slot is refused at once, with no carrier checked,
  discovered or written. A packaged mission-snapshot run caught this before release: a mission-start rediscovery
  without a virtual slot had applied a look that the conversion then refused.
- **Invalid:** the proof logs `CARRIER INVALIDATED`, discards the cache, logs the new `CARRIER CANDIDATE` lines, then
  `CARRIER: <name> SELECTED (...)` and the new carrier's read-only code check.
- **The write guards are unchanged:** the conversion's record guard still refuses a carrier in the mission record, and
  the payload is written only in that conversion's tick. A carrier in the current loadout is therefore never written.
- **Unchanged:** the presentation lifecycle, the 120mm pattern, the Gas Strike shell 197, the custom code, the virtual
  slots, the payload restore and the multiplayer policy.

**Validated offline:**
- **`tests/test_stratagem_slot_conversion.py`:**
  - a valid carrier has the same verdict as the discovery's;
  - each of `in_loadout`, `not_selectable`, `disabled`, `limited_use`, `not_owned`, `donor`, `token` and
    `not_payload_compatible` is reported alone;
  - not ready gives no verdict;
  - read-only.
- **`tests/test_gas_barrage_payload_proof.py`,** with three payload-compatible carriers owned (the 380mm, the Napalm
  and the Walking Barrage):
  - **mission 1:** the loadout without the 380mm: the 380mm carries the Gas Barrage, and both restores are exact;
  - **the 380mm put in the loadout:** `CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout`, the candidate
    scan, then `CARRIER: Orbital Napalm Barrage SELECTED`;
  - **mission 2:** the Napalm carries the Gas Barrage;
  - **the 380mm out, the Napalm in:** the Napalm is invalidated and the 380mm selected again;
  - **mission 3:** the 380mm carries it again;
  - **both in the loadout:** the Walking Barrage carries mission 4;
  - **every tick:** a carrier in the loadout keeps its vanilla bombardment record and its native row. After each
    mission, every carrier, the token and the donor are byte-identical. No test is refused;
  - **the final check:** a carrier that only the mission record shows (saved as the mission starts) is invalidated at
    mission start, and the Napalm carries the Gas Barrage;
  - **no virtual slot:** the mission is refused with no discovery and nothing written;
  - **no carrier eligible:** the test is refused with nothing written. A direct conversion request for a carrier in the
    record is refused with no payload written.
- **The built runtime ZIP** (`proof-gas-barrage-payload`): on each snapshot, the chosen carrier is valid; put in the
  loadout, it is `in_loadout`, and the discovery never chooses it again.

**Not proven (needs the live test):** a second and third mission in one session with the carrier replaced.

### The 0.2.2 live test: carrier revalidation is live-proven (2026-10-03)

**Reported by the user:** the complete Gas Barrage carrier pipeline works. The 380mm was selected first and then put in
the loadout; the Runtime logged `CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout` and selected
Orbital Walking Barrage. The second carrier converted, took the Gas Barrage payload and fired; the payload and the
presentation were restored exactly. The artifacts are in
`build/test-artifacts/live-2026-10-03-gas-barrage-payload-0.2.2-REVALIDATION-VERIFIED` (the session log was not
available locally).

### The fixed cooldown: research (2026-10-03, offline)

`scripts/research_slot_cooldown.py` -> `research/slot-cooldown-F5FEE03DCFDB.json` -> `domains/slot_cooldown.lua`.
Read-only: the game.dll image and the seven retained snapshots; 63 pins, identical in every snapshot.

**1. Where the cooldown is stored [C, O].** In the mission stratagem record ENTRY, the per-slot state the conversion
already keeps with the slot. Each entry holds three u64 game times:

| Entry member | Meaning | Readers |
| --- | --- | --- |
| +0x10 | the activation | HUD inbound bar (`0x1836798`) |
| +0x18 | the cooldown end | availability (`0x66D24A`), the remaining time (`0x6711F5`), the HUD (`0x18368EA`, `0x183A952`), the peer sync |
| +0x20 | the call-in's arrival | HUD inbound time left (`0x18367D4`) |

The game clock is `[[game+0x3326348]+0x18]`, a u64 in **microseconds**: every reader divides the difference by
1000000.0 (`0x66CE52`, `0x183A975`; the constant at game+0x23C7EC0 is pinned).

**2. Entry, definition or player [C].** The entry. The StratagemInfo row's +0x68 (seconds, f32; the public field
`hd2.fields.stratagem.cooldown`) is what the game starts a cooldown FROM, for every use of that type. Its +0x94 (the
cooldown type) is 0 for every orbital; a non-zero type is copied between records by the peer sync (`0x11E83BB`,
`0x11E84A0`).

**3. What the game writes when the carrier is called [O; the writer U].** The activation, the arrival, and
end = arrival + row cooldown x the active modifiers. In the snapshots:
- the Orbital EMS Strike: 75 s -> exactly 64.125 s after its arrival (x 0.855), arriving 4.17 s after its activation;
- the Reinforce: 6 s -> 5.7 s (x 0.95).

**The game counts a cooldown from the call-in's arrival,** not from the call. A never-called entry holds one shared
time from the record's build (110331400 in every mission snapshot), below the clock. The code that writes these at a
call is not in the unprotected .text. The only direct writers of +0x18 there are:
- the record build's zeroes (`0x66F13A`, `0x66F2E0`, `0x66F467`);
- the entry removal's copy;
- the peer sync.

The live proof records the game's write.

**4. The compare [C].** `0x66D200`: the entry is unavailable while `end > clock`, an unsigned u64 compare. Reinforce
(type 0x7C) reads a shared end instead.

**5. Only the local converted slot [C].** Every reader indexes the entry. A write of one entry's +0x18 changes that
slot only: not the token's other entries, not the carrier's row, not another record.

**6. Changing it right after the call [C, O].** Safe once the game has written its own end: every reader only
compares it with the clock. One consequence is for the HUD (`0x1836A30`-`0x1836BF9`, `0x183AA60`, `0x183A97D`-`0x183A9AE`):
- the slot is INBOUND (state 3) while the arrival is ahead, then COOLING (state 4) while the end is above the clock;
- entering state 3 or 4 resets the bar's total (`0x183AB93`, -1); the first frame of the state takes the time left as
  the total, and the bar shows `1 - left / total`;
- so an end written before the arrival is exactly what the cooling bar shows. One written later moves only the time
  left; the bar keeps the native total.

The snapshots confirm the bar rule with real memory. The Eagle Rearm entry's bar total is exactly 102.6 s, its end
minus its activation; the Rocket Pods' bar total is exactly 9.502334 s.

**7. Setting it before the call [C].** Not useful. Above the clock, the entry is unavailable (`0x66D200`): the call
would be refused. At or below the clock, the call's own write replaces it.

**8. Replication [C].** Yes, as a remaining time:
- `rpc_sync_stratagems` (the handler `0x670530`, its log line pinned) carries a peer's record;
- the sender writes each entry's `max(end - clock, 0)` (`0x11E8699`-`0x11E86AD`);
- the receiver rebuilds `end = remaining + its own clock` (`0x11E8376`-`0x11E837F`).

A changed end therefore reaches peers with the next sync. Solo only, like the conversion and the payload.

**9. Restoring at the mission end [C, O].** Nothing to restore:
- the carrier's row (its native cooldown) is never written;
- the record's ends are mission state: the record build writes 0, and every new mission's record holds one shared time
  below the clock.

**10. The existing cooldown API.** Not sufficient:
- `hd2.fields.stratagem.cooldown` is the row's +0x68: every use of the type, the carrier's native cooldown;
- the slot conversion already READS the entry's end (`stratagem_slot_conversion.observe`) and the payload guard the
  clock, but nothing wrote the end.

The new module reuses the conversion's record reader, its identity (record, key, carrier, indices) and the guarded
transaction. It adds no other memory path.

### The fixed cooldown (GasBarrageCooldownProof 0.1.0 and runtime/slot_cooldown.lua, development)

**The goal (the user's, 2026-10-03):** the virtual Gas Barrage always has a 60 s cooldown, whichever carrier was
discovered, never the carrier's or the token's. Only the converted entry is written; never the Precision Strike, the
120mm, the Gas Strike, the carrier's presentation outside the mission, the save or the account.

**The design decision this research raised (open, for the user).** The request was "the end = current game time + 60
s". The game's own rule is "the end = the arrival + the cooldown", and the HUD's cooling bar starts at the arrival:
- **from the call** (`now + 60`): the slot is callable 60 s after the call, but the HUD's cooling phase shows
  `60 - inbound`. That is ~54 s for the 380mm (6 s inbound) and ~57 s for the Walking Barrage (3 s): the carrier's
  inbound time leaks into the displayed cooldown;
- **from the arrival** (`arrival + 60`): the HUD's cooling phase shows 60 s for every carrier, the same rule as every
  vanilla cooldown; the slot is callable 60 s after the barrage arrives.

The proof defaults to **from the arrival** and offers "Count the 60 s from the call" as a Mod Options toggle, so one
live test can show both. The module's `spec.from` is `'arrival'` or `'now'`.

**The module [C]** (`runtime/slot_cooldown.lua`; not exported):
- **When:** `M.arm({definition, seconds, from, carrier})` watches the definition's converted entries every frame. In
  the frame the game starts an entry's cooldown, it writes that end once: one guarded 8-byte transaction, the observed
  end as the exact expectation, the record's peer id and whole entry block as context. A cooldown start is a NEW
  activation with its arrival and an end after it, above the clock.
- **Partial writes:** an end that changes without that (no new activation, or no cooldown after the arrival yet) is
  reported (`changed`) and nothing is written; the watch goes on. The research does not show whether the game writes a
  call in one step or several.
- **Guards** (refused with nothing written; a refused call is never retried and keeps the carrier's own cooldown):
  - the pins (its own and the conversion's); in a mission, as host, solo;
  - the conversion still holds the definition, its record (address and key) and the carrier in that entry;
  - the carrier's cooldown type 0 and unlimited uses, and the entry's;
  - the game's write coherent: activation <= clock <= activation + 10 s, arrival >= activation, the end above the
    arrival and the clock, at most twice the row's cooldown after the arrival;
  - the new end above the clock.
- **Afterwards:** the entry reads the new end, and nothing else of the record changed. A later change of the end by the
  game is reported (`rewritten`), never fought.
- **Events** for the proof: `armed`, `changed`, `overridden` / `refused`, `rewritten`, `hud` (the bar's total on its
  first cooling frame), `ready` (callable again), `ended`.

**The proof [C]** (`proof/GasBarrageCooldownProof`): a small companion of GasBarragePayloadProof 0.2.2, which stays
unchanged and is installed with it. It arms the module at mission start, then logs:
- aboard the ship, the compatible carriers' native cooldowns;
- `COOLDOWN: carrier native = X`, `COOLDOWN: game started = Y`, `COOLDOWN: Gas Barrage override = 60.0 ...` and
  `COOLDOWN: verified end = current_game_time + Z`;
- the HUD bar's total, every 15 s the time left, and `READY AGAIN` with the measured cooldown.

The proof itself writes no memory.

**Validated offline:**
- **`tests/test_slot_cooldown.py`:**
  - the research and its domain;
  - 60 s from the arrival, with exactly the 8 end bytes written and the carrier's row unchanged; the HUD event; ready at
    exactly arrival + 60 s; a second call overridden again;
  - `from = 'now'`; a call made before the watch saw the conversion;
  - an end at or below the clock is ignored;
  - a call written in steps (an end without an activation, then an activation without an arrival, then the whole
    start): two `changed` events with nothing written, then one override; the same activation's end written again is
    a rewrite, never a new call;
  - every refusal writes nothing: STALE, NOT_A_COOLDOWN, SHARED_COOLDOWN, USES_DIFFER, UNSUPPORTED_BUILD, NOT_HOST,
    the wrong carrier and a changed entry;
  - a later change by the game is reported, not rewritten;
  - the watch waits for the conversion and ends with it.
- **`tests/test_gas_barrage_cooldown_proof.py`:** both proofs' own addons end to end. The 380mm carries mission 1 and
  the Napalm mission 2 (the 380mm natively in the loadout). Each call gets exactly 60 s from its arrival, logged in the
  user's format. The carriers' cooldown members are never written, and the whole rows are byte-identical after the
  return to the ship.
- **The built runtime ZIP** (`proof-gas-barrage-cooldown`), with the module loaded at startup from the archive:
  - **aboard the ship:** the pins prove on the real game.dll; the carriers' real rows give 240 s, cooldown type 0;
    nothing is written;
  - **on three mission snapshots:** the HUD draws every entry in its own slot. Then the payload proof's conversion, a
    SIMULATED call (validation scaffolding) and the module's one guarded write: the real record entry reads arrival +
    60 s and nothing else changed. Finally the payload and conversion restores (18 overlay writes).

**Not proven (needs the live test):**
- the game's actual write at a call: values, timing, and that it does not write the end again later;
- that the override lands before the arrival, so the HUD's bar takes 60 s;
- the HUD counting 60 s;
- the slot callable again at the new end, for the 380mm, the Walking Barrage and, if owned, the Napalm Barrage.

### The fixed cooldown live test (2026-10-03)

**Reported by the user:** the complete Gas Barrage, with the fixed 60 s cooldown, is LIVE-PROVEN and complete. The
380mm, the Napalm and the Walking Barrage have all worked as carriers. Recorded as reported; the report does not say
which mode ("from the arrival" or "from the call") was used.

**Next:** the carrier no longer needs to be a payload-compatible orbital. See
`research/docs/arbitrary-carrier-F5FEE03DCFDB.md`: the beacon's type, read once at activation, is the per-call boundary
where the identity carrier's gameplay can be replaced.

## A virtual card in the ship loadout picker: research (2026-10-02, offline)

**The question:** can the Runtime provide the duplicate selection itself? The aim is an **extra card**, "Orbital Gas
Barrage", in the ship's stratagem grid:
- it shows a Runtime-owned name, icon and description;
- it selects the native Orbital Precision Strike, so the save holds Precision, Precision;
- the mission conversion then does the rest.

**The constraints:** data writes only. No native calls or hooks, no StratagemInfo, account, catalogue, inventory or save
writes, and no per-frame brute-force writes.

Evidence: `research/stratagem-picker-F5FEE03DCFDB.json` (`scripts/research_stratagem_picker.py`). It holds 62 pinned
instructions, identical on all seven snapshots, and a whole-body check of the list's add. MultiSelect was read as a
lead only. Nothing was written.

**No retained snapshot holds a picker.** The loadout UI is `[[game+0x347CE38]+0xB0]`, and it is 0 in all seven: the UI
object exists only while the loadout screen does. Everything below is proven in code.

### The card list [C]

- **Where:** the stratagem screen is at ui+0xD2850 and its card list at ui+0xD2F20 (screen+0x6D0). It is a generic list
  control.
- **An entry is only a key:** a 32-bit catalogue item key (+0x92990 + i·4), an enabled byte (+0x92DC2 + i) and a badge
  byte (+0x92EC2 + i). The count is at +0x92984, at most 256.
- **Rows and sections:** four cards per row; per-row counts at +0x92318. Sections are stratagem categories (the row's
  +0xB8) at +0x92854, with their first row and first card.
- **No type, no stable id:** neither the entry nor the card widget stores them. Each use derives them: key → catalogue
  item (+8 stable id) → type (`0x11F2490`).
- **The widgets on screen are pooled:** 12 row widgets (stride 0xAED0) of four card widgets each (stride 0x2B68), filled
  for the visible rows only.

### The path [C]

| Step | What happens |
| --- | --- |
| Grid opens for a slot | The builder (`0x18D8710`, from `0x146ED65`) clears the list (`0x18D27B0`) and sets list mode 3 and four cards per row |
| Candidates | Each type 1..149 that is owned and selectable (`0x136FC20`): one card per type, keyed by its catalogue item; sorted by category |
| Cards | One add per candidate (`0x18D43A0`). The add never reads the key array, so the list itself would accept a repeated key. Then the layout and the first realize (`0x18D44B0`) |
| Presentation | Realize (`0x18D2B60`) fills each visible card from its key (`0x18CAFB0`): the icon is the row's +0xB0, **bound as a GUI material by native code** (`0x18DC5D0`, `0x144F800`). The label is built from the item key (`0x179C920`). The detail panel (name, description, preview) is filled from the focused key and its row on every focus change (`0x18D7210` → `0x191D040`) |
| Enabled state | The builder disables a card whose type is already in the record being edited (`0x18D8BEC`) |
| Click | Needs the card's enabled byte (`0x18D2690`). The confirm reads **the key at the focused cell** (`0x18D5E59`), stores it (screen+0x178C98) and moves the focus to **the first card with that key** (`0x18D1280`) |
| Selected type | The selection handler maps the key to its catalogue item, stable id and type, and writes the slot (`0x189D050`) |
| After the pick | The refresh (`0x18D1890`) enables every entry, then, per record entry, disables **the first entry with its key** through the per-card helper (`0x18D1440`). The helper also flips the realized card's flag (+0x2B5A bit 2) and redraws it natively (`0x18CA560`) |
| Save | `0x1751350`: one {stable id, uses} pair per slot, in order |

**When the game rebuilds:**
- every grid open rebuilds the list;
- every realize (scrolling, navigation, focus moving to a hidden row) refills the visible cards from their keys;
- every focus change refills the detail panel.

### How MultiSelect enables a duplicate [lead, confirmed in code]

Every 3 frames, for each selected stratagem whose card is disabled, it calls the per-card helper `0x18D1440` (list,
key, 1). The helper does three things:
- writes the enabled byte of the first entry with the key (data);
- flips the realized card widget's flag (data);
- redraws the card (`0x18CA560`, native).

**Direct writes reach the first two only.** The card becomes clickable but keeps its dimmed look until the game
realizes that row again.

### Determinations

| | Answer |
| --- | --- |
| The card object | A list entry holding only a catalogue item key, an enabled byte and a badge byte; the card on screen is a pooled widget refilled from that key |
| Candidate list | A dynamic list (at most 256, rows of 4, grouped by category), cleared and rebuilt on every grid open: one card per owned, selectable type |
| Duplicates in the list | The list accepts a repeated key, but the builder makes one card per type. The refresh, the per-card helper and focus-by-key act on the **first** entry with a key |
| The card stores the type / the stable id | **No / no.** Both are derived from the key at every use |
| What a click reads | The key of the focused cell, gated by its enabled byte |
| Add a card after the build | Only by writing the list arrays (key, enabled, badge, row and card counts, later sections' first card) and waiting for the game to realize the row. The game's own add and layout are native calls |
| Repurpose a greyed card | Its enabled byte is data, but its look is redrawn only natively |
| Spare capacity | 256 entries minus the owned, selectable stratagems |
| Auto-layout | A row with a free cell: the next realize lays the card out. A new row needs the native layout |
| Card-creation helper | Yes, native (`0x18D43A0`, `0x18D44B0`): excluded |
| **Per-card presentation** | **No.** The card's icon, label and detail panel are rebuilt by native code from the key and the token's StratagemInfo row at every fill. No per-card field holds a presentation the game reads back |
| Virtual card identity | Only its list index, while the grid lives. After a pick, the slot holds the token's type and the save its stable id: **which card was clicked is not recorded** |
| Which occurrence is virtual | Only record order survives save and restore: **the later of two token entries**, the rule of the mission conversion. A manual second pick of the native card (with MultiSelect) is indistinguishable, and so is a pick of the extra card into an earlier slot |

**The invariant that prevents it:** a card is only a key, and every visual of a card comes from the key's
StratagemInfo row through native GUI code, bound when the card is filled. An extra card that selects the native
Precision Strike must carry the Precision Strike's key, so the game draws the Precision Strike. Showing anything else
needs one of these, all excluded:
- a native call (re-binding the card's material and text);
- a StratagemInfo write (the token's presentation, for every card and slot of it);
- a catalogue write (a key that resolves elsewhere).

**What data writes could still do:** add a second, identical Precision Strike card. It would select the native token,
and the refresh disables only the first card with a key, so it would stay clickable. That is MultiSelect's outcome,
with more UI surgery and a card that may not appear before the player scrolls. It is not the requested card.

**No offline proof and no live test:** the design fails at per-card presentation, and no snapshot holds a picker.
Nothing is built.

**The routes within the rules:**
- **Custom presentation in the picker:** the carrier model. The carrier's own card shows its pre-mission
  presentation.
- **The duplicate token:** keep using MultiSelect for now. A Runtime equivalent would make the same native
  per-card call.

## A Runtime-owned custom stratagem selector: research (2026-10-02, offline); development proof built

**The aim:** the player selects "Orbital Gas Barrage" from a Runtime-owned UI while preparing the normal four-slot
loadout. The selection maps to a vanilla token (the Orbital Precision Strike), so the saved loadout holds ordinary
vanilla data. The game never learns that the entry was custom.

**The constraints:** no StratagemInfo, account, catalogue, inventory, progression or save-format change, no executable
patch, no native game-function call, no hook, no change to the native picker cards, no dependency on MultiSelect.

Evidence: `research/runtime-stratagem-ui-F5FEE03DCFDB.json` (`scripts/research_runtime_stratagem_ui.py`). It holds 337
pinned instructions in game.dll and the executable, identical on all seven snapshots. Mod Options Menu (which builds
its MODS tab by calling about 24 native game functions) and MultiSelect were read as leads only. Nothing was written.
**No retained snapshot holds a loadout screen**, so the screen is proven in code.

### Drawing: what exists [C]

| Mechanism | Usable without a native game-function call? |
| --- | --- |
| The native loadout cards, slot widgets and detail panel | **No.** Their icon and text are bound by native GUI code when a card is filled (see the picker research above) |
| XAML (Noesis) | **No.** The game uses it, but only C++ reaches it: no Lua module, no data path |
| Data writes into existing widgets | **No.** Nothing a widget draws is read back from plain data per frame |
| **The engine's Lua scripting API** | **Yes, if acceptable.** Registered when the Lua state starts (exe `0x2D3590`): `World.create_screen_gui` / `destroy_gui`, `Gui.rect` / `bitmap` / `text` with `update_` and `destroy_` variants, `Application.main_world` (the world the game rendered last, `0x317DE0`), `Mouse`, `Keyboard`, `Pad1..N`, `Window` |

The engine Lua API is how scripts are meant to draw. A released mod draws with it in game (see "Rendering" below),
and the engine's own development HUD script uses it with the font `core/performance_hud/monaco`. That font and its
material are resident in all seven snapshots.

It is **not an FFI call into game code**, but it does run engine code. **Whether it counts as a "native call" under the
rules is the user's decision.** If it does, there is no route at all: nothing reaches the screen without calling
engine code.

**Two properties shape the implementation:**
- **The bindings check nothing.** None of the GUI, World, Application, Window or input bindings raise a Lua error;
  handles are read unchecked, so a wrong argument most likely crashes. The Runtime validates every value first and
  disables drawing on the first failure.
- **The custom resources fit.** A normal GUI resolves `Gui.bitmap`'s material by resource name through `0x264620`. That
  is the same lookup the Runtime's custom icon materials were proven against (the material type; "Material not
  found." when absent). So the card's icon is the Runtime image's own GUI material, and its name and description are
  the Runtime text's strings drawn in the engine font. Neither resource system changes.

**Unproven offline:** that a screen GUI in `main_world` is drawn over the loadout screen. The game renders its worlds
from C++ through the plugin API, which `main_world` follows, but the loadout screen's world is not traced.

### Input [C]

- **Menu actions as data:** the game evaluates its input actions every frame into
  `[game+0x347CF18] + 0x328 + (group·97 + action)·32`, byte 0 = triggered, on any device or binding (`0x12F65E0`). Menu group 0: Up 1, Down 2, Right 3, Left 4, Back 9, Select 10 (the action table, `0xAE6360`).
  Reading them is a data read, so keyboard and controller can share one abstraction.
- **No consuming:** the native grid reacts to the same actions, and no input can be consumed without a hook. The first
  proof therefore uses **Runtime keybinds** (`hd2.input`, keys the loadout screen leaves unbound).
- **Mouse:** the engine's `Mouse` device and `Window` cursor functions exist. A click on a Runtime card could also land
  on whatever native widget lies under it, so mouse input waits for a proven-safe card position.
- **The selector takes semantic actions** (`next`, `previous`, `confirm`, `cancel`), so any source can drive it later.

### The loadout screen and its selection state [C]

`ui = [[game+0x347CE38]+0xB0]` exists only while the loadout screen does.

| Field | Meaning |
| --- | --- |
| ui+0x10 + i·0x9F0, i < 4 | Per-player loadout records: entries at +0x188 (0x30 each: +0 type, +4 uses), count at +0x788, owner at +0x9E8 |
| ui+0x27D0 | The local record's index |
| ui+0x2818, ui+0x281C | Sub-state 10 while the stratagem grid is open, for slot ui+0x281C (set when the grid opens, `0x146EB9C`; the pick goes there, `0x146E5E4`) |
| ui+0x27FC, ui+0x2808 | Ready; launched |
| ui+0x624B0 + i·0x12A8 (+0x128C) | The local panel's four slot widgets (their type) |
| ui+0x66F50 | The local panel's cached record pointer |

**A native pick** (`0x146E0A0`) does all of this, with no ownership check anywhere:
- sets the slot widget's type and icon (`0x189D050` → `0x1893600`) and sends a per-slot message to peers;
- rebuilds the record from the four widgets (`0x18966A0`: cleared, then one entry per filled widget);
- closes the grid and saves (`0x1751350`).

**The save store** is written from the record by:
- each native pick;
- sync_loadout at launch (`0x1467808`, which then writes the mission record and sends the whole loadout);
- on_exit after ready (`0x1467CD9`).

It holds `{stable id, uses}` pairs in order. Restore drops unknown ids and `uses == 0`.

**The record drives the slots.** Every frame, the panel bind (`0x146CB58` → `0x189CA20` → `0x189C900`) hands the
record to `0x1895A20`. That function returns early while its cached record pointer (+0xD960) and local flag are
unchanged. Otherwise it repaints the four widgets from the record's entries (`0x18962CE`..`0x1896347`), for the local
panel too (`0x18962C3`).

### Determinations

| Question | Answer |
| --- | --- |
| 1. Where the four selected stratagems live | The local record `ui+0x10+[ui+0x27D0]·0x9F0`; the slot widgets mirror it and are rebuilt into it on every pick |
| 2. Is changing it enough for the save path | **Yes:** sync_loadout, on_exit and each native pick save the record |
| 3. Does the save run by itself | At launch, on leaving after ready, and on every native pick; **not** on leaving without ready |
| 4. Without the native selection handler | **Yes:** one entry {type, uses} (plus the count for a new slot) and the cached record pointer cleared. The game's own bind then repaints the widgets from the record, so later rebuilds keep the entry |
| 5. Ownership validated at save | **No**, nowhere (save, sync, mission record, restore). The Runtime requires an owned, selectable token anyway, as the grid would offer |
| 6. Slot index preserved | **Yes, in order;** gaps are compacted (widgets {A, empty, C} save as {A, C}) |
| 7. One slot without account data | **Yes:** only the loadout UI object is written |
| Identity | The save holds only the token. **Slot order alone cannot tell** a virtual Precision Strike from a native one. The Runtime keeps its own identity record (definition, slot index, the token's stable id, the loadout's stable ids in order), and reconstructs only when the saved order matches. No save-format extension; several virtual entries can coexist the same way |
| Network | A native pick also messages peers per slot; a direct write does not. sync_loadout sends the whole loadout at launch. **Solo only** |

### The design: a floating card while the grid is open (option E, integrated by lifecycle)

The options the brief listed, against what the code allows:
- **A (a panel inside the screen), C (a tab):** need native widgets. Excluded.
- **D (a separate screen):** needs a native screen. Excluded.
- **B / E (an overlay, a floating selector):** possible through the engine Lua GUI.

The card appears exactly while the stratagem grid is open for a slot, and the selection goes into that slot.

- **Virtual definitions:** `runtime/virtual_stratagems.lua` (development; not public). Each holds an id, a display (a
  Runtime name, a description and an image), `selection.token`, `mission.carrier`, an optional calldown code, and no
  payload yet. It is entirely separate from StratagemInfo.
- **The selector:** `runtime/stratagem_selector.lua` (development; not public).
  - **Lifecycle:** reads only; emits opened, grid opened, grid closed, record changed and closed when they change.
  - **The engine renderer:** retained mode. The card is created when the grid opens and destroyed when it closes,
    only if its world still exists. Every argument is validated, and the font and icon residency are checked first.
  - **The selection:** the guarded transaction above, then a check that the game repainted the slot.
  - **Restore** while the screen is open; the identity record and `reconstruct(saved order)`.
  - `menu_actions` reads the game's menu actions (not wired by default).
- **The proof:** `proof/VirtualSelectorProof`, one card (Orbital Gas Barrage → Orbital Precision Strike). 0.1.0: F7
  selects, Ctrl+F7 restores, F9 status; its card was refused live (see "Rendering"). 0.2.0 is the rendering build.

**Validated offline:**
- `tests/test_stratagem_selector.py`, on a fixture loadout screen with a recording stand-in for the engine API:
  - the card is drawn with the Runtime icon material, the texts and the engine font only while the grid is open;
  - F7 writes slot N (2 writes for a replaced slot, 4 for a new one) and the emulated repaint puts the token in the
    widget;
  - every other entry, the StratagemInfo rows and the catalogue are unchanged;
  - restore is exact;
  - every refusal (not solo, ready, launched, no grid, unbound panel, gaps, limited, unowned, vehicle, closed, in a
    mission) writes nothing;
  - a missing font, icon or API, or a failing engine call, draws nothing;
  - the identity reconstructs only the recorded order.
- The built runtime ZIP: the proof loads from the archive aboard the real ship snapshot, and draws and writes nothing
  without a loadout screen.

**Not proven, so the live test must show:**
- that the card is drawn over the loadout screen;
- the repaint after the write in game;
- the save through the game's own path.

### Rendering: the 0.1.0 live test and the fix (2026-10-02)

**Live test of VirtualSelectorProof 0.1.0** (user report):
- the loadout screen opened and the stratagem grid opened for slot 0, as the lifecycle logged;
- then: `stratagem selector drawing disabled: stingray.Vector3/Color are unavailable`. No card was drawn and nothing
  was written.

**The cause [C]:** 0.1.0 required `type(stingray.Vector3) == 'function'`. In the engine:
- `stingray.Vector2` and `stingray.Vector3` are module **tables** with a `__call` constructor (exe `0x430F3E` →
  `0x431110`, `0x43517E` → `0x435370`), so they are callable but of type `table`;
- `stingray.Color` is a plain C function (`0x3E72CA`).

The constructors were always available in the Runtime's Lua environment, which is the same global `stingray` every mod
reads. The check was wrong, not the environment.

**The reference: Know Your Constellation v4.0** (`mods/cowboybingus/enemy_intelligence`, Vanilla Plus Megapack v36).
It is the pack's map forecast panel (enemy factions and spawn chances). Its addon embeds LuaJIT bytecode; it was listed
offline through `jit.util` in the game's own `lua51.dll` (loaded, never run). It is a lead only.

| | Know Your Constellation | The engine's dev HUD script | Runtime 0.1.0 | Runtime 0.2.0 |
| --- | --- | --- | --- | --- |
| API table | global `stingray` | global `stingray` | `rawget(_G, 'stingray')` (the same) | the same |
| World | `Application.main_world`, checked in `Application.worlds` | its own world, camera and shading environment | `main_world`, checked | `main_world`, checked |
| GUI | `create_screen_gui(world, 'scale', 1, 1)`, retained | `create_screen_gui(world, 0, 0, 'immediate')` | `create_screen_gui(world)`, retained | `create_screen_gui(world, 'scale', 1, 1)`, retained |
| Position | `Vector3(x, y, layer)` | `Vector3` | `Vector3` | `Vector3(x, y, layer)` |
| Size | `Vector2(w, h)` | `Vector2` | `Vector3` | `Vector2(w, h)` |
| Colour | `Color(a, r, g, b)` | `Color` | `Color` | `Color(a, r, g, b)` |
| Constructor check | none (calls them) | none | `type == 'function'`: **refused Vector3** | callable (function, or `__call`) |
| Resolution | `Gui.resolution()` | the window | `Application.back_buffer_size()` | `Gui.resolution()` |
| Shapes | `rect` / `update_rect` | `rect` | `rect`, `update_rect`, `bitmap` | `rect`, `update_rect`, `bitmap` |
| Text | `text` / `update_text`, the game's native font: name, material and runtime atlas read from game memory, passed as `IdString64`, the atlas set with `Gui.material` + `Material.set_*` on its GUI's material | `text` in `monaco` (with `Gui.material`) | `text` in `monaco` | `text` in `monaco`, by name |
| Images | none | none | `bitmap`, the Runtime icon material | the same |
| Updates | only when its content or geometry changes; their results ignored | every frame (immediate) | focus frame; result checked (the 0.2.0 failure) | none by default; an optional focus frame |
| Screen detection | the map and briefing screens, read from game memory | n/a | the loadout grid (data reads) | the same |
| Clean-up | `destroy_gui` only while its world is listed | n/a | the same | the same |

**The text font.** The native-font route needs `IdString64`, `Gui.material`, four `Material` setters and three game
memory reads; the native font's material pointer is null aboard the ship in the snapshots. Runtime keeps the engine
font `core/performance_hud/monaco`, by name. Its material uses a bitmap-font shader (`0x51C11754`). In all seven
snapshots, one of the game's own fonts (its font table at game+0x3772260, the eighth entry, `0xB8F4EE838B4ADE42`) is
loaded with a same-named material using that same shader. So the shader is part of the game's font set [O]. Whether
`monaco` text is visible in the game's main world is confirmed only live.

**The minimal subset (`runtime/engine_gui.lua`):**
- `Application.main_world` and `worlds`;
- `World.create_screen_gui(world, 'scale', 1, 1)` and `destroy_gui`;
- `Gui.resolution`, `rect`, `update_rect`, `text`, `bitmap`;
- the `Vector2`, `Vector3` and `Color` constructors.

Nothing else is called: no `IdString64`, `Gui.material` or `Material` setter, no game memory read for drawing.

**How it works:**
- Every value is validated first: finite pixel boxes inside the resolution, integer layers, colour components 0..255,
  printable text, plain resource names.
- The first failing call destroys the GUI and fails the screen.
- The selector's card and the drawing proof both draw through it.
- Positions are pixels from the bottom-left corner.

**The drawing proof** (`stratagem_selector.overlay`, F8 in the proof):
- one rectangle, the Runtime icon as a bitmap and the Runtime text ("Orbital Gas Barrage") near the screen centre;
- it first checks that the font and the icon are loaded;
- it is removed by destroying its GUI;
- it writes nothing.

**VirtualSelectorProof 0.2.0 (rendering build):**
- the card appears while the grid is open, and F8 toggles the drawing proof;
- **F7 (selection) is disabled**, so this build writes nothing.

#### 0.2.0 live test: the focus frame (2026-10-02)

**The report:** the lifecycle worked, then `stratagem selector drawing disabled: the focus frame could not be updated`.
The game kept running normally.

**What the "focus frame" is:** a Runtime-created GUI element. It is a decorative selection highlight, a rectangle
drawn behind the focused card and recoloured with `Gui.update_rect` when the focus moves. It is not a native UI
object.

**The cause [C]:** the engine bindings return values as follows.

| Binding | Returns |
| --- | --- |
| `World.create_screen_gui` | the GUI (`0x3F09D3`) |
| `Gui.rect`, `Gui.bitmap`, `Gui.text` | one id each (`0x3E1D4E`/`0x3E1D5C`, `0x3E2BA7`, `0x3E5491`) |
| `Gui.update_rect`, `Gui.update_bitmap`, `World.destroy_gui` | **nothing** (`0x3E1F90`, `0x3E2DF7`, `0x3F105D`) |

0.2.0 passed every engine result back unchanged and took the `nil` of a successful `update_rect` for a failure. The
renderer then destroyed the card it had just drawn, in the same frame.

The engine had **accepted** every creation call: the screen GUI, the rectangles, the icon bitmap and both texts, each
returning an id. The reason logged was the renderer's own fallback, so no engine call raised an error. Know Your
Constellation ignores the results of its updates and only asserts on creation ids.

The test stand-in returned a value from every call, so it hid this. It now returns nothing from updates and
`destroy_gui`, as the engine does.

**The fix (0.3.0):**
- **Results:** `runtime/engine_gui.lua` requires an id from a creation call. An update succeeds when it raises no
  error. A call marked optional that fails leaves the GUI open.
- **Required parts:** the screen GUI, each card's background, its icon, its name and its description. If one fails,
  the GUI is destroyed and drawing is disabled.
- **The focus frame is optional** (`selector({focus_frame = true})`, off by default). If it cannot be created or
  updated, `focus frame unavailable (...); the card stays drawn without it` is logged once, the frame is dropped and
  the card stays.
- **VirtualSelectorProof 0.3.0** draws the card **with no focus frame at all**. F8 is still the drawing proof, F7 is
  still disabled, and nothing is written.

**Validated offline:**
- The stand-in now follows the engine's returns, so the 0.2.0 wrapper would fail these tests as it failed live.
- The card renders without a frame.
- The optional frame, when on, draws and moves.
- A frame whose update raises, or whose rectangle returns no id, is dropped while the card stays.
- A required part returning no id destroys the GUI before the next part.
- Clean-up still destroys once.
- The built runtime ZIP draws the overlay and the card (background, icon, name, description, no frame) from the
  archive, then destroys both GUIs. 0 writes.

#### 0.3.0 live test: rendering verified (2026-10-02)

In the real loadout screen, while the stratagem grid was open:
- the Runtime screen GUI rendered;
- the rectangle, the custom icon and the Runtime text (name and description in `monaco`) were visible;
- the card disappeared when the grid closed;
- grid lifecycle detection worked.

F7 was disabled in that build. Recorded as live-proven in `schemas/live_evidence.json` (families
`stratagem_selector_lifecycle` and `stratagem_selector_rendering`); the two earlier non-renders are kept, marked
superseded.

### Grid placement: the card among the native cards [C]

**Where the native cards are on screen.** The game's own hover test (`0x18D0690`) hit-tests each realized card widget
through the GUI element contains-point test `0x144D320`. It reads from the element:
- its size `(w, h)` at +0x24;
- its 4x4 world transform at +0x64: `m00` +0x64, `m02` +0x6C, `m20` +0x84, `m22` +0x8C, translation `x` +0x94 and
  `y` +0x9C.

The on-screen rectangle is therefore x from `tx` to `tx + m00·w + m20·h` and y from `ty` to `ty + m02·w + m22·h`. That
is screen pixels from the bottom-left corner, the same space a `scale 1, 1` screen GUI draws in. Know Your
Constellation (a lead) reads the same fields to place its panel next to a native one. The Runtime proved them in code
and reads them only; it never writes a widget.

**The grid's data**, all in the card list (ui+0xD2F20):
- the row count (+0x91F14, counted by the layout, `0x18D44DF`) and each row's cards (+0x92318);
- the sections' first rows (+0x9274C);
- the first realized row (+0x928D8) and the realized rows (+0x91F0C);
- each realized row widget (stride 0xAED0) with its realized card count (+0xB9B4) and card widgets (+0xC10, stride
  0x2B68);
- the list frame itself, a GUI element of 395 x 528 units (`0x18D8896`).

**The native card** (stratagem card style, `0x18CAD14`): the card is 80 x 80 units, its inner frame 68, its icon 51,
all scaled by the element's transform. Four cards per row.

**The rule (`stratagem_selector.placement`):**
- **The cell:** the one right after the last native card. That is the next column of the last row, or column 0 of a
  new row below it when the last row is full.
- **Size and pitch:** the card is the native size. The column pitch comes from two cards in a row, and the row pitch
  from two consecutive rows of the same section (preferably the last section).
- **The text:** the name and description go in the free cells to its right (two or more), else in the free row below.
- **Hidden** (logged once with the reason) when any of these holds:
  - the last row is not realized (scrolled out);
  - the last row has fewer realized cards than the layout says;
  - the cards differ in size;
  - the card or its text would leave the list frame;
  - the card or its text would overlap any realized native card.

**Movement without per-frame redraws:**
- A cheap signature is read each tick: the layout counts, the frame, and the last row's first card to half a pixel.
- When it changes (scrolling, navigation, a section change, a slot change and the grid rebuild), the card is hidden at
  once, quietly.
- It is drawn again once the signature has been unchanged for 0.2 s.
- While still, no engine call is made.

**The tile** is drawn at the native proportions:
- an edge rectangle the card's size;
- an inner frame of 68/80;
- the custom icon at 51/80, centred;
- a dark text area with the name and description.

There is no focus frame; the optional one stays off.

**Selection and identity:**
- F7 runs the unchanged guarded selection: the token goes into the slot the grid is open for, and the game repaints
  it.
- While the screen is open, `stratagem_selector.track` follows the loadout. When the virtual slot still holds the token,
  the new order is recorded again (another slot changed natively); when it does not, the identity is dropped.
- `reconstruct(saved order)` recognises the virtual slot only when the saved order matches that record.

**Validated offline (`tests/test_stratagem_selector.py`, a fixture native grid of real element transforms):**
- the cell after a partial last row, and a new row after a full one;
- native size, pitch and proportions; the text area to the right or below;
- no overlap;
- no redraw while still;
- hidden when the end of the list is not realized, outside the frame, or with a partly realized last row;
- the placement rule refusing a native card in the cell or its text area, and mixed card sizes;
- shown again after scrolling settles, at the new place;
- F7 writing the token into the grid's slot with the game's repaint;
- the identity following a native change to another slot and dropped when the virtual slot changes;
- reconstruct matching only the recorded order;
- undo.

The built runtime ZIP draws the grid-cell tile from the archive against the stand-in engine. 0 writes.

**VirtualSelectorProof 0.4.0:** the card in the grid cell, F7 selection, Ctrl+F7 undo. The saved loadout is matched
against the Runtime record whenever it changes.

**0.4.0 live test (2026-10-02):** the card did not appear. The log said `not shown: the end of the list is not
visible` and `the card would leave the grid frame`. The stratagem list is a scrollable viewport, and 0.4.0 required
the final native row to be realized (and its text row below it to fit). This was the placement rule, not rendering.

### Scroll-aware placement: the card continues the native list [C]

**The list's scroll state (research `gridScroll`), all read as data:**

| | Answer |
| --- | --- |
| 1. Scroll viewport | The list frame, a GUI element of 395 x 528 units (its on-screen rectangle from its transform). The viewport is 528 units tall for the four-per-row stratagem grid (`0x18D4592`) |
| 2. Content | From 0 (cleared, `0x18D294D`) to the content height (+0x92968): the sum of the row heights (+0x91F18 + 4·row, `0x18D4518`), each row 85 units plus its section header on a section's first row (`0x18D4552`) |
| 3. Scroll offset | +0x92960, units from the content top (`0x18CF84F`); realize skips rows by their heights from it (`0x18D2BBA`) |
| 4. Row height | 85 units: an 80-unit cell (`0x18CC72B`) and a 5-unit gap (`0x18D2579`); a section's first row adds its header |
| 5. Column pitch | 85 units (the same cell and gap) |
| 6. Columns | 4 |
| 7. Candidates | +0x92984 (at most 256) |
| 8. The final card | Row `rowCount - 1`, column `rowCards[last] - 1`; its bottom in content units = content height - 5 |
| 9. Clamping | The offset is clamped to [0, limit], the limit at list+0x8C0 (the scrollbar's +0x7B0, set by `0x1794600`, `0x18CF881`) = content + 20 - 528 when the content is taller than the viewport, else 0 |
| 10. A free cell after the final card | When the final row holds fewer than four cards |
| 11. Content taller than the viewport | When the content height exceeds 528 (+0x928F9 set, the scrollbar shown) |
| 12. The scrollbar | The offset and the limit are plain floats, read safely |

**Categories:** the stratagem grid is **one list of every owned, selectable stratagem**, sorted into category
sections (`0x18D8710`; section ids at +0x92854 are the categories, StratagemInfo +0xB8). It is not filtered per
category.

**Case A, a partial final row:** the card takes the free cell after the final card. That cell is inside the content, so
scrolling to the bottom always brings it into view.

**Case B, a full final row: the limitation [C].**
- A new row would start at the content end. A scrolling list stops 20 units below its content (the limit is
  content + 20 - 528), less than an 80-unit card, so a new row never fully enters the viewport.
- Only a list that does not scroll can show it, when content + 80 <= 528.
- Otherwise the card takes the free cell at the end of the token's own category section (the Orbital section for the
  Precision Strike), else at the end of the last section that has one.
- If no row anywhere has a free cell, it is not shown, and the limitation is logged.

**Placing the cell on screen (`stratagem_selector.target`, `stratagem_selector.placement`):**
- **The target comes from the layout alone,** so the cell does not move while scrolling.
- **The position:** a cell's bottom in content units is its row's top (the sum of the heights above it) plus its row
  height, minus the 5-unit gap. On screen that is the top of the viewport minus (content bottom - scroll offset) x
  scale.
- **The scale** comes from the native card (its pixel height / 80) and must match the frame's (pixel height / 528)
  within 1%.
- **The offset and column 0** come from the first realized native card.
- **Every realized native card** must agree with the same model within 1.5 px: its column, its row's content
  position, its size. Any disagreement refuses, as do row heights that do not add up to the content height.
- **Drawn only while visible:** the card is drawn while its cell lies inside the viewport and clear of every realized
  native card. It is hidden during movement and drawn again after 0.2 s of stillness, as before.
- **The name and description** go in the free cells to its right (two or more), or, for the list's end, the free row
  below when it is visible; otherwise they are omitted (logged). They are never forced outside the frame.

**Validated offline** (`tests/test_stratagem_selector.py`, a fixture list laid out and scrolled as the game does it:
row heights, headers, content, limit, realized rows, element transforms):
- **The five positions:**
  - top of a long list: hidden, logged once with its cell;
  - middle: hidden;
  - bottom: shown in exactly the next cell of the final row, at the scrolled content position;
  - a partial final row with room: the name and description beside it;
  - a full final row: a new row in a short list, the Orbital section's free cell in a scrolling list (hidden until
    scrolled to), any section's, and the limitation when no cell exists.
- Inside the frame, no native card covered, nothing redrawn while still, hidden again on scrolling away.
- The model refusals: a card off its column, row heights not adding up, a frame of another scale.

**VirtualSelectorProof 0.5.0:** this placement, F7 off, nothing written.

### Coordinate calibration: the 0.5.0 live test and the diagnostics build (2026-10-02)

**0.5.0 live test:** the log said `stratagem selector shown for slot 0: 1 card (orbital_gas_barrage) in the grid: end
cell, row 22, column 2 (x 550, y 248, 160 px)`, with no drawing error, but no custom card could be seen in the native
grid. The placement model agrees with itself offline. That does not prove that the Runtime GUI draws in the space the
native transforms describe. **The placement formula stays unchanged until the mismatch is identified.**

**What 0.5.0 assumed without proof, and how 0.6.0 checks each:**

| Assumption | 0.6.0 check |
| --- | --- |
| The Runtime screen GUI's coordinates are the pixels of the native element transforms: same resolution, no scale, no DPI factor | The GUI resolution (`Gui.resolution`) is logged with the list frame's rectangle. Yellow squares mark the GUI's own corners (TR labelled with its resolution) and a cross its centre. Magenta outlines are drawn exactly at the native cards' transform rectangles: if they do not sit on the native cards, the two spaces differ |
| Both use a bottom-left origin with y up | The corner squares are labelled for a bottom-left origin (BL 0,0 / BR / TL / TR). If BL shows at the top of the screen, the axis is flipped |
| A card's transform is a screen position, not a parent-relative or content position | The N0, N1 and N2 outlines at several scroll positions: they must follow the native cards |
| The scroll model (row heights, content, offset, limit) places a cell where the game does | Each stage is logged for every sample. `model - native` compares the pure model (no offset taken from the native cards) with the native transform |
| The card is drawn above the native UI | The tile moves to layers 900-902 and the markers to 990-993. Yellow `L` probe dots at layer 21 sit inside N0 and V. An L hidden where its high-layer outline shows means the native UI covers low layers |

**The stages logged for each sample** (three realized native cards fully inside the viewport, in different rows and
columns: the first card of the first visible row, the last of the middle one, and column 1 of the last), and for V:
1. **content:** x from the frame's left edge, y the card's bottom from the content top, in units;
2. **after scroll:** y minus the scroll offset;
3. **model:** the frame's top-left plus units x scale, in pixels;
4. **native transform:** the card element's own rectangle, the truth. Its depth (the translation's middle component,
   +0x98) is logged too, unproven;
5. **Runtime GUI:** the rectangle the Runtime draws. For a native card, the same pixels. For V, the anchored placement,
   or the pure model when the placement refuses.

A header line before them gives the GUI resolution, back buffer size (when the engine has a binding for it), world
count, frame rectangle and px/unit, card scale, scroll offset, limit and content height, and column 0's position.

**Reading the live result:**
- **N outlines on the native cards, V in the next free cell, the tile visible there:** aligned. This is the stop
  condition for selection work.
- **N outlines on the cards, but no tile and no L probes visible:** occlusion. The native UI covers the main world's
  screen GUI at those layers.
- **N outlines off the cards by a constant factor:** resolution or scale. The conversion is that factor (compare the GUI
  resolution with the frame's rectangle).
- **N outlines mirrored vertically:** axis convention. The conversion is y' = height - y - h.
- **N outlines on the cards, V away from its cell:** the scroll model. The `model - native` lines show where it departs.
- **No markers at all:** the main world's screen GUI is not drawn over the loadout screen.

**VirtualSelectorProof 0.6.0 COORDINATE-DIAGNOSTICS:**
- Rendering only. Diagnostics are on at start; F8 toggles them.
- Calibration lines and markers are produced each time the list is still. Markers close as soon as it moves.
- The card is the tile alone (background, icon, border; no name or description; the native details panel shows text) at
  layer 900.
- No focus frame. F7 is off. Nothing is written.

**Validated offline:**
- `tests/test_stratagem_selector.py`, a fixture list at the bottom and the top:
  - the tile alone on its layers;
  - the header and every stage logged for N0, N1 and N2, in three rows and more than one column;
  - V logged both visible and outside the viewport;
  - the markers drawn in their own GUI, inside its bounds: F, N0..N2, V, the corners, the centre and two L probes;
  - nothing redrawn while still; markers closed on movement and by F8 off; drawn again by F8 on;
  - a uniform 7 px offset between native cards and the model is reported as `model - native` -7, not absorbed;
  - 0 writes.
- The built runtime ZIP, from the archive: the tile at layers 900-902, the markers and the calibration lines from a
  calibration record, then every GUI destroyed. 0 writes.

**0.6.0 live test (2026-10-02):** the coordinates are right, and the card is hidden by the native UI.
- At the bottom of the list:
  - GUI resolution 3840 x 2160;
  - frame 150, 208, 790 x 1056 px;
  - card scale 2 px/unit;
  - scroll 1585 of 1585.
- V: content (200, 2088) units, pure model (550, 258) px, Runtime GUI (550, 248, 160 x 160) px, inside the viewport.
- The native cards' Runtime rectangles equal their native transforms in X and size.
- **A constant 10 px Y difference** separates the pure model from the native transforms: the native card bottoms are
  10 px below the model. The placement already anchors on the native cards, so V is drawn at 248. This is documented
  and will be corrected against the real card bounds once the card is visible. No further iteration until then.
- **The blocker:** the Runtime diagnostic GUI rendered, but the V marker (layer 991) and the tile (layers 900-902) were
  not visible over the native grid. The 0.3.0 card was visible in an empty area. So the next question was render order.

### Render order: why the native loadout UI covers the Runtime GUI [C]

Evidence:
- `research/runtime-stratagem-ui-F5FEE03DCFDB.json`, groups `renderOrder` (exe and game.dll) and `renderConfig`;
- the game's render config, read from the installed data (resource `0xEE6B1BA7E22D71ED`, decoded);
- the Know Your Constellation and performance HUD bytecode, read as leads.

**The references:**

| | Know Your Constellation v4.0 | The engine's performance HUD script |
| --- | --- | --- |
| World | `Application.main_world`, checked in `Application.worlds` | Its own: `Application.new_world`, rendered by its `render` callback with `Application.render_world(world, camera, viewport, shading_environment)` |
| GUI creation | `World.create_screen_gui(world, 'scale', 1, 1)` | `World.create_screen_gui(world, 0, 0, 'immediate')` |
| Render stage | None chosen | The viewport template `hud_world_ui_and_composite_layer` (`Application.create_viewport`) |
| Mode | Retained | Immediate (drawn again every frame) |
| GUIs | One | One |
| Render order changed | No | Only by rendering its own world |
| Layers | `Vector3(x, y, layer or 0)` | `Vector3` |
| Over the game UI | Not established: whether its forecast panel overlaps native UI elements was not checked | Disabled in release builds and while the game plugin runs; never seen in game |

**What decides the order:**
1. **A screen GUI is drawn in its world's transparent passes.** `Gui.rect` keeps the `Vector3` z as an int32 layer
   (`0x3E1CBD`), carried to the render thread with the primitive. **Corrected by the slot overlay research (below):**
   the layer is not per GUI. Each batch's depth is computed from its layer (`0x2693E3`: `0.1 * (1023 - layer) / 1023`)
   and every GUI of one world is sorted together by that key, with no GUI identity in it (`0x4BF4D3`). So a Runtime GUI
   in the same world as a native GUI is ordered against it by layer.
2. **`create_screen_gui` has no stage option.** Its options are only `scale`, `immediate`, `dock_right`, `dock_top`,
   `material` and `shadow_caster` (`0x3F04E2`..`0x3F0736`). No Lua API sets a render order: the exposed modules
   include no Noesis or UI module and no order setter.
3. **The game's UI world** is rendered through `hud_world_ui_and_composite_layer` (game.dll `0xAB1BF0`). Its layer
   config, in order:
   1. `blur_behind_ui`;
   2. clear `ui_target`;
   3. `transparent_pre`, `transparent_shadow`, `transparent`, `transparent_post` into `ui_target` (world GUIs);
   4. **generator `noesis` into `ui_target`**;
   5. `copy_and_blend_ui`: a fullscreen pass from `output_target`, `last_back_buffer` and `ui_target` **into the back
      buffer**.

   The game world (viewport `default`, game.dll `0xAB1BA4`) renders into `output_target`, the base image under the UI.
4. **Each frame**, the engine:
   1. calls the Lua `update` callback (`0x89F81`);
   2. calls the Lua `render` callback, and right after it the game plugin's render callback (`0x8A1E2` → `0x689BC0` →
      plugin `+0x90` = game.dll `0x4EE7E0` → `0xAB7680`; the same callback in all seven snapshots);
   3. inside that callback, the game renders its game world, then the UI world, then an offscreen `ui_3d` world
      (`0xAB7AFC`, `0xAB7B40`, `0xAB7CBD`).

   World renders are queued and run in order (`0x10788C`).
5. **`main_world`** is the listed world with the latest render stamp (`0x318216`, `0x317E44`). Whichever listed world it
   is, a GUI in it is drawn either in the UI world's transparent passes, under Noesis, or in the game image under the
   whole UI. **Resolved by the slot overlay research:** every world rendered in a frame carries the same stamp, and the
   tie goes to the world with the most units (`0x317E65`), the Game World (`worlds()[1]`). A `main_world` GUI is
   therefore drawn in the game image, under the whole UI composite.

**The critical question: can `Gui.rect(..., layer = 990)` ever appear above the native Noesis UI? No.**
- The layer orders primitives inside one GUI, within one transparent pass.
- The Noesis UI is drawn after every transparent pass of the UI world, into the same target, and the result is
  composited over the game image.
- No layer number, GUI creation option, GUI mode or second GUI changes the pass a screen GUI is drawn in.

**Is there an engine path that draws after Noesis?**
- The render config has two viewports whose transparent pass writes straight to the back buffer:
  - **`overlay`:** created by no game code (its id is in neither game.dll nor the exe);
  - **`stingray_debug`:** used only by the engine's own debug world. That world renders after the game behind a setting
    (`0x8A1EC`), and it is **not in `Application.worlds`**, so Lua cannot reach it.
- **A script world rendered through `overlay`** is the only candidate the Lua API offers (`Application.new_world`,
  `create_viewport`, `render_world`). But a script can only queue it from the Lua `update` or `render` callback,
  before the game's render callback. The UI world's `copy_and_blend_ui` then rewrites the whole back buffer after it.
  **Predicted: overwritten.**
- Unproven offline: whether the composite shader uses `last_back_buffer` in a way that keeps earlier back-buffer pixels.

**The engine limitation, exactly:** through the exposed Lua API, a Runtime GUI is either:
- a primitive in a listed world's transparent passes, which the Noesis UI or the UI composite always covers; or
- a script world queued before the game's UI world, whose composite rewrites the back buffer.

The only world drawn after the composite is the engine's own debug world, which the Lua API does not list. If the
live test confirms both predictions, a Runtime-drawn card cannot appear over the native stratagem grid without a native
call. It can still appear wherever the native UI draws nothing, as the 0.3.0 card did.

### RenderOrderProof 0.1.0: the live check (rendering only)

`runtime/render_probe.lua` and `proof/RenderOrderProof`. It draws only and writes nothing; no selection, no custom
stratagem. While a stratagem grid is open and still, it draws over the four cards of the first fully visible row and in
the empty area right of the loadout panels:
- **N0:** TEST RECTANGLE (red, white edge, layers 998-999).
- **N1:** one strip per layer: 0, 21, 100, 900, 990. **F8** adds 2000 and 10000 (the render side's use of a layer
  above 999 is unproven, so it is opt-in and last).
- **N2:** four retained GUIs created in the order A, B, C, D, all at layer 500. The overlap shows whether a later GUI
  draws on top.
- **N3:** an immediate GUI, created as the performance HUD creates one, drawn again every frame.
- **F6:** the overlay world. A script world (camera unit `core/units/camera` and shading environment `midday`, both
  resident in every snapshot) is rendered through `overlay` from the Lua `render` callback, chained after the original
  and restored afterwards. It shows a green rectangle over N0 and outside. It is released after 30 s, on F6, or when the
  list moves or the grid closes.

**Validated offline** (`tests/test_render_probe.py`, the stand-in engine with the engine's own types and returns):
- `engine_gui`:
  - the layer range (999 by default, 10000 only on request);
  - immediate mode as the performance HUD creates it;
  - a chosen world must be listed;
  - the script world built and released in order, and released when a step fails.
- The probe:
  - eight GUIs in order;
  - the test rectangle exactly over N0;
  - the strips over N1, bottom to top;
  - A, B, C and D at layer 500;
  - two immediate rectangles a frame;
  - everything closed on scrolling and redrawn, F8's layers, and everything removed when the grid closes.
- The overlay world:
  - queued from the render callback after the original, whose results are kept;
  - released with the callback restored (on F6, on movement, on timeout, when the grid closes);
  - another chain installed later is left in place but our part stops queueing;
  - refused before anything is made when the callback is missing or the camera unit is not loaded.
- 0 writes.
- **The built runtime ZIP:** scenario `proof-render-order` runs the proof from the archive against the real snapshot's
  residency.

**The route is closed (2026-10-02).** By the user's decision, Runtime GUI is no longer placed over the native
stratagem grid or any other native UI. No RenderOrderProof live result was recorded.

## A Runtime-owned custom stratagems panel (2026-10-02, development)

The custom-stratagem picker is a **separate Runtime-owned panel**: a small CUSTOM STRATAGEMS grid in an area of the
loadout screen that the native UI leaves empty.
- **The native picker:** untouched, and never drawn over.
- **The Runtime picker:** separate.
- **The vanilla loadout record:** the bridge between them. A pick (phase 2) is the existing guarded token write into
  the slot being edited, kept by the existing saved-order reconstruction.

### The native tile's look: what can be reused [C]

Evidence: research groups `cardLook` (game.dll) and each snapshot's `cardLook`.

**What the native card has:**
- **Sizes only for its body.** The stratagem card style sizes the card's elements: the card 80 units, its inner frame
  68, its icon 51 (`0x18CAD23`..`0x18CAD84`). **No texture, GUI material or sprite** carries the card's background,
  border or inner frame.
- **One image: the focus bracket.** It belongs to element `+0x1800` (92 units) and is bound by the image setter
  (`0x18CADEB`, `0x18CADFC`). It is an atlas sprite (`0x270930A62555EBEF`; the other card styles use `0xF78DB8F1CC821769`
  and `0x7D698BF20161DE2B`) on a 1024 x 512 single-channel (BC4) UI atlas page.
  - Its shape: four white corner brackets around the 80-unit card, arms about 15 units, 3 units thick, with a 6-unit
    glow margin.
  - It is resident aboard the ship and at mission end, not during missions.
  - A material (`0xF6978E86E4F4B0D5`) is set on that element first (`0x18CADD2`).

**What the Lua API could reach:**
- `Gui.bitmap` takes a material by name or as an `IdString64`, and `Gui.bitmap_uv` exists.
- But no GUI material that samples the UI atlas page can be named, and the page itself is a texture, not a material.
  Drawing the sprite would need an unknown UI material plus material setup at run time.

**Verdict:** no vanilla resource is reused. The Runtime tile is drawn with rectangles in the native proportions:
- a dark square;
- a thin light border;
- an inner frame at 68/80;
- the icon at 51/80, centred;
- when focused (phase 2), four corner brackets with the sprite's proportions.

### The icon

The source picture (`gas_barrage.png`, 1024 x 1024) becomes two of the proof's own images, through the live-proven
custom image mechanism (256 x 256, BC1, the mod's own texture and GUI icon material):
- `gas_barrage`: the picture as given, reduced 4 x 4;
- `gas_barrage_mask`: the picture in the vanilla convention. The game's own icons are red and green masks on black
  (the 120mm Barrage icon: the category-coloured globe red, the white shells green). Its three colours are separated by
  least squares: dark becomes empty, salmon red, cream green.

How the icon material colours a picture in a Runtime screen GUI is not known offline, so the proof shows both (F8).
`proof/CustomStratagemPanelProof/prepare_icons.py` makes them; neither is a vanilla resource.

### Placement and scaling

- **The box:** the panel stays inside the box where Runtime GUI was proven visible while a stratagem grid is open. That
  is the 0.3.0 card's area: x 0.67 W, its top 0.16 H below the screen top, 0.29 W x 0.15 H.
- **Native units:** everything is laid out in native units (card 80, pitch 85, inner frame 68, icon 51). The pixels per
  unit come from the native cards' own scale while the grid is open (2 px/unit at 4K), else height / 1080.
- **Compact:** if the panel does not fit the box, the unit shrinks.
- **Protected native UI:** the panel refuses to draw if it would meet the native list frame (read while the grid is
  open) or any other protected rectangle.
- **It cannot cover native UI anyway:** the game draws its UI after every Runtime GUI. The panel only shows where
  nothing native is.

| Resolution | px/unit | Box (x, y, w x h) | Panel | Tile | Description area |
| --- | --- | --- | --- | --- | --- |
| 1920 x 1080 | 1 | 1286, 745, 556 x 162 | 556 x 120 | 80 x 80 at 1294, 795 | 282 wide |
| 3840 x 2160 | 2 | 2572, 1490, 1113 x 324 | 1113 x 240 | 160 x 160 | 565 wide |
| 2560 x 1440, 1600 x 900, 1280 x 720 | H / 1080 | the same fractions | fits uncompacted | | |

**The grid:**
- three columns;
- empty cells are not drawn;
- one visible row fits the box, and later rows scroll (the layout supports any count up to 60, with a scroll offset).

**The description area:**
- it sits beside the grid, inside the panel, so it never meets the native details panel;
- phase 1 shows the name;
- phase 2 shows the focused entry's name and its description, wrapped on words, at most 3 lines.

### Phases

- **Phase 1 (CustomStratagemPanelProof 0.1.0):**
  - draws the panel, the tile, the icon (F8: variant) and the name while a stratagem grid is open;
  - no focus, no selection, nothing written.
- **Phase 2 (built after phase 1 is live-checked):**
  - F7 focuses the card (brackets and description), then selects it: `stratagem_selector.select` writes the
    Orbital Precision Strike token into the edited slot (solo, aboard the ship, grid open, guarded);
  - Ctrl+F7 restores the slot, then unfocuses;
  - the identity follows the loadout (`stratagem_selector.track`), and the saved order is reconstructed as before;
  - no mission and no carrier conversion in that proof.

**Validated offline** (`tests/test_custom_stratagem_panel.py`):
- the layout at 1080p, 4K, 1440p, 900p and 720p;
- exact 2x scaling from 1080p to 4K;
- the native card scale, compaction, refusals;
- protected rectangles;
- a five- and seven-entry grid with scrolling;
- word wrap;
- phase 1:
  - one GUI with the panel, edge, title, tile, border, inner frame at 68/80 and the icon at 51/80;
  - the name and no description;
  - nothing redrawn while still;
  - F8 redraws with the mask image;
  - a resolution change redraws;
  - the panel hides when the grid closes;
  - 0 writes and no row changed;
- refusals before anything is created (an icon or the font not loaded), and a refused call mid-way closing the GUI;
- phase 2 (enabled by option):
  - the brackets on the card, the description beside it;
  - the token written into slot 1 and repainted by the game;
  - the identity recorded, the restore, the unfocus.

**The built runtime ZIP:** scenario `proof-custom-stratagem-panel` runs the proof from the archive with both images
seeded as complete families. It lays out at 1080p and 4K, draws the panel with each variant, and destroys the GUI. 0
writes.

### The 0.1.0 live test and the compact redesign (0.2.0)

**0.1.0 live test (2026-10-02):** the panel rendered safely in the empty area, but needed a redesign.
- At 4K it was x 2572, 1113 x 240 px, with a 160 x 160 card: too wide, too far toward the right edge, and the card
  larger than necessary.
- The permanent description area wasted space.
- **The custom icon did not visibly render.**
- **The panel stayed visible too long,** including a transient grid-open state with slot -1.

**The lifecycle, researched [C]** (research group `selectionLifecycle`):
- **`ui+0x273990` is the selection-open byte.** It is set to 1 only by the open handler (`0x146EA57`, `0x146E9D0`,
  reached from one input handler). It is set to 0 only by the close handler (`0x146F3DA`, `0x146F3B0`), also called after
  a pick that leaves no empty slot (`0x146E672`), and at screen init (`0x1466FA6`).
- **The sub-state `ui+0x2818` is not the open grid.** Every frame the screen update recomputes it from the panel's
  **focused** slot (panel `+0xD96C`, set by `0x189578D`): 10 for a focused stratagem slot 0-3, 5 for slot 4, 0 for none
  (`0x1468748`, `0x14686BB`). This happens whether or not a selection is open, so it stays 10 after a pick or Back while
  the slot keeps the focus.
- **The edited slot `ui+0x281C` is -1** until the first selection (`0x1465931`).
- **After a pick** with an empty slot left, the selection stays open on the next empty slot (`0x146E6D4`).
- **The rule now:** `stratagem_selector.screen().gridOpen` requires the selection byte, sub-state 10 and an edited slot
  of 0-3. The old selector and its selection write follow the same, stricter rule.
- **The panel controller polls it every frame.** It is drawn about 0.15 s after the selector opens (so the native cards
  can size it) and destroyed in the first frame it closes. A slot change while open is logged and the panel stays.
- **The logs:** `custom stratagem panel shown: active selector slot N` and `custom stratagem panel hidden: selector
  closed`.

**The compact renderer (default):**

| | 1080p | 1440p | 4K |
| --- | --- | --- | --- |
| px per unit | 1 | 1.33 | 2 |
| Tile | 60 x 60 | 80 x 80 | 120 x 120 |
| Pitch | 64 | 85.3 | 128 |
| Panel (title + 3 x 2 grid) | 204 x 162 at x 1286 | 272 x 216 at x 1715 | 408 x 324 at x 2572 |
| With the tooltip side | 382 wide | 509 wide | 764 wide |

- **The panel wraps only the title and the grid.** The tooltip appears to the right of the panel, level with the
  focused tile's row, only while a tile is focused. It holds the name (up to two lines) and the description (up to three
  lines).
- **The footprint** (the panel plus the tooltip side) stays inside the proven box (x 0.67 W, top 0.16 H, 0.29 W x
  0.15 H) and clear of the native list frame. When it does not fit, the unit shrinks: a native scale larger than
  height / 1080 compacts it.
- **The grid:**
  - three columns, compact 4-unit gaps, empty cells not drawn;
  - at most two rows in view, and more rows wait for scrolling (`scroll` is prepared, not used by the proof);
  - entries are the virtual stratagems, then visual placeholders ("Placeholder Custom Stratagem 2..", a dim `?`, never
    selectable).
- **The tile:**
  - a dark square;
  - a 1-unit outer border;
  - an inner frame at 68/80 of the tile;
  - the icon at 51/80, centred;
  - focus brackets with the native sprite's proportions.
- **The 0.1.0 renderer is kept unchanged as the legacy renderer.** `M.layout` and `M.draw` only gained placeholder
  support. It is used if the compact layout is refused, or when asked for (`renderer = 'legacy'`), under the same
  lifecycle.

**The icon:**
- 0.2.0 uses `orbital_gas_barrage` (from `orbital_gas_barrage.png`, 1254 x 1254, area-averaged to 256 x 256 by
  `prepare_icons.py`). The 0.1.0 images are kept in `legacy-images/` and are not built.
- **Why 0.1.0's icon was invisible is not identified.** Offline, the mip chain is ruled out: the texture header is
  byte-identical to the vanilla 120mm icon texture's, the GPU part is the same size, and every mip level decodes
  consistently.
- The visible 0.3.0 icon was drawn at about 237 px at 4K, on its own background layer 21 with the bitmap at 22. The
  0.1.0 tile icon was 102 px at layer 15.
- **The icon test (F8)** draws the same image at four sizes (118.8, 80, 51 and 38.25 units; at 4K 238, 160, 102 and
  77 px) under the 0.3.0 card's conditions. It shows whether the problem depends on size. No other image is substituted.

**Validated offline** (`tests/test_custom_stratagem_panel.py`):
- the legacy layout unchanged;
- the compact layout at 1080p, 1440p and 4K: exact 2x scaling, six entries in 3 x 2, no overlaps, the tooltip inside the
  side area;
- nine entries with scrolling, one entry, compaction, protected rectangles, placeholders;
- the lifecycle:
  - nothing while the loadout screen is open or a slot is merely focused;
  - nothing with a slot number but no open selection;
  - shown after the selector opens, and kept when the slot moves on;
  - destroyed the frame the selector closes, while the slot stays focused;
  - nothing for a booster slot;
  - shown again for another slot;
  - destroyed when the screen closes;
- the compact draw:
  - one GUI of 59 rectangles;
  - the Gas Barrage icon at 51/80, centred, and five placeholder marks;
  - no permanent description;
- the tooltip:
  - its own GUI with the brackets on the tile and the name and description;
  - it follows the focus and is cleared by Ctrl+F6 and after the sixth tile;
- the icon test at four sizes on layers 21-22;
- the legacy fallback when the compact layout is refused, and by name;
- refusals before anything is created;
- phase 2 (by option): the token write and restore, placeholders refused;
- 0 writes in phase 1.

**The built runtime ZIP:** scenario `proof-custom-stratagem-panel` (0.2.0) runs the proof from the archive with
`orbital_gas_barrage` seeded:
- the compact layout at 1080p and 4K;
- the six-tile panel;
- the tooltip;
- the icon test;
- the legacy renderer;
- every GUI destroyed, 0 writes.

### The 0.2.0 live test, placement right of the details panel and the icon contract (0.3.0)

**0.2.0 live test (2026-10-02):**
- The compact panel worked, and the active-selector lifecycle is correct (live-proven).
- Two problems remained:
  - at x 2572 (4K) the panel was too far left, because the large native details panel occupies the centre;
  - the Orbital Gas Barrage tile was **blank**.

**The native details panel [C]** (research `detailsPanel`):
- While a selection is open, the per-frame update fills the details panel at `ui+0x24B520` (`0x1468773` →
  `0x189FA80`). It is a GUI element like the list frame.
- For a stratagem its size is set to **1024 x 400 units** (`0x189FC39`, `0x189FC44`; mode 0xB, `0x189FC5D`).
- The close handler fades it (`0x146F3E1`).
- `stratagem_selector.details` reads its laid-out size (`+0x24`) and world transform as for the cards. It requires
  exactly the stratagem layout and an even scale, else it refuses.

**The anchored placement (`custom_stratagem_panel.anchored_layout`, the 0.3.0 default):**
- **The column:**
  - starts at `details_right + margin` and ends at `screen_right - margin` (the margin is 15 units: 30 px at 4K, 15 at
    1080p);
  - is limited to the details panel's vertical band, between the top bar and the bottom controls.
- **The panel** takes the column's top-left corner, three columns preferred.
  - The unit is the native card scale, capped so the grid fits.
  - Tiles shrink first. A column is dropped only below 36 px per 1080 lines.
- **The tooltip** goes to the right of the panel when it fits, else below it, inside the column.
- **The icon diagnostics** use the area below the panel.
- **Protection:** the panel, the tooltip area and the footprint must never meet the details panel or the native list
  frame, and must stay on screen.
- **No details panel, no panel:** without a readable details panel nothing is drawn, because its position would be
  unknown.
- **The legacy fallback:** the 0.1.0 renderer remains the fallback with the details panel protected, so it is refused
  wherever it would meet it.
- **It follows the details panel** if it moves (for example while animating in).

| Details panel | Column | Panel | Tile | Tooltip |
| --- | --- | --- | --- | --- |
| 1080p, 500..1524 x 232..632 | 1539, 366 wide | 251 x 193 | 75 | below |
| 4K, 1002..3050 x 600..1400 (2 px/unit) | 3080, 730 wide | 502 x 386 | 150 | below |

(These details positions are examples used by the tests. The game's real rectangle is read live and logged as `right
of the native details panel ...`.)

**Tile size (selector UX pass, 2026-10-04):** the tiles are 75 units at an 80-unit pitch, a quarter larger than the
earlier 60 at 64 (204 x 162 at 1080p). The icon keeps the native proportions of the tile, so it grows with it. The panel
still takes only the column right of the details panel; the tiles shrink first when the column is narrow, and a column
is dropped only below 36 px per 1080 lines. The 0.2.0 box layout (`compact_layout`, no longer drawn) keeps its 60-unit
tiles.

**The Gui.bitmap contract [C]** (research `bitmapContract`):
1. **The first argument** is read by one parser for `Gui.bitmap` and `Gui.bitmap_uv` (`0x3E0FA0`; bitmap_uv:
   `0x3E323A`).
   - In a **legacy-mode** GUI (`+0x89` set) it is a 32-bit id in the GUI's own material set (`0x3E10D3`).
   - Otherwise it is a **material resource** named by a string (MurmurHash64) or an `IdString64` (tag `0x6F6F4D64`,
     from `IdString64.from_hex`, `0x3D3437`).
2. **It is always a material,** resolved by `0x264620` (`0x3E117D`):
   - **refused** for legacy-mode GUIs (`0x264651`);
   - **refused** with "Material not found." when no material of that name is resident;
   - **refused** with "Material sets are not supported for GUIs." when the resource's `+4` is 0 (`0x26474C`);
   - otherwise a per-GUI instance of the material is created and drawn.

   A texture or an atlas sprite is never accepted.
3. **The custom image family provides the correct resource.** Its GUI icon material has the image's name, it is
   resident, it is exactly the icon material of that name, and its `+4` is 1 (as vanilla's).
4. **The material's texture slot cannot be passed on its own.** The material samples it; `Gui.bitmap` has no texture
   argument.
5. **`Gui.bitmap_uv`** takes the same material argument plus UVs. It has no sprite lookup.
6. **A vanilla material can be drawn by the same path:**
   - by name: the engine font material `core/performance_hud/monaco`;
   - by hash: the vanilla 120mm icon material, through `IdString64`.

   Both are resident aboard the ship in the snapshots.
7. **Residency when drawn:** the panel checks the image's texture and GUI material, exactly, before every draw, and
   logs it.

**Not decidable offline:** what the icon material's shader does with a picture in a screen GUI. The 0.3.0 card of
VirtualSelectorProof drew a custom icon visibly through this path; the 0.1.0 and 0.2.0 tiles drew theirs blank. The
custom image format is unchanged (it is live-proven for `presentation_icon`).

**The logs and the icon diagnostics (F8):**
- **Each panel icon draw is logged:** `custom icon GUI bitmap draw attempted: Gui.bitmap("<material>", x, y, w x h,
  layer 15)`, then `... succeeded (engine id N)` or `... failed: <reason>`.
- **F8 logs residency first:** `custom icon loaded: texture ... resident`, and `custom icon GUI material loaded: ...
  resident, exact ..., shader ..., image slot -> ...`.
- **F8 then draws, below the panel, four cells over a split dark | light background:**
  - `font` (vanilla material by name);
  - `vanilla` (vanilla icon material by hash);
  - `name` (custom material by name);
  - `hash` (custom material by hash);
  - then `name large` (the custom material at the 0.3.0 card's size).

  Each is drawn only when resident, each draw is optional (one refusal does not stop the others), and each result is
  logged.
- **No other image is substituted** for the custom icon.

**Validated offline** (`tests/test_custom_stratagem_panel.py`):
- the details reader: the stratagem layout, refusals;
- the anchored placement at 1080p, 1440p and 4K: exactly proportional, the 15-unit margin, inside the band, the tooltip
  below or beside, tiles shrinking with three columns kept, a column dropped only below the minimum, refusals;
- the lifecycle unchanged, and following the details panel when it moves;
- the six-tile draw with the icon logs and the tooltip below the panel;
- the diagnostics:
  - the font by name, the custom material by name and by `IdString64` of its hash;
  - the vanilla icon not drawn while not resident, and drawn by hash once resident;
  - all inside the area below the panel;
- the legacy fallback refused where it would meet the details panel, drawn where it would not, nothing without a details
  panel;
- refusals (including a refused icon logged as failed, and diagnostics continuing past refusals);
- phase 2 by option.

**The built runtime ZIP:** scenario `proof-custom-stratagem-panel` (0.3.0) runs against the real snapshot's residency:
- the engine font and the vanilla 120mm icon material resident;
- the proof's image seeded;
- the anchored layout at 1080p and 4K;
- the panel draw logged;
- the tooltip below the panel;
- all five diagnostics drawn;
- the legacy renderer;
- 0 writes.

### The 0.3.0 live test, the icon investigation and selection from the panel (0.4.0)

**0.3.0 live test (2026-10-02):**
- **Live-proven:**
  - the panel sits immediately right of the native details panel;
  - it overlaps neither the list nor the details panel;
  - the 3 x 2 grid fits;
  - the selector-only lifecycle works.
- **The icon was still blank.** The log read `Gui.bitmap("mods/skyeshade/hd2runtime_custom_stratagem_panel_proof/images/orbital_gas_barrage",
  3140, 1290, 77 x 77, layer 15)` and `succeeded ... (engine id 15)`: the call was accepted but produced no visible
  pixels.

**The icon: what is established [C]:**
- **The resource is right.** `Gui.bitmap` takes a **material** (by name or `IdString64`), never a texture or sprite. It
  makes a per-GUI instance of it and draws a quad with it (research `bitmapContract`). The custom image provides exactly
  that resource: its GUI icon material, resident, exact, `+4` = 1. The id came back, so the lookup found it.
- **The material's shader is opaque offline.** What the material draws is decided by its shader, `0x3461FF0D`, the
  vanilla stratagem icon material template. That shader is in none of the 886 shader libraries in the installed data
  (neither is the engine font material's `0x51C11754`), so its passes, constants and texture use cannot be read offline
  (research `iconShader`).
- **The image itself is fine.** The texture's header is byte-identical to a vanilla icon texture's and every mip level
  decodes, so missing pixels are not a texture defect.
- **Not established:** why a material accepted by `Gui.bitmap` draws nothing visible. The likely class of cause is that
  the icon shader is made for the game's own UI, which feeds it per-draw values (tint, UV rectangle) that a plain screen
  GUI does not set. The 0.3.0 VirtualSelectorProof card's visible icon (a red, green and yellow test pattern) is the
  one observation against that.
- **The format is unchanged** (`presentation_icon` keeps it). If the live diagnostics show that vanilla icon materials
  are also blank while the font material draws, the next step is a separate Runtime "GUI image" resource type: a
  material on a GUI bitmap shader, decided from what the diagnostics show. It does not replace the icon family.

**The icon diagnostics (F8, 0.4.0):**
- **Row 1:**
  - `A font`: the engine font material by name; it draws all the panel's text, so it is a known-good control;
  - `A vanilla`: the vanilla 120mm icon material by hash;
  - `B name` / `B hash`: the custom material by name and by hash;
  - `C texture`: logged as not drawable.
- **Row 2, `D`:** the custom material at 38, 51, 80 and 119 units.
- Each cell is drawn over a dark | light split, so black and invisible can be told apart.
- **Each cell logs:** its resource, whether its material and texture are loaded, the material's shader, its texture
  slot (and what it resolves to), and the bitmap's creation result. Bitmaps are retained, so no update is made.
- **The icon never blocks the tile:** an unavailable or refused icon draws a `?` and is logged.

**Mouse input [C]** (research `mouse`):
- The engine has a Win32 mouse device. `stingray.Mouse` has `axis` / `axis_index` (`cursor`), `button` /
  `button_index` (`left`), `pressed` and `released`.
- Its cursor axis is the device's stored integer position. Whether its y is flipped to the GUI's bottom-left origin is
  not established (its writers are indirect and the executable's imports are hidden).
- **So the panel reads the OS cursor through the Runtime input module.** That is the mechanism the keybinds already use
  (`GetCursorPos`, `ScreenToClient`, `GetClientRect`, `GetAsyncKeyState`, only while the game window has the focus).
  It converts client pixels (top-left) to GUI pixels (bottom-left), scaled to `Gui.resolution`.
- The engine's own `Mouse` reading is logged beside every click (research only).
- **Nothing is consumed:** the game still receives the click, and the native UI capturing the mouse does not hide the
  OS cursor.

**Interaction (0.4.0):**
- **Hover:** while the cursor moves, the tile under it is focused (brackets and tooltip), and leaving all tiles clears
  the focus. Keyboard focus (F6) stays until the cursor moves.
- **Click:** a left press over a tile selects it; holding the button does not repeat.
  - A placeholder is refused.
  - A click in the panel between tiles is logged.
  - A click outside the panel is ignored.
- **Before the write:**
  - the panel checks that the selector is still open for the slot it opened on;
  - `stratagem_selector.select` then re-checks the rest: aboard the ship, the screen open, the selection open for a
    slot 0-3, the local record bound to the panel, solo, not ready, the token selectable.
  - It then makes the existing guarded write. The game's own repaint updates the slot, and the identity is recorded.
- **Ctrl+F7** restores the slot within the same visit.
- **Persistence:** the identity follows the loadout (`stratagem_selector.track`), and the saved order reconstructs it
  (`stratagem_selector.reconstruct`; the proof logs it every second aboard the ship).

**Presenting the token as the custom stratagem: research only (not implemented).** The four presentation fields are
StratagemInfo row members of Precision Strike, so a temporary change reaches every reader of that row on this machine:

| Reader | Effect |
| --- | --- |
| Native picker | Precision Strike's own card would show the custom name and icon. A player choosing the real Precision Strike would see Orbital Gas Barrage |
| Native details panel | Shows the custom name and description whenever Precision Strike is focused |
| Loadout slots | Every slot holding Precision Strike, including other players' panels on this screen. The widgets are built when the loadout screen opens, so a change made while it is open shows after reopening |
| Mission HUD | Built once per mission from the slot's type. With the mission-time conversion the slot becomes the 120mm carrier, whose presentation is already the custom one. Without it, every Precision Strike slot would show the custom presentation |
| Other players | Unaffected: presentation is local, and their game reads its own row |
| Mission-end UI | Its readers are not traced |

Changing Precision Strike's presentation would therefore relabel the vanilla stratagem as well, not just the virtual
slot. It is only safe as a separate proof that applies it while the virtual slot holds the token and restores it
around every native picker visit. The custom panel already supplies the custom presentation in the loadout, and the
carrier supplies it in the mission.

**Validated offline:**
- `tests/test_custom_stratagem_panel.py`:
  - the mouse read, conversion (1080p client on a 4K GUI, origins) and hit test;
  - hover focus and clear, placeholder focus;
  - clicks: placeholder refused, between tiles, outside the panel, a held button counted once;
  - a click on Orbital Gas Barrage writing Precision Strike into slot 1, repainted, identity recorded, reconstructed
    from its order, and still after another slot changes natively;
  - a stale selector slot refused;
  - the icon fallback marks and logs;
  - the diagnostics' nine cells and their logs;
- earlier: the lifecycle, placement and legacy fallback.
- **The built runtime ZIP:** scenario `proof-custom-stratagem-panel` (0.4.0) runs the proof from the archive:
  - the saved loadout is read with no virtual slot;
  - the panel, tooltip, the nine diagnostics against the real snapshot's residency;
  - the mouse conversion and hit test;
  - 0 writes, since nothing can be selected without a loadout screen.

**Validated offline:**
- The selector tests run on a stand-in engine with the engine's own types: callable `Vector2` / `Vector3` tables and a
  `Color` function. They cover:
  - creation as the reference does it;
  - `Vector3` positions, `Vector2` sizes and `Color` colours;
  - the overlay's rectangle, image and text, and its clean removal;
  - refusals before anything is created (an icon or font not loaded, a non-callable constructor, the world gone);
  - every invalid value stopped before the engine;
  - a failing call closing the GUI.
- The built runtime ZIP runs the proof from the archive. Its drawing proof issues the screen GUI, rectangle, icon and
  text against the real snapshot's font residency and the seeded icon, then destroys the GUI. 0 writes.

### The 0.4.0 live test, continuous selection, slot-local icons and the icon colours (0.5.0)

**0.4.0 live test (2026-10-02):**
- **Live-proven:** Orbital Gas Barrage was selected from the panel into slot 0. The guarded loadout-record write put
  the Orbital Precision Strike token in the slot, and the game repainted it.
- **Failed by design:** a second selection was refused, `ALREADY_SELECTED: a virtual selection is already written`.
  0.4.0 kept a single virtual selection.
- **The icon was still invisible.** The F8 diagnostics showed:
  - the custom material and texture loaded;
  - shader `0x3461FF0D`;
  - `Gui.bitmap` creating the bitmap at every size.

  The diagnostic rectangles showed only that the primitives were created.

**Selection semantics (0.5.0):**
- **Several instances.** The Runtime keeps a slot-indexed collection, `stratagem_selector.virtual_slots()`:
  `{slots = {[slot] = {definition, token, type}}, pairs}`.
  - Several slots may hold one definition: the definition is shared, the slot identity is separate.
  - There is no singleton refusal.
- **Replacement.**
  - An occupied slot is replaced through the same guarded write.
  - A slot that already holds the token needs no write and becomes (or stays) virtual.
  - Ctrl+F7 undoes the newest selection only, and gives the slot back its previous virtual state.
- **Following the loadout.**
  - A native change to a virtual slot makes that slot plain.
  - A removed entry (the game compacts the record) moves the later virtual slots down.
  - Any other change of length drops them (never guessed).
- **Reconstruction.** `stratagem_selector.reconstruct(saved)` returns every virtual slot of the recorded order, so
  duplicates stay separate. The save holds only vanilla tokens.
- **A new guard: the slots on screen must mirror the record.** A native pick into a later slot with an empty one
  before it leaves a gap on screen until the next repaint, so a write by record index would land in another slot.
  Refused with `SLOTS_DIFFER`.

**Moving the selection on [C]** (research `selectionAdvance`, `selectionClose`):
- **What the native pick does.**
  - It searches the four slot **widgets** from slot 0 for an empty one (`0x146E619`..`0x146E660`). A widget whose flags
    (`+0x1288`) have bit 2 is skipped; empty means type 0 or above 149.
  - When it finds one, it moves the panel focus through the native setter `0x1895770` (the highlight is applied inside
    it) and writes the edited slot `ui+0x281C` (`0x146E6D4`).
  - Otherwise it calls the close handler.
  - Both paths re-grey the native grid (`0x18D1890`).
- **Nothing reads `ui+0x281C` each frame:** only a pick and the open handler. One guarded u32 write therefore moves the
  open selection on, and the next pick (native or Runtime) lands there.
  - The Runtime searches only the slots after N (never wrapping), with the native rule.
  - It refuses when:
    - the selection closed or moved meanwhile;
    - the panel mode is 1 (a native pick there always closes);
    - the slots have a gap;
    - the player is ready, launched or not solo.
- **Not moved by that write:**
  - the slot highlight, which only native calls apply;
  - the grid's greying.

  The Runtime's cleared cached record pointer also makes the repaint take its first-bind branch, which moves the local
  panel's focus to slot 0 (`0x18963EF`).
- **The selection cannot be closed by data.**
  - The close handler hides the grid, the details panel and the highlight through element calls.
  - Nothing per frame follows the selection byte.
  - The input action states are cleared and recomputed from the devices every frame before the screen reads them
    (`0x12FA0A6`), so a Back cannot be injected.
- **So when the loadout is full:** the panel closes and stays closed until the selector closes, and the player closes
  the native selector with Back.

**Slot-local loadout icons [C]** (research `slotIcon`; `runtime/stratagem_slot_icons.lua`). **Since 0.7.0 this is a
documented fallback only:** virtual slots show their icon through the slot overlay (below, "Slot icon overlays in the
custom stratagem system"), which never writes the native slot. Nothing starts these writes by default.
- **Every repaint resets every slot icon.** Each slot widget's icon element (widget `+0x380`, an image element) gets
  the type's icon whenever the widget takes a type, with no early return (`0x1893650` -> `0x1450160`).
- **What the image setter does:**
  - copies the atlas sprite's rectangle into `+0x134`;
  - stores the name at `+0x150`;
  - binds the sprite's page texture into the element's own material, an engine call (a render command);
  - computes the UV (`+0x124`).
- **The scene update** pushes a dirty element's (bit 1; ancestors bit 3 through `+0xF0`) material and UV to its GUI
  primitive.
- **An icon on the SAME atlas page can therefore be shown in one slot by data.** The Runtime writes the borrowed
  sprite's rectangle and UV (in single precision, as the setter computes it) and sets the dirty bits exactly as the
  setter does.
  - It re-applies after each repaint.
  - It puts the token's rectangle back when the slot stops being virtual.
- **Example.** Orbital Gas Strike's icon (`0x78F1E50B852CFB79`) and Orbital Precision Strike's (`0x53031033EE7A60E3`)
  are both on page `0x5207684C3952B0CC`, with colour set 0, on all seven snapshots.
- **A definition opts in** with `display.slot_icon = 'Orbital Gas Strike'`, a vanilla stratagem.
- **Checked before every write:**
  - the selector's pins;
  - solo;
  - the widget holding the token;
  - the element an image whose name is the token's icon and whose rectangle is the token sprite's;
  - both sprites on one page with one colour set;
  - private read-write memory.
- **No StratagemInfo write:** a native Precision Strike slot keeps its icon.
- **Blocked: the custom image itself.** Binding a texture of its own needs the engine's texture bind, a native call.

**Why `Gui.bitmap` drew nothing, and the fix [C]** (research `iconShader`, `iconColours`, `iconMaterialApi`):
- **The shader is readable after all.** The icon template `0x3461FF0D` is in shader library `0x8CDE642487327D4E`, in its
  GPU part (the earlier search read only the 4-byte main parts).
- **It treats the texture's channels as masks.**
  - R, G, B and A are multiplied by the strengths `c0.x`..`c3.x`.
  - They are coloured `c0.yzw`..`c3.yzw` (a cbuffer of the material instance), stacked R over G over B over A, times the
    vertex colour.
- **The icon material declares no variables, so they are zero and every texel is transparent.**
- **`Gui.bitmap`'s id proves nothing:** it returns one even for a material that was not found (a null material).
- **What the native loadout slot sets** on its element's own material copy (`0x1893669`..`0x18936BF`):
  - `c0` = the category colour of the type's colour set (StratagemInfo `+0xB8`, table at game `+0x331B610`): orbital
    `(0.8, 1.0, 0.431, 0.357)`;
  - `c1` = `(1, 1, 1, 0.933)`;
  - `c2` = `(0.2, 0, 0, 0)`;
  - `c3` is never set.
- **The Runtime now does the same through the exposed Lua API:**
  - `Gui.material(gui, name)` returns the GUI's own instance, through the same per-GUI lookup as `Gui.bitmap`;
  - `Material.set_vector4(instance, 'c0', Quaternion.from_elements(...))` sets each variable through the setter the
    game uses.

  Both are guarded (`engine_gui` `screen.material` / `screen.set_vectors`): a NULL instance is refused, and they are
  used only after a successful bitmap of a resident material.
- **A picture drawn this way keeps its shapes but comes out in mask colours:** red parts in the category colour, green
  parts white, blue parts as a light shadow.
- **True colour would need another material template.** `0xBA25DE35`, used by 702 vanilla GUI materials, outputs the
  texture's RGBA. That would be a separate Runtime resource type, not a change to the icon family.
- **Not explained:** the VirtualSelectorProof 0.3.0 icon that did show. Nothing sets these variables on a Runtime GUI;
  the 0.5.0 diagnostics (row 1 coloured, row 2 plain, with that same test pattern) decide it.

**Validated offline:**
- **`tests/test_stratagem_selector.py`:**
  - four identical instances;
  - replacement, including of the native Precision Strike slot (no write);
  - mixed native and virtual Precision Strike slots;
  - reconstruction of three instances;
  - following a native change and a compacted record;
  - undo of the newest selection;
  - the advance to the next empty slot (one write), the full loadout left open, the guards;
  - the gap refusal.
- **`tests/test_stratagem_slot_icons.py`:**
  - the borrowed icon on a virtual slot only, a native slot of the token untouched;
  - re-application after repaints;
  - restoration;
  - refusals: another page, another colour set, changed atlas data, no slot icon;
  - the single-precision UV.
- **`tests/test_custom_stratagem_panel.py`:**
  - the continuous four-slot selection, with the panel following and closing when full, then reopened;
  - the native colours set on the tile icon's instance, and a NULL instance never used;
  - the coloured and plain diagnostics with the test pattern.
- **The built runtime ZIP:** scenario `proof-custom-stratagem-panel` (0.5.0), against the real snapshot:
  - the 230 pins proven;
  - the colours read from game.dll;
  - both slot icons found on one atlas page by the Runtime's own lookup;
  - the panel, its icon colours and the diagnostics;
  - 0 writes (no loadout screen in any snapshot).

### The 0.5.0 live test and moving the native slot highlight (SlotHighlightProof 0.1.0)

**0.5.0 live test (2026-10-02).**
- **Live-proven:**
  - the virtual-selection write;
  - several virtual instances;
  - the per-slot borrowed icon (virtual slots show Orbital Gas Strike's icon, native Precision Strike slots keep theirs);
  - saved-order reconstruction.
- **Failed:** the advance. The Runtime moved the edited slot (`selector moved from slot 1 to slot 2`), but the native
  slot highlight stayed where it was, so the Runtime's edited slot and the visible native state diverged.

**The highlight, traced [C]** (research `slotFocus`; P = the local panel, `ui+0x595F0`; W = a slot widget,
`P+0x8EC0+k*0x12A8`):

| State | Field | Read by |
| --- | --- | --- |
| Visual highlight / widget focus | `P+0xD96C` (focused slot), `P+0xD970` (previous) | the focus setter `0x1895770`, the repaint's first bind, the per-frame sub-state (`0x1468748`), the details item, the open handler (which copies it to the edited slot), the panel navigation |
| Per-widget focus | `W+0x1288` bit 1 (bit 0 hover, bit 2 disabled, bit 3 selection open) | only the widget visual update `0x18932F0` and the setter |
| Actual edit slot | `ui+0x281C` | only a pick and the open handler |
| Hover | `P+0xD968` | per-frame hover; a mouse Select |
| Active panel group | `ui+0x2739C8` (0: the local one, groups of `0x1EE18` bytes) | the per-frame update |
| Grid focus | the stratagem grid's own cursor (`0x18D5A90`) | the grid |
| Loadout record | the local record | the save and the repaint |

**How it is drawn.**
- `0x18932F0(W)` is a pure function of W's flags. It sets the frame element `W+0x798`: colour, opacity, thickness `W+0x1118` (focused 3) and gap `W+0x111C` (focused 0, unfocused 16), and its bars. It also sets the opacity of `W+0x5E8` and `W+0x1130`.
- It runs only when called: nothing redraws the highlight per frame.
- The element setters store the value, mark the element and its ancestors dirty, and cancel a running tween on that property. The per-frame tree update and the scene push consume the marks; the values persist.

**How the game moves it.**
- **The focus setter `0x1895770`** stores the focus pair, clears bit 1 on the old widget and sets it on the new one, and calls `0x18932F0` on both.
- **Its native callers:**
  - the panel navigation `0x18950B0`: Left, Right, Up and Down, with a sound;
  - a mouse Select;
  - the pick moving on (`0x146E6CF`, then the edited slot);
  - panel resets.

  No network call is involved.
- **The repaint's first bind (`0x18963B5`).** It follows the Runtime's cleared cached record pointer. It inlines the same logic but always forces slot 0, so pre-setting the focus is useless.

**The data path [C].** Every frame in panel mode 0, the panel update (`0x189B9CB` -> `0x18999F0` -> `0x1899CD0`) handles the end of a frame flash. For each slot widget whose byte `W+0x12A0` is set and whose frame has no colour tween running, it clears the byte and calls `0x18932F0(W)` itself (`0x1894C30`..`0x1894C57`). A flash (`0x18939B0`) is the only other writer of that byte. So one guarded transaction moves the highlight, and the game's own code redraws both widgets from their flags:
1. the focus `P+0xD96C`: N -> M;
2. the previous focus `P+0xD970`: -> N;
3. W_N's flags byte: bit 1 off;
4. W_M's flags byte: bit 1 on;
5. W_N's flash byte: 0 -> 1;
6. W_M's flash byte: 0 -> 1;
7. optionally (Ctrl in the proof), the edited slot `ui+0x281C`: -> M, so the next pick lands there.

`runtime/stratagem_slot_focus.lua` makes these writes. It refuses, with nothing written, when:
- the code is not the pinned code;
- the loadout screen is not open, the player is not solo, or is ready;
- the panel mode is not 0, the local group is not active, the container is not bound, or the panel is not local;
- a repaint is pending;
- the target is not slot 0-3, is the same slot, or is disabled;
- the two widgets are in different selection states;
- a flash or colour tween is running on either frame.

It then waits for the game to consume both bytes and verifies:
- the focus, flags and both frames drawn as `0x18932F0` draws them;
- the record, the edited slot (unless moved), the selection byte, the slot types and the cached record pointer unchanged.

Bytes not consumed within a second are put back. The flags are written as single bytes; the 16-bit word holds bit 1 in its low byte.

**Comparing the selector on slots 0-3.**
- No retained snapshot holds a loadout screen, so the comparison is code-derived. A native move k -> k+1 changes:
  - `P+0xD96C` k -> k+1 and `P+0xD970` -> k;
  - bit 1 on both widgets;
  - both frames (colour, thickness and gap; with the selection open, the frame and selected-element opacities);
  - the dirty marks.
- It does **not** change the edited slot, the loadout record, the grid focus or the sub-state (recomputed: still 10).
- A live comparison can be captured read-only with the armed snapshot package (`py hd2.py snapshot arm --wait-for-key --repeat`, docs/snapshots.md), with the selector open on each slot.

**The OS input fallback (research only, not implemented).**
- While the stratagem grid is open, the grid's handler consumes the directions. The panel navigation is skipped (`0x189BDEC`), so a synthetic Left/Right moves the grid cursor, not the slot.
- Moving the slot natively would take Back, then Left/Right |M-N| times (disabled slots skipped; past slot 3 is the booster), then Select, which reopens the selection on M. The game would run its own movement, with no Runtime memory write. But it needs frame-paced OS key events that follow the player's bindings and land in the focused game window.
- The input action states are rebuilt from the devices every frame (`0x12FA0A6`), so they cannot be set as data.

**Validated offline:**
- **`tests/test_stratagem_slot_focus.py`:**
  - the highlight moved 0 -> 1 -> 2 -> 3 with six writes each, consumed and redrawn;
  - every other loadout field unchanged;
  - with the edited slot;
  - every refusal writing nothing;
  - unconsumed bytes put back.
- **The built runtime ZIP:** scenario `proof-slot-highlight`:
  - the proof loads from the archive;
  - the 259 pins are proven on the real snapshot;
  - a move without a loadout screen is refused, with 0 writes.

### SlotHighlightProof 0.1.0 live and the integrated advance (CustomStratagemPanelProof 0.6.0)

**SlotHighlightProof 0.1.0 live test (2026-10-02): passed.**
- F7 and F8 moved the native highlight forwards and backwards, and the game redrew it.
- Ctrl+F7 and Ctrl+F8 also moved the effective edited slot, and a native selection then landed in the moved slot.
- The highlight-only move changed no record, slot type, selection state or cached record pointer.

**The integrated advance (0.6.0).** The panel's selection now passes `stratagem_slot_focus.advance` as the selection's
advance; `stratagem_selector.advance` (the edited slot only) is no longer used by the panel.
- **After the guarded record write and the game's repaint,** the next empty slot after the one written (never wrapping)
  gets the native highlight and the edited slot in one slot-focus transaction. The game's panel update redraws it, and
  the panel follows the same slot.
- **The record write's repaint first puts the highlight on slot 0** (its first bind) whenever the focus was elsewhere,
  so the highlight shows on slot 0 for the repaint's frame before the move. Avoiding that would need a different cached
  record pointer value, which needs its own proof.
- **A slot that already held the token is not written,** so there is no repaint; the move starts from the slot as
  opened.
- **Transient refusals are retried for half a second:** a flash still running, a colour tween, or the repaint not yet
  consumed.
- **With no empty slot after it:**
  - the highlight is put back on the slot just written (a highlight-only move);
  - the panel closes;
  - the native selector stays open, to be closed with Back. **Since the selector UX pass (2026-10-04)** the Runtime
    closes it as Back does: see "Closing the native selector when the loadout is full".
- **Ctrl+F7 (undo)** puts the highlight back on the edited slot after its repaint.
- **Unchanged:** the virtual slots, replacement, the borrowed slot icon and reconstruction.

**Validated offline:**
- **`tests/test_custom_stratagem_panel.py`:**
  - four selections in a row, each with the native highlight and the edited slot on the next slot;
  - the flash bytes consumed;
  - the fixture's first bind seen twice;
  - the highlight back on slot 3 when full;
  - a reopened selector on slot 2 that already holds the token: no record write, the highlight following slot 2.
- **`tests/test_stratagem_slot_icons.py`:**
  - replacing Eagle Airstrike in slot 1 with the advance to slot 2;
  - the native Precision Strike in slot 0 keeping its icon next to the virtual slot's Gas Strike icon.

### The 0.6.0 live test and the four open points: closing, sound, the panel icon, a custom icon in a native slot

**CustomStratagemPanelProof 0.6.0 live test (2026-10-02): passed.** All of these held:
- the custom card selects and writes the token into the edited slot;
- occupied slots are replaced;
- several Gas Barrage instances coexist;
- the native highlight and the edited slot advance together, and the panel follows;
- the saved order reconstructs the virtual slots;
- virtual slots show the borrowed vanilla icon while native Precision Strike slots keep theirs.

#### Closing the native selector when the loadout is full [C] (research `selectionClose`, `selectionCloseBlockers`)

**Not possible by data.**
- **The close handler `0x146F3B0` is called only by:**
  - a pick (no empty slot left);
  - Back;
  - the open handler (an empty grid);
  - launch;
  - two handlers reached from network-message dispatch.
- **Its effects that no per-frame code reproduces from data:**
  - it slides each panel back with pool tweens (`0x189E2F0(P, 0)`); the latch `P+0x1EE11` is read per frame only as a
    parameter;
  - it clears the grid list, releasing resource handles;
  - it fades the grid with a tween.
- **The only per-frame paths that close it** are launch and deploy, which are forbidden.
- **A partial data close is worse.** Clearing the selection byte leaves the grid drawn and frozen, and Back then leaves
  the whole screen.

The behaviour therefore stays as it is: the custom panel closes, the native selector stays open, and the player presses
Back. A synthetic Back key would make the game run its own full close; it is not implemented.

**The game's own close, called (selector UX pass, 2026-10-04; offline only, awaiting a live test)** (research
`selectorClose`; `stratagem_selector.close_native`). Closing is still not possible by data, but the close handler itself
can be called as the game calls it:
- **What Back and a full pick do.** Back on a focused stratagem slot (sub-state 10, `0x146E963`) posts the
  picker-close sound and calls `0x146F3B0` with the loadout UI (`0x146E968..0x146E975`). A pick that leaves no empty
  slot does the same (`0x146E665..0x146E672`). In both, the UI is the handler's first argument kept in `rdi`
  (`0x146E0B6`).
- **The handler.** It has one argument, the loadout UI (kept in `rsi`, `0x146F3D1`), and returns nothing (`0x146F503`).
  It:
  - copies `ui+0x273992` to `ui+0x273991` and clears the selection byte `ui+0x273990` and the sub-state `ui+0x2818`;
  - hides the grid (`0x18DBFF0(ui+0xD2850, 1)`);
  - clears the card list (`0x18D27B0(ui+0xD2F20)`: row count `+0x91F14` and card count `+0x92984` become 0);
  - clears widget flag bit 3 on the four slot widgets and redraws them (`0x18932F0`);
  - slides each panel back (`0x189E2F0`, `0x189CEB0`, `0x1898AB0`).
- **The Runtime's call.** `runtime.native_selector_close(entry, ui)` is a typed `void (*)(void *)` call in
  `runtime/windows_write.lua`. Its only caller is `stratagem_selector.close_native`, reached only from the panel's
  advance (`stratagem_slot_focus.advance`) when a Runtime selection leaves no empty slot:
  - the selection filled the last empty slot;
  - or it replaced a slot of a full loadout (the slot already holding the token included).

  It is exactly what Back does: the picker-close sound, then the call. Nothing is patched or hooked, and nothing is
  written by the Runtime.
- **Guards (refused with nothing called; the native selector stays open for Back):**
  - an adapter that can call game functions;
  - inside the Runtime's own update;
  - the selector's pinned code (19 close pins: the handler, its effects and both callers);
  - the handler's exact first 49 bytes, re-proved before every call;
  - aboard the ship;
  - the same loadout screen, its selection still open for the slot the selection was made in (selection byte set,
    sub-state 10, that edited slot);
  - not ready or launched; solo; panel mode 0;
  - the panel bound to the local record and the slots showing it;
  - the record full, with the selection's token in its slot.
- **Verified:**
  - **at once:** the selection byte cleared, the sub-state 0, the card list empty and every slot unchanged;
  - **over the next frames:** the selection stays closed on the same screen with the same slots.

  A call that leaves the selection open is reported (`NOT CLOSED`) and never taken for a close.
- **The log** names each outcome:
  - `stratagem selector SELECTOR CLOSE VERIFIED: the native selector (open for slot N) closed by the game's own close
    handler (game+146F3B0, the call Back makes) ...`;
  - `SELECTOR CLOSE REFUSED (nothing called; the native selector stays open: close it with Back): <code>: <reason>`.
- **Offline:** `tests/test_stratagem_selector.py` (every guard, the call, the verification, a call that changes
  nothing), `tests/test_custom_stratagem_panel.py` (filling slot 3; replacing slot 2 of the full loadout; a refused
  close) and `tests/test_ui_sound.py` (the pick sound, then the picker-close sound, then the call).
- **Live: not yet tested.** That the grid and the details panel slide away exactly as after Back needs the game.

#### The selection sound [C] (research `uiSound`; `runtime/ui_sound.lua`; SelectionSoundProof 0.1.0)

- **How the screen posts sounds.** The loadout screen posts them through `0x1327F50(key)`. The key is remapped to a
  Wwise event id (the `hash_lookup` resource) and posted on the WwiseWorld of the "Game World"
  (`[[game+0x3326340]+0x10F8]`; the world itself at `+0x10E8`, the first of `Application.worlds` in every snapshot).
- **Which events a selection posts:**
  - a pick filling the last slot posts the picker-close event (`0x97753411` -> `0x0DBB2A14`) before closing, and Back
    posts the same;
  - selecting a loadout slot (the grid opening) posts `0xA31D0645` -> `0x3C38FC71`;
  - a pick that leaves an empty slot posts no sound of its own; a panel transition after it may, but its ids are
    data-driven and not read offline;
  - **every pick** first posts the pick event (`0xBE9303B7` -> `0x6A84A787`): the card list posts it when it accepts a
    card (`0x18CFDD3`), before it reports the pick (selector UX pass, 2026-10-04).
- **The remap is read in every snapshot.** The key-to-event table (`game+0x346C9F8` slots, `+0x346CA00` capacity,
  `+0x346CA04` the empty key, `+0x346CA08` the multiplier) gives the same three event ids in all seven (research
  snapshots `uiSoundRemap`).
- **The Lua path.** The Wwise plugin registers `stingray.Wwise.wwise_world`, `has_event` and
  `stingray.WwiseWorld.trigger_event(wwise_world, name)`. That posts the FNV-1 (lower-case) hash of the name exactly as
  the game posts its ids, so `hd2runtime_bci6lee`, `hd2runtime_bgj4s6o` and `hd2runtime_u64dawv` (the pick) post the
  game's own events. The events' real names are not in the game data.
- **Guards.** The plugin checks no arguments, so `ui_sound.play` posts only:
  - on the world value at the game's own Game World's position in the engine's world array. `Application.worlds`
    lists that array in order (`0x3F821F`..`0x3F8277`). **Corrected during the slot overlay research:** worlds are
    full userdata, so their printed address is not the World pointer. The runtime handed out with SelectionSoundProof
    0.1.0 matched by that address and therefore refuses every post (`NO_WORLD`). The proof needs the current runtime;
  - when `has_event` is true;
  - aboard the ship.
- **Still unknown:** which event the player hears as "the selection sound". SelectionSoundProof plays each one on a
  key for a listening test. The custom panel stays silent until then.
- **Since the selector UX pass (2026-10-04)** the custom panel plays the pick event after every successful selection
  (`stratagem_selector.select`'s `opts.sound`; the panel's `sound` option, on by default). When the selection leaves no
  empty slot, the picker-close event follows with the close, as Back posts it. A refused post is logged
  (`sound stratagem_pick not played: ...`) and changes nothing else. Live: not yet heard.

#### The panel icon: the game's mask convention [C] (research `iconShader`; PanelIconProof 0.1.0)

- **How the icon shader draws.** It colours the texture's channels as masks: R with `c0` (the category colour), G with
  `c1` (white), B with `c2` (a shadow). R is drawn over G over B, and 0 is transparent.
- **The game's own icons are made that way.** The 120mm icon has its red globe in R, its white shells in G, B at 0 and
  the background at 0.
- **Why the 0.6.0 tile looked wrong.** `orbital_gas_barrage.png` is a full-colour picture, so its white parts also light
  the red mask on top. The offline shader model (`tests/test_icon_masks.py`) shows it drawn almost entirely in the
  category colour.
- **The fix.** `sdk/tools/hd2_image.py` `icon_masks` / `icon_mask_shares` convert a red-and-white picture: each pixel is
  unmixed against dark, red and white reference colours by least squares, the red share going to R and the white share
  to G. `orbital_gas_barrage_masks.png` was converted from the full-size source by `prepare_icons.py --mask`; the
  original is unchanged.
- **Previews.** The shader model draws the masks as the intended red-and-white artwork on a transparent background:
  `build/test-artifacts/panel-icon-previews/`.
- **The format is unchanged.** It is the same texture and material format; only the pixels follow the game's
  convention.
- **Next step for authors:** let a mod provide a normal picture and have the build generate the masks.

#### A custom texture in a native slot [C] (research `slotTexture`; SlotTextureProbe 0.1.0, read only)

- **The texture is not in any main-thread field.** Binding a slot icon's texture is a native call (material API +0x78).
  It stores {property, resource} in the material's CPU list, which later clones copy but no draw reads, and queues
  render command 7.
- **What the render thread does.** It stores the texture's render handle `u32 [resource+0]` into the render-side
  material object `R+0x48[k]` (`0x4F4713`, no dirty flag), and every GUI draw reads it there (`0x4FD555`).
- **The custom image in one slot would therefore need a write into render-thread memory** that the render thread reads
  concurrently. The atlas sprite rectangle trick works only within the bound page.
- **Swapping the element's material pointer is rejected:**
  - every repaint would bind the token's atlas texture into the foreign instance;
  - the native GUI would keep a raw pointer to it;
  - the slot's own clone would be orphaned.
- **The chain is probed read-only first** (`runtime/stratagem_slot_texture_probe.lua`):
  1. the slot element's own clone M and its render handle;
  2. its world interface;
  3. the render world (checked by its vtable and back-link);
  4. the render world's index and object tables;
  5. the render-side material R (checked by its vtable, kind 7, shader and template);
  6. the image property's index and the handle the slot draws with;
  7. for comparison, the handles of the sprite's atlas page and of a custom texture.
- **The borrowed same-page icon stays the data-only option** until a render-side write is proven safe.

**Validated offline:**
- **`tests/test_icon_masks.py`:**
  - the unmixing;
  - the converted icon follows the vanilla convention;
  - through the shader model the masks draw red and white and the original does not.
- **`tests/test_ui_sound.py`:**
  - the names hash to the native ids;
  - a post only on the Game World's WwiseWorld;
  - every refusal posting nothing.
- **`tests/test_slot_texture_probe.py`:** the chain resolved, every link checked, nothing written.
- **`tests/test_custom_stratagem_panel.py`:** the Runtime never writes the selection byte when the loadout is full.
- **The built runtime ZIP:**
  - `proof-panel-icon`: the masked icon with the native colours read from game.dll;
  - `proof-selection-sound`: the Game World read from game.dll, posting only on it;
  - `proof-slot-texture-probe`: no loadout screen, nothing read further;
  - all with 0 writes.

### Slot icon overlays: a Runtime GUI over the native slot icons [C] (research `slotOverlay`, `worldOrder`; SlotOverlayProof 0.1.0)

**The aim:** show the custom Orbital Gas Barrage icon on a virtual slot without touching the native slot. That means the
four loadout slots aboard the ship and the mission HUD's stratagem list. The native Precision Strike icon stays as it
is, and nothing is drawn into the native picker.

**Where the slot icons are drawn.**
- **Neither the ship slots nor the mission HUD's stratagem list is Noesis.** Both are the game's own element primitives
  in engine screen GUIs of the Ui World. That world is `[[game+0x3326340]+0x1118]`, `worlds()[2]`, rendered through its
  viewport at `0xAB7B18`.
- **The ship loadout.** The four slot widgets are in scene 3, with the slot icon at layer 14 (`0x1893095`). The icon
  element is the slot widget + `0x380`.
- **The mission HUD.** The stratagem list is in scene 5, with the icon at layer 557. Its chain is the UI root
  `[game+0x346D538]` + `0x24E340` + `0x146DC0`, then entries from + `0x1150`, `0x3760` bytes each. Entry k holds the
  record entry it shows at + `0x3748`, its widget at + `0x7C0`, and the icon element at widget + `0x518`. It is shown
  while the game mode `[[game+0x3326340]+0xAC21C]` is 4.
- **This is the live-proven calldown HUD list.** The HUD root, list, stride and index are exactly those of
  `domains/stratagem_calldown.lua` `hud`; `tests/test_stratagem_slot_overlay.py` checks it.

**The order.**
- **A GUI in `main_world` is under the whole UI.** `Application.main_world` is the Game World (correction 5 above).
- **Inside one world, every GUI's primitives are depth-sorted together by layer** (correction 1 above).
- **So a Runtime screen GUI opened in the Ui World draws over the slot icons.** Its layer must be above the slot parts
  (12–16 aboard the ship, 557 in the HUD) and below the HUD's 950–953 and the native 991–1018. It still draws under
  Noesis.
- **The overlay uses layer 940.** Layers above 1023 wrap and draw near the bottom, so `engine_gui` refuses them.
- **How the Ui World is found.** Lua sees worlds as full userdata, so they are matched by position.
  `Application.worlds` lists the engine's world array in order:
  - the application `[exe+0x1A10208]`;
  - its count at + `0x590`;
  - its array at + `0x598`.

  `stratagem_slot_overlay.world_value` reads that array and finds the Ui World's index in it. It uses the value only
  when `Application.worlds` lists exactly as many worlds.

**The geometry.**
- **The overlay quad.** The overlay is drawn on the quad the native GUI draws for the icon element: the element's
  laid-out size (+`0x24`) through its world transform (`m00` +`0x64`, `m22` +`0x8C`, `tx` +`0x94`, `ty` +`0x9C`; GUI
  pixels, bottom-left origin).
- **The quad is refused when:**
  - it is rotated (`m02` / `m20` not 0);
  - the native primitive does not exist (+`0x110` = `0xFFFFFFFF`);
  - the native effective alpha (+`0x54`) is 0.
- **It follows the native icon every frame.** A move or fade updates the same bitmap (`Gui.update_bitmap`), and the
  overlay's alpha is the native icon's.

**One overlay per virtual slot.** `stratagem_slot_overlay.follow` draws every target its caller returns in one GUI,
one bitmap each. When the target set changes, the GUI is recreated. A slot that stops being virtual loses its overlay
on that very tick, and with no targets the GUI is destroyed.

**The custom art.**
- **The icon.** The overlay is the masked Gas Barrage icon (`orbital_gas_barrage_masks`, the game's mask convention).
- **Its colours.** They are set on this GUI's own material instance, coloured as the native slot colours the Orbital
  Precision Strike (its colour set, read from game.dll).
- **Optional backing plate.** An opaque plate one layer below covers the native icon where the custom art is
  transparent. Without it, the native Precision Strike art shows through those areas.

**The native slot is only read.** The overlay never writes:
- the slot's type;
- its icon element;
- its material or texture;
- the HUD entries.

`selector.prove` checks every pin, the overlay chain included, before any read.

**The fallback through main-thread data: none with custom art.**
- **The slot widget's other elements.** The frame, the selection element and the flash are rewritten by the game's
  widget visual update (`0x18932F0`) from the focus flags.
- **No element can show a texture its material was not bound to.** Binding a texture is a native call that the render
  thread completes (`slotTexture`).
- **The data-only decoration that exists** is the borrowed same-page vanilla icon (`stratagem_slot_icons`), which
  shows vanilla art only. Nothing new was written for the fallback.

**SlotOverlayProof 0.1.0 (visual only):**
- **The fake identity.** A fake virtual slot identity is the proof's own table. It is never the selector's virtual
  slots, so no selection, saved order or mission conversion sees it.
- **Keys:**
  - F5–F8 toggle slots 0–3;
  - F9 sets virtual / native / virtual / native (pressed again, it clears all);
  - Home toggles the backing plate (off by default);
  - End prints the status.
- **Aboard the ship** it overlays the loadout slots.
- **In a mission** it overlays the HUD entry showing that loadout slot: the slot-th non-granted record entry. The HUD
  entry must show the same stratagem type.

**Validated offline:**
- **`tests/test_stratagem_slot_overlay.py`:**
  - the research pins and the HUD chain equal to the calldown list;
  - the GUI opened in the Ui World (never `main_world`), the bitmap at the icon quad and layer, and the colours on its
    own instance;
  - nothing written and the native slot bytes unchanged;
  - moves and fades followed by updates;
  - each slot 0–3, then virtual / native / virtual / native;
  - removal on the tick a slot goes native;
  - the backing plate;
  - every refusal: not drawn, transparent, rotated, the world lists differing, the Ui World missing, the image not
    loaded, the pins not proven;
  - the mission HUD mapping, with a granted entry skipped, a type mismatch refused and the HUD not set up.
- **The built runtime ZIP** (`proof-slot-overlay`), against the real snapshot:
  - the Ui World found at its position in the snapshot's engine world list;
  - the Precision Strike's colours read from game.dll;
  - the mission HUD refused aboard the ship;
  - the proof's keys pressed through the input backend: nothing drawn with no loadout screen open;
  - 0 writes.

**Not proven offline (live test):**
- that the overlay is actually visible above the slot icons. The depth sort is read from code, but no snapshot holds a
  loadout screen.
- that the loadout slots' primitives and alpha hide the overlay when the loadout screen is not shown.
- the HUD overlay in a mission.

**SlotOverlayProof 0.1.0 live test (2026-10-02): passed** (`schemas/live_evidence.json`, family
`stratagem_slot_overlay`).
- **Live-proven:**
  - the Ui World GUI at layer 940 renders above the native slot icons, aligned with them;
  - the native icon stays untouched, and no render-thread texture write is needed;
  - each of the four slots, virtual / native / virtual / native, and several overlays at once;
  - removing a fake identity removes its overlay;
  - the overlay follows the slot geometry;
  - the masked Gas Barrage icon is recognisable.
- **Observed:** without a backing plate, the native Precision Strike art shows through the custom icon's transparent
  parts.
- **Not reported:** the backing plate, the loadout screen closing, the mission HUD.

### Slot icon overlays in the custom stratagem system (0.7.0) [C] (research `slotBackground`; CustomStratagemPanelProof 0.7.0)

**The native slot is no longer written for a virtual slot.** `stratagem_slot_overlay.virtual_slots`, started by the
custom stratagems panel, draws the overlays from the real virtual slots (`stratagem_selector.virtual_slots`):
- **Which slots get one:** each virtual slot whose widget shows its token. The token is resolved by its stable id, and
  the slot gets its definition's `display.icon`. Every other slot gets nothing, including a natively picked Precision
  Strike.
- **The colours:** the icon shader colours of the token's colour set, as the native slot colours the token
  (`stratagem_selector.icon_colours`).
- **The plate:** one layer below, on exactly the icon's quad, in that slot's own icon-background colour (read live).
- **When nothing is drawn:**
  - when the loadout screen closes, every overlay goes; reopened, they are drawn again from the current state;
  - a slot replaced natively stops being virtual (`stratagem_selector.track`), and its overlay goes on that tick;
  - an undo (`restore`) does the same;
  - a slot that shows another type for a moment gets no overlay that frame;
  - in a mission nothing is drawn.
- **The mission HUD's targets exist but are not activated.** `M.mission_target` places them on the HUD entry at the
  HUD's own overlay layer (`hudOverlayLayer`).

**The backing plate: the native icon background [C].** The slot widget build (`0x1892DB0`) lays out, in the 80-unit
widget, under the icon (`+0x380`, layer 14):

| Element | Layer | What it is |
| --- | --- | --- |
| `+0x110` | 12 | Kind 5 (`0x1892EBA`), at 5, 5 (`0x1892F01`), 70 units square (the icon's own area), grey 36/255 (`0x1892F2F`) |
| `+0x228` | 13 | An image element with the icon material; its sprite `0x6E6A67B944661E66` (set by the local panel repaint, `0x1895E12` -> `0x1893870`) is tinted from the colour-set tables `0x331A9B0` (c0) and `0x331B4E0` (c1) |

- **Kind 5 is a filled rectangle.** The element push dispatches on the kind (`0x144DF3B`: flags >> 18); kind 5 goes
  to `0x1444030` (`0x144E0D4`). It creates its GUI primitive through interface `+0x108` (`0x1444144`) with a transform,
  a size and a colour, and no material.
- **The live colour.** An element's effective colour is (a, r, g, b) at `+0x54` (`0x144BEA7`).
- **What the plate reproduces.** The plate takes the grey box's live effective colour, opaque, so the custom art never
  mixes with the Precision Strike art. Where the grey box is not drawn, it takes the native grey and logs it.
- **What it does not reproduce.** The category tint sprite is on a UI atlas page that no GUI material can name (see "The
  native tile's look"), so a virtual slot shows the grey box without the category tint.

**The panel uses the same technique (no separate tuning).**
- **The world.** Every panel GUI is a screen GUI of the Ui World. 0.1–0.6 drew in `main_world`, the Game World, under
  the whole UI composite. That is the likely reason its icon looked darker; this was not measured.
  `world = 'main'` keeps the old path as a documented fallback that is not used by default.
- **The layers.** The panel's layers moved up by 920 into the overlay's band.
- **The tile.** It is opaque. Its icon is drawn by the same `overlay.draw_icon`: the masked icon on the native grey
  plate on exactly its quad.
- **The colours** go through the same `overlay.colour`. The panel tile and the slot overlay get the same `c0`–`c3`
  (checked offline and on the built ZIP); only the size differs.

**The icon resource.**
- The Runtime-rendered icon is `orbital_gas_barrage_masks` (the game's mask convention).
- The author's picture `source/orbital_gas_barrage.png` is kept, unpacked, as the source. The masks are generated from
  it by `prepare_icons.py --mask`.
- The image resource format is unchanged.

**Unchanged:** the selection behaviour (click, replacement, several instances, the highlight and edited-slot advance,
the full-loadout close and Back), reconstruction, and the sound (not identified yet; nothing plays).

**Validated offline:**
- **`tests/test_custom_stratagem_panel.py`** (`VirtualSlotOverlayTests`):
  - virtual / native / virtual / native from real selections, with a native Precision Strike left bare;
  - four instances;
  - plates at the icon quads in the live grey;
  - the panel's and the overlay's colours identical;
  - no Runtime write to an icon element, a background element or StratagemInfo;
  - a native replacement, an undo and a transient type removing the overlay;
  - the screen closing and reopening;
  - the native-grey fallback;
  - nothing drawn in a mission;
  - the `main_world` fallback.
- **The panel tile:** the Ui World GUI, the opaque tile and the plate under the icon.
- **`tests/test_stratagem_slot_overlay.py`:** the shared technique and the follower.
- **The built runtime ZIP** (`proof-custom-stratagem-panel`, against the real snapshot):
  - the panel as a Ui World GUI with the plate and the native colours;
  - an overlay with the same shared functions getting the same colours;
  - the borrowed-icon fallback's atlas lookup intact;
  - 0 writes.

### The native-style panel (0.8.0, 2026-10-06) [C, offline]

**Why it changed.** The user's live r25 report had three parts:
- The panel showed at most six entries. The compact layout was three columns with at most two rows in view, and no
  scroll input was ever wired, so the seventh entry (Pelican Close Air Support) was laid out but never drawn.
- The user asked for a scrollable window like the native list, four cards a row, the native card look, the HD2 font for
  the title at the native list header's size, and the hovered stratagem's description drawn over the native details
  panel "so it feels seamlessly integrated".
- That last request reopens the route the user closed on 2026-10-02, for the details panel only.

**Where it is drawn.** Right of the native details panel, in four columns (`runtime/custom_stratagem_panel.lua`
`native_layout`; the custom stratagems' panel uses `renderer = 'native'`, the compact panel stays the module's default
and fallback):
- **Cards.** Native-sized, 80 units at the native 85-unit pitch, in the native cards' own px per unit.
- **Rows.** Up to six in view. The panel stays above the native squad bars at the screen bottom ("EMPTY SLOT", up to
  about 151 units: the panel's floor is 170) and below the top bar. Its top is at the native list header's level when
  it fits, else raised just enough.
- **Scrolling.** More rows scroll:
  - the mouse wheel over the panel (the engine's `stingray.Mouse` `wheel` axis; the cursor and button of that API are
    already used live);
  - a click on the scrollbar track, a page;
  - keyboard focus (F6), which scrolls to its card.
- **Scrollbar.** A native-style track with its thumb, drawn while there are more rows than fit.

**The card in the native look.** Measured from the native card on the user's screenshot (4K, 2 px per unit):
- a grey 103/255 frame 2 units thick, open in the middle of its left and right sides (a 21-unit gap);
- a translucent inner square at 68/80, and the icon at 51/80 on the slot overlay's plate;
- focused: the same frame in white;
- in a loadout slot: the native equipped look, a yellow 132/121/8 frame, a darker inner square and a dimmed icon. The panel redraws when the selector's picks change: a pick, a native pick over a custom slot, or the selector dropping the last mission's slots. In live r27 the look was computed only when the panel opened, so it showed the previous mission's picks and new picks did not light up;
- unavailable: dimmed, with the warning mark.

**The title.** `CUSTOM STRATAGEMS` in FS Sinclair Medium, centred, at the native list header's cap height (13 units).

**The details overlay.** While a card is focused (hover or F6), its details are drawn over the native details panel
(`draw_native_focus`):
- **The plate.** Opaque, over the panel's interior; the native corner marks stay visible.
- **The text.** The category, name and description where the native panel has them; the two boxes in the user's layout
  of 2026-10-06 (each title inside its box, hanging under the top edge, which starts right of the title):
  - the category line, e.g. `CUSTOM SUPPLY STRATAGEM` for the native `SUPPLY STRATAGEM PERMIT`;
  - the name (FS Sinclair Medium, cap 20 units);
  - the description, wrapped to the panel's width by the glyph advances (FS Sinclair, up to four lines);
  - a STATS box, four rows: CALL-IN TIME, USES, COOLDOWN TIME and CALL-IN CODE, the code in the game's arrows
    (in words when the panel draws in monaco, which has none);
  - an ITEM TRAITS box: `CUSTOM STRATAGEM`, the delivery family, the custom model, the round.
- **The content.** The orchestrator's `panel_details(id)` supplies it. An unavailable entry's description is the reason
  it cannot be picked.
- **The call-in time.** The native panel shows the row's call-in time with the account's ship upgrades (`0x879900`),
  plus the hellpod's travel for a hellpod delivery (`0x6ADB40`). The overlay shows the carrier's own call-in time from
  the catalogue, plus 4.75 s for the expendable, support, pod and sentry kinds, rounded to 0.05 as the native panel
  rounds:
  - every hellpod delivery is the pod `0x73F8498BFFDCF415` (`hellpod/hellpod/hellpod_payload`), and its
    HellpodComponentData gives 4.75 s;
  - the carrier is the one allocated for the pick, else the availability view's; an expendable not picked yet uses
    its carrier weapons' own stratagems when they agree; otherwise `AS ITS CARRIER`;
  - the ship upgrades are the account's and are not read, so this is the base time: the vanilla panel of an upgraded
    account shows less (live: the LAS-98 shows 7.15 s for a base of 3 + 4.75).

**Why it draws above the native panel.** The native details panel is the game's own element primitives in a screen GUI
of the Ui World (research finding 19). Its elements are built by the details class `0x189EB10`, at layers 800 to 803:
the layer setter `0x14491F0` and every immediate passed to it in that class's reach. The overlay's plate and text are
layers 940 to 944, in the same world. That world's primitives are depth-sorted by layer across GUIs, so they draw above
the native panel and below the native 991-1018. This is the slot overlay's live-proven mechanism, on the details panel.

**The fonts (FS Sinclair).** The native UI draws FS Sinclair through its own runtime glyph system: HarfBuzz and the TTF
in package `6728ac296c9eab7b`, with a dynamic glyph cache. The Lua GUI cannot reach that system; `Gui.text` draws only
the engine's distance-field fonts.
- **What the build makes.** `scripts/hd2_font.py` builds Runtime-owned engine fonts in that format from the installed
  game's FS Sinclair and FS Sinclair Medium TTFs: `hd2runtime_fonts/fs_sinclair` and
  `hd2runtime_fonts/fs_sinclair_medium`, each a font, a material and an atlas.
- **The format.** Decoded from `core/performance_hud/monaco` and the game's other engine fonts: a header with the em
  size, the atlas texel size, the distance encoding (-255/64 and 0.4 x 255/64) and the 8-pixel cell padding; then u32
  codepoints; then one 7-float record per glyph (atlas x, y, w, h, the bearing above the baseline, the advance).
- **The atlas.** A true signed distance in all four channels, 0.4 at the edge and 64 levels a pixel, as monaco's
  multi-channel atlas encodes it. Its median and its alpha agree, so monaco's shader draws it unchanged.
- **The material.** Monaco's exact bytes with only its glyph texture renamed.
- **Where they ship.** In the Runtime's own archive, a patch of the boot package (where the game's engine fonts are).
  They load at startup.
- **Metrics.** `domains/ui_fonts.lua` holds the em, cap height and every glyph's advance (the panel measures and wraps
  with them) and the resources' digest; the build refuses other bytes.
- **The fallback.** A role whose font is not loaded draws in monaco, logged once (`title font ... (FS Sinclair not
  loaded: monaco)`).
- **The arrows.** FS Sinclair has no arrow glyphs, so the build draws U+2190 to U+2193 into both fonts: the game's
  stratagem code arrows, a broad triangular head about half their length on a straight stem, a cap height tall
  (`hd2_font.ARROW`, `arrow_polygon`). The font's report lists them as `synthesized`.

**The code check moved forward.** Live r25 also showed the Laser Maxigun as a plain Orbital Precision Strike in the
mission. Its code DOWN LEFT DOWN UP RIGHT is the MG-43 Machine Gun's own code, so every mission refused its slot
(`REFUSED: its code collides with MG-43 Machine Gun`). Two fixes:
- A code equal to any vanilla stratagem's own code is now refused at registration, with that stratagem's name. A weapon
  variant's own row is the carrier and takes the custom code, so its own vanilla code is exempt.
- A carrier weapon is no longer converted for a definition whose slot the mission's code check will refuse.

LaserMaxigunExample 0.1.1 uses DOWN UP UP DOWN DOWN LEFT.

**Validated offline.**
- `tests/test_custom_stratagem_native_panel.py`:
  - seven entries in two rows of four with no scrollbar;
  - thirty entries in six of eight rows, scrolled by the wheel, the track and the focus;
  - the card frames, the equipped and focus looks; the equipped look following the picks (it opens with the last mission's picks, they are dropped, a new pick lights up), with no redraw while nothing changes;
  - FS Sinclair and the monaco fallback;
  - the details overlay's plate and every text; the four stats in order inside the STATS box; the box titles under
    the top edge; the code in arrows, right-aligned with the other values, and in words with monaco.
- `tests/test_weapon_variants.py` `test_the_panel_details`: the stats' order, the call-in time (the carrier weapon's
  own plus the hellpod's 4.75 s), the code's directions, and `AS ITS CARRIER` without a carrier.
- `tests/test_ui_fonts.py`: the format, the atlas encoding, the material, the domain current with the game, and the
  Runtime ZIP carrying exactly those fonts.
- An offline mock-up drew the panel's real GUI calls onto the user's screenshot (`build/model-research/mockup*.png`).

**Live (r27, 2026-10-06): partial.** The cards, the native look and the FS Sinclair title were seen in game with seven entries. The equipped look was stale (fixed offline in r28, not re-tested). The r27 overlay (arrows, call-in time, the user's box layout) was not reported yet.

## The custom stratagem API (0.30.0 development)

The development API built from this document's live-proven parts is `docs/custom-stratagem-api.md`. It covers:

- `hd2.custom_stratagem.register`;
- carrier policies;
- call contexts;
- the payload families (support items, sentries, Eagles, orbital bombardments);
- spawned instances;
- `hd2.ownership`;
- the Pelican gunship options.

Examples: `proof/PelicanCasExample`, `proof/GasBarrageExample`, `proof/GasEatExample`, `proof/HmgSentryExample` and
`proof/EagleStunRocketPodsExample`.

Related research:

- the Gas EAT: `research/docs/gas-eat-F5FEE03DCFDB.md`;
- the payload families: `research/docs/custom-payloads-F5FEE03DCFDB.md`;
- Stratagem MultiSelect and the selector: `research/docs/multi-stratagem-select-F5FEE03DCFDB.md`.

The development proofs described above stay as the known-good references.

## Not proven

- How the matcher resolves equal or extending codes of two available stratagems.
- Multiplayer: code entry is local, and the row changes on this machine only. Do not test multiplayer.

## Live test

See `proof/CustomStratagemP0Proof/README.md`.

## Not in scope (P0 stops here)

Custom payloads (the Gas Barrage, direct payload spawning; the next step, researched first); a new stratagem in the
ship picker (not supported safely: see "A genuinely new selectable stratagem"); a Runtime-presented extra card in the
ship picker (not feasible without native calls: see "A virtual card in the ship loadout picker"); a public
custom-stratagem API; a public
custom-text API; any HUD change beyond redrawing the P0 stratagem's own slot. (Custom icons are public; custom text is
live-verified through the development path.)
