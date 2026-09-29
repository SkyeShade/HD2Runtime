# SentryTurnSpeed

Live test: A/AC-8 Autocannon Sentry horizontal turn speed 20 -> 120 degrees per second and vertical turn speed
20 -> 90 degrees per second.

**Result: live-proven (2026-09-29).** The sentry turns dramatically faster; the difference is obvious in play.
`turret.yaw_speed` and `turret.pitch_speed` no longer need `allow_unverified_effect` on any turreted sentry. The aim
limits (`turret.pitch_min/max`, `turret.yaw_min/max`) were not tested and still need it.

What to verify: deploy the Autocannon Sentry and let enemies approach from the side and from behind. The vanilla
sentry needs about 9 seconds to turn around; with this mod it snaps onto targets in well under 2 seconds.
