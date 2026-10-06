"""The carrier pod (runtime/carrier_pod.lua, domains/carrier_pod_items.lua; docs/research/carrier-pod-items-F5FEE03DCFDB.md
section 11):
  * research/carrier-pod-nodes-F5FEE03DCFDB.json: read-only; every weapon and backpack rack but the One True Flag's names
    ONE unit; the Leveller's slot 1 is EMPTY inside its spawn count at attach_1, a node of that unit, so its capacity is
    2; every exclusive rack's capacity counts only usable slots (inside the spawn count, a node of its unit, distinct);
  * the generated domain is up to date with the research;
  * offline guards without memory: an unknown option, outside a mission, an unexplained plan;
  * on every retained snapshot (when present): scripts/validate_carrier_pod_snapshot.py (each planned slot exact,
    leftovers emptied, every other byte unchanged, protection restored, exact restore, CONFLICT / NOT_NATIVE /
    CARRIER_CALLED / ASSET_UNAVAILABLE refusals with nothing written, NOT_IN_MISSION aboard the ship)."""
import importlib.util
import json
import unittest

from support import ROOT, run

import build_profile

NODES = ROOT / 'research/carrier-pod-nodes-F5FEE03DCFDB.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CarrierPodResearchTests(unittest.TestCase):
    @unittest.skipUnless(NODES.is_file(), 'the carrier pod nodes research is absent')
    def test_the_rack_nodes(self):
        r = json.loads(NODES.read_text(encoding='utf-8'))
        self.assertEqual(r['writes'], 0)
        self.assertEqual(r['unit']['resource'], '0xB52BEAAE4F85C391')
        self.assertEqual(r['unit']['sceneGraph']['nodes'], 56)
        self.assertEqual(r['unit']['namedNodes']['attach_1'], 17)
        self.assertEqual(r['unit']['racks'], 51)
        racks = {x['carrier']: x for x in r['racks'] if x['carrier']}
        leveller = racks['EAT-411 Leveller']
        self.assertEqual((leveller['spawnPayloadSize'], leveller['capacity'], leveller['vanillaPopulated']), (2, 2, 1))
        slot1 = leveller['slots'][1]
        self.assertEqual((slot1['item'], slot1['node']['name'], slot1['node']['index'], slot1['rackSide'],
            slot1['usable'], slot1['role']), (None, 'attach_1', 17, 1, True, 'weapon'))
        for x in r['racks']:
            if not x['exclusiveCarrierRack']:
                continue
            self.assertTrue(x['sharedUnit'] or x['carrier'] == 'CQC-1 One True Flag', x['path'])
            self.assertEqual(x['capacity'], len(x['usableSlots']))
            self.assertLessEqual(x['capacity'], x['spawnPayloadSize'])
            nodes = [x['slots'][i]['node']['hash'] for i in x['usableSlots']]
            self.assertEqual(len(nodes), len(set(nodes)), x['path'])
            for i in x['usableSlots']:
                self.assertTrue(x['slots'][i]['node']['inUnit'])
                self.assertIn(x['slots'][i]['role'], ('weapon', 'backpack'))
        self.assertEqual(racks['EAT-700 Expendable Napalm']['capacity'], 2)
        self.assertEqual(racks['AC-8 Autocannon']['slots'][1]['role'], 'backpack')
        self.assertEqual(racks['M-105 Stalwart']['capacity'], 1)

    def test_the_generated_domain_is_current(self):
        generator = load('generate_carrier_pod_items', 'scripts/generate_carrier_pod_items.py')
        self.assertEqual(generator.generate(check=True), [])

    def test_the_offline_guards(self):
        out = run(r"""
local pod=require('hd2runtime/runtime/carrier_pod');pod.reset_for_tests()
local json=require('hd2runtime/primary_mapper/json')
local function settle(job)for _=1,50 do if job.status~='pending'then break end;update(0.1)end;return job end
local codes={}
local unit={{role='weapon',resource='0x7617642765AC38C7',label='clone'}}
for _,s in ipairs({{carrier='EAT-411 Leveller',items=unit,colour='red'},
    {carrier='EAT-17 Expendable Anti-Tank',items=unit},
    {carrier='EAT-411 Leveller',items={}},
    {carrier='EAT-411 Leveller',items=unit}})do
    codes[#codes+1]=settle(pod.apply(s)).code
end
local item,why=pod.item({resource='backpack',backpack='B-1 Supply Pack'})
local primary=pod.item({resource='player_weapon',weapon='JAR-5 Dominator'})
local _,sidearm=pod.item({resource='player_weapon',weapon='P-2 Peacemaker'})
return json.encode({codes=codes,applied=pod.applied(),backpack=item.kind..'/'..item.role..'/'..item.status,
    primary=primary.status,sidearm=sidearm})
""")
        r = json.loads(out)
        self.assertEqual(r['codes'][:3], ['INVALID', 'NO_EXCLUSIVE_RACK', 'INVALID'])
        self.assertIn(r['codes'][3], ('UNAVAILABLE', 'NOT_IN_MISSION'))
        self.assertFalse(r['applied'])
        self.assertEqual(r['backpack'], 'backpack/backpack/confirmed')
        self.assertEqual(r['primary'], 'unverified')
        self.assertIn('cannot be a pod item', r['sidearm'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_every_retained_snapshot(self):
        module = load('validate_carrier_pod_snapshot', 'scripts/validate_carrier_pod_snapshot.py')
        names = [n for n in module.SNAPSHOTS if (build_profile.snapshot_directory() / n).is_file()]
        results = module.validate(tuple(names))
        for name, result in results.items():
            self.assertTrue(result['passed'], name + ': ' + '; '.join(result['problems']))
        live = [r for r in results.values() if r['phase'] in ('alive', 'reinforced')]
        self.assertTrue(live, 'no live mission snapshot validated')
        for result in live:
            leveller = result['report']['cases'][0]
            self.assertEqual((leveller['carrier'], leveller['apply']['slots']), ('EAT-411 Leveller', 1))


if __name__ == '__main__':
    unittest.main()
