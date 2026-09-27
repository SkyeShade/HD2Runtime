local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('Orbital Precision Strike')
return hd2.plan({id='orbital-precision-proof',operations={
 {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,expect=80,value=20},
 {id='radius',target=strat:attack('delivery_1_projectile_impact'),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=12,value=30},
}})
