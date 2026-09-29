# LiberatorAttackOutputTest

Live test: one Mod Options choice (**Liberator output**) switches what the AR-23 Liberator's attack emits, while the
Liberator keeps its own magazine, ammunition use, reload, rate of fire and handling. Built only; nothing here is
gameplay-confirmed yet.

Needs the HD2Runtime coverage test build (not the published 0.27.0) and Mod Options Menu. The option ID is
`liberator_attack_output.output`, on the MODS tab page "Liberator Attack Output". Change the choice, then press
APPLY. No restart is needed. Each change is one atomic write of the Liberator's projectile reference. The donor's
package is loaded first, automatically: nobody has to bring the EAT-700 or the GL-52.

| Choice | What the Liberator fires |
| --- | --- |
| Vanilla (default) | Its own bullet. Restores the exact original reference. |
| EAT-700 Napalm | The EAT-700 Expendable Napalm rocket |
| GL-52 Arc (impact) | The GL-52 De-Escalator grenade, whose impact explosion releases an arc |

LAS Beam, Trident and ARC-3 Arc are not offered. Beams and arcs are fired by their own weapon components, which a
projectile weapon cannot reference (see `docs/attack-outputs.md`). A choice for them could not do anything.

## What to observe

**Vanilla.** Normal Liberator bullets. Use it to reset between tests. Switching back must fully restore the normal
bullet, with no leftover rocket, grenade or arc behaviour.

**EAT-700 Napalm.**
- Each trigger pull, at the Liberator's normal rate and fire mode, should launch an EAT-700 napalm rocket instead of a
  bullet. It is a slower (200 m/s), heavy projectile with a visible rocket.
- **Impact:** an explosion (radii about 1.6 / 8 / 10 m) that sets targets on fire. Napalm submunitions scatter and burn
  the area.
- **Ammunition:** each rocket takes one Liberator round (30 per magazine); reload is the Liberator's own. There is no
  backblast: that belongs to the EAT-700 weapon, not its rocket.
- Automatic fire means a stream of rockets. Try single fire first, and keep your distance.

**GL-52 Arc (impact).**
- Each shot should fire a De-Escalator grenade: a slow (100 m/s) lobbed projectile.
- **Impact:** a small blast (about 1 / 3 / 4 m), then an electric arc that jumps from the impact point to nearby
  targets. It chains up to 2 times, splits up to 2 ways, reaches about 10 m, and stuns.
- The arc starts at the impact, not the muzzle. There is no ARC-3 charge-up: charge is ARC-3 fire control, not part
  of the arc.
- **Ammunition:** one Liberator round per shot, with the Liberator's own reload.

## Telling the outcomes apart

| You see | Meaning |
| --- | --- |
| The donor projectile with its explosion, fire or arc, one round per shot | **Successful output swap** |
| `HD2Runtime.log` shows `ASSET_UNAVAILABLE` or a package wait that never finishes, and the Liberator still fires bullets | **Assets not loaded:** Runtime refused to write without the donor package. Nothing changed. |
| The log shows `APPLIED`, but shots are invisible or do nothing | **Accepted but inert:** the reference changed, but the game did not render or run that projectile from this host. Report it: it would mean something outside the projectile row matters. |
| A rocket or grenade appears but has no explosion, fire or arc | **Partial output:** the projectile row works but part of its chain did not. Report which part is missing. |
| After switching to Vanilla, bullets still explode or burn | **Stale composition:** this should be impossible (each choice is a single reference). Report it with the log. |

`HD2Runtime.log` should show `ensure liberator-attack-output` resolving and `APPLIED` after each APPLY. For a donor
choice, a package request precedes the write the first time.
