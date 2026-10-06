"""Eagle components research (scripts/research_eagle_components.py -> research/eagle-components-F5FEE03DCFDB.json):
invariants of the committed report, and a cross-check of its key facts against the pinned data when available."""
import json
import unittest

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

import build_profile
from scan import report

REPORT = ROOT / 'research/eagle-components-F5FEE03DCFDB.json'
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()
EAGLES = ['Eagle Strafing Run', 'Eagle Airstrike', 'Eagle Cluster Bomb', 'Eagle Napalm Airstrike',
    'Eagle Smoke Strike', 'Eagle 110mm Rocket Pods', 'Eagle 500kg Bomb', 'Eagle Gas Airstrike']


@unittest.skipUnless(REPORT.is_file(), 'eagle components report absent')
class EagleReportInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(REPORT.read_text(encoding='utf-8'))
        cls.candidates = {c['offset']: c for c in cls.doc['candidates']}

    def test_report_format_and_safety(self):
        self.assertEqual(self.doc['schema'], report.SCHEMA)
        self.assertEqual(self.doc['build'], build_profile.BUILD_ID)
        self.assertEqual(self.doc['writes'], 0)
        self.assertEqual(self.doc['protectionChanges'], 0)
        self.assertEqual(sum(self.doc['counts'].values()), len(self.doc['candidates']))

    def test_every_member_is_a_candidate_with_the_computed_label(self):
        layout = self.doc['layout']['EagleComponent']['members']
        self.assertEqual(self.doc['layout']['EagleComponent']['size'], 152)
        self.assertEqual(len(layout), 36)
        self.assertEqual(sorted(self.candidates), [m['offset'] for m in layout])
        for c in self.candidates.values():
            self.assertEqual(c['confidence'], report.confidence(c['evidence']), c['path'])

    def test_proposed_names_fit_hidden_name_lengths(self):
        for c in self.candidates.values():
            local = c.get('proposedLocalName')
            if local:
                self.assertEqual(len(local), c['nameLength'], c['path'])
                self.assertRegex(local, r'^[a-z][a-z0-9_]*$')
                self.assertEqual(c['proposedName'], 'hd2.fields.eagle.' + local)

    def test_records_are_unique_per_jet(self):
        self.assertEqual(self.doc['summary']['sharedRecords'], 0)
        self.assertEqual(self.doc['ownership']['sharedTypeReport']['sharedRecords'], [])
        for row in self.doc['ownership']['family']:
            self.assertEqual(row['owners'], 1, row['entity'])

    def test_pins_verified_in_every_snapshot(self):
        self.assertEqual(len(self.doc['snapshotEvidence']), 7)
        for snap in self.doc['snapshotEvidence']:
            self.assertEqual(snap['pinMismatches'], [], snap['snapshot'])
            self.assertTrue(snap['typeTableEqualsEntityFile'], snap['snapshot'])
            self.assertEqual(snap['manager']['copyCount'], 0, snap['snapshot'])
        pins = [p for rows in self.doc['pins'].values() for p in rows]
        self.assertEqual(len(pins), self.doc['summary']['pins'])
        for p in pins:
            self.assertRegex(p['bytes'], r'^[0-9a-f]+$')

    def test_published_checks_all_exact(self):
        checks = self.doc['wikiChecks']
        self.assertGreaterEqual(len(checks), 40)
        self.assertTrue(all(c['exact'] for c in checks))
        fields = {(c['subject'], c['field']) for c in checks}
        self.assertIn(('Eagle Strafing Run', 'rounds per run = EagleComponentData +0x28 x rate / 60'), fields)
        self.assertIn(('Eagle Airstrike', 'bombs per strike = native pattern count of EagleComponentData +0x14'), fields)

    def test_pattern_table(self):
        table = self.doc['patternTable']
        self.assertEqual(table['rva'], 0x328CF20)
        self.assertEqual(table['stride'], 0x64)
        counts = [e['count'] for e in table['entries']]
        self.assertEqual(counts, [6, 6, 8, 8, 4, 5, 1, 3])
        for e in table['entries']:
            self.assertEqual(len(e['points']), e['count'])
        used = {name: e['value'] for e in table['entries'] for name in e['usedBy']}
        self.assertEqual(used['Eagle Airstrike'], 0)
        self.assertEqual(used['Eagle 500kg Bomb'], 6)
        self.assertEqual(used['Eagle Smoke Strike'], 3)

    def test_catalogue_and_payload_kinds(self):
        cat = self.doc['catalogue']
        self.assertEqual(sorted(cat), sorted(EAGLES))
        kinds = {n: self.doc['payloads'][n]['payload'] for n in EAGLES}
        self.assertEqual(kinds['Eagle Strafing Run'], 2)
        self.assertEqual(kinds['Eagle 110mm Rocket Pods'], 4)
        self.assertEqual({kinds[n] for n in EAGLES if n not in ('Eagle Strafing Run', 'Eagle 110mm Rocket Pods')}, {5})
        self.assertIn(35, cat['Eagle Strafing Run']['rowsNamingJet'])

    def test_proposal_is_reviewable(self):
        proposal = self.doc['promotionProposal']['typeRecordFields']
        ids = [p['id'] for p in proposal]
        self.assertEqual(len(ids), len(set(ids)))
        for p in proposal:
            self.assertTrue(p['nameLengthFit'], p['id'])
            self.assertIn(p['confidence'], ('CONFIRMED', 'STRONG'), p['id'])
            cand = self.candidates[p['native']['offset']]
            self.assertEqual(p['confidence'], cand['confidence'], p['id'])
            self.assertEqual(p['id'], cand['proposedName'], p['id'])
            if p['phase'] != 'read-only':
                self.assertTrue(p['pins'], p['id'])
                self.assertIn('allow_shared', ' '.join(p['acknowledgements']), p['id'])
                self.assertTrue(p['constraints'], p['id'])
        offsets = {p['native']['offset'] for p in proposal}
        # Members with no reader or a constant-only differential are never proposed.
        for c in self.candidates.values():
            if c['offset'] in offsets:
                self.assertTrue(c['evidence']['codeRead'], c['path'])
                self.assertTrue(c['evidence']['differential'], c['path'])
        not_promoted = {n['member'] for n in self.doc['notPromoted']}
        self.assertIn('per-entity EagleComponentData copy', not_promoted)
        for c in self.candidates.values():
            if c['offset'] not in offsets:
                self.assertIn(c['path'], not_promoted)

    def test_pins_name_their_member(self):
        for p in self.doc['promotionProposal']['typeRecordFields']:
            roles = {pin['rva']: pin['role'] for rows in self.doc['pins'].values() for pin in rows}
            pattern = r'(?<![\w\[])\+0x%02X(?![0-9A-Fa-f])' % p['native']['offset']
            for rva in p['pins']:
                self.assertRegex(roles[rva], pattern, p['id'])


@unittest.skipUnless(REPORT.is_file() and HAVE_DATALIB, 'datalibrary or report absent')
class EagleReportMatchesPinnedData(unittest.TestCase):
    def test_matrix_matches_entity_tables(self):
        from scan import tables
        doc = json.loads(REPORT.read_text(encoding='utf-8'))
        t = tables.pinned()
        eagle = t.component('EagleComponentData')
        self.assertEqual(t.fingerprint('EagleComponentData'), doc['layout']['fingerprints']['EagleComponentData'])
        for name, entry in doc['catalogue'].items():
            record = eagle.record_of(int(entry['jet'], 16))
            self.assertEqual(record, entry['record'], name)
            decoded = eagle.decode(record)
            for member in doc['matrix']['members']:
                value = decoded[str(member['offset'])]
                expected = member['values'][name]
                if isinstance(value, float):
                    self.assertAlmostEqual(value, expected, places=4, msg=f'{name} {member["hex"]}')
                else:
                    self.assertEqual(value, expected, f'{name} {member["hex"]}')

    def test_pods_magazine_pattern_lead(self):
        doc = json.loads(REPORT.read_text(encoding='utf-8'))
        mounts = doc['payloads']['Eagle 110mm Rocket Pods']['mounts']
        self.assertEqual([m['node'] for m in mounts], ['payload_right', 'payload_left'])
        for m in mounts:
            self.assertEqual(m['weapon']['magazine']['pattern'], [146, 146, 82])
            self.assertEqual(m['weapon']['magazine']['capacity'], 3)
            self.assertEqual(m['weapon']['projectileWeapon']['projectile'], 82)


if __name__ == '__main__':
    unittest.main()
