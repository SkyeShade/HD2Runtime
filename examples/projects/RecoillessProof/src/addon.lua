local hd2=require('mods/skyeshade/hd2runtime')
local weapon=hd2.support_weapon('GR-8 Recoilless Rifle')
local projectile=weapon:attack('primary'):projectile()
local explosion=weapon:attack('primary_impact'):explosion()

return hd2.ensure({plan={id='recoilless-proof',operations={
    {id='velocity',target=projectile,allow_shared=true,
        field=hd2.fields.projectile.velocity,expect=250,value=500},
    {id='radius',target=explosion,allow_shared=true,
        field=hd2.fields.explosion.outer_radius,expect=3,value=12},
    {id='damage',target=explosion,allow_shared=true,
        field=hd2.fields.explosion.damage_standard_damage,expect=150,value=1000},
}}})
