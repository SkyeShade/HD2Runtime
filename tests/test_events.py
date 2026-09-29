"""Event bus, timers, mod contexts and keybinds (offline, on the game's own lua51.dll)."""
import unittest

from support import run

PRELUDE = r'''
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local events=require('hd2runtime/runtime/events')
local input=require('hd2runtime/runtime/input')
local api=require('hd2runtime/api/events')
local scheduler=require('hd2runtime/runtime/scheduler')
events.reset_for_tests();input.reset_for_tests()
local function tick(n,dt)for _=1,(n or 1)do if update then update(dt or 0.1)end end end
local function native(name,payload)events.queue(name,payload or{})end
'''


class EventBusTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_order_priority_once_and_unsubscribe(self):
        self.lua(r'''
local seen={}
local a=api.events.on('player_died',function(e)seen[#seen+1]='a'end,{owner='mods/t/a'})
local b=api.events.on('player_died',function(e)seen[#seen+1]='b'end,{owner='mods/t/b',priority=5})
local c=api.events.on('player_died',function(e)seen[#seen+1]='c'end,{owner='mods/t/c'})
local o=api.events.once('player_died',function(e)seen[#seen+1]='o'end,{owner='mods/t/o'})
assert(update,'the first subscription attaches the update watch')
native('player_died');tick()
assert(table.concat(seen)=='baco',table.concat(seen))
assert(o.state=='complete')
seen={}
a:disable();native('player_died');tick()
assert(table.concat(seen)=='bc',table.concat(seen))
a:enable();c:unsubscribe();native('player_died');tick()
assert(table.concat(seen)=='bcba',table.concat(seen))
assert(c.state=='removed')
-- A payload carries name, time, frame, mission and the native cause.
local got
api.events.on('player_died',function(e)got=e end,{owner='mods/t/p'})
native('player_died',{position={1,2,3}});tick()
assert(got.event=='player_died'and got.cause.source=='native'and got.position[3]==3 and got.frame>0)
return 'ok'
''')

    def test_a_broken_callback_never_stops_the_others(self):
        self.lua(r'''
local second=0
api.events.on('entity_died',function()error('intentional failure')end,{owner='mods/t/broken',id='boom'})
api.events.on('entity_died',function()second=second+1 end,{owner='mods/t/healthy'})
for _=1,30 do native('entity_died');tick()end
assert(second==30,'the healthy subscriber ran every time: '..second)
assert(count('event entity_died callback failed (mod mods/t/broken, subscription')==3,'first failures logged in full')
assert(count('intentional failure')>=3)
assert(count('callback disabled (mod mods/t/broken')==1,'disabled after repeated failures')
local broken=events.subscriptions({owner='mods/t/broken'})[1]
assert(broken.state=='failed'and broken.failures==25,broken.state..' '..broken.failures)
-- A failing subscription with max_failures=0 is never disabled.
api.events.on('entity_died',function()error('again')end,{owner='mods/t/stubborn',max_failures=0})
for _=1,40 do native('entity_died');tick()end
assert(events.subscriptions({owner='mods/t/stubborn'})[1].state=='active')
assert(second==70)
return 'ok'
''')

    def test_subscribing_during_dispatch_is_safe(self):
        self.lua(r'''
local seen={}
local late
local first=api.events.on('player_died',function()
  seen[#seen+1]='first'
  late=api.events.on('player_died',function()seen[#seen+1]='late'end,{owner='mods/t/late'})
end,{owner='mods/t/first',priority=10})
local victim
victim=api.events.on('player_died',function()seen[#seen+1]='victim'end,{owner='mods/t/victim'})
api.events.on('player_died',function()seen[#seen+1]='remover';victim:unsubscribe()end,{owner='mods/t/remover',priority=5})
native('player_died');tick()
-- Additions start with the next event (late does not see this one); a removal takes effect at once (victim, removed
-- by an earlier subscriber, is not called), and the rest of the list still runs.
assert(table.concat(seen,',')=='first,remover',table.concat(seen,','))
first:unsubscribe();seen={}
native('player_died');tick()
assert(table.concat(seen,',')=='remover,late',table.concat(seen,','))
return 'ok'
''')

    def test_ids_make_registration_idempotent_and_the_engine_is_a_singleton(self):
        self.lua(r'''
local calls=0
local function register()return api.events.on('player_died',function()calls=calls+1 end,{owner='mods/t/idem',id='main'})end
local one=register();local two=register()
assert(one==two,'the same owner and id return the same subscription')
native('player_died');tick()
assert(calls==1,'one callback despite two registrations: '..calls)
-- Repeated require (even after package.loaded is cleared) returns the same engine and keeps subscriptions.
package.loaded['hd2runtime/runtime/events']=nil
local again=require('hd2runtime/runtime/events')
assert(again==events)
assert(#events.subscriptions({owner='mods/t/idem'})==1)
-- hd2.mod returns one context per id.
assert(api.mod('mods/t/ctx')==api.mod('mods/t/ctx'))
-- The scheduler holds exactly one engine watch.
assert(scheduler.active()==1,'one watch: '..scheduler.active())
return 'ok'
''')

    def test_bad_registrations_are_rejected_not_raised(self):
        self.lua(r'''
local unknown=api.events.on('entity_explodes',function()end,{owner='mods/t/x'})
assert(unknown.state=='rejected'and unknown.reason:find('unknown event entity_explodes',1,true),unknown.reason)
assert(count('event subscription entity_explodes (mods/t/x) rejected: unknown event')==1)
local blocked=api.events.on('entity_damage_pre',function()end,{owner='mods/t/x'})
assert(blocked.state=='rejected'and blocked.reason:find('EVENT_BLOCKED',1,true),blocked.reason)
local nofn=api.events.on('player_died',42,{owner='mods/t/x'})
assert(nofn.state=='rejected'and nofn.reason:find('must be a function',1,true))
assert(nofn:unsubscribe()==nofn and not nofn:active())
return 'ok'
''')

    def test_mission_scope_cleans_up(self):
        self.lua(r'''
local mod=api.mod('mods/t/mission')
local session_calls,mission_calls=0,0
mod:on('player_died',function()session_calls=session_calls+1 end)
events.begin_mission()
mod.mission.kills=3
local scoped=mod:on('player_died',function()mission_calls=mission_calls+1 end,{scope='mission'})
local timer=mod:every(0.5,function()end,{scope='mission'})
native('player_died');tick()
assert(session_calls==1 and mission_calls==1)
local _,epoch=events.mission()
events.end_mission()
assert(scoped.state=='expired','mission subscription expired: '..scoped.state)
assert(timer.state=='expired','mission timer expired: '..timer.state)
assert(mod.mission.kills==nil,'mission table cleared in place')
local _,after=events.mission()
assert(after>epoch,'the epoch advances so handles from that mission are invalid')
native('player_died');tick()
assert(session_calls==2 and mission_calls==1)
local refused=mod:after(1,function()end,{scope='mission'})
assert(refused.state=='rejected','a mission timer needs a mission')
return 'ok'
''')

    def test_timers(self):
        self.lua(r'''
local mod=api.mod('mods/t/timers')
local fired,repeats=0,0
-- Binary fractions keep the game clock exact.
local once=mod:after(0.375,function()fired=fired+1 end)
local rep=mod:every(0.25,function()repeats=repeats+1 end)
tick(2,0.125)
assert(fired==0 and repeats==1,fired..' '..repeats)
tick(1,0.125)
assert(fired==1 and once.state=='complete')
tick(6,0.125)
assert(repeats==4,repeats)
rep:cancel();tick(10,0.125)
assert(repeats==4)
-- A long frame skips missed intervals instead of replaying them in a burst.
local burst=0
mod:every(0.1,function()burst=burst+1 end)
tick(1,2.0)
assert(burst==1,burst)
-- Isolation: a failing timer is logged and the next still runs.
local ok2=false
mod:after(0,function()error('timer boom')end)
mod:after(0,function()ok2=true end)
tick()
assert(ok2 and count('timer callback failed (mod mods/t/timers')==1)
assert(mod:every(0.01,function()end).state=='rejected','below the minimum repeat interval')
-- Idempotent ids replace the earlier timer.
local a=mod:after(5,function()end,{id='tmr'});local b=mod:after(5,function()end,{id='tmr'})
assert(a.state=='cancelled'and b:active())
return 'ok'
''')

    def test_causes_follow_callbacks_and_timers(self):
        self.lua(r'''
local mod=api.mod('mods/t/cause')
local first,second,from_timer
mod:on('player_died',function(e)
  first=events.action_cause(mod.id,'heal')
  mod:after(0,function()from_timer=events.action_cause(mod.id,'explosion')end)
end)
native('player_died');tick();tick()
assert(first.source=='mod'and first.mod=='mods/t/cause'and first.depth==1 and first.parent.event=='player_died')
assert(from_timer.depth==1 and from_timer.parent.event=='player_died','the timer kept its origin event')
-- An event a mod caused carries depth; reacting to it goes one deeper.
mod:on('entity_died',function(e)second=events.action_cause(mod.id,'explosion')end)
native('entity_died',{cause={source='mod',mod='mods/t/cause',action='explosion#1',depth=1}});tick()
assert(second.depth==2,'depth '..second.depth)
return 'ok'
''')

    def test_owner_is_inferred_from_the_mod_resource(self):
        self.lua(r'''
_G.API=api
local chunk=assert(loadstring("return API.events.on('player_died',function()error('x')end),"
  .."API.after(1,function()end),API.input.bind('owner_test.key',{key='F10',on_press=function()end})",
  '@mods/author/owner_probe.lua'))
local sub,timer,binding=chunk()
assert(sub.owner=='mods/author/owner_probe',sub.owner)
assert(timer.owner=='mods/author/owner_probe',timer.owner)
assert(binding.owner=='mods/author/owner_probe',binding.owner)
native('player_died');tick()
assert(count('callback failed (mod mods/author/owner_probe')==1,'the log names the mod')
local anonymous=assert(loadstring("return API.events.on('player_died',function()end)",'=console'))()
assert(anonymous.owner=='unknown')
local explicit=api.events.on('player_died',function()end,{owner=42})
assert(explicit.state=='rejected')
return 'ok'
''')

    def test_watch_detaches_when_idle(self):
        self.lua(r'''
assert(update==nil,'no watch before anything registers')
local sub=api.events.on('player_died',function()end,{owner='mods/t/w'})
assert(update~=nil)
sub:unsubscribe();tick()
assert(update==nil,'the watch completes and the host update is restored')
local t=api.after(0.1,function()end,{owner='mods/t/w'})
assert(update~=nil);tick(2)
assert(update==nil)
return 'ok'
''')


class CatalogTests(unittest.TestCase):
    def test_generated_event_tables_are_fresh(self):
        import sys
        from support import ROOT
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_events
        import generate_event_natives
        import generate_event_entities
        self.assertFalse(generate_events.generate(check=True))
        self.assertFalse(generate_event_natives.generate(check=True))
        self.assertFalse(generate_event_entities.generate(check=True))

    def test_every_available_event_has_a_registered_source(self):
        self.assertEqual(run(PRELUDE + r'''
require('hd2runtime/runtime/event_sources')
local catalog=require('hd2runtime/domains/events_catalog')
for _,name in ipairs(catalog.names)do
  local spec=catalog.events[name]
  if spec.status=='available'then
    assert(events.state.sources[spec.source]or spec.source=='input','no source for '..name)
  else
    assert(spec.status=='blocked'and spec.reason,name)
  end
end
return 'ok'
'''), b'ok')


class ScriptValueTests(unittest.TestCase):
    def test_script_values_bind_to_ensure_with_every_guard(self):
        self.assertEqual(run(PRELUDE + r'''
local options=require('hd2runtime/api/options')
local ensure=require('hd2runtime/api/ensure')
local hd2=require('hd2runtime/api/hd2')
options.reset()
local mod=api.mod('mods/t/values')
local scale=mod:value({id='scale',min=0.5,max=1,step=0.05,default=0.9})
assert(mod:value({id='scale',min=0.5,max=1,step=0.05,default=0.9})==scale,'one handle per mod and id')
assert(scale:get()==0.9 and scale:available())
assert(scale:set(0.72)and scale:get()==0.7)                 -- snapped to the step
assert(scale:set(5)and scale:get()==1)                      -- clamped to max
assert(not scale:set(1),'unchanged: no notification')
assert(not scale:set(0/0))
local target=function()return hd2.booster('Vitality Enhancement'):tuning()end
local function start(request)return ensure.start({},function()end,request)end
-- The whole value domain passes the normal guards at declaration: an out-of-range domain is refused.
local wide=mod:value({id='wide',min=0,max=10,step=1,default=1})
local ok,why=pcall(start,{patch={id='bad',allow_unverified_effect=true,
 target=hd2.booster('Integrated Extinguishers'):tuning(),field=hd2.fields.booster.burn_decay_bonus,expect=0.5,value=wide}})
assert(not ok and tostring(why):find('reviewed range',1,true),tostring(why))
local w=start({patch={id='scaled',allow_unverified_effect=true,target=target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=scale}})
assert(w.bound and w.status~='waiting_for_options','a script value is ready at once: '..tostring(w.status))
-- A menu option cannot be set from code.
local page=hd2.options({id='menu_only',title='Menu Only'})
local slider=page:slider({id='s',label='S',min=0,max=1,step=0.5,default=0})
ok,why=pcall(slider.set,slider,1)
assert(not ok and tostring(why):find('only script values',1,true))
return 'ok'
'''), b'ok')


class InputTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + r'''
local keys,focused={},true
input.set_backend({focused=function()return focused end,down=function(code)return keys[code]==true end})
local VK=input.keys
''' + body), b'ok')

    def test_press_release_modifiers_and_focus(self):
        self.lua(r'''
local mod=api.mod('mods/t/input')
local presses,releases,downs=0,0,0
local b=mod:bind('input_test.action',{key='F6',on_press=function(d)presses=presses+1;assert(d.id=='input_test.action')end,
  on_release=function()releases=releases+1 end})
api.events.on('key_down',function(e)downs=downs+1;assert(e.binding=='input_test.action'and e.key=='F6')end,{owner='mods/t/input'})
tick()
keys[VK.F6]=true;tick();tick()
assert(presses==1 and downs==1,'one press while held: '..presses)
keys[VK.F6]=false;tick()
assert(releases==1)
-- Exact modifiers: Ctrl+F6 does not fire a plain F6 binding.
keys[0x11]=true;keys[VK.F6]=true;tick()
assert(presses==1)
keys[0x11]=false;keys[VK.F6]=false;tick()
local ctrl=0
mod:bind('input_test.ctrl',{key='Ctrl+F6',on_press=function()ctrl=ctrl+1 end})
keys[0x11]=true;keys[VK.F6]=true;tick()
assert(ctrl==1 and presses==1)
keys[0x11]=false;keys[VK.F6]=false;tick()
-- Losing focus releases a held binding and ignores keys.
keys[VK.F6]=true;tick();assert(presses==2)
focused=false;tick();assert(releases==2)
tick();assert(presses==2)
return 'ok'
''')

    def test_the_win32_backend_loads_on_the_game_luajit(self):
        self.assertEqual(run(PRELUDE + r'''
input.set_backend(nil)
local presses=0
api.mod('mods/t/win32'):bind('win32_probe.key',{key='F12',on_press=function()presses=presses+1 end})
tick(3)
assert(count('input unavailable')==0,'the real backend resolved every user32 export')
assert(presses==0,'this test process never owns the foreground window')
return 'ok'
'''), b'ok')

    def test_conflicts_and_ownership(self):
        self.lua(r'''
local a=api.mod('mods/t/a');local b=api.mod('mods/t/b')
local first=a:bind('mod_a.fire',{key='F7',on_press=function()end})
local second=b:bind('mod_b.fire',{key='F7',on_press=function()end})
assert(first.state=='active'and second.state=='conflict',second.state)
assert(second:describe().conflict.binding=='mod_a.fire')
assert(count('input binding mod_b.fire (mods/t/b) wants F7, already bound to mod_a.fire (mods/t/a)')==1)
-- Another mod cannot take over an id.
local stolen=b:bind('mod_a.fire',{key='F8',on_press=function()end})
assert(stolen.state=='rejected'and stolen.reason:find('already registered by mods/t/a',1,true))
-- The owner registering again updates in place (repeated startup).
local again=a:bind('mod_a.fire',{key='F7',on_press=function()end})
assert(again==first)
-- Resolving the conflict by rebinding.
assert(second:rebind('F8')and second.state=='active'and second.key=='F8')
-- Ids must be namespaced.
assert(a:bind('fire',{key='F9',on_press=function()end}).state=='rejected')
assert(a:bind('mod_a.bad',{key='Hyper+F9',on_press=function()end}).state=='rejected')
first:unbind()
assert(b:bind('mod_b.other',{key='F7',on_press=function()end}).state=='active','an unbound key is free again')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
