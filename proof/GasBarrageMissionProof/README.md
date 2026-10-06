# GasBarrageMissionProof 0.5.0 (development only): the custom calldown code

**The invariant this proof establishes:** the game believes the slot is vanilla stratagem X (the carrier) while the
Runtime makes X present as the custom stratagem *and answer to its code*. X keeps its own type, stable id, call-in and
payload. There is no payload change yet (payload stage A).

    custom Gas Barrage (panel) -> saved Orbital Precision Strike token -> carrier DISCOVERED from what you own
    -> the carrier gets the Gas Barrage look and the code UP UP DOWN DOWN (aboard the ship)
    -> solo mission -> ONLY that slot becomes the carrier -> UP UP DOWN DOWN calls the carrier's own normal attack

## Why 0.5.0

**0.4.0 passed live (2026-10-02).**
- The carrier was discovered from your account: the Orbital 380mm HE Barrage.
- Only the virtual slot became the carrier, and it presented as Gas Barrage.
- Its own package loaded and its own call-in fired.
- The Orbital Precision Strike and the 120mm stayed native.

That part is unchanged in 0.5.0.

**New: the Gas Barrage code on the carrier.** It goes through the public `hd2.fields.stratagem.calldown_code` field,
as one `hd2.ensure` on the carrier only.
- **Its native code is read from its row first.** It must equal the reviewed native code, which is the field's `expect`.
- **The ensure restores the native code** when its toggle is off. The Runtime also restores it when the game closes.
- **Never written:** the Precision Strike's and the 120mm's codes and rows. Every report checks them native.

**Why the code is checked so carefully.** The game re-checks every stratagem of your mission on each arrow and calls
the first one whose whole code you have entered, at once. So:
- **an equal code** is ambiguous;
- **a code that starts another's** makes that other stratagem uncallable while the carrier is ready;
- **a code that extends another's** is never reached.

No stratagem's code equals UP UP DOWN DOWN, and none is its start. Three mission-only objectives start with it: the
cargo container, the mobile comms relay and the destroyer call-in. They are granted at mission start on some missions.
The proof therefore:
- **refuses the code** if any stratagem a player can select relates to it (none does on this build);
- **refuses the test aboard the ship** if a saved stratagem relates to it;
- **refuses the conversion at mission start** if the mission record holds a related entry. Nothing is converted, and
  the objective stays callable;
- **watches the record after the conversion.** If a related entry ever appears, the virtual slot goes back to its
  Precision Strike token through the conversion's own guarded restore.

**Do NOT select the carrier natively.** While the proof runs, its own picker card shows the Gas Barrage look and code.
If it is in your saved loadout, the test is refused.

**What it does not change:** the payload, the projectiles, the save format, the account, the catalogue, the inventory
and the StratagemInfo registry. It makes no native call, FFI call, hook or OS input.

**Which build is running:**
- the first log line is `GasBarrageMissionProof 0.5.0 CUSTOM CALLDOWN BUILD: ...`;
- F9 prints `F9 [0.5.0 CUSTOM CALLDOWN]` and the pre-mission check again;
- F10 prints `F10 [0.5.0 CUSTOM CALLDOWN]`.

## Keys

| Key | Action |
| --- | --- |
| Mouse | In the custom panel: hover focuses, a left click selects Orbital Gas Barrage |
| F6 / Ctrl+F6 | Focus next / clear |
| F7 / Ctrl+F7 | Select the focused tile / undo the newest selection |
| Ctrl+F9 | Slot overlays off / on |
| F9 | Ship status and the PRE-MISSION CHECK again |
| F10 | Mission status |

Mod Options Menu is optional. With it, MODS > Gas Barrage Mission Proof has three toggles:
- **Gas Barrage look on the carrier:** off + APPLY, aboard the ship, restores the carrier's own look.
- **Gas Barrage code on the carrier:** off + APPLY restores the carrier's own code.
- **Convert virtual Gas Barrage slots:** off means no conversion.

Without the menu, all three stay on, and the code is restored when the game closes.

## Live test

**Setup:**
- install the HD2Runtime runtime ZIP and `GasBarrageMissionProof-0.5.0.zip` only;
- remove every other proof, including CustomStratagemP0Proof, which also writes codes;
- disable Stratagem MultiSelect and Vanilla Plus Megapack;
- play **solo**, as host. No multiplayer, no matchmaking.

**SHIP**
1. Build exactly this loadout:

       [Gas Barrage] [Eagle Airstrike] [Orbital EMS Strike] [Orbital Walking Barrage]

   - Slot 1: Orbital Gas Barrage from the **CUSTOM STRATAGEMS panel**.
   - Slots 2–4: pick natively.
2. Leave the loadout screen. Look for:
   - the `CARRIER CANDIDATE: ...` lines and `CARRIER: <carrier> (...) SELECTED ... its native code: ...`;
   - `CODE CHECK: the Gas Barrage code up up down down for the carrier <carrier> ...: its native code read from its
     row first: ... (equal: true); native codes equal to it or related to a selectable stratagem: none; mission-only
     stratagems related to it: DropoffCargoContainer ...; MobileCommsRelay ...; CallInDestroyer ... -> SAFE`;
   - `CODE: the carrier <carrier> code (public calldown_code ensure): ... the carrier row holds the Gas Barrage code
     (up up down down); Orbital Precision Strike ... code native = true; donor ... code native = true`.
3. Wait for:

       PRE-MISSION CHECK: ... carrier = <carrier> (stable id ...); carrier present in saved loadout = false; ...
       Orbital Precision Strike presentation native = true, code native = true; donor Orbital 120mm HE Barrage
       presentation native = true, code native = true; the carrier row holds the Gas Barrage text and the Gas Barrage
       icon and the Gas Barrage code (up up down down); the Gas Barrage code against the saved loadout: no conflict
       -> READY: start a solo mission

**MISSION START** (solo):
4. About 5 s after the HUD appears, look for:
   - `CODE CHECK: the Gas Barrage code up up down down against this mission record (...): no entry has an equal code,
     a code that starts with it or a code that is its start`. If it says `TEST REFUSED ... conflicts with this mission
     record`, the mission grants one of the three objectives: report it, abandon, and try another mission;
   - `MISSION START: conversion APPLIED: loadout slot 0 = record entry E -> the carrier <carrier> ...`;
   - `CODE: the carrier <carrier> row holds the Gas Barrage code (up up down down) ...`;
   - `IDENTITY: loadout slot 0 = orbital_gas_barrage (the Runtime's record: kept) ...`.

**HUD**
5. Look for `HUD: HUD slot E ...; its arrows draw up up down down; ...`.
6. Open the stratagem list and take a screenshot. For the first slot, report the name, the icon and the arrows.
   Expected: ORBITAL GAS BARRAGE, the Gas Barrage icon, and **UP UP DOWN DOWN**. The other three slots should be
   unchanged.

**CALL-IN**
7. Enter **UP UP DOWN DOWN** and throw the beacon.
   - Look for `CALL-IN: the virtual Gas Barrage slot ... was called: a call-in of <carrier> ...; the carrier row holds
     the Gas Barrage code (up up down down), the only code that calls it`.
   - Expected: **the carrier's own normal attack** (for the 380mm: its normal barrage). No gas yet.
8. Optional: enter the carrier's old native code (from the `CARRIER` line). Expected: it calls nothing.
9. Press F10.

**MISSION END**
10. Finish or abandon the mission and return to the ship. Look for:
    - `stratagem slot entry E no longer holds <carrier> ... nothing to restore`;
    - `MISSION END: ... conversion gone ...; the carrier row holds the Gas Barrage code (up up down down)`;
    - the next `PRE-MISSION CHECK` with `reconstructed: 1 slot`.

**RESTORE**
11. With Mod Options Menu: MODS > Gas Barrage Mission Proof > **Gas Barrage code on the carrier** off + APPLY. Look for
    `CODE: ... the carrier row holds its native code (...)`, then press F9. Without the menu, closing the game
    restores it.

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`;
- the last step you did.

**Send:**
- every `GasBarrageMissionProof` and `[HD2Runtime]` line, especially:
  - `CARRIER CANDIDATE`, `CARRIER`, `CODE CHECK`, `CODE`, `PRE-MISSION CHECK`, `PRESENTATION`;
  - `MISSION START`, `IDENTITY`, `HUD`, `CALL-IN`, `CODE CONFLICT` (if any), `MISSION END`;
  - `stratagem calldown`, `stratagem slot`, `virtual slot`;
  - F9 and F10;
- the screenshots;
- your notes for steps 1–11.
