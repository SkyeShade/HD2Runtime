local hd2=require('mods/skyeshade/hd2runtime')
-- B/FLAM-80 Cremator: its spray DamageInfo and the fire status it applies per hit.
local cremator=hd2.support_weapon('B/FLAM-80 Cremator')
return hd2.ensure({plan={id='cremator-burn',operations={
    {id='spray',target=cremator:attack('primary'),allow_shared=true,changes={
        {field=hd2.fields.damage.player_standard_damage,expect=3,value=5},
        {field=hd2.fields.damage.player_durable_damage,expect=3,value=5}}},
}}})
