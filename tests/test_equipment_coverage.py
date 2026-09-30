"""Equipment coverage pass (research/equipment-coverage-F5FEE03DCFDB.json): SH-32 recharge, the SH-51 body and energy
barrier, the Warp Pack, the Hover Pack, Guard Dog backpacks, drones and drone weapons, the LAS-17 heat levels, the
LAS-98 beam fire rate and the Maxigun recoil multipliers. Every field is proven offline and needs
allow_unverified_effect; members without that proof stay read-only or unknown."""
import json
import re
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
BACKPACKS = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text(encoding='utf-8'))
VEHICLE_WEAPONS = json.loads((ROOT / 'sdk/VehicleWeaponCapabilities.json').read_text(encoding='utf-8'))
PLAYER = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))
SUPPORT = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))
SNAPSHOT = json.loads((ROOT / 'validation/equipment-coverage-snapshot.json').read_text(encoding='utf-8'))


def backpack_fields(name):
    return {(f['target']['path'], f['target'].get('linked'), f['semanticFieldId']): f
        for f in BACKPACKS['fieldInstances'] if f['target'].get('backpack') == name}


class ResearchTests(unittest.TestCase):
    def test_research_is_offline_and_writes_nothing(self):
        self.assertEqual((RESEARCH['source']['writes'], RESEARCH['source']['protectionChanges']), (0, 0))

    def test_shield_recharge_members_match_three_independent_shields(self):
        decisions = RESEARCH['shields']['decisions']
        for offset, field in (('88', 'shield.recharge_delay'), ('92', 'shield.broken_recharge_delay'),
                ('96', 'shield.recharge_rate')):
            self.assertEqual(decisions[offset]['field'], field)
            self.assertEqual(decisions[offset]['independentConsumers'], 3)
            self.assertTrue(all(c['exact'] for c in decisions[offset]['correlations']))
        values = {c['consumer']: c['values'] for c in RESEARCH['shields']['consumers']}
        self.assertEqual([values['SH-32 Shield Generator Pack'][o] for o in ('88', '92', '96')], [60.0, 12.0, 150.0])
        self.assertEqual([values['SH-51 Directional Shield'][o] for o in ('88', '92', '96')], [3.0, 6.0, 300.0])
        # +100 has only an external label: published as unknown, never a field.
        self.assertIn(100, [m['offset'] for m in RESEARCH['shields']['unknownMembers']])

    def test_directional_shield_body_and_barrier_are_separate(self):
        shield = RESEARCH['directionalShield']
        self.assertTrue(shield['body']['exact'])
        self.assertEqual((shield['body']['mainHealth'], shield['body']['defaultArmor'], shield['body']['populatedZones']),
            (400, 4, 0))
        zone = shield['barrier']['health']['zones'][0]
        self.assertEqual((zone['name'], zone['actors'], zone['armor']), ('body_front', ['c_collision'], 1))
        self.assertEqual(shield['controllerLink'], {'component': 'ShieldControllerComponentData', 'offset': 0,
            'storage': 'u64', 'nameLength': 18})

    def test_warp_pack_values_and_limbs_are_exact(self):
        warp = RESEARCH['warpPack']
        self.assertTrue(all(item['exact'] for item in warp['decisions'].values()))
        limbs = {e['limb']: e for e in warp['injuries']['entries'] if e['limb']}
        self.assertEqual({limb: limbs[limb]['damage'] for limb in ('head', 'l_hand', 'r_hand', 'l_knee', 'r_knee')},
            {'head': 10.0, 'l_hand': 35.0, 'r_hand': 35.0, 'l_knee': 45.0, 'r_knee': 45.0})
        self.assertEqual(limbs['chest']['statusType'], 5)          # Fire

    def test_hover_duration_is_a_hover_only_member(self):
        row = next(m for m in RESEARCH['hoverPack']['members'] if m['offset'] == 156)
        self.assertEqual(row['values'], {'hover': 6.0, 'jump': -1.0, 'variant': -1.0})
        self.assertTrue(row['hoverOnly'])

    def test_guard_dog_chain_and_wiki_correlation(self):
        drones = RESEARCH['guardDogs']['drones']
        self.assertEqual({d['backpack']: d['weapon']['family'] for d in drones}, {'AX/AR-23 Guard Dog': 'projectile',
            'AX/LAS-5 Rover': 'beam', 'AX/FLAM-75 Hot Dog': 'spray', 'AX/ARC-3 K-9': 'arc',
            'AX/TX-13 Dog Breath': 'spray'})
        for drone in drones:
            self.assertTrue(all(drone['correlation'].values()), drone['backpack'])
            self.assertEqual(drone['deposit']['link']['offset'], 24)
            self.assertTrue(drone['drone']['health']['ownership']['uniqueOwner'])
        variant = RESEARCH['guardDogs']['variants'][0]
        self.assertEqual(variant['stratagemsDeliveringRack'], [])

    def test_double_edge_self_damage_is_data_driven(self):
        levels = RESEARCH['heat']['doubleEdge']['levels']
        self.assertEqual([(l['threshold'], l['status']) for l in levels], [(50.0, 'hotshot_laser_rifle'),
            (100.0, 'hotshot_laser_rifle_2'), (190.0, 'hotshot_laser_rifle_3')])
        self.assertEqual([l['tickDamage']['standardDamage'] for l in levels], [20, 40, 100])
        self.assertEqual(levels[2]['tickDamageStatuses'], [{'statusType': 5, 'status': 'fire', 'strength': 10.0}])
        # The self-damage rows are referenced by nothing but the three statuses.
        self.assertEqual({k: v for k, v in RESEARCH['heat']['doubleEdge']['tickDamageUsers'].items()},
            {'542': ['hotshot_laser_rifle'], '543': ['hotshot_laser_rifle_2'], '544': ['hotshot_laser_rifle_3']})
        lock = RESEARCH['heat']['doubleEdge']['overheatLock']
        self.assertEqual(lock['value'], 0)
        self.assertEqual(len(lock['zeroOn']), 2)                    # the LAS-17 and a never-overheating camera

    def test_beam_fire_rate_matches_seven_weapons(self):
        rows = RESEARCH['beamFireRate']['correlations']
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row['exact'] for row in rows))
        self.assertEqual({row['weapon']: row['fireRate'] for row in rows}['LAS-13 Trident'], 300)

    def test_maxigun_reimagined_claims_are_classified(self):
        claims = {re.split(r'[ ,]', claim['classification'])[0] for claim in RESEARCH['maxigun']['claims']}
        self.assertEqual(claims, {'already_mapped', 'genuinely_missing', 'incorrect_target', 'no_op',
            'ignored_by_request'})
        projectile = next(c for c in RESEARCH['maxigun']['claims'] if c['classification'] == 'incorrect_target')
        self.assertNotIn(RESEARCH['maxigun']['firedProjectile']['type'], projectile['rowsAt820'])
        self.assertEqual(RESEARCH['maxigun']['firedProjectile']['velocity'], 920)

    def test_scythe_identity_finding_is_recorded_not_applied(self):
        scythe = RESEARCH['scytheIdentity']
        self.assertEqual(scythe['catalogResolution'], 'DUPLICATE')
        self.assertEqual([c['matchesPublishedHeat'] for c in scythe['candidates']], [True, False])


class CatalogTests(unittest.TestCase):
    def test_new_backpack_fields_need_the_acknowledgement(self):
        for name, key in (('SH-32 Shield Generator Pack', ('backpack', None, 'shield.recharge_delay')),
                ('LIFT-182 Warp Pack', ('backpack', None, 'warp.distance')),
                ('LIFT-860 Hover Pack', ('backpack', None, 'hover.duration')),
                ('AX/AR-23 Guard Dog', ('backpack', None, 'deposit.capacity'))):
            field = backpack_fields(name)[key]
            self.assertTrue(field['editable'])
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual(field['evidence']['tier'], 'native_correlated')
            self.assertTrue(field['evidence']['correlations'])
        self.assertIn('native_correlated', BACKPACKS['evidenceTiers'])

    def test_fallback_armor_is_never_published_as_the_shield_facing_armor(self):
        sh51 = backpack_fields('SH-51 Directional Shield')
        self.assertFalse(sh51[('linked', 'energy_shield', 'entity.armor')]['editable'])
        self.assertFalse(sh51[('linked', 'energy_shield', 'shield.radius')]['editable'])
        zone = sh51[('damage_zone', 'energy_shield', 'zone.armor')]
        self.assertTrue(zone['editable'])
        self.assertEqual(zone['effect']['zoneActors'], ['c_collision'])
        dog = backpack_fields('AX/AR-23 Guard Dog')
        self.assertFalse(dog[('linked', 'drone', 'entity.armor')]['editable'])
        self.assertTrue(dog[('damage_zone', 'drone', 'zone.armor')]['editable'])

    def test_drone_weapons_reuse_the_mounted_weapon_families(self):
        carriers = {v['vehicle']: v for v in VEHICLE_WEAPONS['vehicles'] if v.get('carrier')}
        self.assertEqual(len(carriers), 5)
        fields = {}
        for item in VEHICLE_WEAPONS['fieldInstances']:
            fields.setdefault(item['weapon'], set()).add(item['semanticFieldId'])
        self.assertIn('beam.fire_rate', fields['AX/LAS-5 Rover / gun'])
        self.assertIn('heat.capacity', fields['AX/LAS-5 Rover / gun'])
        self.assertIn('arc.primary.range', fields['AX/ARC-3 K-9 / gun'])
        self.assertIn('damage.primary.status_1_type', fields['AX/TX-13 Dog Breath / gun'])
        self.assertIn('weapon.fire_rate', fields['AX/AR-23 Guard Dog / gun'])
        # The drone reloads from its backpack: the weapon's own spare-magazine counts are not exposed.
        self.assertNotIn('magazine.spare_magazines', fields['AX/AR-23 Guard Dog / gun'])

    def test_weapon_fields_publish_evidence_and_acknowledgement(self):
        sickle = {f['semanticFieldId']: f for f in next(w for w in PLAYER['weapons']
            if w['name'] == 'LAS-17 Double-Edge Sickle')['fields']}
        status = sickle['heat.level_3_self_status']
        self.assertEqual(status['allowedValues'], ['hotshot_laser_rifle', 'hotshot_laser_rifle_2', 'hotshot_laser_rifle_3'])
        self.assertTrue(status['allowNone'])
        for field in ('heat.level_1_threshold', 'heat.overheat_lock', 'heat.level_2_self_status'):
            self.assertEqual(sickle[field]['acknowledgement'], 'allow_unverified_effect')
            self.assertFalse(sickle[field]['effect']['activeSourceProven'])
        support = {(f['supportWeapon'], f['semanticFieldId']): f for f in SUPPORT['fieldInstances']}
        self.assertEqual(support[('LAS-98 Laser Cannon', 'beam.fire_rate')]['value']['baseline'], 60)
        self.assertEqual(support[('M-1000 Maxigun', 'weapon.recoil_multiplier_vertical')]['value']['baseline'], 1.0)


class SnapshotTests(unittest.TestCase):
    def test_every_field_round_trips_and_every_link_is_reproven(self):
        self.assertEqual(SNAPSHOT['status'], 'VALIDATED')
        self.assertEqual(SNAPSHOT['fields'], 81)
        for key in ('baselineMatches', 'noOps', 'changedWrites', 'rollbacks', 'conflictRejections',
                'staleExpectRejections', 'acknowledgementRejections'):
            self.assertEqual(SNAPSHOT[key], SNAPSHOT['fields'], key)
        self.assertEqual(SNAPSHOT['chainTamperRejections'], 23)
        self.assertEqual(SNAPSHOT['readOnlyRejections'], 7)
        self.assertEqual(SNAPSHOT['byFamily'], {'backpack': 55, 'drone_weapon': 16, 'player_weapon': 7,
            'support_weapon': 3})


class ApiTests(unittest.TestCase):
    def test_linked_targets_allowlists_and_ranges(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local dog=hd2.backpack('AX/AR-23 Guard Dog')
local drone=dog:drone()
assert(drone.linked=='drone'and dog:describe().linked[1]=='drone')
assert(drone:weapon().weapon=='AX/AR-23 Guard Dog / gun')
local spec=entity.validate_patch({id='a',target=drone,field=hd2.fields.entity.health,expect=100,value=500,
 allow_unverified_effect=true})
assert(spec.changes[1].descriptor.backing.linked=='drone')
rejects(function()entity.validate_patch({id='b',target=drone,field=hd2.fields.entity.armor,expect=1,value=3,
 allow_unverified_effect=true})end,'read-only')
-- A linked zone and a backpack zone never alias: the drone zone is addressed through the drone only.
rejects(function()entity.validate_patch({id='c',target={resource='backpack',backpack='AX/AR-23 Guard Dog',
 path='damage_zone',zone='zone_0'},field=hd2.fields.zone.armor,expect=1,value=2,allow_unverified_effect=true})end,
 'damage zone identity required')
rejects(function()entity.validate_patch({id='d',target={resource='backpack',backpack='B-1 Supply Pack',path='linked',
 linked='drone'},field=hd2.fields.entity.health,expect=100,value=200,allow_unverified_effect=true})end,
 'unknown linked entity')
local barrier=hd2.backpack('SH-51 Directional Shield'):energy_shield()
rejects(function()entity.validate_patch({id='e',target=barrier,field=hd2.fields.shield.recharge_delay,expect=3,value=1})end,
 'allow_unverified_effect')
assert(barrier:damage_zone('body_front').zone=='zone_0')
local warp=hd2.backpack('LIFT-182 Warp Pack')
rejects(function()entity.validate_patch({id='f',target=warp,field=hd2.fields.warp.distance,expect=10,value=1000,
 allow_unverified_effect=true})end,'reviewed range')
local sickle=hd2.weapon('LAS-17 Double-Edge Sickle')
rejects(function()weapons.validate_patch({id='g',target=sickle,field=hd2.fields.heat.level_1_self_status,
 expect='hotshot_laser_rifle',value='fire',allow_unverified_effect=true})end,'not attachable')
weapons.validate_patch({id='h',target=sickle,field=hd2.fields.heat.level_1_self_status,expect='hotshot_laser_rifle',
 value='none',allow_unverified_effect=true})
rejects(function()weapons.validate_patch({id='i',target=sickle,field=hd2.fields.heat.overheat_lock,expect=false,
 value=1,allow_unverified_effect=true})end,'must be boolean')
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
