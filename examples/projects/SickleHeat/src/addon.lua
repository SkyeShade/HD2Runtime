local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    transaction={
        id='sickle-heat-validation',
        target=hd2.weapon('LAS-16 Sickle'),
        changes={
            {field=hd2.fields.heat.capacity,expect=100,value=140},
            {field=hd2.fields.heat.cool_per_second,expect=8,value=12},
            {field=hd2.fields.heatsink.spare,expect=3,value=5},
        },
    },
})
