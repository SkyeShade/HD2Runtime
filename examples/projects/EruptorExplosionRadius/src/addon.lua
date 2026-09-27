local hd2=require('mods/skyeshade/hd2runtime')

local explosion=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()

return hd2.ensure({
    patch={
        id='eruptor-radius-5m',
        target=explosion,
        field=hd2.fields.explosion.inner_radius,
        expect=4,
        value=5,
    },
})
