# BeaconProbe 0.1.0 (development only): READ-ONLY

**It writes nothing:** no transaction, no guarded write, no native call. It only reads, every Runtime update, through
the Runtime's reader. Research: `research/docs/beacon-redirect-F5FEE03DCFDB.md`.

## What it reads

- **The stratagem beacons:** the manager `[game+0x346BF98] + 0x40 + 0x1380` (27 pinned code locations; any change
  refuses). For each beacon:
  - the type at +0xC;
  - the countdown and threshold;
  - the positions;
  - whether it is activated;
  - its state mode;
  - the marker component's own type copy and the colour category.
- **The call-in table.**
- **The bombardment manager:** its instances and private copies, with each copy's shell list.
- **Every player's mission stratagem record.**

## What it logs

| Line | Meaning |
| --- | --- |
| `BEACON CREATED` | the frame and game time it was first seen, all its fields |
| `BEACON TRACE` | the countdown on the first updates, then every 15th |
| `BEACON TYPE CHANGED (by the game)` | if the game changes a beacon's type |
| `BEACON ACTIVATED` | with **`window: N Runtime updates saw it before activation`**: the time a per-call redirect would have. `0` is the blocker |
| `BEACON SUMMARY` | when the beacon is gone |
| `CALL-INS`, `BOMBARDMENT` | when they change |
| `Ctrl+F11` | the live beacons, call-ins, bombardment, every record, and the **WINDOW TABLE** per type |

## Live test

1. Install the runtime you already have (`HD2Runtime-0.28.0-runtime.zip` with the fixed cooldown) and
   `BeaconProbe-0.1.0.zip`. No other proof is needed.
2. Start a solo mission. Expect `pins: the beacon manager path and its readers are the researched code (27 pins)`.
3. Throw one at a time, each allowed to land and activate:
   - Eagle Strafing Run;
   - an Orbital 120mm HE Barrage (or another barrage);
   - an Orbital Precision Strike;
   - a sentry or emplacement;
   - a support weapon or backpack;
   - then any others: Laser, Railcannon, Eagle Airstrike, 500kg.
4. Optional:
   - a sentry thrown at a moving enemy;
   - a second player in the lobby (their record, their beacons' state mode).
5. Press Ctrl+F11 and send the log.
