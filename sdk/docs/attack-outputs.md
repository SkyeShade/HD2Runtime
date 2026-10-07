# Attack outputs

Can an ordinary magazine-fed ballistic weapon keep its own fire control and ammunition while its attack produces a
different kind of output? This page records what the native data allows, and the Runtime API built on it.
- Research: `scripts/research_attack_outputs.py` → `research/attack-outputs-F5FEE03DCFDB.json`,
  `scripts/research_active_projectile_sources.py` → `research/active-projectile-sources-F5FEE03DCFDB.json`, and
  `scripts/research_projectile_builder.py` → `research/projectile-builder-F5FEE03DCFDB.json` (the typed reference
  graph, spare rows, twins, slots, support hosts).
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
  The ammunition delta is applied when the game builds the weapon. The AR-23 Liberator's own ammunition row is
  live-proven (`weapon_ammunition_projectile_reference`: LiberatorAttackOutputTest, UnifiedProjectileSwapTest), so it
  needs only `allow_shared`. Whether an edit reaches an already-built Liberator, or only the next one built, was not
  reported. The other five weapons keep `allow_unverified_effect`. Each write re-proves the delta
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
- **Host eligibility.** 52 hosts: 46 `component` hosts (29 player, 8 support and 9 mounted weapons) and 6
  `ammunition` hosts. Loadout category never decides it: the native output family and the active source do. Each keeps the live controls' structure: magazine-fed, empty magazine pattern, no WeaponRounds,
  WeaponCharge or WeaponHeat. Others fail with `CROSS_CLASS_HOST_REJECTED`, and the magazine structure is re-proven
  live before every write.
- **Support hosts.** A support weapon is a host by the same rule, not a separate system. The eight are the APW-1,
  EAT-17, EAT-411, EAT-700, GL-21, M-105 Stalwart, MG-206 HMG and S-11 Speargun: magazine-fed, no customization delta
  patches a projectile member, and no other selector exists, so every shot is their own ProjectileWeapon +0.
  - **API.** `hd2.support_weapon(name):projectile_source()` and `:attack(role):projectile_source()` return the same
    shape as for a player weapon. The field is `hd2.fields.attack.projectile` on `support:attack(role)`, with
    `support:attack(role):projectile()` as the expect and the restore value.
  - **Acknowledgement.** Support host swaps need `allow_unverified_effect`, and cross-class donors also
    `allow_unverified_reference`, except exactly the two live-proven pairs: EAT-17 ← PLAS-1 Scorcher and
    M-105 Stalwart ← APW-1 (UnifiedProjectileSwapTest, `support_projectile_reference`).
  - **Read-only support weapons** carry their reason in `projectileSources` and `projectile_source()`:
    - another selector owns the projectile (WeaponRounds ammo types, a magazine pattern, a spawned entity, charge
      levels);
    - a weapon function switches it (GR-8, RL-77);
    - the weapon is not magazine-fed (GL-28, Quasar, Maxigun, Railgun: ACTIVE_DIRECT, but outside the rule the live
      controls established).
- **Mounted hosts.** Mounted weapons (vehicles, Exosuits, emplacements, Guard Dog drones) follow the same rule
  (research/active-projectile-sources, research/projectile-builder `mountedHosts`). The nine hosts:
  - EXO-45 Patriot minigun;
  - both EXO-49 Emancipator autocannons;
  - EXO-51 Lumberer cannon;
  - M-102 Gunner FRV gun and the Super Earth FRV gun;
  - M-103 Supply FRV gun;
  - GATER Oil Rig turret;
  - AX/AR-23 Guard Dog gun.

  Details:
  - **API.** `hd2.vehicle(name):weapon(mount):projectile_source()` (or `:attack(role):projectile_source()`) gives the
    target, `hd2.fields.attack.projectile` and the mount's own attack handle as the expect. Every write re-proves the
    mount chain (the vehicle's MountComponent slot still holds the weapon).
  - **Shared entities.** The Gunner FRV and the Super Earth FRV carry the *same* weapon entity (`sharedEntity`): a
    write there changes both and needs `allow_shared`.
  - **Read-only mounts** carry the reason:
    - the Patriot rocket pod and Maelstrom slots 3 / 4: a spawned entity;
    - the Maelstrom main gun and the Bastion MG: a magazine pattern;
    - the Maelstrom slot 2 and Bastion cannon: a weapon function;
    - the EXO-55 Breakthrough: WeaponRounds.
  - **Row sharing.** Mounted bullet rows are widely shared. The Patriot minigun row is fired by 10 entities, the
    Gatling and machine-gun sentries among them. A *reference* swap changes only the mount; a *slot* write on its row
    needs `allow_shared`.
  - **Acknowledgements.** Mounted swaps need `allow_unverified_effect`, and cross-class donors also
    `allow_unverified_reference`. The exception is exactly the three live-proven donors on the Patriot minigun:
    EAT-17, LAS-58 Talon and PLAS-1 Scorcher (VehicleProjectileBuilderTest, `vehicle_projectile_reference`).
  - **Live test.** examples/projects/VehicleProjectileBuilderTest (the Patriot).
- **One donor pool.** Any catalogued projectile output (`hd2.attack_output(name)`), whatever loadout slot, stratagem or
  mount owns it. On a support host, and for a support donor on a player host, another weapon's attack projectile
  handle (player, support or mounted) resolves to that weapon's catalogued output and is checked like it
  (`UNKNOWN_DONOR` if it has none).
  Liberator → EAT-700 / Talon (ammunition), support ← primary, primary ← support and support ← support all go through
  the one path; examples/projects/UnifiedProjectileSwapTest exercises each.
- **Beam, arc, spray and melee outputs** fail closed with `INCOMPATIBLE_OUTPUT_FAMILY` and the structural reason.
- **Donor outputs** are selectable only when their owner is established to fire that row (66 of 89 weapon
  outputs). Owners that fire a spawned entity, charge or heat levels or a magazine pattern do not offer their +0 row
  as their output.
- **Stratagem-owned donor.** One output is owned by a stratagem entity: the A/M-23 EMS Mortar Sentry shell, fired by
  the turret's own ProjectileWeapon +0, whose expiry explosion leaves an EMS (StaticField) field. It is catalogued for
  `function_ammo.projectile` only (`referenceScope`); any other reference field refuses it with `OUTPUT_SCOPE`. Its
  package is the turret's own loadout package (`stratagem_weapon/A/M-23 EMS Mortar Sentry` in the asset catalog).
  See [stun-field donors](weapon-feeds.md#stun-field-donors).
- **Mode label and icon.** Every selectable projectile output is also a write target for the label and HUD icon a
  weapon-function mode shows when it fires that projectile (`hd2.fields.presentation.mode_label`,
  `hd2.fields.presentation.mode_icon`; native strings and icons only). See
  [mode labels and icons](weapon-feeds.md#mode-labels-and-icons).
- **Source proof.** As a *donor*, an output's owner entity, its ProjectileWeapon record and the reviewed reference
  are re-proven live (a stale source is a CONFLICT). As a *target* of a slot or presentation write, the owner entity,
  its record identity and the ProjectileSettings row identity are re-proven. What the owner fires right now is not a
  condition: another operation may have given it a donor, and the Patriot minigun fired as EAT-17 keeps its own
  bullet row, which the sentries still fire.
- **Assets.** The owner's loadout package is loaded through the 0.27 asset loader before the reference is written.
  The donor weapon never needs to be equipped.
- **Mod Options.** A choice option's `values` may be reference handles, so one dropdown can select between complete
  output compositions. Each choice is a single reference value, so switching choices is one atomic write.

## More donors (0.30.0-dev; not live-tested)

32 more projectiles can be swapped into a weapon (`scripts/research_projectile_donors.py`,
`research/projectile-donors-F5FEE03DCFDB.json`). They are named projectile types from
`research/projectile-identities-F5FEE03DCFDB.json` that the catalogue did not have yet: Eagle payloads, orbital
shells, sentry and emplacement rounds, and some weapons' second projectiles.

```lua
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary')
hd2.ensure({patch={id='reprimand-500kg',target=reprimand,field=hd2.fields.attack.projectile,
    expect=reprimand:projectile(),value=hd2.attack_output('Eagle 500kg Bomb'),
    allow_unverified_reference=true,allow_unverified_effect=true}})
```

**What makes a projectile a donor:**
- **One owner.** One fixed member of one uniquely owned component record holds the type:
  - a stratagem's Eagle payload (`EagleComponentData` +24);
  - an orbital shell (`BombardmentComponentData` +64) or orbital projectile (`OrbitalAbilityComponentData` +532);
  - a stratagem entity's or a weapon's `ProjectileWeapon` +0 or +576 (a weapon's second projectile).
- **A live re-proof.** Like every donor, that member is re-read right before each write (`CONFLICT` if it changed),
  and the donor's `ProjectileSettings` row identity with it.
- **A loadable package.** A stratagem donor's package is its owner entity's own generated loadout package (for example
  `packages/generated/loadout/eagle_bomb`). It is loaded before the write. A weapon's donor uses its weapon's package.
- **The same class rule** as every swap (`research_attack_outputs.projectile_class`).

**What they need:** none has been live-tested, so every use needs `allow_unverified_reference` and
`allow_unverified_effect`, even within the same class. Without them, registration refuses: `this donor is not
live-tested yet and requires allow_unverified_reference=true`.

**What may differ in play:** a donor flies with its own row: speed, gravity, damage and explosions.
- Orbital shells and Eagle bombs are fast and heavy.
- The Railcannon round flies at 14,000 m/s.
- Guided rounds (the P-92's, the W.A.S.P.'s) do not inherit their weapon's lock-on.
- Only the projectile changes: the host keeps its own fire rate, magazine and sounds.

**Not donors here** (110 named types, each with its reason in the research):
- enemy weapons: their effects ship in faction packages;
- unnamed owners;
- array members (magazine round patterns; charge, heat and rounds levels): their element strides are not proven
  here;
- guided-missile components and objective shells;
- second shell types that a different, unnamed record holds.

| `hd2.attack_output(...)` | Projectile | From | Class |
|---|---|---|---|
| `GP-31 Grenade Pistol (projectile 263)` | 263 | fired projectile | explodes on impact and expiry |
| `P-33 Missile Pistol (projectile 127)` | 127 | second projectile (+576) | explodes on impact and expiry |
| `P-92 Warrant (projectile 319)` | 319 | second projectile (+576) | plain |
| `SMG-37 Defender (projectile 3)` | 3 | fired projectile | plain |
| `SMG-37 Defender (projectile 150)` | 150 | fired projectile | plain |
| `A/GM-17 Gas Mortar Sentry` or `A/GM-17 Gas Mortar Sentry (projectile 342)` | 342 | fired projectile | explodes on impact |
| `A/M-12 Mortar Sentry` or `A/M-12 Mortar Sentry (projectile 346)` | 346 | fired projectile | shrapnel |
| `A/MLS-4X Rocket Sentry` or `A/MLS-4X Rocket Sentry (projectile 320)` | 320 | fired projectile | explodes on impact |
| `E/MG-101 HMG Emplacement` or `E/MG-101 HMG Emplacement (projectile 83)` | 83 | fired projectile | plain |
| `Eagle 110mm Rocket Pods` or `Eagle 110mm Rocket Pods (projectile 82)` | 82 | Eagle payload | explodes on impact |
| `Eagle 500kg Bomb` or `Eagle 500kg Bomb (projectile 239)` | 239 | Eagle payload | explodes on impact and expiry |
| `Eagle Airstrike` or `Eagle Airstrike (projectile 170)` | 170 | Eagle payload | explodes on impact |
| `Eagle Cluster Bomb` or `Eagle Cluster Bomb (projectile 286)` | 286 | Eagle payload | explodes on impact |
| `Eagle Gas Airstrike` or `Eagle Gas Airstrike (projectile 188)` | 188 | Eagle payload | explodes on impact |
| `Eagle Napalm Airstrike` or `Eagle Napalm Airstrike (projectile 141)` | 141 | Eagle payload | explodes on impact |
| `Eagle Smoke Strike (projectile 16)` | 16 | fired projectile | explodes on impact |
| `Eagle Smoke Strike (projectile 130)` | 130 | Eagle payload | explodes on impact |
| `Orbital 120mm HE Barrage` or `Orbital 120mm HE Barrage (projectile 194)` | 194 | orbital shell | explodes on impact |
| `Orbital Airburst Strike` or `Orbital Airburst Strike (projectile 158)` | 158 | orbital shell | shrapnel |
| `Orbital EMS Strike` or `Orbital EMS Strike (projectile 74)` | 74 | orbital shell | explodes on impact |
| `Orbital Gas Strike` or `Orbital Gas Strike (projectile 197)` | 197 | orbital shell | explodes on impact |
| `Orbital Gatling Barrage` or `Orbital Gatling Barrage (projectile 77)` | 77 | orbital shell | explodes on impact |
| `Orbital Napalm Barrage` or `Orbital Napalm Barrage (projectile 234)` | 234 | orbital shell | explodes on impact |
| `Orbital Precision Strike` or `Orbital Precision Strike (projectile 100)` | 100 | orbital shell | explodes on impact |
| `Orbital Railcannon Strike` or `Orbital Railcannon Strike (projectile 277)` | 277 | orbital projectile | explodes on impact |
| `Orbital Smoke Strike` or `Orbital Smoke Strike (projectile 247)` | 247 | orbital shell | explodes on impact |
| `Orbital Walking Barrage` or `Orbital Walking Barrage (projectile 80)` | 80 | orbital shell | explodes on impact |
| `TD-220 Bastion MK XVI` or `TD-220 Bastion MK XVI (projectile 36)` | 36 | second projectile (+576) | explodes on impact |
| `AC-8 Autocannon (projectile 284)` | 284 | second projectile (+576) | shrapnel |
| `MG-43 Machine Gun (projectile 49)` | 49 | fired projectile | plain |
| `RL-77 Airburst Rocket Launcher (projectile 96)` | 96 | second projectile (+576) | shrapnel |
| `StA-X3 W.A.S.P. Launcher (projectile 330)` | 330 | second projectile (+576) | shrapnel |

Names: `<owner> (projectile <type>)` always works. The owner's name alone works for a stratagem with exactly one donor
here. Validation: `scripts/validate_packaged_runtime.py` scenario `projectile-donors` (three swaps from the archive,
each donor's package loaded first, and an unacknowledged donor refused) and `projectile-donors-all` (every donor on its
own host); `tests/test_projectile_donors.py`.

## Projectile builder: slots, spare twins and composition classes

A weapon's alternate mode is a native ProgrammableAmmo function projectile ([weapon feeds](weapon-feeds.md)). The
projectile builder (`weapon:programmable_ammo()`) makes one from existing native pieces. The research
(`research/projectile-builder-F5FEE03DCFDB.json`) settles which kind of composition the game supports:

| Class | Meaning | 0.28 status |
| --- | --- | --- |
| REFERENCE_COMPOSITION | re-point references between existing rows (the host's projectile, a row's direct hit or explosions) | supported |
| DERIVED_MUTATION | a distinct native row whose references are edited, so no other entity changes | spare twins only, as an **interim**: they borrow unreferenced vanilla rows |
| CUSTOM_ROW | a new ProjectileType row | not available in 0.28.0: one row per vanilla ProjectileType, read by type with no bound, and the type is what the network replicates; Runtime has no ids of its own yet |

The target for custom projectiles is a Runtime-owned registry, not borrowed rows. Custom projectiles would get their
own ids above the vanilla range, backed by Runtime-owned rows. That needs the native table extended or relocated and
is not researched for 0.28.0. Until then, a spare twin is the only distinct identity, and it is labelled
`interim` and `borrowedVanillaRow` in the catalog.

**Rows and references.** ProjectileSettings has 350 rows (272 bytes each, indexed by ProjectileType). A typed
reference graph covers component members (through nested structs), entity deltas and explosion submunitions
(ExplosionInfo +84). 62 rows are referenced by no typed member. They are not free: a new identity needs one, and
nothing proves what an unreferenced row would draw.

**Spare twins.** An unreferenced row that is byte-identical to a catalogued output's row except its key,
presentation and references has the same flight, model, trail and sound as its twin, and its twin's package covers
it. It is an independent identity: composing it changes no other entity. It is still a **borrowed vanilla row**, and
the unreferenced rows cap how many can exist. A game update may start referencing it. Build migration does not
re-derive "unreferenced", so a spare twin is offered only on the build it was researched on; any other build refuses
it (`SPARE_TWIN_UNVERIFIED_BUILD`) until `scripts/research_projectile_builder.py` is re-run there. This build has
one:
- `S-11 Speargun (spare twin)`: row 300, the Speargun spear with an explosive expiry (400 damage, radius 2.5 / 7 / 8)
  instead of the gas cloud.

Copying a different base into a spare row is not offered. Two things are unproven: whether the game resolves a row's
visual resources when it fires (rather than once at load), and whether code references spare types directly. A
composed spare twin is a local edit: another player without the mod sees the row's vanilla contents.

A spare twin is catalogued for `function_ammo.projectile` only (`referenceScope`). Before every write, of the twin
itself or of a mode firing it, its live row is re-proven byte-identical to its twin's outside the excluded members
(`SPARE_TWIN_CHANGED` otherwise). No catalogued HMG, primary or other support row has a spare twin, so a status on
those bullets is a shared edit (below).

**Slots.** Every selectable projectile output has three references a builder composes, each a value handle on the
donor output:

| Field | Member | Value handle | `none` |
| --- | --- | --- | --- |
| `hd2.fields.projectile.direct_damage` | +60 DamageInfoType: damage, penetration and statuses of a direct hit | `hd2.attack_output(donor):direct_damage()` | refused (a projectile always has a direct hit) |
| `hd2.fields.projectile.impact_explosion` | +144 ExplosionType: released when the projectile hits | `:impact_explosion()` | removes it |
| `hd2.fields.projectile.expiry_explosion` | +156 ExplosionType: released when the projectile expires | `:expiry_explosion()` | removes it |

- **Target and expect.** The target is the output whose row is written (`hd2.attack_output(name)`). The expect is
  that output's own slot handle, or `"none"` where it has none.
- **Donor proof.** The donor row is only read, and its reference is re-proven live (`CONFLICT` if it moved). A damage
  slot takes only a damage handle, an explosion slot only an explosion handle.
- **Packages.** The donor's package is a declared asset dependency; a donor without a catalogued package is refused
  (`ASSET_UNAVAILABLE`).
- **Sharing.** A slot write changes every entity that fires the row, its owner weapon included: `describe().slots`
  and the catalog `slots` publish the entities and typed references. A row with more than one needs `allow_shared`;
  the HMG bullet is 15 references across 6 entities.
- **Acknowledgement.** A slot write needs `allow_unverified_effect`, except the exact (row, slot, donor) tuples a live
  test proved (`slots.<slot>.liveProvenValues`; `projectile_slot_composition`, `donor_row_slot_composition`):
  - the AR-2 Coyote and EXO-45 Patriot minigun impact explosions;
  - the Coyote Pacifier direct hit;
  - the Speargun spare twin's EMS expiry;
  - the LAS-58 Talon row with the GL-21 grenade blast.

  `allow_shared` is never dropped by live proof.
- **Catalogued explosions (0.30.0-dev; not live-tested).** An explosion slot also takes any catalogued explosion with
  a known package, `hd2.explosion(name)` (docs/explosions.md: `hd2.explosions.list({payload = true})`), with
  `allow_unverified_reference` and `allow_unverified_effect`. Its package is loaded before the write (none for the
  mission effects package); its live ExplosionSettings row is re-proven, and the recursion rule below applies.
- **Recursion.** A composition must never make a projectile spawn itself. Before an explosion slot is written, the
  chain explosion → submunition projectile → its impact and expiry explosions is followed in the live tables, and a
  chain that reaches the written row is refused (`RECURSIVE_COMPOSITION`). Native submunition chains (the EAT-700
  shrapnel) pass.
- **Unproven members.** +148 and +152 (f32 values after the impact explosion) and +228 (a ProjectileStatusEffect
  enum) stay unknown and read-only. Nothing proves a delay, a chance or what the status member does.

**Host swaps and slot writes are separate operations.** They write different objects and do not compose
automatically:
- **Swap.** A host swap changes *which row* a host fires: its ProjectileWeapon +0, or its ammunition delta.
- **Slot write.** A slot write changes *a row's* direct hit or explosions, for every entity that fires that row. Its
  target is the row (`hd2.attack_output(name)`), never a host.

In practice:
- **The host's own row.** A slot write there reaches the host only while it fires that row. After a swap, the host
  fires the donor's row, with the donor's effects. The host's own row keeps the edit, and every other entity that
  fires it still shows it. VehicleProjectileBuilderTest showed exactly this: the Patriot minigun's impact effect
  worked with its own bullet and did not follow EAT-17, Talon or Scorcher.
- **The log.** Runtime logs a `note:` line when a slot or label write applies while the row's owner fires another row
  through its ProjectileWeapon +0.
- **Effects on a swapped projectile.** Edit the donor's row explicitly: target `hd2.attack_output(donor)`. That
  changes every entity firing the donor row: the donor weapon itself, and every host swapped onto it. Live-proven
  for exactly one tuple (`donor_row_slot_composition`): the Patriot minigun swapped to the LAS-58 Talon, and the
  GL-21 grenade blast written to the Talon row. The minigun's Talon bolts exploded.
- **What `allow_shared` counts.** It counts the row's native consumers (`slots.<slot>.sharedConsumers`). Hosts that
  other operations swapped onto the row are not counted.
- **One host alone.** An effect on one host's swapped projectile alone needs a row of its own: a spare twin, or the
  Runtime-owned projectile registry, which 0.28 does not have. Nothing re-targets a slot write when a host swap
  changes.

**Where each effect lives** (the live rows, `validation/projectile-builder-snapshot.json` `audit`). A lingering field
is a status volume the explosion leaves; a submunition is a projectile the explosion releases:

| Output | Direct hit | Impact explosion | Expiry explosion |
| --- | --- | --- | --- |
| S-11 Speargun | damage plus gas and gas confusion | none | gas cloud (Gas lingering field, 10 s, radius 5) |
| A/M-23 EMS Mortar Sentry shell | damage | explosion | EMS field (StaticField lingering field, Stun Medium, 7 s) |
| GL-21 Grenade Launcher | damage | explosion | explosion |
| EAT-700 Expendable Napalm | damage plus burning | explosion releasing shrapnel (fire) | none |
| R-36 Eruptor | damage | explosion releasing shrapnel | explosion releasing shrapnel |
| CB-9 Exploding Crossbow | damage | explosion | none |
| AR-2 Coyote | damage plus fire | none | none |

No row here has a delayed explosion member: a delay would be a timed expiry (a lifetime), and +148 / +152 stay
unproven.

**The builder API.** `builder:operations(spec)` returns ensure requests, one per backing object, because the
binding and the function projectile belong to the weapon while the slots and labels belong to projectile rows:
- `<id>-mode`: the binding and the function projectile;
- `<id>-slots`: the base's slots;
- `<id>-label` (`-n` per choice value): the base's mode label and icon;
- `<id>-primary-label`: the weapon's own mode.

`builder:presentation(spec)` returns only the label requests, for a separate option. `builder:bases()` lists every
output a mode can fire.

```lua
local spear=hd2.support_weapon('S-11 Speargun')
local builder=spear:programmable_ammo()
for _,request in ipairs(builder:operations({id='spear-stun',base=hd2.attack_output('S-11 Speargun (spare twin)'),
        expiry_explosion=hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion(),label='stun',
        allow_unverified_effect=true,allow_unverified_reference=true}))do
    hd2.ensure(request)
end
```

**The spec.**
- **`base`** is an output or a Mod Options choice of outputs. Slot overrides need a fixed base.
- **`label`** is a native mode label; with a choice base it is a map from output name to label.
- **`icon`** defaults to `auto`: the label's exact native icon, else the plain round. The empty placeholder is only
  written when restoring vanilla.
- **`enabled`** is a toggle, applied to every request.
- **`allow_unverified_effect`, `allow_unverified_reference` and `allow_shared`** are passed on to the requests
  exactly as the spec gives them. The builder never adds an acknowledgement, so a missing one is refused by the
  write, with its reason.

Examples: SpeargunProjectileBuilderTest (the spear with an EMS field), HMGSpecialAmmoTest (status bullets from donor
rows), UnifiedProjectileSwapTest.

## Catalog and proof model

`sdk/AttackOutputCapabilities.json` lists 130 outputs:
- 108 projectile, among them the stratagem-owned EMS Mortar shell, the Speargun spare twin and 17 mounted weapons;
- 4 beam, 3 arc, 8 spray and 7 melee.

80 projectile outputs are selectable. Each selectable projectile output publishes its `presentation` (mode label,
icon, whether the row is shared) and its `slots`. The catalog also publishes:
- `modePresentation`: the offered labels and icons;
- `projectileSources`: every player attack's, support weapon's and mounted weapon's status, mechanism and reason
  (`kind`, `sharedEntity`);
- `ammunitionSources`;
- `activeSourceModel`: statuses, proof basis, counts and live controls;
- `hostModel`: component and ammunition hosts, with per-host live evidence.

Each output records:
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

`scripts/validate_projectile_builder_snapshot.py` (`validation/projectile-builder-snapshot.json`) runs the
projectile builder and the unified pool on the retained snapshot.
- **Speargun builder.** Every request applies and rolls back in reverse. The spare twin changes only in its
  presentation and expiry explosion (342 → the EMS explosion), and the Speargun's own row only in its presentation.
- **Unified pool.** Support ← primary handle, support ← primary output (cross class), support ← support handle,
  primary ← support handle and the Liberator ammunition each land in the host's own fired member and roll back.
  Restoring a support host's own projectile is its baseline.
- **Refusals.**
  - stale donor and stale slot donor;
  - spare twin changed;
  - dormant source;
  - the four blocked families;
  - a shared row without `allow_shared`;
  - removing the direct hit;
  - a cross slot type;
  - a slot the donor lacks;
  - the wrong expect;
  - a missing package;
  - a spare twin on another game build;
  - direct and two-step recursion;
  - an unknown output, an unknown slot or an extra handle identity;
  - a non-host support weapon.

The packaged runtime (`scripts/validate_packaged_runtime.py`) runs, from the built ZIP:
- `example-asset-test-reprimand-talon-projectile`: the Reprimand direct source;
- `projectile-active-sources`: the Reprimand is ACTIVE_DIRECT, the Liberator's dormant member is refused, and the
  same donor is written to its ammunition source after its package loads;
- `example-liberator-attack-output-test`: the Mod Options choice through Talon, EAT-700, GL-52 and back to Vanilla,
  checking each package request and the exact ammunition baseline;
- `example-speargun-projectile-builder-test`, `example-hmgspecial-ammo-test` (including switching the choice) and
  `example-unified-projectile-swap-test`: each option's exact writes and package requests.

## Cross-family composition (research)

Can the Liberator keep its model, handling and trigger and fire a LAS-5 Scythe, LAS-98 Laser Cannon or LAS-13 Trident
beam? `scripts/research_output_composition.py` (`research/output-composition-F5FEE03DCFDB.json`,
`sdk/OutputCompositionCapabilities.json`) answers the next step after the reference swap, on the pinned entity table,
game.dll code and the retained snapshots. All three compositions are **blocked**, on every route:

| Route | Blocker |
| --- | --- |
| Reference swap | A ProjectileType reference cannot name a BeamType (`INCOMPATIBLE_OUTPUT_FAMILY`, above). |
| Clone or attach the beam component | An entity's components are a packed u16 list inside EntitySettingsHashmap. All 1909 lists are laid end to end with zero slack, so a 24th Liberator component overwrites the next entity's list. Each component table's index is a hash table (resource mod capacity, linear probing: 0x514C10, 0x4F5C10); a new membership also needs a hashed row and a record. No safe allocation or ownership mechanism exists for either. |
| ...and even then | The trigger dispatch (0x742550) reads the entity's output-family flags: a projectile weapon goes to its projectile trigger (0x612800), and only a weapon without one reaches the beam trigger (0x83F750). A Liberator with both components would still fire bullets. |
| Event: suppress the shot, fire a beam | Events are polled after the game fires (`player_fired` from the stats table at 10 Hz): nothing runs before the dispatch, so native output cannot be suppressed without a code hook. |
| A beam action (`hd2.beams.fire`) | A beam is not a request. 0x83F750(entity, firing) only sets the firing flag of that entity's own beam_weapon instance (0x70-byte records, +0x18); the per-frame update does the ray, damage, heat and audio. There is no BeamType, origin or direction argument and no beam queue like the explosion and projectile requests, and for an entity without a beam instance the call writes out of bounds. |

- **Heat.** 22 of 23 beam entities own WeaponHeat. The 40-K Meltagun is the native magazine-fed beam (BeamWeapon +
  WeaponCharge + WeaponMagazine + WeaponReload, no heat): a beam does not intrinsically need heat, but only as its
  own entity's composition.
- **Lifecycle.** A beam starts when its owner's trigger sets the instance flag and stops when it is cleared; the LAS-5
  and LAS-98 beam while held (BeamFireMode 4), the Trident fires its pulse per trigger (BeamFireMode 6). Networking of
  beam instances was not traced.
- **What does work across families:** an explosion can release an arc (the GL-52 composition above), and a weapon can
  gain a second, player-selectable projectile ([weapon feeds](weapon-feeds.md)).

## Live test

The test mod is `LiberatorAttackOutputTest`, a Mod Options choice with Vanilla, LAS-58 Talon (control), EAT-700 Napalm
and GL-52 Arc (impact), all written to the Liberator's ammunition source. EAT-700 and GL-52 passed live (2026-09-29).
The Talon control was not reported. See its README for how to read each outcome.
