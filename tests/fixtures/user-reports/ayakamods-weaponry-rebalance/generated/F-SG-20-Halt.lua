local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-aba9f0c284c40c71aaf8f6ff',
        target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=10,value=20},
            {field=hd2.fields.damage.player_standard_damage,expect=35,value=26},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-a2877e602fe56952c82a3500',
        target=hd2.weapon('SG-20 Halt'):attack('feed_alternate'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.ap_large,expect=2,value=3},
            {field=hd2.fields.damage.ap_slight,expect=2,value=3},
            {field=hd2.fields.damage.player_durable_damage,expect=2,value=4},
            {field=hd2.fields.damage.player_standard_damage,expect=6,value=9},
            {field=hd2.fields.damage.status_1_strength,expect=1,value=3},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='gui-object-2a64b61fd1fed19c196b1ab7',
        target=hd2.weapon('SG-20 Halt'),
        field=hd2.fields.weapon.sway,
        expect=1,
        value=0.8,
    }
})
return operations
