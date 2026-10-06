# GibThresholdTest

Live test for the whole-body gib ("splootch") threshold: `hd2.fields.gore.whole_body_gib_damage` on
`hd2.enemy(name)`. Every log line starts with `GIB THRESHOLD 0.2.0 EXTREME BUILD` (the 0.1.0 build said
`GIB THRESHOLD 0.1.0 BUILD` and only changed Warriors).

**Field meaning.** A Terminid bursts into gibs when the hit that kills it deals at least this much **final damage**
(after armor, the zone multiplier and the durable mix; Electricity counts double). `-1` means it never bursts.

**When it applies.** The value is read at hit time, so bugs that are already alive follow a change at once. The field
needs `allow_unverified_effect` until this test passes. Research: `docs/research/enemy-gib-threshold-F5FEE03DCFDB.md`.

## 0.2.0: the extreme test

0.1.0 asked for exact damage boundaries, which were hard to see in play. 0.2.0 sets an extreme value on **all 23**
Terminid classes that have a whole-body gore group, so the effect is unmistakable:

| Class group | Vanilla | Test |
| --- | ---: | ---: |
| Scavengers (7 classes) | 400 | 1 |
| Hunters (5) | 500 | 1 |
| Warriors, Brood and Alpha Commanders (10) | 750 | 1 |
| Hive Guard | -1 (never) | 1 |

| Option (MODS tab, page **Gib Threshold Test**) | Choices | Default |
| --- | --- | --- |
| Extreme burst test | on / off (off = every class back to vanilla) | on |
| Terminid burst damage | 1 (everything bursts) / -1 (never) | 1 |

Without Mod Options Menu the defaults apply (on, 1).

Chargers, Bile Titans, Spewers, Stalkers and Shriekers have no whole-body gore group and are not affected; neither are
Automatons or Illuminate.

## Checklist (Terminid mission)

1. Log: `GIB THRESHOLD 0.2.0 EXTREME BUILD: loaded; Terminid burst damage 1 on 23 classes ...`, then one
   `patch gib-threshold-<class> APPLIED` line per class (23).
2. **Value 1.** Kill bugs with a **Safe-mode (non-overcharged) Railgun**, a primary and a pistol. Every Scavenger,
   Hunter, Warrior, Brood Commander and **Hive Guard** should burst on the killing hit. Vanilla: a Safe Railgun body
   shot leaves most Warriors intact, and Hive Guards never burst.
3. **Value -1.** Switch to `-1 (never)` and APPLY. Even an EAT-17 or a 500kg kill leaves intact corpses (limbs may still
   sever: those are separate per-limb thresholds).
4. **Already-alive bugs.** Change the value while bugs are alive; the next kills follow it without new spawns.
5. **Off.** Turn `Extreme burst test` off and APPLY: vanilla again (Railgun body kills leave Warriors intact, an EAT
   still bursts them). The log shows 23 restores.
6. **Controls.** Chargers and Bile Titans die exactly as in vanilla in every mode.

## What to report

- For each mode: did bugs burst / stay intact as listed, and which class did not.
- Whether bugs already alive followed a change.
- Any `REJECTED` or `CONFLICT` line from the log.

## Build

`py build.py` (the SDK in `../../../sdk`).
