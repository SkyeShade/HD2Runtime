# ReprimandCustomProjectileProof (development only)

Live proof for weapon projectile replacement (`docs/custom-projectile-rows.md#weapon-projectile-replacement`): the
SMG-32 Reprimand fires the slow custom projectile `dev/talon_combined`, the F11 projectile of CustomProjectileRowProof.
It is **not** an example of a public API: it calls Runtime internals that may change.

Build it with `py scripts/build_custom_projectile_proof.py`, which also builds the matching development runtime into
`build/test-artifacts/`. Install both ZIPs from there: the development `HD2Runtime-<version>-runtime.zip` (it replaces
the installed HD2Runtime for the test) and `ReprimandCustomProjectileProof-0.1.0.zip`. CustomProjectileRowProof can stay
installed alongside it.

## How it works

1. **The carrier swap.** The Reprimand is swapped to fire the TD-110 Maelstrom's slot 2 projectile (type 324). That
   projectile has no particle effect, no unit (model), damage type 0 (the game's all-zero damage row) and no explosion,
   so on its own it is invisible and harmless. This is the ordinary guarded projectile swap; the game copies it into a
   Reprimand when it builds one, so **take a freshly built Reprimand** (your loadout or a new call-in).
2. **The replacement.** At each mission start `dev/talon_combined` is defined and bound to the carrier. Every update
   Runtime reads which projectiles the game spawned (read-only). For each carrier your Reprimand fired, it spawns
   `dev/talon_combined` from the carrier's spawn point along its direction. Aim, spread and fire rate are the game's
   own; the custom projectile appears one frame after the shot.

`dev/talon_combined` is a Runtime-owned clone of the LAS-58 Talon row with the PLAS-1 Scorcher's look, the RS-422
Railgun's damage, the GL-21 Grenade Launcher's flight (about 100 m/s, with gravity) and the R-36 Eruptor's impact
explosion.

## Keys (host, in a mission)

- **F12**: replacement on / off. Off, the Reprimand fires the invisible carrier alone.
- **F9**: logs the counts: replaced, dropped (rate limit), refused, shots that were not yours, and carrier shots from
  another weapon.

## What the log shows

```
mission started: SMG-32 Reprimand carrier shots -> dev/talon_combined: bound
projectile replacement: TD-110 Maelstrom / slot_2 (type 324) shots from the SMG-32 Reprimand are replaced by custom
  projectile dev/talon_combined ...
projectile replacement: TD-110 Maelstrom / slot_2 shot 1: carrier slot N (type 324) at (x, y, z) travelled D m
  (lifetime 0.00), velocity (...); owner A, source W (SMG-32 Reprimand); custom dev/talon_combined from (...) along
  (...) -> slot M, the avatar at (...)
```

The first eight shots are logged in full; then a summary every 10 seconds while shots are replaced. `travelled D m`
answers an open question: whether the game had already moved the carrier when Runtime first saw it (D > 0) or not
(D = 0). Either way the custom projectile starts from the carrier's spawn point.

## Live test

See `docs/custom-projectile-rows.md#live-test-weapon-projectile-replacement`.
