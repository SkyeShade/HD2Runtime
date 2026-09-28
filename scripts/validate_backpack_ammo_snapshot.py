"""Exercise backpack-owned support weapon ammunition on a copy-on-write snapshot overlay.

For every weapon-fed backpack (M-1000 Maxigun, B/FLAM-80 Cremator, GL-28 Belt-Fed Grenade Launcher) and each
of its deposit fields (capacity, starting ammo, ammo from supply):

1. the live bytes equal the reviewed baseline, and a no-op applies as ALREADY_DESIRED,
2. a changed value writes exactly the field, reads back, and rolls back,
3. a third-party change is rejected as CONFLICT,
4. a missing allow_unverified_effect, a stale expect and an out-of-range value are rejected.

The ammunition chain is re-proven on every write; each link is tampered with once and must be rejected:
the backpack tag, the weapon's linked-ammo tag and inventory slot, and the rack's delivered weapon.
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

OUTPUT = ROOT / 'validation/backpack-ammo-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/entity_writes')
local database=require('hd2runtime/domains/entity_authoring')
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
local function candidate(catalog,resource)
 for _,item in ipairs(catalog.candidates)do if item.resourceHash==resource then return item end end
end
local CHANGED={['deposit.capacity']=2000,['deposit.start_amount']=1500,['deposit.refill_amount']=750}
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 backpacks={},fields=0,baselineMatches=0,noOps=0,changedWrites=0,rollbacks=0,conflictRejections=0,
 acknowledgementRejections=0,staleExpectRejections=0,rangeRejections=0,chainTamperRejections=0}
local worker=coroutine.create(function()
 local names={};for name,entry in pairs(database.backpacks)do if entry.feeds then names[#names+1]=name end end
 table.sort(names)
 for _,name in ipairs(names)do
  local entry=database.backpacks[name]
  local target={resource='backpack',backpack=name,path='backpack'}
  local item={backpack=name,weapon=entry.feeds.weapon,fields={}}
  for _,field in ipairs(entry.fields)do if field.editable then
   local label=name..' '..field.semanticFieldId
   local function request(expect,value,ack)
    return {id='backpack-ammo',target=target,field=field.semanticFieldId,expect=expect,value=value,
     allow_unverified_effect=ack or nil}
   end
   reset()
   local plan=resolve(domain.validate_patch(request(field.currentDefault,field.currentDefault,true)))
   local part=plan.changes[1]
   assert(part.before==b.encode(field.currentDefault,field.backing.storage),label..' live baseline differs')
   result.baselineMatches=result.baselineMatches+1
   local checked=guarded.apply(runtime,plan)
   assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,label..' no-op changed state')
   result.noOps=result.noOps+1
   local value=CHANGED[field.semanticFieldId]
   local spec=domain.validate_patch(request(field.currentDefault,value,true))
   plan=resolve(spec);part=plan.changes[1]
   local applied=guarded.apply(runtime,plan)
   assert(applied.status=='APPLIED'and applied.writes==1 and applied.bytes_written==4
    and applied.non_target_bytes_unchanged,label..' write failed: '..tostring(applied.reason))
   assert(runtime.read(part.owner.base+part.offset,4)==b.encode(value,field.backing.storage),label..' read-back failed')
   local restored=guarded.apply(runtime,guarded.inverse(plan))
   assert(restored.status=='APPLIED'and runtime.read(part.owner.base+part.offset,4)==part.before,label..' rollback failed')
   result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
   poke(part.owner.base+part.offset,b.encode(field.currentDefault+3,field.backing.storage))
   rejects(function()resolve(spec)end,'CONFLICT',label..' conflict')
   result.conflictRejections=result.conflictRejections+1
   reset()
   rejects(function()domain.validate_patch(request(field.currentDefault,value,nil))end,'allow_unverified_effect',
    label..' without acknowledgement')
   result.acknowledgementRejections=result.acknowledgementRejections+1
   rejects(function()domain.validate_patch(request(field.currentDefault+1,value,true))end,'expect differs',
    label..' stale expect')
   result.staleExpectRejections=result.staleExpectRejections+1
   rejects(function()domain.validate_patch(request(field.currentDefault,field.max+1,true))end,'reviewed range',
    label..' out of range')
   result.rangeRejections=result.rangeRejections+1
   result.fields=result.fields+1
   item.fields[#item.fields+1]={field=field.semanticFieldId,baseline=field.currentDefault,changedTo=value,
    component=part.identity.component,fieldOffset=part.field_offset,before=b.hex(part.before),
    uniqueOwner=part.identity.unique_owner}
  end end
  -- Tamper with each link of the ammunition chain; the write must be refused.
  local first=entry.fields[1]
  local spec=domain.validate_patch({id='chain',target=target,field=first.semanticFieldId,expect=first.currentDefault,
   value=first.currentDefault,allow_unverified_effect=true})
  reset()
  local _,resolved=resolve(spec)
  local catalog=resolved.catalog
  local tag=catalog.record(resolved.candidate,'TagComponentData')
  local weapon=candidate(catalog,entry.feeds.weaponResource)
  local linked=catalog.record(weapon,'WeaponLinkedAmmoComponentData')
  local rack=catalog.record(candidate(catalog,entry.rack.resource),'HellpodRackComponentData')
  local weapon_slot
  for slot,resource in pairs(entry.rack.slots)do if resource==entry.feeds.weaponResource then weapon_slot=tonumber(slot)end end
  local tampers={
   {'backpack tag',tag.owner.base+tag.offset,string.rep('\0',8),'backpack no longer carries'},
   {'weapon linked-ammo tag',linked.owner.base+linked.offset,string.rep('\0',8),'weapon no longer draws'},
   {'weapon inventory slot',linked.owner.base+linked.offset+12,b.encode(3,'u32'),'weapon no longer draws'},
   {'rack delivered weapon',rack.owner.base+rack.offset+weapon_slot*64,string.rep('\0',8),'no longer delivers'}}
  for _,tamper in ipairs(tampers)do
   reset();poke(tamper[2],tamper[3])
   rejects(function()resolve(spec)end,tamper[4],name..' '..tamper[1])
   result.chainTamperRejections=result.chainTamperRejections+1
  end
  reset()
  item.chainChecks=#tampers
  result.backpacks[#result.backpacks+1]=item
 end
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
    print(json.dumps({k: v for k, v in result.items() if k != 'backpacks'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
