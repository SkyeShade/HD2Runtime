import importlib.util
import json
import re
import struct
import unittest

from support import ROOT


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StratagemIconIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json').read_text())
        cls.support = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())

    def test_research_chain_is_complete_and_unique(self):
        r = self.research
        self.assertEqual(r['enum'], 'StratagemType')
        self.assertEqual([t['value'] for t in r['types']], list(range(r['enumValues'])))
        self.assertEqual((r['types'][0]['name'], r['types'][-1]['name']), ('None', 'Count'))
        self.assertTrue(r['nameTable']['lengthsMatchTypeLibrary'])
        types = [row['type'] for row in r['rows']]
        self.assertEqual(len(types), len(set(types)))
        self.assertEqual(len({row['id'] for row in r['rows']}), len(r['rows']))
        bound = [t for t in r['types'] if t['iconKey']]
        self.assertEqual(len(bound), r['iconLibrary']['typeBindings'])
        self.assertTrue(all(t['template'] == ('empty' if t['iconKey'] in r['iconLibrary']['emptyTemplates'] else 'vector')
            for t in bound))

    def test_every_resolved_root_publishes_its_native_icon_identity(self):
        by_id = {row['id']: row['type'] for row in self.research['rows']}
        internal = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text())['stratagems']
        types = {t['value']: t for t in self.research['types']}
        states = {}
        for item in self.catalog['stratagems']:
            icon = item['uiIcon']; states[icon['state']] = states.get(icon['state'], 0) + 1
            if icon['state'] == 'no_native_root':
                self.assertNotEqual(item['rootResolution'], 'UNIQUE'); self.assertIsNone(icon['iconKey'])
                self.assertIsNone(icon['provenance'])
                self.assertEqual(icon['blocker'], {'kind': 'no_native_root',
                    'rootResolution': item['rootResolution'], 'reason': icon['reason']})
                continue
            self.assertEqual(icon['provenance']['basis'], 'native_stratagem_type')
            self.assertEqual(icon['provenance']['displayNameEquality'], 'not used')
            native = types[by_id[internal[item['name']]['root']['id']]]
            self.assertEqual((icon['nativeType'], icon['nativeTypeValue'], icon['iconKey']), (native['name'], native['value'], native['iconKey']))
            if icon['state'] == 'resolved':
                self.assertEqual(icon['library'], self.catalog['uiIconContract']['library'])
                self.assertNotIn(icon['iconKey'], self.catalog['uiIconContract']['emptyTemplates'])
                self.assertIsNone(icon['blocker'])
            else:
                self.assertTrue(icon['reason'])
                self.assertEqual(icon['blocker'], {'kind': icon['state'], 'reason': icon['reason']})
        self.assertEqual(states, self.catalog['summary']['uiIconStates'])
        # Resupply's StratagemRessuply template has no vector artwork in this build (empty_template).
        self.assertEqual(states, {'resolved': 84, 'empty_template': 5, 'unbound': 5, 'no_native_root': 2})
        keys = [x['uiIcon']['iconKey'] for x in self.catalog['stratagems'] if x['uiIcon']['state'] == 'resolved']
        self.assertEqual(len(keys), len(set(keys)))

    def test_icon_contract_publishes_no_artwork_or_native_addresses(self):
        contract = self.catalog['uiIconContract']
        self.assertEqual((contract['contract'], contract['schemaVersion']), ('hd2runtime.stratagem.ui_icon.v1', 1))
        self.assertEqual(set(contract['states']), {'resolved', 'empty_template', 'unbound', 'no_native_root'})
        self.assertFalse(contract['artworkPublished'])
        text = json.dumps([contract] + [x['uiIcon'] for x in self.catalog['stratagems']])
        self.assertNotRegex(text, r'\b0x[0-9a-fA-F]+\b')
        self.assertNotIn('<path', text); self.assertNotIn('rva', text)

    def test_no_game_artwork_is_shipped(self):
        # Only identity/key metadata ships; the icon library itself never enters the repo or an artifact.
        for folder in ('sdk', 'starter', 'domains', 'research'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file():
                    self.assertNotIn(path.suffix.lower(), {'.xaml', '.png', '.svg', '.dds'}, str(path))

    def test_catalog_equipment_is_presentation_only_and_never_ownership(self):
        weapons = {w['semanticId']: w for w in self.support['weapons']}
        support = [x for x in self.catalog['stratagems'] if x['family'] == 'support']
        self.assertEqual(len(support), 35)
        self.assertTrue(all('catalogEquipment' in x for x in support))
        self.assertFalse(any('catalogEquipment' in x for x in self.catalog['stratagems'] if x['family'] != 'support'))
        for item in support:
            pair = item['catalogEquipment']; weapon = weapons[pair['supportWeapon']]
            self.assertEqual(weapon['name'], pair['supportWeaponName'])
            proven = item['delivers']['known'] is True and item['delivers']['semanticId'] == pair['supportWeapon']
            self.assertEqual(pair['nativeDeliveryProven'], proven)
            # The association never promotes a link: forward and reverse links are unchanged.
            self.assertEqual(weapon['linkedStratagem']['known'], proven)
        only = sorted(x['name'] for x in support if not x['catalogEquipment']['nativeDeliveryProven'])
        self.assertEqual(only, ['CQC-72 Entrenchment Tool', 'SG-88 Break-Action Shotgun'])
        self.assertEqual(only, self.catalog['summary']['catalogOnlyEquipment'])
        c4 = next(x for x in support if x['name'] == 'B/MD C4 Pack')
        # 0.25.0 links C4 through native loadout identity, so its catalog pair is also delivery-proven.
        self.assertTrue(c4['delivers']['known']); self.assertEqual(c4['delivers']['special'], 'placed_item')
        self.assertTrue(c4['catalogEquipment']['nativeCallInResolved'])
        self.assertTrue(c4['catalogEquipment']['nativeDeliveryProven'])
        self.assertIn('catalog cooldown 480 s equals the native definition cooldown', c4['catalogEquipment']['corroboration'])
        self.assertEqual(c4['uiIcon']['iconKey'], 'StratagemC4')

    def test_name_table_requires_a_unique_length_corroborated_run(self):
        research = load('research_stratagem_icons', 'scripts/research_stratagem_icons.py')
        base = 0x1000
        names = ['None', 'Alpha', 'Beta', 'Count']
        blob = bytearray(b'\0' * 64); addresses = []
        for name in names + ['Gamma']:
            addresses.append(base + len(blob)); blob += name.encode() + b'\0'
        blob += b'\0' * (-len(blob) % 8)
        table = len(blob); blob += b''.join(struct.pack('<Q', a) for a in addresses[:4])
        lengths = {i: len('StratagemType_' + n) for i, n in enumerate(names)}
        self.assertEqual(research.name_table(base, bytes(blob), lengths), (table, names))
        with self.assertRaises(ValueError):
            research.name_table(base, bytes(blob), {**lengths, 1: lengths[1] + 1})

    def test_bindings_parse_only_the_type_template(self):
        research = load('research_stratagem_icons', 'scripts/research_stratagem_icons.py')
        xaml = ('<ResourceDictionary><DataTemplate x:Key="StratagemA"><Viewbox><Canvas Width="1" Height="1"><Path Data="M0 0Z"/></Canvas></Viewbox></DataTemplate>'
            '<DataTemplate x:Key="StratagemB"><Viewbox><Canvas Width="1" Height="1"></Canvas></Viewbox></DataTemplate>'
            '<DataTemplate x:Key="StratagemTypeDataTemplate"><ContentControl/><DataTemplate.Triggers>'
            '<DataTrigger Binding="{Binding}" Value="Alpha">\n<Setter TargetName="StratagemIconsContentControl" Property="ContentTemplate" Value="{DynamicResource StratagemA}"/>'
            '</DataTrigger></DataTemplate.Triggers></DataTemplate></ResourceDictionary>')
        bound, vector, keys = research.bindings(xaml)
        self.assertEqual(bound, {'Alpha': 'StratagemA'}); self.assertEqual(vector, {'StratagemA'}); self.assertEqual(keys, {'StratagemA', 'StratagemB'})


if __name__ == '__main__':
    unittest.main()
