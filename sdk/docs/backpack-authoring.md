# Guarded backpack authoring

`hd2.backpack(name)` edits the delivered backpack entity for the 13 wiki backpack stratagems. The
catalog is `sdk/BackpackAuthoringCapabilities.json`.

Each backpack is resolved structurally: StratagemDefinition payload, then hellpod rack, then the
rack's single attached item, which must own `BackpackComponentData`. The runtime re-proves the rack
link before every write. The call-in cooldown stays on `hd2.stratagem(...)`, and the relationship is
published in both catalogs.

| Backpack | Writable | Tier |
| --- | --- | --- |
| LIFT-850 Jump Pack | `recharge.time`, `jump.vertical_launch_velocity` | gameplay_proven (JumpPackImprovements) |
| LIFT-860 Hover Pack | `recharge.time` | schema_proven |
| SH-32 Shield Generator Pack | `shield.radius`, `shield.durability` | schema_proven (relay ShieldComponent) |
| SH-20 Ballistic Shield, SH-51 Directional Shield | `entity.health`, `entity.armor` | schema_proven, wiki-correlated |

Read-only:

- **Deposit charges:** `deposit.capacity`, `deposit.start_amount`, and `deposit.refill_amount` on the
  Supply Pack, Guard Dogs, and Hellbomb. The drone values match the wiki exactly, but no reference mod
  proved write semantics.
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
