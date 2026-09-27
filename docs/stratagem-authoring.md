# Guarded stratagem authoring

HD2Runtime 0.21 adds `hd2.stratagem(name)` graph inspection and guarded writes for
the 20 imported offensive stratagems and 33 uniquely correlated support-weapon
call-ins. The canonical GUI contract is `sdk/StratagemAuthoringCapabilities.json`.
It publishes one descriptor per semantic field instance and never exposes native
addresses, offsets, record indices, or native resource identifiers.

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

`stratagem:attacks()` returns each reviewed native backing object in the delivery
graph. A field descriptor identifies its attack role, exact baseline, backing
object group, shared consumer scope, and plan group. A transaction may contain
fields from one backing object. Use `hd2.plan` to coordinate ProjectileSettings,
DamageInfo, ExplosionSettings, explosion DamageInfo, and status objects.

Eagle definitions keep three separate concepts: ordinary stratagem cooldown,
per-stratagem uses before rearm, and the shared Eagle rearm definition. Editing
`eagle.rearm_time` requires `allow_shared = true` and affects all eight reviewed
Eagle offensive stratagems.

`stratagem.max_uses` remains readable metadata. Its finite value and unlimited
sentinel are structurally resolved, but mutation is blocked until definition-write
semantics are gameplay-proven. Barrage delivery arrays are preserved as delivery
structure; the SDK does not invent scalar shell or volley counts from them.
