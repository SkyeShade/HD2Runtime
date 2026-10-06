"""Exercise the Eagle component fields (hd2.fields.eagle.*, Phase A) through the production write domain.

On a copy-on-write memory overlay of the retained snapshot (no game process, no real writes):

- every editable Eagle field of every Eagle resolves as a guarded no-op: the jet's live EagleComponentData record holds
  exactly the reviewed baseline (research/eagle-components-F5FEE03DCFDB.json);
- the four live-test writes (Airstrike pattern 0 -> 2, Napalm drop interval 0.2 -> 0.6, Strafing Run attack duration
  1.5 -> 3.0, 110mm target radius 20 -> 60): exactly one 4-byte write at the jet's record + the member offset, the
  exact desired bytes, every other byte of the record and of the other Eagles' records unchanged, every page
  protection restored, then the guarded inverse restores the exact original bytes;
- refusals: missing allow_unverified_effect (every field), missing allow_shared on exactly the three shared jets
  (Strafing Run, Gas, Napalm; none on the others), out-of-range, non-finite and non-integer values, a pattern outside
  0..7, a stale expect, read-only members (a member this Eagle's attack never reads, the attack kind, derived counts),
  a third-party value (CONFLICT) and a record whose attack kind changed (record proof).
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

OUTPUT = ROOT / 'validation/eagle-fields-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local stratagems=require('hd2runtime/domains/stratagem_writes')
local db=require('hd2runtime/domains/stratagem_authoring')
local RECORD=152
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=stratagems.capture(runtime,reader,spec)
 local plan=stratagems.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function eagle_fields(name)
 local out={}
 for _,field in ipairs(db.stratagems[name].fields)do
  if field.backing and field.backing.component=='EagleComponentData'then out[field.semanticFieldId]=field end
 end
 return out
end
local function target(name)return {resource='stratagem',stratagem=name,path='stratagem'}end
local function patch(name,field,expect,value,extra)
 local request={id='eagle-field',target=target(name),field=field,expect=expect,value=value,
  allow_unverified_effect=true,allow_shared=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return stratagems.validate_patch(request)
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 eagles={},noOps=0,readOnly=0,roundTrips={},rejections={}}
local function count(key)result.rejections[key]=(result.rejections[key]or 0)+1 end
local worker=coroutine.create(function()
 local names={};for name,entry in pairs(db.stratagems)do if entry.family=='eagle'then names[#names+1]=name end end
 table.sort(names)
 assert(#names==8,'expected the eight Eagles, got '..#names)
 -- 1. Every editable field of every Eagle: a guarded no-op against the live record (exact baseline bytes).
 local addresses={}
 for _,name in ipairs(names)do
  local fields=eagle_fields(name);local editable,readonly={},{}
  local changes={}
  for id,field in pairs(fields)do
   if field.editable then editable[#editable+1]=id
    changes[#changes+1]={field=id,expect=field.currentDefault,value=field.currentDefault}
   else readonly[#readonly+1]=id;result.readOnly=result.readOnly+1 end
  end
  table.sort(editable);table.sort(readonly);table.sort(changes,function(a,b)return a.field<b.field end)
  local spec=stratagems.validate_transaction({id='eagle-noop',target=target(name),changes=changes,
   allow_shared=true,allow_unverified_effect=true})
  local plan=resolve(spec)
  for _,part in ipairs(plan.changes)do
   assert(part.already_desired,name..' '..part.label..' live value differs from the reviewed baseline')
   addresses[name]=part.owner.base+part.offset-part.field_offset
  end
  result.noOps=result.noOps+#plan.changes
  result.eagles[name]={editable=editable,readOnly=readonly,shared=fields['eagle.attack_angle'].shared}
 end
 -- Each Eagle's jet has its own record (distinct addresses, one owner each).
 local seen={};for name,address in pairs(addresses)do
  assert(not seen[address],name..' shares a record with '..tostring(seen[address]));seen[address]=name end
 local function snapshot_records()local out={};for name,address in pairs(addresses)do
  out[name]=runtime.read(address,RECORD)end;return out end
 -- 2. The live-test writes: exact bytes, nothing else, protections restored, inverse restores.
 for _,case in ipairs({{'Eagle Airstrike','eagle.airstrike_pattern',0,2,'i32',20},
   {'Eagle Napalm Airstrike','eagle.drop_interval',0.2,0.6,'f32',44},
   {'Eagle Strafing Run','eagle.fire_duration',1.5,3.0,'f32',40},
   {'Eagle 110mm Rocket Pods','eagle.target_radius',20,60,'f32',36},
   {'Eagle Strafing Run','eagle.attack_sweep_length',60,120,'f32',108},
   {'Eagle 500kg Bomb','eagle.attack_angle',180,90,'f32',28}})do
  reset()
  local name,field,from,to,storage,offset=case[1],case[2],case[3],case[4],case[5],case[6]
  local before=snapshot_records()
  local spec=patch(name,field,from,to)
  local plan=resolve(spec)
  assert(#plan.changes==1,name..' '..field..' plans '..#plan.changes..' changes')
  local part=plan.changes[1]
  local record=part.owner.base+part.offset-part.field_offset
  assert(record==addresses[name]and part.field_offset==offset,name..' '..field..' targets the wrong member')
  assert(part.desired==b.encode(to,storage)and part.before==b.encode(from,storage),name..' '..field..' bytes')
  local writes=counts.writes
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,
   name..' '..field..' write failed: '..tostring(applied.reason))
  assert(counts.writes==writes+1,name..' '..field..' wrote '..(counts.writes-writes)..' times')
  assert(next(protection)==nil,name..' '..field..' left a page protection changed')
  local after=snapshot_records()
  for other,bytes in pairs(after)do
   if other==name then
    assert(bytes:sub(offset+1,offset+4)==b.encode(to,storage),name..' '..field..' did not land')
    assert(bytes:sub(1,offset)..bytes:sub(offset+5)==before[name]:sub(1,offset)..before[name]:sub(offset+5),
     name..' '..field..' changed another byte of its record')
   else assert(bytes==before[other],name..' '..field..' changed '..other..'\'s record')end
  end
  local restored=guarded.apply(runtime,guarded.inverse(plan))
  assert(restored.status=='APPLIED'and next(protection)==nil,name..' '..field..' rollback failed')
  for other,bytes in pairs(snapshot_records())do
   assert(bytes==before[other],name..' '..field..' rollback did not restore '..other)
  end
  result.roundTrips[#result.roundTrips+1]={stratagem=name,field=field,from=from,to=to,offset=offset,
   before=b.hex(part.before),after=b.hex(part.desired),writes=applied.writes,protectionRestored=true,
   otherBytesUnchanged=true,otherEaglesUnchanged=true,inverseRestored=true}
 end
 reset()
 -- 3. Acknowledgements: allow_unverified_effect on every editable field; allow_shared on exactly the shared jets.
 for _,name in ipairs(names)do
  for id,field in pairs(eagle_fields(name))do if field.editable then
   rejects(function()patch(name,id,field.currentDefault,field.currentDefault,{allow_unverified_effect=false})end,
    'allow_unverified_effect',name..' '..id..' acknowledgement');count('acknowledgement')
   if field.shared then
    rejects(function()patch(name,id,field.currentDefault,field.currentDefault,{allow_shared=false})end,
     'allow_shared',name..' '..id..' allow_shared');count('allowShared')
   else
    patch(name,id,field.currentDefault,field.currentDefault,{allow_shared=false})
    result.withoutAllowShared=(result.withoutAllowShared or 0)+1
   end
  end end
 end
 -- 4. Values: range, non-finite, non-integer, enum, stale expect.
 local nan=0/0
 for _,case in ipairs({
   {'Eagle Airstrike','eagle.airstrike_pattern',0,8,'reviewed range','pattern 8 (Count)'},
   {'Eagle Airstrike','eagle.airstrike_pattern',0,-1,'reviewed range','pattern -1'},
   {'Eagle Airstrike','eagle.airstrike_pattern',0,2.5,'integer','fractional pattern'},
   {'Eagle Napalm Airstrike','eagle.drop_interval',0.2,5,'reviewed range','drop interval 5 s'},
   {'Eagle Napalm Airstrike','eagle.drop_interval',0.2,0,'reviewed range','drop interval 0'},
   {'Eagle Strafing Run','eagle.fire_duration',1.5,0,'reviewed range','attack duration 0'},
   {'Eagle Strafing Run','eagle.fire_duration',1.5,nan,'finite','NaN duration'},
   {'Eagle Strafing Run','eagle.fire_duration',1.5,math.huge,'finite','infinite duration'},
   {'Eagle 110mm Rocket Pods','eagle.target_radius',20,-math.huge,'finite','negative infinite radius'},
   {'Eagle 110mm Rocket Pods','eagle.target_radius',20,500,'reviewed range','radius 500'},
   {'Eagle Strafing Run','eagle.attack_sweep_length',60,201,'reviewed range','sweep 201'},
   {'Eagle Airstrike','eagle.attack_angle',90,400,'reviewed range','angle 400'},
   {'Eagle Airstrike','eagle.airstrike_pattern',3,2,'expect differs','stale pattern expect'},
   {'Eagle Napalm Airstrike','eagle.drop_interval',0.3,0.6,'expect differs','stale interval expect'}})do
  rejects(function()patch(case[1],case[2],case[3],case[4])end,case[5],case[6]);count('value')
 end
 -- 5. Read-only: members this Eagle's attack never reads, the attack kind and the derived counts.
 for _,case in ipairs({{'Eagle Strafing Run','eagle.drop_interval',0.5,0.6},
   {'Eagle Strafing Run','eagle.airstrike_pattern',0,2},{'Eagle Airstrike','eagle.target_radius',60,30},
   {'Eagle Airstrike','eagle.fire_duration',1.5,3},{'Eagle 110mm Rocket Pods','eagle.attack_sweep_length',10,20},
   {'Eagle Airstrike','eagle.payload','airstrike','strafe'},{'Eagle Airstrike','eagle.bombs_per_strike',6,8},
   {'Eagle Strafing Run','eagle.strafe_rounds_per_run',100,200}})do
  rejects(function()patch(case[1],case[2],case[3],case[4])end,'read-only',case[1]..' '..case[2]);count('readOnly')
 end
 -- 6. A third-party value in the record: CONFLICT before any byte moves.
 local spec=patch('Eagle Airstrike','eagle.airstrike_pattern',0,2)
 local plan=resolve(spec);local part=plan.changes[1]
 poke(part.owner.base+part.offset,b.encode(5,'i32'))
 rejects(function()resolve(spec)end,'CONFLICT','third-party pattern');count('conflict')
 reset()
 -- 7. The record proof: a record whose attack kind is no longer the reviewed one is refused.
 poke(addresses['Eagle Airstrike']+16,b.encode(2,'i32'))
 rejects(function()resolve(spec)end,'no longer the reviewed','attack kind proof');count('recordProof')
 reset()
 -- 8. A write to one Eagle leaves every other Eagle's record untouched (covered per round trip) and the shared
 -- Eagle rearm row is untouched (no StratagemDefinition change is planned).
 for _,item in ipairs(plan.changes)do assert(item.identity.component=='EagleComponentData','unexpected backing')end
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
