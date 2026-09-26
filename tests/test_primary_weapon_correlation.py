import json
import unittest

from support import ROOT, run


class PrimaryWeaponCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'research/primary-weapon-field-correlation-F5FEE03DCFDB.json').read_text())

    def test_report_is_current_build_read_only_and_exact_gated(self):
        report=self.report
        self.assertEqual(report['mode'],'offline_snapshot_correlation')
        self.assertEqual(report['identity_gate']['exact_runtime_candidates'],49)
        self.assertEqual(report['identity_gate']['unique_wiki_identities'],37)
        self.assertEqual(report['wiki']['weapon_count'],55)
        self.assertEqual(report['extraction']['writes'],0)
        self.assertEqual(report['extraction']['protection_changes'],0)
        self.assertEqual(report['snapshot']['executable_sha256'],
            'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06')

    def test_promotions_match_schema_and_are_not_gameplay_proven(self):
        expected={
            'fire_rate':('ProjectileWeaponComponentData',8,'f32'),
            'pellet_count':('ProjectileSettings',28,'u32'),
            'projectile_velocity':('ProjectileSettings',32,'f32'),
            'projectile_mass':('ProjectileSettings',36,'f32'),
            'drag':('ProjectileSettings',40,'f32'),
            'gravity':('ProjectileSettings',44,'f32'),
        }
        for name,(structure,offset,primitive) in expected.items():
            field=self.report['fields'][name]
            best=field['best_candidate']
            self.assertTrue(field['promoted'],name)
            self.assertEqual((best['structure'],best['offset'],best['primitive_type']),
                (structure,offset,primitive))
        self.assertFalse(self.report['fields']['capacity']['promoted'])
        self.assertEqual(self.report['fields']['gravity']['best_candidate']['exact_matches'],37)
        self.assertEqual(self.report['fields']['pellet_count']['best_candidate']['exact_matches'],5)
        run("""
local schema=require('hd2runtime/schemas/weapon_mapper')
assert(#schema.unmapped==1 and schema.unmapped[1]=='capacity')
for name,spec in pairs(schema.fields)do
 assert(spec.evidence.correlation_proven and spec.evidence.pending_gameplay_confirmation)
 assert(not spec.evidence.gameplay_proven and not spec.evidence.schema_labelled)
end
return'ok'
""")

    def test_duplicate_groups_are_not_arbitrarily_collapsed(self):
        groups=self.report['duplicate_identity_groups']
        self.assertEqual(set(groups),{'AR-23C Liberator Concussive','AR-23P Liberator Penetrator',
            'PLAS-1 Scorcher','SMG-32 Reprimand','SMG-37 Defender'})
        self.assertTrue(groups['AR-23C Liberator Concussive']['distinguished_to_unique_resource'])
        self.assertTrue(groups['PLAS-1 Scorcher']['distinguished_to_unique_resource'])
        self.assertTrue(groups['SMG-32 Reprimand']['distinguished_to_unique_resource'])
        self.assertFalse(groups['AR-23P Liberator Penetrator']['distinguished_to_unique_resource'])
        self.assertFalse(groups['SMG-37 Defender']['distinguished_to_unique_resource'])
        for group in groups.values():
            self.assertTrue(all(resource['ownership']['ProjectileWeaponComponentData']['uniqueOwner']
                and resource['ownership']['WeaponDataComponentData']['uniqueOwner']
                for resource in group['resources']))

    def test_mapper_before_after_metrics(self):
        comparison=self.report['mapper_comparison']
        self.assertEqual(comparison['before']['status_counts'],
            {'EXACT':49,'STRONG':0,'AMBIGUOUS':15,'UNMATCHED':301})
        self.assertEqual(comparison['after']['status_counts'],
            {'EXACT':49,'STRONG':0,'AMBIGUOUS':23,'UNMATCHED':293})
        self.assertEqual(comparison['before']['resolved_unique_wiki_identities'],37)
        self.assertEqual(comparison['after']['resolved_unique_wiki_identities'],44)
        self.assertEqual(set(comparison['after']['duplicate_identity_groups']),
            {'AR-23P Liberator Penetrator','SMG-37 Defender'})


if __name__=='__main__':unittest.main()
