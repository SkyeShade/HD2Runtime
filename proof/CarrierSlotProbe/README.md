# CarrierSlotProbe 0.3.1: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07), with the native slot uses (0.2.0), no lockout (0.2.1), the
doubles and launch fallback (0.3.0) and the doubles' look (0.3.1). One custom stratagem, Carrier Slot Probe: an Orbital
Gas Barrage (the 120mm's own barrage, its shells bursting into the Gas Strike's cloud), 3 uses per mission, 45 s
cooldown, code UP DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its **carrier itself**, not the Orbital Precision Strike token. Needs HD2Runtime
0.30.0-dev r37 or later. **Solo only**: with several players its pick writes the token as before, and a carrier slot
picked solo is refused and locked in a multiplayer mission.

The log names this build: `CarrierSlotProbe 0.3.1 CARRIER SLOT DOUBLES LOOK PROBE BUILD`.

New in 0.3.1 (runtime r37): the carrier also LOOKS pickable. In r36 it could be picked but was still drawn grey. The
Runtime now lifts the grey through the game's own per-card helper, the call the game itself makes to grey or un-grey a
card (Stratagem MultiSelect makes the same call). Its code is checked byte for byte before every call. If that check
fails, the old way stays: pickable, drawn grey.

New in 0.3.0 (runtime r36):

- **Doubles.** The game greys every stratagem already in your loadout ("already in this loadout"), including the
  carrier in your custom slot. The Runtime now lifts that grey for exactly that carrier while you edit another slot,
  so you can pick it there too (as Stratagem MultiSelect allows for any stratagem). Picking it moves the custom slot
  to its next carrier (0.2.1's move). While you edit the custom slot itself, the carrier stays greyed.
- **Launch fallback.** If the slot could not move before the launch (you readied right after the pick), the mission
  swaps your own slot to its new carrier while it is still locked, then makes it ready. Your real pick of that
  stratagem is never written. If the Runtime never saw your pick (made while ready), the probe is refused for that
  mission and its slot stays locked.
- **The only lockout left** is the regular one: the last carrier available for a custom stratagem you selected.

## What to do

1. Install the r37 HD2Runtime and CarrierSlotProbe 0.3.1 (remove 0.3.0). Solo.
2. Pick Carrier Slot Probe from the custom panel into slot 1. The log's `SELECTED` line names its carrier (C).
3. Close the stratagem picker. Open it again for another slot.
4. Find C in the grid: it should look normal (not greyed) and be pickable. Pick it.
5. Within a couple of seconds the custom slot moves to another carrier. The custom icon stays on its slot, and your
   other slot shows C as a normal stratagem.
6. Open the picker on the custom slot itself and look at its new carrier: greyed there (by design).
7. Start a mission. Watch the HUD from its first frame, then call the probe three times and try a fourth. Also call
   C from your other slot.
8. Optional, the fallback: back aboard, pick the probe's current carrier into another slot and press ready right
   away. You will see either a normal move (you were slower than the move), a `LAUNCH FALLBACK`, or an
   `IDENTITY_CHANGED` refusal (the Runtime never saw the pick). All three are safe outcomes.
9. Send the log, and say what you saw in steps 4, 5, 7 and 8.

## What to look for

1. Step 4: `STRATAGEM PICKABLE (native, the carrier-in-slot probe): C` and `stratagem doubles: native grid (slot N):
   pickable 1 card (C), by the game's per-card grey helper (game+18D1440, re-proved; 1 call ...)`. The card looks
   normal, and the pick is accepted. If the log says `the game's per-card grey helper is not used`, send that line.
2. Step 5: `stratagem selector MOVED (carrier-in-slot probe): virtual slot 0 ...: its carrier C ... -> D`, then
   `SHIP (carrier_slot_probe): loadout slot 0 MOVED from C to D (you picked it natively into loadout slot N)`.
3. Step 7: the probe's slot shows Carrier Slot Probe's icon and name from the first frame, and 3 uses that count down
   3 -> 2 -> 1 -> 0. The fourth call is refused. C in your other slot is plain vanilla: its own name, icon and code,
   unlimited uses, and its own strike.
4. The mission log: `LOCKED`, `NATIVE USES ... -> 3 ... read back true`, `ADOPTED`, `RELEASED`, `READY TO CALL`.
   None of `NOT LOCKED`, `NOT RELEASED`, `LOCK FAILED`, `stratagem slot CONVERTED` (unless you hit the fallback in
   step 8).
5. Step 8 with the fallback: `LAUNCH FALLBACK (the carrier-in-slot probe)`, `CONVERTED: virtual carrier_slot_probe:
   loadout slot N = record entry E: C ... -> D`, `RELEASED record entry E`, `READY TO CALL`; C in your other slot
   stays vanilla.
