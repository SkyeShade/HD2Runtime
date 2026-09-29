# KillStackDamageTest

Acceptance test for event-driven state (`docs/event-scripting.md`): **every kill the game credits to the local
player's AR-23 Liberator adds +10% Liberator damage, up to +100% (90 → 180 standard damage), reset when a mission starts
or ends.**

It proves: per-source kill credit (`player_kill_credited`: only the growth the game records under the AR-23 Liberator
counts), mission-scoped Lua state (`mod.mission`), the mission reset events, cap logic, and a script value
(`mod:value`) driving a guarded `hd2.ensure` from event callbacks.

## Limits (stated plainly)

- **Per-source, not per-death.** Liberator kills are counted from the game's own per-weapon kill stat: every +1
  recorded under the AR-23 Liberator is one Liberator kill, and kills with every other weapon, grenade or stratagem add
  nothing. It cannot tell which enemy each kill was, which a stack count does not need. Stats are checked ten times a
  second, so a quick burst can add several stacks in one line.
- **Not a per-hit modifier.** A pre-damage event is not possible without patching game code (see
  `docs/events.md#damage`). The bonus changes the Liberator's damage **definition**: every Liberator in the game
  (yours, a teammate's, and the StA-52 and Liberator Carbine that share the row) deals the boosted damage. Each change
  re-applies after about half a second (the ensure debounce plus a guarded resolution).

## How to test

1. Equip the AR-23 Liberator and deploy. The log shows `mission started: 0 stack(s), Liberator damage 90 (+0%)`.
2. Kill enemies with the Liberator. Each credit logs `N AR-23 Liberator kill(s) credited: S stack(s), Liberator
   damage <90+9S> (+<10S>%)` and then `kill-stack-liberator-damage` `APPLIED`.
3. Kill enemies with another weapon or a stratagem: no stack line.
4. Check that enemies die faster as the stacks grow (for example count Liberator shots on the same enemy type early and
   after 10 kills: about half as many). At 10 stacks the log stops at 180 (+100%).
5. Extract or abandon: `mission ended: Liberator damage back to 90`; the next mission starts from 0.

Report the stack lines, whether other weapons' kills stayed out, the APPLIED lines, and whether the damage change was
visible.
