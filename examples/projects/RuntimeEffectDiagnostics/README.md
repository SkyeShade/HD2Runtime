# RuntimeEffectDiagnostics

Live diagnostic for the AyakaMods report (`docs/user-report-ayakamods-2026-09-29.md`). Six independent tests, each
behind its own Mod Options toggle on the MODS tab page "Runtime Effect Diagnostics". Every toggle is **off** by
default and controls one operation, so one failing test cannot stop or contaminate another. Switching a test off
restores the game's own value.

Needs the HD2Runtime test build that ships with this pass (not the published 0.27.0: that one aborts a mod at its
first invalid operation) and Mod Options Menu. The first line of `HD2Runtime.log` must read
`[HD2Runtime] HD2Runtime 0.27.0 initialized (API 1)`; if it is missing, the old Runtime is running.

## Before you test

- Turn on one or more tests and press APPLY. Wait for `HD2Runtime.log` to show the test's id with `APPLIED`.
- **Magazine, heat and backpack values are copied into a weapon (or backpack) when the game builds it.** A weapon you
  already hold keeps its old copy. After APPLY, get a freshly built one: deploy into a new mission, be reinforced, or
  call in a new support weapon. Damage and cooldown values are read when used and need no rebuild.
- Say for each test whether it changed **immediately** or only **after a rebuild**; both answers are useful.

| # | Toggle | Log id | Vanilla | Test value | What you should see | Needs a rebuilt item |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | MA5C magazine 60 | `diag-ma5c-magazine` | 32 rounds | 60 rounds | The MA5C magazine counter shows 60 and lasts twice as long. | Yes: a newly built MA5C |
| 2 | Halt flechette damage x10 | `diag-halt-damage` | 35 per pellet | 350 per pellet | SG-20 Halt flechette shots (primary feed) one-shot medium enemies. The stun feed is unchanged. | No |
| 3 | Sickle overheats in 5 shots | `diag-sickle-heat` | 1.15 heat per shot (about 87 shots) | 20 heat per shot | The LAS-16 Sickle overheats after about 5 shots. | Yes: a newly built Sickle |
| 4 | Maxigun damage x10 | `diag-maxigun-damage` | 80 per bullet | 800 per bullet | M-1000 Maxigun bullets one-shot medium enemies. | No |
| 5 | Maxigun backpack 3000 | `diag-maxigun-backpack` | 1000 rounds, refill 500 | 3000 rounds, refill 1500 | A newly called-in Maxigun backpack shows 3000 rounds; a supply box refills 1500. | Yes: a new Maxigun call-in |
| 6 | Precision Strike cooldown 5 s | `diag-precision-cooldown` | 80 s | 5 s | Orbital Precision Strike is ready again 5 seconds after use. | Try the next call-in; report if it only changes in a new mission |

## Telling the outcomes apart

| You see | Meaning |
| --- | --- |
| The log shows the id `APPLIED` and the effect appears on a freshly built item | **Works.** The value is consumed when the item is built. |
| It also changes on the item you already hold | Consumed live; please say so. |
| The log shows `APPLIED` but even a freshly built item is unchanged | **Not the active source.** Report the test number and the log. |
| The log shows `<id> rejected: ...` | Runtime refused that one operation and said why; the other tests still run. |
| No line for the id at all, or the version line is missing | The mod or the new Runtime did not load; check the Bingus log. |

The final line `N registered operations settled in S s` tells you when every enabled test has been applied.
