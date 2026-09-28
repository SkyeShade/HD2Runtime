import json
import unittest

from support import ROOT


class SupportWeaponCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/support-weapon-coverage-F5FEE03DCFDB.json').read_text())
        cls.capabilities = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_projectile_offsets_are_decided_by_name_length_and_correlation(self):
        layout = self.research['fieldLayout']
        self.assertEqual((layout['projectile.lifetime']['offset'], layout['projectile.lifetime']['hiddenNameLength']),
            (52, 9))
        self.assertEqual(layout['projectile.penetration_slowdown']['offset'], 64)
        self.assertEqual(self.research['projectileLabelConflict']['hiddenNameLengthAt56'], 20)
        results = self.research['projectileCorrelation']['results']
        self.assertEqual(results['lifetime52'], {'matches': 5, 'mismatches': 0})
        self.assertEqual(results['lifetime56']['matches'], 0)
        self.assertEqual(results['penetration64'], {'matches': 27, 'mismatches': 0})
        self.assertTrue(self.research['liveEquality']['projectileSettings']['identical'])
        self.assertTrue(all(item['indexAndRecordsIdentical']
            for item in self.research['liveEquality']['entityTables'].values()))

    def test_zero_valued_natives_stay_read_only(self):
        instances = self.capabilities['fieldInstances']
        for item in instances:
            if item['semanticFieldId'] in ('projectile.lifetime', 'reload.duration'):
                self.assertNotEqual(item['value']['baseline'], 0, item['instanceKey'])
        weapons = {w['name']: w for w in self.capabilities['weapons']}
        for name in ('TX-41 Sterilizer', 'FLAM-40 Flamethrower', 'PLAS-45 Epoch'):
            self.assertTrue(any(block['field'] == 'reload.duration' for block in weapons[name]['blockedFields']), name)
        self.assertTrue(any(block['field'] == 'projectile.lifetime'
            for block in weapons['GR-8 Recoilless Rifle']['blockedFields']))

    def test_unverified_fields_require_acknowledgement(self):
        acknowledged = {}
        for item in self.capabilities['fieldInstances']:
            acknowledged.setdefault(item['semanticFieldId'], set()).add(item['operation']['acknowledgement'])
        self.assertEqual(acknowledged['reload.duration'], {'allow_unverified_effect'})
        self.assertEqual(acknowledged['windup.wind_down_seconds'], {'allow_unverified_effect'})
        self.assertEqual(acknowledged['windup.wind_up_seconds'], {None})
        self.assertEqual(acknowledged['projectile.lifetime'], {None})
        self.assertEqual(len([i for i in self.capabilities['fieldInstances']
            if i['semanticFieldId'] == 'reload.duration']), 14)

    def test_delivery_resolution_requires_structure_and_fingerprint(self):
        delivery = self.research['deliveryResolution']
        resolved = {name for name, item in delivery.items() if item['decision'] == 'RESOLVED'}
        self.assertEqual(resolved, {'MG-43 Machine Gun', 'M-105 Stalwart', 'MG-206 Heavy Machine Gun',
            'CQC-20 Breaching Hammer'})
        for name in resolved:
            item = delivery[name]
            self.assertEqual(item['structurallyDelivered'], [item['deliveredRoot']])
            confirmed = [root for root in item['fingerprint']['roots'] if root['matchesWiki']]
            self.assertEqual([root['resource'] for root in confirmed], [item['deliveredRoot']])
        for name in ('EAT-17 Expendable Anti-Tank', 'LAS-98 Laser Cannon', 'B/FLAM-80 Cremator'):
            self.assertEqual(delivery[name]['decision'], 'BLOCKED')
            self.assertEqual(len(delivery[name]['structurallyDelivered']), 1)
        self.assertIn('No uniquely correlated call-in', delivery['CQC-72 Entrenchment Tool']['reason'])


if __name__ == '__main__':
    unittest.main()
