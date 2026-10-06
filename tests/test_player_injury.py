"""hd2.actions.injure / player:injure: the game's own limb injury of the local player's avatar
(research/player-injury-path-F5FEE03DCFDB.json). Offline: the event world fixture plus the damage queue, the engine
unit and actor API tables and fake native calls that record what Runtime would pass."""
import json
import unittest

from support import ROOT, run

FIXTURE = (ROOT / 'tests/event_world_fixture.lua').read_text(encoding='utf-8')
RESEARCH = ROOT / 'research/player-injury-path-F5FEE03DCFDB.json'

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
local actions=require('hd2runtime/api/actions')
local scheduler=require('hd2runtime/runtime/scheduler')
local natives=require('hd2runtime/domains/event_natives')
local IJ=natives.injury
events.reset_for_tests();handles.reset_for_tests();actions.reset_for_tests()
world_module.set_runtime(W.runtime)
package.preload['mods/skyeshade/hd2runtime']=function()return require('hd2runtime/api/hd2')end
local hd2=require('mods/skyeshade/hd2runtime')
rawset(_G,'CowboyBingusModLoader',{api=1,version=16})
local function tick(n,dt)for _=1,(n or 1)do if update then update(dt or 0.125)end end end
-- Runs fn inside one game update (as a callback, timer or keybind does) and returns its results.
local function in_update(fn)
    local out
    local w={status='active'};function w.cancel()w.status='cancelled'end
    function w.tick()out={fn()};w.status='complete'end
    scheduler.attach(w);tick()
    return unpack(out)
end
local LOCAL,OTHER='1111222233334444','5555666677778888'
local function unhex(h)return(h:gsub('..',function(p)return string.char(tonumber(p,16))end))end
local function le64(s)local v=0;for i=8,1,-1 do v=v*256+s:byte(i)end;return v end

-- The game side of the injury path: QueueDamage's and the unit actor lookup's entry bytes, the engine unit and actor
-- API tables game.dll reads (global -> table -> slot), and the damage system (the status queue's global).
W.write(W.GAME+IJ.rva,unhex(IJ.prologue))
local U,AA=IJ.unitApi,IJ.actorApi
W.write(W.EXE+U.rva,unhex(U.prologue))
W.write(W.GAME+U.global,W.u64(W.EXE+U.table));W.write(W.EXE+U.table+U.slot,W.u64(W.EXE+U.rva))
W.write(W.GAME+AA.global,W.u64(W.EXE+AA.table))
W.write(W.EXE+AA.table+AA.validSlot,W.u64(W.EXE+AA.validRva));W.write(W.EXE+AA.table+AA.nameSlot,W.u64(W.EXE+AA.nameRva))
local SYSTEM=le64(W.read(W.GAME+IJ.system,8))
local function queue_count(n)W.write(SYSTEM+IJ.count,W.u32(n))end
queue_count(0)

-- The engine's unit actor lookup and QueueDamage: recorded, never executed. Each unit's actors by name.
local unit_actors={}
W.runtime.lookups,W.runtime.injuries={},{}
function W.runtime.native_unit_actor(entry,unit,name)
    assert(entry==W.EXE+U.rva,'the actor was looked up through the wrong function')
    W.runtime.lookups[#W.runtime.lookups+1]={unit=unit,name=name}
    return unit_actors[unit]and unit_actors[unit][name]or nil
end
function W.runtime.native_injure(entry,target,damage,network,creditor_lo,creditor_hi,actor)
    assert(entry==W.GAME+IJ.rva,'the injury was queued through the wrong function')
    W.runtime.injuries[#W.runtime.injuries+1]={target=target,damage=damage,network=network,
        creditor=string.format('%08X%08X',creditor_hi,creditor_lo),actor=actor}
    return true
end
local function give_actors(unit)
    unit_actors[unit]={}
    for index,limb in ipairs(IJ.limbs)do unit_actors[unit][limb.actor]=0xB0002000+index end
end
local function mission(opts)
    opts=opts or{}
    W.players({{peer=LOCAL,avatar=100},{peer=OTHER,avatar=101}},LOCAL)
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=opts.owned~=false,goid=100,creditor=opts.creditor}
    W.add{entity=101,type=W.AVATAR,unit=7101,health=125,owned=false,goid=101}
    W.unit(7100,0,0,0);W.unit(7101,5,0,0)
    give_actors(7100)
    W.state(4,{host=opts.host});tick()
end
local function injure(player,limb,damage,opts)
    return in_update(function()
        local action
        hd2.events.run_as('mods/t/injury',function()action=hd2.actions.injure(player,limb,damage,opts)end)
        return action
    end)
end
'''


class PlayerInjuryTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_the_research_names_six_limbs_on_the_avatar_zones_with_their_health(self):
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        limbs = {item['limb']: (item['zone'], item['zoneHealth']) for item in research['limbs']}
        self.assertEqual(limbs, {'head': ('head', 85), 'chest': ('body', 60), 'l_hand': ('arm_left', 35),
            'r_hand': ('arm_right', 35), 'l_knee': ('leg_left', 45), 'r_knee': ('leg_right', 45)})
        self.assertEqual(research['writes'], 0)
        self.assertFalse(any(research['pinnedBytesMismatchPerSnapshot'].values()))
        template = research['queueDamage']['gameTemplate']
        self.assertEqual((template['kind'], template['element'], template['damage'], template['a17']), (6, 0, 15, 9))
        self.assertEqual({m['modeAbility'] for m in research['fireMode7Abilities']}, {50})

    def test_every_limb_is_queued_at_its_own_actor_with_the_game_template(self):
        self.lua(r'''
mission({host=true,creditor=OTHER})
local me=hd2.local_player()
local names={}
for _,limb in ipairs(hd2.actions.limbs())do names[#names+1]=limb.name..'='..limb.zone..':'..limb.max_damage end
assert(table.concat(names,',')=='head=head:85,chest=body:60,l_hand=arm_left:35,r_hand=arm_right:35,'
    ..'l_knee=leg_left:45,r_knee=leg_right:45',table.concat(names,','))
for index,limb in ipairs(IJ.limbs)do
    local a=injure(me,limb.name,limb.maxDamage)
    assert(a.status=='requested',limb.name..' '..tostring(a.code)..' '..tostring(a.reason))
    local call=W.runtime.injuries[index]
    assert(call.target==100 and call.network==100 and call.damage==limb.maxDamage,limb.name)
    assert(call.actor==0xB0002000+index,'the handle the engine lookup returned for '..limb.name)
    assert(call.creditor==OTHER,'the avatar\'s current last-hit creditor is kept (the VG-70 template)')
    local lookup=W.runtime.lookups[index]
    assert(lookup.unit==7100 and lookup.name==limb.actor,'looked up on the avatar\'s own unit by actor name')
    local d=a:describe()
    assert(d.kind=='injure'and d.limb==limb.name and d.zone==limb.zone and d.damage==limb.maxDamage
        and d.owner=='mods/t/injury',limb.name)
    assert(a.zone_health==limb.maxDamage or a.zone_health==0,'zone health read before the call')
end
assert(count('injury r_hand (arm_right) 35 requested on the local avatar 100 by mods/t/injury')==1)
-- player:injure is the same action, owned by the calling mod.
local a=in_update(function()
    local result
    hd2.events.run_as('mods/t/method',function()result=me:injure('r_hand',5)end)
    return result
end)
assert(a.status=='requested'and a.owner=='mods/t/method'and W.runtime.injuries[7].damage==5,tostring(a.code))
assert(hd2.actions.status().injure.status=='available')
return 'ok'
''')

    def test_limb_damage_target_and_options_are_refused_before_any_game_call(self):
        self.lua(r'''
mission({host=true})
local me=hd2.local_player()
for _,limb in ipairs({'r_arm','R_HAND','arm_right','r_shoulder','',5,nil,{}})do
    assert(injure(me,limb,5).code=='UNKNOWN_LIMB',tostring(limb))
end
for _,damage in ipairs({0,-1,1.5,36,'5',math.huge,-math.huge,0/0,{}})do
    local a=injure(me,'r_hand',damage)
    assert(a.code=='INVALID_AMOUNT',tostring(damage)..' '..tostring(a.code))
end
assert(injure(me,'r_hand',nil).code=='INVALID_AMOUNT')
assert(injure(me,'r_knee',46).code=='INVALID_AMOUNT'and injure(me,'head',86).code=='INVALID_AMOUNT')
assert(injure(me,'head',85).status=='requested'and injure(me,'r_knee',45).status=='requested')
assert(injure(me,'r_hand',5,{buildup=1}).code=='INVALID_OPTION')
assert(injure(me,'r_hand',5,{owner=''}).code=='INVALID_OPTION')
assert(injure(nil,'r_hand',5).code=='INVALID_TARGET'and injure({is_local=true},'r_hand',5).code=='INVALID_TARGET')
assert(#W.runtime.injuries==2 and #W.runtime.lookups==2,#W.runtime.injuries)
return 'ok'
''')

    def test_a_remote_player_and_a_game_outside_a_mission_are_refused(self):
        self.lua(r'''
local me=hd2.local_player()
W.players({{peer=LOCAL,avatar=100}},LOCAL)
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true,goid=100}
give_actors(7100)
W.state(3);tick()
me=hd2.local_player()
assert(injure(me,'r_hand',5).code=='NOT_IN_MISSION')
mission({host=false})                         -- a client: no host needed for its own avatar
local other
for _,player in ipairs(hd2.players())do if not player:is_local_player()then other=player end end
assert(other and injure(other,'r_hand',5).code=='NOT_LOCAL_PLAYER')
local a=injure(hd2.local_player(),'r_hand',5)
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
W.state(3);tick()
assert(injure(hd2.local_player(),'r_hand',5).code=='NOT_IN_MISSION')
assert(#W.runtime.injuries==1)
return 'ok'
''')

    def test_downed_dead_and_unowned_avatars_are_refused(self):
        self.lua(r'''
mission({host=true})
local me=hd2.local_player()
W.set(100,{life=1});tick()
assert(injure(me,'r_hand',5).code=='AVATAR_DOWNED')
W.set(100,{life=2});tick()
assert(injure(me,'r_hand',5).code=='NO_LOCAL_AVATAR','a dead avatar is no usable avatar')
W.set(100,{life=0});tick()
assert(injure(me,'r_hand',5).status=='requested')
W.remove(100);W.remove(101)
mission({host=true,owned=false})
assert(injure(hd2.local_player(),'r_hand',5).code=='NO_LOCAL_AVATAR','not owned by this machine')
assert(#W.runtime.injuries==1)
return 'ok'
''')

    def test_a_changed_or_missing_native_path_refuses_the_injury(self):
        self.lua(r'''
mission({host=true})
local me=hd2.local_player()
-- Outside the game update.
local outside
hd2.events.run_as('mods/t/injury',function()outside=hd2.actions.injure(me,'r_hand',5)end)
assert(outside.code=='NOT_GAME_THREAD',tostring(outside.code))
-- The queue full this frame.
queue_count(IJ.capacity)
assert(injure(me,'r_hand',5).code=='QUEUE_FULL')
queue_count(0)
-- The unit has no such actor now.
unit_actors[7100][IJ.limbs[4].actor]=nil
assert(injure(me,'r_hand',5).code=='LIMB_UNAVAILABLE')
give_actors(7100)
-- The engine API slots must be the pinned functions.
W.write(W.EXE+U.table+U.slot,W.u64(W.EXE+U.rva+16))
assert(injure(me,'r_hand',5).code=='INJURY_UNAVAILABLE')
W.write(W.EXE+U.table+U.slot,W.u64(W.EXE+U.rva))
W.write(W.EXE+AA.table+AA.nameSlot,W.u64(0))
assert(injure(me,'r_hand',5).code=='INJURY_UNAVAILABLE')
W.write(W.EXE+AA.table+AA.nameSlot,W.u64(W.EXE+AA.nameRva))
-- Changed entry bytes: the lookup's, then QueueDamage's.
W.write(W.EXE+U.rva,string.char(0xCC))
assert(injure(me,'r_hand',5).code=='INJURY_UNAVAILABLE')
W.write(W.EXE+U.rva,unhex(U.prologue))
W.write(W.GAME+IJ.rva,string.char(0xCC))
local changed=injure(me,'r_hand',5)
assert(changed.code=='INJURY_UNAVAILABLE'and changed.reason:find('changed'),tostring(changed.reason))
W.write(W.GAME+IJ.rva,unhex(IJ.prologue))
assert(#W.runtime.injuries==0,'nothing was queued')
-- An adapter that cannot call game functions.
local saved=W.runtime.native_injure
W.runtime.native_injure=nil
assert(injure(me,'r_hand',5).code=='INJURY_UNAVAILABLE')
W.runtime.native_injure=saved
assert(injure(me,'r_hand',5).status=='requested')
assert(#W.runtime.injuries==1)
return 'ok'
''')

    def test_injuries_are_rate_limited_per_mod_and_cut_at_the_cause_depth(self):
        self.lua(r'''
hd2.events.run_as('mods/t/injury',function()hd2.events.on('mission_started',function()end)end)   -- the clock runs
mission({host=true})
local me=hd2.local_player()
-- A burst inside one update (time does not advance between the calls).
local codes=in_update(function()
    local out={}
    hd2.events.run_as('mods/t/injury',function()
        for _=1,actions.INJURE_BURST+1 do out[#out+1]=hd2.actions.injure(me,'r_hand',1).code or'ok'end
    end)
    return out
end)
assert(codes[actions.INJURE_BURST]=='ok'and codes[actions.INJURE_BURST+1]=='RATE_LIMITED',table.concat(codes,','))
tick(8)                                       -- one second refills INJURE_REFILL tokens
assert(injure(me,'r_hand',1).status=='requested','refilled')
local other
hd2.events.run_as('mods/t/other',function()end)
other=in_update(function()
    local result
    hd2.events.run_as('mods/t/other',function()result=hd2.actions.injure(me,'l_hand',1)end)
    return result
end)
assert(other.status=='requested','another mod has its own bucket')
local chained
hd2.events.run_as('mods/t/chain',function()
    hd2.events.on('entity_died',function()chained=hd2.actions.injure(me,'r_hand',1)end)
end)
events.queue('entity_died',{cause={source='mod',mod='mods/t/other',action='injure#9',depth=events.MAX_CAUSE_DEPTH}})
tick()
assert(chained and chained.code=='CAUSE_DEPTH',tostring(chained and chained.code))
return 'ok'
''')

    def test_the_generated_natives_carry_the_injury_pins(self):
        self.lua(r'''
local labels={}
for _,pin in ipairs(natives.pins)do labels[pin.label]=pin end
assert(labels['QueueDamage: queue 0 holds 4096 events'].hex=='3d00100000')
assert(labels['VG-70 template: kind 6 (Ability)'].rva==0x11AE1DA)
assert(labels['unit actor lookup: actor +0x18 is its name'].module=='exe')
assert(IJ.rva==0x129F910 and IJ.system==0x347CF38 and IJ.count==0x201120 and IJ.capacity==4096)
assert(IJ.kind==6 and IJ.element==0 and IJ.avatarType=='4D1C334D294DFA97')
assert(IJ.unitApi.rva==0x799DE0 and IJ.actorApi.nameRva==0x799CE0)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
