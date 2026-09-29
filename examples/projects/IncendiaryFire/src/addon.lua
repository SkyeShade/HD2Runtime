local hd2=require('mods/skyeshade/hd2runtime')
-- G-10 Incendiary: a wider explosion and more fire applied per hit. The fire amount lives in the
-- grenade's own DamageInfo row; the shared fire status definition (duration) is left unchanged.
local incendiary=hd2.throwable('G-10 Incendiary')
return hd2.ensure({plan={id='incendiary-fire',operations={
    {id='radius',target=incendiary:explosion(),allow_shared=true,allow_unverified_effect=true,
        field=hd2.fields.explosion.outer_radius,expect=7,value=9},
    {id='fire',target=incendiary:explosion():status_effect('fire'),allow_shared=true,
        allow_unverified_effect=true,field=hd2.fields.status.strength,expect=50,value=80},
}}})
