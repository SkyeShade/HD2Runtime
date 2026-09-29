# SentryDetectionRange

Live test: A/MG-43 Machine Gun Sentry targeting range 75 m -> 25 m.

What to verify: deploy the Machine Gun Sentry in the open. Vanilla, it opens fire on enemies about 75 m away.
With this mod it should ignore enemies until they come within roughly 25 m, even with clear line of sight.

SensorEyeComponent +0 equals the targeting range the wiki states for seven sentries (75/100/125/50 m). It is not
gameplay-proven yet, so the operation passes allow_unverified_effect. Built only.
