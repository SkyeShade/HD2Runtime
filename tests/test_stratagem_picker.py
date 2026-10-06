"""A virtual card in the ship loadout picker (docs/custom-stratagems.md, "A virtual card in the ship loadout picker:
research"; research/stratagem-picker-F5FEE03DCFDB.json). The research is read-only and offline; these tests hold its
recorded determinations to the evidence it recorded."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/stratagem-picker-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


def pins(group):
    return {pin['rva']: pin for pin in RESEARCH['pins'][group]}


class PickerCardResearchTests(unittest.TestCase):
    def test_read_only_and_pinned_on_every_snapshot(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))

    def test_no_snapshot_holds_a_picker(self):
        # The loadout UI exists only while the loadout screen does: no offline proof against a real card list.
        self.assertEqual(len(RESEARCH['pickerInSnapshots']), 7)
        self.assertTrue(all(s['owner'] and s['uiRoot'] == 0 for s in RESEARCH['pickerInSnapshots'].values()))

    def test_an_entry_is_a_key_only(self):
        card_list = pins('cardList')
        self.assertEqual(card_list[0x18D445A]['asm'], 'mov dword ptr [r10 + rax*4 + 0x92990], edx')
        self.assertEqual(card_list[0x18D43B3]['asm'], 'cmp r11d, 0x100')
        # The add writes the key array once and never reads it: no duplicate check in the list itself.
        self.assertEqual(RESEARCH['addCardKeyArrayAccess'], ['mov dword ptr [r10 + rax*4 + 0x92990], edx'])
        self.assertIn('sort only', pins('gridBuild')[0x18D8C0A]['role'])

    def test_presentation_comes_from_the_row_through_native_code(self):
        card = pins('cardPresentation')
        self.assertEqual(card[0x18CB40A]['asm'], 'call 0x11f2490')
        self.assertEqual(card[0x18CB541]['asm'], 'mov rax, qword ptr [r10 + 0xb0]')
        self.assertEqual(card[0x19438AE]['asm'], 'call 0x144f800')
        self.assertEqual(pins('detailPanel')[0x191D54D]['asm'], 'call 0x11f2490')

    def test_the_click_reads_the_key_and_first_match_wins(self):
        click = pins('click')
        self.assertEqual(click[0x18D5E68]['asm'], 'mov dword ptr [rbp + 0x178c98], ebx')
        self.assertIn('FIRST', click[0x18D5E81]['role'])
        enabled = pins('enabledState')
        self.assertIn('FIRST', enabled[0x18D1480]['role'])
        self.assertEqual(enabled[0x18D1536]['asm'], 'call 0x18ca560')

    def test_the_determinations(self):
        d = RESEARCH['determinations']
        self.assertTrue(d['storesType'].startswith('No'))
        self.assertTrue(d['storesStableId'].startswith('No'))
        self.assertTrue(d['perInstancePresentation'].startswith('No'))
        self.assertTrue(d['creationHelper'].startswith('Yes, native'))
        self.assertTrue(RESEARCH['conclusion'].startswith('Not feasible under the constraints'))
        doc = (ROOT / 'docs/custom-stratagems.md').read_text(encoding='utf-8')
        self.assertIn('## A virtual card in the ship loadout picker: research (2026-10-02, offline)', doc)


if __name__ == '__main__':
    unittest.main()
