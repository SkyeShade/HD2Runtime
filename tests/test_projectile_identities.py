"""Projectile identities (scripts/research_projectile_identities.py, docs/research/projectile-identities-F5FEE03DCFDB.md).

Pins the research output: names come only from structural evidence in the game's data (entity members typed
ProjectileType, attack outputs, explosion submunitions), never from the community hint list, which is only compared;
known owners resolve as the Runtime's other research established them; the reviewed hint file keeps every hint row;
and the outputs are current against the pinned datalibrary."""
import csv
import io
import json
import unittest

from support import ROOT

import build_profile

OUTPUT = ROOT / 'research/projectile-identities-F5FEE03DCFDB.json'
HINTS = ROOT / 'research/leads/reddit-projectile-id-hypotheses.csv'
REVIEWED = ROOT / 'research/leads/reddit-projectile-id-hypotheses-reviewed.csv'
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()


def owners(row):
    return {(o['names'][0]['name'] if o['names'] else o['resource'], o['role']) for o in row['identity']['owners']}


class ProjectileIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(OUTPUT.read_text(encoding='utf-8'))
        cls.types = {row['type']: row for row in cls.report['types']}

    def test_every_type_and_no_name_without_evidence(self):
        self.assertEqual(sorted(self.types), list(range(1, 351)))
        self.assertEqual((self.report['writes'], self.report['protectionChanges']), (0, 0))
        for row in self.types.values():
            identity = row['identity']
            evidence = identity['owners'] or identity['outputs'] or identity['submunitionOf']
            self.assertEqual(bool(row['runtimeName']), bool(evidence), row['type'])
            # The hint never becomes a name: the runtime name is built from the evidence only.
            if row['runtimeName']:
                self.assertNotEqual(row['runtimeName'], row['hint']['label'], row['type'])

    def test_known_owners_resolve(self):
        self.assertIn(('R-36 Eruptor', 'fires'), owners(self.types[40]))
        self.assertIn(('PLAS-45 Epoch', 'charge level 1'), owners(self.types[165]))
        self.assertEqual(owners(self.types[193]), {('PLAS-45 Epoch', 'charge level 2'), ('PLAS-45 Epoch', 'charge level 3')})
        self.assertEqual(owners(self.types[197]), {('Orbital Gas Strike', 'orbital shell')})
        self.assertEqual(owners(self.types[188]), {('Eagle Gas Airstrike', 'Eagle payload projectile')})
        self.assertIn(('Orbital EMS Strike', 'orbital shell'), owners(self.types[74]))
        # The shared shrapnel: the Eruptor's, the AC-8's, the GL-28's and the G-6 Frag's explosions spawn type 201.
        sources = {s['explosion'] for s in self.types[201]['identity']['submunitionOf']}
        self.assertTrue({158, 404, 393, 257} <= sources, sources)

    def test_hint_verdicts_are_mechanical_comparisons(self):
        verdicts = {row['hint']['verdict'] for row in self.types.values()}
        self.assertLessEqual(verdicts, {'AGREES', 'CONTRADICTED', 'CONSISTENT', 'INCONSISTENT', 'OWNER_UNNAMED',
            'UNVERIFIED'})
        self.assertEqual(self.types[40]['hint']['verdict'], 'AGREES')
        # The community calls 188 an orbital gas shell; the data says it is the Eagle Gas Airstrike's bomb.
        self.assertEqual(self.types[188]['hint']['verdict'], 'CONTRADICTED')
        summary = self.report['summary']
        self.assertEqual(sum(summary['byVerdict'].values()), 350)
        self.assertEqual(summary['withRuntimeName'], sum(1 for row in self.types.values() if row['runtimeName']))

    def test_the_reviewed_hint_file_keeps_every_hint(self):
        hints = list(csv.DictReader(io.StringIO(HINTS.read_text(encoding='utf-8-sig'))))
        reviewed = list(csv.DictReader(io.StringIO(REVIEWED.read_text(encoding='utf-8'))))
        self.assertEqual([(r['projectile_id'], r['reddit_suggested_label']) for r in reviewed],
            [(r['projectile_id'], r['reddit_suggested_label']) for r in hints])
        self.assertEqual(set(reviewed[0]), {'projectile_id', 'reddit_suggested_label', 'source_status',
            'runtime_verified', 'runtime_name', 'comparison_notes'})
        for row in reviewed:
            self.assertIn(row['runtime_verified'], ('True', 'False', 'unknown'))
            self.assertEqual(row['source_status'], 'unverified community hypothesis')

    @unittest.skipUnless(HAVE_DATALIB, 'pinned datalibrary absent')
    def test_outputs_are_current(self):
        import research_projectile_identities as research
        research.main(['--check'])


if __name__ == '__main__':
    unittest.main()
