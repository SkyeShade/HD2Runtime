# KillHealTest

Acceptance test for the event system (`docs/events.md`): **when the local player kills an enemy, the local player is
healed by 25**, never above maximum health.

It proves: the `entity_killed` event, killer attribution (the game's own last-hit creditor, compared with the local
peer id), local-player identification, the player handle, health change through the game's own heal function
(`AddHealthFraction`, called only after its exact prologue bytes are re-proven), and callback execution. Every heal
it causes is reported by `player_healed` with this mod as the cause.

## How to test

1. Deploy on a mission. `HD2Runtime.log` shows `[mods/hd2runtime_examples/kill_heal_test] mission started`.
2. Take some damage (below 125 health), then kill enemies with any weapon.
3. Every kill credited to anyone logs one line with what the event observed:

   ```
   kill: enemy/v1/automatons/conscript_tier_3 (Marauder) observed=corpse corpse=1234 killer=local player -> heal +25 requested
   player healed +25 -> 105 / 125, cause mod mods/hd2runtime_examples/kill_heal_test
   ```

   - `observed=corpse`: the game had already replaced the enemy by its corpse when Runtime polled (the corpse id is
     logged); `observed=dead_state`: Runtime saw the enemy's dead state first (`corpse=nil`).
   - `killer=local player`, `killer=peer <id>` (a teammate) or `killer=nobody`.

| Situation | Expected |
| --- | --- |
| You kill an enemy while hurt | `-> heal +25 requested`, then `player healed`; the health bar rises by 25 (capped) |
| You kill an enemy at full health | `-> heal +0 requested`, no bar change |
| A teammate kills the enemy | `killer=peer ...` `-> no heal (not credited to the local player)` |
| You destroy something that is not an enemy | `-> no heal (not an enemy)` |
| You are downed or dead | `-> heal refused: the avatar is downed or dead` |

Report a few kill lines (with their `observed=` values: how many were `corpse` and how many `dead_state`), and whether
the health bar visibly moved. If a heal was requested but the bar did not move, say whether you were host (the
`mission started (host ...)` line).

## Limits

- Only the local player can be healed; heals of your own avatar are replicated by the game itself because this
  machine owns it.
- The heal is the game's own function, called from the update callback on the main thread; the exact timing relative
  to the game's own health update is not proven, which is part of what this test checks.
