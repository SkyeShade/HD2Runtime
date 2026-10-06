"""Exercise the sentry component fields (research/sentry-components-F5FEE03DCFDB.json "publication") through the
production stratagem write domain.

On a copy-on-write memory overlay of the retained snapshot (no game process, no real writes):

- every editable sentry component field of every sentry resolves as a guarded no-op: the sentry's live component record
  (WeaponData, WeaponWindUp, BeamWeapon, Turret, SensorEye of its own deployed entity) holds exactly the reviewed
  baseline;
- the live-test writes (MG-43 horizontal spread 10 -> 300, AC-8 recoil climb vertical 10 -> 0, AC-8 pitch/yaw coupling
  1 -> 10, MG-43 side range -1 -> 10 and rear range -1 -> 3, G-16 wind-up 0.5 -> 6, LAS-98 beam fire rate 60 -> 120):
  exactly one 4-byte write at the record + the member offset, the exact desired bytes, every other byte of the record
  and every other sentry's record of that component unchanged, every page protection restored, then the guarded
  inverse restores the exact original bytes;
- refusals: missing allow_unverified_effect (every field; allow_shared is never needed: one owner each), out-of-range,
  non-finite and non-integer values, a negative side/rear range other than -1, a stale expect, the derived recoil
  (read-only), fields on sentries they do not apply to (not exposed) and a third-party value (CONFLICT).
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

OUTPUT = ROOT / 'validation/sentry-fields-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local stratagems=require('hd2runtime/domains/stratagem_writes')
local db=require('hd2runtime/domains/stratagem_authoring')
local SIZE={WeaponDataComponentData=1232,WeaponWindUpComponentData=36,BeamWeaponComponentData=120,
 TurretComponentData=76,SensorEyeComponentData=44}
local SENTRY_FIELDS={['weapon.horizontal_spread']=true,['weapon.vertical_spread']=true,
 ['weapon.recoil_drift_horizontal']=true,['weapon.recoil_drift_vertical']=true,['weapon.recoil_climb_horizontal']=true,
 ['weapon.recoil_climb_vertical']=true,['windup.wind_up_seconds']=true,['windup.wind_down_seconds']=true,
 ['beam.fire_rate']=true,['turret.pitch_yaw_coupling']=true,['targeting.side_range']=true,['targeting.rear_range']=true}
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
local function target(name,path)
 if path=='weapon'then return {resource='stratagem',stratagem=name,path='weapon',entity='main',weapon='primary'}end
 return {resource='stratagem',stratagem=name,path=path,entity='main'}
end
local DERIVED={['weapon.recoil']=true,['weapon.horizontal_recoil']=true,['weapon.vertical_recoil']=true}
local function sentry_fields(name)
 local out={}
 for _,field in ipairs(db.stratagems[name].fields)do
  if SENTRY_FIELDS[field.semanticFieldId]or DERIVED[field.semanticFieldId]and field.target.path=='weapon'then
   out[#out+1]=field end
 end
 return out
end
local function find(name,id)
 for _,field in ipairs(sentry_fields(name))do if field.semanticFieldId==id then return field end end
end
local function patch(name,path,field,expect,value,extra)
 local request={id='sentry-field',target=target(name,path),field=field,expect=expect,value=value,
  allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return stratagems.validate_patch(request)
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 sentries={},noOps=0,derivedReadOnly=0,roundTrips={},rejections={},withoutAllowShared=0}
local function count(key)result.rejections[key]=(result.rejections[key]or 0)+1 end
local worker=coroutine.create(function()
 local names={};for name,entry in pairs(db.stratagems)do
  if entry.sentryFields and #entry.sentryFields.fields>0 then names[#names+1]=name end end
 table.sort(names)
 assert(#names==9,'expected the nine sentries with component fields, got '..#names)
 -- 1. Every editable field of every sentry: a guarded no-op against the live record (exact baseline bytes), one
 -- transaction per backing object.
 local records={}   -- component -> sentry -> record address
 for _,name in ipairs(names)do
  local groups,order={},{}
  local fields={}
  for _,field in ipairs(sentry_fields(name))do
   if field.editable then
    local key=field.operationGroup
    if not groups[key]then groups[key]={path=field.target.path,component=field.backing.component,changes={}}
     order[#order+1]=key end
    local changes=groups[key].changes
    changes[#changes+1]={field=field.semanticFieldId,expect=field.currentDefault,value=field.currentDefault}
    fields[#fields+1]=field.semanticFieldId
   else result.derivedReadOnly=result.derivedReadOnly+1 end
  end
  table.sort(order);table.sort(fields)
  for _,key in ipairs(order)do
   local group=groups[key]
   table.sort(group.changes,function(a,c)return a.field<c.field end)
   local spec=stratagems.validate_transaction({id='sentry-noop',target=target(name,group.path),changes=group.changes,
    allow_unverified_effect=true})
   local plan=resolve(spec)
   for _,part in ipairs(plan.changes)do
    assert(part.already_desired,name..' '..part.label..' live value differs from the reviewed baseline')
    records[group.component]=records[group.component]or{}
    records[group.component][name]=part.owner.base+part.offset-part.field_offset
   end
   result.noOps=result.noOps+#plan.changes
  end
  result.sentries[name]={fields=fields}
 end
 -- Each sentry has its own record of every component (distinct addresses).
 for component,by_name in pairs(records)do
  local seen={};for name,address in pairs(by_name)do
   assert(not seen[address],name..' shares its '..component..' record with '..tostring(seen[address]))
   seen[address]=name end
 end
 local function capture(component)local out={};for name,address in pairs(records[component])do
  out[name]=runtime.read(address,SIZE[component])end;return out end
 -- 2. The live-test writes: exact bytes, nothing else, protections restored, inverse restores.
 for _,case in ipairs({
   {'A/MG-43 Machine Gun Sentry','weapon','weapon.horizontal_spread',10,300,'f32','WeaponDataComponentData',84},
   {'A/AC-8 Autocannon Sentry','weapon','weapon.recoil_climb_vertical',10,0,'f32','WeaponDataComponentData',32},
   {'A/AC-8 Autocannon Sentry','turret','turret.pitch_yaw_coupling',1,10,'f32','TurretComponentData',16},
   {'A/M-12 Mortar Sentry','turret','turret.pitch_yaw_coupling',4,0,'f32','TurretComponentData',16},
   {'A/MG-43 Machine Gun Sentry','targeting','targeting.side_range',-1,10,'f32','SensorEyeComponentData',4},
   {'A/MG-43 Machine Gun Sentry','targeting','targeting.rear_range',-1,3,'f32','SensorEyeComponentData',8},
   {'A/G-16 Gatling Sentry','weapon','windup.wind_up_seconds',0.5,6,'f32','WeaponWindUpComponentData',0},
   {'A/LAS-98 Laser Sentry','weapon','beam.fire_rate',60,120,'i32','BeamWeaponComponentData',104}})do
  reset()
  local name,path,field,from,to,storage,component,offset=case[1],case[2],case[3],case[4],case[5],case[6],case[7],case[8]
  local before=capture(component)
  local spec=patch(name,path,field,from,to)
  local plan=resolve(spec)
  assert(#plan.changes==1,name..' '..field..' plans '..#plan.changes..' changes')
  local part=plan.changes[1]
  local record=part.owner.base+part.offset-part.field_offset
  assert(record==records[component][name]and part.field_offset==offset,name..' '..field..' targets the wrong member')
  assert(part.desired==b.encode(to,storage)and part.before==b.encode(from,storage),name..' '..field..' bytes')
  local writes=counts.writes
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,
   name..' '..field..' write failed: '..tostring(applied.reason))
  assert(counts.writes==writes+1,name..' '..field..' wrote '..(counts.writes-writes)..' times')
  assert(next(protection)==nil,name..' '..field..' left a page protection changed')
  local after=capture(component)
  local others=0
  for other,bytes in pairs(after)do
   if other==name then
    assert(bytes:sub(offset+1,offset+4)==b.encode(to,storage),name..' '..field..' did not land')
    assert(bytes:sub(1,offset)..bytes:sub(offset+5)==before[name]:sub(1,offset)..before[name]:sub(offset+5),
     name..' '..field..' changed another byte of its record')
   else assert(bytes==before[other],name..' '..field..' changed '..other..'\'s record');others=others+1 end
  end
  local restored=guarded.apply(runtime,guarded.inverse(plan))
  assert(restored.status=='APPLIED'and next(protection)==nil,name..' '..field..' rollback failed')
  for other,bytes in pairs(capture(component))do
   assert(bytes==before[other],name..' '..field..' rollback did not restore '..other)
  end
  result.roundTrips[#result.roundTrips+1]={stratagem=name,field=field,from=from,to=to,offset=offset,
   component=component,before=b.hex(part.before),after=b.hex(part.desired),writes=applied.writes,
   otherSentriesChecked=others,protectionRestored=true,otherBytesUnchanged=true,otherSentriesUnchanged=true,
   inverseRestored=true}
 end
 reset()
 -- 3. Acknowledgements: allow_unverified_effect on every editable field; allow_shared never needed (one owner each).
 for _,name in ipairs(names)do
  for _,field in ipairs(sentry_fields(name))do if field.editable then
   local id,path=field.semanticFieldId,field.target.path
   assert(not field.shared,name..' '..id..' is shared')
   rejects(function()patch(name,path,id,field.currentDefault,field.currentDefault,{allow_unverified_effect=false})end,
    'allow_unverified_effect',name..' '..id..' acknowledgement');count('acknowledgement')
   patch(name,path,id,field.currentDefault,field.currentDefault)
   result.withoutAllowShared=result.withoutAllowShared+1
  end end
 end
 -- 4. Values: range, sentinel, non-finite, non-integer, stale expect.
 local nan=0/0
 local MG,AC,M12,G16,LAS='A/MG-43 Machine Gun Sentry','A/AC-8 Autocannon Sentry','A/M-12 Mortar Sentry',
  'A/G-16 Gatling Sentry','A/LAS-98 Laser Sentry'
 for _,case in ipairs({
   {MG,'weapon','weapon.horizontal_spread',10,501,'reviewed range','spread 501'},
   {MG,'weapon','weapon.vertical_spread',10,-1,'reviewed range','negative spread'},
   {AC,'weapon','weapon.recoil_drift_vertical',10,101,'reviewed range','recoil 101'},
   {AC,'weapon','weapon.recoil_climb_horizontal',2.5,-0.5,'reviewed range','negative recoil'},
   {AC,'turret','turret.pitch_yaw_coupling',1,11,'reviewed range','coupling 11'},
   {M12,'turret','turret.pitch_yaw_coupling',4,-0.5,'reviewed range','negative coupling'},
   {MG,'targeting','targeting.side_range',-1,-0.5,'reviewed range','side range -0.5 (not the sentinel)'},
   {MG,'targeting','targeting.rear_range',-1,-2,'reviewed range','rear range -2'},
   {MG,'targeting','targeting.side_range',-1,501,'reviewed range','side range 501'},
   {G16,'weapon','windup.wind_up_seconds',0.5,31,'reviewed range','wind-up 31 s'},
   {G16,'weapon','windup.wind_down_seconds',1,-1,'reviewed range','negative wind-down'},
   {LAS,'weapon','beam.fire_rate',60,0,'reviewed range','beam 0 rpm'},
   {LAS,'weapon','beam.fire_rate',60,3001,'reviewed range','beam 3001 rpm'},
   {LAS,'weapon','beam.fire_rate',60,60.5,'integer','fractional beam rate'},
   {MG,'weapon','weapon.horizontal_spread',10,nan,'finite','NaN spread'},
   {AC,'turret','turret.pitch_yaw_coupling',1,math.huge,'finite','infinite coupling'},
   {MG,'targeting','targeting.rear_range',-1,-math.huge,'finite','negative infinite rear range'},
   {MG,'weapon','weapon.horizontal_spread',12,300,'expect differs','stale spread expect'},
   {M12,'turret','turret.pitch_yaw_coupling',1,0,'expect differs','stale coupling expect'}})do
  rejects(function()patch(case[1],case[2],case[3],case[4],case[5])end,case[6],case[7]);count('value')
 end
 -- The sentinel and the range bounds are accepted.
 patch(MG,'targeting','targeting.side_range',-1,0);patch(MG,'targeting','targeting.side_range',-1,500)
 patch(MG,'targeting','targeting.rear_range',-1,-1)
 -- 5. Read-only: the derived recoil means.
 for _,case in ipairs({{MG,'weapon.recoil',5.5,0},{MG,'weapon.horizontal_recoil',10,0},
   {AC,'weapon.vertical_recoil',10,0}})do
  rejects(function()patch(case[1],'weapon',case[2],case[3],case[4])end,'read-only',case[1]..' '..case[2]);count('readOnly')
 end
 -- 6. Fields a sentry does not carry are not exposed (the reviewed exclusions).
 for _,case in ipairs({{LAS,'weapon','weapon.horizontal_spread',5,10},
   {'A/FLAM-40 Flame Sentry','weapon','weapon.recoil_drift_horizontal',0,1},
   {'A/ARC-3 Tesla Tower','targeting','targeting.side_range',-1,10},
   {MG,'weapon','windup.wind_up_seconds',0.5,1},{MG,'weapon','beam.fire_rate',60,120},
   {'A/ARC-3 Tesla Tower','turret','turret.pitch_yaw_coupling',1,2}})do
  local ok,why=pcall(function()patch(case[1],case[2],case[3],case[4],case[5])end)
  assert(not ok and(tostring(why):find('not exposed',1,true)or tostring(why):find('no reviewed',1,true)
   or tostring(why):find('deployed entity',1,true)),case[1]..' '..case[3]..': '..tostring(why))
  count('notApplicable')
 end
 -- 7. A third-party value in the record: CONFLICT before any byte moves.
 local spec=patch(MG,'weapon','weapon.horizontal_spread',10,300)
 local plan=resolve(spec);local part=plan.changes[1]
 poke(part.owner.base+part.offset,b.encode(25,'f32'))
 rejects(function()resolve(spec)end,'CONFLICT','third-party spread');count('conflict')
 reset()
 spec=patch(AC,'turret','turret.pitch_yaw_coupling',1,10)
 plan=resolve(spec);part=plan.changes[1]
 poke(part.owner.base+part.offset,b.encode(2,'f32'))
 rejects(function()resolve(spec)end,'CONFLICT','third-party coupling');count('conflict')
 reset()
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
