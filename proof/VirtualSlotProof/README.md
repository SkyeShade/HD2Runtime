# VirtualSlotProof 0.1.0 (development only): mission-time slot conversion

This proof tests the virtual-stratagem foundation with **no custom presentation, code or payload**.

- **Ship loadout:** two Orbital Precision Strikes. The duplicate needs the Stratagem MultiSelect mod, used here as a
  research dependency.
- **In the mission:** the **second** Precision Strike slot becomes the **Orbital 120mm HE Barrage**, which you own but
  did not select.

The game then has two different vanilla stratagems in their own slots. Research and design:
[Mission-time slot conversion](../../docs/custom-stratagems.md).

## What it writes

**One write:** the 4-byte type of one entry of the local player's mission stratagem record. It goes through the
Runtime's guarded development path, `runtime/stratagem_slot_conversion.lua`.

**Never written:** the saved loadout, the loadout screen, account items, the catalogue, the inventory, any
StratagemInfo row, the HUD, executable code.

**Before the write** it also loads the 120mm's call-in package, through the game's own package system. An unselected
stratagem's assets are not loaded in a mission.

## Guards before the write

If any guard fails, the conversion is refused and nothing is written.

- **Build:** the record, HUD, matcher, call-in and ownership code are the reviewed code (pins).
- **Situation:** in a mission, as host, **solo** (one stratagem record). A direct write is not sent to other players.
- **The two stratagems:** both catalogued, found by stable id, and different.
- **The carrier:** enabled, selectable and owned (the game's own availability rule, read-only), and not in the record.
- **Uses:** both stratagems, and the token entry, have unlimited uses.
- **The token:** at least two Precision Strikes among the record's loadout entries; the later one converts.
- **Not in use:** no call-in of that entry is in flight.
- **Assets:** the 120mm's call-in package is resident.

**After the write**, it checks:
- the entry reads the 120mm;
- every other entry and the count are unchanged;
- non-target bytes are unchanged and the protection is restored.

## Restore

- **During the mission:** **MODS > Virtual Slot Proof > "Convert the second Precision Strike"** off + APPLY writes
  the Precision Strike back.
- **At the mission end:** the game rebuilds the record for the ship by itself, which discards the conversion. The saved
  loadout keeps the two Precision Strikes.
- **Finalizer:** a finalizer also restores before the Lua state closes.

**Which build is running:**
- the first log line is `VirtualSlotProof 0.1.0 VIRTUAL-SLOT-CONVERSION BUILD: ...`;
- F9 prints `F9 [0.1.0 VIRTUAL-SLOT-CONVERSION]`.

Build with `py scripts/build_custom_projectile_proof.py --only VirtualSlotProof`.

## Live test

Solo, as host. Do not test multiplayer. Disable other stratagem mods except Stratagem MultiSelect, and keep the
CustomStratagemP0Proof **off**, so the 120mm is vanilla.

1. Install the HD2Runtime runtime ZIP, `VirtualSlotProof-0.1.0.zip` and Stratagem MultiSelect.
2. **Ship:** select **two Orbital Precision Strikes**, and leave the loadout screen. The `saved ship loadout` line
   should say `two Orbital Precision Strikes saved`.
3. **Mission:** start a solo mission. About 5 seconds after the stratagem list fills, check:
   - the `slot probe (before any write)` lines: the record entries, `2 Orbital Precision Strike loadout entries`, and
     the carrier `owned true, selectable true, enabled true, unlimited true, in the record false`;
   - `[HD2Runtime] stratagem slot CONVERTED: entry N Orbital Precision Strike (type 118) -> Orbital 120mm HE Barrage
     (type 136) ...`, whose checks must all say `true`;
   - `HUD slot N now holds Orbital 120mm HE Barrage (the vanilla HUD refreshed it ...)`.
4. **The HUD:** open the stratagem menu. It should show **one Orbital Precision Strike** and **one Orbital 120mm HE
   Barrage**, each with its own code.
5. **The Precision Strike:** enter **Right Right Up** and throw: the normal Precision Strike.
6. **The carrier:** enter **Right Right Down Left Right Down** and throw: the normal **120mm barrage**. Check that its
   assets look right (shells and explosions; no purple question marks).
7. **Independence:** both stay usable on their own cooldowns.
8. **Restore (optional):** switch the toggle off and APPLY in the mission. The `RESTORED` line should say `exact:
   true`, and the menu shows two Precision Strikes again.
9. **Mission end:** after extraction, aboard the ship: the `saved ship loadout` line still says `two Orbital Precision
   Strikes saved`. The loadout screen shows two Precision Strikes.

**If the game crashes:** stop and do not retry. Send `%APPDATA%\Arrowhead\Helldivers2\dumps\` (the newest `.dmp`),
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`, and the last step you did.

Send:
- every `VirtualSlotProof` and `[HD2Runtime]` line;
- an F9 line from the mission;
- what the stratagem menu showed (step 4) and what each call-in did (steps 5 and 6).
