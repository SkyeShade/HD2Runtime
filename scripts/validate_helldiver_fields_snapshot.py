"""Exercise the type-wide Helldiver fields (hd2.helldiver(); docs/helldiver-fields.md) through the production write
domain (domains/helldiver_writes.lua) on every retained snapshot of the build.

On a copy-on-write memory overlay of each snapshot (no game process, no real writes):

- identity: the AvatarComponentData table framing the generated data carries (it is not in the runtime profile)
  matches the loaded entity file; avatar_helldiver owns one entity row, AvatarComponentData record 0 (index row 1) and
  HealthComponentData record 76 (index row 443) alone; the six zone name hashes hold;
- every field instance (21 avatar, the default-zone explosion share and 5 x 6 zone fields) resolves as a guarded
  no-op: the live bytes are the reviewed vanilla value;
- round trips (jog 3.2 -> 4.5; sprint duration 23 -> 3 and recover delay 1.5 -> 0.5 in one transaction; the head's
  damage_multiplier normal -> none; the body's damage_multiplier_dps normal -> inherit; the body's zone health
  60 -> 120; the explosion share 0.5 -> 0.25): exactly the target bytes change; every other byte of the component
  table (index rows and every record) is unchanged; every opened page returns to its original protection; the
  guarded inverse restores the original bytes;
- the private-copy report equals what research/avatar-fields-F5FEE03DCFDB.json observed in the same snapshot (the
  ship's avatar carries an AvatarComponentData copy, the mission avatars none), and the write notes name it for the
  avatar fields only (never for the type-only zone multipliers); a tampered layout pin makes the report unavailable;
- rejections: a missing allow_shared or allow_unverified_effect, out-of-range values, an unknown zone, an unknown
  damage multiplier name, a stale expect, a moved index row (record ownership), a second owner of the record (consumer
  scope), a changed zone name hash and a third-party value (CONFLICT).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from validate_entity_authoring_snapshot import lua, sources  # noqa: E402
import validate_attachment_authoring_snapshot as overlay_source  # noqa: E402

OUTPUT = ROOT / 'validation/helldiver-fields-snapshot.json'
RESEARCH = ROOT / 'research/avatar-fields-F5FEE03DCFDB.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local W=require('hd2runtime/domains/helldiver_writes')
local D=require('hd2runtime/domains/helldiver_fields')
local world_module=require('hd2runtime/runtime/event_world')
local entities=require('hd2runtime/core/entity_catalog')
local discover=require('hd2runtime/runtime/discover')
world_module.set_runtime(runtime)
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 noops=0,roundTrips={},rejections={},notes={}}
local function clean(why)return(tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ',''))end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 result.rejections[label]=clean(why):sub(1,200)
end
local ENTITY={resource='helldiver',helldiver='Helldiver',path='entity'}
local function zone_target(zone)return {resource='helldiver',helldiver='Helldiver',path='damage_zone',zone=zone}end
local function patch(target,field,expect,value,extra)
 local r={id='helldiver-'..field:gsub('[^%w]','_'),target=target,field=field,expect=expect,value=value,allow_shared=true,
  allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return W.validate_patch(r)
end
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=W.capture(runtime,reader,spec)
 local plan=W.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved,reader
end
local function component(name)return name=='AvatarComponentData'and D.avatar.layout or profile.components[name]end
local function table_of(owner,name)
 local c=component(name)
 return owner.base+c.offset+28,c.record_offset+c.records*c.stride,c
end
local function replaced(bytes,offset,value)return bytes:sub(1,offset)..value..bytes:sub(offset+#value+1)end
local worker=coroutine.create(function()
 reset();W.reset_for_tests()
 -- 1. Identity: the framing the generated table carries, the owners and the zone name hashes, on the live tables.
 do
  local reader=Reader.new(runtime)
  local roots=discover.locate(runtime,reader,profile,{entity=true})
  local owner=roots.entity
  local c=D.avatar.layout
  local framing=runtime.read(owner.base+c.offset-4,32)
  assert(b.u32(framing,0)==c.index and b.hex(framing:sub(5,32))==c.header,'AvatarComponentData framing differs')
  local spec=patch(ENTITY,'helldiver.speed.jog',3.2,3.2)
  local _,resolved=resolve(spec)
  local avatar=resolved.catalog.record(resolved.candidate,'AvatarComponentData')
  local hspec=patch(zone_target('head'),'zone.health',85,85)
  local _,hresolved=resolve(hspec)
  local health=hresolved.catalog.record(hresolved.candidate,'HealthComponentData')
  local zones={}
  for _,zone in ipairs(D.zones)do
   local at=D.zone.base+zone.index*D.zone.stride+D.zone.nameOffset
   assert(b.hex(health.bytes:sub(at+1,at+4))==zone.nameHash,'zone name hash differs: '..zone.id)
   zones[#zones+1]=zone.id
  end
  result.identity={framing=true,entityRow=resolved.candidate.entityRow,
   avatar={recordIndex=avatar.identity.recordIndex,indexRow=avatar.identity.indexRow,ownerCount=avatar.identity.ownerCount},
   health={recordIndex=health.identity.recordIndex,indexRow=health.identity.indexRow,ownerCount=health.identity.ownerCount},
   zones=zones}
 end
 -- 2. Every field instance is a guarded no-op: the live bytes are the reviewed vanilla value.
 for _,field in ipairs(D.fields)do
  local target=field.zone and zone_target(field.zone)or ENTITY
  local plan=resolve(patch(target,field.id,field.currentDefault,field.currentDefault))
  assert(plan.changes[1].already_desired,field.id..' '..tostring(field.zone)..' live value differs from the vanilla value')
  result.noops=result.noops+1
 end
 -- 3. Round trips: exact target bytes, the rest of the component table unchanged, protection restored, inverse
 --    restores.
 local function round_trip(key,spec,name)
  reset();W.reset_for_tests()
  local plan,resolved,reader=resolve(spec)
  local owner=plan.changes[1].owner
  local base,size,c=table_of(owner,name)
  local before=runtime.read(base,size)
  local expected=before
  for _,change in ipairs(plan.changes)do expected=replaced(expected,owner.base+change.offset-base,change.desired)end
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==#plan.changes and applied.non_target_bytes_unchanged
   and applied.protection_restored,key..' write failed: '..tostring(applied.reason))
  assert(next(protection)==nil,key..' a page kept a changed protection')
  local after=runtime.read(base,size)
  assert(after==expected,key..' bytes outside the targets changed')
  local changed=0
  for i=1,size do if before:byte(i)~=after:byte(i)then changed=changed+1 end end
  local record=resolved.catalog.record(resolved.candidate,name)
  local offsets,values={},{}
  for _,change in ipairs(plan.changes)do
   offsets[#offsets+1]=change.offset-record.offset
   local storage=change.label=='zone.health'and'i32'or change.label:find('damage_multiplier',1,true)and'u32'or'f32'
   values[#values+1]=b.value(after,owner.base+change.offset-base,storage)
  end
  local inverse=guarded.apply(runtime,guarded.inverse(plan))
  assert(inverse.status=='APPLIED'and inverse.protection_restored and next(protection)==nil,key..' rollback failed')
  assert(runtime.read(base,size)==before,key..' rollback did not restore the table')
  result.roundTrips[key]={writes=applied.writes,tableBytesChanged=changed,tableBytesCompared=size,
   otherRecordsUnchanged=c.records-1,targetOffsetsInRecord=offsets,written=values,
   protectionChanges=applied.protection_changes,protectionRestored=true,restored=true,notes=plan.notes or{},
   readerBytes=reader.bytes}
  reset()
 end
 round_trip('jog',patch(ENTITY,'helldiver.speed.jog',3.2,4.5),'AvatarComponentData')
 round_trip('stamina',W.validate_transaction({id='helldiver-stamina',target=ENTITY,allow_shared=true,
  allow_unverified_effect=true,changes={{field='helldiver.stamina.sprint_duration',expect=23,value=3},
  {field='helldiver.stamina.recover_delay',expect=1.5,value=0.5}}}),'AvatarComponentData')
 round_trip('head_damage_multiplier',patch(zone_target('head'),'zone.damage_multiplier','normal','none'),
  'HealthComponentData')
 round_trip('body_damage_multiplier_dps',patch(zone_target('body'),'zone.damage_multiplier_dps','normal','inherit'),
  'HealthComponentData')
 round_trip('body_health',patch(zone_target('body'),'zone.health',60,120),'HealthComponentData')
 round_trip('explosive_share',patch(ENTITY,'entity.explosive_damage_percentage',0.5,0.25),'HealthComponentData')
 -- 4. The private-copy report, and the notes of an avatar write and a type-only zone write.
 reset();W.reset_for_tests()
 local report=W.private_copies()
 result.privateCopies=report
 local plan=resolve(patch(ENTITY,'helldiver.speed.sprint',5.5,5.5))
 result.notes.avatar=plan.notes or{}
 plan=resolve(patch(zone_target('leg_left'),'zone.damage_multiplier','normal','normal'))
 result.notes.typeOnlyZone=plan.notes or{}
 plan=resolve(patch(zone_target('leg_left'),'zone.affects_main_health',0.85,0.85))
 result.notes.healthZone=plan.notes or{}
 -- A tampered layout pin: the report is unavailable and the note says so (the write itself is not refused).
 do
  local world=assert(world_module.open())
  local pin=D.privateCopies.pins[1]
  W.reset_for_tests()
  poke(world.game+pin.rva,'\204')
  local tampered=W.private_copies()
  assert(tampered.status=='unavailable'and tostring(tampered.reason):find('avatar manager layout changed',1,true),
   'a tampered pin did not make the report unavailable: '..tostring(tampered.reason))
  result.tamperedPin=tampered.reason
  local note_plan=resolve(patch(ENTITY,'helldiver.speed.sprint',5.5,5.5))
  assert(note_plan.notes and note_plan.notes[1]:find('could not check for private copies',1,true),
   'the tampered report gave no note')
  result.notes.unavailable=note_plan.notes
  reset();W.reset_for_tests()
 end
 -- 5. Rejections.
 rejects(function()patch(ENTITY,'helldiver.speed.jog',3.2,4.5,{allow_shared=false})end,'allow_shared','no allow_shared')
 rejects(function()patch(ENTITY,'helldiver.speed.jog',3.2,4.5,{allow_unverified_effect=false})end,
  'allow_unverified_effect','no allow_unverified_effect')
 rejects(function()patch(ENTITY,'helldiver.speed.jog',3.2,10.5)end,'reviewed range','jog 10.5')
 rejects(function()patch(ENTITY,'helldiver.stamina.sprint_duration',23,0)end,'reviewed range','sprint duration 0')
 rejects(function()patch(ENTITY,'helldiver.speed.jog',3.2,0/0)end,'finite','jog NaN')
 rejects(function()patch(zone_target('tail'),'zone.health',85,90)end,'UNKNOWN_ZONE','unknown zone')
 rejects(function()patch(zone_target('head'),'zone.damage_multiplier','normal','armoured')end,
  'UNKNOWN_DAMAGE_MULTIPLIER','unknown damage multiplier name')
 rejects(function()patch(ENTITY,'helldiver.speed.jog',3.0,4.5)end,'expect differs','stale expect')
 local function tamper(label,spec,name,at,bytes,needle)
  reset();W.reset_for_tests()
  local _,resolved=resolve(spec)
  local record=resolved.catalog.record(resolved.candidate,name)
  local c=component(name)
  local base=record.owner.base+c.offset+28
  poke(at(record,base,c),bytes(record,c))
  rejects(function()resolve(spec)end,needle,label)
  reset()
 end
 local jog=patch(ENTITY,'helldiver.speed.jog',3.2,4.5)
 local head=patch(zone_target('head'),'zone.damage_multiplier','normal','none')
 tamper('avatar index row moved',jog,'AvatarComponentData',function(record,base)return base+record.identity.indexRow*16+8 end,
  function()return b.encode(1,'u32')end,'record ownership changed')
 tamper('avatar record gains a second owner',jog,'AvatarComponentData',function(_,base)return base end,
  function()return b.unhex('1111111111111111')..b.encode(0,'u32')..b.encode(0,'u32')end,'consumer scope changed')
 tamper('health index row moved',head,'HealthComponentData',function(record,base)return base+record.identity.indexRow*16+8 end,
  function(record)return b.encode(record.identity.recordIndex+1,'u32')end,'record ownership changed')
 tamper('zone name hash changed',head,'HealthComponentData',function(record)
   return record.owner.base+record.offset+D.zone.base+D.zone.nameOffset end,
  function()return b.unhex('01020304')end,'damage zone identity changed')
 tamper('avatar third-party value',jog,'AvatarComponentData',function(record)return record.owner.base+record.offset+16 end,
  function()return b.encode(7.25,'f32')end,'CONFLICT')
 tamper('zone third-party value',head,'HealthComponentData',function(record)
   return record.owner.base+record.offset+D.zone.base+196 end,function()return b.encode(1,'u32')end,'CONFLICT')
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def expected_copies(research):
    """{snapshot: [(entity, avatar copy, health copy)]} from the research observations."""
    out = {}
    for observation in research['observations']:
        manager = observation['avatarManager']
        out[observation['snapshot']] = {'simulated': manager['simulatedHere'], 'avatars': sorted(
            (int(a['entity'], 16), a['privateCopy'] is not None, a['healthPrivateCopy'])
            for a in manager['avatars'] if a['simulatedHere'])}
    return out


def validate_one(snapshot: Path, expected: dict) -> dict:
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\n' + PROGRAM)
    report = json.loads(execute(program.encode()))
    problems = []
    copies = report.get('privateCopies') or {}
    if copies.get('status') != 'checked':
        problems.append('the private-copy report is unavailable: %s' % copies.get('reason'))
    else:
        got = sorted((a['entity'], a['avatar_copy'], bool(a.get('health_copy'))) for a in copies.get('avatars', []))
        if copies.get('simulated') != expected['simulated'] or got != expected['avatars']:
            problems.append('private copies %r differ from the research %r' % (got, expected))
    has_copy = any(avatar for _, avatar, _ in expected['avatars'])
    if bool(report['notes']['avatar']) != has_copy:
        problems.append('the avatar write note %r does not match the private copy' % report['notes']['avatar'])
    if report['notes']['typeOnlyZone']:
        problems.append('a type-only zone field got a private-copy note')
    if any(health for _, _, health in expected['avatars']) != bool(report['notes']['healthZone']):
        problems.append('the health zone note does not match the health private copy')
    report['status'] = 'VALIDATED' if not problems else 'FAILED'
    report['problems'] = problems
    return report


def validate(snapshots=None) -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    expected = expected_copies(research)
    names = snapshots or research['source']['snapshots']
    results = {name: validate_one(build_profile.snapshot_directory() / name, expected[name]) for name in names}
    failed = sorted(name for name, item in results.items() if item['status'] != 'VALIDATED')
    return {'status': 'VALIDATED' if not failed else 'FAILED', 'snapshots': len(results), 'failed': failed,
        'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='append', help='a snapshot file name (default: every research snapshot)')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    for name, item in sorted(result['results'].items()):
        print(item['status'], name, '; '.join(item['problems']))
    print(result['status'], len(result['failed']), 'failed of', result['snapshots'])
    if result['status'] != 'VALIDATED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
