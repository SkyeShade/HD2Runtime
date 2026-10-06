"""Exercise the orbital bombardment pattern fields (hd2.fields.orbital.salvos, shells_per_salvo, shell_interval(_random),
salvo_interval(_random), scatter, salvo_scatter) and the call-in time (hd2.fields.stratagem.call_in_time) through the
production write domain.

On a copy-on-write memory overlay of the retained snapshot (no game process, no real writes):

- every pattern field of the ten reviewed orbitals resolves as a guarded no-op: each orbital's live
  BombardmentComponentData record holds exactly the reviewed baseline (research/bombardment-payload-F5FEE03DCFDB.json),
  and every orbital has its own record;
- every catalogued row's call-in resolves as a guarded no-op: the live StratagemInfo +0x54 holds exactly the baseline;
- the live-test writes (EMS Strike 1 -> 5 salvos and 1 -> 3 shells, Napalm Barrage 5 -> 1 shells and scatter 25 -> 1,
  120mm shell interval 0.75 -> 0.3, Gatling salvo interval 0 -> 1; the 120mm call-in 5 -> 1, the 380mm 6 -> 15, the Eagle
  Airstrike 0 -> 3): exactly one 4-byte write at the record (row) + the member offset, the exact desired bytes, every
  other byte of that record and of every other orbital's record (row) unchanged, every page protection restored, then
  the guarded inverse restores the exact original bytes;
- one transaction turns the EMS Strike into a barrage (salvos, shells, both delays, scatter): one write per member;
- refusals: missing allow_unverified_effect, out-of-range, non-integer and non-finite values, a stale expect, a
  third-party value (CONFLICT) and a record whose shell list changed (record proof).
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

OUTPUT = ROOT / 'validation/orbital-fields-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local stratagems=require('hd2runtime/domains/stratagem_writes')
local db=require('hd2runtime/domains/stratagem_authoring')
local RECORD=192
local ROW=profile.stratagem.stride
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
local function fields_of(name,predicate)
 local out={}
 for _,field in ipairs(db.stratagems[name].fields)do if predicate(field)then out[field.semanticFieldId]=field end end
 return out
end
local function pattern_fields(name)
 return fields_of(name,function(f)return f.backing and f.backing.component=='BombardmentComponentData'end)
end
local function call_in(name)return fields_of(name,function(f)return f.semanticFieldId=='stratagem.call_in_time'end)
 ['stratagem.call_in_time']end
local function target(name)return {resource='stratagem',stratagem=name,path='stratagem'}end
local function patch(name,field,expect,value,extra)
 local request={id='orbital-field',target=target(name),field=field,expect=expect,value=value,
  allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return stratagems.validate_patch(request)
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 orbitals={},patternNoOps=0,callInNoOps=0,roundTrips={},transactions={},rejections={}}
local function count(key)result.rejections[key]=(result.rejections[key]or 0)+1 end
-- One write: exactly one 4-byte change at the planned member, every other byte of every watched block unchanged,
-- protections restored, the inverse restores everything.
local function round_trip(name,field,from,to,storage,watched,size)
 reset()
 local function blocks()local out={};for key,address in pairs(watched)do out[key]=runtime.read(address,size)end
  return out end
 local before=blocks()
 local plan=resolve(patch(name,field,from,to))
 assert(#plan.changes==1,name..' '..field..' plans '..#plan.changes..' changes')
 local part=plan.changes[1]
 local base=part.owner.base+part.offset-part.field_offset
 assert(base==watched[name],name..' '..field..' targets another record')
 assert(part.desired==b.encode(to,storage)and part.before==b.encode(from,storage),name..' '..field..' bytes')
 local writes=counts.writes
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,
  name..' '..field..' write failed: '..tostring(applied.reason))
 assert(counts.writes==writes+1 and next(protection)==nil,name..' '..field..' writes or protection')
 local offset=part.field_offset
 for key,bytes in pairs(blocks())do
  if key==name then
   assert(bytes:sub(offset+1,offset+4)==b.encode(to,storage),name..' '..field..' did not land')
   assert(bytes:sub(1,offset)..bytes:sub(offset+5)==before[key]:sub(1,offset)..before[key]:sub(offset+5),
    name..' '..field..' changed another byte of its block')
  else assert(bytes==before[key],name..' '..field..' changed '..key)end
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and next(protection)==nil,name..' '..field..' rollback failed')
 for key,bytes in pairs(blocks())do assert(bytes==before[key],name..' '..field..' rollback did not restore '..key)end
 result.roundTrips[#result.roundTrips+1]={stratagem=name,field=field,from=from,to=to,offset=offset,
  before=b.hex(part.before),after=b.hex(part.desired),writes=applied.writes,protectionRestored=true,
  otherBytesUnchanged=true,inverseRestored=true}
end
local worker=coroutine.create(function()
 -- 1. Every pattern field of every reviewed orbital: a guarded no-op against its own live record.
 local orbitals={}
 for name,entry in pairs(db.stratagems)do if next(pattern_fields(name))then orbitals[#orbitals+1]=name end end
 table.sort(orbitals)
 assert(#orbitals==10,'expected the ten reviewed orbitals, got '..#orbitals)
 local records={}
 for _,name in ipairs(orbitals)do
  local changes,ids={},{}
  for id,field in pairs(pattern_fields(name))do
   assert(field.editable and field.acknowledgement=='allow_unverified_effect'and not field.shared,name..' '..id)
   changes[#changes+1]={field=id,expect=field.currentDefault,value=field.currentDefault};ids[#ids+1]=id
  end
  table.sort(changes,function(a,c)return a.field<c.field end);table.sort(ids)
  assert(#changes==8,name..' publishes '..#changes..' pattern fields')
  local plan=resolve(stratagems.validate_transaction({id='orbital-noop',target=target(name),changes=changes,
   allow_unverified_effect=true}))
  for _,part in ipairs(plan.changes)do
   assert(part.already_desired,name..' '..part.label..' live value differs from the reviewed baseline')
   records[name]=part.owner.base+part.offset-part.field_offset
  end
  result.patternNoOps=result.patternNoOps+#plan.changes
  result.orbitals[name]={fields=ids,shellTypes=pattern_fields(name)['orbital.salvos'].shellTypes}
 end
 local seen={};for name,address in pairs(records)do
  assert(not seen[address],name..' shares a record with '..tostring(seen[address]));seen[address]=name end
 -- 2. Every catalogued row's call-in: a guarded no-op against its own live row.
 local rows={}
 local names={};for name in pairs(db.stratagems)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local field=call_in(name)
  assert(field and field.editable and field.acknowledgement=='allow_unverified_effect',name..' call-in')
  local plan=resolve(patch(name,'stratagem.call_in_time',field.currentDefault,field.currentDefault))
  assert(#plan.changes==1 and plan.changes[1].already_desired,name..' live call-in differs from the baseline')
  local part=plan.changes[1]
  assert(part.field_offset==0x54,name..' call-in is not +0x54')
  rows[name]=part.owner.base+part.offset-part.field_offset
  result.callInNoOps=result.callInNoOps+1
 end
 -- 3. The live-test writes.
 for _,case in ipairs({{'Orbital EMS Strike','orbital.salvos',1,5,'u32'},
   {'Orbital EMS Strike','orbital.shells_per_salvo',1,3,'u32'},
   {'Orbital Napalm Barrage','orbital.shells_per_salvo',5,1,'u32'},
   {'Orbital Napalm Barrage','orbital.scatter',25,1,'f32'},
   {'Orbital 120mm HE Barrage','orbital.shell_interval',0.75,0.3,'f32'},
   {'Orbital Gatling Barrage','orbital.salvo_interval',0,1,'f32'}})do
  round_trip(case[1],case[2],case[3],case[4],case[5],records,RECORD)
 end
 local watched={}
 for _,name in ipairs({'Orbital 120mm HE Barrage','Orbital 380mm HE Barrage','Eagle Airstrike',
   'Orbital Precision Strike'})do watched[name]=rows[name]end
 for _,case in ipairs({{'Orbital 120mm HE Barrage',5,1},{'Orbital 380mm HE Barrage',6,15},{'Eagle Airstrike',0,3}})do
  round_trip(case[1],'stratagem.call_in_time',case[2],case[3],'f32',watched,ROW)
 end
 -- 4. One transaction: the EMS Strike as a barrage of 5 salvos of 3 shells.
 reset()
 local ems='Orbital EMS Strike'
 local before=runtime.read(records[ems],RECORD)
 local changes={{field='orbital.salvos',expect=1,value=5},{field='orbital.shells_per_salvo',expect=1,value=3},
  {field='orbital.shell_interval',expect=0.35,value=0.4},{field='orbital.salvo_interval',expect=2,value=1.5},
  {field='orbital.scatter',expect=1,value=20}}
 local plan=resolve(stratagems.validate_transaction({id='ems-barrage',target=target(ems),changes=changes,
  allow_unverified_effect=true}))
 assert(#plan.changes==5,'the EMS barrage plans '..#plan.changes..' changes')
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==5 and next(protection)==nil,'the EMS barrage write failed: '
  ..tostring(applied.reason))
 local after=runtime.read(records[ems],RECORD)
 assert(b.u32(after,0x18)==5 and b.u32(after,0x04)==3,'the EMS counts did not land')
 for k=0,7 do assert(after:sub(0x40+4*k+1,0x40+4*k+4)==before:sub(0x40+4*k+1,0x40+4*k+4),'a shell type moved')end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and runtime.read(records[ems],RECORD)==before,'the EMS barrage rollback failed')
 result.transactions[#result.transactions+1]={stratagem=ems,changes=#changes,writes=applied.writes,
  shellTypesUnchanged=true,inverseRestored=true}
 -- The call-in and the cooldown of one row in one transaction (one StratagemInfo object).
 reset()
 local row_before=runtime.read(rows['Orbital 120mm HE Barrage'],ROW)
 plan=resolve(stratagems.validate_transaction({id='call-in-and-cooldown',target=target('Orbital 120mm HE Barrage'),
  changes={{field='stratagem.call_in_time',expect=5,value=1},{field='stratagem.cooldown',expect=180,value=60}},
  allow_unverified_effect=true}))
 applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==2,'the call-in and cooldown write failed')
 restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED'and runtime.read(rows['Orbital 120mm HE Barrage'],ROW)==row_before,
  'the call-in and cooldown rollback failed')
 result.transactions[#result.transactions+1]={stratagem='Orbital 120mm HE Barrage',changes=2,writes=2,
  inverseRestored=true}
 reset()
 -- 5. Acknowledgements: allow_unverified_effect on every new field.
 for _,name in ipairs(orbitals)do
  for id,field in pairs(pattern_fields(name))do
   rejects(function()patch(name,id,field.currentDefault,field.currentDefault,{allow_unverified_effect=false})end,
    'allow_unverified_effect',name..' '..id..' acknowledgement');count('acknowledgement')
  end
 end
 for _,name in ipairs(names)do
  rejects(function()patch(name,'stratagem.call_in_time',call_in(name).currentDefault,call_in(name).currentDefault,
   {allow_unverified_effect=false})end,'allow_unverified_effect',name..' call-in acknowledgement');count('acknowledgement')
 end
 -- 6. Values: range, integer, non-finite, stale expect.
 local nan=0/0
 for _,case in ipairs({
   {ems,'orbital.salvos',1,0,'reviewed range','0 salvos'},{ems,'orbital.salvos',1,17,'reviewed range','17 salvos'},
   {ems,'orbital.salvos',1,2.5,'integer','fractional salvos'},
   {ems,'orbital.shells_per_salvo',1,0,'reviewed range','0 shells'},
   {ems,'orbital.shells_per_salvo',1,65,'reviewed range','65 shells'},
   {ems,'orbital.shell_interval',0.35,-1,'reviewed range','negative delay'},
   {ems,'orbital.shell_interval',0.35,11,'reviewed range','11 s between shells'},
   {ems,'orbital.salvo_interval',2,31,'reviewed range','31 s between salvos'},
   {ems,'orbital.scatter',1,101,'reviewed range','scatter 101'},
   {ems,'orbital.salvo_scatter',0,nan,'finite','NaN salvo scatter'},
   {ems,'orbital.salvos',2,5,'expect differs','stale salvos expect'},
   {'Orbital 120mm HE Barrage','stratagem.call_in_time',5,-1,'reviewed range','negative call-in'},
   {'Orbital 120mm HE Barrage','stratagem.call_in_time',5,61,'reviewed range','61 s call-in'},
   {'Orbital 120mm HE Barrage','stratagem.call_in_time',5,math.huge,'finite','infinite call-in'},
   {'Orbital 120mm HE Barrage','stratagem.call_in_time',4,1,'expect differs','stale call-in expect'}})do
  rejects(function()patch(case[1],case[2],case[3],case[4])end,case[5],case[6]);count('value')
 end
 -- 7. A third-party value in the record: CONFLICT before any byte moves.
 local spec=patch(ems,'orbital.salvos',1,5)
 plan=resolve(spec)
 local part=plan.changes[1]
 poke(part.owner.base+part.offset,b.encode(2,'u32'))
 rejects(function()resolve(spec)end,'CONFLICT','third-party salvos');count('conflict')
 reset()
 -- 8. The record proof: a record whose shell list changed is no longer the reviewed one.
 poke(records[ems]+0x40,b.encode(137,'u32'))
 rejects(function()resolve(spec)end,'no longer the reviewed','shell list proof');count('recordProof')
 reset()
 for _,item in ipairs(plan.changes)do assert(item.identity.component=='BombardmentComponentData','unexpected backing')end
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
