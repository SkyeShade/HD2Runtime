"""Exercise drop-pod payload slots on a copy-on-write snapshot overlay.

For every authored payload slot of every writable rack, and every rack spawn count:

1. the live slot bytes equal the reviewed baseline and a no-op applies as ALREADY_DESIRED,
2. a changed reference (or count) writes exactly that field, reads back, and rolls back,
3. a third-party change is rejected as CONFLICT,
4. missing allow_unverified_reference / allow_unverified_effect / allow_shared is rejected.

Explicit scenarios cover the Surplus EAT pod (support weapon, consumable, two different slots, restore), an
ordinary support weapon pod, a weapon+backpack pod, invalid replacements, wrong slots, read-only racks, and
tampered rack/pickup state (random payload, missing attach node, pickup that lost its interaction).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources
import validate_attachment_authoring_snapshot as overlay_source

OUTPUT = ROOT / 'validation/pod-payload-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/pod_payload_writes')
local pods=require('hd2runtime/domains/pod_payload_authoring')
local FIELD,COUNT='payload.entity','payload.spawn_count'
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function round_trip(spec,label)
 local plan=resolve(spec)
 local changed=0
 for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==changed and applied.non_target_bytes_unchanged,
  label..' write failed: '..tostring(applied.reason))
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,label..' read-back failed')
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED',label..' rollback failed')
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,label..' rollback did not restore')
 end
 return plan,applied
end
local function pickup(name)return assert(pods.names[name],'no pickup '..name)end
local SUPPLY,HEALTH=pickup('Supply Box'),pickup('Health Pack (pod)')
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 racks=0,slots=0,baselineMatches=0,noOps=0,changedWrites=0,rollbacks=0,conflictRejections=0,
 acknowledgementRejections=0,sharedRejections=0,spawnCounts=0,scenarios={},rejections={}}
local worker=coroutine.create(function()
 local names={};for name,rack in pairs(pods.racks)do if rack.writable then names[#names+1]=name end end
 table.sort(names)
 for _,name in ipairs(names)do
  local rack=pods.racks[name];result.racks=result.racks+1
  local numbers={};for number in pairs(rack.slots)do numbers[#numbers+1]=tonumber(number)end;table.sort(numbers)
  for _,number in ipairs(numbers)do
   local slot=rack.slots[tostring(number)]
   local label=name..' slot '..number
   local target={resource='pod_rack',rack=name,path='slot',slot=number}
   local function request(expect,value,ref,shared)
    return {id='pod-slot',target=target,field=FIELD,expect=expect,value=value,
     allow_unverified_reference=ref or nil,allow_shared=shared or nil}
   end
   reset()
   local plan=resolve(domain.validate_patch(request(slot.current,slot.current,false,rack.shared)))
   for _,part in ipairs(plan.changes)do assert(part.before==part.desired,label..' live slot differs from the reviewed baseline')end
   result.baselineMatches=result.baselineMatches+1
   assert(guarded.apply(runtime,plan).status=='ALREADY_DESIRED',label..' no-op changed state')
   result.noOps=result.noOps+1
   local value=slot.current==SUPPLY and HEALTH or SUPPLY
   local spec=domain.validate_patch(request(slot.current,value,true,rack.shared))
   plan=round_trip(spec,label)
   result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
   poke(plan.changes[1].owner.base+plan.changes[1].offset,string.rep('\7',8))
   rejects(function()resolve(spec)end,'CONFLICT',label..' conflict')
   result.conflictRejections=result.conflictRejections+1
   reset()
   rejects(function()domain.validate_patch(request(slot.current,value,false,rack.shared))end,
    'allow_unverified_reference',label..' without acknowledgement')
   result.acknowledgementRejections=result.acknowledgementRejections+1
   if rack.shared then
    rejects(function()domain.validate_patch(request(slot.current,value,true,false))end,'allow_shared',
     label..' without allow_shared')
    result.sharedRejections=result.sharedRejections+1
   end
   result.slots=result.slots+1
  end
  -- Spawn count.
  local rtarget={resource='pod_rack',rack=name,path='rack'}
  local count=rack.spawnCount<4 and rack.spawnCount+1 or rack.spawnCount-1
  round_trip(domain.validate_patch({id='pod-count',target=rtarget,field=COUNT,expect=rack.spawnCount,value=count,
   allow_unverified_effect=true,allow_shared=rack.shared or nil}),name..' spawn count')
  rejects(function()domain.validate_patch({id='pod-count',target=rtarget,field=COUNT,expect=rack.spawnCount,
   value=count,allow_shared=rack.shared or nil})end,'allow_unverified_effect',name..' count acknowledgement')
  result.spawnCounts=result.spawnCounts+1
 end

 -- Explicit scenarios.
 local EAT='EAT-17 Expendable Anti-Tank pod'
 local eat=pods.racks[EAT]
 local vanilla=eat.slots['1'].current
 local function slot_target(rack,number)return {resource='pod_rack',rack=rack,path='slot',slot=number}end
 local function scenario(key,request)
  reset()
  local spec=request.changes and domain.validate_transaction(request)or domain.validate_patch(request)
  local plan,applied=round_trip(spec,key)
  local parts={}
  for index,part in ipairs(plan.changes)do parts[index]={fieldOffset=part.field_offset,before=b.hex(part.before),
   after=b.hex(part.desired)}end
  result.scenarios[key]={rack=request.target.rack,writes=applied.writes,changes=parts}
 end
 local mg=assert(pods.names['MG-43 Machine Gun'],'MG-43 pickup')
 scenario('surplus_eat_support_weapon',{id='s1',target=slot_target(EAT,1),field=FIELD,expect=vanilla,value=mg,
  allow_unverified_reference=true,allow_shared=true})
 scenario('surplus_eat_consumable',{id='s2',target=slot_target(EAT,2),field=FIELD,expect=vanilla,value=SUPPLY,
  allow_unverified_reference=true,allow_shared=true})
 -- Two different slot contents in one pod: two slot patches planned together.
 reset()
 local first=domain.validate_patch({id='s3a',target=slot_target(EAT,1),field=FIELD,expect=vanilla,value=SUPPLY,
  allow_unverified_reference=true,allow_shared=true})
 local second=domain.validate_patch({id='s3b',target=slot_target(EAT,2),field=FIELD,expect=vanilla,
  value=pickup('Grenade Box'),allow_unverified_reference=true,allow_shared=true})
 local plan1=resolve(first);assert(guarded.apply(runtime,plan1).status=='APPLIED')
 local plan2=resolve(second);assert(guarded.apply(runtime,plan2).status=='APPLIED')
 assert(plan1.changes[1].desired~=plan2.changes[1].desired,'two slots hold the same item')
 result.scenarios.two_different_slots={slot1=b.hex(plan1.changes[1].desired),slot2=b.hex(plan2.changes[1].desired)}
 -- Same entity twice, then restore vanilla on both.
 reset()
 scenario('same_entity_twice',{id='s4',target=slot_target(EAT,1),field=FIELD,expect=vanilla,value=SUPPLY,
  allow_unverified_reference=true,allow_shared=true})
 reset()
 local restore=domain.validate_patch({id='s5',target=slot_target(EAT,1),field=FIELD,expect=vanilla,value=vanilla,
  allow_shared=true})
 assert(guarded.apply(runtime,resolve(restore)).status=='ALREADY_DESIRED','restoring vanilla needs no reference ack')
 result.scenarios.restore_vanilla={acknowledgement='allow_shared only (vanilla occupant)'}
 local rail='RS-422 Railgun pod'
 scenario('ordinary_support_pod',{id='s6',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value=SUPPLY,allow_unverified_reference=true})
 local maxi='M-1000 Maxigun pod'
 scenario('weapon_backpack_pod',{id='s7',target=slot_target(maxi,2),field=FIELD,
  expect=pods.racks[maxi].slots['2'].current,value=pickup('B-1 Supply Pack'),allow_unverified_reference=true})
 -- Package-risk replacement: a world pickup with its own package, never in a vanilla rack.
 local grenade=pods.pickups[pickup('Grenade Box')]
 assert(grenade.compatibility=='UNVERIFIED_REFERENCE'and not grenade.alwaysResident,'grenade box risk class changed')
 rejects(function()domain.validate_patch({id='s8',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value=grenade.semanticId})end,'allow_unverified_reference',
  'package-risk replacement without acknowledgement')
 scenario('package_risk_replacement',{id='s8',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value=grenade.semanticId,allow_unverified_reference=true})
 -- Rejections.
 local function reject(key,fn,needle)rejects(fn,needle,key);result.rejections[#result.rejections+1]=key end
 reject('raw identifier',function()domain.validate_patch({id='r1',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value='0x49119612EB284A48',allow_unverified_reference=true})end,
  'not a reviewed pickup')
 reject('unknown pickup',function()domain.validate_patch({id='r2',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value='pickup/v1/solo-silo/0000',allow_unverified_reference=true})end,
  'not a reviewed pickup')
 reject('wrong slot',function()domain.validate_patch({id='r3',target=slot_target(rail,5),field=FIELD,
  expect='empty',value=SUPPLY,allow_unverified_reference=true})end,'not an authored payload slot')
 reject('read-only rack',function()domain.validate_patch({id='r4',target=slot_target('MS-11 Solo Silo pod',1),
  field=FIELD,expect='empty',value=SUPPLY,allow_unverified_reference=true})end,'read-only')
 reject('field on wrong target',function()domain.validate_patch({id='r5',target={resource='pod_rack',rack=rail,
  path='rack'},field=FIELD,expect=pods.racks[rail].slots['1'].current,value=SUPPLY,allow_unverified_reference=true})end,
  'slot field')
 -- Tampered live state.
 local spec=domain.validate_patch({id='t',target=slot_target(rail,1),field=FIELD,
  expect=pods.racks[rail].slots['1'].current,value=SUPPLY,allow_unverified_reference=true})
 reset()
 local _,resolved=resolve(spec)
 local record=resolved.record
 poke(record.owner.base+record.offset+552,b.encode(1,'u32'))
 reject('rack turned random',function()resolve(spec)end,'random payloads')
 reset();poke(record.owner.base+record.offset+8,string.rep('\0',4))
 reject('slot lost its attach node',function()resolve(spec)end,'attach node')
 reset()
 local supply=pods.pickups[SUPPLY]
 local reader=Reader.new(runtime)
 local catalog=require('hd2runtime/core/entity_catalog').capture(reader,
  require('hd2runtime/runtime/discover').locate(runtime,reader,require('hd2runtime/schemas/current'),{entity=true}).entity,
  require('hd2runtime/schemas/current'),{'InteractableComponentData'})
 local box
 for _,candidate in ipairs(catalog.candidates)do if candidate.resourceHash==supply.resource then box=candidate end end
 local interact=catalog.record(box,'InteractableComponentData')
 for zone=0,7 do poke(interact.owner.base+interact.offset+8+zone*136+40,b.encode(0,'u32'))end
 reject('replacement lost its pickup interaction',function()resolve(spec)end,'no longer offers')
 reset()
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
    print(json.dumps({k: v for k, v in result.items() if k != 'scenarios'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
