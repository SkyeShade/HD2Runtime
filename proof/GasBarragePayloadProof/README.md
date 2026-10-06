# GasBarragePayloadProof 0.2.2 (development only): carrier revalidation

0.2.1 is live-proven: the carrier is native aboard the ship, presents as Orbital Gas Barrage only in the mission, and is
restored exactly on the return to the ship. Its second mission in the same session was refused, though. The carrier
discovered once (the 380mm) had been put in the loadout, and 0.2.1 kept it for the session.

**0.2.2 fixes only the carrier selection.** The discovered carrier is a cache, revalidated before every mission against
the CURRENT loadout, with the discovery's own guards:
- the checks: in the loadout, not owned, not selectable, disabled, limited uses, no call-in package, a special-case type,
  not payload-compatible, the donor;
- when: aboard the ship whenever the saved loadout changes (and every 5 s), and at mission start against the mission
  record (the final check);
- if invalid: `CARRIER INVALIDATED: <carrier> reason: <codes>`, the discovery runs again at once, then `CARRIER:
  <next> SELECTED`. The test is refused only when no carrier is eligible.

A carrier in your loadout is never written: no look, no code, no payload.

Unchanged: the presentation lifecycle, the 120mm pattern, the Gas Strike shell 197, the code, the virtual slots, the
payload restore.

## The lifecycle (0.2.1, live-proven 2026-10-03), unchanged

| Phase | The carrier |
| --- | --- |
| Ship | **Native**: its own name, description, icon and code, so its own card shows in the loadout picker. Selecting the custom Gas Barrage only records the virtual slot. |
| Mission start | Checked native, then the Gas Barrage look and code applied and verified, then (unchanged) the packages, the conversion and the payload, then `READY TO CALL`. It is never callable without the look and code. |
| Mission | Keeps the look and code for the whole mission. |
| Mission end | The payload is restored (unchanged). |
| Return to the ship | The look and code are restored from the exact bytes captured at mission start, as soon as the mission HUD is gone (at the latest 5 s after the mission end), whether or not you open the loadout. |
| Loadout screen opening | The hard boundary: a stale look found then is restored in that same frame. Every opening logs that the carrier is native. |

**What the restore will and will not do:**
- it writes only where the carrier row still holds what this proof wrote; another writer's bytes are refused, never
  overwritten;
- it never touches the Precision Strike token, the 120mm, the Gas Strike, the account catalogue or the save.

## Live test

**Setup:** as for 0.2.1: install this hand-off's HD2Runtime runtime ZIP and `GasBarragePayloadProof-0.2.2.zip` only (no
other proof, no Stratagem MultiSelect or Vanilla Plus Megapack). Play solo, as host. The first log line must be
`GasBarragePayloadProof 0.2.2 CARRIER REVALIDATION BUILD: ...`.

**MISSION 1: the loadout WITHOUT the 380mm**
1. Build **[Gas Barrage] [Eagle Airstrike] [Orbital EMS Strike] [something that is not an orbital barrage]**. Gas Barrage
   comes from the custom panel.
2. Leave the loadout screen. Expect `CARRIER: Orbital 380mm HE Barrage SELECTED (...)` (the Napalm listed as eligible).
3. Play the mission as in 0.2.1: `carrier presentation APPLIED`, `READY TO CALL`, the Gas Barrage with UP UP DOWN DOWN.
   Return to the ship: `PAYLOAD: RESTORED ... exact`, `RETURN TO SHIP: carrier presentation RESTORED ... exact = true`.

**BETWEEN MISSIONS: put the 380mm in your loadout**
4. Open the loadout and natively pick **Orbital 380mm HE Barrage** into a slot. Keep Gas Barrage in its slot (select it
   again in the custom panel if it was lost). Leave the loadout screen.
5. Expect, in this order:
   - `CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout (...)`;
   - the `CARRIER CANDIDATE` lines (the 380mm `-> rejected: in the loadout`);
   - `CARRIER: Orbital Napalm Barrage SELECTED (...)`;
   - `PRE-MISSION CHECK ... carrier = Orbital Napalm Barrage ...; carrier present in saved loadout = false ... -> READY`.

**MISSION 2**
6. Start the mission. Expect `carrier presentation APPLIED` on the **Napalm**, `READY TO CALL`, and the Gas Barrage with
   UP UP DOWN DOWN. Your own 380mm stays a normal 380mm (its own icon, name and code; call it if you like: a normal 380mm
   barrage).
7. Return to the ship: both restores, exact.

**Optional, MISSION 3:** remove the 380mm and put the Napalm in your loadout instead. Expect `CARRIER INVALIDATED: Orbital
Napalm Barrage reason: in_loadout`, then a new `CARRIER: ... SELECTED` (the 380mm again, or another compatible carrier),
and the Gas Barrage working again.

**Send:**
- `HD2Runtime.log` (copy it before restarting the game). Especially the `CARRIER INVALIDATED`, `CARRIER CANDIDATE`,
  `CARRIER: ... SELECTED`, `PRE-MISSION CHECK`, `MISSION START`, `READY TO CALL`, `PAYLOAD`, `RETURN TO SHIP` and
  `LOADOUT OPEN` lines;
- whether the Gas Barrage fired in each mission, and whether your natively selected 380mm or Napalm behaved and looked
  normal.

**If the game crashes:** stop and do not retry. Send:
- the newest `.dmp` from `%APPDATA%\Arrowhead\Helldivers2\dumps\`;
- `HD2Runtime.log`;
- the last step you did.

## Keys

| Key | Action |
| --- | --- |
| Mouse | In the custom panel: hover focuses, a left click selects Orbital Gas Barrage |
| F6 / Ctrl+F6 | Focus next / clear |
| F7 / Ctrl+F7 | Select the focused tile / undo the newest selection |
| Ctrl+F9 | Slot overlays off / on |
| F9 | Ship status (`mission presentation APPLIED / not applied`, the loadout and picker opening counts), the PRE-MISSION CHECK and the carrier's PAYLOAD RECORD |
| F10 | Mission status and the carrier's PAYLOAD RECORD |

Mod Options Menu is optional. With it, MODS > Gas Barrage Payload Proof has four toggles: the look, the code, the payload
and converting the virtual slots. The look and code toggles are read at mission start (aboard the ship the carrier is
always native). Without the menu, all four stay on.

## Stage C (0.2.0, live-proven 2026-10-03), unchanged since

| | Stage B (0.1.1) | Stage C (0.2.0 and 0.2.1) |
| --- | --- | --- |
| Pattern | the 120mm's | the 120mm's: 5 salvos, 3 shells per salvo, 0.75 s between shells, 2 s between salvos, scatter 27 |
| Shell list | 194, 137, 137 (the 120mm's shells) | **197, 197, 197** (the Orbital Gas Strike's reviewed shell) |

**The gas chain the carrier points at;** nothing of it is written or copied:

    shell 197 -> explosion 82 -> damage 447: gas and gas_confusion, once at each impact
                              -> volume template 16: a 15 s, 15 m gas cloud applying gas and gas_confusion every tick

**In the conversion's tick** (never callable before all of it): the conversion, then the 120mm pattern, then the shell
list, each verified. Any failure rolls back and undoes the conversion. Every guard of stages B and C is unchanged.

**Never written:** the Gas Strike's shell, explosion, gas cloud, statuses and record; the 120mm's record and shells;
the Precision Strike; the StratagemInfo registry; the account catalogue; the save.
