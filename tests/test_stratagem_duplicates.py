"""Duplicate loadout slots and virtual stratagems (docs/custom-stratagems.md, "Duplicate slots and virtual stratagems:
research"; research/stratagem-duplicates-F5FEE03DCFDB.json). The research is read-only and offline; these tests hold its
recorded determinations to the evidence it recorded."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/stratagem-duplicates-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


def pins(group):
    return {pin['rva']: pin for pin in RESEARCH['pins'][group]}


class DuplicateSlotResearchTests(unittest.TestCase):
    def test_read_only_and_pinned_on_every_snapshot(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))

    def test_only_the_picker_ui_refuses_a_duplicate(self):
        grid = pins('gridDuplicateDisable')
        self.assertEqual(grid[0x18D8BEC]['asm'], 'mov byte ptr [rsp + r9*4 + 0x60], r12b')
        save = pins('save')
        self.assertEqual(save[0x175140A]['asm'], 'add rcx, 0x30')                 # one pair per slot, in order
        self.assertIn('slot by slot', pins('peerSync')[0x11E8360]['role'])
        self.assertEqual(RESEARCH['multiselect']['module'], 'mods/OnlyTanks/stratagem_multiselect')

    def test_the_matcher_keeps_one_candidate_per_type(self):
        matcher = pins('matcher')
        self.assertEqual(matcher[0x66DC10]['asm'], 'mov ebp, dword ptr [r13 + rsi*4]')   # a type-indexed map
        self.assertEqual(matcher[0x66DB9B]['asm'], 'call 0xa106c0')                      # the type's code
        self.assertIn('per type', matcher[0x66DC10]['role'])
        per_slot = pins('perSlotState')
        self.assertIn('(peer, slot index)', per_slot[0x66D28D]['role'])

    def test_the_determinations(self):
        d = RESEARCH['determinations']
        self.assertTrue(d['duplicatesCoexist'].startswith('Yes in game logic'))
        self.assertTrue(d['matcherDistinguishesSlots'].startswith('No'))
        self.assertTrue(d['differentCodes'].startswith('No'))
        self.assertTrue(d['slotSpecificPresentation'].startswith('No'))
        self.assertTrue(d['virtualStratagemRegistry'].startswith('Not feasible without executable hooks'))
        doc = (ROOT / 'docs/custom-stratagems.md').read_text(encoding='utf-8')
        self.assertIn('## Duplicate slots and virtual stratagems: research (2026-10-02, offline)', doc)


if __name__ == '__main__':
    unittest.main()
