# PelicanCasProof 0.1.1 (development only): Pelican Close Air Support with a red-beacon carrier

**0.1.0 is live-proven** (the code, the neutralized carrier beacon, the empty Pelican over the beacon for 60 s, the
cooldown, the mission-only presentation). Its carrier was the Orbital EMS Strike: an orbital whose beacon is **blue**.
0.1.1 changes **only the carrier choice**: a carrier's beacon category is the colour of its beam, the StratagemInfo
row's +0xD4 (1 red = offensive, 2 blue = support, 3 yellow = other; read by the game when the thrown ball lands),
reported apart from its delivery family and its ping colour (+0xB8). The Pelican CAS takes only a **red** carrier: an
orbital first, then an Eagle (refused by the existing discovery guards in this build: limited uses, Eagle Rearm), then
any other red carrier; with none left it is refused (the explicit fallback: refuse). The rest of the flow is 0.1.0's.

The rest of this page is 0.1.0's, with the build names updated.

The first custom stratagem whose delivery is a game Pelican (docs/research/pelican-cas-F5FEE03DCFDB.md, section 5e).
No weapons, no Gas Barrage payload.

**What happens:**
1. Aboard the ship you select **Pelican Close Air Support** in the custom panel. The saved loadout holds the vanilla
   Orbital Precision Strike token.
2. A **carrier** is allocated for it: the Gas Barrage's own carrier discovery runs first and reserves every carrier it
   could use; the Pelican CAS takes the first unused **red-beacon** carrier (owned, selectable, enabled, unlimited,
   not in your loadout, never the 120mm or the Gas Strike): an orbital, then an Eagle, then any other red carrier,
   each by red ping, call-in class, then stable id. Nothing left: refused, never shared.
   Aboard the ship the carrier stays native (its own card in the loadout picker).
3. Mission start (solo): the carrier takes the Pelican Close Air Support name, description, icon and the code
   **LEFT DOWN LEFT UP LEFT UP**; the beacon watch and the 60 s cooldown are armed; only the virtual slot becomes the
   carrier. `READY TO CALL`.
4. The call throws the **carrier's own beacon** (its red beam, its call-in time). In the beacon's first Runtime update
   its delivery becomes **none** (one guarded write of that beacon's type): the carrier's own attack never comes.
5. The beacon's landing position is recorded. At its activation the Runtime asks for **one empty game Pelican**
   anchored at that position: created 250 m back along your heading and 80 m up, it flies in, hovers over the beacon,
   is held 60 s after its release, then leaves as the game makes it.
6. The slot cools down 60 s from the call-in's arrival (the carrier's own cooldown is never written).
7. Back aboard the ship the carrier's look and code are restored exactly.

**Never written:** the carrier's StratagemInfo cooldown or payload; any shared Pelican, carrier or weapon definition;
the token; the save, account or catalogue. No patch, hook or detour; the only native call is the game's own Pelican
spawn request, through `hd2.pelican.spawn`.

## Which build is running

- The first line is `PelicanCasProof 0.1.1 RED-BEACON CARRIER BUILD`.
- F9 (ship) and F10 (mission) print `[0.1.1 RED-BEACON CARRIER BUILD]`.

## Live test

**Setup:**
- install this hand-off's HD2Runtime runtime ZIP and `PelicanCasProof-0.1.1.zip` (PelicanOrbitProof 0.1.0 may stay
  installed);
- **uninstall** the Gas Barrage proofs (GasBarragePayloadProof, GasBarrageCooldownProof): one custom stratagem per
  mission in this build, and they use the same keys; the allocation still reserves the Gas Barrage's carriers;
- disable Stratagem MultiSelect, Vanilla Plus Megapack and the Pelican Cover Flag mod;
- play **solo**, as host.

**SHIP**
1. Open the loadout, open a stratagem slot, select **Pelican Close Air Support** in the custom panel (click, or F6 then
   F7); pick the rest natively. Do **not** pick the carrier named in the `CARRIER:` line.
2. Leave the loadout screen. Expect `CARRIER CANDIDATE` lines, each with `family = ...` and `beacon_category = ...`
   (the Orbital EMS Strike: `family = orbital ..., beacon_category = support (blue beam ...) -> not offensive`),
   `CUSTOM CARRIER: Gas Barrage = ... (orbital, red beacon), Pelican CAS = ... (..., red beacon); distinct = true`,
   `CARRIER: <name> SELECTED for the Pelican CAS ... beacon_category = offensive (a red beacon, ...)`, `CODE CHECK: ...
   SAFE`, then `PRE-MISSION CHECK: ... READY: start a SOLO mission`.

**MISSION**
1. Expect `MISSION START: carrier presentation APPLIED`, `MISSION START: the beacon watch is armed`, `MISSION START:
   conversion APPLIED`, `READY TO CALL`, `COOLDOWN: armed`. The HUD slot shows the Pelican CAS icon and
   LEFT DOWN LEFT UP LEFT UP.
2. Throw it somewhere open, **away from you** (30-60 m): its beam must be **red**. Expect `BEACON CREATED`, `BEACON LANDED (call 1): ... at (...)`,
   `BEACON NEUTRALIZED ... the carrier's own payload will not execute`, then `COOLDOWN: Pelican CAS override = 60.0`.
3. At the activation: `BEACON ACTIVATED ... the delivery the game had: none (type 0)`, `PELICAN CAS REQUESTED`,
   `PELICAN SPAWN REQUESTED ... anchor (...)`, `PELICAN SPAWN CREATED ... verified true`, `PELICAN CAS SPAWNED`.
4. Watch: **no carrier attack**; an **empty** Pelican flies in from behind you and hovers **over the beacon**. Expect
   `PELICAN CAS HOVERING ... from the beacon horizontally ... -> AT THE BEACON`, `PELICAN CAS MOVERS (INTERNAL ...)`,
   `PELICAN CAS RELEASED`, `PELICAN CAS HELD: ... departs 60.0 s after its release`.
5. While it is held, **walk away** from the beacon (50 m or more): it must stay over the beacon. `PELICAN CAS STATE`
   lines every 5 s give its distance from the beacon and yours.
6. About 60 s later: `PELICAN CAS DEPARTING`, `PELICAN CAS GONE`, `PELICAN CAS SUMMARY ... -> PASS ...`; then
   `COOLDOWN: READY AGAIN`. Optionally call it a second time.
7. Return to the ship: `MISSION END`, `RETURN TO SHIP: carrier presentation RESTORED ... exact = true`; open the
   loadout: `LOADOUT OPEN #1: ... NATIVE`.

**Send** every line starting with `PelicanCasProof`, `CARRIER`, `CUSTOM CARRIER`, `CODE CHECK`, `PRE-MISSION`,
`MISSION`, `READY`, `HUD`, `CALL-IN`, `BEACON`, `PELICAN`, `COOLDOWN`, `RETURN TO SHIP`, `LOADOUT`, `F9`, `F10`, and say
what you saw: the HUD slot, the beacon colour, whether the carrier's own attack came, where the Pelican came from, where
and how high it hovered, whether it followed you, and how it left.
