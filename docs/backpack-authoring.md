# Guarded backpack authoring

`hd2.backpack(name)` edits the delivered backpack entity for the 13 wiki backpack stratagems and the
3 weapon-fed backpacks that store support weapon ammunition. The catalog is
`sdk/BackpackAuthoringCapabilities.json`.

Each backpack is resolved structurally: StratagemDefinition payload, then hellpod rack, then the
rack's single attached item, which must own `BackpackComponentData`. The runtime re-proves the rack
link before every write. The call-in cooldown stays on `hd2.stratagem(...)`, and the relationship is
published in both catalogs.

| Backpack | Writable | Tier |
| --- | --- | --- |
| LIFT-850 Jump Pack | `recharge.time`, `jump.vertical_launch_velocity` | gameplay_proven (JumpPackImprovements) |
| LIFT-860 Hover Pack | `recharge.time`; `hover.duration`, `jump.vertical_launch_velocity` (`allow_unverified_effect`) | schema_proven; native_correlated |
| LIFT-182 Warp Pack | `warp.*` distance, biases, heat and per-limb injury damage (`allow_unverified_effect`) | native_correlated |
| SH-32 Shield Generator Pack | `shield.radius`, `shield.durability`; `shield.recharge_delay`, `shield.broken_recharge_delay`, `shield.recharge_rate` (`allow_unverified_effect`) | schema_proven; native_correlated |
| SH-20 Ballistic Shield | `entity.health`; plate armor `zone.armor` on `:damage_zone('shield')` (`allow_unverified_effect`) | health schema_proven; plate armor offline-proven (see below) |
| SH-51 Directional Shield | body `entity.health`, `entity.armor`; the barrier through `:energy_shield()` (all `allow_unverified_effect`) | schema_proven / native_correlated |
| Guard Dogs (AR-23, Rover, Hot Dog, K-9, Dog Breath) | drone magazines `deposit.*`; the drone through `:drone()`; its weapon through `:drone():weapon()` (all `allow_unverified_effect`) | native_correlated / schema_proven |

**native_correlated** (new in this release): a typed native member whose meaning is proven offline. That means an
exact published value on every independent entity that publishes one, a differential across the record type, and a
consistent hidden-name length (`research/equipment-coverage-F5FEE03DCFDB.json`, from
`scripts/research_equipment_coverage.py`). None of these fields has been shown in game yet, so every write needs
`allow_unverified_effect`. Each descriptor publishes its `evidence.correlations` (native value next to the published
one) and an `effect` block (active source, lifecycle).

Read-only:

- **Supply Pack and Hellbomb deposits:** no published value proves what their charges do.
- **Other launch members:** two further Jumppack launch scalars were only ever experiment profiles, and no
  horizontal impulse member is identified.
- **Hover Pack ascent, speed and fuel:** the Hover Pack-only vectors and scalars from +145 to +276 have no
  published values. Their layout and hover/jump differential are published as unknown members.
- **Warp Pack:** the maximum survivable unit size (a `UnitSize` enum: only "Medium" = 1 is correlated), the chest
  injury status (Fire), the arrival explosion (a shared ExplosionSettings row) and the remaining typed members.
- **SH-32 +100** ("restart charge" in an external export only), the barrier radius (0: the directional barrier is
  not a sphere), the drone and barrier default-zone armor (the fallback for unlisted actors), the barrier's
  ShieldHitFilter member.
- **Drone AI:** sensor, navigation, targeting, behavior, boids, rotation and motion are generic unit components
  with identical values on every drone and no published values (detection, leash, speed, docking): unknown.

Recharge and launch velocity live on different components, so combine them with `hd2.plan`:

```lua
local jump=hd2.backpack('LIFT-850 Jump Pack')
hd2.ensure({plan={id='jump',operations={
    {id='recharge',target=jump,field=hd2.fields.recharge.time,expect=15,value=8},
    {id='launch',target=jump,field=hd2.fields.jump.vertical_launch_velocity,expect=40,value=50}}}})
```

## SH-20 Ballistic Shield armor

A live report set the SH-20's `entity.armor` to 5; the MG-206 HMG (armor penetration 4) still damaged the shield.
`scripts/research_ballistic_shield.py` (output `research/ballistic-shield-F5FEE03DCFDB.json`) explains why, from the
pinned datalibrary and the game.dll image:

- The SH-20's health record (HealthComponentData record 292, one owner) has a **default zone** (+280, the old
  `entity.armor`) and one damage zone, **zone 0 "shield"** (+736), which lists the shield's hit actors
  (`damageable`, `collision`). The game's zone lookup (game.dll 0x922060) matches the hit actor against every
  zone's list and falls back to the default zone only when no zone lists it. Every bullet on the plate resolves to
  zone 0.
- The armor rule (0x129C9F0): full damage when AP − armor ≥ 1, **65 % when AP equals armor**, none when AP is lower.
  Zone 0 kept armor 4, so the AP 4 HMG was the equal case: (0.3 × 150 + 0.7 × 35) × 0.65 = 45 damage per bullet,
  about 23 bullets to break the 1000-health plate.
- Both armor values are copied into the shield's health instance when it spawns (+0x5C, +0x60): an edit reaches
  shields spawned after the write, never one already in the world.

The API follows the active source:

- `hd2.backpack('SH-20 Ballistic Shield Backpack'):damage_zone('shield')` with `hd2.fields.zone.armor` (vanilla 4,
  0 to 10). Every write re-proves the record's single owner, the zone's name hash and its whole hit-actor list.
  It needs `allow_unverified_effect` until a live test passes (`examples/projects/BallisticShieldArmorTest`).
- The SH-20's `entity.armor` is **read-only** (DORMANT_OR_METADATA for the plate), with the reason pointing at the
  zone. It was live-failed by the report above.
- `entity.health` is the plate's pool (zone 0 health is −1: damage goes to main health) and stays writable.
- SH-51 Directional Shield: `entity.health` / `entity.armor` bind the backpack **body** (record 296, no populated
  zone, so every hit on the body uses the default zone; exact published 400 / Heavy). The energy barrier is a
  separate entity: see below.

Not proven: the shield model's full physics actor list (the game data is in the newer bundle format); a hittable
part no zone lists would use the default-zone armor.

## Shields: recharge delays and rate

The ShieldComponent members +88, +92 and +96 hold exact published values on three independent shields:

| Shield | +76 capacity | +88 recharge delay | +92 broken delay | +96 recharge rate |
| --- | --- | --- | --- | --- |
| SH-32 Shield Generator Pack | 150 | 60 s | 12 s | 150 /s |
| SH-51 energy barrier | 1000 | 3 s | 6 s | 300 /s |
| FX-12 relay | 4000 | 0.00999999978 s | 45 s | 400 /s |

Their hidden-name lengths (14, 21, 13) fit the names. The SH32 ShieldBoost addon's stated originals (60 s, 12 s)
are recorded as a lead only. `shield.recharge_delay` is the time after damage before an unbroken shield recharges,
`shield.broken_recharge_delay` the time before a broken shield restarts, and `shield.recharge_rate` the health
restored per second. They are authored on the SH-32 and the SH-51 barrier (the relay keeps its existing fields).

## SH-51 Directional Shield: body and barrier

The backpack spawns the barrier through its `ShieldControllerComponent` (+0, the barrier entity).
`hd2.backpack('SH-51 Directional Shield'):energy_shield()` targets that entity, and every write re-proves the link.

- Shield energy: `shield.durability` (1000), `shield.recharge_delay` (3), `shield.broken_recharge_delay` (6) and
  `shield.recharge_rate` (300), all exact published values.
- `:energy_shield():damage_zone('body_front')`: the barrier's only damage zone. Its only hit actor is the barrier
  collision (`c_collision`), so projectiles striking the barrier resolve there: `zone.armor` (1), `zone.health`
  (450). Whether the shield energy absorbs a hit before the zone is consulted is not traced, so the zone fields
  are `effect.activeSource = UNPROVEN`.
- The barrier's default-zone armor is read-only: it is only the fallback for an unlisted actor, never the
  shield-facing armor.

## LIFT-182 Warp Pack

`DisplacementComponentData` (632 bytes, one owner) now ships in the runtime profile. Exact published values:
distance (+120, 10 m), upward bias (+128, 1.4 m), downward bias (+132, 4 m), safe and unsafe heat thresholds (+140,
+144: 15 / 45 %), heat per warp (+148, 33 %) and heat cooldown (+152, 6 %/s). Unsafe warps damage one limb through
the typed `HeatInjuryInfo[12]` table (stride 24). Each entry is named by its native limb, and every write re-proves
that name: head 10, `l_hand` / `r_hand` 35, `l_knee` / `r_knee` 45 (`warp.head_injury_damage`,
`warp.left_arm_injury_damage`, ...). The chest entry applies Fire instead of damage (the published "Inflicts Fire").

## LIFT-860 Hover Pack

The Hover Pack and both jump packs share `JumppackComponent` (280 bytes, three records).

- `hover.duration` (+156) holds the published six seconds, and only the Hover Pack record sets it: both jump-pack
  records hold the -1 sentinel.
- The launch uses the vertical launch member (+0, 40) that is gameplay-proven on the LIFT-850. Whether the Hover
  Pack reads it is what `examples/projects/HoverPackTest` checks.
- The recharge (11.5 s) is the existing `recharge.time`. The wiki gives "at most 12 s", an upper bound.

## Guard Dogs

Chain: stratagem -> rack -> backpack -> the backpack's `DepositComponent` +24 (the drone entity) -> the drone's
`MountComponent` slot 0 -> the drone weapon. Each link is re-proven before every write.

- `hd2.backpack(name)`: the drone magazines the backpack holds (`deposit.capacity`, `deposit.start_amount`,
  `deposit.refill_amount`). These are exact published Max Rounds / Starting Rounds / Mags from Supply on all five
  backpacks, and fall under the same 1023 live limit as backpack ammunition.
- `:drone()`: the drone's own health (`entity.health`, 100, exact) and its body damage zone
  (`:drone():damage_zone(0)`: `zone.armor` 1, `zone.health` 100). The default-zone armor is read-only (fallback).
- `:drone():weapon()`: the drone weapon in the mounted-weapon catalog (`sdk/VehicleWeaponCapabilities.json`,
  carrier `backpack_drone`), with the normal weapon fields:
  - AR-23 dog: projectile, 660 rpm, 45 rounds.
  - Rover: beam and heat, `beam.fire_rate` 60.
  - Hot Dog and Dog Breath: spray damage and statuses.
  - K-9: arc range, chain and split, damage, Stun Small.

  The drone reloads from the backpack, so the weapon's own spare-magazine counts are not exposed.

The assault-rifle drone backpack (`drone_assault_rifle_backpack`) is attached by a rack that no stratagem
delivers. It is not a catalog item and is not exposed.

