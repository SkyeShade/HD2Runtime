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
            'live_proven': ['enemy_main_health', 'enemy_zone_armor', 'minefield_salvos', 'sentry_targeting_range',
                'sentry_turret_turn_speed', 'weapon_projectile_status_reference'],
            'not_tested': ['enemy_attack_damage'], 'inconclusive': ['structure_health']})
        self.assertEqual((catalog['summary']['tests'], catalog['summary']['passed']), (9, 7))
        for name, entry in self.registry['families'].items():
            if entry['status'] == 'live_proven':
                self.assertTrue(any(t['result'] == 'PASS' for t in live_evidence.tests(name)), name)

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
            projectile = field['backing'].get('settings') == 'damage' and field.get('writeScope') == \
                'shared_projectile_damage_definition'
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
