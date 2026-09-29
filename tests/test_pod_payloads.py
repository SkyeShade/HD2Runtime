import importlib.util
import json
import re
import unittest

from support import ROOT, run


spec = importlib.util.spec_from_file_location('generate_pod_payload_authoring',
    ROOT / 'scripts/generate_pod_payload_authoring.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PodPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/pod-payloads-F5FEE03DCFDB.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/PodPayloadCapabilities.json').read_text())
        cls.racks = {r['name']: r for r in cls.catalog['racks']}
        cls.pickups = {p['name']: p for p in cls.catalog['pickups']}

    def test_generated_outputs_are_fresh(self):
        self.assertFalse(generator.generate(check=True))

    def test_native_model_and_surplus_eat(self):
        self.assertTrue(all(self.research['liveEquality'].values()))
        members = {m['member']: m['offset'] for m in self.research['typeLibrary']['HellpodRackComponent']}
        self.assertEqual(members, {'payloads': 0, 'random_payload_size': 552, 'spawn_payload_size': 556})
        eat = next(r for r in self.research['racks'] if (r['path'] or '').endswith('weapon_rack_lat_oneshot'))
        self.assertEqual(eat['spawnPayloadSize'], 2)
        self.assertEqual([s['item'] is not None for s in eat['slots']][:4], [True, True, False, False])
        self.assertEqual(eat['slots'][0]['item'], eat['slots'][1]['item'])
        self.assertEqual({c['nativeType'] for c in eat['consumers']}, {'LATOneshot', 'LATOneshot_Booster'})
        rack = self.racks['EAT-17 Expendable Anti-Tank pod']
        self.assertTrue(rack['shared'])
        self.assertIn('Surplus EAT Allocation', [c['booster'] for c in rack['consumers']])
        self.assertEqual([s['current']['name'] for s in rack['slots'][:2]], ['EAT-17 Expendable Anti-Tank'] * 2)
        self.assertEqual(rack['slots'][0]['acknowledgements'], ['allow_unverified_reference', 'allow_shared'])

    def test_catalog_coverage_and_safety(self):
        summary = self.catalog['summary']
        self.assertEqual((summary['racks'], summary['writableRacks'], summary['sharedRacks']), (56, 48, 6))
        self.assertEqual(summary['writableSlots'], 192)
        self.assertEqual(summary['pickups'], 68)
        self.assertEqual(summary['pickupsByCategory'], {'ammo': 2, 'backpack': 25, 'grenade': 1, 'stim': 2,
            'supply': 1, 'support_weapon': 37})
        self.assertEqual(summary['alwaysResidentPickups'], 1)
        self.assertTrue(self.pickups['Supply Box']['residency']['alwaysResident'])
        self.assertEqual(self.pickups['Grenade Box']['compatibility'], 'UNVERIFIED_REFERENCE')
        self.assertEqual(self.pickups['Health Pack (pod)']['compatibility'], 'SCHEMA_COMPATIBLE')
        self.assertFalse(self.racks['MS-11 Solo Silo pod']['writable'])
        self.assertFalse(self.racks['Jammed Pod pod']['writable'])
        self.assertNotRegex(json.dumps(self.catalog).lower(), re.compile(r'0x[0-9a-f]{8,}'))
        self.assertEqual(set(self.catalog['categories']), set(summary['pickupsByCategory']))

    def test_snapshot_overlay_validation(self):
        result = json.loads((ROOT / 'validation/pod-payload-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        for key in ('slots', 'baselineMatches', 'noOps', 'changedWrites', 'rollbacks', 'conflictRejections',
                    'acknowledgementRejections'):
            self.assertEqual(result[key], 192, key)
        self.assertEqual((result['racks'], result['spawnCounts'], result['sharedRejections']), (48, 48, 24))
        self.assertEqual(len(result['rejections']), 9)
        self.assertIn('live-verified pickup outside its tested slot', result['rejections'])
        for key in ('surplus_eat_support_weapon', 'surplus_eat_consumable', 'two_different_slots', 'same_entity_twice',
                    'restore_vanilla', 'ordinary_support_pod', 'weapon_backpack_pod', 'package_risk_replacement',
                    'live_verified_pair'):
            self.assertIn(key, result['scenarios'])

    def test_lua_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function rejects(r,t) local ok,why=pcall(patches.validate,r);assert(not ok and tostring(why):find(t,1,true),tostring(why)) end
local rack=hd2.booster('Surplus EAT Allocation'):granted_stratagem():delivery():rack()
assert(rack.rack=='EAT-17 Expendable Anti-Tank pod')
assert(hd2.stratagem('EAT-17 Expendable Anti-Tank'):payload().rack==rack.rack)
local eat=rack:slot(1):current();local supply=hd2.pickup('Supply Box')
patches.validate{id='a',target=rack:slot(1),field=hd2.fields.payload.entity,expect=eat,value=supply,
 allow_unverified_reference=true,allow_shared=true}
patches.validate{id='a2',target=rack:slot(2),field=hd2.fields.payload.entity,expect=eat,value=eat,allow_shared=true}
rejects({id='b',target=rack:slot(1),field=hd2.fields.payload.entity,expect=eat,value=supply,allow_shared=true},
 'allow_unverified_reference')
rejects({id='c',target=rack:slot(1),field=hd2.fields.payload.entity,expect=eat,value=supply,
 allow_unverified_reference=true},'allow_shared')
rejects({id='d',target=rack:slot(1),field=hd2.fields.payload.entity,expect=eat,value='0x49119612EB284A48',
 allow_unverified_reference=true,allow_shared=true},'not a reviewed pickup')
assert(not pcall(function()return rack:slot(5)end))
local maxigun=hd2.stratagem('M-1000 Maxigun'):payload()
assert(maxigun:slot(2):current().category=='backpack')
assert(#hd2.pickups('supply')==1 and #hd2.pickups()==68)
assert(not pcall(function()return hd2.stratagem('Orbital Laser'):payload()end))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
