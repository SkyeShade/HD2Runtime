"""The loadout pod research (docs/research/loadout-pod-F5FEE03DCFDB.md, research/loadout-pod-F5FEE03DCFDB.json):
read-only, every pin identical in every snapshot, and the facts the design rests on: the weapon pickup case and its
slots, the rack spawning its items inside its own creation, the WeaponData private copy and the selector reading it,
the ammunition source chosen by components, and what is refused."""
import json
import unittest

from support import ROOT

PATH = ROOT / 'research/loadout-pod-F5FEE03DCFDB.json'


@unittest.skipUnless(PATH.is_file(), 'research/loadout-pod-F5FEE03DCFDB.json is absent')
class LoadoutPodResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(PATH.read_text(encoding='utf-8'))

    def test_read_only_and_pinned(self):
        r = self.r
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        roles = {p['rva'] for rows in r['pins'].values() for p in rows}
        for rva in (0x97C940, 0x938B2E, 0x509AE9, 0x575ACB, 0x7554DD, 0x756805, 0x612CD7, 0x742B43, 0x772588):
            self.assertIn(rva, roles)

    def test_pickup_slots(self):
        i = self.r['interaction']
        self.assertEqual(i['cases']['0x97C940'], [1, 2, 3])
        self.assertIn(13, i['cases']['0x97D63A'])
        self.assertEqual(i['names']['1'], 'PickupWeaponPrimary')
        self.assertEqual(i['weaponCaseSlots']['PickupWeaponPrimary'], 1)
        jar = self.r['entities']['JAR-5 Dominator']
        self.assertEqual(jar['interactZones'], ['PickupWeaponPrimary'])
        self.assertEqual(jar['loadoutItemType'], 1)
        for item in ('M-1000 Maxigun', 'M-1000 Maxigun Backpack', 'M-105 Stalwart'):
            self.assertEqual(self.r['entities'][item]['interactZones'][0], 'PickupHellpod')
        self.assertEqual(self.r['podPayloadCatalog']['primariesInRacksOrLoot'], [])

    def test_fire_modes_and_private_copies(self):
        jar = self.r['entities']['JAR-5 Dominator']['weaponData']
        self.assertEqual((jar['modes'], jar['functions'], jar['owners']), ([2, 3, 0, 0], [0, 3], 1))
        self.assertEqual(self.r['weaponDataLayout']['copies'], '0xB0')
        self.assertEqual(self.r['weaponDataLayout']['copyStride'], '0x4D0')
        for o in self.r['observations']:
            self.assertTrue(o['componentWorldAgrees'])
            copies = [x for x in o['instances'] if x['copy']]
            self.assertEqual(len(copies), o['copyCount'])
            for x in o['instances']:
                self.assertEqual(x['modeIndex'], 0)
                self.assertEqual(x['currentMode'], x['typeModes'][0])
                if x['copy']:
                    self.assertEqual(x['copy']['modes'], x['typeModes'])
        ship = [c for c in self.r['jar5PrivateCopiesObserved'] if c['label'] == 'jet_rifle']
        self.assertTrue(ship and ship[0]['modes'] == [2, 3, 0, 0])

    def test_ammunition_source(self):
        e = self.r['entities']
        self.assertNotIn('WeaponLinkedAmmo', e['JAR-5 Dominator']['components'])
        self.assertIn('WeaponMagazine', e['JAR-5 Dominator']['components'])
        self.assertEqual(e['M-1000 Maxigun']['linkedAmmo']['inventorySlot'], 6)
        self.assertNotIn('WeaponMagazine', e['M-1000 Maxigun']['components'])
        self.assertIn('Deposit', e['M-1000 Maxigun Backpack']['components'])
        linked = [x for o in self.r['observations'] for x in o['instances'] if 10 in x.get('weaponFlags', [])]
        self.assertTrue(all(x['label'] == 'seaf_gun' for x in linked))
        self.assertIn('arc_thrower', self.r['weaponDataByte952']['nonZeroOwners'])

    def test_design_and_refusals(self):
        self.assertEqual([s['stage'] for s in self.r['stages']], ['A', 'B', 'C'])
        refused = ' '.join(x['request'] for x in self.r['refused'])
        self.assertIn('pod rack', refused)
        self.assertIn('native ammunition link', refused)
        self.assertIn('player\'s own', refused)
        self.assertEqual(self.r['answers']['q3_backpackFedAmmo']['nativeLinkForJar5']['label'], 'CONFIRMED (blocked)')
        self.assertEqual(self.r['packages']['jar5']['package'], '0x10A7605527187EF5')
        self.assertFalse(self.r['maxigunRack']['ownerCount'] > 1)


if __name__ == '__main__':
    unittest.main()
