# DoubleEdgeOverheatTest

Live test for the LAS-17 Double-Edge Sickle heat levels. Uses the MODS tab (page **Double-Edge Overheat**).

The LAS-17 has three heat levels at 50, 100 and 190 of its 200 heat. From each level it fires a stronger pulse and
applies a self-damage status to you: ticks of 20, 40 and 100. The level-3 status also sets you on fire, because its
damage row carries Fire. Self-damage is data, not code, so moving the levels moves when you start burning. The
level-3 status can also be swapped for the level-2 one, which keeps the heavy pulses without the fire.

| Option | Default | What it does |
| --- | --- | --- |
| Later heat levels | on | levels at 150 / 175 / 199 (vanilla 50 / 100 / 190) |
| No self-ignition | on | level 3 applies the level-2 status (no fire) |
| Overheat lock | off | turns the lock-at-maximum-heat flag on (the LAS-17 is the only weapon with it off) |

## How to test

1. Check the log: `transaction double-edge-levels APPLIED` and `patch double-edge-no-ignition APPLIED`.
2. Equip a **fresh** LAS-17 (the values are copied when the weapon is built): re-equip it at the armory, or start
   a mission with it.
3. Fire continuously and watch the heat bar and your health. Vanilla: burning starts around a quarter of the bar.
   Expected: no self-damage until about three quarters of the bar, and heavy (red) pulses only at the very top.
4. Keep firing at maximum heat: vanilla sets you on fire; with **No self-ignition** you should take the level-2
   damage but never catch fire.
5. Turn **Overheat lock** on, APPLY, fresh LAS-17: at maximum heat the weapon should stop firing and need a reload,
   like the LAS-16 Sickle.
6. Turn everything off, APPLY, fresh LAS-17: vanilla behavior again.

Report where burning starts, whether you catch fire at maximum heat, and what the lock does.
`allow_unverified_effect` is set: these fields are mapped offline, not yet shown in game.
