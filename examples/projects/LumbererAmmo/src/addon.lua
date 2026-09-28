local hd2=require('mods/skyeshade/hd2runtime')
-- Recreates Lumberer Ammo v1.1: flamethrower arm 500 -> 1000, anti-tank cannon arm 25 -> 35.
local lumberer=hd2.vehicle('EXO-51 Lumberer Exosuit')
return hd2.ensure({plan={id='lumberer-ammo',operations={
    {id='flamer',target=lumberer:weapon('left_gun'),field=hd2.fields.weapon.capacity,expect=500,value=1000},
    {id='cannon',target=lumberer:weapon('right_gun'),field=hd2.fields.weapon.capacity,expect=25,value=35}}}})
