"""Coverage pass: sentry turret motion / targeting range, the status catalog and status references, enemies and
enemy structures. Every field here is published only with its research proof; these tests pin the proofs, the
typed API and the guards."""
import json
import unittest

from support import ROOT, run

TURRETED = ('A/MG-43 Machine Gun Sentry', 'A/G-16 Gatling Sentry', 'A/AC-8 Autocannon Sentry',
    'A/M-12 Mortar Sentry', 'A/MLS-4X Rocket Sentry', 'A/M-23 EMS Mortar Sentry', 'A/LAS-98 Laser Sentry',
    'A/FLAM-40 Flame Sentry', 'A/GM-17 Gas Mortar Sentry')


class SentryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = {s['name']: s for s in json.loads(
            (ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json').read_text())['stratagems']}
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())

    def fields(self, stratagem, path):
        return {f['semanticFieldId']: f for f in self.catalog['fieldInstances']
            if f['target'].get('stratagem') == stratagem and f['target']['path'] == path}

    def test_turret_members_equal_the_wiki_tables_on_every_turreted_sentry(self):
        for name in TURRETED:
            proof = self.research[name]['deploymentProofs']['turret']
            self.assertTrue(proof['exact'], name)
            self.assertEqual(set(proof['wikiChecks']), {'horizontalTurnSpeed', 'verticalTurnSpeed', 'verticalLimit'})
            fields = self.fields(name, 'turret')
            self.assertEqual(set(fields), {'turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min',
                'turret.pitch_max', 'turret.yaw_min', 'turret.yaw_max'})
            table = self.research[name]['deploymentProofs']['wikiTable']
            self.assertEqual(fields['turret.yaw_speed']['currentDefault'], table['horizontalTurnSpeed'])
            self.assertEqual(fields['turret.pitch_speed']['currentDefault'], table['verticalTurnSpeed'])
            self.assertEqual([fields['turret.pitch_min']['currentDefault'], fields['turret.pitch_max']['currentDefault']],
                table['verticalLimit'])
            for field in fields.values():
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                self.assertFalse(field['shared'])
                self.assertEqual(field['backingObjectKind'], 'TurretComponentData')
        autocannon = self.fields('A/AC-8 Autocannon Sentry', 'turret')
        flame = self.fields('A/FLAM-40 Flame Sentry', 'turret')
        self.assertEqual(autocannon['turret.yaw_speed']['currentDefault'], 20.0)
        self.assertEqual(flame['turret.yaw_speed']['currentDefault'], 140.0)
        self.assertEqual(self.fields('A/M-12 Mortar Sentry', 'turret')['turret.pitch_min']['currentDefault'], 35.0)
        # The Tesla Tower, emplacements and mines have no turret component.
        self.assertFalse(self.fields('A/ARC-3 Tesla Tower', 'turret'))
        self.assertFalse(self.fields('E/MG-101 HMG Emplacement', 'turret'))

    def test_targeting_range_rests_on_stated_ranges(self):
        stated = {name: s['deploymentProofs']['sensor']['statement'] for name, s in self.research.items()
            if (s.get('deploymentProofs') or {}).get('sensor', {}).get('statement')}
        self.assertEqual(len(stated), 7)
        self.assertTrue(all(item['exact'] for item in stated.values()))
        self.assertEqual({item['value'] for item in stated.values()}, {50, 75, 100, 125})
        ranges = {name: self.fields(name, 'targeting').get('targeting.range') for name in self.research}
        self.assertEqual(sum(1 for field in ranges.values() if field), 10)
        self.assertEqual(ranges['A/M-12 Mortar Sentry']['currentDefault'], 125.0)
        self.assertEqual(ranges['A/ARC-3 Tesla Tower']['currentDefault'], 25.0)

    def test_sentry_lifetime_uses_the_gameplay_proven_member(self):
        for name in TURRETED:
            lifetime = self.research[name]['deploymentProofs']['lifetime']
            self.assertTrue(lifetime['exact'], name)
            field = self.fields(name, 'deployed_entity')['payload.lifetime']
            self.assertEqual(field['currentDefault'], lifetime['wiki'])
            self.assertIsNone(field.get('acknowledgement'))

    def test_api_and_guards(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local entity=hd2.stratagem('A/AC-8 Autocannon Sentry'):deployed_entity()
local turret=entity:turret()
assert(turret.path=='turret' and #turret:describe().fields==6 and turret:describe().turret)
transactions.validate{id='turn',target=turret,allow_unverified_effect=true,changes={
 {field=hd2.fields.turret.yaw_speed,expect=20,value=120},{field=hd2.fields.turret.pitch_speed,expect=20,value=90}}}
local ok,why=pcall(patches.validate,{id='turn',target=turret,field=hd2.fields.turret.yaw_speed,expect=20,value=120})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),why)
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=20,value=5000})
assert(not ok and tostring(why):find('reviewed range',1,true),why)
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=80,value=120})
assert(not ok and tostring(why):find('expect differs',1,true),why)
local targeting=hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():targeting()
patches.validate{id='range',target=targeting,allow_unverified_effect=true,field=hd2.fields.targeting.range,expect=75,value=25}
assert(not pcall(function()return hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():turret()end))
assert(hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():targeting():describe().targeting.range==25)
patches.validate{id='life',target=entity,field=hd2.fields.payload.entity_lifetime,expect=150,value=300}
return 'ok'
''')


ATTACHABLE = {'fire', 'fire_panic', 'burning_heavy', 'stun_small', 'stun_medium', 'stun_large', 'gas', 'gas_2',
    'gas_confusion', 'gas_confusion_2', 'flamer_slowed'}


class StatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/status-effects-F5FEE03DCFDB.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/StatusEffectCatalog.json').read_text())
        cls.player = {w['name']: w for w in json.loads(
            (ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())['weapons']}

    def test_catalog_is_named_by_the_live_rows(self):
        statuses = {s['semanticId']: s for s in self.research['statuses']}
        self.assertEqual(len(statuses), 71)
        self.assertEqual(len({s['name'] for s in statuses.values()}), 66)   # repeated names get _2/_3
        self.assertEqual({k for k, s in statuses.items() if s['attachable']}, ATTACHABLE)
        self.assertEqual((statuses['fire']['name'], statuses['fire']['duration']), ('Fire', 3.0))
        self.assertEqual((statuses['stun_medium']['name'], statuses['stun_medium']['duration']), ('Stun Medium', 3.0))
        # Electric and acid are applied by other systems or only by enemies: catalogued, never attachable.
        self.assertFalse(statuses['electric']['attachable'])
        self.assertFalse(statuses['acid_splash']['attachable'])
        self.assertEqual(self.catalog['summary'], {'statuses': 71, 'attachable': 11,
            'families': self.catalog['summary']['families']})
        self.assertNotRegex(json.dumps(self.catalog), r'nativeType|0x[0-9A-Fa-f]{8}')

    def test_attachment_model(self):
        model = self.research['model']
        self.assertEqual(model['owner'], 'DamageInfo')
        self.assertEqual(model['slots'], 4)
        self.assertFalse(model['packingViolations'])
        self.assertEqual(sum(model['rowsBySlotsUsed'].values()), model['damageRows'])
        self.assertEqual(model['rowsBySlotsUsed']['4'], 0)

    def test_slot_fields(self):
        def slots(name):
            return {f['semanticFieldId']: f for f in self.player[name]['fields'] if 'status_' in f['semanticFieldId']}
        liberator = slots('AR-23 Liberator')
        self.assertEqual(liberator['damage.status_1_type']['currentDefault'], 'none')
        self.assertEqual(liberator['damage.status_1_strength']['currentDefault'], 0)
        self.assertTrue(liberator['damage.status_1_type']['statusAttach'])
        coyote = slots('AR-2 Coyote')
        self.assertEqual(coyote['damage.status_1_type']['currentDefault'], 'fire')
        self.assertTrue(coyote['damage.status_1_type']['allowNone'])          # the last used slot
        self.assertEqual(coyote['damage.status_2_type']['currentDefault'], 'none')
        for field in liberator.values():
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
        self.assertEqual(set(liberator['damage.status_1_type']['allowedValues']), ATTACHABLE)

    def test_snapshot_validation_record(self):
        record = json.loads((ROOT / 'validation/coverage-pass-snapshot.json').read_text())
        self.assertEqual(record['status'], 'VALIDATED')
        slots = record['statusSlots']
        self.assertEqual(set(slots['attached']), {'maxigun_stun', 'liberator_fire'})
        self.assertEqual(slots['attached']['maxigun_stun']['status'], 'stun_medium')
        self.assertEqual(slots['attached']['liberator_fire']['status'], 'fire')
        self.assertEqual(slots['rejections'], {'acknowledgement': 2, 'middleSlotClear': 1, 'notAttachable': 1,
            'packingHole': 1, 'staleCatalog': 1})
        self.assertEqual(slots['swapped']['coyote']['to'], 'stun_small')
        self.assertEqual(slots['cleared']['flamethrower']['slot'], 3)

    def test_api_and_guards(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local transactions=require('hd2runtime/domains/transactions')
local patches=require('hd2runtime/domains/patches')
local bullets=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile()
transactions.validate{id='stun',target=bullets,allow_shared=true,allow_unverified_effect=true,changes={
 {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'},
 {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}}
local ok,why=pcall(transactions.validate,{id='stun',target=bullets,allow_shared=true,changes={
 {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'}}})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),why)
ok,why=pcall(patches.validate,{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='none',value='electric'})
assert(not ok and tostring(why):find('not attachable',1,true),why)
ok,why=pcall(patches.validate,{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='none',value='no_such_status'})
assert(not ok and tostring(why):find('unknown status',1,true),why)
ok,why=pcall(patches.validate,{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='fire',value='gas'})
assert(not ok and tostring(why):find('expect differs',1,true),why)
local flamer=hd2.support_weapon('FLAM-40 Flamethrower'):attack('primary')
ok,why=pcall(patches.validate,{id='x',target=flamer,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='fire',value='none'})
assert(not ok and tostring(why):find('cannot be cleared',1,true),why)
patches.validate{id='x',target=flamer,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_3_type,expect='fire_panic',value='none'}
return 'ok'
''')

    def test_migration_carries_status_references_only_over_an_identical_status_table(self):
        from migration import engine

        class Table:
            def __init__(self, rows):
                self.rows = rows
                self.layout = type('L', (), {'members': []})()

        class View:
            def __init__(self, table):
                self.table = table

            def settings_table(self, kind):
                return self.table

        class Result:
            def __init__(self):
                self.flags, self.failed = [], []

            def flag(self, state, reason):
                self.flags.append(state)

        def verdict(source, target):
            check = engine.Engine.__new__(engine.Engine)
            check.S, check.T = View(source), View(target)
            result = Result()
            check._status_table(result)
            return result.flags

        rows = [(0, 5, b'Fire' + bytes(148)), (1, 38, b'Stun' + bytes(148))]
        self.assertEqual(verdict(Table(rows), Table(list(rows))), [])
        self.assertEqual(verdict(Table(rows), Table([(0, 5, b'Fire' + bytes(148)), (1, 38, b'Gas!' + bytes(148))])),
            ['BLOCKED'])
        self.assertEqual(verdict(Table(rows), None), ['UNCHECKED'])


if __name__ == '__main__':
    unittest.main()
