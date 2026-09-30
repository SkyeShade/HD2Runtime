# ShieldGeneratorPackTest

Live test for the SH-32 Shield Generator Pack recharge fields. Uses the MODS tab (page **Shield Pack Test**).

The three members hold exact published values on three independent shields:

| Shield | Recharge delay | Broken delay | Recharge rate |
| --- | --- | --- | --- |
| SH-32 | 60 s | 12 s | 150 /s |
| SH-51 barrier | 3 s | 6 s | 300 /s |
| FX-12 relay | 0.01 s | 45 s | 400 /s |

Capacity (150) and radius are already authored. The member at +100 ("restart charge" in an external export) has no
published value and stays read-only.

| Option | Default | What it does |
| --- | --- | --- |
| Fast recharge | on | damaged shield recharges after 2 s (vanilla 60 s) |
| Fast restart | on | broken shield restarts after 2 s (vanilla 12 s) |
| Slow refill | off | recharge 150 -> 10 health per second |

## How to test

1. Check the log: the enabled patches `APPLIED`.
2. Call in a **fresh** SH-32 after APPLY.
3. Take one small hit (the shield dims but does not break): it should refill about 2 s later (vanilla: a minute).
4. Break the shield (heavy fire): it should come back about 2 s later (vanilla 12 s).
5. **Slow refill** on, APPLY, fresh pack: after a hit the shield should visibly refill over many seconds.
6. Everything off, APPLY, fresh pack: vanilla.

Report the delays you measured and whether a fresh pack was needed. `allow_unverified_effect` is set: these fields
are mapped offline, not yet shown in game.
