local hd2=require('mods/skyeshade/hd2runtime')
-- K-2 Throwing Knife: direct-hit damage (no explosion). Standard and durable damage are one
-- DamageInfo row, so they form one transaction; the carry count is the knife's ThrowableComponent.
local knife=hd2.throwable('K-2 Throwing Knife')
return hd2.ensure({plan={id='throwing-knife',operations={
    {id='damage',target=knife:damage(),allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.player_standard_damage,expect=300,value=450},
        {field=hd2.fields.damage.player_durable_damage,expect=150,value=225}}},
    {id='carry',target=knife,allow_unverified_effect=true,
        field=hd2.fields.throwable.max_count,expect=20,value=30},
}}})
