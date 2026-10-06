# CarrierSlotProbe 0.2.0: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07), with the native slot uses (0.2.0). One custom stratagem, Carrier
Slot Probe: an Orbital Gas Barrage (the 120mm's own barrage, its shells bursting into the Gas Strike's cloud), 3 uses
per mission, 45 s cooldown, code UP DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its **carrier itself**, not
the Orbital Precision Strike token. Needs HD2Runtime 0.30.0-dev r34 or later. **Solo only**: with several players its
pick writes the token as before, and a carrier slot picked solo is refused and locked in a multiplayer mission.

The log names this build: `CarrierSlotProbe 0.2.0 CARRIER SLOT USES PROBE BUILD`.

New in 0.2.0:

- **Native uses.** Its 3 uses are the game's own per-slot uses: the HUD shows the counter, the game counts it down and
  shows the depleted look at 0. One 4-byte write into this player's own record entry for that slot (-1 -> 3), only
  after every guard below; written back to -1 when the Runtime lets the slot go while the mission still runs.
- **The lock.** From the mission's first update until the probe is READY TO CALL, its slot is locked (its cooldown end
  far ahead), so the carrier's own vanilla call can never come out of it. Released right before its cooldown is armed.
- **The native block.** While a custom slot holds the carrier, that carrier is blocked in the native stratagem picker
  ("held by your custom stratagem carrier_slot_probe ..."), so it cannot also be picked natively.
- A fix: the adopted slot was never let go at the mission's end in 0.1.0 (it carried over into the next mission).

## The uses write never touches a real stratagem

Before the write, every one of these must hold, else nothing is written and the probe is refused for the mission (its
slot stays locked: unusable, never the carrier's own call):

1. The slot is this player's own custom carrier slot, and its record entry holds exactly the carrier's type, with
   unlimited uses, not called and not in flight, in this mission's record (its address and key).
2. The carrier's type is in **no other entry** of the record (`CARRIER_ELSEWHERE`): a native pick of the same
   stratagem is never written.
3. The carrier's row has unlimited uses (`USES_DIFFER`), a per-player cooldown (`SHARED_COOLDOWN`), and is not an
   Eagle or type 28/124 (`SPECIAL_USES`).

Only that record entry is written, never the stratagem's row (`StratagemInfo`) and never another player's entry. The
record is rebuilt by the game for every mission (seeded from the row), so a write can never carry over.

## What to do

1. Install the r34 HD2Runtime and CarrierSlotProbe 0.2.0 (remove 0.1.0). Solo.
2. Open the loadout screen and pick Carrier Slot Probe from the custom panel.
3. Open the native stratagem picker: the carrier the slot holds (a red orbital) should be unavailable there.
4. Leave the loadout screen and come back: the slot still shows the custom pick.
5. Start a mission. Watch the HUD from its first frame.
6. Right after landing, try its code once (UP DOWN UP DOWN LEFT RIGHT LEFT). The lock may already be released by
   the time you can input it (it only lasts until READY TO CALL): then skip this step.
7. Once ready, call it three times (wait out the 45 s cooldown between calls). After the third call, try a fourth.
8. Finish or abandon the mission and go back aboard the ship. Start a second mission and look at the slot again.
9. Send the log.

## What to look for

1. The pick: `stratagem selector SELECTED: carrier_slot_probe -> slot N holds <a red orbital> (type T, the CARRIER
   itself: the carrier-in-slot probe)`. No `CARRIER INVALIDATED` after it.
2. The native picker (step 3): the carrier is greyed out or refused, with `held by your custom stratagem
   carrier_slot_probe (its carrier itself, in loadout slot N)`.
3. **The flash** (step 5): the HUD shows Carrier Slot Probe's icon and name from its first frame, never Orbital
   Precision Strike and never the carrier's own icon. Please say exactly what you saw.
4. **The counter** (step 5): the slot shows **3** uses on the HUD (0.1.0 showed none).
5. The early call (step 6), if you got one in: refused by the game (the slot may show a very long cooldown for that
   moment); the carrier's own strike never lands.
6. The log, in order:
   - `CARRIER-IN-SLOT PROBE carrier_slot_probe: LOCKED record entry E at ... until it is ready to call`;
   - `stratagem slot NATIVE USES (carrier-in-slot probe): virtual carrier_slot_probe: record entry E (...) uses -1 -> 3`,
     ending `read back true; every other entry unchanged`;
   - `stratagem slot ADOPTED (carrier-in-slot probe): ... with 3 native uses each`;
   - `CARRIER-IN-SLOT PROBE carrier_slot_probe: RELEASED record entry E`;
   - `MISSION (carrier_slot_probe): NATIVE USES: 3 per slot`, then `READY TO CALL`;
   - no `stratagem slot CONVERTED`, no `NOT LOCKED`, no `NOT RELEASED`, no `REFUSED`.
7. The calls (step 7): the gas barrage lands each time; the counter goes 3 -> 2 -> 1 -> 0; after the third call the
   slot shows the game's own depleted look and the fourth call is refused.
8. Back aboard (step 8): the carrier's own look is restored (`RETURN TO SHIP`) and the slot is still the custom pick.
   In the second mission the counter is back at 3 (the game rebuilt the record).
9. Your other stratagem slots: their counters and cooldowns are exactly vanilla in both missions.
