"""RC coverage (0.28): user-reported gaps and the mounted projectile hosts.

- MA5C penetration slowdown: every player projectile host publishes projectile velocity, drag and penetration
  slowdown generically (the published 0.27.0 SDK had no penetration slowdown on any player weapon).
- AR/GL-21 One-Two underbarrel: the launcher is a separate weapon entity (research/underbarrel-weapons); its grenade
  spread and rounds are nested sub-target fields, never flattened into the rifle. GP-31 / P-72 keep their fail-closed
  duplicate identity with the proven reason (one root is another weapon's underbarrel).
- Mounted hosts: mounted projectile weapons join the one projectile host rule and donor pool.
"""
import json
import unittest

from support import ROOT, run


def load(name):
    return json.loads((ROOT / 'sdk' / name).read_text(encoding='utf-8'))


class PlayerCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load('PlayerWeaponAuthoringCapabilities.json')
        cls.weapons = {w['name']: w for w in cls.catalog['weapons']}

    def test_every_projectile_host_publishes_velocity_drag_and_penetration_slowdown(self):
        hosts = [w for w in self.catalog['weapons'] if any(f['semanticFieldId'] == 'projectile.velocity'
            or f['semanticFieldId'].startswith('projectile.') and f['semanticFieldId'].endswith('.velocity')
            for f in w['fields'])]
        self.assertEqual(len(hosts), 66)
        for weapon in hosts:
            ids = {f['semanticFieldId'].replace('.primary.', '.').replace('.alternate.', '.') for f in weapon['fields']}
            for field in ('projectile.velocity', 'projectile.drag', 'projectile.penetration_slowdown'):
                self.assertIn(field, ids, weapon['name'])
        ma5c = {f['semanticFieldId']: f for f in self.weapons['MA5C Assault Rifle']['fields']}
        self.assertTrue(ma5c['projectile.penetration_slowdown']['editable'])
        self.assertEqual(ma5c['projectile.penetration_slowdown']['apiFieldConstant'],
            'hd2.fields.projectile.penetration_slowdown')

    def test_underbarrels_are_nested_sub_targets_with_only_proven_members(self):
        subs = {s['name']: s for s in self.catalog['subweapons']}
        self.assertEqual(sorted(subs), ['AR-11 Arbitrator / underbarrel', 'AR/GL-21 One-Two / underbarrel',
            'SMG/FLAM-34 Stoker / underbarrel'])
        launcher = subs['AR/GL-21 One-Two / underbarrel']
        values = {f['semanticFieldId']: f['currentDefault'] for f in launcher['fields']}
        self.assertEqual(values, {'weapon.horizontal_spread': 30.0, 'weapon.vertical_spread': 30.0,
            'weapon.fire_rate': 900.0, 'rounds.feed_capacity_1': 1.0, 'rounds.spare_rounds': 5,
            'rounds.rounds_from_supply': 5, 'rounds.starting_rounds': 3})
        self.assertEqual(launcher['resources'], ['0x02CD7321CD8445F5'])
        self.assertTrue(all(f['acknowledgement'] == 'allow_unverified_effect' and f['writeScope'] == 'weapon_local'
            for f in launcher['fields']))
        self.assertIn('reload time', ' '.join(launcher['notExposed']))
        # Not flattened: the rifle keeps its own records and has no grenade fields.
        rifle = self.weapons['AR/GL-21 One-Two']
        self.assertEqual(rifle['subweapons'], [{'name': 'AR/GL-21 One-Two / underbarrel', 'kind': 'underbarrel'}])
        self.assertNotIn('rounds.spare_rounds', {f['semanticFieldId'] for f in rifle['fields']})
        self.assertEqual({f['semanticFieldId']: f['currentDefault'] for f in rifle['fields']}['weapon.fire_rate'], 650)
        # The Stoker's underbarrel flamer: spread only (no rounds, no projectile).
        self.assertEqual({f['semanticFieldId'] for f in subs['SMG/FLAM-34 Stoker / underbarrel']['fields']},
            {'weapon.horizontal_spread', 'weapon.vertical_spread'})

    def test_misattributed_duplicate_roots_resolve_to_the_proven_root(self):
        # 0.30.2: the underbarrel root is dropped and the weapon is writable (research/weapon-roots).
        for name, host in (('GP-31 Grenade Pistol', 'AR/GL-21 One-Two'), ('P-72 Crisper', 'SMG/FLAM-34 Stoker')):
            weapon = self.weapons[name]
            self.assertFalse(weapon['ordinaryWritesBlocked'], name)
        research = json.loads((ROOT / 'research/underbarrel-weapons-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        self.assertEqual([(c['weapon'], c['dropRoot'], c['keptRoots']) for c in research['catalogCorrections']],
            [('GP-31 Grenade Pistol', '0x02CD7321CD8445F5', ['0x52E4334E6A128CAF']),
             ('P-72 Crisper', '0x992B6F65A5BAB53D', ['0x3F92BA65EF65CCA9'])])

    def test_underbarrel_writes_target_the_launcher_entity(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(fn,needle)
 local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
local launcher=hd2.weapon('AR/GL-21 One-Two'):underbarrel()
assert(launcher:describe().subweaponOf=='AR/GL-21 One-Two')
local spec=patches.validate{id='spread',target=launcher,field=hd2.fields.weapon.horizontal_spread,expect=30,value=5,
 allow_unverified_effect=true}
assert(spec.resource=='0x02CD7321CD8445F5'and spec.weapon=='AR/GL-21 One-Two / underbarrel')
patches.validate{id='spare',target=launcher,field=hd2.fields.rounds.spare_rounds,expect=5,value=12,
 allow_unverified_effect=true}
rejects(function()
 patches.validate{id='spare',target=launcher,field=hd2.fields.rounds.spare_rounds,expect=5,value=12}end,
 'allow_unverified_effect')
-- The rifle's own spread is a different record.
local rifle=patches.validate{id='r',target=hd2.weapon('AR/GL-21 One-Two'),field=hd2.fields.weapon.horizontal_spread,
 expect=1,value=2}
assert(rifle.resource=='0xA955C4EA6F6D4203')
rejects(function()return hd2.weapon('AR-23 Liberator'):underbarrel()end,'no reviewed underbarrel')
return 'ok'
'''), b'ok')


class MountedHostTests(unittest.TestCase):
    def test_mounted_hosts_and_sources(self):
        vehicles = load('VehicleWeaponCapabilities.json')
        hosts = sorted(i['weapon'] for i in vehicles['fieldInstances']
            if i['semanticFieldId'] in ('attack.projectile', 'attack.primary.projectile'))
        self.assertEqual(hosts, ['AX/AR-23 Guard Dog / gun', 'EXO-45 Patriot Exosuit / right_gun',
            'EXO-49 Emancipator Exosuit / left_gun', 'EXO-49 Emancipator Exosuit / right_gun',
            'EXO-51 Lumberer Exosuit / right_gun', 'FRV (Super Earth variant) / gun', 'GATER Oil Rig / turret',
            'M-102 Gunner FRV / gun', 'M-103 Supply FRV / gun'])
        outputs = load('AttackOutputCapabilities.json')
        sources = {s['weapon']: s for s in outputs['projectileSources'] if s.get('kind') == 'vehicle_weapon'}
        self.assertEqual(sources['M-102 Gunner FRV / gun']['sharedEntity'], ['FRV (Super Earth variant) / gun'])
        self.assertEqual(sources['EXO-45 Patriot Exosuit / left_gun']['status'], 'BLOCKED')
        self.assertIn('ProjectileEntity', sources['EXO-45 Patriot Exosuit / left_gun']['reason'])
        patriot = next(o for o in outputs['outputs'] if o['owner']['name'] == 'EXO-45 Patriot Exosuit / right_gun')
        self.assertEqual((patriot['slots']['impactExplosion']['shared'],
            patriot['slots']['impactExplosion']['sharedConsumerCount']), (True, 10))
        self.assertIn('gatling_turret', patriot['slots']['impactExplosion']['namedSharedConsumers'])


if __name__ == '__main__':
    unittest.main()
