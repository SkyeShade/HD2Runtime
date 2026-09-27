local hd2=require('mods/skyeshade/hd2runtime')

local target=hd2.weapon('GL-15 Evictor'):attack('primary')
local source=hd2.weapon('P-33 Missile Pistol'):attack('primary'):projectile()

return hd2.ensure({
    patch={
        id='evictor-missile-projectile',
        target=target,
        field=hd2.fields.attack.projectile,
        expect=target:projectile(),
        value=source,
    },
})
