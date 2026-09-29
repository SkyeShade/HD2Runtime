"""Central live-test evidence (schemas/live_evidence.json): the registry is consistent, promotions reach exactly the
recorded scope in every catalog, and untested or inconclusive families keep their acknowledgement."""
import json
import re
import unittest

from support import ROOT

import generate_live_evidence
import live_evidence


def load(name):
    return json.loads((ROOT / 'sdk' / name).read_text())


class LiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = live_evidence.load()
        cls.stratagems = load('StratagemAuthoringCapabilities.json')
        cls.player = load('PlayerWeaponAuthoringCapabilities.json')
        cls.support = load('SupportWeaponAuthoringCapabilities.json')
        cls.enemies = load('EnemyAuthoringCapabilities.json')

    def test_registry_and_published_catalog(self):
        generate_live_evidence.generate(check=True)
        catalog = load('LiveEvidenceCatalog.json')
        self.assertEqual(catalog['summary']['families'], {
            'live_proven': ['attack_output_cross_class', 'enemy_main_health', 'enemy_zone_armor', 'minefield_salvos',
                'sentry_targeting_range', 'sentry_turret_turn_speed', 'weapon_ammunition_projectile_reference',
                'weapon_projectile_reference_direct', 'weapon_projectile_status_reference'],
            'not_tested': ['enemy_attack_damage'], 'inconclusive': ['structure_health'],
            'live_failed': ['weapon_projectile_reference_dormant_member'], 'pending': []})
        self.assertEqual((catalog['summary']['tests'], catalog['summary']['passed']), (16, 11))
        for name, entry in self.registry['families'].items():
            if entry['status'] == 'live_proven':
                self.assertTrue(any(t['result'] == 'PASS' for t in live_evidence.tests(name)), name)

    def test_host_path_evidence(self):
        """Composition tests keep donor, write, host-path and gameplay evidence apart; a failed host never counts
        against the donor output."""
        tests = {(t['mod'], t.get('choice')): t for t in live_evidence.tests('weapon_projectile_reference_direct')
            + live_evidence.tests('weapon_projectile_reference_dormant_member')
            + live_evidence.tests('attack_output_cross_class')}
        reprimand = tests[('AssetTestReprimandTalonProjectile', None)]
        self.assertEqual((reprimand['result'], reprimand['host'], reprimand['donor']),
            ('PASS', 'SMG-32 Reprimand', 'LAS-58 Talon'))
        self.assertTrue(all(reprimand['evidence'].values()))
        [liberator] = [t for (mod, _), t in tests.items() if t['result'] == 'FAIL']
        self.assertEqual((liberator['host'], liberator['donor']), ('AR-23 Liberator', 'LAS-58 Talon'))
        self.assertEqual(liberator['evidence'], {'donorOutputWorks': True, 'referenceWriteSucceeded': True,
            'hostReadsReference': False, 'gameplayOutputChanged': False})
        self.assertIn('FULL METAL JACKET', liberator['hostPath'])
        unproven = [t for t in tests.values() if t['result'] == 'UNPROVEN']
        self.assertEqual(sorted(t['choice'] for t in unproven), ['EAT-700 Napalm', 'GL-52 Arc (impact)'])
        self.assertTrue(all(t['evidence']['hostReadsReference'] is False and t['evidence']['donorOutputWorks'] is None
            and t['supersededBy'] == 'projectile-source-correction-2026-09-29' for t in unproven))

    def test_corrected_source_promotions_are_exactly_the_tested_scope(self):
        """The ammunition path is proven for the Liberator's own delta row only; the cross-class outputs for the two
        compositions the user played only; the Reprimand direct path again."""
        runs = [t for t in live_evidence.tests('weapon_ammunition_projectile_reference', current=True)]
        self.assertEqual(sorted(t['choice'] for t in runs), ['EAT-700 Napalm', 'GL-52 Arc (impact)'])
        self.assertTrue(all(t['result'] == 'PASS' and all(t['evidence'].values()) and t['host'] == 'AR-23 Liberator'
            and t['mechanism'] == 'ammunition' for t in runs))
        self.assertEqual({t['mod'] for t in live_evidence.tests('attack_output_cross_class', current=True)},
            {'LiberatorAttackOutputTest'})
        family = self.registry['families']['weapon_ammunition_projectile_reference']
        self.assertEqual(family['provenWeapons'], ['AR-23 Liberator'])
        self.assertTrue(any('JAR-5 Dominator' in item for item in family['notPromoted']))
        cross = self.registry['families']['attack_output_cross_class']
        self.assertEqual([c['output'] for c in cross['provenCompositions']],
            ['EAT-700 Expendable Napalm', 'GL-52 De-Escalator'])
        direct = [t for t in live_evidence.tests('weapon_projectile_reference_direct') if t['result'] == 'PASS']
        self.assertEqual([t['session'] for t in direct],
            ['projectile-host-path-2026-09-29', 'projectile-source-correction-2026-09-29'])
        self.assertEqual(live_evidence.proven('weapon_ammunition_projectile_reference')['tests'],
            ['LiberatorAttackOutputTest'])

    def test_stratagem_promotions_are_exactly_the_tested_members(self):
        by_field = {}
        for field in self.stratagems['fieldInstances']:
            if field['semanticFieldId'].split('.')[0] in ('turret', 'targeting', 'minefield'):
                by_field.setdefault(field['semanticFieldId'], []).append(field)
        promoted = {'turret.yaw_speed': 9, 'turret.pitch_speed': 9, 'targeting.range': 10, 'minefield.salvos': 4}
        for field_id, fields in by_field.items():
            for field in fields:
                if field_id in promoted:
                    self.assertIsNone(field.get('acknowledgement'), field_id)
                    self.assertEqual(field['liveEvidence']['status'], 'live_proven')
                else:
                    self.assertEqual(field['acknowledgement'], 'allow_unverified_effect', field_id)
                    self.assertNotIn('liveEvidence', field)
        self.assertEqual({k: len(v) for k, v in by_field.items() if k in promoted}, promoted)

    def test_status_promotion_covers_only_projectile_direct_hit_rows(self):
        player = [f for w in self.player['weapons'] for f in w['fields'] if f.get('statusSlot')]
        for field in player:
            # Rows a weapon may not fire (charge / heat levels, spawned entities) do not inherit the promotion.
            projectile = field['backing'].get('settings') == 'damage' and field.get('writeScope') == \
                'shared_projectile_damage_definition' and field['effect']['activeSource'] == 'ACTIVE_DIRECT'
            self.assertEqual(bool(field.get('liveEvidence')), projectile, field['semanticFieldId'])
            self.assertEqual(field.get('acknowledgement') is None, projectile)
        support = [f for f in self.support['fieldInstances']
            if re.search(r'status_\d_(type|strength)$', f['semanticFieldId'])]
        for field in support:
            projectile = field['target']['path'] == 'projectile_reference' and field['semanticFieldId'].startswith('damage.')
            self.assertEqual(bool(field.get('liveEvidence')), projectile, field['instanceKey'])
            self.assertEqual(field['operation']['acknowledgement'] is None, projectile, field['instanceKey'])
        vehicle = [f for f in load('VehicleWeaponCapabilities.json')['fieldInstances'] if 'status_' in f['semanticFieldId']]
        self.assertTrue(vehicle and all(f['acknowledgement'] == 'allow_unverified_effect' for f in vehicle))

    def test_enemy_evidence_and_structure_gate(self):
        kinds = {c['name']: c['kind'] for c in self.enemies['classes']}
        for field in self.enemies['fieldInstances']:
            kind, field_id = kinds[field['target']['enemy']], field['semanticFieldId']
            live = field.get('liveEvidence')
            if field['editable'] and kind == 'enemy' and field_id in ('entity.health', 'zone.armor'):
                self.assertEqual(live['status'], 'live_proven')
            else:
                self.assertIsNone(live)
            gated = field['editable'] and kind == 'structure' and field_id in ('entity.health', 'zone.health')
            self.assertEqual(field.get('acknowledgement') == 'allow_unverified_effect', gated, field['instanceKey'])
        # Attack fields stay acknowledgement-gated (EnemyAttackDamageTest was not run).
        self.assertEqual(self.enemies['model']['fields']['damage.standard_damage']['acknowledgement'],
            'allow_unverified_effect')

    def test_examples_follow_the_evidence(self):
        promoted = ('SentryTurnSpeed', 'SentryDetectionRange', 'MinefieldSalvos', 'MaxigunStun', 'LiberatorFireStatus',
            'EnemyHealthTest', 'EnemyArmorZoneTest')
        gated = ('EnemyAttackDamageTest', 'StructureHealthTest', 'FabricatorHealthAllVariants', 'GazerHealthTest')
        for name in promoted + gated:
            addon = (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text()
            self.assertEqual('allow_unverified_effect=true' in addon, name in gated, name)


if __name__ == '__main__':
    unittest.main()
