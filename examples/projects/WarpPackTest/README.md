# WarpPackTest

Live test for the LIFT-182 Warp Pack. Uses the MODS tab (page **Warp Pack Test**).

Every field here is an exact published Warp Pack value at a typed native member. The warp distance is 10 m and each
warp adds 33 % heat. Below 15 % heat a warp is safe; 15-45 % damages one random limb (head 10, arms 35, legs 45; the
chest sets you on fire); above that it kills you. The values are copied into a Warp Pack when it spawns.

| Option | Default | What it does |
| --- | --- | --- |
| Long warp | on | warp distance 10 -> 25 m |
| Cool pack | on | heat per warp 33 -> 10 % (two safe warps back to back) |
| No limb damage | off | unsafe-warp damage to head, arms and legs -> 0 |

## How to test

1. Check the log: `patch warp-distance APPLIED` and `patch warp-heat APPLIED`.
2. Call in a **fresh** Warp Pack after APPLY.
3. Warp on flat ground next to a landmark: the jump should cover about 25 m (vanilla 10 m).
4. Warp twice quickly: with **Cool pack** both warps should be safe (no damage), and the orb should stay purple
   longer. A third quick warp is unsafe (orange).
5. Turn **No limb damage** on, APPLY, fresh pack. Warp until the orb is orange (unsafe, not red) and warp again:
   no limb should be damaged or broken (you may still catch fire). **Never warp while the orb is red**: that still
   kills you.
6. Everything off, APPLY, fresh pack: vanilla.

Report the warp distance, how many safe warps you get in a row, and whether unsafe warps damaged a limb.
`allow_unverified_effect` is set: these fields are mapped offline, not yet shown in game.
