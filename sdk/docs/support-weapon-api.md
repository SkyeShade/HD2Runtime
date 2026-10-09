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
`hd2.support_weapon(name):backpack()` (see [Backpack ammunition](backpack-ammo.md)). Other
backpack-dependent weapons keep backpack storage read-only.

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
| `windup.wind_down_seconds` | `WeaponWindUpComponentData` +4 | Name length 14; no scraped value | M-1000 Maxigun. **Requires `allow_unverified_effect=true`.** |

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
