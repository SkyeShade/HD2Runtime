local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        plan={
            id='support-plan-a7d11bc364c94023b9ff184d',
            operations={
                {
                    id='support-49005d2aba74da74f53befc8',
                    target=hd2.support_weapon('FLAM-40 Flamethrower'),
                    changes={
                        {field=hd2.fields.magazine.magazines_from_supply,expect=6,value=8},
                        {field=hd2.fields.magazine.spare_magazines,expect=5,value=8},
                        {field=hd2.fields.magazine.starting_magazines,expect=3,value=8},
                        {field=hd2.fields.weapon.capacity,expect=150,value=350},
                    },
                },
                {
                    id='support-d66c99def731dc2dde7980b0',
                    target=hd2.support_weapon('FLAM-40 Flamethrower'):attack('primary_status_5'),
                    allow_shared=true,
                    field=hd2.fields.status.duration,
                    expect=3,
                    value=10,
                },
                {
                    id='support-cc981b80d9163ea29e8e8ed2',
                    target=hd2.support_weapon('FLAM-40 Flamethrower'),
                    field=hd2.fields.weapon.ergonomics,
                    expect=5,
                    value=25,
                },
                {
                    id='support-b5fcf1d4220c17f451391d9d',
                    target=hd2.support_weapon('FLAM-40 Flamethrower'):attack('primary'),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.damage.ap_direct,expect=4,value=8},
                        {field=hd2.fields.damage.ap_extreme,expect=4,value=6},
                        {field=hd2.fields.damage.ap_large,expect=4,value=8},
                        {field=hd2.fields.damage.ap_slight,expect=4,value=8},
                        {field=hd2.fields.damage.player_durable_damage,expect=2,value=8},
                        {field=hd2.fields.damage.player_standard_damage,expect=2,value=10},
                    },
                },
                {
                    id='support-f747e2656c8e760c72330ef4',
                    target=hd2.support_weapon('FLAM-40 Flamethrower'):attack('primary_status_5'),
                    allow_shared=true,
                    field=hd2.fields.status.strength,
                    expect=2,
                    value=5,
                }
            },
        }
    }),
    hd2.ensure({
        plan={
            id='support-plan-ff0bc43a596f53f27e5dfd80',
            operations={
                {
                    id='support-d0a433eb59e88faa485f1573',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'):attack('primary'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.projectile.drag,expect=0.3,value=0.1},
                        {field=hd2.fields.projectile.pellet_count,expect=1,value=2},
                        {field=hd2.fields.projectile.penetration_slowdown,expect=0.25,value=0.05},
                        {field=hd2.fields.projectile.velocity,expect=980,value=1960},
                    },
                },
                {
                    id='support-9401c3d9683daa4817216b5d',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'),
                    field=hd2.fields.weapon.fire_rate,
                    expect=600,
                    value=1150,
                },
                {
                    id='support-82b8fff675e3ca5aec780860',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'),
                    allow_unverified_effect=true,
                    field=hd2.fields.reload.duration,
                    expect=5.5,
                    value=5,
                },
                {
                    id='support-afdfc9922ea1555ac2bf3aed',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'),
                    changes={
                        {field=hd2.fields.weapon.ergonomics,expect=0,value=30},
                        {field=hd2.fields.weapon.horizontal_spread,expect=5,value=1},
                        {field=hd2.fields.weapon.recoil_climb_horizontal,expect=15,value=3},
                        {field=hd2.fields.weapon.recoil_climb_vertical,expect=30,value=6},
                        {field=hd2.fields.weapon.recoil_drift_horizontal,expect=50,value=10},
                        {field=hd2.fields.weapon.recoil_drift_vertical,expect=80,value=10},
                        {field=hd2.fields.weapon.vertical_spread,expect=5,value=1},
                    },
                },
                {
                    id='support-7e472931eaa978f00de204f8',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'),
                    changes={
                        {field=hd2.fields.magazine.magazines_from_supply,expect=2,value=8},
                        {field=hd2.fields.magazine.spare_magazines,expect=2,value=10},
                        {field=hd2.fields.magazine.starting_magazines,expect=1,value=8},
                        {field=hd2.fields.weapon.capacity,expect=100,value=300},
                    },
                },
                {
                    id='support-bd9b831b96f7775ccfa8375d',
                    target=hd2.support_weapon('MG-206 Heavy Machine Gun'):attack('primary'):projectile(),
                    allow_shared=true,
                    changes={
                        {field=hd2.fields.damage.player_durable_damage,expect=35,value=75},
                        {field=hd2.fields.damage.player_standard_damage,expect=150,value=250},
                    },
                }
            },
        }
    })
}
