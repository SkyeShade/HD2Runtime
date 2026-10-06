# CarrierSlotProbe 0.2.1: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07), with the native slot uses (0.2.0) and no lockout (0.2.1). One
custom stratagem, Carrier Slot Probe: an Orbital Gas Barrage (the 120mm's own barrage, its shells bursting into the Gas
Strike's cloud), 3 uses per mission, 45 s cooldown, code UP DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its
**carrier itself**, not the Orbital Precision Strike token. Needs HD2Runtime 0.30.0-dev r35 or later. **Solo only**:
with several players its pick writes the token as before, and a carrier slot picked solo is refused and locked in a
multiplayer mission.

The log names this build: `CarrierSlotProbe 0.2.1 CARRIER SLOT NO LOCKOUT PROBE BUILD`.

New in 0.2.1 (runtime r35):

- **No lockout.** The Runtime no longer blocks the slot's carrier in the native picker (0.2.0's red "held by your
  custom stratagem ... unpick it first" card is gone). Only the regular rule still blocks a carrier: the last viable
  carrier of a selected custom stratagem. The game itself greys any stratagem already in your own loadout ("already in
  this loadout"), so the carrier shows greyed for you, as every stratagem in your loadout does.
- **The slot keeps its carrier** while nobody else holds it, even when another carrier would now rank higher.
- **The move.** When anyone else picks the carrier, the slot moves to its next carrier aboard the ship, before the
  launch, with one guarded write of that slot. A real pick is never written. Solo you cannot trigger this (the game
  greys the carrier for you), so it is tested offline only. If the slot cannot move (you were ready), the mission
  refuses the probe, locks its own slot, and never presents or writes the other pick.

From 0.2.0, unchanged: the native uses (3, the game's own counter), the lock until READY TO CALL, the early
presentation. The r34 log showed that sequence running; what the HUD showed is still unreported.

## What to do

1. Install the r35 HD2Runtime and CarrierSlotProbe 0.2.1 (remove 0.2.0). Solo.
2. Open the loadout screen and pick Carrier Slot Probe from the custom panel.
3. Open the native stratagem picker for another slot and look at the carrier the probe's slot holds (a red orbital,
   named in the log's `SELECTED` line).
4. Pick and unpick a few native red orbitals in your other slots, then leave the loadout screen and come back.
5. Start a mission. Watch the HUD from its first frame.
6. Call it three times (45 s cooldown between calls), then try a fourth.
7. Send the log, and say what you saw in steps 3, 5 and 6.

## What to look for

1. Step 3: the carrier card is greyed like any stratagem in your loadout, **not** the red blocked card. The log has no
   `STRATAGEM BLOCKED (native): ... held by your custom stratagem`.
2. Step 4: the probe's slot keeps its carrier: no `stratagem selector MOVED` line, and `PRE-MISSION
   (carrier_slot_probe): READY: carrier X` keeps the same X.
3. Step 5: the HUD shows Carrier Slot Probe's icon and name from its first frame (never Orbital Precision Strike or
   the carrier's own icon), and the slot shows **3** uses.
4. Step 6: the counter goes 3 -> 2 -> 1 -> 0; then the game's own depleted look, and the fourth call is refused.
5. The log, in order: `LOCKED record entry`, `NATIVE USES ... uses -1 -> 3 ... read back true`, `ADOPTED ... with 3
   native uses each`, `RELEASED record entry`, `MISSION (carrier_slot_probe): NATIVE USES: 3 per slot`, `READY TO
   CALL`; and none of `NOT LOCKED`, `NOT RELEASED`, `REFUSED`, `LOCK FAILED`, `stratagem slot CONVERTED`.
