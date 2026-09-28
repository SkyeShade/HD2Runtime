local hd2=require('mods/skyeshade/hd2runtime')

-- Weapon name, field, and expect come from the SDK's
-- PlayerWeaponAuthoringCapabilities.json: "AR-23C Liberator Concussive",
-- weapon.fire_rate, currentDefault 400, editable, weapon_local.
return hd2.ensure({
    patch={
        id='my-hd2-mod-fire-rate',
        target=hd2.weapon('AR-23C Liberator Concussive'),
        field=hd2.fields.weapon.fire_rate,
        expect=400,
        value=1100,
    },
})
