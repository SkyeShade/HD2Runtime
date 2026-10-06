# BeaconRedirectProof 0.3.0 (development only): the beacon's timing and the barrage's lifecycle

**Status of the earlier runs:**
- 0.1.0 (Eagle Strafing Run -> 120mm) is live-proven at the beacon level.
- 0.2.0 (AC-8 Autocannon -> 120mm) is live-proven at the dispatcher level: the dispatcher was given type 136 and the
  120mm's payload, and requested its spawn. The redirected beacon keeps the AC-8's timers (8.715 / 8.715).
- 0.2.0's 30 s summary ("NO ... barrage instance") was **wrong**. Its baseline was read after the game had spawned the
  barrage. Its own change line shows a 120mm barrage instance from the activation to 24.3 s after it, as long as the
  native control's (24.2 s). Whether shells fell at the AC-8 beacon is what 0.3.0 measures.

Solo host; no multiplayer change; not part of the Gas Barrage.

## Modes (Mod Options > Beacon Redirect Proof, read at mission start)

| Mode | What is written, in the AC-8 beacon's first update |
| --- | --- |
| **Type only** (default) | its type, 25 -> 136: 0.2.0's live-proven write, nothing else |
| **Timing** ("Normalize the AC-8 beacon's timing ...") | its type 25 -> 136 **and** its countdown and threshold, set to a native 120mm control beacon's (observed earlier in this mission), in **one** guarded transaction |
| Neutral | its type 25 -> 0 (only after a 120mm barrage was seen from the AC-8; not with Timing) |

**Timing guards,** in addition to the type guards (pins, solo host, the 120mm's package resident, the same entity at
the same index, type exactly 25, not activated, countdown not below its threshold, not a remote copy, once per beacon):
- a target: a native 120mm control beacon seen in this mission. Without one, the AC-8 beacon is **refused whole** and
  delivers natively;
- the target is plausible: threshold > 0, countdown >= threshold, at most 120 s;
- the beacon's countdown and threshold are exactly the values seen when it was first seen;
- no earlier timing write for that beacon.

After the write, the type, the countdown and the threshold are read back, the other members compared, the non-target
bytes checked and the protection restored.

**Never written:**
- any StratagemInfo (the AC-8's, the 120mm's);
- any component, projectile or bombardment record;
- the mission record, the save, the account.

## What is observed (read-only, every beacon and every barrage)

| Line | What it shows |
| --- | --- |
| `BEACON TIMING CONTROL` | a native 120mm beacon's countdown and threshold (the timing mode's target) |
| `CALL-IN TIMING` | each beacon's timers as first seen, the call-in as applied, the activation delay |
| `... DISPATCH` | what the dispatcher was given (type, payload, spawn requested) |
| `BOMBARDMENT ... created` | a barrage instance, attributed to the beacon that activated in the same update: its start delay, salvos, aim |
| `BOMBARDMENT ... FIRST SHELL` | the barrage actually firing (its own shells-fired counter) |
| `BOMBARDMENT ... removed` | shells fired, first and last shell, its life |
| `LIFECYCLE` | per beacon, everything above in one line, times after its activation |

## Live test

1. Install `HD2Runtime-0.28.0-runtime.zip` (this build) and `BeaconRedirectProof-0.3.0.zip`; remove 0.2.0. The first
   proof line is `BeaconRedirectProof 0.3.0 BEACON TIMING BUILD`.
2. Put **AC-8 Autocannon and Orbital 120mm HE Barrage** in your loadout. Start a **solo** mission. Wait for
   `BEACON REDIRECT READY`.
3. **Mission 1, type only (default):**
   - throw the **120mm** once, natively, and wait for its `LIFECYCLE` line (about 30 s);
   - then throw the **AC-8** once, and wait for its `LIFECYCLE` line;
   - watch whether 120mm shells land at the AC-8 beacon.
4. **Mission 2, timing:** Mod Options > Beacon Redirect Proof > "Normalize the AC-8 beacon's timing ...", then a new
   solo mission:
   - throw the **120mm** first (the control: `BEACON TIMING CONTROL ... the target timing for the next AC-8 beacon`);
   - then the **AC-8**. Expect `BEACON REDIRECT TIMING: ... countdown 8.715 -> <the control's>, threshold ... read back
     true`, the activation after the 120mm's call-in, and its `LIFECYCLE`.
5. **Send:**
   - every `BEACON`, `CALL-IN TIMING`, `BOMBARDMENT`, `LIFECYCLE` and `MISSION START` line;
   - what you saw at each beacon: shells, the beam.
6. **On a crash:** keep the newest dump (`%APPDATA%\Arrowhead\Helldivers2\crash_data` / `dumps`) and the Runtime log.

Ctrl+F12 logs the live beacons and the barrage instances with their shells fired.
