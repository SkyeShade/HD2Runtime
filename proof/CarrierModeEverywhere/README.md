# CarrierModeEverywhere 0.1.0: every custom stratagem in the carrier-in-slot mode

A development test switch (2026-10-07). While it is installed, every custom stratagem of every installed mod that does
not name its own `selection` takes `selection = 'carrier'`: its loadout slot holds its **carrier itself**, as
CarrierSlotProbe does, instead of the Orbital Precision Strike token. A mod that names `selection = 'token'` keeps the
token. One session then shows which custom stratagems work in that mode and which fail.

Needs HD2Runtime 0.30.0-dev r42 or later. The log names this build:
`CarrierModeEverywhere 0.1.0 CARRIER MODE EVERYWHERE TEST BUILD`, then
`CARRIER MODE FOR EVERY CUSTOM STRATAGEM: ON (development; hd2.custom_stratagem.carrier_mode_all): N custom stratagems`.

- Re-pick your custom slots after installing (or removing) it: a slot picked in the other mode stays in it, and the
  mission refuses it (locked, never called).
- With friends, every player needs it (it is part of the registry hash); otherwise custom multiplayer reports the
  mismatch and custom stratagems are disabled on every machine, as for any other mod difference.
- Remove it to get the token back.

## Test (solo first)

For each custom stratagem you have installed, one at a time or several per mission:

1. Pick it from the custom panel. The log line `stratagem selector SELECTED: <id> -> slot N holds <carrier> (... the
   CARRIER itself ...)` must appear. A pick that is refused logs `REFUSED` with a reason: note it.
2. Launch. In the mission: its own icon and name on your HUD from the first frame; its uses (if any) on the game's own
   counter.
3. Call it. Does the custom payload arrive (not the carrier's own)?
4. Note per stratagem: pick OK / refused (reason), look OK / carrier's look, payload OK / carrier's payload / nothing.

Send the log and the notes. The `CARRIER-IN-SLOT` and `REFUSED` lines name what failed.
