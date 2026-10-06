"""proof/ExtractionPelicanProbe 0.1.0 and proof/PelicanTurretProbe 0.3.0: read-only probes on the offline Pelican world of
tests/test_pelicans.py. The extraction probe follows a behaviour-202 entity (the extraction Pelican, shuttle_gunship): its
stages, its circle against its anchor, its landing point and its chin turret. The turret probe follows chin turrets
(behaviour 645) and Gatling Sentries (213): the Pelican each rides, its weapon components, its record's changes, and
whether a Runtime Pelican carries one, and (0.3.0) what each fires and what of it is per instance. Neither writes
anything."""
import json
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS


def addon(folder):
    from test_event_scripting import SDK
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body), body


HARNESS = r"""
local function proof()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local function lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
local function n(text)local k=0;for _,line in ipairs(logged)do if line:find(text,1,true)then k=k+1 end end;return k end
local GUNSHIP=b.unhex(PE.variants.byType.shuttle_gunship.resource):reverse()
local TURRET=b.unhex(PE.variants.byType.shuttle_gunship_turret_hmg.resource):reverse()
-- An entity with a Behavior record (index i), its handle's resource as the game's, at a position.
local function entity(i,id,resource,behaviour,x,y,z)
    transport(i,id,{resource=resource,behaviour=behaviour})
    W.write(b.pointer(W.read(BHANDLES+i*8,8),0),resource)
    position(i,x,y,z)
end
-- The game removing an entity: its Behavior map key emptied.
local function drop(id)
    local keys=b.pointer(W.read(BCOMP+PE.components.behavior.keys,8),0)
    for k=0,63 do
        if b.u32(W.read(keys+k*8,4),0)==id then W.write(keys+k*8,W.u32(4294967295)..W.u32(0))end
    end
end
"""


class ReadOnlyPelicanProbeTests(unittest.TestCase):
    def lua(self, name, body):
        resource, wrapped, _ = addon(ROOT / 'proof' / name)
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + '\nlocal PROOF_ADDON=' + lua_literal(wrapped)
            + '\nlocal PROOF_RESOURCE=' + lua_literal(resource) + '\n' + HARNESS
            + 'return (function()\n' + body + '\nend)()\n'), b'ok')

    def test_the_sources_are_read_only(self):
        for name, build in (('ExtractionPelicanProbe', '0.1.0 EXTRACTION PELICAN PROBE'),
                ('PelicanTurretProbe', '0.3.0 TURRET WEAPON CONFIG PROBE')):
            _, _, body = addon(ROOT / 'proof' / name)
            code = '\n'.join(line.split('--')[0] for line in body.splitlines())
            self.assertIn("local BUILD='%s'" % build, body)
            self.assertEqual((ROOT / 'proof' / name / 'VERSION').read_text(encoding='utf-8').strip(),
                build.split(' ')[0])
            for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                    'native_spawn_pelican', 'hd2.pelican.spawn', 'pelicans.hold', 'pelicans.retarget',
                    'pelicans.orbit', 'pelicans.spawn', 'pelicans.request', 'beacons.', 'hd2.ensure', 'hd2.patch'):
                self.assertNotIn(forbidden, code, name + ': ' + forbidden)

    def test_the_extraction_probe_follows_the_extraction_pelican_and_its_turret(self):
        self.lua('ExtractionPelicanProbe', r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local writes=#W.runtime.writes
proof()
tick(4)
-- The extraction Pelican (behaviour 202, shuttle_gunship) arriving, its chin turret 3 m below it.
entity(0,8001,GUNSHIP,202,100,100,80);stage(0,2,0);target(0,0,0,40);tcount(1)
entity(1,8002,TURRET,645,100,100,77);stage(1,1,0);tcount(2)
tick(4)
assert(n('EXTRACTION PELICAN SEEN (#1): entity 8001, type shuttle_gunship (EF3A4136B21592CB), behaviour 202')==1,
    lines('EXTRACTION'))
assert(n('EXTRACTION PELICAN TURRET (#1): entity 8002 (type shuttle_gunship_turret_hmg, behaviour 645, stage 1) 3.0 m from '
    ..'it')==1,lines('TURRET'))
-- Its holding stage: the circle against its anchor (the fixture's anchor component is not laid out: unreadable).
BOMB.set_clock(T0+5000000);stage(0,5,0);target(0,30,0,30);tick(4)
assert(n('EXTRACTION PELICAN STAGE (#1): entity 8001: 2 -> 5 after 5.0 s in it')==1,lines('STAGE'))
assert(n('EXTRACTION PELICAN CIRCLE (#1): entity 8001')>=1,lines('CIRCLE'))
BOMB.set_clock(T0+9000000);stage(0,6,0);tick(4)
drop(8001);tick(4)
assert(n('EXTRACTION PELICAN GONE (#1): entity 8001')==1 and n('EXTRACTION PELICAN SUMMARY (#1): stages 2 (')==1,
    lines('EXTRACTION PELICAN'))
assert(#W.runtime.writes==writes,'the probe wrote')
return 'ok'
''')

    def test_the_turret_probe_reports_the_turret_of_a_runtime_pelican_and_its_changes(self):
        self.lua('PelicanTurretProbe', r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local writes=#W.runtime.writes
proof()
tick(4)
-- A Runtime Pelican (spawned through the manager), hovering at (60, 70, 15); its chin turret beside it.
pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican'},function()end)
tick()
stage(0,6,0);position(0,60,70,15)
W.write(b.pointer(W.read(BHANDLES,8),0),PELICAN)                    -- the Behavior handle's resource, as the game's
entity(1,8102,TURRET,645,60,70,12);stage(1,1,0);tcount(2)
-- The link: the Pelican's handle +0xC; the turret's attachable record names it (node 35).
W.write(b.pointer(W.read(BHANDLES,8),0)+12,W.u32(0x40007D))
local A=PE.attachment
local acomp=W.alloc(0x100);W.write(W.GAME+A.global,W.u64(acomp))
local arecs=W.alloc(0x1000);W.write(acomp+A.records,W.u64(arecs))
map(acomp,{keys=A.map,capacity=A.map+8,empty=A.map+0xC,multiplier=A.map+0x10})(8102,0)
W.write(arecs,W.u32(0x40007D)..W.u32(35)..W.u32(4294967295)..W.u32(4294967295)..f32(60)..f32(70)..f32(12))
local after_spawn=#W.runtime.writes
tick(4)
assert(n('TURRET SEEN (#1): the Pelican chin turret: entity 8102, type shuttle_gunship_turret_hmg, behaviour 645')==1
    and n('rides the shuttle_transport 9501 (behaviour 667, a Runtime Pelican), 3.0 m away')==1,lines('TURRET'))
assert(n('RUNTIME PELICAN TURRET: Pelican 9501 (behaviour 667, stage 6, handle link 0x40007D): a chin turret rides it by '
    ..'its attachable link: entity 8102, node 35')==1,lines('RUNTIME PELICAN'))
assert(n('TURRET LINK (#1): entity 8102')==1 and n('parent link 0x40007D, node 35, world position (60.0, 70.0, 12.0); its '
    ..'parent by that link: the shuttle_transport 9501 (behaviour 667, a Runtime Pelican')==1,lines('TURRET LINK'))
-- Its record changes (a target acquired): reported by offset.
stage(1,3,0);target(1,5,5,5)
tick(12)
assert(n('TURRET STATE (#1): entity 8102')>=1 and n('record words changed in 1 s')>=1,lines('TURRET STATE'))
assert(n('TURRET FOLLOW (#1): entity 8102: its attachable world position (60.0, 70.0, 12.0), 3.0 m from its parent 9501')>=1,
    lines('TURRET FOLLOW'))
drop(8102);tick(4)
assert(n('TURRET GONE (#1): entity 8102')==1,lines('TURRET GONE'))
assert(#W.runtime.writes==after_spawn,'the probe wrote')
return 'ok'
''')

    def test_the_turret_probe_reports_what_the_turret_fires_and_what_is_per_instance(self):
        self.lua('PelicanTurretProbe', r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local GATLING=b.unhex(PE.variants.byType.gatling_turret.resource):reverse()
local writes=#W.runtime.writes
proof()
tick(4)
-- A chin turret (no Pelican near): a magazine weapon at 300 RPM, no pattern, chambered 120, no copies.
entity(0,8401,TURRET,645,10,10,40);stage(0,1,0);tcount(1)
local set_magazine=turret_weapon(8401,{flags=0xC0,interval=0.2,rpm=300,rounds=500,chambered=120})
tick(4)
assert(n('TURRET WEAPON (#1): the Pelican chin turret, entity 8401: path magazine (flags 0xC0); its own resolved '
    ..'ProjectileWeapon: none (it uses its type\'s shared record); shot interval 0.2000 s = 300 RPM (current 300, slots '
    ..'0/300/0, index 1); magazine: 500 rounds, pattern off, chambered 120, length 0, own copy none; weapon_heat no; '
    ..'wind-up (spin-up) no')==1,lines('TURRET WEAPON'))
assert(n('GATLING CONFIG (#1) 1/4: entity 8401: projectile 120 -> 148: from the resolved ProjectileWeapon +0 (no '
    ..'pattern); per instance only through its own resolved ProjectileWeapon copy: ABSENT')==1,lines('GATLING CONFIG'))
assert(n('GATLING CONFIG (#1) 2/4: entity 8401: rate 300 -> 1600 RPM: the shot interval +0xC is this instance\'s own')==1,
    lines('GATLING CONFIG'))
assert(n('GATLING CONFIG (#1) 3/4: entity 8401: pattern off -> on (148,148,148,242,148): the magazine pattern is type '
    ..'data (shared)')==1 and n('GATLING CONFIG (#1) 4/4: entity 8401: spin-up: wind-up component absent')==1,
    lines('GATLING CONFIG'))
assert(n('GATLING CONFIG (#1): verdict: NO per-instance home for the projectile type on this turret')==1,
    lines('verdict'))
-- It fires: a round used, the chambered type re-derived (still 120).
set_magazine(499,120);tick(12)
assert(n('TURRET FIRE (#1): entity 8401')==1 and n('rounds 500 -> 499, chambered 120 -> 120; interval 0.2000 s')==1,
    lines('TURRET FIRE'))
-- A Gatling Sentry: its pattern on (chambered 242), wind-up present; no GATLING CONFIG for it.
entity(1,8402,GATLING,213,50,50,0);stage(1,1,0);tcount(2)
turret_weapon(8402,{flags=0xC0,interval=60/1600,rpm=1600,rounds=500,chambered=242,pattern=true,length=5,windUp=true})
tick(4)
assert(n('TURRET WEAPON (#2): the Gatling Sentry, entity 8402: path magazine (flags 0xC0)')==1
    and n('= 1600 RPM')==1 and n('pattern on, chambered 242, length 5')==1 and n('wind-up (spin-up) yes')==1,
    lines('TURRET WEAPON'))
assert(n('GATLING CONFIG (#2)')==0,lines('GATLING CONFIG (#2)'))
assert(#W.runtime.writes==writes,'the probe wrote')
return 'ok'
''')

    def test_the_turret_probe_reports_a_per_instance_copy(self):
        self.lua('PelicanTurretProbe', r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local writes=#W.runtime.writes
proof()
tick(4)
entity(0,8501,TURRET,645,10,10,40);stage(0,1,0);tcount(1)
turret_weapon(8501,{flags=0xC0,interval=0.2,rpm=300,rounds=500,chambered=120,copy={projectileType=120,rpm=300}})
tick(4)
assert(n('its own resolved ProjectileWeapon: YES (projectile 120, RPM 300)')==1,lines('TURRET WEAPON'))
assert(n('per instance only through its own resolved ProjectileWeapon copy: PRESENT')==1
    and n('GATLING CONFIG (#1): verdict: a per-instance ProjectileWeapon copy exists')==1,lines('GATLING CONFIG'))
assert(#W.runtime.writes==writes,'the probe wrote')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
