"""runtime/pelican_heading.lua (research/docs/pelican-cas-F5FEE03DCFDB.md section 20e): a Runtime-held Pelican's body
heading in its hold through its hover controller's desired facing D, on the offline Pelican world of tests/test_pelicans.py
with the turret fixture of tests/test_pelican_gatling.py and a simulated hover controller (game+0x3326DB0). The
controller itself is the game's; the guards, the stepped writes and the read-back are the Runtime's own."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING

HEADING = r"""
local heading=require('hd2runtime/runtime/pelican_heading')
heading.reset()
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
local HD=PE.heading
-- The hover controller: the Pelican (9501) at index 0, simulated here, enabled; D the direction it arrived from (+Y).
local HCOMP,hkey=manager({global=HD.global,map=HD.map})
local HRECS,HENTS=W.alloc(0x1000),W.alloc(0x1000)
W.write(HCOMP+HD.simulated,W.u32(1));W.write(HCOMP+HD.records,W.u64(HRECS));W.write(HCOMP+HD.entries,W.u64(HENTS))
local function controller()
    hkey(9501,0)
    W.write(HRECS+HD.desired,f32(0)..f32(1)..f32(0))
    W.write(HENTS+HD.enabled,'\1\0')
end
-- The Pelican held (stage 6, released), the host's, its flight in mode 1.
local function held(world)
    stage(0,6,1)
    W.write(b.pointer(W.read(BHANDLES,8),0)+0x14,W.u32(1))
    local t=pelicans.targets(world,9501)
    W.write(t.flight_record+HD.flightMode,W.u32(1))
end
local function desired()local raw=W.read(HRECS+HD.desired,12);return b.value(raw,0,'f32'),b.value(raw,4,'f32'),
    b.value(raw,8,'f32')end
local function face(t,point)BOMB.set_clock(t);return in_update(function()return heading.face_step(world_module.open(),9501,
    point,'test')end)end
"""


class PelicanHeadingTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + HEADING + body
            + '\nend)()\n'), b'ok')

    def test_the_research(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        pinned = {p['rva'] for p in research['pins']['heading']}
        # The controller after the flight; its gating; D read by the controller and stored by the game's own setter;
        # 667 stage 3 sets D, stage 6 enters flight mode 1.
        self.assertTrue({0x573D01, 0x573D10, 0x6D1A24, 0x6D1A78, 0x6D2847, 0x6D4ED0, 0x45A801, 0x45C161} <= pinned)
        h = research['heading']
        self.assertEqual((h['global'], h['records'], h['stride'], h['desired']), ('0x3326DB0', 0x48, 0x28, 0xC))

    def test_it_turns_toward_the_point_smoothly_and_never_fights(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
controller()
local world=world_module.open()
-- Not held yet: nothing.
assert(face(T0,{x=100,y=70,z=0})==nil)
held(world)
local s=heading.state(world,9501)
assert(s and math.abs(s.desired_yaw-90)<1e-3 and s.mode==1 and s.simulated and s.enabled and not s.crashed)
-- East of it (0 degrees): 40 deg/s from 90, 0.25 s: 80; aligned 4-byte writes (x and y; z stays 0).
local w0=#W.runtime.writes
local e=face(T0+250000,{x=100,y=70,z=0})
assert(e and e.kind=='turned'and math.abs(e.from-90)<1e-3 and math.abs(e.to-80)<1e-3 and math.abs(e.toward)<1e-3,
    tostring(e and e.kind)..' '..tostring(e and e.code)..' '..tostring(e and e.reason))
assert(#W.runtime.writes==w0+2)
local x,y,z=desired()
assert(math.abs(x-math.cos(math.rad(80)))<1e-6 and math.abs(y-math.sin(math.rad(80)))<1e-6 and z==0)
-- 0.5 s later: 20 more degrees.
e=face(T0+750000,{x=100,y=70,z=0})
assert(math.abs(e.to-60)<1e-3)
-- No point: the heading is kept, nothing written.
w0=#W.runtime.writes
assert(face(T0+1000000,nil)==nil and #W.runtime.writes==w0)
-- Another writer changes D: stopped for good, not fought.
W.write(HRECS+HD.desired,f32(1)..f32(0)..f32(0))
e=face(T0+1250000,{x=100,y=70,z=0})
assert(e and e.kind=='stopped'and n('PELICAN HEADING STOPPED (test): Pelican 9501')==1)
assert(face(T0+1500000,{x=60,y=200,z=0})==nil and #W.runtime.writes==w0)
return 'ok'
""")

    def test_only_in_the_hold_in_mode_1_and_where_it_is_simulated(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
controller()
local world=world_module.open()
held(world)
-- Not simulated here (another machine's authority partition): refused.
W.write(HCOMP+HD.simulated,W.u32(0))
local e=face(T0+250000,{x=100,y=70,z=0})
assert(e and e.kind=='refused'and e.code=='NOT_CONTROLLED')
W.write(HCOMP+HD.simulated,W.u32(1))
-- Another flight mode, another stage: nothing.
local t=pelicans.targets(world,9501)
W.write(t.flight_record+HD.flightMode,W.u32(0))
assert(face(T0+500000,{x=100,y=70,z=0})==nil)
W.write(t.flight_record+HD.flightMode,W.u32(1))
stage(0,8,1)
assert(face(T0+750000,{x=100,y=70,z=0})==nil)
stage(0,6,1)
-- Outside the update: refused.
e=heading.face_step(world,9501,{x=100,y=70,z=0},'test')
assert(e and e.kind=='refused'and e.code=='NOT_GAME_THREAD')
-- Nothing written in any of these.
local x,y=desired()
assert(x==0 and y==1)
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
