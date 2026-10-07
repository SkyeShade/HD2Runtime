"""The thrown stratagem balls and their throwers (runtime/call_ins.lua; research/peer-messaging-F5FEE03DCFDB.json
"callIn"; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md section 11), on the offline event world with a call-in
component laid out as the research found it: a beacon's network id finds the one ball naming it; its thrower is that
ball's owner peer, checked against the thrower's record (its entry holds the ball's type, or the token on a synced custom
slot whose carrier the ball holds); a ball in hand, no ball, two balls or a mismatch are never guessed; changed code
refuses; the research and its domain."""
import json
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE

RESEARCH = json.loads((ROOT / 'research/peer-messaging-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

HARNESS = PRELUDE + r"""
local call_ins=require('hd2runtime/runtime/call_ins');call_ins.reset_for_tests()
local CI=require('hd2runtime/domains/peer_messaging').callIn
for _,pin in ipairs(CI.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local COMP=W.alloc(0x100)
local STATES=W.alloc(16*CI.stride)
W.write(W.GAME+CI.global,W.u64(COMP))
W.write(COMP+CI.states,W.u64(STATES))
local function peer8(hex)return b.unhex(hex):reverse()end
-- balls: {{type, owner (hex or nil), entry, beacon}}
local function balls(list)
    W.write(COMP+CI.total,W.u32(#list))
    for i,x in ipairs(list)do
        local at=STATES+(i-1)*CI.stride
        W.write(at,string.rep('\0',CI.stride))
        W.write(at+CI.type,W.u32(x.type or 0))
        if x.owner then W.write(at+CI.owner,peer8(x.owner))end
        W.write(at+CI.entry,W.u32((x.entry or 0)%4294967296))
        W.write(at+CI.beaconNetwork,W.u32(x.beacon or CI.noNetwork))
    end
end
local function world()return assert(world_module.open())end
-- Each player's record as the game holds it: granted defaults first, then the loadout (index order).
local RECORDS={
    {peer=LOCAL,entries={{index=0,type=124,granted=1},{index=1,type=22,granted=0},{index=2,type=9,granted=0}}},
    {peer=OTHER,entries={{index=0,type=124,granted=1},{index=1,type=41,granted=0},{index=2,type=118,granted=0},
        {index=3,type=118,granted=0}}}}
"""


class CallInTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_the_research_and_its_domain(self):
        ci = RESEARCH['callIn']
        self.assertEqual((ci['global'], ci['total'], ci['states'], ci['stride']), ('0x3326D98', 0x18, 0x60, 0x28))
        self.assertEqual((ci['type'], ci['owner'], ci['entry'], ci['beaconNetwork']), (0x8, 0x10, 0x18, 0x1C))
        rvas = {p['rva'] for p in ci['pins']}
        for rva in (0x6A3635, 0x6A3416, 0x6A4886, 0x6A489C, 0x13634FF, 0x66D286, 0x1866A1B):
            self.assertIn(rva, rvas)
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        for snap in RESEARCH['snapshots']:
            self.assertEqual(snap['callIn']['thrown'], [])           # no ball in flight in a retained snapshot
            self.assertEqual(snap['hostPeer'], snap['localPeer'])     # the solo host is its own session host

    def test_a_beacon_maps_to_its_throwers_ball_and_record(self):
        self.lua(r"""
-- In hand (entry -1), no owner, this machine's own landed ball, the other player's ball on the converted custom slot.
balls({{type=9,owner=OTHER,entry=-1},{type=9,owner=nil,entry=2,beacon=0x200},{type=9,owner=LOCAL,entry=2,beacon=0x123},
    {type=9,owner=OTHER,entry=3,beacon=0x124}})
local list=assert(call_ins.balls(world()))
assert(#list==2 and list[1].owner==LOCAL and list[2].owner==OTHER,'only thrown balls with an owner')
local t=assert(call_ins.thrower(world(),0x123,RECORDS))
assert(t.peer==LOCAL and t.entry==2 and t.slot==1 and t.type==9)
-- The other player's ball: its record here still holds the token (its conversion is not sent).
local r,why=call_ins.thrower(world(),0x124,RECORDS)
assert(not r and why:find('holds type 118, the ball type 9',1,true),tostring(why))
local function accept(peer,slot,entry_type,ball_type)return peer==OTHER and slot==2 and entry_type==118 and ball_type==9 end
t=assert(call_ins.thrower(world(),0x124,RECORDS,accept))
assert(t.peer==OTHER and t.entry==3 and t.slot==2)
-- Never a guess: no ball, two balls, an owner without a record.
r,why=call_ins.thrower(world(),0x999,RECORDS)
assert(not r and why=='no thrown ball names that beacon (yet)')
balls({{type=9,owner=OTHER,entry=3,beacon=0x124},{type=9,owner=LOCAL,entry=2,beacon=0x124}})
r,why=call_ins.thrower(world(),0x124,RECORDS,accept)
assert(not r and why=='two balls name that beacon')
balls({{type=9,owner='9999999999999999',entry=1,beacon=0x125}})
r,why=call_ins.thrower(world(),0x125,RECORDS)
assert(not r and why:find('has no stratagem record here',1,true))
assert(not call_ins.thrower(world(),nil,RECORDS)and not call_ins.thrower(world(),CI.noNetwork,RECORDS))
""")

    def test_changed_code_refuses_and_nothing_is_written(self):
        self.lua(r"""
balls({{type=9,owner=LOCAL,entry=2,beacon=0x123}})
local writes=W.runtime.writes and#W.runtime.writes or 0
local pin=CI.pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC))
call_ins.reset_for_tests()
local r,why=call_ins.balls(world())
assert(not r and why:find('changed',1,true),tostring(why))
assert((W.runtime.writes and#W.runtime.writes or 0)==writes)
""")


if __name__ == '__main__':
    unittest.main()
