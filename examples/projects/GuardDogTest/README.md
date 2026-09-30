# GuardDogTest

Live test for Guard Dog backpacks, their drones and drone weapons. Uses the MODS tab (page **Guard Dog Test**).

Runtime reaches each part through its own native link. The backpack deploys the drone: the backpack's deposit names
the drone entity, and that link is re-proven before every write. The drone carries its weapon in its mount. The
drone magazines are stored in the backpack (AR-23: 8 / 8 / 8, exact published values). The drone has its own health
(100) and a body damage zone. Values are copied when the backpack or the drone spawns.

| Option | Default | What it does |
| --- | --- | --- |
| AR-23: 20 drone magazines | on | backpack drone magazines 8 -> 20 (capacity and at call-in) |
| AR-23: tough drone | on | drone health 100 -> 2000 (main and body zone) |
| AR-23: 200-round gun | on | drone gun magazine 45 -> 200 |
| AR-23: double fire rate | off | drone gun 660 -> 1320 rpm |
| Rover: fast beam | off | Rover beam fire rate 60 -> 240 per minute |
| K-9: long arc | off | K-9 arc range 55 -> 110 m, chain 2 -> 6 targets (allow_shared: the arc row) |

## How to test

1. Check the log: every enabled operation `APPLIED`.
2. Call in a **fresh** AX/AR-23 Guard Dog after APPLY.
3. Magazines: the backpack ammo counter should show 20 drone magazines.
4. Magazine size: the drone should fire much longer bursts before it docks to reload.
5. Toughness: let enemies (or a teammate) shoot the deployed drone: it should survive far longer than vanilla
   (100 health).
6. Optional toggles (APPLY and call in a fresh backpack): the AR-23 gun at double speed; a fresh **Rover**, whose
   beam should kill much faster; a fresh **K-9**, whose arc should reach twice as far and chain to more enemies.
7. Everything off, APPLY, fresh backpacks: vanilla.

Report each change you could see, and whether it needed a fresh backpack. `allow_unverified_effect` is set: these
fields are mapped offline, not yet shown in game.
