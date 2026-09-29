# SentryTurnSpeed

Live test: A/AC-8 Autocannon Sentry horizontal turn speed 20 -> 120 degrees per second and vertical turn speed
20 -> 90 degrees per second.

What to verify: deploy the Autocannon Sentry and let enemies approach from the side and from behind. The vanilla
sentry needs about 9 seconds to turn around; with this mod it should snap onto targets in under 2 seconds.

The values are the TurretComponent members that equal the wiki's Horizontal/Vertical Turn Speed on every turreted
sentry. They are not gameplay-proven yet, so the operation passes allow_unverified_effect. Built only.
