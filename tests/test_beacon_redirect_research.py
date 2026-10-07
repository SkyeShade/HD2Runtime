"""The beacon redirect research (research/docs/beacon-redirect-F5FEE03DCFDB.md,
research/beacon-redirect-F5FEE03DCFDB.json): read-only, its pins identical in every snapshot; the manager path plausible
in every snapshot; the type replicated only at creation; the marker colour from the row category; the per-second
re-targeting keyed on +0x170 for pods only; the Eagle Rearm fleet keyed on the row's link."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/beacon-redirect-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class BeaconRedirectResearchTests(unittest.TestCase):
    def test_read_only_and_pinned(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        roles = {p['rva']: p['role'] for rows in RESEARCH['pins'].values() for p in rows}
        for rva in (0xFDAF4B, 0x5712FB, 0x6AE939, 0x6ABB53, 0x6AB546, 0x6A1426, 0x13D1557, 0x66E696, 0x670DD0):
            self.assertIn(rva, roles)

    def test_the_manager_path_in_every_snapshot(self):
        rows = RESEARCH['managerPath']['perSnapshot']
        self.assertEqual(len(rows), 7)
        for row in rows:
            self.assertEqual((row['count'], row['active'], row['mapCapacity']), (0, 0, 128))

    def test_semantics(self):
        beacon = RESEARCH['beacon']
        self.assertIn('type 0xC2EB5C15', beacon['replicatedAtCreation'])
        self.assertNotIn('type 0xC2EB5C15', beacon['replicatedOnChange'])
        categories = RESEARCH['categoryByFamily']
        self.assertEqual((categories['orbital'], categories['eagle'], categories['sentry'], categories['support']),
            ([0], [0], [3], [2]))
        follows = RESEARCH['followsByFamily']
        self.assertEqual((follows['orbital'], follows['eagle'], follows['sentry'], follows['support']),
            ([False], [False], [True], [True]))
        red, blue = RESEARCH['marker']['colours']['offensive'], RESEARCH['marker']['colours']['supply']
        self.assertEqual(red[0], 1.0)
        self.assertGreater(blue[3], 0.9)
        self.assertEqual(RESEARCH['neutralType']['type'], 0)

    def test_call_in_timing(self):
        # Both timers are computed once at creation from the carrier's row (0x6A5B70): the call-in (+0x54, modifiers),
        # the delivery time and the linger (+0x60); the activation is the crossing; the beacon is removed below zero.
        roles = {p['rva'] for p in RESEARCH['pins']['timing']}
        for rva in (0x6AE7D5, 0x87997F, 0x87999A, 0x6A5D87, 0x6A5DAF, 0x6A5DAB, 0x6AE8AB, 0x6ABB6E, 0x6ABCD8, 0x6AD9CA):
            self.assertIn(rva, roles)
        timing = RESEARCH['timing']
        self.assertEqual((timing['row']['callIn'], timing['row']['linger'], timing['countdown'], timing['threshold']),
            (0x54, 0x60, 0x0, 0x4))
        rows = timing['byStratagem']
        self.assertEqual((rows['Eagle Strafing Run']['callIn'], rows['Eagle Strafing Run']['deliveryTime']),
            (0.0, 'aircraft flight'))
        self.assertEqual((rows['Orbital 120mm HE Barrage']['callIn'], rows['Orbital 120mm HE Barrage']['orbitalTravel']),
            (5.0, True))
        self.assertEqual((rows['AC-8 Autocannon']['callIn'], rows['AC-8 Autocannon']['linger'],
            rows['AC-8 Autocannon']['category'], rows['AC-8 Autocannon']['deliveryTime']), (3.0, 4.0, 2, 'pod fall'))
        # Every Eagle has no call-in: it activates in its first update with state.
        self.assertEqual({row['callIn'] for row in rows.values() if row['kind'] == 0}, {0.0})

    def test_the_timers_have_no_consumer_outside_the_beacon(self):
        # The sweep of the beacon component's code finds only the pinned readers, the creation-message copies and the
        # element moves; the research script fails on any other access.
        accesses = {int(a, 16) for a in RESEARCH['timingAccesses']}
        readers = {p['rva'] for p in RESEARCH['pins']['timingReaders']}
        self.assertTrue(readers <= accesses)
        self.assertTrue({0x6ABB58, 0x6ABB5E, 0x6ABB3C, 0x6ABC77, 0x6AE7EA, 0x6A5DAF} <= accesses)
        self.assertTrue(all(0x6A0000 <= a < 0x6B0000 for a in accesses))
        # Only type 0x94 can have its call-in zeroed.
        self.assertIn(0x6A5C6E, {p['rva'] for p in RESEARCH['pins']['timing']})

    def test_the_barrage_lifecycle(self):
        import re
        pins = {p['rva']: p for p in RESEARCH['pins']['bombardmentLifecycle']}
        self.assertTrue({0x8519B7, 0x851A9A, 0x853551, 0x853554, 0x8522D5} <= set(pins))
        # The pinned manager is the payload domain's.
        text = (ROOT / 'domains/bombardment_payload.lua').read_text(encoding='utf-8')
        manager = int(re.search(r'\["manager"\]=\{\["global"\]=(\d+)', text).group(1))
        self.assertEqual(pins[0x851943]['ripTarget'], manager)
        instance = RESEARCH['bombardmentInstance']
        self.assertEqual((instance['states'], instance['stride'], instance['shellsFired'], instance['shellsLeft'],
            instance['salvosLeft']), (0x58, 0x70, 0x0, 0x4, 0xC))

    def test_the_ball_decides_the_look_and_a_redirect_can_unbalance_the_orbital_counter(self):
        # The beam (+0xD4), the ping and the steering (+0x170) come from the thrown ball's own type, before the beacon
        # exists; a per-player orbital counter is incremented by the spawn type and decremented by the current type.
        ball = {p['rva']: p for p in RESEARCH['pins']['ballPresentation']}
        self.assertIn('+ 0xd4]', ball[0x6A21A5]['asm'])
        self.assertIn('+ 0x170]', ball[0x6A0830]['asm'])
        counter = {p['rva']: p for p in RESEARCH['pins']['orbitalCounter']}
        self.assertTrue(counter[0x6A8ABB]['asm'].startswith('inc dword ptr'))
        self.assertIn('+ 0xc]', counter[0x6AA84F]['asm'])

    def test_the_dispatcher_record(self):
        record = RESEARCH['dispatchRecord']
        self.assertEqual((record['payload'], record['type'], record['spawn'], record['spawnRequested'],
            record['elementWaves']), (0x418, 0x424, 0x8D8, 10, 0x2C))
        roles = {p['rva'] for p in RESEARCH['pins']['dispatchRecord']}
        self.assertTrue({0x6ABB89, 0x6AC03D, 0x6AC04B, 0x6AD90F, 0x6AD919, 0x6AEB7A, 0x6AD9F9, 0x6AC007} <= roles)


if __name__ == '__main__':
    unittest.main()
