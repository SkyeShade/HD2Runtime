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


# Task 3 live results (schemas/live_evidence.json, session task3-actions-2026-09-29): the exact promoted pairs.
TASK3_TARGETS = [('NUX-223 Hellbomb', 'hd2.explosions.spawn'), ('R-36 Eruptor', 'hd2.projectiles.spawn'),
    ('Resupply', 'stratagem.definition_cooldown'), ('fire', 'hd2.status.apply')] + [
    ('Resupply pod slot %d <- Grenade Box' % slot, 'payload.entity') for slot in (1, 2, 3, 4)]


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
            'live_proven': ['attack_output_cross_class', 'enemy_main_health', 'enemy_zone_armor',
                'event_action_explosion_named', 'event_action_projectile', 'event_action_status',
                'event_player_died_position', 'event_weapon_in_hand', 'minefield_salvos', 'pod_payload_pair',
                'sentry_targeting_range', 'sentry_turret_turn_speed', 'stratagem_definition_cooldown',
                'weapon_ammunition_projectile_reference', 'weapon_heat_per_shot', 'weapon_magazine_capacity',
                'weapon_projectile_damage', 'weapon_projectile_reference_direct', 'weapon_projectile_status_reference'],
            'live_partial': ['backpack_deposit_ammo'],
            'not_tested': ['enemy_attack_damage'], 'inconclusive': ['structure_health'],
            'live_failed': ['backpack_shield_default_armor', 'weapon_projectile_reference_dormant_member'],
            'pending': ['backpack_shield_zone_armor']})
        self.assertEqual((catalog['summary']['tests'], catalog['summary']['passed']), (29, 22))
        for name, entry in self.registry['families'].items():
            if entry['status'] == 'live_proven':
                self.assertTrue(any(t['result'] == 'PASS' for t in live_evidence.tests(name)), name)

    def test_task3_promotes_exactly_the_tested_scopes(self):
        """Task 3 (all five PASS): only the exact tested identities are promoted; untested identities, other players,
        client requests and inferred slots stay unpromoted."""
        families = self.registry['families']
        scoped = {name: [(p['target'], p['field']) for p in families[name].get('provenTargets') or []]
            for name in ('event_action_explosion_named', 'event_action_projectile', 'event_action_status')}
        self.assertEqual(scoped, {'event_action_explosion_named': [('NUX-223 Hellbomb', 'hd2.explosions.spawn')],
            'event_action_projectile': [('R-36 Eruptor', 'hd2.projectiles.spawn')],
            'event_action_status': [('fire', 'hd2.status.apply')]})
        for name in ('event_action_explosion_named', 'event_action_projectile', 'event_action_status'):
            self.assertTrue(any('other players' in item for item in families[name]['notPromoted']), name)
        self.assertIn('the B-100 Portable Hellbomb (type 125)', families['event_action_explosion_named']['notPromoted'])
        weapon = families['event_weapon_in_hand']
        self.assertIn('remote players (not read; unproven)', weapon['notPromoted'])
        self.assertTrue(any('support, held_item and unknown' in item for item in weapon['notPromoted']))
        self.assertEqual(families['pod_payload_pair']['acknowledgementRemoved'], 'allow_unverified_reference')
        catalog = load('EventCatalog.json')['actions']
        self.assertEqual([n['name'] for n in catalog['explosions']['named'] if n['liveProven']], ['NUX-223 Hellbomb'])
        self.assertEqual(catalog['explosions']['liveProvenWeapons'], [])
        self.assertEqual(catalog['projectiles']['liveProven'], ['R-36 Eruptor'])
        self.assertEqual([s['id'] for s in catalog['statusEffects']['statuses'] if s['liveProven']], ['fire'])

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


    def test_effect_diagnostics_promote_exactly_the_tested_targets(self):
        """The five passing diagnostics promote their exact (target, field) pairs and nothing else; the Maxigun backpack
        is partial and keeps its acknowledgement."""
        self.assertEqual(sorted(live_evidence.proven_targets()), sorted([
            ('LAS-16 Sickle', 'heat.heat_per_shot'), ('M-1000 Maxigun', 'damage.primary.standard_damage'),
            ('MA5C Assault Rifle', 'magazine.capacity'), ('Orbital Precision Strike', 'stratagem.definition_cooldown'),
            ('SG-20 Halt', 'damage.primary.standard_damage')] + TASK3_TARGETS))
        weapons = load('PlayerWeaponAuthoringCapabilities.json')
        promoted = sorted((w['name'], f['semanticFieldId']) for w in weapons['weapons'] for f in w['fields']
            if (f.get('liveEvidence') or {}).get('family') in ('weapon_magazine_capacity', 'weapon_heat_per_shot',
                'weapon_projectile_damage'))
        self.assertEqual(promoted, [('LAS-16 Sickle', 'heat.heat_per_shot'), ('MA5C Assault Rifle', 'magazine.capacity'),
            ('SG-20 Halt', 'damage.primary.standard_damage')])
        support = load('SupportWeaponAuthoringCapabilities.json')
        promoted = [(f['supportWeapon'], f['qualifiedSemanticFieldId']) for f in support['fieldInstances']
            if (f.get('liveEvidence') or {}).get('family') == 'weapon_projectile_damage']
        self.assertEqual(promoted, [('M-1000 Maxigun', 'damage.primary.standard_damage')])
        stratagems = load('StratagemAuthoringCapabilities.json')
        promoted = [s['name'] for s in stratagems['stratagems'] if s['cooldownCapability'].get('liveEvidence')]
        self.assertEqual(sorted(promoted), ['Orbital Precision Strike', 'Resupply'])
        backpack = self.registry['families']['backpack_deposit_ammo']
        self.assertEqual((backpack['status'], backpack['provenTargets']), ('live_partial', []))
        backpacks = load('BackpackAuthoringCapabilities.json')
        for field in backpacks['fieldInstances']:
            if field['semanticFieldId'].startswith('deposit.') and field['editable']:
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                self.assertNotIn('liveEvidence', field)

if __name__ == '__main__':
    unittest.main()
