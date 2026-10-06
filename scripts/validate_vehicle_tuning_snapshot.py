"""Exercise the vehicle tuning fields through the production write domains on the retained snapshot.

Fields (docs/vehicle-authoring.md, docs/vehicle-weapons.md, research/vehicle-mech-components-F5FEE03DCFDB.json):
turret.yaw_speed / pitch_speed / pitch_min / pitch_max / yaw_min / yaw_max on the five mounted weapons that own a
TurretComponent (domains/player_weapon_writes.lua), rotation.turn_speed / acceleration / deceleration on the four
Exosuits and vehicle.steering_response_speed on the seven wheeled or tracked catalog vehicles
(domains/entity_writes.lua).

On a copy-on-write memory overlay of the snapshot (no game process, no real writes):

- every field instance resolves as a guarded no-op: its own record (index row, record, single owner) and the
  reviewed baseline hold in the live table;
- round trips (M-103 Supply FRV gun turret.yaw_speed 130 -> 30, EXO-45 Patriot rotation.turn_speed 65 -> 20, M-102
  Gunner FRV vehicle.steering_response_speed 3.1 -> 0.5, and the TD-220 Bastion cannon yaw limits -20/20 -> -5/5 in
  one transaction): exactly the target bytes change; every other byte of the component table (all index rows and
  every other record) is unchanged; every opened page returns to its original protection; the guarded inverse
  restores the original bytes;
- the guarded context: the component table contributes its index rows and the one target record, never its whole
  record array (context, read allowance and reader bytes are recorded);
- rejections: non-applicable targets (FRV gun, flamethrower and Exosuit arms have no turret record; FRVs have no body
  rotation; Exosuits have no VehicleMotion), out-of-range and non-finite values, a crossing limit pair, a missing
  allow_unverified_effect, a stale expect, a moved index row (record ownership) and a third-party value (CONFLICT).
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

OUTPUT = ROOT / 'validation/vehicle-tuning-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local entity_writes=require('hd2runtime/domains/entity_writes')
local weapon_writes=require('hd2runtime/domains/player_weapon_writes')
local entity_db=require('hd2runtime/domains/entity_authoring')
local weapon_db=require('hd2runtime/domains/vehicle_weapon_authoring')
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 noops={},roundTrips={},rejections={}}
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 result.rejections[label]=tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):sub(1,180)
end
local TUNING={['rotation.turn_speed']=true,['rotation.acceleration']=true,['rotation.deceleration']=true,
 ['vehicle.steering_response_speed']=true}
local function tuning_fields(name)
 local out={}
 for _,field in ipairs(entity_db.vehicles[name].fields)do if TUNING[field.semanticFieldId]then out[#out+1]=field end end
 return out
end
local function turret_fields(key)
 local out={}
 for _,field in ipairs(weapon_db.weapons[key].fields)do
  if field.semanticFieldId:match('^turret%.')then out[#out+1]=field end
 end
 return out
end
local function vehicle_request(name,field,expect,value,extra)
 local r={id='tuning',target={resource='vehicle',vehicle=name,path='entity'},field=field,expect=expect,value=value,
  allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function weapon_target(key)return {resource='vehicle_weapon',path='weapon',weapon=key}end
local function weapon_request(key,field,expect,value,extra)
 local r={id='tuning',target=weapon_target(key),field=field,expect=expect,value=value,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function resolve(domain,spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved,reader
end
-- The whole component table (index rows + every record) of the loaded entity allocation.
local function table_of(owner,name)
 local c=profile.components[name]
 return owner.base+c.offset+28,c.record_offset+c.records*c.stride,c
end
local function context_total(snapshots)
 local seen,total={},0
 for _,s in ipairs(snapshots)do
  local key=tostring(s.owner.base)..':'..s.offset..':'..#s.bytes
  if not seen[key]then seen[key]=true;total=total+#s.bytes end
 end
 return total
end
-- Context bytes captured inside one component table: its index rows and the records the plan proves.
local function table_context(snapshots,owner,name)
 local base,size,c=table_of(owner,name)
 local seen,index_bytes,record_bytes={},0,0
 for _,s in ipairs(snapshots)do
  local first=s.owner.base+s.offset;local last=first+#s.bytes
  local key=first..':'..#s.bytes
  if s.owner.base==owner.base and not seen[key]and first<base+size and last>base then
   seen[key]=true
   local lo,hi=math.max(first,base),math.min(last,base+size)
   local split=base+c.record_offset
   index_bytes=index_bytes+math.max(0,math.min(hi,split)-lo)
   record_bytes=record_bytes+math.max(0,hi-math.max(lo,split))
  end
 end
 return index_bytes,record_bytes,c
end
local function replaced(bytes,offset,value)return bytes:sub(1,offset)..value..bytes:sub(offset+#value+1)end
local function record_of(resolved,name)
 return resolved.catalog.record(resolved.candidate,name)
end
local worker=coroutine.create(function()
 reset()
 -- 1. Every instance is a guarded no-op on the live tables.
 local vehicles,mounts={}, {}
 for name in pairs(entity_db.vehicles)do if #tuning_fields(name)>0 then vehicles[#vehicles+1]=name end end
 for key in pairs(weapon_db.weapons)do if #turret_fields(key)>0 then mounts[#mounts+1]=key end end
 table.sort(vehicles);table.sort(mounts)
 local instances=0
 for _,name in ipairs(vehicles)do
  for _,field in ipairs(tuning_fields(name))do
   local plan=resolve(entity_writes,entity_writes.validate_patch(vehicle_request(name,field.semanticFieldId,
    field.currentDefault,field.currentDefault)))
   assert(plan.changes[1].already_desired,name..' '..field.semanticFieldId..' live value differs from the baseline')
   result.noops[#result.noops+1]={target=name,field=field.semanticFieldId,baseline=field.currentDefault,
    component=field.backing.component}
   instances=instances+1
  end
 end
 for _,key in ipairs(mounts)do
  for _,field in ipairs(turret_fields(key))do
   local plan=resolve(weapon_writes,weapon_writes.validate_patch(weapon_request(key,field.semanticFieldId,
    field.currentDefault,field.currentDefault)))
   assert(plan.changes[1].already_desired,key..' '..field.semanticFieldId..' live value differs from the baseline')
   result.noops[#result.noops+1]={target=key,field=field.semanticFieldId,baseline=field.currentDefault,
    component='TurretComponentData'}
   instances=instances+1
  end
 end
 result.vehicles,result.mounts,result.instances=#vehicles,#mounts,instances
 -- 2. Round trips: exact target bytes, the rest of the component table unchanged, protection restored, inverse
 --    restores; the table contributes only its index rows and one record to the guarded context.
 local function round_trip(key,domain,spec,component,expected_writes)
  reset()
  local plan,resolved,reader=resolve(domain,spec)
  local owner=plan.changes[1].owner
  local base,size=table_of(owner,component)
  local before=runtime.read(base,size)
  local expected=before
  for _,change in ipairs(plan.changes)do expected=replaced(expected,owner.base+change.offset-base,change.desired)end
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==expected_writes and applied.non_target_bytes_unchanged
   and applied.protection_restored,key..' write failed: '..tostring(applied.reason))
  assert(next(protection)==nil,key..' a page kept a changed protection')
  local after=runtime.read(base,size)
  assert(after==expected,key..' bytes outside the targets changed')
  local changed=0
  for i=1,size do if before:byte(i)~=after:byte(i)then changed=changed+1 end end
  local record=record_of(resolved,component)
  local values={}
  for _,change in ipairs(plan.changes)do
   local at=owner.base+change.offset-base
   values[#values+1]=b.value(after,at,'f32')
   assert(change.offset>=record.offset and change.offset<record.offset+#record.bytes,key..' target outside its record')
  end
  local index_bytes,record_bytes,c=table_context(plan.snapshots,owner,component)
  local inverse=guarded.apply(runtime,guarded.inverse(plan))
  assert(inverse.status=='APPLIED'and inverse.protection_restored and next(protection)==nil,key..' rollback failed')
  assert(runtime.read(base,size)==before,key..' rollback did not restore the table')
  local total=context_total(plan.snapshots)
  result.roundTrips[key]={writes=applied.writes,tableBytesChanged=changed,tableBytesCompared=size,
   otherRecordsUnchanged=c.records-1,targetOffsetsInRecord=(function()local o={}
    for _,change in ipairs(plan.changes)do o[#o+1]=change.offset-record.offset end;return o end)(),
   written=values,protectionChanges=applied.protection_changes,protectionRestored=true,restored=true,
   contextBytes=total,tableIndexContextBytes=index_bytes,tableRecordContextBytes=record_bytes,
   tableIndexBytes=c.record_offset,recordStride=c.stride,tableRecordBytes=c.records*c.stride,
   readAllowance=guarded.read_allowance(#plan.changes,total,4*#plan.changes),readCeiling=guarded.READ_CEILING,
   readerBytes=reader.bytes}
  reset()
 end
 round_trip('m103_turret_yaw_speed',weapon_writes,weapon_writes.validate_patch(weapon_request('M-103 Supply FRV / gun',
  'turret.yaw_speed',130,30)),'TurretComponentData',1)
 round_trip('patriot_turn_speed',entity_writes,entity_writes.validate_patch(vehicle_request('EXO-45 Patriot Exosuit',
  'rotation.turn_speed',65,20)),'RotationComponentData',1)
 round_trip('frv_steering_response_speed',entity_writes,entity_writes.validate_patch(vehicle_request('M-102 Gunner FRV',
  'vehicle.steering_response_speed',3.1,0.5)),'VehicleMotionComponentData',1)
 round_trip('bastion_cannon_yaw_limits',weapon_writes,weapon_writes.validate_transaction({id='tuning',
  target=weapon_target('TD-220 Bastion MK XVI / attach_tank_gun'),allow_unverified_effect=true,changes={
   {field='turret.yaw_min',expect=-20,value=-5},{field='turret.yaw_max',expect=20,value=5}}}),'TurretComponentData',2)
 -- 3. Other entity writes keep their context: a Bastion main-health no-op captures no tuning table.
 do
  reset()
  local spec=entity_writes.validate_patch({id='h',target={resource='vehicle',vehicle='TD-220 Bastion MK XVI',
   path='entity'},field='entity.health',expect=8000,value=8000})
  local names=entity_writes.names_for({spec})
  for _,name in ipairs(names)do
   assert(name~='RotationComponentData'and name~='VehicleMotionComponentData','health write captures a tuning table')
  end
  local wspec=weapon_writes.validate_patch(weapon_request('M-103 Supply FRV / gun','weapon.capacity',120,120,
   {allow_unverified_effect=false}))
  for _,name in ipairs(weapon_writes.with_turret({'ProjectileWeaponComponentData'},{wspec}))do
   assert(name~='TurretComponentData','capacity write captures the turret table')
  end
  result.unrelatedWritesCaptureTuningTables=false
 end
 -- 4. Rejections.
 local function weapon_patch(key,field,expect,value,extra)
  return weapon_writes.validate_patch(weapon_request(key,field,expect,value,extra))
 end
 local function vehicle_patch(name,field,expect,value,extra)
  return entity_writes.validate_patch(vehicle_request(name,field,expect,value,extra))
 end
 for _,key in ipairs({'M-102 Gunner FRV / gun','M-104 Incinerator FRV / gun','EXO-45 Patriot Exosuit / left_gun',
   'EXO-49 Emancipator Exosuit / right_gun'})do
  rejects(function()weapon_patch(key,'turret.yaw_speed',130,30)end,'not exposed','not applicable: '..key)
 end
 rejects(function()vehicle_patch('M-102 Gunner FRV','rotation.turn_speed',65,20)end,'not exposed',
  'not applicable: FRV body rotation')
 rejects(function()vehicle_patch('EXO-45 Patriot Exosuit','vehicle.steering_response_speed',3.1,0.5)end,'not exposed',
  'not applicable: Exosuit steering')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,0)end,'reviewed minimum','value 0')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,721)end,'reviewed maximum','value 721')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.pitch_max',90,91)end,'reviewed maximum','pitch 91')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,0/0)end,'finite','value NaN')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,math.huge)end,'finite','value inf')
 rejects(function()weapon_patch('TD-220 Bastion MK XVI / attach_tank_gun','turret.yaw_min',-20,30)end,
  'TURRET_LIMIT_ORDER','crossing yaw limits')
 rejects(function()vehicle_patch('EXO-45 Patriot Exosuit','rotation.turn_speed',65,0.5)end,'reviewed range','turn 0.5')
 rejects(function()vehicle_patch('EXO-45 Patriot Exosuit','rotation.acceleration',0,-1)end,'reviewed range',
  'acceleration -1')
 rejects(function()vehicle_patch('EXO-45 Patriot Exosuit','rotation.deceleration',0,10001)end,'reviewed range',
  'deceleration 10001')
 rejects(function()vehicle_patch('M-102 Gunner FRV','vehicle.steering_response_speed',3.1,0.01)end,'reviewed range',
  'steering 0.01')
 rejects(function()vehicle_patch('M-102 Gunner FRV','vehicle.steering_response_speed',3.1,0/0)end,'finite',
  'steering NaN')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,30,{allow_unverified_effect=false})end,
  'allow_unverified_effect','turret missing acknowledgement')
 rejects(function()vehicle_patch('EXO-45 Patriot Exosuit','rotation.turn_speed',65,20,
  {allow_unverified_effect=false})end,'allow_unverified_effect','rotation missing acknowledgement')
 rejects(function()vehicle_patch('M-102 Gunner FRV','vehicle.steering_response_speed',3.1,0.5,
  {allow_unverified_effect=false})end,'allow_unverified_effect','steering missing acknowledgement')
 rejects(function()weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',100,30)end,'expect differs','stale expect')
 -- A moved index row and a third-party value, on each write domain.
 local function tamper(label,domain,spec,component,needle)
  reset()
  local _,resolved=resolve(domain,spec)
  local record=record_of(resolved,component)
  local c=profile.components[component]
  local row_at=record.owner.base+c.offset+28+record.identity.indexRow*16+8
  poke(row_at,b.encode((record.identity.recordIndex+1)%c.records,'u32'))
  rejects(function()resolve(domain,spec)end,needle,label..': index row moved');reset()
  local change=spec.changes[1]
  poke(record.owner.base+record.offset+change.descriptor.backing.offset,b.encode(123.5,'f32'))
  rejects(function()resolve(domain,spec)end,'CONFLICT',label..': third-party value');reset()
 end
 tamper('turret',weapon_writes,weapon_patch('M-103 Supply FRV / gun','turret.yaw_speed',130,30),'TurretComponentData',
  'component ownership identity changed')
 tamper('rotation',entity_writes,vehicle_patch('EXO-45 Patriot Exosuit','rotation.turn_speed',65,20),
  'RotationComponentData','entity component ownership changed')
 tamper('steering',entity_writes,vehicle_patch('M-102 Gunner FRV','vehicle.steering_response_speed',3.1,0.5),
  'VehicleMotionComponentData','entity component ownership changed')
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
    print(json.dumps({k: v for k, v in result.items() if k != 'noops'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
