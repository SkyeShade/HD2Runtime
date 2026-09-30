"""Exercise every writable fire_rate.* / weapon_function.* / function_ammo.* / presentation.* field on a copy-on-write
overlay of the retained snapshot.

For each player and support weapon:

1. Rate-of-fire modes (three slots in weapon-menu order {X, Y, Z}): the reviewed rates apply as a guarded no-op;
   the default (Y) edited alone writes only its slot; a weapon without a selector fills X and Z together with its
   rate-of-fire binding (one transaction); every write reads back and rolls back exactly; a third-party slot value is
   a CONFLICT; a missing acknowledgement, a list that is not three slots, an empty default, a negative, non-finite or
   out-of-range rate, and rates without their selector are rejected.
2. Programmable ammunition: an addable host gains the ProgrammableAmmo binding and a donor projectile together (its
   package declared); native hosts swap and restore their own function projectile; a stale donor, a changed host,
   a beam donor and a missing reference acknowledgement are rejected.
3. Presentation: the reviewed traits and penetration label apply as no-ops; a changed label replaces, adds or
   removes exactly one tag slot and never touches the neighbouring LoadoutEntry record; unknown, duplicate and
   sixth traits are rejected; a stale LoadoutEntry index row is rejected.

It pins the exact bytes of the MG-206 edit, the Liberator added modes, the Speargun GL-52 and EMS Mortar modes (the
EMS donor's package, a stale turret record and its function-projectile-only scope) and the Liberator Concussive medium
label, checks that blocked weapons refuse writes, and that overlapping views (fire_rate.modes with
weapon.fire_rate, presentation.traits with presentation.armor_penetration) never share a plan.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources  # noqa: E402
import validate_attachment_authoring_snapshot as overlay_source  # noqa: E402

OUTPUT = ROOT / 'validation/weapon-modes-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/player_weapon_writes')
local players=require('hd2runtime/domains/player_weapon_authoring')
local supports=require('hd2runtime/domains/support_weapon_authoring')
local outputs=require('hd2runtime/domains/attack_outputs')
local RATES,LEFT,RIGHT,FUNCTION='fire_rate.modes','weapon_function.left','weapon_function.right','function_ammo.projectile'
local TRAITS,PENETRATION='presentation.traits','presentation.armor_penetration'
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function field_of(weapon,id)
 for _,item in ipairs(weapon.fields or{})do if item.semanticFieldId==id and item.editable then return item end end
end
local function handle(id)return setmetatable({resource='attack_output',output=id},{})end
local result={status='VALIDATED',rates={checked=0,edited=0,added=0,noops=0,liveProven={}},functions={checked=0,native=0},
 presentation={checked=0,replaced=0,added=0,removed=0,traits=0},rollbacks=0,conflictRejections=0,
 acknowledgementRejections=0,adversarialRejections=0,blockedRejections=0,neighbourChecks=0,weapons={},
 fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
-- Apply a spec, verify the exact bytes, then roll back and verify the originals. Returns the plan.
local function write_and_restore(spec,label,expect_parts)
 local plan=resolve(spec)
 local changed=0
 for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
 if expect_parts then assert(changed==expect_parts,label..' changed '..changed..' slots, expected '..expect_parts)end
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==changed and applied.non_target_bytes_unchanged,
  label..' write failed: '..tostring(applied.reason))
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,label..' write did not land')
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED',label..' rollback failed')
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,label..' rollback did not restore')
 end
 result.rollbacks=result.rollbacks+1
 return plan
end
local function noop(spec,label)
 local plan=resolve(spec)
 local checked=guarded.apply(runtime,plan)
 assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,label..' no-op changed state')
end
local function first_written(plan)
 for _,part in ipairs(plan.changes)do if part.before~=part.desired then return part end end
end
local worker=coroutine.create(function()
 for _,set in ipairs({{kind='player_weapon',db=players},{kind='support_weapon',db=supports}})do
  local names={};for name in pairs(set.db.weapons)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local weapon=set.db.weapons[name]
   if not weapon.ordinaryWritesBlocked then
    local target={resource=set.kind,path='weapon',weapon=name}
    local function patch(field,expect,value,extra)
     local request={id='weapon-mode-check',target=target,field=field,expect=expect,value=value,
      allow_unverified_effect=true}
     for key,item in pairs(extra or{})do request[key]=item end
     return domain.validate_patch(request)
    end
    local function transaction(changes,extra)
     local request={id='weapon-mode-check',target=target,changes=changes,allow_unverified_effect=true}
     for key,item in pairs(extra or{})do request[key]=item end
     return domain.validate_transaction(request)
    end
    local row={kind=set.kind,weapon=name}
    -- 1. Rate-of-fire modes.
    local rates=field_of(weapon,RATES)
    if rates then
     reset()
     local current=rates.currentDefault
     noop(patch(RATES,current,current),name..' rates')
     result.rates.noops=result.rates.noops+1
     local edited={current[1],current[2]+10,current[3]}   -- the default (Y) edited alone: only its slot is written
     local plan=write_and_restore(patch(RATES,current,edited),name..' rate edit',1)
     result.rates.edited=result.rates.edited+1
     poke(first_written(plan).owner.base+first_written(plan).offset,b.encode(1234.5,'f32'))
     rejects(function()resolve(patch(RATES,current,edited))end,'CONFLICT','rate conflict')
     result.conflictRejections=result.conflictRejections+1
     reset()
     if rates.acknowledgement=='allow_unverified_effect'then
      rejects(function()patch(RATES,current,edited,{allow_unverified_effect=false})end,'allow_unverified_effect',
       'rate acknowledgement')
      result.acknowledgementRejections=result.acknowledgementRejections+1
     else
      -- A live-proven pair (schemas/live_evidence.json) is written without the acknowledgement.
      assert(rates.liveEvidence,name..' rates need no acknowledgement but are not live-proven')
      patch(RATES,current,edited,{allow_unverified_effect=false})
      result.rates.liveProven[#result.rates.liveProven+1]=name
     end
     local y=current[2]
     for _,value in ipairs({{100,y,300,400},{y},{y,300},{current[1],0,current[3]},{current[1],-5,current[3]},
       {-5,y,current[3]},{current[1],y,1/0},{0/0,y,current[3]},{current[1],rates.max+1,current[3]},
       {current[1],y,rates.max+1}})do
      local ok=pcall(patch,RATES,current,value)
      assert(not ok,name..' accepted rates {'..table.concat(value,', ')..'}')
      result.adversarialRejections=result.adversarialRejections+1
     end
     if rates.maxModes==1 then
      rejects(function()patch(RATES,current,{y+100,y,0})end,'allows 1','second rate without a bindable selector')
      result.adversarialRejections=result.adversarialRejections+1
     end
     if rates.fireRateState=='addable'then
      local side=rates.bindableInputs[1]
      local added={y+200,y,y+100}                  -- X and Z filled; the default Y unchanged
      rejects(function()patch(RATES,current,added)end,'SELECTOR_REQUIRED','rates without a selector')
      rejects(function()patch('weapon_function.'..side,'none','rate_of_fire')end,'SELECTOR_REQUIRED','selector alone')
      result.adversarialRejections=result.adversarialRejections+2
      local spec=transaction({{field=RATES,expect=current,value=added},
       {field='weapon_function.'..side,expect='none',value='rate_of_fire'}})
      write_and_restore(spec,name..' added rates',3)   -- X and Z slots, and the binding; Y is unchanged
      result.rates.added=result.rates.added+1
     end
     result.rates.checked=result.rates.checked+1
     row.rates=rates.fireRateState
    end
    -- 2. Programmable ammunition.
    local projectile=field_of(weapon,FUNCTION)
    if projectile then
     reset()
     local donor=handle('output/v1/projectile/gl-52-de-escalator')
     local native=projectile.currentDefault.projectileType~=0
     local own=setmetatable({resource=set.kind,path='function_projectile',weapon=name},{})
     local expect=native and own or'none'
     local changes={{field=FUNCTION,expect=expect,value=donor}}
     if not native then changes[2]={field='weapon_function.'..projectile.bindableInputs[1],expect='none',
      value='programmable_ammo'} end
     local spec=transaction(changes,{allow_unverified_reference=true})
     assert(#spec.asset_dependencies>=0)
     local plan=write_and_restore(spec,name..' function projectile',native and 1 or 2)
     local wrote=false
     for _,part in ipairs(plan.changes)do if part.field_offset==576 then
      wrote=b.u32(part.desired,0)==outputs.outputs['output/v1/projectile/gl-52-de-escalator'].currentDefault
     end end
     assert(wrote,name..' did not write the donor projectile type')
     if native then
      noop(patch(FUNCTION,own,own),name..' native function projectile restore')
      result.functions.native=result.functions.native+1
     end
     rejects(function()transaction(changes)end,'allow_unverified_reference','function projectile reference ack')
     rejects(function()transaction({{field=FUNCTION,expect=expect,value=handle('output/v1/beam/las-98-laser-cannon')},
      changes[2]},{allow_unverified_reference=true})end,'INCOMPATIBLE_OUTPUT_FAMILY','beam donor')
     result.acknowledgementRejections=result.acknowledgementRejections+1
     result.adversarialRejections=result.adversarialRejections+1
     -- A changed host (it now spawns an entity) is refused.
     local host=plan.changes[1]
     for _,part in ipairs(plan.changes)do if part.field_offset==576 then host=part end end
     poke(host.owner.base+host.offset-576+40,b.encode(1,'u32'))
     rejects(function()resolve(spec)end,'FUNCTION_HOST_CHANGED','changed host')
     result.adversarialRejections=result.adversarialRejections+1
     reset()
     result.functions.checked=result.functions.checked+1
     row.functionAmmo=projectile.functionAmmoState
    end
    -- 3. Presentation.
    local penetration=field_of(weapon,PENETRATION)
    local traits=field_of(weapon,TRAITS)
    if penetration then
     reset()
     noop(patch(PENETRATION,penetration.currentDefault,penetration.currentDefault),name..' label')
     local value=penetration.currentDefault=='medium'and'heavy'or'medium'
     local plan=write_and_restore(patch(PENETRATION,penetration.currentDefault,value),name..' label change',nil)
     local changed=0
     for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
     assert(changed==1,name..' label change wrote '..changed..' slots')
     if penetration.currentDefault=='none'then result.presentation.added=result.presentation.added+1
     else
      result.presentation.replaced=result.presentation.replaced+1
      write_and_restore(patch(PENETRATION,penetration.currentDefault,'none'),name..' label removal',nil)
      result.presentation.removed=result.presentation.removed+1
     end
     -- The neighbouring LoadoutEntry record (the next 32 bytes) never changes.
     local last=plan.changes[#plan.changes]
     local after=last.owner.base+last.offset+4
     local neighbour=runtime.read(after,12)
     local again=resolve(patch(PENETRATION,penetration.currentDefault,value))
     assert(guarded.apply(runtime,again).status=='APPLIED')
     assert(runtime.read(after,12)==neighbour,name..' label write touched the next LoadoutEntry record')
     guarded.apply(runtime,guarded.inverse(again))
     result.neighbourChecks=result.neighbourChecks+1
     poke(plan.changes[1].owner.base+plan.changes[1].offset,b.encode(0x12345678,'u32'))
     rejects(function()resolve(patch(PENETRATION,penetration.currentDefault,value))end,'CONFLICT','label conflict')
     result.conflictRejections=result.conflictRejections+1
     reset()
     rejects(function()patch(PENETRATION,penetration.currentDefault,'super_penetrating')end,'native penetration labels',
      'unknown label')
     result.adversarialRejections=result.adversarialRejections+1
     result.presentation.checked=result.presentation.checked+1
     row.armorPenetration=penetration.currentDefault
    end
    if traits then
     reset()
     noop(patch(TRAITS,traits.currentDefault,traits.currentDefault),name..' traits')
     local value={'stun'}
     for index,id in ipairs(traits.currentDefault)do if index<4 and id~='stun'then value[#value+1]=id end end
     if table.concat(value,',')==table.concat(traits.currentDefault,',')then value={'heat'}end
     write_and_restore(patch(TRAITS,traits.currentDefault,value),name..' traits change',nil)
     rejects(function()patch(TRAITS,traits.currentDefault,{'stun','stun'})end,'twice','duplicate trait')
     rejects(function()patch(TRAITS,traits.currentDefault,{'bogus'})end,'unknown trait','unknown trait')
     rejects(function()patch(TRAITS,traits.currentDefault,{'stun','heat','beam','arc','melee','sticky'})end,
      'at most five','sixth trait')
     result.adversarialRejections=result.adversarialRejections+3
     if penetration then
      rejects(function()resolve(transaction({{field=TRAITS,expect=traits.currentDefault,value=value},
       {field=PENETRATION,expect=penetration.currentDefault,value='medium'}}))end,'overlapping semantic fields',
       'overlapping presentation views')
     end
     result.presentation.traits=result.presentation.traits+1
    end
    if row.rates or row.functionAmmo or row.armorPenetration then result.weapons[#result.weapons+1]=row end
   end
  end
 end
 reset()
 -- MG-206: its three native modes in weapon-menu order {X, Y, Z}, each edited independently.
 local hmg={resource='support_weapon',path='weapon',weapon='MG-206 Heavy Machine Gun'}
 local plan=resolve(domain.validate_patch({id='hmg-modes',target=hmg,field=RATES,expect={450,600,750},
  value={1400,200,700},allow_unverified_effect=true}))
 assert(#plan.changes==3,'MG-206 rates are not three slots')
 local bytes={}
 for index,part in ipairs(plan.changes)do
  assert(part.field_offset==4*index,'MG-206 rate slot offsets changed')
  bytes[index]=b.hex(part.before)..'>'..b.hex(part.desired)
 end
 assert(b.hex(plan.changes[1].desired)==b.hex(b.encode(1400,'f32'))and b.hex(plan.changes[2].desired)==
  b.hex(b.encode(200,'f32'))and b.hex(plan.changes[3].desired)==b.hex(b.encode(700,'f32')),'MG-206 slot mapping')
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==3 and applied.bytes_written==12 and applied.non_target_bytes_unchanged)
 result.hmg={slots=bytes,bytesWritten=applied.bytes_written,record=plan.changes[1].identity.record_index}
 reset()
 -- AR-23 Liberator: three selectable rates on its free left input.
 local liberator={resource='player_weapon',path='weapon',weapon='AR-23 Liberator'}
 plan=resolve(domain.validate_transaction({id='liberator-rates',target=liberator,allow_unverified_effect=true,changes={
  {field=RATES,expect={0,640,0},value={950,450,700}},{field=LEFT,expect='none',value='rate_of_fire'}}}))
 local written={}
 for _,part in ipairs(plan.changes)do
  if part.before~=part.desired then written[#written+1]=part.identity.component..'+'..part.field_offset..'='..b.hex(part.desired)end
 end
 table.sort(written)
 applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==4,'Liberator added rates write failed')
 result.liberator={written=written,bytesWritten=applied.bytes_written}
 reset()
 -- S-11 Speargun: a player-selectable stun projectile on its free left input.
 local spear={resource='support_weapon',path='weapon',weapon='S-11 Speargun'}
 local spec=domain.validate_transaction({id='speargun-stun',target=spear,allow_unverified_effect=true,
  allow_unverified_reference=true,changes={{field=LEFT,expect='none',value='programmable_ammo'},
  {field=FUNCTION,expect='none',value=handle('output/v1/projectile/gl-52-de-escalator')}}})
 plan=resolve(spec)
 written={}
 for _,part in ipairs(plan.changes)do
  if part.before~=part.desired then written[#written+1]=part.identity.component..'+'..part.field_offset..'='..b.hex(part.desired)end
 end
 table.sort(written)
 applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==2,'Speargun stun write failed')
 local dependency=spec.asset_dependencies[1]
 assert(dependency,'Speargun stun donor declares no asset dependency')
 local declared={}
 for key,item in pairs(dependency)do if type(item)=='string'or type(item)=='number'then declared[key]=item end end
 result.speargun={written=written,assetDependency=declared}
 reset()
 -- S-11 Speargun, stun-field mode: the A/M-23 EMS Mortar shell, a stratagem-owned donor whose expiry explosion leaves
 -- a StaticField (Stun Medium) volume. Its package is the turret's own loadout package; the turret record is re-proven.
 local ems_id='output/v1/projectile/a-m-23-ems-mortar-sentry'
 local ems=outputs.outputs[ems_id]
 assert(ems and ems.owner.kind=='stratagem'and ems.fieldEffect.volume=='StaticField','EMS donor not catalogued')
 local ems_spec=domain.validate_transaction({id='speargun-ems',target=spear,allow_unverified_effect=true,
  allow_unverified_reference=true,changes={{field=LEFT,expect='none',value='programmable_ammo'},
  {field=FUNCTION,expect='none',value=handle(ems_id)}}})
 plan=resolve(ems_spec)
 written={}
 for _,part in ipairs(plan.changes)do
  if part.before~=part.desired then written[#written+1]=part.identity.component..'+'..part.field_offset..'='..b.hex(part.desired)end
 end
 table.sort(written)
 applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==2,'Speargun EMS write failed')
 local ems_dependency=assert(ems_spec.asset_dependencies[1],'EMS donor declares no asset dependency')
 declared={}
 for key,item in pairs(ems_dependency)do if type(item)=='string'or type(item)=='number'then declared[key]=item end end
 result.speargunEms={written=written,assetDependency=declared,fieldEffect={volume=ems.fieldEffect.volume,
  seconds=ems.fieldEffect.seconds,radius=ems.fieldEffect.radius}}
 reset()
 -- A stale EMS turret record is refused.
 local ems_reader=Reader.new(runtime)
 local ems_resolved=domain.capture(runtime,ems_reader,ems_spec)
 local turret=ems_resolved.catalog.record(ems_resolved.reference_sources[FUNCTION],ems.backing.component)
 poke(turret.owner.base+turret.offset,b.encode(7,'u32'))
 rejects(function()resolve(ems_spec)end,'source projectile reference changed','stale EMS turret')
 result.adversarialRejections=result.adversarialRejections+1
 reset()
 -- The stratagem donor is catalogued for function_ammo.projectile only: projectile references refuse it.
 rejects(function()domain.validate_patch({id='ems-scope',target={resource='player_weapon',path='attack',
  weapon='SMG-32 Reprimand',attack='primary'},field='attack.projectile',allow_unverified_effect=true,
  allow_unverified_reference=true,expect=setmetatable({resource='player_weapon',path='projectile_reference',
  weapon='SMG-32 Reprimand',attack='primary'},{}),value=handle(ems_id)})end,'OUTPUT_SCOPE',
  'EMS donor on a projectile reference')
 result.adversarialRejections=result.adversarialRejections+1
 -- Mode presentation (domains/output_writes.lua): every selectable projectile output's weapon-function label and
 -- icon (ProjectileInfo +12, +16) apply as guarded no-ops, change exactly their own bytes, roll back, and refuse a
 -- third-party value, a missing shared acknowledgement, unknown and non-offered values and a stale owner.
 local presenter=require('hd2runtime/domains/output_writes')
 local function resolve_output(spec)
  local reader=Reader.new(runtime)
  local resolved=presenter.capture(runtime,reader,spec)
  local plan=presenter.prepare(resolved,reader,spec);reader.verify()
  return plan
 end
 result.presentation.outputs=0
 local ids={};for id,output in pairs(outputs.outputs)do if output.presentationFields then ids[#ids+1]=id end end
 table.sort(ids)
 local LABEL,ICON='presentation.mode_label','presentation.mode_icon'
 for _,id in ipairs(ids)do
  local output=outputs.outputs[id]
  local fields=output.presentationFields
  local target=setmetatable({resource='attack_output',output=id},{})
  local shared=fields[LABEL].shared
  local function spec_of(changes,extra)
   local request={id='mode-presentation',target=target,changes=changes,allow_unverified_effect=true,
    allow_shared=shared or nil}
   for key,item in pairs(extra or{})do if item==false then request[key]=nil else request[key]=item end end
   return presenter.validate_transaction(request)
  end
  local label,icon=fields[LABEL].currentDefault,fields[ICON].currentDefault
  reset()
  local noop_plan=resolve_output(spec_of({{field=LABEL,expect=label,value=label},{field=ICON,expect=icon,value=icon}}))
  local checked=guarded.apply(runtime,noop_plan)
  assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,id..' presentation no-op changed state')
  local new_label=label=='stun'and'gas'or'stun'
  local new_icon=icon=='ammo_stun'and'default'or'ammo_stun'
  local spec=spec_of({{field=LABEL,expect=label,value=new_label},{field=ICON,expect=icon,value=new_icon}})
  local plan=resolve_output(spec)
  assert(#plan.changes==3 and plan.changes[1].field_offset==12 and plan.changes[2].field_offset==16
   and plan.changes[3].field_offset==20,id..' presentation shape')
  local changed=0
  for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==changed and applied.bytes_written==changed*4
   and applied.non_target_bytes_unchanged,id..' presentation write failed: '..tostring(applied.reason))
  local restored=guarded.apply(runtime,guarded.inverse(plan))
  assert(restored.status=='APPLIED',id..' presentation rollback failed')
  for _,part in ipairs(plan.changes)do
   assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,id..' presentation rollback')
  end
  result.rollbacks=result.rollbacks+1
  poke(plan.changes[1].owner.base+plan.changes[1].offset,b.encode(0x12345678,'u32'))
  rejects(function()resolve_output(spec)end,'CONFLICT',id..' presentation conflict')
  result.conflictRejections=result.conflictRejections+1
  reset()
  if shared then
   rejects(function()spec_of({{field=LABEL,expect=label,value=new_label}},{allow_shared=false})end,'allow_shared',
    id..' shared presentation')
   result.acknowledgementRejections=result.acknowledgementRejections+1
  end
  rejects(function()spec_of({{field=LABEL,expect=label,value=new_label}},{allow_unverified_effect=false})end,
   'allow_unverified_effect',id..' presentation acknowledgement')
  rejects(function()spec_of({{field=LABEL,expect=label,value='bogus'}})end,'native mode label',id..' unknown label')
  local unoffered=label=='unnamed_e24deafa'and'he_2359c1bc'or'unnamed_e24deafa'
  rejects(function()spec_of({{field=LABEL,expect=label,value=unoffered}})end,'not an offered',
   id..' non-offered label')
  rejects(function()spec_of({{field=ICON,expect=icon,value='content/ui/custom'}})end,'native weapon-function icon',
   id..' custom icon')
  rejects(function()spec_of({{field=LABEL,expect='heat_mk2_x',value=new_label}})end,'expect differs',
   id..' stale expect')
  result.acknowledgementRejections=result.acknowledgementRejections+1
  result.adversarialRejections=result.adversarialRejections+4
  result.presentation.outputs=result.presentation.outputs+1
 end
 -- The owner no longer firing the reviewed projectile is refused (the S-11 Speargun spear).
 local spear_output=outputs.outputs['output/v1/projectile/s-11-speargun']
 local spear_spec=presenter.validate_patch({id='spear-label',target=setmetatable({resource='attack_output',
  output=spear_output.id},{}),field=LABEL,expect='none',value='gas',allow_unverified_effect=true})
 local owner_reader=Reader.new(runtime)
 local owner=presenter.capture(runtime,owner_reader,spear_spec)
 local owner_record=owner.catalog.record(owner.candidate,spear_output.backing.component)
 poke(owner_record.owner.base+owner_record.offset,b.encode(7,'u32'))
 rejects(function()resolve_output(spear_spec)end,'no longer fires','stale Speargun owner')
 result.adversarialRejections=result.adversarialRejections+1
 reset()
 -- Pins: the Speargun modes the live test labels (spear GAS, EMS shell STUN with the stun icon).
 local labels={}
 -- GAS has no native icon: "auto" resolves to the generic fallback; STUN names its native stun icon explicitly.
 for _,item in ipairs({{spear_output.id,'gas','auto'},{'output/v1/projectile/a-m-23-ems-mortar-sentry','stun',
   'ammo_stun'}})do
  local pinned=resolve_output(presenter.validate_transaction({id='pin',target=setmetatable({resource='attack_output',
   output=item[1]},{}),allow_unverified_effect=true,changes={{field=LABEL,expect='none',value=item[2]},
   {field=ICON,expect='default',value=item[3]}}}))
  labels[item[1]]={label=b.hex(pinned.changes[1].desired),
   icon=b.hex(pinned.changes[2].desired)..b.hex(pinned.changes[3].desired),iconValue=pinned.changes[2].value,
   row=pinned.changes[1].identity.record_index}
 end
 result.modePresentation=labels
 -- A stale donor source is refused.
 local donor=outputs.outputs['output/v1/projectile/gl-52-de-escalator']
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local source_record=resolved.catalog.record(resolved.reference_sources[FUNCTION],donor.backing.component)
 poke(source_record.owner.base+source_record.offset,b.encode(7,'u32'))
 rejects(function()resolve(spec)end,'source projectile reference changed','stale donor')
 result.adversarialRejections=result.adversarialRejections+1
 reset()
 -- AR-23C Liberator Concussive: MEDIUM ARMOR PENETRATING in place of LIGHT, nothing else.
 local concussive={resource='player_weapon',path='weapon',weapon='AR-23C Liberator Concussive'}
 local label=domain.validate_patch({id='concussive-label',target=concussive,field=PENETRATION,expect='light',
  value='medium',allow_unverified_effect=true})
 plan=resolve(label)
 written={}
 for _,part in ipairs(plan.changes)do
  if part.before~=part.desired then written[#written+1]={offset=part.field_offset,before=b.hex(part.before),
   after=b.hex(part.desired)}end
 end
 assert(#written==1 and written[1].offset==12 and written[1].before=='1541ef11'and written[1].after=='47c0e2b7',
  'Concussive label bytes differ')
 applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.bytes_written==4)
 result.concussive={written=written,record=plan.changes[1].identity.record_index}
 reset()
 -- A stale LoadoutEntry index row (the record it names changed) is refused.
 reader=Reader.new(runtime)
 resolved=domain.capture(runtime,reader,label)
 local identity=resolved.candidate.ownership.LoadoutEntryComponentData
 local component=profile.components.LoadoutEntryComponentData
 local catalog_record=resolved.catalog.record(resolved.candidate,'LoadoutEntryComponentData')
 local index_row=catalog_record.owner.base+component.offset+28+identity.indexRow*16
 poke(index_row+8,b.encode(identity.recordIndex==0 and 1 or identity.recordIndex-1,'u32'))
 rejects(function()resolve(label)end,'ownership identity changed','stale LoadoutEntry index')
 result.adversarialRejections=result.adversarialRejections+1
 reset()
 -- Blocked weapons never accept these writes.
 for _,item in ipairs({{'player_weapon','SG-20 Halt',RATES,{0,80,0},{0,90,0}},{'player_weapon','VG-70 Variable',
   RATES,{300,550,750},{0,550,0}},{'support_weapon','M-1000 Maxigun',RATES,{0,1500,0},{0,1400,0}},
   {'player_weapon','AR-61 Tenderizer',LEFT,'rate_of_fire','none'},{'player_weapon','SG-20 Halt',PENETRATION,'light',
   'heavy'},{'player_weapon','LAS-5 Scythe',FUNCTION,'none','none'}})do
  local ok=pcall(domain.validate_patch,{id='blocked',target={resource=item[1],path='weapon',weapon=item[2]},
   field=item[3],expect=item[4],value=item[5],allow_unverified_effect=true})
  assert(not ok,item[2]..' accepted '..item[3])
  result.blockedRejections=result.blockedRejections+1
 end
 -- The older fire-rate view overlaps the default slot and never shares a plan with the mode list.
 rejects(function()resolve(domain.validate_transaction({id='overlap',target=liberator,allow_unverified_effect=true,
   changes={{field=RATES,expect={0,640,0},value={0,700,0}},{field='weapon.fire_rate',expect=640,value=700}}}))end,
   'overlapping semantic fields','overlapping fire-rate views')
 result.overlapRejected=true
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def validate(snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\n' + PROGRAM)
    return json.loads(execute(program.encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'weapons'}, indent=2))


if __name__ == '__main__':
    main()
