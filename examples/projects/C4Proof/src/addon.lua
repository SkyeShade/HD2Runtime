local hd2=require('mods/skyeshade/hd2runtime')
local explosion=hd2.support_weapon('B/MD C4 Pack'):attack('detonation'):explosion()

return hd2.ensure({plan={id='c4-proof',operations={
    {id='radius',target=explosion,allow_shared=true,
        field=hd2.fields.explosion.outer_radius,expect=7,value=18},
    {id='damage',target=explosion,allow_shared=true,
        field=hd2.fields.explosion.damage_standard_damage,expect=2000,value=6000},
}}})
