# VampiricThrowingKnivesTest

Showcase for exact damage attribution (`docs/events.md`, "Damage and hit attribution"): **when the local player's K-2
Throwing Knife damages something, the local player heals 25**, never above maximum health.

The attribution is the game's own. The game adds its `dealt_damage` mission stat under the source that dealt the
damage: a gun's weapon, a throwable, a stratagem payload. The K-2 is its own source. `player_damage_dealt` reports that
growth per source every tenth of a second, so nothing is inferred from timing:

| Situation | Expected |
| --- | --- |
| A knife hits an enemy while you are hurt | `knife damage <n> -> heal +25 requested`, then `player healed +25` |
| A knife misses (hits the ground or nothing) | no line: the game records no damage |
| A knife hits an armored part it cannot penetrate | no line: no damage is recorded |
| Your gun or a stratagem damages an enemy | `damage <n> by <weapon> -> no heal (not the knife)` |
| An enemy dies from another source | nothing (this mod does not listen to deaths) |
| You are downed or dead | `heal refused: the avatar is downed or dead` |

## How to test

1. Equip the K-2 Throwing Knife. Deploy on a mission; `HD2Runtime.log` shows
   `[mods/hd2runtime_examples/vampiric_throwing_knives_test] mission started`.
2. Take some damage (below 125 health).
3. Throw knives at the ground: no knife line.
4. Throw knives at enemies: each hit logs `knife damage <n> -> heal +25 requested` and the health bar rises by 25.
5. Shoot enemies with your primary: `damage <n> by <weapon> -> no heal (not the knife)`, and no heal.
6. Note any `projectile hits ... by K-2 Throwing Knife` line. None is expected: the knife is a thrown entity, not a
   projectile.

Report a few knife lines (with the logged damage), whether misses stayed silent, whether other weapons logged
`no heal`, and whether the health bar moved. To try damage-proportional healing, set `PROPORTION = 0.25` in
`src/addon.lua`: the heal is then 25% of the damage the game recorded for the knife.

## Limits

- Local player only, polled 10 times per second: two knife hits in the same tenth of a second heal once (the event
  sums their damage).
- The game records damage per source, not per victim. Which enemy was hit is not reported.
- Heals of your own avatar are replicated by the game itself; this was proven as host (see `KillHealTest`).
