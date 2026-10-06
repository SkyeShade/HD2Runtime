# EpochExplosionsTest

Live test for the PLAS-45 Epoch's three explosions and the RS-422 Railgun's overcharge explosion (docs/support-weapon-
api.md "Charge-level shots and explosions"). Uses the MODS tab (page **Epoch Explosions Test**). The log starts with
`EPOCH EXPLOSIONS 0.1.0 BUILD`; then one `APPLIED` line per option that is on.

How the Epoch picks what it fires: its own charge record, read when you release the trigger.

| You do | The Epoch fires / spawns | Role | Vanilla |
| --- | --- | --- | --- |
| release after 1 s and before 2.5 s | the partial-charge shot | `attack('primary')`, explosion `attack('primary_impact')` | blast 2.3 / 3 / 4 m, 500 damage |
| release at 2.5 s or later (also past 2.6 s) | the full-charge shot | `attack('full_charge')`, explosion `attack('full_charge_impact')` | blast 3 / 4 / 5 m, 800 damage |
| keep holding: 3.25 s after the overcharge time | nothing is fired; the Epoch is destroyed and explodes **in your hands** | `attack('overcharge_explosion')` | 3 / 4 / 5 m, 800 damage: **kills you** |

Explosion rows are read when the explosion happens, so an `APPLIED` write changes the next explosion. A projectile row is
copied into a shot when it is fired, so a projectile write changes the next shot. The full-charge explosion and the
overcharge explosion share **one damage row**: changing the overcharge damage also changes the full-charge blast damage.

| Option | Default | Fields | Vanilla -> test |
| --- | --- | --- | --- |
| Harmless overcharge (keep on) | **on** | Epoch `overcharge_explosion` damage standard / durable / push force (shared with `full_charge_impact`) | 800 / 800 / 30 -> 1 / 1 / 0 |
| Wide overcharge blast | off | Epoch `overcharge_explosion` inner / outer / shockwave radius | 3 / 4 / 5 m -> 15 / 18 / 20 m |
| Big partial-charge blast | off | Epoch `primary_impact` radii | 2.3 / 3 / 4 m -> 9.2 / 12 / 16 m |
| Big full-charge blast | off | Epoch `full_charge_impact` radii | 3 / 4 / 5 m -> 9 / 12 / 15 m |
| Slow full-charge shot | off | Epoch `full_charge` projectile velocity | 250 -> 60 m/s |
| Gentle Railgun overcharge (keep on) | **on** | RS-422 `overcharge_explosion` damage standard / durable / push force | 300 / 300 / 40 -> 1 / 1 / 0 |

## Safety first

- **Never hold the Epoch past 3 s while "Harmless overcharge" is off, and never hold the Railgun in Unsafe mode past
  3 s while "Gentle Railgun overcharge" is off.** The overcharge explosion spawns in your hands and kills you in vanilla.
- With "Big partial-charge blast" or "Big full-charge blast" on, shoot targets **30 m away or more**: the bigger blast
  hurts you too.
- Before the overcharge steps, confirm the log line `transaction epoch-harmless-overcharge APPLIED` (and
  `transaction railgun-gentle-overcharge APPLIED`). If it says REJECTED or anything else, do not overcharge.

## Checklist (host, in a mission, Epoch and Railgun called in; a group of small enemies helps)

- [ ] Log shows `EPOCH EXPLOSIONS 0.1.0 BUILD`, `transaction epoch-harmless-overcharge APPLIED` and
      `transaction railgun-gentle-overcharge APPLIED`.
- [ ] **Harmless overcharge** (on): hold the Epoch's trigger and keep holding past 2.6 s; about 3.25 s later the Epoch is
      destroyed and explodes. **You survive and are not thrown** (vanilla: 800 damage kills you). Note your health
      before and after.
- [ ] Same option, shared damage row: fire a **full-charge** shot (release at 2.5 s or later) into a group: only the
      enemy hit directly dies (the shot's own 400 damage); the blast no longer kills the others. A **partial-charge**
      shot (release between 1 s and 2.5 s) into a group still kills with its blast (500 damage, 3 m).
- [ ] **Wide overcharge blast** with Harmless overcharge still on: self-destruct the Epoch near enemies 10 to 15 m away:
      they flinch (the blast keeps its stagger); vanilla reaches 4 m.
- [ ] Turn **Harmless overcharge off** (log: disabled). From now on do not overcharge the Epoch.
- [ ] **Big partial-charge blast**: partial-charge shots (release between 1 s and 2.5 s) kill enemies up to about 12 m
      from the impact; full-charge shots still blast only about 4 m.
- [ ] **Big full-charge blast** (turn Big partial-charge blast off): full-charge shots kill enemies up to about 12 m from
      the impact; partial-charge shots blast only about 3 m.
- [ ] **Slow full-charge shot**: full-charge shots crawl (60 m/s instead of 250 m/s) and drop steeply; partial-charge
      shots fly as before.
- [ ] **Gentle Railgun overcharge** (on): Railgun in Unsafe mode, hold 3 s: it fires, is destroyed and explodes; **you
      survive and are not thrown** (vanilla 300 damage).
- [ ] Turn every option off: the log shows each operation disabled; behaviour is vanilla again (do not overcharge).

Report for each line: what you saw, your health before and after an overcharge, and the APPLIED / REJECTED log lines.
Also report whether other players' Epochs changed (writes change this machine's copy; untested).
