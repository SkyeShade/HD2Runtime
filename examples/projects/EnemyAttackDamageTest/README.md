# EnemyAttackDamageTest

Live test: Spewer bile artillery ("Bile Bombard"). Direct-hit damage 500 -> 50 and its explosion 200 -> 20.

**Result: not tested yet (2026-09-29).** Runtime applied the writes cleanly, but the Spewer artillery attack could
not be reliably provoked in play. Enemy attack fields stay offline-proven and need `allow_unverified_effect`.

What to verify: on a Terminid mission, let a Bile or Rupture Spewer's arcing artillery land on or next to you.
Vanilla, a direct hit (500 damage) far exceeds a Helldiver's health and the splash (200) is also severe. With this
mod, either should take only a small share of your health. The close-range bile spray is a different attack and stays
vanilla, so it is the control.
