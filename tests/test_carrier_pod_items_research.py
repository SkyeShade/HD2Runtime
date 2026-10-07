"""The carrier pod items research (research/docs/carrier-pod-items-F5FEE03DCFDB.md,
research/carrier-pod-items-F5FEE03DCFDB.json): read-only, every pin identical in every snapshot, and the facts the
design rests on: the type-agnostic rack spawner, the generic placement and release, the item kinds' pickup zones and
the One True Flag precedent, the exclusive carrier racks, and what stays refused."""
import json
import unittest

from support import ROOT

PATH = ROOT / 'research/carrier-pod-items-F5FEE03DCFDB.json'


@unittest.skipUnless(PATH.is_file(), 'research/carrier-pod-items-F5FEE03DCFDB.json is absent')
class CarrierPodItemsResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(PATH.read_text(encoding='utf-8'))
        cls.items = {i['key']: i for i in cls.r['itemCatalog']['items']}
        cls.racks = {r['resource']: r for r in cls.r['carrierRacks']['racks']}

    def test_read_only_and_pinned(self):
        r = self.r
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        rvas = {p['rva'] for rows in r['pins'].values() for p in rows}
        for rva in (0x938B2E, 0x935A73, 0x935A97, 0x93573C, 0x93572E, 0x9355ED, 0x934970, 0x978BD3, 0x935EB2,
                0x97F28A, 0xB57914, 0xB57A71, 0x97C949, 0x97C9F4):
            self.assertIn(rva, rvas)
        bind = next(p for p in r['pins']['rackPlacement'] if p['rva'] == 0x935E96)
        self.assertEqual(bind['ripTarget'], 0x33267F8)

    def test_interaction_cases(self):
        i = self.r['interaction']
        self.assertEqual(i['cases']['0x97C940'], [1, 2, 3])
        self.assertIn(13, i['cases']['0x97D63A'])
        self.assertEqual(i['cases']['0x97D677'], [14])
        self.assertEqual(i['names']['14'], 'PickupThrowable')

    def test_zone_flags_and_precedent(self):
        z = self.r['zoneComparison']['entities']
        self.assertEqual(z['JAR-5 Dominator']['zones'], [1])
        self.assertEqual(z['JAR-5 Dominator']['flags']['1'], z['EAT-17 Expendable Anti-Tank']['flags']['3'])
        self.assertEqual(z['CQC-1 One True Flag']['zones'], [3])
        self.assertFalse(z['CQC-1 One True Flag']['entityBind'])
        self.assertFalse(z['JAR-5 Dominator']['entityBind'])
        flag = self.items['support_weapon/CQC-1 One True Flag']
        self.assertTrue(flag['vanillaRacks'])
        self.assertFalse(flag['hellpodZone'])

    def test_item_verdicts(self):
        jar = self.items['player_weapon/JAR-5 Dominator']
        self.assertEqual((jar['kind'], jar['verdict'], jar['confidence']), ('primary', 'CANDIDATE', 'STRONG'))
        self.assertEqual(jar['package'], '0x10A7605527187EF5')
        for item in self.items.values():
            if item['kind'] == 'throwable':
                self.assertEqual(item['verdict'], 'REFUSED_THROWABLE')
            if item['verdict'] == 'CANDIDATE':
                self.assertTrue(item['hasPickupZone'])
            if item['kind'] in ('primary', 'sidearm') and not item['hasPickupZone']:
                self.assertEqual(item['verdict'], 'REFUSED_NO_PICKUP_ZONE')
        summary = self.r['itemCatalog']['summary']
        self.assertEqual(summary['primary'], {'CANDIDATE': 56})
        self.assertNotIn('CANDIDATE', summary['throwable'])

    def test_exclusive_carrier_racks(self):
        for rack in self.racks.values():
            if rack['exclusiveCarrierRack']:
                self.assertEqual(rack['recordOwnerCount'], 1)
                self.assertEqual(len(rack['consumers']), 1)
                self.assertTrue(rack['carrier'])
                self.assertEqual(rack['randomPayloadSize'], 0)
                self.assertGreaterEqual(rack['maxItems'], 1)
                self.assertNotIn(rack['resource'], self.r['outsideReferences']['gameDll'])
            else:
                self.assertTrue(rack['reasons'])
        shared = {'0x0DC7A18342B62BEC', '0x94C5114EBA59AA21', '0x61353DF120F27732', '0x77C52E494527AA8A'}
        for resource in shared:
            self.assertFalse(self.racks[resource]['exclusiveCarrierRack'])
        self.assertIn('M-1000 Maxigun', self.r['carrierRacks']['exclusiveByMaxItems']['2'])
        self.assertEqual(set(self.r['carrierRacks']['exclusiveByMaxItems']), {'1', '2'})

    def test_design_is_refusing(self):
        refused = ' '.join(x['request'] for x in self.r['refused'])
        for word in ('throwables', 'shared', 'after the first call', 'multiplayer'):
            self.assertIn(word, refused)
        stages = [s['stage'] for s in self.r['stages']]
        self.assertEqual(stages[:3], ['A', 'B', 'C'])


if __name__ == '__main__':
    unittest.main()
