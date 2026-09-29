local hd2=require('mods/skyeshade/hd2runtime')
-- Charger: main health 2400 -> 240. HealthComponent +0 is the gameplay-proven main health member (the same member
-- vehicles and the Shield Relay use); the Charger identity is a hash-verified native class whose 17 damage zones
-- match the wiki anatomy exactly. Applies to Chargers spawned after the write.
local charger=hd2.enemy('Charger')
return hd2.ensure({patch={id='enemy-health-test',target=charger,field=hd2.fields.entity.health,expect=2400,value=240}})
