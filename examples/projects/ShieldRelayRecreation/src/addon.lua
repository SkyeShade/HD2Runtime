local hd2=require('mods/skyeshade/hd2runtime')
local relay=hd2.stratagem('FX-12 Shield Generator Relay')
local base=relay:deployed_entity()
return hd2.ensure({plan={id='shield-relay-recreation',operations={
 {id='cooldown',target=relay,field=hd2.fields.stratagem.definition_cooldown,expect=90,value=180},
 {id='shield',target=base:shield(),changes={
  {field=hd2.fields.shield.entity_radius,expect=15,value=8},
  {field=hd2.fields.shield.entity_durability,expect=4000,value=40000}}},
 {id='lifetime',target=base,field=hd2.fields.payload.entity_lifetime,expect=40,value=90},
 {id='base-health',target=base,field=hd2.fields.entity.health,expect=450,value=4500},
 {id='body-zone-health',target=base:damage_zone('body_front'),
  field=hd2.fields.zone.health,expect=450,value=4500},
}}})
