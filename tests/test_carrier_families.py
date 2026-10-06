"""Carrier families (scripts/research_carrier_families.py -> research/carrier-families-F5FEE03DCFDB.json): every
catalogued stratagem row classified by the fields the game's call-in system and UI read (delivery kind +0x3C,
category +0xB8, selectable/enabled), checked against the catalogue's own families."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/carrier-families-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class CarrierFamilyTests(unittest.TestCase):
    def test_read_only_and_complete(self):
        self.assertEqual(RESEARCH['writes'], 0)
        counts = {k: v['count'] for k, v in RESEARCH['families'].items()}
        self.assertEqual(counts, {'offensive': 20, 'support': 45, 'deployable': 18, 'vehicle': 9, 'special': 2})

    def test_the_families_by_native_fields(self):
        families = RESEARCH['families']
        self.assertEqual((families['offensive']['categories'], families['offensive']['kinds']), ([0], [0, 1, 5]))
        self.assertEqual((families['support']['categories'], families['support']['kinds']), ([2], [2]))
        self.assertEqual((families['deployable']['categories'], families['deployable']['kinds']), ([3], [2]))
        self.assertEqual(families['vehicle']['kinds'], [3])
        by_name = {s['name']: s for s in RESEARCH['stratagems']}
        self.assertEqual(by_name['AC-8 Autocannon']['family'], 'support')
        self.assertEqual(by_name['A/G-16 Gatling Sentry']['family'], 'deployable')
        self.assertEqual(by_name['MD-6 Anti-Personnel Minefield']['beam'], 1)        # a red beam on a deployable
        self.assertEqual(by_name['Eagle Strafing Run']['family'], 'offensive')
        self.assertTrue(by_name['Eagle Strafing Run']['eagle'] and by_name['Eagle Strafing Run']['rearm'])
        self.assertEqual(by_name['Orbital 120mm HE Barrage']['family'], 'offensive')
        # Every Eagle has limited uses and links Eagle Rearm; every support and deployable is unlimited.
        self.assertTrue(all(s['uses'] > 0 and s['rearm'] for s in RESEARCH['stratagems'] if s['eagle']))
        self.assertEqual(families['support']['unlimited'], 45)
        self.assertEqual(families['deployable']['unlimited'], 18)


if __name__ == '__main__':
    unittest.main()
