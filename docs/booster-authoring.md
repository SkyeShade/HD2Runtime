# Booster authoring

Boosters are their own authoring domain: `hd2.booster(name)`. They are not stratagems, and they
have no component or settings type of their own. The catalog is
`sdk/BoosterAuthoringCapabilities.json`. The evidence is in
`research/booster-native-F5FEE03DCFDB.json` (`scripts/research_booster_native.py`) and
`research/booster-authoring-F5FEE03DCFDB.json` (`scripts/research_booster_authoring.py`).

## Native model

The on-disk `game.dll` is packed. The research reads the unpacked image from the retained
snapshot and traces every booster through the code that implements it.

- **One gate for every booster.** `IsBoosterActive(booster)` scans the mission's active-booster
  list and the players' loadouts. It has 38 direct call sites. 35 pass a literal booster value,
  and together they cover every booster except Armed Resupply Pods and Surplus EAT Allocation,
  which are data-driven. Of the other three, one reads the `StratagemInfo` booster list, one reads
  the susceptibility gate, and one is the UAV radar path.
- **A native Booster definition table.** `game.dll` holds a static table with one 0x38-byte row
  per enum value. The row's tuning scalar is at `+8` and a granted `StratagemType` is at `+4`.
  Game code reads the scalar right after the gate, for example
  `if IsBoosterActive(Vitality) damage = int(damage * table[Vitality].scalar)`. 25 instructions
  read the table and none write it. It is byte-identical across three snapshots from two game
  sessions.
- **Code-selected settings rows.** Some boosters pick an existing settings row by literal type.
  The hellpod-impact branch spawns explosion 83 (Firebomb), 335 (Stun Pods), or 400 (smoke).
  The stim applies status 29 instead of 25 (Experimental Infusion). Dead Sprint applies status 59,
  whose damage type is DamageInfo 541.
- **Data references.** The pinned type library references the `Booster` enum only from the
  `StratagemInfo` booster list (Armed Resupply Pods) and the `StatusEffectSusceptibility` gate
  (Integrated Extinguishers; the gated override is a particle effect and is cosmetic).

No executable code is ever written. Code bytes are only read, as proofs.

## Identity

All 20 boosters resolve to exactly one enum value. `game.dll` contains its own `Booster` enum-name
table, `[None, Vitality, …, FreeEAT, Count]`, indexed by value. Every one of its 22 names matches
the type library's hidden alias length for that value. This agrees with the UI template's
member-to-icon bindings for the 18 boosters it names. It also resolves the 11 former candidate
sets and the two boosters the UI template omits:

| Booster | Native member | Value | Corroboration |
| --- | --- | --- | --- |
| Integrated Extinguishers | `FireExtinguish` | 19 | The only value that gates status susceptibilities |
| Surplus EAT Allocation | `FreeEAT` | 20 | Its table row grants `StratagemType_LATOneshot_Booster` |

## Targets

Every booster field requires `allow_unverified_effect=true`: the native value and its consumer
are proven, but no changed value has been gameplay-tested. Fields on settings rows that game code
selects also require `allow_shared=true`, because the type-library carriers that remain undecoded
(`DestructionEffect` unions) and dynamically typed call sites cannot be fully excluded.

### `booster:tuning()`: the native definition table scalar

Each field is the booster's own row, so it is booster-local by construction. Every write
re-proves the following live:

- the `game.dll` fingerprint and `SizeOfImage`;
- the relocated enum-name pointers and the target's name string;
- every table row's identity bytes (scalars masked), plus the table-walker bound;
- the exact bytes of `IsBoosterActive` and of every gate and consumer instruction.

Values are range-checked because consumers divide by, subtract from, or truncate them.

| Booster | Field | Baseline | Consumer | Wiki fingerprint |
| --- | --- | --- | --- | --- |
| Vitality Enhancement | `booster.damage_taken_scale` | 0.9 | `int(damage * v)` | exact (90%) |
| Stamina Enhancement | `booster.stamina_scale` | 1.3 | Stamina efficiency (drain ÷ v) | not comparable |
| Muscle Enhancement | `booster.terrain_slowdown_scale` | 0.35 | `1 - slowdown * v` | none |
| UAV Recon Booster | `booster.radar_range_scale` | 1.5 | Radar scan scale | approximate (~50%) |
| Increased Reinforcement Budget | `booster.reinforcements_per_player` | 1 | `int(v + x)` per player | exact (+1) |
| Flexible Reinforcement Budget | `booster.reinforcement_cooldown_scale` | 0.75 | Refill cooldown × v | exact (2:00 → 1:30) |
| Localization Confusion | `booster.encounter_rate_scale` | 0.9 | Spawn rate × v, two timers ÷ v | approximate |
| Expert Extraction Pilot | `booster.extraction_time_scale` | 0.7 | Extract call-in × v | exact (30%) |
| Motivational Shocks | `booster.slow_scale` | 0.5 | Applied slow × v | differs (wiki ~25%) |
| Sample Scanner | `booster.double_sample_chance` | 0.15 | `random < v` | exact (15%) |
| Dead Sprint | `booster.health_floor` | 0.05 | Drain stops at this health fraction | exact (5%) |
| Sample Extricator | `booster.sample_drop_cap` | 10 | `count < int(v)` | exact (10) |
| Integrated Extinguishers | `booster.burn_decay_bonus` | 0.5 | Burn decay × 1/(1-v); range ≤ 0.95 | approximate |

```lua
local vitality=hd2.booster('Vitality Enhancement'):tuning()
hd2.ensure({patch={id='vitality',target=vitality,allow_unverified_effect=true,
    field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.75}})
```

Some values are read only at a specific moment. The reinforcement budget is set when it
initialises, and a granted stratagem's uses are copied when it is granted. An edit therefore
applies from the next such point.

### `booster:explosion()`: extra hellpod-impact explosion

The live write proves the pinned gate, the literal selector, and the row identities. The
`ExplosionSettings` row and its `DamageInfo` row are separate backing objects, so a change that
touches both needs `hd2.plan`.

| Booster | Explosion | Fields |
| --- | --- | --- |
| Firebomb Hellpods | type 83 (exact wiki fingerprint) | radii 2/4/4, 200/200 damage, AP 10, demolition 40, stagger 15, push 20, burn strength 20 |
| Stun Pods | type 335 (exact wiki fingerprint) | radii 2/4/4, 50/50 damage, AP 10, demolition 40, stagger 50, stun strength 100 |
| Concealed Insertion | type 400 (smoke, no damage) | radii 5/5 |

Zero-valued members (Stun Pods push, the smoke shockwave radius) stay read-only. The burn and stun
status definitions are shared by every fire and stun source, so only this explosion's own status
strength is exposed.

### `booster:status_effect()`: Experimental Infusion

This link is now structural: the stim applies status 29 instead of 25 while the booster is active.
The fields are `status.strength` 1.1, `status.duration` 10, and `status.incoming_damage_scale` 0.9.
All of them require `allow_shared`.

### `booster:status_damage()`: Dead Sprint drain

Status 59 is applied, queried, and removed only by Dead Sprint's four code sites. Its DamageInfo
541 exposes `damage.standard_damage` 5 and `damage.durable_damage` 5. The tick rate that turns this
into the published ~3.6 %/s is not established.

### `booster:granted_stratagem()`: Surplus EAT Allocation

The table row's `+4` names `LATOneshot_Booster`. At mission start the game looks that type up in
the `StratagemSettings` runtime table and grants it with the definition's use count. The field is
`stratagem.max_uses`, baseline 2, an exact match for the wiki's "two free uses".

### `booster:deployed_entity()`: Armed Resupply Pods

`weapon.fire_rate` 640 and `magazine.capacity` 140 on the turret its entity delta attaches. The
turret's projectile is shared with player weapons. Its payload lifetime is 0, meaning no limit.
Its turret, targeting and sensor members have hidden names. All three stay blocked.

## Still blocked

| Booster | Reason |
| --- | --- |
| Hellpod Space Optimization | Eight code paths select full capacity instead of the default fill; no scalar participates. Its table scalar (1.5) has no reader. |

Every booster also lists narrower blocked fields in the catalog: base values owned by other
systems, unnamed members, and table scalars with no reader.

## Validation

- `scripts/validate_booster_authoring_snapshot.py` runs every field on a copy-on-write overlay of
  the retained snapshot:
  - a guarded no-op, then a changed in-range write with read-back and guarded rollback;
  - rejection of a conflicting third-party value, missing acknowledgements, and out-of-range values;
  - per target, rejection of a changed instruction byte, a changed enum name, a changed row
    identity, a changed `IsBoosterActive`, a relocated `game.dll` base, and a wrong build.
  
  Table writes need no page-protection change, because `.data` is read-write.
- The packaged-runtime validator applies Booster scenarios from the built runtime ZIP with real
  overlay writes, then re-applies them after a simulated reset.
