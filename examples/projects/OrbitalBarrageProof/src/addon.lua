local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('Orbital 120mm HE Barrage')
return hd2.plan({id='orbital-barrage-proof',operations={
 {id='radius',target=strat:attack('delivery_1_projectile_impact'),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=10,value=25},
 {id='damage',target=strat:attack('delivery_1_projectile_impact_damage'),allow_shared=true,
  field=hd2.fields.explosion.damage_standard_damage,expect=1200,value=3000},
}})
