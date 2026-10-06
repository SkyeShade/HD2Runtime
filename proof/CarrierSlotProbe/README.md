# CarrierSlotProbe 0.1.0: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07). One custom stratagem, Carrier Slot Probe: an Orbital Gas Barrage
(the 120mm's own barrage, its shells bursting into the Gas Strike's cloud), 3 uses per mission, 45 s cooldown, code
UP DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its **carrier itself**, not the Orbital Precision Strike token.
Needs HD2Runtime 0.30.0-dev r33 or later. **Solo only**: with several players its pick writes the token as before, and
a carrier slot picked solo is refused and locked in a multiplayer mission.

The log names this build: `CarrierSlotProbe 0.1.0 CARRIER IN SLOT PROBE BUILD`.

## What to do

1. Solo, open the loadout screen and pick Carrier Slot Probe from the custom panel.
2. Look at the slot: it shows the custom icon (the overlay) as before. Leave the loadout screen and come back: the slot
   still shows it.
3. Start a mission and watch the HUD from the first moment it appears.
4. Call it three times.

## What to look for

1. The pick: `stratagem selector SELECTED: carrier_slot_probe -> slot N holds <a red orbital> (type T, the CARRIER
   itself: the carrier-in-slot probe)`, not Orbital Precision Strike. No `CARRIER INVALIDATED` after it.
2. **The flash:** the mission HUD shows Carrier Slot Probe's icon and name from its first frame. There should be no
   moment with Orbital Precision Strike, and none with the carrier's own icon. Please report exactly what you saw.
3. The timing lines, in order:
   - `CARRIER-IN-SLOT PROBE TIMING: game state Ship -> PrepareMission at ...`, if the Runtime runs on the loading screen;
   - `carrier_slot_probe: applying the presentation on its carrier ... during PrepareMission` (or `during Mission`);
   - `TIMING: the mission HUD is populated at ...`. The presentation must come before this line.
4. The mission: `ADOPTED (carrier-in-slot probe)` then `READY TO CALL`, with no `stratagem slot CONVERTED`.
5. The calls: the gas barrage lands; the slot cools down 45 s; after the third call `USES: 3 of 3: SPENT` and the slot
   stays unavailable.
6. Back aboard the ship: the carrier's own look is restored as before (`RETURN TO SHIP`), and the slot is still the
   custom pick.
