# RailgunChargeTest

Live test for the charge fields (`hd2.fields.charge.*`, docs/support-weapon-api.md "Charge"). Uses the MODS tab
(page **Railgun Charge Test**). The log starts with `RAILGUN CHARGE 0.1.0 BUILD`; then one `APPLIED` line per option
that is on.

Every field is a member of the weapon's own WeaponChargeComponent record, read live by the native charge code every
frame. An APPLIED write takes effect immediately, also on a Railgun already in your hands; no new call-in is needed.

The Railgun has two fire modes: **Safe** (the charge stops at the full charge time and waits for you to release) and
**Unsafe** (it keeps charging; at the overcharge time it fires, is destroyed and explodes). Switch with the
weapon-function key. Vanilla: minimum 0.45 s, full 0.5 s, overcharge 3 s.

| Option | Default | Field(s) | Vanilla -> test |
| --- | --- | --- | --- |
| Slow charge | on | charge.level_1 / level_2 / level_3 (one transaction) | 0.45 / 0.5 / 3 s -> 0.05 / 2 / 8 s |
| No overcharge explosion | off | charge.explode_at_overcharge | on -> off |
| 5 s hold limit | off | charge.overcharge_limit_seconds | 0 (off) -> 5 s |
| Auto fire at full charge | off | charge.auto_fire_at_full | off -> on |
| Crawling minimum shot | off | charge.speed_multiplier_min | 0.7 -> 0.05 |
| Weak overcharged armor penetration | off | charge.penetration_multiplier_overcharge | 1.0 -> 0.2 |
| Huge overcharged damage | off | charge.damage_multiplier_overcharge | 2.5 -> 10 |
| Epoch overcharge explosion | off | charge.overcharge_explosion | RS-422 Railgun -> PLAS-45 Epoch |
| Arc Thrower 3-arc burst | off | ARC-3 charge.burst_shots / burst_interval_seconds | 0 / 0 -> 3 / 0.25 s |

## Checklist (host, in a mission, Railgun called in)

- [ ] Log shows `RAILGUN CHARGE 0.1.0 BUILD` and `transaction railgun-charge-times APPLIED`.
- [ ] **Slow charge**, Safe mode: a tap fires at once (minimum 0.05 s). Holding: the "full" sound and the charge
      reticle arrive only after about 2 s (vanilla 0.5 s).
- [ ] **Slow charge**, Unsafe mode: hold. Nothing explodes at 3 s; the Railgun fires and explodes at about 8 s.
- [ ] Slow charge **off**, **No overcharge explosion** on, Unsafe: hold 10 s: no explosion. Release fires a fully
      overcharged shot (2.5x damage).
- [ ] Slow charge off, No overcharge explosion **and** **5 s hold limit** on, Unsafe: hold. Past 3 s nothing happens;
      at about 5 s the Railgun explodes **without firing** (vanilla: fires and explodes at 3 s).
- [ ] **Auto fire at full charge**, Safe mode (slow charge on makes it obvious): keep the trigger held; the shot leaves
      by itself when the charge is full.
- [ ] **Crawling minimum shot**: tap-fire (release right at the minimum charge): the round crawls (about 100 m/s
      instead of 1400 m/s) and drops visibly. A full Safe shot is unchanged.
- [ ] **Weak overcharged armor penetration**, Unsafe: shots released near the overcharge time bounce off medium armor
      (for example a Charger's leg or a Hulk's front); Safe shots still penetrate.
- [ ] **Huge overcharged damage**, Unsafe: a late shot kills heavy targets in one hit.
- [ ] **Epoch overcharge explosion** (log: a package request for the Epoch, then APPLIED), Unsafe: the failure
      explosion is the Epoch's big blast (800 damage, 3 / 4 / 5 m) instead of the Railgun's small one (300 damage,
      0.4 / 2 / 3 m). Stand back.
- [ ] **Arc Thrower 3-arc burst**, ARC-3: one charge fires three arcs, 0.25 s apart.
- [ ] Turn every option off: the log shows each operation disabled; behaviour is vanilla again.

Report for each line: what you saw, and the APPLIED / REJECTED log lines. Also report whether other players' Railguns
changed (writes act where the weapon is simulated; untested).
