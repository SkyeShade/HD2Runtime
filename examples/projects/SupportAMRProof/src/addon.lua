local hd2=require('mods/skyeshade/hd2runtime')
local weapon=hd2.support_weapon('APW-1 Anti-Materiel Rifle')
local projectile=weapon:attack('primary'):projectile()

return hd2.ensure({plan={id='support-amr-proof',operations={
    {id='fire-rate',target=weapon,field=hd2.fields.weapon.fire_rate,expect=400,value=800},
    {id='velocity',target=projectile,allow_shared=true,
        field=hd2.fields.projectile.velocity,expect=880,value=1400},
    {id='damage',target=projectile,allow_shared=true,
        field=hd2.fields.damage.player_standard_damage,expect=450,value=900},
}}})
