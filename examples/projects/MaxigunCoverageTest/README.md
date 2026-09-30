# MaxigunCoverageTest

Live test for the two Maxigun members that were not yet authored. Uses the MODS tab (page **Maxigun Coverage
Test**). Everything else Maxigun Reimagined changes is already authored or deliberately not reproduced (see
`research/equipment-coverage-F5FEE03DCFDB.json`, `maxigun.claims`).

The members are the first pair of the typed RecoilModifiers struct. They are 1.0 on 364 of 366 weapons and no
attachment patches them.

| Option | Default | What it does |
| --- | --- | --- |
| Heavy climb | on | vertical recoil multiplier 1 -> 5 |
| No sideways kick | on | horizontal recoil multiplier 1 -> 0 |

## How to test

1. Check the log: both patches `APPLIED`.
2. Call in a **fresh** Maxigun after APPLY and fire long bursts at a wall.
3. Expected: the muzzle climbs much harder than vanilla, with no left-right wander.
4. Turn one option off at a time (APPLY, fresh Maxigun) to see which axis each one drives.
5. Everything off, APPLY, fresh Maxigun: vanilla.

Report what each option did. `allow_unverified_effect` is set: mapped offline, not yet shown in game.
