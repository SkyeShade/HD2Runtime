import json
import sys
import unittest

from support import ROOT, run

sys.path.insert(0,str(ROOT/'sdk'))
from tools.wiki_player import compact


class SupportWeaponCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=compact(ROOT/'data/wiki_support_weapons.json')

    def test_nested_support_metadata_and_graph_are_preserved(self):
        data=self.catalog
        self.assertEqual(data['weapon_count'],35)
        self.assertEqual(data['slot_counts'],{'primary':0,'secondary':0,'support':35})
        self.assertEqual(data['multi_attack_weapon_count'],24)
        mg=next(w for w in data['weapons'] if w['name']=='MG-43 Machine Gun')
        self.assertEqual((mg['slot'],mg['fire_rate'],mg['capacity']),('support',760,175))
        self.assertEqual((mg['recoil'],mg['horizontal_recoil'],mg['vertical_recoil']),(21.25,17.5,25))
        gr8=next(w for w in data['weapons'] if w['name']=='GR-8 Recoilless Rifle')
        self.assertTrue(gr8['backpack_dependent'])
        self.assertEqual(len(gr8['attacks']),5)
        self.assertEqual(gr8['attacks'][2]['parent_attack'],'GR-8 P')
        railgun=next(w for w in data['weapons'] if w['name']=='RS-422 Railgun')
        unknown=[a for a in railgun['attacks'] if a['kind']=='Unknown']
        self.assertEqual(len(unknown),1)
        self.assertIn('Max Charge',unknown[0]['name'])

    def test_support_weapon_only_candidates_do_not_weaken_player_slot_gate(self):
        run("""
local matcher=require('hd2runtime/primary_mapper/matcher')
local attack={name='A',kind='Projectile'}
local runtime={weapon_data_only=true,fire_rate=760,capacity=175,ergonomics=15}
local support={name='Support',slot='support',fire_rate=760,capacity=175,ergonomics=15,attacks={attack}}
local primary={name='Primary',slot='primary',fire_rate=760,capacity=175,ergonomics=15,attacks={attack}}
local a=matcher.rank(runtime,{weapons={support}}).rankedWikiMatches[1]
local b=matcher.rank(runtime,{weapons={primary}}).rankedWikiMatches[1]
assert(a.structurallyCompatible and not b.structurallyCompatible)
return'ok'
""")


class SupportWeaponRuntimeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.json').read_text())
        cls.mapping=json.loads((ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.identity-candidates.json').read_text())
        cls.summary=json.loads((ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.summary.json').read_text())
        cls.by_name={w['catalogIdentity']:w for w in cls.report['weapons']}

    def test_all_35_read_only_snapshot_invariants(self):
        self.assertEqual(len(self.report['weapons']),35)
        self.assertEqual(self.report['mode'],'snapshot')
        self.assertEqual((self.report['writes'],self.report['protectionChanges'],
                          self.report['fixtureFallback']),(0,0,'disabled'))
        self.assertEqual(self.summary['resolvedIdentities'],30)
        self.assertEqual(self.summary['uniqueIdentities'],24)
        self.assertFalse(self.summary['guardedAuthoringReady'])

    def test_catalog_branch_counts_and_unknown_are_preserved(self):
        self.assertEqual(self.summary['catalogBranchCounts'],{
            'Projectile':32,'Explosion':34,'Beam':2,'Arc':2,'Spray':3,
            'Melee':4,'Status':17,'Unknown':1})
        railgun=self.by_name['RS-422 Railgun']
        unknown=next(a for a in railgun['attackGraph'] if a['kind']=='Unknown')
        self.assertEqual(unknown['state'],'UNRESOLVED')
        self.assertIn('intentionally',unknown['unresolvedReason'])

    def test_representative_roots_and_multibranch_graph(self):
        expected={
            'GR-8 Recoilless Rifle':'0x9F80D67A12A7E40F',
            'RS-422 Railgun':'0x2E9D0BDC48B09E60',
            'FLAM-40 Flamethrower':'0x39AB99895147A3BF',
            'AC-8 Autocannon':'0xA8CFFB316F0B5C5F',
        }
        for name,resource in expected.items():
            self.assertEqual(self.mapping[name]['canonicalResourceHash'],resource)
        gr8=self.by_name['GR-8 Recoilless Rifle']
        self.assertEqual(len(gr8['attackGraph']),5)
        self.assertTrue(gr8['backpackDependent'])
        self.assertTrue(any(a['kind']=='Projectile'and a['state']=='RESOLVED' for a in gr8['attackGraph']))
        self.assertTrue(all(a['state']=='UNRESOLVED' for a in gr8['attackGraph'] if a['kind']=='Explosion'))
        self.assertFalse(gr8['ammoFeedMagazine'][0]['backpackRuntimeOwnershipProven'])

    def test_duplicate_resources_and_shared_settings_fail_closed(self):
        duplicates={w['catalogIdentity'] for w in self.report['weapons']
                    if w['identityResolution']=='DUPLICATE'}
        self.assertEqual(duplicates,{'B/FLAM-80 Cremator','EAT-17 Expendable Anti-Tank',
            'LAS-98 Laser Cannon','M-105 Stalwart','MG-206 Heavy Machine Gun','MG-43 Machine Gun'})
        self.assertIsNone(self.mapping['MG-43 Machine Gun']['canonicalResourceHash'])
        self.assertEqual(len(self.report['sharedSettingsGroups']),1)
        self.assertEqual(self.report['sharedSettingsGroups'][0]['weapons'],
            ['GL-21 Grenade Launcher','GL-52 De-Escalator'])
        self.assertTrue(all(not weapon['guardedAuthoringReady'] for weapon in self.report['weapons']))

    def test_unresolved_set_is_explicit(self):
        self.assertEqual(set(self.summary['unresolvedWeapons']),{
            'ARC-3 Arc Thrower','B/MD C4 Pack','CQC-72 Entrenchment Tool',
            'GL-28 Belt-Fed Grenade Launcher','MS-11 Solo Silo'})


if __name__=='__main__':unittest.main()
