"""proof/PelicanSpawnProof 0.2.0: the proof's own addon on the offline Pelican world of tests/test_pelicans.py (the
game's spawn request simulated). As host, Ctrl+F8 spawns, through the public hd2.pelican API only, one empty Pelican
anchored 25 m east of the local player (created 250 m back along the heading, 80 m up); the proof logs its existence,
stages, hover against the requested point, release, hold, departure and removal, and refuses a second one while it is
alive. On every machine it observes every transport Pelican read-only (INTERNAL readers): a client logs the host's."""
import json
import re
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS

FOLDER = ROOT / 'proof/PelicanSpawnProof'
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
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], BODY)


class PelicanSpawnProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pelican_spawn_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n' + HARNESS + body), b'ok')

    def test_the_spawn_uses_the_public_api_only_and_the_observation_only_readers(self):
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_spawn_pelican', 'pelicans.hold', 'pelicans.spawn', 'pelicans.request', 'pelicans.watch'):
            self.assertNotIn(forbidden, BODY)
        # The Runtime module, and two INTERNAL read-only modules for the observation (its readers only).
        self.assertEqual(BODY.count('require('), 3)
        self.assertIn("local pelicans=require('hd2runtime/runtime/pelicans')", BODY)
        self.assertIn("local world_module=require('hd2runtime/runtime/event_world')", BODY)
        used = set(re.findall(r'pelicans\.([a-z_]+)\(', BODY))
        self.assertEqual(used, {'list', 'clock', 'anchor', 'owned'})
        self.assertEqual(BODY.count('hd2.pelican.spawn('), 1)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.2.0')
        self.assertIn("BUILD='0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD'", BODY)
        self.assertNotIn('EMPTY PELICAN SPAWN BUILD', BODY)

    def test_ctrl_f8_spawns_an_empty_pelican_and_it_is_held_then_gone(self):
        self.lua(r'''
pworld()
-- The local player's avatar at (100, 200, 10). The payload world replaced the component world object that also holds
-- the network-id map the player list resolves avatars through: the map is laid out again in it (network id 100 ->
-- the player's slot 0 -> entity 100).
W.players({{peer=LOCAL,avatar=100}},LOCAL)
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
W.unit(7100,100,200,10)
local A=require('hd2runtime/domains/event_natives').playerAvatars
local NSLOTS=W.alloc(64*8)
for k=0,63 do W.write(NSLOTS+k*8,W.u32(0x7FFF)..W.u32(0))end
W.write(NSLOTS+(100%64)*8,W.u32(100)..W.u32(0))
W.write(CWORLD+A.mapSlots,W.u64(NSLOTS));W.write(CWORLD+A.mapCapacity,W.u32(64))
W.write(CWORLD+A.mapEmpty,W.u32(0x7FFF));W.write(CWORLD+A.mapMultiplier,W.u32(1))
W.write(CWORLD+A.entityBase,W.u32(100))
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
ctrl('F8')
assert(n('Ctrl+F8 [0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD]: requested to hover at (125.0, 200.0, 10.0) (25 m east of '
    ..'you), hover 60 s, 1 player in the mission: status requested; created at (-125.0, 200.0, 90.0)')==1,
    table.concat(logged,' | '))
tick(2)
assert(#spawn_calls==1 and spawn_calls[1].ax==125 and spawn_calls[1].x==-125 and spawn_calls[1].z==90
    and spawn_calls[1].fx==1 and spawn_calls[1].fy==0,lines('PELICAN'))
assert(n('PELICAN SPAWN REQUESTED (mods/skyeshade/hd2runtime_pelican_spawn_proof)')==1,lines('PELICAN'))
assert(n('PELICAN SPAWN CREATED (mods/skyeshade/hd2runtime_pelican_spawn_proof): entity 9501')==1,lines('PELICAN'))
assert(n('PELICAN EXISTS: entity 9501 (network id 700): a transport Pelican, empty')==1
    and n('created at (-125.0, 200.0, 90.0) (250.0 m from the requested position); its anchor (125.0, 200.0, 10.0) read '
    ..'back (0.0 m from it)')==1,lines('PELICAN'))
-- Observed read-only here too (the host's own).
assert(n('SEEN PELICAN (HOST): entity 9501 network id 700 at (-125.0, 200.0, 90.0); stage 1')==1
    and n('its anchor (125.0, 200.0, 10.0); a Runtime Pelican of this machine true')==1,lines('SEEN PELICAN'))
-- A second request while it is alive: refused by the proof.
ctrl('F8')
assert(n('a Pelican of this proof is still alive (entity 9501); one at a time')==1)
assert(#spawn_calls==1)
-- The flight.
local c=spawn_calls[1]
BOMB.set_clock(T0+8000000);stage(0,3,0);target(0,c.ax,c.ay,c.az+15);tick()
assert(n('PELICAN STAGE: entity 9501: 1 -> 3 at 8.0 s')==1,lines('PELICAN STAGE'))
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);tick()
assert(n('PELICAN HOVERING: entity 9501 at 15.0 s')==1 and n('0.0 m from the requested position horizontally, 15.0 m '
    ..'above it')==1,lines('PELICAN HOVERING'))
BOMB.set_clock(T0+20000000);stage(0,6,1);stamp(0,'releaseTime',T0+20000000);tick()
assert(n('PELICAN RELEASED: entity 9501 in stage 6 at 20.0 s (released nothing)')==1,lines('PELICAN RELEASED'))
assert(n('PELICAN HELD: entity 9501: departs 60.0 s after its release (native 0.6 s); verified true')==1,lines('HELD'))
for _=1,48 do tick()end
assert(n('PELICAN STATE: entity 9501 stage 6 released true cargo false')>=1,lines('PELICAN STATE'))
BOMB.set_clock(T0+80000000);stage(0,8,1);tick()
assert(n('PELICAN DEPARTING: entity 9501: stage 8, 60.0 s after its release')==1,lines('DEPARTING'))
BOMB.set_clock(T0+94000000);tcount(0);tick()
assert(n('PELICAN GONE: entity 9501: 94.0 s after it was spawned, 74.0 s after its release, 14.0 s after departing')==1,
    lines('PELICAN GONE'))
tick(8)
assert(n('SEEN PELICAN (HOST): entity 9501 GONE')==1,lines('SEEN PELICAN'))
assert(n('PELICAN SUMMARY: entity 9501: spawned empty, hovered 60.0 s after its release (asked 60), left and was removed '
    ..'by the game 14.0 s later')==1,lines('SUMMARY'))
return 'ok'
''')

    def test_a_client_spawns_nothing_and_logs_the_hosts_pelican(self):
        self.lua(r'''
pworld()
W.state(4,{host=false})
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
ctrl('F8')
assert(n('Ctrl+F8: this machine is a CLIENT: only the host spawns')==1 and #spawn_calls==0,lines('Ctrl+F8'))
-- The host's Pelican, replicated here (a fixture transport: entity 7200, network id 812, empty, stage 3).
transport(0,7200,{network=812});stage(0,3,0);position(0,5,6,40);tcount(1)
tick(8)
assert(n('SEEN PELICAN (CLIENT): entity 7200 network id 812 at (5.0, 6.0, 40.0); stage 3, released false, cargo none, '
    ..'associated none')==1 and n('a Runtime Pelican of this machine false')==1,lines('SEEN PELICAN'))
BOMB.set_clock(T0+5000000);stage(0,6,1);tick(8)
assert(n('SEEN PELICAN (CLIENT): entity 7200 network id 812: stage 3 -> 6')==1
    and n('SEEN PELICAN (CLIENT): entity 7200 network id 812 RELEASED')==1,lines('SEEN PELICAN'))
tcount(0);tick(8)
assert(n('SEEN PELICAN (CLIENT): entity 7200 GONE')==1,lines('SEEN PELICAN'))
return 'ok'
''')

    def test_outside_a_mission_nothing_is_requested(self):
        self.lua(r'''
W.state(3)
proof()
tick(4)
ctrl('F8')
assert(n('Ctrl+F8: not in a mission')==1 and #spawn_calls==0)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
