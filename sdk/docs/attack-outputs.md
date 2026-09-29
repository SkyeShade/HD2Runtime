# Attack outputs

Can an ordinary magazine-fed ballistic weapon keep its own fire control and ammunition while its attack produces a
different kind of output? This page records what the native data allows, and the Runtime API built on it.
- Research: `scripts/research_attack_outputs.py` → `research/attack-outputs-F5FEE03DCFDB.json`.
- Catalog: `sdk/AttackOutputCapabilities.json` (contract `hd2runtime.attack_outputs.v1`).

## Native model

A weapon entity owns **exactly one output-family component**, next to its fire-control and resource components:

| Output family | Component | Output reference | Also owns |
| --- | --- | --- | --- |
| projectile (bullets, rockets, grenades) | ProjectileWeaponComponent | +0 ProjectileType | rounds per minute (+8), infinite ammo (+36) |
| beam | BeamWeaponComponent | +0 BeamType | beam fire mode (+100), heat buildup (+16), pulse members |
| arc | ArcWeaponComponent | +0 ArcType | rounds per minute (+4), infinite ammo (+8) |
| spray | SprayWeaponComponent | +200 DamageInfoType | |
| melee | MeleeWeaponComponent | +12 DamageInfoType | |

The fire-control and resource components sit alongside the output component:
- **WeaponData:** handling, recoil, spread and fire modes.
- **Resource:** WeaponMagazine, WeaponRounds, WeaponHeat or WeaponCharge.
- **WeaponReload.**

For example:
- the Liberator is ProjectileWeapon + WeaponMagazine + WeaponReload;
- the LAS-98 and Trident are BeamWeapon + WeaponHeat + WeaponReload;
- the ARC-3 is ArcWeapon + WeaponCharge;
- the ARC-12 Blitzer fires arcs with no WeaponCharge at all. Charge is ARC-3 fire control, not part of the arc output.

**There is no common output abstraction.** The three references are different enum types indexing different settings
tables. There is no shared output interface or tagged union. A scan of every struct in the type library found only
these cross-family links in settings data:
- ProjectileInfo +144 / +156 → ExplosionType: impact and expiry explosions;
- ExplosionInfo +84 → ProjectileType: shrapnel or submunitions;
- ExplosionInfo +120 → ArcType: **an explosion can release an arc**;
- BeamInfo +96 → ExplosionType, and WeaponChargeComponent +200 → ExplosionType.

Nothing outside the beam system references a BeamType: only BeamWeaponComponent, BeamInfo and the BeamPrisms type
do. BeamPrisms (light and heavy beam types with heat multipliers) exists in the type library but is embedded in no
struct in this build.

## The Liberator experiments

| Requested output | Result | Why |
| --- | --- | --- |
| **LAS Beam** (LAS-98) | **blocked** | A beam is fired only by a BeamWeaponComponent, which also owns the beam's fire mode and heat buildup. The Liberator has no such component and no heat, and nothing a projectile does can reference a beam. It would need the Liberator entity's component composition changed, which is not a reference write. |
| **Trident** (LAS-13) | **blocked** | The same family boundary. See below for how the Trident differs. |
| **EAT-700 Napalm** | **supported** | Same family. The Liberator's ProjectileWeapon +0 reference becomes the EAT-700 rocket, and everything the rocket does hangs off its own projectile row (details below). |
| **ARC-3 Arc** | **blocked** | The ARC-3's arc (ArcType 7) is emitted only by its ArcWeaponComponent. No explosion references it. |
| Arc on impact (native alternative) | **supported** | A projectile-family swap to the GL-52 De-Escalator grenade. Its impact explosion releases a native arc (ExplosionInfo +120). |

**Trident.** It is one BeamWeaponComponent (BeamType 6) in BeamFireMode 6; the continuous beams use 4. Where the
continuous beams have 60 / 1 / 0, the Trident has +104 = 300, +108 = 2 and +112 = 0.15. It also uses a single-fire
audio event instead of loop start/stop. No member counts beams, so beam count, spread, tick and pulse behaviour stay
unidentified and read-only.

**EAT-700 chain.** Everything the rocket does hangs off its own projectile row:
- impact explosion: 250 damage, fire, radii 1.6 / 8 / 10 m;
- that explosion's napalm submunition projectile, and the submunition's own fire explosion;
- the burning statuses.

**ARC-3 alternatives, both refused.**
- Firing the ARC-3 arc from the Liberator's muzzle would need an ArcWeaponComponent on the Liberator entity.
- Releasing it at impact would mean re-pointing a shared explosion row's arc member. The only arc explosions belong
  to the G-31 Arc grenade and the GL-52, so both would change.

**What the host keeps in the supported swaps.** Only ProjectileWeapon +0 changes. The Liberator keeps:
- its WeaponMagazine: 30 rounds and ammunition consumption;
- its WeaponReload;
- its rounds per minute (640) and trigger behaviour, which live in its own ProjectileWeapon component;
- its handling (WeaponData).

The output brings its projectile's flight, damage, explosions, submunitions, arcs and statuses. It does not bring
backblast, charge or heat.

## API

```lua
local host=hd2.weapon('AR-23 Liberator'):attack('primary')
host:output():describe()                      -- {family='projectile', compatibilityClass='conventional_plain', ...}
hd2.attack_output('EAT-700 Expendable Napalm') -- typed handle (semantic ID or owner name)
hd2.attack_outputs({family='beam'})           -- catalogued IDs

hd2.ensure({patch={id='liberator-napalm',target=host,allow_unverified_reference=true,allow_unverified_effect=true,
    field=hd2.fields.attack.projectile,expect=host:projectile(),value=hd2.attack_output('EAT-700 Expendable Napalm')}})
```

- **Backward compatibility.** `attack:projectile()` and projectile-reference swaps between player weapons are
  unchanged. A same-class swap needs no new acknowledgement, whether the value is a weapon's `projectile()` handle or
  an `attack_output` handle.
- **Cross-class projectile outputs** need `allow_unverified_reference` and `allow_unverified_effect`. Examples: a
  ballistic host firing a rocket or an arc grenade.
- **Host eligibility.** The host must be a **magazine-fed projectile host**, where every round is ProjectileWeapon
  +0:
  - a WeaponMagazine with an empty magazine pattern;
  - no WeaponRounds, WeaponCharge or WeaponHeat that selects projectiles by ammo type, charge or heat level.

  58 weapons qualify. Others fail with `CROSS_CLASS_HOST_REJECTED`, and the host composition is re-proven live
  before every write.
- **Beam, arc, spray and melee outputs** fail closed with `INCOMPATIBLE_OUTPUT_FAMILY` and the structural reason.
- **Source proof.** The output's owner entity, its ProjectileWeapon record identity and the ProjectileSettings row are
  re-proven live. A stale source is a CONFLICT.
- **Assets.** The owner's loadout package is loaded through the 0.27 asset loader before the reference is written.
  The donor weapon never needs to be equipped. The loader's order is unchanged: dependency known, loader verified
  for the build, package requested, package resident, then the reference is written.
- **Mod Options.** A choice option's `values` may be reference handles, so one dropdown can select between complete
  output compositions. Each choice is a single reference value, so switching choices is one atomic write.

## Catalog and proof model

`sdk/AttackOutputCapabilities.json` lists 105 outputs: 89 projectile, 3 beam, 2 arc, 4 spray and 7 melee. 78
projectile outputs are selectable. Each entry records:
- family and kind: ballistic, explosive, explosive submunition, arc on impact, continuous beam, pulsed multi-beam,
  arc, spray or melee;
- owner, emitter component and structural class;
- package and auto-load support;
- compatible host families, required coordinated references (none, for projectile outputs) and acknowledgements;
- live proof;
- for blocked families, the reason.

No native identifier is published.

Four proof levels are kept separate:
1. **Identity:** the owner and settings row are re-proven live.
2. **Assets:** the package is loaded.
3. **Structural:** one ProjectileType reference; cross-family is blocked.
4. **Gameplay:** live-proven only by a user-run test. No cross-class output has been live-tested yet.

## Validation

`scripts/validate_attack_output_snapshot.py` runs on the retained snapshot:
- the Vanilla no-op;
- byte-exact apply and rollback for the EAT-700, GL-52 and Talon outputs;
- the CONFLICT when a plain patch meets another output;
- family, acknowledgement, non-host, stale-source and host-magazine-pattern rejections.

The packaged-runtime scenario for `LiberatorAttackOutputTest` switches the Mod Options choice through every
composition from the built ZIP. It checks each package request, and that Vanilla restores the baseline.

## Live test

The test mod is `LiberatorAttackOutputTest`, a Mod Options choice with Vanilla, EAT-700 Napalm and GL-52 Arc
(impact). It is built only, not yet gameplay-confirmed. See its README.
