"""Exercise the projectile builder and the unified projectile donor pool through the production write domains on the
retained snapshot (research/projectile-builder-F5FEE03DCFDB.json).

On a copy-on-write memory overlay of the snapshot (no game process, no real writes). Byte round trips prove the guarded
write mechanics only; the gameplay effect of every composition here is pending a live test.

- Speargun builder (SpeargunProjectileBuilderTest): weapon:programmable_ammo():operations() on the S-11 Speargun with
  the spare twin as base and the EMS Mortar shell's expiry explosion. Every request is applied in order and rolled back
  in reverse; the spare twin row changes only in its presentation and expiry explosion, the Speargun's own row only in
  its presentation, and the twin match holds before and after.
- Impact vs expiry audit: which slots each family's showcase row has (direct hit, impact, expiry, submunition,
  lingering field), from the live rows.
- Unified donor pool: support hosts <- primary donors and support donors, a primary host <- a support donor handle,
  the Liberator's ammunition <- Talon; each write lands in the host's own fired member and rolls back exactly.
- HMG special ammunition: the HMG programmable mode on a donor bullet and the donor-row label.
- Adversarial: stale donor, stale slot donor, spare twin changed, dormant source, incompatible families, shared row
  without allow_shared, removing the direct hit, cross slot types, a slot the donor lacks, the wrong expect, a missing
  package, recursion (direct and two-step), stale handles, a non-host support weapon.
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

OUTPUT = ROOT / 'validation/projectile-builder-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local hd2=require('hd2runtime/api/hd2')
local domains=require('hd2runtime/domains/write_domains')
local outputs=require('hd2runtime/domains/attack_outputs')
local function stage(request)
 local domain=domains.for_resource(request.target.resource)
 local spec=domain.validate_transaction(request)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,spec,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 return needle
end
local function live(owner,offset,width)return runtime.read(owner.base+offset,width)end
local function u32(owner,offset)return b.u32(live(owner,offset,4),0)end
local function diff_ranges(a,c)
 local ranges={}
 for index=1,#a do
  if a:sub(index,index)~=c:sub(index,index)then
   local last=ranges[#ranges]
   if last and last[2]==index-1 then last[2]=index else ranges[#ranges+1]={index-1,index}end
  end
 end
 return ranges
end
local function within(ranges,allowed)
 for _,range in ipairs(ranges)do
  local ok=false
  for _,item in ipairs(allowed)do if range[1]>=item[1]and range[2]<=item[2]then ok=true end end
  if not ok then return false end
 end
 return true
end
local function slot(name,field)return outputs.outputs[outputs.aliases[name]].slotFields[field].currentDefault end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 proofScope='guarded write mechanics; every composition here is pending a live test',
 speargun={},audit={},unified={},hmg={},rejections={}}
local worker=coroutine.create(function()
 -- Speargun builder: spare twin base, EMS expiry explosion, STUN label; GAS on the weapon's own mode.
 local spear=hd2.support_weapon('S-11 Speargun')
 local builder=spear:programmable_ammo()
 local twin=hd2.attack_output('S-11 Speargun (spare twin)')
 local ems=hd2.attack_output('A/M-23 EMS Mortar Sentry')
 local requests=builder:operations({id='spear-stun',base=twin,expiry_explosion=ems:expiry_explosion(),label='stun',
  allow_unverified_effect=true,allow_unverified_reference=true})
 for _,request in ipairs(builder:presentation({id='spear-gas',primary_label='gas',allow_unverified_effect=true}))do
  requests[#requests+1]=request
 end
 -- The builder never acknowledges on the author's behalf: without them the mode is refused.
 -- (An unproven base: the spare twin itself is live-proven on the Speargun and needs none.)
 local bare=builder:operations({id='bare',base=hd2.attack_output('AR-2 Coyote'),label='stun'})
 assert(bare[1].transaction.allow_unverified_effect==nil and bare[1].transaction.allow_unverified_reference==nil,
  'the builder added an acknowledgement')
 result.rejections.builderWithoutAcknowledgement=rejects(function()stage(bare[1].transaction)end,
  'allow_unverified','builder without acknowledgements')
 assert(#requests==4,'the Speargun builder no longer makes four requests')
 local spare=outputs.outputs[outputs.aliases['S-11 Speargun (spare twin)']]
 local own=outputs.outputs[outputs.aliases['S-11 Speargun']]
 local spare_type,own_type=spare.currentDefault,own.currentDefault
 local ems_expiry=slot('A/M-23 EMS Mortar Sentry','projectile.expiry_explosion')
 local _,_,probe=stage(requests[2].transaction)
 local root=probe.roots.projectile
 local spare_row,own_row=root.records[spare_type],root.records[own_type]
 local spare_before=live(root.owner,spare_row.offset,#spare_row.bytes)
 local own_before=live(root.owner,own_row.offset,#own_row.bytes)
 local twin_expiry=b.u32(spare_before,156)
 local plans={}
 for index,request in ipairs(requests)do
  local plan,spec=stage(request.transaction)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.non_target_bytes_unchanged,request.transaction.id..' failed: '
   ..tostring(applied.status))
  plans[index]=plan
  result.speargun[request.transaction.id]={writes=applied.writes,changes=#spec.changes,
   packages=spec.asset_dependencies and#spec.asset_dependencies or 0}
 end
 local spare_after=live(root.owner,spare_row.offset,#spare_row.bytes)
 local own_after=live(root.owner,own_row.offset,#own_row.bytes)
 assert(b.u32(spare_after,156)==ems_expiry,'the spare twin expiry is not the EMS explosion')
 assert(within(diff_ranges(spare_before,spare_after),{{12,24},{156,160}}),
  'the spare twin changed outside its presentation and expiry explosion')
 assert(within(diff_ranges(own_before,own_after),{{12,24}}),'the Speargun row changed outside its presentation')
 assert(b.u32(own_after,156)==b.u32(own_before,156),'the Speargun gas expiry moved')
 for index=#plans,1,-1 do
  assert(guarded.apply(runtime,guarded.inverse(plans[index])).status=='APPLIED','Speargun rollback '..index..' failed')
 end
 assert(live(root.owner,spare_row.offset,#spare_row.bytes)==spare_before
  and live(root.owner,own_row.offset,#own_row.bytes)==own_before,'Speargun rollback did not restore both rows')
 result.speargun.rows={spareTwinOf='S-11 Speargun',spareExpiry={from=twin_expiry,to=ems_expiry},
  gasExpiryUnchanged=true,changedMembers={spare={'presentation','expiry_explosion'},own={'presentation'}}}
 reset()

 -- Impact vs expiry audit from the live rows: direct hit, impact, expiry, and what each explosion releases.
 local explosions=probe.roots.explosion
 for _,name in ipairs({'S-11 Speargun','A/M-23 EMS Mortar Sentry','GL-21 Grenade Launcher','EAT-700 Expendable Napalm',
   'R-36 Eruptor','CB-9 Exploding Crossbow','AR-2 Coyote'})do
  local output=outputs.outputs[outputs.aliases[name]]
  local row=root.records[output.currentDefault]
  local function explosion(offset)
   local value=b.u32(row.bytes,offset)
   if value==0 then return nil end
   local e=explosions.records[value]
   return {submunition=b.u32(e.bytes,84)~=0,lingeringField=b.u32(e.bytes,100)~=0,arc=b.u32(e.bytes,120)~=0}
  end
  result.audit[name]={directHit=b.u32(row.bytes,60)~=0,impact=explosion(144),expiry=explosion(156)}
 end
 assert(result.audit['S-11 Speargun'].impact==nil and result.audit['S-11 Speargun'].expiry.lingeringField,
  'the Speargun gas is no longer an expiry field')

 -- Unified donor pool: each write lands in the host's own fired member.
 local function host_swap(label,weapon,value,extra)
  local source=weapon:projectile_source()
  assert(source.writable,label..' host is not writable')
  local request={id='u',target=source.target,changes={{field=source.field,expect=source.expect,value=value}}}
  for key,flag in pairs(extra or{})do request[key]=flag end
  local plan,spec,resolved=stage(request)
  local part=plan.changes[1]
  local before=live(part.owner,part.offset,4)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,label..' failed')
  local member='ammunition delta'
  if source.field=='attack.projectile'then
   local base=resolved.catalog.record(resolved.candidate,'ProjectileWeaponComponentData')
   assert(part.owner.base+part.offset==base.owner.base+base.offset,label..' did not write the host ProjectileWeapon +0')
   member='ProjectileWeapon +0'
  end
  local written=u32(part.owner,part.offset)
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED'and live(part.owner,part.offset,4)==before,
   label..' rollback failed')
  reset()
  result.unified[label]={host=source.weapon,member=member,from=b.u32(before,0),to=written,
   crossClass=spec.changes[1].cross_class==true,packages=#spec.asset_dependencies}
  return written
 end
 local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
 assert(host_swap('support <- primary handle',eat,hd2.weapon('PLAS-1 Scorcher'):attack('primary'):projectile(),
  {allow_unverified_effect=true})==outputs.outputs[outputs.aliases['PLAS-1 Scorcher']].currentDefault)
 host_swap('support <- primary output (cross class)',eat,hd2.attack_output('AR-2 Coyote'),
  {allow_unverified_effect=true,allow_unverified_reference=true})
 host_swap('support <- support handle',hd2.support_weapon('MG-206 Heavy Machine Gun'),
  hd2.support_weapon('M-105 Stalwart'):attack('primary'):projectile(),{allow_unverified_effect=true})
 host_swap('primary <- support handle',hd2.weapon('SMG-32 Reprimand'),
  hd2.support_weapon('EAT-700 Expendable Napalm'):attack('primary'):projectile(),
  {allow_unverified_effect=true,allow_unverified_reference=true})
 host_swap('Liberator ammunition <- Talon',hd2.weapon('AR-23 Liberator'),hd2.attack_output('LAS-58 Talon'),
  {allow_shared=true})
 -- Mounted hosts: the Patriot minigun's own ProjectileWeapon +0 (mount chain re-proven), same pool.
 local patriot=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun')
 host_swap('mounted <- support output (cross class)',patriot,hd2.attack_output('EAT-17 Expendable Anti-Tank'),
  {allow_unverified_effect=true,allow_unverified_reference=true})
 host_swap('mounted <- primary handle',patriot,hd2.weapon('LAS-58 Talon'):attack('primary'):projectile(),
  {allow_unverified_effect=true})
 host_swap('mounted <- mounted handle',patriot,hd2.vehicle('EXO-49 Emancipator Exosuit'):weapon('left_gun'):attack('primary'),
  {allow_unverified_effect=true,allow_unverified_reference=true})
 host_swap('primary <- mounted handle',hd2.weapon('SMG-32 Reprimand'),patriot:attack('primary'),{})
 host_swap('shared mounted entity (both FRVs)',hd2.vehicle('M-102 Gunner FRV'):weapon('gun'),
  hd2.attack_output('R-4 Hyena'),{allow_shared=true,allow_unverified_effect=true})
 local restore=eat:projectile_source()
 local plan=stage({id='r',target=restore.target,changes={{field=restore.field,expect=restore.expect,value=restore.expect}}})
 assert(plan.changes[1].already_desired,'restoring the EAT-17 projectile is not the baseline')
 result.unified.restoreIsBaseline=true

 -- HMG special ammunition: the programmable mode on a donor bullet and that donor row's label.
 local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun'):programmable_ammo()
 for _,request in ipairs(hmg:operations({id='hmg',base=hd2.attack_output('R-4 Hyena'),label='incendiary',
   allow_unverified_effect=true,allow_unverified_reference=true}))do
  local plan,spec=stage(request.transaction)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.non_target_bytes_unchanged,request.transaction.id..' failed')
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',request.transaction.id..' rollback failed')
  result.hmg[request.transaction.id]={writes=applied.writes,packages=#(spec.asset_dependencies or{})}
 end
 reset()

 -- Adversarial.
 local slots=requests[2].transaction
 local mode=requests[1].transaction
 local function poke_row(type_,offset,value)
  local row=root.records[type_];poke(root.owner.base+row.offset+offset,b.encode(value,'u32'))
 end
 -- A stale slot donor: the EMS row no longer holds its reviewed expiry explosion.
 poke_row(outputs.outputs[outputs.aliases['A/M-23 EMS Mortar Sentry']].currentDefault,156,twin_expiry)
 result.rejections.staleSlotDonor=rejects(function()stage(slots)end,'CONFLICT','stale slot donor');reset()
 -- The spare twin no longer matches its twin (its velocity changed): both the slot and the mode refuse it.
 local velocity=b.u32(spare_before,32)
 poke_row(spare_type,32,velocity+1)
 result.rejections.spareTwinChanged=rejects(function()stage(slots)end,'SPARE_TWIN_CHANGED','spare twin slot')
 rejects(function()stage(mode)end,'SPARE_TWIN_CHANGED','spare twin mode');reset()
 -- Another game build: the spare twin is proven unreferenced only on the build it was researched on.
 local build=spare.spare.researchedBuild
 spare.spare.researchedBuild='0000000000000000000000000000000000000000000000000000000000000000'
 result.rejections.spareTwinOtherBuild=rejects(function()stage(slots)end,'SPARE_TWIN_UNVERIFIED_BUILD',
  'spare twin slot on another build')
 rejects(function()stage(mode)end,'SPARE_TWIN_UNVERIFIED_BUILD','spare twin mode on another build')
 spare.spare.researchedBuild=build
 -- A stale donor output: the Coyote no longer fires its catalogued projectile.
 local coyote={id='c',target=eat:projectile_source().target,allow_unverified_effect=true,allow_unverified_reference=true,
  changes={{field='attack.projectile',expect=eat:projectile_source().expect,value=hd2.attack_output('AR-2 Coyote')}}}
 local _,coyote_spec,coyote_resolved=stage(coyote)
 local donor=coyote_resolved.catalog.record(coyote_resolved.reference_sources[coyote_spec.changes[1].canonical_field],
  'ProjectileWeaponComponentData')
 poke(donor.owner.base+donor.offset,b.encode(276,'u32'))
 result.rejections.staleDonor=rejects(function()stage(coyote)end,'source projectile reference changed','stale donor')
 reset()
 -- The dormant Liberator member.
 local liberator=hd2.weapon('AR-23 Liberator'):attack('primary')
 result.rejections.dormantSource=rejects(function()stage({id='d',target=liberator,allow_unverified_effect=true,
  allow_unverified_reference=true,changes={{field='attack.projectile',expect=liberator:projectile(),
  value=hd2.attack_output('LAS-58 Talon')}}})end,'DORMANT_PROJECTILE_REFERENCE','dormant source')
 -- Families a projectile host cannot reference.
 for _,name in ipairs({'LAS-98 Laser Cannon','ARC-3 Arc Thrower','FLAM-40 Flamethrower','CQC-2 Saber'})do
  rejects(function()stage({id='f',target=eat:projectile_source().target,allow_unverified_effect=true,
   allow_unverified_reference=true,changes={{field='attack.projectile',expect=eat:projectile_source().expect,
   value=hd2.attack_output(name)}}})end,'INCOMPATIBLE_OUTPUT_FAMILY',name)
 end
 result.rejections.incompatibleFamilies=4
 -- A shared row: the HMG bullet (15 consumers) needs allow_shared for a slot write; with it, it applies.
 local hmg_output=hd2.attack_output('MG-206 Heavy Machine Gun')
 local shared={id='s',target=hmg_output,allow_unverified_effect=true,changes={{field='projectile.direct_damage',
  expect=hmg_output:direct_damage(),value=hd2.attack_output('AR-2 Coyote'):direct_damage()}}}
 result.rejections.sharedRow=rejects(function()stage(shared)end,'allow_shared','shared row')
 shared.allow_shared=true
 local plan=stage(shared)
 assert(#plan.changes==1 and not plan.changes[1].already_desired,'the shared HMG slot write did not resolve')
 local hmg_slot=outputs.outputs[outputs.aliases['MG-206 Heavy Machine Gun']].slotFields['projectile.direct_damage']
 result.sharedWithAcknowledgement={entities=#hmg_slot.sharedConsumers,references=hmg_slot.consumerReferences}
 -- Removing the direct hit; an explosion handle in the damage slot; a slot the donor lacks; the wrong expect.
 local function spare_slot(field,expect,value)
  return {id='x',target=twin,allow_unverified_effect=true,changes={{field=field,expect=expect,value=value}}}
 end
 result.rejections.removeDirectHit=rejects(function()stage(spare_slot('projectile.direct_damage',twin:direct_damage(),
  'none'))end,'cannot be removed','direct hit none')
 result.rejections.crossSlotType=rejects(function()stage(spare_slot('projectile.direct_damage',twin:direct_damage(),
  ems:expiry_explosion()))end,'a damage slot takes','cross slot type')
 result.rejections.donorLacksSlot=rejects(function()stage(spare_slot('projectile.expiry_explosion',
  twin:expiry_explosion(),hd2.attack_output('S-11 Speargun'):impact_explosion()))end,'has no impactExplosion',
  'donor lacks slot')
 result.rejections.wrongExpect=rejects(function()stage(spare_slot('projectile.expiry_explosion',ems:expiry_explosion(),
  ems:expiry_explosion()))end,'expect must be this output','wrong expect')
 -- The spare twin's own expiry is already desired (no write).
 assert(stage(spare_slot('projectile.expiry_explosion',twin:expiry_explosion(),twin:expiry_explosion()))
  .changes[1].already_desired,'the spare twin own expiry is not a no-op')
 -- A donor without a catalogued package.
 local assets=require('hd2runtime/core/assets')
 local original=assets.dependency
 assets.dependency=function(key)if key:find('EMS Mortar',1,true)then return nil end return original(key)end
 local ok,why=pcall(stage,slots)
 assets.dependency=original
 assert(not ok and tostring(why):find('ASSET_UNAVAILABLE',1,true),'missing package not refused: '..tostring(why))
 result.rejections.missingPackage='ASSET_UNAVAILABLE'
 -- Recursion: the EMS explosion releasing the spare twin itself, directly and through a second projectile.
 local ems_type=outputs.outputs[outputs.aliases['A/M-23 EMS Mortar Sentry']].currentDefault
 local ems_impact=slot('A/M-23 EMS Mortar Sentry','projectile.impact_explosion')
 local function poke_explosion(type_,offset,value)
  local row=explosions.records[type_];poke(explosions.owner.base+row.offset+offset,b.encode(value,'u32'))
 end
 poke_explosion(ems_expiry,84,spare_type)
 result.rejections.recursionDirect=rejects(function()stage(slots)end,'RECURSIVE_COMPOSITION','direct recursion');reset()
 poke_explosion(ems_expiry,84,ems_type);poke_explosion(ems_impact,84,spare_type)
 result.rejections.recursionTwoStep=rejects(function()stage(slots)end,'RECURSIVE_COMPOSITION','two-step recursion')
 reset()
 -- A native submunition chain is followed without a false positive (the EAT-700 impact releases its shrapnel).
 local napalm=stage(spare_slot('projectile.impact_explosion','none',
  hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion()))
 assert(#napalm.changes==1,'a native submunition chain was refused')
 result.submunitionChainAccepted='EAT-700 Expendable Napalm impact explosion'
 -- Stale handles.
 result.rejections.unknownOutput=rejects(function()stage(spare_slot('projectile.expiry_explosion',twin:expiry_explosion(),
  {resource='attack_output_slot',output='output/v1/projectile/not-a-row',slot='expiryExplosion'}))end,
  'unknown attack output','unknown output')
 result.rejections.unknownSlot=rejects(function()stage(spare_slot('projectile.expiry_explosion',twin:expiry_explosion(),
  {resource='attack_output_slot',output=spare.id,slot='delayedExplosion'}))end,'must be "none"','unknown slot')
 result.rejections.beamHasNoSlots=rejects(function()hd2.attack_output('LAS-98 Laser Cannon'):expiry_explosion()end,
  'has no projectile slots','beam slot handle')
 result.rejections.stale_identity=rejects(function()stage(spare_slot('projectile.expiry_explosion',twin:expiry_explosion(),
  {resource='attack_output_slot',output=spare.id,slot='expiryExplosion',row=300}))end,'unsupported identity',
  'extra handle identity')
 -- Mounted: a stale mount chain (the Patriot no longer mounts the reviewed minigun) and the rocket pod (not a host).
 local psource=patriot:projectile_source()
 local mounted={id='m',target=psource.target,allow_unverified_effect=true,allow_unverified_reference=true,
  changes={{field='attack.projectile',expect=psource.expect,value=hd2.attack_output('EAT-17 Expendable Anti-Tank')}}}
 local _,mspec,mresolved=stage(mounted)
 local vehicle_candidate
 for _,candidate in ipairs(mresolved.catalog.candidates)do
  if candidate.resourceHash==hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun'):describe().name and false then end
 end
 local chain=require('hd2runtime/domains/vehicle_weapon_authoring').weapons['EXO-45 Patriot Exosuit / right_gun'].mountChain
 for _,candidate in ipairs(mresolved.catalog.candidates)do if candidate.resourceHash==chain.vehicleResource then
  vehicle_candidate=candidate end end
 local mount=mresolved.catalog.record(vehicle_candidate,'MountComponentData')
 poke(mount.owner.base+mount.offset+chain.slot*24,string.rep(string.char(0),8))
 result.rejections.staleMountChain=rejects(function()stage(mounted)end,'vehicle mount chain changed','stale mount chain')
 reset()
 assert(not hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('left_gun'):projectile_source().writable)
 result.rejections.mountedNonHost=rejects(function()stage({id='l',
  target={resource='vehicle_weapon',path='attack',weapon='EXO-45 Patriot Exosuit / left_gun',attack='primary'},
  allow_unverified_effect=true,allow_unverified_reference=true,changes={{field='attack.projectile',
  expect=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('left_gun'):attack('primary'),
  value=hd2.attack_output('AR-2 Coyote')}}})end,'field is not exposed','mounted non-host')
 result.rejections.mountedBeamDonor=rejects(function()stage({id='b',target=psource.target,allow_unverified_effect=true,
  allow_unverified_reference=true,changes={{field='attack.projectile',expect=psource.expect,
  value=hd2.attack_output('AX/LAS-5 Rover / gun')}}})end,'INCOMPATIBLE_OUTPUT_FAMILY','mounted beam donor')
 -- The Patriot minigun bullet row is shared with sentries and the MG-43: a slot write needs allow_shared.
 local prow=hd2.attack_output('EXO-45 Patriot Exosuit / right_gun')
 result.rejections.mountedSharedRow=rejects(function()stage({id='p',target=prow,allow_unverified_effect=true,
  changes={{field='projectile.impact_explosion',expect='none',value=hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion()}}})end,
  'allow_shared','mounted shared row')
 local prow_slot={id='p',target=prow,allow_unverified_effect=true,allow_shared=true,changes={{field='projectile.impact_explosion',
  expect='none',value=hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion()}}}
 local plan=stage(prow_slot)
 assert(#plan.changes==1 and not plan.changes[1].already_desired,'the Patriot slot write did not resolve')
 assert(plan.notes==nil,'a swapped-owner note on a Patriot firing its own row')
 -- A swap and a slot are separate: with the minigun swapped to EAT-17, the slot write still edits row 148 (the
 -- sentries fire it), and the plan carries the note that the edit does not reach the swapped minigun.
 local swap=stage(mounted)
 poke(swap.changes[1].owner.base+swap.changes[1].offset,swap.changes[1].desired)
 local swapped=stage(prow_slot)
 assert(#swapped.changes==1 and swapped.changes[1].identity.record_kind==plan.changes[1].identity.record_kind
  and swapped.changes[1].offset==plan.changes[1].offset,'a swapped Patriot moved its row slot write')
 assert(swapped.notes and swapped.notes[1]:find('currently fires another projectile',1,true)
  and swapped.notes[1]:find('do not follow a swapped projectile',1,true),'no swapped-owner note')
 result.swappedOwnerSlot={row=swapped.changes[1].identity.record_kind,note=swapped.notes[1]}
 reset()
 -- A support weapon that is not a host.
 local gl28=hd2.support_weapon('GL-28 Belt-Fed Grenade Launcher')
 assert(not gl28:projectile_source().writable,'GL-28 became a host')
 result.rejections.nonHostSupport=rejects(function()stage({id='g',target=gl28:attack('primary'),
  allow_unverified_effect=true,allow_unverified_reference=true,changes={{field='attack.projectile',
  expect=gl28:attack('primary'):projectile(),value=hd2.attack_output('AR-2 Coyote')}}})end,'field is not exposed',
  'non-host support weapon')
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
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
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
