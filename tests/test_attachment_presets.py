import copy
import importlib.util
import json
import struct
import unittest

from support import ROOT


spec = importlib.util.spec_from_file_location(
    'attachment_research', ROOT / 'scripts/research_attachment_presets.py')
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


class AttachmentPresetResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads((ROOT / 'build/weapon-composition-raw.json').read_text())
        cls.state = research.state_from_composition_raw(cls.raw, 'current_snapshot_unknown_preset')
        cls.reports = research.build_reports([cls.state])

    def test_catalog_is_complete_and_all_new_paths_fail_closed(self):
        selection = self.reports['selection']
        effects = self.reports['effects']
        self.assertEqual(selection['summary']['attachmentOptions'], 419)
        self.assertEqual(selection['summary']['magazineOptions'], 36)
        self.assertEqual(selection['summary']['knownNativeOptionCatalogIdentities'], 52)
        self.assertEqual(selection['summary']['nativeIdentitiesTiedToRows'], 13)
        self.assertEqual(selection['summary']['knownNativeHeatsinkIdentities'], 9)
        self.assertEqual(selection['summary']['writableSelections'], 0)
        self.assertEqual(effects['summary']['optionEffectOwnersProven'], 0)
        self.assertEqual(effects['summary']['writableEffectFields'], 0)
        self.assertTrue(all(not row['writable'] for row in selection['options']))
        self.assertTrue(all(not row['writable'] for row in effects['options']))

    def test_static_defaults_are_not_claimed_as_current_or_saved_presets(self):
        preset = self.reports['preset']
        self.assertFalse(preset['ownershipFindings']['weaponPresetStateFound'])
        self.assertIsNone(preset['ownershipFindings']['selectedAttachmentOwner'])
        self.assertIsNone(preset['ownershipFindings']['savedPresetOwner'])
        self.assertIn('not proven current player selection',
            preset['nativeLayout']['defaultDefinitions']['meaning'])
        self.assertEqual(preset['summary']['nativeDefaultRelationships'], 20)

    def test_ar23c_magazine_fingerprints_remain_distinct(self):
        source = json.loads((ROOT.parent / 'HD2WikiImporter/output/wiki_primary_weapon_attachments.json').read_text())
        weapon = next(item for item in source['weapons']
            if item['name'] == 'AR-23C Liberator Concussive')
        values = {item['name']: item['magazineCorrelation']
            for item in weapon['optionsByCategory']['Magazine']}
        self.assertEqual(values['Drum Magazine']['capacity'], 60)
        self.assertEqual(values['Short Magazine']['capacity'], 30)
        self.assertEqual(values['Extended Magazine']['capacity'], 45)
        self.assertEqual(values['Drum Magazine']['maxMagazines'], 6)
        self.assertEqual(values['Short Magazine']['partialReloadSeconds'], 1.65)

    def test_targeted_diff_reports_only_changed_reviewed_component_bytes(self):
        after = copy.deepcopy(self.state)
        after['label'] = 'short_selected'
        weapon = next(item for item in after['weapons']
            if item['weapon'] == 'AR-23C Liberator Concussive')
        component = weapon['components']['WeaponCustomizationComponentData']
        body = bytearray.fromhex(component['bytes'])
        struct.pack_into('<I', body, 4, 0x12345678)
        component['bytes'] = body.hex()
        comparison = research.compare_states(self.state, after)
        self.assertEqual(comparison['changedRecords'], 1)
        change = comparison['changes'][0]
        self.assertEqual(change['component'], 'WeaponCustomizationComponentData')
        self.assertEqual(change['ranges'][0]['offset'], 4)
        self.assertNotEqual(change['beforeDefaultDefinitions'], change['afterDefaultDefinitions'])

    def test_single_snapshot_report_requests_lifecycle_captures_and_is_read_only(self):
        report = self.reports['diff']
        self.assertEqual(report['summary']['result'], 'INSUFFICIENT_STATE_CAPTURES')
        self.assertEqual(report['summary']['comparisons'], 0)
        self.assertFalse(report['scope']['broadNumericScan'])
        for artifact in self.reports.values():
            self.assertEqual(artifact['safety']['writes'], 0)
            self.assertEqual(artifact['safety']['protectionChanges'], 0)
            self.assertEqual(artifact['safety']['fixtureFallback'], 'disabled')

    def test_generated_artifacts_are_current(self):
        for name, path in research.OUTPUTS.items():
            self.assertEqual(json.loads(path.read_text()), self.reports[name])


if __name__ == '__main__':
    unittest.main()
