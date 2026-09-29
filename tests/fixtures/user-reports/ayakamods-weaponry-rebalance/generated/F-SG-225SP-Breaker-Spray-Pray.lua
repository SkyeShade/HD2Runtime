local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-d185123e2a4e5934b766adb6',
        target=hd2.weapon('SG-225SP Breaker Spray&Pray'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.player_durable_damage,expect=4,value=7},
            {field=hd2.fields.damage.push_force,expect=1,value=10},
            {field=hd2.fields.damage.stagger,expect=3,value=15},
            {field=hd2.fields.damage.player_standard_damage,expect=15,value=19},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='gui-object-638a52e9f20978259a9eaffd',
        target=hd2.weapon('SG-225SP Breaker Spray&Pray'),
        field=hd2.fields.weapon.sway,
        expect=1,
        value=0.8,
    }
})
return operations
