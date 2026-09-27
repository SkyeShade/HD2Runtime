local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    patch={
        id='concussive-semi-auto',
        target=hd2.weapon('AR-23C Liberator Concussive'),
        field=hd2.fields.weapon.default_fire_mode,
        expect=hd2.enums.fire_mode.full_auto,
        value=hd2.enums.fire_mode.semi_auto,
    },
})
