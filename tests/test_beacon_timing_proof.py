"""proof/BeaconTimingProof 0.1.0 (runtime/beacons.lua): the proof's own addon on the offline payload world with a beacon
manager. Default: an AC-8 Autocannon beacon gets a 6 s call-in in its first update and a 15 s lifetime after activation
2 s later (the remaining call-in kept); after its activation one more change is refused (ACTIVATED) with nothing
written; the TIMING RESULT line reports the measured activation and lifetime. Option: the 120mm delivery with a
native 120mm's timing in one transaction, and the barrage's counters read at its creation. No StratagemInfo row is
written."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

FOLDER = ROOT / 'proof/BeaconTimingProof'

HARNESS = r"""
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
local function options_on(names)
    local options=require('hd2runtime/api/options')
    options.reset()
    rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,
        get=function(id)for _,name in ipairs(names)do if tostring(id):find(name,1,true)then return true end end end,
        on_change=function()return true end,ready=function()return true end})
end
require('hd2runtime/runtime/beacons').reset_for_tests()
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class BeaconTimingProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_beacon_timing_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + HARNESS + body), b'ok')

    def test_the_sources(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write('):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertIn("local BUILD='0.1.0 BEACON TIMING API'", body)

    def test_call_in_then_lifetime_then_the_guard(self):
        self.lua(r'''
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('BeaconTimingProof 0.1.0 BEACON TIMING API BUILD')==1 and count('mode TIMING (call-in 6')==1
    and count('BEACON TIMING READY:')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
-- Landed AC-8 beacon as created: call-in 3 s, threshold 8.717.
beacon(0,7101,25,11.717,8.717);counts(1,1);tick()
assert(count('BEACON TIMING APPLIED (first update): entity 7101; call-in 3.000 s, lifetime after activation 8.717 s '
    ..'(countdown 11.717, activation threshold 8.717) -> call-in 6.000 s, lifetime after activation 8.717 s (countdown '
    ..'14.717, activation threshold 8.717); verified true')==1,lines('APPLIED'))
assert(#W.runtime.writes==writes+1)
-- 2 s later (the countdown ran 2 s): the lifetime 15 s, the remaining call-in (4 s) kept.
set_countdown(0,12.717);tick(22)
assert(count('BEACON TIMING APPLIED (2.')==1 and count('-> call-in 4.000 s, lifetime after activation 15.000 s (countdown '
    ..'19.000, activation threshold 15.000); verified true')==1,lines('APPLIED'))
assert(#W.runtime.writes==writes+3)
-- The activation 6 s after first seen: one more change is refused, nothing written.
set_countdown(0,14.99);activate(0);BOMB.set_clock(106000000);tick()
assert(count('BEACON TIMING ACTIVATED: entity 7101, delivery AC-8 Autocannon, 6.000 s after first seen')==1
    and count('BEACON TIMING GUARD: a change after the activation: refused ACTIVATED')==1,lines('7101'))
assert(#W.runtime.writes==writes+3)
counts(0,0);BOMB.set_clock(121000000);tick()
assert(count('TIMING RESULT: entity 7101: activation 6.000 s after first seen (set call-in 6.000 s); the beacon remained '
    ..'15.000 s after its activation (set lifetime 15.000 s)')==1,lines('TIMING RESULT'))
assert(W.read(ROW25,400)==ROW25_BYTES and count('callback failed')==0)
return 'ok'
''')

    def test_the_120mm_with_a_native_120mm_timing(self):
        self.lua(r'''
options_on({'delivery_120mm'})
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('mode 120MM (delivery Orbital 120mm HE Barrage, call-in 4 s, lifetime 22.4 s)')==1
    and count('BEACON TIMING READY:')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
beacon(0,7201,25,8.715,8.715);counts(1,1);tick()
assert(count('BEACON TIMING APPLIED (first update): entity 7201, delivery AC-8 Autocannon -> Orbital 120mm HE Barrage; '
    ..'call-in 0.000 s')==1 and count('-> call-in 4.000 s, lifetime after activation 22.400 s (countdown 26.400, activation '
    ..'threshold 22.400); verified true')==1 and count('protection restored true), 3 writes')==1,lines('APPLIED'))
assert(type_at(0)==136 and#W.runtime.writes==writes+3)
-- The barrage: its counters as read at creation, then its removal.
set_countdown(0,22.39);dispatched(0,136,BIG_PAYLOAD);BOMB.set_instances({BIG_PAYLOAD},1);set_barrage(0,0,0,5,2.0)
BOMB.set_clock(104000000);tick()
assert(count('BARRAGE: instance 4243 (0x2D3BD00B1ED411B1) created: start delay 2.000 s, counters at creation: shells fired '
    ..'0, shells left 0, salvos left 5')==1,lines('BARRAGE'))
set_barrage(0,1,2,4);tick(5);set_barrage(0,15,0,0);tick(5)
BOMB.set_instances({},0);tick()
assert(count('BARRAGE: instance 4243 removed')==1 and count('shells fired 15 (counter 0 -> 15)')==1,lines('BARRAGE'))
assert(W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
