# EnemySpawnMixTest 0.1.0

Live test for enemy spawn weights (`hd2.enemies.spawn_weight`, `docs/enemy-spawns.md`). Requires HD2Runtime 0.30.0-dev+ /
API 1 and Bingus Shared Loader v15+. Mod Options Menu is optional: without it every option keeps its default.

Each option scales one or more enemy types' weights in the game's spawn rosters. The type is then picked more or less
often within the spawn groups it shares, or (× 0) never. This changes **which** enemies spawn, not **how many**. The
pick is proven offline (`validation/enemy-spawn-weights-snapshot.json`), not yet in game.

**Set the options aboard the ship (APPLY), then deploy.** A type turned back on from × 0 returns only once you are aboard
the ship again. **Host the mission:** the host's rosters decide what spawns.

## Options (MODS page "Enemy Spawn Mix Test")

| Option | Default | Change |
|---|---|---|
| No Bile Titans | on | Terminids: Bile Titan × 0 |
| Hive Guard swarm | on | Terminids: Hive Guard × 5 in the warrior groups |
| No Hunters | off | Terminids: both Hunter tiers × 0 |
| Berserker rush | on | Automatons: Berserker × 5 in the groups they share with tanks and Hulks |
| No tanks | off | Automatons: all three tanks × 0 |
| No Watchers | on | Illuminate: Watcher × 0 |

## Checklist (report each line: pass / fail / not seen)

1. The log shows `ENEMY SPAWN MIX 0.1.0 BUILD` and, for each option that is on, `enemy spawns (...): <enemy> spawn weight x
   <k> APPLIED in <n> roster row(s)`.
2. **No Bile Titans.** A Terminid mission at difficulty 7 or higher, played long enough to see heavies: no Bile Titan
   spawns (the other heavies still do). Note any Bile Titan you see, and whether it came from a breach, a patrol or a
   nest.
3. **Hive Guard swarm.** Warrior patrols and breaches have clearly more Hive Guards and fewer plain warriors than usual.
4. **No Watchers.** An Illuminate mission: no Watcher spawns.
5. **Berserker rush.** An Automaton mission at difficulty 7+: noticeably more Berserkers where tanks and Hulks usually
   appear.
6. **Off by default, then on (aboard the ship, APPLY, deploy).** No Hunters: no Hunter of either tier. No tanks: no
   tank.
7. **Back on.** Turn an option off aboard the ship (APPLY): the log shows `<enemy> restored to the vanilla weights`, and
   the next mission is vanilla for that type. Turning a × 0 option off *during* a mission logs that the restore waits,
   then `restored` once you are back aboard the ship.
8. Nothing crashes, and every other enemy type spawns as usual.

Save `HD2Runtime.log` after the session (the game overwrites it at launch).
