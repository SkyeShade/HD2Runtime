local hd2=require('mods/skyeshade/hd2runtime')
-- Firebomb Hellpods spawns this extra explosion on every hellpod impact. The explosion row and
-- its damage row are separate native objects, so each gets its own plan operation.
local firebomb=hd2.booster('Firebomb Hellpods'):explosion()
return hd2.ensure({plan={id='incendiary-hellpods',operations={
    {id='radius',target=firebomb,allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.inner_radius,expect=2,value=3},
        {field=hd2.fields.explosion.outer_radius,expect=4,value=6},
    }},
    {id='damage',target=firebomb,allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.explosion.damage_standard_damage,expect=200,value=300},
        {field=hd2.fields.status.strength,expect=20,value=40},
    }},
}}})
