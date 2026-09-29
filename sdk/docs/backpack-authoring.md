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
| LIFT-860 Hover Pack | `recharge.time` | schema_proven |
| SH-32 Shield Generator Pack | `shield.radius`, `shield.durability` | schema_proven (relay ShieldComponent) |
| SH-20 Ballistic Shield | `entity.health`; plate armor `zone.armor` on `:damage_zone('shield')` (`allow_unverified_effect`) | health schema_proven; plate armor offline-proven (see below) |
| SH-51 Directional Shield | `entity.health`, `entity.armor` (`allow_unverified_effect`) | AMBIGUOUS: the backpack body, not the barrier |

Read-only:

- **Deposit charges:** `deposit.capacity`, `deposit.start_amount`, and `deposit.refill_amount` on the
  Supply Pack, Guard Dogs, and Hellbomb. The drone values match the wiki exactly, but no reference mod
  proved write semantics. The same fields are writable on the weapon-fed backpacks, where the deposit
  is the proven weapon ammunition store (see [Backpack ammunition](backpack-ammo.md)).
- **Hover Pack vertical launch velocity:** the member is proven on the Jump Pack only.
- **Other launch members:** two further Jumppack launch scalars were only ever experiment profiles,
  and no horizontal impulse member is identified.
- **Warp Pack:** it owns no reviewed behavior component.

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
- SH-51 Directional Shield: `entity.health` / `entity.armor` bind the backpack body (record 296, no zones). The
  energy barrier is a separate entity (its own record, zone `body_front`), and which record the barrier's hits reach
  is not traced, so both fields need `allow_unverified_effect` (AMBIGUOUS).

Not proven: the shield model's full physics actor list (the game data is in the newer bundle format); a hittable
part no zone lists would use the default-zone armor.

