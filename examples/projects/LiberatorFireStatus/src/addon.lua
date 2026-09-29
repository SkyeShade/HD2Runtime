local hd2=require('mods/skyeshade/hd2runtime')
-- AR-23 Liberator: every bullet also applies Fire (strength 2), the status and strength the AR-2 Coyote bullet
-- applies through the same DamageInfo slot. Magazine, fire modes and projectile unchanged.
local bullets=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()
return hd2.ensure({plan={id='liberator-fire-status',operations={
    {id='fire',target=bullets,allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='fire'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
