# HoverPackTest

Live test for the LIFT-860 Hover Pack. Uses the MODS tab (page **Hover Pack Test**).

The published hover time (six seconds) sits in a member only the Hover Pack sets; both jump packs hold -1 there.
The launch uses the vertical launch member that is gameplay-proven on the LIFT-850 Jump Pack; this test checks
whether the Hover Pack reads it too. The other Hover Pack members (vectors and scalars from +160 on) have no
published values: they stay unknown and read-only.

| Option | Default | What it does |
| --- | --- | --- |
| Long hover | on | hover 6 -> 20 s |
| High launch | off | vertical launch velocity 40 -> 80 |
| Quick recharge | off | recharge 11.5 -> 3 s |

## How to test

1. Check the log: `patch hover-duration APPLIED`.
2. Call in a **fresh** Hover Pack after APPLY.
3. Activate it and count: you should hold your height for about 20 s before it lets you down (vanilla 6 s).
4. **High launch** on, APPLY, fresh pack: the take-off should go much higher before it levels out. If nothing
   changes, report that too: it means the Hover Pack launch does not read this member.
5. **Quick recharge** on, APPLY, fresh pack: ready again about 3 s after landing.
6. Everything off, APPLY, fresh pack: vanilla.

Report the hover time, the launch height and the recharge. `allow_unverified_effect` is set on the hover fields.
