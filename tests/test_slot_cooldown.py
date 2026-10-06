"""A converted slot's fixed cooldown (runtime/slot_cooldown.lua, docs/custom-stratagems.md "The fixed cooldown";
research/slot-cooldown-F5FEE03DCFDB.json): when the game starts the converted carrier entry's cooldown, the same frame
replaces its end with a fixed time counted from the call-in's arrival (or from that frame), through one guarded 8-byte
transaction, and nothing else of the record or the carrier's row changes. Offline: the payload world (the 380mm carrier
converted from the virtual Gas Barrage slot), its game clock and the HUD list."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

RESEARCH = json.loads((ROOT / 'research/slot-cooldown-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

COOL = r"""
local cool=require('hd2runtime/runtime/slot_cooldown')
local CD=require('hd2runtime/domains/slot_cooldown')
cool.reset_for_tests()
local US=1000000
local INDEX=2                        -- loadout slot 0 = record entry 2 (two granted defaults first)
local function entry_at(h)return h.record+0x38+0x188+INDEX*0x30 end
local function u64_at(at)local s=W.read(at,8);return b.u32(s,0)+b.u32(s,4)*4294967296 end
local function put64(at,n)W.write(at,W.u32(n%4294967296)..W.u32(math.floor(n/4294967296)))end
local function record_bytes(h)return W.read(h.record+0x38+0x188,6*0x30)..W.read(h.record+0x38+0x788,4)end
-- The game's call, as the snapshots show it: an activation, an arrival `inbound` s later and an end the row's 240 s x
-- 0.855 after the arrival.
local function call(h,at,inbound,native)
    local arrival=at+math.floor((inbound or 6)*US)
    put64(entry_at(h)+0x10,at);put64(entry_at(h)+0x20,arrival)
    put64(entry_at(h)+0x18,arrival+math.floor((native or 205.2)*US))
    return arrival
end
local function arm(spec)
    local events={}
    local watch,why=cool.arm(spec or{definition='orbital_gas_barrage',seconds=60},function(e)events[#events+1]=e end)
    assert(watch,why)
    return events
end
local function kinds(events)local out={};for k,e in ipairs(events)do out[k]=e.kind end;return table.concat(out,',')end
local function last(events,kind)for k=#events,1,-1 do if events[k].kind==kind then return events[k]end end end
-- The HUD's bar for entry 2 in its first cooling frame, as the game's update leaves it.
local function hud_cooling(h,total,left)
    local slot=h.slots and h.slots[INDEX]and h.slots[INDEX].address
    local bar=slot+CD.hud.bar
    W.write(bar+CD.hud.barIndex,W.u32(INDEX));W.write(bar+CD.hud.barState,W.u32(CD.hud.cooling))
    W.write(bar+CD.hud.barTotal,b.encode(total,'f32'));W.write(slot+CD.hud.coolingLeft,b.encode(left or total,'f32'))
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + COOL + body)


class SlotCooldownResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(RESEARCH['clock'], {'global': '0x3326348', 'time': 0x18, 'perSecond': 1000000})
        self.assertEqual(RESEARCH['entry'], {'activation': 0x10, 'cooldownEnd': 0x18, 'arrival': 0x20})
        self.assertEqual(RESEARCH['row'], {'cooldown': 0x68, 'cooldownType': 0x94})
        ems = next(c for c in RESEARCH['calls'] if c['name'] == 'Orbital EMS Strike')
        self.assertEqual((ems['rowCooldown'], ems['afterArrivalSeconds'], ems['modifier']), (75.0, 64.125, 0.855))
        rearm = next(x for x in RESEARCH['bars'] if x['type'] == 49)
        self.assertAlmostEqual(rearm['barTotal'], 102.6, places=4)        # the first cooling frame's time left
        for snap in RESEARCH['snapshots']:
            self.assertEqual(snap['records'], 1)
            self.assertTrue(snap['sharedEndBelowClock'])                     # a fresh record's ends: all available
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        self.assertIn(0x66D25C, roles)                                       # end above the clock: unavailable
        self.assertIn(0x183A99C, roles)                                      # the bar takes its first time left
        self.assertIn(0x11E86AD, roles)                                      # peers get the remaining cooldown
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_slot_cooldown
        self.assertEqual(generate_slot_cooldown.generate(check=True), [])


class SlotCooldownTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_call_gets_sixty_seconds_from_its_arrival_and_nothing_else_changes(self):
        self.check(r'''
local h=converted()
local events=arm()
tick()
assert(kinds(events)=='armed',kinds(events))
local a=events[1]
assert(a.carrier=='Orbital 380mm HE Barrage'and a.type==125 and a.rowCooldown==240 and a.cooldownType==0
    and a.indices[1]==INDEX and a.slots[INDEX]==0 and a.from=='arrival'and a.seconds==60)
-- Nothing is written while the entry is not called.
local writes=#W.runtime.writes
tick();tick()
assert(#W.runtime.writes==writes and#events==1)
-- The game's call: activated 0.3 s ago, arriving 6 s later, its end 205.2 s after the arrival.
local before=record_bytes(h)
local arrival=call(h,CLOCK-300000,6,205.2)
local row_before=W.read(ROW[125],400)
tick()
local o=last(events,'overridden')
assert(o,kinds(events))
assert(o.index==INDEX and o.slot==0 and o.carrier=='Orbital 380mm HE Barrage'and o.rowCooldown==240)
assert(o.activation==CLOCK-300000 and o.arrival==arrival and o.gameEnd==arrival+205200000 and o.clock==CLOCK)
assert(o.desired==arrival+60*US and o.base==arrival and o.from=='arrival'and o.writes==1)
for _,key in ipairs({'finish','others','nonTarget','protection'})do assert(o.verify[key],key)end
assert(#W.runtime.writes==writes+1 and W.runtime.writes[#W.runtime.writes].address==entry_at(h)+0x18)
assert(u64_at(entry_at(h)+0x18)==arrival+60*US)
-- Only the 8 end bytes of entry 2 changed; the carrier's row (its own 240 s cooldown) is never written.
local now=record_bytes(h)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=INDEX*0x30+0x10 and at<INDEX*0x30+0x28),'record byte '..at..' changed')
end
assert(W.read(ROW[125],400)==row_before)
assert(count('slot cooldown OVERRIDDEN: entry 2 (Orbital 380mm HE Barrage): end '..(arrival+205200000)..' -> '
    ..(arrival+60*US)..' (60 s from the arrival; the game\'s: 205.200 s after the arrival, row 240 s); 1 write; the '
    ..'entry reads it: true; nothing else changed: true; non-target bytes unchanged true; protection restored true')==1)
-- The HUD's first cooling frame: its bar's total.
BOMB.set_clock(arrival+500000)
hud_cooling(h,59.5,59.5)
tick()
local hd=last(events,'hud')
assert(hd and hd.total==59.5 and hd.overridden==true and hd.finish==arrival+60*US and hd.expected==59.5,kinds(events))
-- Available again exactly at the new end: 60 s after the arrival.
BOMB.set_clock(arrival+60*US-1);tick()
assert(not last(events,'ready'))
BOMB.set_clock(arrival+60*US);tick()
local r=last(events,'ready')
assert(r and r.clock==arrival+60*US and r.finish==arrival+60*US and r.overridden and r.arrival==arrival)
-- A second call is a new call: overridden again, one write.
local second=call(h,arrival+61*US,3,205.2)
BOMB.set_clock(arrival+61*US+100000);tick()
assert(kinds(events)=='armed,overridden,hud,ready,overridden'and#W.runtime.writes==writes+2,kinds(events))
assert(u64_at(entry_at(h)+0x18)==second+60*US)
return 'ok'
''')

    def test_uses_spend_the_slot_with_the_last_call(self):
        # spec.uses (calls per mission, 2026-10-06): every call counted from this machine's own entry; the one that uses
        # the last of them ends MAX_SECONDS after its arrival (longer than any mission), through the same guarded write.
        self.check(r'''
local h=converted()
local events=arm({definition='orbital_gas_barrage',seconds=60,uses=2})
tick()
local writes=#W.runtime.writes
local arrival=call(h,CLOCK-300000,6,205.2)
tick()
local o=last(events,'overridden')
assert(o and o.calls==1 and o.uses==2 and o.depleted==false and o.desired==arrival+60*US,kinds(events))
BOMB.set_clock(arrival+60*US);tick()
assert(last(events,'ready'))
local second=call(h,arrival+61*US,3,205.2)
BOMB.set_clock(arrival+61*US+100000);tick()
o=last(events,'overridden')
assert(o.calls==2 and o.depleted==true and o.seconds==cool.MAX_SECONDS and o.desired==second+cool.MAX_SECONDS*US,
    tostring(o.desired))
assert(u64_at(entry_at(h)+0x18)==second+cool.MAX_SECONDS*US and#W.runtime.writes==writes+2)
assert(count('('..cool.MAX_SECONDS..' s from the arrival;')==1,table.concat(logged,' | '))
-- Spent: not available again within the mission.
BOMB.set_clock(second+(cool.MAX_SECONDS-1)*US);tick()
assert(kinds(events)=='armed,overridden,ready,overridden',kinds(events))
return 'ok'
''')

    def test_uses_without_seconds_keep_the_games_cooldown_until_the_last_call(self):
        self.check(r'''
local h=converted()
local events=arm({definition='orbital_gas_barrage',uses=2})
tick()
local writes=#W.runtime.writes
local arrival=call(h,CLOCK-300000,6,205.2)
tick()
local c=last(events,'call')
assert(c and c.calls==1 and c.uses==2 and not c.depleted and#W.runtime.writes==writes,kinds(events))
assert(u64_at(entry_at(h)+0x18)==arrival+205200000,'the game\'s own end')
BOMB.set_clock(arrival+205200000);tick()
local second=call(h,arrival+206*US,3,205.2)
BOMB.set_clock(arrival+206*US+100000);tick()
local o=last(events,'overridden')
assert(o and o.calls==2 and o.depleted and o.desired==second+cool.MAX_SECONDS*US and#W.runtime.writes==writes+1)
-- The spec: uses 1..MAX_USES (whole), seconds required without uses.
for _,bad in ipairs({{definition='x',uses=0},{definition='x',uses=1.5},{definition='x',uses=cool.MAX_USES+1},
        {definition='x'}})do
    local w,why=cool.arm(bad,function()end)
    assert(w==nil and why,tostring(bad.uses))
end
return 'ok'
''')

    def test_from_now_counts_the_seconds_from_the_frame_that_saw_the_call(self):
        self.check(r'''
local h=converted()
local events=arm({definition='orbital_gas_barrage',seconds=60,from='now'})
tick()
local arrival=call(h,CLOCK-300000,3,205.2)
tick()
local o=last(events,'overridden')
assert(o and o.from=='now'and o.base==CLOCK and o.desired==CLOCK+60*US,kinds(events))
assert(u64_at(entry_at(h)+0x18)==CLOCK+60*US and arrival<CLOCK+60*US)
return 'ok'
''')

    def test_a_call_seen_before_the_watch_saw_the_conversion_is_still_overridden(self):
        self.check(r'''
local h=converted()
local arrival=call(h,CLOCK-300000,6,205.2)
local events=arm()
tick()
assert(kinds(events)=='armed,overridden',kinds(events))
assert(u64_at(entry_at(h)+0x18)==arrival+60*US)
return 'ok'
''')

    def test_a_call_written_in_steps_is_overridden_once_its_cooldown_start_is_complete(self):
        self.check(r'''
local h=converted()
local events=arm()
tick()
local writes=#W.runtime.writes
-- Step 1: an end above the clock without an activation: reported, nothing written, still watching.
put64(entry_at(h)+0x18,CLOCK+100*US)
tick()
local c=last(events,'changed')
assert(c and c.reason=='the end changed without a new activation'and#W.runtime.writes==writes,kinds(events))
-- Step 2: the activation, but no arrival yet: reported again, nothing written.
put64(entry_at(h)+0x10,CLOCK-300000);put64(entry_at(h)+0x18,CLOCK+101*US)
tick()
assert(kinds(events)=='armed,changed,changed'and last(events,'changed').reason:find('not a cooldown after the arrival',
    1,true)and#W.runtime.writes==writes,kinds(events))
-- Step 3: the arrival and the end after it: the cooldown start, overridden once.
local arrival=call(h,CLOCK-300000,6,205.2)
tick()
assert(kinds(events)=='armed,changed,changed,overridden'and u64_at(entry_at(h)+0x18)==arrival+60*US
    and#W.runtime.writes==writes+1,kinds(events))
-- The same activation's end written again is a rewrite, never a new call.
put64(entry_at(h)+0x18,arrival+205200000)
tick()
assert(kinds(events)=='armed,changed,changed,overridden,rewritten'and#W.runtime.writes==writes+1,kinds(events))
return 'ok'
''')

    def test_an_end_at_or_below_the_clock_is_not_a_cooldown(self):
        self.check(r'''
local h=converted()
local events=arm()
tick()
local writes=#W.runtime.writes
put64(entry_at(h)+0x10,CLOCK-1000);put64(entry_at(h)+0x20,CLOCK-1000);put64(entry_at(h)+0x18,CLOCK)
tick();tick()
assert(kinds(events)=='armed'and#W.runtime.writes==writes,kinds(events))
return 'ok'
''')

    def test_every_failed_guard_refuses_with_nothing_written(self):
        self.check(r'''
local function refused(code,prepare,text,spec)
    cool.reset_for_tests();slots.reset_for_tests()
    local h=converted()
    local events=arm(spec)
    tick()
    local writes=#W.runtime.writes
    local before=record_bytes(h)
    local undo=prepare(h)
    tick()
    local e=last(events,'refused')
    assert(e and e.code==code and(text==nil or tostring(e.reason):find(text,1,true)),
        code..' expected, got '..kinds(events)..' '..tostring(e and e.code)..': '..tostring(e and e.reason))
    assert(#W.runtime.writes==writes,code..': written')
    assert(not last(events,'overridden'),code)
    if undo then undo()end
    return h,events
end
-- A call activated 20 s ago (the watch missed it): never a late write.
refused('STALE',function(h)call(h,CLOCK-20*US,6,205.2)end,'20.0 s ago')
-- Not a cooldown after the arrival: more than twice the row's 240 s.
refused('NOT_A_COOLDOWN',function(h)call(h,CLOCK-300000,6,481)end,'more than twice')
-- A shared cooldown type (row +0x94): copied between records by the peer sync.
refused('SHARED_COOLDOWN',function(h)
    W.write(ROW[125]+0x94,W.u32(2));call(h,CLOCK-300000,6,205.2)
    return function()W.write(ROW[125]+0x94,W.u32(0))end
end)
-- Limited uses on the entry.
refused('USES_DIFFER',function(h)W.write(entry_at(h)+4,W.u32(3));call(h,CLOCK-300000,6,205.2)end)
-- A changed reader: the pins.
refused('UNSUPPORTED_BUILD',function(h)
    local pin=CD.pins[#CD.pins]
    W.write(W.GAME+pin.rva,string.char(0xCC));call(h,CLOCK-300000,6,205.2)
    return function()W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
end,'slot cooldown code changed')
-- Not the host.
refused('NOT_HOST',function(h)
    W.state(4,{host=false});call(h,CLOCK-300000,6,205.2)
end)
return 'ok'
''')

    def test_the_wrong_carrier_or_a_changed_entry_is_refused(self):
        self.check(r'''
local h=converted()
local events=arm({definition='orbital_gas_barrage',seconds=60,carrier='Orbital Walking Barrage'})
tick()
assert(kinds(events)=='armed,refused,ended'and events[2].code=='NOT_THE_CARRIER',kinds(events))
assert(not cool.armed())
-- The converted entry no longer holds the carrier when its cooldown starts (the type of entry 2 rewritten).
cool.reset_for_tests()
events=arm()
tick()
local writes=#W.runtime.writes
W.write(entry_at(h),W.u32(118))
call(h,CLOCK-300000,6,205.2)
tick()
assert(kinds(events)=='armed'and#W.runtime.writes==writes,kinds(events))   -- not the carrier: not watched
return 'ok'
''')

    def test_a_later_change_by_the_game_is_reported_never_fought(self):
        self.check(r'''
local h=converted()
local events=arm()
tick()
local arrival=call(h,CLOCK-300000,6,205.2)
tick()
local writes=#W.runtime.writes
put64(entry_at(h)+0x18,arrival+205200000)      -- the game writes its own end again
tick();tick()
local r=last(events,'rewritten')
assert(r and r.expected==arrival+60*US and r.value==arrival+205200000,kinds(events))
assert(#W.runtime.writes==writes and u64_at(entry_at(h)+0x18)==arrival+205200000)
assert(kinds(events)=='armed,overridden,rewritten')
return 'ok'
''')

    def test_the_watch_ends_with_the_conversion_and_waits_for_one(self):
        self.check(r'''
-- Armed before the conversion: waits.
local h=pworld()
local events=arm()
tick();tick()
assert(kinds(events)==''and cool.armed())
assert(settle_job(slots.convert_virtual(PSPEC)).status=='converted')
tick()
assert(kinds(events)=='armed')
-- The conversion returned to the token: the watch ends.
assert(settle_job(slots.restore()).status=='restored')
tick()
assert(kinds(events)=='armed,ended'and not cool.armed(),kinds(events))
-- Armed outside a mission: ends.
cool.reset_for_tests()
W.state(3)
events=arm()
tick()
assert(kinds(events)=='ended',kinds(events))
-- The spec.
assert(not cool.arm({definition='x',seconds=0})and not cool.arm({definition='x',seconds=60,from='later'})
    and not cool.arm({seconds=60})and not cool.arm({definition='x',seconds=7200}))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
