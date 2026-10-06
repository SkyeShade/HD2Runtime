"""The carrier weapon clone's reviewed data and conversion (domains/weapon_clone.lua, runtime/weapon_clone.lua;
docs/research/carrier-weapon-clone-F5FEE03DCFDB.md):
  * the generated domain is up to date with research/carrier-weapon-clone-F5FEE03DCFDB.json;
  * its facts: the EAT-17's pool (EAT-700, then EAT-411), every host record exclusively owned, every write a width the
    guarded transaction takes, the levels (presentation 3 members, model and full on top), the donor's reviewed values;
  * offline guards without memory: an unreviewed carrier, a carrier outside the donor's class, an unknown level, a
    non-Runtime name or icon, outside a mission;
  * on every retained snapshot (when present): scripts/validate_weapon_clone_snapshot.py (each copied member exact,
    exclusive owners re-proven, unrelated bytes unchanged, protection restored, exact restore, CONFLICT / NOT_NATIVE /
    CARRIER_PRESENT refusals)."""
import importlib.util
import json
import unittest

from support import ROOT, run

import build_profile

DOMAIN = r"""
local D=require('hd2runtime/domains/weapon_clone')
local clone=require('hd2runtime/runtime/weapon_clone');clone.reset_for_tests()
local json=require('hd2runtime/primary_mapper/json')
"""


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeaponCloneDomainTests(unittest.TestCase):
    def test_the_generated_domain_is_current(self):
        generator = load('generate_weapon_clone', 'scripts/generate_weapon_clone.py')
        self.assertEqual(generator.generate(check=True), [])

    def test_the_reviewed_facts(self):
        research = json.loads((ROOT / 'research/carrier-weapon-clone-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        d = research['domain']
        self.assertEqual(d['donors']['EAT-17 Expendable Anti-Tank']['pool'],
            ['EAT-700 Expendable Napalm', 'EAT-411 Leveller'])
        self.assertEqual(d['donors']['EAT-17 Expendable Anti-Tank']['projectile'], 132)
        eat700 = d['carriers']['EAT-700 Expendable Napalm']
        self.assertEqual(eat700['levels'], {'model': 11, 'full': 8})
        self.assertEqual(eat700['projectile'], 259)
        self.assertEqual(eat700['markerKind'], 2)
        for carrier in d['carriers'].values():
            self.assertTrue(all(r['ownerCount'] == 1 for r in carrier['records'].values()))
            self.assertEqual({p['role'] for p in carrier['presentation']}, {'name', 'image', 'icon'})
            for w in carrier['writes']:
                self.assertIn(w['width'], (1, 4, 8, 12))
                self.assertIn(w['level'], ('model', 'full'))
                self.assertNotEqual(w['native'], w['donor'])
        unit = next(w for w in eat700['writes'] if w['component'] == 'UnitComponentData')
        self.assertEqual((unit['offset'], unit['level'], unit['donor']), (0, 'model', 'd30169eda02f9380'))
        rocket = next(w for w in eat700['writes'] if w['component'] == 'ProjectileWeaponComponentData' and w['offset'] == 0)
        self.assertEqual((rocket['level'], rocket['donor'], rocket['native']), ('full', '84000000', '03010000'))

    def test_the_offline_guards(self):
        out = run(DOMAIN + r"""
local function settle(job)for _=1,50 do if job.status~='pending'then break end;update(0.1)end;return job end
local codes={}
for _,s in ipairs({{carrier='MG-43 Machine Gun',donor='EAT-17 Expendable Anti-Tank',level='full'},
    {carrier='EAT-700 Expendable Napalm',donor='MG-43 Machine Gun',level='full'},
    {carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='half'},
    {carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='full',name='EAT-17G'},
    {carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='full',icon='eat17g'},
    {carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='full',colour='red'}})do
    codes[#codes+1]=settle(clone.apply(s)).code
end
local writes={}
for _,level in ipairs(D.levels)do writes[#writes+1]=clone.writes_at('EAT-700 Expendable Napalm',level)end
return json.encode({codes=codes,writes=writes,pool=clone.pool('EAT-17 Expendable Anti-Tank'),
    none=clone.pool('MG-43 Machine Gun')==nil,applied=clone.applied()})
""")
        result = json.loads(out)
        self.assertEqual(result['codes'], ['UNREVIEWED', 'UNREVIEWED', 'INVALID', 'INVALID', 'INVALID', 'INVALID'])
        self.assertEqual(result['writes'], [3, 14, 22])
        self.assertEqual(result['pool'], ['EAT-700 Expendable Napalm', 'EAT-411 Leveller'])
        self.assertTrue(result['none'])
        self.assertFalse(result['applied'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_every_retained_snapshot(self):
        module = load('validate_weapon_clone_snapshot', 'scripts/validate_weapon_clone_snapshot.py')
        names = [n for n in module.SNAPSHOTS if (build_profile.snapshot_directory() / n).is_file()]
        results = module.validate(tuple(names))
        for name, result in results.items():
            self.assertTrue(result['passed'], name + ': ' + '; '.join(result['problems']))
        live = [r for r in results.values() if r['phase'] in ('alive', 'reinforced')]
        self.assertTrue(live, 'no live mission snapshot validated')


if __name__ == '__main__':
    unittest.main()
