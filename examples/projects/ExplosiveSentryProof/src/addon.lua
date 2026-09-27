local hd2=require('mods/skyeshade/hd2runtime')
local strat=hd2.stratagem('A/MLS-4X Rocket Sentry')
local weapon=strat:deployed_entity():weapon('primary')
return hd2.plan({id='explosive-sentry-proof',operations={
 {id='cooldown',target=strat,field=hd2.fields.stratagem.definition_cooldown,expect=150,value=300},
 {id='radius',target=weapon:attack('primary_impact'):explosion(),allow_shared=true,
  field=hd2.fields.explosion.outer_radius,expect=4,value=8},
 {id='damage',target=weapon:attack('primary_impact_damage'):damage(),allow_shared=true,
  field=hd2.fields.explosion.damage_standard_damage,expect=150,value=220},
}})
