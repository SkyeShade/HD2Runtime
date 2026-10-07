"""The arbitrary carrier research (research/docs/arbitrary-carrier-F5FEE03DCFDB.md,
research/arbitrary-carrier-F5FEE03DCFDB.json): read-only, its pins identical in every snapshot, and the facts the
report rests on: the delivery kinds per family, the Eagle row (one aircraft payload, linked Eagle Rearm), the beacon's
type read once at activation by the spawn dispatcher, and the bombardment private copies."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/arbitrary-carrier-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class ArbitraryCarrierResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        self.assertIn(0x6AE910, roles)      # beacon init: the type into the element's +0xC
        self.assertIn(0x6ABC14, roles)      # activation: the beacon's own type ...
        self.assertIn(0x6ABC72, roles)      # ... to the spawn dispatcher
        self.assertIn(0x6ABE21, roles)      # no payload: nothing spawned
        self.assertIn(0x66E696, roles)      # the Eagle fleet: rows linking Eagle Rearm
        self.assertIn(0x50447D, roles)      # private copy, else the shared record

    def test_delivery_kinds_and_the_eagle_row(self):
        families = RESEARCH['deliveryFamilies']
        self.assertEqual(families['0'], ['eagle', 'uncatalogued'])
        self.assertIn('orbital', families['1'])
        self.assertTrue({'sentry', 'emplacement', 'mine', 'backpack', 'support'} <= set(families['2']))
        self.assertIn('vehicle', families['3'])
        self.assertIn('orbital', families['5'])
        # Only Eagle Rearm is ever linked, and among catalogued rows only by Eagles (type 35, an uncatalogued
        # Strafing Run variant, links it too).
        self.assertEqual({x['type'] for x in RESEARCH['linkedTypes']}, {49})
        self.assertEqual({x['family'] for x in RESEARCH['linkedTypes']} - {None}, {'eagle'})
        row = RESEARCH['strafingRun']['row']
        self.assertEqual((row['type'], row['delivery'], row['uses'], row['linkedType'], row['payloads']),
            (30, 0, 4, 49, ['0x23A60681DD4383EC']))
        self.assertTrue({'Eagle', 'ProjectileWeapon', 'Unit'} <= set(RESEARCH['strafingRun']['components']))
        self.assertIn('Bombardment', RESEARCH['orbitalComponents'])
        observed = RESEARCH['rearmObserved']
        self.assertEqual(observed['rearm'][:2], observed['strafingRun'][:2])

    def test_the_beacon_and_the_empty_rows(self):
        beacon = RESEARCH['beacon']
        self.assertEqual((beacon['element']['stride'], beacon['element']['type']), (0x40, 0xC))
        self.assertEqual(beacon['replicated']['type'], '0xC2EB5C15')
        self.assertEqual(RESEARCH['defaultRow'], '0x37CB470')
        self.assertTrue(any(r['type'] == 49 for r in RESEARCH['payloadless']))
        self.assertEqual(RESEARCH['bombardment']['copySize'], 192)


if __name__ == '__main__':
    unittest.main()
