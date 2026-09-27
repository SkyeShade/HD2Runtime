import json
import unittest

from support import ROOT


class FinalFiveResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'research/final-five-player-weapons-F5FEE03DCFDB.json').read_text())

    def test_all_five_are_exact_unique_resources(self):
        expected={
            'P-2 Peacemaker':'0x05E4E5C2DB6E44A2',
            'SG-20 Halt':'0x4E310B1FE4C52B52',
            'SG-451 Cookout':'0xD323DE60855898AC',
            'SG-8 Punisher':'0x41EAC4A03987FAA0',
            'SG-8S Slugger':'0x4F749E2EE26F532D'}
        self.assertEqual({name:item['resourceHash'] for name,item in self.report['mappings'].items()},expected)
        self.assertTrue(all(item['status']=='EXACT' for item in self.report['mappings'].values()))
        self.assertEqual(self.report['final']['totalIdentitiesResolved'],80)
        self.assertEqual(self.report['final']['totalUniqueResolved'],73)

    def test_halt_branches_capacity_and_status_are_preserved(self):
        halt=self.report['mappings']['SG-20 Halt']
        self.assertEqual(halt['capacityFeeds'],[8,8])
        self.assertEqual([(a['projectileType'],a['damageType']) for a in halt['attacks']],
            [(183,166),(191,175)])
        self.assertEqual(halt['attacks'][1]['damageStatusStrength'],1)

    def test_catalog_discrepancy_and_read_only_invariants(self):
        comparison=self.report['catalogComparison']
        self.assertEqual(comparison['numericDisagreements'],[])
        self.assertIn('SG-8S Slugger pellet_count',comparison['missingImportedFields'][0])
        self.assertEqual(self.report['safety'],{'mode':'snapshot','writes':0,
            'protectionChanges':0,'fixtureFallback':'disabled','gameLaunched':False})


if __name__=='__main__':unittest.main()
