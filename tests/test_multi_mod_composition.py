"""Several mods editing support, sentry, backpack and drone weapon data at once
(research/docs/support-sentry-conflict-F5FEE03DCFDB.md).

A user report: "ARC-3 Arc Thrower with AX/LAS-5 Rover: only the Arc Thrower works; looks like it conflicts with mods
that modify sentry turret values". These tests pin what the Runtime does with such combinations:

* names resolve exactly (no designation or prefix matching: 'ARC-3' is neither the Arc Thrower nor the A/ARC-3 Tesla
  Tower);
* the Arc Thrower, the Rover (backpack, drone and drone gun), the K-9 drone gun and the sentry turret, targeting and
  weapon records are independent native records, so separate mods compose: every write lands on its own bytes, no
  other byte changes, page protection is restored, and each mod's restore returns only its own bytes;
* where two catalogues do reach one native record (the Arc Thrower's stun status row is the Tesla Tower's), two mods
  with different values fail closed on the later one, and the CONFLICT names the mod and operation that hold the
  bytes and every other catalogued user of the record;
* the one record a catalogue marks unshared although another catalogue uses it (FLAM-66 Torcher / AX/FLAM-75 Hot Dog
  drone gun) is still accepted (the published contract), with a warning naming the other user.

The snapshot tests run on a copy-on-write overlay of the retained current-build snapshot (no game process).
"""
import json
from pathlib import Path
import sys
import unittest

from support import ROOT, run

sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402


class NameResolutionTests(unittest.TestCase):
    def test_names_resolve_by_exact_catalogue_key_only(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local function fails(fn,text)
 local ok,why=pcall(fn)
 assert(not ok,'resolved: '..text)
 return tostring(why)
end
-- The Arc Thrower, its call-in, and the Tesla Tower (designation A/ARC-3) are three distinct identities.
assert(hd2.support_weapon('ARC-3 Arc Thrower').weapon=='ARC-3 Arc Thrower')
assert(hd2.stratagem('ARC-3 Arc Thrower').stratagem=='ARC-3 Arc Thrower')
assert(hd2.stratagem('A/ARC-3 Tesla Tower').stratagem=='A/ARC-3 Tesla Tower')
assert(hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity().stratagem=='A/ARC-3 Tesla Tower')
-- Designations, partial names and the other item's name never resolve.
assert(fails(function()return hd2.support_weapon('ARC-3')end,'ARC-3'):find('unknown reviewed support weapon',1,true))
fails(function()return hd2.support_weapon('Arc Thrower')end,'Arc Thrower')
fails(function()return hd2.support_weapon('A/ARC-3 Tesla Tower')end,'Tesla as support weapon')
fails(function()return hd2.stratagem('ARC-3 Tesla Tower')end,'Tesla without A/')
fails(function()return hd2.stratagem('ARC-3')end,'ARC-3 stratagem')
fails(function()return hd2.stratagem('A/ARC-3')end,'A/ARC-3 stratagem')
fails(function()return hd2.backpack('AX/LAS-5')end,'AX/LAS-5')
fails(function()return hd2.backpack('Rover')end,'Rover')
fails(function()return hd2.backpack('AX/LAS-5 Rover / gun')end,'drone gun as backpack')
-- The Rover's drone gun is reached only through its carrier backpack, and is not the K-9's.
local rover=hd2.backpack('AX/LAS-5 Rover'):drone():weapon()
local k9=hd2.backpack('AX/ARC-3 K-9'):drone():weapon()
assert(rover.weapon=='AX/LAS-5 Rover / gun'and k9.weapon=='AX/ARC-3 K-9 / gun')
-- Every catalogue key's leading designation alone resolves to nothing.
local catalogues={
 {require('hd2runtime/domains/support_weapon_authoring').weapons,hd2.support_weapon},
 {require('hd2runtime/domains/stratagem_authoring').stratagems,hd2.stratagem},
 {require('hd2runtime/domains/entity_authoring').backpacks,hd2.backpack},
}
local checked=0
for _,pair in ipairs(catalogues)do
 for name in pairs(pair[1])do
  local designation=name:match('^(%S+)%s')
  if designation and not pair[1][designation]then
   local ok=pcall(pair[2],designation)
   assert(not ok,'designation resolved: '..designation..' (from '..name..')')
   checked=checked+1
  end
 end
end
assert(checked>=100,checked)
return 'ok'
'''), b'ok')


class SharedRecordIndexTests(unittest.TestCase):
    def test_reported_items_use_independent_native_records(self):
        result = json.loads(run(r'''
local records=require('hd2runtime/core/shared_records')
local json=require('hd2runtime/primary_mapper/json')
local function fields(list)
 local out={};for _,f in ipairs(list)do if f.editable~=false then out[#out+1]=f end end;return out
end
local groups={
 arc=fields(require('hd2runtime/domains/support_weapon_authoring').weapons['ARC-3 Arc Thrower'].fields),
 rover_gun=fields(require('hd2runtime/domains/vehicle_weapon_authoring').weapons['AX/LAS-5 Rover / gun'].fields),
 rover=fields(require('hd2runtime/domains/entity_authoring').backpacks['AX/LAS-5 Rover'].fields),
 k9_gun=fields(require('hd2runtime/domains/vehicle_weapon_authoring').weapons['AX/ARC-3 K-9 / gun'].fields),
}
local strat=require('hd2runtime/domains/stratagem_authoring').stratagems
local sentries={}
for name,entry in pairs(strat)do if entry.family=='sentry'then sentries[#sentries+1]=name end end
table.sort(sentries)
local out={sentries=sentries,others={},turret=0}
for key,list in pairs(groups)do
 out.others[key]={}
 for _,field in ipairs(list)do
  for _,group in ipairs(records.others(field))do
   out.others[key][#out.others[key]+1]=field.semanticFieldId..' -> '..group.resource..' '..group.target
  end
 end
 table.sort(out.others[key])
end
-- Sentry turret and targeting records belong to their sentry alone.
for _,name in ipairs(sentries)do
 for _,field in ipairs(strat[name].fields)do
  local path=field.target.path
  if path=='turret'or path=='targeting'then
   out.turret=out.turret+1
   assert(#records.others(field)==0,name..' '..field.semanticFieldId..' is shared')
   assert(field.shared==false and field.backing.uniqueOwner==true,name..' '..field.semanticFieldId)
  end
 end
end
return json.encode(out)
'''))
        # The Rover (backpack, drone, drone gun) and the K-9 drone gun share no native record with anything else.
        self.assertFalse(result['others']['rover_gun'])
        self.assertFalse(result['others']['rover'])
        self.assertFalse(result['others']['k9_gun'])
        # The Arc Thrower's only cross-catalogue record is its stun status row: the A/ARC-3 Tesla Tower's, and the
        # status's own definition (hd2.status_effect('stun_small'), 0.31.0).
        self.assertEqual(result['others']['arc'],
                         ['status.primary_status_37.duration -> status_effect stun_small',
                          'status.primary_status_37.duration -> stratagem A/ARC-3 Tesla Tower'])
        self.assertIn('A/ARC-3 Tesla Tower', result['sentries'])
        self.assertIn('A/LAS-98 Laser Sentry', result['sentries'])
        self.assertGreater(result['turret'], 40)

    def test_only_the_torcher_row_is_shared_without_its_catalogue_saying_so(self):
        result = json.loads(run(r'''
local records=require('hd2runtime/core/shared_records')
local json=require('hd2runtime/primary_mapper/json')
local out={}
for _,item in ipairs(records.unlisted_sharing())do
 local names={}
 for _,group in ipairs(item.others)do names[#names+1]=group.resource..' '..group.target end
 out[#out+1]={owner=item.entry.resource..' '..item.entry.target,field=item.entry.field,others=names}
end
return json.encode(out)
'''))
        owners = {(r['owner'], tuple(r['others'])) for r in result}
        self.assertEqual(owners, {('player_weapon FLAM-66 Torcher', ('vehicle_weapon AX/FLAM-75 Hot Dog / gun',))})
        self.assertEqual(len(result), 17)   # every writable field of the Torcher's DamageInfo row

    def test_cross_catalogue_users_of_shared_rows(self):
        self.assertEqual(run(r'''
local records=require('hd2runtime/core/shared_records')
local strat=require('hd2runtime/domains/stratagem_authoring').stratagems
local function field(entry,id)
 for _,f in ipairs(entry.fields)do if f.semanticFieldId==id then return f end end
 error('no field '..id)
end
local function names(f)
 local out={};for _,g in ipairs(records.others(f))do out[#out+1]=g.resource..' '..g.target end
 return ','..table.concat(out,',')..','
end
-- Sentry weapon rows that support weapons (and an Exosuit) also fire.
local laser=names(field(strat['A/LAS-98 Laser Sentry'],'damage.standard_damage'))
assert(laser:find(',support_weapon LAS-98 Laser Cannon,',1,true),laser)
local gatling=names(field(strat['A/G-16 Gatling Sentry'],'damage.standard_damage'))
for _,n in ipairs({'stratagem A/MG-43 Machine Gun Sentry','support_weapon MG-43 Machine Gun',
  'vehicle_weapon EXO-45 Patriot Exosuit / right_gun'})do assert(gatling:find(','..n..',',1,true),gatling)end
-- The Tesla Tower's stun row is the Arc Thrower's.
local tesla=names(field(strat['A/ARC-3 Tesla Tower'],'status.duration'))
assert(tesla==',status_effect stun_small,support_weapon ARC-3 Arc Thrower,',tesla)
-- An attack output's slot is another handle on its owner weapon's own row, never another user.
local arbitrator=names(field(require('hd2runtime/domains/player_weapon_authoring').weapons['AR-11 Arbitrator'],
 'terminal.primary.impact.explosion'))
assert(arbitrator==',,',arbitrator)
return 'ok'
'''), b'ok')


class ConflictMessageTests(unittest.TestCase):
    def test_conflict_names_holding_operation_and_other_users(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local ownership=require('hd2runtime/core/ownership')
local records=require('hd2runtime/core/shared_records')
local b=require('hd2runtime/core/bytes')
records.reset_claims()
local tesla=patches.validate({id='tesla-stun',allow_shared=true,
 target=hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():weapon('primary'):attack('primary_damage_status_1'),
 field=hd2.fields.status.duration,expect=1.5,value=2})
local arc=patches.validate({id='arc-stun',allow_shared=true,
 target=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary_status_37'),field=hd2.fields.status.duration,
 expect=1.5,value=3})
local change=arc.changes[1]
-- Nobody applied the observed bytes: the message says so, and names the record's other user.
local ok,why=pcall(ownership.expected,change,b.encode(2,'f32'))
why=tostring(why)
assert(not ok and why:find('CONFLICT: status.duration is neither expected nor desired',1,true),why)
assert(why:find('target support_weapon ARC-3 Arc Thrower',1,true),why)
assert(why:find('no HD2Runtime patch, transaction, plan or ensure applied these bytes this session',1,true),why)
assert(why:find('the same native record is also used by status_effect stun_small status.duration, stratagem A/ARC-3 '
 ..'Tesla Tower status.duration',1,true),why)
-- Another mod's operation applied them: it is named, with its target and value.
records.claim(tesla,'ensure','mods/carol/sentries')
ok,why=pcall(ownership.expected,change,b.encode(2,'f32'))
why=tostring(why)
assert(why:find('held by mods/carol/sentries ensure tesla-stun (stratagem A/ARC-3 Tesla Tower status.duration = 2)',
 1,true),why)
-- Bytes changed after that operation applied them: the last applier is named, and the outside change stated.
ok,why=pcall(ownership.expected,change,b.encode(9,'f32'))
why=tostring(why)
assert(why:find('last applied by mods/carol/sentries ensure tesla-stun',1,true)
 and why:find('changed since outside HD2Runtime',1,true),why)
-- The rule itself is unchanged: the reviewed and the desired bytes are still accepted.
assert(ownership.expected(change,change.expected)==change.expected)
assert(ownership.expected(change,change.desired)==change.expected)
-- A Rover drone gun field has no other user: no "also used by" part.
local rover=patches.validate({id='rover-rate',allow_unverified_effect=true,
 target=hd2.backpack('AX/LAS-5 Rover'):drone():weapon(),field=hd2.fields.beam.fire_rate,expect=60,value=120})
ok,why=pcall(ownership.expected,rover.changes[1],b.encode(90,'i32'))
why=tostring(why)
assert(not ok and not why:find('also used by',1,true)
 and why:find('target vehicle_weapon AX/LAS-5 Rover / gun',1,true),why)
records.reset_claims()
return 'ok'
'''), b'ok')

    def test_unlisted_sharing_is_warned_once_and_still_accepted(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local records=require('hd2runtime/core/shared_records')
-- The published contract: the Torcher's own damage row needs no allow_shared, and stays accepted.
local spec=patches.validate({id='torcher-damage',target=hd2.weapon('FLAM-66 Torcher'),
 field=hd2.fields.damage.player_standard_damage,expect=2,value=3})
local lines=records.warn_unlisted(spec,'patch','mods/test/torcher')
assert(#lines==1 and lines[1]:find('patch torcher-damage (mods/test/torcher): damage.standard_damage of '
 ..'player_weapon FLAM-66 Torcher is in a native record that vehicle_weapon AX/FLAM-75 Hot Dog / gun also uses',
 1,true),tostring(lines[1]))
assert(#records.warn_unlisted(spec,'patch','mods/test/torcher')==0,'warned twice')
-- Fields their catalogue already marks shared, and independent fields, are not warned.
local arc=patches.validate({id='arc-stun',allow_shared=true,
 target=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary_status_37'),field=hd2.fields.status.duration,
 expect=1.5,value=3})
assert(#records.warn_unlisted(arc,'patch','mods/test/arc')==0)
local rover=patches.validate({id='rover-rate',allow_unverified_effect=true,
 target=hd2.backpack('AX/LAS-5 Rover'):drone():weapon(),field=hd2.fields.beam.fire_rate,expect=60,value=120})
assert(#records.warn_unlisted(rover,'patch','mods/test/rover')==0)
-- The shared acknowledgement on the record's other side is unchanged.
local ok,why=pcall(patches.validate,{id='hotdog',allow_unverified_effect=true,
 target=hd2.backpack('AX/FLAM-75 Hot Dog'):drone():weapon():attack('primary'),
 field=hd2.fields.damage.player_standard_damage,expect=2,value=3})
assert(not ok and tostring(why):find('allow_shared',1,true),tostring(why))
return 'ok'
'''), b'ok')


# --------------------------------------------------------------------------------------------- snapshot overlay --
HARNESS = r'''
local LINES={}
print=function(...)local parts={}for i=1,select('#',...)do parts[#parts+1]=tostring((select(i,...)))end
 LINES[#LINES+1]=table.concat(parts,' ')end
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
-- Copy-on-write overlay with page protections (the contract of the options and packaged-runtime validators).
local PAGE=4096
local overlay,protection={},{}
local runtime={mode='snapshot-overlay'}
local counts={writes=0,protection_changes=0}
local simulated=0
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)return source.module_hash(handle)end
function runtime.monotonic_time()return simulated end
function runtime.query(at)
 local r,why=source.query(at)
 if not r or r.allocation_base==0 then return r,why end
 local low,high=r.base,r.base+r.size
 if next(protection)==nil then return r end
 local pages={}
 for page in pairs(protection)do if page>=low and page<high then pages[#pages+1]=page end end
 if #pages==0 then return r end
 table.sort(pages)
 for _,page in ipairs(pages)do
  if at>=page and at<page+PAGE then r.base=page;r.size=PAGE;r.protect=protection[page];return r end
  if page>at then high=math.min(high,page)else low=math.max(low,page+PAGE)end
 end
 r.base=low;r.size=high-low;return r
end
function runtime.read(at,n)
 local bytes,why=source.read(at,n)
 if not bytes then return nil,why end
 for address,value in pairs(overlay)do
  if address<at+n and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
  end
 end
 return bytes
end
function runtime.protect(page,size,value)
 counts.protection_changes=counts.protection_changes+1
 local old=protection[page]or original_protect(page)
 if value==original_protect(page)then protection[page]=nil else protection[page]=value end
 return old
end
function runtime.write(at,bytes)
 assert((protection[at-at%PAGE]or original_protect(at-at%PAGE))==4,'overlay write without writable page')
 counts.writes=counts.writes+1;overlay[at]=bytes
 return true,nil,#bytes
end
package.loaded['hd2runtime/runtime/windows_write']={create=function()return runtime end}
-- Mod Options Menu stand-in (the packaged-runtime validator's): toggles drive each mod's enable and restore.
local menu={api=1,version=1,max_mods=8,max_options=32,values={},callbacks={}}
function menu.register_option(id,spec)
 menu.values[id]=spec.type=='toggle'and spec.default==true or spec.default;return true
end
function menu.get(id)return menu.values[id]end
function menu.set(id,value)menu.values[id]=value;return true end
function menu.on_change(id,fn)
 menu.callbacks[id]=menu.callbacks[id]or{};table.insert(menu.callbacks[id],fn);return true
end
function menu.ready()return true end
function menu.apply(id,value)menu.values[id]=value;for _,fn in ipairs(menu.callbacks[id]or{})do fn(value,id)end end
rawset(_G,'ModOptionsMenu',menu)
local events=require('hd2runtime/runtime/events')
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local domains=require('hd2runtime/domains/write_domains')
local Reader=require('hd2runtime/runtime/reader')
local F=hd2.fields
local FRAME=1/60
local function frames(seconds)
 for _=1,math.floor(seconds/FRAME+0.5)do simulated=simulated+FRAME;update(FRAME)end
end
local function settle(handles,limit)
 local spent=0
 local function idle()
  for _,h in ipairs(handles)do
   if h.status=='running'or h.status=='waiting_for_options'or(h.status=='waiting'and(h.runs or 0)==0)then
    return false
   end
  end
  return true
 end
 frames(1)
 while not idle()and spent<(limit or 600)do frames(1);spent=spent+1 end
 return spent
end
-- The exact bytes a request writes, resolved read-only through its domain (no write, no protection change).
local function resolve(kind,body)
 local spec=(kind=='transaction'and transactions or patches).validate(body)
 local result
 local worker=coroutine.create(function()
  local reader=Reader.new(runtime)
  local domain=domains.for_kind(spec.kind)
  local resolved=domain.capture(runtime,reader,spec)
  local plan=domain.prepare(resolved,reader,spec);reader.verify()
  result={}
  for _,change in ipairs(plan.changes)do
   result[#result+1]={at=change.owner.base+change.offset,before=change.before,desired=change.desired,
    label=change.label}
  end
 end)
 repeat local ok,why=coroutine.resume(worker);assert(ok,why)until coroutine.status(worker)=='dead'
 return result
end
local function check(ok,message)if not ok then error(message,2)end end
'''


def snapshot_run(body):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    from validate_entity_authoring_snapshot import lua, sources
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(text) + ',' + lua(name) + '))(...) end' for name, text in sources().items())
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(build_profile.SNAPSHOT).resolve()) + '\n'
        + HARNESS + '\n' + body)
    return json.loads(execute(program.encode()))


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class MultiModSnapshotTests(unittest.TestCase):
    def test_independent_mods_compose_byte_exact_and_restore_their_own_bytes(self):
        result = snapshot_run(r'''
local arc=hd2.support_weapon('ARC-3 Arc Thrower')
local rover=hd2.backpack('AX/LAS-5 Rover')
local k9=hd2.backpack('AX/ARC-3 K-9')
local tesla=hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity()
local laser=hd2.stratagem('A/LAS-98 Laser Sentry'):deployed_entity()
local gatling=hd2.stratagem('A/G-16 Gatling Sentry'):deployed_entity()
local deposit=rover:describe().fields[1]
-- Four mods, deliberately reusing the same operation ids (ids are per mod).
local MODS={
 {owner='mods/alice/arc_thrower',page='alice_arc',ops={
  {'transaction',{id='op-1',target=arc:attack('primary'),allow_shared=true,changes={
   {field=F.arc.range,expect=55,value=80},{field=F.arc.chain_count,expect=1,value=3},
   {field=F.damage.player_standard_damage,expect=250,value=400}}}},
  {'patch',{id='op-2',target=arc,field=F.weapon.ergonomics,expect=50,value=70}},
  {'patch',{id='op-3',target=arc,field=F.charge.minimum_seconds,expect=0.699999988079071,value=0.5}}}},
 {owner='mods/bob/rover',page='bob_rover',ops={
  {'transaction',{id='op-1',target=rover:drone():weapon(),allow_unverified_effect=true,changes={
   {field=F.beam.fire_rate,expect=60,value=120},{field=F.heat.capacity,expect=200,value=400},
   {field=F.heat.heat_per_shot,expect=2,value=1}}}},
  {'patch',{id='op-2',target=rover:drone():weapon():attack('primary'),allow_shared=true,allow_unverified_effect=true,
   field=F.damage.player_standard_damage,expect=200,value=300}},
  {'patch',{id='op-3',target=rover,allow_unverified_effect=true,field=deposit.semanticFieldId,
   expect=deposit.currentDefault,value=deposit.currentDefault+1}}}},
 {owner='mods/carol/sentries',page='carol_sentries',ops={
  {'transaction',{id='op-1',target=laser:turret(),changes={
   {field=F.turret.yaw_speed,expect=80,value=160},{field=F.turret.pitch_speed,expect=50,value=100}}}},
  {'patch',{id='op-2',target=laser:targeting(),field=F.targeting.range,expect=50,value=100}},
  {'patch',{id='op-3',target=laser:weapon('primary'),field=F.heat.capacity,expect=250,value=500}},
  {'patch',{id='op-4',target=gatling:turret(),field=F.turret.yaw_speed,expect=80,value=120}},
  {'patch',{id='op-5',target=gatling:weapon('primary'),field=F.weapon.fire_rate,expect=1600,value=2000}},
  {'patch',{id='op-6',target=tesla:targeting(),field=F.targeting.range,expect=25,value=40}},
  {'patch',{id='op-7',target=tesla:weapon('primary'):attack('primary'),allow_shared=true,
   field=F.arc.range,expect=20,value=30}}}},
 {owner='mods/dave/k9',page='dave_k9',ops={
  {'patch',{id='op-1',target=k9:drone():weapon():attack('primary'),allow_shared=true,allow_unverified_effect=true,
   field=F.arc.range,expect=55,value=70}}}},
 -- A mod without options (plain hd2.ensure, as most exports are): always on, never restored.
 {owner='mods/erin/plain',plain=true,ops={
  {'patch',{id='op-1',target=gatling:targeting(),field=F.targeting.range,expect=75,value=100}},
  {'transaction',{id='op-2',target=rover:drone():weapon(),allow_unverified_effect=true,changes={
   {field=F.heat.cool_per_second,expect=50,value=80}}}}}},
}
-- Every target's exact bytes, resolved read-only before anything runs.
local targets,by_address={},{}
for m,mod in ipairs(MODS)do
 mod.targets={}
 for _,op in ipairs(mod.ops)do
  for _,t in ipairs(resolve(op[1],op[2]))do
   check(not by_address[t.at],'two operations resolved to the same bytes: '..t.label)
   check(t.before~=t.desired,mod.owner..' '..t.label..' is already its desired value')
   t.mod=m;by_address[t.at]=t;targets[#targets+1]=t;mod.targets[#mod.targets+1]=t
  end
 end
end
check(counts.writes==0 and next(overlay)==nil,'resolution wrote')
-- Register each mod inside its own scope, as the SDK wrapper does.
local handles={}
for _,mod in ipairs(MODS)do
 events.run_as(mod.owner,function()
  if not mod.plain then
   local page=hd2.options({id=mod.page,title=mod.page})
   mod.enabled=page:toggle({id='enabled',label='Enabled',default=true})
  end
  mod.handles={}
  for _,op in ipairs(mod.ops)do
   local request={enabled=mod.enabled};request[op[1]]=op[2]
   local h=hd2.ensure(request)
   mod.handles[#mod.handles+1]=h;handles[#handles+1]=h
  end
 end)
end
local function state(t)return runtime.read(t.at,#t.desired)end
local function expect_state(label)
 -- Each target holds its mod's desired bytes when the mod is enabled, else its original bytes; nothing else changed.
 for _,t in ipairs(targets)do
  local want=MODS[t.mod].on and t.desired or t.before
  check(state(t)==want,label..': '..MODS[t.mod].owner..' '..t.label..' is '..b.hex(state(t))..', not '..b.hex(want))
 end
 for at,bytes in pairs(overlay)do
  local t=by_address[at]
  check(t and #bytes==#t.desired,label..': a write landed outside every operation target')
  check(bytes==(MODS[t.mod].on and t.desired or t.before),label..': stale bytes at '..t.label)
 end
 check(next(protection)==nil,label..': page protection not restored')
end
for _,mod in ipairs(MODS)do mod.on=true end
local spent=settle(handles,900)
for _,mod in ipairs(MODS)do
 for index,h in ipairs(mod.handles)do
  check(h.status=='waiting'and h.runs==1 and h.result.status=='APPLIED',
   mod.owner..' operation '..index..' '..tostring(h.status)..' '..tostring(h.error))
 end
end
expect_state('all mods applied')
local applied_writes=counts.writes
check(applied_writes==#targets,'writes '..applied_writes..' for '..#targets..' targets')
local result={targets=#targets,operations=#handles,settleSeconds=spent,writes=applied_writes,restores={}}
-- Each mod's restore returns only its own bytes; the others keep theirs.
for _,mod in ipairs(MODS)do if not mod.plain then
 menu.apply(mod.page..'.enabled',false);mod.on=false
 settle(mod.handles,600)
 for _,h in ipairs(mod.handles)do check(h.status=='disabled'and h.restores==1,mod.owner..' did not restore: '
  ..tostring(h.status)..' '..tostring(h.error))end
 expect_state(mod.owner..' disabled')
 result.restores[#result.restores+1]=mod.owner
end end
-- Every optional mod off: the overlay holds the original bytes everywhere they wrote; the plain mod keeps its own.
for at,bytes in pairs(overlay)do
 local t=by_address[at]
 check(bytes==(MODS[t.mod].plain and t.desired or t.before),'not restored: '..t.label)
end
-- Re-enable one mod: it applies again while the others stay restored.
menu.apply('bob_rover.enabled',true);MODS[2].on=true
settle(MODS[2].handles,600)
expect_state('rover re-enabled')
for _,line in ipairs(LINES)do
 check(not line:find('CONFLICT',1,true)and not line:find('REJECTED',1,true),line)
end
result.protectionChanges=counts.protection_changes
source.close()
return json.encode(result)
''')
        self.assertEqual(result['operations'], 16)
        self.assertEqual(result['targets'], 21)
        self.assertEqual(result['writes'], 21)
        self.assertEqual(len(result['restores']), 4)

    def test_shared_row_edits_from_two_mods(self):
        result = snapshot_run(r'''
local arc_target=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary_status_37')
local tesla_target=hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():weapon('primary')
 :attack('primary_damage_status_1')
local arc_body={id='stun',allow_shared=true,target=arc_target,field=F.status.duration,expect=1.5,value=3}
local tesla_body={id='stun',allow_shared=true,target=tesla_target,field=F.status.duration,expect=1.5,value=2}
-- One native row behind both handles.
local a=resolve('patch',arc_body)[1];local t=resolve('patch',tesla_body)[1]
check(a.at==t.at,'the Arc Thrower and Tesla Tower stun rows resolved apart')
local out={}
-- Different values: the mod that applied first holds the row; the later one fails closed and names it. The sentry
-- mod is settled first so the order does not depend on the scheduler.
local alice,carol
events.run_as('mods/carol/sentries',function()carol=hd2.ensure({patch=tesla_body})end)
settle({carol},600)
check(carol.status=='waiting'and carol.result.status=='APPLIED','tesla '..tostring(carol.error))
events.run_as('mods/alice/arc_thrower',function()alice=hd2.ensure({patch=arc_body})end)
settle({alice},600)
check(alice.status=='rejected'and alice.result.code=='CONFLICT','arc '..tostring(alice.status))
check(runtime.read(a.at,4)==b.encode(2,'f32')and counts.writes==1,'the rejected mod wrote')
check(next(protection)==nil,'protection not restored')
out.conflict=alice.error
-- Equal values compose: the second finds its desired bytes (ALREADY_DESIRED) and writes nothing.
local equal
events.run_as('mods/erin/arc_thrower',function()equal=hd2.ensure({patch={id='stun-2',allow_shared=true,
 target=arc_target,field=F.status.duration,expect=1.5,value=2}})end)
settle({equal},600)
check(equal.status=='waiting'and equal.result.status=='ALREADY_DESIRED'and counts.writes==1,
 'equal value '..tostring(equal.status)..' '..tostring(equal.error))
-- The acknowledgement stays mandatory on both handles, at registration (no write).
local refused
events.run_as('mods/frank/no_ack',function()
 refused={hd2.ensure({patch={id='stun-3',target=arc_target,field=F.status.duration,expect=1.5,value=4}}),
  hd2.ensure({patch={id='stun-4',target=tesla_target,field=F.status.duration,expect=1.5,value=4}})}
end)
for _,h in ipairs(refused)do
 check(h.status=='rejected'and tostring(h.error):find('allow_shared',1,true),tostring(h.error))
end
out.writes=counts.writes
source.close()
return json.encode(out)
''')
        conflict = result['conflict']
        self.assertIn('CONFLICT: status.duration is neither expected nor desired', conflict)
        self.assertIn('target support_weapon ARC-3 Arc Thrower', conflict)
        self.assertIn('observed 2', conflict)
        self.assertIn('held by mods/carol/sentries ensure stun (stratagem A/ARC-3 Tesla Tower status.duration = 2)',
                      conflict)
        self.assertIn('the same native record is also used by status_effect stun_small status.duration, '
                      'stratagem A/ARC-3 Tesla Tower status.duration', conflict)
        self.assertEqual(result['writes'], 1)

    def test_catalogue_shared_records_are_one_native_address(self):
        result = snapshot_run(r'''
local strat=function(name)return hd2.stratagem(name):deployed_entity():weapon('primary')end
local pairs_={
 {'arc thrower / tesla tower stun',
  {id='a',allow_shared=true,target=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary_status_37'),
   field=F.status.duration,expect=1.5,value=1.5},
  {id='b',allow_shared=true,target=strat('A/ARC-3 Tesla Tower'):attack('primary_damage_status_1'),
   field=F.status.duration,expect=1.5,value=1.5}},
 {'torcher / hot dog damage (no allow_shared on the Torcher)',
  {id='a',target=hd2.weapon('FLAM-66 Torcher'),field=F.damage.player_standard_damage,expect=2,value=2},
  {id='b',allow_shared=true,allow_unverified_effect=true,
   target=hd2.backpack('AX/FLAM-75 Hot Dog'):drone():weapon():attack('primary'),
   field=F.damage.player_standard_damage,expect=2,value=2}},
 {'laser sentry / laser cannon damage',
  {id='a',allow_shared=true,target=strat('A/LAS-98 Laser Sentry'):attack('primary_damage'),
   field=F.damage.player_standard_damage,expect=350,value=350},
  {id='b',allow_shared=true,target=hd2.support_weapon('LAS-98 Laser Cannon'):attack('primary'),
   field=F.damage.player_standard_damage,expect=350,value=350}},
 {'gatling sentry / MG-43 damage',
  {id='a',allow_shared=true,target=strat('A/G-16 Gatling Sentry'):attack('primary_damage'),
   field=F.damage.player_standard_damage,expect=90,value=90},
  {id='b',allow_shared=true,target=hd2.support_weapon('MG-43 Machine Gun'):attack('primary'):projectile(),
   field=F.damage.player_standard_damage,expect=90,value=90}},
}
local out={}
for _,item in ipairs(pairs_)do
 local x=resolve('patch',item[2])[1];local y=resolve('patch',item[3])[1]
 out[item[1]]=x.at==y.at
end
-- The Rover drone gun's records are none of the sentries' or the Arc Thrower's.
local rover=resolve('transaction',{id='r',allow_unverified_effect=true,target=hd2.backpack('AX/LAS-5 Rover'):drone()
 :weapon(),changes={{field=F.beam.fire_rate,expect=60,value=60},{field=F.heat.capacity,expect=200,value=200}}})
local laser=resolve('patch',{id='l',target=hd2.stratagem('A/LAS-98 Laser Sentry'):deployed_entity():weapon('primary'),
 field=F.heat.capacity,expect=250,value=250})
local separate=true
for _,r in ipairs(rover)do for _,l in ipairs(laser)do if r.at==l.at then separate=false end end end
out['rover heat / laser sentry heat separate']=separate
source.close()
return json.encode(out)
''')
        for name, same in result.items():
            self.assertTrue(same, name)


if __name__ == '__main__':
    unittest.main()
