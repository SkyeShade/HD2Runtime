local hd2=require('mods/skyeshade/hd2runtime')
-- M-1000 Maxigun: every bullet also applies Stun Medium (strength 2), the status and strength the AR-32 Pacifier
-- and SMG-72 Pummeler bullets apply through the same DamageInfo slot. Damage, projectile and fire rate unchanged.
-- The bullet DamageInfo row is shared, so allow_shared is required; a status on an attack that does not use it is
-- not gameplay-proven, so allow_unverified_effect is required.
local bullets=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile()
return hd2.ensure({plan={id='maxigun-stun',operations={
    {id='stun',target=bullets,allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
