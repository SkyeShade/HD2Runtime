# ProjectileHomingTest 0.1.0

Live test for projectile homing (`hd2.projectiles.homing`, `docs/projectile-homing.md`). Requires HD2Runtime 0.30.0+
/ API 1 and Bingus Shared Loader v15+. Mod Options Menu is optional: without it every option keeps its default.

Each option makes the local player's OWN shots of one weapon turn toward a target while they fly: every update Runtime
turns that one shot's own velocity by at most the turn rate and keeps its speed (one guarded write). The weapon, its
projectile row and every other projectile are never written. The steering path is proven offline
(`validation/projectile-homing-snapshot.json`), not yet in game. Play solo first.

## Options (MODS page "Projectile Homing Test")

| Option | Default | Shots that home |
|---|---|---|
| Expendable Anti-Tank | on | EAT-17 rockets, on enemies |
| Eruptor | on | R-36 Eruptor shells, on enemies (the shrapnel does not home) |
| Grenade Launcher | on | GL-21 grenades, on enemies |
| Liberator | off | AR-23 Liberator bullets, on enemies (6 x the turn rate) |
| Machine Gun Sentry | off | A/MG-43 sentry rounds, on enemies (6 x the turn rate) |
| Stim Pistol | on | P-11 stims, on other players (2 x the turn rate; needs friends and "Also with other players") |
| Turn rate (deg/s) | 120 | how fast a rocket, shell or grenade may turn (30..240) |
| Cone (deg) | 30 | how far off its direction a target may be when the shot looks for one |
| Also with other players | off | experimental: also home with friends in the game |

Every weapon uses a range of 150 m, starts steering after 2 m and aims 1 m above the target's feet.

## Checklist (report each line: pass / fail / not seen)

1. The log shows `PROJECTILE HOMING 0.1.0 BUILD` and one `projectile homing (...): ... home on ...` line per option
   that is on.
2. **EAT-17.** Fire past a standing enemy, about 10-20 degrees to its side, from 30-80 m: the rocket curves into it. The
   log shows `locked on <enemy>` and `first steering write: ... velocity turned ... (1 write, 12 bytes; non-target bytes
   unchanged true; protection restored true; speed kept ...)`.
3. **The hit counts.** The curved rocket damages or kills what it hits (the kill is yours in the mission stats).
4. **Eruptor and grenade launcher.** The same with their shells and grenades; the grenades still fall (gravity is the
   game's), but bend toward the target.
5. **Nothing to home on.** Fire into an empty area or straight up: the shot flies exactly as vanilla.
6. **Turn rate.** Set 30, APPLY, and fire past an enemy: a wide, slow curve that may miss; set 240: a tight curve.
7. **Off by default, then on.** Liberator: bullets bend visibly toward an enemy fired near. Machine Gun Sentry: its
   rounds bend toward its target.
8. **Turn an option off and APPLY:** the log shows `stopped`; that weapon's next shots fly straight.
9. **With friends** (every player runs HD2Runtime; "Also with other players" on): your homing shots home on your
   screen; on a friend's screen the same shots fly straight, but the hit is drawn where your shot hit. A friend's
   shots are never steered by your game. With Stim Pistol on, a stim fired near a teammate curves into them and heals
   them.
10. At the mission end the log has one summary line per weapon and projectile type that fired:
    `... own shots seen, ... steered (... writes ...)`.

Save `HD2Runtime.log` after the session (the game overwrites it at launch).
