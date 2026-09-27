# Guarded composition plans

`hd2.plan` coordinates semantic writes across multiple related objects. Each
operation keeps its own typed target and shared-write acknowledgement. Runtime
resolution combines the complete phase mutation set before any page protection
change, then the existing guarded transaction engine performs stable rereads,
exact-width writes, verification, rollback, protection restoration, and
undeclared-byte checks.

```lua
local projectile=hd2.weapon('AR-23C Liberator Concussive')
    :attack('primary'):projectile()
local impact=projectile:terminal_action('impact')
local expiry=projectile:terminal_action('expiry')
local eruptor=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()

return hd2.ensure({
    plan={
        id='concussive-composition',
        operations={
            {
                id='damage', target=projectile, allow_shared=true,
                changes={
                    {field=hd2.fields.damage.ap_direct,expect=2,value=3},
                    {field=hd2.fields.damage.ap_slight,expect=2,value=3},
                    {field=hd2.fields.damage.ap_large,expect=2,value=3},
                    {field=hd2.fields.damage.ap_extreme,expect=2,value=3},
                    {field=hd2.fields.damage.push_force,expect=60,value=30},
                },
            },
            {id='impact',target=impact,allow_shared=true,
                field=hd2.fields.terminal.explosion,
                expect=impact:no_explosion(),value=eruptor},
            {id='expiry',target=expiry,allow_shared=true,
                field=hd2.fields.terminal.explosion,
                expect=expiry:no_explosion(),value=eruptor},
        },
    },
})
```

Operations execute in declaration order. Identical semantic aliases targeting
the same bytes coalesce only when their expected and desired values agree.
Distinct or conflicting overlaps reject before protection changes.

## Dependency-changing phases

A projectile reference replacement changes the object reached by later
projectile fields. Put the replacement in one phase and use `target_from` in a
later phase:

```lua
hd2.plan({
    id='swap-and-tune',
    phases={
        {id='selector',operations={{
            id='swap',target=target_attack,
            field=hd2.fields.attack.projectile,
            expect=target_attack:projectile(),value=source_projectile,
        }}},
        {id='definition',operations={{
            id='physics',
            target_from={operation='swap',path='projectile'},
            allow_shared=true,
            changes={
                {field=hd2.fields.projectile.velocity,expect=180,value=220},
                {field=hd2.fields.projectile.drag,expect=0,value=0.2},
            },
        }}},
    },
})
```

The second phase freshly resolves both the changed attack selector and the
resulting projectile definition. `target_from` also supports `terminal.impact`
and `terminal.expiry`. It can only reference a projectile replacement in a
prior phase.

If a later phase fails, its writes are first rolled back by the guarded
transaction engine. Earlier phases are then reverted in reverse order using
guarded inverse plans derived from their verified post-state. A target that was
already desired before this plan invocation is not claimed or reverted.

`allow_shared=true` applies to one operation only. Editing a shared projectile,
its DamageInfo, and a shared ExplosionSettings record requires acknowledgement
on each corresponding operation. One operation may contain fields from only one
owning component/settings object, so ProjectileSettings, DamageInfo,
ExplosionSettings, and explosion DamageInfo use separate operations inside the
same plan.
