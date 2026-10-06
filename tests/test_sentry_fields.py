"""Sentry component fields (research/sentry-components-F5FEE03DCFDB.json "publication").

Pins the published catalog against the reviewed research publication: every field on every sentry its structure
carries, with its research baseline, range, read timing (spawn copy or live) and allow_unverified_effect; the reviewed
exclusions (Laser/Flame/Tesla spread and recoil, the Tesla's side/rear ranges) as blocked fields; the read-only averaged
recoil; the lifecycle and AI engagement caps added to the existing turret and targeting fields; the deferred
proximity range. Then the guards (ranges, the -1 sentinel, non-finite and non-integer values, acknowledgements, no
allow_shared, fields a sentry does not carry), the snapshot-overlay write scenario and the live-test artifact."""
import importlib.util
import json
import re
import unittest

from support import ROOT, run

import build_profile

RESEARCH = ROOT / 'research/sentry-components-F5FEE03DCFDB.json'
PROJECTILE = ('A/MG-43 Machine Gun Sentry', 'A/G-16 Gatling Sentry', 'A/AC-8 Autocannon Sentry', 'A/M-12 Mortar Sentry',
    'A/MLS-4X Rocket Sentry', 'A/M-23 EMS Mortar Sentry', 'A/GM-17 Gas Mortar Sentry')
TURRETED = PROJECTILE + ('A/LAS-98 Laser Sentry', 'A/FLAM-40 Flame Sentry')
SPREAD_RECOIL = ('weapon.horizontal_spread', 'weapon.vertical_spread', 'weapon.recoil_drift_horizontal',
    'weapon.recoil_drift_vertical', 'weapon.recoil_climb_horizontal', 'weapon.recoil_climb_vertical')
APPLIES = {**{field: set(PROJECTILE) for field in SPREAD_RECOIL},
    'windup.wind_up_seconds': {'A/G-16 Gatling Sentry'}, 'windup.wind_down_seconds': {'A/G-16 Gatling Sentry'},
    'beam.fire_rate': {'A/LAS-98 Laser Sentry'}, 'turret.pitch_yaw_coupling': set(TURRETED),
    'targeting.side_range': set(TURRETED), 'targeting.rear_range': set(TURRETED)}
PATH = {**{field: 'weapon' for field in SPREAD_RECOIL}, 'windup.wind_up_seconds': 'weapon',
    'windup.wind_down_seconds': 'weapon', 'beam.fire_rate': 'weapon', 'turret.pitch_yaw_coupling': 'turret',
    'targeting.side_range': 'targeting', 'targeting.rear_range': 'targeting'}
RANGE = {**{field: (0, 500) for field in SPREAD_RECOIL[:2]}, **{field: (0, 100) for field in SPREAD_RECOIL[2:]},
    'windup.wind_up_seconds': (0, 30), 'windup.wind_down_seconds': (0, 30), 'beam.fire_rate': (1, 3000),
    'turret.pitch_yaw_coupling': (0, 10), 'targeting.side_range': (0, 500), 'targeting.rear_range': (0, 500)}
TIMING = {**{field: 'spawn' for field in SPREAD_RECOIL}, 'windup.wind_up_seconds': 'live',
    'windup.wind_down_seconds': 'live', 'beam.fire_rate': 'unverified', 'turret.pitch_yaw_coupling': 'live',
    'targeting.side_range': 'spawn', 'targeting.rear_range': 'spawn'}
# The research baselines (docs/research/sentry-components-F5FEE03DCFDB.md sections 4, 5, 7, 8).
BASELINE = {('A/MG-43 Machine Gun Sentry', 'weapon.horizontal_spread'): 10.0,
    ('A/M-12 Mortar Sentry', 'weapon.vertical_spread'): 100.0, ('A/MLS-4X Rocket Sentry', 'weapon.vertical_spread'): 15.0,
    ('A/AC-8 Autocannon Sentry', 'weapon.horizontal_spread'): 2.0,
    ('A/MG-43 Machine Gun Sentry', 'weapon.recoil_drift_horizontal'): 20.0,
    ('A/G-16 Gatling Sentry', 'weapon.recoil_climb_vertical'): 3.0,
    ('A/AC-8 Autocannon Sentry', 'weapon.recoil_climb_vertical'): 10.0,
    ('A/G-16 Gatling Sentry', 'windup.wind_up_seconds'): 0.5, ('A/G-16 Gatling Sentry', 'windup.wind_down_seconds'): 1.0,
    ('A/LAS-98 Laser Sentry', 'beam.fire_rate'): 60, ('A/AC-8 Autocannon Sentry', 'turret.pitch_yaw_coupling'): 1.0,
    ('A/M-12 Mortar Sentry', 'turret.pitch_yaw_coupling'): 4.0, ('A/GM-17 Gas Mortar Sentry', 'turret.pitch_yaw_coupling'): 4.0,
    ('A/FLAM-40 Flame Sentry', 'targeting.side_range'): -1.0, ('A/LAS-98 Laser Sentry', 'targeting.rear_range'): -1.0}


class SentryCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        cls.publication = cls.research['publication']
        cls.fields = {(f['target'].get('stratagem'), f['semanticFieldId'], f['target']['path']): f
            for f in cls.catalog['fieldInstances']}
        cls.public = {item['name']: item for item in cls.catalog['stratagems']}

    def test_every_field_on_every_applicable_sentry_has_its_research_baseline(self):
        self.assertEqual(set(self.publication['fields']), set(APPLIES))
        sentries = [name for name, item in self.public.items() if item['family'] == 'sentry']
        self.assertEqual(len(sentries), 10)
        writable = 0
        for field_id, applies in APPLIES.items():
            spec = self.publication['fields'][field_id]
            self.assertEqual(set(spec['appliesTo']), applies, field_id)
            for name in sentries:
                field = self.fields.get((name, field_id, PATH[field_id]))
                if name not in applies:
                    self.assertIsNone(field, (name, field_id))
                    continue
                writable += 1
                self.assertEqual(field['currentDefault'], self.publication['sentries'][name]['values'][field_id])
                self.assertEqual(field['apiFieldConstant'], 'hd2.fields.' + field_id)
                self.assertTrue(field['editable'], (name, field_id))
                self.assertEqual((field['min'], field['max']), RANGE[field_id], field_id)
                self.assertTrue(field['rangeJustification'] and field['nativeReader'])
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')   # not live-tested
                self.assertNotIn('liveEvidence', field)
                self.assertEqual(field['readTiming'], TIMING[field_id], field_id)
                self.assertTrue(field['readTimingNote'])
                self.assertEqual((field['shared'], field['allowSharedRequired']), (False, False), (name, field_id))
                self.assertEqual(field['sharedConsumers'], [{'stratagem': name, 'path': 'deployed_entity/weapon:primary'}])
                self.assertEqual(field['backingObjectKind'], spec['component'])
                self.assertIn('not per deployment', field['writeScope'])
                if field_id.startswith('targeting.'):
                    self.assertEqual(field['sentinelValues'][0]['value'], -1)
                else:
                    self.assertNotIn('sentinelValues', field)
        self.assertEqual(writable, 72)
        for (name, field_id), value in BASELINE.items():
            self.assertEqual(self.fields[(name, field_id, PATH[field_id])]['currentDefault'], value, (name, field_id))
        summary = self.catalog['summary']
        self.assertEqual((summary['sentryComponentFieldsWritable'], summary['sentryComponentFieldsDerived']), (72, 21))
        self.assertEqual(summary['sentryComponentFieldsDeferred'], ['targeting.proximity_range'])

    def test_records_have_one_owner_each(self):
        internal = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text())['stratagems']
        for name, sentry in self.publication['sentries'].items():
            for component, own in sentry['components'].items():
                self.assertEqual((own['owners'], own['unique']), (1, True), (name, component))
            for field in internal[name]['fields']:
                if field['semanticFieldId'] in APPLIES:
                    backing = field['backing']
                    self.assertEqual((backing['ownerCount'], backing['uniqueOwner']), (1, True))
                    self.assertEqual(backing['recordIndex'], sentry['components'][backing['component']]['record'])

    def test_exclusions_are_published_with_their_reason(self):
        def blocked(name):
            return {b['field']: b['reason'] for b in self.public[name]['deployedEntity']['blockedFields']}
        for name, word in (('A/LAS-98 Laser Sentry', 'beam'), ('A/FLAM-40 Flame Sentry', 'spray'),
                ('A/ARC-3 Tesla Tower', 'arc')):
            reasons = blocked(name)
            for field_id in SPREAD_RECOIL:
                self.assertIn(word, reasons[field_id], (name, field_id))
        tesla = blocked('A/ARC-3 Tesla Tower')
        for field_id in ('targeting.side_range', 'targeting.rear_range'):
            self.assertIn('shape type 3', tesla[field_id])
        self.assertEqual(self.public['A/MG-43 Machine Gun Sentry']['sentryFields']['excluded'], {})
        self.assertEqual(self.public['A/MG-43 Machine Gun Sentry']['sentryFields']['constants']['turret.pitch_yaw_coupling'],
            'hd2.fields.turret.pitch_yaw_coupling')

    def test_averaged_recoil_is_derived_and_read_only(self):
        expected = {'A/MG-43 Machine Gun Sentry': (10.0, 1.0, 5.5), 'A/G-16 Gatling Sentry': (5.0, 1.5, 3.25),
            'A/AC-8 Autocannon Sentry': (2.5, 10.0, 6.25)}
        for name in PROJECTILE:
            for field_id in ('weapon.horizontal_recoil', 'weapon.vertical_recoil', 'weapon.recoil'):
                field = self.fields[(name, field_id, 'weapon')]
                self.assertFalse(field['editable'])
                self.assertTrue(field['reason'])
                self.assertTrue(field['derivedFrom'])
                self.assertNotIn('acknowledgement', field)
        for name, values in expected.items():
            self.assertEqual(tuple(self.fields[(name, f, 'weapon')]['currentDefault'] for f in
                ('weapon.horizontal_recoil', 'weapon.vertical_recoil', 'weapon.recoil')), values)
        for name in ('A/LAS-98 Laser Sentry', 'A/FLAM-40 Flame Sentry', 'A/ARC-3 Tesla Tower'):
            self.assertNotIn((name, 'weapon.recoil', 'weapon'), self.fields)

    def test_existing_fields_publish_their_lifecycle_and_the_ai_cap(self):
        timing = {'turret.yaw_speed': 'spawn', 'turret.pitch_speed': 'spawn', 'turret.pitch_min': 'live',
            'turret.pitch_max': 'live', 'turret.yaw_min': 'live', 'turret.yaw_max': 'live'}
        for name in TURRETED:
            for field_id, expected in timing.items():
                self.assertEqual(self.fields[(name, field_id, 'turret')]['readTiming'], expected, (name, field_id))
            rng = self.fields[(name, 'targeting.range', 'targeting')]
            self.assertEqual((rng['readTiming'], rng['min'], rng['max']), ('spawn', 1, 500))   # range unchanged
        cap = {name: self.fields[(name, 'targeting.range', 'targeting')].get('engagementCap') for name in TURRETED}
        self.assertEqual({name: (c or {}).get('scoreCutoffMeters') for name, c in cap.items()}, {
            'A/MG-43 Machine Gun Sentry': 100.0, 'A/G-16 Gatling Sentry': 100.0, 'A/AC-8 Autocannon Sentry': 100.0,
            'A/LAS-98 Laser Sentry': 100.0, 'A/FLAM-40 Flame Sentry': 50.0, 'A/M-12 Mortar Sentry': 125.0,
            'A/M-23 EMS Mortar Sentry': 125.0, 'A/GM-17 Gas Mortar Sentry': 125.0, 'A/MLS-4X Rocket Sentry': None})
        for name, minimum in (('A/M-12 Mortar Sentry', 25.0), ('A/M-23 EMS Mortar Sentry', 14.0),
                ('A/GM-17 Gas Mortar Sentry', 14.0)):
            self.assertEqual(cap[name]['minimumMeters'], minimum)
            self.assertEqual(cap[name]['proximitySensor']['radiusMeters'], 125.0)
        # The live-proven fields keep their evidence and no acknowledgement.
        self.assertIn('liveEvidence', self.fields[('A/MG-43 Machine Gun Sentry', 'targeting.range', 'targeting')])
        self.assertIn('liveEvidence', self.fields[('A/AC-8 Autocannon Sentry', 'turret.yaw_speed', 'turret')])

    def test_proximity_range_is_deferred(self):
        self.assertFalse(any(f['semanticFieldId'] == 'targeting.proximity_range' for f in self.catalog['fieldInstances']))
        definitions = json.loads((ROOT / 'schemas/stratagem_fields.json').read_text())['fields']
        self.assertNotIn('targeting.proximity_range', {d['id'] for d in definitions})
        deferred = self.publication['deferred']
        self.assertEqual([d['field'] for d in deferred], ['targeting.proximity_range'])
        self.assertIn('runtime profile', deferred[0]['reason'])
        proposal = next(p for p in self.research['promotionProposal']
            if p.get('semanticFieldId') == 'targeting.proximity_range')
        self.assertEqual(proposal['status'], 'deferred')

    def test_live_evidence_family_is_pending_and_scoped(self):
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        family = registry['families']['sentry_component_fields']
        self.assertEqual(family['status'], 'pending')
        self.assertEqual(set(family['fields']), set(APPLIES))
        self.assertIn('sentry', family['scope'])
        self.assertTrue(any('SentryTuningTest' in test for test in family['nextTests']))


class SentryGuardTests(unittest.TestCase):
    def test_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local function rejects(request,text,label)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),label..': '..tostring(why))
end
assert(hd2.fields.turret.pitch_yaw_coupling=='turret.pitch_yaw_coupling'
 and hd2.fields.targeting.side_range=='targeting.side_range' and hd2.fields.targeting.rear_range=='targeting.rear_range',
 'field constants')
local function entity(name)return hd2.stratagem(name):deployed_entity()end
local mg=entity('A/MG-43 Machine Gun Sentry');local ac=entity('A/AC-8 Autocannon Sentry')
local m12=entity('A/M-12 Mortar Sentry');local g16=entity('A/G-16 Gatling Sentry')
local las=entity('A/LAS-98 Laser Sentry');local tesla=entity('A/ARC-3 Tesla Tower')
-- One owner each: allow_unverified_effect is needed, allow_shared is not.
transactions.validate{id='t',target=mg:weapon('primary'),allow_unverified_effect=true,changes={
 {field=hd2.fields.weapon.horizontal_spread,expect=10,value=300},{field=hd2.fields.weapon.vertical_spread,expect=10,value=300}}}
rejects({id='p',target=mg:weapon('primary'),field=hd2.fields.weapon.horizontal_spread,expect=10,value=300},
 'allow_unverified_effect','spread ack')
patches.validate{id='p',target=ac:turret(),allow_unverified_effect=true,field=hd2.fields.turret.pitch_yaw_coupling,
 expect=1,value=10}
rejects({id='p',target=m12:turret(),field=hd2.fields.turret.pitch_yaw_coupling,expect=4,value=0},
 'allow_unverified_effect','coupling ack')
patches.validate{id='p',target=g16:weapon('primary'),allow_unverified_effect=true,field=hd2.fields.windup.wind_up_seconds,
 expect=0.5,value=6}
patches.validate{id='p',target=las:weapon('primary'),allow_unverified_effect=true,field=hd2.fields.beam.fire_rate,
 expect=60,value=120}
transactions.validate{id='t',target=mg:targeting(),allow_unverified_effect=true,changes={
 {field=hd2.fields.targeting.side_range,expect=-1,value=10},{field=hd2.fields.targeting.rear_range,expect=-1,value=3}}}
-- The -1 sentinel and the range bounds.
patches.validate{id='p',target=mg:targeting(),allow_unverified_effect=true,field=hd2.fields.targeting.side_range,
 expect=-1,value=-1}
patches.validate{id='p',target=mg:targeting(),allow_unverified_effect=true,field=hd2.fields.targeting.rear_range,
 expect=-1,value=0}
local nan=0/0
for _,case in ipairs({{mg:targeting(),'targeting.side_range',-1,-0.5,'reviewed range'},
  {mg:targeting(),'targeting.rear_range',-1,501,'reviewed range'},{mg:weapon('primary'),'weapon.vertical_spread',10,501,'reviewed range'},
  {ac:weapon('primary'),'weapon.recoil_climb_vertical',10,101,'reviewed range'},{ac:turret(),'turret.pitch_yaw_coupling',1,11,'reviewed range'},
  {g16:weapon('primary'),'windup.wind_down_seconds',1,31,'reviewed range'},{las:weapon('primary'),'beam.fire_rate',60,0,'reviewed range'},
  {las:weapon('primary'),'beam.fire_rate',60,90.5,'integer'},{mg:weapon('primary'),'weapon.horizontal_spread',10,nan,'finite'},
  {ac:turret(),'turret.pitch_yaw_coupling',1,math.huge,'finite'},{mg:weapon('primary'),'weapon.horizontal_spread',12,30,'expect differs'}})do
 rejects({id='p',target=case[1],allow_unverified_effect=true,field=case[2],expect=case[3],value=case[4]},case[5],
  case[2]..' '..tostring(case[4]))
end
-- Read-only averaged recoil.
rejects({id='p',target=mg:weapon('primary'),allow_unverified_effect=true,field=hd2.fields.weapon.recoil,expect=5.5,value=0},
 'read-only','averaged recoil')
-- Fields a sentry does not carry.
for _,case in ipairs({{las:weapon('primary'),'weapon.horizontal_spread',5,10},{tesla:targeting(),'targeting.side_range',-1,10},
  {mg:weapon('primary'),'windup.wind_up_seconds',0.5,1},{mg:weapon('primary'),'beam.fire_rate',60,120}})do
 rejects({id='p',target=case[1],allow_unverified_effect=true,field=case[2],expect=case[3],value=case[4]},'not exposed',
  case[2])
end
-- Different records are different backing objects: one transaction may not span them.
local ok,why=pcall(transactions.validate,{id='t',target=g16:weapon('primary'),allow_unverified_effect=true,changes={
 {field=hd2.fields.windup.wind_up_seconds,expect=0.5,value=2},{field=hd2.fields.weapon.horizontal_spread,expect=10,value=20}}})
assert(not ok and tostring(why):find('multiple backing objects',1,true),tostring(why))
-- The descriptors list the new fields on their targets.
local listed={}
for _,field in ipairs(ac:turret():describe().fields)do listed[field.semanticFieldId]=field end
assert(listed['turret.pitch_yaw_coupling'] and listed['turret.yaw_speed'],'turret describe')
listed={}
for _,field in ipairs(mg:targeting():describe().fields)do listed[field.semanticFieldId]=field end
assert(listed['targeting.side_range'] and listed['targeting.rear_range'] and listed['targeting.range'],'targeting describe')
return 'ok'
''')


class SentrySnapshotOverlayTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((ROOT / 'validation/sentry-fields-snapshot.json').read_text())

    def test_overlay_validation(self):
        result = self.result
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['noOps'], result['derivedReadOnly'], result['withoutAllowShared']), (72, 21, 72))
        self.assertEqual(result['rejections'], {'acknowledgement': 72, 'conflict': 2, 'notApplicable': 6,
            'readOnly': 3, 'value': 19})
        trips = {(t['stratagem'], t['field']): t for t in result['roundTrips']}
        self.assertEqual(len(trips), 8)
        for trip in trips.values():
            self.assertEqual(trip['writes'], 1)
            for key in ('protectionRestored', 'otherBytesUnchanged', 'otherSentriesUnchanged', 'inverseRestored'):
                self.assertTrue(trip[key], key)
        # Exact bytes: f32 10 -> 300, 1 -> 10, -1 -> 10, -1 -> 3, 0.5 -> 6 and the i32 beam rate 60 -> 120.
        spread = trips[('A/MG-43 Machine Gun Sentry', 'weapon.horizontal_spread')]
        self.assertEqual((spread['before'], spread['after'], spread['offset']), ('00002041', '00009643', 84))
        coupling = trips[('A/AC-8 Autocannon Sentry', 'turret.pitch_yaw_coupling')]
        self.assertEqual((coupling['before'], coupling['after'], coupling['offset']), ('0000803f', '00002041', 16))
        side = trips[('A/MG-43 Machine Gun Sentry', 'targeting.side_range')]
        self.assertEqual((side['before'], side['after'], side['offset']), ('000080bf', '00002041', 4))
        self.assertEqual(trips[('A/MG-43 Machine Gun Sentry', 'targeting.rear_range')]['after'], '00004040')
        self.assertEqual(trips[('A/G-16 Gatling Sentry', 'windup.wind_up_seconds')]['after'], '0000c040')
        beam = trips[('A/LAS-98 Laser Sentry', 'beam.fire_rate')]
        self.assertEqual((beam['before'], beam['after']), ('3c000000', '78000000'))
        self.assertEqual(result['writes'], 2 * len(trips))
        self.assertEqual(result['protectionChanges'], 2 * result['writes'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_overlay_validation_is_current(self):
        spec = importlib.util.spec_from_file_location('validate_sentry_fields_snapshot',
            ROOT / 'scripts/validate_sentry_fields_snapshot.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.validate(build_profile.SNAPSHOT), self.result)


class SentryLiveTestArtifactTests(unittest.TestCase):
    def test_example_uses_the_catalog_baselines_and_exact_acknowledgements(self):
        project = ROOT / 'examples/projects/SentryTuningTest'
        source = (project / 'src/addon.lua').read_text(encoding='utf-8')
        self.assertIn("local BANNER='SENTRY TUNING 0.1.0 BUILD'", source)
        manifest = json.loads((project / 'hd2runtime.json').read_text())
        self.assertEqual(manifest['requires']['hd2runtime']['min_version'], (ROOT / 'VERSION').read_text().strip())
        self.assertIn('mod_options_menu', manifest['optional'])
        self.assertNotIn('allow_shared=true', source)              # one owner per record
        catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        baseline = {(f['target']['stratagem'], f['semanticFieldId']): f['currentDefault']
            for f in catalog['fieldInstances'] if f['target']['resource'] == 'stratagem'}
        operations = re.findall(r"\{field=hd2\.fields\.(\w+\.\w+),expect=(-?[\d.]+),value=(-?[\d.]+)\}", source)
        operations += re.findall(r"field=hd2\.fields\.(\w+\.\w+),expect=(-?[\d.]+),value=(-?[\d.]+)\}\}\)", source)
        self.assertEqual(len(operations), 12)
        names = re.findall(r"sentry\('([^']+)'\)", source)
        self.assertEqual(set(names), {'A/MG-43 Machine Gun Sentry', 'A/AC-8 Autocannon Sentry', 'A/M-12 Mortar Sentry',
            'A/G-16 Gatling Sentry'})
        for field, expect, _ in operations:
            self.assertTrue(any(abs(baseline.get((name, field), 1e9) - float(expect)) < 1e-6 for name in names), field)
        # Every new field sets allow_unverified_effect; only the live-proven targeting.range control omits it.
        ensures = source.split('hd2.ensure(')[1:]
        self.assertEqual(len(ensures), 8)
        for ensure in ensures:
            self.assertEqual('allow_unverified_effect=true' in ensure, 'targeting.range' not in ensure, ensure[:60])
        self.assertTrue((project / 'README.md').is_file())
        self.assertFalse((project / 'build').exists())   # no built artifact is committed

    def test_packaged_scenario_toggles_every_option(self):
        spec = importlib.util.spec_from_file_location('validate_packaged_runtime',
            ROOT / 'scripts/validate_packaged_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn('example-sentry-tuning-test', module.SCENARIOS)
        toggles = module.STRATAGEM_FIELD_TOGGLES['example-sentry-tuning-test']
        self.assertEqual([t[0].split('.')[1] for t in toggles], ['mg43_spread', 'ac8_recoil', 'ac8_coupling',
            'm12_coupling', 'g16_windup', 'mg43_blind_spots', 'mg43_yaw_limits', 'mg43_range_control'])
        self.assertEqual(sum(t[2] for t in toggles), 12)
        self.assertIn('menu', module.EXTRAS['example-sentry-tuning-test'])

    def test_example_validation_is_recorded(self):
        report = json.loads((ROOT / 'validation/example-projects.json').read_text(encoding='utf-8'))
        result = report['results']['SentryTuningTest']
        self.assertEqual((result['status'], result['minVersion'], result['baselineChanges']),
            ('VALIDATED', '0.30.0-dev', 12))


if __name__ == '__main__':
    unittest.main()
