# PelicanWeaponBehaviorProof 0.1.0 (development only, solo host): the Pelican's own chin turret, continuous fire

The Pelican keeps its own chin turret: its entity, model, node 41 and targeting AI. Only its weapon behaviour changes,
for that one Pelican, through the game's own routines. No shared definition is written. Research:
research/docs/pelican-cas-F5FEE03DCFDB.md, section 17.

## The burst, found

The chin turret's AI (behaviour 645) is a four-stage machine:
- **stage 2** aims for at least **1.5 s**;
- entering **stage 3** pulls the trigger and stamps its own fire-window start;
- **0.5 s later** it goes back to stage 2, releasing the trigger.

Both durations are constants in the AI's code, so the weapon's RPM cannot change them. The Gatling Sentry's AI, by
contrast, holds the trigger for its whole firing stage and stops only when its own conditions end it.

**Continuous fire:** each time this turret starts firing, one guarded write moves its own fire-window start 1 h ahead.
It then keeps firing until its AI itself leaves the stage (no target, no line of fire), as the Gatling's does.

## What it does

3 s into each Pelican CAS hover, once:
- **Weapon:** the game's copy routine gives the turret its own ProjectileWeapon record. Then **projectile 148** and the
  configured **RPM** (default **600**) are set on it.
- **Continuous fire:** on by default.
- **Gatling ammo pattern** 148, 148, 148, 242, 148: **off by default**. Ctrl+F10 turns it on. It uses the game's
  magazine copy routine to give the turret its own magazine record with that pattern, plus the pattern mode and length
  the game itself derives from such a magazine.
- **Spin-up:** not available. It is a component the turret's type does not have, and no game routine adds one to a
  live entity.

The projectile's package is requested through the Runtime's asset loader first (`assets for pelican-weapon
requested`, then `resident`). No Gatling Sentry is needed in the loadout.

Every 2 s while it acts, `WEAPON FIRE` reports:
- the rounds fired and the measured rounds per minute;
- whether it is in its firing stage;
- how many times it entered that stage (bursts) and how many holds were applied;
- its shot interval, chambered round and rounds left.

`WEAPON SUMMARY` comes when the Pelican leaves.

**Keys** (each applies to Pelicans seen from then on):
- Ctrl+Shift+F2: RPM 600 -> 1000 -> 1600 -> 300.
- Ctrl+F9: continuous on/off.
- Ctrl+F10: pattern on/off.
- Ctrl+Shift+F1: status.

## Which build is running

The first line is `PelicanWeaponBehaviorProof 0.1.0 CHIN TURRET CONTINUOUS-FIRE BUILD (solo host)`.

## Live test

**Setup:** solo host. Install this hand-off's runtime ZIP, `PelicanWeaponBehaviorProof-0.1.0.zip` and
`PelicanCasProof-0.1.1.zip`. Don't install PelicanGatlingProof alongside it: both would act on the same Pelican.

1. In a mission with enemies, call Pelican CAS near enemies. The defaults are 148, 600 RPM, continuous. Watch whether
   the chin gun fires without its bursts.
2. Press Ctrl+F9 (continuous off) and call CAS again. The native bursts at 600 RPM give a comparison.
3. Press Ctrl+F9 again (continuous back on), Ctrl+F10 (pattern on) and Ctrl+Shift+F2 twice (1600 RPM). Call CAS again.

**Send** every line starting with `PelicanWeaponBehaviorProof`, `PELICAN WEAPON`, `WEAPON`, `assets for` and `Ctrl+`.
For each run, say how it fired (bursts or continuous), whether it tracked targets while firing continuously, and
whether you saw tracers.
