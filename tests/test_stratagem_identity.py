"""Whether a genuinely new selectable stratagem is possible (docs/custom-stratagems.md, "A genuinely new selectable
stratagem: research"; research/stratagem-identity-F5FEE03DCFDB.json). The research is read-only and offline; these
tests hold its recorded determinations to the evidence it recorded."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/stratagem-identity-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class StratagemIdentityResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_and_pinned_on_every_snapshot(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        for group in ('registryFill', 'picker', 'restore', 'peerSync', 'report', 'availability', 'alternateResolution'):
            self.assertTrue(RESEARCH['pins'][group], group)

    def test_the_registry_is_a_full_static_array_with_one_writer(self):
        registry = RESEARCH['registry']
        self.assertEqual((registry['table'], registry['entries'], registry['rowSize']), ('0x37CB600', 150, 400))
        self.assertEqual((registry['writer'], registry['stores']), ('0x11F2080', ['0x11F2225']))
        self.assertEqual(registry['source'], 'generated_stratagem_settings.dl_bin')
        self.assertLess(registry['referencesAfterABoundsCompare'], registry['references'] // 10)
        fill = {pin['rva']: pin for pin in RESEARCH['pins']['registryFill']}
        self.assertEqual(fill[0x11F2225]['asm'], 'mov qword ptr [r13 + rax*8], rdx')   # table[row.type] = row
        for snapshot in RESEARCH['snapshots']:
            self.assertEqual(snapshot['empty'], [0])                                # type 0 means none
            self.assertEqual((snapshot['filled'], snapshot['typeIsIndex'], snapshot['rowsInSettingsBuffer']),
                (149, 149, 149))                                                    # no free type
            self.assertEqual((snapshot['enumNames']['validNames'], snapshot['enumNames']['after'][0]), (150, 'Count'))

    def test_the_picker_persistence_and_network_paths_are_recorded(self):
        picker = {pin['rva']: pin['asm'] for pin in RESEARCH['pins']['picker']}
        self.assertEqual((picker[0x18D8AA1], picker[0x18D8AA9]), ('mov ebx, 1', 'mov edi, 0x96'))
        restore = {pin['rva']: pin['role'] for pin in RESEARCH['pins']['restore']}
        self.assertIn('dropped', restore[0x17521B6])
        sync = {pin['rva']: pin['asm'] for pin in RESEARCH['pins']['peerSync']}
        self.assertEqual(sync[0x11E83AB], 'mov rax, qword ptr [rdx + rax*8]')       # unchecked on every peer

    def test_the_determinations(self):
        determinations = RESEARCH['determinations']
        self.assertTrue(determinations['A_newNumericIdentity'].startswith('Not possible safely'))
        self.assertTrue(determinations['B_newSelectableEntry'].startswith('Not possible without a type'))
        self.assertIn('Live-proven', determinations['C_carrier'])
        self.assertIn('not supported safely by the current game architecture', RESEARCH['conclusion'])
        doc = (ROOT / 'docs/custom-stratagems.md').read_text(encoding='utf-8')
        self.assertIn('**True new selectable StratagemInfo identities are not supported safely by the current game '
            'architecture.**', doc)


if __name__ == '__main__':
    unittest.main()
