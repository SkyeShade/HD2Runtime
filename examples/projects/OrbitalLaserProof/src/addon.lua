local hd2=require('mods/skyeshade/hd2runtime')
local damage=hd2.stratagem('Orbital Laser'):attack('beam_damage')
return hd2.patch({id='orbital-laser-proof',target=damage,
 field=hd2.fields.damage.player_standard_damage,expect=60,value=400})
