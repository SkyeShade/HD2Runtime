# CarrierSlotProbe 0.4.0: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07). One custom stratagem, Carrier Slot Probe: an Orbital Gas Barrage
(the 120mm's own barrage, its shells bursting into the Gas Strike's cloud), 3 uses per mission, 45 s cooldown, code UP
DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its **carrier itself**, not the Orbital Precision Strike token.
Needs HD2Runtime 0.30.0-dev r38 or later.

The log names this build: `CarrierSlotProbe 0.4.0 CARRIER SLOT MULTIPLAYER PROBE BUILD`.

What it does, by version:

- **0.2.0:** native slot uses (the game's own HUD counter); the slot locked until it is ready to call.
- **0.2.1:** no lockout of its carrier; the slot moves to its next carrier when someone else picks it.
- **0.3.0:** doubles (you can pick its carrier in another slot); the launch fallback.
- **0.3.1:** the carrier looks pickable (the game's own grey helper). Live: works (r37).
- **0.4.0 (EXPERIMENTAL, NOT live-tested):** with friends, through custom multiplayer:
  - your pick writes the carrier the lobby gives Carrier Slot Probe;
  - a friend's native pick of that carrier moves your slot before the launch, if the Runtime can read the other
    players' picks on the loadout screen;
  - every machine shows every player's slot of it as Carrier Slot Probe, the teammate panel (CTRL) included, through
    the game's own card. The Runtime's teammate overlay is not drawn over it any more.

Without custom multiplayer (a friend without a matching Runtime and mod set), the pick writes the token, as before.

## Multiplayer test (2 players)

Both players install the r38 HD2Runtime and CarrierSlotProbe 0.4.0 (remove 0.3.1), with the same other custom
stratagem mods (or none). Player A and player B; swap roles in a second run (host and client behave differently).

1. Form the lobby. Both logs should show `CUSTOM MP STATE` with both players and custom multiplayer enabled.
2. **A** picks Carrier Slot Probe from the custom panel. A's log: `several players (custom multiplayer, EXPERIMENTAL r38):
   its pick writes the carrier the lobby gives it`, then `SELECTED: carrier_slot_probe -> slot N holds C (... the CARRIER
   itself ...)`. Note C.
3. A's log also shows one of:
   - `CUSTOM MP SCREEN NATIVES (aboard the ship, read-only ...)`: the Runtime reads B's picks;
   - `CUSTOM MP SCREEN NATIVES not used`, with the reason: send that line.
4. **B** opens the native picker and picks C (it is pickable: it is not in B's loadout). Within about 2 s A's log shows
   `stratagem selector MOVED ... C -> D` and `SHIP (carrier_slot_probe): loadout slot N MOVED from C to D (another
   player picked it natively)`. A's custom icon stays on its slot.
5. Optional: **B** picks Carrier Slot Probe too. Both get the same carrier (one carrier per custom stratagem).
6. Launch. In the mission:
   - **A's HUD:** Carrier Slot Probe's icon and name from the first frame, 3 uses.
   - **B holds CTRL:** A's slot shows Carrier Slot Probe's icon. Is it the game's own card, with its cooldown and uses?
     B's log: `REMOTE CARRIER PRESENTED (the carrier-in-slot probe): peer <A> slot N holds D for carrier_slot_probe` and
     `TEAMMATE HUD NATIVE: ... no overlay`.
   - **A calls it:** both see the gas barrage. Does B's view of A's beacon show the custom icon?
   - **A's uses:** after each of A's calls, what does B's CTRL card show (3, 2, 1, or no counter)?
7. Send both logs and what you saw in step 6.

If step 4 does not move A's slot before the launch, A's slot is refused in that mission (`CUSTOM MP DESYNC`, locked,
never called): safe, but please send the logs.

## Solo test (unchanged from 0.3.1)

1. Pick Carrier Slot Probe, close the picker, reopen it for another slot: its carrier looks pickable. Pick it: the
   custom slot moves to its next carrier.
2. In a mission: the custom look from the first frame, 3 uses counting down 3 -> 2 -> 1 -> 0, the fourth call refused.
