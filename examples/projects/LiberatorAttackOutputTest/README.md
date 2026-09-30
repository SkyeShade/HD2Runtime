# LiberatorAttackOutputTest

Live test: one Mod Options choice (**Liberator output**) switches what the AR-23 Liberator fires. The Liberator keeps
its own magazine, ammunition use, reload, rate of fire and handling.

**Live result (2026-09-29): EAT-700 Napalm and GL-52 Arc (impact) pass.** The donor packages loaded automatically, the
Liberator fired the EAT-700 napalm projectile and the GL-52 grenade, and the GL-52 impact released its arc. The
LAS-58 Talon control choice was not reported.

Needs HD2Runtime 0.28.0 and Mod Options Menu. The option ID is
`liberator_attack_output.output`, on the MODS tab page "Liberator Attack Output". Change the choice, then press
APPLY. The donor's package is loaded first, automatically: nobody has to bring the Talon, EAT-700 or GL-52.

## What changed since the first build

The first build wrote the Liberator's `attack.projectile` (ProjectileWeapon +0). In play that changed nothing, with
the new and the older API alike, while the identical write on the SMG-32 Reprimand works. The reason is in the game
data: the Liberator's default ammunition customization, **RIFLE 5,5x50mm. FULL METAL JACKET**, carries an entity delta
that overwrites ProjectileWeapon +0 with its bullet whenever the weapon is built. The member we wrote was dormant. The
Reprimand has no ammunition customization, so its member is the projectile it fires.

This build writes the Liberator's **active source**, the projectile of that default ammunition
(`weapon:ammunition():projectile()`). `attack.projectile` on the Liberator is now refused with
`DORMANT_PROJECTILE_REFERENCE`.

| Choice | What the Liberator should fire |
| --- | --- |
| Vanilla (default) | Its own bullet. Restores the exact original ammunition projectile. |
| LAS-58 Talon (control) | The Talon laser bolt. This donor is live-proven on the Reprimand, so this choice tests the corrected host path alone. |
| EAT-700 Napalm | The EAT-700 Expendable Napalm rocket (cross-class). |
| GL-52 Arc (impact) | The GL-52 De-Escalator grenade, whose impact explosion releases an arc (cross-class). |

LAS Beam, Trident and ARC-3 Arc are not offered. Beams and arcs are fired by their own weapon components, which a
projectile weapon cannot reference (see `docs/attack-outputs.md`).

## When a change takes effect

The ammunition delta is applied **when the game builds the weapon**. The write lands immediately (the log shows
`APPLIED`), but the Liberator you are already holding may keep its current projectile until the game builds a new
one. Test it in this order, and report what you see at each step:

1. **In the ship.** Choose **LAS-58 Talon (control)**, press APPLY, then deploy with the Liberator.
2. **Mid-mission.** Switch to another choice and press APPLY. First fire the Liberator you are holding: does it change
   right away? Then get a freshly built Liberator (be reinforced) and fire again.
3. **Back to Vanilla.** Choose Vanilla, APPLY, get a freshly built Liberator, and confirm normal bullets with no
   leftover rocket, grenade, arc or laser behaviour.

Only the Liberator should be affected: its FULL METAL JACKET ammunition is not the default of any other weapon, and
only the Liberator carries it in its unlock list. If another weapon changes too, report it.

## What to observe

**LAS-58 Talon (control).** Liberator shots are visible Talon laser bolts that hit and damage, at the Liberator's
normal rate, with one Liberator round per shot. If this works, the corrected host path works.

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
| The donor projectile on a freshly built Liberator, one round per shot | **Ammunition source works.** Say whether it also changed on the Liberator you were already holding. |
| The Talon control works, but EAT-700 or GL-52 do not | The host path works; the cross-class output is the problem. Report which part is missing. |
| No choice changes anything, even when set in the ship before deploying | **The edited ammunition delta is not re-applied** (cached at load, or read from elsewhere). Report it with the log. |
| `HD2Runtime.log` shows `ASSET_UNAVAILABLE` or a package wait that never finishes | **Assets not loaded:** Runtime refused to write without the donor package. Nothing changed. |
| The log shows `AMMUNITION_SOURCE_CHANGED` | The game data no longer matches the reviewed ammunition source; Runtime refused the write. |
| A rocket or grenade appears but has no explosion, fire or arc | **Partial output:** the projectile row works but part of its chain did not. |
| After returning to Vanilla and rebuilding, rounds still explode, burn or fire lasers | **Stale composition:** this should be impossible (each choice is a single reference). Report it with the log. |

`HD2Runtime.log` should show `ensure liberator-attack-output` resolving and `APPLIED` after each APPLY. For a donor
choice, a package request precedes the write the first time.
