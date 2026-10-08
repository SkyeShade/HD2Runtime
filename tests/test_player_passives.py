"""Per-player armor passives (runtime/player_passives.lua, api/player_passives.lua; research/player-attributes-
F5FEE03DCFDB.json): the read API (every passive of the game, the local player's kits, slots and the modifiers the game
reads for flags 3, in order), the write (one guarded 4-byte write per slot on the local player's applied record, the
identity proven first), its re-application after the game re-derives the slots on a kit change, stop() restoring the
kit's values, every refusal, the solo suspension, and the generated domain against the research. On the offline event
world (tests/event_world_fixture.lua) with a customization manager laid out as the domain describes."""
import json
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE, SDK
from reference_format import lua as lua_literal

RESEARCH = json.loads((ROOT / 'research/player-attributes-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

WORLD = PRELUDE + r'''
local b=require('hd2runtime/core/bytes')
W.guarded_runtime()
local PP=require('hd2runtime/runtime/player_passives');PP.reset_for_tests()
local api=require('hd2runtime/api/player_passives')
local D=require('hd2runtime/domains/player_passives')
local MG,R=D.manager,D.record
for _,pin in ipairs(D.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local TYPES={Set=0,Add=1,Multiply=2,Time=3}
-- The manager: every passive of the research as the game holds it, a few kits, one applied record.
local MGR=W.alloc(0x1000)
W.write(W.GAME+MG.globalRva,W.u64(MGR))
local array=W.alloc(#D.passives*8)
local index={}
for id=0,MG.passiveIds-1 do index[id]=4294967295 end
for i,p in ipairs(D.passives)do
    local object=W.alloc(0x40)
    local rows=W.alloc(math.max(#p.modifiers,1)*16)
    for k,m in ipairs(p.modifiers)do
        W.write(rows+(k-1)*16,W.u32(tonumber(m.key,16))..W.u32(TYPES[m.type])..W.f32(m.value)..W.u32(0))
    end
    W.write(object,W.u32(p.id)..W.u32(0)..W.u64(0)..W.u64(rows)..W.u64(#p.modifiers)..W.u64(0)..W.u64(0)
        ..W.u32(p.package and tonumber(p.package,16)or 0))
    W.write(array+(i-1)*8,W.u64(object))
    index[p.id]=i-1
end
local SANCTIONER,SANCTIONER_HELMET,CAPE=0x4DD749C6,0x47BCEC20,0x33929CAA
local FORTIFIED_KIT,EXPLOSIVE_KIT,SCOUT_HELMET=0x44444444,0x22222222,0x55555555
local KITS={{SANCTIONER,32,0},{FORTIFIED_KIT,3,0},{EXPLOSIVE_KIT,17,0},{SANCTIONER_HELMET,0,1},{CAPE,0,2},
    {SCOUT_HELMET,2,1}}
local kits=W.alloc(#KITS*8)
for i,k in ipairs(KITS)do
    local row=W.alloc(0x40)
    W.write(row,W.u32(k[1]));W.write(row+0x1C,W.u32(k[2]));W.write(row+0x28,W.u32(k[3]))
    W.write(kits+(i-1)*8,W.u64(row))
end
W.write(MGR+MG.kits,W.u64(kits)..W.u32(#KITS))
W.write(MGR+MG.passives,W.u64(array)..W.u32(#D.passives))
for id=0,MG.passiveIds-1 do W.write(MGR+MG.passiveIndex+id*4,W.u32(index[id]))end
local ENTITY=10                      -- the fixture's player list: player slot 0 is entity 10
local SLOTS=W.alloc(8*8)
local function map(entity)
    for k=0,7 do W.write(SLOTS+k*8,W.u32(0)..W.u32(0))end
    if entity then W.write(SLOTS+((entity*2)%8)*8,W.u32(entity)..W.u32(0))end
end
W.write(MGR+MG.map,W.u64(SLOTS)..W.u32(8)..W.u32(0)..W.u32(2))
local DESCRIPTOR=W.alloc(0x18)
W.write(DESCRIPTOR+8,W.u32(ENTITY))
W.write(MGR+MG.descriptors,W.u64(DESCRIPTOR))
W.write(MGR+MG.recordCount,W.u32(1))
local RECORD=MGR+MG.applied
-- What 0x874520 does when a new kit's package is ready: the kit id, and the slot = the kit's passive.
local function game_sets(armor,helmet)
    if armor then
        W.write(RECORD+R.armorKit,W.u32(armor[1]));W.write(RECORD+R.armorPassive,W.u32(armor[2]))
    end
    if helmet then
        W.write(RECORD+R.helmetKit,W.u32(helmet[1]));W.write(RECORD+R.helmetPassive,W.u32(helmet[2]))
    end
end
W.write(RECORD+R.capeKit,W.u32(CAPE))
game_sets({SANCTIONER,32},{SANCTIONER_HELMET,0})
map(ENTITY)
W.players({{peer=LOCAL,avatar=100}},LOCAL)
local function slot(offset)return b.u32(W.read(RECORD+offset,4),0)end
local function armor()return slot(R.armorPassive)end
local function second()return slot(R.helmetPassive)end
local function writes()return#W.runtime.writes end
local function keys(list)
    local out={}
    for _,m in ipairs(list)do out[#out+1]=('%s:%s:%s:%g:%s'):format(m.key_name,m.source,m.type,m.value,m.passive)end
    return table.concat(out,' ')
end
'''


def lua(body):
    return run(WORLD + body)


class PlayerPassiveTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_read_api(self):
        self.check(r'''
local list=hd2.passives.list()
assert(#list==32 and list[1].id==0 and list[1].name=='STANDARD ISSUE','every passive of the game')
local by={}
for _,p in ipairs(list)do by[p.id]=p end
assert(by[32].name=='REDUCED SIGNATURE'and by[32].modifiers[1].key=='AF8B7112'
    and by[32].modifiers[1].key_name=='movement_noise'and by[32].modifiers[1].type=='Multiply'
    and by[32].modifiers[1].value==0.5)
assert(by[17].effect_package and by[17].package=='644F8A3B'and not by[8].effect_package)
assert(by[4]==nil and by[22]==nil,'unused ids')
assert(hd2.passives.find('servo-assisted').id==8 and hd2.passives.find(2).name=='SCOUT')
assert(select(2,hd2.passives.find(4))=='UNKNOWN_PASSIVE'and select(2,hd2.passives.find('nope'))=='UNKNOWN_PASSIVE')
local mine=assert(hd2.player_passives())
assert(mine.entity==ENTITY and mine.record==0 and mine.armor_kit.id=='0x4DD749C6'
    and mine.armor_kit.name=='RS-100 SANCTIONER'and mine.armor_kit.passive==32)
assert(mine.helmet_kit.name=='RS-100 Sanctioner'and mine.cape_kit.name=="FALLEN HERO'S VENGEANCE")
assert(mine.armor_passive.id==32 and mine.armor_passive.name=='REDUCED SIGNATURE'and mine.helmet_passive.id==0)
assert(mine.overridden==false and mine.derived.armor==32 and mine.derived.second==0)
assert(keys(mine.effective)=='movement_noise:armor:Multiply:0.5:32 enemy_detection_range:armor:Multiply:0.6:32',
    keys(mine.effective))
assert(writes()==0,'reading writes nothing')
-- No record yet: nil, code, reason.
map(nil)
local none,code=hd2.player_passives()
assert(none==nil and code=='NO_RECORD',tostring(code))
-- An armor kit the kit table does not hold (yet): not ready.
map(ENTITY)
game_sets({0x99999999,32})
local _,code2=hd2.player_passives()
assert(code2=='NOT_READY',tostring(code2))
return 'ok'
''')

    def test_override_reapply_after_a_kit_change_and_restore(self):
        self.check(r'''
local h=hd2.player_passives.set({armor='SERVO-ASSISTED',second='SCOUT'})
assert(h.status=='active',tostring(h.code)..' '..tostring(h.reason))
assert(armor()==8 and second()==2 and writes()==2,'one 4-byte write per slot: '..writes())
for _,w in ipairs(W.runtime.writes)do assert(#w.bytes==4)end
assert(W.runtime.writes[1].address==RECORD+R.armorPassive or W.runtime.writes[2].address==RECORD+R.armorPassive)
local mine=hd2.player_passives()
assert(mine.overridden and mine.runtime~=nil and mine.armor_passive.name=='SERVO-ASSISTED')
-- The armor's rows first, then the second passive's keys the armor lacks.
assert(keys(mine.effective)=='throw_range:armor:Multiply:1.3:8 limb_health:armor:Multiply:1.5:8 '
    ..'radar_scan_interval:second:Time:2:2 enemy_detection_range:second:Multiply:0.7:2',keys(mine.effective))
assert(count('passives (')>=1 and count('APPLIED: armor SERVO-ASSISTED (8), second SCOUT (2)')==1,
    table.concat(logged,' | '))
-- Held: nothing more is written while the slots hold the values.
tick(8)
assert(writes()==2)
-- The player changes armor: the game re-derives the armor slot from the new kit (FORTIFIED, 3); the Runtime re-applies.
game_sets({FORTIFIED_KIT,3})
tick(4)
assert(armor()==8 and second()==2 and writes()==3,'re-applied: '..armor()..' '..writes())
assert(count('RE-APPLIED after the kit changed (armor 0x4DD749C6 -> 0x44444444')==1,table.concat(logged,' | '))
assert(h:describe().applications==2)
-- A helmet change re-derives the helmet slot (this helmet has SCOUT itself: still re-applied as asked).
game_sets(nil,{SCOUT_HELMET,2})
tick(4)
assert(second()==2 and writes()==3,'the slot already holds the value')
-- stop(): the kit's values come back (FORTIFIED from the new armor kit, SCOUT from the new helmet).
h:stop()
assert(h.status=='stopped'and armor()==3 and second()==2 and writes()==4,armor()..' '..second()..' '..writes())
assert(count('stopped: armor FORTIFIED (3) (the kit\'s), second SCOUT (2) (the kit\'s) restored')==1,
    table.concat(logged,' | '))
tick(8)
assert(writes()==4,'nothing is written after stop()')
return 'ok'
''')

    def test_stop_leaves_values_the_game_rederived_and_a_second_set_replaces(self):
        self.check(r'''
local h=hd2.player_passives.set({armor=6,owner='mods/a'})       -- ENGINEERING KIT
assert(h.status=='active'and armor()==6 and second()==0 and writes()==1)
-- The same mod again: replaced in place (no restore in between).
local h2=hd2.player_passives.set({armor=8,second=7,owner='mods/a'})
assert(h2.status=='active'and h.status=='replaced'and armor()==8 and second()==7 and writes()==3,writes())
h:stop()
assert(armor()==8 and writes()==3,'stopping the replaced handle writes nothing')
-- Another mod is refused while it is held.
local other=hd2.player_passives.set({armor=2,owner='mods/b'})
assert(other.status=='refused'and other.code=='ALREADY_SET',tostring(other.code))
assert(hd2.player_passives.status().owner=='mods/a'and hd2.player_passives.status().second.name=='MED-KIT')
-- The kit changes and stop() comes before the Runtime looked again: the armor slot is the game's (left alone); the
-- second slot is still this override's for the same helmet: restored.
game_sets({FORTIFIED_KIT,3})
h2:stop()
assert(armor()==3 and second()==0 and writes()==4,armor()..' '..second()..' '..writes())
-- Now another mod may.
local h3=hd2.player_passives.set({second='SCOUT',owner='mods/b'})
assert(h3.status=='active'and second()==2,tostring(h3.code))
h3:stop()
return 'ok'
''')

    def test_every_refusal(self):
        self.check(r'''
local function refused(spec,code)
    local h=hd2.player_passives.set(spec)
    assert(h.status=='refused'and h.code==code,code..': got '..tostring(h.code)..' '..tostring(h.reason))
    return h
end
refused(5,'INVALID_OPTION')
refused({},'INVALID_OPTION')
refused({armor=8,colour='red'},'INVALID_OPTION')
refused({second=0},'INVALID_OPTION')
refused({armor='NOPE'},'UNKNOWN_PASSIVE')
refused({armor=4},'UNKNOWN_PASSIVE')
refused({armor=99},'UNKNOWN_PASSIVE')
refused({second=25},'UNKNOWN_PASSIVE')
refused({armor=8,second='servo-assisted'},'SAME_PASSIVE')
refused({second=32},'SAME_PASSIVE')            -- the armor kit's own passive
-- An effect package nobody's record holds: refused (17 INTEGRATED EXPLOSIVES).
local p=refused({armor='INTEGRATED EXPLOSIVES'},'PACKAGE_NOT_RESIDENT')
assert(p.reason:find('644F8A3B',1,true),p.reason)
assert(writes()==0)
-- Several players: solo only.
W.players({{peer=LOCAL,avatar=100},{peer=OTHER,avatar=101}},LOCAL)
refused({armor=8},'NOT_SOLO')
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- A slot that holds neither the kit's value nor this override's: someone else's; never overwritten.
W.write(RECORD+R.armorPassive,W.u32(9))
refused({armor=8},'UNEXPECTED_STATE')
assert(armor()==9)
W.write(RECORD+R.armorPassive,W.u32(32))
-- The record descriptor does not carry the local player's entity.
W.write(DESCRIPTOR+8,W.u32(77))
refused({armor=8},'UNEXPECTED_STATE')
W.write(DESCRIPTOR+8,W.u32(ENTITY))
-- The record is not private read-write memory.
local query=W.runtime.query
W.runtime.query=function(at)
    local r=query(at)
    if r and at>=MGR and at<MGR+0x1000 then r.protect=2 end
    return r
end
refused({armor=8},'NOT_PRIVATE')
W.runtime.query=query
assert(writes()==0,'no refusal writes')
-- A pin changed: unsupported, nothing written.
require('hd2runtime/runtime/event_world').open().player_passives_proven=nil
local pin=D.pins[1]
W.write(W.GAME+pin.rva,string.rep('\144',#pin.hex/2))
refused({armor=8},'UNSUPPORTED_BUILD')
local none,code=hd2.player_passives()
assert(none==nil and code=='UNSUPPORTED_BUILD')
assert(writes()==0)
return 'ok'
''')

    def test_an_effect_package_passive_while_resident_waiting_and_solo_suspension(self):
        self.check(r'''
-- The armor kit carries INTEGRATED EXPLOSIVES (17): its package is resident, so it may become the second passive.
game_sets({EXPLOSIVE_KIT,17})
local h=hd2.player_passives.set({armor='SERVO-ASSISTED',second='INTEGRATED EXPLOSIVES'})
assert(h.status=='active'and armor()==8 and second()==17,tostring(h.code)..' '..tostring(h.reason))
h:stop()
assert(armor()==17 and second()==0)
game_sets({SANCTIONER,32})
-- No record yet: waiting, applied when it appears.
map(nil)
local w=hd2.player_passives.set({armor=8})
assert(w.status=='waiting'and w.code=='NO_RECORD'and writes()==4,tostring(w.status)..' '..tostring(w.code))
tick(4)
assert(w.status=='waiting'and armor()==32)
map(ENTITY)
tick(4)
assert(w.status=='active'and armor()==8,tostring(w.status))
-- A second player joins: suspended, the kit's value back; solo again: re-applied.
W.players({{peer=LOCAL,avatar=100},{peer=OTHER,avatar=101}},LOCAL)
tick(4)
assert(w.status=='suspended'and w.code=='NOT_SOLO'and armor()==32,tostring(w.status)..' '..armor())
assert(count('SUSPENDED')==1)
W.players({{peer=LOCAL,avatar=100}},LOCAL)
tick(4)
assert(w.status=='active'and armor()==8,tostring(w.status))
-- Someone else writes the slot: lost, never overwritten again.
W.write(RECORD+R.armorPassive,W.u32(9))
tick(4)
assert(w.status=='lost'and armor()==9 and count('LOST')==1,tostring(w.status))
local n=writes()
w:stop()
assert(armor()==9 and writes()==n,'a lost override restores nothing')
return 'ok'
''')


def probe():
    """proof/PassiveSwapProbe inside the SDK's addon wrapper, exactly as its built ZIP ships it."""
    project = ROOT / 'proof/PassiveSwapProbe'
    spec = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
    return SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'],
        (project / 'src/addon.lua').read_text(encoding='utf-8-sig')), spec['resource']


class PassiveSwapProbeTests(unittest.TestCase):
    def test_the_probe_logs_cycles_adds_and_restores(self):
        addon, resource = probe()
        self.assertEqual(lua('local ADDON,RESOURCE=' + lua_literal(addon) + ',' + lua_literal(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(...)
    local codes={...}
    for _,c in ipairs(codes)do keys[c]=true end;tick()
    for _,c in ipairs(codes)do keys[c]=false end;tick()
end
assert(loadstring(ADDON,'@'..RESOURCE))()
local F8,CTRL,SHIFT=input.keys.F8,0x11,0x10
assert(count('PassiveSwapProbe 0.1.0 PASSIVE SWAP PROBE BUILD')==1,table.concat(logged,' | '))
assert(count('the game has 32 armor passives')==1 and count('ARMOR SLOT REDUCED SIGNATURE (32)')==1,
    table.concat(logged,' | '))
press(F8)
assert(armor()==8 and count('MODE SERVO-ASSISTED (F8): handle active')==1 and count('OBSERVE: THROW RANGE x1.3')==1,
    table.concat(logged,' | '))
press(CTRL,F8)
assert(armor()==8 and second()==7 and count('MODE SERVO-ASSISTED + second MED-KIT')==1,table.concat(logged,' | '))
press(F8)
assert(armor()==6 and second()==7,'ENGINEERING KIT, MED-KIT kept')
press(SHIFT,F8)
assert(count('STATUS (Shift+F8): mode ENGINEERING KIT + second MED-KIT; handle active')==1,table.concat(logged,' | '))
press(CTRL,SHIFT,F8)
assert(armor()==32 and second()==0 and count('RESTORED (Ctrl+Shift+F8)')==1,table.concat(logged,' | '))
return 'ok'
'''), b'ok')


class PlayerPassivesDomainTests(unittest.TestCase):
    def test_the_domain_is_the_research(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('g', ROOT / 'scripts/generate_player_passives.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(check=True), [])
        d = module.build()
        self.assertEqual(d['manager']['globalRva'], 0x33264F8)
        self.assertEqual((d['manager']['applied'], d['manager']['appliedStride'], d['record']['armorPassive'],
            d['record']['helmetPassive'], d['kit']['passive']), (0x96C, 0x44, 0x3C, 0x38, 0x1C))
        self.assertEqual(len(d['passives']), 32)
        self.assertEqual(d['unused'], [4, 22, 23, 24, 25, 26, 27, 28, 29, 30])
        self.assertEqual(sorted(p['id'] for p in d['passives'] if p['package']), [17, 19])
        self.assertEqual(len(d['pins']), len({p['rva'] for g in RESEARCH['pins'].values() for p in g}))
        self.assertEqual([f['key'] for f in d['flagsOne']], ['54A69284', '73734D67', 'A68930C2'])
        self.assertEqual((d['observed']['entity'], d['observed']['armorPassive'], d['observed']['helmetPassive']),
            (5, 32, 0))
        # Every key a passive carries has a semantic name; the writer is the only one the research found.
        self.assertTrue(all(m['key_name'] for p in d['passives'] for m in p['modifiers']))
        self.assertIn('only 0x874520 writes applied +0x38/+0x3C', RESEARCH['writers']['appliedPassives'])


if __name__ == '__main__':
    unittest.main()
