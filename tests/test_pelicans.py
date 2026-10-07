"""The transport Pelican (runtime/pelicans.lua; research/docs/pelican-cas-F5FEE03DCFDB.md): the read-only readers of the
Transport, Behavior and transform components, the per-update watch (seen, cargo, stages, release, departure, gone),
and the per-instance hold: one guarded 8-byte write of a released Pelican's release time (P+0x178), so it departs the
asked seconds after its release; every refusal writes nothing. Offline: the payload world with the three components
laid out as the research found them."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

RESEARCH = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

PELICANS = r"""
local pelicans=require('hd2runtime/runtime/pelicans')
local PE=require('hd2runtime/domains/pelican')
pelicans.reset_for_tests()
for _,pin in ipairs(PE.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local TC,BC,XC,F=PE.components.transport,PE.components.behavior,PE.components.bearer,PE.flight
local P=BC.context
local function f32(v)return b.encode(v,'f32')end
local EMPTY=4294967295
-- An entity map of 64 slots, multiplier 1 (slot = entity % 64).
local function map(component,layout)
    local keys=W.alloc(64*8)
    for k=0,63 do W.write(keys+k*8,W.u32(EMPTY)..W.u32(0))end
    W.write(component+layout.keys,W.u64(keys))
    W.write(component+layout.capacity,W.u32(64));W.write(component+layout.empty,W.u32(EMPTY))
    W.write(component+layout.multiplier,W.u32(1))
    return function(entity,index)
        local slot=entity%64
        while b.u32(W.read(keys+slot*8,4),0)~=EMPTY and b.u32(W.read(keys+slot*8,4),0)~=entity do slot=(slot+1)%64 end
        W.write(keys+slot*8,W.u32(entity)..W.u32(index))
    end
end
local TCOMP,BCOMP,XCOMP=W.alloc(0x100),W.alloc(0x100),W.alloc(0x100)
W.write(W.GAME+TC.global,W.u64(TCOMP));W.write(W.GAME+BC.global,W.u64(BCOMP));W.write(W.GAME+XC.global,W.u64(XCOMP))
local THANDLES,TELEMENTS=W.alloc(0x1000),W.alloc(0x1000)
W.write(TCOMP+TC.handles,W.u64(THANDLES));W.write(TCOMP+TC.elements,W.u64(TELEMENTS))
local BHANDLES,BRECORDS=W.alloc(0x1000),W.alloc(0x2000)     -- page-sized: the target page lies inside its allocation
W.write(BCOMP+BC.handles,W.u64(BHANDLES));W.write(BCOMP+BC.records,W.u64(BRECORDS))
local XRECORDS=W.alloc(0x2000);W.write(XCOMP+XC.records,W.u64(XRECORDS))
local bkey,xkey=map(BCOMP,BC),map(XCOMP,XC)
local PELICAN=b.unhex(PE.entity):reverse()
local FRV=PE.vehicles['M-102 Gunner FRV'].vehicle
local BEHAVIOUR=667
local function tcount(n)W.write(TCOMP+TC.count,W.u32(n))end
local function record(i)return BRECORDS+i*BC.stride end
-- A transport (i = its index everywhere): resource (default the Pelican), entity, cargo (hex), spawned cargo, timer.
local function transport(i,entity,o)
    o=o or{}
    local handle=W.alloc(0x20)
    W.write(handle,(o.resource or PELICAN)..W.u32(entity)..W.u32(0)..W.u32(o.network or 0x7fff))
    W.write(THANDLES+i*8,W.u64(handle))
    local cargo=o.cargo and b.unhex(o.cargo):reverse()or string.rep('\0',8)
    W.write(TELEMENTS+i*TC.stride,cargo..W.u32(o.spawned or 0)..f32(o.timer or 0)..string.rep('\0',0x18)
        ..W.u32(o.associated or 0)..string.rep('\0',0x14))
    bkey(entity,i);xkey(entity,i)
    W.write(BHANDLES+i*8,W.u64(W.alloc(0x18)))
    W.write(record(i),W.u32(o.behaviour or BEHAVIOUR)..string.rep('\0',BC.stride-4))
end
local function stage(i,s,flags)
    W.write(record(i)+P+F.stage,W.u32(s))
    if flags~=nil then W.write(record(i)+P+F.flags,W.u32(flags))end
end
local function stamp(i,member,us)W.write(record(i)+P+F[member],W.u64(us))end
local function release_us(i)local raw=W.read(record(i)+P+F.releaseTime,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
local function target(i,x,y,z)W.write(record(i)+P+F.target,f32(x)..f32(y)..f32(z))end
local function position(i,x,y,z)W.write(XRECORDS+i*XC.stride+XC.position,f32(x)..f32(y)..f32(z))end
local function spawned(i,entity)W.write(TELEMENTS+i*TC.stride+TC.spawnedCargo,W.u32(entity))end
local function kinds(events)local out={};for k,e in ipairs(events)do out[k]=e.kind end;return table.concat(out,',')end
local function last(events,kind)for k=#events,1,-1 do if events[k].kind==kind then return events[k]end end end
local function near(a,c)return math.abs(a-c)<1e-3 end
-- The clock in microseconds (the game's): T0 = 200 s.
local T0=200000000
-- The spawn (PE.spawn): the world's entity settings table with the Pelican registered (cargo timer 0), and the
-- game's spawn request simulated: it records the call and creates a transport Pelican at the next index, stage 1, at
-- the pose's position (spawn_mode 'cargo' makes it carry a vehicle, as a vehicle row's Pelican would).
-- The spawn (SPAWN, one table: the harnesses together stay under Lua's 200 locals): the game's spawn request simulated
-- (it records the call and creates a transport Pelican at the next index, stage 1, at the pose's position, its
-- drop-position record holding the context's anchor; SPAWN.mode 'cargo' makes it carry a vehicle, 'no_anchor' leaves
-- the anchor unset), the world's entity settings table with the Pelican registered, the drop-position component.
local SPAWN={calls={},mode=nil,next=9500,SP=PE.spawn,AN=PE.anchor}
do
    local SP,AN=SPAWN.SP,SPAWN.AN
    W.write(W.GAME+SP.rva,b.unhex(SP.prologue))
    SPAWN.world=b.pointer(W.read(W.GAME+SP.world,8),0)
    local tab=W.alloc(0x1000)
    W.write(SPAWN.world+SP.settingsTable,W.u64(tab))
    local lo,hi=b.u32(PELICAN,0),b.u32(PELICAN,4)
    local slot=((hi%SP.settingsSlots)*(4294967296%SP.settingsSlots)+lo%SP.settingsSlots)%SP.settingsSlots
    function SPAWN.register(on)
        W.write(tab+slot*16,on and(PELICAN..W.u32(3)..W.u32(0))or string.rep('\0',16))
        W.write(tab+SP.settingsBase+3*SP.settingsStride,f32(0)..f32(2))
    end
    SPAWN.register(true)
    local acomp=W.alloc(0x100);W.write(W.GAME+AN.global,W.u64(acomp))
    local arecords=W.alloc(0x1000);W.write(acomp+AN.records,W.u64(arecords))
    local akey=map(acomp,{keys=AN.mapKeys,capacity=AN.mapCapacity,empty=AN.mapEmpty,multiplier=AN.mapMultiplier})
    local function anchor_record(i,x,y,z)W.write(arecords+i*AN.stride+AN.position,f32(x)..f32(y)..f32(z))end
    -- The flight component (PE.flightTarget), page-sized records: the game's move-to writes its target.
    local FT=PE.flightTarget
    local fcomp=W.alloc(0x100);W.write(W.GAME+FT.global,W.u64(fcomp))
    local frecords=W.alloc(0x2000);W.write(fcomp+FT.records,W.u64(frecords))
    local fkey=map(fcomp,FT)
    function SPAWN.flight_target(i)
        local raw=W.read(frecords+i*FT.stride+FT.target,12)
        return {x=b.value(raw,0,'f32'),y=b.value(raw,4,'f32'),z=b.value(raw,8,'f32')}
    end
    -- The game's move-to (0x4D1150): P+0x1BC and the flight record's target together.
    function SPAWN.push(i,x,y,z)
        target(i,x,y,z)
        W.write(frecords+i*FT.stride+FT.target,f32(x)..f32(y)..f32(z))
    end
    W.runtime.native_spawn_pelican=function(entry,x,y,z,fx,fy,ax,ay,az)
        SPAWN.calls[#SPAWN.calls+1]={entry=entry,x=x,y=y,z=z,fx=fx,fy=fy,ax=ax,ay=ay,az=az}
        local i=b.u32(W.read(TCOMP+TC.count,4),0)
        SPAWN.next=SPAWN.next+1
        transport(i,SPAWN.next,{cargo=SPAWN.mode=='cargo'and FRV or nil,spawned=SPAWN.mode=='cargo'and 9999 or nil,
            network=700+i})
        akey(SPAWN.next,i);fkey(SPAWN.next,i)
        if SPAWN.mode=='no_anchor'then anchor_record(i,0,0,0)else anchor_record(i,ax,ay,az)end
        stage(i,1,0);position(i,x,y,z);tcount(i+1)
        SPAWN.push(i,ax,ay,az+6)
        return SPAWN.next
    end
end
local spawn_calls,SP,CWORLD,register=SPAWN.calls,SPAWN.SP,SPAWN.world,SPAWN.register
-- The turret weapon (research "turretWeapon"): one fixture entity as a magazine projectile weapon (index 0 everywhere).
-- spec = {flags, interval, rpm, rounds, pattern, chambered, length, copy = {projectileType, rpm} or nil, windUp}.
-- Returns set_magazine(rounds, chambered).
local function turret_weapon(entity,spec)
    local TW=PE.turretWeapon
    local function component(c)
        local comp=W.alloc(0x200);W.write(W.GAME+c.global,W.u64(comp))
        return comp,map(comp,{keys=c.map,capacity=c.map+8,empty=c.map+0xC,multiplier=c.map+0x10})
    end
    local PW,MG,WP=TW.projectileWeapon,TW.magazine,TW.weapon
    local pw,pkey=component(PW);pkey(entity,0)
    local inst,rof,cur=W.alloc(0x200),W.alloc(0x100),W.alloc(0x100)
    W.write(pw+PW.instances,W.u64(inst));W.write(pw+PW.rof,W.u64(rof));W.write(pw+PW.current,W.u64(cur))
    W.write(inst+PW.interval,f32(spec.interval))
    W.write(rof+PW.rofSlots,f32(0)..f32(spec.rpm)..f32(0)..W.u32(1))
    W.write(cur+PW.currentRpm,f32(spec.rpm))
    local ckey=map(pw,{keys=PW.copies,capacity=PW.copies+8,empty=PW.copies+0xC,multiplier=PW.copies+0x10})
    if spec.copy then
        local copies=W.alloc(0x400);W.write(pw+PW.copyRecords,W.u64(copies));ckey(entity,0)
        W.write(copies,W.u32(spec.copy.projectileType)..f32(0)..f32(spec.copy.rpm)..f32(0))
    end
    local wp,wkey=component(WP);wkey(entity,0)
    local wrecs=W.alloc(0x100);W.write(wp+WP.records,W.u64(wrecs));W.write(wrecs+WP.flags,W.u32(spec.flags))
    local mg,mkey=component(MG);mkey(entity,0)
    map(mg,{keys=MG.copies,capacity=MG.copies+8,empty=MG.copies+0xC,multiplier=MG.copies+0x10})
    local mrecs=W.alloc(0x100);W.write(mg+MG.records,W.u64(mrecs))
    local function set_magazine(rounds,chambered)
        W.write(mrecs,W.u32(rounds)..W.u32(spec.pattern and 1 or 0)..W.u32(chambered)..W.u32(spec.length or 0))
    end
    set_magazine(spec.rounds,spec.chambered)
    component(TW.heat)
    local _,ukey=component(TW.windUp)
    if spec.windUp then ukey(entity,0)end
    return set_magazine
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + PELICANS + body)


class PelicanResearchTests(unittest.TestCase):
    def test_the_domain_is_current_and_pins_the_hold(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_pelican
        self.assertEqual(generate_pelican.generate(check=True), [])
        pinned = {p['rva'] for rows in RESEARCH['pins'].values() for p in rows}
        # The release time, its departure check, the hover start, the removal, the cargo timer and the pass order.
        self.assertTrue({0x45B33C, 0x45B134, 0x45B13B, 0x45C185, 0x45CBF6, 0x6D9863, 0x571305, 0x57243D} <= pinned)
        self.assertEqual(RESEARCH['pelican']['transportSettings']['cargoTimer'], 0.0)
        self.assertFalse(RESEARCH['cargo']['window'])
        self.assertEqual(RESEARCH['flight']['releaseTime'], 0x178)
        self.assertEqual(len(RESEARCH['vehicles']), 9)

    def test_the_turret_weapon_research(self):
        tw = RESEARCH['turretWeapon']
        # The fire path's projectile: flags, the chambered type re-derived after every shot, the resolved record.
        pinned = {p['rva'] for p in RESEARCH['pins']['turretWeapon']}
        self.assertTrue({0x74575D, 0x745805, 0x745A4F, 0x6149EC, 0x74480B, 0x5151B9, 0x5151CC, 0x61B0B7, 0x5A7FEF,
            0x611C69, 0x77E8E6} <= pinned)
        self.assertEqual(tw['observed']['chinTurret'], {'projectileType': 120, 'rpmSlots': [0.0, 300.0, 0.0],
            'magazinePattern': False, 'pattern': [], 'capacity': 500})
        self.assertEqual(tw['observed']['gatlingSentry'], {'projectileType': 148, 'rpmSlots': [0.0, 1600.0, 0.0],
            'magazinePattern': True, 'pattern': [148, 148, 148, 242, 148], 'capacity': 500})
        # No per-instance copies in any mission snapshot; every shot interval is 60 / its RPM.
        for snapshot in tw['snapshots'].values():
            self.assertEqual((snapshot['projectileWeaponCopies'], snapshot['copyCount'], snapshot['magazineCopies']),
                (0, 0, 0))
            self.assertTrue(snapshot['intervalIs60OverRpm'])
        self.assertEqual((tw['weapon']['heat'], tw['weapon']['magazine'], tw['projectileWeapon']['interval']),
            (0x200, 0x80, 0xC))

    def test_the_turret_rate_and_copy_routine_research(self):
        # Research only: the rate is the replicated current RPM, the interval follows it; the copy routine's profile.
        rate = {p['rva'] for p in RESEARCH['pins']['turretRate']}
        self.assertTrue({0x616E93, 0x616EC0, 0x612CFD, 0x611941, 0x61195C, 0x617599, 0x61784D} <= rate)
        self.assertTrue(RESEARCH['turretRate']['snapshotsCachedIsCurrent'])
        for snapshot in RESEARCH['turretWeapon']['snapshots'].values():
            self.assertTrue(snapshot['cachedIsCurrentRpm'])
            self.assertGreaterEqual(snapshot['copyCapacity'], 128)
        copy = RESEARCH['copyRoutine']
        self.assertTrue({0x515554, 0x51555A, 0x61B0F9, 0x61950F, 0x173B71D} <= {p['rva'] for p in RESEARCH['pins']['copyRoutine']})
        self.assertFalse(copy['capacity']['checked'])
        self.assertFalse(copy['replicationCall'])
        # Research-only groups stay out of the runtime domain.
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_pelican
        self.assertNotIn('turretRate', generate_pelican.GROUPS)
        self.assertNotIn('copyRoutine', generate_pelican.GROUPS)


class PelicanTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_readers_find_only_transport_pelicans(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
transport(0,9001,{cargo=FRV,spawned=9100,network=77});stage(0,3,0);target(0,10,20,30);position(0,11,21,131)
transport(1,9002,{resource=b.unhex('1122334455667788')})                 -- another transport: not a Pelican
tcount(2)
local world=world_module.open()
local list=assert(pelicans.list(world))
local n=0;for _ in pairs(list)do n=n+1 end
assert(n==1)
local p=list[9001]
assert(p.network==77 and p.cargo==FRV and pelicans.cargo_name(p.cargo)=='M-102 Gunner FRV' and p.cargo_spawned==9100)
assert(p.behaviour==667 and p.stage==3 and not p.released and near(p.target.z,30) and near(p.position.z,131))
assert(pelicans.clock(world)==T0)
return 'ok'
''')

    def test_the_watch_reports_the_flight_and_holds_once_released(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
local events={}
local w=assert(pelicans.watch({hold=60,label='test'},function(e)events[#events+1]=e end))
tick()
-- A vehicle Pelican appears with its cargo already spawned (the research: no window).
transport(0,9001,{cargo=FRV,spawned=9100});stage(0,1,0);tcount(1);position(0,0,0,0)
tick()
assert(kinds(events)=='seen',kinds(events))
assert(events[1].cargo.resource==FRV and events[1].cargo.spawned==9100)
-- Approach, then the hover (its start stamped), then the release at T0 + 20 s.
BOMB.set_clock(T0+10000000);stage(0,3,0);target(0,5,5,50);tick()
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);tick()
local writes=#W.runtime.writes
BOMB.set_clock(T0+20000000);stage(0,6,1);stamp(0,'releaseTime',T0+20000000);tick()
assert(kinds(events)=='seen,stage,stage,released,held',kinds(events))
local r=last(events,'released')
assert(near(r.hover,5)and near(r.seconds,20)and r.stage==6)
local held=last(events,'held').result
assert(held.verified and held.writes==1 and held.seconds==60)
-- One 8-byte write, the release time moved: it departs 60 s after its release (0.6 s is the native wait).
assert(#W.runtime.writes==writes+1 and W.runtime.writes[#W.runtime.writes].address==record(0)+P+F.releaseTime)
assert(release_us(0)==T0+20000000+60000000-600000)
assert(held.native==T0+20600000 and held.departure==T0+80000000)
assert(count('pelican HOLD APPLIED: Pelican 9001 (stage 6): departs 60.0 s after its release instead of 0.6 s '
    ..'(60.0 s from now); 1 write; verified true')==1,table.concat(logged,' | '))
-- Never held twice; the game departs (stage 8) and removes it.
BOMB.set_clock(T0+80000000);stage(0,8,1);tick()
assert(last(events,'departing').stage==8 and near(last(events,'departing').after_release,60))
BOMB.set_clock(T0+95000000);tcount(0);tick()
local gone=last(events,'gone')
assert(gone.entity==9001 and near(gone.seconds,95)and near(gone.after_release,75)and gone.held)
assert(#W.runtime.writes==writes+1)
return 'ok'
''')

    def test_a_cargo_that_appears_later_reports_its_window(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
local events={}
assert(pelicans.watch({},function(e)events[#events+1]=e end))
transport(0,9001,{cargo=FRV});stage(0,1,0);tcount(1);tick()
assert(events[1].cargo.spawned==nil)
tick();BOMB.set_clock(T0+50000);spawned(0,9100);tick()
local c=last(events,'cargo')
assert(c.spawned==9100 and c.updates==2 and near(c.seconds,0.05))
-- Observe only: nothing is written when released.
local writes=#W.runtime.writes
stage(0,6,1);stamp(0,'releaseTime',T0+50000);tick()
assert(last(events,'released')and not last(events,'held')and #W.runtime.writes==writes)
return 'ok'
''')

    def test_every_hold_refusal_writes_nothing(self):
        self.check(r'''
pworld()
local function refused(code,prepare,seconds,expect_behaviour)
    BOMB.set_clock(T0+1000000)
    transport(0,9001,{cargo=FRV,spawned=9100});stage(0,6,1);stamp(0,'hoverStart',T0-5000000)
    stamp(0,'releaseTime',T0+800000);tcount(1)
    local undo=prepare and prepare()
    local before=W.read(record(0),BC.stride)
    local writes=#W.runtime.writes
    local p=pelicans.read(world_module.open(),9001)
    local raw=p and p.release_raw or W.read(record(0)+P+F.releaseTime,8)
    local r,got,why=pelicans.hold(world_module.open(),9001,{behaviour=expect_behaviour or 667,release=raw},seconds or 60)
    assert(not r and got==code,code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#W.runtime.writes==writes and W.read(record(0),BC.stride)==before,code..': written')
    if undo then undo()end
end
refused('NOT_RELEASED',function()stage(0,6,0)end)                                   -- hovering, not released
refused('NOT_RELEASED',function()stage(0,3,0)end)
refused('DEPARTING',function()BOMB.set_clock(T0+1500000)end)                         -- 0.7 s after the release
refused('HOLD_INVALID',nil,0)
refused('HOLD_INVALID',nil,121)
refused('HOLD_INVALID',nil,0.5)                                                     -- shorter than the native 0.6 s
refused('UNEXPECTED_BEHAVIOUR',nil,nil,668)
refused('RELEASE_UNEXPECTED',function()stamp(0,'releaseTime',T0+2000000)end)        -- in the future
refused('GONE',function()tcount(0)end)
refused('NOT_HOST',function()W.state(4,{host=false})return function()W.state(4)end end)
refused('NOT_IN_MISSION',function()W.state(3)return function()W.state(4)end end)
refused('UNSUPPORTED_BUILD',function()
    pelicans.reset_for_tests()
    local pin=PE.pins[1];W.write(W.GAME+pin.rva,string.char(0xCC))
    return function()W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end)
-- The observed bytes are compared: a release time read earlier no longer matches.
BOMB.set_clock(T0+1000000);transport(0,9001,{cargo=FRV,spawned=9100});stage(0,6,1);stamp(0,'releaseTime',T0+800000)
local stale=W.read(record(0)+P+F.releaseTime,8)
stamp(0,'releaseTime',T0+900000)
local r,code=pelicans.hold(world_module.open(),9001,{behaviour=667,release=stale},60)
assert(not r and code=='RELEASE_UNEXPECTED')
return 'ok'
''')

    def test_stage_seven_uses_its_three_second_wait(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0+1000000)
transport(0,9001,{});stage(0,7,0);stamp(0,'releaseTime',T0);tcount(1)
local p=pelicans.read(world_module.open(),9001)
local r=assert(pelicans.hold(world_module.open(),9001,{behaviour=667,release=p.release_raw},30))
assert(r.verified and r.native==T0+3000000 and r.departure==T0+30000000)
assert(release_us(0)==T0+30000000-3000000)
return 'ok'
''')

    def test_a_second_watch_replaces_the_first_loudly(self):
        self.check(r'''
pworld()
local first=assert(pelicans.watch({label='probe'}))
local second=assert(pelicans.watch({label='cas'}))
assert(first.status=='cancelled'and second.status=='active')
assert(count('pelican WATCH REPLACED: "probe" stopped; "cas" now runs (one Pelican watch at a time)')==1)
assert(not pelicans.watch({hold=0}))
return 'ok'
''')



class PelicanSpawnTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_a_queued_spawn_creates_an_empty_pelican_and_holds_it_after_its_release(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
local events={}
local request=pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican',hold=60},
    function(e)events[#events+1]=e end)
assert(#spawn_calls==0)                                             -- made in the manager's own update, not here
tick()
assert(#spawn_calls==1 and spawn_calls[1].entry==W.GAME+SP.rva and spawn_calls[1].x==10 and spawn_calls[1].fy==1)
local s=last(events,'spawned')
assert(s and s.result.verified and s.result.entity==9501 and s.result.verify.empty and s.result.verify.unassociated)
assert(count('PELICAN SPAWN REQUESTED (mods/test/pelican): anchor (60.0, 70.0, 2.0) (where it hovers), spawn point '
    ..'(10.0, 20.0, 5.0), facing (0.00, 1.00); context: the game\'s default (2208 zero bytes: no cargo, no associated '
    ..'entity) with the anchor at +0x610, no modifier block')==1,table.concat(logged,' | '))
assert(spawn_calls[1].ax==60 and spawn_calls[1].ay==70 and spawn_calls[1].az==2)
assert(count('PELICAN SPAWN native call returned entity 9501')==1)
assert(count('PELICAN SPAWN CREATED (mods/test/pelican): entity 9501 (network id 700) at (10.0, 20.0, 5.0); empty: no '
    ..'cargo, no cargo entity, no associated entity; anchor (60.0, 70.0, 2.0) read back from its drop-position record; '
    ..'flight: behaviour 667, stage 1; verified true')==1,table.concat(logged,' | '))
assert(s.result.verify.anchor and near(pelicans.anchor(world_module.open(),9501).x,60))
assert(pelicans.owned(9501)and pelicans.active()[1]==9501)
-- Its flight: to the hover point, the hover, the release (held: one write), the departure, gone.
BOMB.set_clock(T0+10000000);stage(0,3,0);target(0,10,20,25);tick()
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);tick()
assert(last(events,'hovering'))
local writes=#W.runtime.writes
BOMB.set_clock(T0+21000000);stage(0,6,1);stamp(0,'releaseTime',T0+21000000);tick()
assert(last(events,'released')and last(events,'held').result.verified and #W.runtime.writes==writes+1)
assert(release_us(0)==T0+21000000+60000000-600000)
BOMB.set_clock(T0+81000000);stage(0,8,1);tick()
assert(near(last(events,'departing').after_release,60))
BOMB.set_clock(T0+95000000);tcount(0);tick()
local gone=last(events,'gone')
assert(gone and gone.entity==9501 and near(gone.after_release,74)and gone.held and not pelicans.owned(9501))
assert(not last(events,'cargo'))
return 'ok'
""")

    def test_every_spawn_refusal_calls_nothing(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
local function refused(code,prepare,spec)
    local undo=prepare and prepare()
    local events={}
    pelicans.request(spec or{x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican'},function(e)events[#events+1]=e end)
    local calls=#spawn_calls
    tick()
    local r=last(events,'refused')
    assert(r and r.code==code,code..' expected, got '..tostring(r and r.code)..': '..tostring(r and r.reason))
    assert(#spawn_calls==calls,code..': the game was called')
    if undo then undo()end
end
refused('NOT_IN_MISSION',function()W.state(3)return function()W.state(4)end end)
refused('HOST_ONLY',function()W.state(4,{host=false})return function()W.state(4)end end)
refused('UNSUPPORTED_BUILD',function()
    pelicans.reset_for_tests()
    local pin=PE.pins[1];W.write(W.GAME+pin.rva,string.char(0xCC))
    return function()W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end)
refused('UNSUPPORTED_BUILD',function()
    W.write(W.GAME+SP.rva+0xB0,string.char(0xCC))                     -- the request's bytes, outside every pin
    return function()W.write(W.GAME+SP.rva+0xB0,b.unhex(SP.prologue:sub(0xB0*2+1,0xB0*2+2)))end
end)
refused('CONTEXT_UNEXPECTED',function()
    W.write(CWORLD+SP.defaultContext+0x3F0,W.u32(77))               -- an associated entity in the default context
    return function()W.write(CWORLD+SP.defaultContext+0x3F0,W.u32(0))end
end)
refused('PELICAN_UNAVAILABLE',function()register(false)return function()register(true)end end)
refused('PELICAN_UNAVAILABLE',function()
    W.runtime.packages[PE.packageId]='absent'
    return function()W.runtime.packages[PE.packageId]=nil end
end)
refused('INVALID_POSITION',nil,{x=0/0,y=0,z=0,fx=0,fy=1,ax=1,ay=1,az=1})
refused('INVALID_POSITION',nil,{x=0,y=0,z=0,fx=0,fy=1,ax=1,ay=0/0,az=1})
refused('INVALID_POSITION',nil,{x=200000,y=0,z=0,fx=0,fy=1,ax=1,ay=1,az=1})
refused('INVALID_FACING',nil,{x=0,y=0,z=0,fx=1,fy=1,ax=1,ay=1,az=1})
-- At most MAX_ACTIVE Runtime Pelicans: the fifth is refused.
for _=1,pelicans.MAX_ACTIVE do pelicans.request({x=1,y=2,z=3,fx=1,fy=0,ax=4,ay=5,az=6})end
tick()
assert(#pelicans.active()==pelicans.MAX_ACTIVE)
refused('PELICAN_LIMIT')
-- Outside the Runtime's own update the call itself refuses.
local r,code=pelicans.spawn(world_module.open(),{x=1,y=2,z=3,fx=1,fy=0,ax=4,ay=5,az=6})
assert(not r and code=='NOT_GAME_THREAD')
return 'ok'
""")

    def test_a_pelican_without_the_anchor_is_reported_unverified(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
SPAWN.mode='no_anchor'
local events={}
pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican'},function(e)events[#events+1]=e end)
tick()
local u=last(events,'unverified')
assert(u and u.result.verify.empty and u.result.verify.anchor==false and not u.result.verified)
assert(count('anchor false (read (0.0, 0.0, 0.0))')==1,table.concat(logged,' | '))
return 'ok'
""")

    def test_a_pelican_with_cargo_is_reported_unverified(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
SPAWN.mode='cargo'
local events={}
pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican'},function(e)events[#events+1]=e end)
tick()
local u=last(events,'unverified')
assert(u and u.result.verify.exists and u.result.verify.empty==false and not u.result.verified)
assert(count('PELICAN SPAWN UNVERIFIED (mods/test/pelican): entity 9501: exists true, empty false')==1,
    table.concat(logged,' | '))
return 'ok'
""")

    def test_the_movers_diagnostic_reads_which_components_hold_a_pelican(self):
        self.check(r"""
pworld()
tcount(0)
transport(0,9001,{});tcount(1)
local world=world_module.open()
-- No flight component and no native mover in this world: none holds it.
local m=pelicans.movers(world,9001)
assert(m.flight==nil and m.flight_target==nil and m.ground==false and m.other==false)
-- The flight component holding it (record 0, its target), and the ground mover holding it too.
local FT,NM=PE.flightTarget,PE.nativeMovers
local fc,fr,gc=W.alloc(0x100),W.alloc(0x1000),W.alloc(0x100)
W.write(W.GAME+FT.global,W.u64(fc));W.write(fc+FT.records,W.u64(fr));map(fc,FT)(9001,0)
W.write(fr+FT.target,f32(1)..f32(2)..f32(3))
W.write(W.GAME+NM.ground.global,W.u64(gc));map(gc,NM.ground)(9001,4)
m=pelicans.movers(world,9001)
assert(m.flight==0 and near(m.flight_target.z,3)and m.ground==true and m.other==false)
assert(pelicans.movers(world,9002).flight==nil)
return 'ok'
""")


    def test_the_variant_readers_are_read_only(self):
        self.check(r"""
pworld()
tcount(0)
local world=world_module.open()
-- The type behaviour settings: the gunship's 202, the transport's 667 (a fixture table, the game's layout).
local VS=PE.variants.settings
local tab=W.alloc(VS.entries+64*VS.entryStride)
W.write(CWORLD+VS.offset,W.u64(tab))
local function put(hex,index,behaviour)
    local key=b.unhex(hex):reverse()
    local lo,hi=b.u32(key,0),b.u32(key,4)
    local slot=((hi%VS.slots)*(4294967296%VS.slots)+lo%VS.slots)%VS.slots
    W.write(tab+slot*16,key..W.u32(index)..W.u32(0))
    W.write(tab+VS.entries+index*VS.entryStride,W.u32(behaviour)..f32(20)..W.u32(0))
end
put(PE.variants.byType.shuttle_gunship.resource,3,202)
put(PE.variants.byType.shuttle_transport.resource,4,667)
assert(pelicans.type_behaviour(world,PE.variants.byType.shuttle_gunship.resource)==202)
assert(pelicans.type_behaviour(world,PE.variants.byType.shuttle_transport.resource)==667)
assert(pelicans.type_behaviour(world,'0123456789ABCDEF')==nil)
-- A live behaviour-202 entity (the gunship) and a 667 one: the scan finds them by behaviour.
local GUNSHIP=b.unhex(PE.variants.byType.shuttle_gunship.resource):reverse()
transport(0,8001,{resource=GUNSHIP,behaviour=202});stage(0,5,0);target(0,1,2,33);tcount(1)
W.write(b.pointer(W.read(BHANDLES,8),0),GUNSHIP)                      -- the Behavior handle's resource, as the game's
transport(1,8002,{});stage(1,6,1);tcount(2)
local found=pelicans.behaviours(world,{[202]=true})
assert(found[8001]and not found[8002]and found[8001].variant=='shuttle_gunship'and found[8001].stage==5
    and near(found[8001].target.z,33))
-- The weapon-side components: a fixture turret manager holding entity 8003.
local c=PE.turretComponents.turret
local comp=W.alloc(0x100);W.write(W.GAME+c.global,W.u64(comp))
map(comp,{keys=c.map,capacity=c.map+8,empty=c.map+0xC,multiplier=c.map+0x10})(8003,5)
local w=pelicans.weapon_components(world,8003)
assert(w.turret==5 and w.mount==nil and next(pelicans.weapon_components(world,8001))==nil)
return 'ok'
""")

    def test_the_pose_handle_and_attachment_readers(self):
        self.check(r"""
pworld()
tcount(0)
local world=world_module.open()
transport(0,8201,{});position(0,10,20,30);tcount(1)
-- A yaw of +90 degrees (z up): the rotation quaternion (0, 0, sin 45, cos 45); its forward (Y) turns to -X.
local h=math.sqrt(0.5)
W.write(XRECORDS+0*XC.stride+PE.pose.rotation,f32(0)..f32(0)..f32(h)..f32(h))
local pose=pelicans.pose(world,8201)
assert(pose and near(pose.position.z,30)and near(pose.forward.x,-1)and near(pose.forward.y,0)and near(pose.yaw,180)
    and near(pose.pitch,0),tostring(pose and pose.yaw))
-- Its Behavior handle's link (+0xC).
local handle=b.pointer(W.read(BHANDLES,8),0)
W.write(handle,PELICAN..W.u32(8201)..W.u32(0x40083B)..W.u32(701))
local hd=pelicans.handle(world,8201)
assert(hd.resource==PE.entity and hd.entity==8201 and hd.link==0x40083B and hd.network==701)
-- A mounted child's attachable record: its parent's link, the node, its world position.
local A=PE.attachment
local comp=W.alloc(0x100);W.write(W.GAME+A.global,W.u64(comp))
local recs=W.alloc(0x1000);W.write(comp+A.records,W.u64(recs))
map(comp,{keys=A.map,capacity=A.map+8,empty=A.map+0xC,multiplier=A.map+0x10})(8202,1)
W.write(recs+A.stride,W.u32(0x40083B)..W.u32(35)..W.u32(4294967295)..W.u32(4294967295)..f32(1)..f32(2)..f32(3)
    ..f32(0)..f32(0)..f32(0)..f32(1))
local at=pelicans.attachable(world,8202)
assert(at and at.link==hd.link and at.node==35 and near(at.position.y,2)and near(at.rotation.w,1))
assert(pelicans.attachable(world,8201)==nil)
return 'ok'
""")

    def test_the_turret_weapon_reader(self):
        self.check(r"""
pworld()
local world=world_module.open()
-- A chin turret: a magazine weapon (flags 0x80), 300 RPM, no pattern, 500 rounds, chambered 120, no copies.
local set_magazine=turret_weapon(8301,{flags=0xC0,interval=0.2,rpm=300,rounds=500,chambered=120})
local w=pelicans.weapon_config(world,8301)
assert(w and w.path=='magazine'and w.flags==0xC0 and not w.heat and not w.windUp and w.copy==nil
    and near(w.interval,0.2)and near(w.rpm,300)and near(w.currentRpm,300)and near(w.rofSlots.y,300)and w.rofIndex==1)
assert(w.magazine.rounds==500 and not w.magazine.pattern and w.magazine.chambered==120 and not w.magazine.copy)
set_magazine(499,120)
assert(pelicans.weapon_config(world,8301).magazine.rounds==499)
assert(pelicans.weapon_config(world,8302)==nil)
-- With its own resolved ProjectileWeapon copy, a heat weapon and a wind-up.
turret_weapon(8303,{flags=0x200,interval=60/1600,rpm=1600,rounds=0,chambered=0,copy={projectileType=148,rpm=1600},
    windUp=true})
w=pelicans.weapon_config(world,8303)
assert(w.path=='heat'and w.copy.projectileType==148 and near(w.copy.rpm.y,1600)and w.windUp and near(w.rpm,1600))
assert(pelicans.turret_types.gatlingSentry.projectileType==148 and pelicans.turret_types.chinTurret.rpmSlots[2]==300)
return 'ok'
""")

RETARGET = r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
local events={}
pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican',hold=60},
    function(e)events[#events+1]=e end)
tick()
local world=world_module.open()
-- Hovering, then released and held (the manager's one write).
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);position(0,60,70,15);tick()
BOMB.set_clock(T0+21000000);stage(0,6,1);stamp(0,'releaseTime',T0+21000000);tick()
assert(last(events,'held').result.verified)
local function targets()return pelicans.targets(world,9501)end
"""


class PelicanRetargetTests(unittest.TestCase):
    """runtime/pelicans.lua retarget and orbit (research "retarget"): a held Runtime Pelican's hover point is per-instance
    data, P+0x1BC and the flight record's +0x4FC written together in one guarded transaction; the orbit moves it around a
    circle and puts the game's own hover point back at the end."""

    def check(self, body):
        self.assertEqual(lua(RETARGET + body), b'ok')

    def test_a_held_pelican_is_retargeted_in_one_guarded_transaction_and_every_refusal_writes_nothing(self):
        self.check(r"""
local t=targets()
assert(t and near(t.flight.z,8)and near(t.behaviour.x,60)and t.flight_index==0)
local writes=#W.runtime.writes
local r,code,why=pelicans.retarget(world,9501,t.raw,{x=90,y=70,z=62})
-- Six 4-byte members (x, y, z of both targets); y is unchanged, so 4 are written.
assert(r and r.verified and r.writes==4 and #W.runtime.writes==writes+4,tostring(code)..' '..tostring(why)..' '
    ..tostring(r and r.writes))
assert(near(SPAWN.flight_target(0).x,90)and near(SPAWN.flight_target(0).z,62)and near(targets().behaviour.x,90))
local function refused(want,expect,point,prepare)
    local undo=prepare and prepare()
    local before=#W.runtime.writes
    local got,c=pelicans.retarget(world,9501,expect or targets().raw,point or{x=61,y=70,z=40})
    assert(got==nil and c==want and #W.runtime.writes==before,want..' expected, got '..tostring(c))
    if undo then undo()end
end
refused('TARGET_CHANGED',t.raw)                                    -- the old observation: another writer is not fought
refused('OUT_OF_RANGE',nil,{x=60+250,y=70,z=40})
refused('OUT_OF_RANGE',nil,{x=60,y=70,z=-5})
refused('INVALID_TARGET',nil,{x=0/0,y=0,z=0})
refused('NOT_HOLDING',nil,nil,function()stage(0,8,1);return function()stage(0,6,1)end end)
refused('NATIVE_MOVER',nil,nil,function()
    local g=W.alloc(0x100);W.write(W.GAME+PE.nativeMovers.ground.global,W.u64(g));map(g,PE.nativeMovers.ground)(9501,0)
    return function()W.write(W.GAME+PE.nativeMovers.ground.global,W.u64(0))end end)
refused('NOT_IN_MISSION',nil,nil,function()W.state(3)return function()W.state(4)end end)
assert(select(2,pelicans.retarget(world,4242,targets().raw,{x=61,y=70,z=40}))=='NOT_RUNTIME_PELICAN')
return 'ok'
""")

    def test_a_target_across_a_page_boundary_is_written_as_aligned_members(self):
        # Live (OrbitProof 0.1.0, 44.9 s): the flight record moved and its 12-byte target straddled a page; the guarded
        # transaction refused it by an error. The retarget now writes three aligned 4-byte members per target.
        self.check(r"""
local FT=PE.flightTarget
local fc=b.pointer(W.read(W.GAME+FT.global,8),0)
local old=b.pointer(W.read(fc+FT.records,8),0)
local raw=W.read(old,FT.stride)
local page=W.alloc(0x3000)
local moved=page+0x1000-FT.target-4                                 -- its target: the last 4 bytes of a page + 8
W.write(moved,raw);W.write(fc+FT.records,W.u64(moved))
local t=targets()
assert((t.flight_record+FT.target)%4096==4092,'the target straddles a page')
local r,code,why=pelicans.retarget(world,9501,t.raw,{x=70,y=80,z=62})
assert(r and r.verified,tostring(code)..' '..tostring(why))
assert(near(SPAWN.flight_target(0).x,70)or near(targets().flight.x,70))
assert(near(targets().flight.y,80)and near(targets().flight.z,62))
return 'ok'
""")

    def test_the_orbit_sweeps_the_circle_then_puts_the_hover_point_back_and_the_departure_is_the_games(self):
        self.check(r"""
local home=SPAWN.flight_target(0)
local seen={}
local o=assert(pelicans.orbit(9501,{center={x=60,y=70,z=2},radius=40,altitude=60,duration=10,interval=0.5,period=10,
    mode='sweep',entry=2,label='test'},function(e)seen[#seen+1]=e end))
-- The Pelican follows its target (each update it is moved onto it).
local clock=T0+21000000
local points={}
for k=1,48 do
    clock=clock+250000;BOMB.set_clock(clock)
    local f=SPAWN.flight_target(0);position(0,f.x,f.y,f.z)
    tick()
    local g=SPAWN.flight_target(0)
    if math.abs(g.z-62)<1e-3 then points[#points+1]=g end
end
local started=last(seen,'started')
assert(started and count('ORBIT STARTED: Pelican 9501 (test): sweep mode, centre (60.0, 70.0, 2.0), radius 40.0 m, '
    ..'60.0 m above it, 10.0 s, a target every 0.50 s, one lap every 10 s; entry 2.0 s from 6.0 m up')==1,
    table.concat(logged,' | '))
assert(last(seen,'established')and near(started.from_height,6))
for _,p in ipairs(points)do assert(math.abs(math.sqrt((p.x-60)^2+(p.y-70)^2)-40)<1e-2,'a target off the circle')end
assert(#points>=12,'targets written: '..#points)
local stop=last(seen,'stopped')
assert(stop and stop.reason:find('the duration (10.0 s) is over',1,true)and stop.refusals==0,tostring(stop and stop.reason))
assert(stop.stats.degrees>270 and stop.stats.laps<1.2,'turned '..tostring(stop.stats.degrees))
assert(near(stop.stats.radius.max,40)and near(stop.stats.height.max,60))
-- The game's hover point is back; the game's departure then pushes its own target.
local back=SPAWN.flight_target(0)
assert(near(back.x,home.x)and near(back.y,home.y)and near(back.z,home.z))
local samples=0
for _,e in ipairs(seen)do if e.kind=='sample'then samples=samples+1 end end
assert(samples>=7)
BOMB.set_clock(T0+81000000);stage(0,8,1);SPAWN.push(0,500,500,100);tick()
assert(near(SPAWN.flight_target(0).x,500)and last(events,'departing'))
return 'ok'
""")

    def test_the_orbit_stops_without_fighting_when_overwritten_or_when_the_game_departs(self):
        self.check(r"""
local seen={}
assert(pelicans.orbit(9501,{center={x=60,y=70,z=2},radius=40,altitude=60,duration=60,interval=0.25,mode='steps',
    step=45,near=8,entry=0},function(e)seen[#seen+1]=e end))
BOMB.set_clock(T0+21250000);tick()
local first=SPAWN.flight_target(0)
assert(near(first.x,100)and near(first.y,70)and near(first.z,62))   -- angle 0 (the Pelican over the centre)
-- Steps: no new target until it is within 8 m of the current one; then 45 degrees on.
BOMB.set_clock(T0+21500000);tick()
assert(near(SPAWN.flight_target(0).x,100))
position(0,96,71,60);BOMB.set_clock(T0+21750000);tick()
local second=SPAWN.flight_target(0)
assert(near(second.x,60+40*math.cos(math.pi/4))and near(second.y,70+40*math.sin(math.pi/4)))
-- Another writer changes the target: the orbit stops and writes nothing more.
SPAWN.push(0,1,2,30)
local writes=#W.runtime.writes
BOMB.set_clock(T0+22000000);tick()
assert(last(seen,'stopped').reason:find('OVERWRITTEN',1,true)and #W.runtime.writes==writes)
assert(near(SPAWN.flight_target(0).x,1))
-- A new orbit, then the game departs: it stops at once.
SPAWN.push(0,60,70,8)
seen={}
assert(pelicans.orbit(9501,{center={x=60,y=70,z=2},radius=40,altitude=60,duration=60,interval=0.25,entry=0},
    function(e)seen[#seen+1]=e end))
BOMB.set_clock(T0+22250000);tick()
stage(0,8,1);SPAWN.push(0,500,500,100);BOMB.set_clock(T0+22500000);tick()
assert(last(seen,'stopped').reason:find('the game ended the hold (stage 8)',1,true))
assert(near(SPAWN.flight_target(0).x,500))                          -- the departure's own target, untouched
-- Lead: the target 10 m ahead along the circle of its own angle (the Pelican out on the circle, at angle 0).
SPAWN.push(0,60,70,8);stage(0,6,1);position(0,100,70,62)
seen={}
assert(pelicans.orbit(9501,{center={x=60,y=70,z=2},radius=40,altitude=60,duration=20,interval=0.25,mode='lead',lead=10,
    entry=0},function(e)seen[#seen+1]=e end))
BOMB.set_clock(T0+30000000);tick()
local lt=SPAWN.flight_target(0)
assert(near(lt.x,60+40*math.cos(0.25))and near(lt.y,70+40*math.sin(0.25))and near(lt.z,62),lt.x..', '..lt.y)
position(0,60,110,62);BOMB.set_clock(T0+30500000);tick()        -- now at 90 degrees: the target 0.25 rad beyond
local lt2=SPAWN.flight_target(0)
assert(near(lt2.x,60+40*math.cos(math.pi/2+0.25))and near(lt2.y,70+40*math.sin(math.pi/2+0.25)))
assert(count('10 m ahead')>=1)
stage(0,8,1);SPAWN.push(0,500,500,100);BOMB.set_clock(T0+31000000);tick()
-- Bad specs are refused.
assert(select(2,pelicans.orbit(9501,{center={x=0,y=0,z=0},radius=500,altitude=60,duration=60})):find('radius',1,true))
assert(select(2,pelicans.orbit(9501,{center={x=0,y=0,z=0},radius=40,altitude=60,duration=60,mode='spin'})))
assert(select(2,pelicans.orbit(9501,{center={x=0,y=0,z=0},radius=40,altitude=60,duration=10,entry=10})):find('entry',1,
    true))

-- The entry: a new orbit spirals out and climbs from its hover (6 m up, over the centre) to 40 m out, 60 m up in 4 s.
SPAWN.push(0,60,70,8);stage(0,6,1)
seen={}
assert(pelicans.orbit(9501,{center={x=60,y=70,z=2},radius=40,altitude=60,duration=20,interval=0.5,period=20,entry=4},
    function(e)seen[#seen+1]=e end))
local clock=T0+23000000
local heights,radii={},{}
for _=1,24 do
    clock=clock+250000;BOMB.set_clock(clock)
    local f=SPAWN.flight_target(0);position(0,f.x,f.y,f.z)
    tick()
    local g=SPAWN.flight_target(0)
    heights[#heights+1]=g.z-2;radii[#radii+1]=math.sqrt((g.x-60)^2+(g.y-70)^2)
end
assert(heights[1]<12 and radii[1]<5,'the first entry target is near its hover: '..heights[1]..', '..radii[1])
for k=2,#heights do assert(heights[k]>=heights[k-1]-1e-3 and radii[k]>=radii[k-1]-1e-3,'the entry only grows')end
assert(near(heights[#heights],60)and near(radii[#radii],40),'established: '..heights[#heights]..', '..radii[#radii])
assert(last(seen,'established'))
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
