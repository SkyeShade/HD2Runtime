# Enemy and structure authoring

Since the coverage pass, Runtime can author the health and damage zones of enemies and enemy structures
(fabricators, emplacements, nests, objective buildings).
- Research: `scripts/research_enemy_authoring.py` → `research/enemy-authoring-F5FEE03DCFDB.json`.
- Public catalog: `sdk/EnemyAuthoringCapabilities.json` (contract `hd2runtime.enemy.guarded_authoring.v1`).
- Coverage: 177 classes (138 enemies, 39 structures), 10,425 field instances (9,300 health and zone fields,
  1,125 attack fields), 9,106 of them writable.

How often each enemy type spawns (its weight in the game's spawn rosters) is set with
`hd2.enemies.spawn_weight`, not with a field: see [enemy spawn weights](enemy-spawns.md).

## Identity: native first

Each class is a native entity whose resource path is hash-verified. Its HealthComponent record is unique to it:
no two classes share a health record.

Wiki names are used only where the data proves them.
- **Named (21 classes).** The class carries a wiki name only when all of these hold:
  - its anatomy matches exactly one wiki page;
  - that page matches no other class;
  - the match is carried by at least two damage zones with identical health, armor, durable share and
    damage-to-main.

  Examples: Charger, Bile Titan, Hive Guard, Stalker, Impaler, Marauder, Gunship, Dropship, Watcher, Fleshmob,
  Crusher, Veracitor, Gatekeeper and the Gazer (a structure).
- **Native name, with wiki candidates.** Every other class is addressed by its native class name, and
  `wikiCandidates` lists each wiki page whose anatomy it matches exactly. A candidate is not identity. Typical cases:
  - variants that share one anatomy: `hunter_base` / `hunter_tier_1` / `hunter_tier_2` all match the Hunter page;
    six `lieutenant_*` classes match all four Hulk pages; ten `soldier*` classes match Devastator;
  - five fabricator classes that match both the Automaton Fabricator and Warp Gateway pages.

  `wikiCandidateEvidence` gives each candidate's strength:
  - `zonesMatched: 0` means only the main health and armor numbers agree, which can be coincidence;
  - `kindAgrees: false` means the wiki page is an enemy and the class is a structure path, or the reverse.

Enemy versus structure follows the native path: objectives, environment gameplay assets and emplacements are
structures.

## Native model

Every enemy uses the HealthComponent that vehicles and deployables use: a 22,096-byte record with a main block, a
default zone and 38 damage-zone slots (552 bytes each, from +520).

| Field | Member | Evidence | Acknowledgement |
| --- | --- | --- | --- |
| `entity.health` | main health (+0) | **live-proven on enemies** (EnemyHealthTest); gameplay-proven on vehicles | none (structures: `allow_unverified_effect`) |
| `entity.armor` | default zone armor | gameplay-proven (vehicle zones) | none |
| `entity.constitution` | +24 (len 12) | member name length + wiki constitution | `allow_unverified_effect` |
| `entity.constitution_rate` | +28 (len 23) | member name length | `allow_unverified_effect` |
| `entity.durable_resistance` | default zone durable share | member name length + wiki "durable %" | `allow_unverified_effect` |
| `entity.explosive_damage_percentage` | default zone explosive share | member name length + wiki "explosion reduction" | `allow_unverified_effect` |
| `zone.health` | zone +232 | gameplay-proven (vehicle zones) | none (structures: `allow_unverified_effect`) |
| `zone.armor` | zone +216 | **live-proven on enemies** (EnemyArmorZoneTest); gameplay-proven on vehicle zones | none |
| `zone.affects_main_health` | zone +248 | gameplay-proven (vehicle zones) | none |
| `zone.constitution` | zone +236 | member name length | `allow_unverified_effect` |
| `zone.durable_resistance` | zone +204 | member name length + wiki "durable %" | `allow_unverified_effect` |
| `zone.explosive_damage_percentage` | zone +324 | member name length + wiki "explosion reduction" | `allow_unverified_effect` |

- **Live evidence (2026-09-29, [live evidence](live-evidence.md)).**
  - Enemy main health: EnemyHealthTest turned Chargers fragile while Charger Behemoths stayed tanky.
  - Enemy zone armor: EnemyArmorZoneTest let light rounds hurt the Charger's head while other plates still deflected.

  Both are live-proven on enemy classes; the fields carry `liveEvidence`. Neither ever needed an acknowledgement,
  so none was removed.
- **Structure health.** Structure health (`entity.health` and `zone.health` on structures) is offline-proven only:
  the StructureHealthTest result was inconclusive (see Live tests). Structure health writes therefore now require
  `allow_unverified_effect`. Structure armor fields are unchanged.
- **Units.** The wiki's "explosion damage reduction 25%" is the native explosive share 0.75. "Durable 75%" is the
  durable share 0.75.
- **Sentinels are read-only.**
  - A zone health of −1 means the zone uses the main health pool.
  - An explosive share that is not set means explosions resolve through another zone.

  Neither is authored, because both change a zone's behaviour, not its tuning.
- **Always read-only.** `fatal`, downs-on-death and main-health-capped are published but never writable.
- **Spawned entities.** Writes change the class definition. Enemies already on the map keep their current health;
  enemies spawned after the write use the new values.
  The exception is `gore.whole_body_gib_damage`, which is read at hit time; see below.

## Whole-body gib threshold (`gore.whole_body_gib_damage`)

The damage at which a killed enemy bursts into gibs (the "splootch"). Research:
[enemy-gib-threshold](research/enemy-gib-threshold-F5FEE03DCFDB.md).

**Semantics.** The killing hit's final damage must reach this value for the enemy to burst. A hit that kills only the
damage zone it lands on is checked too.

- The final damage is the damage after armor, the zone damage multiplier, the durable mix, the element and relation
  multipliers, and the zone health cap.
- Electricity counts double.
- `-1` disables bursting.
- Units are damage points.

**Native member.** GoreGroupInfo +0 (f32, hidden name 10 characters) of the class's **first whole-body gore group**
(the first group with flag +866). It lives in the class's own GoreComponentData record, not in its HealthComponent. The
gore evaluator (0x9057D0) compares the hit with it at 0x905E39.

**Eligible classes.** 23 classes:

| Family | Vanilla value | Classes |
| --- | ---: | --- |
| Scavengers | 400 | 7 |
| Hunters | 500 | 5 |
| Warriors, including the Brood and Alpha classes | 750 | 10 |
| Hive Guard | -1 (disabled in vanilla) | 1 |

No other class gets the field:

- Spewers, Chargers, the Bile Titan, Stalkers, Shriekers and every Automaton or Illuminate unit have no whole-body gore
  group.
- The other disabled whole-body groups (`dragon`, `observer`, two tank turrets) are not offered, because their
  whole-body action never runs in vanilla.

**Value rule.** Accepted values are `-1`, or `0 < value <= 100000`. NaN, infinities, 0 and other negatives are refused.
The largest vanilla DamageInfo damage is 10,000, so even an Electricity (×2) critical (×1.5) hit stays below 100,000.

**Lifecycle (ACTIVE_DIRECT).** The value is read at hit time from the shared loaded GoreComponentData table. A write
therefore affects enemies of that class that are **already alive**, as well as later spawns. Each class owns its record,
so nothing is shared.

**Guards.** Each write re-proves:

- the class's GoreComponentData record index, index row and unique owner;
- that the target is group index × 872 + 0;
- the group's actor list (+340, `boss`);
- the group's flags (+864..+867, including +866 = 1);
- that every earlier group's +866 is clear;
- the expected current value.

A write therefore never lands on a limb group.

**Acknowledgement.** Writes need `allow_unverified_effect` until the live test passes (`examples/projects/GibThresholdTest`).

```lua
hd2.ensure({patch={id='warrior-burst',target=hd2.enemy('warrior_tier_2'),allow_unverified_effect=true,
    field=hd2.fields.gore.whole_body_gib_damage,expect=750,value=400}})
```

Not authored:

- Per-limb sever thresholds. Limb groups exist, but their identity is not cleanly provable per named group.
- The secondary "gored" threshold.
- The gib impulse scales.

## Zones

Each zone has an id (`zone_<index>`), a native name where the game stores a known one (`head`, `body_rear`,
`left_arm`, …) and a wiki label where the research can pin it.
- A wiki label is attached only when exactly as many native zones agree with the wiki zone as the wiki lists.
- When more agree, the label is withheld because which zone carries it is unknowable. This happens when zones have
  identical values or the wiki leaves values unstated. Examples: the Bile Titan's sacs, the Gazer's sphere and base,
  the Stalker's legs.
- In total, 224 of 289 matched zone pairings carry a label.
- Repeated wiki zones get ordinals ("Arms #1", "Arms #2"). The ordinal does not say which side is which.

## API

```lua
local charger=hd2.enemy('Charger')                  -- wiki name, or native class name ('charger')
local head=charger:zone('Head')                      -- zone id, native name, wiki label or index
hd2.ensure({plan={id='charger-tuning',operations={
    {id='body',target=charger,changes={{field=hd2.fields.entity.health,expect=2400,value=1200}}},
    {id='head',target=head,changes={{field=hd2.fields.zone.armor,expect=4,value=3}}},
}}})

local fabricator=hd2.structure('spawner_factory_conscript_base')
hd2.enemies({kind='structure',faction='automatons'})  -- reviewed names
charger:describe()                                    -- identity, zones and every field (value, range, editability)
```

- **Constructors.** `hd2.enemy` accepts enemies and structures. `hd2.structure` accepts structures only.
- **Ranges.** Health 1 to 10,000,000; armor 0 to 10; shares 0 to 10; constitution 0 to 10,000,000.

## Guards

Each write re-proves, against the live entity table:
- the class's resource and entity row;
- the HealthComponent record index, index row, owner count and uniqueness;
- the expected current bytes.

A third-party change to the same bytes is a CONFLICT.

The coverage-pass snapshot validator (`validation/coverage-pass-snapshot.json`) checks all of this against the
retained snapshot:
- it resolves all 9,129 writable fields as guarded no-ops;
- it round-trips Charger health and head armor, fabricator health and Warrior head health;
- it checks the conflict, range, acknowledgement, stale-expect and sentinel rejections.

The whole-body gib threshold has its own snapshot validator (`validation/enemy-gib-threshold-snapshot.json`). It covers
round trips that change exactly the four target bytes of the 7 MB GoreComponentData table, a 23-class transaction within
the read budget, and the guard tampers.

## Migration

Enemy health and zone fields migrate like vehicle fields: component coordinates are re-identified per class. Attack
fields migrate as settings rows re-walked from their weapon (see Attacks).
- **Same build:** all 10,425 are EXACT.
- **Previous build (D8E23968D141):**
  - 10,088 MOVED (record, index row or settings row moved; layout unchanged), 336 EXACT and 1 BASELINE_CHANGED
    (the spore lung's main health, 5000 → 30000);
  - all 9,106 writable fields are recovered, with 0 unsafe stale writes.
- **Whole-body gib fields** (added after that record; GoreComponentData is in the migration view since extractor
  version 6): all 23 are EXACT on the same build. Against D8E23968D141 all 23 are MOVED (record coordinates moved,
  layout unchanged), with 0 unsafe stale writes.

## Attacks (mounted weapons)

The research is `scripts/research_enemy_attacks.py` → `research/enemy-attacks-F5FEE03DCFDB.json`.

Enemies fire ranged weapons through mounts, like player vehicles. The chain is the one already proven for vehicle
mounts:
1. class MountComponent slot (24-byte MountInfo);
2. the mounted weapon entity;
3. its ProjectileWeapon (+0 projectile type) or SprayWeapon (+200 damage type);
4. ProjectileSettings (+60 DamageInfo; +144/+156 impact/expiry explosions);
5. ExplosionSettings (+4 DamageInfo);
6. the DamageInfo row.

62 classes own a MountComponent and 43 of them mount weapons. The weapons reach 94 DamageInfo rows. 169 attacks
are published on 38 classes, with 1,125 fields. Each attack is one settings row:
- 85 DamageInfo rows;
- 54 ProjectileSettings rows;
- 30 ExplosionSettings rows.

Rows with no DamageInfo of their own, such as the Spewers' bile spray, are skipped.

| Id | Row | Fields |
| --- | --- | --- |
| `slot_<n>` | the projectile's direct-hit DamageInfo | the nine DamageInfo members |
| `slot_<n>_impact` / `slot_<n>_expiry` | its explosions' DamageInfo | the nine DamageInfo members |
| `slot_<n>_spray` | a spray weapon's DamageInfo | the nine DamageInfo members |
| `slot_<n>_projectile` | the ProjectileSettings the weapon fires | `projectile.velocity`, `mass`, `drag`, `gravity`, `pellet_count` |
| `slot_<n>_impact_explosion` / `slot_<n>_expiry_explosion` | the ExplosionSettings | `explosion.inner_radius`, `outer_radius`, `shockwave_radius` |

The nine DamageInfo members are the ones player weapons use: `hd2.fields.damage.player_standard_damage`,
`player_durable_damage`, `ap_direct`, `ap_slight`, `ap_large`, `ap_extreme`, `demolition`, `stagger` and `push_force`.
The projectile and explosion members are the ones player, support and vehicle weapons use.

**Explosions are cross-checked separately.** The wiki states an explosion's standard damage and three radii for many
enemy attacks. An explosion carries `wikiExplosionOf` when those four values equal an explosion on the class's own
named or candidate page:
- 14 of the 30 explosion rows match this way, for example the Gunship's and Hulks' HEAT rockets
  (70 damage, 0.65 / 1.65 / 3.15 m), Bile Bombard (200, 1 / 8 / 14 m) and the Factory Strider cannon;
- 22 match some page;
- `lieutenant_ivory_legion`'s expiry explosion equals the Hulk Firebomber's WP rounds. This is recorded on the
  attack only; it does not name the class.

The wiki states no projectile velocity or mass for enemies, so projectile rows rest on the structural chain alone.
Vehicle mounted weapons publish the same members on the same basis.

```lua
local rockets=hd2.enemy('Gunship'):attack('HEAT Rocket Racks')   -- or :attack('slot_0')
hd2.ensure({patch={id='gunship-rockets',target=rockets,allow_shared=true,allow_unverified_effect=true,
    field=hd2.fields.damage.player_standard_damage,expect=30,value=10}})
```

**Naming.** An attack carries a wiki name (`wikiAttacks`) only when all nine published values of an attack on the
class's own named or candidate page equal the row: standard and durable damage, the four AP values, demolition,
stagger and push. 23 rows are named this way (12 distinct wiki attacks), for example:
- the Gunship's HEAT Rocket Racks and Heavy Fusion Cycler;
- the Gatekeeper's Plasma Starcannon volley and charge shots;
- Bile Bombard on the Spewers;
- the Factory Strider's Fusion Gatling Guns and Fusion Repeater Cannon;
- the Stingray's Plasma Destructor Gunpods;
- the Hulk Bruiser's Fusion Autocannon.

Near-misses stay unnamed. The Devastator page lists stagger 15 / push 10 for its Fusion Assault Cannon. The row
the `soldier` classes fire has 10 / 15, and so does the Factory Strider page for the same row, so the soldier
attack is not named.

`rowWikiMatches` lists every wiki ranged attack on any page with the same nine values: 49 attacks have one. It
describes the shared row, not the class. For example, `siege_engine`'s rows equal the Vox Engine's Plasma Duster
Miniguns and Plasma Macro-Culverin, but the class anatomy does not match the Vox Engine page.

**Sharing.** DamageInfo rows are global settings.
- `sharedWithClasses` lists the reviewed classes whose chains reach the row. Examples:
  - the Gunship's rockets are the same row as the Hulk artillery and rocket tank projectiles;
  - the Devastator rifle row reaches 12 classes.
- Other native users are possible, so every write needs `allow_shared`.
- The effect on enemy attacks is not live-confirmed, so every write also needs `allow_unverified_effect`.

**Guards.** Before every write Runtime re-reads the class's mount slot, the weapon entity's component record and
every settings link. The coverage validator checks this: repointing the Gunship's mount slot refuses the write
before any byte moves.

**Migration.** Each attack field is a settings row anchored on its weapon entity, and the engine re-walks the
weapon chain in the new build. Each attack's mount link is a relationship. A broken mount link blocks only that
attack, not the class's health fields.

## Not mapped (candidates only)

- **Melee, ability and beam attacks.** Chargers, Stalkers, Hunters, Warriors, the Bile Titan's vomit and slams, the
  Harvester's beam, and death explosions run through melee, ability and beam systems. They are not
  reached by a mount chain, so they are not mapped.
- **Status slots on enemy attacks.** The DamageInfo rows are reachable, but enemy attacks do not yet take status
  references.
- **Movement, detection, aggression and AI timers.** No member has an independent proof. This follows the
  instruction not to expose speculative AI fields.
- **Constitution and durable behaviour.** The members are identified, but their effect on enemies has not been
  live-tested. They are writable only with `allow_unverified_effect`.
- **Wiki variant names** (Hunter, Warrior, Devastator, the Hulks, Trooper, Berserker, the tanks, the Harvester).
  Their anatomy is shared by several native classes, or no class matches exactly, so they stay native-named.

## Live tests (2026-09-29)

| Mod | Result |
| --- | --- |
| `EnemyHealthTest` (Charger health 2400 → 240) | **passed**: live-proven enemy main health |
| `EnemyArmorZoneTest` (Charger head armor 4 → 1) | **passed**: live-proven enemy zone armor |
| `EnemyAttackDamageTest` (Spewer Bile Bombard 500 → 50, splash 200 → 20) | **not tested**: applied cleanly, but the artillery attack could not be provoked; attack fields stay offline-proven |
| `StructureHealthTest` (one fabricator variant 1500 → 150) | **inconclusive**: see below |

**Structure test.** The write applied cleanly, but the fabricators tested seemed to need about the usual number of
Railgun shots. Only one of the five fabricator variants was edited, and the variant cannot be identified in game, so
this is not a failure.

The offline data offers one explanation, not established. A fabricator has two health pools:
- main health: 1500 on the armor-5 housing;
- a fatal `insides` zone: 400 health, armor 4, forwarding 0% of its damage to main health.

A fabricator destroyed through the vent dies when the `insides` pool runs out. That needs the same shots whether or
not main health changed.

Stronger tests, built and ready to import:
- **`FabricatorHealthAllVariants`** edits all five fabricator classes at once. Shoot the armored housing, away from
  the vent.
- **`GazerHealthTest`** edits the Illuminate Gazer (main health 900 → 90). It is the one structure with a proven wiki
  name, and it is easy to recognise. Shoot its eye, which forwards all its damage to main health.

Structure health stays gated until one of them passes.
