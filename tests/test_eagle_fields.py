"""Eagle attack fields (hd2.fields.eagle.*, Phase A): EagleComponentData members of each Eagle stratagem's own jet.

Pins the published catalog against the reviewed research publication (every Phase A field on every Eagle with its
research baseline, editable exactly where the native code reads it for that Eagle's attack kind), the guards (ranges,
non-finite values, the pattern enumeration, allow_unverified_effect on every field, allow_shared exactly on the three
shared jets, read-only members), the snapshot-overlay write scenario and the live-test artifact."""
import importlib.util
import json
import re
import unittest

from support import ROOT, run

import build_profile

RESEARCH = ROOT / 'research/eagle-components-F5FEE03DCFDB.json'
EAGLES = ('Eagle Strafing Run', 'Eagle Airstrike', 'Eagle Cluster Bomb', 'Eagle Napalm Airstrike',
    'Eagle Smoke Strike', 'Eagle 110mm Rocket Pods', 'Eagle 500kg Bomb', 'Eagle Gas Airstrike')
PHASE_A = ('eagle.airstrike_pattern', 'eagle.drop_interval', 'eagle.fire_duration', 'eagle.attack_sweep_length',
    'eagle.target_radius', 'eagle.attack_angle')
SHARED = {'Eagle Strafing Run', 'Eagle Gas Airstrike', 'Eagle Napalm Airstrike'}
EDITABLE = {   # by attack kind: bombs (5), strafe (2), rockets (4)
    'Eagle Strafing Run': {'eagle.fire_duration', 'eagle.attack_sweep_length', 'eagle.target_radius',
        'eagle.attack_angle'},
    'Eagle 110mm Rocket Pods': {'eagle.fire_duration', 'eagle.target_radius', 'eagle.attack_angle'},
    **{name: {'eagle.airstrike_pattern', 'eagle.drop_interval', 'eagle.attack_angle'} for name in
        ('Eagle Airstrike', 'Eagle Cluster Bomb', 'Eagle Napalm Airstrike', 'Eagle Smoke Strike', 'Eagle 500kg Bomb',
         'Eagle Gas Airstrike')}}
# The research baselines (research/docs/eagle-components-F5FEE03DCFDB.md, section 3).
BASELINE = {
    'Eagle Strafing Run': (0, 0.5, 1.5, 60, 60, 180), 'Eagle Airstrike': (0, 0.2, 1.5, 50, 60, 90),
    'Eagle Cluster Bomb': (3, 0.1, 1.5, 50, 60, 90), 'Eagle Napalm Airstrike': (4, 0.2, 1.5, 50, 60, 90),
    'Eagle Smoke Strike': (3, 0.2, 2.0, 60, 60, 90), 'Eagle 110mm Rocket Pods': (0, 0.5, 2.0, 10, 20, 180),
    'Eagle 500kg Bomb': (6, 0.05, 1.5, 0, 60, 180), 'Eagle Gas Airstrike': (7, 0.2, 1.5, 50, 60, 90)}
RANGES = {'eagle.airstrike_pattern': (0, 7), 'eagle.drop_interval': (0.02, 1.0), 'eagle.fire_duration': (0.1, 6.0),
    'eagle.attack_sweep_length': (0.0, 200.0), 'eagle.target_radius': (1.0, 300.0), 'eagle.attack_angle': (0.0, 360.0)}


class EagleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.publication = json.loads(RESEARCH.read_text(encoding='utf-8'))['publication']
        cls.fields = {}
        for field in cls.catalog['fieldInstances']:
            if field['backingObjectKind'] == 'EagleComponentData':
                cls.fields.setdefault(field['target']['stratagem'], {})[field['semanticFieldId']] = field

    def test_every_phase_a_field_on_every_eagle_has_its_research_baseline(self):
        self.assertEqual(set(self.fields), set(EAGLES))
        for name in EAGLES:
            fields = self.fields[name]
            for field_id, baseline in zip(PHASE_A, BASELINE[name]):
                field = fields[field_id]
                self.assertAlmostEqual(field['currentDefault'], baseline, places=5, msg=(name, field_id))
                self.assertEqual(field['currentDefault'], self.publication['eagles'][name]['values'][field_id[6:]])
                self.assertEqual(field['target'], {'resource': 'stratagem', 'stratagem': name, 'path': 'stratagem'})
                self.assertEqual(field['apiFieldConstant'], 'hd2.fields.' + field_id)
                self.assertEqual(field['editable'], field_id in EDITABLE[name], (name, field_id))
                if field['editable']:
                    self.assertEqual((field['min'], field['max']), RANGES[field_id], (name, field_id))
                    self.assertTrue(field['rangeJustification'])
                    self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')   # not live-tested
                    self.assertNotIn('liveEvidence', field)
                    self.assertIn(field['readTiming'], ('live', 'dispatch'))
                    self.assertIn('not per call', field['writeScope'].lower())
                else:
                    self.assertTrue(field['reason'], (name, field_id))
                    self.assertNotIn('acknowledgement', field)
        summary = self.catalog['summary']
        self.assertEqual(summary['eagleComponentFieldsWritable'], sum(len(v) for v in EDITABLE.values()))
        self.assertEqual(summary['eagleComponentFieldsWritable'], 25)
        self.assertEqual(summary['eagleComponentFieldsReadOnly'], 38)
        self.assertEqual(summary['eagleComponentSharedJets'], sorted(SHARED))

    def test_readers_and_timing(self):
        timing = {'eagle.airstrike_pattern': 'live', 'eagle.drop_interval': 'live', 'eagle.fire_duration': 'live',
            'eagle.attack_sweep_length': 'live', 'eagle.target_radius': 'dispatch', 'eagle.attack_angle': 'dispatch'}
        for name, editable in EDITABLE.items():
            for field_id in editable:
                field = self.fields[name][field_id]
                self.assertEqual(field['readTiming'], timing[field_id], field_id)
                self.assertIn('0x514B40' if timing[field_id] == 'live' else '0x514640', field['nativeReader'])

    def test_allow_shared_exactly_on_the_shared_jets(self):
        for name in EAGLES:
            for field in self.fields[name].values():
                self.assertEqual(field['allowSharedRequired'], name in SHARED, (name, field['semanticFieldId']))
                self.assertEqual(field['shared'], name in SHARED)
                consumers = field['sharedConsumers']
                self.assertIn({'stratagem': name, 'path': 'eagle_jet'}, consumers)
                others = [c for c in consumers if 'externalConsumer' in c]
                self.assertEqual(bool(others), name in SHARED)
                for other in others:
                    self.assertTrue(other['semanticStatus'])
                    self.assertNotRegex(other['externalConsumer'], r'0x[0-9A-Fa-f]{16}')
        strafe = self.fields['Eagle Strafing Run']['eagle.fire_duration']['sharedConsumers']
        self.assertEqual({c['path'] for c in strafe}, {'eagle_jet', 'stratagem_definition', 'eagle_spawner'})
        for name in ('Eagle Gas Airstrike', 'Eagle Napalm Airstrike'):
            self.assertEqual({c['path'] for c in self.fields[name]['eagle.attack_angle']['sharedConsumers']},
                {'eagle_jet', 'eagle_spawner'})
        public = {item['name']: item for item in self.catalog['stratagems']}
        for name in EAGLES:
            self.assertEqual(public[name]['eagleAttack']['allowSharedRequired'], name in SHARED)

    def test_pattern_enumeration_and_derived_counts(self):
        bombs = [6, 6, 8, 8, 4, 5, 1, 3]
        patterns = self.catalog['eagleAirstrikePatterns']
        self.assertEqual([p['value'] for p in patterns['values']], list(range(8)))
        self.assertEqual([p['bombs'] for p in patterns['values']], bombs)
        self.assertEqual(patterns['extraBombStatDefault'], 0)
        for name, editable in EDITABLE.items():
            fields = self.fields[name]
            if 'eagle.airstrike_pattern' in editable:
                allowed = fields['eagle.airstrike_pattern']['allowedValues']
                self.assertEqual([(a['value'], a['bombs']) for a in allowed], list(zip(range(8), bombs)))
                self.assertEqual(fields['eagle.bombs_per_strike']['currentDefault'],
                    bombs[fields['eagle.airstrike_pattern']['currentDefault']])
                self.assertFalse(fields['eagle.bombs_per_strike']['editable'])
            else:
                self.assertNotIn('eagle.bombs_per_strike', fields)
            self.assertFalse(fields['eagle.payload']['editable'])
        self.assertEqual(self.fields['Eagle Airstrike']['eagle.bombs_per_strike']['currentDefault'], 6)
        self.assertEqual(self.fields['Eagle 500kg Bomb']['eagle.bombs_per_strike']['currentDefault'], 1)
        self.assertEqual(self.fields['Eagle Strafing Run']['eagle.strafe_rounds_per_run']['currentDefault'], 100)
        self.assertEqual({name: self.fields[name]['eagle.payload']['currentDefault'] for name in EAGLES},
            {**{name: 'airstrike' for name in EAGLES}, 'Eagle Strafing Run': 'strafe',
             'Eagle 110mm Rocket Pods': 'rocket'})

    def test_one_backing_object_per_jet(self):
        objects = {name: {f['backingObjectId'] for f in fields.values()} for name, fields in self.fields.items()}
        self.assertTrue(all(len(ids) == 1 for ids in objects.values()))
        self.assertEqual(len({next(iter(ids)) for ids in objects.values()}), 8)

    def test_live_evidence_family_is_pending_and_scoped(self):
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        family = registry['families']['eagle_component_fields']
        self.assertEqual(family['status'], 'pending')
        self.assertEqual(set(family['fields']), set(PHASE_A))
        self.assertTrue(any('EagleFieldsTest' in test for test in family['nextTests']))


class EagleGuardTests(unittest.TestCase):
    def test_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local function rejects(request,text,label)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),label..': '..tostring(why))
end
assert(hd2.fields.eagle.airstrike_pattern=='eagle.airstrike_pattern' and hd2.fields.eagle.attack_angle=='eagle.attack_angle')
local air=hd2.stratagem('Eagle Airstrike')
local strafe=hd2.stratagem('Eagle Strafing Run')
local napalm=hd2.stratagem('Eagle Napalm Airstrike')
local rockets=hd2.stratagem('Eagle 110mm Rocket Pods')
-- The Airstrike's jet record has one consumer: no allow_shared; allow_unverified_effect is always needed.
patches.validate{id='p',target=air,allow_unverified_effect=true,field=hd2.fields.eagle.airstrike_pattern,expect=0,value=2}
rejects({id='p',target=air,field=hd2.fields.eagle.airstrike_pattern,expect=0,value=2},'allow_unverified_effect','ack')
-- Shared jets need allow_shared.
rejects({id='p',target=strafe,allow_unverified_effect=true,field=hd2.fields.eagle.fire_duration,expect=1.5,value=3},
 'allow_shared','strafe shared')
patches.validate{id='p',target=strafe,allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.eagle.fire_duration,expect=1.5,value=3}
rejects({id='p',target=napalm,allow_unverified_effect=true,field=hd2.fields.eagle.drop_interval,expect=0.2,value=0.6},
 'allow_shared','napalm shared')
patches.validate{id='p',target=rockets,allow_unverified_effect=true,field=hd2.fields.eagle.target_radius,expect=20,value=60}
-- Values.
local nan=0/0
for _,case in ipairs({{air,'eagle.airstrike_pattern',0,8,'reviewed range'},{air,'eagle.airstrike_pattern',0,1.5,'integer'},
  {air,'eagle.drop_interval',0.2,0,'reviewed range'},{strafe,'eagle.fire_duration',1.5,nan,'finite'},
  {strafe,'eagle.fire_duration',1.5,math.huge,'finite'},{rockets,'eagle.target_radius',20,301,'reviewed range'},
  {strafe,'eagle.attack_sweep_length',60,-1,'reviewed range'},{air,'eagle.attack_angle',90,-10,'reviewed range'},
  {air,'eagle.airstrike_pattern',2,3,'expect differs'}})do
 rejects({id='p',target=case[1],allow_shared=true,allow_unverified_effect=true,field=case[2],expect=case[3],
  value=case[4]},case[5],case[2]..' '..tostring(case[4]))
end
-- Read-only members.
for _,case in ipairs({{strafe,'eagle.airstrike_pattern',0,2},{air,'eagle.target_radius',60,30},
  {rockets,'eagle.attack_sweep_length',10,20},{air,'eagle.payload','airstrike','strafe'},
  {air,'eagle.bombs_per_strike',6,8},{strafe,'eagle.strafe_rounds_per_run',100,200}})do
 rejects({id='p',target=case[1],allow_shared=true,allow_unverified_effect=true,field=case[2],expect=case[3],
  value=case[4]},'read-only',case[2])
end
-- One record per transaction: Eagle fields and the definition cooldown are separate backing objects.
transactions.validate{id='t',target=air,allow_unverified_effect=true,changes={
 {field=hd2.fields.eagle.airstrike_pattern,expect=0,value=2},{field=hd2.fields.eagle.drop_interval,expect=0.2,value=0.3}}}
local ok,why=pcall(transactions.validate,{id='t',target=air,allow_unverified_effect=true,changes={
 {field=hd2.fields.eagle.airstrike_pattern,expect=0,value=2},{field=hd2.fields.stratagem.definition_cooldown,expect=15,value=5}}})
assert(not ok and tostring(why):find('multiple backing objects',1,true),tostring(why))
-- The descriptor lists the Eagle fields on the stratagem itself.
local listed={}
for _,field in ipairs(air:describe().fields)do listed[field.semanticFieldId]=field end
assert(listed['eagle.airstrike_pattern']and listed['eagle.drop_interval']and listed['eagle.bombs_per_strike'])
return 'ok'
''')


class EagleSnapshotOverlayTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((ROOT / 'validation/eagle-fields-snapshot.json').read_text())

    def test_overlay_validation(self):
        result = self.result
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual(result['noOps'], 25)
        self.assertEqual(result['readOnly'], 38)
        self.assertEqual(result['rejections'], {'acknowledgement': 25, 'allowShared': 10, 'conflict': 1,
            'readOnly': 8, 'recordProof': 1, 'value': 14})
        self.assertEqual(result['withoutAllowShared'], 15)
        trips = {(t['stratagem'], t['field']): t for t in result['roundTrips']}
        self.assertEqual(set(trips), {('Eagle Airstrike', 'eagle.airstrike_pattern'),
            ('Eagle Napalm Airstrike', 'eagle.drop_interval'), ('Eagle Strafing Run', 'eagle.fire_duration'),
            ('Eagle 110mm Rocket Pods', 'eagle.target_radius'), ('Eagle Strafing Run', 'eagle.attack_sweep_length'),
            ('Eagle 500kg Bomb', 'eagle.attack_angle')})
        for trip in trips.values():
            self.assertEqual(trip['writes'], 1)
            for key in ('protectionRestored', 'otherBytesUnchanged', 'otherEaglesUnchanged', 'inverseRestored'):
                self.assertTrue(trip[key], key)
        # Exact bytes: pattern 0 -> 2 (i32) and the f32 encodings of 0.2 -> 0.6 and 1.5 -> 3.0.
        self.assertEqual((trips[('Eagle Airstrike', 'eagle.airstrike_pattern')]['before'],
            trips[('Eagle Airstrike', 'eagle.airstrike_pattern')]['after']), ('00000000', '02000000'))
        self.assertEqual(trips[('Eagle Napalm Airstrike', 'eagle.drop_interval')]['after'], '9a99193f')
        self.assertEqual(trips[('Eagle Strafing Run', 'eagle.fire_duration')]['after'], '00004040')
        self.assertEqual(result['writes'], 2 * len(trips))
        self.assertEqual(result['protectionChanges'], 2 * result['writes'])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_overlay_validation_is_current(self):
        spec = importlib.util.spec_from_file_location('validate_eagle_fields_snapshot',
            ROOT / 'scripts/validate_eagle_fields_snapshot.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.validate(build_profile.SNAPSHOT), self.result)


class EagleLiveTestArtifactTests(unittest.TestCase):
    def test_example_uses_the_catalog_baselines_and_exact_acknowledgements(self):
        project = ROOT / 'examples/projects/EagleFieldsTest'
        source = (project / 'src/addon.lua').read_text(encoding='utf-8')
        self.assertIn("local BANNER='EAGLE FIELDS 0.1.0 BUILD'", source)
        manifest = json.loads((project / 'hd2runtime.json').read_text())
        self.assertEqual(manifest['requires']['hd2runtime']['min_version'], '0.30.0')   # the release that added these fields
        self.assertIn('mod_options_menu', manifest['optional'])
        catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        baseline = {(f['target']['stratagem'], f['semanticFieldId']): f['currentDefault']
            for f in catalog['fieldInstances'] if f['backingObjectKind'] == 'EagleComponentData'}
        operations = re.findall(r"target=hd2\.stratagem\('([^']+)'\),\s*(allow_shared=true,)?allow_unverified_effect=true,"
            r"field=hd2\.fields\.(eagle\.\w+),expect=([\d.]+),value=([\d.]+)", source)
        self.assertEqual(len(operations), 4)
        for name, shared, field, expect, value in operations:
            self.assertAlmostEqual(float(expect), baseline[(name, field)], places=5)
            self.assertEqual(bool(shared), name in SHARED, name)
        self.assertTrue((project / 'README.md').is_file())
        self.assertFalse((project / 'build').exists())   # no built artifact is committed

    def test_packaged_scenario_toggles_every_option(self):
        spec = importlib.util.spec_from_file_location('validate_packaged_runtime',
            ROOT / 'scripts/validate_packaged_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn('example-eagle-fields-test', module.SCENARIOS)
        self.assertEqual(module.STRATAGEM_FIELD_TOGGLES['example-eagle-fields-test'],
            [('eagle_fields_test.airstrike_pattern', [1], 1, True), ('eagle_fields_test.napalm_interval', [2], 1, True),
             ('eagle_fields_test.strafe_duration', [3], 1, True), ('eagle_fields_test.rocket_radius', [4], 1, True)])
        self.assertIn('menu', module.EXTRAS['example-eagle-fields-test'])


if __name__ == '__main__':
    unittest.main()
