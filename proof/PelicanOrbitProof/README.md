# PelicanOrbitProof 0.3.0 (development only): where does the Pelican point?

**0.2.0 is live-proven:** the full 60 s twice, 0 refused, behaviour 667 and stage 6 throughout (1.6-1.9 laps, radius
mean 39-40 m, height mean 56 m).

**0.3.0 adds, the orbit unchanged:**
- **read-only orientation sampling** every 0.25 s once established: its root rotation (the transform's quaternion),
  its forward (the rotation's Y axis), pitch and bank, its velocity, its angle on the circle, the circle's tangent and
  the direction to its flight target. `ORBIT POSE` once a second; `ORBIT ORIENTATION` per run: the mean angle between
  its nose and the tangent, its velocity and its target, and which one its nose follows;
- a **lead** mode (the default): the target is always N m ahead along the circle from the Pelican's own angle, so it
  flies along the tangent. **Ctrl+Shift+F7** cycles N: 10, 15, 20, 5 m. **Ctrl+Shift+F10** cycles lead, sweep, steps.

No rotation is written: this measures whether the flight faces its direction of travel by itself.

**Runs to make:** lead 10 m (the default), then Ctrl+Shift+F7 to 15, to 20, then to 5; then Ctrl+Shift+F10 twice to
sweep for comparison. Send the `ORBIT ORIENTATION` lines, and say whether it looked like it faced where it flew.

The rest of this page is 0.2.0's, with the build names updated.

# PelicanOrbitProof 0.2.0: the orbit entry, and the full 60 s

**0.1.0 live result:** the normal Pelican (behaviour 667) circled the centre on per-instance retargets (1.4 laps, stage 6,
0 refused) but stopped at 44.9 s with `scheduler rejected: ... transaction target alignment/page boundary`.

**The cause:** the Pelican's flight record had moved inside its component array (records move as other entities come and
go), and its 12-byte target then straddled a 4 KB page. The guarded transaction keeps every write inside one page, so it
refused, by an error that cancelled the orbit job. This was an alignment edge in our transaction plan: not cleanup, not
the scheduler, and nothing was written wrong.

**0.2.0 fixes (the guard unchanged):**
- each target is written as its three naturally aligned 4-byte members (x, y, z), all in the same transaction between two
  game updates, so the flight never reads half a target. The orbit catches any error and stops cleanly;
- **the entry:** for the first 15 s the circle's radius and height grow smoothly from where the Pelican hovers (over the
  centre, about 6 m up) to 40 m and 60 m while it starts to turn: a spiral climb. Then the orbit is **ESTABLISHED**. The
  update interval stays 0.25 s (no extra writes).

The rest of this page is 0.1.0's, with the build names updated.

## What 0.1.0 does (unchanged)

The Pelican CAS hover is live-proven: the game's transport Pelican, spawned empty with the beacon as its anchor, holds
over the beacon, steered by its flight component's target. This proof asks whether the **same normal Pelican**
(behaviour 667, never the extraction's behaviour 202) circles when the Runtime moves that per-instance target
(research/docs/pelican-cas-F5FEE03DCFDB.md, "Retargeting a live Pelican" and "The orbit").

**What happens on Ctrl+Shift+F8:**
1. One empty Pelican (`hd2.pelican.spawn`) anchored at the **centre**: the landing position of the last beacon you threw
   in the last 2 minutes (only read; its delivery is the game's own, so throw something harmless such as a Resupply),
   else 30 m east of you. It flies in, hovers over the centre, is released and held 65 s.
2. Once held, the orbit (internal `runtime/pelicans.lua`, not a public API): radius **40 m**, **60 m** above the centre,
   **60 s**. Every update interval one guarded per-instance retarget of its hover point: the Pelican's own target
   (P+0x1BC) and its flight record's target, written together exactly as the game's own move-to does.
   - `sweep` (default): the target moves continuously, one lap every 30 s;
   - `steps`: the target jumps 45 degrees once the Pelican is within 8 m of it (the extraction Pelican's own rule).
3. After 60 s the orbit puts the game's own hover point back; the hold ends 5 s later and the departure is the game's.
4. It stops at once, never fighting, if the stage leaves 6, another writer changes the target, a retarget is refused
   or the Pelican is gone.

**Never written:** any shared Pelican definition, the beacon (read only), any carrier, weapon, save or account data. No
patch, hook or detour.

## Which build is running

- The first line is `PelicanOrbitProof 0.3.0 ORBIT ORIENTATION BUILD`.
- Ctrl+Shift+F11 prints `[0.3.0 ORBIT ORIENTATION BUILD]` and the next run's mode and interval.

## Live test

**Setup:** this hand-off's HD2Runtime runtime ZIP and `PelicanOrbitProof-0.3.0.zip` (PelicanCasProof 0.1.1 may stay
installed: different keys); the Pelican Cover Flag mod disabled; solo, as host. A Resupply in your loadout helps (a
harmless beacon for the centre).

**Run 1 (sweep, a target every 0.25 s, the default):**
1. Throw the Resupply into an open area. Expect `ORBIT CENTRE: beacon ... landed at (...)`.
2. Press **Ctrl+Shift+F8**. Expect `ORBIT RUN 1 REQUESTED [0.3.0 ...]: centre (...) (the beacon ... you threw ...)`,
   `PELICAN SPAWNED`, `PELICAN HOVERING`, `PELICAN HELD (run 1) ... 65.0 s`, then `ORBIT STARTED ... ENTRY 15.0 s`,
   `ORBIT SAMPLE ... ENTRY` lines (the spiral climb), then `ORBIT ESTABLISHED`.
3. **Watch** for 60 s: does it circle the centre, about 40 m out and high up; smoothly or in jerks; does it face its
   direction of travel; does it stay over the centre rather than follow you (walk away)?
4. `ORBIT SAMPLE` every second; after the **full 60 s** `ORBIT STOPPED ... is back`, `ORBIT SUMMARY ... THE FULL 60 s`,
   then `PELICAN DEPARTING` (the game's departure) and `PELICAN GONE`. No `scheduler rejected` line.

**Run 2:** press **Ctrl+Shift+F9** twice (`every 1.00 s`), then Ctrl+Shift+F8 again (a beacon thrown within 2 minutes
is reused; otherwise 30 m east of you).

**Run 3:** press **Ctrl+Shift+F10** (`steps`) and Ctrl+Shift+F9 until `every 0.25 s`, then Ctrl+Shift+F8.

**Send** every line starting with `PelicanOrbitProof`, `ORBIT`, `PELICAN` and `Ctrl+Shift`, and for each run say what you
saw: smooth or jerky, how wide and how high, its heading, and how it ended and left.
