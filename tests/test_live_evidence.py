"""Central live-test evidence (schemas/live_evidence.json): the registry is consistent, promotions reach exactly the
recorded scope in every catalog, and untested or inconclusive families keep their acknowledgement."""
import json
import re
import unittest

from support import ROOT, run

import generate_live_evidence
import live_evidence


def load(name):
    return json.loads((ROOT / 'sdk' / name).read_text())


# Task 3 live results (schemas/live_evidence.json, session task3-actions-2026-09-29): the exact promoted pairs.
TASK3_TARGETS = [('NUX-223 Hellbomb', 'hd2.explosions.spawn'), ('R-36 Eruptor', 'hd2.projectiles.spawn'),
    ('Resupply', 'stratagem.definition_cooldown'), ('fire', 'hd2.status.apply')] + [
    ('Resupply pod slot %d <- Grenade Box' % slot, 'payload.entity') for slot in (1, 2, 3, 4)]
# Weapon composition live results (session weapon-composition-2026-09-30): the exact promoted pairs.
# The projectile builder session (2026-09-30): exact host, slot, presentation and event targets.
PROJECTILE_BUILDER_TARGETS = [('AR-2 Coyote', 'projectile.direct_damage'), ('AR-2 Coyote', 'projectile.impact_explosion'),
    ('AR-32 Pacifier', 'presentation.mode_icon'), ('AR-32 Pacifier', 'presentation.mode_label'),
    ('EAT-17 Expendable Anti-Tank', 'attack.primary.projectile'), ('K-2 Throwing Knife', 'player_damage_dealt'),
    ('M-105 Stalwart', 'attack.primary.projectile'), ('MG-206 Heavy Machine Gun', 'function_ammo.projectile'),
    ('MG-206 Heavy Machine Gun', 'presentation.mode_icon'), ('MG-206 Heavy Machine Gun', 'presentation.mode_label'),
    ('MG-206 Heavy Machine Gun', 'weapon_function.left'), ('P-35 Re-Educator', 'presentation.mode_icon'),
    ('P-35 Re-Educator', 'presentation.mode_label'), ('R-4 Hyena', 'presentation.mode_icon'),
    ('R-4 Hyena', 'presentation.mode_label'), ('S-11 Speargun', 'function_ammo.projectile'),
    ('S-11 Speargun', 'presentation.mode_icon'), ('S-11 Speargun', 'presentation.mode_label'),
    ('S-11 Speargun', 'weapon_function.left'), ('S-11 Speargun (spare twin)', 'presentation.mode_icon'),
    ('S-11 Speargun (spare twin)', 'presentation.mode_label'), ('S-11 Speargun (spare twin)', 'projectile.expiry_explosion'),
    ('local_player', 'hd2.actions.heal')]
# The vehicle projectile builder session (2026-09-30): the Patriot minigun swaps and its own row's impact slot.
VEHICLE_TARGETS = [('EXO-45 Patriot Exosuit / right_gun', 'attack.primary.projectile'),
    ('EXO-45 Patriot Exosuit / right_gun', 'projectile.impact_explosion'), ('LAS-58 Talon', 'projectile.impact_explosion')]
COMPOSITION_TARGETS = [('MG-206 Heavy Machine Gun', 'fire_rate.modes'), ('AR-23 Liberator', 'fire_rate.modes'),
    ('AR-23 Liberator', 'weapon_function.left'), ('SG-20 Halt', 'rounds.feed_capacity_1'),
    ('SG-20 Halt', 'rounds.feed_capacity_2'), ('AR-23C Liberator Concussive', 'presentation.armor_penetration')]


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
            'live_proven': ['attack_output_cross_class', 'custom_icon_resource_family',
                'custom_stratagem_expendable_availability', 'custom_stratagem_expendable_clone',
                'custom_stratagem_expendable_payload', 'custom_stratagem_weapon_variant', 'donor_row_slot_composition',
                'enemy_main_health',
                'enemy_zone_armor',
                'event_action_explosion_named', 'event_action_heal', 'event_action_projectile', 'event_action_status',
                'event_damage_source_attribution', 'event_player_died_position', 'event_weapon_in_hand',
                'minefield_salvos', 'pod_payload_pair', 'projectile_slot_composition', 'sentry_targeting_range',
                'sentry_turret_turn_speed', 'stratagem_calldown_code', 'stratagem_carrier_bombardment_pattern',
                'stratagem_carrier_presentation_lifecycle', 'stratagem_carrier_shell_redirect',
                'stratagem_custom_panel_icon',
                'stratagem_custom_panel_lifecycle', 'stratagem_custom_panel_multiple_instances',
                'stratagem_custom_panel_rendering',
                'stratagem_custom_panel_selection',
                'stratagem_definition_cooldown', 'stratagem_mission_slot_conversion',
                'stratagem_presentation', 'stratagem_presentation_custom_image',
                'stratagem_presentation_custom_text', 'stratagem_selector_advance', 'stratagem_selector_lifecycle',
                'stratagem_selector_rendering', 'stratagem_slot_focus', 'stratagem_slot_icon_borrowed',
                'stratagem_slot_overlay', 'stratagem_virtual_carrier_conversion',
                'stratagem_virtual_slot_reconstruction',
                'support_projectile_reference',
                'vehicle_projectile_reference', 'weapon_ammunition_projectile_reference', 'weapon_fire_rate_modes_native',
                'weapon_fire_rate_selector_added', 'weapon_heat_per_shot', 'weapon_magazine_capacity',
                'weapon_mode_presentation', 'weapon_presentation_penetration_label', 'weapon_programmable_ammo_added',
                'weapon_projectile_damage', 'weapon_projectile_reference_direct', 'weapon_projectile_status_reference',
                'weapon_rounds_feed_capacity'],
            'live_partial': ['backpack_deposit_ammo', 'custom_stratagem_expendable_delivery',
                'custom_stratagem_native_panel', 'custom_stratagem_pelican_native_gun', 'custom_stratagem_silo'],
            'not_tested': ['enemy_attack_damage'],
            'inconclusive': ['stratagem_selector_grid_placement', 'structure_health'],
            'live_failed': ['backpack_shield_default_armor', 'runtime_gui_render_order',
                'weapon_projectile_reference_dormant_member'],
            'pending': ['backpack_shield_zone_armor',
                'custom_stratagem_sentry_multiplayer', 'custom_stratagem_uses',
                'eagle_component_fields',
                'enemy_spawn_weights',
                'orbital_pattern_fields', 'projectile_homing', 'projectile_more_donors', 'sentry_component_fields', 'stratagem_call_in_time', 'support_charge_level_rows',
                'support_overcharge_explosion_rows', 'weapon_presentation_traits']})
        self.assertEqual((catalog['summary']['tests'], catalog['summary']['passed']), (123, 96))
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
        runs = [t for t in live_evidence.tests('weapon_ammunition_projectile_reference', current=True)
            if t['mod'] == 'LiberatorAttackOutputTest']
        self.assertEqual(sorted(t['choice'] for t in runs), ['EAT-700 Napalm', 'GL-52 Arc (impact)'])
        # UnifiedProjectileSwapTest (2026-09-30) passed the Liberator -> Talon ammunition swap again.
        self.assertEqual([t['donor'] for t in live_evidence.tests('weapon_ammunition_projectile_reference', current=True)
            if t['mod'] == 'UnifiedProjectileSwapTest'], ['LAS-58 Talon'])
        self.assertTrue(all(t['result'] == 'PASS' and all(t['evidence'].values()) and t['host'] == 'AR-23 Liberator'
            and t['mechanism'] == 'ammunition' for t in runs))
        self.assertEqual({t['mod'] for t in live_evidence.tests('attack_output_cross_class', current=True)},
            {'LiberatorAttackOutputTest', 'UnifiedProjectileSwapTest'})
        family = self.registry['families']['weapon_ammunition_projectile_reference']
        self.assertEqual(family['provenWeapons'], ['AR-23 Liberator'])
        self.assertTrue(any('JAR-5 Dominator' in item for item in family['notPromoted']))
        cross = self.registry['families']['attack_output_cross_class']
        self.assertEqual([(c['host'], c['output']) for c in cross['provenCompositions']],
            [('AR-23 Liberator', 'EAT-700 Expendable Napalm'), ('AR-23 Liberator', 'GL-52 De-Escalator'),
             ('SMG-32 Reprimand', 'EAT-700 Expendable Napalm')])
        direct = [t for t in live_evidence.tests('weapon_projectile_reference_direct') if t['result'] == 'PASS']
        self.assertEqual([t['session'] for t in direct],
            ['projectile-host-path-2026-09-29', 'projectile-source-correction-2026-09-29'])
        self.assertEqual(live_evidence.proven('weapon_ammunition_projectile_reference')['tests'],
            ['LiberatorAttackOutputTest', 'UnifiedProjectileSwapTest'])

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
            # A charge-level row only one charge level fires (the PLAS-45 Epoch's shots) does not inherit it either.
            projectile = field['target']['path'] == 'projectile_reference' and field['semanticFieldId'].startswith(
                'damage.') and not field.get('chargeLevel')
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
        ('Orbital 120mm HE Barrage', 'stratagem.calldown_code'), ('GR-8 Recoilless Rifle', 'stratagem.calldown_code'),
        ('Orbital 120mm HE Barrage', 'stratagem.presentation.name'),
        ('Orbital 120mm HE Barrage', 'stratagem.presentation.name_cased'),
        ('Orbital 120mm HE Barrage', 'stratagem.presentation.description'),
        ('Orbital 120mm HE Barrage', 'stratagem.presentation.icon'),
            ('SG-20 Halt', 'damage.primary.standard_damage')] + TASK3_TARGETS + COMPOSITION_TARGETS
            + PROJECTILE_BUILDER_TARGETS + VEHICLE_TARGETS))
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

    def test_projectile_builder_session_promotes_exactly_the_tested_tuples(self):
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        session = next(s for s in registry['sessions'] if s['id'] == 'projectile-builder-2026-09-30')
        self.assertEqual(sorted({t['mod'] for t in session['tests']}), ['HMGSpecialAmmoTest', 'ProjectileSlotTest',
            'SpeargunProjectileBuilderTest', 'UnifiedProjectileSwapTest', 'VampiricThrowingKnivesTest'])
        self.assertTrue(all(t['result'] == 'PASS' for t in session['tests']))
        families = registry['families']
        for name in ('weapon_programmable_ammo_added', 'support_projectile_reference', 'projectile_slot_composition',
                'weapon_mode_presentation', 'event_damage_source_attribution', 'event_action_heal'):
            self.assertEqual(families[name]['status'], 'live_proven', name)
        # The partial GL-52 Speargun run is superseded, not deleted.
        speargun = [t for s in registry['sessions'] for t in s['tests'] if t['mod'] == 'SpeargunGasStunTest']
        self.assertEqual([t.get('supersededBy') for t in speargun], ['projectile-builder-2026-09-30'])
        self.assertIn('damage-proportional heal', ' '.join(families['event_action_heal']['notPromoted']))
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local outputs=require('hd2runtime/domains/output_writes')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local function swap(weapon,value)
 local source=weapon:projectile_source()
 return patches.validate{id='s',target=source.target,field=source.field,expect=source.expect,value=value}
end
-- Support hosts: exactly the two tested pairs drop allow_unverified_effect.
local eat,stalwart=hd2.support_weapon('EAT-17 Expendable Anti-Tank'),hd2.support_weapon('M-105 Stalwart')
swap(eat,hd2.weapon('PLAS-1 Scorcher'):attack('primary'):projectile())
swap(eat,hd2.attack_output('PLAS-1 Scorcher'))
swap(stalwart,hd2.attack_output('APW-1 Anti-Materiel Rifle'))
rejects(function()swap(eat,hd2.attack_output('EAT-411 Leveller'))end,'allow_unverified_effect')
rejects(function()swap(stalwart,hd2.attack_output('M-105 Stalwart')=='x'or hd2.attack_output('MG-206 Heavy Machine Gun'))end,
 'allow_unverified_effect')
rejects(function()swap(hd2.support_weapon('EAT-411 Leveller'),hd2.attack_output('PLAS-1 Scorcher'))end,
 'allow_unverified_effect')
-- The tested cross-class component composition; another donor on the same host keeps both acknowledgements.
swap(hd2.weapon('SMG-32 Reprimand'),hd2.support_weapon('EAT-700 Expendable Napalm'):attack('primary'):projectile())
rejects(function()swap(hd2.weapon('SMG-32 Reprimand'),hd2.attack_output('GL-52 De-Escalator'))end,
 'allow_unverified_reference')
-- Programmable modes: the tested (host, binding, function projectile) pairs.
local function mode(weapon,value)
 local source=weapon:feed('programmable'):source()
 return transactions.validate{id='m',target=source.target,changes={
  {field=source.binding.field,expect=source.binding.expect,value=source.binding.value},
  {field='function_ammo.projectile',expect=source.expect,value=value}}}
end
local spear,hmg=hd2.support_weapon('S-11 Speargun'),hd2.support_weapon('MG-206 Heavy Machine Gun')
mode(spear,hd2.attack_output('S-11 Speargun (spare twin)'))
for _,name in ipairs({'R-4 Hyena','AR-32 Pacifier','P-35 Re-Educator'})do mode(hmg,hd2.attack_output(name))end
rejects(function()mode(spear,hd2.attack_output('A/M-23 EMS Mortar Sentry'))end,'allow_unverified_effect')
rejects(function()mode(hmg,hd2.attack_output('AR-2 Coyote'))end,'allow_unverified_effect')
-- Slots: the exact (row, slot, donor) tuples.
local coyote=hd2.attack_output('AR-2 Coyote')
local function slot(target,field,expect,value,extra)
 local request={id='x',target=target,changes={{field=field,expect=expect,value=value}}}
 for k,v in pairs(extra or{})do request[k]=v end
 return outputs.validate_transaction(request)
end
for _,value in ipairs({hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
  hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion(),hd2.attack_output('S-11 Speargun'):expiry_explosion(),
  hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion(),'none'})do
 slot(coyote,'projectile.impact_explosion','none',value)
end
slot(coyote,'projectile.direct_damage',coyote:direct_damage(),hd2.attack_output('AR-32 Pacifier'):direct_damage())
rejects(function()slot(coyote,'projectile.impact_explosion','none',hd2.attack_output('R-36 Eruptor'):impact_explosion())end,
 'allow_unverified_effect')
rejects(function()slot(coyote,'projectile.expiry_explosion','none',
 hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion())end,'allow_unverified_effect')
local twin=hd2.attack_output('S-11 Speargun (spare twin)')
slot(twin,'projectile.expiry_explosion',twin:expiry_explosion(),hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion())
-- Presentation: the tested labels with their auto icons; any other label keeps the acknowledgement.
local function label(target,value,icon,extra)
 local view=target:describe().presentation
 local request={id='l',target=target,changes={{field='presentation.mode_label',expect=view.label,value=value},
  {field='presentation.mode_icon',expect=view.icon,value=icon or'auto'}}}
 for k,v in pairs(extra or{})do request[k]=v end
 return outputs.validate_transaction(request)
end
label(twin,'stun');label(hd2.attack_output('S-11 Speargun'),'gas');label(hd2.attack_output('R-4 Hyena'),'incendiary')
rejects(function()label(twin,'flak')end,'allow_unverified_effect')
rejects(function()label(twin,'stun','ammo_flak')end,'allow_unverified_effect')
-- A shared row keeps allow_shared even for a live-proven value.
local hmg_output=hd2.attack_output('MG-206 Heavy Machine Gun')
rejects(function()label(hmg_output,'standard')end,'allow_shared')
label(hmg_output,'standard',nil,{allow_shared=true})
return 'ok'
'''), b'ok')

    def test_vehicle_projectile_session_promotes_exactly_the_tested_scopes(self):
        """VehicleProjectileBuilderTest (2026-09-30): the Patriot minigun <- EAT-17, Talon and Scorcher swaps and its
        own bullet row's four impact explosions. The status bullets, other mounts and donors, and an effect following a
        swapped projectile stay unproven; allow_shared is never dropped."""
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        session = next(s for s in registry['sessions'] if s['id'] == 'vehicle-projectile-builder-2026-09-30')
        self.assertEqual([(t['operation'], t.get('choice')) for t in session['tests']],
            [('patriot-minigun-projectile', 'EAT-17'), ('patriot-minigun-projectile', 'Talon'),
             ('patriot-minigun-projectile', 'Scorcher'),
             ('patriot-minigun-impact', 'Grenade blast, Gas cloud, EMS field, Napalm')])
        family = registry['families']['vehicle_projectile_reference']
        self.assertEqual(family['provenTargets'], [{'target': 'EXO-45 Patriot Exosuit / right_gun',
            'field': 'attack.primary.projectile', 'values': ['output/v1/projectile/eat-17-expendable-anti-tank',
                'output/v1/projectile/las-58-talon', 'output/v1/projectile/plas-1-scorcher']}])
        self.assertIn('status bullets', ' '.join(family['notPromoted']))
        self.assertIn('a slot effect following a swapped host projectile',
            registry['families']['projectile_slot_composition']['notPromoted'])
        vehicles = {(i['weapon'], i['semanticFieldId']): i for i in load('VehicleWeaponCapabilities.json')['fieldInstances']}
        patriot = vehicles[('EXO-45 Patriot Exosuit / right_gun', 'attack.primary.projectile')]
        self.assertEqual((patriot['acknowledgement'], patriot['liveProvenValues']), ('allow_unverified_effect',
            family['provenTargets'][0]['values']))
        for key in (('EXO-49 Emancipator Exosuit / left_gun', 'attack.primary.projectile'),
                ('M-102 Gunner FRV / gun', 'attack.primary.projectile')):
            self.assertNotIn('liveProvenValues', vehicles[key], key)
        outputs = {o['owner']['name']: o for o in load('AttackOutputCapabilities.json')['outputs']}
        impact = outputs['EXO-45 Patriot Exosuit / right_gun']['slots']['impactExplosion']
        self.assertEqual((impact['shared'], impact['liveProvenValues']), (True, ['none',
            'output/v1/projectile/a-m-23-ems-mortar-sentry#expiryExplosion',
            'output/v1/projectile/eat-700-expendable-napalm#impactExplosion',
            'output/v1/projectile/gl-21-grenade-launcher#impactExplosion',
            'output/v1/projectile/s-11-speargun#expiryExplosion']))
        self.assertEqual(outputs['EXO-45 Patriot Exosuit / right_gun']['slots']['expiryExplosion']['liveProvenValues'],
            [])
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local outputs=require('hd2runtime/domains/output_writes')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local source=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun'):projectile_source()
local function swap(value,s)
 s=s or source
 return patches.validate{id='s',target=s.target,field=s.field,expect=s.expect,value=value}
end
-- The three tested donors (two of them cross-class) and the restore need no acknowledgement.
for _,name in ipairs({'EAT-17 Expendable Anti-Tank','LAS-58 Talon','PLAS-1 Scorcher'})do swap(hd2.attack_output(name))end
swap(hd2.weapon('LAS-58 Talon'):attack('primary'):projectile())
swap(source.expect)
-- Offered but not reported (the status bullets), another donor, another mount.
for _,name in ipairs({'R-4 Hyena','AR-32 Pacifier','P-35 Re-Educator','EAT-700 Expendable Napalm'})do
 rejects(function()swap(hd2.attack_output(name))end,'allow_unverified_effect')
end
rejects(function()swap(hd2.attack_output('EAT-17 Expendable Anti-Tank'),
 hd2.vehicle('EXO-49 Emancipator Exosuit'):weapon('left_gun'):projectile_source())end,'allow_unverified_effect')
-- The own row's impact slot: the four tested explosions and none, allow_shared still required.
local row=hd2.attack_output('EXO-45 Patriot Exosuit / right_gun')
local function slot(field,value,extra)
 local request={id='x',target=row,changes={{field=field,expect='none',value=value}}}
 for k,v in pairs(extra or{})do request[k]=v end
 return outputs.validate_transaction(request)
end
for _,value in ipairs({hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
  hd2.attack_output('S-11 Speargun'):expiry_explosion(),hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion(),
  hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion(),'none'})do
 slot('projectile.impact_explosion',value,{allow_shared=true})
end
rejects(function()slot('projectile.impact_explosion',hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion())end,
 'allow_shared')
rejects(function()slot('projectile.impact_explosion',hd2.attack_output('R-36 Eruptor'):impact_explosion(),
 {allow_shared=true})end,'allow_unverified_effect')
rejects(function()slot('projectile.expiry_explosion',hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
 {allow_shared=true})end,'allow_unverified_effect')
-- The explicit donor-row composition (follow-up session): exactly the Talon row with the GL-21 grenade blast. Any
-- other effect on the Talon row, or the grenade blast on another donor row, keeps the acknowledgement.
local function talon(value,target)
 return outputs.validate_transaction{id='t',target=target or hd2.attack_output('LAS-58 Talon'),allow_shared=target~=nil,
  changes={{field='projectile.impact_explosion',expect='none',value=value}}}
end
talon(hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion())
rejects(function()talon(hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion())end,'allow_unverified_effect')
rejects(function()talon('none')end,'allow_unverified_effect')
rejects(function()talon(hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
 hd2.attack_output('PLAS-1 Scorcher'))end,'allow_unverified_effect')
return 'ok'
'''), b'ok')
        # The three operation kinds stay separate records: host swap, host-native row slot, donor-row slot.
        donor = registry['families']['donor_row_slot_composition']
        self.assertEqual(sorted(donor['operationModel']), ['donorRowSlot', 'hostNativeRowSlot', 'hostProjectileSwap'])
        self.assertEqual(donor['provenTargets'], [{'target': 'LAS-58 Talon', 'field': 'projectile.impact_explosion',
            'values': ['output/v1/projectile/gl-21-grenade-launcher#impactExplosion']}])
        self.assertEqual(donor['provenOperationChains'], [{'hostSwap': {'host': 'EXO-45 Patriot Exosuit / right_gun',
            'field': 'attack.primary.projectile', 'value': 'output/v1/projectile/las-58-talon'},
            'rowSlot': {'row': 'LAS-58 Talon', 'field': 'projectile.impact_explosion',
                'value': 'output/v1/projectile/gl-21-grenade-launcher#impactExplosion'}, 'separateOperations': True}])
        followup = next(s for s in registry['sessions'] if s['id'] == 'vehicle-projectile-builder-followup-2026-09-30')
        self.assertEqual([(t['operation'], t['family'], t['result']) for t in followup['tests']],
            [('patriot-minigun-projectile', 'vehicle_projectile_reference', 'PASS'),
             ('talon-bolt-impact', 'donor_row_slot_composition', 'PASS')])
        for needle in ('every other donor row', 'the other mounted weapons', 'the status bullets',
                'shared sentry behaviour'):
            self.assertIn(needle, ' '.join(donor['notPromoted']))

    def test_weapon_composition_promotes_exactly_the_tested_scopes(self):
        """Weapon composition (2026-09-30): the MG-206 rates, the Liberator's added selector (the rate_of_fire binding
        only), the Halt feed capacities and the Concussive's light/medium/heavy label drop allow_unverified_effect;
        every other weapon and value keeps it. The Speargun's partial GL-52 run is superseded by the projectile
        builder session (2026-09-30), which promoted exactly its tested pairs."""
        families = self.registry['families']
        self.assertEqual(families['weapon_programmable_ammo_added']['status'], 'live_proven')
        self.assertEqual(families['weapon_presentation_traits']['status'], 'pending')
        [speargun] = [t for t in live_evidence.tests('weapon_programmable_ammo_added') if t['mod'] == 'SpeargunGasStunTest']
        self.assertEqual((speargun['result'], speargun['host'], speargun['donor'], speargun['supersededBy']),
            ('PARTIAL', 'S-11 Speargun', 'GL-52 De-Escalator', 'projectile-builder-2026-09-30'))
        self.assertTrue(all(speargun['evidence'].values()))
        self.assertEqual(live_evidence.proven_target('weapon_fire_rate_selector_added', 'AR-23 Liberator',
            'weapon_function.left')['values'], ['rate_of_fire'])
        player = {(w['name'], f['semanticFieldId']): f for w in load('PlayerWeaponAuthoringCapabilities.json')['weapons']
            for f in w['fields']}
        self.assertIsNone(player[('AR-23 Liberator', 'fire_rate.modes')]['acknowledgement'])
        left = player[('AR-23 Liberator', 'weapon_function.left')]
        self.assertEqual((left['acknowledgement'], left['liveProvenValues']), ('allow_unverified_effect', ['rate_of_fire']))
        label = player[('AR-23C Liberator Concussive', 'presentation.armor_penetration')]
        self.assertEqual((label['acknowledgement'], label['liveProvenValues']),
            ('allow_unverified_effect', ['heavy', 'light', 'medium']))
        for key in (('AR-23C Liberator Concussive', 'fire_rate.modes'), ('AR-23 Liberator', 'presentation.traits'),
                ('AR-23C Liberator Concussive', 'presentation.traits'), ('AR-61 Tenderizer', 'fire_rate.modes'),
                ('AR-23 Liberator', 'presentation.armor_penetration')):
            self.assertEqual(player[key]['acknowledgement'], 'allow_unverified_effect', key)
            self.assertNotIn('liveEvidence', player[key], key)
        support = {(f['supportWeapon'], f['semanticFieldId']): f for f in
            load('SupportWeaponAuthoringCapabilities.json')['fieldInstances']}
        self.assertIsNone(support[('MG-206 Heavy Machine Gun', 'fire_rate.modes')]['operation']['acknowledgement'])
        for key in (('MG-43 Machine Gun', 'fire_rate.modes'), ('EAT-411 Leveller', 'function_ammo.projectile')):
            self.assertEqual(support[key]['operation']['acknowledgement'], 'allow_unverified_effect', key)
            self.assertNotIn('liveEvidence', support[key], key)
        # The Speargun's selector and function projectile are promoted for the tested values only (the builder
        # session); every other value keeps the acknowledgement.
        for key, values in ((('S-11 Speargun', 'function_ammo.projectile'),
                ['output/v1/projectile/s-11-speargun-spare-twin']),
                (('S-11 Speargun', 'weapon_function.left'), ['programmable_ammo'])):
            self.assertEqual(support[key]['operation']['acknowledgement'], 'allow_unverified_effect', key)
            self.assertEqual(support[key]['liveEvidence']['values'], values, key)
        for name, needs in (('HMGFireRateModesTest', False), ('AddedFireRateModeTest', False),
                ('WeaponPresentationTest', False), ('SpeargunGasStunTest', True)):
            addon = (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text()
            self.assertEqual('allow_unverified_effect=true' in addon, needs, name)


if __name__ == '__main__':
    unittest.main()
