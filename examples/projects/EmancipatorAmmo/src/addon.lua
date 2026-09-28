local hd2=require('mods/skyeshade/hd2runtime')
-- Recreates Emancipator Ammo v1: each autocannon arm holds 150 rounds instead of 100. The arms are
-- independent mounted weapons with their own magazine records.
local emancipator=hd2.vehicle('EXO-49 Emancipator Exosuit')
return hd2.ensure({plan={id='emancipator-ammo',operations={
    {id='left',target=emancipator:weapon('left_gun'),field=hd2.fields.weapon.capacity,expect=100,value=150},
    {id='right',target=emancipator:weapon('right_gun'),field=hd2.fields.weapon.capacity,expect=100,value=150}}}})
