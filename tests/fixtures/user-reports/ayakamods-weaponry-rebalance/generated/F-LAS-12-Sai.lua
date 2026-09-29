local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-2a7269b665783a5d909780a8',
        target=hd2.weapon('LAS-12 Sai'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=4,value=41},
            {field=hd2.fields.damage.player_standard_damage,expect=80,value=55},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-f1af46f43e5b20cc65720691',
        target=hd2.weapon('LAS-12 Sai'),
        changes={
            {field=hd2.fields.weapon.horizontal_spread,expect=140,value=40},
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=25,value=15},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
            {field=hd2.fields.weapon.vertical_spread,expect=140,value=40},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-ef52be410d921d00a14057a6',
        target=hd2.weapon('LAS-12 Sai'),
        changes={
            {field=hd2.fields.heat.cool_per_second,expect=5.4,value=8},
            {field=hd2.fields.heat.heat_per_shot,expect=2,value=1},
        },
    }
})
return operations
