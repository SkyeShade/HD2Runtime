"""proof/GasShellProof 0.1.0 (runtime/beacons.lua, runtime/bombardment_executor.lua): the proof's own addon on the offline
payload world with a beacon manager. An AC-8 Autocannon beacon's delivery becomes 'none' in its first update; at its
activation (no spawn requested) the executor fires the 120mm pattern of shell 197 at the beacon's position (the state's
+0x30); each shell lands in the simulated projectile pool, which the proof counts. Only the beacon's type is written."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS

FOLDER = ROOT / 'proof/GasShellProof'

HARNESS = r"""
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
require('hd2runtime/runtime/beacons').reset_for_tests()
-- The host's avatar (entity 100; the payload world's component-world object hides the avatar lookup: stubbed).
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
require('hd2runtime/runtime/handles').local_avatar=function()return {id=100}end
-- FireProjectile as the game does it for the pool: each shell lands at the next counter slot (speed 400).
local fire=W.runtime.native_projectile
W.runtime.native_projectile=function(entry,system,kind,x,y,z,dx,dy,dz,entity)
    fire(entry,system,kind,x,y,z,dx,dy,dz,entity)
    W.spawn_projectile({type=kind,position={x=x,y=y,z=z},velocity={x=dx*400,y=dy*400,z=dz*400},speed=400,source=entity,
        owner=entity})
    return true
end
local function shells()local n=0;for _,p in ipairs(W.runtime.projectiles)do if p.type==197 then n=n+1 end end;return n end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class GasShellProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_gas_shell_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + HARNESS + body), b'ok')

    def test_the_sources(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write('):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertIn("local BUILD='0.1.0 RUNTIME GAS SHELLS'", body)

    def test_a_neutralized_ac8_beacon_gets_15_gas_shells(self):
        self.lua(r'''
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
assert(count('GasShellProof 0.1.0 RUNTIME GAS SHELLS BUILD')==1 and count('GAS SHELLS READY:')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
beacon(0,7101,25,11.717,8.717);counts(1,1);tick()
assert(count('GAS SHELLS BEACON NEUTRALIZED: entity 7101, delivery AC-8 Autocannon -> none, verified true, 1 write')==1,
    lines('GAS SHELLS'))
assert(type_at(0)==0 and#W.runtime.writes==writes+1)
-- The activation: type 0, nothing spawned by the game; the beacon at (50, 60, 5).
W.write(STATE+0x30,b.encode(50,'f32')..b.encode(60,'f32')..b.encode(5,'f32'))
set_countdown(0,8.7);activate(0);BOMB.set_clock(103000000);tick()
assert(count('GAS SHELLS BEACON ACTIVATED: entity 7101, delivery none')==1 and count('spawn requested no')==1,
    lines('ACTIVATED'))
assert(count('GAS SHELLS STARTED for beacon 7101 at (50.0, 60.0, 5.0): shell 197, 5 salvos of 3, 0.75 s between shells, '
    ..'2.00 s between salvos, scatter +-27.0 m, origin 3000 m above each aim')==1,lines('STARTED'))
assert(count('GAS SHELLS DIFFERENCE 1: origin')==1 and count('GAS SHELLS DIFFERENCE 6: network')==1)
tick(220)
assert(shells()==15,'shells '..shells())
assert(count('GAS SHELL 15 (salvo 5)')==1,lines('GAS SHELL '))
assert(count('GAS SHELLS POOL: the first shell 197 in the game\'s projectile pool')==1
    and count('velocity (0.0, 0.0, -400.0), speed 400.0')==1,lines('POOL'))
assert(count('GAS SHELLS RESULT for beacon 7101: ended: 15 shells in 5 salvos over ')==1
    and count('the game\'s projectile pool shows 15 shell(s) 197')==1,lines('RESULT'))
for _,s in ipairs(W.runtime.projectiles)do
    assert(math.abs(s.x-50)<=27 and math.abs(s.y-60)<=27 and math.abs(s.z-3005)<1e-4 and s.entity==100)
end
-- Only the beacon's type was written; no record changed.
assert(#W.runtime.writes==writes+1 and W.read(ROW25,400)==ROW25_BYTES and W.read(ROW[136],400)==ROW136_BYTES)
assert(count('callback failed')==0)
return 'ok'
''')

    def test_a_missing_gas_package_fires_nothing(self):
        self.lua(r'''
pworld()
BOMB.set_clock(100000000)
proof()
tick(64)
local assets=require('hd2runtime/core/assets')
local PACKAGE=assets.dependency_for_stratagem(GAS_ID,'x').package
beacon(0,7101,25,11.717,8.717);counts(1,1);tick()
W.runtime.packages[PACKAGE]='absent'
set_countdown(0,8.7);activate(0);tick()
assert(count('GAS SHELLS REFUSED for beacon 7101 (nothing fired): SHELL_NOT_RESIDENT')==1 and shells()==0,
    lines('GAS SHELLS'))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
