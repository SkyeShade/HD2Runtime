"""Invariants of research/hoverpack-components-F5FEE03DCFDB.json (scripts/research_hoverpack_components.py)."""
import json
import unittest

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

import build_profile
from scan import report

OUTPUT = ROOT / 'research/hoverpack-components-F5FEE03DCFDB.json'
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()
IDENTITY_PROVEN = {'0', '156'}   # gameplay-proven launch member and the published hover duration


def load():
    return json.loads(OUTPUT.read_text(encoding='utf-8'))


@unittest.skipUnless(OUTPUT.is_file(), 'hover pack research output absent')
class HoverpackReportTests(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.by_path = {c['path']: c for c in self.doc['candidates']}

    def test_report_format(self):
        self.assertEqual(self.doc['schema'], report.SCHEMA)
        self.assertEqual(self.doc['build'], build_profile.BUILD_ID)
        self.assertEqual(self.doc['scope']['recordSize'], 280)
        self.assertEqual(len(self.doc['records']), 4)

    def test_confidence_is_mechanical(self):
        for candidate in self.doc['candidates']:
            evidence = dict(candidate['evidence'])
            if candidate['path'] in IDENTITY_PROVEN:
                evidence['nameLengthFit'] = True
            self.assertEqual(candidate['confidence'], report.confidence(evidence), candidate['path'])
            if candidate['evidence']['codeRead']:
                self.assertTrue(candidate['codeRefs'], candidate['path'])

    def test_name_lengths_fit_exactly(self):
        for candidate in self.doc['candidates']:
            if candidate['evidence']['nameLengthFit']:
                self.assertEqual(len(candidate['proposedName']), candidate['nameLength'], candidate['path'])

    def test_pack_values(self):
        jump, hover = self.doc['summary']['jumpPack'], self.doc['summary']['hoverPack']
        self.assertEqual(jump['launchThrust'], 40.0)
        self.assertEqual(jump['launchWindow'], 0.5)
        self.assertEqual(jump['launchForwardRatio'], 0.4)
        self.assertEqual(jump['airControlMaxSpeed'], 25.0)
        self.assertEqual(hover['duration'], 6.0)
        self.assertEqual([hover['maxHorizontal'], hover['maxVertical']], [3.5, 10.0])
        self.assertEqual(hover['verticalAccelLow'], 9.8)

    def test_existing_ids_keep_their_members(self):
        self.assertEqual(self.by_path['0']['existingId'], 'hd2.fields.jump.vertical_launch_velocity')
        self.assertEqual(self.by_path['0']['confidence'], 'CONFIRMED')
        self.assertEqual(self.by_path['156']['existingId'], 'hd2.fields.hover.duration')
        self.assertEqual(self.by_path['156']['confidence'], 'CONFIRMED')

    def test_lifecycle_is_live_type_record(self):
        lifecycle = self.doc['lifecycle']
        self.assertEqual(lifecycle['entityDeltasTargeting']['JumppackComponentData'], 0)
        read = [s for s in lifecycle['snapshots'] if s.get('status') == 'read']
        self.assertTrue(read)
        self.assertTrue(all(s['loadedTableEqualsFile'] for s in read))

    def test_proposal_targets_code_read_members(self):
        ids = []
        for field in self.doc['promotionProposal']['fields']:
            ids.append(field['id'])
            self.assertTrue(field['id'].startswith(('hd2.fields.jump.', 'hd2.fields.hover.')))
            for path in field['path'].split('+'):
                candidate = self.by_path[path]
                self.assertTrue(candidate['evidence']['codeRead'], field['id'])
                self.assertIn(candidate['role'], ('gameplay', 'switch'), field['id'])
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_shared_struct_type_with_related_families(self):
        for family in self.doc['crossFamily']['related']:
            for struct_type in family['nestedStructTypes']:
                self.assertNotEqual(struct_type, 'JumppackComponent', family['component'])


@unittest.skipUnless(OUTPUT.is_file() and HAVE_DATALIB, 'datalibrary or research output absent')
class HoverpackDataTests(unittest.TestCase):
    def test_matrix_matches_pinned_tables(self):
        from scan import tables
        doc = load()
        component = tables.pinned().component('JumppackComponentData')
        labels = doc['scope']['labels']
        for member in component.members():
            for record, label in enumerate(labels):
                native = tables.decode(member, component.raw(record))
                if member.atom == 'VECTOR':
                    for index, value in enumerate(native):
                        self.assertAlmostEqual(doc['matrix'][f'{member.path}[{index}]'][label], value, places=5)
                elif isinstance(native, float):
                    self.assertAlmostEqual(doc['matrix'][member.path][label], native, places=5, msg=member.path)
                elif not isinstance(native, str):
                    self.assertEqual(doc['matrix'][member.path][label], native, member.path)


if __name__ == '__main__':
    unittest.main()
