"""Explosion identities (scripts/research_explosion_identities.py, docs/research/explosion-identities-F5FEE03DCFDB.md).

Pins the research output: every ExplosionSettings type is listed; a name comes only from a typed reference (a projectile
row, a beam row, an entity component member, a customization delta), a code literal attributed to a behavior or ability
dispatcher entry, or a shrapnel chain; the reviewed explosions (research/event-actions, the catalogued weapon
explosions) keep their owners; every type is proven against the game's settings table; packages are only owner,
loadout or mission effects packages; and the outputs are current against the pinned data."""
import json
import os
import unittest

from support import ROOT

import build_profile

OUTPUT = ROOT / 'research/explosion-identities-F5FEE03DCFDB.json'
DOC = ROOT / 'docs/research/explosion-identities-F5FEE03DCFDB.md'
ACTIONS = json.loads((ROOT / 'research/event-actions-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()
HAVE_SNAPSHOTS = all((build_profile.snapshot_directory() / name).is_file() for name in (
    'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap', 'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap',
    'F5FEE03DCFDB-20260926T222226Z.hd2snap'))
HAVE_GAME = (__import__('pathlib').Path(os.environ.get('HD2_GAME_ROOT',
    r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2')) / 'data/bundles.nxa').is_file()


class ExplosionIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(OUTPUT.read_text(encoding='utf-8'))
        cls.types = {row['type']: row for row in cls.report['explosions']}

    def test_every_type_once_and_read_only(self):
        self.assertEqual(sorted(self.types), list(range(1, 423)))
        self.assertEqual((self.report['writes'], self.report['protectionChanges']), (0, 0))
        names = [row['name'] for row in self.types.values() if row['name']]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(self.report['summary']['named'], len(names))

    def test_no_name_without_evidence(self):
        for row in self.types.values():
            if row['name']:
                self.assertTrue(row['owners'], row['type'])
                self.assertIn(row['evidenceTier'], ('data', 'code', 'chain'))
                self.assertRegex(row['name'], r'^[a-z_]+/[a-z0-9_]+(/[a-z0-9_]+)+$')
                self.assertIsNone(row['unnamedReason'])
                self.assertIn(row['name'].split('/')[0], ('weapon', 'support_weapon', 'throwable', 'stratagem',
                    'backpack', 'vehicle', 'enemy', 'entity'))
            else:
                self.assertTrue(row['unnamedReason'], row['type'])
                self.assertIsNone(row['label'])

    def test_known_owners(self):
        expect = {158: 'weapon/r36_eruptor/impact', 59: 'weapon/cb9_exploding_crossbow/impact',
            82: 'stratagem/orbital_gas_strike/shell_impact', 188: 'stratagem/orbital_ems_strike/shell_impact',
            242: 'stratagem/nux223_hellbomb/behavior', 125: 'backpack/b100_portable_hellbomb/behavior',
            293: 'entity/cyborg_production_unit/ability', 325: 'support_weapon/rl77_airburst_rocket_launcher/impact',
            176: 'stratagem/orbital_120mm_he_barrage/shell_impact', 257: 'throwable/g6_frag/detonation'}
        for kind, name in expect.items():
            self.assertEqual(self.types[kind]['name'], name, kind)
        # The Hellbomb's row is requested by mission objectives too (event-actions sharedType): shared.
        self.assertTrue(self.types[242]['shared'])
        self.assertGreater(self.types[242]['ownerCount'], 1)
        # The Eruptor's explosion is its projectile's impact (projectile-identities: projectile 40 fires).
        owners = self.types[158]['owners']
        self.assertTrue(any(o.get('name') == 'R-36 Eruptor' and o['reference'] == 'projectile' and o['projectile'] == 40
            for o in owners))
        # A component member: the G-6 Frag's ExplosiveComponent +36 detonation.
        self.assertTrue(any(o.get('name') == 'G-6 Frag' and o.get('component') == 'ExplosiveComponentData'
            and o.get('member') == '36' for o in self.types[257]['owners']))

    def test_every_reviewed_explosion_is_named_after_its_owner(self):
        for item in ACTIONS['catalogueTypes']:
            row = self.types[item['type']]
            self.assertTrue(row['name'], item)
            self.assertTrue(any(o.get('name') == item['weapon'] for o in row['owners']), item)
        for item in ACTIONS['namedExplosions']:
            row = self.types[item['type']]
            self.assertTrue(any(o.get('name') == item['name'] and o['reference'] == 'named' for o in row['owners']))

    def test_settings_table_and_code_proofs(self):
        self.assertEqual(self.report['summary']['settingsVerified'], 422)
        for observation in self.report['settingsTable']['observations']:
            self.assertEqual((observation['matched'], observation['mismatched']), (422, []))
        self.assertEqual(self.report['settingsTable']['typeBound'], 0x1A7)
        wrappers = {w['function']: w for w in self.report['code']['wrappers']}
        self.assertEqual(set(wrappers), {0x13C6D30, 0x4C89C0, 0x11AD240, 0x11AD4A0, 0x11AD6E0, 0x11AD7E0, 0x11AD9D0})
        sites = [s for s in self.report['code']['sites'] if s['literal'] == 242]
        self.assertTrue(any(['behavior', 224] in s['dispatchers'] for s in sites))
        self.assertGreater(self.report['summary']['codeSitesAttributed'], 200)

    def test_packages(self):
        allowed = {'own_loadout_package', 'stratagem_call_in_package', 'effect_loadout_package',
            'mission_effects_package', 'named_explosion_package'}
        for row in self.types.values():
            package = row['package']
            if package:
                self.assertIn(package['via'], allowed)
                self.assertTrue(package['package'].startswith('0x'))
                if package['via'] == 'mission_effects_package':
                    self.assertEqual(package['name'], 'packages/content/effects_mission')
                    self.assertTrue(package['mission'])
                elif package['via'] == 'effect_loadout_package':
                    self.assertTrue(package['name'].startswith('packages/generated/loadout/'))
        mission = self.report['missionPackages']['packages/content/effects_mission']
        self.assertTrue(all(s['resident'] for s in mission['mission']))
        self.assertFalse(any(s['resident'] for s in mission['ship']))
        # The Eruptor's effect ships in the mission effects package, not in its loadout package.
        self.assertEqual(self.types[158]['package']['via'], 'mission_effects_package')
        self.assertEqual(self.types[82]['package']['via'], 'stratagem_call_in_package')

    def test_document_lists_what_stays_unnamed(self):
        text = DOC.read_text(encoding='utf-8')
        for reason in self.report['summary']['unnamedBy']:
            self.assertIn(reason, text)

    @unittest.skipUnless(HAVE_DATALIB and HAVE_SNAPSHOTS and HAVE_GAME, 'pinned data, snapshots or game data absent')
    def test_outputs_are_current(self):
        import research_explosion_identities as research
        research.main(['--check'])


if __name__ == '__main__':
    unittest.main()
