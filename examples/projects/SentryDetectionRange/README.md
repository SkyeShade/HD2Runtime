# SentryDetectionRange

Live test: A/MG-43 Machine Gun Sentry targeting range 75 m -> 25 m.

**Result: live-proven (2026-09-29).** The sentry ignores enemies at normal sentry distances and starts targeting
only when they are very close. `targeting.range` no longer needs `allow_unverified_effect` on any sentry.

What to verify: deploy the Machine Gun Sentry in the open. Vanilla, it opens fire on enemies about 75 m away. With
this mod it ignores them until they come within roughly 25 m, even with clear line of sight.
