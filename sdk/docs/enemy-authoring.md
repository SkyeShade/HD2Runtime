# Enemy and structure authoring

Since the coverage pass, Runtime can author the health and damage zones of enemies and enemy structures
(fabricators, emplacements, nests, objective buildings).
- Research: `scripts/research_enemy_authoring.py` → `research/enemy-authoring-F5FEE03DCFDB.json`.
- Public catalog: `sdk/EnemyAuthoringCapabilities.json` (contract `hd2runtime.enemy.guarded_authoring.v1`).
- Coverage: 177 classes (138 enemies, 39 structures), 10,065 field instances (9,300 health and zone fields, 765
  attack fields), 8,746 of them writable.

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
| `entity.health` | main health (+0) | gameplay-proven (vehicles, Shield Relay) | none |
| `entity.armor` | default zone armor | gameplay-proven (vehicle zones) | none |
| `entity.constitution` | +24 (len 12) | member name length + wiki constitution | `allow_unverified_effect` |
| `entity.constitution_rate` | +28 (len 23) | member name length | `allow_unverified_effect` |
| `entity.durable_resistance` | default zone durable share | member name length + wiki "durable %" | `allow_unverified_effect` |
| `entity.explosive_damage_percentage` | default zone explosive share | member name length + wiki "explosion reduction" | `allow_unverified_effect` |
| `zone.health` | zone +232 | gameplay-proven (vehicle zones) | none |
| `zone.armor` | zone +216 | gameplay-proven (vehicle zones) | none |
| `zone.affects_main_health` | zone +248 | gameplay-proven (vehicle zones) | none |
| `zone.constitution` | zone +236 | member name length | `allow_unverified_effect` |
| `zone.durable_resistance` | zone +204 | member name length + wiki "durable %" | `allow_unverified_effect` |
| `zone.explosive_damage_percentage` | zone +324 | member name length + wiki "explosion reduction" | `allow_unverified_effect` |

- **Units.** The wiki's "explosion damage reduction 25%" is the native explosive share 0.75. "Durable 75%" is the
  durable share 0.75.
- **Sentinels are read-only.**
  - A zone health of −1 means the zone uses the main health pool.
  - An explosive share that is not set means explosions resolve through another zone.

  Neither is authored, because both change a zone's behaviour, not its tuning.
- **Always read-only.** `fatal`, downs-on-death and main-health-capped are published but never writable.
- **Spawned entities.** Writes change the class definition. Enemies already on the map keep their current health;
  enemies spawned after the write use the new values.

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
- it resolves all 7,981 writable fields as guarded no-ops;
- it round-trips Charger health and head armor, fabricator health and Warrior head health;
- it checks the conflict, range, acknowledgement, stale-expect and sentinel rejections.

## Migration

Enemy fields migrate like vehicle fields: component coordinates are re-identified per class.
- **Same build:** all 9,300 are EXACT.
- **Previous build (D8E23968D141):**
  - 9,215 MOVED (record or index row moved; layout unchanged), 84 EXACT and 1 BASELINE_CHANGED (the spore lung's
    main health, 5000 → 30000);
  - all 7,981 writable fields are recovered, with 0 unsafe stale writes.

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

62 classes own a MountComponent and 43 of them mount weapons. The weapons reach 94 DamageInfo rows. 85 of those rows
are published as attacks: 765 fields on 38 classes. Rows with no DamageInfo of their own, such as the Spewers'
bile spray, are skipped.

Attack ids:

| Id | Attack |
| --- | --- |
| `slot_<n>` | the projectile's direct hit |
| `slot_<n>_impact` / `slot_<n>_expiry` | its explosions |
| `slot_<n>_spray` | a spray weapon |

The fields are the nine DamageInfo members player weapons use: `hd2.fields.damage.player_standard_damage`,
`player_durable_damage`, `ap_direct`, `ap_slight`, `ap_large`, `ap_extreme`, `demolition`, `stagger` and `push_force`.

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
- **Status on enemy attacks, projectile speed and explosion radius.** These rows are reachable through the same chain.
  Enemy attacks publish only DamageInfo for now, so one target never mixes backing objects.
- **Movement, detection, aggression and AI timers.** No member has an independent proof. This follows the
  instruction not to expose speculative AI fields.
- **Constitution and durable behaviour.** The members are identified, but their effect on enemies has not been
  live-tested. They are writable only with `allow_unverified_effect`.
- **Wiki variant names** (Hunter, Warrior, Devastator, the Hulks, Trooper, Berserker, the tanks, the Harvester).
  Their anatomy is shared by several native classes, or no class matches exactly, so they stay native-named.

## Live tests (built only; not yet gameplay-confirmed)

- `EnemyHealthTest`: Charger main health 2400 → 240.
- `EnemyArmorZoneTest`: Charger head armor 4 → 1.
- `StructureHealthTest`: the base Automaton fabricator class, main health 1500 → 150.
- `EnemyAttackDamageTest`: Spewer Bile Bombard, direct hit 500 → 50 and explosion 200 → 20 (shared by every Spewer).
