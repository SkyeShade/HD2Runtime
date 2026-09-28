local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the Surplus EAT Allocation pod opens with two Resupply supply boxes instead of two EATs.
-- The Supply Box is the one pickup proven resident in every mission (Resupply is always available), so
-- this test does not depend on another stratagem's package being loaded.
-- The EAT pod is shared: the EAT-17 call-in uses the same rack, so its pods change too (allow_shared).
local rack=hd2.booster('Surplus EAT Allocation'):granted_stratagem():delivery():rack()
local eat=rack:slot(1):current()
local supply=hd2.pickup('Supply Box')
local operations={}
for number=1,2 do
    operations[number]={id='slot-'..number,target=rack:slot(number),field=hd2.fields.payload.entity,
        expect=eat,value=supply,allow_unverified_reference=true,allow_shared=true}
end
return hd2.ensure({plan={id='surplus-eat-pod-swap',operations=operations}})
