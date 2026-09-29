local hd2=require('mods/skyeshade/hd2runtime')
-- Charger head armor 4 -> 1. The head is native zone_0 ('head'), identified by its native name and the wiki anatomy
-- (1200 health, armor 4, 70% to main). Zone armor is the member vehicle zones already use. New Chargers only.
local head=hd2.enemy('Charger'):zone('Head')
return hd2.ensure({patch={id='enemy-armor-zone-test',target=head,field=hd2.fields.zone.armor,expect=4,value=1}})
