# DirectionalShieldTest

Live test for the SH-51 Directional Shield. Uses the MODS tab (page **Directional Shield Test**).

The backpack body and the energy barrier are separate entities:

* **Body** (the emitter on your back): health 400, armor Heavy, both exact published values. It has no damage zone,
  so every hit on it uses its default armor.
* **Barrier**: the backpack spawns it through its shield controller, and that link is re-proven before every
  write. It owns the shield energy: capacity 1000, recharge after 3 s, restart 6 s after breaking, 300 per s, all
  exact published values. Its only damage zone, "body_front", is the one projectiles striking the barrier resolve
  to. The barrier's default armor is only the fallback, not the shield-facing armor.

| Option | Default | What it does |
| --- | --- | --- |
| 5000 shield | on | barrier capacity 1000 -> 5000 |
| Long outage | on | broken barrier restarts after 20 s (vanilla 6 s) |
| Sturdy emitter | off | backpack body health 400 -> 4000 |

## How to test

1. Check the log: the enabled patches `APPLIED`.
2. Call in a **fresh** SH-51 after APPLY and raise the barrier.
3. Let enemies fire at the barrier: it should hold about five times longer than vanilla before it breaks.
4. Once it breaks, time the restart: about 20 s (vanilla 6 s).
5. **Sturdy emitter** on, APPLY, fresh SH-51: the backpack itself (shot from behind or the side) should take far
   more damage before it is destroyed.
6. Everything off, APPLY, fresh SH-51: vanilla.

Report the holding time, the restart time and the emitter result. `allow_unverified_effect` is set: these fields
are mapped offline, not yet shown in game.
