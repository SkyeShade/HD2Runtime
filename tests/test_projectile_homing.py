"""Projectile homing (runtime/projectile_homing.lua, api/homing.lua, docs/projectile-homing.md).

Pins the research (the projectile update hands the flight record's own velocity to the ballistic integrator, which
integrates the position from it; the census of every velocity store), the generated domain and its weapon catalogue
(every named non-enemy owner of the projectile identities, with its types and firing entity types), the public API's
refusals, the steering math, and the snapshot validation: on the retained mission snapshot one planted shot of the
weapon in hand is turned by exactly turn_rate x dt per update toward a living enemy at the same speed, one guarded
transaction each, and every other byte of its records and every other projectile stays as it was."""
import json
import unittest

from support import ROOT, run

import build_profile

RESEARCH = ROOT / 'research/projectile-homing-F5FEE03DCFDB.json'
VALIDATION = ROOT / 'validation/projectile-homing-snapshot.json'
MISSION = build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
SNAPSHOTS = all((build_profile.snapshot_directory() / name).is_file() for name in (
    'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap', MISSION.name,
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap'))

PRELUDE = r'''
local api=require('hd2runtime/api/homing')
local homing=require('hd2runtime/runtime/projectile_homing')
local D=require('hd2runtime/domains/projectile_homing')
homing.reset_for_tests()
local function refused(handle,code)
    assert(handle.status=='refused',tostring(handle.status))
    assert(handle.code==code,tostring(handle.code)..': '..tostring(handle.reason))
end
'''


class ProjectileHomingTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body + "\nreturn 'ok'"), b'ok')

    def test_the_research_proves_the_velocity_is_the_steps_own(self):
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual((research['writes'], research['protectionChanges']), (0, 0))
        roles = {pin['rva']: pin['asm'] for group in research['proofs'].values() for pin in group}
        # The update hands flight +0x0C to the integrator as the velocity, the record itself as the position.
        self.assertEqual(roles[0x13AB55A], 'lea rdx, [rdi + 0xc]')
        self.assertEqual(roles[0x13AB566], 'mov r8, rdi')
        self.assertEqual(roles[0x13AB59A], 'call 0x13aae30')
        # The integrator loads it once, integrates the position from it and stores it back.
        for rva in (0x13AAE7F, 0x13AAE8A, 0x13AAE95, 0x13AB022, 0x13AB02D, 0x13AB044, 0x13AB062, 0x13AB067, 0x13AB06D):
            self.assertIn(rva, roles)
        # The unit-driven member and the network impact handler (the shooter's position).
        self.assertEqual(roles[0x13AB26C], 'mov r12d, dword ptr [rdi + 0x50]')
        self.assertEqual(roles[0xB9E156], 'mov r8, r12')
        census = research['census']
        self.assertEqual(len(census['pool']), 19)
        self.assertEqual({item['rva'] for item in census['local']},
            {0x13AB53F, 0x13AB544, 0x13AB549, 0x13AB062, 0x13AB067, 0x13AB06D})
        self.assertEqual(research['pool']['flight']['velocity'], 0x0C)
        self.assertEqual(research['pool']['flight']['unit'], 0x50)

    @unittest.skipUnless(SNAPSHOTS, 'retained mission snapshots absent')
    def test_outputs_are_current(self):
        import research_projectile_homing
        research_projectile_homing.main(['--check'])
        import generate_projectile_homing
        self.assertEqual(generate_projectile_homing.generate(check=True), [])

    def test_the_catalogue_names_nearly_every_gun(self):
        import generate_projectile_homing
        weapons = {w['name']: w for w in generate_projectile_homing.build()['weapons']}
        self.assertGreaterEqual(len(weapons), 170)
        self.assertEqual(weapons['EAT-17 Expendable Anti-Tank']['types'], [132])
        self.assertIn('80932FA0ED6901D3', weapons['EAT-17 Expendable Anti-Tank']['sources'])
        self.assertEqual(weapons['P-11 Stim Pistol']['types'], [318])
        self.assertEqual(weapons['SG-8 Punisher']['types'], [260])
        self.assertEqual(weapons['AR-23 Liberator']['types'], [276])
        for name in ('A/MG-43 Machine Gun Sentry', 'Orbital Gas Strike', 'Eagle Airstrike', 'RS-422 Railgun',
                'TD-110 Maelstrom'):
            self.assertIn(name, weapons)
        for weapon in weapons.values():
            self.assertTrue(weapon['types'] and weapon['sources'], weapon['name'])
            self.assertFalse(any('enemy' in c for c in weapon['categories']), weapon['name'])
            for source in weapon['sources']:
                self.assertRegex(source, '^[0-9A-F]{16}$')

    def test_options_and_refusals(self):
        self.lua(r'''
refused(api.homing('LAS-5 Scythe',{owner='mods/a'}),'UNKNOWN_WEAPON')
refused(api.homing(132,{owner='mods/a'}),'UNKNOWN_WEAPON')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',target='allies'}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',turn_rate=0}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',turn_rate=2000}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',cone=0.5}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',range=1e6}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',retarget='yes'}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',speed=3}),'INVALID_OPTION')
refused(api.homing('P-11 Stim Pistol',{owner='mods/a',label=string.rep('x',65)}),'INVALID_OPTION')
assert(#homing.configs()==0,'a refusal configured something')
local stims=api.homing('p-11 stim pistol',{owner='mods/a',target='friendly',multiplayer=true})
assert(stims.status=='active',stims.reason)
assert(stims.weapon=='P-11 Stim Pistol'and stims.types[1]==318 and stims.target=='friendly')
local c=homing.configs()[1]
assert(c.multiplayer==true and c.target=='friendly'and math.abs(c.turn_rate-math.rad(90))<1e-12)
assert(math.abs(c.cone_cos-math.cos(math.rad(30)))<1e-12 and c.range==100 and c.arm_distance==2 and c.aim_height==1)
assert(c.sources['D6B1FB05B9109353'],'the Stim Pistol entity type')
refused(api.homing('P-11 Stim Pistol',{owner='mods/b'}),'ALREADY_HOMING')
-- The same mod replaces its own configuration.
local again=api.homing('P-11 Stim Pistol',{owner='mods/a',turn_rate=45})
assert(again.status=='active'and#homing.configs()==1 and homing.configs()[1].turn_rate==math.rad(45))
-- An output id resolves to its weapon.
local eat=api.homing('output/v1/projectile/eat-17-expendable-anti-tank',{owner='mods/b'})
assert(eat.status=='active'and eat.weapon=='EAT-17 Expendable Anti-Tank',tostring(eat.reason))
-- Every projectile type of a weapon gets its own configuration; stop() ends them all.
local maelstrom=api.homing('TD-110 Maelstrom',{owner='mods/c'})
assert(maelstrom.status=='active'and#maelstrom.configs==#maelstrom.types and#maelstrom.types>1)
local status=api.status()
assert(#status==2+#maelstrom.types,#status)
maelstrom:stop()
assert(maelstrom.status=='stopped'and#api.status()==2)
local stats=eat:stats()
assert(stats.shots==0 and stats.writes==0 and next(stats.refused)==nil)
local list=api.list()
local names={}
for _,item in ipairs(list)do names[item.name]=item end
assert(names['P-11 Stim Pistol']and names['SG-8 Punisher']and names['EAT-17 Expendable Anti-Tank'])
assert(#list==#D.weapons)
''')

    def test_hd2_exports_the_api(self):
        self.lua(r'''
local hd2=require('hd2runtime/api/hd2')
assert(hd2.projectiles.homing==api.homing and hd2.projectiles.homing_list==api.list
    and hd2.projectiles.homing_status==api.status)
assert(type(hd2.projectiles.spawn)=='function','the existing projectile API stays')
''')

    def test_the_turn_is_exact_and_keeps_a_unit_vector(self):
        self.lua(r'''
local function len(x,y,z)return math.sqrt(x*x+y*y+z*z)end
local function angle(ax,ay,az,bx,by,bz)return math.acos(math.max(-1,math.min(1,ax*bx+ay*by+az*bz)))end
-- 90 degrees apart, 10 degrees a step.
local x,y,z,between=homing.turn_toward(1,0,0,0,1,0,math.rad(10))
assert(math.abs(between-math.pi/2)<1e-12)
assert(math.abs(len(x,y,z)-1)<1e-12 and math.abs(angle(x,y,z,1,0,0)-math.rad(10))<1e-9)
assert(math.abs(angle(x,y,z,0,1,0)-math.rad(80))<1e-9)
-- Within reach: exactly the target direction.
x,y,z=homing.turn_toward(1,0,0,0.6,0.8,0,math.rad(60))
assert(x==0.6 and y==0.8 and z==0)
-- Opposite directions turn about a perpendicular axis.
x,y,z,between=homing.turn_toward(0,0,1,0,0,-1,math.rad(5))
assert(math.abs(between-math.pi)<1e-9 and math.abs(len(x,y,z)-1)<1e-9)
assert(math.abs(angle(x,y,z,0,0,1)-math.rad(5))<1e-9)
''')

    @unittest.skipUnless(MISSION.is_file(), 'retained mission snapshot absent')
    def test_the_snapshot_validation(self):
        import validate_projectile_homing_snapshot as validation
        result = validation.validate(MISSION)
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertTrue(all(check['ok'] for check in result['checks']))
        self.assertEqual(len(result['checks']), 35)
        self.assertEqual(result['protectionChanges'], 0)
        self.assertAlmostEqual(result['firstTurnDegrees'], 1.5, places=9)
        self.assertGreater(result['enemies'], 0)
        recorded = json.loads(VALIDATION.read_text(encoding='utf-8'))
        self.assertEqual({k: v for k, v in recorded.items() if k != 'log'},
            {k: v for k, v in json.loads(json.dumps(result, sort_keys=True)).items() if k != 'log'})


if __name__ == '__main__':
    unittest.main()
