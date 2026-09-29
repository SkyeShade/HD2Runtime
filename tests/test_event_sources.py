"""Native event sources and handles on an offline fixture world laid out as domains/event_natives.lua describes."""
import unittest

from support import ROOT, run

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
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local sources=require('hd2runtime/runtime/event_sources')
local api=require('hd2runtime/api/events')
events.reset_for_tests();handles.reset_for_tests()
world_module.set_runtime(W.runtime)
local function tick(n)for _=1,(n or 1)do if update then update(0.125)end end end
local LOCAL,OTHER='1111222233334444','5555666677778888'
local MARAUDER,CHARGE='0002BA767DF856F3','03C74D93700C884D'
'''


class EventSourceTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_the_world_is_proven_and_a_changed_instruction_disables_every_source(self):
        self.lua(r'''
local world,why=world_module.open()
assert(world,why)
assert(world_module.game_state(world).name=='Ship')
-- Tamper one pinned byte: the proof fails and the source reports why (no reads of unproven structures).
local natives=require('hd2runtime/domains/event_natives')
local pin=natives.pins[5]
W.write((pin.module=='exe'and W.EXE or W.GAME)+pin.rva,string.char(0xCC))
world_module.set_runtime(W.runtime)
local ok,reason=world_module.open()
assert(not ok and reason:find('native event structure changed',1,true),tostring(reason))
local sub=api.events.on('entity_died',function()end,{owner='mods/t/x'})
assert(sub.state=='active')
assert(api.events.status().entity_died.status=='unavailable')
assert(count('event source health unavailable: native event structure changed')==1)
return 'ok'
''')

    def test_a_source_waits_for_the_game_modules_and_starts_once_they_load(self):
        self.lua(r'''
local real=W.runtime.module
W.runtime.module=function(name)return nil end        -- the game modules are not loaded yet
world_module.set_runtime(W.runtime)
local sub=api.events.on('entity_died',function()end,{owner='mods/t/wait'})
assert(api.events.status().entity_died.status=='retry',api.events.status().entity_died.status)
assert(count('event source health waiting: TARGET_UNAVAILABLE')==1)
tick(8)
assert(count('event source health waiting')==1,'logged once')
W.runtime.module=real
world_module.set_runtime(W.runtime)
tick(40)
assert(api.events.status().entity_died.status=='active',api.events.status().entity_died.status)
assert(count('event source health started')==1)
return 'ok'
''')

    def test_mission_boundaries_scope_state_and_invalidate_handles(self):
        self.lua(r'''
local mod=api.mod('mods/t/mission')
local started,ended={}, {}
mod:on('mission_started',function(e)started[#started+1]=e end)
mod:on('mission_ended',function(e)ended[#ended+1]=e;assert(mod.mission.kills==2,'still readable in mission_ended')end)
tick()
W.state(4,{host=true});tick()
assert(#started==1 and started[1].host==true and started[1].mode=='Mission',tostring(#started))
mod.mission.kills=2
local scoped=mod:on('entity_died',function()end,{scope='mission'})
W.players({{peer=LOCAL}},LOCAL)
W.add{entity=500,type=MARAUDER,unit=9000,health=100}
tick()
local handle=handles.entity({id=500,type=MARAUDER,descriptor_pointer=W.read(0,0)and nil})
assert(handle:is_valid(),'valid during the mission')
W.state(3);tick()
assert(#ended==1 and ended[1].game_state=='Ship')
assert(scoped.state=='expired')
assert(mod.mission.kills==nil)
assert(not handle:is_valid(),'a handle from the ended mission is invalid')
return 'ok'
''')

    def test_deaths_are_attributed_to_the_creditor(self):
        self.lua(r'''
local mod=api.mod('mods/t/kills')
local died,killed={}, {}
mod:on('entity_died',function(e)died[#died+1]=e end)
mod:on('entity_killed',function(e)killed[#killed+1]=e end)
W.players({{peer=LOCAL},{peer=OTHER}},LOCAL)
W.state(4);tick()
W.add{entity=501,type=MARAUDER,unit=9001,health=100}
W.add{entity=502,type=MARAUDER,unit=9002,health=100}
W.add{entity=503,type=MARAUDER,unit=9003,health=100}
W.add{entity=504,type=CHARGE,unit=9004,health=10}
W.unit(9001,1,2,3)
tick()
W.set(501,{life=2,health=0,creditor=LOCAL})
W.set(502,{life=2,health=0,creditor=OTHER})
W.set(503,{life=2,health=0})
W.set(504,{life=2,health=0,creditor=LOCAL})
tick()
assert(#died==4 and #killed==3,#died..' '..#killed)
local by={}
for _,e in ipairs(died)do by[e.entity.id]=e end
assert(by[501].local_killer and by[501].killer:is_local_player()and by[501].enemy and by[501].name=='Marauder')
assert(by[501].position.x==1 and by[501].position.z==3,'position snapshot at death')
assert(not by[502].local_killer and by[502].killer.peer=='5555666677778888')
assert(by[503].killer==nil and not by[503].local_killer,'environmental death has no killer')
assert(by[504].local_killer and by[504].enemy==false,'a non-enemy kill is reported as not an enemy')
-- A death is reported once.
tick();assert(#died==4)
return 'ok'
''')

    def test_kill_heal_flow_with_cause_attribution(self):
        self.lua(r'''
local mod=api.mod('mods/t/killheal')
W.players({{peer=LOCAL,avatar=600}},LOCAL)
W.state(4);W.add{entity=600,type=W.AVATAR,unit=9600,owned=true,health=50,max=125}
W.add{entity=610,type=MARAUDER,unit=9610,health=100}
W.add{entity=611,type=CHARGE,unit=9611,health=10}
W.add{entity=612,type=MARAUDER,unit=9612,health=100}
local healed={}
mod:on('entity_killed',function(e)
  if e.local_killer and e.enemy then
    local player=api.local_player()
    local amount,why=player:heal(25)
    assert(amount==25,tostring(why))
  end
end)
mod:on('player_healed',function(e)healed[#healed+1]=e end)
tick()
W.set(611,{life=2,health=0,creditor=LOCAL});tick();tick()   -- not an enemy: no heal
W.set(612,{life=2,health=0,creditor=OTHER});tick();tick()   -- another player's kill: no heal
assert(#W.runtime.heals==0)
W.set(610,{life=2,health=0,creditor=LOCAL});tick();tick()
assert(#W.runtime.heals==1 and math.abs(W.runtime.heals[1].fraction-25/125)<1e-6)
assert(W.get(600).health==75)
assert(#healed==1 and healed[1].amount==25 and healed[1].local_player)
assert(healed[1].cause.source=='mod'and healed[1].cause.mod=='mods/t/killheal'and healed[1].cause.depth==1)
assert(healed[1].cause.parent.event=='entity_killed')
-- Clamped to maximum health; refused when full, downed or not the local player's avatar.
W.set(600,{health=120});tick()
assert(api.local_player():heal(25)==5)
tick();assert(W.get(600).health==125)
assert(api.local_player():heal(25)==0)
W.set(600,{life=1});tick()
local none,why=api.local_player():heal(25)
assert(none==nil and why:find('downed or dead',1,true),tostring(why))
return 'ok'
''')

    def test_handles_fail_safely_after_destruction_and_reuse(self):
        self.lua(r'''
W.state(4);tick()
W.add{entity=700,type=MARAUDER,unit=9700,health=80}
W.unit(9700,5,6,7)
local state=world_module.entity_state(world_module.open(),700)
local handle=handles.entity({id=700,type=MARAUDER,descriptor_pointer=state.descriptor.pointer})
assert(handle:is_valid()and handle:is_alive()and handle:health()==80 and handle:position().y==6)
assert(handle:is_enemy()and handle.name=='Marauder')
W.remove_unit(9700)
assert(handle:position()==nil,'a destroyed unit has no position')
W.remove(700)
assert(not handle:is_valid()and handle:health()==nil and not handle:is_alive())
assert(handle:is_enemy(),'static facts stay readable')
-- The same id reused by another object is not the old handle.
W.add{entity=700,type=CHARGE,unit=9701,health=10}
assert(not handle:is_valid())
local d=handle:describe()
assert(d.valid==false and d.reason:find('another object',1,true),tostring(d.reason))
return 'ok'
''')

    def test_player_death_keeps_the_last_position(self):
        self.lua(r'''
local mod=api.mod('mods/t/death')
local deaths,spawns={}, {}
mod:on('player_died',function(e)deaths[#deaths+1]=e end)
mod:on('player_spawned',function(e)spawns[#spawns+1]=e end)
W.state(4);W.players({{peer=LOCAL}},LOCAL);tick()
W.add{entity=800,type=W.AVATAR,unit=9800,owned=true,health=125,max=125}
W.unit(9800,10,20,30)
W.players({{peer=LOCAL,avatar=800}},LOCAL);tick()
assert(#spawns==1 and spawns[1].local_player and spawns[1].position.x==10)
W.unit(9800,11,21,31);tick()
-- Death and unit removal in the same tick: the last position read alive is kept.
W.set(800,{life=2,health=0});W.remove_unit(9800);tick()
assert(#deaths==1 and deaths[1].local_player and deaths[1].position.x==11,tostring(deaths[1]and deaths[1].position))
assert(deaths[1].player:is_local_player())
tick();assert(#deaths==1,'reported once')
return 'ok'
''')

    def test_player_fired_counts_new_shots_every_tenth_of_a_second(self):
        self.lua(r'''
local mod=api.mod('mods/t/fired')
local fired={}
mod:on('player_fired',function(e)fired[#fired+1]=e end)
W.players({{peer=LOCAL}},LOCAL)   -- the player list descriptor makes the local player entity 10
W.stats(10,0);W.state(4);tick(2)
W.stats(10,3);tick(1)
assert(#fired==1 and fired[1].shots==3 and fired[1].total==3 and fired[1].local_player,tostring(#fired))
tick(2);assert(#fired==1,'no new shots, no event')
W.stats(10,10);tick(1)
assert(#fired==2 and fired[2].shots==7)
W.stats(10,2);tick(2)                 -- the table was reset: re-baseline, no event
W.stats(10,4);tick(1)
assert(#fired==3 and fired[3].shots==2)
return 'ok'
''')

    def test_damage_is_reported_per_tick_with_its_creditor(self):
        self.lua(r'''
local mod=api.mod('mods/t/damage')
local hits={}
mod:on('entity_damaged',function(e)hits[#hits+1]=e end)
W.state(4);W.players({{peer=LOCAL}},LOCAL);tick()
W.add{entity=900,type=MARAUDER,unit=9900,health=100};tick()
W.set(900,{health=70,creditor=LOCAL});tick()
W.set(900,{health=65});tick()
assert(#hits==2 and hits[1].damage==30 and hits[1].health==70 and hits[1].local_attacker)
assert(hits[2].damage==5)
return 'ok'
''')

    def test_the_in_game_ffi_read_path_reports_the_same_events(self):
        # read_into fills FFI buffers exactly as the live adapter does (ReadProcessMemory into a reusable buffer).
        self.lua(r'''
W.mirror()
world_module.set_runtime(W.runtime)
local mod=api.mod('mods/t/ffi')
local died,hits={}, {}
mod:on('entity_died',function(e)died[#died+1]=e end)
mod:on('entity_damaged',function(e)hits[#hits+1]=e end)
W.players({{peer=LOCAL}},LOCAL);W.state(4);tick()
W.add{entity=1501,type=MARAUDER,unit=0,health=100};tick()
W.set(1501,{health=60,creditor=LOCAL});tick()
W.set(1501,{life=2,health=0});tick()
assert(sources.health.record_block.data~=nil,'the FFI buffer path was used')
assert(#hits==1 and hits[1].damage==40 and hits[1].local_attacker,tostring(#hits))
assert(#died==1 and died[1].local_killer and died[1].enemy,tostring(#died))
return 'ok'
''')

    def test_a_poll_costs_the_same_number_of_reads_for_many_entities(self):
        self.lua(r'''
local mod=api.mod('mods/t/perf')
mod:on('entity_died',function()end)
W.state(4);tick()
for i=1,40 do W.add{entity=1000+i,type=MARAUDER,unit=0,health=100}end
tick()   -- first sight: one descriptor read per new entity
local view=sources.health.world.view
local before=view.reads;tick();local steady=view.reads-before
for i=41,60 do W.add{entity=1000+i,type=MARAUDER,unit=0,health=100}end
tick()
before=view.reads;tick()
assert(view.reads-before==steady,'reads per tick do not grow with entities: '..steady..' vs '..(view.reads-before))
assert(steady<=16,'bulk reads only: '..steady)
return 'ok'
''')



class EventWorldSnapshotReportTests(unittest.TestCase):
    def test_the_snapshot_validation_is_current_and_passed(self):
        import json
        report = json.loads((ROOT / 'validation/event-world-snapshot.json').read_text(encoding='utf-8'))
        natives = (ROOT / 'domains/event_natives.lua').read_text(encoding='utf-8')
        self.assertTrue(report['passed'])
        self.assertEqual(report['writes'], 0)
        self.assertEqual(len(report['snapshots']), 3)
        for name, item in report['snapshots'].items():
            self.assertEqual(item['pins'], natives.count('["label"]'), name)   # validated against today's table
            self.assertTrue(item['tamperRefused'], name)
            self.assertEqual(item['localAvatar']['health'], 125, name)

if __name__ == '__main__':
    unittest.main()
