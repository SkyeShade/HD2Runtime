# SentryTuningTest

Live test for the sentry component fields: spread, recoil, the pitch/yaw coupling, the side/rear targeting ranges and
the Gatling wind-up. It also includes two controls, the yaw limits and an oversized targeting range. It uses the MODS
tab (page **Sentry Tuning Test**).

The log banner is **SENTRY TUNING 0.1.0 BUILD**. Check that this exact line appears, so you know the right build is
loaded.

**What a write changes.** Each field is a member of the sentry's **own deployed entity**. Each sentry owns these
records alone, so no operation needs `allow_shared`. It is a **type-record write**: every deployment of that sentry on
this machine uses the new value until the option is turned off. It is not per deployment.

**When it takes effect.** Spread, recoil and the targeting ranges are copied into a sentry when it **spawns**. Set
those options first, then call the sentry in; a sentry already standing keeps its old values. The coupling, the yaw
limits and the wind-up are read live, so they also change a sentry that is already standing.

**Acknowledgements.** Nothing new here is live-proven yet, so every new field sets `allow_unverified_effect`.
`targeting.range` is live-proven and needs no acknowledgement.

| Option | Default | What it does | Fields |
| --- | --- | --- | --- |
| MG-43: very wide spread | on | MG-43 spread 10/10 -> 300/300 mrad | `weapon.horizontal_spread`, `weapon.vertical_spread` |
| AC-8: no vertical recoil | on | AC-8 vertical recoil drift and climb 10 -> 0 | `weapon.recoil_drift_vertical`, `weapon.recoil_climb_vertical` |
| AC-8: turn first, then elevate | on | AC-8 pitch/yaw coupling 1 -> 10 | `turret.pitch_yaw_coupling` |
| M-12: elevate while turning | on | M-12 pitch/yaw coupling 4 -> 0 | `turret.pitch_yaw_coupling` |
| G-16: slow spin-up | on | G-16 wind-up 0.5 -> 6 s | `windup.wind_up_seconds` |
| MG-43: blind flanks and rear | off | MG-43 side range -1 -> 10 m, rear range -1 -> 3 m | `targeting.side_range`, `targeting.rear_range` |
| MG-43: +-30 degree traverse | off | MG-43 yaw limits -180/180 -> -30/30 | `turret.yaw_min`, `turret.yaw_max` |
| MG-43: range 300 m (control) | off | MG-43 targeting range 75 -> 300 m | `targeting.range` |

## Before the mission

1. Install this mod, Bingus and the HD2Runtime build being tested (0.30.0 or later).
2. Take **A/MG-43 Machine Gun Sentry**, **A/AC-8 Autocannon Sentry**, **A/M-12 Mortar Sentry** and
   **A/G-16 Gatling Sentry**. Repeat over several missions if your loadout is full.
3. Play as the host (solo is simplest). Set the options **before** calling each sentry in.

## Checklist

- [ ] **Log.** It shows `SENTRY TUNING 0.1.0 BUILD` and `APPLIED` for each enabled operation:
      `sentry-mg43-spread`, `sentry-ac8-recoil`, `sentry-ac8-coupling`, `sentry-m12-coupling` and
      `sentry-g16-windup`, plus any off-by-default option you turn on.
- [ ] **MG-43, very wide spread.** The tracers fan out visibly, about +-8.6 degrees. At 30 m most rounds miss a
      single target. Vanilla is a tight stream.
- [ ] **AC-8, no vertical recoil.** Its shots stay on target while it fires. Vanilla: the aim kicks upward a little
      with each shot.
- [ ] **AC-8 coupling 10.** When an enemy appears to the side, the sentry first turns to face it with its barrel
      level, then elevates. Vanilla turns and elevates together. The effect is easiest to see on a target above or
      below the sentry.
- [ ] **M-12 coupling 0.** The mortar raises its barrel while it is still turning. Vanilla mostly turns first, then
      raises.
- [ ] **G-16 wind-up 6 s.** The barrels spin up slowly over about 6 s. Note whether the first shot waits for the
      spin-up or comes at the usual moment.
- [ ] **MG-43 blind spots** (turn the spread option off and this one on, then call a new MG-43). The sentry still
      engages enemies ahead of its barrel at the usual range. It ignores enemies to its side until they are within
      about 10 m, and enemies behind it until they are within about 3 m.
- [ ] **MG-43 yaw limits.** The turret will not turn more than 30 degrees either side of its deploy direction. This
      one is read live, so a standing MG-43 changes at once.
- [ ] **MG-43 range 300 (control).** The sentry still does not engage enemies beyond about 100 m. The sentry AI
      stops scoring targets at 100 m, so this negative result is expected.
- [ ] **Restore.** Turn each option off and APPLY. The next deployment of that sentry is vanilla again, and the log
      shows the restore. Spawn-copied fields only revert on sentries called in after the restore.
- [ ] **Other sentries.** Sentries you did not change (for example the Rocket Sentry) behave exactly as vanilla.

Report each item as seen, not seen, or unclear, together with the log. For spread, recoil and the ranges, also note
whether the sentry was called in before or after the option was applied.
