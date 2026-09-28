import json
import re
import unittest

from support import ROOT


class AttachmentCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lists = json.loads((ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json').read_text())
        cls.research = json.loads((ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json').read_text())
        cls.magazines = json.loads((ROOT / 'sdk/MagazineAttachmentCapabilities.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/WeaponAttachmentCatalog.json').read_text())

    def test_unlock_lists_are_keyed_by_native_loadout_identity(self):
        weapons = self.lists['weapons']
        self.assertEqual(len(weapons), 52)
        self.assertTrue(all(item['weaponKind'] == 'player' and item['weapon'] for item in weapons))
        self.assertTrue(all(item['copies'] == 1 for item in weapons))
        self.assertEqual(len({item['loadoutItemId'] for item in weapons}), 52)
        self.assertTrue(all(option['known'] for item in weapons for option in item['options']))
        self.assertEqual(self.lists['layout']['header'], ['key', 'key', 0, 0, 'count', 'sequence'])

    def test_every_resolution_is_evidence_backed(self):
        by_path = {item['addPath']: item for item in self.research['magazineAttachments']}
        for weapon in self.research['weapons']:
            for option in weapon['catalogOptions']:
                relation = option['relationship']
                if relation == 'native_resource_default':
                    self.assertEqual(option['attachment'], weapon['nativeDefault'])
                elif relation == 'catalog_effects_unique':
                    self.assertEqual(option['candidates'], [option['attachment']])
                elif relation == 'catalog_effects_unlock_list':
                    self.assertGreater(len(option['candidates']), 1)
                    self.assertEqual(option['unlockListedCandidates'], [option['attachment']])
                    self.assertIn(option['attachment'], weapon['unlockListed'])
                else:
                    self.assertIsNone(option['attachment'])
                if option['attachment'] and option['effects']['fullReloadSeconds'] is not None:
                    native = by_path[option['attachment']]['effects']['reload']
                    if native:
                        self.assertAlmostEqual(native['value'], option['effects']['fullReloadSeconds'], places=2)

    def test_look_alike_options_resolve_to_their_own_weapon_variants(self):
        weapons = {item['weapon']: item['magazineSlot'] for item in self.magazines['weapons']}
        names = {item['semanticId']: item['name'] for item in self.magazines['attachments']}

        def option(weapon, name):
            return names[next(o for o in weapons[weapon]['options'] if o['name'] == name)['attachment']]
        self.assertEqual(option('AR-23 Liberator', 'Drum Magazine'), 'Rifle 5,5x50mm. Drum')
        self.assertEqual(option('AR-23A Liberator Carbine', 'Drum Magazine'), 'Rifle 5,5x50mm. Drum Carbine')
        self.assertEqual(option('AR-23A Liberator Carbine', 'Short Magazine'), 'Rifle 5,5x50mm. Standard Fastreload')
        self.assertEqual(option('SMG-37 Defender', 'Drum Magazine'), 'SMG 12x25mm. Drum')
        self.assertEqual(option('SMG-72 Pummeler', 'Drum Magazine'), 'SMG 12x25mm. Drum Pummeler')
        self.assertEqual(option('MP-98 Knight', 'Extended Magazine'), 'SMG 9x20mm. Top Mounted Extended')
        self.assertEqual(option('SMG-203 Gallant', 'Extended Magazine'), 'SMG 9x20mm. Top Mounted Extended Solvent')
        summary = self.magazines['summary']
        self.assertEqual((summary['resolvedOptions'], summary['unresolvedOptions']), (49, 3))
        self.assertTrue(all(field['allowSharedRequired'] and not field['reviewedScopeComplete']
            for field in self.magazines['fieldInstances']))

    def test_drum_publishes_its_consumers_and_effects(self):
        drum = next(item for item in self.magazines['attachments'] if item['name'] == 'Rifle 5,5x50mm. Drum')
        self.assertEqual(drum['compatibleWeapons'], ['AR-23 Liberator', 'AR-23A Liberator Carbine',
            'AR-23C Liberator Concussive', 'AR-23P Liberator Penetrator', 'AR-59 Suppressor'])
        self.assertFalse(drum['consumers']['scopeComplete'])
        effects = {item['effect']: item for item in drum['effects']}
        self.assertTrue(effects['reload_duration']['writable'])
        self.assertTrue(effects['stat_modifier']['writable'])
        self.assertFalse(effects['visual_magazine']['writable'])
        self.assertEqual(drum['values']['ergonomicsModifier'], -15)

    def test_generic_catalog_is_read_only_and_sanitized(self):
        summary = self.catalog['summary']
        self.assertEqual(summary['attachments'], 241)
        self.assertEqual(summary['writableEffects'], 0)
        self.assertTrue(all(not item['writable'] for item in self.catalog['attachments']))
        self.assertTrue(all(not effect['writable'] and effect['blocker']
            for item in self.catalog['attachments'] for effect in item['effects']))
        self.assertIsNone(re.search(r'\b0x[0-9a-f]{6,}', json.dumps(self.catalog).lower()))
        magazine_ids = {item['semanticId'] for item in self.magazines['attachments']}
        linked = {item['magazineAuthoring'] for item in self.catalog['attachments'] if item['magazineAuthoring']}
        self.assertEqual(linked, magazine_ids)
        brake = next(item for item in self.catalog['attachments']
            if item['name'] == '5,5mm. Muzzle brake Custom Penetrator')
        self.assertEqual([m['type'] for m in brake['statModifiers']],
            ['Add_Ergonomics', 'Mul_Sway', 'Mul_RecoilHorizontal', 'Mul_ClimbHorizontal'])


if __name__ == '__main__':
    unittest.main()
