"""Sentry component research (scripts/research_sentry_components.py -> research/sentry-components-F5FEE03DCFDB.json).

The JSON invariants always run; the checks against the pinned entity file run only where the data library is present
(skipped otherwise)."""
import json
import unittest

from support import ROOT

RESEARCH = json.loads((ROOT / 'research/sentry-components-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
TURRETED = ['MG43', 'G16', 'AC8', 'M12', 'MLS4X', 'M23', 'LAS98', 'FLAM40', 'GM17']


def candidate(component, offset):
    return next(c for c in RESEARCH['candidates'] if c['component'] == component and c['offset'] == offset)


def pinned_tables():
    try:
        from scan import tables
        return tables.pinned()
    except (OSError, ValueError, KeyError):
        return None


class SentryResearchTests(unittest.TestCase):
    def test_read_only_report(self):
        self.assertEqual(RESEARCH['schema'], 'hd2runtime.scan.candidates/1')
        self.assertEqual(RESEARCH['build'], 'F5FEE03DCFDB')
        self.assertEqual((RESEARCH['writes'], RESEARCH['scope']['writes'], RESEARCH['scope']['protectionChanges']),
            (0, 0, 0))
        self.assertEqual(RESEARCH['scope']['gameDllSha256'],
            '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E')
        self.assertEqual(len(RESEARCH['scope']['sentries']), 10)
        counts = RESEARCH['counts']
        self.assertEqual(sum(counts.values()), len(RESEARCH['candidates']))

    def test_published_values_match_on_every_sentry(self):
        checks = RESEARCH['wikiChecks']
        for label in TURRETED:
            for key in ('turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min/max',
                    'weapon.horizontal_spread/vertical_spread', 'payload.lifetime', 'entity.health'):
                self.assertTrue(checks[label][key]['exact'], (label, key))
            self.assertTrue(all(item['exact'] for item in checks[label].values()), label)
        # Spread is the published full width: the mortar's 50 x 100, the rocket's 5 x 15.
        self.assertEqual(checks['M12']['weapon.horizontal_spread/vertical_spread']['native'], [50.0, 100.0])
        self.assertEqual(checks['MLS4X']['weapon.horizontal_spread/vertical_spread']['native'], [5.0, 15.0])
        # Recoil: the published horizontal/vertical are the means of drift and climb (MG-43: 10 / 1 / 5.5).
        self.assertEqual(checks['MG43']['weapon.recoil (mean)']['native'], 5.5)

    def test_confidence_labels(self):
        self.assertEqual(candidate('TurretComponentData', 12)['confidence'], 'CONFIRMED')
        self.assertEqual(candidate('TurretComponentData', 8)['confidence'], 'CONFIRMED')
        self.assertEqual(candidate('TurretComponentData', 16)['confidence'], 'STRONG')
        self.assertEqual(candidate('TurretComponentData', 28)['confidence'], 'STRONG')
        self.assertEqual(candidate('SensorEyeComponentData', 0)['confidence'], 'CONFIRMED')
        self.assertEqual(candidate('SensorEyeComponentData', 4)['confidence'], 'STRONG')
        self.assertEqual(candidate('SensorProximityComponentData', 0)['confidence'], 'STRONG')
        for offset in (84, 88, 0, 4, 28, 32):
            self.assertEqual(candidate('WeaponDataComponentData', offset)['confidence'], 'CONFIRMED', offset)
        self.assertEqual(candidate('TargetingComponentData', 0)['confidence'], 'UNKNOWN')
        # Every proposed native-name candidate fits the hidden-name length exactly.
        for item in RESEARCH['candidates']:
            if item['proposedName']:
                self.assertTrue(item['proposedNameLengthFit'], item['proposedName'])

    def test_member_values(self):
        values = candidate('TurretComponentData', 16)['values']
        self.assertEqual(values['M12'], 4.0)
        self.assertEqual(values['MG43'], 1.0)
        self.assertEqual(candidate('SensorProximityComponentData', 0)['values'], {'M12': 125.0, 'M23': 125.0,
            'GM17': 125.0})
        side = candidate('SensorEyeComponentData', 4)['values']
        self.assertTrue(all(value == -1.0 for value in side.values()))
        self.assertEqual(candidate('WeaponWindUpComponentData', 0)['values'], {'G16': 0.5})
        self.assertEqual(RESEARCH['sharedRecords'], [])

    def test_behaviour_constants_are_code(self):
        direct = RESEARCH['behaviourConstants']['directFire']
        self.assertEqual(direct['G16']['distanceScoreCurve']['points'][-1], [100.0, 0.0])
        self.assertEqual(direct['FLAM40']['distanceScoreCurve']['points'][-1], [50.0, 0.0])
        self.assertEqual({k: v['fireConeDegrees'] for k, v in direct.items()},
            {'MG43': 3.0, 'G16': 3.0, 'AC8': 2.0, 'FLAM40': 10.0, 'LAS98': 10.0})
        mortars = RESEARCH['behaviourConstants']['mortars']
        self.assertIn([25.0, 0.0, 26.0, 0.9], mortars['M12']['curveSegments'])
        self.assertIn([14.0, 0.0, 15.0, 0.9], mortars['M23']['curveSegments'])
        self.assertIn([75.0, 1.0, 125.0, 0.0], mortars['GM17']['curveSegments'])

    def test_code_pins_recorded(self):
        code = RESEARCH['codeReferences']
        for group in ('turretSettings', 'turretSpawnCopy', 'turretUpdate', 'sensorEye', 'sensorProximity',
                'targeting', 'weaponData', 'windUp', 'behaviour'):
            self.assertTrue(code[group]['pins'], group)
            for pin in code[group]['pins']:
                self.assertTrue(pin['asm'] and pin['bytes'] and pin['role'], pin)
        roles = {pin['rva']: pin['asm'] for pin in code['turretUpdate']['pins']}
        self.assertEqual(roles[0x6DF703], 'movss xmm1, dword ptr [rsi + 0x10]')
        self.assertEqual(roles[0x6DF713], 'call 0x2109e10')

    def test_proposals_and_not_promoted(self):
        ids = {p['semanticFieldId'] if isinstance(p['semanticFieldId'], str) else tuple(p['semanticFieldId'])
            for p in RESEARCH['promotionProposal']}
        for wanted in ('weapon.horizontal_spread', 'weapon.vertical_spread', 'turret.pitch_yaw_coupling',
                'targeting.side_range', 'targeting.rear_range', 'targeting.proximity_range', 'beam.fire_rate'):
            self.assertIn(wanted, ids)
        for proposal in RESEARCH['promotionProposal']:
            if 'acknowledgement' in proposal:
                self.assertTrue(proposal['acknowledgement'].startswith('allow_unverified_effect'), proposal)
        reasons = ' '.join(item['member'] for item in RESEARCH['notPromoted'])
        self.assertIn('Behaviour constants', reasons)
        self.assertIn('SensorEyeComponentData +12/+16', reasons)

    def test_snapshot_lifecycle(self):
        snaps = RESEARCH['snapshotEvidence']
        if snaps['state'] != 'read':
            self.skipTest('retained snapshots absent when the research ran')
        self.assertFalse(snaps['sentryInstancesPresent'])
        turrets = [t for s in snaps['snapshots'].values() for t in s['turrets']]
        self.assertTrue(turrets and all(t['copyMatchesType'] for t in turrets))
        for entry in snaps['snapshots'].values():
            eye = entry['sensorEyeInstances']
            self.assertEqual(eye['instances'], eye['rangeEqualsTypeTimesScale'])

    def test_against_pinned_tables(self):
        t = pinned_tables()
        if t is None:
            self.skipTest('pinned data library absent')
        for component, fingerprint in RESEARCH['layoutFingerprints'].items():
            self.assertEqual(t.fingerprint(component), fingerprint, component)
        turret = t.component('TurretComponentData')
        mortar = int(RESEARCH['scope']['sentries']['M12']['resource'], 16)
        record = turret.record_of(mortar)
        self.assertEqual(turret.decode(record)['16'], 4.0)
        self.assertEqual(turret.member(16).name_length, 14)
        proximity = t.component('SensorProximityComponentData')
        self.assertEqual(proximity.member(0).name_length, 5)


if __name__ == '__main__':
    unittest.main()
