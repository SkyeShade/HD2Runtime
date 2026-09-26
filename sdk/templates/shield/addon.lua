local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    transaction={
        id='shield-relay-proof',
        target=hd2.stratagem('Shield Relay'),
        changes={
            {field=hd2.fields.shield.radius,expect=15,value=8},
            {field=hd2.fields.shield.durability,expect=4000,value=40000},
            {field=hd2.fields.payload.lifetime,expect=40,value=90},
            {field=hd2.fields.stratagem.cooldown,expect=90,value=180},
        },
    },
})
