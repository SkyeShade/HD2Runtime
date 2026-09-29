# EnemyAttackDamageTest

Live test: Spewer bile artillery ("Bile Bombard"). Direct-hit damage 500 -> 50 and its explosion 200 -> 20.

What to verify: on a Terminid mission, let a Bile or Rupture Spewer's arcing artillery land on or next to you.
Vanilla, a direct hit (500 damage) far exceeds a Helldiver's health and the splash (200) is also severe. With
this mod, either should only take a small share of your health. The Spewers' close-range bile spray is a different attack and stays vanilla,
so it is the control.

Evidence:
- The Rupture Spewer's mount slot 1 fires a projectile whose DamageInfo row equals the wiki's Bile Bombard on all
  nine values.
- Runtime re-proves the whole chain before writing.
- Every Spewer class shares the rows.

Built only; the effect on enemy attacks is not yet live-confirmed.
