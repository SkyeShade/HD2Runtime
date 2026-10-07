"""The development beacon API (runtime/beacons.lua; research/docs/beacon-redirect-F5FEE03DCFDB.md, "The beacon API"):
semantic timing (call_in_time = countdown - threshold, lifetime_after_activation = threshold), one guarded transaction per
change (delivery, timing, or both atomically), every refusal writing nothing, and the first-update watch. Offline: the
payload world with the beacon manager of tests/test_beacon_redirect.py."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

API = r"""
local beacons=require('hd2runtime/runtime/beacons')
beacons.reset_for_tests()
local function near(a,b0)return math.abs(a-b0)<1e-4 end
local function timers()local e=element(0);return b.value(e,0,'f32'),b.value(e,4,'f32')end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + BEACONS + API + body)


class BeaconApiTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_timing_semantics(self):
        self.check(r'''
-- An AC-8 created with a 3 s call-in and an 8.717 s threshold.
local c,h=beacons.plan_timing(11.717,8.717,{call_in_time=6})          -- the call-in, keeping the lifetime
assert(near(c,14.717)and near(h,8.717))
c,h=beacons.plan_timing(11.717,8.717,{lifetime_after_activation=20})  -- the lifetime, keeping the call-in
assert(near(c,23)and near(h,20))
c,h=beacons.plan_timing(8.715,8.715,{call_in_time=4,lifetime_after_activation=22.444})
assert(near(c,26.444)and near(h,22.444))
c,h=beacons.plan_timing(11.717,8.717,{countdown=30,activation_threshold=10})  -- explicit
assert(c==30 and h==10)
local function bad(change)local x,code=beacons.plan_timing(11.717,8.717,change);assert(not x and code=='TIMING_INVALID')end
bad({call_in_time=-1})
bad({lifetime_after_activation=0})
bad({call_in_time=200})
bad({countdown=5,activation_threshold=8})                              -- no crossing would happen
bad({call_in_time=4,countdown=12})                                     -- semantic and explicit mixed
bad({call_in_time=0/0})
local t=beacons.timing_of({countdown=26.444,threshold=22.444})
assert(near(t.call_in_time,4)and near(t.lifetime_after_activation,22.444))
return 'ok'
''')

    def test_apply_timing_delivery_and_both(self):
        self.check(r'''
pworld()
local world=world_module.open()
-- Timing only: an AC-8 beacon (as created) gets a 6 s call-in; its lifetime is kept; nothing else changes.
beacon(0,7601,25,11.717,8.717);counts(1,1)
local before=element(0)
local writes=#W.runtime.writes
local r,code,why=beacons.apply(world,7601,{type=25,timers=before:sub(1,8)},{call_in_time=6})
assert(r and r.verified,tostring(code)..' '..tostring(why))
local c,h=timers()
assert(near(c,14.717)and near(h,8.717)and type_at(0)==25 and r.delivery==nil and near(r.timing.to.call_in_time,6))
local after=element(0)
for i=1,0x40 do assert(after:byte(i)==before:byte(i)or i<=4,'byte '..(i-1))end      -- only the countdown changed
assert(#W.runtime.writes==writes+1)
-- Delivery and timing in one transaction (the 120mm with a native 120mm's timing).
BR.reset_for_tests()
beacon(0,7602,25,8.715,8.715);counts(1,1)
before=element(0)
writes=#W.runtime.writes
r=assert(beacons.apply(world,7602,{type=25,timers=before:sub(1,8)},{delivery='Orbital 120mm HE Barrage',call_in_time=4,
    lifetime_after_activation=22.444}))
c,h=timers()
assert(r.verified and type_at(0)==136 and near(c,26.444)and near(h,22.444)and#W.runtime.writes==writes+3)
assert(r.delivery.from==25 and r.delivery.to==136 and r.delivery.to_name=='Orbital 120mm HE Barrage')
assert(count('beacon APPLIED: beacon 7602 (index 0): delivery AC-8 Autocannon -> Orbital 120mm HE Barrage, call-in 0.000 '
    ..'-> 4.000 s, lifetime after activation 8.715 -> 22.444 s; 3 writes; verified true')==1)
-- Delivery 'none' (neutral) alone.
beacon(0,7603,25,11.717,8.717);counts(1,1)
r=assert(beacons.apply(world,7603,{type=25},{delivery='none'}))
assert(r.verified and type_at(0)==0)
-- No StratagemInfo row written.
assert(W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES)
return 'ok'
''')

    def test_every_refusal_writes_nothing(self):
        self.check(r'''
pworld()
local function refused(code,expect,change,prepare,entity)
    beacon(0,7701,25,11.717,8.717);counts(1,1)
    W.write(STATE+0x8E4,string.char(0));W.write(STATE+0x8E0,W.u32(1))
    local undo=prepare and prepare()
    local before=element(0)
    local writes=#W.runtime.writes
    local r,got,why=beacons.apply(world_module.open(),entity or 7701,expect or{type=25,timers=before:sub(1,8)},
        change or{call_in_time=6})
    assert(not r and got==code,code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#W.runtime.writes==writes and element(0)==before,code..': written')
    if undo then undo()end
end
refused('ACTIVATED',nil,nil,function()activate(0)end)
refused('CROSSED',nil,nil,function()set_countdown(0,8.0)end)
refused('TIMING_UNEXPECTED',nil,nil,function()W.write(ELEMENTS+4,b.encode(0,'f32'))end)                  -- threshold 0
refused('TIMING_UNEXPECTED',{type=25,timers=b.encode(11.0,'f32')..b.encode(8.717,'f32')})              -- not as observed
refused('UNEXPECTED_TYPE',{type=30})
refused('NOT_NORMAL_MODE',nil,nil,function()W.write(STATE+0x8E0,W.u32(2))end)        -- delivered by the host
refused('NOT_NORMAL_MODE',nil,nil,function()W.write(STATE+0x8E0,W.u32(0))end)        -- blocked
refused('NOT_OWNED',nil,nil,function()counts(1,0)end)                                 -- a copy: no state here
refused('GONE',nil,nil,nil,9999)
refused('TIMING_INVALID',nil,{call_in_time=-2})
refused('TIMING_INVALID',nil,{lifetime_after_activation=200})
refused('UNKNOWN_DELIVERY',nil,{delivery='Not A Stratagem'})
refused('INVALID',nil,{})
refused('NOT_HOST',nil,nil,function()W.state(4,{host=false})return function()W.state(4)end end)
refused('NOT_IN_MISSION',nil,nil,function()W.state(3)return function()W.state(4)end end)
refused('UNSUPPORTED_BUILD',nil,nil,function()
    BR.reset_for_tests()                                   -- the pins' proof is cached per loaded game.dll
    local pin=BD.pins[1];W.write(W.GAME+pin.rva,string.char(0xCC))
    return function()W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end)
-- A delivery whose call-in package is not resident.
local assets=require('hd2runtime/core/assets')
local PACKAGE=assets.dependency_for_stratagem(BIG_ID,'x').package
W.runtime.packages[PACKAGE]='absent'
refused('DELIVERY_NOT_RESIDENT',nil,{delivery='Orbital 120mm HE Barrage'})
W.runtime.packages[PACKAGE]=nil
return 'ok'
''')

    def test_the_watch_decides_in_the_first_update_and_measures_the_timing(self):
        self.check(r'''
pworld()
BOMB.set_clock(500000000)
local events={}
local decided
local watch=assert(beacons.watch({carrier='AC-8 Autocannon',decide=function(beacon)
    decided=beacon
    return {call_in_time=6,lifetime_after_activation=12}
end},function(e)events[#events+1]=e end))
tick()
assert(events[1].kind=='ready')
beacon(0,7801,25,11.717,8.717);counts(1,1);tick()
assert(decided and decided.entity==7801 and decided.carrier=='AC-8 Autocannon'and near(decided.timing.call_in_time,3))
local applied
for _,e in ipairs(events)do if e.kind=='applied'then applied=e end end
assert(applied and applied.result.verified and near(applied.result.timing.to.call_in_time,6))
local c,h=timers()
assert(near(c,18)and near(h,12))
-- Another stratagem's beacon: reported as observed, never changed.
beacon(1,7802,136,26.444,22.444);counts(2,2);tick()
local seen
for _,e in ipairs(events)do if e.kind=='created'and e.beacon.entity==7802 then seen=e end end
assert(seen and seen.observed and b.u32(W.read(ELEMENTS+0x40+0xC,4),0)==136)
-- The activation 6 s later, the beacon gone 12 s after it.
set_countdown(0,11.9);activate(0);BOMB.set_clock(506000000);tick()
local act
for _,e in ipairs(events)do if e.kind=='activated'and e.entity==7801 then act=e end end
assert(act and near(act.seconds,6)and act.delivery=='AC-8 Autocannon')
counts(0,0);BOMB.set_clock(518000000);tick()
local gone
for _,e in ipairs(events)do if e.kind=='gone'and e.entity==7801 then gone=e end end
assert(gone and near(gone.after,12))
return 'ok'
''')


class BeaconWatchReplacementTests(unittest.TestCase):
    def test_a_second_watch_replaces_the_first_loudly(self):
        self.assertEqual(lua(r'''
pworld()
local first=assert(beacons.watch({carrier='AC-8 Autocannon',label='timing proof'}))
local second=assert(beacons.watch({carrier='AC-8 Autocannon',label='gas proof'}))
assert(first.status=='cancelled'and second.status=='active')
assert(count('beacon WATCH REPLACED: "timing proof" stopped; "gas proof" now runs')==1,table.concat(logged,' | '))
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
