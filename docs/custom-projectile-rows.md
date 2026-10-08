# Runtime-owned custom projectile rows (hybrid rows)

Status: **infrastructure and development proofs only** (v0.29.0 work). There is no public API. The development
proof ran live on host on 2026-09-30, twice. In the second run every variant worked, also after deaths and in a second
mission: see [Live results](#live-results). A weapon fires a custom projectile only through
[weapon projectile replacement](#weapon-projectile-replacement), live-verified on the SMG-32 Reprimand on
2026-10-01. Build F5FEE03DCFDB.

## Architecture

A custom projectile is a semantic definition backed by a **Runtime-owned ProjectileInfo row**:

```
semantic definition (runtime/custom_projectiles.lua)
  -> Runtime-owned 272-byte ProjectileInfo row (a block the Runtime allocates; never a vanilla row)
       row+0x00 = a vanilla base ProjectileType (the LAS-58 Talon's 144 in the proof)
       only COPIED_AT_SPAWN members may differ from the live vanilla base row
  -> the game's native SpawnProjectile, called directly with the Runtime-owned row in its descriptor
```

No ProjectileType is added, no vanilla row is borrowed or written, the vanilla registry is not relocated or
extended, and no game code is patched. The spawned projectile keeps the vanilla base type, which is what the game's
later lookups and other machines know about.

| Piece | File | Role |
| --- | --- | --- |
| Research | `scripts/research_projectile_rows.py` -> `research/projectile-rows-F5FEE03DCFDB.json` | SpawnProjectile, the member policy and its evidence (read-only) |
| Domain | `scripts/generate_projectile_rows.py` -> `domains/projectile_rows.lua` | generated: call facts, row size, member policy, pins |
| Policy | `core/projectile_rows.lua` | pure: clone, permitted changes, hybrid validation |
| Registry | `runtime/custom_projectiles.lua` | definitions, their Runtime-owned rows and packages |
| Native layer | `runtime/event_world.lua` `spawn_projectile_row` | every guard, then the one native call |
| Adapter | `runtime/windows_write.lua` `owned_block`, `owned_write`, `native_spawn_projectile` | memory the Runtime owns; the call |
| Action | `api/actions.lua` `spawn_custom_projectile` (not exported by `hd2`) | authority, rate limit, asset gate, logging |
| Components | `domains/projectile_rows.lua` `components`, `core/projectile_rows.lua` `component_changes` | semantic descriptors; copy exactly the members a component owns |
| Catalogue | `scripts/research_projectile_components.py` -> `research/projectile-components-F5FEE03DCFDB.json`, `scripts/generate_projectile_catalogue_report.py` -> `research/docs/projectile-components-F5FEE03DCFDB.md` | every vanilla row split into components, identical values grouped |
| Proof | `proof/CustomProjectileRowProof`, `scripts/build_custom_projectile_proof.py` | development-only live test |
| Pool | `scripts/research_projectile_pool.py` -> `research/projectile-pool-F5FEE03DCFDB.json` -> `domains/projectile_rows.lua` `pool`; `runtime/event_world.lua` `projectile_counter`, `projectile_types`, `projectile_slot` | the projectile pool, read-only: which projectiles spawned since the last look |
| Replacement | `runtime/projectile_replacement.lua`; `api/actions.lua` `replace_projectiles`, `stop_replacing_projectiles` (not exported by `hd2`) | a weapon's carrier shots replaced by a custom projectile |
| Replacement proof | `proof/ReprimandCustomProjectileProof` | development-only live test: the SMG-32 Reprimand fires `dev/talon_combined` |
| Fire-mode proof | `proof/ReprimandFireModeProof` | development-only live test: a Normal / Custom projectile mode, three fire rates, a 50-round magazine |
| Fire-mode proof (Concussive) | `proof/LiberatorConcussiveFireModeProof` | the same on the AR-23C Liberator Concussive (its Drum magazine attachment owns the capacity) |
| Mounted-weapon proof | `proof/PatriotCustomProjectileProof` | the EXO-45 Patriot's minigun fires `dev/talon_combined`; source-identity binding, suppression check, pool confirmation |

## The native call

game.dll `0x13A9830` `SpawnProjectile(system, const descriptor *, const extra *)` inserts one projectile into the
system's 2048-slot pool and returns the slot (0 at once when the system is inactive, `+0x28`). The descriptor it reads:

| Offset | Field | Runtime passes |
| --- | --- | --- |
| +0x00 | position pointer | the requested position |
| +0x08 | direction pointer | the requested direction, normalised (a zero vector is refused) |
| +0x10 | ProjectileInfo row | the definition's Runtime-owned row |
| +0x18 | source entity | the local avatar |
| +0x1C | owner entity | the local avatar |
| +0x20 | creditor peer (u64) | the local peer |
| +0x28 | kind | 2 |

The third argument is null: all 15 uses in SpawnProjectile test it, and the one callee it is passed to tests it too.
This is exactly the descriptor FireProjectile's plain path builds (`0x13A9700`). There, row = settings[type],
source = owner = the entity, and the creditor comes from `0x129C690`, which maps an avatar to its network id and then
to the owning peer, so for the local avatar it is the local peer. `hd2.explosions` already passes that creditor.

Before each call, `spawn_projectile_row` checks all of these and refuses with a code otherwise:

- it runs inside the game update (`NOT_GAME_THREAD`);
- SpawnProjectile's exact prologue matches, and every projectile-row pin matches (91 instructions, proven once per
  loaded game.dll; `CUSTOM_PROJECTILE_UNAVAILABLE`);
- the projectile system is active (`NOT_IN_MISSION`);
- the base type's vanilla row resolves and carries that type (`UNKNOWN_PROJECTILE`);
- the Runtime-owned row reads back (`ROW_UNREADABLE`) and is a VALID hybrid of the live base row
  (`HYBRID_INCOMPATIBLE`);
- the position is finite, the direction is a unit vector, source and owner exist, and the creditor is a peer id.

The action layer adds its own checks: host only, a mission, the local avatar, the projectile rate limit (12 at once,
4 per second per mod), the cause depth, and every package of the definition resident (base and donors, through the
asset gate). The adapter only accepts a row it allocated itself.

## Member policy

Each ProjectileInfo member (bitfield bits separately, and padding) has one class, with the reason and evidence recorded
in `domains/projectile_rows.lua`:

| Class | Meaning | Members |
| --- | --- | --- |
| BASE_TYPE | must equal the chosen vanilla type | +0x00 |
| COPIED_AT_SPAWN | SpawnProjectile copies it into the spawned projectile; may differ | ballistics: +0x18 diameter (mm), +0x20 speed (m/s), +0x24 mass (g), +0x28 drag, +0x2C gravity, +0x38 lifetime variance, +0x40 penetration slowdown; +0x3C direct damage; +0x90 impact explosion; +0x48 / +0x50 / +0x58 / +0x60 / +0x68 spawn effect; +0x70 / +0x78 record resources |
| LATE_LOOKUP | read again through the stored vanilla type; must equal | +0x80 unit, +0xF0 bit 12, +0xF4, +0xF8, +0xFC bits 0/1, +0x100..+0x10B |
| FIRE_PATH_LOOKUP | read through the weapon's configured type; must equal | +0x1C pellet count, +0x0C mode label, +0x10 mode icon |
| UNKNOWN | not proven either way; must equal | everything else, including +0x30, +0x34 lifetime, +0x9C expiry explosion, the +0x94 overlap gate, the other +0xF0 bits, padding and unnamed bits |

`core/projectile_rows.validate(custom, base, base_type)` returns VALID only when row+0 is the base type, the base row
carries it, and every byte outside COPIED_AT_SPAWN members equals the live base row. Each differing member is
reported with its class, label and reason (for example `+0xF4 collision_filter (LATE_LOOKUP)`).
`core/projectile_rows.apply` refuses any change to a member that is not COPIED_AT_SPAWN. A definition is validated
when it is built and again before every spawn, against the live base row. So if another mod later edits a restricted
member of the base, spawns are refused rather than mismatched.

A member counts as COPIED_AT_SPAWN only when all of these hold:

- SpawnProjectile reads it, and the copy is pinned (`domains/projectile_rows.lua` `pins`);
- it is not a late lookup;
- the census of every settings-table reader in game.dll's code (57 loads) finds no reader outside the reviewed
  configured-type functions.

The research script fails when a new reader of such a member appears. The census has 28 readers reviewed as weapon,
stratagem or statistics lookups. The 29 unreviewed ones read only members that stay locked (+0x00, +0x04, +0x10,
+0x1C, +0x80, +0xF0, +0xF4, +0xFC), and five of them are the stored-type late lookups themselves.

Semantic names and units are published with each member (`label`, `unit`). The ballistics names come from the spawn
code:

- +0x18 is the diameter in millimetres: x 0.0005 gives the radius in metres, which is squared and multiplied by pi/2,
  1.2 (air density) and the +0x28 drag coefficient to give the drag constant.
- +0x24 is in grams (x 0.001 into kilograms).
- +0x38 is the random lifetime variance: the lifetime varies by a random +-(+0x38 x lifetime).

Speed, gravity and penetration slowdown are copied into the slot's ballistics or hit record. The impact explosion is
copied into the hit record, and hit processing reads that copy.

Not promoted yet, though read at spawn: +0x34 lifetime, +0x9C expiry explosion and +0x30. Their evidence was not part
of this pass.

## Components

A definition names its donors by component (`runtime/custom_projectiles.lua`):

```lua
{id = 'dev/talon_combined', base = 'LAS-58 Talon', components = {visual = 'PLAS-1 Scorcher',
    damage = 'RS-422 Railgun', ballistics = 'GL-21 Grenade Launcher', impact_explosion = 'R-36 Eruptor'}}
```

Donors are named by weapon or by projectile output id. A component copies exactly the members its descriptor owns
from the donor's live vanilla row. No donor range is ever copied as a block, and the hybrid validation runs on the
result as before.

| Descriptor | Owns | Assets | Constraint | Live |
| --- | --- | --- | --- | --- |
| ProjectileVisual (`visual`) | +0x48, +0x50, +0x58, +0x60, +0x68 (spawn particle effects) | the donor's package | the donor's unit (+0x80) must equal the base's: the visible part of a unit projectile is its unit, which stays the base's | OBSERVED (PLAS-1 Scorcher on a Talon) |
| ProjectileDamage (`damage`) | +0x3C direct damage (its DamageInfo includes armour penetration and statuses) | the donor's package | none | consumed VERIFIED, magnitude OBSERVED (RS-422 Railgun) |
| ProjectileImpactExplosion (`impact_explosion`) | +0x90 | the donor's package | none | VERIFIED on a Runtime-owned row (R-36 Eruptor on a Talon); also live-proven on native rows |
| ProjectileBallistics (`ballistics`) | +0x18 diameter, +0x20 speed, +0x24 mass, +0x28 drag, +0x2C gravity, +0x38 lifetime variance, +0x40 penetration slowdown | none | none | OBSERVED (GL-21 Grenade Launcher on a Talon; +0x38 and +0x40 not exercised) |

- **Re-proven donor values.** Damage and impact-explosion values are re-proven against the donor's catalogued slot
  (`DONOR_CHANGED` otherwise).
- **Catalogued explosions (0.30.0; not live-tested).** `impact_explosion` also takes a catalogued explosion
  (`hd2.explosion(name)` or its name; docs/explosions.md) with a known package: its type is written at +0x90 after its
  live settings record proves the reviewed type, damage link and radii, and its package (unless it is the mission
  effects package) joins the definition's dependencies.
- **Packages.** They are gathered only for components with assets, deduplicated, and loaded through the asset gate
  before a spawn.
- **Unassigned members.** +0x70 and +0x78 are copied at spawn but belong to no component, because their meaning is
  not established.
- **No colour component.** Colour is baked into the particle effect assets.

**The catalogue** (`research/docs/projectile-components-F5FEE03DCFDB.md`) splits all 350 vanilla rows into these
components. All 350 live rows match the datalibrary. 86 rows have a catalogued identity, 70 rows have a runtime donor
(78 donor names), and 139 rows have a unit.

| Component | Unique values (all rows) | Unique values with a runtime donor |
| --- | --- | --- |
| Visual | 103 | 30 (20 usable on a unit-less base) |
| Direct damage | 233 | 66 |
| Impact explosion | 145 | 23 |
| Ballistic profile | 201 | 51 |

## Evidence (research/projectile-rows-F5FEE03DCFDB.json)

Confirmed on this build:

- **The row is only read during the call.** SpawnProjectile reads the row through descriptor +0x10 and stores row+0x00
  in the pool's per-slot type array (`system+0xE5040`, `0x13A9BB5`). It copies what it needs, for example +0x3C into the
  record +0x0C along with that DamageInfo's armour penetration.
- **Later code reads the vanilla table again, at exactly five places.** The stored type is written once
  (`0x13A9BB5`) and read back only at `0x13A8B20`, `0x13ABCB1`, `0x13AD834`, `0x13AD8E6` and `0x13B3204`. Each
  indexes the vanilla table at once. Through them the game reads:
  - +0xF4 every frame (`0x13ABDAD`), and +0xF8 in an out-of-line block of the same update (`0x13AC0D8`);
  - +0xFC bit 0 on a damage hit (`0x13AD858`, `0x13AD90A`);
  - +0xFC bit 1, +0x100..+0x10B and +0x80 in the unit hand-off (`0x13A8B41`..`0x13A8BE4`);
  - +0xF0 bit 12 on impact (`0x13B322F`).

  These are the only row members reread through a spawned projectile's stored type.
- **Configured-type readers are not late lookups.** Every other settings-table reader takes its type from a weapon,
  stratagem or entity's configured data: component lookups, StratagemSettings weapon lists, the weapon firing path
  and the weapon statistics queries. That includes the readers of +0x04, +0x10, +0x20, +0x90, the ballistics members
  and a weapon's own +0xF0 bit 12 (`0x851B89`). None of them sees a row spawned directly.
- **No member is a colour or tint.** +0x48 and +0x60 are particle effects created with the spawn pose. Their only
  per-spawn variables are `start` and `end` (thin hashes `0x88F1AF97` / `0xE783D2BD`), set to the slot position.
  Colour is baked into the effect asset. The per-call extra parameters carry speed and damage multipliers, not
  colour.
- **A typeless row cannot work.** Type 0 selects a default row 0x110 bytes before the table (`game+0x37C7560`), so
  every late lookup would read that default row.
- **Pellet count is read on the fire path.** +0x1C is read through the weapon's configured type (`0x75B95F`) and never
  by SpawnProjectile.
- **The row is 272 bytes.** The type library's ProjectileInfo, the datalibrary stride and the default row all agree.
- **The proof rows are vanilla.** Rows 144, 142 and 186 are byte-identical to the datalibrary in every mission
  snapshot.

Not proven:

- **The census's reach.** It follows a table register loaded by `lea` for 64 bytes only. Loads further away (such as
  the configured-type +0xF0 reads at `0x851B85`) are covered by the pinned stored-type closure, not by the census.
- **Each ballistics member on its own.** F6 changes five members at once, and the live report covers the flight as a
  whole (see [Live results](#live-results)). +0x38 and +0x40 are equal in the GL-21 and Talon rows, so no live test
  has changed them.
- **What +0x48 / +0x60 look like.** Each is created at spawn with the spawn pose through engine world API +0x280, and
  its handle is kept in the slot's effect record. Live, the Scorcher's +0x48 / +0x58 made the projectile look
  visibly different (blue-ish, OBSERVED; see [Live results](#live-results)). They are the only visual-relevant members
  the proof changes, but that the result is exactly the Scorcher's effect is not confirmed. +0x60 was not exercised
  (neither row has one).
- **Visibility on other machines.** No network send from SpawnProjectile was found. Other players would only know the
  base type.

## Development proof

`py scripts/build_custom_projectile_proof.py` writes both ZIPs to `build/test-artifacts/`:

- `HD2Runtime-<version>-runtime.zip`, the development runtime from this tree. It reports the same version as the
  last release (the version is not bumped for development builds), so do not distribute it.
- `CustomProjectileRowProof-0.1.0.zip`.

Before a live test, validate the runtime ZIP with `py scripts/validate_packaged_runtime.py
build/test-artifacts/HD2Runtime-<version>-runtime.zip`.

The proof tests each component on its own, then all four together (`custom_projectiles.DEVELOPMENT_VARIANTS`). Every
variant is a Talon row with only the named component taken from its donor.

| Key | Variant | Differs from the Talon in | Packages |
| --- | --- | --- | --- |
| F7 | `dev/talon_visual` | visual from the PLAS-1 Scorcher (+0x48, +0x58) | Talon, Scorcher |
| F5 | `dev/talon_damage` | damage from the RS-422 Railgun (+0x3C: 600 / 225, armour penetration 5 instead of 200 / 20, 3) | Talon, Railgun |
| F6 | `dev/talon_ballistics` | ballistics from the GL-21 Grenade Launcher (100 m/s instead of 1300, gravity 1 instead of 0, drag 1.2, 40 mm, 50 g): a visible lob | Talon |
| F10 | `dev/talon_impact` | impact explosion from the R-36 Eruptor (+0x90: explosion 158, radii 4 / 7 / 8 m, 225 damage, with its shrapnel) | Talon, Eruptor |
| F11 | `dev/talon_combined` | all four above | Talon, Scorcher, Railgun, Eruptor |
| F8 | vanilla LAS-58 Talon | (control) | |
| F9 | integrity check | every vanilla row, table entries 0 and 351, and every variant's Runtime-owned row, against the mission start and the definitions | |

The proof follows the local avatar across the mission (`proof/CustomProjectileRowProof/README.md#avatar-lifecycle`):
it logs `waiting for avatar`, `avatar became available`, `avatar lost` and `avatar restored`, and the keys wait for an
avatar instead of failing. Definitions stay ready from one mission to the next.

The live-verified `dev/talon_hybrid_proof` (visual + damage) stays defined as `custom_projectiles.DEVELOPMENT_PROOF`
for the validators.

The Speargun, the suggested visual donor, cannot supply its visible spear: the spear is its unit resource (+0x80), a
LATE_LOOKUP member that must stay the Talon's (none). The Scorcher has no unit, so its whole in-flight effect can
transfer. The GL-21's visible grenade is a unit too, so its visual is refused on the Talon (`COMPONENT_CONSTRAINT`),
while its ballistics transfer.

Expected log lines, one set per variant:

```
defined: custom projectile dev/talon_combined base type=144 base identity=LAS-58 Talon custom row=0x...
  hybrid compatibility=VALID components: visual from PLAS-1 Scorcher (+0x48 spawn_effect 0xAA3E9927A36A96FB ->
  0x5747E23201659524; +0x58 spawn_effect_parameter 0.05 -> 0.01), damage from RS-422 Railgun (+0x3C direct_damage
  54 -> 64), impact_explosion from R-36 Eruptor (+0x90 impact_explosion 0 -> 158), ballistics from GL-21 Grenade
  Launcher (+0x18 diameter 10 -> 40; +0x20 speed 1300 -> 100; +0x24 mass 12 -> 50; +0x28 drag 0 -> 1.2; +0x2C
  gravity 0 -> 1)
custom projectile dev/talon_combined ... hybrid compatibility=VALID ... native spawn result=slot N vanilla base row
  unchanged fired from (...) by mods/skyeshade/hd2runtime_custom_projectile_row_proof
F11: dev/talon_combined (visual from PLAS-1 Scorcher + damage from RS-422 Railgun + impact_explosion from R-36
  Eruptor + ballistics from GL-21 Grenade Launcher) from (x, y, z) along (dx, dy, dz) [held weapon pose]: requested
F9: 350 vanilla rows compared: all byte-identical to the mission start; row 144 byte-identical; table entries 0 and
  351 unchanged
F9: dev/talon_visual Runtime-owned row 0x... unchanged since its definition
```

### Aiming

Runtime has no researched muzzle node or camera transform. F7 and F8 therefore aim with the most accurate thing it
can read, the weapon in hand.

- **Weapon pose.** `runtime/event_world.lua` `entity_unit` reads the held entity's unit from the game's entity map.
  `unit_pose` reads that unit's root world pose: the rotation rows of the same 4x4 world matrix whose translation row
  `unit_position` already reads. Both are internal, read-only and not exported by `hd2`.
- **Origin and direction.** The shot leaves 1.0 m along the weapon's forward axis (+Y) from the weapon root. That
  approximates the muzzle and keeps the shot clear of your own body. The direction is the weapon's forward axis, so
  it follows the weapon's pitch.
- **Fallback.** The weapon pose is used only while the weapon is in your hands: within 2.5 m of the avatar and
  heading within 60 degrees of the way the avatar faces. Otherwise the shot leaves at chest height (1.4 m) along the
  avatar's facing. This covers nothing in hand, and a weapon that is not in the hands.
- **Log.** Each F7/F8 line names its source: `[held weapon pose]` or `[avatar facing (...)]`.

Evidence (`validation/custom-projectile-snapshot.json`):

- In every retained snapshot the avatar's root pose is an exact upright rotation (row 2 = +Z).
- In the first mission snapshot the held R-36 Eruptor is 1.1 m from the avatar, to its +X side, and points along the
  avatar's +Y (alignment 0.9997). This supports the engine's +X right / +Y forward / +Z up convention.
- In the snapshot taken just before the Hellbomb death, the same weapon's unit is 4.75 m away and faces backwards. The
  proof's rule falls back to the avatar's facing there, which is why the rule exists.

Not proven:

- how closely the weapon's forward axis follows the camera aim (hip fire, sprint and reload animations move the
  weapon);
- where the muzzle actually is.

## Live results

Development proof, solo host. Recorded as reported.

### First run (2026-09-30): visual + damage

Development runtime from this tree. F7 fired `dev/talon_hybrid_proof` (Scorcher visual and Railgun damage together);
F7 and F8 fired from 2.5 m above the avatar along +X.

| Capability | Status | Evidence |
| --- | --- | --- |
| Custom-row spawn (SpawnProjectile with a Runtime-owned row) | **VERIFIED live** | F7 spawned the custom projectile reliably, repeatedly; no crash during repeated spawns and impacts. |
| Custom damage donor (+0x3C, RS-422 Railgun DamageInfo) | **OBSERVED** | The custom projectile dealt substantially more damage to enemies than the vanilla Talon, consistent with the Railgun's 600 / 225 against the Talon's 200 / 20. Not marked VERIFIED: the damage was not measured and armour penetration (5 against 3) was not tested. |
| Custom visual donor (+0x48 / +0x58, PLAS-1 Scorcher spawn effect) | **OBSERVED** | The custom projectile appeared blue-ish and visually distinct from the vanilla Talon bolt, consistent with the Scorcher's plasma effect. +0x48 / +0x58 are the only visual-relevant members the proof changes; that the result is exactly the Scorcher's effect is not confirmed. |
| Vanilla table isolation | **VERIFIED live** | F9: all 350 vanilla rows byte-identical to the mission start, row 144 included; table entries 0 and 351 unchanged; the Runtime-owned row unchanged. The F8 vanilla Talon control kept working. |

Why damage is only OBSERVED: F7 and F8 differ only in the row. The descriptor template is the same (kind 2, the
avatar as source and owner), so a clear damage increase points at +0x3C being consumed. A decisive test would promote
it:

- shots-to-kill against the same enemy type with F8 and then F7 (the Railgun row should need about a third of the
  shots);
- or an armoured zone that the Talon's bolts (armour penetration 3) do not penetrate but armour penetration 5 does.

### Second run (2026-09-30): every variant, deaths and a second mission

The development runtime with the local-avatar fix (`build/test-artifacts/HD2Runtime-0.28.0-runtime.zip`, SHA-256
`6ED5B4AE8615D9C3367DFD3FD47D090C47A0D18896344C69D0B69E3A90FC12C5`) and `CustomProjectileRowProof-0.1.0.zip`, shots
from the held weapon. The user reported that F5, F6, F7, F8, F9, F10 and F11 all work, also after dying and in a new
mission.

What the log shows:

- **Spawns.** Two missions, 183 custom spawns (F5 12, F6 20, F7 9, F10 30, F11 112) and 11 F8 vanilla bolts. Every
  custom spawn logged `hybrid compatibility=VALID` and `vanilla base row unchanged`, and nothing was refused. F7 and F10
  first logged `waiting_for_assets`, then fired once their two packages were resident.
- **Integrity.** F9 ran three times: twice in the first mission, and once in the second against that mission's new
  baseline. Each time all 350 vanilla rows were byte-identical and all five Runtime-owned rows were unchanged. Both
  missions used the same five row addresses: the definitions were kept, not rebuilt.
- **Avatar.** Entity 803 was found through the player list at mission start. Five deaths each ended in
  `avatar restored` (803 → 891 → 948 → 962 → 975 → 994). After the sixth death (994) the proof waited, with reminders
  at 10 s and 20 s, until the mission ended. In the next mission it found entity 1464. No `note:` line appeared:
  Runtime's action layer resolved the same avatar every time.

| Capability | Status | Evidence |
| --- | --- | --- |
| Custom-row spawn | **VERIFIED live** (again) | 183 spawns of five variants in two missions, no crash. The returned slot wrapped past the pool's end (2028 → 11, 2040 → 23) without a failure. |
| Impact explosion donor (+0x90, R-36 Eruptor explosion 158) | **VERIFIED live** | F10 was reported working. The Talon row has no impact explosion (+0x90 = 0), so an explosion on impact can only come from the Runtime-owned row's +0x90. The log agrees independently. F5, F6 and F7 shots took consecutive slots, but consecutive F10 shots were 31 slots apart (32, 63, 94 … 869): 30 more projectiles spawned per shot. That is consistent with explosion 158 releasing its submunition (ProjectileType 201, the Eruptor's shrapnel). The number of fragments per explosion is not researched. |
| Ballistics donor (+0x18, +0x20, +0x24, +0x28, +0x2C; GL-21 Grenade Launcher) | **OBSERVED** | F6 was reported working (the expectation in the checklist: a Talon bolt at about 100 m/s that drops in an arc). The five members changed together; what each contributes is not separated, and nothing was measured. +0x38 and +0x40 are equal in both rows and were not exercised. |
| Visual donor (+0x48 / +0x58, PLAS-1 Scorcher) | **OBSERVED** (again) | F7 was reported working, now as the only change on the Talon. |
| Damage donor (+0x3C, RS-422 Railgun) | **OBSERVED** (unchanged) | F5 was reported working; there is still no shots-to-kill or armour test, so it is not promoted. |
| All four components together (F11) | **OBSERVED** | 112 spawns, including 44 in one stretch, were reported working. |
| Vanilla table isolation | **VERIFIED live** (again) | F9 three times, once in the second mission. The F8 vanilla control fired in both missions. |
| Mission lifecycle | **VERIFIED live** | A mission ended and the next started. The definitions stayed, the baseline was retaken, and every key spawned again without a restart. How the first mission ended was not reported. |
| Local avatar resolution (`runtime/handles.lua` `local_avatar`, player list first) | **VERIFIED live** | Every spawn was credited to avatars found through the player list: entities 803 to 1464, far past the first 64 records. Before the fix, the action layer did not see entity 803 and refused spawns with `NO_LOCAL_AVATAR`. Every reinforcement was picked up (`avatar restored`). |

Still not reported:

- a decisive damage test (shots-to-kill against one enemy type, or armour an F8 bolt does not penetrate), which would
  promote F5 to VERIFIED;
- where shots leave while aiming down sights, from the hip and while sprinting. Six F11 shots fell back to the
  avatar's facing because the weapon was not in the hands: four pointing backwards 0.5 m away, two 0.8-0.9 m away and
  turned 65-68 degrees;
- the action layer's death-reaction path (`include_dead`, an action requested from `player_died`). The proof has no
  such action, and DeathHellbombTest was not rerun on this runtime;
- what other players see (untested; SpawnProjectile sends nothing that was found).

## Live test

Solo, as host. Aim with your weapon: every shot leaves from it (see [Aiming](#aiming)). Compare each variant with
F8. Items 1-7 were reported working in the second run; a shots-to-kill or armour test for item 2 and the positions
in item 8 are still open.

1. **F7 visual only.** It looks like the Scorcher's plasma, not the Talon's bolt. Flight and damage stay the Talon's:
   straight, fast, the same shots-to-kill as F8.
2. **F5 damage only.** It looks and flies exactly like F8 but hits much harder. Count shots-to-kill on one enemy
   type, or try armour an F8 bolt bounces off (armour penetration 5 against 3).
3. **F6 ballistics only.** It looks like F8 (Talon bolt) and deals Talon damage, but flies at about 100 m/s and
   drops in an arc like a grenade. Report whether the arc and speed are obvious, and whether impact, collision and
   expiry still behave.
4. **F10 impact explosion only.** It looks and flies like F8 but explodes where it hits, with the Eruptor's blast and
   shrapnel.
5. **F11 all four.** Plasma look, arcing flight, Railgun damage and the Eruptor blast on impact.
6. **F9.** Every vanilla row, including 144, and every custom row stay unchanged.
7. **Stability.** Repeated shots and impacts don't crash, the mission can finish, and a second mission starts and
   every key spawns again.
8. **Aim.** The shot lines log `[held weapon pose]` while you hold a weapon. Report where they leave while aiming
   down sights, from the hip and while sprinting.

## Weapon projectile replacement

A weapon fires a custom projectile without any change to the game's code. The weapon's fire path turns its
projectile type into a row through the vanilla table, so a Runtime-owned row cannot be named there. Instead:

1. **Carrier.** The mod swaps the weapon to fire a *carrier* through the ordinary guarded projectile swap
   (`attack.projectile`). A carrier is a vanilla projectile that is invisible and harmless on its own. The proof uses
   the TD-110 Maelstrom's slot 2 projectile (type 324): no particle effect, no unit, damage type 0 and no explosion.
   Damage type 0 selects the game's default DamageInfo row, which is all zero (no damage, no armour penetration, no
   status) in every mission snapshot. Like the Reprimand's own bullet (type 123) it has lifetime 0, which the update
   never counts down, and collision filter 0: it flies like a bullet until it hits something.
2. **Watch.** Every update, Runtime reads the projectile system's spawn counter and the types of the slots spawned
   since its previous look (`runtime/event_world.lua`, read-only).
3. **Replace.** For each carrier slot whose creditor is the local peer (and, optionally, whose source entity is the
   named weapon), Runtime spawns the custom projectile through `spawn_projectile_row`, with every guard of a custom
   spawn. It starts from the carrier's spawn point (its position less its distance travelled along its direction),
   and it is credited to the local avatar as a custom spawn always is.

The replacement writes nothing. The carrier flies on, and its shot is the game's own: aim, spread, fire rate, recoil
and ammunition. The custom projectile appears one frame after the shot, because the engine calls Lua's `update` before
the game update that fires weapons (`docs/events.md`).

### The pool (research/projectile-pool-F5FEE03DCFDB.json)

| Member | Where | Evidence |
| --- | --- | --- |
| spawn counter | system +0x30 (u32) | SpawnProjectile adds 1 and takes slot = counter & 0x7FF (`0x13A986A`..`0x13A98F4`); 0 at mission start |
| skip rule | | a slot is skipped (the counter advances again) only while its previous projectile's impact or expiry explosion is pending (hit record +0x7C / +0x80, `0x13A991F`, `0x13A9937`); a carrier must have neither |
| type | +0xE5040 + slot x 4 | row +0 (`0x13A9BB5`) |
| position, velocity | flight record +0x3040 + slot x 0x70: +0x00, +0x0C | descriptor position and direction x speed (`0x13A9E3D`..`0x13A9E7F`) |
| distance travelled | flight +0x30 | 0 at spawn (`0x13AA0BB`); the update adds each step's length (`0x13AB80E`) |
| lifetime | flight +0x34 | counted down only while above 0 (`0x13AB82D`..`0x13AB83C`) |
| source entity | +0x3B040 + slot x 0x24, +0x0C | descriptor +0x18 (`0x13AA4EE`) |
| creditor, owner | hit record +0x4D040 + slot x 0xC8: +0x00, +0x08 | descriptor +0x20 and +0x1C (`0x13AA78F`, `0x13AA788`) |

In the four mission snapshots the counter reads 0, 331, 768 and 1005. The newest slots hold world positions, a
velocity near the stored speed, a distance travelled, the local peer as creditor and an owner and source entity. A
finished projectile clears its flags and leaves its records until the slot is reused, so a carrier that already hit
something is still read. Every offset is a pinned instruction, re-proven once per loaded game.dll before the first
read.

### Guards

- **Binding.** Host only. The carrier must be a catalogued projectile output without an impact or expiry explosion
  (`CARRIER_HAS_EXPLOSION`), and the definition's packages load first (`waiting_for_assets`, then `bound`). A binding
  replaces only carriers spawned after it.
- **Every update.** Nothing happens unless the projectile system is active. A new mission (the counter restarts) or
  more than 2048 spawns in one update start again from the current counter. Authority (a mission, host, local avatar
  and peer) is read once per update in which a carrier spawned.
- **Rate.** At most 24 replacements in one update and a burst of 40, refilled at 30 per second. Extra shots are
  dropped and counted, never queued.
- **Spawn.** Each replacement is an ordinary custom spawn: SpawnProjectile's prologue and pins, the projectile system
  active, and the row a VALID hybrid of its live base row.

### Live result (2026-10-01)

Reported by the user: solo host, `ReprimandCustomProjectileProof` on the development runtime from
`build/test-artifacts/` (SHA-256 `F936321DA1B97A06C2A3A25730F8F9DF7D82CD7A72F2E85FD1492F6D181C0AD3`). It "works
flawlessly": the SMG-32 Reprimand fired the type 324 carrier, Runtime detected each carrier and spawned
`dev/talon_combined` in its place. 50 shots replaced, 0 dropped, 0 refused. The logged carriers had travelled 0.00 m when
Runtime first read them.

| Capability | Status | Evidence |
| --- | --- | --- |
| The swapped Reprimand fires carrier 324 through the pool path | **VERIFIED live** | every replaced carrier was read from the pool with the local peer as creditor and the Reprimand as source |
| Weapon projectile replacement: carrier 324 -> `dev/talon_combined` on the SMG-32 Reprimand | **VERIFIED live** | 50 replaced, 0 dropped, 0 refused |
| Where the carrier is when Runtime reads it | **OBSERVED** | travelled 0.00 m: the game had not moved the carrier yet. The cause (the weapon firing after the projectile update, or a new projectile not stepped in its first update) is not established; the replacement starts from the spawn point either way |

The promotion covers exactly this weapon, carrier and definition. Other weapons, carriers and definitions use the same
mechanism but are not live-tested.

### Live results (2026-10-01): fire modes and the Patriot

Reported by the user, solo host, on the development runtime from `build/test-artifacts/`. Recorded as reported.

**ReprimandFireModeProof** (SMG-32 Reprimand): the Normal and Custom modes both worked, and at about 1500 rpm 51 shots
were replaced, 0 dropped, 0 refused, every carrier read at 0.00 m travelled.

**PatriotCustomProjectileProof** (EXO-45 Patriot right gun): at about 1200 rpm 5 of 5 shots were replaced, 0 dropped, 0
refused, 0 native bullet sightings (suppression held), carriers read at 0.00 m travelled, with about 10.6 ms
replacement latency (one game update). The shots were credited to the local pilot (the local peer).

| Capability | Status | Evidence |
| --- | --- | --- |
| Mode-aware binding: the Reprimand's ProgrammableAmmo mode (+576 = carrier 324) replaced, its Normal mode never | **VERIFIED live** | both modes worked in one session; 51 replaced, 0 dropped, 0 refused |
| Replacement at about 1500 rpm on the Reprimand | **VERIFIED live** | 51 replaced at about 1500 rpm, 0 dropped |
| Source-bound binding on a mounted weapon: carrier 324 -> `dev/talon_combined` on the Patriot right gun | **VERIFIED live** (5 shots) | 5 of 5 replaced, 0 dropped, 0 refused; a small sample |
| Suppression of the Patriot's native bullet by the carrier swap | **VERIFIED live** (5 shots) | 0 native sightings |
| Who a Patriot right-gun shot is credited to | **OBSERVED** | the local peer (the pilot); `credit = 'local_or_none'` was not needed in this run |
| Replacement latency | **OBSERVED** | about 10.6 ms: one game update |

Not reported in these runs, so not promoted: the 50-round magazine, the 490 and 872 rpm choices, the mode labels and
icons, aim and spread checks, and the Liberator Concussive proof.

**Observation, not a replacement failure:** during the Patriot test the Patriot's arm was destroyed. The custom
projectile is Talon-based with the RS-422 Railgun's damage, the R-36 Eruptor's impact explosion and the GL-21's
ballistics, so its own explosion near the exosuit is the likely interaction. The cause is not established here; it is
a follow-up for the projectile definition, not for the replacement.

### Not proven

- What a carrier does on impact visually (sparks or decals of a damage-type-0 bullet): not separately reported.
- Multiplayer: whether other players' shots appear in the host's pool, and what they see. Only the local player's
  carriers are replaced, on the host.
- Any weapon, carrier or definition other than the Reprimand, carrier 324 and `dev/talon_combined`.

### Mode-aware binding

A weapon can fire the carrier in only one of its modes: the game's ProgrammableAmmo weapon function fires
ProjectileWeapon +576 instead of the weapon's projectile while it is on (`docs/weapon-feeds.md`). With +576 set to the
carrier, the carrier type itself marks the Custom mode, so the binding needs no notion of modes: only carrier shots are
replaced, and the Normal mode's native projectile is never a carrier.

Two optional binding settings serve the fire-mode proof (`api/actions.lua` `replace_projectiles`):

- **`unreplaced`**: the weapon's other projectile output (the Normal mode's). Its shots from the same weapon and player
  are counted and logged as `normal mode: ... -> no replacement`, and never replaced. Replacement lines then start
  with `custom mode:`. It must be another type than the carrier (`INVALID_UNREPLACED`).
- **`detail_logs`**: how many shots of each kind are logged in full (`math.huge` for every shot; default 8).

Every binding also measures **bursts**: the weapon's shots (replaced, dropped and unreplaced) until 0.3 s pass without
one. A burst of two or more shots is logged with its count and rate, `burst: 50 shots (50 custom, 0 normal) over 1.96 s
= 1500 rpm`, and `describe()` publishes the last one and the last shot's mode. Shots are timed at the update that first
saw them, so the rate is exact to about one frame at each end.

The Runtime has no reader of the selector state, so the selected mode is known only from the projectile a shot fired.

### Source-bound binding (PatriotCustomProjectileProof)

A mounted weapon has no catalogued weapon name, so `weapon` cannot select its shots. Four more binding settings serve
the Patriot proof (all internal: `api/actions.lua` `replace_projectiles` is not exported):

- **`source`**: a projectile output whose owner entity type (its catalogue `resource`) is the only accepted source
  identity. A shot from any other source counts under `other weapons`.
- **`suppressed`**: the host's native projectile, which the carrier swap replaced. A shot of it from the same source
  is logged as `SUPPRESSION FAILED` and never replaced; the summary reports `suppression held` or `FAILED`.
- **`credit = 'local_or_none'`**: also accepts a shot credited to no peer. Which peer a mounted weapon's shot is
  credited to is not proven offline.
- **`attribute`**: each logged shot also carries its creditor, owner and source identities, the host context, and the
  latency (the update's `dt` and the carrier's flight time before the read).

Every binding now also **confirms** each custom projectile: the next update must find the definition's base type in
the pool slot SpawnProjectile returned (`confirmed`, else `not`). With `carriers`, `replaced` and `confirmed` equal,
each shot produced exactly one custom projectile.

### Live test: weapon projectile replacement

Install the development runtime and `ReprimandCustomProjectileProof` from `build/test-artifacts/`. Solo, as host, with
the SMG-32 Reprimand in your loadout (or called in after the mod loaded).

1. **Replacement.** Fire the Reprimand. Each shot should be the plasma-looking, arcing `dev/talon_combined` projectile,
   at the Reprimand's fire rate, with the Eruptor blast on impact. No vanilla Reprimand bullet should be visible.
2. **Aim.** Shots should leave from the muzzle and land where you aim (hip and down sights), with the Reprimand's
   spread. Report any visible offset or delay.
3. **Carrier alone.** Press F12 (replacement off) and fire: nothing should be visible, and enemies should take no
   damage. Report any impact sparks. Press F12 again to turn replacement back on.
4. **Point blank.** Fire into a wall or an enemy right in front of you. The custom projectile should still appear and
   hit.
5. **Counts.** Press F9 after a few bursts. `dropped` should stay 0 at the Reprimand's fire rate.
6. **Lifecycle.** Die, reinforce and fire again; finish the mission and fire in the next one.
7. **Log.** Send the `projectile replacement:` lines, especially the first `shot N` lines with `travelled D m`.

### Live test: Reprimand fire modes

Install the development runtime and `ReprimandFireModeProof` from `build/test-artifacts/`, and uninstall
`ReprimandCustomProjectileProof`. Solo, as host, with a Reprimand built after APPLY (loadout or call-in). Pick the
rate in Mod Options before taking the weapon; each rate needs a freshly built Reprimand.

1. **Normal mode.** The native bullet; no custom projectile; the log shows `normal mode: ... -> no replacement`.
2. **Custom mode** (weapon-function menu). The custom projectile appears for every shot, no carrier is visible, and
   there is no second projectile; the log shows `custom mode: ... -> slot M`.
3. **Normal -> Custom.** The projectile changes with the mode.
4. **Custom -> Normal.** Replacement stops; the native bullet is back.
5. **490 rpm** (Mod Options). The burst log reads about 490 rpm.
6. **872 rpm.** About 872 rpm.
7. **1500 rpm.** About 1500 rpm in the burst log, `dropped` 0 in F9, every shot replaced.
8. **Magazine.** 50 shots from a full magazine before the reload (one burst of 50 in the log).
9. **Rapid fire.** Several full magazines at 1500 rpm in Custom mode; F9 counts after each.
10. **Aim and spread.** Down sights, from the hip, and moving.
11. **F12.** Off: Custom mode fires the harmless carrier alone (nothing visible, no damage). On: replacement is back.

Report the burst lines, the F9 lines, and whether the mode menu shows STANDARD and HE with their icons.

The Patriot's live test is in `proof/PatriotCustomProjectileProof/README.md`.

`LiberatorConcussiveFireModeProof` runs the same checklist on the AR-23C Liberator Concussive (rates 400 / 640 / 1500;
the magazine is its Drum attachment's, 50 with its toggle on, 60 off). Install one fire-mode proof at a time.

## Not in scope

These are left for later work:

- a public API for weapon projectile replacement, a choice of carrier per weapon, and replacing other players' shots
  (a cosmetic copy on clients);
- HUD names and icons;
- networking;
- registry relocation, padding ids, or ids 351 and above;
- fully synthetic rows;
- a public create/clone API.
