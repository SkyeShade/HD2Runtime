# GasBarrageCooldownProof 0.1.0 (development only): the fixed 60 s Gas Barrage cooldown

A **companion** of GasBarragePayloadProof 0.2.2. Install both; 0.2.2 is unchanged and live-proven. That proof selects,
discovers, presents, converts and pays the Gas Barrage. This one only gives the converted Gas Barrage slot a fixed 60 s
cooldown, whichever carrier was discovered. Solo host only; no multiplayer.

## What the research found (research/slot-cooldown-F5FEE03DCFDB.json)

- **Where:** the cooldown belongs to the mission stratagem record ENTRY (the slot), not to the stratagem's row and not to
  another per-player structure. The entry's +0x18 holds the cooldown end, an absolute game time in microseconds. Next to
  it are +0x10, the activation, and +0x20, the call-in's arrival.
- **The compare:** the game clock is `[[game+0x3326348]+0x18]`. The entry is unavailable while its end is above the
  clock (an unsigned compare, `0x66D24A`-`0x66D25C`).
- **What a call writes:** end = the call-in's ARRIVAL + the row's cooldown (+0x68) x the active modifiers. In the
  snapshots, the EMS Strike's 75 s became 64.125 s after its arrival (x 0.855). The game counts a cooldown from the
  arrival.
- **The HUD:** the slot shows INBOUND until the arrival, then COOLING while the end is above the clock. Its bar takes the
  time left on its first cooling frame as its total.
- **Peers:** `rpc_sync_stratagems` sends each entry's remaining cooldown, and the receiver rebuilds the end on its own
  clock, so the cooldown replicates. That is why this is solo only.

## What this proof does

`runtime/slot_cooldown.lua` watches the converted entry every frame. In the frame the game starts its cooldown, it
writes the end once, through one guarded 8-byte transaction:

- **Default:** 60 s after the call-in's ARRIVAL, the game's own rule. The HUD's cooling bar then shows 60 s for every
  carrier, and the slot is callable 60 s after the barrage arrives.
- **Option "Count the 60 s from the call":** 60 s after the moment the Runtime sees the call (the current game time). The
  carrier's inbound time then comes out of the 60 s, so the cooling bar shows less than 60 s, by a different amount for
  each carrier.

A cooldown start is a NEW activation with its arrival and an end after it. If the end changes without that, the proof
logs `COOLDOWN: record entry N's end changed, not yet a cooldown start`, writes nothing and keeps watching (the research
does not show whether the game writes a call in one step).

A call it cannot prove keeps the carrier's own cooldown and logs `REFUSED` with the reason. Such calls are: stale, no
longer the carrier, a shared cooldown type, or not a cooldown. Each call is written once; a later change of the end by
the game is reported, never fought.

Never written: the carrier's row (its own 240 s cooldown), the Precision Strike, the 120mm, the Gas Strike, the save
and the account. Nothing needs restoring, because the record's ends are mission state the game rebuilds.

## Live test

1. Install `HD2Runtime-0.28.0-runtime.zip` (this build), `GasBarragePayloadProof-0.2.2.zip` (unchanged) and
   `GasBarrageCooldownProof-0.1.0.zip`. The first line of this proof's log is `GasBarrageCooldownProof 0.1.0 FIXED
   COOLDOWN BUILD`.
2. Aboard the ship, before any conversion, check for `COOLDOWN: carrier native cooldowns before any conversion`: the
   compatible carriers' own cooldowns.
3. Run the Gas Barrage test as before: the custom panel, `PRE-MISSION CHECK ... READY`, a solo mission, `READY TO CALL`.
   You should see `MISSION START: the fixed cooldown is armed` and `COOLDOWN: the Gas Barrage conversion is seen ...
   COOLDOWN: carrier native = 240.00 s`.
4. Call the Gas Barrage (UP UP DOWN DOWN). Expect these lines:
   - `COOLDOWN: carrier native = X` (the row, and with the game's modifiers);
   - `COOLDOWN: game started = Y s after the call-in's arrival`;
   - `COOLDOWN: Gas Barrage override = 60.0 s from the call-in's arrival`;
   - `COOLDOWN: verified end = current_game_time + Z`, where Z = 60 + the time left inbound;
   - `COOLDOWN: HUD: ... its bar took a total of ~60 s`;
   - `COOLDOWN: +15/+30/+45 s after the arrival`;
   - `COOLDOWN: READY AGAIN ... 60.00 s after the call-in's arrival`.

   Check that the HUD counts about 60 s once the barrage arrives, then call it again.
5. Repeat with the 380mm in your loadout: the next eligible carrier is the Napalm Barrage if you own it, otherwise the
   Walking Barrage (as in the 0.2.2 test). If you own the Napalm, also try the 380mm and the Napalm both in your loadout,
   which gives the Walking Barrage. The native cooldowns are all 240 s, but the inbound times differ. The cooldown must
   still be 60 s from the arrival.
6. Optional: switch on "Count the 60 s from the call" (Mod Options, Gas Barrage Cooldown Proof) before a mission and
   compare. The verified end is then `current_game_time + 60.0`.

Ctrl+F10 logs the cooldown status. The payload proof's own `CALL-IN: ... cooldown changed` line may appear twice for
one call: once for the game's write and once for this override.
