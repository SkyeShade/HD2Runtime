local hd2=require('mods/skyeshade/hd2runtime')
-- AR-23 Liberator bullets apply Fire (strength 2, the AR-2 Coyote value) through the first empty status slot of their
-- DamageInfo row, shared with the AR-23A Liberator Carbine and StA-52 (allow_shared). Status references on player
-- and support projectile rows are live-proven (2026-09-29): no acknowledgement is needed.
local bullets=hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()
return hd2.ensure({plan={id='liberator-fire-status',operations={
    {id='fire',target=bullets,allow_shared=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='fire'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
