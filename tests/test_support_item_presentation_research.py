"""The support item presentation research (docs/research/support-item-presentation-F5FEE03DCFDB.md,
research/support-item-presentation-F5FEE03DCFDB.json): read-only, its pins identical in every snapshot, and the facts
the design rests on: every icon and name consumer reads the TYPE records (EncyclopediaEntry, Spottable), neither table
has an instance copy, the EAT-17's marker icon is its stratagem icon, and the EAT-700 is the only EAT-compatible
carrier weapon."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/support-item-presentation-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class SupportItemPresentationResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        self.assertIn(0x18277CC, roles)     # HUD weapon panel: EncyclopediaEntry +0x30
        self.assertIn(0x1826999, roles)     # ... rebuilt on a wielded-entity change
        self.assertIn(0xFFC404, roles)      # prompt: Spottable +0x38
        self.assertIn(0xFFC4F6, roles)      # prompt: EncyclopediaEntry +8
        self.assertIn(0x18B1ACA, roles)     # minimap: Spottable +0x38
        self.assertIn(0x509359, roles)      # Equipment has an instance copy (the only one of the three)

    def test_type_tables_are_read_in_place_without_instance_copies(self):
        self.assertTrue(all(all(v.values()) for v in RESEARCH['typeTables']['inPlaceInEverySnapshot'].values()))
        covers = RESEARCH['census']['instanceCopySwitchCovers']
        self.assertFalse(covers['EncyclopediaEntryComponentData'])
        self.assertFalse(covers['SpottableComponentData'])
        self.assertTrue(covers['EquipmentComponentData'])
        direct = RESEARCH['census']['directTableReaders']
        self.assertEqual([r['function'] for r in direct['SpottableComponentData']], [0x4FE440])
        self.assertFalse(any(v['markerIconFound'] for v in RESEARCH['snapshots']['spottableInstanceBlockHoldsAnIcon']
            .values()))
        readers = RESEARCH['census']['memberReaders']
        self.assertIn('0xFFB710', readers['spottable+0x38 marker_icon'])
        self.assertIn('0x1827740', readers['encyclopedia+0x30 icon'])

    def test_eat17_values(self):
        eat = RESEARCH['weapons']['lat_oneshot']
        self.assertEqual(eat['spottable']['marker_icon'], '0xCF20900C57479CA6')   # = StratagemInfo +0xB0 of 147
        self.assertEqual(eat['spottable']['marker_texture_type'], 2)
        self.assertEqual(eat['encyclopedia']['text']['name'], 'EXPENDABLE ANTI-TANK')
        self.assertEqual(eat['interactZoneLabel']['text'], '#ITEM')
        self.assertTrue(all(r['nameIsEncyclopediaUpper'] for r in eat['stratagemRows']))
        self.assertEqual({r['type'] for r in eat['stratagemRows']}, {15, 147})
        self.assertTrue(RESEARCH['checks']['everyRecordOneOwner'])

    def test_carrier_weapon(self):
        compatible = [c for c in RESEARCH['carrierCandidates'] if c['eatCompatible']]
        self.assertEqual([c['weapon'] for c in compatible], ['expendable_napalm_launcher'])
        eat700 = compatible[0]
        self.assertFalse(eat700['inWorldLoot'])
        self.assertEqual(eat700['deliveredBy'], ['EAT-700 Expendable Napalm'])
        self.assertEqual(sorted(eat700['projectile']['differsFromEat17'], key=int), ['0', '4', '8', '60', '144'])
        eat17 = next(c for c in RESEARCH['weapons'].values() if c['resource'] == '0x80932FA0ED6901D3')
        self.assertEqual(eat17['equipment']['equipment_type'], eat700['equipmentType'])
        for snapshot, categories in RESEARCH['snapshots']['loadoutWeaponCategory'].items():
            self.assertEqual(categories, {'EAT-17': 2, 'EAT-700': 2, 'EAT-411': 2}, snapshot)


if __name__ == '__main__':
    unittest.main()
