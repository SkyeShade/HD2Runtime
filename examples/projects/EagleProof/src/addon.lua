local hd2=require('mods/skyeshade/hd2runtime')
local eagle=hd2.stratagem('Eagle Airstrike')
return hd2.plan({id='eagle-proof',operations={
 {id='definition',target=eagle,changes={
  {field=hd2.fields.stratagem.definition_cooldown,expect=15,value=5},
  {field=hd2.fields.eagle.uses_per_rearm,expect=2,value=6},
 }},
 {id='rearm',target=eagle:eagle_rearm(),allow_shared=true,
  field=hd2.fields.eagle.rearm_time,expect=150,value=30},
 {id='payload',target=eagle:attack('delivery_1_projectile_impact'),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=10,value=20},
}})
