local hd2=require('mods/skyeshade/hd2runtime')
-- EAT-17 Expendable Anti-Tank: direct-hit damage of its rocket and the impact explosion radius.
local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
return hd2.ensure({plan={id='eat-heavy-warhead',operations={
    {id='direct',target=eat:attack('primary'):projectile(),allow_shared=true,changes={
        {field=hd2.fields.damage.player_standard_damage,expect=2000,value=3000},
        {field=hd2.fields.damage.player_durable_damage,expect=2000,value=3000}}},
    {id='blast',target=eat:attack('primary_impact'):explosion(),allow_shared=true,
        field=hd2.fields.explosion.outer_radius,expect=3,value=5},
}}})
