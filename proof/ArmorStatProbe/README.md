# ArmorStatProbe 0.1.0

The live test of armor stats (`hd2.armor_stats`, docs/armor-stats.md). It exercises the two writable levers:
- the local player's own **stamina factor** (`hd2.armor_stats.player():set`);
- the **worn armor kit's piece weights** (`hd2.armor_stats.kit(...)`, one `hd2.ensure`). Every player wearing that kit
  is affected, so test solo.

The per-weight class tables are read-only in this build (their game.dll pages are executable at run time), so they are
not tested here. Development only, solo. Requires HD2Runtime 0.30.0-dev with the armor stats build. Install it alone:
other proofs also use F9.

## How to test

1. Start a **solo** mission. Light or medium armor shows the biggest differences. The log line `STATE (loaded)` names
   your kit, its stats and your stamina factor (light 0.75, medium 1, heavy 1.5).
2. **Stamina (F9).** Find flat open ground. Sprint from a full bar until you are exhausted and count the seconds:
   this is the baseline.
   - **F9** once: `STAMINA 0.5`. Sprint again: it should last about **twice** as long, and refill about half as fast.
   - **F9** again: `STAMINA 1.5`. The sprint should last about 2/3 as long as at factor 1 (on light armor, about
     **half** the baseline).
   - **F9** again: `STAMINA GAME`, the kit's own factor.
   - The factor lasts until the game applies your armor again. After a death and reinforcement the log shows
     `SPAWN: the game applied the armor again (stamina factor ...)`, and the probe sets the mode again.
3. **Armor (Ctrl+F9).** Stand still and let one weak enemy hit you several times in each mode (a Scavenger, a Hunter
   or an Automaton trooper). Every hit logs `HIT [mode] #n: -N health`.
   - **Ctrl+F9** once: `KIT ALL HEAVY`. Every armor piece of your kit is heavy (rating 150, damage x0.75). Hits must
     cost visibly less: x0.6 of a light armor's, x0.75 of a medium armor's.
   - **Ctrl+F9** again: `KIT ALL LIGHT` (rating 50, damage x1.25).
   - **Ctrl+F9** again: `KIT VANILLA`, the kit's own pieces.
   - The armor rating changes on the next hit. Speed and stamina follow only after the next respawn (that is part of
     the test; the log's `STATE (spawned)` shows them).
   - The armory (on the ship) shows the new rating, speed and stamina at once.
4. **Shift+F9** logs the per-mode hit averages and the state; it changes nothing.
5. Before you change armor or leave, press **Ctrl+F9** until `KIT VANILLA`. The probe binds to the first kit you
   cycled; reload the mod to bind another.

## What the log shows

- `STATE (...)`: your avatar slot, armor kit, stamina factor (and the one the kit gives), armor bonus, and what the
  kit gives now: rating, speed, stamina regen, armor value and damage multiplier.
- `STAMINA <mode>`: the write's status (`APPLIED`, or `refused` with a code, for example `NOT_SOLO` or
  `UNEXPECTED_STATE`).
- `KIT <mode>`: the kit's stats after the change. `KIT ENSURE <id>: <status>` comes from the ensure.
- `HIT [mode] #n: -N health`: the health lost per hit, and the average per mode.
- `[HD2Runtime] armor stats (...)` and the transaction lines (`note: ... now gives rating ...`): the Runtime's own.

## What to report

For each mode, the sprint seconds and the average health lost per hit from the same enemy. Also report whether speed
and stamina changed after a respawn with `ALL HEAVY` / `ALL LIGHT`, and the `STATE (spawned)` lines.

## Known limits

- **Shared.** The kit's pieces are read by every player wearing that kit on this machine.
- **Speed is unproven.** The speed factor goes into the avatar's locomotion record at the next armor apply, but how the
  game uses it is not proven. A visibly slower jog with `ALL HEAVY` after a respawn is evidence.
- **Status effects.** One status effect sets the armor bonus to -1, and another multiplies the stamina factor. While
  one is active, a stamina write is refused (`UNEXPECTED_STATE`).
