"""proof/BeaconProbe 0.1.0 (read-only; docs/research/beacon-redirect-F5FEE03DCFDB.md): the probe's own addon on the
offline event world with a beacon component manager laid out as the research found it ([game+0x346BF98] + 0x40 +
0x1380; elements of 0x40 bytes with the type at +0xC; state of 0x8E8 bytes, activated at +0x8E4). It logs a beacon's
creation, the Runtime updates before its activation (the redirect window), a type change, the activation and the
removal; it refuses when the pinned code differs; it never writes."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

FOLDER = ROOT / 'proof/BeaconProbe'

HARNESS = r"""
local PD=require('hd2runtime/domains/bombardment_payload')
local function put64(at,n)W.write(at,W.u32(n%4294967296)..W.u32(math.floor(n/4294967296)))end
-- The pinned code, as the game has it.
local PINS={{0xFDAF4B,'488d4f40'},{0x5712FB,'488d8f80130000'},{0x571305,'e8d6a01300'},{0x6AB42C,'8b4634'},
    {0x6AB490,'488b4678'},{0x6AB812,'837e3800'},{0x6AB830,'4c8b6678'},{0x6AB837,'4d69efe8080000'},{0x6AB842,'4c036e68'},
    {0x6AB84A,'418b443c0c'},{0x6ABB58,'f3410f10043c'},{0x6ABB5E,'f3410f104c3c04'},{0x6ABB77,'4180bde408000000'},
    {0x6ABB8D,'41c685e408000001'},{0x6ABC14,'418b4c3c0c'},{0x6ABC72,'e839010000'},{0x6AE910,'89440f0c'},
    {0x6AE829,'448b4e50'},{0x13D1389,'4c8b05c856f501'},{0x13D1393,'458b4830'},{0x13D1397,'458b5038'},
    {0x13D13AC,'4d8b5828'},{0x13D13B0,'418b7834'},{0x13D14AB,'486bc82c'},{0x13D14AF,'498b4050'},{0x13D14B3,'8b5c0128'},
    {0x13D1557,'8b87b8000000'}}
for _,p in ipairs(PINS)do W.write(W.GAME+p[1],b.unhex(p[2]))end
-- The component world and its beacon manager; the game clock.
local WORLD_OBJECT=W.alloc(0x2000)
W.write(W.GAME+PD.component.global,W.u64(WORLD_OBJECT))
local MGR=WORLD_OBJECT+0x40+0x1380
local HANDLES,STATE,ELEMENTS=W.alloc(0x100),W.alloc(4*0x8E8),W.alloc(4*0x40)
W.write(MGR+0x50,W.u32(128))
W.write(MGR+0x60,W.u64(HANDLES));W.write(MGR+0x68,W.u64(STATE));W.write(MGR+0x78,W.u64(ELEMENTS))
local CLOCK_OBJECT=W.alloc(0x40)
W.write(W.GAME+PD.clock.global,W.u64(CLOCK_OBJECT))
local function set_clock(us)put64(CLOCK_OBJECT+PD.clock.time,us)end
set_clock(100000000)
local function f32(v)return b.encode(v,'f32')end
local function beacon(i,entity,kind,countdown,threshold)
    local handle=W.alloc(0x20);W.write(handle+8,W.u32(entity));W.write(HANDLES+i*8,W.u64(handle))
    local e=ELEMENTS+i*0x40
    W.write(e,f32(countdown)..f32(threshold));W.write(e+0xC,W.u32(kind))
end
local function counts(n,active)W.write(MGR+0x34,W.u32(n)..W.u32(active))end
local function activate(i)W.write(STATE+i*0x8E8+0x8E4,string.char(1))end
local function countdown(i,v)W.write(ELEMENTS+i*0x40,f32(v))end
local function probe()assert(loadstring(PROBE_ADDON,'@'..PROBE_RESOURCE))()end
-- The marker component: entity 7001's element holds the type `kind` (an 8-slot map, multiplier 1, empty key 0).
local MARKER=W.alloc(0x80)
W.write(W.GAME+0x3326A58,W.u64(MARKER))
local MKEYS,MELEM=W.alloc(8*8),W.alloc(4*0x2C)
W.write(MARKER+0x28,W.u64(MKEYS));W.write(MARKER+0x30,W.u32(8)..W.u32(0)..W.u32(1));W.write(MARKER+0x50,W.u64(MELEM))
local function marker(entity,kind)W.write(MKEYS+(entity%8)*8,W.u32(entity)..W.u32(0));W.write(MELEM+0x28,W.u32(kind))end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class BeaconProbeTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_beacon_probe')
        self.assertEqual(run(WORLD + '\nlocal PROBE_ADDON=' + lua_literal(wrapped) + '\nlocal PROBE_RESOURCE='
            + lua_literal(resource) + HARNESS + body), b'ok')

    def test_the_sources_write_nothing(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction.apply',
                'guarded_transaction'):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')

    def test_a_beacon_its_window_its_activation_and_its_summary(self):
        self.lua(r'''
local writes=#W.runtime.writes
mission({host=true})
probe()
tick(3)
assert(count('pins: the beacon manager path and its readers are the researched code (27 pins)')==1,
    table.concat(logged,' | '))
assert(count('BEACON CREATED:')==0)
-- A 120mm beacon lands: seen for 4 updates before it activates.
beacon(0,7001,136,6.0,0.5);marker(7001,136);counts(1,0)
tick()
assert(count('BEACON CREATED: type 136')==1 or count('BEACON CREATED: Orbital 120mm HE Barrage (type 136)')==1,
    table.concat(logged,' | '))
assert(count('countdown 6.000, threshold 0.500, position')==1)
assert(count('category offensive (red); marker component type ')==1 and count('SAME AS the beacon type')==1,
    table.concat(logged,' | '))
counts(1,1)
for k=1,3 do countdown(0,6.0-k);tick()end
set_clock(105500000)
activate(0);countdown(0,0.4);tick()
assert(count('BEACON ACTIVATED:')==1 and count('window: 4 Runtime updates saw it before activation')==1,
    table.concat(logged,' | '))
counts(0,0);tick()
assert(count('BEACON SUMMARY:')==1 and count('type UNCHANGED throughout')==1 and count('5.500 s after first seen')==1,
    table.concat(logged,' | '))
-- A beacon activated in the update it was first seen: window 0, the blocker.
beacon(0,7002,118,0.0,0.0);activate(0);counts(1,1);tick()
assert(count('window: 0 Runtime updates: NO update saw it before activation (the current blocker for this type)')==1,
    table.concat(logged,' | '))
counts(0,0);tick()
-- A type changed by the game is reported.
beacon(1,7003,136,3.0,0.5);counts(2,0)
W.write(HANDLES,W.u64(0));tick()
W.write(ELEMENTS+0x40+0xC,W.u32(118));tick()
assert(count('BEACON TYPE CHANGED (by the game): entity 7003')==1,table.concat(logged,' | '))
-- Ctrl+F11 table.
assert(#W.runtime.writes==writes,'the probe wrote')
return 'ok'
''')

    def test_a_changed_pin_refuses_and_reads_nothing(self):
        self.lua(r'''
W.write(W.GAME+0x6ABC14,string.char(0xCC))
mission({host=true})
probe()
beacon(0,7001,136,6.0,0.5);counts(1,0)
tick(3)
assert(count('REFUSED: the beacon code changed (the type passed at activation at game+6ABC14)')==1
    and count('BEACON CREATED:')==0,table.concat(logged,' | '))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
