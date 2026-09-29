# KillHealTest

Acceptance test for the event system (`docs/events.md`): **when the local player kills an enemy, the local player is
healed by 25**, never above maximum health.

It proves: the `entity_killed` event, killer attribution (the game's own last-hit creditor, compared with the local
peer id), local-player identification, the player handle, health change through the game's own heal function
(`AddHealthFraction`, called only after its exact prologue bytes are re-proven), and callback execution. Every heal
it causes is reported by `player_healed` with this mod as the cause.

## How to test

1. Deploy on a mission. `HD2Runtime.log` shows `[mods/hd2runtime_examples/kill_heal_test] mission started`.
2. Take some damage (below 125 health), then kill an enemy with any weapon.
3. The log shows `killed <enemy>: heal +25 requested` and then `player healed +25 -> <health> / 125, cause mod
   mods/hd2runtime_examples/kill_heal_test`. Your health bar rises by 25 (less when you were within 25 of full).

| Situation | Expected |
| --- | --- |
| You kill an enemy while hurt | Health +25 (capped at maximum); log lines above |
| You kill an enemy at full health | No change (`heal +0`) |
| A teammate kills the enemy | No heal (the kill is credited to them) |
| An enemy dies to the environment (fall, fire with no creditor) | No heal |
| You destroy something that is not an enemy (for example a drilling charge) | `local kill of a non-enemy`: no heal |
| You are downed or dead | Refused: `the avatar is downed or dead` |

Report the log lines around a kill, and whether the health bar visibly moved. If a heal was requested but the bar did
not move, say whether you were host (the `mission started (host ...)` line).

## Limits

- Only the local player can be healed; heals of your own avatar are replicated by the game itself because this
  machine owns it.
- The heal is the game's own function, called from the update callback on the main thread; the exact timing relative
  to the game's own health update is not proven, which is part of what this test checks.
