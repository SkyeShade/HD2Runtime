"""Hand-written event scripting (docs/event-scripting.md): snapshots that outlive entities, delayed callbacks, per-mod
ownership, source attribution, gameplay actions, and the example mods exactly as their built ZIPs ship them."""
import importlib.util
import json
import unittest

from support import ROOT, run
import sys

sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

FIXTURE = (ROOT / 'tests/event_world_fixture.lua').read_text(encoding='utf-8')
_spec = importlib.util.spec_from_file_location('hd2_sdk_cli', ROOT / 'sdk/hd2.py')
SDK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SDK)


def wrapped(project):
    """An example addon exactly as the SDK builds it (dependency check + startup run as the mod's resource id)."""
    folder = ROOT / 'examples/projects' / project
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


PRELUDE = r'''
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local W=(function()
''' + FIXTURE + r'''
end)()
local events=require('hd2runtime/runtime/events')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local sources=require('hd2runtime/runtime/event_sources')
local actions=require('hd2runtime/api/actions')
events.reset_for_tests();handles.reset_for_tests();actions.reset_for_tests()
world_module.set_runtime(W.runtime)
package.preload['mods/skyeshade/hd2runtime']=function()return require('hd2runtime/api/hd2')end
local hd2=require('mods/skyeshade/hd2runtime')
rawset(_G,'CowboyBingusModLoader',{api=1,version=16})
local function tick(n,dt)for _=1,(n or 1)do if update then update(dt or 0.125)end end end
local LOCAL,OTHER='1111222233334444','5555666677778888'
local DEVASTATOR,MARAUDER='B92435FBF60F0748','0002BA767DF856F3'   -- soldier_mg, conscript_tier_3
local LIBERATOR,ERUPTOR,HELLPOD='968211C0033DCE64','B6AFF2195568767F','73F8498BFFDCF415'
local function mission(opts)
    W.players({{peer=LOCAL,avatar=100}},LOCAL)
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
    W.unit(7100,0,0,0)
    W.state(4,opts);tick()
end
'''


class EventScriptingTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_a_corpse_observed_death_keeps_identity_and_position_for_a_delayed_callback(self):
        self.lua(r'''
local saved,fired={},{}
hd2.events.run_as('mods/t/delayed',function()
    hd2.events.on('entity_died',function(event)
        saved=event
        saved.timer=hd2.after(2,function()
            -- Snapshot values only: count the game reads this callback makes.
            local view=sources.health.world.view
            local before=view.reads
            fired.identity=event.semantic_id
            fired.name=event.name
            fired.x,fired.y,fired.z=event.position.x,event.position.y,event.position.z
            fired.entity_id=event.entity_id
            fired.handle_identity=event.entity.semantic_id
            fired.reads=view.reads-before
            fired.valid=event.entity:is_valid()
            fired.written=pcall(function()event.position.x=0 end)
        end)
    end)
end)
mission()
W.add{entity=601,type=DEVASTATOR,unit=9101,health=750};W.unit(9101,4,5,6)
tick()
W.set(601,{health=100,creditor=LOCAL});tick()
W.replace_by_corpse(601,700);tick()                  -- replaced before a poll saw the dead state
assert(saved.observed=='corpse'and saved.corpse_id==700,'corpse-observed death')
assert(saved.semantic_id=='enemy/v1/automatons/soldier_mg'and saved.entity:is('enemy/v1/automatons/soldier_mg'))
assert(saved.entity_id==601 and saved.faction=='automatons'and saved.enemy and saved.display_name==nil,
    'the class has no proven wiki name')
assert(saved.timer.owner=='mods/t/delayed','the timer belongs to the mod whose callback started it')
W.remove_unit(9101)                                   -- the corpse goes too: nothing of it is left in the game
tick(20)                                              -- 2.5 s
assert(fired.identity=='enemy/v1/automatons/soldier_mg'and fired.handle_identity==fired.identity)
assert(fired.x==4 and fired.y==5 and fired.z==6,'the death position survives destruction')
assert(fired.entity_id==601 and fired.reads==0,'snapshot fields never read the game: '..tostring(fired.reads))
assert(fired.valid==false and fired.written==false,'the handle is invalid; the position is read-only')
assert(tostring(saved.position)=='(4.00, 5.00, 6.00)'and saved.position:copy().x==4)
return 'ok'
''')

    def test_mission_cleanup_cancels_delayed_callbacks_and_they_never_come_back(self):
        self.lua(r'''
local fired,timer=0
hd2.events.run_as('mods/t/cleanup',function()
    hd2.events.on('entity_died',function(event)
        timer=hd2.after(5,function()fired=fired+1 end,{scope='mission'})
    end)
end)
mission()
W.add{entity=602,type=MARAUDER,unit=9102,health=100};W.unit(9102,1,1,1);tick()
W.set(602,{life=2,health=0});tick()
assert(timer and timer:active()and timer.owner=='mods/t/cleanup')
W.state(3);tick()                                     -- the mission ends before the timer is due
assert(timer.state=='expired'and not timer:active(),timer.state)
tick(80)                                              -- 10 s later
assert(fired==0,'an expired mission timer never fires')
assert(timer:cancel().state=='expired'and timer:remaining()==nil,'and cannot be revived')
local session=hd2.after(0.5,function()fired=fired+10 end,{owner='mods/t/cleanup'})
tick(8)
assert(fired==10,'a session timer runs outside a mission')
return 'ok'
''')

    def test_everything_a_mod_registers_belongs_to_it_without_passing_its_id(self):
        self.lua(r'''
local sub,timer,binding,inner_timer,context
hd2.events.run_as('mods/author/alpha',function()
    context=hd2.mod()
    sub=hd2.events.on('entity_died',function()inner_timer=hd2.after(1,function()end)end)
    timer=hd2.every(1,function()end)
    binding=hd2.input.bind('alpha.key',{key='F11',on_press=function()end})
end)
assert(context.id=='mods/author/alpha'and hd2.mod('mods/author/alpha')==context)
assert(sub.owner=='mods/author/alpha'and timer.owner=='mods/author/alpha'and binding.owner=='mods/author/alpha')
mission()
W.add{entity=603,type=MARAUDER,unit=0,health=100};tick()
W.set(603,{life=2,health=0});tick()
assert(inner_timer.owner=='mods/author/alpha','a timer started inside a callback belongs to that callback\'s mod')
-- An explicit owner still wins; outside any mod scope a console chunk cannot use hd2.mod() without an id.
local explicit=hd2.events.on('entity_died',function()end,{owner='mods/author/beta'})
assert(explicit.owner=='mods/author/beta')
local console=assert(loadstring('return hd2.mod()','=console'))
setfenv(console,setmetatable({hd2=hd2},{__index=_G}))
local ok,why=pcall(console)
assert(not ok and tostring(why):find('cannot tell which mod',1,true),tostring(why))
-- A startup error propagates out of the scope, and the scope does not leak.
assert(not pcall(hd2.events.run_as,'mods/author/gamma',function()error('boom')end))
assert(hd2.events.owner()=='unknown','no scope is left behind')
return 'ok'
''')

    def test_a_failing_callback_of_one_mod_never_stops_another(self):
        self.lua(r'''
local healthy=0
hd2.events.run_as('mods/t/broken',function()hd2.events.on('entity_died',function()error('broken on purpose')end)end)
hd2.events.run_as('mods/t/healthy',function()hd2.events.on('entity_died',function()healthy=healthy+1 end)end)
mission()
W.add{entity=604,type=MARAUDER,unit=0,health=100};tick()
W.set(604,{life=2,health=0});tick()
assert(healthy==1)
assert(count('callback failed (mod mods/t/broken')==1,'the failure names the mod')
return 'ok'
''')

    def test_credited_kills_are_named_per_source_and_a_shared_source_stays_unnamed(self):
        self.lua(r'''
local credited
hd2.events.run_as('mods/t/credit',function()
    hd2.events.on('player_kill_credited',function(event)credited=event end)
end)
local natives=require('hd2runtime/domains/event_natives')
local K=natives.stats.keys
mission()
W.stat(10,K.dealt_kills,0,1,LIBERATOR);tick(2)
W.stat(10,K.dealt_kills,2,1,LIBERATOR);W.stat(10,K.dealt_kills,1,2,HELLPOD);W.stat(10,K.dealt_kills,3,3,ERUPTOR);tick()
assert(credited and credited.kills==6 and credited.total==6,tostring(credited and credited.kills))
local by={}
for _,source in ipairs(credited.sources)do by[source.type]=source end
assert(by[LIBERATOR].name=='AR-23 Liberator'and by[LIBERATOR].kills==2)
assert(by[ERUPTOR].name=='R-36 Eruptor'and by[ERUPTOR].kills==3)
assert(by[HELLPOD].name==nil and by[HELLPOD].kills==1,'the hellpod is shared by many stratagems: unnamed')
assert(credited.sources[1].type==ERUPTOR,'largest first')
return 'ok'
''')

    def test_an_explosion_is_requested_only_when_every_guard_holds(self):
        self.lua(r'''
local P={x=10,y=20,z=3}
-- A mod that acts has subscriptions: they keep the game clock (the rate limit's time base) running.
hd2.events.run_as('mods/t/boom',function()hd2.events.on('mission_started',function()end)end)
local function spawn(what,opts)
    local action
    hd2.events.run_as('mods/t/boom',function()action=hd2.explosions.spawn(what,opts or{position=P})end)
    return action
end
-- Outside a mission.
local a=spawn('R-36 Eruptor')
assert(a.status=='refused'and a.code=='NOT_IN_MISSION'and a.owner=='mods/t/boom',tostring(a.code))
-- Unknown explosions fail closed before anything else.
assert(spawn(158).code=='UNKNOWN_EXPLOSION','a raw id is refused')
assert(spawn('AR-23 Liberator').code=='UNKNOWN_EXPLOSION','a weapon without a catalogued explosion')
assert(spawn('Hellbomb').code=='NOT_IN_MISSION','the named Hellbomb resolves (proven code literal)')
assert(spawn('Orbital Hellbomb').code=='UNKNOWN_EXPLOSION','an unknown name is refused')
assert(spawn('GP-31 Grenade Pistol').code=='ASSET_UNKNOWN','a package nobody can load is refused')
assert(spawn('R-36 Eruptor',{position={x=0/0,y=0,z=0}}).code=='INVALID_POSITION')
assert(spawn('R-36 Eruptor',{position={y=1,z=2}}).code=='INVALID_POSITION','a missing axis refuses, never raises')
-- A client cannot change enemy health.
mission({host=false})
assert(spawn('R-36 Eruptor').code=='HOST_ONLY')
W.state(3);tick()
mission({host=true})
-- The request: the local avatar is source and owner, the local peer the creditor, the catalogued type.
a=spawn('R-36 Eruptor')
assert(a.status=='requested'and a:requested(),tostring(a.code)..' '..tostring(a.reason))
local call=W.runtime.explosions[1]
assert(call.type==158 and call.source==100 and call.owner==100 and call.peer==LOCAL,call.peer)
assert(call.x==10 and call.y==20 and call.z==3)
assert(count('explosion R-36 Eruptor requested at (10.00, 20.00, 3.00) by mods/t/boom')==1)
-- A typed handle works the same way.
assert(spawn(hd2.explosions.of('CB-9 Exploding Crossbow')).status=='requested'and W.runtime.explosions[2].type==59)
-- Game-side guards: a full queue, a settings record that does not carry the type, a changed request function.
W.queue_count(256)
assert(spawn('R-36 Eruptor').code=='QUEUE_FULL')
W.queue_count(0)
-- Rate limit: 6 at once per mod; 3 attempts were made above (the full-queue attempt counts too).
local codes={}
for _=1,4 do local attempt=spawn('R-36 Eruptor');codes[#codes+1]=attempt.code or attempt.status end
assert(table.concat(codes,',')=='requested,requested,requested,RATE_LIMITED',table.concat(codes,','))
tick(40)                                              -- 5 s refill
-- The named Hellbomb explosions: the NUX-223 detonation (type 242) and the B-100 Portable Hellbomb (type 125), the
-- code literals Runtime re-proves with its event pins. Names are case-insensitive.
a=spawn('hellbomb')
assert(a.status=='requested'and a.explosion=='NUX-223 Hellbomb'and W.runtime.explosions[6].type==242,tostring(a.code))
assert(W.runtime.explosions[6].source==100 and W.runtime.explosions[6].owner==100)
a=spawn('B-100 Portable Hellbomb')
assert(a.status=='requested'and W.runtime.explosions[7].type==125,tostring(a.code))
local listed={}
for _,item in ipairs(hd2.explosions.list())do listed[item.name]=item end
assert(listed['NUX-223 Hellbomb'].source=='behavior'and listed['NUX-223 Hellbomb'].assets_known)
assert(listed['R-36 Eruptor'].source=='weapon'and listed['R-36 Eruptor'].weapon=='R-36 Eruptor')
local X=require('hd2runtime/domains/event_natives').explosion
W.write(W.GAME+X.rva,string.char(0xCC))
assert(spawn('R-36 Eruptor').code=='EXPLOSION_UNAVAILABLE','a changed request function is never called')
assert(#W.runtime.explosions==7,#W.runtime.explosions)
return 'ok'
''')

    def test_a_projectile_is_fired_only_when_every_guard_holds(self):
        self.lua(r'''
local P,D={x=10,y=20,z=3},{x=0,y=0,z=-2}
hd2.events.run_as('mods/t/shoot',function()hd2.events.on('mission_started',function()end)end)
local function spawn(what,opts)
    local action
    hd2.events.run_as('mods/t/shoot',function()action=hd2.projectiles.spawn(what,opts or{position=P,direction=D})end)
    return action
end
-- Outside a mission; unknown names and raw ids fail closed first.
assert(spawn('R-36 Eruptor').code=='NOT_IN_MISSION')
assert(spawn(158).code=='UNKNOWN_PROJECTILE'and spawn('Orbital Laser').code=='UNKNOWN_PROJECTILE')
assert(spawn('R-36 Eruptor',{position=P,direction={x=0,y=0,z=0}}).code=='INVALID_DIRECTION')
assert(spawn('R-36 Eruptor',{position={x=0/0,y=0,z=0},direction=D}).code=='INVALID_POSITION')
assert(spawn('R-36 Eruptor',{position={y=0,z=0},direction=D}).code=='INVALID_POSITION','a missing axis refuses')
assert(spawn('R-36 Eruptor',{position=P,direction={y=1,z=0}}).code=='INVALID_DIRECTION','a missing axis refuses')
mission({host=false})
assert(spawn('R-36 Eruptor').code=='HOST_ONLY')
W.state(3);tick()
mission({host=true})
-- The request: the local avatar fires it; the direction is normalised; the catalogued type.
local a=spawn('R-36 Eruptor')
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
local shot=W.runtime.projectiles[1]
local eruptor
for _,item in ipairs(hd2.projectiles.list())do if item.weapon=='R-36 Eruptor'then eruptor=item end end
assert(shot.type==eruptor.type and shot.entity==100 and shot.dz==-1 and shot.dx==0,shot.type)
assert(count('projectile R-36 Eruptor fired from (10.00, 20.00, 3.00) by mods/t/shoot')==1)
-- Another firer is refused; the local player's own handle is accepted.
assert(spawn('R-36 Eruptor',{position=P,direction=D,firer={id=555}}).code=='FIRER_UNSUPPORTED')
assert(spawn('R-36 Eruptor',{position=P,direction=D,firer=hd2.local_player()}).status=='requested')
-- An inactive projectile system (the game's own gate) and a table entry that does not carry the type.
W.projectiles_active(false)
assert(spawn('R-36 Eruptor').code=='NOT_IN_MISSION')
W.projectiles_active(true)
local X=require('hd2runtime/domains/event_natives').projectile
W.write(W.GAME+X.rva,string.char(0xCC))
assert(spawn('R-36 Eruptor').code=='PROJECTILE_UNAVAILABLE','a changed wrapper is never called')
assert(#W.runtime.projectiles==2,#W.runtime.projectiles)
return 'ok'
''')

    def test_a_projectile_rate_limit_and_asset_wait(self):
        self.lua(r'''
local P,D={x=1,y=2,z=3},{x=1,y=0,z=0}
hd2.events.run_as('mods/t/shoot',function()hd2.events.on('mission_started',function()end)end)
mission({host=true})
local function spawn(what)
    local action
    hd2.events.run_as('mods/t/shoot',function()action=hd2.projectiles.spawn(what,{position=P,direction=D})end)
    return action
end
local codes={}
for _=1,13 do codes[#codes+1]=spawn('R-36 Eruptor').code or'ok'end
assert(codes[12]=='ok'and codes[13]=='RATE_LIMITED',table.concat(codes,','))
tick(40)
for package in pairs(require('hd2runtime/domains/package_residency').packages)do W.runtime.packages[package]='absent'end
local fired=#W.runtime.projectiles
local a=spawn('R-36 Eruptor')
assert(a.status=='waiting_for_assets',a.status)
tick(8)
-- The fixture has no package system to request through: the gate refuses, and nothing is fired.
assert(a.status=='refused'and a.code=='ASSET_UNAVAILABLE',a.status..' '..tostring(a.code))
assert(#W.runtime.projectiles==fired)
return 'ok'
''')

    def test_a_status_is_requested_only_for_an_allowlisted_status_and_a_live_target(self):
        self.lua(r'''
hd2.events.run_as('mods/t/burn',function()hd2.events.on('mission_started',function()end)end)
local function apply(target,what,opts)
    local action
    hd2.events.run_as('mods/t/burn',function()action=hd2.status.apply(target,what,opts)end)
    return action
end
local enemy={id=200}
assert(apply(enemy,'fire').code=='NOT_IN_MISSION')
mission({host=true})
W.add{entity=200,type=DEVASTATOR,unit=7200,health=500}
tick()
-- Only statuses a player weapon applies; raw ids, stims and ambiguous display names are refused.
assert(apply(enemy,5).code=='UNKNOWN_STATUS'and apply(enemy,'stim_heal').code=='UNKNOWN_STATUS')
assert(apply(enemy,'blind').code=='UNKNOWN_STATUS')
local ids={}
for _,item in ipairs(hd2.status.list())do ids[#ids+1]=item.id end
assert(table.concat(ids,',')=='fire,fire_panic,burning_heavy,stun_small,stun_medium,stun_large,gas,gas_2,gas_confusion,'
    ..'gas_confusion_2,flamer_slowed',table.concat(ids,','))
assert(apply(enemy,'fire',{strength=5}).code=='INVALID_OPTION','strength is the status\'s own')
assert(apply(enemy,'fire',{buildup=0}).code=='INVALID_AMOUNT'and apply(enemy,'fire',{buildup=5000}).code=='INVALID_AMOUNT')
assert(apply(nil,'fire').code=='INVALID_TARGET')
-- The request: the local avatar instigates; default buildup 100 (the game's own template).
local a=apply(enemy,'Fire')
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
local call=W.runtime.statuses[1]
assert(call.type==5 and call.target==200 and call.buildup==100 and call.instigator==100,
    ('%s %s %s %s'):format(call.type,call.target,call.buildup,call.instigator))
local stun=apply(enemy,'stun_medium',{buildup=250})
assert(stun.status=='requested'and W.runtime.statuses[2].type==38,tostring(stun.code))
assert(count('status fire requested on entity 200 (buildup 100) by mods/t/burn')==1)
-- Per-target limit: 4 at once.
local codes={}
for _=1,3 do codes[#codes+1]=apply(enemy,'gas').code or'ok'end
assert(table.concat(codes,',')=='ok,ok,RATE_LIMITED',table.concat(codes,','))
-- A gone target, a full queue and a changed request function are refused before any call.
local gone=apply({id=999+4194304*5},'fire')   -- a stale id: another generation of slot 999
assert(gone.code=='TARGET_GONE','gone '..tostring(gone.code)..' '..tostring(gone.status))
tick(40)
W.status_queue_count(4096)
local full=apply({id=100},'fire')
assert(full.code=='QUEUE_FULL','full '..tostring(full.code))
W.status_queue_count(0)
local S=require('hd2runtime/domains/event_natives').status
W.write(W.GAME+S.rva,string.char(0xCC))
local changed=apply({id=100},'fire')
assert(changed.code=='STATUS_UNAVAILABLE','changed '..tostring(changed.code))
mission({host=false})
local client=apply(enemy,'fire')
assert(client.code=='HOST_ONLY','client '..tostring(client.code))
assert(#W.runtime.statuses==4,#W.runtime.statuses)
return 'ok'
''')

    def test_the_equipped_weapon_and_its_events_follow_switches_death_and_respawn(self):
        self.lua(r'''
mission({host=true})
local me=hd2.local_player()
local none,why=me:equipped_weapon()
assert(none==nil and why=='nothing in hand',tostring(why))
W.hold(100,605,ERUPTOR,1)
local held=me:equipped_weapon()
assert(held.name=='R-36 Eruptor'and held.type==ERUPTOR and held.entity_id==605 and held.avatar_id==100)
assert(held.slot=='primary'and held.slot_proven==true and held.selection==1)
local seen={}
hd2.events.run_as('mods/t/weapons',function()
    hd2.events.on('weapon_changed',function(e)
        seen[#seen+1]='changed '..tostring(e.previous and e.previous.name)..' -> '..tostring(e.current and e.current.name)
    end)
    hd2.events.on('weapon_equipped',function(e)seen[#seen+1]='equipped '..tostring(e.weapon.name)end)
    hd2.events.on('weapon_unequipped',function(e)seen[#seen+1]='unequipped '..tostring(e.weapon.name)..' '..e.reason end)
end)
tick(2)
assert(#seen==0,'what is held when Runtime starts watching is the baseline')
-- A switch: selection and slot 0 change together.
W.hold(100,606,LIBERATOR,2)
tick(2)
assert(table.concat(seen,'|')=='unequipped R-36 Eruptor switched|equipped AR-23 Liberator|changed R-36 Eruptor -> '
    ..'AR-23 Liberator',table.concat(seen,'|'))
assert(me:equipped_weapon().slot=='secondary')
-- An item that is not catalogued (a stratagem ball): no name, an inferred slot.
seen={}
W.hold(100,934,'0123456789ABCDEF',5)
tick(2)
local ball=me:equipped_weapon()
assert(ball.name==nil and ball.slot=='held_item'and ball.slot_proven==false and ball.entity_id==934)
assert(seen[3]=='changed AR-23 Liberator -> nil'or seen[3]=='changed AR-23 Liberator -> nil',table.concat(seen,'|'))
-- Death: the game removes the wielder; nothing is held.
seen={}
W.drop_wielder(100)
tick(2)
assert(table.concat(seen,'|')=='unequipped nil emptied|changed nil -> nil',table.concat(seen,'|'))
assert(me:equipped_weapon()==nil)
-- Respawn: a new avatar gets a fresh instance and wields its first item.
seen={}
W.players({{peer=LOCAL,avatar=101}},LOCAL)
W.add{entity=101,type=W.AVATAR,unit=7101,health=125,owned=true}
W.hold(101,707,ERUPTOR,1)
tick(2)
assert(table.concat(seen,'|')=='equipped R-36 Eruptor|changed nil -> R-36 Eruptor',table.concat(seen,'|'))
-- A stale held entity (another generation of its slot) is nothing in hand; another player is refused.
W.hold(101,707+4194304*3,ERUPTOR,1)
assert(me:equipped_weapon()==nil)
local other=setmetatable({peer=OTHER,is_local=false},{__index=handles.Player})
local refused,reason=other:equipped_weapon()
assert(refused==nil and reason:find('only the local player',1,true),tostring(reason))
return 'ok'
''')

    def test_runtime_requested_explosions_are_reported_once_with_their_cause(self):
        self.lua(r"""
mission({host=true})
W.queue_requests(true)                -- a request lands in the queue, as in the game
local seen={}
hd2.events.run_as('mods/t/watch',function()hd2.events.on('explosion',function(e)seen[#seen+1]=e end)end)
hd2.events.run_as('mods/t/boom',function()
    hd2.events.on('entity_died',function()hd2.explosions.spawn('R-36 Eruptor',{position={x=5,y=6,z=7}})end)
end)
W.add{entity=500,type=MARAUDER,unit=9000,health=100};tick()
W.set(500,{life=2,health=0});tick()     -- the death is dispatched; the mod requests an explosion after the poll
assert(#W.runtime.explosions==1 and #seen==0)
tick()                                   -- the next poll reports the request, then finds it queued: not twice
assert(#seen==1,#seen)
local e=seen[1]
assert(e.observed=='request'and e.name=='R-36 Eruptor'and e.position.x==5 and e.local_player and e.owner_id==100)
assert(e.cause.source=='mod'and e.cause.mod=='mods/t/boom'and e.cause.kind=='explosion'and e.cause.depth==1)
assert(e.cause.parent.event=='entity_died'and e.cause.parent.cause.source=='native')
tick();W.explosion_update();tick()
assert(#seen==1,'the queued copy of a Runtime request is never reported')
-- Requested by Runtime itself, outside any mod callback (a custom stratagem's blast): cause runtime. A requester that
-- passes its action's cause is reported with it.
local world=world_module.open()
local lo,hi=world_module.local_peer(world)
assert(world_module.explode(world,{type=158,x=1,y=1,z=1,source=100,owner=100,peer_lo=lo,peer_hi=hi}))
local cause={source='mod',mod='mods/t/explicit',action='explosion#99',kind='explosion',depth=1}
assert(world_module.explode(world,{type=158,x=2,y=2,z=2,source=100,owner=100,peer_lo=lo,peer_hi=hi,cause=cause}))
tick()
assert(#seen==3 and seen[2].cause.source=='runtime'and seen[3].cause==cause,#seen)
-- A native request queued after them is reported from the queue.
W.request_explosion({type=158,position={x=9,y=9,z=9},source=100,owner=100,creditor=LOCAL})
tick();assert(#seen==4 and seen[4].observed=='queue'and seen[4].cause.source=='native')
return 'ok'
""")

    def test_an_explosion_waits_for_its_assets_and_fails_closed_when_they_cannot_load(self):
        self.lua(r'''
mission({host=true})
for package in pairs(require('hd2runtime/domains/package_residency').packages)do W.runtime.packages[package]='absent'end
local action
hd2.events.run_as('mods/t/assets',function()action=hd2.explosions.spawn('R-36 Eruptor',{position={x=1,y=2,z=3}})end)
assert(action.status=='waiting_for_assets',action.status)
tick(8)
-- The fixture has no package system to request through: the gate refuses, and nothing is requested.
assert(action.status=='refused'and action.code=='ASSET_UNAVAILABLE',action.status..' '..tostring(action.code))
assert(#W.runtime.explosions==0)
return 'ok'
''')

    def test_a_mod_caused_chain_is_cut_at_the_cause_depth(self):
        self.lua(r'''
local action
mission({host=true})
hd2.events.run_as('mods/t/chain',function()
    hd2.events.on('entity_died',function()action=hd2.explosions.spawn('R-36 Eruptor',{position={x=0,y=0,z=0}})end)
end)
events.queue('entity_died',{cause={source='mod',mod='mods/t/other',action='explosion#9',depth=events.MAX_CAUSE_DEPTH}})
tick()
assert(action and action.code=='CAUSE_DEPTH',tostring(action and action.code))
return 'ok'
''')


class ExampleModTests(unittest.TestCase):
    """The shipped example mods, loaded exactly as their built ZIPs run them, on the offline fixture world."""

    def example(self, project, body):
        program = PRELUDE + '\nlocal ADDON=' + lua(wrapped(project)) + '\n' + body
        self.assertEqual(run(program), b'ok')

    def test_heavy_devastator_delayed_explosion(self):
        self.example('HeavyDevastatorDelayedExplosionTest', r'''
local returned=assert(loadstring(ADDON,'@mods/hd2runtime_examples/heavy_devastator_delayed_explosion_test'))()
assert(returned==true)
local id='mods/hd2runtime_examples/heavy_devastator_delayed_explosion_test'
assert(count('['..id..'] loaded')==1)
mission({host=true})
assert(count('R-36 Eruptor explosion assets ready')==1,'assets warmed at mission start')
W.add{entity=611,type=DEVASTATOR,unit=9111,health=750};W.unit(9111,40,-12,2.5)
W.add{entity=612,type=MARAUDER,unit=9112,health=125};W.unit(9112,1,1,1)
tick()
W.set(612,{life=2,health=0});tick()
assert(count('automaton died: enemy/v1/automatons/conscript_tier_3 (Marauder), not a target')==1)
W.set(611,{health=50,creditor=LOCAL});tick()
W.replace_by_corpse(611,720);tick()
assert(count('Heavy Devastator died at (40.00, -12.00, 2.50) (enemy/v1/automatons/soldier_mg, observed=corpse, corpse=720)')==1)
assert(count('scheduled explosion in 3 s')==1)
W.remove_unit(9111)                                   -- the corpse is gone before the timer fires
tick(26)
assert(count('timer fired at saved position (40.00, -12.00, 2.50) (the entity is still valid: false)')==1)
assert(count('explosion requested: R-36 Eruptor at (40.00, -12.00, 2.50)')==1)
local call=W.runtime.explosions[1]
assert(#W.runtime.explosions==1 and call.x==40 and call.y==-12 and call.z==2.5 and call.type==158)
-- As a client the same logic logs the exact refusal instead.
W.state(3);tick();W.runtime.explosions={}
mission({host=false})
W.add{entity=613,type=DEVASTATOR,unit=9113,health=750};W.unit(9113,5,5,5);tick()
W.set(613,{life=2,health=0});tick();tick(26)
assert(count('explosion blocked: HOST_ONLY: ')==1 and #W.runtime.explosions==0)
return 'ok'
''')

    def test_kill_heal_logs_the_observation_and_heals(self):
        self.example('KillHealTest', r'''
assert(loadstring(ADDON,'@mods/hd2runtime_examples/kill_heal_test'))()
mission({host=true})
W.set(100,{health=80})
W.add{entity=621,type=MARAUDER,unit=0,health=125};tick()
W.set(621,{health=10,creditor=LOCAL});tick()
W.replace_by_corpse(621,730);tick()
assert(count('kill: enemy/v1/automatons/conscript_tier_3 (Marauder) observed=corpse corpse=730 killer=local player -> heal +25 requested')==1)
assert(#W.runtime.heals==1 and W.runtime.heals[1].entity==100)
tick()
assert(count('player healed +25 -> 105 / 125, cause mod mods/hd2runtime_examples/kill_heal_test')==1)
W.add{entity=622,type=MARAUDER,unit=0,health=125};tick()
W.set(622,{life=2,health=0,creditor=OTHER});tick()
assert(count('observed=dead_state corpse=nil killer=peer '..OTHER..' -> no heal (not credited to the local player)')==1)
return 'ok'
''')

    def test_vampiric_throwing_knives_heal_only_on_knife_damage(self):
        self.example('VampiricThrowingKnivesTest', r'''
assert(loadstring(ADDON,'@mods/hd2runtime_examples/vampiric_throwing_knives_test'))()
local K=require('hd2runtime/domains/event_natives').stats.keys
local KNIFE='F7B35A9C5AE340B6'
mission({host=true})
W.set(100,{health=80})
W.stat(10,K.dealt_damage,0,1,KNIFE);W.stat(10,K.dealt_damage,0,2,ERUPTOR);tick(2)   -- baseline
tick(3);assert(#W.runtime.heals==0,'a miss records nothing')
W.stat(10,K.dealt_damage,300,1,KNIFE);tick()
assert(count('knife damage 300 -> heal +25 requested')==1 and #W.runtime.heals==1 and W.runtime.heals[1].entity==100)
tick()
assert(count('player healed +25 -> 105 / 125, cause mod mods/hd2runtime_examples/vampiric_throwing_knives_test')==1)
W.stat(10,K.dealt_damage,905,2,ERUPTOR);tick()
assert(count('damage 905 by R-36 Eruptor -> no heal (not the knife)')==1 and #W.runtime.heals==1)
W.stat(10,K.dealt_damage,40);tick()
assert(count('damage 40 without a source -> no heal')==1 and #W.runtime.heals==1)
-- The knife and another weapon in the same check: one heal for the knife, none for the other weapon.
W.set(100,{health=80})
W.stat(10,K.dealt_damage,450,1,KNIFE);W.stat(10,K.dealt_damage,1005,2,ERUPTOR);tick()
assert(count('knife damage 150 -> heal +25 requested')==1 and #W.runtime.heals==2)
assert(count('damage 100 by R-36 Eruptor -> no heal (not the knife)')==1)
return 'ok'
''')

    def test_player_kill_credited_example_logs_each_source(self):
        self.example('PlayerKillCreditedExample', r'''
assert(loadstring(ADDON,'@mods/hd2runtime_examples/player_kill_credited_example'))()
local K=require('hd2runtime/domains/event_natives').stats.keys
mission()
W.stat(10,K.dealt_kills,0,1,ERUPTOR);tick(2)
W.stat(10,K.dealt_kills,1,1,ERUPTOR);W.stat(10,K.dealt_kills,3,2,'23A60681DD4383EC');W.stat(10,K.dealt_kills,1,3,HELLPOD)
tick()
assert(count('player kill credited: +5 (total 5)')==1)
assert(count('  Eagle Strafing Run +3')==1 and count('  R-36 Eruptor +1')==1)
assert(count('  unnamed source '..HELLPOD..' +1')==1)
return 'ok'
''')

    def test_kill_stack_counts_only_liberator_credits(self):
        self.example('KillStackDamageTest', r'''
local requested
hd2.ensure=function(request)requested=request;return{status='waiting'}end
assert(loadstring(ADDON,'@mods/hd2runtime_examples/kill_stack_damage_test'))()
assert(requested and requested.patch.id=='kill-stack-liberator-damage')
local value=requested.patch.value
local K=require('hd2runtime/domains/event_natives').stats.keys
mission()
assert(count('mission started: 0 stack(s), Liberator damage 90 (+0%)')==1)
W.stat(10,K.dealt_kills,0,1,LIBERATOR);tick(2)
W.stat(10,K.dealt_kills,4,2,ERUPTOR);tick()
assert(count('Liberator kill(s) credited')==0,'kills with another weapon add nothing')
W.stat(10,K.dealt_kills,2,1,LIBERATOR);tick()
assert(count('2 AR-23 Liberator kill(s) credited: 2 stack(s), Liberator damage 108 (+20%)')==1)
W.state(3);tick()
assert(count('mission ended: Liberator damage back to 90')==1)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
