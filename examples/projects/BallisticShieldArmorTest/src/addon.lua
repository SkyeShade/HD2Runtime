local hd2=require('mods/skyeshade/hd2runtime')
-- SH-20 Ballistic Shield plate armor 4 -> 5 (docs/backpack-authoring.md). Every hit on the shield resolves to damage
-- zone 0 "shield"; with its armor at 5, AP 4 weapons (MG-206 HMG, APW-1 Anti-Materiel Rifle) deal no damage while AP 5
-- (RS-422 Railgun) still does. Armor is copied into a shield when it spawns: test on a newly called-in SH-20.
local plate=hd2.backpack('SH-20 Ballistic Shield Backpack'):damage_zone('shield')
return hd2.ensure({patch={id='ballistic-shield-plate-armor',target=plate,allow_unverified_effect=true,
    field=hd2.fields.zone.armor,expect=4,value=5}})
