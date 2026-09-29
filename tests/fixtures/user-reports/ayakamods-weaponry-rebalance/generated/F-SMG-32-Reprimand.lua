local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    plan={
        id='plan-978a3a452b01199799d56d4e',
        operations={
            {
                id='op-0434d999b631183c177a808f',
                target=hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile(),
                allow_shared=true,
                field=hd2.fields.projectile.drag,
                expect=1.2,
                value=0.6,
            },
            {
                id='op-84fa0eeec6b1beb063512a05',
                target=hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile(),
                allow_shared=true,
                changes={
                    {field=hd2.fields.damage.player_durable_damage,expect=32,value=83},
                    {field=hd2.fields.damage.player_standard_damage,expect=140,value=110},
                },
            }
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-83b36bae82739da2e4f92309',
        target=hd2.weapon('SMG-32 Reprimand'),
        changes={
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=55,value=45},
            {field=hd2.fields.weapon.recoil_drift_vertical,expect=40,value=20},
            {field=hd2.fields.weapon.sway,expect=1,value=0.5},
        },
    }
})
return operations
