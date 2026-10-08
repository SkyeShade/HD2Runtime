"""Coverage pass: sentry turret motion / targeting range, the status catalog and status references, enemies and
enemy structures. Every field here is published only with its research proof; these tests pin the proofs, the
typed API and the guards."""
from collections import Counter
import json
import re
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
            # turret.pitch_yaw_coupling (TurretComponent +16): the sentry component fields, tests/test_sentry_fields.py.
            self.assertEqual(set(fields), {'turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min',
                'turret.pitch_max', 'turret.yaw_min', 'turret.yaw_max', 'turret.pitch_yaw_coupling'})
            table = self.research[name]['deploymentProofs']['wikiTable']
            self.assertEqual(fields['turret.yaw_speed']['currentDefault'], table['horizontalTurnSpeed'])
            self.assertEqual(fields['turret.pitch_speed']['currentDefault'], table['verticalTurnSpeed'])
            self.assertEqual([fields['turret.pitch_min']['currentDefault'], fields['turret.pitch_max']['currentDefault']],
                table['verticalLimit'])
            for field_id, field in fields.items():
                # Turn speeds are live-proven (SentryTurnSpeed); the untested aim limits keep the acknowledgement.
                if field_id in ('turret.yaw_speed', 'turret.pitch_speed'):
                    self.assertIsNone(field.get('acknowledgement'))
                    self.assertEqual(field['liveEvidence']['family'], 'sentry_turret_turn_speed')
                else:
                    self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                    self.assertNotIn('liveEvidence', field)
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
        for field in filter(None, ranges.values()):     # live-proven (SentryDetectionRange)
            self.assertIsNone(field.get('acknowledgement'))
            self.assertEqual(field['liveEvidence']['tests'], ['SentryDetectionRange'])

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
assert(turret.path=='turret' and #turret:describe().fields==7 and turret:describe().turret)
transactions.validate{id='turn',target=turret,changes={
 {field=hd2.fields.turret.yaw_speed,expect=20,value=120},{field=hd2.fields.turret.pitch_speed,expect=20,value=90}}}
local ok,why=pcall(patches.validate,{id='turn',target=turret,field=hd2.fields.turret.pitch_min,expect=-60,value=-30})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=20,value=5000})
assert(not ok and tostring(why):find('reviewed range',1,true),why)
ok,why=pcall(patches.validate,{id='turn',target=turret,allow_unverified_effect=true,
 field=hd2.fields.turret.yaw_speed,expect=80,value=120})
assert(not ok and tostring(why):find('expect differs',1,true),why)
local targeting=hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():targeting()
patches.validate{id='range',target=targeting,field=hd2.fields.targeting.range,expect=75,value=25}
assert(not pcall(function()return hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():turret()end))
assert(hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():targeting():describe().targeting.range==25)
patches.validate{id='life',target=entity,field=hd2.fields.payload.entity_lifetime,expect=150,value=300}
return 'ok'
''')


MINES = {'MD-6 Anti-Personnel Minefield': (6, 8), 'MD-I4 Incendiary Mines': (6, 8), 'MD-17 Anti-Tank Mines': (6, 3),
    'MD-8 Gas Mines': (6, 8)}


class MineCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = {s['name']: s for s in json.loads(
            (ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json').read_text())['stratagems']}
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())

    def test_three_independent_proofs_agree_on_every_minefield(self):
        for name, (salvos, per_salvo) in MINES.items():
            proof = self.research[name]['mineChain']['countProof']
            self.assertTrue(proof['exact'], name)
            self.assertEqual((proof['wiki']['statement']['salvos'], proof['wiki']['statement']['perSalvo']),
                (salvos, per_salvo))
            self.assertEqual(proof['wiki']['structured'], {'salvos': salvos, 'capacity': per_salvo})
            self.assertEqual(proof['native'], {'salvos': salvos, 'perSalvo': per_salvo,
                'distinctLaunchSockets': salvos * per_salvo})
            self.assertTrue(proof['thrower']['uniqueOwner'])

    def test_fields_are_reduce_only_and_acknowledged(self):
        fields = [f for f in self.catalog['fieldInstances'] if f['semanticFieldId'].startswith('minefield.')]
        self.assertEqual(len(fields), 8)
        for field in fields:
            salvos, per_salvo = MINES[field['target']['stratagem']]
            baseline = salvos if field['semanticFieldId'] == 'minefield.salvos' else per_salvo
            self.assertEqual((field['currentDefault'], field['min'], field['max']), (baseline, 1, baseline))
            if field['semanticFieldId'] == 'minefield.salvos':          # live-proven (MinefieldSalvos)
                self.assertIsNone(field.get('acknowledgement'))
                self.assertEqual(field['liveEvidence']['family'], 'minefield_salvos')
            else:
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual(field['target']['path'], 'minefield')
            self.assertFalse(field['shared'])
        record = json.loads((ROOT / 'validation/coverage-pass-snapshot.json').read_text())['minefield']
        self.assertEqual(record['rejections'], {'increase': 2, 'acknowledgement': 1})
        self.assertEqual(record['liveProvenWithoutAcknowledgement'], 'minefield.salvos')

    def test_api(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local mines=hd2.stratagem('MD-6 Anti-Personnel Minefield'):deployed_entity():minefield()
local d=mines:describe()
assert(#d.fields==2 and d.minefield.launchSockets==48 and d.minefield.salvos==6)
assert(d.minefield.deploymentPattern:find('truncates the angular deployment',1,true))
patches.validate{id='m',target=mines,field=hd2.fields.minefield.salvos,expect=6,value=2}
local ok0,why0=pcall(patches.validate,{id='m',target=mines,field=hd2.fields.minefield.mines_per_salvo,expect=8,value=4})
assert(not ok0 and tostring(why0):find('allow_unverified_effect',1,true),tostring(why0))
local ok,why=pcall(patches.validate,{id='m',target=mines,allow_unverified_effect=true,
 field=hd2.fields.minefield.mines_per_salvo,expect=8,value=9})
assert(not ok and tostring(why):find('range',1,true),why)
assert(not pcall(function()return hd2.stratagem('A/MG-43 Machine Gun Sentry'):deployed_entity():minefield()end))
return 'ok'
''')


ATTACHABLE = {'fire', 'fire_panic', 'burning_heavy', 'stun_small', 'stun_medium', 'stun_large', 'gas', 'gas_2',
    'gas_confusion', 'gas_confusion_2', 'flamer_slowed'}
# The reviewed extension (schemas/status_attachment_policy.json, 0.30.2): statuses enemies or hazards apply through
# DamageInfo slots, and attack effects other systems apply. Never terrain, stim, weather or system statuses.
ENEMY_SLOT = {'confusion', 'lava', 'acid_splash', 'choked', 'stun_massive', 'inverted_aim_assist', 'tremor',
    'tornado_stun'}
OTHER_SYSTEM = {'acid_stream', 'thermite', 'cyborg_fire', 'burning_light', 'radiation_light', 'radiation_heavy',
    'electric', 'bleed', 'poison', 'gloom', 'slowed', 'rooted', 'blind', 'deaf', 'stun_illuminate'}


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
        # Electric and acid are applied by other systems or only by enemies: the research keeps them unattachable;
        # the reviewed policy extends the published catalog (0.30.2).
        self.assertFalse(statuses['electric']['attachable'])
        self.assertFalse(statuses['acid_splash']['attachable'])
        self.assertEqual(self.catalog['summary'], {'statuses': 71, 'attachable': 34,
            'attachableByTier': {'player_attack': 11, 'enemy_slot': 8, 'other_system': 15},
            'families': self.catalog['summary']['families']})
        published = {s['semanticId']: s for s in self.catalog['statuses']}
        self.assertEqual({k for k, s in published.items() if s['attachTier'] == 'enemy_slot'}, ENEMY_SLOT)
        self.assertEqual({k for k, s in published.items() if s['attachTier'] == 'other_system'}, OTHER_SYSTEM)
        never = {k for k, s in published.items() if not s['attachable']}
        self.assertTrue({'acid_storm', 'blizzard', 'mud', 'stim_heal', 'pure_damage', 'hidden'} <= never)
        self.assertTrue(all(published[k]['family'] in ('terrain', 'stim', 'weather', 'system', 'sense') for k in never))
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
        # Projectile direct-hit rows are live-proven (LiberatorFireStatus, MaxigunStun); other rows stay gated.
        for field in liberator.values():
            self.assertIsNone(field.get('acknowledgement'))
            self.assertEqual(field['liveEvidence']['family'], 'weapon_projectile_status_reference')
        hatchet = slots('CQC-5 Combat Hatchet')          # melee row
        self.assertTrue(hatchet and all(f['acknowledgement'] == 'allow_unverified_effect' for f in hatchet.values()))
        promoted = [f for w in self.player.values() for f in w['fields'] if f.get('statusSlot')]
        # 12 slots sit on rows their weapon may not fire (charge / heat levels, spawned entities: see each field's
        # effect); they keep allow_unverified_effect and do not inherit the projectile status promotion. The 26
        # explosion status slots (0.30.2) are gated too: a status on an explosion is not live-proven.
        self.assertEqual(sum(1 for f in promoted if f.get('liveEvidence')), 129)
        self.assertEqual(sum(1 for f in promoted if f.get('acknowledgement')), 73)
        explosion = [f for f in promoted if f['semanticFieldId'].startswith('explosion.')]
        self.assertEqual(len(explosion), 26)
        self.assertTrue(all(f.get('acknowledgement') == 'allow_unverified_effect' for f in explosion))
        self.assertEqual(set(liberator['damage.status_1_type']['allowedValues']), ATTACHABLE | ENEMY_SLOT | OTHER_SYSTEM)
        observed = {s['semanticId']: s.get('liveObserved') for s in self.catalog['statuses']}
        self.assertEqual(observed['fire'][0]['test'], 'LiberatorFireStatus')
        self.assertIn('1-2 s', observed['stun_medium'][0]['observation'])

    def test_snapshot_validation_record(self):
        record = json.loads((ROOT / 'validation/coverage-pass-snapshot.json').read_text())
        self.assertEqual(record['status'], 'VALIDATED')
        slots = record['statusSlots']
        self.assertEqual(set(slots['attached']), {'maxigun_stun', 'liberator_fire'})
        self.assertEqual(slots['attached']['maxigun_stun']['status'], 'stun_medium')
        self.assertEqual(slots['attached']['liberator_fire']['status'], 'fire')
        self.assertEqual(slots['rejections'], {'acknowledgement': 1, 'middleSlotClear': 1, 'notAttachable': 1,
            'packingHole': 1, 'staleCatalog': 1})
        self.assertEqual(slots['liveProvenWithoutAcknowledgement'], 2)
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
transactions.validate{id='stun',target=bullets,allow_shared=true,changes={
 {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'}}}
local ok,why=pcall(transactions.validate,{id='stun',target=hd2.weapon('CQC-5 Combat Hatchet'),changes={
 {field=hd2.fields.damage.status_1_type,expect='none',value='fire'}}})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
-- Statuses beyond those player attacks apply keep allow_unverified_effect, even on this live-proven direct-hit row.
ok,why=pcall(patches.validate,{id='x',target=bullets,allow_shared=true,
 field=hd2.fields.damage.status_1_type,expect='none',value='electric'})
assert(not ok and tostring(why):find('requires allow_unverified_effect',1,true),tostring(why))
patches.validate{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='none',value='electric'}
patches.validate{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.status_1_type,expect='none',value='acid_splash'}
for _,never in ipairs({'acid_storm','stim_heal','pure_damage','mud'})do
 ok,why=pcall(patches.validate,{id='x',target=bullets,allow_shared=true,allow_unverified_effect=true,
  field=hd2.fields.damage.status_1_type,expect='none',value=never})
 assert(not ok and tostring(why):find('not attachable',1,true),never..': '..tostring(why))
end
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


class PlayerProjectileMemberTests(unittest.TestCase):
    def test_slowdown_and_lifetime_agree_with_every_stated_player_value(self):
        research = json.loads((ROOT / 'research/player-projectile-members-F5FEE03DCFDB.json').read_text())
        self.assertEqual(research['summary'], {'branches': 67, 'resolved': 67, 'penetration_slowdown:exact': 67,
            'lifetime:exact': 10, 'lifetime:wiki_silent': 57})
        catalog = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
        fields = [f for w in catalog['weapons'] for f in w['fields']
            if re.match(r'^projectile\.(primary\.|alternate\.)?(penetration_slowdown|lifetime)$', f['semanticFieldId'])]
        self.assertEqual(len(fields), 77)
        self.assertEqual(sum(1 for f in fields if f['editable']), 77)   # + GP-31 and P-72 (0.30.2: the seven DUPLICATE weapons resolved to their proven roots, research/weapon-roots)
        self.assertTrue(all(f['writeScope'] == 'shared_projectile_definition' and f['backing']['offset'] in (52, 64)
            for f in fields))
        self.assertFalse([f for f in fields if f['semanticFieldId'].endswith('lifetime') and not f['currentDefault']])
        record = json.loads((ROOT / 'validation/coverage-pass-snapshot.json').read_text())['playerProjectileMembers']
        self.assertEqual((record['fields'], record['weapons']), (75, 64))


PROVEN = {'entity.health', 'entity.armor', 'zone.health', 'zone.armor', 'zone.affects_main_health'}


class EnemyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = json.loads((ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json').read_text())
        cls.catalog = json.loads((ROOT / 'sdk/EnemyAuthoringCapabilities.json').read_text())
        cls.classes = {c['name']: c for c in cls.catalog['classes']}

    def zone(self, name, label):
        return next(z for z in self.classes[name]['zones'] if z['wikiZone'] == label)

    def test_identity_is_native_first(self):
        summary = self.catalog['summary']
        self.assertEqual((summary['classes'], summary['enemies'], summary['structures']), (177, 138, 39))
        self.assertEqual(summary['sharedHealthRecords'], 0)
        named = [c for c in self.research['classes'] if c['wikiName']]
        self.assertEqual(len(named), 21)
        for item in named:
            self.assertGreaterEqual(item['wikiEvidence']['zonesMatched'], 2, item['className'])
            self.assertEqual(item['wikiCandidates'], [item['wikiName']])
            self.assertEqual(item['wikiCandidateEvidence'][0]['nativeClassesMatchingPage'], 1)
        # Shared anatomies stay native: the Hunter / Hulk / Devastator pages match several classes.
        for name, pages in (('hunter_base', ['Hunter']), ('lieutenant_base', ['Hulk Bruiser', 'Hulk Firebomber',
                'Hulk Obliterator', 'Hulk Scorcher']), ('soldier', ['Devastator'])):
            self.assertIsNone(self.classes[name]['wikiName'])
            self.assertEqual(self.classes[name]['wikiCandidates'], pages)
        self.assertNotRegex(json.dumps(self.catalog), r'0x[0-9A-Fa-f]{8}|recordIndex|indexRow')

    def test_representative_classes(self):
        cases = {   # name: (faction, kind, main health, zones)
            'hunter_base': ('terminids', 'enemy', 130, 9),       # Terminid small
            'Charger': ('terminids', 'enemy', 2400, 17),          # Terminid armored
            'Bile Titan': ('terminids', 'enemy', 6500, 26),       # Terminid large, multi-zone
            'Marauder': ('automatons', 'enemy', 125, 6),          # Automaton infantry
            'lieutenant_base': ('automatons', 'enemy', 1800, 6),  # Automaton heavy (a Hulk; variant unproven)
            'tank_turret_heavycannon': ('automatons', 'enemy', 2100, 2),  # Automaton vehicle turret
            'Watcher': ('illuminate', 'enemy', 600, 6),           # Illuminate
            'Gazer': ('illuminate', 'structure', 900, 3),         # named structure
            'spawner_factory_conscript_base': ('automatons', 'structure', 1500, 1)}   # fabricator
        for name, (faction, kind, health, zones) in cases.items():
            item = self.classes[name]
            self.assertEqual((item['faction'], item['kind'], item['main']['health'], len(item['zones'])),
                (faction, kind, health, zones), name)
            self.assertEqual(item['accessor'], 'hd2.structure' if kind == 'structure' else 'hd2.enemy')
        head = self.zone('Charger', 'Head')
        self.assertEqual((head['id'], head['health'], head['armor'], head['affectsMainHealth']), ('zone_0', 1200, 4, 0.7))
        self.assertEqual(self.classes['Charger']['mainZone']['explosiveDamagePercentage'], 0.75)  # wiki: 25% reduction
        self.assertEqual(self.zone('Marauder', 'Head')['health'], 40)
        self.assertEqual(self.zone('Gazer', 'Eye')['health'], 700)
        self.assertEqual([z['health'] for z in self.classes['tank_turret_heavycannon']['zones']], [-1, 750])

    def test_ambiguous_zone_labels_are_withheld(self):
        titan = {z['wikiZone'] for z in self.classes['Bile Titan']['zones']}
        self.assertNotIn('Upper Sac', titan)       # several native zones carry identical values
        self.assertIn('Leg Armor #1', titan)
        self.assertEqual({z['wikiZone'] for z in self.classes['Gazer']['zones']}, {'Eye', None})
        pairs = [p for c in self.research['classes'] if c.get('wikiEvidence') for p in c['wikiEvidence']['zonePairs']]
        labelled = sum(1 for c in self.catalog['classes'] for z in c['zones'] if z['wikiZone'])
        self.assertEqual(labelled, sum(1 for p in pairs if p['unambiguous']))

    def test_field_safety(self):
        fields = self.catalog['model']['fields']
        self.assertEqual({k for k, f in fields.items() if f['acknowledgement'] is None}, PROVEN)
        self.assertTrue(all(f['acknowledgement'] == 'allow_unverified_effect' for k, f in fields.items()
            if k not in PROVEN))
        instances = self.catalog['fieldInstances']
        self.assertEqual(len(instances), 10448)          # 9,300 health / zone + 1,125 attack + 23 whole-body gib
        for item in instances:
            low, high = fields[item['semanticFieldId']]['range']
            if item['editable']:
                self.assertTrue(low <= item['currentDefault'] <= high, item['instanceKey'])
            else:
                self.assertTrue(item['currentDefault'] is None or item['currentDefault'] == -1, item['instanceKey'])
                self.assertTrue(item['reason'])
        self.assertEqual(sum(1 for i in instances if i['editable']), 9129)

    def test_snapshot_validation_record(self):
        record = json.loads((ROOT / 'validation/coverage-pass-snapshot.json').read_text())['enemies']
        self.assertEqual((record['classes'], record['fields'], record['readOnly'], record['attackFields']),
            (177, 9129, 1319, 1125))
        self.assertEqual(set(record['roundTrips']), {'charger_health', 'charger_head_armor', 'fabricator_health',
            'warrior_head_health', 'gunship_rocket_damage', 'bile_bombard_explosion_damage', 'bile_bombard_velocity',
            'gunship_rocket_blast_radius'})
        self.assertEqual(record['rejections'], {'acknowledgement': 1, 'range': 1, 'staleExpect': 1, 'sentinel': 1,
            'attackShared': 1, 'attackAcknowledgement': 1, 'brokenMountChain': 1, 'structureAcknowledgement': 1})

    def test_api_and_guards(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local charger=hd2.enemy('Charger')
assert(hd2.enemy('charger').enemy=='Charger')
local head=charger:zone('Head')
assert(head.zone=='zone_0' and charger:zone('head').zone=='zone_0' and charger:zone(0).zone=='zone_0')
assert(#charger:zones()==17 and head:describe().wikiZone=='Head')
transactions.validate{id='charger',target=charger,changes={{field=hd2.fields.entity.health,expect=2400,value=240},
 {field=hd2.fields.entity.armor,expect=4,value=2}}}
patches.validate{id='head',target=head,field=hd2.fields.zone.armor,expect=4,value=1}
local ok,why=pcall(patches.validate,{id='c',target=charger,field=hd2.fields.entity.constitution,expect=750,value=0})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),why)
patches.validate{id='c',target=charger,allow_unverified_effect=true,field=hd2.fields.entity.constitution,expect=750,value=0}
ok,why=pcall(patches.validate,{id='x',target=charger,field=hd2.fields.entity.health,expect=2400,value=0})
assert(not ok and tostring(why):find('reviewed range',1,true),why)
ok,why=pcall(patches.validate,{id='x',target=charger:zone('Underside'),field=hd2.fields.zone.health,expect=-1,value=500})
assert(not ok and tostring(why):find('read-only',1,true),why)
ok,why=pcall(patches.validate,{id='x',target=head,field=hd2.fields.entity.health,expect=2400,value=240})
assert(not ok and tostring(why):find('not exposed',1,true),why)
assert(not pcall(function()return hd2.enemy('Bile Titan'):zone('Upper Sac')end))
assert(not pcall(function()return hd2.structure('Charger')end))
local gazer=hd2.structure('Gazer')
patches.validate{id='g',target=gazer:zone('Eye'),allow_unverified_effect=true,field=hd2.fields.zone.health,
 expect=700,value=70}
local sok,swhy=pcall(patches.validate,{id='g',target=gazer,field=hd2.fields.entity.health,expect=900,value=90})
assert(not sok and tostring(swhy):find('allow_unverified_effect',1,true),tostring(swhy))
patches.validate{id='g',target=gazer:zone('Eye'),field=hd2.fields.zone.armor,expect=1,value=0}
local fab=hd2.structure('spawner_factory_conscript_base')
assert(fab:describe().wikiName==nil and fab:describe().kind=='structure')
patches.validate{id='f',target=fab,allow_unverified_effect=true,field=hd2.fields.entity.health,expect=1500,value=150}
patches.validate{id='m',target=hd2.enemy('Marauder'):zone('Head'),field=hd2.fields.zone.health,expect=40,value=400}
assert(#hd2.enemies({kind='structure'})==39 and #hd2.enemies({faction='illuminate',kind='enemy'})>0)
return 'ok'
''')

    def test_attacks_are_mount_chain_rows_named_only_by_exact_matches(self):
        research = json.loads((ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json').read_text())
        self.assertEqual(research['summary']['wikiMatchedRows'], 23)
        summary = self.catalog['summary']
        self.assertEqual((summary['attacks'], summary['classesWithAttacks'], summary['attackFieldInstances']),
            (169, 38, 1125))
        roles = Counter(a['role'].split('_settings')[0] + ('_settings' if '_settings' in a['role'] else '')
            for c in self.catalog['classes'] for a in c['attacks'])
        self.assertEqual(roles['projectile_settings'], 54)
        self.assertEqual(roles['explosion_settings'], 30)
        gunship = {a['id']: a for a in self.classes['Gunship']['attacks']}
        self.assertEqual(gunship['slot_0']['wikiAttacks'], ['HEAT Rocket Racks'])
        # Explosions are identified by standard damage and all three radii on the class's own page.
        self.assertEqual(gunship['slot_0_impact_explosion']['wikiExplosionOf'], ['Gunship: HEAT Rocket Racks'])
        self.assertEqual(gunship['slot_0_impact']['wikiExplosionOf'], ['Gunship: HEAT Rocket Racks'])
        self.assertEqual(gunship['slot_2']['wikiAttacks'], ['Heavy Fusion Cycler'])
        self.assertIn('Gunship', gunship['slot_0']['sharedWithClasses'])
        for item in self.catalog['classes']:
            for attack in item['attacks']:
                for name in attack['wikiAttacks']:     # class-level names are a subset of the row-level matches
                    self.assertTrue(any(match.endswith(': ' + name) for match in attack['rowWikiMatches']))
        # The Devastator page lists stagger 15 / push 10 for its cannon; the row (and the Factory Strider page for the
        # same row) has 10 / 15, so the soldier classes' attack stays unnamed.
        self.assertEqual(self.classes['soldier']['attacks'][0]['wikiAttacks'], [])
        attack_fields = [i for i in self.catalog['fieldInstances'] if i['target']['path'] == 'attack']
        self.assertTrue(all(i['shared'] and i['allowSharedRequired'] for i in attack_fields))
        self.assertEqual(self.catalog['model']['fields']['damage.standard_damage']['apiFieldConstant'],
            'hd2.fields.damage.player_standard_damage')

    def test_attack_api_and_guards(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local rockets=hd2.enemy('Gunship'):attack('HEAT Rocket Racks')
assert(rockets.attack=='slot_0' and #rockets:describe().fields==9)
patches.validate{id='r',target=rockets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.player_standard_damage,expect=30,value=3}
local ok,why=pcall(patches.validate,{id='r',target=rockets,allow_unverified_effect=true,
 field=hd2.fields.damage.player_standard_damage,expect=30,value=3})
assert(not ok and tostring(why):find('allow_shared',1,true),why)
ok,why=pcall(patches.validate,{id='r',target=rockets,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.standard_damage,expect=30,value=3})
assert(not ok and tostring(why):find('player_standard_damage',1,true),why)
local spewer=hd2.enemy('Rupture Spewer')
assert(spewer:attack('Bile Bombard').attack=='slot_1')
patches.validate{id='s',target=spewer:attack('slot_1_impact'),allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.damage.ap_direct,expect=5,value=2}
assert(not pcall(function()return hd2.enemy('Charger'):attack('slot_0')end))
assert(#hd2.enemy('Gatekeeper'):attacks()==16)
local shell=hd2.enemy('Rupture Spewer'):attack('slot_1_projectile')
assert(#shell:describe().fields==5)
patches.validate{id='v',target=shell,allow_shared=true,allow_unverified_effect=true,field=hd2.fields.projectile.velocity,
 expect=shell:describe().fields[1].currentDefault,value=10}
local blast=hd2.enemy('Gunship'):attack('slot_0_impact_explosion')
patches.validate{id='b',target=blast,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.explosion.outer_radius,expect=1.65,value=3}
return 'ok'
''')

    def test_migration_anchors_attacks_on_their_weapon_and_blocks_per_attack(self):
        from migration import source
        attack = {'id': 'slot_0', 'slot': 0, 'weapon': {'resource': '0x2'}}
        field = {'id': 'damage.stagger', 'path': 'attack', 'attack': 'slot_0', 'currentDefault': 35,
            'editable': True, 'backing': {'kind': 'settings', 'settings': 'damage', 'recordType': 8, 'group': 1,
                'row': 9, 'offset': 32, 'storage': 'u32', 'width': 4}}
        tables = {'enemy_authoring': {'enemies': {'Gunship': {'resource': '0x1', 'health': {'uniqueOwner': True},
            'attacks': [attack], 'fields': [field]}}}}
        [record] = source.normalize(tables)
        self.assertEqual((record['object'], record['backing']['kind'], record['backing']['anchors']),
            ('Gunship/attack/slot_0', 'settings', [2]))
        self.assertTrue(record['shared'])
        self.assertEqual(record['locator']['guard'], {'id': 'damage.stagger', 'path': 'attack', 'attack': 'slot_0'})
        [link] = [l for l in source.relationships(tables) if l['key'].startswith('enemy-attack-mount:')]
        self.assertEqual((link['kind'], link['vehicle'], link['slot'], link['weapon'], link['blocks']),
            ('vehicle_mount', 1, 0, 2, [['enemy_authoring', 'Gunship/attack/slot_0']]))

    def test_migration_rebinds_the_compact_enemy_nodes(self):
        import apply_migration
        from migration import overlay, source
        field = {'id': 'zone.armor', 'path': 'damage_zone', 'zone': 'zone_0', 'currentDefault': 4, 'editable': True,
            'backing': {'offset': 736, 'storage': 'u32', 'width': 4}}
        tables = {'enemy_authoring': {'enemies': {'Charger': {'resource': '0x1', 'health': {
            'component': 'HealthComponentData', 'recordIndex': 7, 'indexRow': 9, 'ownerCount': 1,
            'uniqueOwner': True}, 'fields': [field]}}}}
        [record] = source.normalize(tables)
        self.assertEqual(record['key'], 'enemy:Charger:zone_0:zone.armor')
        self.assertEqual({k: record['backing'][k] for k in ('recordIndex', 'indexRow', 'offset', 'resource')},
            {'recordIndex': 7, 'indexRow': 9, 'offset': 736, 'resource': 1})
        self.assertEqual(record['locator'], {'path': ['enemies', 'Charger', 'fields', 0],
            'guard': {'id': 'zone.armor', 'path': 'damage_zone', 'zone': 'zone_0'}})
        target = dict(record['backing'], recordIndex=8, indexRow=12)
        decision = {'domain': 'enemy_authoring', 'locator': record['locator'], 'action': 'rebind',
            'state': 'MOVED', 'target': target, 'baseline': {'old': 4, 'new': 4}, 'reason': 'moved'}
        item = apply_migration.field_patch(record['key'], decision, tables, 'NEXT')
        overlay.patch('enemy_authoring', tables['enemy_authoring'], [item])
        self.assertEqual((field['backing']['recordIndex'], field['backing']['indexRow']), (8, 12))
        self.assertEqual(apply_migration.verify({'decisions': {record['key']: decision}}, tables, 'NEXT'), [])
        decision = dict(decision, action='readonly', state='LOST', reason='gone')
        self.assertEqual(apply_migration.field_patch(record['key'], decision, tables, 'NEXT')['set']['editable'], False)



class CoverageAuditTests(unittest.TestCase):
    def test_audit_is_fresh_against_the_catalogs(self):
        import audit_runtime_coverage as audit
        if not audit.WIKI.is_dir():
            self.skipTest('scraped wiki datasets not present')
        audit.main(['--check'])
        report = json.loads(audit.JSON_OUTPUT.read_text())
        self.assertEqual(report['writes'], 0)
        self.assertEqual(report['enemies']['attackRowsByKind'], {'damage': 85, 'explosion': 30, 'projectile': 54})
        # The four minefields (minefield.salvos) and the ten reviewed orbitals (orbital.salvos).
        self.assertEqual(report['stratagems']['statCoverage']['salvos']['covered'], 14)
        self.assertEqual(report['stratagems']['statCoverage']['callInTimeSeconds']['covered'], 61)


if __name__ == '__main__':
    unittest.main()
