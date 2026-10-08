"""Armor stats (hd2.armor_stats; api/armor_stats.lua, runtime/armor_stats.lua, domains/armor_stats_writes.lua;
research/armor-stats-F5FEE03DCFDB.json): the generated domain against the research, the kit / class / curve targets
and their descriptors, the averager replicas, every refusal, the guarded transaction refusing an executable image page,
the per-player write on the offline event world (tests/event_world_fixture.lua) with a customization manager, a kit
and an avatar manager laid out as the domains describe, the snapshot overlay report, the wiring and the probe."""
import json
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE, SDK
from reference_format import lua as lua_literal

RESEARCH = json.loads((ROOT / 'research/armor-stats-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
OVERLAY = json.loads((ROOT / 'validation/armor-stats-snapshot.json').read_text(encoding='utf-8'))

# The offline world: the pins (this feature's and the passive store's), the vanilla tables and curve, the customization
# manager with the RS-100 Sanctioner at its research index (three bodies, all light, an undergarment piece), the local
# player's applied record, and the avatar manager with the local avatar (100) at slot 0 of its entity -> slot map.
WORLD = PRELUDE + r'''
local b=require('hd2runtime/core/bytes')
local RT=W.guarded_runtime()
require('hd2runtime/core/page_protection').reset_executable_data_for_tests()
local A=require('hd2runtime/runtime/armor_stats');A.reset_for_tests()
local D=require('hd2runtime/domains/armor_stats')
local PD=require('hd2runtime/domains/player_passives')
local MG,R=PD.manager,PD.record
for _,list in ipairs({D.pins,D.constants,PD.pins})do
    for _,pin in ipairs(list)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end
for _,t in pairs(D.tables)do W.write(W.GAME+t.rva,b.unhex(t.hex))end
W.write(W.GAME+D.curve.rva,b.unhex(D.curve.hex))
-- The tables' and the curve's pages are PAGE_EXECUTE_READWRITE, as in every retained snapshot (the curve spans two).
for _,extent in ipairs({{D.tables.armor.rva,12},{D.tables.speed.rva,12},{D.tables.stamina.rva,12},{D.curve.rva,40}})do
    for at=W.GAME+extent[1],W.GAME+extent[1]+extent[2]-1 do RT.protections[at-at%4096]=0x40 end
end
local SANCTIONER=A.kit_by_id['4DD749C6']
local MGR=W.alloc(0x1000)
W.write(W.GAME+MG.globalRva,W.u64(MGR))
local passives=W.alloc(8)
W.write(MGR+MG.passives,W.u64(passives)..W.u32(1))
local kits=W.alloc((SANCTIONER.index+1)*8)
local ROW=W.alloc(0x40)
W.write(kits+SANCTIONER.index*8,W.u64(ROW))
W.write(MGR+MG.kits,W.u64(kits)..W.u32(SANCTIONER.index+1))
local BODIES=W.alloc(3*0x18)
local PIECES={}
local slots={}
for slot in pairs(SANCTIONER.weights)do if slot~='cape'then slots[#slots+1]=slot end end
table.sort(slots)
local function slot_index(name)for i,s in ipairs(D.slots)do if s==name then return i-1 end end end
for i,body in ipairs({0,1,3})do
    local list={}
    if body==3 then list={{slot=1,type=0,weight=0}}
    else
        for _,slot in ipairs(slots)do list[#list+1]={slot=slot_index(slot),type=0,weight=SANCTIONER.weights[slot]}end
        list[#list+1]={slot=2,type=1,weight=0}       -- an undergarment piece: never averaged
    end
    local at=W.alloc(4096)      -- whole pages, as an allocation is in game
    for k,p in ipairs(list)do
        W.write(at+(k-1)*0x60+8,W.u32(p.slot)..W.u32(p.type)..W.u32(p.weight))
        p.address=at+(k-1)*0x60
    end
    PIECES[body]=list
    W.write(BODIES+(i-1)*0x18,W.u32(body)..W.u32(0)..W.u64(at)..W.u32(#list)..W.u32(0))
end
W.write(ROW,W.u32(0x4DD749C6));W.write(ROW+0x1C,W.u32(SANCTIONER.passive));W.write(ROW+0x28,W.u32(0))
W.write(ROW+0x30,W.u64(BODIES)..W.u32(3)..W.u32(0))
local function set_weight(weight)
    for _,body in ipairs({0,1,3})do
        for _,p in ipairs(PIECES[body])do if p.type==0 then W.write(p.address+0x10,W.u32(weight))end end
    end
end
-- The local player's applied record (player entity 10, body type 0, armor kit the Sanctioner).
local ENTITY=10
local SLOTS=W.alloc(8*8)
W.write(SLOTS+((ENTITY*2)%8)*8,W.u32(ENTITY)..W.u32(0))
W.write(MGR+MG.map,W.u64(SLOTS)..W.u32(8)..W.u32(0)..W.u32(2))
local DESCRIPTOR=W.alloc(0x18)
W.write(DESCRIPTOR+8,W.u32(ENTITY))
W.write(MGR+MG.descriptors,W.u64(DESCRIPTOR))
W.write(MGR+MG.recordCount,W.u32(1))
local RECORD=MGR+MG.applied
W.write(RECORD,W.u32(0));W.write(RECORD+R.armorKit,W.u32(0x4DD749C6));W.write(RECORD+R.armorPassive,W.u32(32))
-- The avatar manager: avatar 100 at slot 0 (bucket (100 x 1) % 8 = 4).
local AV=D.avatar
local AVM=W.alloc(AV.armorModifier+AV.armorStride*AV.maxSlots)
W.write(W.GAME+AV.globalRva,W.u64(AVM))
local BUCKETS=W.alloc(8*8)
W.write(BUCKETS+4*8,W.u32(100)..W.u32(0))
W.write(AVM+AV.map,W.u64(BUCKETS)..W.u32(8)..W.u32(0)..W.u32(1))
local STAMINA,ARMOR=AVM+AV.staminaFactor,AVM+AV.armorModifier
W.write(STAMINA,W.f32(0.75));W.write(ARMOR,W.f32(0))
W.players({{peer=LOCAL,avatar=100}},LOCAL)
local function f32_at(at)return b.value(W.read(at,4),0,'f32')end
local function writes()return#W.runtime.writes end
local me=hd2.armor_stats.player()
'''


def lua(body):
    return run(WORLD + body)


def probe():
    """proof/ArmorStatProbe inside the SDK's addon wrapper, exactly as its built ZIP ships it."""
    project = ROOT / 'proof/ArmorStatProbe'
    spec = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
    return SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'],
        (project / 'src/addon.lua').read_text(encoding='utf-8-sig')), spec['resource']


class ArmorStatsDataTests(unittest.TestCase):
    def test_the_research_is_read_only_and_pinned_in_every_snapshot(self):
        self.assertEqual(RESEARCH['writes'], [])
        self.assertEqual(RESEARCH['pinCount'], 177)
        self.assertEqual(set(map(len, RESEARCH['pinnedBytesMismatchPerSnapshot'].values())), {0})
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)

    def test_the_domain_is_generated_from_the_research(self):
        import generate_armor_stats
        self.assertEqual(generate_armor_stats.generate(check=True), [])

    def test_the_generated_tables_kits_and_pins(self):
        self.assertEqual(run(r'''
local D=require('hd2runtime/domains/armor_stats')
assert(#D.kits==135,'every armor kit: '..#D.kits)
assert(D.tables.armor.rva==0x21CB160 and D.tables.speed.rva==0x2160678 and D.tables.stamina.rva==0x21C6F78)
assert(table.concat(D.tables.armor.values,',')=='0,1,2'and table.concat(D.tables.stamina.values,',')=='0.75,1,1.5')
assert(D.curve.rva==0x21CEFF0 and #D.curve.points==5 and D.curve.points[1][1]==3 and D.curve.points[5][2]==1.66)
-- The research's 166 instruction pins and this feature's 12 slot-map pins.
local slot=0
for _,pin in ipairs(D.pins)do if pin.label:find('avatarSlot',1,true)then slot=slot+1 end end
assert(#D.pins==178 and slot==12,#D.pins..' '..slot)
assert(D.avatar.map==0xF8 and D.avatar.staminaFactor==0x53E900 and D.avatar.staminaStride==0x1238
    and D.avatar.armorModifier==0x546AC4 and D.avatar.armorStride==0x1B8)
assert(D.passives[1].name=='EXTRA PADDING'and D.passives[1].armor[1].type=='Add'and D.passives[1].armor[1].value==1)
local s=require('hd2runtime/runtime/armor_stats').kit_by_id['4DD749C6']
assert(s.name=='RS-100 SANCTIONER'and s.passive==32 and s.bodies==3 and s.weights.torso==0 and s.vanilla.rating==50)
assert(D.ambiguousNames['b-01 tactical']and #D.ambiguousNames['b-01 tactical']==9)
return 'ok'
''').decode().splitlines()[0], 'ok')


class ArmorStatsApiTests(unittest.TestCase):
    def test_targets_descriptors_formulas_and_describe(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local A=require('hd2runtime/runtime/armor_stats')
assert(hd2.armor_class==hd2.armor_stats.class)
local kit=hd2.armor_stats.kit('fs-37 ravager')
assert(kit.resource=='armor_kit'and kit.armor_kit=='1F9BFA78')
assert(hd2.armor_stats.kit(0x1F9BFA78).armor_kit=='1F9BFA78'and hd2.armor_stats.kit('0x1f9bfa78').armor_kit=='1F9BFA78')
local d=kit:describe()
assert(d.source=='research'and d.stats.rating==50 and d.stats.speed==550 and d.stats.stamina_regen==125
    and d.stats.damage_multiplier==1.25 and d.stats.class=='light'and d.passive.id==6 and d.liveTested==false)
assert(#d.fields==9 and d.fields[1].semanticFieldId=='armor_kit.piece_weight.cape'and d.fields[1].editable==true
    and d.fields[1].currentDefault=='light'and d.fields[1].acknowledgements[1]=='allow_shared')
-- The change helper: every slot, the vanilla expect, no acknowledgement.
local changes=kit:changes('heavy')
assert(#changes==9)
for _,c in ipairs(changes)do
    assert(c.expect=='light'and c.value=='heavy'and c.allow_shared==nil and c.allow_unverified_effect==nil)
end
assert(#kit:changes(2,{'torso'})==1)
assert(not pcall(kit.changes,kit,'heavy',{'helmet'}))
assert(not pcall(kit.changes,kit,'titanium'))
-- Preview: the torso heavy moves the armor value by 2/7 (7 counted pieces), all heavy gives heavy armor.
local p=kit:preview({torso='heavy'})
assert(math.abs(p.armor_value-2/7)<1e-6 and math.abs(p.rating-(50+100/7))<1e-4,tostring(p.rating))
local all={}
for _,c in ipairs(changes)do all[c.field:match('[^.]+$')]='heavy'end
local h=kit:preview(all)
assert(h.rating==150 and h.speed==450 and h.stamina_regen==50 and h.damage_multiplier==0.75 and h.class=='heavy')
-- A kit with Extra Padding and a mixed kit from the research census.
for _,item in ipairs(hd2.armor_stats.kits())do
    local k=A.kit_by_id[item.id]
    local s=A.stats(A.research_pieces(k),{armor={0,1,2},speed={1.1,1,0.9},stamina={0.75,1,1.5}},
        require('hd2runtime/domains/armor_stats').curve.points,k.passive,0)
    assert(math.abs(s.rating-item.vanilla.rating)<1e-3 and math.abs(s.armor_value-item.vanilla.armor_value)<1e-5,
        item.id..' '..s.rating..' '..item.vanilla.rating)
end
-- The curve and PassiveValue.
local pts=require('hd2runtime/domains/armor_stats').curve.points
assert(A.curve(pts,3)==0.65 and A.curve(pts,9)==0.65 and A.curve(pts,-2)==1 and A.curve(pts,1)==1
    and math.abs(A.curve(pts,0.5)-1.125)<1e-9 and math.abs(A.curve(pts,-0.5)-1.455)<1e-9)
assert(A.passive_value({{type='Add',value=1}},2)==3 and A.passive_value({{type='Set',value=1},{type='Multiply',value=2}},0)==2)
-- Classes and the curve: read-only.
local c=hd2.armor_class('heavy'):describe()
assert(c.source=='research'and c.rating.value==2 and c.rating.display==150 and c.speed.display==450
    and c.stamina.display==50 and c.damage_multiplier==0.75 and c.editable==true
    and c.executable_data:find('PAGE_EXECUTE_READWRITE',1,true))
local f=hd2.armor_stats.class('light'):fields()
assert(#f==3 and f[1].semanticFieldId=='armor_class.rating'and f[1].editable==true and f[1].min==-1 and f[1].max==4
    and f[2].min==0.5 and f[3].max==2 and f[1].executableData==true)
local cu=hd2.armor_stats.damage_curve():describe()
assert(#cu.points==5 and cu.points[1].armor_value==-1 and cu.points[5].damage==0.65 and #cu.fields==5)
assert(hd2.fields.armor_kit.piece_weight_torso=='armor_kit.piece_weight.torso'
    and hd2.fields.armor_class.stamina=='armor_class.stamina'
    and hd2.fields.armor_damage_curve.at_minus_1=='armor_damage_curve.at_minus_1')
return 'ok'
''').decode().splitlines()[0], 'ok')

    def test_refusals(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/armor_stats_writes')
local F=hd2.fields
local kit=hd2.armor_stats.kit('4DD749C6')
local function refused(request,needle,multiple)
    local ok,why=pcall(multiple and W.validate_transaction or W.validate_patch,request)
    assert(not ok and tostring(why):find(needle,1,true),needle..': '..tostring(why))
end
local function torso(extra)
    local r={id='t',target=kit,field=F.armor_kit.piece_weight_torso,expect='light',value='heavy',allow_shared=true,
        allow_unverified_effect=true}
    for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
    return r
end
local spec=W.validate_patch(torso())
assert(spec.kind=='armor_kit'and spec.armor_kit=='4DD749C6'and spec.changes[1].weight==2)
assert(W.validate_patch(torso({expect=0,value=1})).changes[1].weight==1)
refused(torso({allow_shared=false}),'allow_shared')
refused(torso({allow_unverified_effect=false}),'allow_unverified_effect')
refused(torso({value=3}),'UNKNOWN_WEIGHT')
refused(torso({value='titanium'}),'UNKNOWN_WEIGHT')
refused(torso({value=1.5}),'UNKNOWN_WEIGHT')
refused(torso({expect='medium'}),'expect differs')
refused(torso({field='armor_kit.piece_weight.helmet'}),'not exposed')
refused(torso({colour='red'}),'unsupported option')
refused(torso({target={resource='armor_kit',armor_kit='DEADBEEF'}}),'UNKNOWN_ARMOR_KIT')
refused(torso({target={resource='armor_kit',armor_kit='B-01 Tactical'}}),'AMBIGUOUS_ARMOR_KIT')
refused(torso({target={resource='armor_kit',armor_kit='4DD749C6',extra=1}}),'unsupported armor stats target identity')
refused({id='t',target=kit,allow_shared=true,allow_unverified_effect=true,changes={
    {field=F.armor_kit.piece_weight_torso,expect='light',value='heavy'},
    {field=F.armor_kit.piece_weight_torso,expect='light',value='medium'}}},'twice',true)
assert(not pcall(hd2.armor_stats.kit,'nope')and not pcall(hd2.armor_stats.kit,'B-01 Tactical'))
local ok,why=pcall(hd2.armor_stats.class,'titanium')
assert(not ok and why:find('UNKNOWN_ARMOR_CLASS',1,true))
-- Class and curve fields: validated in full (acknowledgements, expect, range); written as reviewed executable data.
local heavy=hd2.armor_class('heavy')
local function class(extra)
    local r={id='c',target=heavy,field=F.armor_class.rating,expect=2,value=0,allow_shared=true,allow_unverified_effect=true}
    for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
    return r
end
local D=require('hd2runtime/domains/armor_stats')
for _,c in ipairs({{class(),'armor',2},{class({field=F.armor_class.speed,expect=0.9,value=1.2}),'speed',2},
        {class({field=F.armor_class.stamina,expect=1.5,value=0.5}),'stamina',2}})do
    local v=W.validate_patch(c[1])
    assert(v.target_kind=='armor_class'and v.changes[1].rva==D.tables[c[2]].rva+c[3]*4
        and v.changes[1].table==c[2],c[2])
end
refused(class({allow_shared=false}),'allow_shared')
refused(class({allow_unverified_effect=false}),'allow_unverified_effect')
refused(class({value=9}),'reviewed range')
refused(class({value=0/0}),'finite')
refused(class({expect=1}),'expect differs')
refused(class({target={resource='armor_class',armor_class='titanium'}}),'UNKNOWN_ARMOR_CLASS')
local cv=W.validate_patch({id='k',target=hd2.armor_stats.damage_curve(),field=F.armor_damage_curve.at_2,expect=0.75,
    value=0.1,allow_shared=true,allow_unverified_effect=true})
assert(cv.target_kind=='armor_damage_curve'and cv.changes[1].table=='curve')
refused({id='k',target=hd2.armor_stats.damage_curve(),field=F.armor_damage_curve.at_2,expect=0.75,value=9,
    allow_shared=true,allow_unverified_effect=true},'reviewed range')
-- The public entry points refuse the same way (no acknowledgement is ever added).
local watch=hd2.patch({id='no-ack',target=kit,field=F.armor_kit.piece_weight_torso,expect='light',value='heavy'})
assert(watch==nil or watch.status=='rejected',tostring(watch and watch.status))
local class_watch=hd2.patch(class())
assert(not(class_watch.error and class_watch.error:find('WRITE_REFUSED_IMAGE_PAGE',1,true)),tostring(class_watch.error))
-- Per-player options.
local me=hd2.armor_stats.player()
assert(me:set({stamina_factor=0.5}).code=='ACKNOWLEDGEMENT_REQUIRED')
assert(me:set({stamina_factor=9,allow_unverified_effect=true}).code=='OUT_OF_RANGE')
assert(me:set({armor_bonus=-2,allow_unverified_effect=true}).code=='OUT_OF_RANGE')
assert(me:set({armor_bonus=0/0,allow_unverified_effect=true}).code=='OUT_OF_RANGE')
assert(me:set({allow_unverified_effect=true}).code=='INVALID_OPTION')
assert(me:set({speed_factor=1,allow_unverified_effect=true}).code=='INVALID_OPTION')
assert(me:set(5).code=='INVALID_OPTION')
return 'ok'
''').decode().splitlines()[0], 'ok')


class ImagePageGuardTests(unittest.TestCase):
    def test_an_executable_image_page_is_refused_before_any_page_is_opened(self):
        # game.dll's tables sit in PAGE_EXECUTE_READWRITE pages at run time; a guarded write never targets one.
        self.assertEqual(run(r'''
local b=require('hd2runtime/core/bytes')
local guarded=require('hd2runtime/core/guarded_transaction')
local GAME=0x10000000
local memory={[GAME+0x21CB160]=b.unhex('000000000000803f00000040')}
local protects,writes=0,0
local runtime={}
function runtime.query(at)
    return {base=GAME+0x2112000,size=0x528000,state=0x1000,type=0x1000000,protect=0x40,allocation_base=GAME,
        allocation_protect=0x80}
end
function runtime.read(at,n)
    local bytes=memory[GAME+0x21CB160]
    return bytes:sub(at-(GAME+0x21CB160)+1,at-(GAME+0x21CB160)+n)
end
function runtime.protect()protects=protects+1;return 0x40 end
function runtime.write()writes=writes+1;return true,nil,4 end
function runtime.system_info()return 4096 end
local owner={base=GAME,size=0x4700000,type=0x1000000,protect=0x40}
local report=guarded.apply(runtime,{snapshots={{owner=owner,offset=0x21CB160,bytes=memory[GAME+0x21CB160]}},
    changes={{label='armor_class.rating',owner=owner,offset=0x21CB168,expected=b.encode(2,'f32'),
    desired=b.encode(0,'f32'),before=b.encode(2,'f32'),already_desired=false,identity={},chain={}}}})
assert(report.status=='REJECTED'and report.writes==0 and protects==0 and writes==0,report.status)
assert(report.guard_failure and report.guard_failure:find('failed=protection',1,true),tostring(report.guard_failure))
assert(report.protection_restored==true)
return 'ok'
''').decode().splitlines()[0], 'ok')


class ArmorPlayerTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_read_set_restore_and_the_kit_now(self):
        self.check(r'''
local seen=assert(me:describe())
assert(seen.entity==ENTITY and seen.avatar==100 and seen.slot==0 and seen.armor_bonus==0 and seen.stamina_factor==0.75
    and seen.armor_kit.id=='4DD749C6'and seen.body_type==0 and seen.overridden==false)
assert(seen.derived.stamina_factor==0.75 and seen.derived.rating==50 and seen.derived.speed_factor==1.1
    and seen.effective_armor_value==0)
local kit=hd2.armor_stats.kit('4DD749C6'):describe()
assert(kit.source=='live'and kit.stats.rating==50 and kit.pieces.torso.count==2 and kit.pieces.cape.count==1
    and kit.tables_vanilla==true,tostring(kit.source)..' '..tostring(kit.reason))
assert(writes()==0,'reading writes nothing')
local r=me:set({stamina_factor=0.5,armor_bonus=1,allow_unverified_effect=true})
assert(r.status=='APPLIED'and r.writes==2 and r.verified==true,tostring(r.code)..' '..tostring(r.reason))
assert(f32_at(STAMINA)==0.5 and f32_at(ARMOR)==1 and writes()==2)
for _,w in ipairs(W.runtime.writes)do assert(#w.bytes==4 and(w.address==STAMINA or w.address==ARMOR))end
local now=me:describe()
assert(now.overridden and now.effective_armor_value==1 and now.stamina_factor==0.5)
-- Over the Runtime's own value: accepted.
r=me:set({stamina_factor=1.5,allow_unverified_effect=true})
assert(r.status=='APPLIED'and r.writes==1 and f32_at(STAMINA)==1.5)
r=me:set({stamina_factor=1.5,allow_unverified_effect=true})
assert(r.status=='UNCHANGED'and r.writes==0)
-- Restore: the kit's F and 0.
r=me:restore()
assert(r.status=='APPLIED'and r.writes==2 and f32_at(STAMINA)==0.75 and f32_at(ARMOR)==0,tostring(r.code))
assert(me:describe().overridden==false)
assert(count('armor stats (')>=2,table.concat(logged,' | '))
-- A status effect's -1 is the game's own value.
W.write(ARMOR,W.f32(-1))
r=me:set({armor_bonus=2,allow_unverified_effect=true})
assert(r.status=='APPLIED'and f32_at(ARMOR)==2)
me:restore()
assert(f32_at(ARMOR)==0)
-- After a kit write the avatar still holds the vanilla pieces' F: accepted until the next apply.
set_weight(2)
assert(me:describe().derived.stamina_factor==1.5)
r=me:set({stamina_factor=0.5,allow_unverified_effect=true})
assert(r.status=='APPLIED',tostring(r.code)..' '..tostring(r.reason))
r=me:restore()
assert(r.status=='APPLIED'and f32_at(STAMINA)==1.5,'restore writes the F the pieces give now')
set_weight(0)
return 'ok'
''')

    def test_refusals_on_the_world(self):
        self.check(r'''
local function refused(spec,code)
    local r=me:set(spec)
    assert(r.status=='refused'and r.code==code,code..': got '..tostring(r.code)..' '..tostring(r.reason))
    return r
end
-- A third-party value (a status effect multiplying the factor): never overwritten; restore leaves it alone.
W.write(STAMINA,W.f32(0.9))
local r=refused({stamina_factor=0.5,allow_unverified_effect=true},'UNEXPECTED_STATE')
assert(r.reason:find('0.75',1,true)and math.abs(f32_at(STAMINA)-0.9)<1e-6,r.reason)
W.write(ARMOR,W.f32(0.5))
refused({armor_bonus=1,allow_unverified_effect=true},'UNEXPECTED_STATE')
local back=me:restore()
assert(back.status=='UNCHANGED'and#back.skipped==2 and math.abs(f32_at(STAMINA)-0.9)<1e-6,tostring(back.status)..' '..tostring(back.code)..' '..tostring(back.reason))
W.write(STAMINA,W.f32(0.75));W.write(ARMOR,W.f32(0))
-- Several players: solo only; restore still runs.
local solo=me:set({stamina_factor=0.5,allow_unverified_effect=true})
assert(solo.status=='APPLIED',tostring(solo.code)..' '..tostring(solo.reason))
W.players({{peer=LOCAL,avatar=100},{peer=OTHER,avatar=101}},LOCAL)
refused({stamina_factor=1.5,allow_unverified_effect=true},'NOT_SOLO')
local rs=me:restore()
assert(rs.status=='APPLIED'and f32_at(STAMINA)==0.75,tostring(rs.code)..' '..tostring(rs.reason))
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- No avatar slot / no avatar.
W.write(BUCKETS+4*8,W.u32(0)..W.u32(0))
refused({stamina_factor=0.5,allow_unverified_effect=true},'NO_AVATAR_SLOT')
W.write(BUCKETS+4*8,W.u32(100)..W.u32(0))
W.players({{peer=LOCAL}},LOCAL)
refused({stamina_factor=0.5,allow_unverified_effect=true},'NO_LOCAL_AVATAR')
local none,code=me:describe()
assert(none==nil and code=='NO_LOCAL_AVATAR',tostring(code))
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- The avatar manager is not private read-write memory.
local query=W.runtime.query
W.runtime.query=function(at)
    local q=query(at)
    if q and at>=AVM and at<AVM+AV.armorModifier+AV.armorStride*AV.maxSlots then q.protect=2 end
    return q
end
refused({stamina_factor=0.5,allow_unverified_effect=true},'NOT_PRIVATE')
W.runtime.query=query
assert(writes()==1+1,'only the solo write and its restore wrote: '..writes())
-- A pin changed: unsupported, nothing written.
require('hd2runtime/runtime/event_world').open().armor_stats_proven=nil
local pin=D.pins[#D.pins]
W.write(W.GAME+pin.rva,string.rep('\144',#pin.hex/2))
refused({stamina_factor=0.5,allow_unverified_effect=true},'UNSUPPORTED_BUILD')
assert(select(2,me:describe())=='UNSUPPORTED_BUILD',tostring(select(2,me:describe())))
local kit=hd2.armor_stats.kit('4DD749C6'):describe()
assert(kit.source=='research'and kit.reason:find('UNSUPPORTED_BUILD',1,true),tostring(kit.reason))
return 'ok'
''')


class ArmorStatsSnapshotTests(unittest.TestCase):
    def test_the_snapshot_overlay_report(self):
        self.assertEqual((OVERLAY['status'], OVERLAY['snapshots'], OVERLAY['failed']), ('VALIDATED', 7, []))
        self.assertEqual(set(OVERLAY['results']), {s['snapshot'] for s in RESEARCH['snapshots']})
        for name, result in OVERLAY['results'].items():
            self.assertEqual((result['status'], result['fixtureFallback'], result['kitCount']), ('VALIDATED', 'disabled',
                135), name)
            self.assertEqual(result['kits']['statsMatched'], 135, name)
            self.assertEqual(result['proof'], {'pins': 178, 'constants': 7, 'tablesVanilla': True}, name)
            self.assertEqual({page['protect'] for page in result['imagePages'].values()}, {0x40}, name)
            self.assertEqual(result['imagePageGuard']['status'], 'REJECTED', name)
            self.assertIn('failed=protection', result['imagePageGuard']['guardFailure'])
            trips = result['roundTrips']
            self.assertEqual((trips['sanctioner_torso_heavy']['writes'], trips['sanctioner_torso_heavy']['written']),
                (2, [2, 2]), name)
            self.assertEqual(trips['sanctioner_torso_heavy']['liveAfter']['rating'], 70, name)
            self.assertEqual(trips['ravager_all_heavy']['liveAfter']['rating'], 150, name)
            for key in ('sanctioner_torso_heavy', 'ravager_all_heavy'):
                trip = trips[key]
                self.assertEqual((trip['protectionChanges'], trip['restored'], trip['pieceBytesChanged']),
                    (0, True, trip['writes']), name)
            # The class tables and the curve: reviewed executable data, one 4-byte write each, no protection change.
            self.assertEqual(trips['heavy_rating_0']['liveAfter'], {'rating': 0, 'display': 50, 'damage': 1.25}, name)
            self.assertEqual(trips['heavy_stamina_0_5']['liveAfter'], {'stamina': 0.5, 'display': 150}, name)
            self.assertEqual(trips['curve_at_2_0_5']['liveAfter'], {'at_2': 0.5}, name)
            for key in ('heavy_rating_0', 'heavy_stamina_0_5', 'curve_at_2_0_5'):
                trip = trips[key]
                self.assertEqual((trip['writes'], trip['protectionChanges'], trip['restored']), (1, 0, True), name)
                self.assertTrue(1 <= trip['bytesChanged'] <= 4, name)
            rejections = result['rejections']
            for label in ('no allow_shared', 'no allow_unverified_effect', 'weight 3', 'unknown kit',
                    'ambiguous kit name', 'unknown class', 'third-party piece weight', 'kit moved', 'tampered pin',
                    'curve at_0 without allow_unverified_effect', 'class without allow_shared', 'class rating 9'):
                self.assertIn(label, rejections, name)
            self.assertIn('ARMOR_KIT_MOVED', rejections['kit moved'])
            self.assertIn('CONFLICT', rejections['third-party piece weight'])
            if result['player']['status'] == 'checked':
                self.assertEqual((result['player']['slot'], result['player']['stamina_factor'],
                    result['player']['armor_bonus'], result['player']['kit']), (0, 0.75, 0, '4DD749C6'), name)
                self.assertEqual(result['player']['written'], {'stamina_factor': 0.5, 'armor_bonus': 2, 'effective': 2})
                self.assertEqual(rejections['player third-party stamina'], 'UNEXPECTED_STATE')
            else:
                self.assertIn('end-transition', name)
        self.assertEqual(sum(1 for r in OVERLAY['results'].values() if r['player']['status'] == 'checked'), 6)


class ArmorStatsWiringTests(unittest.TestCase):
    def test_sdk_docs_release_notes_and_packaged_scenario(self):
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8')
        for text in ('---@class HD2ArmorStatsApi', 'function HD2ArmorStatsApi.kit(identity) end',
                '---@class HD2ArmorKitTarget', 'function HD2ArmorKitTarget:changes(weight, slots) end',
                '---@class HD2ArmorPlayer', '---@field armor_stats HD2ArmorStatsApi',
                '---@field piece_weight_torso "armor_kit.piece_weight.torso"'):
            self.assertIn(text, stub)
        self.assertEqual(stub, (ROOT / 'starter/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8'))
        self.assertEqual((ROOT / 'docs/armor-stats.md').read_text(encoding='utf-8'),
            (ROOT / 'sdk/docs/armor-stats.md').read_text(encoding='utf-8'))
        notes = (ROOT / 'docs/releases/0.30.0-dev.md').read_text(encoding='utf-8')
        self.assertIn('## Armor rating, speed and stamina (2026-10-08, not live-tested)', notes)
        self.assertIn('docs/armor-stats.md', (ROOT / 'README.md').read_text(encoding='utf-8'))
        packaged = (ROOT / 'scripts/validate_packaged_runtime.py').read_text(encoding='utf-8')
        self.assertIn("'proof-armor-stats': lambda: proof('ArmorStatProbe')", packaged)
        self.assertIn("'generate_armor_stats'", (ROOT / 'scripts/regenerate_domains.py').read_text(encoding='utf-8'))
        self.assertIn('generate_armor_stats.generate(check=True)',
            (ROOT / 'scripts/build_release.py').read_text(encoding='utf-8'))
        self.assertEqual((ROOT / 'proof/ArmorStatProbe/VERSION').read_text(encoding='utf-8'), '0.2.0\n')


class ArmorStatProbeTests(unittest.TestCase):
    def test_the_probe_cycles_stamina_binds_the_kit_and_logs_hits(self):
        addon, resource = probe()
        self.assertEqual(lua('local ADDON,RESOURCE=' + lua_literal(addon) + ',' + lua_literal(resource) + r'''
-- The public write path (hd2.ensure) on the offline world's guarded adapter.
package.loaded['hd2runtime/runtime/windows_write']={create=function()return W.runtime end}
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(...)
    local codes={...}
    for _,c in ipairs(codes)do keys[c]=true end;tick()
    for _,c in ipairs(codes)do keys[c]=false end;tick()
end
assert(loadstring(ADDON,'@'..RESOURCE))()
local F9,CTRL,SHIFT=input.keys.F9,0x11,0x10
assert(count('ArmorStatProbe 0.2.0 ARMOR STAT PROBE BUILD')==1,table.concat(logged,' | '))
assert(count('STATE (loaded): avatar 100 slot 0; armor kit 4DD749C6 RS-100 SANCTIONER; STAMINA FACTOR 0.75 (the kit '
    ..'gives 0.75); ARMOR BONUS 0')==1,table.concat(logged,' | '))
press(F9)
assert(f32_at(STAMINA)==0.5 and count('STAMINA 0.5 (F9): APPLIED')==1,table.concat(logged,' | '))
press(F9)
assert(f32_at(STAMINA)==1.5 and count('STAMINA 1.5 (F9): APPLIED')==1)
press(F9)
assert(f32_at(STAMINA)==0.75 and count('STAMINA GAME (F9): APPLIED')==1,table.concat(logged,' | '))
press(CTRL,F9)
assert(count('KIT 4DD749C6 RS-100 SANCTIONER bound: 7 armor slots')==1 and count('KIT ALL HEAVY (Ctrl+F9)')==1,
    table.concat(logged,' | '))
-- The ensure applies the change through the typed kit domain: every armor piece of every body heavy.
tick(80)
local function weights()
    local out={}
    for _,body in ipairs({0,1,3})do
        for _,p in ipairs(PIECES[body])do
            if p.type==0 then out[#out+1]=b.u32(W.read(p.address+0x10,4),0)end
        end
    end
    return table.concat(out,'')
end
assert(weights()==string.rep('2',13),weights()..' | '..table.concat(logged,' | '):sub(-1500))
assert(count('KIT ENSURE 4DD749C6: ')>=1 and count('now gives rating 150')>=1,table.concat(logged,' | '):sub(-1500))
press(SHIFT,F9)
assert(count('STATUS (Shift+F9): stamina GAME, kit ALL HEAVY, curve VANILLA (kit 4DD749C6')==1,table.concat(logged,' | '))
assert(count('KIT LIVE (Shift+F9): kit 4DD749C6 gives rating 150')==1,table.concat(logged,' | '):sub(-800))
-- ALL LIGHT (this kit's vanilla), then VANILLA: the ensure's own bytes are a transition, not a conflict.
press(CTRL,F9);tick(40)
assert(weights()==string.rep('0',13),weights())
press(CTRL,F9);tick(40)
assert(weights()==string.rep('0',13)and count('KIT VANILLA (Ctrl+F9)')==1,weights())
-- Alt+F9: the damage curve through one ensure (reviewed executable data): TOUGH x0.5, FRAGILE x2, VANILLA.
local ALT=0x12
local CURVE_BYTES=W.read(W.GAME+D.curve.rva,40)
local function curve()
    local out={}
    for _,pt in ipairs(hd2.armor_stats.damage_curve():describe().points)do out[#out+1]=('%g'):format(pt.damage)end
    return table.concat(out,',')
end
assert(curve()=='1.66,1.25,1,0.75,0.65',curve())
press(ALT,F9);tick(80)
assert(count('CURVE TOUGH (Alt+F9)')==1 and curve()=='0.83,0.625,0.5,0.375,0.325',curve()..' | '
    ..table.concat(logged,' | '):sub(-1500))
assert(count('CURVE ENSURE: ')>=1,table.concat(logged,' | '):sub(-800))
press(ALT,F9);tick(40)
assert(count('CURVE FRAGILE (Alt+F9)')==1 and curve()=='3.32,2.5,2,1.5,1.3',curve())
press(SHIFT,F9)
assert(count('CURVE LIVE (Shift+F9): A -1 x3.32, A 0 x2.5')==1,table.concat(logged,' | '):sub(-800))
press(ALT,F9);tick(40)
assert(count('CURVE VANILLA (Alt+F9)')==1 and curve()=='1.66,1.25,1,0.75,0.65'
    and W.read(W.GAME+D.curve.rva,40)==CURVE_BYTES,curve())
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
