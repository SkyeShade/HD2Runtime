"""Scripting services for UI and game mods (docs/events.md): hd2.build(), hd2.on_frame, raw key state
(hd2.input.down / pressed / released) and per-mod saved data (hd2.store). Offline, on the game's own lua51.dll."""
import shutil
import tempfile
import unittest
from pathlib import Path

from support import ROOT, run
import sys

sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

FIXTURE = (ROOT / 'tests/event_world_fixture.lua').read_text(encoding='utf-8')
PRELUDE = r'''
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local W=(function()
''' + FIXTURE + r'''
end)()
local events=require('hd2runtime/runtime/events')
local input=require('hd2runtime/runtime/input')
local world_module=require('hd2runtime/runtime/event_world')
local fingerprint=require('hd2runtime/core/fingerprint')
events.reset_for_tests();input.reset_for_tests();fingerprint.reset()
world_module.set_runtime(W.runtime)
local hd2=require('hd2runtime/api/hd2')
local function tick(n,dt)for _=1,(n or 1)do if update then update(dt or 0.125)end end end
'''


class ScriptingServiceTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_build_status_tells_a_wrong_build_from_not_ready_and_hashes_once(self):
        self.lua(r'''
local status,info=hd2.build()
assert(status=='matched',tostring(status));assert(#info.pinned==12 and info.reason==nil)
local hashes=0
local real_hash,real_module=W.runtime.module_hash,W.runtime.module
W.runtime.module_hash=function(h)hashes=hashes+1;return 'another build'end
-- A new game.dll identity (another loaded module) is hashed again; a wrong build is remembered, not re-hashed.
W.runtime.module=function(name)if name=='game.dll'then return 'other.dll'end;return real_module(name)end
W.runtime.address=(function(address)return function(h)if h=='other.dll'then return 0x7000000 end;return address(h)end end)(W.runtime.address)
world_module.set_runtime(W.runtime)
for _=1,50 do assert(hd2.build()=='mismatched')end
assert(hashes==2,'a wrong build is hashed once per loaded module: '..hashes)
local state,why=hd2.game_state()
assert(state==nil and why:find('unsupported build fingerprint',1,true),tostring(why))
assert(hashes==2,'game_state() on a wrong build re-hashed: '..hashes)
-- Not loaded yet: not_ready with the reason, nothing cached.
W.runtime.module=function()return nil end
world_module.set_runtime(W.runtime)
local status2,info2=hd2.build()
assert(status2=='not_ready'and info2.reason=='game modules not loaded',tostring(info2.reason))
-- A hash that cannot complete raises inside: not_ready, never cached as a wrong build.
W.runtime.module=real_module
W.runtime.module_hash=function()error('module read failed')end
fingerprint.reset();world_module.set_runtime(W.runtime)
local status3,info3=hd2.build()
assert(status3=='not_ready'and info3.reason:find('module read failed',1,true),tostring(info3.reason))
W.runtime.module_hash=real_hash
assert(hd2.build()=='matched','a failed hash was not cached')
return 'ok'
''')

    def test_on_frame_runs_every_tick_with_dt_and_can_pause_and_cancel(self):
        self.lua(r'''
local seen,handle_seen={},nil
local h=hd2.on_frame(function(dt,handle)seen[#seen+1]=dt;handle_seen=handle end,{owner='mods/t/frame'})
assert(h.state=='active'and h.kind=='frame',h.state)
tick(3,0.016)
assert(#seen==3 and math.abs(seen[1]-0.016)<1e-9 and handle_seen==h,#seen)
h:disable();tick(2);assert(#seen==3)
h:enable();tick(1);assert(#seen==4)
assert(h:remaining()==nil and h:describe().kind=='frame')
-- Order is registration order; one added inside a callback runs from the next tick.
local order={}
local late
hd2.on_frame(function()order[#order+1]='a'
    if not late then late=hd2.on_frame(function()order[#order+1]='late'end,{owner='mods/t/frame'})end end,
    {owner='mods/t/frame'})
hd2.on_frame(function()order[#order+1]='b'end,{owner='mods/t/frame'})
tick(1);assert(table.concat(order,',')=='a,b',table.concat(order,','))
order={};tick(1);assert(table.concat(order,',')=='a,b,late',table.concat(order,','))
-- Cancelled callbacks stop at once; a failing one is disabled after max failures and never stops the others.
h:cancel();local n=#seen;tick(2);assert(#seen==n and h.state=='cancelled')
local healthy=0
local bad=hd2.on_frame(function()error('boom')end,{owner='mods/t/bad'})
hd2.on_frame(function()healthy=healthy+1 end,{owner='mods/t/ok'})
tick(30)
assert(healthy==30 and bad.state=='failed',bad.state)
assert(count('frame callback failed (mod mods/t/bad')>=1)
-- The same id replaces the earlier callback; hd2.every keeps its floor and points at on_frame.
local first,second=0,0
hd2.on_frame(function()first=first+1 end,{owner='mods/t/id',id='loop'})
hd2.on_frame(function()second=second+1 end,{owner='mods/t/id',id='loop'})
tick(2);assert(first==0 and second==2,first..' '..second)
local every=hd2.every(0.01,function()end,{owner='mods/t/id'})
assert(every.state=='rejected'and every.reason:find('hd2.on_frame',1,true),every.reason)
-- Mission scope: expires with the mission.
events.begin_mission({});local m=0
hd2.on_frame(function()m=m+1 end,{owner='mods/t/m',scope='mission'})
tick(2);events.end_mission();tick(2);assert(m==2,m)
-- A mod context has it too.
local ctx=hd2.mod('mods/t/ctx');local c=0
local ch=ctx:on_frame(function()c=c+1 end);tick(1);assert(c==1 and ch.owner=='mods/t/ctx')
return 'ok'
''')

    def test_raw_keys_report_down_pressed_released_once_per_tick_and_only_with_focus(self):
        self.lua(r'''
local held,focus={},true
input.set_backend({focused=function()return focus end,down=function(code)return held[code]==true end,
    mouse=function()return 10,20,1920,1080 end})
local W_,ENTER=0x57,0x0D
assert(hd2.input.down('W')==false and hd2.input.pressed('w')==false)
local presses,releases,downs=0,0,0
hd2.on_frame(function()
    if hd2.input.pressed('W')then presses=presses+1 end
    if hd2.input.released('W')then releases=releases+1 end
    if hd2.input.down('W')then downs=downs+1 end
end,{owner='mods/t/keys'})
held[W_]=true;tick(3)
assert(presses==1 and downs==3 and releases==0,presses..' '..downs)
held[W_]=nil;tick(2)
assert(releases==1 and presses==1,releases)
-- No focus: every key reads up; regaining the focus with the key held is not a press.
held[W_]=true;focus=false;tick(2)
assert(hd2.input.down('W')==false and presses==1)
focus=true;tick(2)
assert(hd2.input.down('W')==true and presses==1,'a key held while the focus came back is no press: '..presses)
-- Modifiers and mouse buttons by name; aliases; unknown names raise.
held[0x11]=true;assert(hd2.input.down('Ctrl')and hd2.input.down('control'))
assert(hd2.input.down('Return')==false)
held[0x01]=true;assert(hd2.input.down('MOUSE1'))
assert(not pcall(hd2.input.down,'NOPE'))
assert(not pcall(hd2.input.pressed,42))
local names=hd2.input.keys(true);local has={}
for _,n in ipairs(names)do has[n]=true end
assert(has.CTRL and has.MOUSE1 and has.F6 and not hd2.input.keys().CTRL)
assert(hd2.input.focused()==true)
local m=hd2.input.mouse();assert(m.x==10 and m.w==1920)
return 'ok'
''')

    def test_store_saves_values_between_sessions_and_keeps_mods_apart(self):
        folder = Path(tempfile.mkdtemp(prefix='hd2store'))
        try:
            setup = 'local store_module=require("hd2runtime/runtime/mod_store")\nstore_module.set_folder(' \
                + lua(str(folder)) + ')\n'
            self.lua(setup + r'''
local ctx=hd2.mod('mods/t/arcade')
local s=ctx:store()
assert(s:get('high',0)==0)
s:set('high',4200):set('name','HELLDIVER'):set('scores',{10,20,30}):set('opts',{sound=true,volume=0.5})
local t=s:get('scores');t[1]=999;assert(s:get('scores')[1]==10,'get returns a copy')
-- Saved shortly after (one write for the burst), or at once with save().
tick(1);assert(s:describe().saved==0 and s:describe().dirty)
tick(10);assert(s:describe().saved==1 and not s:describe().dirty,'debounced save')
-- Refused values raise and change nothing.
assert(not pcall(s.set,s,'bad',function()end))
assert(not pcall(s.set,s,'nan',0/0))
local cyc={};cyc.self=cyc;assert(not pcall(s.set,s,'cyc',cyc))
assert(not pcall(s.set,s,'',1))
assert(not pcall(s.set,s,'mixed',{1,x=2}))
-- Another mod has its own store.
local other=hd2.mod('mods/t/other'):store();assert(other:get('high')==nil)
other:set('high',1);assert(other:save()==true)
-- Reload from disk (a new game session).
store_module.reset_for_tests()
local again=hd2.mod('mods/t/arcade'):store()
assert(again:get('high')==4200 and again:get('name')=='HELLDIVER',tostring(again:get('high')))
assert(again:get('scores')[3]==30 and again:get('opts').volume==0.5 and again:get('opts').sound==true)
assert(table.concat(again:keys(),',')=='high,name,opts,scores')
again:set('high',nil);again:save()
store_module.reset_for_tests()
assert(hd2.mod('mods/t/arcade'):store():get('high')==nil)
assert(hd2.mod('mods/t/other'):store():get('high')==1)
-- The calling mod is found the way hd2.mod() finds it; no mod -> refused.
local ok_scoped,via=pcall(hd2.events.run_as,'mods/t/other',function()return hd2.store()end)
assert(ok_scoped and via:get('high')==1)
return 'ok'
''')
            files = sorted(p.name for p in folder.iterdir())
            self.assertEqual(files, ['mods_t_arcade.json', 'mods_t_other.json'])
            text = (folder / 'mods_t_arcade.json').read_text(encoding='utf-8')
            self.assertEqual(text, '{"name":"HELLDIVER","opts":{"sound":true,"volume":0.5},"scores":[10,20,30]}')
            # A damaged file is moved aside and the store starts empty (logged), never raising into the mod.
            (folder / 'mods_t_arcade.json').write_text('{"name":', encoding='utf-8')
            self.lua(setup + r'''
local s=hd2.mod('mods/t/arcade'):store()
assert(s:get('name')==nil and s:describe().load_error,'corrupt file starts empty')
assert(count('could not be read')==1)
s:set('name','again');assert(s:save())
return 'ok'
''')
            self.assertTrue((folder / 'mods_t_arcade.json.corrupt').exists())
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_store_json_round_trips_strings_and_numbers_exactly(self):
        self.lua(r'''
local store=require('hd2runtime/runtime/mod_store')
local value={text='quote " backslash \\ newline \n tab \t ctl \1 utf8 é',int=-42,big=9007199254740991,
    frac=0.1,tiny=1e-300,list={true,false,'x'},empty={}}
local back=store.decode(store.encode(value))
for k,v in pairs(value)do if type(v)~='table'then assert(back[k]==v,k..' '..tostring(back[k]))end end
assert(back.list[1]==true and back.list[2]==false and back.list[3]=='x' and next(back.empty)==nil)
assert(store.decode(' {"a" : [1, 2.5e3, -0.5], "u":"\\u00e9\\u0041"} ').a[2]==2500)
assert(store.decode('{"u":"\\u00e9\\u0041"}').u=='é'..'A')
for _,bad in ipairs({'{','[1,]','{"a":1}x','nul','"abc','{"a" 1}'})do assert(not pcall(store.decode,bad),bad)end
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
