# GazerHealthTest

Live test: Illuminate Gazer main health 900 -> 90.

Why: the Gazer is the one structure with a proven wiki name and it is easy to recognise, so there is no variant
ambiguity.

What to verify: on an Illuminate mission, shoot a Gazer's eye with a light primary (e.g. AR-23 Liberator) and count
the hits.
- The eye has little armor, its own 700-health pool and forwards all its damage to main health.
- Vanilla it takes many hits. With the mod, main health should run out after one or two.
- The Gazer Spire (a separate native class) stays vanilla, so it is the control.

Structure health is offline-proven only, so the patch passes `allow_unverified_effect`.
