local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('E/AT-12 Anti-Tank Emplacement')
local entity=strat:deployed_entity()
local weapon=entity:weapon('primary')
return hd2.plan({id='anti-tank-emplacement-proof',operations={
 {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,expect=180,value=360},
 {id='health',target=entity,field=hd2.fields.entity.health,expect=300,value=600},
 {id='projectile',target=weapon:attack('primary'):projectile(),allow_shared=true,
  field=hd2.fields.projectile.mass,expect=6500,value=7000},
 {id='explosion',target=weapon:attack('primary_impact'):explosion(),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=6,value=8},
}})
