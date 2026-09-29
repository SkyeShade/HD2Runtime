# Attack outputs

Can an ordinary magazine-fed ballistic weapon keep its own fire control and ammunition while its attack produces a
different kind of output? This page records what the native data allows, and the Runtime API built on it.
- Research: `scripts/research_attack_outputs.py` → `research/attack-outputs-F5FEE03DCFDB.json`, and
  `scripts/research_active_projectile_sources.py` → `research/active-projectile-sources-F5FEE03DCFDB.json`.
- Catalog: `sdk/AttackOutputCapabilities.json` (contract `hd2runtime.attack_outputs.v1`, schema 2).

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

## Active projectile source

**Live controls.** Writing ProjectileWeapon +0 to the LAS-58 Talon projectile works on the SMG-32 Reprimand: it fires
Talon bolts. The identical write on the AR-23 Liberator lands cleanly and changes nothing: the Liberator keeps
firing its bullet. That happened with the older projectile-swap API too, and with the EAT-700 and GL-52 choices of
the first test mod. A projectile pointer existing, and a guarded write landing, does not prove the firing path reads
it.

**Why.** A weapon is built from its entity components plus the entity deltas of its customization:

```
WeaponCustomizationComponentData  default (slot, option) pairs
  -> WeaponCustomizableItem (generated_weapon_customization_settings)   option ID, AddPath, slots
  -> entity delta keyed by that AddPath (ComponentEntityDeltaStorage)
       component index, member offset, bytes: applied when the weapon is built
```

Ammunition items (customization slot 6) patch **ProjectileWeaponComponentData +0 itself**. The Liberator's default
customization carries **RIFLE 5,5x50mm. FULL METAL JACKET**, whose delta sets +0 to its bullet (276) whenever a
Liberator is built. The base member is therefore dormant: whatever it holds is overwritten. The Reprimand's defaults
(laser sight, holographic sight, paint) patch no projectile member, so its base +0 is what it fires. The base value
equals the ammunition value on the Liberator, which is why nothing looked different offline.

**Every projectile-like reference a weapon reaches** (members found by type in the pinned type library, through
nested structs and arrays):

| Reference | Role |
| --- | --- |
| ProjectileWeapon +0 ProjType | the fired projectile, unless a customization delta patches it |
| ProjectileWeapon +576 WeaponFunctionProjectileType | the projectile of a programmable-ammo weapon function |
| ProjectileWeapon +40 ProjectileEntity | when set, firing spawns an entity instead of a projectile |
| WeaponMagazine +4 Projectiles[32], +132 FirstProjectile | a magazine pattern that overrides rounds |
| WeaponRounds +64 / +68 | primary / alternate magazine projectile of rounds-fed weapons |
| WeaponCharge / WeaponHeat level ProjType (+4, +28, +52) | charge- or heat-level projectiles |
| customization entity deltas | 97 ammunition items patch one of the above: slot 6 patches +0 (67) or WeaponRounds +64 (15); slot 7, the alternate magazine's ammunition, patches WeaponRounds +68 (15) |

Fire modes do not select projectiles. Magazine, optic, muzzle and underbarrel options patch no projectile member.
Alternate ammunition does: the Liberator's runtime unlock list carries ten other ammunition items (Penetrator,
Explosive, ...), each patching +0 with its own projectile. The armory exposes no ammunition category in the option
catalog, so the default is what a Liberator is built with.

**Classification** of every projectile weapon (89) and every catalogued player attack field:

| Status | Meaning | Weapons | Of the 58 old hosts | Old writable attack fields (57) |
| --- | --- | ---: | ---: | ---: |
| `ACTIVE_DIRECT` | no customization patches a projectile member, no other selector: the member is fired | 51 | 43 | 37 |
| `INDIRECT` | a default ammunition delta patches the member at weapon build; the delta is the active source | 6 | 6 | 5 |
| `DORMANT_OR_METADATA` | the member is overridden and the overriding source is not uniquely identified | 0 | 0 | 0 |
| `AMBIGUOUS` | depends on state not proven offline (equippable ammunition, a weapon function, or rounds weapons where +0 and WeaponRounds both carry a projectile) | 3 | 3 | 9 |
| `BLOCKED` | another selector owns the projectile (spawned entity, charge or heat levels, magazine pattern, rounds) | 29 | 6 | 6 |

INDIRECT: AR-23 Liberator, JAR-5 Dominator, P-19 Redeemer, P-2 Peacemaker, R-63 Diligence, SG-225 Breaker (and the
SG-20 Halt's rounds member). The old host list's six BLOCKED weapons fire spawned entities (P-33, P-34, P-92, FAF-14,
MLS-4X, StA-X3); its three AMBIGUOUS are the MP-98 Knight (equippable ammunition) and the GR-8 and RL-77 (weapon
functions).

**Proof basis.** The decoded data path, checked against the two live controls. No native reader of the firing path
was traced. A retained-snapshot scan found only the shared entity-table copy of each weapon's ProjectileWeapon
record (no built weapon was resident), so whether a built weapon copies its component data or reads it through the
delta is not observed.

## The Liberator experiments

| Requested output | Result | Why |
| --- | --- | --- |
| **LAS Beam** (LAS-98) | **blocked** | A beam is fired only by a BeamWeaponComponent, which also owns the beam's fire mode and heat buildup. The Liberator has no such component and no heat, and nothing a projectile does can reference a beam. It would need the Liberator entity's component composition changed, which is not a reference write. |
| **Trident** (LAS-13) | **blocked** | The same family boundary. See below for how the Trident differs. |
| **EAT-700 Napalm** | **supported** | Same family. The Liberator's fired projectile (its default ammunition projectile) becomes the EAT-700 rocket, and everything the rocket does hangs off its own projectile row (details below). |
| **ARC-3 Arc** | **blocked** | The ARC-3's arc (ArcType 7) is emitted only by its ArcWeaponComponent. No explosion references it. |
| Arc on impact (native alternative) | **supported** | A projectile-family swap to the GL-52 De-Escalator grenade, written the same way. Its impact explosion releases a native arc (ExplosionInfo +120). |

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

**What the host keeps in the supported swaps.** Only its fired projectile changes (for the Liberator, the
ammunition delta's projectile). The Liberator keeps:
- its WeaponMagazine: 30 rounds and ammunition consumption;
- its WeaponReload;
- its rounds per minute (640) and trigger behaviour, which live in its own ProjectileWeapon component;
- its handling (WeaponData).

The output brings its projectile's flight, damage, explosions, submunitions, arcs and statuses. It does not bring
backblast, charge or heat.

## API

```lua
local liberator=hd2.weapon('AR-23 Liberator')
local source=liberator:attack('primary'):projectile_source()
-- {status='INDIRECT', mechanism='ammunition', writable=true, target=liberator:ammunition(),
--  field='ammunition.projectile', expect=liberator:ammunition():projectile(),
--  acknowledgements={'allow_shared','allow_unverified_effect'}, reason=...}

hd2.ensure({patch={id='liberator-napalm',target=source.target,field=hd2.fields.ammunition.projectile,
    expect=source.expect,value=hd2.attack_output('EAT-700 Expendable Napalm'),
    allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true}})

local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')   -- ACTIVE_DIRECT
hd2.ensure({patch={id='reprimand-talon',target=reprimand,field=hd2.fields.attack.projectile,
    expect=reprimand:projectile(),value=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()}})
```

**Guarantee.** When Runtime reports a projectile reference as writable for a host, changing it changes the projectile
that host fires, as far as the decoded data path and the live controls establish. Nothing is writable merely because
a projectile pointer exists.

- **`attack:projectile_source()`** (and `weapon:projectile_source(role)`) returns the status, mechanism, reason and,
  when writable, the target, field and expect handle. Use it instead of assuming `attack.projectile`.
- **Direct (`ACTIVE_DIRECT`).** `attack.projectile` on `weapon:attack(role)` is unchanged: 37 attacks, the Reprimand
  among them. A same-class swap needs no acknowledgement.
- **Ammunition (`INDIRECT`).** `weapon:ammunition()` is the default ammunition; `hd2.fields.ammunition.projectile`
  writes the projectile its delta patches into ProjectileWeapon +0. `ammunition:projectile()` is the expect handle,
  and the value that restores the reviewed ammunition projectile. It needs `allow_shared` (an ammunition definition
  applies to every weapon that equips it; observed equippers are published) and `allow_unverified_effect`.
  The ammunition delta is applied when the game builds the weapon, and whether an edited delta reaches the next
  build is not live-tested yet (the rebuilt `LiberatorAttackOutputTest` tests it). Each write re-proves the delta
  chain in the live, uniquely owned delta allocation and that the weapon's own default customization still names
  the ammunition item (`AMMUNITION_SOURCE_CHANGED` otherwise). Six weapons: AR-23 Liberator, JAR-5 Dominator,
  P-19 Redeemer, P-2 Peacemaker, R-63 Diligence, SG-225 Breaker.
- **Refused members.** `attack.projectile` on an INDIRECT attack fails with `DORMANT_PROJECTILE_REFERENCE` and names
  the ammunition target; AMBIGUOUS with `UNPROVEN_PROJECTILE_SOURCE`; BLOCKED with `PROJECTILE_SOURCE_BLOCKED`.
  20 of the 57 attack fields that were writable before are now read-only for this reason.
- **Projectile edits follow the active source.** Projectile and damage fields of an INDIRECT weapon resolve through
  its ammunition projectile, so after an ammunition swap they report `COMPOSITION_TARGET_CHANGED` exactly like a
  direct swap.
- **Cross-class projectile outputs** need `allow_unverified_reference` and `allow_unverified_effect`, on either
  mechanism.
- **Host eligibility.** 35 player weapons: 29 `component` hosts and 6 `ammunition` hosts, each keeping the live
  controls' structure (magazine-fed, empty magazine pattern, no WeaponRounds, WeaponCharge or WeaponHeat). Others
  fail with `CROSS_CLASS_HOST_REJECTED`, and the magazine structure is re-proven live before every write. The earlier
  58 counted any magazine-fed projectile pointer, including the Liberator and eight support weapons that have no
  guarded projectile reference target.
- **Beam, arc, spray and melee outputs** fail closed with `INCOMPATIBLE_OUTPUT_FAMILY` and the structural reason.
- **Donor outputs** are selectable only when their owner is established to fire that row (66 of 89). Owners that
  fire a spawned entity, charge or heat levels or a magazine pattern do not offer their +0 row as their output.
- **Source proof.** The output's owner entity, its ProjectileWeapon record identity and the ProjectileSettings row are
  re-proven live. A stale source is a CONFLICT.
- **Assets.** The owner's loadout package is loaded through the 0.27 asset loader before the reference is written.
  The donor weapon never needs to be equipped.
- **Mod Options.** A choice option's `values` may be reference handles, so one dropdown can select between complete
  output compositions. Each choice is a single reference value, so switching choices is one atomic write.

## Catalog and proof model

`sdk/AttackOutputCapabilities.json` lists 105 outputs: 89 projectile, 3 beam, 2 arc, 4 spray and 7 melee. 66
projectile outputs are selectable. It also publishes `projectileSources` (every player attack's status, mechanism
and reason), `ammunitionSources`, `activeSourceModel` (statuses, proof basis, counts, live controls) and `hostModel`
(component and ammunition hosts, with per-host live evidence). Each output records:
- family and kind: ballistic, explosive, explosive submunition, arc on impact, continuous beam, pulsed multi-beam,
  arc, spray or melee;
- owner, emitter component, structural class, and whether the owner is established to fire it;
- package and auto-load support;
- compatible host families, required coordinated references (none, for projectile outputs) and acknowledgements;
- live proof (donor side);
- for blocked families, the reason.

No native identifier is published.

Five proof levels are kept separate:
1. **Identity:** the owner and settings row are re-proven live.
2. **Assets:** the package is loaded.
3. **Structural:** one ProjectileType reference; cross-family is blocked.
4. **Active source:** the written member is the one the host fires.
5. **Gameplay:** live-proven only by a user-run test. Live evidence records four facts per composition test: the
   donor output works, the reference write succeeded, the host reads the reference, the gameplay output changed.
   - Reprimand → Talon: pass on all four (`weapon_projectile_reference_direct`, live-proven).
   - Liberator → Talon: donor works, write succeeded, host does not read it, no change
     (`weapon_projectile_reference_dormant_member`, live-failed; the member is now read-only).
   - Liberator EAT-700 and GL-52 (first build): unproven, and superseded. They wrote the same dormant member.
   - Liberator ammunition source, rebuilt `LiberatorAttackOutputTest`: **pass** for EAT-700 Napalm and GL-52 Arc
     (impact). The donor packages loaded automatically, the Liberator fired the donor projectiles, and the GL-52
     impact released its arc (`weapon_ammunition_projectile_reference` and `attack_output_cross_class`, live-proven).
   - Reprimand → Talon passed again on the active-source build.

**What the passes promote, and what they do not.** Only the tested scope:
- the Liberator's own ammunition row (RIFLE 5,5x50mm. FULL METAL JACKET) no longer needs `allow_unverified_effect`;
  `allow_shared` stays;
- exactly the Liberator × EAT-700 and Liberator × GL-52 compositions need no cross-class acknowledgement
  (`provenCompositions` in the catalog);
- the EAT-700 and GL-52 outputs are live-proven as donors (`liveProof.donorOutput`).

The other five INDIRECT weapons use the same kind of mechanism but their own ammunition rows, which no test exercised,
so they keep `allow_unverified_effect`. Every other cross-class pair keeps both acknowledgements.

## Validation

`scripts/validate_attack_output_snapshot.py` runs on the retained snapshot. Byte round trips prove the guarded write
mechanics only; every scenario first asserts the host's active source:
- the Reprimand → Talon write (the live pass) lands on its ProjectileWeapon +0 and rolls back exactly;
- the Liberator's `attack.projectile` is refused as `DORMANT_PROJECTILE_REFERENCE`;
- the Liberator's ammunition Vanilla is an already-desired no-op; Talon, EAT-700 and GL-52 land in the ammunition
  delta data while the dormant +0 never moves, each declares its package, and each rolls back exactly;
- after a swap, the Liberator's projectile edits report `COMPOSITION_TARGET_CHANGED`; a plain patch meeting another
  output is a CONFLICT;
- family, acknowledgement (shared, reference, effect), `NO_AMMUNITION_SOURCE`, wrong expect handle,
  `AMMUNITION_SOURCE_CHANGED`, stale output source and host magazine pattern rejections.

The packaged runtime (`scripts/validate_packaged_runtime.py`) runs, from the built ZIP:
- `example-asset-test-reprimand-talon-projectile`: the Reprimand direct source;
- `projectile-active-sources`: the Reprimand is ACTIVE_DIRECT, the Liberator's dormant member is refused, and the
  same donor is written to its ammunition source after its package loads;
- `example-liberator-attack-output-test`: the Mod Options choice through Talon, EAT-700, GL-52 and back to Vanilla,
  checking each package request and the exact ammunition baseline.

## Live test

The test mod is `LiberatorAttackOutputTest`, a Mod Options choice with Vanilla, LAS-58 Talon (control), EAT-700 Napalm
and GL-52 Arc (impact), all written to the Liberator's ammunition source. EAT-700 and GL-52 passed live (2026-09-29).
The Talon control was not reported. See its README for how to read each outcome.
