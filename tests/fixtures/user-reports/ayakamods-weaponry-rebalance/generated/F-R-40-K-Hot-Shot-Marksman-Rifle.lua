local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-1fa21a42f1e0a9f422dd041f',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.player_durable_damage,expect=40,value=161},
            {field=hd2.fields.damage.player_standard_damage,expect=275,value=215},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-b3b8d1322fea2e6411e98b68',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),
        changes={
            {field=hd2.fields.weapon.recoil_climb_horizontal,expect=12.5,value=10},
            {field=hd2.fields.weapon.recoil_climb_vertical,expect=32.5,value=25},
            {field=hd2.fields.weapon.recoil_drift_horizontal,expect=12.5,value=10},
            {field=hd2.fields.weapon.recoil_drift_vertical,expect=17.5,value=15},
            {field=hd2.fields.weapon.sway,expect=1,value=0.8},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-05950074751c8c07d5f1d507',
        target=hd2.weapon('R/40-K Hot-Shot Marksman Rifle'),
        changes={
            {field=hd2.fields.magazine.magazines_from_supply,expect=7,value=9},
            {field=hd2.fields.magazine.spare_magazines,expect=7,value=9},
        },
    }
})
return operations
