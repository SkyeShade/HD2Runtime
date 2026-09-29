# Enemy and structure authoring

Since the coverage pass, Runtime can author the health and damage zones of enemies and enemy structures
(fabricators, emplacements, nests, objective buildings).
- Research: `scripts/research_enemy_authoring.py` → `research/enemy-authoring-F5FEE03DCFDB.json`.
- Public catalog: `sdk/EnemyAuthoringCapabilities.json` (contract `hd2runtime.enemy.guarded_authoring.v1`).
- Coverage: 177 classes (138 enemies, 39 structures), 9,300 field instances, 7,981 of them writable.

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

## Not mapped (candidates only)

- **Enemy attacks.** Most enemies own no ProjectileWeaponComponent: their attacks run through melee and ability
  systems that Runtime has not mapped. Mounted enemy weapons (gunships, Hulks, tanks) resolve through
  MountComponent. Their weapon identity per mount is not yet proven.
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
