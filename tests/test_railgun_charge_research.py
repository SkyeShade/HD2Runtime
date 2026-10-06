"""Invariants of research/railgun-charge-F5FEE03DCFDB.json (scripts/research_railgun_charge.py). Research only."""
import json
import unittest

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

import build_profile
from scan import report

OUTPUT = ROOT / 'research/railgun-charge-F5FEE03DCFDB.json'
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()


def load():
    return json.loads(OUTPUT.read_text(encoding='utf-8'))


@unittest.skipUnless(OUTPUT.is_file(), 'railgun charge research output absent')
class RailgunChargeReportTests(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.by_path = {c['path']: c for c in self.doc['candidates']}

    def test_report_format(self):
        self.assertEqual(self.doc['schema'], report.SCHEMA)
        self.assertEqual(self.doc['build'], build_profile.BUILD_ID)
        self.assertEqual(self.doc['scope']['recordSize'], 216)
        self.assertEqual(len(self.doc['records']), 11)

    def test_confidence_is_mechanical(self):
        for candidate in self.doc['candidates']:
            self.assertEqual(candidate['confidence'], report.confidence(candidate['evidence']), candidate['path'])
            if candidate['evidence']['codeRead']:
                self.assertTrue(candidate['codeRefs'], candidate['path'])

    def test_name_lengths_fit_exactly(self):
        for candidate in self.doc['candidates']:
            if candidate['evidence']['nameLengthFit']:
                self.assertEqual(len(candidate['proposedName']), candidate['nameLength'], candidate['path'])

    def test_railgun_values_and_behaviour(self):
        rail = self.doc['summary']['railgun']
        self.assertEqual(rail['chargeTimes'], [0.45, 0.5, 3.0])
        self.assertEqual(rail['damageMultiplier'], [1.0, 2.5])
        self.assertEqual(rail['speedMultiplier'], [0.7, 1.0])
        self.assertEqual(rail['explodeWhenOvercharged'], 1)
        self.assertEqual(rail['autoFireInSafety'], 0)
        self.assertEqual(rail['overchargeExplosionType'], 326)
        self.assertEqual(rail['fireModes']['slots'][:2], [5, 6])

    def test_charge_times_are_confirmed_by_code_and_published_values(self):
        for path in ('0[0].0', '0[1].0', '0[2].0'):
            candidate = self.by_path[path]
            self.assertEqual(candidate['confidence'], 'CONFIRMED')
            self.assertIn('RS-422 Railgun', candidate['publishedBy'])
            self.assertEqual(candidate['unit'], 'seconds')

    def test_published_values_and_explosions_are_exact(self):
        for label, item in self.doc['published'].items():
            self.assertTrue(all(item['exact'].values()), label)
        matched = {e['label']: e for e in self.doc['overchargeExplosions'] if e.get('published')}
        self.assertEqual(matched['RS-422 Railgun']['explosionType'], 326)
        self.assertEqual(matched['PLAS-45 Epoch']['explosionType'], 321)
        for entry in matched.values():
            self.assertTrue(all(branch['allExact'] for branch in entry['published']))

    def test_existing_ids_are_audited(self):
        verdicts = {item['id']: item['verdict'] for item in self.doc['existingIdAudit']}
        for level in (1, 2, 3):
            # Corrected in the schema (unit seconds, same offsets).
            self.assertEqual(verdicts[f'hd2.fields.charge.level_{level}'], 'corrected')
        # Deprecated aliases of the canonical speed-multiplier ids (schemas/player_weapon_fields.json alias_rules).
        self.assertEqual(verdicts['hd2.fields.charge.minimum_seconds'], 'deprecated_alias')
        self.assertEqual(verdicts['hd2.fields.charge.maximum_seconds'], 'deprecated_alias')

    def test_lifecycle_is_live_type_record(self):
        lifecycle = self.doc['lifecycle']
        self.assertEqual(lifecycle['entityDeltasTargetingComponent'], 0)
        read = [s for s in lifecycle['snapshots'] if s.get('status') == 'read']
        self.assertTrue(read)
        self.assertTrue(all(s['loadedTableEqualsFile'] for s in read))

    def test_proposal_targets_known_members(self):
        for field in self.doc['promotionProposal']['fields']:
            self.assertTrue(field['id'].startswith('hd2.fields.charge.'))
            candidate = self.by_path[field['path']]
            self.assertEqual(candidate['offset'], field['offset'], field['id'])
            self.assertIn(candidate['confidence'], ('CONFIRMED', 'STRONG', 'UNKNOWN'), field['id'])
            self.assertTrue(candidate['evidence']['codeRead'], field['id'])
        ids = [field['id'] for field in self.doc['promotionProposal']['fields']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_pins_are_unique_and_grouped(self):
        rvas = [pin['rva'] for pin in self.doc['code']['pins']]
        self.assertEqual(len(rvas), len(set(rvas)))
        groups = {pin['group'] for pin in self.doc['code']['pins']}
        for group in ('resolver', 'update', 'fire', 'scaling', 'projectile', 'arc', 'failure'):
            self.assertIn(group, groups)


@unittest.skipUnless(OUTPUT.is_file() and HAVE_DATALIB, 'datalibrary or research output absent')
class RailgunChargeDataTests(unittest.TestCase):
    def test_matrix_matches_pinned_tables(self):
        from scan import tables
        doc = load()
        component = tables.pinned().component('WeaponChargeComponentData')
        labels = doc['scope']['labels']
        for member in component.members():
            values = doc['matrix'][member.path]
            for record, label in enumerate(labels):
                native = tables.decode(member, component.raw(record))
                if isinstance(native, float):
                    self.assertAlmostEqual(values[label], native, places=5, msg=member.path)
                elif not isinstance(native, (list, str)):
                    self.assertEqual(values[label], native, member.path)


if __name__ == '__main__':
    unittest.main()
