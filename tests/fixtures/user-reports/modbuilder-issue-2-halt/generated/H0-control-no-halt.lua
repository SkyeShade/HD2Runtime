local hd2=require('mods/skyeshade/hd2runtime')

return {
    hd2.ensure({
        patch={
            id='gui-object-1cc8282cf3f687c7088ea1e2',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.fire_rate,
            expect=490,
            value=539,
        }
    }),
    hd2.ensure({
        patch={
            id='gui-object-d1d8b4937e04e28ef1e40df8',
            target=hd2.weapon('SMG-32 Reprimand'),
            field=hd2.fields.weapon.sway,
            expect=1,
            value=1.1,
        }
    }),
    hd2.ensure({
        transaction={
            id='gui-object-62e0b1f6fdaa0b0c382af24c',
            target=hd2.weapon('AR-23 Liberator'),
            changes={
                {field=hd2.fields.weapon.ergonomics,expect=65,value=71.5},
                {field=hd2.fields.weapon.sway,expect=1,value=1.1},
            },
        }
    })
}
