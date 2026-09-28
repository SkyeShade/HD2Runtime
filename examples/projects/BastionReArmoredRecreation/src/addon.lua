local hd2=require('mods/skyeshade/hd2runtime')
local LUNCH_BOX={zone_3=true,zone_4=true}
local function vehicle_operations(name,prefix)
 local vehicle=hd2.vehicle(name)
 local operations={{id=prefix..'-main',target=vehicle,changes={
  {field=hd2.fields.entity.health,expect=8000,value=16000},
  {field=hd2.fields.entity.armor,expect=4,value=5}}}}
 for _,zone in ipairs(vehicle:damage_zones())do
  local changes={}
  for _,field in ipairs(zone:describe().fields)do
   if field.semanticFieldId=='zone.armor'and field.currentDefault==4 then
    changes[#changes+1]={field=hd2.fields.zone.armor,expect=4,value=5}
   elseif field.semanticFieldId=='zone.affects_main_health'and LUNCH_BOX[zone.zone]then
    changes[#changes+1]={field=hd2.fields.zone.affects_main_health,expect=1,value=0}
   end
  end
  if #changes>0 then operations[#operations+1]={id=prefix..'-'..zone.zone,target=zone,changes=changes}end
 end
 return operations
end
return hd2.ensure({plan={id='bastion-rearmored-recreation',phases={
 {id='bastion',operations=vehicle_operations('TD-220 Bastion MK XVI','bastion')},
 {id='maelstrom',operations=vehicle_operations('TD-110 Maelstrom','maelstrom')},
}}})
