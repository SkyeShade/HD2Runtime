"""proof/BeaconRedirectProof 0.3.0 (research/docs/beacon-redirect-F5FEE03DCFDB.md): the proof's own addon on the offline
payload world with a beacon manager, a marker component and barrage instances. Type-only mode (default): an AC-8
Autocannon beacon (25) is redirected to 136 in its first update; a native 120mm thrown first is observed read-only as
the control; each beacon's barrage instance is attributed to it (created in its activation's update) and its start
delay, first and last shell, shells fired and removal are reported in a LIFECYCLE line. Timing mode: without a control
the AC-8 beacon is refused whole; with one, the type and the beacon's countdown and threshold (the control's) are
written in one transaction. Neutral writes 0. No StratagemInfo or payload record is written."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

FOLDER = ROOT / 'proof/BeaconRedirectProof'

PROOF_HARNESS = r"""
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
-- Mod Options Menu: the named options on.
local function options_on(names)
    local options=require('hd2runtime/api/options')
    options.reset()
    rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,
        get=function(id)for _,name in ipairs(names)do if tostring(id):find(name,1,true)then return true end end end,
        on_change=function()return true end,ready=function()return true end})
end
-- A native 120mm control beacon (index 0): created, activated 4 s later with its barrage (instance entity 4243), the
-- barrage's first shell 3.2 s after, 15 shells, removed 24 s after; the beacon gone 22.2 s after its activation.
local function native_control(clock)
    beacon(0,7201,136,26.196,22.196);counts(1,1);marker(7201,136);BOMB.set_clock(clock);tick()
    set_countdown(0,22.19);dispatched(0,136,BIG_PAYLOAD);BOMB.set_instances({BIG_PAYLOAD},1);set_barrage(0,0,0,5,3.2)
    BOMB.set_clock(clock+4000000);tick()
    set_barrage(0,1,2,4);BOMB.set_clock(clock+7200000);tick()
    set_barrage(0,15,0,0);BOMB.set_clock(clock+23000000);tick()
    counts(0,0);BOMB.set_clock(clock+26200000);tick()
    BOMB.set_instances({},0);BOMB.set_clock(clock+28000000);tick()
end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class BeaconRedirectProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_beacon_redirect_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + PROOF_HARNESS + body), b'ok')

    def test_the_sources(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write('):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.3.0')
        self.assertIn("local BUILD='0.3.0 BEACON TIMING'", body)
        self.assertNotIn('SUPPORT BEACON REDIRECT', body)

    def test_type_only_the_control_and_the_ac8_lifecycles(self):
        self.lua(r'''
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('BeaconRedirectProof 0.3.0 BEACON TIMING BUILD')==1 and count('mode TYPE ONLY')==2
    and count('BEACON REDIRECT READY:')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
-- The native 120mm control: observed, never written; its barrage's lifecycle.
native_control(110000000)
assert(count('BEACON TIMING CONTROL: native Orbital 120mm HE Barrage beacon 7201: countdown 26.196 s, threshold 22.196 s '
    ..'(call-in 4.000 s)')==1,lines('CONTROL'))
assert(count('BOMBARDMENT: instance 4243 (0x2D3BD00B1ED411B1 (Orbital 120mm HE Barrage payload 1)) created in the update '
    ..'beacon 7201 activated: start delay 3.20 s, 5 salvos')==1 and count('FIRST SHELL 3.20 s after it was created')==1,
    lines('BOMBARDMENT'))
assert(count('LIFECYCLE: native Orbital 120mm HE Barrage (136), beacon 7201: countdown 26.196 s, threshold 22.196 s as '
    ..'first seen; activation 4.000 s after first seen; beacon life after the activation 22.200 s; barrage instance 4243 '
    ..'(0x2D3BD00B1ED411B1 (Orbital 120mm HE Barrage payload 1)): created 0.00 s, start delay 3.20 s, first shell 3.20 s, '
    ..'last shell 19.00 s, 15 shells fired, removed 24.00 s')==1,lines('LIFECYCLE'))
assert(#W.runtime.writes==writes)
-- The AC-8: type 25 -> 136 only; its timers stay the AC-8's (8.715); the barrage is attributed to it.
beacon(0,7101,25,8.715,8.715);counts(1,1);marker(7101,25);BOMB.set_clock(140000000);tick()
assert(count('BEACON REDIRECT APPLIED: entity = 7101, type 25 -> 136, verified = true')==1 and count('BEACON REDIRECT TIMING:')==0
    and#W.runtime.writes==writes+1 and type_at(0)==136,lines('7101'))
set_countdown(0,8.70);dispatched(0,136,BIG_PAYLOAD);BOMB.set_instances({BIG_PAYLOAD},1);set_barrage(0,0,0,5,3.2)
BOMB.set_clock(140010000);tick()
assert(count('BEACON REDIRECT ACTIVATED: entity = 7101, activation type = Orbital 120mm HE Barrage (136)')==1
    and count('created in the update beacon 7101 activated')==1,lines('7101'))
set_barrage(0,1,2,4);BOMB.set_clock(143210000);tick()
counts(0,0);BOMB.set_clock(148710000);tick()
set_barrage(0,15,0,0);BOMB.set_clock(159010000);tick()
BOMB.set_instances({},0);BOMB.set_clock(164010000);tick()
assert(count('LIFECYCLE: AC-8 Autocannon -> Orbital 120mm HE Barrage, beacon 7101: countdown 8.715 s, threshold 8.715 s '
    ..'as first seen; activation 0.010 s after first seen; beacon life after the activation 8.700 s; barrage instance 4243')==1
    and count('first shell 3.20 s, last shell 19.00 s, 15 shells fired, removed 24.00 s')==2,lines('LIFECYCLE'))
assert(W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES and#W.runtime.writes==writes+1)
assert(count('REFUSED')==0 and count('callback failed')==0)
return 'ok'
''')

    def test_timing_mode_needs_the_control_then_writes_the_type_and_the_timers(self):
        self.lua(r'''
options_on({'timing'})
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('mode TIMING')==2,table.concat(logged,' | '))
local writes=#W.runtime.writes
-- No control yet: the AC-8 beacon is refused whole, nothing written.
beacon(0,7101,25,8.715,8.715);counts(1,1);tick()
assert(count('BEACON REDIRECT REFUSED for entity 7101 (nothing written; the beacon goes on natively): NO_TARGET_TIMING: '
    ..'no native Orbital 120mm HE Barrage beacon was observed in this mission yet')==1 and#W.runtime.writes==writes
    and type_at(0)==25,lines('REFUSED'))
counts(0,0);tick()
-- The control, then an AC-8: type and timers in one transaction, in its first update.
native_control(110000000)
assert(count('the target timing for the next AC-8 beacon')==1,lines('CONTROL'))
writes=#W.runtime.writes
beacon(0,7102,25,8.715,8.715);counts(1,1);BOMB.set_clock(140000000);tick()
assert(count('BEACON REDIRECT APPLIED: entity = 7102, type 25 -> 136, verified = true')==1,lines('7102'))
assert(count('BEACON REDIRECT TIMING: entity = 7102, countdown 8.715 -> 26.196, threshold 8.715 -> 22.196 (call-in 0.000 -> '
    ..'4.000 s), read back true; the target: the native Orbital 120mm HE Barrage beacon 7201')==1,lines('TIMING'))
local e=element(0)
assert(type_at(0)==136 and math.abs(b.value(e,0,'f32')-26.196)<1e-5 and math.abs(b.value(e,4,'f32')-22.196)<1e-5)
assert(#W.runtime.writes>writes and W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES)
return 'ok'
''')

    def test_neutral_writes_0_and_the_record_stays_empty(self):
        self.lua(r'''
options_on({'neutral'})
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('BEACON REDIRECT ARMED: carrier AC-8 Autocannon (type 25), target type 0 (neutral: the empty default row); '
    ..'mode NEUTRAL (type 0)')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
beacon(0,7301,25,11.717,8.717);counts(1,1);marker(7301,25)
tick()
assert(count('BEACON REDIRECT APPLIED: entity = 7301, type 25 -> 0, verified = true')==1 and type_at(0)==0,
    table.concat(logged,' | '))
set_countdown(0,8.7);activate(0);BOMB.set_clock(103000000);tick()
assert(count('BEACON REDIRECT ACTIVATED: entity = 7301, activation type = type 0 (the empty default row), original type = '
    ..'AC-8 Autocannon, redirected = true')==1,lines('ACTIVATED'))
assert(count('spawn requested = no')==1 and count('UNCHANGED at this activation')==1,lines('DISPATCH'))
assert(#W.runtime.writes==writes+1 and W.read(ROW25,400)==ROW25_BYTES)
return 'ok'
''')

    def test_an_ac8_payload_entity_is_reported(self):
        self.lua(r'''
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
beacon(0,7101,25,11.717,8.717);counts(1,1)
tick()
dispatched(0,136,BIG_PAYLOAD);set_countdown(0,8.7);tick()
W.add{entity=901,type='73F8498BFFDCF415',unit=7901,health=500}
tick(3)
assert(count('OBSERVED: a new entity 901 of type 0x73F8498BFFDCF415 (AC-8 Autocannon payload 2')==1
    and count('the AC-8 Autocannon delivery still ran')==1,lines('OBSERVED'))
return 'ok'
''')

    def test_a_beacon_before_the_target_package_is_resident_is_refused(self):
        self.lua(r'''
pworld()
local assets=require('hd2runtime/core/assets')
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local PACKAGE=assets.dependency_for_stratagem(BIG_ID,'x').package
W.runtime.packages[PACKAGE]='absent'
local requested=0
W.runtime.package_request=function()requested=requested+1 end
proof()
tick(64)
local writes=#W.runtime.writes
beacon(0,7101,25,11.717,8.717);counts(1,0)
tick()
assert(count('BEACON REDIRECT REFUSED for entity 7101 (nothing written; the beacon goes on natively): '
    ..'TARGET_NOT_RESIDENT')==1 and#W.runtime.writes==writes and type_at(0)==25,table.concat(logged,' | '))
assert(requested==1)
W.runtime.packages[PACKAGE]=nil
tick(40)
assert(count('BEACON REDIRECT READY:')==1,table.concat(logged,' | '))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
