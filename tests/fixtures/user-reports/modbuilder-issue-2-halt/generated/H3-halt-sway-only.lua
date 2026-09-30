local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        patch={
            id='gui-object-fd5f98440f4482ea96b79ad8',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-458f3277369af725e80a19d9',
            target=hd2.weapon('SG-20 Halt'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-52f52e2ae0a28e9f7526e75e',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-df10a69fd28f65fa6d3ea5a5',
            target=hd2.weapon('AR-23 Liberator'),
            changes={
                {field=hd2.fields.weapon.ergonomics,expect=65,value=71.5},
                {field=hd2.fields.weapon.sway,expect=1,value=1.1},
            },
        }
    })
}
