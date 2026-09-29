# KillStackDamageTest

Acceptance test for event-driven state (`docs/events.md`): **every enemy kill credited to the local player adds +10%
AR-23 Liberator damage, up to +100% (90 → 180 standard damage), reset when a mission starts or ends.**

It proves: killer attribution, mission-scoped Lua state (`mod.mission`), the mission reset events, cap logic, and a
script value (`mod:value`) driving a guarded `hd2.ensure` from event callbacks.

## Limits (stated plainly)

- **Not a per-hit modifier.** A pre-damage event is not possible without patching game code (see
  `docs/events.md#damage`). The bonus changes the Liberator's damage **definition**: every Liberator in the game —
  yours, a teammate's, and the StA-52 and Liberator Carbine that share the row — deals the boosted damage. Each change
  re-applies after about half a second (the ensure debounce plus a guarded resolution).
- **Any weapon's kills count.** The game data Runtime can read credits a kill to a player, not to a weapon.

## How to test

1. Equip the AR-23 Liberator and deploy. The log shows `mission started: 0 stack(s), Liberator damage 90 (+0%)`.
2. Kill enemies. Each kill logs `killed <enemy>: N stack(s), Liberator damage <90+9N> (+<10N>%)` and then
   `kill-stack-liberator-damage` `APPLIED`.
3. Check that enemies die faster as the stacks grow (for example count Liberator shots on the same enemy type early
   and after 10 kills: about half as many).
4. At 10 stacks the log stops at 180 (+100%).
5. Extract or abandon: `mission ended: Liberator damage back to 90`; the next mission starts from 0.

Report the stack lines, the APPLIED lines, and whether the damage change was visible.
