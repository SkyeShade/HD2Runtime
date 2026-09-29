# Generated HD2Runtime API reference

Static evidence records prior confirmations, never current process ownership. Runtime reads set current_live_ownership_proven only after live resolution.

Canonical source: `schemas/sdk.json`. Unknown semantic ranges remain unknown. Storage limits are not gameplay ranges.

Writable means an enabled, reviewed transition for that resource; it does not mean arbitrary values are allowed.

## Operations

- `hd2.describe(...)`: Describe schema and prior evidence without reading memory.
- `hd2.read(...)`: Create a bounded read job; advance with job.step().
- `hd2.observe(...)`: Runtime-scheduled read observation; default 60 update seconds.
- `hd2.enumerate_primary_weapons(...)`: Enumerate structurally owned weapon resources through one bounded shared discovery pass.
- `hd2.map_primary_weapons(...)`: Schedule one read-only primary weapon enumeration after a startup delay.
- `hd2.capture_snapshot(...)`: Incrementally capture committed readable current-process regions to a build-bound HD2SNAP file.
- `hd2.snapshot_control(...)`: Armed capture (research tooling): wait for `py hd2.py snapshot arm` requests and capture on each one; never captures on its own.
- `hd2.format(...)`: Format a completed read result.
- `hd2.patch(...)`: Freshly resolve and apply one reviewed scalar or typed-reference change. Option handles require hd2.ensure.
- `hd2.transaction(...)`: Validate every change before writing; guarded rollback on failure.
- `hd2.plan(...)`: Coordinate ordered semantic operations across multiple related backing objects and phases.
- `hd2.ensure(...)`: Wrap exactly one patch, transaction, or composition plan. The first run is fully guarded; afterwards only the applied target bytes are re-checked, backing off from interval (default 60 s) to max_interval (default 600 s). Drift triggers the full guarded path again; conflicts are terminal. Each guarded run retries transient not-ready failures up to 6 attempts, 5 s apart. An option handle as a field value, or an enabled toggle, makes the ensure follow in-game options. It waits until the options are settled (status waiting_for_options). Without Mod Options Menu it runs with the options' declared defaults, or, when the options page was declared with fallback='disable', stays inactive (status unavailable); each applied change re-runs the full guarded validation and write for the same operation; disabling restores the reviewed baseline through the same guards.
- `hd2.metrics(...)`: Process-wide counters (scans, lookups, hashes, writes, verifications, scheduler ticks) and worst durations for performance audits.
- `hd2.options(...)`: Declare an in-game options page (a MODS tab category). CowboyBingus Mod Options Menu v1+ (needs Bingus Shared Loader v18+) is an optional enhancement of mods that use this: without it, or if it is incompatible or rejects an option, one warning is logged per page and every hd2.ensure bound to those options runs normally with the options' declared defaults (fallback='default', the default). Declare the page with fallback='disable' to keep those operations inactive for the session instead. Defaults are validated with the operation when it is declared. Mods that do not call hd2.options are unaffected.
- `hd2.require_assets(...)`: Make the game load the packages that one to 16 typed handles (hd2.pickup, hd2.weapon, hd2.support_weapon, hd2.throwable, hd2.vehicle, hd2.backpack, a mounted-weapon candidate, a projectile handle) need, through the same reference-counted package system the game uses for loadouts. Status waiting_for_assets until every package is resident, then complete (result.status RESIDENT), or rejected with code ASSET_UNAVAILABLE. Never blocks; times out after 90 s. Package identities come only from the generated catalog; mods never pass package IDs. patch, transaction, plan and ensure already do this automatically for reference swaps, so most mods never call it.
- `hd2.asset_dependency(...)`: Offline: whether a typed handle's package dependency is known and auto-loadable, and how it was derived. No IDs.

## HD2Weapon

- `:projectile()` → `HD2Projectile` (only where mapped).
- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Projectile

- `:damage()` → `HD2DamageProfile` (only where mapped).
- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2DamageProfile

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Vehicle

- `:health()` → `HD2HealthComponent` (only where mapped).
- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2HealthComponent

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Stratagem

- `:shield()` → `HD2Shield` (only where mapped).
- `:payload()` → `HD2Payload` (only where mapped).
- `:damage()` → `HD2DamageProfile` (only where mapped).
- `:orbital()` → `HD2OrbitalAbility` (only where mapped).
- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Shield

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Payload

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2Equipment

- `:recharge()` → `HD2RechargeComponent` (only where mapped).
- `:jumppack()` → `HD2JumppackComponent` (only where mapped).
- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2RechargeComponent

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2JumppackComponent

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## HD2OrbitalAbility

- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.

## APW-1 Anti-Materiel Rifle

0x89C5493E08CA4207 (`hd2.resources.amr`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.weapon.crosshair_type` | Weapon / integer | read | 3 | structural_candidate, schema_labelled, gameplay_proven, prior live confirmation | unknown | crosshair_type | ReticleAmr/research/gameplay-confirmation-0.1.0.json |

## Bastion

0x16474112801385B6 (`hd2.resources.bastion`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.health.default_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.main_health` | HealthComponent / integer | read | 8000 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/README.md |
| `hd2.fields.health.zones_0_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_1_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_10_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_11_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_12_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_13_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_14_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_15_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_16_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_17_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_18_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_19_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_2_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_20_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_21_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_22_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_23_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_24_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_25_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_26_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_27_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_28_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_29_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_3_affects_main_health` | HealthComponent / number | read | 1 | structural_candidate, gameplay_proven, prior live confirmation | {"known_values": [0, 1], "complete": false, "note": "Known tested flags; no broader numeric range established."} | none | BastionReArmored/src/lunchbox_proof/validate.lua |
| `hd2.fields.health.zones_3_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_30_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_31_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_32_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_33_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_34_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_35_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_36_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_37_armor` | HealthComponent / integer | read | 0 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_4_affects_main_health` | HealthComponent / number | read | 1 | structural_candidate, gameplay_proven, prior live confirmation | {"known_values": [0, 1], "complete": false, "note": "Known tested flags; no broader numeric range established."} | none | BastionReArmored/src/lunchbox_proof/validate.lua |
| `hd2.fields.health.zones_4_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_5_armor` | HealthComponent / integer | read | 4 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_6_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_7_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_8_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_9_armor` | HealthComponent / integer | read | 2 | structural_candidate, prior live confirmation | unknown | none | BastionReArmored/src/armor_proof/validate.lua |

## JAR-5 Dominator

0x80F1A156D9FA1E36 (`hd2.resources.jar5`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.damage.armor_penetration` | DamageProfile / integer | read / reviewed write | 3 | structural_candidate, schema_labelled, gameplay_proven, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |
| `hd2.fields.damage.armor_penetration_lanes_1` | DamageProfile / integer | read | 3 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |
| `hd2.fields.damage.armor_penetration_lanes_2` | DamageProfile / integer | read | 3 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |
| `hd2.fields.damage.armor_penetration_lanes_3` | DamageProfile / integer | read | 0 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |
| `hd2.fields.damage.durable_damage` | DamageProfile / integer | read | 90 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |
| `hd2.fields.projectile.projectile_type` | Projectile / integer | read | 177 | structural_candidate, schema_labelled, prior live confirmation | unknown | projectile_type | Jar-5_buff/docs/research.md |
| `hd2.fields.damage.standard_damage` | DamageProfile / integer | read | 275 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | Jar-5_buff/docs/research.md |

## Jump Pack

0x59C5CA839449B379 (`hd2.resources.jump_pack`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.jumppack.movement_scalar_04` | JumppackComponent / number | read | 20 | structural_candidate, prior live confirmation | unknown | none | JumpPackImprovements/research/movement.md |
| `hd2.fields.jumppack.movement_scalar_24` | JumppackComponent / number | read | 60 | structural_candidate, prior live confirmation | unknown | none | JumpPackImprovements/research/movement.md |
| `hd2.fields.recharge.recharge` | RechargeComponent / number | read | 15 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | JumpPackImprovements/research/current-build-port.md |
| `hd2.fields.jumppack.vertical_launch_velocity` | JumppackComponent / number | read | 40 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | JumpPackImprovements/README.md |

## Maelstrom

0xB0C9FAF4AF8903F9 (`hd2.resources.maelstrom`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.health.default_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.main_health` | HealthComponent / integer | read | 8000 | structural_candidate | unknown | none | BastionReArmored/README.md |
| `hd2.fields.health.zones_0_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_1_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_10_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_11_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_12_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_13_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_14_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_15_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_16_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_17_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_18_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_19_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_2_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_20_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_21_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_22_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_23_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_24_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_25_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_26_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_27_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_28_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_29_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_3_affects_main_health` | HealthComponent / number | read | 1 | structural_candidate | {"known_values": [0, 1], "complete": false, "note": "Known tested flags; no broader numeric range established."} | none | BastionReArmored/src/lunchbox_proof/validate.lua |
| `hd2.fields.health.zones_3_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_30_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_31_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_32_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_33_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_34_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_35_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_36_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_37_armor` | HealthComponent / integer | read | 0 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_4_affects_main_health` | HealthComponent / number | read | 1 | structural_candidate | {"known_values": [0, 1], "complete": false, "note": "Known tested flags; no broader numeric range established."} | none | BastionReArmored/src/lunchbox_proof/validate.lua |
| `hd2.fields.health.zones_4_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_5_armor` | HealthComponent / integer | read | 4 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_6_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_7_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_8_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |
| `hd2.fields.health.zones_9_armor` | HealthComponent / integer | read | 2 | structural_candidate | unknown | none | BastionReArmored/src/armor_proof/validate.lua |

## Orbital Laser

0xEC3575E7A93793BB (`hd2.resources.orbital_laser`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.damage.damage_type` | DamageProfile / integer | read | 513 | structural_candidate, schema_labelled, prior live confirmation | unknown | damage_type | StrongerOrbitalLaser/src/damage/validate.lua |
| `hd2.fields.damage.durable_damage` | DamageProfile / integer | read | 60 | structural_candidate, schema_labelled, gameplay_proven, prior live confirmation | unknown | none | StrongerOrbitalLaser/research/gameplay-proof-400.md |
| `hd2.fields.orbital.interval` | OrbitalAbility / number | read | 0.1 | structural_candidate, schema_labelled, prior live confirmation | unknown | none | StrongerOrbitalLaser/src/damage/validate.lua |
| `hd2.fields.damage.standard_damage` | DamageProfile / integer | read | 60 | structural_candidate, schema_labelled, gameplay_proven, prior live confirmation | unknown | none | StrongerOrbitalLaser/research/gameplay-proof-400.md |

## Shield Relay

0xED13DDC480EC6910 (`hd2.resources.shield_relay`)

| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hd2.fields.stratagem.cooldown` | Stratagem / number | read / reviewed write | 90 | structural_candidate, schema_labelled, gameplay_proven, prior live confirmation | unknown | none | ShieldRelayImprovements/research/cooldown-live-confirmation.json |
| `hd2.fields.shield.durability` | Shield / number | read / reviewed write | 4000 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | ShieldRelayImprovements/README.md |
| `hd2.fields.payload.lifetime` | Payload / number | read / reviewed write | 40 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | ShieldRelayImprovements/README.md |
| `hd2.fields.shield.radius` | Shield / number | read / reviewed write | 15 | structural_candidate, gameplay_proven, prior live confirmation | unknown | none | ShieldRelayImprovements/README.md |

## Known enum members

- `hd2.enums.projectile_type`: {"jar5": 177}; partial catalog, source: Jar-5_buff/docs/research.md
- `hd2.enums.damage_type`: {"jar5": 153, "orbital_laser": 513}; partial catalog, source: Existing checked projectile/OrbitalAbility linkage
- `hd2.enums.crosshair_type`: {"amr_original": 3}; partial catalog, source: ReticleAmr/research/gameplay-confirmation-0.1.0.json
- `hd2.enums.fire_mode`: {"full_auto": 1, "semi_auto": 2}; partial catalog, source: WeaponDataComponentData native mode vector; conventional projectile consumers only

## Reviewed write contracts

```json
{
  "patch": {
    "resource": "jar5",
    "field": "armor_penetration",
    "expect": 3,
    "value": 4,
    "logical_mapping": {
      "storage": "u32",
      "offsets": [
        12,
        16,
        20
      ],
      "preserved_offset": 24
    }
  },
  "transaction": {
    "resource": "shield_relay",
    "fields": {
      "radius": {
        "expect": 15,
        "value": 8
      },
      "durability": {
        "expect": 4000,
        "value": 40000
      },
      "lifetime": {
        "expect": 40,
        "value": 90
      },
      "cooldown": {
        "expect": 90,
        "value": 180
      }
    }
  }
}
```
