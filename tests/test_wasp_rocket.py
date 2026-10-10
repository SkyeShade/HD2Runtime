"""0.30.4 (research/wasp-rocket-F5FEE03DCFDB.json, docs/support-weapon-api.md "Missiles"): the StA-X3 W.A.S.P. Launcher,
FAF-14 Spear, MLS-4X Commando, P-33 Missile Pistol and P-92 Warrant spawn a SeekingMissile entity per shot
(ProjectileWeapon +40; +584 for the ProgrammableAmmo function). The missile flies by its own SeekingMissile record, which
the missile.* / function_missile.* fields write through the weapon's link (re-proven before every write); the carried
projectile row (ProjectileWeapon +0) is only the hit row, and the fired projectile is not swapped. The snapshot tests
write on a copy-on-write overlay of the retained snapshot."""
import json
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run

RESEARCH = json.loads((ROOT / 'research/wasp-rocket-F5FEE03DCFDB.json').read_text())
WASP = 'StA-X3 W.A.S.P. Launcher'
FIELDS = ('max_lifetime', 'starting_speed', 'minimum_speed', 'preferred_speed', 'acceleration', 'max_angle_to_target',
    'turn_rate_at_max_angle', 'turn_rate_aligned', 'guidance_delay')


def weapon(name):
    return next(w for w in RESEARCH['weapons'] if any(n['name'] == name for n in w['names']))


class ResearchTests(unittest.TestCase):
    def test_the_shot_spawns_a_missile_that_carries_the_shot_type(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        asm = {(group, row['rva']): row['asm'] for group, rows in RESEARCH['proofs'].items() for row in rows}
        # ProjectileWeapon +40 set: one shot through 0x615940, which spawns the entity by resource.
        self.assertEqual(asm[('fireSpawnsEntity', 0x6143CD)], 'cmp qword ptr [rax + 0x28], 0')
        self.assertEqual(asm[('shot', 0x615B15)], 'mov rbx, qword ptr [r13 + 0x28]')
        # ProgrammableAmmo state 1: +576 and +584 replace the type and the entity.
        self.assertEqual(asm[('shot', 0x615B23)], 'mov eax, dword ptr [r13 + 0x240]')
        self.assertEqual(asm[('shot', 0x615B30)], 'mov rax, qword ptr [r13 + 0x248]')
        self.assertEqual(asm[('shot', 0x61604F)], 'mov dword ptr [rbp + 0x504], r12d')
        self.assertEqual(asm[('shot', 0x6164D4)], 'call 0xfdc140')
        # The missile takes the spawn info's type (its own +176 is 0) and registers a unit-driven projectile.
        self.assertEqual(asm[('missileSpawn', 0x6414E0)], 'mov eax, dword ptr [rax + 0x424]')
        self.assertEqual(asm[('missileSpawn', 0x641D7A)], 'cmp byte ptr [rax + 0xad], 0')
        self.assertEqual(asm[('missileSpawn', 0x13A9DCE)], 'mov dword ptr [r15 + rsi + 0x3090], ecx')
        # Its flight is the type record, every update; the starting speed at spawn.
        self.assertEqual(asm[('missileUpdate', 0x64283A)], 'call 0x504690')
        self.assertEqual(asm[('missileUpdate', 0x643656)], 'movss xmm1, dword ptr [rsi + 0x40]')
        self.assertEqual(asm[('missileUpdate', 0x6442DE)], 'minss xmm12, xmm0')
        self.assertEqual(asm[('missileSpawn', 0x64114E)], 'movss xmm0, dword ptr [rax + 0x44]')

    def test_wasp_missiles(self):
        wasp = weapon(WASP)
        self.assertEqual((wasp['projectileType'], wasp['functionProjectileType']), (43, 330))
        spawns = {item['member']: item for item in wasp['spawns']}
        self.assertEqual(set(spawns), {40, 584})
        for member, carried in ((40, 43), (584, 330)):
            missile = spawns[member]
            self.assertTrue(missile['exposable'] and missile['projectileSystem'])
            self.assertEqual(missile['projectileType'], carried)
            self.assertEqual(missile['seekingMissile']['ownerCount'], 1)
            self.assertEqual(missile['references']['projectileWeaponRecords'],
                [{'component': 'ProjectileWeaponComponentData', 'record': 248, 'member': member}])
            self.assertEqual(missile['references']['entityDeltaOccurrences'], 0)
        values = spawns[40]['seekingMissile']['values']
        self.assertEqual((values['starting_speed'], values['preferred_speed'], values['max_lifetime']), (10, 100, 30))
        self.assertEqual(spawns[584]['seekingMissile']['values']['preferred_speed'], 80)
        checks = RESEARCH['checks']
        self.assertTrue(checks['snapshotsIdenticalToPinned'])
        self.assertGreaterEqual(checks['snapshots'], 9)

    def test_names_match_the_type_library(self):
        members = {m['offset']: m for m in RESEARCH['members']}
        for name, offset, length in (('max_lifetime', 64, 12), ('starting_speed', 68, 14), ('preferred_speed', 76, 15),
                ('acceleration', 80, 12), ('time_to_enable_guidance', 12, 23)):
            self.assertEqual((members[offset]['leadName'], members[offset]['hiddenNameLength']), (name, length))
        # The turn members are named by the code (both lead names have length 14).
        self.assertEqual(members[88]['field'], 'turn_rate_at_max_angle')
        self.assertEqual(members[92]['field'], 'turn_rate_aligned')

    def test_other_entity_weapons(self):
        # The Breacher's charge is no missile; the Maelstrom's missile is not run by the projectile system.
        breacher = weapon('P-34 Breacher')['spawns'][0]
        self.assertFalse(breacher['exposable'])
        self.assertIsNone(breacher['seekingMissile'])
        maelstrom = weapon('TD-110 Maelstrom / slot_3')['spawns'][0]
        self.assertFalse(maelstrom['exposable'] or maelstrom['projectileSystem'])
        for name in ('FAF-14 Spear', 'MLS-4X Commando', 'P-33 Missile Pistol', 'P-92 Warrant'):
            self.assertTrue(all(item['exposable'] for item in weapon(name)['spawns']), name)


class CatalogueTests(unittest.TestCase):
    def test_support_and_player_rows(self):
        support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
        rows = {}
        for f in support['fieldInstances']:
            if f['semanticFieldId'].split('.')[0] in ('missile', 'function_missile'):
                rows.setdefault(f['supportWeapon'], []).append(f)
        self.assertEqual({k: len(v) for k, v in rows.items()},
            {WASP: 18, 'FAF-14 Spear': 8, 'MLS-4X Commando': 8})   # guidance_delay only where natively > 0
        for row in rows[WASP]:
            self.assertEqual(row['operation']['acknowledgement'], 'allow_unverified_effect')
            self.assertFalse(row['sharedScope']['shared'])
            self.assertEqual(row['target']['path'], 'weapon')
            self.assertEqual(row['effect']['activeSource'], 'SPAWNED_ENTITY_RECORD')
            self.assertIn('min', row['missile'])
        ids = {r['semanticFieldId'] for r in rows[WASP]}
        self.assertEqual(ids, {d + '.' + f for d in ('missile', 'function_missile') for f in FIELDS})
        player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        counts = {w['name']: sum(1 for f in w['fields'] if f.get('spawnedEntity')) for w in player['weapons']}
        self.assertEqual({k: v for k, v in counts.items() if v}, {'P-33 Missile Pistol': 18, 'P-92 Warrant': 9})

    def test_projectile_source_says_why(self):
        catalog = json.loads((ROOT / 'sdk/AttackOutputCapabilities.json').read_text())
        sources = {(s['weapon'], s['attack']): s for s in catalog['projectileSources']}
        wasp = sources[(WASP, 'primary')]
        self.assertEqual(wasp['status'], 'BLOCKED')
        for text in ('ProjectileEntity', 'missile.*', 'function_missile.*', 'projectile 43', 'not swapped'):
            self.assertIn(text, wasp['reason'])
        self.assertIn('not run by the projectile system', sources[('TD-110 Maelstrom / slot_3', 'primary')]['reason'])
        self.assertIn('not a missile', sources[('P-34 Breacher', 'primary')]['reason'])
        output = next(o for o in catalog['outputs'] if o['semanticId'] == 'output/v1/projectile/sta-x3-w-a-s-p-launcher')
        self.assertIn('SeekingMissile', output['blockedReason'])

    def test_lua_guards(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
local F=hd2.fields
rejects({id='a',target=wasp,field=F.missile.preferred_speed,expect=100,value=20},'allow_unverified_effect')
patches.validate{id='a',target=wasp,allow_unverified_effect=true,field=F.missile.preferred_speed,expect=100,value=20}
patches.validate{id='b',target=wasp,allow_unverified_effect=true,field=F.function_missile.preferred_speed,expect=80,value=20}
rejects({id='c',target=wasp,allow_unverified_effect=true,field=F.missile.max_lifetime,expect=30,value=0},
 'reviewed minimum')
rejects({id='d',target=wasp,allow_unverified_effect=true,field=F.missile.preferred_speed,expect=100,value=5000},
 'reviewed maximum')
rejects({id='e',target=wasp,allow_unverified_effect=true,field=F.missile.preferred_speed,expect=90,value=20},
 'expect differs')
-- The Spear's guidance is switched on by its own logic (-1): no guidance_delay row.
rejects({id='f',target=hd2.support_weapon('FAF-14 Spear'),allow_unverified_effect=true,
 field=F.missile.guidance_delay,expect=-1,value=1},'not exposed')
patches.validate{id='g',target=hd2.weapon('P-33 Missile Pistol'),allow_unverified_effect=true,
 field=F.missile.acceleration,expect=200,value=50}
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class SnapshotTests(unittest.TestCase):
    def test_wasp_missiles_written_through_the_link(self):
        result = snapshot_run(r'''
update=update or function()end
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
local changes={{field=F.missile.preferred_speed,expect=100,value=20},{field=F.missile.minimum_speed,expect=10,value=5},
    {field=F.missile.guidance_delay,expect=0.009999999776482582,value=2},
    {field=F.function_missile.preferred_speed,expect=80,value=20}}
local where=resolve('transaction',{id='w',target=wasp,allow_unverified_effect=true,changes=changes})
check(#where==4,'four members of two missile records: '..#where)
local h={}
events.run_as('mods/test/wasp_rocket',function()
    h.op=hd2.ensure({transaction={id='wasp-slow',target=wasp,allow_unverified_effect=true,changes=changes}})
end)
settle({h.op})
check(h.op.result and h.op.result.status=='APPLIED','missile transaction '..tostring(h.op.error))
check(runtime.read(where[1].at,4)==b.encode(20,'f32'),'preferred speed 20 written')
check(runtime.read(where[3].at,4)==b.encode(2,'f32'),'guidance delay 2 written')
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==4,'exactly four members written: '..n)
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])

    def test_a_weapon_that_spawns_another_entity_is_refused(self):
        result = snapshot_run(r'''
update=update or function()end
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
-- Another mod makes the W.A.S.P. spawn something else: its ProjectileWeapon +40 (fire rate is +8 of the same record).
local rate=resolve('patch',{id='r',target=wasp,field=F.weapon.fire_rate,expect=500,value=500})[1]
overlay[rate.at+32]=b.unhex('0100000000000000')
local h={}
events.run_as('mods/test/wasp_rocket_tamper',function()
    h.op=hd2.ensure({patch={id='wasp-fast',target=wasp,allow_unverified_effect=true,
        field=F.missile.preferred_speed,expect=100,value=300}})
end)
settle({h.op})
local text=tostring(h.op.error or(h.op.result and(h.op.result.reason or h.op.result.status)))
check(text:find('SPAWNED_ENTITY_CHANGED',1,true)~=nil,'refused: '..text)
local n=0
for _ in pairs(overlay)do n=n+1 end
check(n==1,'nothing written besides the tamper: '..n)
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
