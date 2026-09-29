local hd2=require('mods/skyeshade/hd2runtime')
-- Live test C: the M-102 Gunner FRV's gun becomes the TD-220 Bastion's tank cannon. The cannon lives in the
-- Bastion's package, which is only loaded when someone brings the Bastion.
local gun=hd2.vehicle('M-102 Gunner FRV'):mount('slot_0')
local cannon=hd2.vehicle('TD-220 Bastion MK XVI'):mount('slot_0'):current()
return hd2.ensure({patch={id='asset-test-frv-bastion-cannon',target=gun,field=hd2.fields.mount.weapon,
    expect=gun:current(),value=gun:candidate(cannon.semanticId),allow_unverified_reference=true}})
