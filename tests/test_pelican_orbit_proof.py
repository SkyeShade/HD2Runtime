"""proof/PelicanOrbitProof 0.1.0: the proof's own addon on the offline Pelican world of tests/test_pelicans.py (the game's
spawn request simulated, a flight component holding each Runtime Pelican). Ctrl+Shift+F8 in a solo mission spawns one
empty Pelican through hd2.pelican.spawn, anchored at the centre (the last beacon thrown, else 30 m east of the player);
once released and held, runtime/pelicans.lua's orbit moves its hover point around a 40 m circle, 60 m above the centre,
for 60 s with guarded per-instance retargets, then puts the game's own hover point back; the departure is the game's."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS

FOLDER = ROOT / 'proof/PelicanOrbitProof'
BODY = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')

HARNESS = r"""
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function chord(key)
    keys[0x11]=true;keys[0x10]=true;keys[input.keys[key]]=true;tick()
    keys[input.keys[key]]=false;keys[0x10]=false;keys[0x11]=false;tick()
end
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
-- The local player (avatar 100, unit 7100 at (100, 200, 10)) resolvable through the network-id map (the payload world
-- replaced the component world object that held it).
local function player()
    W.players({{peer=LOCAL,avatar=100}},LOCAL)
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
    W.unit(7100,100,200,10)
    local A=require('hd2runtime/domains/event_natives').playerAvatars
    local slots_=W.alloc(64*8)
    for k=0,63 do W.write(slots_+k*8,W.u32(0x7FFF)..W.u32(0))end
    W.write(slots_+(100%64)*8,W.u32(100)..W.u32(0))
    W.write(CWORLD+A.mapSlots,W.u64(slots_));W.write(CWORLD+A.mapCapacity,W.u32(64))
    W.write(CWORLD+A.mapEmpty,W.u32(0x7FFF));W.write(CWORLD+A.mapMultiplier,W.u32(1))
    W.write(CWORLD+A.entityBase,W.u32(100))
end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], BODY)


class PelicanOrbitProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pelican_orbit_proof')
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n' + HARNESS
            + 'return (function()\n' + body + '\nend)()\n'), b'ok')

    def test_the_sources(self):
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.3.0')
        self.assertIn("local BUILD='0.3.0 ORBIT ORIENTATION BUILD'", BODY)
        self.assertIn("local MODES={'lead','sweep','steps'}", BODY)
        self.assertIn('local ENTRY=15', BODY)
        code = '\n'.join(line.split('--')[0] for line in BODY.splitlines())
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_spawn_pelican', 'pelicans.hold', 'pelicans.spawn', 'pelicans.request', 'pelicans.retarget',
                'beacons.apply', 'beacons.watch', 'redirect.apply'):
            self.assertNotIn(forbidden, code)
        # The spawn through the public API; the orbit through the Runtime's guarded driver only.
        self.assertEqual(code.count('hd2.pelican.spawn('), 1)
        self.assertEqual(code.count('pelicans.orbit('), 1)
        self.assertIn('local RADIUS,ALTITUDE,DURATION,PERIOD,STEP,NEAR=40,60,60,30,45,8', code)

    def test_ctrl_shift_f8_circles_the_centre_for_60_s_then_the_game_departs(self):
        self.lua(r'''
pworld()
player()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
chord('F8')
assert(n('ORBIT RUN 1 REQUESTED [0.3.0 ORBIT ORIENTATION BUILD]: centre (130.0, 200.0, 10.0) (30 m east of you (no beacon in '
    ..'the last 2 minutes)); lead mode 10 m ahead, a target every 0.25 s; radius 40 m, 60 m up, 60 s; the Pelican held 65 '
    ..'s: status requested')==1,lines('ORBIT'))
tick(2)
assert(#spawn_calls==1 and spawn_calls[1].ax==130 and spawn_calls[1].ay==200,lines('PELICAN'))
assert(n('PELICAN SPAWNED (run 1): entity 9501: empty, behaviour 667, its anchor (130.0, 200.0, 10.0) (0.0 m from the '
    ..'centre)')==1,lines('PELICAN'))
-- Hover over the centre, release, hold (65 s).
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);position(0,130,200,23);tick()
BOMB.set_clock(T0+20000000);stage(0,6,1);stamp(0,'releaseTime',T0+20000000);tick()
assert(n('PELICAN HELD (run 1): entity 9501: departs 65.0 s after its release; verified true')==1,lines('PELICAN HELD'))
tick()
assert(n('ORBIT STARTED (run 1): entity 9501: lead, 10 m ahead along the circle, a target every 0.25 s; centre (130.0, 200.0, '
    ..'10.0), radius 40 m, 60 m above it, 60 s; starting at 0.0 degrees; ENTRY 15.0 s: a spiral climb from 6.0 m up')==1,
    lines('ORBIT'))
-- 60 s of game time: each update the Pelican is put on its target (it follows).
local clock=T0+20000000
for _=1,250 do
    clock=clock+250000;BOMB.set_clock(clock)
    local f=SPAWN.flight_target(0);position(0,f.x,f.y,f.z)
    tick()
end
assert(n('ORBIT SAMPLE (run 1) t=')>=55,lines('ORBIT SAMPLE'))
assert(n('ESTABLISHED: angle')>=40 and n('radius 40.0 m (asked 40.0), height 60.0 m (asked 60.0)')>=40
    and n('behaviour 667')>=55 and n('ENTRY: angle')>=10,lines('ORBIT SAMPLE'))
assert(n('ORBIT ESTABLISHED (run 1): entity 9501 at 15.')==1,lines('ORBIT ESTABLISHED'))
assert(n('ORBIT STOPPED (run 1): the duration (60.0 s) is over: its hover point (130.0, 200.0, 16.0) is back; the hold '
    ..'and the game\'s departure follow')==1,lines('ORBIT STOPPED'))
assert(n('ORBIT ORIENTATION (run 1): lead mode 10 m, ')==1 and n('ORBIT POSE (run 1): yaw')>=10,lines('ORBIT O'))
assert(n('ORBIT SUMMARY (run 1): lead mode, a target every 0.25 s: ')==1 and n('-> IT CIRCLED')==1
    and n(', THE FULL 60 s')==1
    and n('it stayed in stage 6, behaviour 667 ->')==1,lines('ORBIT SUMMARY'))
local f=SPAWN.flight_target(0)
assert(math.abs(f.x-130)<1e-3 and math.abs(f.z-16)<1e-3,'the hover point is back')
-- The game's departure, then gone.
BOMB.set_clock(T0+85000000);stage(0,8,1);SPAWN.push(0,900,900,100);tick()
assert(n('PELICAN DEPARTING (run 1): entity 9501: stage 8, 65.0 s after its release')==1,lines('DEPARTING'))
BOMB.set_clock(T0+99000000);tcount(0);tick()
assert(n('PELICAN GONE (run 1): entity 9501')==1 and n('REFUSED')==0 and n('callback failed')==0,lines('PELICAN'))
return 'ok'
''')

    def test_the_interval_and_mode_keys_and_the_refusals(self):
        self.lua(r'''
pworld()
player()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
chord('F9');chord('F10')
assert(n('Ctrl+Shift+F9: the next run retargets every 0.50 s')==1 and n('Ctrl+Shift+F10: the next run uses the sweep '
    ..'mode')==1,lines('Ctrl+Shift'))
chord('F7')
assert(n('Ctrl+Shift+F7: the next lead run aims 15 m ahead along the circle')==1,lines('Ctrl+Shift+F7'))
W.state(3);tick()
chord('F8')
assert(n('Ctrl+Shift+F8: not in a mission')==1 and #spawn_calls==0)
W.state(4);tick()
chord('F8')
assert(n('ORBIT RUN 1 REQUESTED [')==1 and n('sweep mode, a target every 0.50 s')==1,lines('ORBIT'))
chord('F8')
assert(n('Ctrl+Shift+F8: run 1 is still alive (one at a time)')==1)
return 'ok'
''')


    def test_the_centre_is_the_last_beacon_thrown(self):
        self.lua(r'''
pworld()
player()
BOMB.set_clock(T0)
tcount(0)
proof()
tick(4)
-- A landed beacon (owned here: its state, mode 1; counting) at (150, 220, 5), in the beacon manager (read-only).
local BD=require('hd2runtime/domains/beacon_redirect')
require('hd2runtime/runtime/beacon_redirect').reset_for_tests()
for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local CW=b.pointer(W.read(W.GAME+BD.path.world,8),0)
local MGR=CW+BD.path.systems+BD.path.beacons
local H,ST,EL=W.alloc(0x1000),W.alloc(0x3000),W.alloc(0x1000)
W.write(MGR+0x50,W.u32(128));W.write(MGR+0x60,W.u64(H));W.write(MGR+0x68,W.u64(ST));W.write(MGR+0x78,W.u64(EL))
local handle=W.alloc(0x20);W.write(handle+8,W.u32(7001));W.write(H,W.u64(handle))
local function f32(v)return b.encode(v,'f32')end
W.write(EL,f32(8)..f32(3)..W.u32(0x11)..W.u32(33)..string.rep('\0',0x2C)..string.char(1)..'\0\0\0')
W.write(ST+BD.state.position,f32(150)..f32(220)..f32(5));W.write(ST+BD.state.mode,W.u32(1)..string.char(0))
W.write(MGR+0x34,W.u32(1)..W.u32(1))
tick(2)
assert(n('ORBIT CENTRE: beacon 7001 (type 33) landed at (150.0, 220.0, 5.0)')==1,lines('ORBIT'))
local writes=#W.runtime.writes
chord('F8')
assert(n('centre (150.0, 220.0, 5.0) (the beacon 7001 you threw 0.0 s ago)')==1,lines('ORBIT RUN'))
tick()
assert(#spawn_calls==1 and spawn_calls[1].ax==150 and spawn_calls[1].ay==220 and spawn_calls[1].az==5)
assert(CT==nil and W.read(EL+0xC,4)==W.u32(33),'the beacon is only read')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
