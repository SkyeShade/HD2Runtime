local hd2=require('mods/skyeshade/hd2runtime')
-- The laser's beam DamageInfo; it is reached through more than one graph path, so allow_shared=true.
local damage=hd2.stratagem('Orbital Laser'):attack('beam_damage')
return hd2.patch({id='orbital-laser-proof',target=damage,allow_shared=true,
 field=hd2.fields.damage.player_standard_damage,expect=60,value=400})
