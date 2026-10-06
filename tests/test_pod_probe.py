"""proof/PodProbe 0.1.0 (read-only): the proof's own addon on the offline payload world with a beacon manager and a
simulated TransportComponent manager ([game+0x3326518]): an AC-8 pod created from a beacon (linked by the beacon's
network id), its landing (the spawn timer armed), its content spawn and its removal are reported, with the per-pod
window. Nothing is written."""
import json
import re
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

FOLDER = ROOT / 'proof/PodProbe'
BODY = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
PINS = re.findall(r"\{rva=(0x[0-9A-F]+),hex='([0-9a-f]+)'", BODY)

HARNESS = r"""
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
for _,pin in ipairs(POD_PINS)do W.write(W.GAME+pin[1],b.unhex(pin[2]))end
-- The TransportComponent manager: count +0x10, handles +0x38, elements +0x40 (0x40 each), blocks +0x48 (0x18 each).
local TMGR,THANDLES,TELEMENTS,TBLOCKS=W.alloc(0x100),W.alloc(0x100),W.alloc(0x1000),W.alloc(0x400)
W.write(W.GAME+0x3326518,W.u64(TMGR))
W.write(TMGR+0x38,W.u64(THANDLES));W.write(TMGR+0x40,W.u64(TELEMENTS));W.write(TMGR+0x48,W.u64(TBLOCKS))
W.write(TMGR+0x10,W.u32(0))
local function hash(hex)return(b.unhex((hex:gsub('^0x',''))):reverse())end
local function pod(i,entity,net,content,kind,beacon_net)  -- kind: the stratagem type in the block
    local handle=W.alloc(0x20);W.write(handle+8,W.u32(entity));W.write(handle+0x10,W.u32(net))
    W.write(THANDLES+i*8,W.u64(handle))
    W.write(TELEMENTS+i*0x40,hash(content)..W.u32(4294967295)..b.encode(-1,'f32')..b.encode(-1,'f32')..string.char(1,0,0,0)
        ..W.u32(100))
    W.write(TBLOCKS+i*0x18,hash(content)..W.u32(0)..W.u32(kind)..W.u32(beacon_net))  -- +8 kind 0, +0xC type
end
local function pods(n)W.write(TMGR+0x10,W.u32(n))end
local function land(i)W.write(TELEMENTS+i*0x40+0xC,b.encode(0.5,'f32'))end
local function spawn(i,entity)W.write(TELEMENTS+i*0x40+0x8,W.u32(entity))end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], BODY)


class PodProbeTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pod_probe')
        pins = 'local POD_PINS={' + ','.join('{%s,%s}' % (rva, lua_literal(hexs)) for rva, hexs in PINS) + '}\n'
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n' + pins + HARNESS + body), b'ok')

    def test_the_sources(self):
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'redirect_now',
                'beacons.apply', 'transaction'):
            self.assertNotIn(forbidden, BODY)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertEqual(len(PINS), 15)

    def test_an_ac8_pod_from_creation_to_its_content(self):
        self.lua(r'''
pworld()
proof()
tick(8)
assert(count('pins: the Transport component and its readers are the researched code (15 pins)')==1,
    table.concat(logged,' | '))
local writes=#W.runtime.writes
-- An AC-8 beacon (network id 31) and its pod (entity 801, network id 41) carrying the AC-8's rack.
beacon(0,7101,25,8.7,8.7);counts(1,1)
local handle=b.pointer(W.read(HANDLES,8),0);W.write(handle+0x10,W.u32(31))
pod(0,801,41,'0x5F41C4DCABE95421',25,31);pods(1)
tick(2)
assert(count('POD CREATED: entity 801 (network id 41), content 0x5F41C4DCABE95421 (AC-8 Autocannon payload 1), type '
    ..'AC-8 Autocannon (25), kind 0, call flag 1, owner 100; from the beacon with network id 31 (beacon entity 7101, its type '
    ..'now AC-8 Autocannon (25))')==1,lines('POD'))
tick(20);land(0);tick(2)
assert(count('POD LANDED: entity 801')==1,lines('POD'))
tick(4);spawn(0,900);tick(2)
assert(count('POD CONTENT SPAWNED: entity 801, content entity 900 (0x5F41C4DCABE95421 (AC-8 Autocannon payload 1))')==1,
    lines('POD'))
pods(0);tick(2)
assert(count('POD SUMMARY: entity 801, content 0x5F41C4DCABE95421')==1,lines('POD SUMMARY'))
assert(#W.runtime.writes==writes,'the probe writes nothing')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
