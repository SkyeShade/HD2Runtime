"""Exercise the whole-body gib threshold (gore.whole_body_gib_damage) through the production enemy write domain on
the retained snapshot.

On a copy-on-write memory overlay of the snapshot (no game process, no real writes):

- every eligible class (23) resolves as a guarded no-op against the live GoreComponentData table: its own record,
  the whole-body group's guards and the reviewed baseline all hold;
- round trips (Warrior tier 2 750 -> 400, Hive Guard -1 -> 750, Scavenger tier 1 400 -> -1, Alpha-class Warrior
  750 -> 100000): exactly the four target bytes change; every other byte of the 7 MB GoreComponentData table (the
  class's own limb groups and all 208 other records) and the class's HealthComponent record are unchanged; every
  opened page is back to its original protection; the guarded inverse restores the original bytes;
- all 23 classes in one transaction (the largest a single plan phase can build) apply and restore inside the guarded
  read budget, with the context and read-allowance numbers recorded;
- rejections: a non-eligible class (Charger, Devastator, dragon, Watcher), out-of-range and non-finite values, a
  missing allow_unverified_effect, a stale expect, a cleared whole-body flag, a changed actor list, a moved index row
  (record ownership) and a third-party value (CONFLICT).
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

OUTPUT = ROOT / 'validation/enemy-gib-threshold-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local enemies=require('hd2runtime/domains/enemy_writes')
local enemy_db=require('hd2runtime/domains/enemy_authoring')
local F='gore.whole_body_gib_damage'
local GROUP=872
local c=profile.components.GoreComponentData
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',field=F,
 classes={},roundTrips={},rejections={}}
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 result.rejections[label]=tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):sub(1,160)
end
local function gore_field(name)
 for _,field in ipairs(enemy_db.enemies[name].fields)do if field.id==F then return field end end
end
local eligible={}
for name in pairs(enemy_db.enemies)do if gore_field(name)then eligible[#eligible+1]=name end end
table.sort(eligible)
local function request(name,expect,value,extra)
 local r={id='gib-'..name:gsub('[^%w]','_'),target={resource='enemy',enemy=name,path='entity'},field=F,
  expect=expect,value=value,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=enemies.capture(runtime,reader,spec)
 local plan=enemies.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved,reader
end
-- The whole GoreComponentData table (index rows + 209 records) of the loaded entity allocation.
local function table_of(owner)
 return owner.base+c.offset+28,c.record_offset+c.records*c.stride
end
local function context_total(snapshots)
 local seen,total={},0
 for _,s in ipairs(snapshots)do
  local key=tostring(s.owner.base)..':'..s.offset..':'..#s.bytes
  if not seen[key]then seen[key]=true;total=total+#s.bytes end
 end
 return total
end
local function replaced(bytes,offset,value)return bytes:sub(1,offset)..value..bytes:sub(offset+#value+1)end
local worker=coroutine.create(function()
 reset()
 -- 1. Every eligible class resolves as a guarded no-op on the live table.
 for _,name in ipairs(eligible)do
  local field=gore_field(name)
  local plan,resolved=resolve(enemies.validate_patch(request(name,field.currentDefault,field.currentDefault)))
  local part=plan.changes[1]
  assert(part.already_desired,name..' live value differs from the reviewed baseline')
  local record=resolved.catalog.record(resolved.candidate,'GoreComponentData')
  assert(record.identity.uniqueOwner and record.bytes:byte(field.backing.goreGroup*GROUP+867)==1,
   name..' whole-body flag absent')
  result.classes[#result.classes+1]={name=name,baseline=field.currentDefault,
   recordOffsetOfTarget=field.backing.offset,group=field.backing.goreGroup}
 end
 result.eligibleClasses=#eligible
 -- 2. Round trips: exact target bytes, every other table byte and the HealthComponent record unchanged,
 --    protection restored, inverse restores.
 local function round_trip(key,name,from,to)
  reset()
  local spec=enemies.validate_patch(request(name,from,to))
  local plan,resolved,reader=resolve(spec)
  local part=plan.changes[1]
  local base,size=table_of(part.owner)
  local before=runtime.read(base,size)
  local health=resolved.catalog.record(resolved.candidate,'HealthComponentData')
  local health_before=runtime.read(health.owner.base+health.offset,#health.bytes)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged
   and applied.protection_restored,key..' write failed: '..tostring(applied.reason))
  assert(next(protection)==nil,key..' a page kept a changed protection')
  local target=part.owner.base+part.offset-base
  local after=runtime.read(base,size)
  assert(after==replaced(before,target,part.desired),key..' bytes outside the target changed')
  assert(b.value(after,target,'f32')==b.value(part.desired,0,'f32')and b.value(part.desired,0,'f32')==to,key..' write did not land')
  local changed=0
  for i=1,4 do if before:byte(target+i)~=after:byte(target+i)then changed=changed+1 end end
  assert(runtime.read(health.owner.base+health.offset,#health.bytes)==health_before,key..' health record changed')
  local record=resolved.catalog.record(resolved.candidate,'GoreComponentData')
  local record_start=record.offset-(c.offset+28)
  local inverse=guarded.apply(runtime,guarded.inverse(plan))
  assert(inverse.status=='APPLIED'and inverse.protection_restored and next(protection)==nil,key..' rollback failed')
  assert(runtime.read(base,size)==before,key..' rollback did not restore the table')
  result.roundTrips[key]={class=name,from=from,to=to,writes=applied.writes,targetBytesChanged=changed,
   targetOffsetInRecord=part.offset-record.offset,
   limbGroupBytesUnchanged=c.stride-GROUP,otherRecordsUnchanged=c.records-1,
   tableBytesCompared=size,healthRecordUnchanged=true,protectionChanges=applied.protection_changes,
   protectionRestored=true,restored=true,contextBytes=context_total(plan.snapshots),
   readAllowance=guarded.read_allowance(1,context_total(plan.snapshots),4),readerBytes=reader.bytes,
   recordStartInTable=record_start}
  reset()
 end
 round_trip('warrior_tier_2','warrior_tier_2',750,400)
 round_trip('hive_guard','Hive Guard',-1,750)
 round_trip('scavenger_tier_1','scavenger_tier_1',400,-1)
 round_trip('warrior_big_tier2_max','warrior_big_tier2',750,100000)
 -- 3. All eligible classes in one transaction (one plan phase): budget and restore.
 reset()
 local specs={}
 for _,name in ipairs(eligible)do
  local baseline=gore_field(name).currentDefault
  specs[#specs+1]=enemies.validate_patch(request(name,baseline,baseline==-1 and 1 or baseline/2))
 end
 local reader=Reader.new(runtime)
 local resolved=enemies.capture_many(runtime,reader,specs)
 local plan={changes={},snapshots=reader.snapshots}
 for index,spec in ipairs(specs)do
  for _,change in ipairs(enemies.prepare(resolved[index],reader,spec).changes)do plan.changes[#plan.changes+1]=change end
 end
 reader.verify()
 local base,size=table_of(plan.changes[1].owner)
 local before=runtime.read(base,size)
 local expected=before
 for _,change in ipairs(plan.changes)do expected=replaced(expected,change.owner.base+change.offset-base,change.desired)end
 local total=context_total(plan.snapshots)
 local allowance=guarded.read_allowance(#plan.changes,total,4*#plan.changes)
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==#eligible and applied.non_target_bytes_unchanged
  and next(protection)==nil,'combined write failed: '..tostring(applied.reason))
 assert(runtime.read(base,size)==expected,'combined write changed bytes outside its targets')
 local inverse=guarded.apply(runtime,guarded.inverse(plan))
 assert(inverse.status=='APPLIED'and runtime.read(base,size)==before,'combined rollback did not restore')
 result.combined={classes=#eligible,writes=applied.writes,contextBytes=total,contexts=#plan.snapshots,
  readAllowance=allowance,readCeiling=guarded.READ_CEILING,readerBytes=reader.bytes,readerCeiling=16*1024*1024,
  contextCeiling=2*1024*1024,restored=true}
 reset()
 -- 4. Rejections.
 local warrior=request('warrior_tier_2',750,400)
 for _,name in ipairs({'Charger','soldier','dragon','Watcher'})do
  rejects(function()enemies.validate_patch(request(name,750,400))end,'not exposed','not eligible: '..name)
 end
 for _,bad in ipairs({0,-0.5,-2,100001})do
  rejects(function()enemies.validate_patch(request('warrior_tier_2',750,bad))end,'reviewed range',
   'value '..tostring(bad))
 end
 rejects(function()enemies.validate_patch(request('warrior_tier_2',750,0/0))end,'finite','value NaN')
 rejects(function()enemies.validate_patch(request('warrior_tier_2',750,math.huge))end,'finite','value inf')
 rejects(function()enemies.validate_patch(request('warrior_tier_2',750,400,{allow_unverified_effect=false}))end,
  'allow_unverified_effect','missing acknowledgement')
 rejects(function()enemies.validate_patch(request('warrior_tier_2',500,400))end,'expect differs','stale expect')
 local spec=enemies.validate_patch(warrior)
 local _,resolved_one=resolve(spec)
 local record=resolved_one.catalog.record(resolved_one.candidate,'GoreComponentData')
 local field=gore_field('warrior_tier_2')
 local group_base=record.owner.base+record.offset+field.backing.goreGroup*GROUP
 poke(group_base+866,'\0')
 rejects(function()resolve(spec)end,'identity changed','whole-body flag cleared');reset()
 poke(group_base+340,b.encode(0x12345678,'u32'))
 rejects(function()resolve(spec)end,'identity changed','actor list changed');reset()
 local identity=record.identity
 local row_at=record.owner.base+c.offset+28+identity.indexRow*16+8
 poke(row_at,b.encode((identity.recordIndex+1)%c.records,'u32'))
 rejects(function()resolve(spec)end,'enemy gore record ownership changed','index row moved');reset()
 poke(record.owner.base+record.offset+field.backing.offset,b.encode(123,'f32'))
 rejects(function()resolve(spec)end,'CONFLICT','third-party value');reset()
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
    print(json.dumps({k: v for k, v in result.items() if k != 'classes'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
