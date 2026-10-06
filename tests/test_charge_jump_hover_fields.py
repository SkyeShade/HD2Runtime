"""Charge fields (scripts/charge_fields.py) and jump / hover movement fields (scripts/jump_hover_fields.py): every new or
corrected field on every applicable weapon or pack, baselines equal to the research values, the deprecated charge ids,
the acknowledgement, range, boolean and reference rules, and the retained-snapshot overlay validation."""
import json
import struct
import unittest

from support import ROOT, run

SUPPORT = json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text(encoding='utf-8'))
BACKPACKS = json.loads((ROOT / 'sdk/BackpackAuthoringCapabilities.json').read_text(encoding='utf-8'))
CHARGE = json.loads((ROOT / 'research/railgun-charge-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
HOVER = json.loads((ROOT / 'research/hoverpack-components-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SCHEMA = json.loads((ROOT / 'schemas/player_weapon_fields.json').read_text(encoding='utf-8'))
ENTITY_SCHEMA = json.loads((ROOT / 'schemas/entity_fields.json').read_text(encoding='utf-8'))
SNAPSHOT_REPORT = ROOT / 'validation/charge-jump-hover-snapshot.json'

TIMES = ('charge.level_1', 'charge.level_2', 'charge.level_3')
LEGACY = ('charge.minimum_seconds', 'charge.maximum_seconds')
# field -> research matrix path (research/railgun-charge-F5FEE03DCFDB.json)
CHARGE_PATHS = {'charge.level_1': '0[0].0', 'charge.level_2': '0[1].0', 'charge.level_3': '0[2].0',
    'charge.minimum_seconds': '72.0', 'charge.maximum_seconds': '72.4',
    'charge.speed_multiplier_min': '72.0', 'charge.speed_multiplier_overcharge': '72.4',
    'charge.damage_multiplier_min': '72.8', 'charge.damage_multiplier_overcharge': '72.12',
    'charge.penetration_multiplier_min': '72.16', 'charge.penetration_multiplier_overcharge': '72.20',
    'charge.arc_distance_multiplier_min': '72.24', 'charge.arc_distance_multiplier_overcharge': '72.28',
    'charge.auto_fire_at_full': '184', 'charge.explode_at_overcharge': '185', 'charge.burst_shots': '188',
    'charge.burst_interval_seconds': '192', 'charge.overcharge_limit_seconds': '204.4'}
PROJECTILE = ('charge.speed_multiplier_min', 'charge.speed_multiplier_overcharge')
HIT = ('charge.damage_multiplier_min', 'charge.damage_multiplier_overcharge', 'charge.penetration_multiplier_min',
    'charge.penetration_multiplier_overcharge')
ARC = ('charge.arc_distance_multiplier_min', 'charge.arc_distance_multiplier_overcharge')
OVERCHARGE = ('charge.explode_at_overcharge', 'charge.overcharge_limit_seconds', 'charge.overcharge_explosion')
BURST = ('charge.burst_shots', 'charge.burst_interval_seconds')
EXPECTED_CHARGE = {
    'RS-422 Railgun': set(TIMES + LEGACY + PROJECTILE + HIT + OVERCHARGE + BURST + ('charge.auto_fire_at_full',)),
    'PLAS-45 Epoch': set(TIMES + LEGACY + PROJECTILE + HIT + OVERCHARGE + BURST),
    'ARC-3 Arc Thrower': set(TIMES + LEGACY + HIT + ARC + BURST + ('charge.auto_fire_at_full',)),
    '40-K Meltagun': set(TIMES + LEGACY + ('charge.auto_fire_at_full',)),
}
JUMP_ONLY = ('jump.launch_duration', 'jump.launch_forward_ratio', 'jump.sustain_start_delay', 'jump.air_control_max_speed',
    'jump.takeoff_forward_speed', 'jump.takeoff_speed', 'jump.takeoff_speed_alternate_stance')
SHARED = ('jump.sustain_thrust', 'jump.sustain_duration', 'jump.sustain_forward_ratio', 'jump.sustain_start_speed',
    'jump.sustain_cutoff_speed', 'jump.air_control_acceleration')
HOVER_ONLY = ('hover.max_horizontal_speed', 'hover.max_vertical_speed', 'hover.vertical_acceleration_low_speed',
    'hover.vertical_acceleration_high_speed', 'hover.vertical_speed_range_end', 'hover.fuel_rate_low_speed',
    'hover.fuel_rate_high_speed')
MOVEMENT_PATHS = {'jump.launch_duration': '24', 'jump.launch_forward_ratio': '32', 'jump.sustain_thrust': '36',
    'jump.sustain_duration': '40', 'jump.sustain_forward_ratio': '44', 'jump.sustain_start_delay': '48',
    'jump.sustain_start_speed': '52', 'jump.sustain_cutoff_speed': '56', 'jump.air_control_acceleration': '60',
    'jump.air_control_max_speed': '176[0]', 'jump.takeoff_forward_speed': '208', 'jump.takeoff_speed': '212',
    'jump.takeoff_speed_alternate_stance': '216', 'hover.max_horizontal_speed': '176[0]',
    'hover.max_vertical_speed': '176[1]', 'hover.vertical_acceleration_low_speed': '160[1].0',
    'hover.vertical_acceleration_high_speed': '160[1].4', 'hover.vertical_speed_range_end': '184[1].4',
    'hover.fuel_rate_low_speed': '200[0]', 'hover.fuel_rate_high_speed': '200[1]'}


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def charge_instances(weapon):
    return {item['semanticFieldId']: item for item in SUPPORT['fieldInstances']
        if item['supportWeapon'] == weapon and item['semanticFieldId'].startswith('charge.')}


def pack_fields(name):
    return {item['semanticFieldId']: item for item in BACKPACKS['fieldInstances']
        if item['target']['backpack'] == name and item['target']['path'] == 'backpack'}


class SchemaTests(unittest.TestCase):
    def test_existing_charge_ids_keep_offsets_and_correct_metadata(self):
        definitions = {item['id']: item for item in SCHEMA['fields']}
        for field_id, offset, name in (('charge.level_1', 0, 'Minimum charge time'),
                ('charge.level_2', 24, 'Full charge time'), ('charge.level_3', 48, 'Overcharge time')):
            self.assertEqual((definitions[field_id]['offset'], definitions[field_id]['unit'],
                definitions[field_id]['display_name']), (offset, 'seconds', name))
        for field_id, offset, canonical in (('charge.minimum_seconds', 72, 'charge.speed_multiplier_min'),
                ('charge.maximum_seconds', 76, 'charge.speed_multiplier_overcharge')):
            self.assertEqual(definitions[field_id]['offset'], offset)
            self.assertEqual(definitions[field_id]['unit'], 'multiplier')
            self.assertEqual(definitions[canonical]['offset'], offset)
            self.assertEqual(definitions[field_id]['semantic_target'], definitions[canonical]['semantic_target'])
        rules = {(rule['alias'], rule['canonical']): rule for rule in SCHEMA['alias_rules']}
        for alias, canonical in (('charge.minimum_seconds', 'charge.speed_multiplier_min'),
                ('charge.maximum_seconds', 'charge.speed_multiplier_overcharge')):
            self.assertTrue(rules[(alias, canonical)]['deprecated'])
            self.assertTrue(rules[(alias, canonical)]['requires_identical_backing'])

    def test_launch_thrust_unit_is_corrected_and_id_kept(self):
        definitions = {item['id']: item for item in ENTITY_SCHEMA['fields']}
        launch = definitions['jump.vertical_launch_velocity']
        self.assertEqual((launch['offset'], launch['unit']), (0, 'meters_per_second_squared'))
        for field_id in JUMP_ONLY + SHARED + HOVER_ONLY:
            self.assertEqual(definitions[field_id]['component'], 'JumppackComponentData', field_id)


class ChargeCatalogTests(unittest.TestCase):
    def test_every_weapon_offers_exactly_the_fields_its_code_reads(self):
        for weapon, expected in EXPECTED_CHARGE.items():
            self.assertEqual(set(charge_instances(weapon)), expected, weapon)

    def test_baselines_equal_the_research_values(self):
        records = {record['labels'][0]: record for record in CHARGE['records'] if record['labels']}
        for weapon in EXPECTED_CHARGE:
            label = records[weapon]['label']
            for field_id, instance in charge_instances(weapon).items():
                if field_id == 'charge.overcharge_explosion':
                    self.assertEqual(instance['value']['baseline'], weapon)
                    continue
                native = CHARGE['matrix'][CHARGE_PATHS[field_id]][label]
                baseline = instance['value']['baseline']
                if isinstance(baseline, bool):
                    self.assertEqual(baseline, bool(native), (weapon, field_id))
                else:
                    self.assertAlmostEqual(baseline, f32(native), places=6, msg=(weapon, field_id))
        rail = charge_instances('RS-422 Railgun')
        self.assertEqual([round(rail[field]['value']['baseline'], 6) for field in TIMES], [0.45, 0.5, 3.0])
        self.assertEqual(round(rail['charge.damage_multiplier_overcharge']['value']['baseline'], 6), 2.5)

    def test_new_fields_need_the_acknowledgement_and_carry_ranges(self):
        for weapon in EXPECTED_CHARGE:
            for field_id, instance in charge_instances(weapon).items():
                charge = instance['charge']
                if field_id in TIMES:
                    self.assertIsNone(instance['operation']['acknowledgement'])
                    self.assertEqual(charge['max'], 60.0)
                elif field_id in LEGACY:
                    # The legacy contract: no acknowledgement, no range, deprecated.
                    self.assertIsNone(instance['operation']['acknowledgement'])
                    self.assertNotIn('max', charge)
                    self.assertTrue(charge['deprecated'] and charge['legacyContract'])
                else:
                    self.assertEqual(instance['operation']['acknowledgement'], 'allow_unverified_effect', field_id)
                    if instance['value']['type'] == 'number':
                        self.assertIn('max', charge, field_id)
                self.assertTrue(instance['writable'], (weapon, field_id))
                self.assertEqual(charge['effect']['activeSource'], 'LIVE_TYPE_RECORD')

    def test_legacy_ids_alias_projectile_weapons_and_are_dormant_elsewhere(self):
        for weapon in ('RS-422 Railgun', 'PLAS-45 Epoch'):
            fields = charge_instances(weapon)
            for legacy, canonical in zip(LEGACY, PROJECTILE):
                self.assertEqual(fields[legacy]['charge']['aliasOf'], canonical)
                self.assertEqual(fields[legacy]['backing']['objectKey'], fields[canonical]['backing']['objectKey'])
                self.assertEqual([notice['kind'] for notice in fields[legacy]['charge']['notices']], ['deprecated'])
        for weapon in ('ARC-3 Arc Thrower', '40-K Meltagun'):
            fields = charge_instances(weapon)
            for legacy in LEGACY:
                self.assertNotIn('aliasOf', fields[legacy]['charge'])
                self.assertTrue(fields[legacy]['charge']['dormant'])
                self.assertEqual([notice['kind'] for notice in fields[legacy]['charge']['notices']],
                    ['deprecated', 'dormant'])

    def test_overcharge_explosion_lists_only_donors_with_a_known_package(self):
        for weapon in ('RS-422 Railgun', 'PLAS-45 Epoch'):
            explosion = charge_instances(weapon)['charge.overcharge_explosion']
            self.assertEqual(explosion['value']['type'], 'overcharge_explosion_reference')
            self.assertEqual(explosion['charge']['allowedValues'], ['PLAS-45 Epoch', 'RS-422 Railgun'])
            self.assertEqual(set(explosion['charge']['donors']), {'PLAS-45 Epoch', 'RS-422 Railgun'})
        blocked = {item['field'] for weapon in SUPPORT['weapons'] if weapon['name'] in EXPECTED_CHARGE
            for item in weapon['blockedFields']}
        self.assertIn('overcharge limit state (+204)', blocked)


class MovementCatalogTests(unittest.TestCase):
    def test_each_pack_offers_exactly_what_its_flight_code_reads(self):
        jump, hover = pack_fields('LIFT-850 Jump Pack'), pack_fields('LIFT-860 Hover Pack')
        self.assertTrue(set(JUMP_ONLY + SHARED) <= set(jump))
        self.assertFalse(set(HOVER_ONLY) & set(jump))
        self.assertTrue(set(SHARED + HOVER_ONLY) <= set(hover))
        self.assertFalse(set(JUMP_ONLY) & set(hover))
        # The Dark Fluid vessel shares the component but is not a call-in backpack.
        self.assertNotIn('Dark Fluid', json.dumps([item['name'] for item in BACKPACKS['backpacks']]))

    def test_baselines_ranges_and_evidence(self):
        for name in ('LIFT-850 Jump Pack', 'LIFT-860 Hover Pack'):
            for field_id, field in pack_fields(name).items():
                if field_id not in MOVEMENT_PATHS:
                    continue
                native = HOVER['matrix'][MOVEMENT_PATHS[field_id]][name]
                self.assertAlmostEqual(field['currentDefault'], f32(native), places=6, msg=(name, field_id))
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                self.assertEqual(field['evidence']['tier'], 'native_consumer_proven')
                self.assertLessEqual(field['min'], field['currentDefault'])
                self.assertGreaterEqual(field['max'], field['currentDefault'])
                if not field['evidence']['differential']:
                    self.assertIn('no value differs between the packs', field['acknowledgementReason'])
        hover_launch = pack_fields('LIFT-860 Hover Pack')['jump.vertical_launch_velocity']
        self.assertEqual([notice['kind'] for notice in hover_launch['notices']], ['dormant'])
        jump_launch = pack_fields('LIFT-850 Jump Pack')['jump.vertical_launch_velocity']
        self.assertEqual(jump_launch['evidence']['tier'], 'gameplay_proven')
        self.assertNotIn('notices', jump_launch)


class ApiTests(unittest.TestCase):
    def test_charge_write_rules(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local notices=require('hd2runtime/core/field_notices')
local F=hd2.fields
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local rail=hd2.support_weapon('RS-422 Railgun');local arc=hd2.support_weapon('ARC-3 Arc Thrower')
local melta=hd2.support_weapon('40-K Meltagun');local epoch=hd2.support_weapon('PLAS-45 Epoch')
-- The deprecated id writes the canonical bytes, keeps its old contract and says so once.
local legacy=writes.validate_patch{id='l',target=rail,field=F.charge.minimum_seconds,expect=0.7,value=25}
local canonical=writes.validate_patch{id='c',target=rail,field=F.charge.speed_multiplier_min,expect=0.7,value=2,
 allow_unverified_effect=true}
assert(legacy.changes[1].canonical_field=='charge.speed_multiplier_min')
assert(legacy.changes[1].descriptor.backing.offset==72 and canonical.changes[1].descriptor.backing.offset==72)
notices.reset()
local lines=notices.warn(legacy,'patch','Mod',nil)
assert(#lines==1 and lines[1]:find('DEPRECATED',1,true)and lines[1]:find('speed multiplier',1,true),lines[1])
assert(#notices.warn(legacy,'patch','Mod',nil)==0)
assert(#notices.warn(canonical,'patch','Mod',nil)==0)
-- Arc and beam weapons: the legacy ids stay writable and dormant; the canonical speed ids are not offered.
for _,weapon in ipairs({arc,melta})do
 local item=writes.validate_patch{id='d',target=weapon,field=F.charge.maximum_seconds,
  expect=weapon==arc and 1.399999976158142 or 1,value=0.5}
 local dormant=notices.warn(item,'patch','Mod',nil)
 assert(#dormant==2 and dormant[2]:find('DORMANT',1,true),table.concat(dormant,' | '))
 rejects(function()writes.validate_patch{id='x',target=weapon,field=F.charge.speed_multiplier_overcharge,
  expect=1,value=1,allow_unverified_effect=true}end,'not exposed')
end
-- Acknowledgement, range, finiteness, booleans.
rejects(function()writes.validate_patch{id='a',target=rail,field=F.charge.damage_multiplier_overcharge,expect=2.5,
 value=3}end,'allow_unverified_effect')
rejects(function()writes.validate_patch{id='r',target=rail,field=F.charge.damage_multiplier_overcharge,expect=2.5,
 value=10.5,allow_unverified_effect=true}end,'above the reviewed maximum')
rejects(function()writes.validate_patch{id='r2',target=rail,field=F.charge.burst_shots,expect=0,value=11,
 allow_unverified_effect=true}end,'above the reviewed maximum')
rejects(function()writes.validate_patch{id='r3',target=rail,field=F.charge.burst_shots,expect=0,value=1.5,
 allow_unverified_effect=true}end,'integer')
rejects(function()writes.validate_patch{id='n',target=rail,field=F.charge.overcharge_limit_seconds,expect=0,
 value=0/0,allow_unverified_effect=true}end,'finite')
rejects(function()writes.validate_patch{id='b',target=rail,field=F.charge.auto_fire_at_full,expect=false,value=1,
 allow_unverified_effect=true}end,'must be boolean')
local flag=writes.validate_patch{id='f',target=rail,field=F.charge.explode_at_overcharge,expect=true,value=false,
 allow_unverified_effect=true}
assert(flag.changes[1].expected==string.char(1)and flag.changes[1].desired==string.char(0))
rejects(function()writes.validate_patch{id='e',target=epoch,field=F.charge.auto_fire_at_full,expect=false,
 value=true,allow_unverified_effect=true}end,'not exposed')
-- Charge times: a write that breaks minimum < full < overcharge is accepted (the ids are older than the rule) and logs
-- one CHARGE ORDER notice per operation; ordered writes log none; the per-field ranges still refuse.
notices.reset()
local fast=writes.validate_patch{id='o',target=rail,field=F.charge.level_2,expect=0.5,value=0.2}
assert(fast.changes[1].desired and fast.changes[1].descriptor.backing.offset==24)
local order=notices.warn(fast,'ensure','Mod',nil)
assert(#order==1 and order[1]:find('CHARGE ORDER',1,true)and order[1]:find('fires nothing',1,true),order[1])
assert(#notices.warn(fast,'ensure','Mod',nil)==0)
local over=writes.validate_patch{id='o2',target=rail,field=F.charge.level_3,expect=3,value=0.48}
local over_lines=notices.warn(over,'patch','Mod',nil)
assert(#over_lines==1 and over_lines[1]:find('overcharge time',1,true),over_lines[1])
local both=writes.validate_transaction{id='o5',target=rail,changes={{field=F.charge.level_2,expect=0.5,value=4},
 {field=F.charge.level_1,expect=0.45,value=5}}}
assert(#notices.warn(both,'transaction','Mod',nil)==1)
local ordered=writes.validate_transaction{id='o3',target=rail,changes={{field=F.charge.level_2,expect=0.5,value=4},
 {field=F.charge.level_3,expect=3,value=8}}}
assert(#notices.warn(ordered,'transaction','Mod',nil)==0)
rejects(function()writes.validate_patch{id='o4',target=rail,field=F.charge.level_2,expect=0.5,value=0}end,
 'below the reviewed minimum')
-- The overcharge explosion of another weapon: reference acknowledgement, package, catalogue.
writes.validate_patch{id='x0',target=rail,field=F.charge.overcharge_explosion,expect='RS-422 Railgun',
 value='RS-422 Railgun',allow_unverified_effect=true}
rejects(function()writes.validate_patch{id='x1',target=rail,field=F.charge.overcharge_explosion,
 expect='RS-422 Railgun',value='PLAS-45 Epoch',allow_unverified_effect=true}end,'allow_unverified_reference')
local swap=writes.validate_patch{id='x2',target=rail,field=F.charge.overcharge_explosion,expect='RS-422 Railgun',
 value='PLAS-45 Epoch',allow_unverified_effect=true,allow_unverified_reference=true}
assert(swap.asset_dependencies[1].key=='support_weapon/PLAS-45 Epoch')
rejects(function()writes.validate_patch{id='x3',target=rail,field=F.charge.overcharge_explosion,
 expect='RS-422 Railgun',value='LAS-99 Quasar Cannon',allow_unverified_effect=true,allow_unverified_reference=true}end,
 'no catalogued overcharge explosion')
rejects(function()writes.validate_patch{id='x4',target=rail,field=F.charge.overcharge_explosion,
 expect='PLAS-45 Epoch',value='RS-422 Railgun',allow_unverified_effect=true,allow_unverified_reference=true}end,
 'expect differs')
local assets=require('hd2runtime/core/assets');local real=assets.dependency
assets.dependency=function(key)if key=='support_weapon/PLAS-45 Epoch'then return nil end return real(key)end
local ok,why=pcall(writes.validate_patch,{id='x5',target=rail,field=F.charge.overcharge_explosion,
 expect='RS-422 Railgun',value='PLAS-45 Epoch',allow_unverified_effect=true,allow_unverified_reference=true})
assets.dependency=real
assert(not ok and tostring(why):find('UNKNOWN_EXPLOSION_PACKAGE',1,true),tostring(why))
return 'ok'
'''), b'ok')

    def test_movement_write_rules(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local entity=require('hd2runtime/domains/entity_writes')
local notices=require('hd2runtime/core/field_notices')
local F=hd2.fields
local function rejects(fn,needle)local ok,why=pcall(fn);assert(not ok and tostring(why):find(needle,1,true),tostring(why))end
local jump=hd2.backpack('LIFT-850 Jump Pack');local hover=hd2.backpack('LIFT-860 Hover Pack')
local spec=entity.validate_patch{id='j',target=jump,field=F.jump.launch_forward_ratio,expect=0.4,value=0.95,
 allow_unverified_effect=true}
assert(spec.changes[1].descriptor.backing.offset==32)
rejects(function()entity.validate_patch{id='a',target=jump,field=F.jump.launch_forward_ratio,expect=0.4,
 value=0.95}end,'allow_unverified_effect')
rejects(function()entity.validate_patch{id='r',target=jump,field=F.jump.launch_forward_ratio,expect=0.4,
 value=1.01,allow_unverified_effect=true}end,'outside the reviewed range')
rejects(function()entity.validate_patch{id='f',target=jump,field=F.jump.sustain_thrust,expect=60,value=1/0,
 allow_unverified_effect=true}end,'finite')
rejects(function()entity.validate_patch{id='h',target=hover,field=F.jump.launch_duration,expect=0.5,value=1,
 allow_unverified_effect=true}end,'not exposed')
rejects(function()entity.validate_patch{id='h2',target=jump,field=F.hover.fuel_rate_low_speed,expect=1.6,value=0,
 allow_unverified_effect=true}end,'not exposed')
local fuel=entity.validate_transaction{id='fuel',target=hover,allow_unverified_effect=true,changes={
 {field=F.hover.fuel_rate_low_speed,expect=1.6,value=-0.9},{field=F.hover.fuel_rate_high_speed,expect=0,value=-0.9}}}
assert(#fuel.changes==2)
rejects(function()entity.validate_patch{id='h3',target=hover,field=F.hover.vertical_speed_range_end,expect=8,value=0,
 allow_unverified_effect=true}end,'outside the reviewed range')
-- The Hover Pack launch thrust write is dormant: writable, one notice.
notices.reset()
local dormant=entity.validate_patch{id='d',target=hover,field=F.jump.vertical_launch_velocity,expect=40,value=80,
 allow_unverified_effect=true}
local lines=notices.warn(dormant,'ensure','Mod',nil)
assert(#lines==1 and lines[1]:find('DORMANT',1,true),lines[1])
assert(#notices.warn(dormant,'ensure','Mod',nil)==0)
assert(#notices.warn(entity.validate_patch{id='p',target=jump,field=F.jump.vertical_launch_velocity,expect=40,
 value=50},'patch','Mod',nil)==0)
return 'ok'
'''), b'ok')

    def test_registration_emits_the_notice_once(self):
        self.assertEqual(run(r'''
local shared=require('hd2runtime/core/shared_records')
local writes=require('hd2runtime/domains/player_weapon_writes')
local hd2=require('hd2runtime/api/session').new({},function()end)
require('hd2runtime/core/field_notices').reset()
local spec=writes.validate_patch{id='legacy-reg',target=hd2.support_weapon('PLAS-45 Epoch'),
 field=hd2.fields.charge.maximum_seconds,expect=1,value=1.2}
local seen={}
local function emit(line)seen[#seen+1]=line end
shared.warn_unlisted(spec,'patch','RegMod',emit)
shared.warn_unlisted(spec,'patch','RegMod',emit)
local deprecated=0
for _,line in ipairs(seen)do if line:find('DEPRECATED',1,true)then deprecated=deprecated+1 end end
assert(deprecated==1,table.concat(seen,' | '))
return 'ok'
'''), b'ok')


@unittest.skipUnless(SNAPSHOT_REPORT.is_file(), 'charge / jump / hover snapshot validation not run')
class SnapshotTests(unittest.TestCase):
    def test_every_field_round_trips_on_the_retained_snapshot(self):
        report = json.loads(SNAPSHOT_REPORT.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'VALIDATED')
        charge = sum(len(fields) for fields in EXPECTED_CHARGE.values())
        movement = sum(1 for name in ('LIFT-850 Jump Pack', 'LIFT-860 Hover Pack')
            for field_id, field in pack_fields(name).items() if field_id.split('.')[0] in ('jump', 'hover')
            and field['editable'])
        self.assertEqual(report['byFamily'], {'charge': charge, 'jump_pack': 14, 'hover_pack': 15})
        self.assertEqual(report['fields'], charge + movement)
        for key in ('baselineMatches', 'noOps', 'changedWrites', 'isolatedWrites', 'protectionRestored', 'rollbacks',
                'conflictRejections', 'staleExpectRejections'):
            self.assertEqual(report[key], report['fields'], key)
        self.assertEqual(report['aliasEquivalences'], 4)          # 2 legacy ids x 2 projectile weapons
        self.assertEqual(report['deprecationNotices'], 8)         # 2 legacy ids x 4 charge weapons
        self.assertEqual(report['dormantNotices'], 5)             # ARC-3 and Meltagun legacy ids, Hover launch
        self.assertEqual((report['chargeOrderNotices'], report['chargeOrderTransactions']), (4, 4))
        self.assertEqual((report['referenceSwaps'], report['referenceRejections']), (2, 6))
        self.assertGreater(report['acknowledgementRejections'], 0)
        self.assertGreater(report['rangeRejections'], 0)
        self.assertEqual(report['booleanRejections'], 5)
        for item in report['checked']:
            self.assertEqual(len(item['before']), 2 * item['width'])


if __name__ == '__main__':
    unittest.main()
