local hd2=require('mods/skyeshade/hd2runtime')
local gater=hd2.vehicle('GATER Oil Rig'):mount('turret'):current()
local function swap(id,vehicle)
 local gun=hd2.vehicle(vehicle):mount('gun')
 return {id=id,target=gun,allow_unverified_reference=true,
  field=hd2.fields.mount.weapon,expect=gun:current(),value=gun:candidate(gater.semanticId)}
end
return hd2.ensure({plan={id='frv-weapon-swap-recreation',operations={
 swap('frv','M-102 Gunner FRV'),
 swap('frv-super-earth','FRV (Super Earth variant)'),
}}})
