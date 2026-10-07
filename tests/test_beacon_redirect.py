"""The per-beacon redirect (runtime/beacon_redirect.lua; research/docs/beacon-redirect-F5FEE03DCFDB.md): in the update an
Eagle Strafing Run (30) or AC-8 Autocannon (25) beacon is first seen, one guarded 4-byte write changes that beacon's type
(+0xC) to the 120mm's 136 (or to 0, neutral); nothing else of the beacon, no StratagemInfo and no payload record
changes; every failed guard writes nothing; a beacon whose countdown has started (+0x3C) but not crossed its threshold
is still redirected; the beacon is then watched to its activation, with the call-in timing (game clock), the
dispatcher's own record, the marker's type and, with observe, every other beacon reported read-only. Offline: the
payload world (its component world object is the beacon manager's root) with a beacon manager and a marker component
laid out as the research found them."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

RESEARCH = json.loads((ROOT / 'research/beacon-redirect-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

BEACONS = r"""
local BR=require('hd2runtime/runtime/beacon_redirect')
local BD=require('hd2runtime/domains/beacon_redirect')
BR.reset_for_tests()
for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
-- Eagle Strafing Run's row (type 30) carrying its stable id; the 120mm is type 136 in the payload world.
local TABLE_RVA=require('hd2runtime/schemas/current').stratagem.table_rva
local ROW30=W.alloc(400);W.write(ROW30,W.u32(30)..W.u32(2808191861));W.write(W.GAME+TABLE_RVA+30*8,W.u64(ROW30))
-- AC-8 Autocannon (type 25): a supply (blue) hellpod with its call-in members (call-in 3 s, linger 4 s, re-targeting).
local ROW25=W.alloc(400);W.write(ROW25,W.u32(25)..W.u32(875551083));W.write(W.GAME+TABLE_RVA+25*8,W.u64(ROW25))
local TR=BD.timing.row
W.write(ROW25+TR.callIn,b.encode(3,'f32'));W.write(ROW25+TR.linger,b.encode(4,'f32'));W.write(ROW25+TR.kind,W.u32(2))
W.write(ROW25+TR.category,W.u32(2));W.write(ROW25+TR.follows,string.char(2))
W.write(ROW[136]+TR.callIn,b.encode(5,'f32'));W.write(ROW[136]+TR.kind,W.u32(5));W.write(ROW[136]+TR.category,W.u32(0))
local ROW30_BYTES,ROW136_BYTES,ROW25_BYTES=W.read(ROW30,400),W.read(ROW[136],400),W.read(ROW25,400)
local BIG_PAYLOAD='0x2D3BD00B1ED411B1'
-- The beacon manager under the component world object W.bombardment() installed.
local COMPONENT_WORLD=b.pointer(W.read(W.GAME+BD.path.world,8),0)
local MGR=COMPONENT_WORLD+BD.path.systems+BD.path.beacons
local HANDLES,STATE,ELEMENTS=W.alloc(0x1000),W.alloc(0x3000),W.alloc(0x1000)  -- page-sized: a target page lies inside its allocation
W.write(MGR+0x50,W.u32(128))
W.write(MGR+0x60,W.u64(HANDLES));W.write(MGR+0x68,W.u64(STATE));W.write(MGR+0x78,W.u64(ELEMENTS))
local function f32(v)return b.encode(v,'f32')end
local function beacon(i,entity,kind,countdown,threshold)
    local handle=W.alloc(0x20);W.write(handle+8,W.u32(entity));W.write(HANDLES+i*8,W.u64(handle))
    local e=ELEMENTS+i*0x40
    W.write(e,f32(countdown)..f32(threshold)..W.u32(0x11)..W.u32(kind)..f32(10)..f32(0)..f32(20)..f32(10)..f32(0)
        ..f32(20)..W.u32(0)..string.rep('\0',0x10)..string.char(0)..'\0\0\0')
    W.write(STATE+i*0x8E8+0x8E0,W.u32(1)..string.char(0))   -- mode 1: a normal owned beacon (live)
end
local function counts(n,active)W.write(MGR+0x34,W.u32(n)..W.u32(active))end
local function activate(i)W.write(STATE+i*0x8E8+0x8E4,string.char(1))end
-- The game's activation as the dispatcher leaves it (BD.dispatch): its record in the state, the waves, "activated".
local DR=BD.dispatch
local function dispatched(i,kind,payload)
    local at=STATE+i*0x8E8
    W.write(at+DR.payload,(b.unhex((payload:gsub('^0x',''))):reverse()));W.write(at+DR.called,string.char(1))
    W.write(at+DR.type,W.u32(kind));W.write(at+DR.waveType,W.u32(kind));W.write(at+DR.spawn,W.u32(DR.spawnRequested))
    W.write(ELEMENTS+i*0x40+DR.elementWaves,W.u32(1))
    activate(i)
end
local function counting(i)W.write(ELEMENTS+i*0x40+0x3C,string.char(1))end
-- Barrage instance states (BD.bombardment) in the fixture's bombardment manager (BOMB.set_instances makes the handles,
-- entities 4243, 4244, ...): set_barrage(i, fired, left, salvos, salvo timer).
local BI=BD.bombardment
local BMGR=b.pointer(W.read(W.GAME+PD.manager.global,8),0)
local BSTATES,BTIMERS=W.alloc(0x1000),W.alloc(0x100)
W.write(BMGR+BI.states,W.u64(BSTATES));W.write(BMGR+BI.removalTimers,W.u64(BTIMERS))
local function set_barrage(i,fired,left,salvos,timer)
    W.write(BSTATES+i*BI.stride,W.u32(fired)..W.u32(left)..b.encode(0.5,'f32')..W.u32(salvos)..b.encode(timer or 0,'f32')
        ..b.encode(10,'f32')..b.encode(0,'f32')..b.encode(20,'f32'))
end
local function set_countdown(i,v)W.write(ELEMENTS+i*0x40,b.encode(v,'f32'))end
-- The marker component (BD.marker): a 16-slot entity map (multiplier 1) and its elements' own types.
local MK=BD.marker
local MARKERS,MKEYS,MELEMENTS=W.alloc(0x100),W.alloc(0x100),W.alloc(0x400)
W.write(W.GAME+MK.global,W.u64(MARKERS));W.write(MARKERS+MK.keys,W.u64(MKEYS));W.write(MARKERS+MK.elements,W.u64(MELEMENTS))
W.write(MARKERS+MK.capacity,W.u32(16));W.write(MARKERS+MK.empty,W.u32(4294967295));W.write(MARKERS+MK.multiplier,W.u32(1))
for k=0,15 do W.write(MKEYS+k*8,W.u32(4294967295)..W.u32(0))end
local marked=0
local function marker(entity,kind)
    local slot=entity%16
    while b.u32(W.read(MKEYS+slot*8,4),0)~=4294967295 do slot=(slot+1)%16 end
    W.write(MKEYS+slot*8,W.u32(entity)..W.u32(marked));W.write(MELEMENTS+marked*MK.stride+MK.type,W.u32(kind))
    marked=marked+1
end
local function element(i)return W.read(ELEMENTS+i*0x40,0x40)end
local function type_at(i)return b.u32(element(i),0xC)end
local function arm(spec)
    local events={}
    local watch,why=BR.arm(spec or{carrier='Eagle Strafing Run',target='Orbital 120mm HE Barrage'},
        function(e)events[#events+1]=e end)
    assert(watch,why)
    return events
end
local function kinds(events)local out={};for k,e in ipairs(events)do out[k]=e.kind end;return table.concat(out,',')end
local function last(events,kind)for k=#events,1,-1 do if events[k].kind==kind then return events[k]end end end
local SPEC={carrierType=30,targetType=136,resident=true}
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + BEACONS + body)


class BeaconRedirectResearchTests(unittest.TestCase):
    def test_the_domain_is_current(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_beacon_redirect
        self.assertEqual(generate_beacon_redirect.generate(check=True), [])
        roles = {p['rva'] for rows in RESEARCH['pins'].values() for p in rows}
        self.assertTrue({0x6ABC14, 0x6ABE0E, 0x6ABE21, 0x6ABB8D, 0x5712FB} <= roles)


class BeaconRedirectTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_eagle_30_becomes_136_in_the_update_it_is_first_seen_and_only_the_type_changes(self):
        self.check(r'''
pworld()
local events=arm()
tick()
assert(kinds(events)=='armed,ready',kinds(events))
assert(events[1].carrierType==30 and events[1].targetType==136)
local writes=#W.runtime.writes
local bomb=BOMB.read(BIG_ID)
-- A Strafing Run beacon appears: its 1.2 s window is not waited for.
beacon(0,7001,30,1.2,0.0);counts(1,1)
local before=element(0)
assert(type_at(0)==30)
tick()
assert(kinds(events)=='armed,ready,created,applied',kinds(events))
local a=last(events,'applied')
assert(a.entity==7001 and a.from==30 and a.to==136 and a.writes==1 and a.frame==last(events,'created').frame)
for _,key in ipairs({'type','others','nonTarget','protection'})do assert(a.verify[key],key)end
assert(#W.runtime.writes==writes+1 and W.runtime.writes[#W.runtime.writes].address==ELEMENTS+0xC)
assert(type_at(0)==136)
local after=element(0)
for i=1,0x40 do assert(after:byte(i)==before:byte(i)or(i>0xC and i<=0x10),'element byte '..(i-1)..' changed')end
-- No StratagemInfo row, no payload record written.
assert(W.read(ROW30,400)==ROW30_BYTES and W.read(ROW[136],400)==ROW136_BYTES and BOMB.read(BIG_ID)==bomb)
assert(count('beacon redirect APPLIED: beacon 7001 (index 0): type 30 -> 136; 1 write; type reads back true; its '
    ..'other members unchanged true; non-target bytes unchanged true; protection restored true')==1)
-- The game activates it: the type it had then.
tick();tick()
assert(not last(events,'activated'))
activate(0);tick()
local act=last(events,'activated')
assert(act and act.type==136 and act.redirected and act.applied and act.updates==3,kinds(events))
counts(0,0);tick()
assert(last(events,'gone')and last(events,'gone').activated)
assert(#W.runtime.writes==writes+1)
return 'ok'
''')

    def test_neutral_writes_0_and_a_one_update_window_is_enough(self):
        self.check(r'''
pworld()
local events=arm({carrier='Eagle Strafing Run',neutral=true})
tick()
assert(kinds(events)=='armed',kinds(events))             -- no package for type 0
assert(events[1].targetType==0)
-- A beacon with one update before activation: written in that update, activated in the next.
beacon(0,7002,30,0.01,0.0);counts(1,1)
tick()
assert(last(events,'applied')and type_at(0)==0,kinds(events))
activate(0);tick()
local act=last(events,'activated')
assert(act.type==0 and act.redirected and act.updates==1)
return 'ok'
''')

    def test_every_failed_guard_writes_nothing(self):
        self.check(r'''
pworld()
local world=world_module.open()
local function refused(code,prepare,entity,spec)
    BR.reset_for_tests()
    for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
    beacon(0,7001,30,1.2,0.0);counts(1,1)
    local undo=prepare and prepare()
    local before=element(0)
    local writes=#W.runtime.writes
    local result,got,why=BR.redirect_now(world_module.open(),spec or SPEC,entity or 7001)
    assert(not result and got==code,code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#W.runtime.writes==writes and element(0)==before,code..': written')
    if undo then undo()end
end
-- The expected start, then each refusal.
refused('NOT_THE_CARRIER',function()W.write(ELEMENTS+0xC,W.u32(118))end)                 -- a wrong beacon type
refused('ACTIVATED',function()activate(0)return function()W.write(STATE+0x8E4,string.char(0))end end)
refused('CROSSED',function()set_countdown(0,-0.01)end)                                     -- below its threshold
refused('REMOTE',function()W.write(STATE+0x8E0,W.u32(2))end)                              -- a remote copy
refused('GONE',nil,9999)                                                                  -- a missing beacon
refused('GONE',function()counts(0,0)end)                                                  -- removed
refused('TARGET_NOT_RESIDENT',nil,nil,{carrierType=30,targetType=136,resident=false})
refused('UNSUPPORTED_BUILD',function()
    local pin=BD.pins[1];W.write(W.GAME+pin.rva,string.char(0xCC))
    return function()W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end)
refused('NOT_HOST',function()W.state(4,{host=false})return function()W.state(4)end end)
refused('NOT_IN_MISSION',function()W.state(3)return function()W.state(4)end end)
-- Repeated application: the second attempt is refused and writes nothing.
BR.reset_for_tests()
beacon(0,7003,30,1.2,0.0);counts(1,1)
assert(BR.redirect_now(world_module.open(),SPEC,7003))
local writes=#W.runtime.writes
local again,code=BR.redirect_now(world_module.open(),SPEC,7003)
assert(not again and code=='ALREADY_REDIRECTED'and#W.runtime.writes==writes and type_at(0)==136)
return 'ok'
''')

    def test_the_watch_ignores_other_types_reports_misses_and_reverts(self):
        self.check(r'''
pworld()
local events=arm()
tick()
local writes=#W.runtime.writes
-- Another stratagem's beacon: not touched.
beacon(0,7010,118,2.0,0.0);counts(1,1);tick()
assert(kinds(events)=='armed,ready'and#W.runtime.writes==writes,kinds(events))
-- A carrier beacon first seen already activated: the window was missed, nothing written.
beacon(1,7011,30,0.0,0.0);activate(1);counts(2,2);tick()
assert(last(events,'missed')and last(events,'missed').entity==7011 and#W.runtime.writes==writes,kinds(events))
-- A redirected beacon whose type comes back before activation: reported.
counts(0,0);tick()
W.write(STATE+0x8E4,string.char(0));W.write(STATE+0x8E8+0x8E4,string.char(0))
beacon(0,7012,30,2.0,0.0);counts(1,1);tick()
assert(last(events,'applied')and type_at(0)==136)
W.write(ELEMENTS+0xC,W.u32(30));tick()
assert(last(events,'reverted')and last(events,'reverted').value==30,kinds(events))
activate(0);tick()
assert(last(events,'activated').type==30 and last(events,'activated').redirected==false)
return 'ok'
''')


    def test_a_counting_beacon_is_still_redirected_and_the_crossing_is_the_limit(self):
        self.check(r'''
pworld()
local world=world_module.open()
-- The countdown has started (+0x3C set in the first update with state) and is still above the threshold: the
-- dispatcher has not run (it runs only at the crossing, with "activated" clear): redirected.
beacon(0,7020,30,3.377,3.377);counts(1,1);counting(0)
local writes=#W.runtime.writes
local result,code,why=BR.redirect_now(world,SPEC,7020)
assert(result and type_at(0)==136 and#W.runtime.writes==writes+1,tostring(code)..' '..tostring(why))
-- One frame later the countdown is below the threshold: the crossing has passed, refused, nothing written.
BR.reset_for_tests()
beacon(0,7021,30,3.367,3.377);counts(1,1);counting(0)
writes=#W.runtime.writes
local again,code2=BR.redirect_now(world,SPEC,7021)
assert(not again and code2=='CROSSED'and#W.runtime.writes==writes and type_at(0)==30)
return 'ok'
''')

    def test_a_support_beacon_25_becomes_136_with_its_own_timing_and_the_dispatch_reported(self):
        self.check(r'''
pworld()
BOMB.set_clock(100000000)
local events=arm({carrier='AC-8 Autocannon',target='Orbital 120mm HE Barrage',observe=true})
tick()
assert(kinds(events)=='armed,ready',kinds(events))
local armed=events[1]
assert(armed.carrierType==25 and armed.targetType==136 and armed.carrierTiming.callIn==3 and armed.carrierTiming.linger==4
    and armed.carrierTiming.category==2 and armed.carrierTiming.follows and armed.targetTiming.callIn==5
    and armed.targetTiming.category==0 and armed.targetTiming.kind==5)
local writes=#W.runtime.writes
-- Thrown: in flight (no state yet), its timers as the game created them from the AC-8's row (call-in 3 s + 8.717 s).
beacon(0,7101,25,11.717,8.717);counts(1,0);marker(7101,25)
tick()
assert(kinds(events)=='armed,ready,created,applied',kinds(events))
local c=last(events,'created')
assert(c.countdown>11.7 and c.threshold>8.7 and c.mode==nil and c.marker==25 and c.timing.callIn==3,kinds(events))
assert(type_at(0)==136 and#W.runtime.writes==writes+1 and W.read(ROW25,400)==ROW25_BYTES)
-- It lands (state), counts down; not yet activated.
counts(1,1);counting(0);set_countdown(0,10.0);BOMB.set_clock(101000000);tick()
assert(not last(events,'activated'))
-- The crossing, 2.37 s after it was first seen: the dispatcher records the 120mm's type and payload, a spawn request.
set_countdown(0,8.70);dispatched(0,136,BIG_PAYLOAD);BOMB.set_clock(102370000);tick()
local act=last(events,'activated')
assert(act and act.type==136 and act.redirected and act.n==1 and math.abs(act.seconds-2.37)<1e-6 and act.first_countdown>11.7
    and act.stateful==false,kinds(events))
assert(act.dispatch.type==136 and act.dispatch.payload==BIG_PAYLOAD and act.dispatch.requested and act.dispatch.waves==1
    and act.dispatch.called==1 and act.before.requested==false,act.dispatch.payload)
assert(act.marker==25 and act.carrierMarker==25)
-- The barrage's instance is readable; the beacon is removed 8.7 s after its activation.
BOMB.set_instances({BIG_PAYLOAD},1)
local bombs=BR.bombardment(world_module.open())
assert(bombs.total==1 and bombs.by[BIG_PAYLOAD]==1)
counts(0,0);BOMB.set_clock(111070000);tick()
local gone=last(events,'gone')
assert(gone.activated and gone.activations==1 and math.abs(gone.after-8.7)<1e-6 and math.abs(gone.seconds-11.07)<1e-6)
assert(W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES and#W.runtime.writes==writes+1)
return 'ok'
''')

    def test_observe_reports_every_other_beacon_read_only(self):
        self.check(r'''
pworld()
BOMB.set_clock(200000000)
local events=arm({carrier='AC-8 Autocannon',target='Orbital 120mm HE Barrage',observe=true})
tick()
local writes=#W.runtime.writes
-- A native 120mm (the control): observed, never written.
beacon(0,7201,136,26.972,21.972);counts(1,1);marker(7201,136)
tick()
local o=last(events,'observed')
assert(o and o.phase=='created'and o.type==136 and o.timing.callIn==5 and o.marker==136,kinds(events))
set_countdown(0,21.9);dispatched(0,136,BIG_PAYLOAD);BOMB.set_clock(205000000);tick()
o=last(events,'observed')
assert(o.phase=='activated'and o.type==136 and o.dispatch.requested and math.abs(o.seconds-5)<1e-6,kinds(events))
counts(0,0);BOMB.set_clock(227000000);tick()
o=last(events,'observed')
assert(o.phase=='gone'and math.abs(o.after-22)<1e-6)
assert(#W.runtime.writes==writes and not last(events,'created')and not last(events,'applied'))
-- Without observe, other beacons stay silent.
BR.reset_for_tests()
for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local quiet=arm({carrier='AC-8 Autocannon',target='Orbital 120mm HE Barrage'})
tick()
beacon(0,7202,136,26.972,21.972);counts(1,1);tick()
assert(kinds(quiet)=='armed,ready',kinds(quiet))
return 'ok'
''')


    def test_type_and_timing_in_one_transaction(self):
        self.check(r'''
pworld()
local world=world_module.open()
-- An AC-8 beacon whose call-in is already spent (countdown = threshold = 8.715, as live): type 25 -> 136 and its timers
-- to a native 120mm's (26.196 / 22.196), one transaction, the same update.
beacon(0,7401,25,8.715,8.715);counts(1,1)
local before=element(0)
local writes=#W.runtime.writes
local SPEC25={carrierType=25,targetType=136,resident=true,timing={countdown=26.196,threshold=22.196}}
local result,code,why=BR.redirect_now(world,SPEC25,7401,before:sub(1,8))
assert(result,tostring(code)..' '..tostring(why))
for _,key in ipairs({'type','others','nonTarget','protection','countdown','threshold'})do assert(result.verify[key],key)end
local after=element(0)
assert(type_at(0)==136 and math.abs(b.value(after,0,'f32')-26.196)<1e-5 and math.abs(b.value(after,4,'f32')-22.196)<1e-5)
for i=1,0x40 do assert(after:byte(i)==before:byte(i)or i<=8 or(i>0xC and i<=0x10),'element byte '..(i-1)..' changed')end
assert(#W.runtime.writes>writes and W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES)
assert(math.abs(result.timing.from.countdown-8.715)<1e-5 and math.abs(result.timing.to.threshold-22.196)<1e-5)
assert(count('beacon redirect APPLIED: beacon 7401 (index 0): type 25 -> 136; countdown 8.715 -> 26.196, threshold 8.715 '
    ..'-> 22.196, timers read back true')==1)
-- Never twice: a second timing write is refused.
local again,code2=BR.redirect_now(world,SPEC25,7401,element(0):sub(1,8))
assert(not again and code2=='TIMING_ALREADY')
return 'ok'
''')

    def test_every_timing_guard_writes_nothing(self):
        self.check(r'''
pworld()
local function refused(code,timing,observed,prepare)
    BR.reset_for_tests()
    for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
    beacon(0,7402,25,8.715,8.715);counts(1,1)
    if prepare then prepare()end
    local before=element(0)
    local writes=#W.runtime.writes
    local result,got,why=BR.redirect_now(world_module.open(),{carrierType=25,targetType=136,resident=true,timing=timing},
        7402,observed==nil and before:sub(1,8)or observed)
    assert(not result and got==code,code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#W.runtime.writes==writes and element(0)==before,code..': written')
end
local GOOD={countdown=26.196,threshold=22.196}
refused('TIMING_INVALID',{countdown=26.196,threshold=0})                    -- no positive threshold
refused('TIMING_INVALID',{countdown=20,threshold=22.196})                   -- the crossing would never happen
refused('TIMING_INVALID',{countdown=500,threshold=22.196})                  -- implausibly long
refused('TIMING_INVALID',{countdown=0/0,threshold=22.196})                  -- not a number
refused('TIMING_UNEXPECTED',GOOD,false)                                     -- the first-seen timers unknown
refused('TIMING_UNEXPECTED',GOOD,b.encode(8.0,'f32')..b.encode(8.715,'f32'))  -- not the values first seen
refused('NOT_THE_CARRIER',GOOD,nil,function()W.write(ELEMENTS+0xC,W.u32(118))end)
refused('ACTIVATED',GOOD,nil,function()activate(0)end)
-- The 120mm's package not resident: refused before anything else is read.
BR.reset_for_tests()
beacon(0,7403,25,8.715,8.715);counts(1,1)
local before,writes=element(0),#W.runtime.writes
local result,got=BR.redirect_now(world_module.open(),{carrierType=25,targetType=136,resident=false,timing=GOOD},7403,
    before:sub(1,8))
assert(not result and got=='TARGET_NOT_RESIDENT'and#W.runtime.writes==writes and element(0)==before)
return 'ok'
''')

    def test_the_watch_writes_timing_only_with_a_target_and_tracks_the_barrage(self):
        self.check(r'''
pworld()
BOMB.set_clock(300000000)
-- No target timing yet: the AC-8 beacon is refused whole, nothing written.
local target=nil
local events=arm({carrier='AC-8 Autocannon',target='Orbital 120mm HE Barrage',observe=true,
    timing=function()if target then return target end;return nil,'no native control yet'end})
tick()
local writes=#W.runtime.writes
beacon(0,7501,25,8.715,8.715);counts(1,1);tick()
local r=last(events,'refused')
assert(r and r.code=='NO_TARGET_TIMING'and r.reason=='no native control yet'and#W.runtime.writes==writes and type_at(0)==25,
    kinds(events))
-- With a target: the next AC-8 beacon gets the type and the timers in its first update.
counts(0,0);tick()
target={countdown=26.196,threshold=22.196,source='native control 7000'}
beacon(0,7502,25,8.715,8.715);counts(1,1);tick()
local a=last(events,'applied')
assert(a and a.entity==7502 and a.timing.source=='native control 7000'and type_at(0)==136
    and math.abs(b.value(element(0),4,'f32')-22.196)<1e-5,kinds(events))
-- It activates 4 s later (its new timers); the dispatcher's barrage instance appears in the same update.
set_countdown(0,22.19);dispatched(0,136,BIG_PAYLOAD);BOMB.set_instances({BIG_PAYLOAD},1);set_barrage(0,0,0,5,3.2)
BOMB.set_clock(304000000);tick()
local act=last(events,'activated')
assert(act.entity==7502 and act.type==136 and act.clock==304000000)
local made=last(events,'bombardment')
assert(made and made.phase=='created'and made.entity==4243 and made.payload==BIG_PAYLOAD and made.beacons[1]==7502
    and math.abs(made.startDelay-3.2)<1e-6 and made.salvos==5,kinds(events))
-- Its first shell 3.2 s later, its last at 19 s, then it is removed.
set_barrage(0,1,2,4);BOMB.set_clock(307200000);tick()
local fired=last(events,'bombardment')
assert(fired.phase=='fired'and fired.entity==4243 and math.abs(fired.after-3.2)<1e-6)
set_barrage(0,15,0,0);BOMB.set_clock(323000000);tick()
BOMB.set_instances({},0);BOMB.set_clock(328000000);tick()
local ended=last(events,'bombardment')
assert(ended.phase=='ended'and ended.shells==15 and math.abs(ended.life-24)<1e-6 and math.abs(ended.first-3.2)<1e-6
    and math.abs(ended.last-19)<1e-6,kinds(events))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
