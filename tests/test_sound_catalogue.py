"""The full sound-event catalogue and the playback controls (docs/sounds.md; docs/research/sound-events-F5FEE03DCFDB.md;
docs/research/wwise-plugin-bindings-F5FEE03DCFDB.md):
  * research/sound-events-F5FEE03DCFDB.json -> scripts/generate_sound_events.py -> domains/sound_events.lua,
    sdk/SoundEventCatalogue.json; research/wwise-plugin-F5FEE03DCFDB.json -> scripts/generate_wwise_plugin.py ->
    domains/wwise_plugin.lua (current, names from evidence only, the pins equal to the installed plugin's bytes);
  * scripts/wwise_banks.py parsers on synthetic bank data;
  * hd2.sounds.list / describe over both catalogues (the weapon catalogue unchanged), asset targets of sound events;
  * hd2.sounds.play at a position with a rotation, on a unit, refusing events that would leave the sound engine changed;
  * handle controls against a recording fake of the Wwise plugin's Lua API, each binding called with the argument order
    read from the plugin's code; the plugin's counter-id map read through its own hash (runtime/wwise_plugin.lua)."""
import json
import re
import struct
import sys
import unittest
from pathlib import Path

from support import ROOT, run

sys.path.insert(0, str(ROOT / 'scripts'))
import wwise_banks as wb  # noqa: E402

RESEARCH = ROOT / 'research/sound-events-F5FEE03DCFDB.json'
PLUGIN_RESEARCH = ROOT / 'research/wwise-plugin-F5FEE03DCFDB.json'
DLL = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\bin\plugins\wwise_pluginw64_release.dll')


class ResearchAndGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        import generate_sound_events
        cls.catalogue = generate_sound_events.build()

    def test_the_research_covers_every_bank_and_event(self):
        r = self.research
        self.assertEqual(r['writes'], 0)
        c = r['counts']
        self.assertEqual((c['banks'], c['events']), (416, 10030))
        self.assertEqual(c['metadataCovered'], c['events'], 'every event has the game\'s own metadata record')
        self.assertLessEqual(sum(c['nodesNotParsedExactly'].values()), 1)
        self.assertEqual(r['names']['controlMatches'], 0, 'no coincidental FNV-1 matches in the control')
        for i, e in r['events'].items():
            self.assertTrue(e['banks'] and all(b in r['banks'] for b in e['banks']), i)

    def test_the_generated_files_are_current(self):
        import generate_sound_events
        import generate_wwise_plugin
        self.assertEqual(generate_sound_events.generate(check=True), [])
        self.assertEqual(generate_wwise_plugin.generate(check=True), [])

    def test_names_come_from_evidence(self):
        d, r = self.catalogue, self.research
        families = '|'.join(d['families'])
        pattern = re.compile(r'^(%s)/[a-z0-9_]+/[a-z0-9_]+$' % families)
        own = {row['name'].lower() for row in r['eventNames'].values()}
        banks = {b['name'] for b in d['banks']}
        for name, e in d['events'].items():
            self.assertRegex(name, pattern)
            family, bank, event = name.split('/')
            self.assertIn(bank, banks)
            # The event part is its id, or its own Wwise name as the game's code or data spells it (FNV-1 checked).
            if event != e['id'].lower():
                self.assertIn(event, own)
                self.assertEqual(wb.fnv1(event), int(e['id'], 16))
                self.assertEqual(e['wwise'], event)
            # explosions: only events whose sounds play on the game's own 'explosion' bus.
            if family == 'explosions':
                self.assertIn('explosion', (e.get('bus') or '').split('/'))
        self.assertEqual(len(d['events']), 10030)
        # Every weapon-catalogue event links back to its weapon sounds.
        import generate_weapon_sounds
        by_id = {e['id']: e for e in d['events'].values()}
        for wname, s in generate_weapon_sounds.build()['sounds'].items():
            for key in ('event', 'start', 'stop'):
                if s.get(key) and s[key] != '00000000':
                    self.assertIn(wname, by_id[s[key]]['weapons'])
        # No weapon-catalogue event has a persistent global effect (so hd2.sounds.play never refuses one).
        self.assertFalse([e['id'] for e in d['events'].values() if e.get('weapons') and e.get('persistent')])

    def test_the_plugin_pins_are_the_installed_plugins_bytes(self):
        if not DLL.is_file():
            self.skipTest('the game is not installed')
        import generate_wwise_plugin
        raw = DLL.read_bytes()
        pe = struct.unpack_from('<I', raw, 0x3C)[0]
        nsec = struct.unpack_from('<H', raw, pe + 6)[0]
        opt = struct.unpack_from('<H', raw, pe + 20)[0]
        sections = []
        for i in range(nsec):
            o = pe + 24 + opt + 40 * i
            vsize, va, rsize, rptr = struct.unpack_from('<IIII', raw, o + 8)
            sections.append((va, rsize, rptr))
        d = generate_wwise_plugin.build()
        self.assertEqual(struct.unpack_from('<I', raw, pe + 80)[0], d['imageSize'])
        for pin in d['pins']:
            va, rsize, rptr = next(s for s in sections if s[0] <= pin['rva'] < s[0] + s[1])
            at = rptr + pin['rva'] - va
            self.assertEqual(raw[at:at + len(pin['hex']) // 2].hex(), pin['hex'], pin['label'])
        self.assertGreater(len(d['pins']), 300)


class BankParserTests(unittest.TestCase):
    def test_hirc_events_and_actions(self):
        body_event = bytes([2]) + struct.pack('<II', 0x11, 0x22)
        set_state = struct.pack('<HIBBB', 0x1204, 0xAA, 0, 0, 0) + struct.pack('<II', 0x1234, 0xAA)
        play = struct.pack('<HIBBB', 0x0403, 0x99, 0, 0, 0)
        objs = [(4, 0x1000, body_event), (3, 0x11, set_state), (3, 0x22, play)]
        hirc = struct.pack('<I', len(objs)) + b''.join(struct.pack('<BII', k, len(b) + 4, i) + b for k, i, b in objs)
        raw = b'BKHD' + struct.pack('<I', 4) + b'\0' * 4 + b'HIRC' + struct.pack('<I', len(hirc)) + hirc
        parsed = wb.hirc(raw)
        self.assertEqual(wb.event_actions(parsed[0x1000][1]), [0x11, 0x22])
        a = wb.action(parsed[0x11][1])
        self.assertEqual((a['action'], a['scope'], a['group'], a['value']), ('set_state', 'global', 0x1234, 0xAA))
        self.assertEqual(wb.action(parsed[0x22][1])['action'], 'play')
        self.assertRaises(ValueError, wb.event_actions, bytes([3]) + b'\0' * 4)

    def test_global_effects(self):
        def act(t, target=1):
            return {'type': t, 'target': target, 'scope': wb.SCOPES.get(t & 0xFF, 'unknown') if t >> 8 not in
                wb.GLOBAL_ACTIONS else 'global'}
        self.assertEqual(wb.effects([act(0x0403)]), [])
        self.assertEqual(wb.effects([act(0x1204)]), ['state'])
        self.assertEqual(wb.effects([act(0x1302)]), ['parameter'])
        self.assertEqual(wb.effects([act(0x1303)]), [], 'a game parameter on the posting object only')
        self.assertEqual(wb.effects([act(0x0A02), act(0x0B02)]), [], 'a duck the event undoes itself')
        self.assertEqual(wb.effects([act(0x0A02)]), ['mix'])
        self.assertEqual(wb.effects([act(0x0202)]), ['pause'])
        self.assertEqual(wb.effects([act(0x0202), act(0x0302)]), [])
        self.assertEqual(wb.effects([act(0x0102)]), ['stop'])
        self.assertEqual(wb.effects([act(0x0103)]), [])

    def test_stmg_and_metadata(self):
        body = struct.pack('<HfHH', 0, -96.0, 140, 50)
        body += struct.pack('<I', 1) + struct.pack('<III', 7, 1000, 1) + struct.pack('<III', 1, 2, 300)
        body += struct.pack('<I', 1) + struct.pack('<IIBI', 9, 10, 0, 1) + struct.pack('<fII', 0.5, 11, 4)
        body += struct.pack('<I', 1) + struct.pack('<IfIffB', 12, 3.0, 0, 0.0, 0.0, 0)
        body += struct.pack('<I', 0)
        s = wb.stmg(body)
        self.assertEqual(s['stateGroups'][0]['transitions'], [(1, 2, 300)])
        self.assertEqual(s['switchGroups'][0]['points'], [(0.5, 11, 4)])
        self.assertEqual(s['parameters'][0]['default'], 3.0)
        self.assertRaises(ValueError, wb.stmg, body + b'\0')
        meta = struct.pack('<II', 0x78A3F4A5, 28) + struct.pack('<IfffIII', 5, 160.0, 1.0, 0.5, 0, 0, 0)
        self.assertEqual(wb.metadata(meta)[5][1], 160.0)
        self.assertEqual(wb.fnv1('Set_State__Mastering_StereoOutputFormat_On'),
            wb.fnv1('set_state__mastering_stereooutputformat_on'))


HARNESS = r'''
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function()end
local events=require('hd2runtime/runtime/events')
events.reset_for_tests()
local calls,known={},{}
local NEXT=100
local function rec(name)return function(...)calls[#calls+1]={name,...};return true end end
local Q={}
rawset(_G,'stingray',{
    Wwise={wwise_world=function(w)return 'WW'end,has_event=function(name)return known[name]==true end},
    WwiseWorld={trigger_event=function(ww,name,a,b)NEXT=NEXT+1;calls[#calls+1]={'trigger_event',ww,name,a,b}
            return NEXT,a and 555 or 77 end,
        stop_event=rec('stop_event'),pause_event=rec('pause_event'),resume_event=rec('resume_event'),
        is_playing=function(ww,id)calls[#calls+1]={'is_playing',ww,id};return true end,
        get_playing_elapsed=function(ww,id)calls[#calls+1]={'get_playing_elapsed',ww,id};return 1500 end,
        set_source_parameter=rec('set_source_parameter'),set_switch=rec('set_switch'),post_trigger=rec('post_trigger')},
    Vector3=function(x,y,z)return {'V3',x,y,z}end,
    Quaternion={from_elements=function(x,y,z,w)return {'Q',x,y,z,w}end}})
local S=require('hd2runtime/runtime/sound_events')
local U=require('hd2runtime/runtime/ui_sound')
local C=require('hd2runtime/runtime/sound_catalogue')
local E=require('hd2runtime/domains/sound_events')
S.reset_for_tests()
local NOW=0
local ENTRY={state=0}
S.hooks.game_world=function()return 'GAMEWORLD'end
S.hooks.playing_entry=function(counter)if ENTRY.state==nil then return nil,'unreadable'end
    return {state=ENTRY.state,id=ENTRY.state==2 and 0 or counter+9000}end
S.hooks.now=function()return NOW end
local hd2=require('hd2runtime/api/hd2')
local function last(name)for i=#calls,1,-1 do if calls[i][1]==name then return calls[i]end end end
-- Catalogue events of a kind, found by their fields.
local function find(pred)
    local names={}
    for name,e in pairs(E.events)do if pred(e,name)then names[#names+1]=name end end
    table.sort(names)
    return names[1],E.events[names[1]]
end
'''


class CatalogueApiTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_list_and_describe_over_both_catalogues(self):
        self.lua(r'''
-- The default list is still the weapon firing-sound catalogue, unchanged.
local weapons=hd2.sounds.list()
assert(#weapons==171 and weapons[1].catalogue==nil and weapons[1].designed_rpm~=nil,#weapons)
assert(hd2.sounds.describe('sentry/gatling').kind=='loop')
-- The event catalogue.
local all=hd2.sounds.list({catalogue='events'})
assert(#all==10030,#all)
for i=2,#all do assert(all[i-1].name<all[i].name)end
local explosions=hd2.sounds.list({catalogue='events',family='explosions'})
assert(#explosions>0)
for _,e in ipairs(explosions)do assert(e.bus:find('explosion',1,true)and e.catalogue=='events')end
local loops=hd2.sounds.list({catalogue='events',kind='loop',faction='automaton'})
for _,e in ipairs(loops)do assert(e.kind=='loop'and e.faction=='automaton')end
local named=hd2.sounds.list({catalogue='events',named=true})
assert(#named==E.counts.named)
local d=hd2.sounds.describe('ambience/env_shared/env_sludge_bubbling')
assert(d and d.wwise_name=='env_sludge_bubbling'and d.kind=='loop'and d.family=='ambience'and d.bank=='env_shared')
assert(hd2.sounds.describe('env_sludge_bubbling').name==d.name,'by its own Wwise name')
assert(hd2.sounds.describe('no/such/sound')==nil)
-- A weapon-catalogue event lists its weapon sounds.
local gatling=hd2.sounds.list({catalogue='events',weapon='sentry/gatling'})
assert(#gatling==2,'the Gatling loop start and stop')
-- Both catalogues together.
local both=hd2.sounds.list({catalogue='all',text='gatling'})
local w,e=0,0
for _,s in ipairs(both)do if s.catalogue=='events'then e=e+1 else w=w+1 end end
assert(w>=1 and e>=0)
-- Invalid filters raise with the reason.
assert(not pcall(hd2.sounds.list,{catalogue='events',family='nope'}))
assert(not pcall(hd2.sounds.list,{catalogue='events',kind='shot'}))
assert(not pcall(hd2.sounds.list,{catalogue='nope'}))
assert(not pcall(hd2.sounds.list,{catalogue='events',colour=1}))
-- The Init bank's game parameters, switch and state groups.
local params=hd2.sounds.parameters()
assert(#params==565)
local rf
for _,p in ipairs(params)do if p.name=='rounds_fired'then rf=p end end
assert(rf and rf.named)
local sw=hd2.sounds.switch_groups()
local materials
for _,g in ipairs(sw)do if g.name=='materials'then materials=g end end
assert(materials and#materials.values>=20)
assert(#hd2.sounds.state_groups()>=86)
return 'ok'
''')

    def test_sound_events_are_asset_targets(self):
        self.lua(r'''
local api_assets=require('hd2runtime/api/assets')
local banks=E.banks
local strat=find(function(e)local p=banks[e.banks[1]].provider return p and p.stratagem~=nil end)
local item=find(function(e)local p=banks[e.banks[1]].provider return p and p.item~=nil end)
local resident=find(function(e)return banks[e.banks[1]].provider==nil end)
local t=hd2.sounds.asset(strat)
assert(t.resource=='sound'and t.sound==strat)
local deps=assert(api_assets.sound_dependencies(strat))
assert(#deps>=1 and deps[1].via=='sound_bank_stratagem_call_in')
local info=hd2.asset_dependency(t)
assert(info.known and info.autoLoadSupported and info.key=='sound/'..strat)
local ideps=assert(api_assets.sound_dependencies(item))
assert(#ideps==1 and ideps[1].via=='sound_bank_loadout_item')
local none,why=api_assets.sound_dependencies(resident)
assert(none==nil and why:find('resident-only',1,true))
-- The weapon catalogue's own targets are unchanged.
assert(api_assets.sound_dependencies('sentry/gatling')[1].package=='0x992D325D88DE5FBF')
return 'ok'
''')

    def test_play_catalogue_events_and_refuse_persistent_global_effects(self):
        self.lua(r'''
local name,e=find(function(e)return e.kind=='one_shot'and not e.effects end)
local spec=S.resolve(name)
assert(spec.id==tonumber(e.id,16)and U.fnv1(spec.name)==spec.id and spec.sound==name)
known[spec.name]=true
local h=assert(hd2.sounds.play(name,{owner='mods/t/c'}))
local t=last('trigger_event')
assert(t[2]=='WW'and t[3]==spec.name and t[4]==nil,'the default source: no third argument')
assert(h.source_kind=='world'and h.wwise==h.playing+9000)
-- An event with its own Wwise name posts that name.
local own=S.resolve('ambience/env_shared/env_sludge_bubbling')
assert(own.name=='env_sludge_bubbling')
-- Persistent global effects (a state, a global game parameter, an undone global mix change or pause): refused, by
-- catalogue name, by its own Wwise name and by id; nothing posted.
local pname,pe=find(function(e)return e.persistent end)
local n=#calls
for _,ev in ipairs({pname,{id=tonumber(pe.id,16)}})do
    local x,code=hd2.sounds.play(ev,{owner='mods/t/c'})
    assert(x==nil and code=='GLOBAL_EVENT',tostring(code))
end
local x,code=hd2.sounds.play('Set_State__Mastering_StereoOutputFormat_On',{owner='mods/t/c'})
assert(x==nil and code=='GLOBAL_EVENT')
assert(#calls==n)
-- A transient global effect (a global stop of an element) is allowed.
local tname=find(function(e)return e.effects and not e.persistent and e.kind~='control'end)
if tname then
    local ts=S.resolve(tname);known[ts.name]=true
    assert(hd2.sounds.play(tname,{owner='mods/t/c'}))
end
return 'ok'
''')

    def test_position_rotation_and_unit_sources(self):
        self.lua(r'''
known.boom=true
local h=assert(hd2.sounds.play('boom',{owner='mods/t/p',position={1,2,3},rotation={0,0,0,2}}))
local t=last('trigger_event')
assert(t[4][1]=='V3'and t[4][2]==1 and t[4][4]==3)
assert(t[5][1]=='Q'and t[5][5]==1,'the rotation normalised')
assert(h.source_kind=='position'and h.source==555)
assert(hd2.sounds.play('boom',{owner='mods/t/p',position={x=4,y=5,z=6}}))
assert(last('trigger_event')[5]==nil,'no rotation: no fourth argument')
local unit=newproxy()
local u=assert(hd2.sounds.play('boom',{owner='mods/t/p',unit=unit}))
assert(last('trigger_event')[4]==unit and u.source_kind=='unit')
local n=#calls
for _,bad in ipairs({{unit=42},{unit={}},{unit=unit,position={1,2,3}},{rotation={0,0,0,1}},
        {position={1,2,3},rotation={0,0,0,0}},{position={1,2,3},rotation={0/0,0,0,1}},{position={1,2}}})do
    bad.owner='mods/t/p'
    local x,code=hd2.sounds.play('boom',bad)
    assert(x==nil and code=='INVALID',tostring(code))
end
assert(#calls==n,'nothing posted')
return 'ok'
''')

    def test_handle_controls_call_each_binding_in_its_argument_order(self):
        self.lua(r'''
known.boom=true
local h=assert(hd2.sounds.play('boom',{owner='mods/t/h',position={1,2,3}}))
-- set_source_parameter(world, source, name, value) on the handle's own source.
assert(h:set_parameter('rounds_fired',3)==true)
local c=last('set_source_parameter')
assert(c[2]=='WW'and c[3]==555 and c[4]=='rounds_fired'and c[5]==3)
-- An unnamed parameter by id: posted through a name hashing to it.
local pid
for hex,p in pairs(E.parameters)do if not p.name then pid=tonumber(hex,16);break end end
assert(h:set_parameter({id=pid},0.5)==true and U.fnv1(last('set_source_parameter')[4])==pid)
assert(select(2,h:set_parameter('x',0/0))=='INVALID')
-- set_switch(world, group, switch, source); post_trigger(world, source, name).
assert(h:set_switch('materials','metal_thin')==true)
c=last('set_switch')
assert(c[2]=='WW'and c[3]=='materials'and c[4]=='metal_thin'and c[5]==555)
assert(h:post_trigger('stinger')==true)
c=last('post_trigger')
assert(c[2]=='WW'and c[3]==555 and c[4]=='stinger')
-- pause / resume / is_playing / get_playing_elapsed take the sound engine's id read after the post.
assert(h:pause()==true and last('pause_event')[3]==h.wwise and last('pause_event')[2]=='WW')
assert(h:resume()==true and last('resume_event')[3]==h.wwise)
assert(h:is_playing()==true and last('is_playing')[3]==h.wwise)
assert(h:elapsed()==1.5 and last('get_playing_elapsed')[3]==h.wwise)
-- The world's default source and a unit's source are shared with the game's own sounds: no source calls.
local w=assert(hd2.sounds.play('boom',{owner='mods/t/h2'}))
local x,code=w:set_parameter('rounds_fired',1)
assert(x==nil and code=='SHARED_SOURCE')
assert(select(2,w:set_switch('materials','metal_thin'))=='SHARED_SOURCE')
assert(select(2,w:post_trigger('stinger'))=='SHARED_SOURCE')
assert(w:pause()==true,'pause acts on the instance, not the source')
local u=assert(hd2.sounds.play('boom',{owner='mods/t/h2',unit=newproxy()}))
assert(select(2,u:set_parameter('rounds_fired',1))=='SHARED_SOURCE')
-- No proven engine id (a queued post, a shared instance, an unreadable record): those four are refused.
for _,state in ipairs({2,3,4,1})do
    ENTRY.state=state
    local q=assert(hd2.sounds.play('boom',{owner='mods/t/q'..state}))
    assert(q.wwise==nil)
    local n=#calls
    for _,m in ipairs({'pause','resume','is_playing','elapsed'})do
        local r,rc=q[m](q)
        assert(r==nil and rc=='UNPROVEN_ID',m)
    end
    assert(#calls==n)
    assert(q:describe().controls==false and q:describe().controls_reason)
    assert(q:stop()==true,'stop takes the plugin\'s own id')
end
ENTRY.state=nil
local q=assert(hd2.sounds.play('boom',{owner='mods/t/q'}))
assert(q.wwise==nil and select(2,q:pause())=='UNPROVEN_ID')
ENTRY.state=0
-- Stopped: no more calls; is_playing is false.
assert(h:stop()==true and h:is_playing()==false)
assert(select(2,h:set_parameter('rounds_fired',1))=='STOPPED')
assert(select(2,h:pause())=='STOPPED')
-- Source calls share the mod's budget; reads do not.
local r=assert(hd2.sounds.play('boom',{owner='mods/t/rate',position={0,0,0}}))
local ok=0
for _=1,40 do if r:set_parameter('rounds_fired',1)then ok=ok+1 end end
assert(ok==S.RATE-1,ok)
for _=1,40 do assert(r:is_playing()==true)end
return 'ok'
''')


class PluginMapTests(unittest.TestCase):
    def test_the_counter_map_is_read_through_the_plugins_own_hash(self):
        def h(k):
            x = (k * 0x5BD1E995) & 0xFFFFFFFF
            x ^= x >> 24
            return (x * 0x5BD1E995) & 0xFFFFFFFF
        keys = [1, 2, 101, 0xDEADBEEF, 0xFFFFFFFE]
        body = r'''
local P=require('hd2runtime/runtime/wwise_plugin')
local D=require('hd2runtime/domains/wwise_plugin')
local b=require('hd2runtime/core/bytes')
for k,v in pairs(%s)do assert(P.hash(k)==v,k)end
-- A fake plugin image: its header, every pinned instruction, the manager and a counter map with a chain.
local BASE=0x180000000
local mem={}
local function put(at,s)for i=1,#s do mem[at+i-1]=s:byte(i)end end
local function u32(v)return string.char(v%%256,math.floor(v/256)%%256,math.floor(v/65536)%%256,math.floor(v/16777216)%%256)end
local function u64(v)return u32(v%%4294967296)..u32(math.floor(v/4294967296))end
local header=string.rep('\0',4096)
put(BASE,header);put(BASE,'MZ');put(BASE+60,u32(64));put(BASE+64,'PE\0\0');put(BASE+64+80,u32(D.imageSize))
for _,pin in ipairs(D.pins)do put(BASE+pin.rva,b.unhex(pin.hex))end
local MANAGER,ENTRIES=0x20000000,0x30000000
put(BASE+D.counterMap.managerGlobal,u64(MANAGER))
local M=MANAGER+D.counterMap.map
put(M,string.rep('\0',0x28));put(M+0x10,u64(ENTRIES));put(M+0x20,u32(3));put(M+0x24,u32(8))
for i=0,7 do put(ENTRIES+16*i,u32(0)..u32(0)..u32(0)..u32(0xFFFFFFFE))end
local function bucket(k)return P.hash(k)%%8 end
-- counter 101 in its bucket; counter 7 chained behind another key in its bucket.
put(ENTRIES+16*bucket(101),u32(101)..u32(0)..u32(5001)..u32(0x7FFFFFFF))
local b7=bucket(7)
local spare=(b7+1)%%8==bucket(101)and(b7+2)%%8 or(b7+1)%%8
put(ENTRIES+16*b7,u32(999)..u32(0)..u32(1)..u32(spare))
put(ENTRIES+16*spare,u32(7)..u32(2)..u32(0)..u32(0x7FFFFFFF))
local view={}
function view.read(at,n)local t={}for i=0,n-1 do local v=mem[at+i];if v==nil then return nil end;t[#t+1]=string.char(v)end
    return table.concat(t)end
function view.pointer(at)local s=view.read(at,8);if not s then return nil end;return b.u32(s,0)+b.u32(s,4)*4294967296 end
function view.proves(at,hex)local e=b.unhex(hex);return view.read(at,#e)==e end
local world={view=view,runtime={module=function(n)return n==D.module and'H'or nil end,address=function()return BASE end}}
P.reset_for_tests()
assert(P.prove(world))
local e=assert(P.counter_entry(world,101))
assert(e.state==0 and e.id==5001)
e=assert(P.counter_entry(world,7))
assert(e.state==2 and e.id==0,'followed the chain')
assert(P.counter_entry(world,12345)==nil)
-- A changed instruction or image size: not proven, nothing read.
local pin=D.pins[#D.pins]
mem[BASE+pin.rva]=(mem[BASE+pin.rva]+1)%%256
P.reset_for_tests()
local ok,why=P.prove(world)
assert(ok==nil and why:find('changed',1,true))
assert(P.counter_entry(world,101)==nil)
return 'ok'
''' % ('{' + ','.join('[%d]=%d' % (k, h(k)) for k in keys) + '}')
        self.assertEqual(run(body), b'ok')


if __name__ == '__main__':
    unittest.main()
