"""Exercise the armor stats (hd2.armor_stats; docs/armor-stats.md) through the production modules
(domains/armor_stats_writes.lua, runtime/armor_stats.lua) on every retained snapshot of the build.

On a copy-on-write memory overlay of each snapshot (no game process, no real writes):

- proof: the research's instruction pins, the slot-map pins this feature adds and the consumers' constants hold in
  game.dll; the three tables and the damage curve hold their vanilla bytes;
- the image pages: the protection of the tables' and the curve's pages (PAGE_EXECUTE_READWRITE in every retained
  snapshot), and a guarded transaction aimed directly at the heavy armor entry is REJECTED before any page is opened
  (failed=protection; nothing written, no protection change);
- every armor kit (135): found at its research index with its passive and body count; every armor slot's pieces hold
  the research's vanilla weight (one capture, a guarded no-op per kit); the live stats the Lua replicas give equal the
  research's census (rating, speed, stamina regen, the gameplay factors, the damage multiplier, the class label);
- round trips: RS-100 Sanctioner's torso light -> heavy (every body's torso piece) and FS-37 Ravager all heavy in one
  transaction: exactly the target bytes change, no page protection changes, the plan note gives the new stats, the
  live describe follows (rating), the guarded inverse restores the original bytes;
- the local player (where the snapshot has one): the avatar slot through the game's own map, armor bonus 0 and the
  stamina factor the kit derives; stamina_factor 0.5 and armor_bonus 2 written (exact bytes), restored to the game's
  values; a third-party stamina value refused (UNEXPECTED_STATE);
- rejections: no allow_shared, no allow_unverified_effect, an out-of-range or unknown weight, a stale expect, an
  unknown kit or class, an ambiguous kit name, a class or curve change without its acknowledgements or out of range, a
  third-party piece weight (CONFLICT), a moved kit (ARMOR_KIT_MOVED) and a tampered pin;
- the class tables and the curve (reviewed executable data, the user's decision of 2026-10-08): a guarded write to an
  UNREGISTERED table entry is refused (failed=protection, nothing written); through the domain (pins proved, the exact
  4-byte extent registered) the heavy armor value, the heavy stamina factor and the curve point at armor value 2 are
  written, exactly their 4 bytes change, no page protection changes, the live describe follows, the guarded inverse
  restores the original bytes.
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

OUTPUT = ROOT / 'validation/armor-stats-snapshot.json'
RESEARCH = ROOT / 'research/armor-stats-F5FEE03DCFDB.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]
WRITE_CHECK = "assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without writable page')"
assert WRITE_CHECK in OVERLAY
# A reviewed executable-data extent (core/page_protection.lua) is written in its page as mapped (0x40, never
# re-protected); anything else still needs a writable page.
OVERLAY = OVERLAY.replace(WRITE_CHECK, "local p=protection[at-at%PAGE] or original_protect(at-at%PAGE)\n"
    " assert(p==4 or (p==0x40 and require('hd2runtime/core/page_protection').reviewed_executable_data(at,#bytes)),"
    "'overlay write without writable page')")

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local W=require('hd2runtime/domains/armor_stats_writes')
local page_protection=require('hd2runtime/core/page_protection')
page_protection.reset_executable_data_for_tests()
local A=require('hd2runtime/runtime/armor_stats')
local D=require('hd2runtime/domains/armor_stats')
local api=require('hd2runtime/api/armor_stats')
local world_module=require('hd2runtime/runtime/event_world')
world_module.set_runtime(runtime)
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 kits={},roundTrips={},rejections={},player={}}
local function clean(why)return(tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ',''))end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 result.rejections[label]=clean(why):sub(1,240)
end
local function fresh()reset();A.reset_for_tests();world_module.set_runtime(runtime)end
local function kit_target(id)return {resource='armor_kit',armor_kit=id}end
local function slot_field(slot)return 'armor_kit.piece_weight.'..slot end
local function kit_transaction(id,changes,extra)
 local r={id='armor-'..id,target=kit_target(id),allow_shared=true,allow_unverified_effect=true,changes=changes}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return W.validate_transaction(r)
end
local function every_slot(kit,value)
 local changes={}
 for _,slot in ipairs(D.slots)do
  local w=kit.weights[slot]
  if w then changes[#changes+1]={field=slot_field(slot),expect=A.weight_name(w),value=value or A.weight_name(w)}end
 end
 return changes
end
local function resolve_many(specs)
 local reader=Reader.new(runtime)
 local resolved=W.capture_many(runtime,reader,specs)
 local plans={}
 for i,spec in ipairs(specs)do plans[i]=W.prepare(resolved[i],reader,spec)end
 reader.verify()
 return plans,resolved,reader
end
local function resolve(spec)
 local plans,resolved,reader=resolve_many({spec})
 return plans[1],resolved[1],reader
end
local function hexr(n)return string.format('%X',n)end
local worker=coroutine.create(function()
 fresh()
 -- 1. Proof and the tables.
 local world=assert(world_module.open())
 local proven,why=A.prove(world)
 assert(proven,'pins: '..tostring(why))
 local tables,points,vanilla=A.read_tables(world)
 assert(tables and vanilla,'the tables or the curve are not vanilla: '..tostring(points))
 result.proof={pins=#D.pins,constants=#D.constants,tablesVanilla=vanilla}
 -- 2. The image pages: their protection, and a guarded transaction aimed at the heavy armor entry.
 local pages={}
 for _,name in ipairs({'armor','speed','stamina'})do
  local r=runtime.query(world.game+D.tables[name].rva)
  pages[name]={protect=r.protect,type=r.type,regionRva=hexr(r.base-world.game),regionSize=hexr(r.size)}
 end
 local rc=runtime.query(world.game+D.curve.rva)
 pages.curve={protect=rc.protect,type=rc.type,regionRva=hexr(rc.base-world.game),regionSize=hexr(rc.size)}
 result.imagePages=pages
 do
  local r=runtime.query(world.game+D.tables.armor.rva)
  local owner={base=world.game,size=natives_image_size,type=r.type,protect=r.protect}
  local at=D.tables.armor.rva+8
  local bytes=runtime.read(world.game+D.tables.armor.rva,12)
  local before=counts.writes+counts.protection_changes
  local report=guarded.apply(runtime,{snapshots={{owner=owner,offset=D.tables.armor.rva,bytes=bytes}},changes={{
   label='armor_class.rating',owner=owner,offset=at,expected=b.encode(2,'f32'),desired=b.encode(0,'f32'),
   before=b.encode(2,'f32'),already_desired=false,identity={component='armor table',component_type='native_module_data',
   record_index=2,unique_owner=false,owner_count=0},chain={}}}})
  assert(report.status=='REJECTED'and report.writes==0 and report.protection_changes==0
   and counts.writes+counts.protection_changes==before,'a guarded write reached the armor table: '..tostring(report.status))
  assert(report.guard_failure and report.guard_failure:find('failed=protection',1,true),tostring(report.guard_failure))
  assert(runtime.read(world.game+D.tables.armor.rva,12)==bytes,'the armor table changed')
  result.imagePageGuard={status=report.status,reason=report.reason,guardFailure=report.guard_failure:gsub('0x%x+','0x?')}
 end
 -- 3. Every armor kit: one capture, a guarded no-op per kit; the live stats equal the research's.
 local specs={}
 for _,kit in ipairs(D.kits)do specs[#specs+1]=kit_transaction(kit.id,every_slot(kit))end
 local plans,resolved=resolve_many(specs)
 local mismatched={}
 for i,kit in ipairs(D.kits)do
  for _,change in ipairs(plans[i].changes)do assert(change.already_desired,kit.id..' '..change.label..' is not vanilla')end
  local live=resolved[i].live
  local stats=A.stats(live.pieces,tables,points,kit.passive,0)
  local v=kit.vanilla
  -- The research rounds the display numbers to 4 decimals and the factors to 6.
  local function near(a,c,e)return type(a)=='number'and math.abs(a-c)<=e end
  local same=near(stats.rating,v.rating,1e-4)and near(stats.speed,v.speed,1e-4)and near(stats.stamina_regen,v.stamina,1e-4)
   and near(stats.speed_factor,v.speedFactor,1e-6)and near(stats.stamina_factor,v.staminaFactor,1e-6)
   and near(stats.damage_multiplier,v.damageMultiplier,1e-6)and near(stats.armor_value,v.armorValue,1e-6)
   and stats.class==kit.class
  if not same then
   mismatched[#mismatched+1]=('%s (rating %s/%s speed %s/%s stamina %s/%s factors %s/%s %s/%s damage %s/%s A %s/%s class %s/%s)')
    :format(kit.id,tostring(stats.rating),tostring(v.rating),tostring(stats.speed),tostring(v.speed),
    tostring(stats.stamina_regen),tostring(v.stamina),tostring(stats.speed_factor),tostring(v.speedFactor),
    tostring(stats.stamina_factor),tostring(v.staminaFactor),tostring(stats.damage_multiplier),
    tostring(v.damageMultiplier),tostring(stats.armor_value),tostring(v.armorValue),tostring(stats.class),
    tostring(kit.class))
  end
  result.kits.pieces=(result.kits.pieces or 0)+#plans[i].changes
  result.kits.statsMatched=(result.kits.statsMatched or 0)+(same and 1 or 0)
 end
 assert(#mismatched==0,'live stats differ from the research for '..table.concat(mismatched,', '))
 result.kitCount=#D.kits
 -- 4. Round trips.
 local function round_trip(key,spec)
  fresh()
  local plan,res,reader=resolve(spec)
  local arrays={}
  for _,change in ipairs(plan.changes)do
   local base=change.owner.base+change.offset-0x10
   arrays[#arrays+1]={at=base,before=runtime.read(base,0x60)}
  end
  local whole={}
  for _,p in ipairs(res.live.pieces)do whole[#whole+1]={at=p.address,before=runtime.read(p.address,0x60)}end
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==#plan.changes and applied.non_target_bytes_unchanged
   and applied.protection_restored and applied.protection_changes==0,key..' write failed: '..tostring(applied.reason))
  local changed=0
  for _,p in ipairs(whole)do
   local after=runtime.read(p.at,0x60)
   for i=1,0x60 do if p.before:byte(i)~=after:byte(i)then changed=changed+1 end end
  end
  local targets={}
  for _,change in ipairs(plan.changes)do
   targets[#targets+1]=b.u32(runtime.read(change.owner.base+change.offset,4),0)
   assert(runtime.read(change.owner.base+change.offset,4)==change.desired,key..' target not written')
  end
  local live=A.describe_kit(res.kit)
  local inverse=guarded.apply(runtime,guarded.inverse(plan))
  assert(inverse.status=='APPLIED'and inverse.protection_restored,key..' rollback failed')
  for _,p in ipairs(whole)do assert(runtime.read(p.at,0x60)==p.before,key..' rollback did not restore a piece')end
  result.roundTrips[key]={writes=applied.writes,pieceBytesChanged=changed,piecesCompared=#whole,written=targets,
   protectionChanges=applied.protection_changes,restored=true,note=plan.notes and plan.notes[1],
   effect=plan.effect,liveAfter=live.stats,source=live.source,readerBytes=reader.bytes}
  assert(changed==applied.writes,key..' bytes outside the targets changed ('..changed..' bytes for '..applied.writes..' writes)')
  fresh()
 end
 round_trip('sanctioner_torso_heavy',kit_transaction('4DD749C6',{{field=slot_field('torso'),expect='light',value='heavy'}}))
 local ravager=A.kit_by_id['1F9BFA78']
 round_trip('ravager_all_heavy',kit_transaction('1F9BFA78',every_slot(ravager,'heavy')))
 assert(result.roundTrips.ravager_all_heavy.liveAfter.rating==150 and result.roundTrips.ravager_all_heavy.effect.rating==150
  and result.roundTrips.sanctioner_torso_heavy.liveAfter.class=='heavy','the live stats did not follow the write')
 -- 4b. The class tables and the curve: reviewed executable data, through the domain.
 local function image_round_trip(key,request,extent_rva,extent_size,check)
  fresh()
  local spec=W.validate_patch(request)
  local plan=resolve(spec)
  local base=world.game+extent_rva
  local before=runtime.read(base,extent_size)
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==#plan.changes and applied.non_target_bytes_unchanged
   and applied.protection_restored and applied.protection_changes==0,key..' write failed: '..tostring(applied.reason))
  local after=runtime.read(base,extent_size)
  local changed=0
  for i=1,extent_size do if before:byte(i)~=after:byte(i)then changed=changed+1 end end
  assert(changed>=1 and changed<=4*#plan.changes,key..': '..changed..' bytes changed')
  for _,change in ipairs(plan.changes)do
   assert(runtime.read(change.owner.base+change.offset,4)==change.desired,key..' target not written')
   assert(runtime.query(change.owner.base+change.offset).protect==page_protection.REVIEWED_EXECUTABLE,key..' page re-protected')
  end
  local live=check()
  local inverse=guarded.apply(runtime,guarded.inverse(plan))
  assert(inverse.status=='APPLIED'and inverse.protection_changes==0,key..' rollback failed')
  assert(runtime.read(base,extent_size)==before,key..' rollback did not restore the table')
  result.roundTrips[key]={writes=applied.writes,bytesChanged=changed,protectionChanges=applied.protection_changes,
   restored=true,note=plan.notes and plan.notes[1],liveAfter=live}
  fresh()
 end
 local function class_req(class,field,expect,value)
  return {id='class-'..class..'-'..field,target={resource='armor_class',armor_class=class},field='armor_class.'..field,
   expect=expect,value=value,allow_shared=true,allow_unverified_effect=true}
 end
 image_round_trip('heavy_rating_0',class_req('heavy','rating',2,0),D.tables.armor.rva,12,function()
  local c=A.describe_class(A.weight('heavy'))
  assert(c.rating.value==0 and c.rating.display==50 and c.damage_multiplier==1.25,'heavy rating did not follow: '
   ..tostring(c.rating.value))
  return {rating=c.rating.value,display=c.rating.display,damage=c.damage_multiplier}
 end)
 image_round_trip('heavy_stamina_0_5',class_req('heavy','stamina',1.5,0.5),D.tables.stamina.rva,12,function()
  local c=A.describe_class(A.weight('heavy'))
  assert(c.stamina.value==0.5 and c.stamina.display==150,'heavy stamina did not follow')
  return {stamina=c.stamina.value,display=c.stamina.display}
 end)
 image_round_trip('curve_at_2_0_5',{id='curve-2',target={resource='armor_damage_curve'},field='armor_damage_curve.at_2',
  expect=0.75,value=0.5,allow_shared=true,allow_unverified_effect=true},D.curve.rva,40,function()
  local cu=A.describe_curve()
  local at2
  for _,pt in ipairs(cu.points)do if pt.armor_value==2 then at2=pt.damage end end
  assert(at2==0.5,'the curve did not follow: '..tostring(at2))
  return {at_2=at2}
 end)
 -- 5. The local player.
 fresh()
 local seen,code,reason=A.observe_player()
 if not seen then
  result.player={status='unavailable',code=code,reason=reason}
 else
  result.player={status='checked',entity=seen.entity,avatar=seen.avatar,slot=seen.slot,armor_bonus=seen.armor_bonus,
   stamina_factor=seen.stamina_factor,kit=seen.armor_kit and seen.armor_kit.id,derived=seen.derived,
   effective=seen.effective_armor_value}
  assert(seen.armor_bonus==0 and seen.derived and A.same(seen.stamina_factor,seen.derived.stamina_factor),
   'the avatar members are not the game\'s own values')
  local r,c,w=A.write_player({stamina_factor=0.5,armor_bonus=2},false)
  assert(r and r.status=='APPLIED'and r.writes==2 and r.verified,'player write: '..tostring(c)..' '..tostring(w))
  local now=A.observe_player()
  assert(now.stamina_factor==0.5 and now.armor_bonus==2 and now.overridden,'the player write did not land')
  result.player.written={stamina_factor=now.stamina_factor,armor_bonus=now.armor_bonus,effective=now.effective_armor_value}
  local again=A.write_player({stamina_factor=1.5},false)
  assert(again and again.status=='APPLIED'and again.writes==1,'a second value over this Runtime\'s own was refused')
  local back=A.write_player({},true)
  assert(back and back.status=='APPLIED'and back.writes==2,'restore failed')
  local after=A.observe_player()
  assert(after.armor_bonus==0 and A.same(after.stamina_factor,seen.derived.stamina_factor)and not after.overridden,
   'restore did not put the game values back')
  -- A third-party value: refused.
  local s=A.read_player(assert(world_module.open()))
  poke(s.stamina.address,b.encode(0.9,'f32'))
  local none,rcode=A.write_player({stamina_factor=0.5},false)
  assert(none==nil and rcode=='UNEXPECTED_STATE','a third-party stamina value was overwritten: '..tostring(rcode))
  result.rejections['player third-party stamina']=rcode
  fresh()
 end
 -- 6. Rejections.
 local sanctioner=kit_target('4DD749C6')
 local function torso(extra,value,expect)
  return function()kit_transaction('4DD749C6',{{field=slot_field('torso'),expect=expect or'light',value=value or'heavy'}},extra)end
 end
 rejects(torso({allow_shared=false}),'allow_shared','no allow_shared')
 rejects(torso({allow_unverified_effect=false}),'allow_unverified_effect','no allow_unverified_effect')
 rejects(torso(nil,3),'UNKNOWN_WEIGHT','weight 3')
 rejects(torso(nil,'titanium'),'UNKNOWN_WEIGHT','unknown weight name')
 rejects(torso(nil,'heavy','medium'),'expect differs','stale expect')
 rejects(function()W.validate_patch{id='x',target=kit_target('DEADBEEF'),field=slot_field('torso'),expect='light',
  value='heavy',allow_shared=true,allow_unverified_effect=true}end,'UNKNOWN_ARMOR_KIT','unknown kit')
 rejects(function()api.kit('B-01 Tactical')end,'AMBIGUOUS_ARMOR_KIT','ambiguous kit name')
 rejects(function()api.class('titanium')end,'UNKNOWN_ARMOR_CLASS','unknown class')
 rejects(function()W.validate_patch{id='x',target=sanctioner,field='armor_kit.piece_weight.helmet',expect='light',
  value='heavy',allow_shared=true,allow_unverified_effect=true}end,'not exposed','a slot the kit has no piece in')
 for _,class in ipairs(D.classes)do
  for i,f in ipairs({'rating','speed','stamina'})do
   local vanilla=D.tables[({'armor','speed','stamina'})[i]].values[A.weight(class)+1]
   local v=W.validate_patch{id='x',target={resource='armor_class',armor_class=class},field='armor_class.'..f,
    expect=vanilla,value=vanilla,allow_shared=true,allow_unverified_effect=true}
   assert(v.target_kind=='armor_class'and v.changes[1].rva==D.tables[({'armor','speed','stamina'})[i]].rva
    +A.weight(class)*4,class..' '..f..' resolves to its entry')
  end
 end
 rejects(function()W.validate_patch{id='x',target={resource='armor_class',armor_class='heavy'},field='armor_class.rating',
  expect=2,value=0}end,'allow_shared','class without allow_shared')
 rejects(function()W.validate_patch{id='x',target={resource='armor_class',armor_class='heavy'},field='armor_class.rating',
  expect=2,value=9,allow_shared=true,allow_unverified_effect=true}end,'reviewed range','class rating 9')
 for _,point in ipairs(W.CURVE_KEYS)do
  local v=W.validate_patch{id='x',target={resource='armor_damage_curve'},field='armor_damage_curve.'..point.name,
   expect=A.curve(D.curve.points,point.key),value=1,allow_shared=true,allow_unverified_effect=true}
  assert(v.target_kind=='armor_damage_curve','curve '..point.name..' resolves')
  rejects(function()W.validate_patch{id='x',target={resource='armor_damage_curve'},field='armor_damage_curve.'..point.name,
   expect=A.curve(D.curve.points,point.key),value=1,allow_shared=true}end,'allow_unverified_effect',
   'curve '..point.name..' without allow_unverified_effect')
 end
 local spec=kit_transaction('4DD749C6',{{field=slot_field('torso'),expect='light',value='heavy'}})
 local function tamper(label,at,needle)
  fresh()
  local _,res=resolve(spec)
  local address,bytes=at(res)
  poke(address,bytes)
  rejects(function()resolve(spec)end,needle,label)
  fresh()
 end
 tamper('third-party piece weight',function(res)
   for _,p in ipairs(res.live.pieces)do if p.type==0 and p.slot==2 then return p.address+0x10,b.encode(1,'u32')end end
  end,'CONFLICT')
 tamper('kit moved',function(res)
   local manager=b.pointer(runtime.read(world.game+D.customization.globalRva,8),0)
   local kits=b.pointer(runtime.read(manager,8),0)
   return kits+res.kit.index*8,runtime.read(kits+(res.kit.index+1)*8,8)
  end,'ARMOR_KIT_MOVED')
 tamper('tampered pin',function()return world.game+D.pins[1].rva,'\204'end,'native armor code changed')
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def validate_one(snapshot: Path, research: dict) -> dict:
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    natives = (ROOT / 'domains/event_natives.lua').read_text(encoding='utf-8')
    size = int(natives.split('["imageSize"]=', 1)[1].split(',', 1)[0])
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\nlocal natives_image_size=' + str(size) + '\n' + PROGRAM)
    report = json.loads(execute(program.encode()))
    problems = []
    expected = next(s for s in research['snapshots'] if s['snapshot'] == Path(snapshot).name)
    player = report.get('player') or {}
    if expected['players'] and expected['players'][0]['avatars']:
        observed = expected['players'][0]
        avatar = observed['avatars'][0]
        if player.get('status') != 'checked':
            problems.append('the local player is unavailable: %s' % player.get('reason'))
        elif (player['avatar'] != int(avatar['avatar'], 16) or player['kit'] != observed['armorKit']
                or abs(player['stamina_factor'] - avatar['staminaFactor_0x53E900']) > 1e-6
                or abs(player['derived']['stamina_factor'] - observed['computed']['staminaFactor']) > 1e-6):
            problems.append('the player %r differs from the research %r' % (player, observed))
    for name, page in (report.get('imagePages') or {}).items():
        if page['protect'] not in (0x2, 0x4, 0x40):
            problems.append('the %s page has protection 0x%X' % (name, page['protect']))
    report['status'] = 'VALIDATED' if not problems else 'FAILED'
    report['problems'] = problems
    return report


def validate(snapshots=None) -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    names = snapshots or [s['snapshot'] for s in research['snapshots']]
    results = {name: validate_one(build_profile.snapshot_directory() / name, research) for name in names}
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
