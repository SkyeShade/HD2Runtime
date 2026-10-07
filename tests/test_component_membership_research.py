"""The component membership research (research/docs/component-membership-F5FEE03DCFDB.md,
research/component-membership-F5FEE03DCFDB.json). It is read-only, and its pins are identical in every snapshot. It
covers the facts behind the verdicts:
- membership at spawn is the EntitySettings u16 list;
- type lookups are open-addressing hashes over the loaded index rows (key 0 = empty, no tombstones);
- the entity file is loaded in place into one PAGE_READONLY allocation;
- vanilla data keeps row <=> list membership exact;
- WeaponRounds and WeaponAssistedReload never occur without WeaponReload;
- destroy and network handlers follow the current list."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/component-membership-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class ComponentMembershipResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        for rva in (0xFDB636, 0x5817BD, 0x58140E, 0xFDC943, 0x581D24, 0x4FCE75, 0x753B51, 0x172F8EB, 0x778CD2):
            self.assertIn(rva, roles)

    def test_loaded_in_place_read_only(self):
        checks = RESEARCH['checks']
        self.assertTrue(checks['entityFileReadOnlyInEverySnapshot'])
        self.assertTrue(checks['everySlotPointsIntoTheLoadedFile'])
        self.assertTrue(checks['onlyTheListPointersArePatched'])
        for snap in RESEARCH['snapshots'].values():
            self.assertTrue(snap['entityFile']['eshIsFirstInstanceData'])
            self.assertEqual(snap['entityFile']['protect'], '0x2')

    def test_hash_structure(self):
        hashes = RESEARCH['structures']['hashTables']
        self.assertEqual((hashes['tables'], hashes['rows'], hashes['rowsOffProbePath']), (270, 24241, 0))
        self.assertEqual((hashes['emptyKey'], hashes['tombstoneSupport']), (0, False))
        self.assertEqual(hashes['sharedRecordsVanilla'], 0)
        self.assertEqual(hashes['focus']['WeaponReload'], {'capacity': 498, 'rows': 249, 'records': 250, 'free': 249})
        settings = RESEARCH['structures']['entitySettings']
        self.assertEqual((settings['capacity'], settings['rows']), (4096, 1909))
        self.assertTrue(settings['rowsOnProbePath'] and settings['listsSorted'] and settings['listsUnique'])
        self.assertTrue(RESEARCH['checks']['listsPackedNoSlack'])

    def test_membership_invariants(self):
        invariant = RESEARCH['structures']['membershipInvariant']
        self.assertEqual((invariant['rowWithoutListEntry'], invariant['listEntryWithoutRow']), (0, 0))
        co = RESEARCH['cooccurrence']
        self.assertEqual(co['WeaponRounds without WeaponReload'], 0)
        self.assertEqual(co['WeaponAssistedReload without WeaponReload'], 0)
        self.assertEqual(co['Backblast and WeaponRounds'], 0)
        self.assertEqual(co['WeaponMagazine and WeaponRounds'], 0)

    def test_lifecycle_and_consumers(self):
        readers = {r['function']: r for r in RESEARCH['code']['entitySettingsReaders']}
        self.assertEqual(readers['0xFDC820']['handlerTables'], ['0xf0dfb0', '0xf0e9d0'])   # destroy follows the list
        self.assertTrue(readers['0x581C40']['byNetworkRowIndex'] and readers['0x581C40']['iteratesList'])
        self.assertTrue(RESEARCH['checks']['gate1IsWeaponReload'])
        self.assertTrue(RESEARCH['checks']['gate2IsSeatCollection'])
        self.assertGreater(RESEARCH['checks']['resolverSitesWithoutNullTest'], 0)

    def test_ac8_case(self):
        ac8 = RESEARCH['ac8']
        self.assertEqual(ac8['membershipDiffToEat17'], {'remove': ['WeaponAssistedReload', 'WeaponReload',
            'WeaponRounds'], 'add': ['WeaponMagazine', 'Backblast']})
        self.assertFalse(ac8['removal']['WeaponReload']['zeroingBreaksLookups'])
        self.assertTrue(ac8['removal']['WeaponRounds']['zeroingBreaksLookups'])
        self.assertEqual(ac8['addition']['Backblast']['eat17RecordOwners'], ['lat_oneshot'])

    def test_verdicts(self):
        verdicts = RESEARCH['answers']['q4_safety']['verdicts']
        self.assertTrue(verdicts['removal'].startswith('REFUSED'))
        self.assertTrue(verdicts['addition'].startswith('REFUSED'))
        self.assertTrue(verdicts['fullTransplant'].startswith('RESEARCH-ONLY'))


if __name__ == '__main__':
    unittest.main()
