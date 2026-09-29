local hd2=require('mods/skyeshade/hd2runtime')
-- M-1000 Maxigun bullets apply Stun Medium (strength 2, the AR-32 Pacifier / SMG-72 Pummeler value) through the
-- first empty status slot of their DamageInfo row. Status references on player and support projectile rows are
-- live-proven (2026-09-29): no acknowledgement is needed. allow_shared stays: settings rows are global definitions.
local bullets=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile()
return hd2.ensure({plan={id='maxigun-stun',operations={
    {id='stun',target=bullets,allow_shared=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
