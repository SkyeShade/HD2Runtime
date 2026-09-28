import copy
import json
import re
import sys
import unittest
from unittest import mock

from support import ROOT
sys.path.insert(0,str(ROOT/'scripts'))
import generate_stratagem_authoring
import generate_support_weapon_authoring
import support_callin_linkage


AMBIGUOUS={'B/FLAM-80 Cremator','CQC-20 Breaching Hammer','EAT-17 Expendable Anti-Tank',
    'LAS-98 Laser Cannon','M-105 Stalwart','MG-206 Heavy Machine Gun','MG-43 Machine Gun'}


class SupportCallInLinkageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.support=json.loads((ROOT/'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
        cls.stratagems=json.loads((ROOT/'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.weapons={item['name']:item for item in cls.support['weapons']}
        cls.support_roots={item['name']:item for item in cls.stratagems['stratagems']
            if item['family']=='support'}
        cls.by_stratagem_id={item['semanticId']:item for item in cls.stratagems['stratagems']}
        cls.by_weapon_id={item['semanticId']:item for item in cls.support['weapons']}

    def test_summary_audit(self):
        audit=self.support['supportCallInLinks']['audit']
        self.assertEqual(audit['supportWeapons'],35)
        self.assertEqual(audit['knownLinks'],32)
        self.assertEqual(audit['unresolvedLinks'],3)
        self.assertEqual(audit['reverseLinksKnown'],32)
        self.assertEqual(audit['relationships'],32)
        self.assertEqual(audit['bidirectionalMismatches'],0)
        self.assertEqual(audit['linksRelyingOnDisplayNameOnly'],0)
        self.assertEqual(audit['specialLinks'],['MS-11 Solo Silo'])
        self.assertEqual(self.support['summary']['linkedStratagemIdentities'],32)
        self.assertEqual(self.support['summary']['supportCallInLinkage'],audit)
        self.assertEqual(self.stratagems['summary']['supportCallInLinkage'],audit)
        self.assertEqual(self.stratagems['summary']['supportDeliveryLinksKnown'],32)

    def test_every_support_weapon_publishes_linkage_state(self):
        self.assertEqual(len(self.weapons),35)
        self.assertEqual(len(self.support_roots),35)
        for name,weapon in self.weapons.items():
            link=weapon['linkedStratagem']
            self.assertIn(link['state'],('linked','unresolved_call_in','unresolved_delivery'),name)
            self.assertEqual(link['known'],link['state']=='linked',name)
            self.assertEqual(link['relationship'],'call_in',name)
            if link['known']:
                self.assertIsNone(link['blocker'],name)
                self.assertEqual(link['confidence'],'reviewed',name)
                self.assertTrue(link['semanticId'].startswith('stratagem/v1/'),name)
            else:
                self.assertTrue(link['blocker'],name)
                self.assertIsNone(link['semanticId'],name)
                self.assertIsNone(link['relationshipId'],name)
        for name,root in self.support_roots.items():
            self.assertIn('delivers',root,name)

    def test_semantic_ids_are_stable_unique_and_opaque(self):
        self.assertEqual(self.weapons['GR-8 Recoilless Rifle']['semanticId'],
            'support-weapon/v1/gr-8-recoilless-rifle/0c0cddff45ad97f6')
        self.assertEqual(self.support_roots['GR-8 Recoilless Rifle']['semanticId'],
            'stratagem/v1/gr-8-recoilless-rifle/0c0cddff45ad97f6')
        self.assertEqual(self.weapons['GR-8 Recoilless Rifle']['linkedStratagem']['relationshipId'],
            'support-callin/v1/gr-8-recoilless-rifle/81fa192e64230582')
        self.assertEqual(len(self.by_weapon_id),35)
        self.assertEqual(len(self.by_stratagem_id),len(self.stratagems['stratagems']))
        for item in self.stratagems['stratagems']:
            self.assertRegex(item['semanticId'],r'^stratagem/v1/[a-z0-9-]+/[0-9a-f]{16}$')
        for item in self.support['weapons']:
            self.assertRegex(item['semanticId'],r'^support-weapon/v1/[a-z0-9-]+/[0-9a-f]{16}$')
        # The field-instance identity and the weapon-level semantic identity agree.
        for instance in self.support['fieldInstances']:
            self.assertEqual(instance['supportWeaponIdentity']['weaponKey'],
                self.weapons[instance['supportWeapon']]['semanticId'])

    def test_every_known_relationship_is_bidirectional(self):
        relationships=self.support['supportCallInLinks']['relationships']
        self.assertEqual(relationships,self.stratagems['supportCallInLinks']['relationships'])
        self.assertEqual(len({item['relationshipId']for item in relationships}),32)
        for relationship in relationships:
            weapon=self.by_weapon_id[relationship['supportWeapon']]
            stratagem=self.by_stratagem_id[relationship['stratagem']]
            self.assertEqual(stratagem['family'],'support')
            self.assertEqual(weapon['linkedStratagem']['semanticId'],stratagem['semanticId'])
            self.assertEqual(stratagem['delivers']['semanticId'],weapon['semanticId'])
            self.assertEqual(weapon['linkedStratagem']['relationshipId'],relationship['relationshipId'])
            self.assertEqual(stratagem['delivers']['relationshipId'],relationship['relationshipId'])
            self.assertEqual(stratagem['delivers']['kind'],'support_weapon')
        for name,weapon in self.weapons.items():
            link=weapon['linkedStratagem']
            if link['known']:
                self.assertEqual(self.by_stratagem_id[link['semanticId']]['delivers']['semanticId'],
                    weapon['semanticId'])
        for name,root in self.support_roots.items():
            delivers=root['delivers']
            if delivers['known']:
                self.assertEqual(self.by_weapon_id[delivers['semanticId']]['linkedStratagem']['semanticId'],
                    root['semanticId'])

    def test_audit_rejects_one_way_links(self):
        linkage=support_callin_linkage.build()
        weapons=copy.deepcopy(linkage['supportWeapons']);stratagems=copy.deepcopy(linkage['stratagems'])
        stratagems['GR-8 Recoilless Rifle']['semanticId']=support_callin_linkage.support_weapon_key(
            'FAF-14 Spear')
        with self.assertRaises(ValueError):
            support_callin_linkage.audit_links(linkage['relationships'],weapons,stratagems)
        stratagems=copy.deepcopy(linkage['stratagems'])
        weapons['AC-8 Autocannon']['semanticId']=None
        with self.assertRaises(ValueError):
            support_callin_linkage.audit_links(linkage['relationships'],weapons,stratagems)

    def test_known_links_are_structural_not_display_name_equality(self):
        for relationship in self.support['supportCallInLinks']['relationships']:
            provenance=relationship['provenance']
            self.assertEqual(provenance['basis'],'native_payload_graph')
            self.assertTrue(set(provenance['evidence'])&{'stratagem_payload_is_support_root',
                'hellpod_rack_attaches_support_weapon'},relationship['relationshipId'])
        # Removing the native delivery graph must remove every link even though the
        # stratagem and weapon display names still match exactly.
        research=json.loads(support_callin_linkage.SUPPORT_RESEARCH.read_text())
        research['nativeSupportGraph']['hellpodRacks']=[]
        for weapon in research['weapons']:
            weapon['ownershipChain']=[node for node in weapon.get('ownershipChain')or[]
                if node['kind']not in('stratagem_payload','spawned_silo')]
        roots=json.loads(support_callin_linkage.STRATAGEM_RESEARCH.read_text())['supportRoots']
        for root in roots:
            if root['resolution']=='UNIQUE':
                root['currentRoot']['payloads']=['0x0000000000000001']
        path=ROOT/'build/test-support-callin-no-graph.json'
        path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(research))
        try:
            stripped=support_callin_linkage.build(roots,path)
        finally:
            path.unlink()
        self.assertEqual(stripped['audit']['knownLinks'],0)
        self.assertEqual(stripped['relationships'],[])

    def test_structural_link_disagreeing_with_name_correlation_is_rejected(self):
        roots=json.loads(support_callin_linkage.STRATAGEM_RESEARCH.read_text())['supportRoots']
        by_name={root['name']:root for root in roots}
        first,second=by_name['GR-8 Recoilless Rifle'],by_name['FAF-14 Spear']
        first['currentRoot'],second['currentRoot']=second['currentRoot'],first['currentRoot']
        with self.assertRaises(ValueError):
            support_callin_linkage.build(roots)

    def test_ambiguous_weapon_identity_keeps_link_and_write_blocking(self):
        ambiguous={name for name,weapon in self.weapons.items()
            if weapon['identityStatus']!='UNIQUE'and weapon['linkedStratagem']['known']}
        self.assertEqual(ambiguous,AMBIGUOUS)
        self.assertEqual(set(self.support['supportCallInLinks']['audit']['ambiguousWeaponIdentityNames']),
            AMBIGUOUS)
        runtime,_=generate_support_weapon_authoring.build()
        for name in AMBIGUOUS:
            weapon=self.weapons[name]
            self.assertEqual(weapon['identityStatus'],'DUPLICATE')
            self.assertFalse(weapon['writable'],name)
            self.assertEqual(weapon['writableFieldCount'],0,name)
            self.assertTrue(runtime['weapons'][name]['ordinaryWritesBlocked'],name)
            self.assertFalse(runtime['weapons'][name]['fields'],name)
            self.assertTrue(any(item['field']=='ordinary writes'for item in weapon['blockedFields']))
            relationship=next(item for item in self.support['supportCallInLinks']['relationships']
                if item['supportWeaponName']==name)
            self.assertEqual(relationship['weaponIdentityStatus'],'DUPLICATE')
            root=self.support_roots[name]
            self.assertEqual(root['rootResolution'],'UNIQUE')
            self.assertTrue(root['cooldownCapability']['writable'])
        self.assertIn('never lifts support-weapon write blocking',
            self.support['supportCallInLinks']['joinContract']['writeGuardsUnchanged'])

    def test_unresolved_call_ins_remain_explicit(self):
        for name in ('SG-88 Break-Action Shotgun','CQC-72 Entrenchment Tool'):
            link=self.weapons[name]['linkedStratagem']
            self.assertFalse(link['known'])
            self.assertEqual(link['state'],'unresolved_call_in')
            self.assertIn('not guessed',link['blocker'])
            root=self.support_roots[name]
            self.assertEqual(root['rootResolution'],'UNRESOLVED')
            self.assertEqual(root['delivers']['kind'],'unresolved')
            self.assertFalse(root['delivers']['known'])
            self.assertTrue(root['delivers']['blocker'])
        c4=self.weapons['B/MD C4 Pack']['linkedStratagem']
        self.assertEqual(c4['state'],'unresolved_delivery')
        self.assertIn('not inferred from display names',c4['blocker'])
        root=self.support_roots['B/MD C4 Pack']
        self.assertEqual(root['rootResolution'],'UNIQUE')
        self.assertEqual(root['delivers']['state'],'unresolved_delivery')
        self.assertEqual(root['delivers']['companionDeliveries'],
            [{'kind':'backpack'},{'kind':'unmapped_entity'}])
        audit=self.support['supportCallInLinks']['audit']
        self.assertEqual(audit['unresolvedCallIns'],
            ['CQC-72 Entrenchment Tool','SG-88 Break-Action Shotgun'])
        self.assertEqual(audit['unresolvedDeliveries'],['B/MD C4 Pack'])

    def test_solo_silo_relationship_is_named_reversible_and_composable(self):
        weapon=self.weapons['MS-11 Solo Silo'];root=self.support_roots['MS-11 Solo Silo']
        link=weapon['linkedStratagem']
        self.assertTrue(link['known'])
        self.assertEqual(link['kind'],'support_weapon_delivery')
        self.assertEqual(link['semanticId'],root['semanticId'])
        self.assertEqual(link['stratagemName'],'MS-11 Solo Silo')
        self.assertEqual(link['special'],'deployable_silo')
        self.assertIn('stratagem_payload_is_support_root',link['provenance']['evidence'])
        self.assertEqual(root['delivers']['semanticId'],weapon['semanticId'])
        self.assertEqual(root['delivers']['deliveryObject'],'deployable_silo')
        relationship=next(item for item in self.support['supportCallInLinks']['relationships']
            if item['relationshipId']==link['relationshipId'])
        graph=relationship['deliveryGraph']
        self.assertEqual(graph['composition'],'reference')
        self.assertFalse(graph['duplicatesFields'])
        nodes={node['node']:node for node in graph['nodes']}
        self.assertEqual(nodes['call_in']['view'],'stratagem')
        self.assertEqual(nodes['call_in']['fields'],['stratagem.cooldown','stratagem.max_uses'])
        self.assertEqual(nodes['delivery']['object'],'deployable_silo')
        self.assertEqual(nodes['attack_entity']['object'],'missile')
        self.assertEqual(nodes['attack_entity']['parent'],'delivery')
        explosions=[node for node in graph['nodes']if node['object']=='explosion']
        self.assertEqual(sorted(node['attackRole']for node in explosions),['detonation','impact'])
        for node in explosions:
            self.assertEqual(node['parent'],'attack_entity')
            self.assertEqual(node['view'],'support_weapon')
            self.assertEqual(node['targetPath'],'explosion')
        # Referenced nodes resolve to existing canonical instances in their own view.
        roles={item['target']['attackRole']for item in self.support['fieldInstances']
            if item['supportWeapon']=='MS-11 Solo Silo'}
        self.assertEqual(roles,{'detonation','impact'})
        self.assertTrue(any(item['target']['stratagem']=='MS-11 Solo Silo'
            and item['semanticFieldId']=='stratagem.cooldown'
            for item in self.stratagems['fieldInstances']))
        # The explosion graph stays in the support-weapon view only.
        self.assertFalse(any(item['target'].get('stratagem')=='MS-11 Solo Silo'
            and item['target']['path']!='stratagem'for item in self.stratagems['fieldInstances']))

    def test_delivery_graph_references_are_internally_consistent(self):
        for relationship in self.support['supportCallInLinks']['relationships']:
            nodes=relationship['deliveryGraph']['nodes']
            ids={node['node']for node in nodes}
            self.assertEqual(len(ids),len(nodes))
            for node in nodes:
                if node['parent']:self.assertIn(node['parent'],ids)
                expected=(relationship['stratagem']if node['view']=='stratagem'
                    else relationship['supportWeapon'])
                self.assertEqual(node['semanticId'],expected)

    def test_no_raw_native_identifiers_are_published(self):
        research=json.loads(support_callin_linkage.SUPPORT_RESEARCH.read_text())
        graph=research['nativeSupportGraph']
        hashes={rack['resourceHash']for rack in graph['hellpodRacks']}
        hashes|={item for rack in graph['hellpodRacks']for item in rack['attachedResources']}
        hashes|={item for weapon in research['weapons']for item in weapon['resourceHashes']}
        roots=json.loads(support_callin_linkage.STRATAGEM_RESEARCH.read_text())['supportRoots']
        hashes|={item for root in roots if root['resolution']=='UNIQUE'
            for item in root['currentRoot']['payloads']}
        ids={str(root['currentRoot']['id'])for root in roots if root['resolution']=='UNIQUE'}
        published=json.dumps([self.support['supportCallInLinks'],
            [weapon['linkedStratagem']for weapon in self.support['weapons']],
            [root['delivers']for root in self.support_roots.values()]]).lower()
        self.assertNotIn('0x',published)
        for value in hashes:
            self.assertNotIn(value[2:].lower(),published)
        numbers=set(re.findall(r'\d{6,}',published))
        self.assertFalse(numbers&ids)

    def test_generated_sdk_metadata_includes_relationship_data(self):
        for document in (self.support,self.stratagems):
            links=document['supportCallInLinks']
            self.assertEqual(links['contract'],'hd2runtime.support_callin_linkage.v1')
            self.assertEqual(links['joinContract']['mergeKey'],'relationshipId')
            self.assertFalse(links['joinContract']['displayNameMatchingRequired'])
            self.assertFalse(links['joinContract']['rawNativeIdentifiersPublished'])
            self.assertTrue(links['joinContract']['writeTargetsRemainSeparate'])
        # Runtime metadata inspection carries both catalog summaries, including the audit.
        self.assertIn('supportCallInLinkage',(ROOT/'domains/metadata.lua').read_text())

    def test_release_freshness_catches_stale_linkage(self):
        self.assertFalse(generate_support_weapon_authoring.generate(check=True))
        self.assertFalse(generate_stratagem_authoring.generate(check=True)[0])
        original=support_callin_linkage.build

        def stale(*args,**kwargs):
            value=original(*args,**kwargs)
            value['relationships'][0]['confidence']='stale'
            return value
        with mock.patch.object(support_callin_linkage,'build',stale):
            with self.assertRaisesRegex(RuntimeError,'Stale support authoring'):
                generate_support_weapon_authoring.generate(check=True)
            with self.assertRaisesRegex(RuntimeError,'Stale stratagem authoring'):
                generate_stratagem_authoring.generate(check=True)
        release=(ROOT/'scripts/build_release.py').read_text()
        self.assertIn('generate_support_weapon_authoring.generate(check=True)',release)
        self.assertIn('generate_stratagem_authoring.generate(check=True)',release)
        self.assertIn('support_call_in_linkage',release)


if __name__=='__main__':
    unittest.main()
