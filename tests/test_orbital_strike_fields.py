"""Orbital bombardment pattern fields (hd2.fields.orbital.salvos, shells_per_salvo, shell_interval(_random),
salvo_interval(_random), scatter, salvo_scatter) and the call-in time (hd2.fields.stratagem.call_in_time).

Pins the published catalog against the reviewed research (research/bombardment-payload-F5FEE03DCFDB.json: every pattern
field on every reviewed orbital with its record baseline, the shell list proven before every write; research/beacon-
redirect-F5FEE03DCFDB.json: every catalogued row's call-in), the guards (ranges, integers, non-finite values,
allow_unverified_effect, one backing object per transaction), the snapshot-overlay write scenario and the live-test
artifact."""
import importlib.util
import json
import re
import struct
import unittest

from support import ROOT, run

import build_profile

PATTERN = ROOT / 'research/bombardment-payload-F5FEE03DCFDB.json'
TIMING = ROOT / 'research/beacon-redirect-F5FEE03DCFDB.json'
FIELDS = {   # field id: (offset, storage, minimum, maximum, read timing)
    'orbital.salvos': (0x18, 'u32', 1, 16, 'creation'),
    'orbital.shells_per_salvo': (0x04, 'u32', 1, 64, 'creation'),
    'orbital.shell_interval': (0x08, 'f32', 0, 10, 'live'),
    'orbital.shell_interval_random': (0x0C, 'f32', 0, 10, 'live'),
    'orbital.salvo_interval': (0x1C, 'f32', 0, 30, 'live'),
    'orbital.salvo_interval_random': (0x20, 'f32', 0, 30, 'live'),
    'orbital.scatter': (0x24, 'f32', 0, 100, 'live'),
    'orbital.salvo_scatter': (0x28, 'f32', 0, 100, 'live'),
}
ORBITALS = ('Orbital 120mm HE Barrage', 'Orbital 380mm HE Barrage', 'Orbital Airburst Strike', 'Orbital EMS Strike',
    'Orbital Gas Strike', 'Orbital Gatling Barrage', 'Orbital Napalm Barrage', 'Orbital Precision Strike',
    'Orbital Smoke Strike', 'Orbital Walking Barrage')
# The research's own vanilla counts (docs/stratagem-authoring.md "Orbital bombardment pattern").
COUNTS = {'Orbital 120mm HE Barrage': (5, 3), 'Orbital 380mm HE Barrage': (5, 3), 'Orbital Airburst Strike': (4, 1),
    'Orbital EMS Strike': (1, 1), 'Orbital Gas Strike': (1, 1), 'Orbital Gatling Barrage': (4, 60),
    'Orbital Napalm Barrage': (5, 5), 'Orbital Precision Strike': (1, 1), 'Orbital Smoke Strike': (6, 1),
    'Orbital Walking Barrage': (5, 3)}


def catalog():
    return json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text(encoding='utf-8'))


class OrbitalPatternCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog()
        cls.research = json.loads(PATTERN.read_text(encoding='utf-8'))
        cls.fields = {}
        for field in cls.catalog['fieldInstances']:
            if field['backingObjectKind'] == 'BombardmentComponentData':
                cls.fields.setdefault(field['target']['stratagem'], {})[field['semanticFieldId']] = field

    def test_every_pattern_field_on_every_reviewed_orbital_has_its_record_baseline(self):
        self.assertEqual(set(self.fields), set(ORBITALS))
        records = {record['name']: bytes.fromhex(record['vanilla']) for record in self.research['records'].values()}
        for name in ORBITALS:
            self.assertEqual(set(self.fields[name]), set(FIELDS), name)
            for field_id, (offset, storage, low, high, timing) in FIELDS.items():
                field = self.fields[name][field_id]
                native = struct.unpack_from('<I' if storage == 'u32' else '<f', records[name], offset)[0]
                self.assertAlmostEqual(field['currentDefault'], native, places=5, msg=(name, field_id))
                self.assertTrue(field['editable'], (name, field_id))
                self.assertEqual((field['min'], field['max'], field['readTiming']), (low, high, timing), field_id)
                self.assertLessEqual(low, field['currentDefault'])
                self.assertLessEqual(field['currentDefault'], high)
                self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
                self.assertFalse(field['shared'], (name, field_id))
                self.assertEqual(field['target'], {'resource': 'stratagem', 'stratagem': name, 'path': 'stratagem'})
                self.assertEqual(field['apiFieldConstant'], 'hd2.fields.' + field_id)
            salvos = self.fields[name]['orbital.salvos']['currentDefault']
            shells = self.fields[name]['orbital.shells_per_salvo']['currentDefault']
            self.assertEqual((salvos, shells), COUNTS[name], name)

    def test_one_backing_object_per_orbital(self):
        objects = {name: {f['backingObjectId'] for f in fields.values()} for name, fields in self.fields.items()}
        self.assertTrue(all(len(ids) == 1 for ids in objects.values()))
        self.assertEqual(len({next(iter(ids)) for ids in objects.values()}), len(ORBITALS))

    def test_the_public_barrage_summary_and_the_shell_list(self):
        public = {item['name']: item for item in self.catalog['stratagems']}
        for name in ORBITALS:
            summary = public[name]['barrageScheduling']
            self.assertTrue(summary['writable'], name)
            self.assertEqual(set(summary['fields']), set(FIELDS))
            self.assertEqual(summary['shellsPerCall'], COUNTS[name][0] * COUNTS[name][1])
            research = next(r for r in self.research['records'].values() if r['name'] == name)
            self.assertEqual(summary['shellTypes'], research['shells'])
        # The Orbital Laser and Railcannon have no bombardment record: no barrage summary.
        self.assertIsNone(public['Orbital Laser'].get('barrageScheduling'))

    def test_live_evidence_family_is_pending_and_scoped(self):
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        family = registry['families']['orbital_pattern_fields']
        self.assertEqual(family['status'], 'pending')
        self.assertEqual(set(family['fields']), set(FIELDS))
        self.assertTrue(any('OrbitalStrikeFieldsTest' in test for test in family['nextTests']))


class CallInCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog()
        cls.timing = json.loads(TIMING.read_text(encoding='utf-8'))['timing']['byStratagem']
        cls.fields = {f['target']['stratagem']: f for f in cls.catalog['fieldInstances']
            if f['semanticFieldId'] == 'stratagem.call_in_time'}

    def test_every_catalogued_row_publishes_its_researched_call_in(self):
        self.assertEqual(len(self.fields), 94)
        for name, field in self.fields.items():
            self.assertEqual(field['backingObjectKind'], 'StratagemDefinition')
            self.assertAlmostEqual(field['currentDefault'], self.timing[name]['callIn'], places=5, msg=name)
            self.assertTrue(field['editable'])
            self.assertEqual((field['min'], field['max'], field['readTiming']), (0, 60, 'beacon_creation'))
            self.assertEqual(field['acknowledgement'], 'allow_unverified_effect')
            self.assertEqual(field['apiFieldConstant'], 'hd2.fields.stratagem.call_in_time')
        self.assertEqual(self.fields['Orbital 120mm HE Barrage']['currentDefault'], 5)
        self.assertEqual(self.fields['Orbital 380mm HE Barrage']['currentDefault'], 6)
        self.assertTrue(all(self.fields[name]['currentDefault'] == 0 for name in self.fields if name.startswith('Eagle')))

    def test_the_public_summary_and_the_items_without_a_call_in(self):
        public = {item['name']: item for item in self.catalog['stratagems']}
        refused = sorted(name for name, item in public.items() if not item['callInTime']['writable'])
        self.assertEqual(refused, ['CQC-72 Entrenchment Tool', 'SG-88 Break-Action Shotgun'])
        self.assertEqual(public['Orbital 120mm HE Barrage']['callInTime']['field'], 'hd2.fields.stratagem.call_in_time')
        self.assertIn('not part of it', public['Orbital 120mm HE Barrage']['callInTime']['semantics'])

    def test_live_evidence_family_is_pending(self):
        registry = json.loads((ROOT / 'schemas/live_evidence.json').read_text(encoding='utf-8'))
        family = registry['families']['stratagem_call_in_time']
        self.assertEqual((family['status'], family['fields']), ('pending', ['stratagem.call_in_time']))


class StrikeFieldGuardTests(unittest.TestCase):
    def test_api_and_guards(self):
        run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local transactions=require('hd2runtime/domains/transactions')
local function rejects(request,text,label)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),label..': '..tostring(why))
end
assert(hd2.fields.orbital.salvos=='orbital.salvos' and hd2.fields.orbital.salvo_scatter=='orbital.salvo_scatter'
 and hd2.fields.stratagem.call_in_time=='stratagem.call_in_time')
local ems=hd2.stratagem('Orbital EMS Strike')
local barrage=hd2.stratagem('Orbital 120mm HE Barrage')
-- One owner: no allow_shared; allow_unverified_effect is always needed.
patches.validate{id='p',target=ems,allow_unverified_effect=true,field=hd2.fields.orbital.salvos,expect=1,value=5}
rejects({id='p',target=ems,field=hd2.fields.orbital.salvos,expect=1,value=5},'allow_unverified_effect','ack')
patches.validate{id='p',target=barrage,allow_unverified_effect=true,field=hd2.fields.stratagem.call_in_time,expect=5,
 value=1}
rejects({id='p',target=barrage,field=hd2.fields.stratagem.call_in_time,expect=5,value=1},'allow_unverified_effect',
 'call-in ack')
local nan=0/0
for _,case in ipairs({{ems,'orbital.salvos',1,0,'reviewed range'},{ems,'orbital.salvos',1,17,'reviewed range'},
  {ems,'orbital.salvos',1,1.5,'integer'},{ems,'orbital.shells_per_salvo',1,65,'reviewed range'},
  {ems,'orbital.shell_interval',0.35,nan,'finite'},{ems,'orbital.scatter',1,101,'reviewed range'},
  {ems,'orbital.salvos',2,3,'expect differs'},{barrage,'stratagem.call_in_time',5,61,'reviewed range'},
  {barrage,'stratagem.call_in_time',5,-1,'reviewed range'},{barrage,'stratagem.call_in_time',5,math.huge,'finite'}})do
 rejects({id='p',target=case[1],allow_unverified_effect=true,field=case[2],expect=case[3],value=case[4]},case[5],
  case[2]..' '..tostring(case[4]))
end
-- The pattern fields share one record; the call-in shares the stratagem row with the cooldown.
transactions.validate{id='t',target=ems,allow_unverified_effect=true,changes={
 {field=hd2.fields.orbital.salvos,expect=1,value=5},{field=hd2.fields.orbital.shells_per_salvo,expect=1,value=3}}}
transactions.validate{id='t',target=barrage,allow_unverified_effect=true,changes={
 {field=hd2.fields.stratagem.call_in_time,expect=5,value=1},
 {field=hd2.fields.stratagem.definition_cooldown,expect=180,value=60}}}
local ok,why=pcall(transactions.validate,{id='t',target=ems,allow_unverified_effect=true,changes={
 {field=hd2.fields.orbital.salvos,expect=1,value=5},{field=hd2.fields.stratagem.call_in_time,expect=2,value=1}}})
assert(not ok and tostring(why):find('multiple backing objects',1,true),tostring(why))
local listed={}
for _,field in ipairs(ems:describe().fields)do listed[field.semanticFieldId]=field end
assert(listed['orbital.salvos']and listed['orbital.salvo_scatter']and listed['stratagem.call_in_time'])
return 'ok'
''')


class StrikeFieldSnapshotOverlayTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((ROOT / 'validation/orbital-fields-snapshot.json').read_text())

    def test_overlay_validation(self):
        result = self.result
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual((result['patternNoOps'], result['callInNoOps']), (80, 94))
        self.assertEqual(result['rejections'], {'acknowledgement': 174, 'conflict': 1, 'recordProof': 1, 'value': 15})
        trips = {(t['stratagem'], t['field']): t for t in result['roundTrips']}
        self.assertEqual(len(trips), 9)
        for trip in trips.values():
            self.assertEqual(trip['writes'], 1)
            for key in ('protectionRestored', 'otherBytesUnchanged', 'inverseRestored'):
                self.assertTrue(trip[key], key)
        self.assertEqual((trips[('Orbital EMS Strike', 'orbital.salvos')]['before'],
            trips[('Orbital EMS Strike', 'orbital.salvos')]['after']), ('01000000', '05000000'))
        self.assertEqual(trips[('Orbital 120mm HE Barrage', 'stratagem.call_in_time')]['offset'], 0x54)
        self.assertEqual(trips[('Orbital 380mm HE Barrage', 'stratagem.call_in_time')]['after'], '00007041')
        transactions = {t['stratagem']: t for t in result['transactions']}
        self.assertEqual(transactions['Orbital EMS Strike']['writes'], 5)
        self.assertTrue(transactions['Orbital EMS Strike']['shellTypesUnchanged'])
        self.assertEqual(result['orbitals']['Orbital 120mm HE Barrage']['shellTypes'], [194, 137, 137])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_overlay_validation_is_current(self):
        spec = importlib.util.spec_from_file_location('validate_orbital_fields_snapshot',
            ROOT / 'scripts/validate_orbital_fields_snapshot.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.validate(build_profile.SNAPSHOT), self.result)


class StrikeFieldLiveTestArtifactTests(unittest.TestCase):
    def test_example_uses_the_catalog_baselines_and_the_acknowledgement(self):
        project = ROOT / 'examples/projects/OrbitalStrikeFieldsTest'
        source = (project / 'src/addon.lua').read_text(encoding='utf-8')
        self.assertIn("local BANNER='ORBITAL STRIKE FIELDS 0.1.0 BUILD'", source)
        manifest = json.loads((project / 'hd2runtime.json').read_text())
        self.assertEqual(manifest['requires']['hd2runtime']['min_version'], (ROOT / 'VERSION').read_text().strip())
        self.assertIn('mod_options_menu', manifest['optional'])
        baseline = {(f['target']['stratagem'], f['semanticFieldId']): f['currentDefault']
            for f in catalog()['fieldInstances']}
        # Every change: the target stratagem, then its field / expect pairs (patches and transactions).
        blocks = re.findall(r"target=hd2\.stratagem\('([^']+)'\),\s*allow_unverified_effect=true,(.*?)\}\}\)", source, re.S)
        self.assertEqual(len(blocks), 6)
        checked = 0
        for name, body in blocks:
            for field, expect in re.findall(r"field=hd2\.fields\.(\w+\.\w+),expect=([\d.]+)", body):
                self.assertAlmostEqual(float(expect), baseline[(name, field)], places=5, msg=(name, field))
                checked += 1
        self.assertEqual(checked, 12)
        self.assertTrue((project / 'README.md').is_file())
        self.assertFalse((project / 'build').exists())

    def test_packaged_scenario_toggles_every_option(self):
        spec = importlib.util.spec_from_file_location('validate_packaged_runtime',
            ROOT / 'scripts/validate_packaged_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn('example-orbital-strike-fields-test', module.SCENARIOS)
        self.assertEqual([item[0] for item in module.STRATAGEM_FIELD_TOGGLES['example-orbital-strike-fields-test']],
            ['orbital_strike_fields_test.' + option for option in ('ems_barrage', 'precise_napalm', 'fast_120mm',
                'slow_380mm', 'gatling_pauses', 'eagle_delay')])
        self.assertIn('menu', module.EXTRAS['example-orbital-strike-fields-test'])


if __name__ == '__main__':
    unittest.main()
