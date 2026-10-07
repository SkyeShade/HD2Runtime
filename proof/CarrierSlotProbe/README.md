# CarrierSlotProbe 0.4.2: the carrier-in-slot probe

Probe 1 of the carrier-in-slot proposal (2026-10-07). One custom stratagem, Carrier Slot Probe: an Orbital Gas Barrage
(the 120mm's own barrage, its shells bursting into the Gas Strike's cloud), 3 uses per mission, 45 s cooldown, code UP
DOWN UP DOWN LEFT RIGHT LEFT. Its loadout slot holds its **carrier itself**, not the Orbital Precision Strike token.
Needs HD2Runtime 0.30.0-dev r41 or later.

The log names this build: `CarrierSlotProbe 0.4.2 CARRIER SLOT MULTIPLAYER PROBE BUILD`.

What it does, by version:

- **0.2.0:** native slot uses (the game's own HUD counter); the slot locked until it is ready to call.
- **0.2.1:** no lockout of its carrier; the slot moves to its next carrier when someone else picks it.
- **0.3.0:** doubles (you can pick its carrier in another slot); the launch fallback.
- **0.3.1:** the carrier looks pickable (the game's own grey helper). Live: works (r37).
- **0.4.0 (EXPERIMENTAL; first two-player test with r38, see 0.4.1):** with friends, through custom multiplayer:
  - your pick writes the carrier the lobby gives Carrier Slot Probe;
  - a friend's native pick of that carrier moves your slot before the launch, if the Runtime can read the other
    players' picks on the loadout screen;
  - every machine shows every player's slot of it as Carrier Slot Probe, the teammate panel (CTRL) included, through
    the game's own card. The Runtime's teammate overlay is not drawn over it any more.
- **0.4.1 (runtime r40), after the first two-player test:**
  - both players' slots of it now get the SAME carrier (r38: the preview counted the other player's custom slot as a
    real pick, so a second player's pick got another carrier and the host's was refused at mission start);
  - the other players' slots of it are presented as Carrier Slot Probe from the loading screen (r38: the TAB menu
    still showed the carrier's own name, Orbital Gatling Barrage).
- **0.4.2 (runtime r41), after the second two-player test:**
  - the custom look is no longer undone on the loading screen or in the mission's first frames (r40: when only the
    client brought it, both players saw the carrier's own look all mission);
  - the slot no longer flips between two carriers aboard the ship (r40: a stale pick in the other player's record);
  - a carrier slot keeps its carrier unless someone really picks it; when two players hold it, both follow one carrier
    (the lowest player id's).

Without custom multiplayer (a friend without a matching Runtime and mod set), the pick writes the token, as before.

## Multiplayer test (2 players)

Both players install the r41 HD2Runtime and CarrierSlotProbe 0.4.2 (remove 0.4.1), with the same other custom
stratagem mods (or none). Player A and player B; swap roles in a second run (host and client behave differently).

1. Form the lobby. Both logs should show `CUSTOM MP STATE` with both players and custom multiplayer enabled.
2. **A** picks Carrier Slot Probe from the custom panel. A's log: `several players (custom multiplayer, EXPERIMENTAL r38):
   its pick writes the carrier the lobby gives it`, then `SELECTED: carrier_slot_probe -> slot N holds C (... the CARRIER
   itself ...)`. Note C.
3. A's log shows `CUSTOM MP NATIVE PICKS (aboard the ship, ...): the other players' native picks (<B> from the loadout
   screen | its stratagem record): ...; pins carrier_slot_probe=...`. The slot must NOT keep moving back and forth.
4. **B** opens the native picker and picks C (it is pickable: it is not in B's loadout). Within about 2 s A's log shows
   `stratagem selector MOVED ... C -> D` and `SHIP (carrier_slot_probe): loadout slot N MOVED from C to D (another
   player picked it natively)`. A's custom icon stays on its slot.
5. **B** picks Carrier Slot Probe too: B's `SELECTED` line names the same carrier as A's (one carrier per custom
   stratagem). This is what failed in the r38 test's second session.
6. Launch. In the mission:
   - **A's HUD:** Carrier Slot Probe's icon and name from the first frame, 3 uses.
   - **B holds CTRL, and B presses TAB:** A's slot shows Carrier Slot Probe's icon and name in both. Is it the game's
     own card, with its cooldown and uses?
     B's log: `REMOTE CARRIER PRESENTED (the carrier-in-slot probe): peer <A> slot N holds D for carrier_slot_probe` and
     `TEAMMATE HUD NATIVE: ... no overlay`.
   - **A calls it:** both see the gas barrage. Does B's view of A's beacon show the custom icon?
   - **A's uses:** after each of A's calls, what does B's CTRL card show (3, 2, 1, or no counter)?
7. Send both logs and what you saw in step 6.

8. Then the three line-ups, one mission each: only A brings it; only B brings it; both bring it. In each, both
   players' HUD, CTRL card and TAB menu show Carrier Slot Probe (never the carrier's own name or icon). There is no
   `RETURN TO SHIP` line before the mission ends.

If step 4 does not move A's slot before the launch, A's slot is refused in that mission (`CUSTOM MP DESYNC`, locked,
never called): safe, but please send the logs.

## Solo test (unchanged from 0.3.1)

1. Pick Carrier Slot Probe, close the picker, reopen it for another slot: its carrier looks pickable. Pick it: the
   custom slot moves to its next carrier.
2. In a mission: the custom look from the first frame, 3 uses counting down 3 -> 2 -> 1 -> 0, the fourth call refused.
