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
        arc=next(w for w in data['weapons'] if w['name']=='ARC-3 Arc Thrower')
        self.assertEqual((arc['attacks'][0]['arc_range'],arc['attacks'][0]['arc_velocity'],
                          arc['attacks'][0]['arc_spread'],arc['attacks'][0]['arc_chain_spread']),
                         (55,300,40,60))
        self.assertEqual((arc['attacks'][1]['status_strength'],arc['attacks'][1]['status_duration']),(8,1.5))
        c4=next(w for w in data['weapons'] if w['name']=='B/MD C4 Pack')
        self.assertEqual((c4['attacks'][0]['explosion_inner_radius'],
                          c4['attacks'][0]['explosion_outer_radius'],
                          c4['attacks'][0]['explosion_shockwave_radius']),(3,7,8))

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

    def test_support_melee_accepts_native_secondary_tag_and_arc_rate_is_diagnostic(self):
        run("""
local matcher=require('hd2runtime/primary_mapper/matcher')
local melee={name='Tool',slot='support',attacks={{name='hit',kind='Melee',
 standard_damage=165,durable_damage=83,ap_direct=3,stagger=25}}}
local mr=matcher.rank({weapon_slot='secondary',attack_kind='Melee',standard_damage=165,
 durable_damage=83,ap_direct=3,stagger=25},{weapons={melee}})
assert(mr.rankedWikiMatches[1].structurallyCompatible)
local arc={name='Arc',slot='support',fire_rate=60,attacks={{name='arc',kind='Arc',
 standard_damage=250,durable_damage=100,ap_direct=7,arc_range=55}}}
local ar=matcher.rank({attack_kind='Arc',fire_rate=-1,standard_damage=250,durable_damage=100,
 ap_direct=7,arc_range=55},{weapons={arc}})
local top=ar.rankedWikiMatches[1]
assert(#top.mismatched==0 and #top.diagnosticDisagreements==1)
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
        self.assertEqual(self.summary['resolvedIdentities'],35)
        self.assertEqual(self.summary['uniqueIdentities'],27)
        self.assertEqual(self.summary['duplicateIdentityGroups'],8)
        self.assertEqual((self.summary['ambiguousIdentities'],self.summary['unresolvedIdentities']),(0,0))
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
        linked=next(a for a in gr8['attackGraph'] if a['name']=='GR-8 P IE')
        self.assertEqual(linked['state'],'RESOLVED')
        self.assertFalse(gr8['ammoFeedMagazine'][0]['backpackRuntimeOwnershipProven'])

    def test_duplicate_resources_and_shared_settings_fail_closed(self):
        duplicates={w['catalogIdentity'] for w in self.report['weapons']
                    if w['identityResolution']=='DUPLICATE'}
        self.assertEqual(duplicates,{'B/FLAM-80 Cremator','CQC-20 Breaching Hammer',
            'CQC-72 Entrenchment Tool','EAT-17 Expendable Anti-Tank','LAS-98 Laser Cannon',
            'M-105 Stalwart','MG-206 Heavy Machine Gun','MG-43 Machine Gun'})
        self.assertIsNone(self.mapping['MG-43 Machine Gun']['canonicalResourceHash'])
        self.assertGreaterEqual(len(self.report['sharedSettingsGroups']),1)
        self.assertTrue(any(group['weapons']==['GL-21 Grenade Launcher','GL-52 De-Escalator']
            for group in self.report['sharedSettingsGroups']))
        self.assertTrue(all(not weapon['guardedAuthoringReady'] for weapon in self.report['weapons']))

    def test_native_family_resolution_and_rate_diagnostics(self):
        self.assertEqual(self.summary['unresolvedWeapons'],[])
        arc=self.by_name['ARC-3 Arc Thrower']
        self.assertEqual(arc['resourceHashes'],['0x96DE9CD50F7306E6'])
        self.assertEqual(arc['chargeCadence'][0]['value']['minimumSeconds'],.699999988079071)
        self.assertEqual([branch['state'] for branch in arc['attackGraph']],['RESOLVED','RESOLVED'])
        cqc=self.by_name['CQC-72 Entrenchment Tool']
        self.assertEqual(cqc['identityResolution'],'DUPLICATE')
        self.assertEqual(cqc['resourceHashes'],['0x7E1F76163C667E4B','0xE85E623F93F96FB3'])
        gl28=self.by_name['GL-28 Belt-Fed Grenade Launcher']
        self.assertEqual(gl28['identityResolutionBasis'],'linked_projectile_explosion_graph_with_rate_diagnostic')
        self.assertEqual(gl28['fireRateDiagnostics'][0]['runtimeOptions'],
            {'low':160,'default':240,'high':320,'representation':'schema_vec3_selector'})

    def test_deployable_and_stratagem_owned_explosion_graphs(self):
        c4=self.by_name['B/MD C4 Pack']
        self.assertEqual(c4['resourceHashes'],['0x9B75217D8312DD67'])
        self.assertEqual(c4['attackGraph'][0]['state'],'RESOLVED')
        solo=self.by_name['MS-11 Solo Silo']
        self.assertEqual(solo['resourceHashes'],['0xDE18775FA447A9BF'])
        self.assertEqual(solo['attackOwnerResourceHash'],'0xDDDB2910FF2B24E9')
        self.assertEqual([node['kind'] for node in solo['ownershipChain']],
            ['stratagem_payload','spawned_silo','placed_or_attack_entity'])
        self.assertTrue(all(branch['state']=='RESOLVED' for branch in solo['attackGraph']))

    def test_explosion_status_and_backpack_progress_are_bounded(self):
        self.assertEqual(self.summary['resolvedBranchCounts']['Explosion'],18)
        self.assertEqual(self.summary['resolvedBranchCounts']['Status'],8)
        graph=self.report['nativeSupportGraph']
        self.assertEqual(graph['settingsCounts'],{'explosion':422,'status':71})
        self.assertEqual(self.summary['backpackDependentWeapons'],9)
        self.assertEqual(self.summary['backpackWeaponsWithWeaponLinkedAmmoOwnership'],3)
        self.assertEqual(self.summary['backpackEntityLinksProven'],0)


if __name__=='__main__':unittest.main()
