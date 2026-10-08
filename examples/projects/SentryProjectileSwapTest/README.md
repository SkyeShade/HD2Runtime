# SentryProjectileSwapTest

Live test of the 0.30.2 sentry and emplacement projectile swaps (`hd2.stratagem(name):attack('primary'):projectile_source()`):

| Stratagem | Fires | What to check |
|---|---|---|
| E/MG-101 HMG Emplacement | APW-1 Anti-Materiel Rifle rounds | the emplacement fires the AMR round (damage, tracer) |
| E/AT-12 Anti-Tank Emplacement | GR-8 Recoilless Rifle rockets | recoilless rockets and their explosions |
| A/AC-8 Autocannon Sentry | PLAS-1 Scorcher plasma | plasma bolts; whether the sentry still hits moving targets (its aim leads for its own shell) |

The write is type-level: every one of these stratagems on this machine changes, including teammates' (their own
machines keep the stock round). The donor packages are loaded before the write. Not live-tested: every write needs
`allow_unverified_effect`.

Report: does each fire the donor round? Any crash, missing explosion or wrong sound? Does the Autocannon Sentry miss?
The log lines `plan sentry-projectile-swap APPLIED` and `assets for ... resident`.
