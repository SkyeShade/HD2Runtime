local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the Resupply stratagem as an hd2.stratagem target. It uses two rows on the MODS tab (Mod Options
-- Menu); changes take effect when you press APPLY.
-- * Resupply cooldown: Vanilla (180 s) or 5 s. This is StratagemDefinition +104 of the only AmmoRack row
--   (research/resupply-F5FEE03DCFDB.json).
-- * Resupply payload: Vanilla supply boxes or grenade boxes, set in the four spawned slots of the Resupply drop pod.
--   The Grenade Box has its own package; Runtime loads it before it writes a slot that references it. This donor
--   is live-proven in the MG-43 pod (AssetTestMg43PodGrenadeBox), not yet in this pod.
-- The log shows each step: the options applied, the donor package loading, then an "APPLIED" line per operation.
-- When a Resupply pod lands, the test logs it (the pod rack entity has health, so entity_spawned sees it).
-- The Resupply rack is shared with the reward variant of Resupply (allow_shared).
local mod=hd2.mod()
local resupply=hd2.stratagem('Resupply')
local rack=resupply:delivery():rack()
local supply=rack:slot(1):current()
local grenades=hd2.pickup('Grenade Box')

local options=hd2.options({id='resupply_test',title='Resupply Test'})
local cooldown=options:choice({id='cooldown',label='Resupply cooldown',choices={'Vanilla (180 s)','5 s'},
    values={180,5},default=2,description='Time before Resupply can be called again.'})
local payload=options:choice({id='payload',label='Resupply payload',choices={'Vanilla supply boxes','Grenade boxes'},
    values={supply,grenades},default=2,
    description='What the four spawned slots of the Resupply pod hold. Grenade boxes load their own package first.'})

local operations={}
operations[1]=hd2.ensure({patch={id='resupply-cooldown',target=resupply,
    field=hd2.fields.stratagem.definition_cooldown,expect=180,value=cooldown}})
local slots={}
for number=1,4 do
    slots[number]={id='slot-'..number,target=rack:slot(number),field=hd2.fields.payload.entity,
        expect=supply,value=payload,allow_unverified_reference=true,allow_shared=true}
end
operations[2]=hd2.ensure({plan={id='resupply-payload',operations=slots}})

local RACK='entity/v1/helldivers/ammo_rack'
assert(hd2.entities.describe(RACK),'unknown entity id '..RACK)
hd2.events.on('entity_spawned',function(event)
    if event.semantic_id~=RACK then return end
    mod:log('Resupply pod landed (entity '..tostring(event.entity_id)..'): expect '
        ..(payload:index()==2 and'four grenade boxes'or'four supply boxes')..'; pick one up to check it works')
end,{id='resupply_pod'})
hd2.events.on('mission_started',function()
    mod:log('mission started: Resupply cooldown '..tostring(cooldown:get())..' s, payload '
        ..(payload:index()==2 and'grenade boxes'or'supply boxes'))
end,{id='mission'})

mod:log('loaded: call Resupply; the cooldown and pod contents follow the Resupply Test options')
return operations
