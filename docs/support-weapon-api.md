# Guarded support-weapon authoring

HD2Runtime 0.20 keeps the graph-aware 35-weapon inspection catalog and enables guarded
authoring for the 27 uniquely resolved runtime identities. The eight duplicate groups remain
visible through `describe()` and `attacks()`, but patch, transaction, and plan validation rejects
them before runtime discovery. No duplicate root is chosen by score or list order.

The normal semantic field constants are reused. A projectile target can edit `projectile.*` and
linked `damage.*` fields, while an explosion target can edit `explosion.*` and
`explosion.damage_*` fields. Definitions are shared runtime objects, so settings edits require
`allow_shared=true`.

```lua
local hd2=require('mods/skyeshade/hd2runtime')
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=gr8:attack('primary'):projectile()
local explosion=gr8:attack('primary_impact'):explosion()

return hd2.ensure({
    plan={
        id='recoilless-proof',
        operations={
            {id='physics',target=projectile,allow_shared=true,
                field=hd2.fields.projectile.velocity,expect=250,value=500},
            {id='blast-radius',target=explosion,allow_shared=true,
                field=hd2.fields.explosion.outer_radius,expect=3,value=12},
            {id='blast-damage',target=explosion,allow_shared=true,
                field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000},
        },
    },
})
```

`ARC-3 Arc Thrower` exposes `arc.*`, `damage.*`, `status.*`, and `charge.*`. Its native fire-rate
value is the `-1` charge-controlled sentinel, so `weapon.fire_rate` is intentionally absent.
`RS-422 Railgun` exposes the resolved primary projectile, its overcharge explosion and charge component (see
[Charge](#charge) and [Charge-level shots and explosions](#charge-level-shots-and-explosions)); the catalog's Max Charge
branch stays unresolved (it is the primary shot at the overcharge damage multiplier, not a row of its own). Spray and melee attacks expose their
owned DamageInfo fields, and resolved status branches expose strength and duration.

C4 resolves through `ExplosiveComponentData` to its detonation `ExplosionSettings`. Solo Silo
keeps the full stratagem payload -> `HellpodRackComponentData` -> missile entity chain. Every Solo
Silo write freshly verifies that chain, then resolves the independently owned detonation or impact
explosion. The handheld or delivery root is never treated as the damage owner.

Weapon-side magazine and rounds-feed fields are independent of backpack storage. The three
backpack-fed weapons (M-1000 Maxigun, B/FLAM-80 Cremator, GL-28 Belt-Fed Grenade Launcher) own no
magazine at all: their ammunition is the backpack's `DepositComponent`, authored through
`hd2.support_weapon(name):backpack()` (see [Backpack ammunition](backpack-ammo.md)). The five team-reload weapons
reload from their backpack's deposit once their own spares are spent; both are authorable (see
[Team-reload weapons](#team-reload-weapons-0304-offline-only)).

LAS-98 uses the 0.18 `WeaponHeatComponentData` layout in the retained snapshot, including heat
capacity, generation, cooling, and heatsinks. Its runtime roots are still unresolved (see below),
so both heat and beam writes remain blocked.

## Firing sound (`weapon.sound`, offline only)

The 21 support weapons with a ProjectileWeapon record that fire one catalogued sound take `hd2.fields.weapon.sound`
(a catalogue sound name; [weapon firing sounds](weapon-sounds.md#a-weapons-own-firing-sound-weaponsound-offline-only)).
It writes the delivered weapon type's record, so a weapon called in after the write fires with the new sound. The
MGX-42 Bullet Storm and SG-88 Break-Action Shotgun (fire mode 4/7) and the beam, arc, spray, melee and placed weapons
are blocked declarations, refused with their reason. Not live-tested.

```lua
hd2.patch({id = 'maxigun-gatling', target = hd2.support_weapon('M-1000 Maxigun'), field = hd2.fields.weapon.sound,
    expect = 'support/m1000', value = 'sentry/gatling', allow_unverified_effect = true})
```

## Charge

The four charge weapons (RS-422 Railgun, PLAS-45 Epoch, ARC-3 Arc Thrower, 40-K Meltagun) expose their own
`WeaponChargeComponent` record (one owner each). The native charge code reads it live every frame and on every
shot; no customization and no per-instance copy exists. **A write takes effect on the next frame, including a weapon
already in hand.** Research: `research/railgun-charge-F5FEE03DCFDB.json`,
[research/docs/railgun-charge-F5FEE03DCFDB.md](research/railgun-charge-F5FEE03DCFDB.md).

How charging works: while the trigger is held the charge grows by the frame time. Outside fire mode 6 it stops at the
full charge time (Railgun **Safe**); in fire mode 6 it keeps growing (Railgun **Unsafe**, the Epoch always). Releasing
at or above the minimum charge time fires; below it cancels. The shot's multipliers go linearly from their minimum
value (at the minimum charge time) to 1.0 (at the full charge time), then to their overcharge value (at the overcharge
time). The charge meter, sounds and reticle shake follow the charge; they never feed back into firing.

| Field | Meaning | Unit, range | Weapons |
| --- | --- | --- | --- |
| `charge.level_1` / `level_2` / `level_3` | minimum / full / overcharge charge time | seconds; 0..60 / 0.01..60 / 0.01..60 (keep minimum < full < overcharge: see below) | all four |
| `charge.speed_multiplier_min` / `_overcharge` | projectile launch speed multiplier | 0..10 | projectile weapons (Railgun, Epoch) |
| `charge.damage_multiplier_min` / `_overcharge` | hit damage multiplier (projectiles) or arc damage multiplier | 0..10 | Railgun, Epoch, ARC-3 |
| `charge.penetration_multiplier_min` / `_overcharge` | armor-penetration multiplier: each of the four AP values, rounded | 0..10 | Railgun, Epoch, ARC-3 |
| `charge.arc_distance_multiplier_min` / `_overcharge` | arc distance multiplier | 0..10 | ARC-3 |
| `charge.auto_fire_at_full` | outside fire mode 6, fire as soon as the charge is full | boolean | Railgun, ARC-3, Meltagun (not the Epoch: always mode 6) |
| `charge.explode_at_overcharge` | in fire mode 6, reaching the overcharge time fires, destroys the weapon and spawns the overcharge explosion | boolean (hazard) | Railgun, Epoch |
| `charge.overcharge_limit_seconds` | in the overcharged state, the weapon is destroyed and explodes **without** firing once held this long | seconds, 0..60 (0 = off; hazard) | Railgun, Epoch |
| `charge.overcharge_explosion` | the explosion the overcharge failure spawns (which one; its radii and damage are `attack('overcharge_explosion')`, see [Charge-level shots and explosions](#charge-level-shots-and-explosions)) | name of a charge weapon whose explosion to use: `'RS-422 Railgun'` or `'PLAS-45 Epoch'` | Railgun, Epoch |
| `charge.burst_shots` | shots per charge (0 and 1 = one shot) | integer 0..10 | Railgun, Epoch, ARC-3 |
| `charge.burst_interval_seconds` | delay before each further shot of one charge (0 = no further shot) | seconds, 0..10 | Railgun, Epoch, ARC-3 |

A field is offered only on the weapons whose code path reads it: a beam (the Meltagun) reads no multiplier and refuses
to fire at all with a burst count, and only weapons that can be in fire mode 6 can overcharge. Every new field needs
`allow_unverified_effect` (the meanings are proven from the native code, not yet in game); an explosion of **another**
weapon also needs `allow_unverified_reference` and loads that weapon's package first. Explosions whose package is not
catalogued are refused (`UNKNOWN_EXPLOSION_PACKAGE`). The overcharge limit's charge state (+204, "overcharged" on every
record) stays read-only.

**Charge-time order.** The times are meant to stay minimum < full < overcharge, but these ids are older than that rule,
so a write that breaks it is **accepted**; its registration logs a one-time `CHARGE ORDER` notice (per operation) with
the resulting times and what the game will do. A time the operation does not write is taken at its reviewed value. In
game:

- **full <= minimum** (for example a "fast Railgun" lowering only `level_2` below the 0.45 s minimum): the meter shows
  full first; outside fire mode 6 (Railgun Safe) the charge stops at the full time, so a release never reaches the
  minimum and **fires nothing** unless `charge.auto_fire_at_full` is on; in fire mode 6 a release fires only from the
  minimum time. Lower `level_1` in the same transaction.
- **overcharge <= full**: in fire mode 6 the overcharge is reached at the overcharge time (with
  `charge.explode_at_overcharge` the weapon fires and is destroyed, even before a full charge) and the shot multipliers
  jump to their overcharge values.

Write related times together in one transaction to keep them ordered. The per-field ranges still apply.

```lua
local rail=hd2.support_weapon('RS-422 Railgun')
hd2.ensure({transaction={id='slow-rail',target=rail,changes={
    {field=hd2.fields.charge.level_2,expect=0.5,value=2},
    {field=hd2.fields.charge.level_3,expect=3,value=8}}}})
hd2.ensure({patch={id='no-boom',target=rail,allow_unverified_effect=true,
    field=hd2.fields.charge.explode_at_overcharge,expect=true,value=false}})
```

**Corrected ids.** `charge.level_1` / `level_2` / `level_3` were published as "Charge level" multipliers; they are the
three charge **times** in seconds (same offsets, same values). `charge.minimum_seconds` and `charge.maximum_seconds`
were published as times; they are the projectile **speed multipliers** at the minimum charge and at full overcharge
(+72 / +76). Both keep writing exactly the same bytes with exactly their old contract (no acknowledgement, no range),
but they are deprecated:

- on projectile weapons they are aliases of `charge.speed_multiplier_min` / `charge.speed_multiplier_overcharge`
  (`schemas/player_weapon_fields.json` `alias_rules`); a registration that uses them logs a one-time
  `DEPRECATED` notice naming the real meaning;
- on arc and beam weapons (ARC-3, Meltagun) nothing reads +72 / +76, so the canonical ids are not offered there. The
  legacy ids stay writable and also log a one-time `DORMANT` notice: the write has no effect.

Live test: `examples/projects/RailgunChargeTest`.

## Charge-level shots and explosions

A charge weapon's own charge record also decides **which projectile a release fires** and **which explosion the
overcharge failure spawns** (research: `research/charge-explosions-F5FEE03DCFDB.json`,
[research/docs/charge-explosions-F5FEE03DCFDB.md](research/charge-explosions-F5FEE03DCFDB.md)). When the trigger is
released, the native fire code picks the projectile of the charge level reached; the overcharge failure destroys the
weapon and spawns its explosion at the weapon. Each of those rows is its own attack role:

| Weapon | Role | What it is | Fired / spawned when | Vanilla |
| --- | --- | --- | --- | --- |
| PLAS-45 Epoch | `primary` | the **partial-charge** shot (projectile and its direct-hit damage) | released at or after 1 s and before 2.5 s | 250 m/s, 400 / 200 damage, AP 4 |
| PLAS-45 Epoch | `primary_impact` | its explosion, at impact and when the projectile expires | with that shot | 2.3 / 3 / 4 m, 500 damage |
| PLAS-45 Epoch | `full_charge` | the **full-charge** shot | released at 2.5 s or later, also past the overcharge time (2.6 s) | 250 m/s, 400 / 200 damage, AP 5 |
| PLAS-45 Epoch | `full_charge_impact` | its explosion, at impact and when the projectile expires | with that shot | 3 / 4 / 5 m, 800 damage |
| PLAS-45 Epoch | `overcharge_explosion` | the **overcharge** explosion | held overcharged for 3.25 s: the Epoch is destroyed **without firing** and the explosion spawns in the wielder's hands | 3 / 4 / 5 m, 800 damage |
| RS-422 Railgun | `overcharge_explosion` | the overcharge explosion | Unsafe mode, at the overcharge time (3 s): the shot leaves, then the Railgun is destroyed and the explosion spawns in the wielder's hands | 0.4 / 2 / 3 m, 300 damage |

The fields are the normal ones: `projectile.*` and `damage.*` on `support:attack(role):projectile()`, `explosion.*`
and `explosion.damage_*` on `support:attack(role):explosion()`. The catalog branches resolve on these roles too
(`attack('P3')` is `full_charge`, `attack('P3 IE')` is `full_charge_impact`, `attack('PLAS-45 EPOCH Overcharge E')` and
`attack('RS-422 RAILGUN Overcharge E')` are `overcharge_explosion`). Every Railgun shot is its own projectile
(`primary`); the catalog's "Railgun Max Charge" is that shot at `charge.damage_multiplier_overcharge`, not a row of its
own.

```lua
local epoch=hd2.support_weapon('PLAS-45 Epoch')
hd2.ensure({transaction={id='epoch-harmless-overcharge',target=epoch:attack('overcharge_explosion'):explosion(),
    allow_shared=true,allow_unverified_effect=true,changes={
    {field=hd2.fields.explosion.damage_standard_damage,expect=800,value=1},
    {field=hd2.fields.explosion.damage_durable_damage,expect=800,value=1}}}})
hd2.ensure({patch={id='epoch-slow-full-charge',target=epoch:attack('full_charge'):projectile(),
    allow_shared=true,allow_unverified_effect=true,field=hd2.fields.projectile.velocity,expect=250,value=60}})
```

- **Acknowledgements.** Every field of these roles needs `allow_shared=true` (settings rows are shared definitions)
  and `allow_unverified_effect=true`: which level fires which row, and what the failure spawns, are proven from the
  native code, not yet in game. A row only one charge level fires is `AMBIGUOUS` for the weapon, the same rule as the
  PLAS-101 Purifier's player-weapon rows.
- **The Epoch's partial-charge fields gained `allow_unverified_effect` in 0.30.0.** Until 0.28.x, `primary` and
  `primary_impact` were presented as "the Epoch's" projectile and explosion; they are only the partial-charge shot, so
  an edit never changed full-charge or overcharged shots. Their ids and instance keys are unchanged. A mod
  that declares an older SDK keeps writing them without the acknowledgement, as a logged legacy operation
  ([legacy SDK compatibility](legacy-sdk-compatibility.md)); a mod that declares 0.30.0 or later needs it.
- **Self-damage.** The overcharge explosion spawns at the weapon, in the wielder's hands: its damage hits the wielder.
  Lower its damage (and push force) before testing a bigger blast.
- **One damage row for two explosions.** The Epoch's full-charge explosion and its overcharge explosion name the same
  damage row: `explosion.damage_*` on `full_charge_impact` and on `overcharge_explosion` write the same bytes, so a write
  through one changes both (two operations on it conflict, as any two writes of the same bytes). Their radii are
  separate rows.
- **Who else changes.** Rows of the Epoch shots have no other consumer. The Epoch overcharge explosion is also named by
  the 40-K Meltagun's charge record, which never reaches its failure (always fire mode 1). The Railgun overcharge
  explosion is also named by the PLAS-39 Accelerator Rifle (always fire mode 2, never fails), and its damage row is also
  the overcharge explosion of the PLAS-101 Purifier, PLAS-15 Loyalist, ARC-3 Arc Thrower, an enemy Watcher weapon and
  three unidentified charge records (`chargeLevel.sharedConsumers` in the catalog). A charge weapon whose
  `charge.overcharge_explosion` a mod sets to `'PLAS-45 Epoch'` (or `'RS-422 Railgun'`) spawns that explosion too, so an
  edit of its contents reaches that weapon.
- **Swapped references refuse.** Each role resolves its row live through the weapon's own charge record (the level's
  projectile selector, or the overcharge explosion reference). If another operation changed it (for example
  `charge.overcharge_explosion` set to another weapon's explosion), the write is refused instead of editing a different
  row.
- **When it applies.** An explosion row and its damage row are read when the explosion happens: a write changes the
  next explosion, also one released by a projectile already in flight. A projectile row is copied into a shot when it
  is fired: a write changes the next shot.
- **Multiplayer.** A write changes this machine's copy of the shared row. The charge update and the failure run where
  the weapon is simulated (its owner); what other players see is not tested.

Each field instance in `sdk/SupportWeaponAuthoringCapabilities.json` carries `chargeLevel` (level, when it fires,
phases, read timing, shared consumers, self-damage, multiplayer) and `effect`. Live test:
`examples/projects/EpochExplosionsTest` (harmless overcharge explosions by default).

## CQC-20 Breaching Hammer blast (0.30.4, offline only)

The hammer has two damage rows. Its swing is the melee attack (`attack('primary')`: 300 / 150, AP 3). Its charged
hit's blast is an explosion (published "CQC-20 BREACHING HAMMER IE": 2200 / 2200, Anti-Tank II, radii 0.5 / 3 / 12 m,
demolition 30, stagger 50, push 40). The blast is neither a projectile's nor a placed charge's explosion: the hammer's
own `MeleeWeaponComponent` +160 ability slot names AbilityId 38, and the ability's code requests the explosion
(`research/explosion-identities-F5FEE03DCFDB.json`, `scripts/ability_explosion_fields.py`). No other entity names that
ability; the explosion row and its damage row have no other user.

```lua
local blast=hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()
hd2.ensure({transaction={id='hammer-blast',target=blast,allow_shared=true,allow_unverified_effect=true,changes={
    {field=hd2.fields.explosion.damage_standard_damage,expect=2200,value=3000},
    {field=hd2.fields.explosion.damage_durable_damage,expect=2200,value=3000},
    {field=hd2.fields.explosion.outer_radius,expect=3,value=5}}}})
```

- Fields: `explosion.inner_radius`, `outer_radius`, `shockwave_radius`, and `explosion.damage.*` (standard and durable
  damage, the four AP values, demolition, stagger, push, the status slots), the same set as every support explosion.
- Acknowledgements: `allow_unverified_effect` (not yet shown in game) and `allow_shared`, like every support settings
  row. It is the same row as `hd2.explosion('support_weapon/cqc20_breaching_hammer/ability')` ([explosions](explosions.md)),
  which needs only `allow_unverified_effect`; use one of the two.
- Every write re-proves that the hammer's melee record still names AbilityId 38 exactly once in its ability slots,
  and that the explosion row and its damage link are the reviewed rows. If another mod changed the ability, the write is
  refused with `ABILITY_CHANGED` and nothing is written.
- Multiplayer: a per-type row on each machine; the machine that simulates the blast (the host, for the damage it deals)
  reads its own copy.
- Live test: `proof/RebalanceFixesProof` ("Hammer: big blast", "Hammer: gentle blast").

## Wind-up (Maxigun, LAS-98, Quasar; 0.30.4)

`windup.wind_up_seconds` is the M-1000 Maxigun's spin-up (0.5 s; 0 = instant), `windup.wind_down_seconds` only a switch
(0 = the barrels stop at once; any positive value spins down over the wind-up time). The LAS-98 and the Quasar wind up
through their firing charge (`heat.firing_charge` / `heat.charge_gain_per_second`). The table of every weapon is in
[player weapons](player-weapon-authoring.md#which-field-reduces-a-weapons-wind-up).

## Projectile swaps (support hosts)

Eight support weapons are projectile hosts: APW-1, EAT-17, EAT-411, EAT-700, GL-21, M-105 Stalwart, MG-206 HMG and
S-11 Speargun. They pass the same rule as player component hosts: magazine-fed, and every shot is their own
ProjectileWeapon +0. `hd2.fields.attack.projectile` on `support:attack(role)` replaces what they fire. The donor is
any catalogued projectile output or another weapon's attack projectile handle, from any loadout slot. The support host
path is not live-proven yet, so it needs `allow_unverified_effect`; cross-class donors also need
`allow_unverified_reference`. `support:projectile_source()` gives the target, field and expect, or the reason a
support weapon is read-only. See [attack outputs](attack-outputs.md) (support hosts, one donor pool).

```lua
local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
local source=eat:projectile_source()
hd2.ensure({transaction={id='eat-scorcher',target=source.target,allow_unverified_effect=true,
    changes={{field=source.field,expect=source.expect,value=hd2.weapon('PLAS-1 Scorcher'):attack('primary'):projectile()}}}})
```

## Beam swaps (LAS-98, 40-K Meltagun; 0.30.4, offline only)

The LAS-98 Laser Cannon and the 40-K Meltagun write their own BeamWeapon +0 (no customization patches it): any
catalogued beam output, through `support:beam_source()` and `hd2.fields.attack.beam` on the weapon itself, with
`allow_unverified_reference` and `allow_unverified_effect`; `support:beam()` restores the weapon's own beam. The donor
owner's package is loaded first. See [attack outputs](attack-outputs.md) "Beam swaps".

```lua
local source=hd2.support_weapon('LAS-98 Laser Cannon'):beam_source()
hd2.ensure({patch={id='las98-melta',target=source.target,field=hd2.fields.attack.beam,expect=source.expect,
    value=hd2.attack_output('40-K Meltagun'),allow_unverified_reference=true,allow_unverified_effect=true}})
```

## Missiles: W.A.S.P., Spear, Commando (0.30.4, offline only)

Research: `research/docs/wasp-rocket-F5FEE03DCFDB.md` (`scripts/research_wasp_rocket.py`,
`research/wasp-rocket-F5FEE03DCFDB.json`; every claim pinned to game.dll instructions). A lead (filediver's
`SeekingMissileComponent`) named the members; each name is checked against the type library's hidden-name length.

**How they fire.** The StA-X3 W.A.S.P. Launcher, FAF-14 Spear and MLS-4X Commando do not fire a projectile. Their
ProjectileWeapon +40 (ProjectileEntity) names a **missile entity**, and every shot spawns one (0x6143CD, 0x615B15).
The missile is a unit with its own `SeekingMissileComponent`. It carries the shot's projectile row (the W.A.S.P.:
projectile 43) as a unit-driven projectile: the row supplies the hit damage and the impact explosion. The existing
"Explosion · Primary impact" fields are row 43's explosion. The row does **not** supply the flight: the projectile's
position is the missile's every step, so the row's velocity, drag and gravity do nothing. The flight is the missile's
own record.

The W.A.S.P.'s ProgrammableAmmo function (state 1) spawns a second missile instead (ProjectileWeapon +584), carrying
projectile 330 (+576), whose impact explosion releases seven projectile-43 submunitions.

**Fields** on `hd2.support_weapon(name)` (the weapon itself; the editor's "Missile" section). `missile.*` is the
missile the weapon fires by default. `function_missile.*` is the W.A.S.P.'s ProgrammableAmmo missile.

| Field | Meaning | W.A.S.P. | Spear | Commando | Range |
| --- | --- | ---: | ---: | ---: | --- |
| `missile.max_lifetime` | seconds before the missile ends | 30 | 30 | 30 | 0.1 to 600 |
| `missile.starting_speed` | speed when it spawns (m/s) | 10 | 10 | 30 | 0 to 1000 |
| `missile.minimum_speed` | target speed at launch (m/s) | 10 | 10 | 75 | 0 to 1000 |
| `missile.preferred_speed` | target speed it accelerates to (m/s) | 100 | 100 | 120 | 0 to 1000 |
| `missile.acceleration` | how fast the target speed grows (m/s²) | 200 | 200 | 200 | 0 to 10000 |
| `missile.max_angle_to_target` | angle (degrees) at and beyond which the turn rate is `turn_rate_at_max_angle` | 45 | 45 | 45 | 1 to 180 |
| `missile.turn_rate_at_max_angle` | turn rate when far off target | 15 | 10 | 2 | 0 to 1000 |
| `missile.turn_rate_aligned` | turn rate when on target (blended in between) | 18 | 13 | 12 | 0 to 1000 |
| `missile.guidance_delay` | seconds of flight before guidance switches on | 0.01 | - | - | 0.01 to 60 |

The function missile (`function_missile.*`) has the same values except preferred speed 80 and turn rates 30 / 35.

- **Acknowledgement:** `allow_unverified_effect` on every field. The code that reads each member is pinned; nothing
  has been shown in game yet.
- **What the code does:** target speed = `minimum_speed` + age x `acceleration`, capped at `preferred_speed`. The
  missile ends when its age reaches `max_lifetime`; 0 or less would mean no limit, so it is not offered.
- **Turn rates are named by the code.** The two lead names (`min_turn_speed`, `max_turn_speed`) have the same length,
  so the ids describe what the code does with +88 and +92.
- **`guidance_delay`** exists only where the native value is above 0. The Spear (-1) and the Commando (0, it is
  laser-guided) switch guidance on by other logic.
- **When it applies:** the record is read on every missile update, so a write changes missiles already in flight.
  `starting_speed` is read when a missile spawns: it changes the next missile.
- **Every write re-proves the link.** The weapon's ProjectileWeapon member must still name the reviewed missile, and
  the missile must still own exactly the reviewed record. If another mod changed what the weapon spawns, the write is
  refused (`SPAWNED_ENTITY_CHANGED`).
- **Shared?** No. Each missile record has one owner, and exactly one ProjectileWeapon member in the game names each
  missile (no entity delta or game.dll constant does). The writeScope is `weapon_local`.
- **Multiplayer:** a type record. Every machine moves its own copy of the missile from its own record, so a player
  without the same edit sees the vanilla flight. Damage and the explosion follow the carried projectile, whose impact
  the shooter decides.

```lua
-- Slow W.A.S.P. rockets: easy to see and follow.
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
hd2.ensure({transaction={id='wasp-slow',target=wasp,allow_unverified_effect=true,changes={
    {field=hd2.fields.missile.preferred_speed,expect=100,value=20},
    {field=hd2.fields.missile.minimum_speed,expect=10,value=5}}}})
```

**No projectile swap.** `support:projectile_source()` stays read-only, and its reason now says why:

- **Swapping the spawned entity** (+40 / +584) is not offered. The entity is spawned by resource on the shooter and
  replicated, so another missile needs its unit, effects and package resident on every machine. No package or
  replication proof exists.
- **Swapping the carried row** (ProjectileWeapon +0) is not offered. It would change only the hit row (damage, impact
  explosion), never the missile's flight or model. The row reaches the missile through the shooter's spawn info
  (0x61604F -> 0x6414E0), and how another machine's copy gets its type is not traced.

The P-33 Missile Pistol and P-92 Warrant have the same fields (see [player weapon authoring](player-weapon-authoring.md)).

**Not covered:**

- **Lock-on** (time, range): no member of the missile. The W.A.S.P. owns no lock-on component; not traced.
- **Other missile members** (`javelin_firing_mode`, targeting mode, the speed controller's factors,
  `target_update_interval`): read by the code, but their effect is not traced.
- **Other missiles.** The EXO-45 Patriot's missile has the same structure but is not offered on mounted weapons yet.
  The TD-110 Maelstrom's missile has its own explosive (not run by the projectile system). The P-34 Breacher spawns a
  thrown charge, not a missile.

Live test: `proof/WaspRocketProof`.

## Warm-up and cooldown after overheat

The wiki's **Warmup** and **Cooldown After Overheat** of the LAS-98 Laser Cannon and the LAS-99 Quasar Cannon are not
members of the weapon's records. Each follows from fields you can edit, and each weapon's `blockedFields` lists
`heat.warmup` and `heat.overheat_cooldown` with the fields to edit and this weapon's values:

| | Edit | LAS-98 | LAS-99 Quasar |
| --- | --- | --- | --- |
| Warm-up | `heat.firing_charge` / `heat.charge_gain_per_second` | 100 / 200 = 0.5 s | 100 / 33 = about 3 s |
| Cooldown after overheat | `heat.capacity` / `heat.cool_per_second` | 100 / 5 = 20 s | 100 / 6.66 = about 15 s |

- The warm-up fields are WeaponHeat +148 / +152 (0.30.4). They need `allow_unverified_effect` because their names are
  leads ([player weapon authoring](player-weapon-authoring.md) "Wind-up and Trident-like beam blasts"). The Quasar
  also has `heat.reset_charge_after_shot` true: it charges again before every shot.
- The cooldown is the time to cool from full heat. The Quasar's one shot adds 100 heat (`heat.heat_per_shot`), which
  fills its 100 capacity, so every shot overheats it. The game scales the rate by its cold and hot multipliers
  (`heat.cool_per_second_cold` / `_hot`, derived). No overheat-lockout duration member is proven.
  `heat.overheat_lock` is only the flag that locks a weapon at maximum heat. One lead is not exposed: WeaponHeat +140
  (FP32, unnamed) is 400 on every other player heat weapon and 6.66 on the Quasar, the same as its cooling rate. It may be
  the cooling rate while overheated. A live test of `heat.cool_per_second` on the Quasar decides it.

```lua
local quasar=hd2.support_weapon('LAS-99 Quasar Cannon')
hd2.ensure({transaction={id='quick-quasar',target=quasar,allow_unverified_effect=true,changes={
    {field=hd2.fields.heat.charge_gain_per_second,expect=33,value=66},          -- warm-up about 1.5 s
    {field=hd2.fields.heat.cool_per_second,expect=6.659999847412109,value=13.32}, -- cooldown about 7.5 s
}}})
```

If a heat write is refused with "the game reads its WeaponHeatComponentData table from another place", another mod
has moved the game's heat table ([diagnostics](diagnostics.md) "Component tables another mod moved").

## Team-reload weapons (0.30.4, offline only)

The GR-8 Recoilless Rifle, RL-77 Airburst Rocket Launcher, FAF-14 Spear, StA-X3 W.A.S.P. Launcher and AC-8 Autocannon
each come with a backpack that a teammate (or the wearer) reloads them from. The game code
(`research/team-reload-ammo-F5FEE03DCFDB.json`) decides a reload like this:

1. **The weapon's own spares first.** If the weapon itself holds spare magazines (or rounds), the wielder may reload,
   with or without a backpack, and the reload uses one of them.
2. **Then the worn backpack.** Only when the weapon's own spares are 0 does the game look at the backpack: it must be
   the weapon's own backpack and hold at least one reload. The reload then costs one from the backpack.
3. **A teammate's reload always uses a backpack**, never the weapon's own spares.
4. **Spawn and resupply.** The weapon spawns with `min(starting, maximum)` own spares and every resupply adds
   `max(1, from supply)` up to the maximum. The backpack refills separately.

Natively the maximum (`magazine.spare_magazines`) is 0 on all of them. That clamps the start and every resupply to 0,
which is why they keep no ammunition of their own: the native `magazine.magazines_from_supply` 6 is clamped away. So
the wielder cannot reload without a backpack or a teammate.

**Magazine weapons (GR-8, RL-77, FAF-14, StA-X3):** these rows are real fields now (they were flagged "no effect" in
0.30.2 and 0.30.3):

| Field | Meaning | Native | Range |
| --- | --- | --- | --- |
| `magazine.spare_magazines` | The most spare magazines the weapon itself carries | 0 | 0 to 31 |
| `magazine.starting_magazines` | Its own spares at spawn, clamped to the maximum | 0 | 0 to 31 |
| `magazine.magazines_from_supply` | Own spares gained per resupply (at least 1), up to the maximum | 6 | 0 to 31 |

- **Acknowledgement:** `allow_unverified_effect` (proven from game code, not yet shown in game). Mods that declare an
  older SDK keep writing them without it ([legacy SDK compatibility](legacy-sdk-compatibility.md)).
- **Raise the maximum and the start together.** A start alone has no effect (it is clamped to the maximum, 0).
- **31:** the live spare count is the network field `magazines_remaining` (5 bits); the game clamps it to 31.
- **Applies to weapons called in after the write** (the spawn reads the record); a resupply reads the maximum again.
- One magazine is one reload (1 rocket; the StA-X3 holds 7). The HUD readout of these own spares is not traced: the
  live test reports what it shows.

```lua
-- GR-8: three spare rockets of its own (reload alone, no backpack), and the backpack still holds its 5
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
hd2.ensure({transaction={id='gr8-own-spares',target=gr8,allow_unverified_effect=true,changes={
    {field=hd2.fields.magazine.spare_magazines,expect=0,value=3},
    {field=hd2.fields.magazine.starting_magazines,expect=0,value=3},
    {field=hd2.fields.magazine.magazines_from_supply,expect=6,value=3}}}})
```

**AC-8 Autocannon (rounds):** not offered. The game would use the AC-8's own rounds first too, but each reload
subtracts its 5-round reload amount from them with no lower bound, while a resupply adds at least 1 round. A count
that is not a multiple of 5 would drop below zero. `rounds.spare_rounds` therefore accepts only its native 0, and
`rounds.starting_rounds` and `rounds.rounds_from_supply` have no effect (clamped to it); their `noEffect.reason` says
so. Its backpack is authorable.

**The backpacks** (`hd2.support_weapon(name):backpack()`): capacity, starting amount (-1 = full, the native value) and
supply refill, see [Backpack ammunition](backpack-ammo.md#team-reload-backpacks-0304-offline-only).

**Multiplayer:** the weapon's and the backpack's records are type records, edited on every peer that runs the mod. The
live counts (the weapon's own spares and the backpack's amount) are per-instance network fields owned by one peer and
replicated, so every player sees the same counts. The spawn amounts come from the record of the peer that creates the
weapon or backpack.

In `sdk/SupportWeaponAuthoringCapabilities.json` each of these rows carries `teamReload` (`role`, `ownSpares`, range,
research) and the weapon's `ammoBackpack` has `relationship: "team_reload"`.

## 0.24 coverage

Evidence: `research/support-weapon-coverage-F5FEE03DCFDB.json`, produced by
`scripts/research_support_weapon_coverage.py`. The live snapshot proves every relied-on native
table is byte-identical to the pinned reference; scraped values are fingerprints only.

| Field | Native owner | Evidence | Writable where |
| --- | --- | --- | --- |
| `projectile.lifetime` | `ProjectileInfo` +52 | Type-library member name length 9 (`life_time`); 5/5 exact scraped matches, 0/5 at the competing +56 | Native lifetime is non-zero (LAS-99, PLAS-45, RL-77, RS-422, S-11). A 0 lifetime means "no explicit limit" and stays read-only. |
| `projectile.penetration_slowdown` | `ProjectileInfo` +64 | Name length 20; 27/27 exact matches, 1/27 at +56 | Every resolved projectile branch |
| `reload.duration` | `WeaponReloadComponentData` +56 | Name length 8 (`duration`); scraped reload times agree only approximately | Native duration is non-zero (14 weapons). **Requires `allow_unverified_effect=true`.** A 0 duration means the reload ability's default applies and stays read-only. |
| `windup.wind_up_seconds` | `WeaponWindUpComponentData` +0 | Name length 12; exact scraped match (Maxigun 0.5 s) | M-1000 Maxigun |
| `windup.wind_down_seconds` | `WeaponWindUpComponentData` +4 | Name length 14; no scraped value. A switch, not a time (0.30.4): 0 stops the barrels at once, any positive value spins down over the wind-up time | M-1000 Maxigun. **Requires `allow_unverified_effect=true`.** |

Projectile fields live on shared definitions and need `allow_shared=true`, like the other
`projectile.*` fields. Filediver labels +56 as `LifeTime`; the type library and the correlation
both contradict that for this build.

```lua
local mg43=hd2.support_weapon('MG-43 Machine Gun')
hd2.ensure({patch={id='mg43-reload',target=mg43,allow_unverified_effect=true,
    field=hd2.fields.reload.duration,expect=4.5,value=3}})
```

### Delivery-resolved identities

Duplicate groups used to be blocked as a whole. Each root in these groups owns separate component
records, so the only open question was which root the player receives. A group is now resolved
(`identityStatus` `DELIVERY_RESOLVED`) only when both are true:

1. The linked call-in StratagemDefinition's hellpod rack attaches exactly one candidate root.
2. An independent proof names that same root, and no other candidate:
   - `WIKI_MAGAZINE`: its native magazine tuple (capacity, starting, from supply, spare) alone matches
     the scraped values;
   - `LOADOUT_PACKAGE`: the call-in's own package is exactly that root's loadout package;
   - `SUPPORT_WEAPON_PATH`: it is the only candidate whose resource path lies under the carried
     support-weapon equipment tree. The path is a `hashes.txt` string whose resource hash equals the
     root, so it names the asset rather than guessing.

`identityResolution.basis` is `call_in_delivery_and_scraped_fingerprint` when the magazine proof applies,
otherwise `call_in_delivery_and_structural_identity`. `identityResolution.confirmations` lists every proof
that applies.

| Weapon | Result |
| --- | --- |
| MG-43 Machine Gun | Resolved. Delivered root 175/2/2/3 matches; the other root is 175/30/6/12. |
| M-105 Stalwart | Resolved. Delivered root 250/2/2/3 matches; three other roots are 150/0/0/0. |
| MG-206 Heavy Machine Gun | Resolved. Delivered root 100/1/2/2 matches; the FRV gun and another root differ. |
| CQC-20 Breaching Hammer | Resolved. Delivered root 1/7/7/7 matches; the other root has no magazine. |
| EAT-17 Expendable Anti-Tank | Resolved (`SUPPORT_WEAPON_PATH`). The delivered root is `equipment/support_weapons/lat_oneshot`; the other root has no resource path and no showcase, encyclopedia or customization component. Both roots have identical magazines, so the magazine proof cannot apply. |
| LAS-98 Laser Cannon | Resolved (`SUPPORT_WEAPON_PATH`). The delivered root is `equipment/support_weapons/laser_cannon`; the others are the hellpod laser turret and an unnamed emplacement weapon. The native reload (5.0 s) still disagrees with the scraped 3.65 s. That is a value question, not an identity one. |
| B/FLAM-80 Cremator | Resolved (`LOADOUT_PACKAGE`, `SUPPORT_WEAPON_PATH`). The delivered root is `equipment/support_weapons/heavy_flamethrower`. The other root is the Exosuit flamethrower mount (`vehicles/combat_walker_flamethrower`), whose package is empty. The scraped 500 capacity is the backpack fuel; the handheld has no magazine record. |
| CQC-72 Entrenchment Tool | Blocked. Its two native roots share one package and matching melee records; one is a `SupportWeapon` loadout item and the other a `SidearmWeapon` item. It has no call-in (state `no_call_in`). |

Resolved weapons reuse the Solo Silo chain check: every write re-proves live that the call-in
StratagemDefinition payload is the rack and that the rack attaches the delivered root. Fields
edit only the delivered weapon. Other native roots with the same catalog name (vehicle,
emplacement, or mission variants) keep their own records, although shared settings rows still
require `allow_shared`.

The GUI-facing `SupportWeaponAuthoringCapabilities.json` schema v2 reports every weapon, catalog
branch, writable fields by domain, shared scopes, blocked fields and exact reasons, backpack
dependency, and linked stratagem status. Its canonical `fieldInstances` collection contains one
entry for every internal authoring descriptor. Each entry includes the exact baseline, API field
constant, attack-qualified target, semantic backing-object key, complete reviewed consumer scope,
shared acknowledgement key, and transaction/plan grouping keys. `backingObjects` and
`operationGroups` provide deduplicated joins for building one transaction per accepted Runtime
backing scope and one plan across related objects.

The older `weapons[].writableFieldsByDomain` lookup remains available as a deduplicated
compatibility view. It must not be used to enumerate authoring instances because equal field names
on different attacks or backing objects intentionally remain separate in `fieldInstances`.

Semantic object and instance keys are stable opaque digests of reviewed identities. The artifact
contains no runtime addresses, offsets, record IDs, resource hashes, projectile IDs, or explosion
IDs. The older `SupportWeaponCapabilities.json` remains as the detailed inspection/evidence
artifact.

Snapshot validation resolves all promoted fields through production ownership chains and applies
their current values as guarded no-ops. The checked result must be `ALREADY_DESIRED`, with zero
writes, zero protection changes, stable rereads, and fixture fallback disabled.

## Support call-in linkage

Support weapons and their call-in stratagems remain separate authoring targets:
`hd2.support_weapon(...)` edits the delivered weapon, and `hd2.stratagem(...)` edits the call-in
definition. Since 0.22.1, both capability catalogs publish the reviewed relationship between them,
so tools can present one merged view without matching display names or using private tables.

Every support weapon has a stable `semanticId` (`support-weapon/v1/...`) and every stratagem has a
stable `semanticId` (`stratagem/v1/...`). These IDs are opaque digests of semantic identity and are
safe to persist. `weapons[].linkedStratagem` holds the forward link and support
`stratagems[].delivers` holds the reverse link. Both catalogs carry the same
`supportCallInLinks.relationships` collection. Use its `relationshipId`
(`support-callin/v1/...`) as the merge key.

Links are proven structurally. Either the call-in StratagemDefinition's primary payload is the
support weapon's own runtime root, or it is a hellpod rack that attaches one of the weapon's runtime
resources. The historical stratagem debug-name table is only a cross-check, and generation fails if
the two disagree. The generator also fails on any one-way link.

| State | Support weapons |
| --- | --- |
| `linked` | 33, including MS-11 Solo Silo (special: `deployable_silo`) and B/MD C4 Pack (special: `placed_item`) |
| `no_call_in` | SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool |
| `unresolved_call_in`, `unresolved_delivery` | none |

A second, independent native identity corroborates the payload graph. Each loadout item's
`LoadoutEntryComponent` carries an item id and a `LoadoutItemType`. For 29 of the 33 linked
support weapons the item id is the id of the call-in StratagemDefinition. The generator fails if
an item id ever names a different call-in than the structural link.

- **B/MD C4 Pack** (`placed_item`). The call-in rack attaches the detonator (the thrower) and the
  backpack; the backpack's deposit refills the detonator. The placed charge, which the catalog
  identifies as C4, is linked because both of these hold: its loadout item id is the C4 call-in
  id, and the call-in's package is its package. That package is owned only by the rack, the
  detonator, the backpack, and the charge. The `deliveryGraph` keeps them separate: call-in
  (cooldown) -> rack items `thrower` and `backpack` (native-only nodes, no authoring view) ->
  placed charge (the support-weapon view) -> `detonation` explosion.
- **SG-88 and CQC-72** (`no_call_in`). No StratagemDefinition carries their loadout item ids or
  names their packages. No rack, deposit, entity delta, or other entity record references them.
  `noCallIn` gives the reason, the root `loadoutItemTypes`, and a catalog-sourced
  `acquisition` of `world_pickup` with `nativeDeliveryProven=false`: only the absence of a call-in
  is native. On the stratagem side their `rootResolution` is `NO_CALL_IN`.

A relationship alone never lifts support-weapon write blocking. Every linked duplicate group
(MG-43, M-105, MG-206, CQC-20, EAT-17, LAS-98 and B/FLAM-80) is resolved only because an independent
proof also names the delivered root: scraped magazine values, the call-in's package, or a
hash-verified support-weapon resource path (see "Delivery-resolved identities"). No linked support
weapon remains ambiguous. CQC-72 is an unlinked duplicate and stays blocked.

Each relationship has a reference-only `deliveryGraph`. Its nodes name the owning view
(`stratagem` or `support_weapon`), the semantic ID, and the target path or attack role. An editor
uses these to select existing `fieldInstances`; no fields are copied. For Solo Silo the graph is
stratagem call-in (cooldown) -> deployable silo -> missile -> `detonation` and `impact`
explosions. Edits still persist through the original target types.

## Equipment coverage (research/equipment-coverage-F5FEE03DCFDB.json)

- **LAS-98 Laser Cannon `beam.fire_rate`** (`BeamWeaponComponentData` +104, rpm, 60): how often the beam applies its
  damage. It is the published "Beam Fire Rate" on seven weapons, including the two non-60 values (LAS-13 Trident
  300, 40-K Meltagun 50). Already authored before this pass: beam length and radius, damage and armor
  penetration, heat, cooling, heatsinks, reload, handling, stationary firing and the Fire status. The published
  cooling triple (7.5 - 5 - 3.8) is the cool rate times the native 1.5 / 0.75 multipliers
  (`heat.cool_per_second_cold` / `_hot`, derived and read-only). The published 0.5 s warmup is
  `heat.firing_charge / heat.charge_gain_per_second` = 100 / 200 (0.30.4; see "Warm-up and cooldown after overheat").
- **M-1000 Maxigun `weapon.recoil_multiplier_horizontal` / `weapon.recoil_multiplier_vertical`**
  (`WeaponDataComponentData` +60 / +64): the first pair of the typed `RecoilModifiers` struct. It is 1.0 on 364
  of 366 weapon records, and no attachment patches it.

Both need `allow_unverified_effect`.

Maxigun Reimagined was reviewed as a research lead, not a source. Every edit it makes was located independently:

- Already authored: its spread, sway, ergonomics, crosshair, mobile firing, wind-up, backpack, damage and status
  edits. Its "companion record" is the Maxigun's own WeaponData record, addressed 16 bytes in.
- Its selector and weapon-function binding are not reproduced: selectors are not authored on wind-up weapons, and
  its rate slots X/Z are dormant.
- Its projectile edit targets a ProjectileSettings row at 820 m/s. The Maxigun fires projectile 306 at 920 m/s,
  the published M-1000 P, so that edit would change another weapon's projectile.
- Its muzzle-effect and audio edits are ignored.
