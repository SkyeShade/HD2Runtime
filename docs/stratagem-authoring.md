# Guarded stratagem authoring

HD2Runtime 0.22 extends the 0.21 `hd2.stratagem(name)` graph with deployed entities
for 10 sentries, four conventional emplacements, and four mine deployment systems.
The 20 imported offensive stratagems and 33 uniquely correlated support-weapon
call-ins remain available. The canonical GUI contract is
`sdk/StratagemAuthoringCapabilities.json`. It publishes one descriptor per semantic
field instance and never exposes native addresses, offsets, record indices, or
native resource identifiers.

```lua
local precision = hd2.stratagem("Orbital Precision Strike")

hd2.patch({
    id = "precision_cooldown",
    target = precision,
    field = hd2.fields.stratagem.definition_cooldown,
    expect = 80,
    value = 40,
})
```

Defensive stratagems keep the stratagem definition, deployed entity, mounted
weapon, and attack settings as separate semantic targets:

```lua
local emplacement = hd2.stratagem("E/AT-12 Anti-Tank Emplacement")
local entity = emplacement:deployed_entity()
local cannon = entity:weapon("primary")
local projectile = cannon:attack("primary"):projectile()

return hd2.plan({
    id = "anti_tank_emplacement",
    operations = {
        { id = "health", target = entity,
          field = hd2.fields.entity.health, expect = 300, value = 600 },
        { id = "mass", target = projectile, allow_shared = true,
          field = hd2.fields.projectile.mass, expect = 6500, value = 7000 },
    },
})
```

`stratagem:attacks()` returns each reviewed native backing object in the delivery
graph. A field descriptor identifies its attack role, exact baseline, backing
object, target-specific operation group, reviewed shared consumer scope, and plan
group. A transaction may contain fields from one operation group. Use `hd2.plan`
to coordinate an entity, mounted weapon, ProjectileSettings, DamageInfo,
ExplosionSettings, explosion DamageInfo, status, beam, arc, and heat objects.

All 18 deployment entities expose guarded health and armor authoring. Twelve
mounted weapons expose the safely resolved subset of ammo, fire rate, heat,
projectile, damage, explosion, beam, arc, and status fields. These APIs reuse the
same field constants and settings primitives as player and support weapons.

Mine stratagems resolve the deployed mines' explosion. The chain is:
stratagem → mine deployer (`payloads[0]`) → its `MinefieldComponentData` +24, a 14-character
`ExplosionType` member → ExplosionSettings row → its DamageInfo → status rows.

- The deployer's `ThrowerComponentData` names the mine it launches.
- Where that mine has entity settings (contact, gas and incendiary mines), its own
  `ExplosiveComponentData` +36 names the same explosion row.
- The anti-tank mine unit has no entity settings of its own, so the deployer is the only native
  owner of its explosion.

`hd2.stratagem(name):mine()` is the explosion attack (`mine`). `attack('mine_damage')` and
`attack('mine_damage_status_N')` are its DamageInfo and status. These are global settings rows, so
writes require `allow_shared`. Every write re-proves live that the deployer's MinefieldComponent still
names the reviewed row.

| Stratagem | Explosion radii (inner / outer / shockwave) | Damage | Status |
| --- | --- | --- | --- |
| MD-6 Anti-Personnel Minefield | 1.2 / 5 / 7 | 700 / 700, AP 3 | — |
| MD-I4 Incendiary Mines | 1.2 / 4 / 7 | 300 / 300, AP 3 | fire, 3 s |
| MD-17 Anti-Tank Mines | 3 / 7 / 14 | 2000 / 2000, AP 5 | — |
| MD-8 Gas Mines | 2 / 6 / 6 | 3 / 3, AP 6 | two gas statuses, 6 s / 5 s |

### Mine count

`hd2.stratagem(name):deployed_entity():minefield()` exposes the deployer's salvo count (`minefield.salvos`) and mines
per salvo (`minefield.mines_per_salvo`). They are ThrowerComponent throw slot 0, +40 and +44. Three independent proofs
agree on all four minefields:
- **Wiki.** The deployment sentence ("Six salvos of eight mines are deployed, totaling up to forty-eight"; "six salvos
  of three" for the MD-17) and the structured Salvos/Capacity fields.
- **Type library.** Both are typed u32 members of the throw-slot struct (hidden name lengths 11 and 15), fingerprinted
  on every research run.
- **Structure.** The slot's 48-entry launch-socket array holds exactly salvos × mines-per-salvo distinct sockets:
  48 on the MD-6, MD-I4 and MD-8, and 18 on the MD-17. By contrast, the caltrops grenade, the only other thrower,
  throws every item from its root node.

Because there is one launch socket per mine, counts can only be reduced (range 1 to the vanilla value). More mines
than sockets would need nodes the model does not have.

**`minefield.salvos` is live-proven (2026-09-29).** `MinefieldSalvos` (MD-6, 6 → 2) made the launcher fire two
salvos and stop. It no longer needs `allow_unverified_effect`. `minefield.mines_per_salvo` was not tested and still
does.

**Deployment pattern.** In that test the mines landed in only one portion, about a quadrant, of the launcher's normal
360-degree pattern. They were not spread thinly around the whole circle. Successive salvos cover different rotational
sectors, so reducing the salvo count truncates the angular deployment sequence rather than evenly reducing mine
density across 360 degrees. `minefield.mines_per_salvo` may be what thins each sector instead, but that is untested:
it needs `allow_unverified_effect` and a live test.

Still read-only or unavailable:
- **Mine spacing, trigger radius and arming time.** The thrower's launch floats (e.g. 5/15, 7/17 and 7/15.5, likely
  a throw-distance band) and the Minefield floats (0.001/1.0, 0.2, 0.25/0.2) have no wiki value to prove them
  against. The wiki's only spacing statement ("flung 10-20 meters") matches none of them. They are published
  read-only in the research.
- **Trigger-to-detonation delay** (0.002 s). It is proven by layout on three mines, but the AT mine has no
  entity of its own.
- **Lifetime and chain reaction.** No owner was found.

Projectile lifetime and penetration slowdown on mounted weapons remain blocked: no shared schema-labelled native
field is proven. Sentry turret, targeting and weapon-handling fields are described in
[their own section](#sentry-turret-motion-targeting-and-weapon-handling).

Eagle definitions keep three separate concepts: ordinary stratagem cooldown,
per-stratagem uses before rearm, and the shared Eagle rearm definition. Editing
`eagle.rearm_time` requires `allow_shared = true` and affects all eight reviewed
Eagle offensive stratagems.

### Eagle attack fields

Since 0.30.0, each Eagle stratagem also exposes how its jet attacks. The fields live on the stratagem itself
(`hd2.stratagem(name)`), next to `eagle.uses_per_rearm`:

```lua
local airstrike = hd2.stratagem("Eagle Airstrike")

hd2.patch({
    id = "airstrike_pattern",
    target = airstrike,
    allow_unverified_effect = true,
    field = hd2.fields.eagle.airstrike_pattern,
    expect = 0,
    value = 2,  -- 8 bombs in a tight zigzag instead of 6
})
```

**What a write changes.** Each field is a member of the attack record of that Eagle's **own jet**.

- Runtime reaches the record through the stratagem's payload, and proves it again before every write: the jet, the
  record's owner, and the jet's attack kind.
- The record is **type data**. A write applies to every call of that Eagle on this machine, by any player, until it
  is restored. It is **not per call**.
- No other selectable Eagle reads the record, so the other Eagles are never affected.
- A field the strike reads live also changes a jet that is already in flight. A field read at dispatch applies from
  the next call.

| Field | Unit | Range | Editable on | Read |
| --- | --- | --- | --- | --- |
| `eagle.airstrike_pattern` | pattern | 0..7 (enumerated) | the six bomb Eagles | live, at every bomb release |
| `eagle.drop_interval` | seconds | 0.02..1.0 | the six bomb Eagles | live, at every bomb release |
| `eagle.fire_duration` | seconds | 0.1..6.0 | Strafing Run, 110mm Rocket Pods | live, during the attack |
| `eagle.attack_sweep_length` | meters | 0..200 | Strafing Run | live, during the strafe |
| `eagle.target_radius` | meters | 1..300 | Strafing Run, 110mm Rocket Pods | at dispatch |
| `eagle.attack_angle` | degrees | 0..360 | all eight | at dispatch |

What each field does:

- **`eagle.airstrike_pattern`** picks one of the eight native landing patterns. Each pattern is a bomb count plus the
  points the bombs land on, rotated to the attack heading. `eagleAirstrikePatterns` in the catalog lists them.

  | Pattern | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | Bombs | 6 | 6 | 8 | 8 | 4 | 5 | 1 | 3 |

  The vanilla patterns are: Airstrike 0, Cluster Bomb and Smoke Strike 3, Napalm 4, 500kg 6, Gas 7. Any other value
  is refused.
- **`eagle.drop_interval`** is the time between bomb releases. Each bomb is still aimed at its own landing point.
- **`eagle.fire_duration`** is how long the Strafing Run fires (1.5 s, which is 100 rounds), or the 110mm salvo
  window that is split between its targets.
- **`eagle.attack_sweep_length`** is how far the strafe's aim walks forward during the burst.
- **`eagle.target_radius`** is how far around the beacon the call looks for targets. It keeps the best 8.
- **`eagle.attack_angle`** is the approach heading relative to the throw direction: 90 flies across the throw, 180
  flies along it. If that heading is blocked, the jet takes the nearest clear heading.

**Fields that are read-only on an Eagle.** Every Eagle publishes all six fields with their native values. A field
that the Eagle's attack never reads is read-only on that Eagle, and its `reason` says why. For example, the Strafing
Run has no bomb pattern, and bomb Eagles skip the target search.

There are also three descriptive read-only fields:

- `eagle.payload`: the attack kind (`strafe`, `rocket` or `airstrike`).
- `eagle.bombs_per_strike`: the pattern's bomb count.
- `eagle.strafe_rounds_per_run`: 100 for the Strafing Run.

**Acknowledgements.** Every field needs `allow_unverified_effect = true` until a live test passes (EagleFieldsTest).
Three jets have other proven readers, so their fields also need `allow_shared = true`. Each descriptor lists those
readers in `sharedConsumers`:

- Strafing Run: an unused DSS strafing row and the DSS Eagle Storm.
- Napalm Airstrike: the DSS Eagle Storm.
- Gas Airstrike: the DSS Eagle Storm.

Values outside the range, non-finite numbers and non-integer patterns are refused. The research and the
justification for each range are in [Eagle components](research/eagle-components-F5FEE03DCFDB.md).

`stratagem.max_uses` edits the mission use count of every non-Eagle stratagem, including
unlimited <-> finite transitions; see [Stratagem mission uses](stratagem-uses.md). The orbital salvo and shell counts are the
bombardment record's own members (see [Orbital bombardment pattern](#orbital-bombardment-pattern)); its shell list is
never written.

`stratagem.calldown_code` sets the arrow code of every stratagem whose cooldown is writable (a list of 1 to 9 of
`'up'`, `'right'`, `'down'`, `'left'`); the mission HUD's stratagem list is redrawn to match. See
[Stratagem calldown codes](stratagem-calldown-code.md).

`stratagem.presentation.*` (`hd2.fields.stratagem.presentation_name`, `presentation_name_cased`,
`presentation_description`, `presentation_icon`) sets how a stratagem looks, using another stratagem's vanilla name,
description or icon, while it stays itself. See [Stratagem presentation](stratagem-presentation.md).
`presentation_icon` also takes a mod's own icon, `hd2.resources.image(id)`: see [Custom images](custom-images.md).

### Orbital bombardment pattern

`hd2.stratagem(name)` exposes the pattern of the ten orbitals that fire a barrage from a bombardment record: the
120mm, 380mm, Walking, Napalm and Gatling barrages, and the Airburst, EMS, Gas, Precision and Smoke strikes. Each field is
a member of the orbital's **own** `BombardmentComponentData` record (its payload[0]). In every snapshot each record has
one owner, and one stratagem row lists it, so no `allow_shared` is needed.

| Field | Unit | Range | Read |
| --- | --- | --- | --- |
| `orbital.salvos` | count | 1..16 | once, when the barrage is created |
| `orbital.shells_per_salvo` | count | 1..64 | once, when the barrage is created |
| `orbital.shell_interval` | seconds | 0..10 | for every shell |
| `orbital.shell_interval_random` | seconds | 0..10 | for every shell |
| `orbital.salvo_interval` | seconds | 0..30 | at every salvo |
| `orbital.salvo_interval_random` | seconds | 0..30 | at every salvo |
| `orbital.scatter` | record units | 0..100 | for every shell |
| `orbital.salvo_scatter` | record units | 0..100 | at every salvo |

Vanilla patterns (salvos x shells per salvo, delay between shells / salvos, scatter):

| Orbital | Pattern | Delays (s) | Scatter |
| --- | --- | --- | --- |
| 120mm HE Barrage | 5 x 3 | 0.75 / 2 | 27 |
| 380mm HE Barrage | 5 x 3 | 1.5 / 3 | 36 |
| Walking Barrage | 5 x 3 | 1.5 / 3 | 25 |
| Napalm Barrage | 5 x 5 | 0.5 / 2 | 25 |
| Gatling Barrage | 4 x 60 | 0.045 / 0 | 7 |
| Airburst Strike | 4 x 1 | 0 / 4 | 2 |
| Smoke Strike | 6 x 1 | 0 / 0 | 15 |
| EMS, Gas, Precision Strike | 1 x 1 | 0.35-0.5 / 1-3 | 1 |

- **The shells.** A call fires `salvos x shells_per_salvo` shells. Within a salvo they cycle through the record's listed
  shell types in order (`shellTypes`; the 120mm's are 194, 137, 137), starting again at every salvo. The game counts the
  listed types when the barrage starts and picks each shell modulo that count, so any count is safe: the shell list
  itself is never written, and Runtime proves it unchanged before every write. An EMS Strike set to 5 salvos of 3 fires
  15 EMS shells.
- **The delays.** A delay is its fixed part plus a random fraction of the random part (every vanilla random part is 0).
- **When it applies.** The two counts are copied when a barrage is created: they apply from the next call, never to a
  barrage already firing. The delays and the scatters are re-read for every shell, so they also change a barrage of
  that orbital in progress.
- **Scope.** A type-record write: every call of that orbital on this machine (by any player) uses it, until it is
  restored. It is not per call. With several players every machine fires its own shells from its own record, so every
  machine must run the same mod.
- **Runtime custom stratagems.** A custom orbital whose `pattern` is this orbital refuses to start while the record is
  not exactly vanilla. A native custom orbital (`orbital={native=true}`) whose donor is this orbital fires the edited
  pattern, because it is that orbital's own barrage.
- **Not mapped.** The aim walk (+0x10/+0x14) and the barrage drift (+0x60, the Walking Barrage's walk) have code-proven
  readers but no proven unit; they stay unpublished. The Orbital Laser and Railcannon have no bombardment record.

Every field needs `allow_unverified_effect = true` until a live test passes (OrbitalStrikeFieldsTest). Values outside the
range, non-finite numbers and non-integer counts are refused. Evidence: `research/bombardment-payload-F5FEE03DCFDB.json`
(readers pinned by `scripts/research_bombardment_payload.py`); write scenario: `validation/orbital-fields-snapshot.json`.

```lua
-- The Orbital EMS Strike as an EMS barrage: 5 salvos of 3 shells, 1.5 s apart, spread wide.
hd2.transaction({id='ems-barrage',target=hd2.stratagem('Orbital EMS Strike'),allow_unverified_effect=true,changes={
    {field=hd2.fields.orbital.salvos,expect=1,value=5},
    {field=hd2.fields.orbital.shells_per_salvo,expect=1,value=3},
    {field=hd2.fields.orbital.salvo_interval,expect=2,value=1.5},
    {field=hd2.fields.orbital.scatter,expect=1,value=20}}})
```

### Call-in time

`hd2.fields.stratagem.call_in_time` is the call-in countdown of every catalogued stratagem (94 rows): StratagemInfo
+0x54, in the same row as `stratagem.cooldown`. When a beacon is created, the game reads the carrier type's call-in,
applies the player's upgrades and any active mission effect, and never lets it drop below 0. The beacon then activates
that long after it lands. The vanilla values:

| Stratagems | Call-in |
| --- | --- |
| 380mm HE Barrage | 6 s |
| 120mm HE Barrage, Napalm Barrage; every backpack (Portable Hellbomb included) | 5 s |
| Walking Barrage; sentries, emplacements, minefields and support weapons | 3 s |
| The other orbitals; the EAT-17, EAT-700 and EAT-411 | 2 s |
| Orbital Railcannon Strike | 1 s |
| Resupply | 7.5 s |
| Eagles, vehicles and Exosuits, the A/MLS-4X Rocket Sentry, the FX-12 Shield Generator Relay | 0 s |

- **What it is not.** The delivery comes after it and is not part of it: a pod's fall, an orbital's travel and an
  aircraft's flight. An Eagle's call-in is 0 (its delay is the jet's flight), so a raised value delays the jet's
  dispatch. Ship upgrades shorten the countdown in game (the native 120mm 5 s showed 4 s live).
- **When it applies.** Read once per beacon: a write applies to beacons thrown after it; a beacon already thrown keeps
  its countdown.
- **Scope.** A type-record write: every beacon of that stratagem created on this machine. With several players the
  thrower's machine computes its own beacon's countdown (and replicates it), so every thrower needs the mod.
- **Range.** 0 to 60 seconds. The CQC-72 Entrenchment Tool and the SG-88 Break-Action Shotgun have no call-in stratagem.

The field needs `allow_unverified_effect = true` until a live test passes. It can share a transaction with the cooldown
(one StratagemInfo row). Evidence: `research/beacon-redirect-F5FEE03DCFDB.json` (timing).

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
| `linked` | 33, including MS-11 Solo Silo (`deployable_silo`) and B/MD C4 Pack (`placed_item`) |
| `no_call_in` | SG-88 Break-Action Shotgun, CQC-72 Entrenchment Tool (`rootResolution` `NO_CALL_IN`) |

B/MD C4 Pack links to the placed charge through native loadout identity. The charge's loadout
item id is the call-in id, and the call-in package is owned only by the rack, the detonator, the
backpack, and the charge. The rack-delivered detonator (`thrower`) and backpack are published as
companion deliveries. SG-88 and CQC-72 have no StratagemDefinition at all: no stratagem carries
their loadout item ids or packages, and nothing native delivers them. See
[support-weapon authoring](support-weapon-api.md).

Seven linked weapons have ambiguous runtime roots: MG-43, M-105, EAT-17, MG-206, LAS-98,
B/FLAM-80, and CQC-20. Their call-in links are known and their stratagem cooldowns stay writable.
The relationship never lifts support-weapon write blocking, so their weapon fields remain blocked.

Each relationship has a reference-only `deliveryGraph`. Its nodes name the owning view
(`stratagem` or `support_weapon`), the semantic ID, and the target path or attack role. An editor
uses these to select existing `fieldInstances`; no fields are copied. For Solo Silo the graph is
stratagem call-in (cooldown) -> deployable silo -> missile -> `detonation` and `impact`
explosions. Edits still persist through the original target types.

## Shield Generator Relay shield and damage zones

Since 0.23.0 the FX-12 Shield Generator Relay exposes its shield projector separately from the
physical base. Both are components of the same deployed entity. The spawned runtime shield instance
remains unresolved, so the shield is authored through its typed configuration.

| Target | Field | Constant | Baseline |
| --- | --- | --- | --- |
| `deployed_entity():shield()` | `shield.radius` | `hd2.fields.shield.entity_radius` | 15 |
| `deployed_entity():shield()` | `shield.durability` | `hd2.fields.shield.entity_durability` | 4000 |
| `deployed_entity()` | `payload.lifetime` | `hd2.fields.payload.entity_lifetime` | 40 |
| `deployed_entity()` | `entity.health` / `entity.armor` | `hd2.fields.entity.*` | 450 / 2 |
| `deployed_entity():damage_zone('body_front')` | `zone.health`, `zone.armor`, `zone.affects_main_health` | `hd2.fields.zone.*` | 450 / 2 / 1 |

The `entity_` prefix avoids a clash with the legacy `hd2.fields.shield.radius` constants, which still
drive the unchanged 0.4 `ShieldRelay` proof. ShieldRelayImprovements proved radius, shield health,
lifetime, cooldown, and physical health in gameplay. The recharge delay and rate members are not
promoted, because their labels come only from an external export.

Every deployed entity also exposes its populated damage zones through `damage_zones()` and
`damage_zone(id)`, using the shared `HealthComponent` zone schema described in
[vehicle authoring](vehicle-authoring.md).

## Sentry turret motion, targeting and weapon handling

A sentry's tunable members belong to its own deployed entity. Each sentry owns every one of these records alone, so no
write needs `allow_shared`. A write is a type-record write: it affects every deployment of that sentry on this machine
until it is restored. It is not per deployment.

**When a write takes effect.** Each descriptor publishes `readTiming`:

| `readTiming` | Fields | Effect of a write |
| --- | --- | --- |
| `spawn` | `turret.yaw_speed`, `turret.pitch_speed`, `targeting.range`, `targeting.side_range`, `targeting.rear_range`, `weapon.horizontal_spread`, `weapon.vertical_spread`, `weapon.recoil_*` | Copied into the sentry when it spawns: applies to sentries deployed **after** the write. A sentry already standing keeps its copy. |
| `live` | `turret.pitch_min/max`, `turret.yaw_min/max`, `turret.pitch_yaw_coupling`, `windup.wind_up_seconds`, `windup.wind_down_seconds` | Read every update: also changes sentries already deployed. |
| `unverified` | `beam.fire_rate` (Laser Sentry) | When the game reads it is not established: write it before calling the sentry in. |

The turn speeds are copied together with a per-sentry speed factor (1 by default; ship modules can raise it). The
targeting ranges are copied times a per-sentry sensor scale.

### Turret motion

Every turreted sentry (MG-43, G-16, AC-8, M-12, MLS-4X, M-23, LAS-98, FLAM-40, GM-17) exposes its turret through
`hd2.stratagem(name):deployed_entity():turret()`:

| Field | Native member | Range | Proof |
| --- | --- | --- | --- |
| `turret.yaw_speed` | TurretComponent +12 | 1–720 °/s | wiki "Horizontal Turn Speed" on all nine; live-proven |
| `turret.pitch_speed` | TurretComponent +8 | 1–720 °/s | wiki "Vertical Turn Speed" on all nine; live-proven |
| `turret.pitch_min` / `turret.pitch_max` | TurretComponent +20 / +24 | −90…90 ° | wiki "Vertical Limit" on all nine; native clamp read every frame |
| `turret.yaw_min` / `turret.yaw_max` | TurretComponent +28 / +32 | −180…180 ° | native clamp read every frame; no published table |
| `turret.pitch_yaw_coupling` | TurretComponent +16 | 0–10 | native read every frame; new in 0.30.0 |

- The values differ enough to prove the members: the Autocannon Sentry turns 20/20 with limits −60…70, the mortars
  55/55 with 35…89 and the Flame Sentry 140/140.
- **Yaw limits.** They are −180/180 on every sentry, which keeps the turret free to turn all the way round. A span
  narrower than 359.94° makes the turret clamp at the limits instead of wrapping.
- **`turret.pitch_yaw_coupling`.** Each frame the pitch step is multiplied by min(1, e^−value), where e is the yaw
  error in degrees left after the frame's yaw step:
  - 0 lets pitch and yaw move independently (most enemy turrets);
  - 1 is the direct-fire sentries;
  - 4 is the mortars, whose barrel barely elevates until the sentry faces its target.
- **Speed ramp.** The yaw also slows linearly inside the last 5° of error. That ramp is hard-coded.

### Targeting

`hd2.stratagem(name):deployed_entity():targeting()`:

| Field | Native member | Range | Sentries |
| --- | --- | --- | --- |
| `targeting.range` | SensorEyeComponent +0 | 1–500 m | all ten; live-proven |
| `targeting.side_range` | SensorEyeComponent +4 | 0–500 m, or −1 | the nine turreted sentries |
| `targeting.rear_range` | SensorEyeComponent +8 | 0–500 m, or −1 | the nine turreted sentries |

- **`targeting.range`** equals the targeting range the wiki states for seven sentries: MG-43 and G-16 75 m, AC-8 and
  MLS-4X 100 m, M-23 and GM-17 125 m, LAS-98 50 m.
- **Side and rear ranges.**
  - A sentry's sensor sits on its turret head. The range in a direction at angle a from where it points is
    |cos a| × (the range ahead, or `targeting.rear_range` behind) + (1 − |cos a|) × `targeting.side_range`.
  - Every native sentry has −1/−1, meaning "use `targeting.range`", which is why sentries see all around them. −1 is
    the only accepted value below 0.
  - A smaller rear range makes a sentry ignore enemies behind its barrel until they come close.
  - The Tesla Tower's sensor is a different type whose test reads only the main range, so it has neither field.
- **The AI caps the useful range.** Target selection scores candidates on a hard-coded distance curve that reaches 0
  at:
  - 100 m on the MG-43, G-16, AC-8 and LAS-98;
  - 50 m on the FLAM-40;
  - 125 m on the mortars.

  A `targeting.range` above that cap does not extend engagement; lowering it does work. The accepted range stays
  1–500 m for compatibility. Each descriptor publishes its cap as `engagementCap`.
- **Mortars also acquire through a second sensor.** The M-12, M-23 and GM-17 own a SensorProximity component
  (125 m) that marks every enemy within its radius as perceived, with no line-of-sight check. Lowering
  `targeting.range` alone therefore does not shrink a mortar's acquisition.
  - The proximity radius (`targeting.proximity_range`) is researched but deferred: it is not writable yet.
  - The mortars also never target enemies closer than 25 m (M-12) or 14 m (EMS and gas mortars). That minimum is
    hard-coded as well.

### Weapon handling

`hd2.stratagem(name):deployed_entity():weapon("primary")` exposes the same WeaponData members as the player and
support weapons, with the same field constants:

| Field | Native member | Range | Sentries |
| --- | --- | --- | --- |
| `weapon.horizontal_spread` / `weapon.vertical_spread` | WeaponData +84 / +88 | 0–500 mrad (full width) | the seven projectile sentries |
| `weapon.recoil_drift_horizontal` / `_vertical` | WeaponData +0 / +4 | 0–100 | the seven projectile sentries |
| `weapon.recoil_climb_horizontal` / `_vertical` | WeaponData +28 / +32 | 0–100 | the seven projectile sentries |
| `weapon.recoil`, `weapon.horizontal_recoil`, `weapon.vertical_recoil` | derived means | read-only | the seven projectile sentries |
| `windup.wind_up_seconds` / `windup.wind_down_seconds` | WeaponWindUp +0 / +4 | 0–30 s (`wind_down_seconds` is a switch: 0 stops the barrels at once, any positive value spins down over the wind-up time) | G-16 Gatling Sentry |
| `heat.firing_charge` / `heat.charge_gain_per_second` / `heat.charge_loss_per_second` (0.30.4) | WeaponHeat +148 / +152 / +156 | 0–10000 / 0–100000 / 0–100000; read live | A/LAS-98 Laser Sentry: its wind-up, 100 / 200 = 0.5 s before each beam (`allow_unverified_effect`; research/windup-controls-F5FEE03DCFDB.json) |
| `beam.fire_rate` | BeamWeapon +104 | 1–3000 rpm | LAS-98 Laser Sentry |

- **The seven projectile sentries** are the MG-43, G-16, AC-8, M-12, MLS-4X, M-23 and GM-17.
- **Spread and recoil:**
  - Their values equal the wiki's detailed tables on every one of the seven. For example the mortar's spread is
    50 × 100 mrad, and the MG-43's recoil is 10 / 1 / 5.5, which are the means of drift and climb.
  - The game copies them into the weapon when the sentry spawns. Every shot then turns by up to half the spread
    each way, and kicks the turret's own aim by the recoil. So zero recoil tightens a sentry's grouping.
- **Excluded sentries.** The Laser, Flame and Tesla sentries carry the same WeaponData members and their published
  values match. However, no read of them on a beam, spray or arc attack is shown, so they are excluded and the
  reason is listed in `blockedFields`.
- **`windup.*`.** Read by the wind-up routine every update. Whether the Gatling waits for full spin before firing is
  not established; the effect may be the barrel spin only.

### Live evidence

**Live-proven (2026-09-29; see [live evidence](live-evidence.md)):**

- `SentryTurnSpeed` made the AC-8 turn dramatically faster.
- `SentryDetectionRange` made the MG-43 hold fire until enemies were very close.

`turret.yaw_speed`, `turret.pitch_speed` and `targeting.range` need no acknowledgement and carry a `liveEvidence`
reference. Every other field above needs `allow_unverified_effect=true`. The new 0.30.0 fields belong to the
pending family `sentry_component_fields`. Their live test is `examples/projects/SentryTuningTest`.

`payload.lifetime` is published on every sentry and the Tesla Tower. It is the HellpodPayload member
ShieldRelayImprovements proved in gameplay; the sentry values equal the wiki's lifetime (150 s, or 180 s for the
mortars and laser sentry).

### What stays unmapped

Most of a sentry's engagement logic is compiled AI code, not data, so no write can change it:

- the distance score curves and caps above;
- the fire cones: the sentry fires only within 3° of its aim on the MG-43 and G-16, 2° on the AC-8 and 10° on the
  FLAM-40 and LAS-98;
- the re-pick, initial-wait and alert timings;
- the mortar minimum distances.

Data members that stay unmapped:

- **TargetingComponent +4/+8/+12.** These were previously listed as "timers (0.5 / 0.5 / 5 s)". That was wrong:
  - +8 and +12 are the damping and stiffness of the aim-direction spring, and +16 and +20 are its speed cap and gate
    angle;
  - they are the same on every sentry;
  - whether the turret follows that spring is not shown;
  - no reader of +4 was found.
- **TurretComponent +36/+40 (0.1).** The debounce of the rotation sound and animation events; presentation only.
- **SensorEye +12/+16 (20/20, 360/360 on the AC-8).** Cone half-angles used only by a sensor type no sentry has.

Details: [sentry component research](research/sentry-components-F5FEE03DCFDB.md).

## Vehicle and backpack call-in definitions

Nine vehicle and 13 backpack StratagemDefinitions are listed with writable cooldowns. Each carries a
`delivers` link to the `hd2.vehicle` or `hd2.backpack` semantic ID of the entity it delivers.

## Resupply

```lua
local resupply = hd2.stratagem('Resupply')
hd2.ensure({patch = {id = 'fast-resupply', target = resupply,
    field = hd2.fields.stratagem.definition_cooldown, expect = 180, value = 5}})
local rack = resupply:delivery():rack()   -- the Resupply pod: four Supply Box slots
```

- **Identity** (`research/resupply-F5FEE03DCFDB.json`, `scripts/research_resupply.py`): the only StratagemInfo row of
  native type AmmoRack (33), whose UI icon is `StratagemRessuply`. Its id, group, row, package and payload list are
  identical in all seven retained snapshots. Family `mission`, always available.
- **Fields:** cooldown (+104, 180 s) and mission uses (+80, unlimited), guarded like every other definition.
- **Payload:** three (Resupply rack, hellpod) pairs of one rack; `delivers` links it to the `Resupply pod`
  (`hd2.pod_rack`). The rack is shared with the Resupply reward variant (`allow_shared`).
- **Live-proven** (ResupplyTest): a 5 s cooldown (ready again 5 s after use), and Grenade Boxes in pod slots 1-4
  (package loaded automatically). Those four slot/pickup pairs need no `allow_unverified_reference`
  (`docs/pod-payloads.md`).
- **Not offered:** a medal payload. No medal pickup entity exists, and the one exploration-reward entity uses an
  unproven interaction type and grants server-side account progression.

## Stratagem icon identity and catalog equipment

`StratagemAuthoringCapabilities.json` publishes two presentation facts per stratagem. Neither changes write semantics.

### `uiIcon`

For each stratagem, `uiIcon` names the game's own icon for that stratagem:

```json
"uiIcon": {"state": "resolved", "nativeType": "C4", "nativeTypeValue": 14,
           "iconKey": "StratagemC4", "library": "content/ui/shared/resources/generated_icons/stratagem_icons",
           "provenance": {"basis": "native_stratagem_type", "evidence": [...], "displayNameEquality": "not used",
                          "researchArtifact": "stratagem-icons-F5FEE03DCFDB.json"},
           "blocker": null}
```

`iconKey` is the key tooling uses to find the artwork. For any state other than `resolved`,
`blocker` holds `{kind, reason}`, and `reason` repeats the same text. `provenance` is `null` for
`no_native_root`. The top-level `uiIconContract` (contract `hd2runtime.stratagem.ui_icon.v1`)
describes each state, the chain, the library and its SHA-256.

**Structural chain** (also in `uiIconContract.chain`). No display names are used.

1. The mapped `StratagemInfo` row's member 0 is `type`: `ENUM_UINT32`, enum `StratagemType` in the pinned type library.
2. The StratagemType value maps to its native member name through the enum name table in `game.dll`. The table is accepted only as the unique pointer run `None`…`Count` whose every entry length equals the type library's hidden alias length for that value (151 of 151).
3. The native member name maps to an icon key through the game UI's `StratagemTypeDataTemplate` DataTriggers in the icon library.
4. The icon key maps to a `DataTemplate` in the same library.

**States:**

| State | Meaning | Count (pinned build) |
| --- | --- | ---: |
| `resolved` | The bound template has vector artwork | 84 |
| `empty_template` | Bound, but the template is empty in this game build (Maxigun, Jump Pack, Rover, Hot Dog) | 4 |
| `unbound` | The library binds no icon to the native type (Eagle Gas Airstrike, AC-8 Autocannon, 40-K Meltagun, M-103 Supply FRV, TD-110 Maelstrom) | 5 |
| `no_native_root` | No call-in stratagem, so no native type (CQC-72, SG-88: `rootResolution` `NO_CALL_IN`) | 2 |

No two roots resolve to the same template. The library has 111 templates: 92 contain vector artwork and 19 are empty (`uiIconContract.emptyTemplates`).

**Artwork:** it is never published (`artworkPublished: false`). Tooling reads the library read-only from the user's installed game and verifies `librarySha256` for the reviewed build.

### `catalogEquipment`

Every support stratagem is generated from one support-weapon catalog record. Runtime locates its call-in by a reviewed native debug name. `catalogEquipment` records that pairing so tooling can present the call-in and its equipment together:

```json
"catalogEquipment": {"kind": "support_weapon", "supportWeapon": "support-weapon/v1/b-md-c4-pack/67a19fb797b95c09",
  "basis": "catalog_record", "nativeCallInResolved": true, "nativeDeliveryProven": true, "corroboration": [...]}
```

It is presentation only.
- `delivers` (stratagem side) and `linkedStratagem` (weapon side) remain the only native ownership links. They are unchanged.
- `nativeDeliveryProven` is true only when `delivers` already names this weapon.
- `summary.catalogOnlyEquipment` lists the pairs without proven delivery: CQC-72 Entrenchment Tool and SG-88 Break-Action Shotgun. B/MD C4 Pack's delivery is proven through native loadout identity (see above).
- For C4, the call-in's reviewed debug name (`TEAM WEAPONS. C4`), cooldown (480 s) and unlimited uses corroborate the catalog record.

Research: `scripts/research_stratagem_icons.py` → `research/stratagem-icons-F5FEE03DCFDB.json`. Generator: `scripts/generate_stratagem_authoring.py`.
