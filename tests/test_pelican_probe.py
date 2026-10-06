"""proof/PelicanProbe 0.1.0: the proof's own addon on the offline payload world with a beacon manager and the Pelican's
components (tests/test_pelicans.py). Aboard the ship it logs the read-only carrier allocation of the two custom
stratagems; in a mission it observes a vehicle Pelican from its beacon to its removal and holds it once released (one
guarded write of its own release time; Ctrl+F8 turns the hold off)."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS
from test_pelicans import PELICANS

FOLDER = ROOT / 'proof/PelicanProbe'
BODY = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')

HARNESS = r"""
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function ctrl(key)keys[0x11]=true;keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;keys[0x11]=false;tick()end
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
-- A beacon at (100, 200, 10) activating 0.05 s before clock t, and the vehicle Pelican it spawns, first seen at t.
local function call_in(t)
    beacon(0,7201,136,0.5,0.4);counts(1,1)
    W.write(STATE+0x30,b.encode(100,'f32')..b.encode(200,'f32')..b.encode(10,'f32'))
    BOMB.set_clock(t-50000);tick(2)
    activate(0);tick(2)
    transport(0,9001,{cargo=FRV,spawned=9100,network=55});stage(0,1,0);position(0,100,200,12);tcount(1)
    BOMB.set_clock(t);tick(2)
end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], BODY)


class PelicanProbeTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pelican_probe')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n' + HARNESS + body), b'ok')

    def test_the_sources(self):
        # The only write is the Runtime's guarded hold (runtime/pelicans.lua): no native call, no FFI, no direct write.
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'redirect_now', 'beacons.apply', 'pelicans.hold', 'carrier_presentation', 'convert_virtual'):
            self.assertNotIn(forbidden, BODY)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertIn("BUILD='0.1.0 PELICAN PROBE + HOLD'", BODY)

    def test_aboard_the_ship_the_allocation_is_logged_once_per_loadout(self):
        self.lua(r'''
W.state(3)
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=ID130}})
local writes=#W.runtime.writes
proof()
tick(8)
assert(n('CUSTOM CARRIER: Gas Barrage = Orbital 380mm HE Barrage (orbital, red beacon), Pelican CAS = Orbital Airburst '
    ..'Strike (orbital, red beacon); distinct = true (read-only; saved loadout: Orbital Precision Strike, ')==1,
    lines('CUSTOM CARRIER'))
-- (the allocator now counts every red carrier of the pool taken or reserved: the Gas Barrage's 380mm)
assert(n('CUSTOM CARRIER: Pelican CAS -> Orbital Airburst Strike (type 83, stable id 1560416221, class 1): the first of 2 '
    ..'eligible, 1 skipped as taken or reserved')==1,lines('CUSTOM CARRIER'))
tick(20)
assert(n('CUSTOM CARRIER: Gas Barrage =')==1)
-- The Airburst saved into the loadout: the Pelican CAS is refused, never given the Gas Barrage's carrier.
W.saved_loadout({{id=PRECISION_ID},{id=AIRBURST_ID},{id=ID130}});tick(4)
assert(n('Pelican CAS = REFUSED (no unused red (offensive) carrier: 1 red eligible, 1 taken or reserved by an earlier '
    ..'custom stratagem')==1,
    lines('CUSTOM CARRIER'))
assert(#W.runtime.writes==writes)
return 'ok'
''')

    def test_a_vehicle_pelican_is_observed_from_its_beacon_and_held_after_its_release(self):
        self.lua(r'''
pworld()
proof()
tick(4)
assert(n('pins: the Transport, Behavior and transform components and the flight\'s stage machine are the researched '
    ..'code')==1,table.concat(logged,' | '))
assert(n('PELICAN WATCH: running; hold 60 s after each release')==1)
local T=300000000
call_in(T)
assert(n('PELICAN SEEN: entity 9001 (network id 55), behaviour 667, stage 1; cargo M-102 Gunner FRV, ALREADY SPAWNED '
    ..'(entity 9100): no per-call cargo window; cargo timer 0.00; associated none; at (100.0, 200.0, 12.0); from the '
    ..'Orbital 120mm HE Barrage (136) beacon 7201 at (100.0, 200.0, 10.0) (activated 0.05 s before; 2.0 m away)')==1,
    lines('PELICAN'))
-- Its flight: to the hover point above the beacon, the hover, the release.
BOMB.set_clock(T+8000000);stage(0,3,0);target(0,100,200,25);position(0,300,400,150);tick(2)
assert(n('PELICAN STAGE: entity 9001: 1 -> 3 at 8.0 s; target (100.0, 200.0, 25.0); at (300.0, 400.0, 150.0) (target '
    ..'0.0 m from the beacon horizontally)')==1,lines('PELICAN STAGE'))
BOMB.set_clock(T+20000000);stage(0,6,0);stamp(0,'hoverStart',T+20000000);position(0,100,200,25);tick(2)
local writes=#W.runtime.writes
BOMB.set_clock(T+24000000);stage(0,6,1);stamp(0,'releaseTime',T+24000000);tick(2)
assert(n('PELICAN RELEASED: entity 9001 in stage 6, 24.0 s after it was first seen; hovered 4.0 s before its release; '
    ..'hover point (100.0, 200.0, 25.0), at (100.0, 200.0, 25.0); 0.0 m from the beacon horizontally, 15.0 m above it; '
    ..'native departure 0.6 s after the release')==1,lines('PELICAN RELEASED'))
assert(n('PELICAN HELD: entity 9001: departs 60.0 s after its release (native 0.6 s); verified true')==1,lines('HELD'))
assert(#W.runtime.writes==writes+1)
-- The game departs and removes it.
BOMB.set_clock(T+84000000);stage(0,8,1);tick(2)
assert(n('PELICAN DEPARTING: entity 9001: stage 8, 60.0 s after its release')==1,lines('DEPARTING'))
BOMB.set_clock(T+98000000);tcount(0);tick(2)
assert(n('PELICAN GONE: entity 9001: 98.0 s after it was first seen, 74.0 s after its release, 14.0 s after departing; '
    ..'held yes (60.0 s)')==1,lines('PELICAN GONE'))
assert(n('PELICAN SUMMARY: entity 9001: hover after the release 60.0 s (asked 60.0); fly-out and removal 14.0 s')==1,
    lines('SUMMARY'))
return 'ok'
''')

    def test_ctrl_f8_observes_only(self):
        self.lua(r'''
pworld()
proof()
tick(4)
ctrl('F8')
assert(n('Ctrl+F8 [0.1.0 PELICAN PROBE + HOLD]: hold OFF (observe only)')==1,table.concat(logged,' | '))
assert(n('PELICAN WATCH: running; hold OFF (observe only)')==1)
local T=300000000
call_in(T)
local writes=#W.runtime.writes
BOMB.set_clock(T+20000000);stage(0,6,1);stamp(0,'hoverStart',T+19000000);stamp(0,'releaseTime',T+20000000);tick(2)
assert(n('PELICAN RELEASED: entity 9001')==1 and n('PELICAN HELD: ')==0 and #W.runtime.writes==writes)
return 'ok'
''')


    def test_ctrl_f8_aboard_the_ship_applies_to_the_next_mission(self):
        self.lua(r'''
pworld()
proof()
tick(4)
assert(n('PELICAN WATCH: running; hold 60 s after each release')==1)
W.state(3);tick(4)                                                   -- back aboard the ship
ctrl('F8')
assert(n('Ctrl+F8 [0.1.0 PELICAN PROBE + HOLD]: hold OFF (observe only)')==1)
pworld();tick(4)                                                     -- the next mission
assert(n('PELICAN WATCH: running; hold OFF (observe only)')==1,lines('PELICAN WATCH'))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
