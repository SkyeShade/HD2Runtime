# PlayerKillCreditedExample

Small example of per-source kill credit (`docs/event-scripting.md#10-source-attribution-what-can-and-cannot-be-known`).

The game keeps the local player's mission stats per source: each kill it credits to you is recorded under the weapon,
throwable or stratagem payload that made it. `player_kill_credited` reports how those counters grew since the
previous check (ten a second). This mod logs them:

```
player kill credited: +4 (total 37)
  Eagle Strafing Run +3
  R-36 Eruptor +1
```

## What it is not

It does not say which enemy each source killed. `entity_killed` tells which entity died and which player the game
credits; `player_kill_credited` tells which source increased your cumulative kill stats. The two cannot be linked to
each other per death.

## How to test

Deploy and kill enemies with different weapons, a grenade and a stratagem. Each credit logs one line per source.
An unnamed source (`unnamed source <type>`) is a type the catalog cannot name uniquely (for example the hellpod,
which many stratagems share); `(recorded without a source)` is growth the game recorded with no source.

Report the lines together with what you used, especially any source that is unnamed or named wrongly.
