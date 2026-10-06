"""The vehicle and mech component research domain (scripts/research_vehicle_mech_components.py,
research/vehicle-mech-components-F5FEE03DCFDB.json, docs/research/vehicle-mech-components-F5FEE03DCFDB.md): read-only,
every proposal meets the field-naming proof standard (code read, name-length fit, differential, ownership, lifecycle),
the record-lookup rule holds for every table, and the facts the report rests on. The layout fingerprints and a few
values are re-read from the pinned entity file when the data library is present."""
import json
import unittest

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

import build_profile

RESEARCH_PATH = ROOT / 'research/vehicle-mech-components-F5FEE03DCFDB.json'
RESEARCH = json.loads(RESEARCH_PATH.read_text(encoding='utf-8')) if RESEARCH_PATH.is_file() else None
DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()
CONFIDENCE = ('CONFIRMED', 'STRONG', 'PLAUSIBLE', 'UNKNOWN')


@unittest.skipIf(RESEARCH is None, 'vehicle mech research JSON absent')
class VehicleMechResearchTests(unittest.TestCase):
    def test_read_only_and_build(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertEqual(RESEARCH['build'], build_profile.BUILD_ID)
        self.assertEqual(RESEARCH['schema'], 'hd2runtime.scan.candidates/1')
        self.assertEqual(RESEARCH['inputs']['entitiesSha256'], build_profile.ENTITY_SHA256)

    def test_table_offset_rule(self):
        for component, item in RESEARCH['codeMap'].items():
            self.assertEqual(item['tableOffset'], 0xF12478 + 8 * item['componentIndex'], component)
            self.assertTrue(item['lookups']['tableLoads'], component)
        self.assertEqual(RESEARCH['codeMap']['MountComponentData']['lookups']['byResource'], [0x510220])

    def test_pins_cover_the_semantics(self):
        pins = {p['rva']: p for rows in RESEARCH['pins'].values() for p in rows}
        for rva, asm in ((0x6DF4AD, 'movss xmm9, dword ptr [rax + 0x20]'), (0x6DF4BE, 'movss xmm7, dword ptr [rax + 0x1c]'),
                         (0x6DFC7F, 'movss xmm6, dword ptr [rsi + 0x14]'), (0x6DFC91, 'movss xmm6, dword ptr [rsi + 0x18]'),
                         (0x6E0806, 'mov eax, dword ptr [rax + 0xc]'), (0x6E0844, 'mov eax, dword ptr [rax + 8]'),
                         (0x61D758, 'movss xmm0, dword ptr [r15]'), (0x61F913, 'mulss xmm2, dword ptr [rdx + 0x30]'),
                         (0x715902, 'mulss xmm0, dword ptr [r12 + 0x16c]'), (0x4FA859, 'add rax, qword ptr [r11 + 0xc0]')):
            self.assertEqual(pins[rva]['asm'], asm)
            self.assertTrue(pins[rva]['bytes'])
        self.assertEqual(pins[0x510225]['ripTarget'], 0x346BF98)
        self.assertAlmostEqual(pins[0x6DF4B6]['constant'], 0.0174533, places=6)
        self.assertEqual(RESEARCH['networkFieldNames']['fields']['0x9611C029']['name'], 'turn_speed_modifier')

    def test_lifecycle(self):
        managers = RESEARCH['lifecycle']['managers']
        self.assertIsNone(managers['VehicleMotionComponentData']['resolvedAccessor'])
        for component in ('VehicleComponentData', 'TurretComponentData', 'RotationComponentData',
                          'LocomotionComponentData'):
            self.assertIsNotNone(managers[component]['resolvedAccessor'], component)
            self.assertTrue(RESEARCH['codeMap'][component]['lookups']['resolved'], component)
        self.assertFalse(RESEARCH['codeMap']['VehicleMotionComponentData']['lookups']['resolved'])
        for name, row in RESEARCH['lifecycle']['snapshots'].items():
            if isinstance(row, dict) and 'TurretComponentData' in row:
                # No vehicle is alive and no private copy exists in any retained mission snapshot.
                self.assertEqual(row['vehicleComponentInstanceCounters'], [0, 0, 0], name)
                self.assertEqual(row['ProjectileWeaponComponentData']['privateCopies'], 0, name)
        feasibility = RESEARCH['customVehicleFeasibility']['components']
        self.assertFalse(feasibility['VehicleMotionComponentData']['privateCopySupported'])
        self.assertTrue(feasibility['TurretComponentData']['privateCopySupported'])

    def test_inventory(self):
        vehicles = {v['label']: v for v in RESEARCH['vehicles']}
        catalog = [v for v in RESEARCH['vehicles'] if v['catalogName']]
        self.assertEqual(len(catalog), 11)
        for name in ('EXO-45 Patriot Exosuit', 'EXO-49 Emancipator Exosuit', 'EXO-51 Lumberer Exosuit',
                     'EXO-55 Breakthrough Exosuit'):
            self.assertEqual((vehicles[name]['kind'], vehicles[name]['driveModel']), ('exosuit', 'legged_pilot'))
        for name in ('TD-220 Bastion MK XVI', 'TD-110 Maelstrom'):
            self.assertEqual(vehicles[name]['driveModel'], 'tracked')
        for name in ('M-102 Gunner FRV', 'M-103 Supply FRV', 'M-104 Incinerator FRV'):
            self.assertEqual((vehicles[name]['driveModel'], vehicles[name]['populatedWheels']), ('wheeled', 4))
        for vehicle in RESEARCH['vehicles']:
            for component, record in vehicle['components'].items():
                self.assertEqual(record['shared'], record['owners'] > 1)

    def test_candidates_and_proposal(self):
        candidates = {(c['component'], c['offset']): c for rows in RESEARCH['families'].values()
            for c in rows['candidates']}
        self.assertEqual(set(RESEARCH['families']), {'movement', 'suspension', 'turret', 'durability'})
        for candidate in candidates.values():
            self.assertIn(candidate['confidence'], CONFIDENCE)
            self.assertIn(candidate['status'], ('proposed', 'research_only', 'already_promoted'))
        pins = set(RESEARCH['pins'])
        proposed = {(p['component'], p['offset']) for p in RESEARCH['promotionProposal']}
        self.assertEqual(proposed, {k for k, c in candidates.items() if c['status'] == 'proposed'})
        for proposal in RESEARCH['promotionProposal']:
            candidate = candidates[(proposal['component'], proposal['offset'])]
            self.assertTrue(proposal['fieldId'].startswith('hd2.fields.'))
            self.assertIn(proposal['confidence'], ('STRONG', 'CONFIRMED'))
            self.assertEqual(len(proposal['semanticName']), proposal['nameLength'], proposal['fieldId'])
            self.assertTrue(candidate['evidence']['codeRead'] and candidate['evidence']['differential'])
            self.assertTrue(proposal['codeRefs'] and set(proposal['codeRefs']) <= pins, proposal['fieldId'])
            self.assertIn('allow_unverified_effect', proposal['acknowledgement'])
            self.assertFalse(proposal['sharedRecord'])
            self.assertTrue(proposal['values'] and proposal['units'] and proposal['constraints'])
        ids = {p['fieldId'] for p in RESEARCH['promotionProposal']}
        # Phase 2: vehicle turrets reuse the sentry turret ids on the same TurretComponent members.
        self.assertEqual(ids, {'hd2.fields.turret.yaw_speed', 'hd2.fields.turret.pitch_speed',
            'hd2.fields.turret.pitch_min', 'hd2.fields.turret.pitch_max', 'hd2.fields.turret.yaw_min',
            'hd2.fields.turret.yaw_max', 'hd2.fields.rotation.turn_speed', 'hd2.fields.rotation.acceleration',
            'hd2.fields.rotation.deceleration', 'hd2.fields.vehicle.steering_response_speed'})
        for proposal in RESEARCH['promotionProposal']:
            self.assertTrue(proposal['lifecycle'] and proposal['rangeReason'], proposal['fieldId'])
            self.assertLess(proposal['min'], proposal['max'])
        for row in RESEARCH['notPromoted']:
            self.assertTrue(row['reasons'], row)

    def test_authoring_backings(self):
        authoring = RESEARCH['authoring']
        self.assertEqual(len(authoring['vehicleFields']), 19)    # 4 Exosuits x 3 rotation + 7 steering vehicles
        self.assertEqual(len(authoring['mountFields']), 30)      # 5 turret mounts x 6
        self.assertEqual(authoring['entityDeltas']['touchingTargets'], [])
        for item in authoring['vehicleFields'] + authoring['mountFields']:
            self.assertEqual((item['ownerCount'], item['uniqueOwner'], item['ownerResources']), (1, True, [item['resource']]))
            contract = authoring['fieldContracts'][item['field']]
            self.assertTrue(contract['min'] <= item['baseline'] <= contract['max'], item)
        self.assertIn('M-102 Gunner FRV / gun', authoring['notApplicable']['turret'])
        self.assertIn('EXO-45 Patriot Exosuit / left_gun', authoring['notApplicable']['turret'])
        self.assertIn('M-102 Gunner FRV', authoring['notApplicable']['rotation'])
        self.assertIn('EXO-45 Patriot Exosuit', authoring['notApplicable']['steering'])

    def test_published_values(self):
        bastion = {x['quantity']: x for x in RESEARCH['publishedMovement']['TD-220 Bastion MK XVI']['values']}
        self.assertEqual(bastion['top speed (drive gear)']['matches'], [])
        durability = {r['vehicle']: r for r in RESEARCH['durabilityCrossCheck']['vehicles']}
        for name, row in durability.items():
            if row['published']:
                self.assertEqual((row['mainHealth'], row['mainArmor']),
                    (row['publishedMainHealth'], row['publishedMainArmor']), name)
        tires = next(a for a in durability['M-102 Gunner FRV']['anatomy'] if a['part'].startswith('Tires'))
        self.assertEqual((tires['publishedHealth'], len(tires['zonesWithEqualHealth'])), (350, 4))


@unittest.skipIf(RESEARCH is None or not HAVE_DATALIB, 'pinned data library absent')
class VehicleMechPinnedDataTests(unittest.TestCase):
    def test_layouts_and_values_match_the_pinned_tables(self):
        import struct
        from scan import tables
        t = tables.pinned()
        for component, layout in RESEARCH['layouts'].items():
            self.assertEqual(t.fingerprint(component), layout['fingerprint'], component)
        turret = t.component('TurretComponentData')
        gun = turret.raw(turret.record_of(0x4DF41F84668D07FB))            # M-103 Supply FRV gun
        self.assertEqual(struct.unpack_from('<6f', gun, 8), (90.0, 130.0, 1.0, -60.0, 90.0, -180.0))
        rotation = t.component('RotationComponentData')
        patriot = rotation.raw(rotation.record_of(0x79E4B3D2DA5E45E3))
        self.assertEqual(struct.unpack_from('<3f', patriot, 0), (65.0, 0.0, 0.0))
        motion = t.component('VehicleMotionComponentData')
        frv = motion.raw(motion.record_of(0xCC21C7FFD3EBEFB9))
        self.assertAlmostEqual(struct.unpack_from('<f', frv, 364)[0], 3.1, places=5)


if __name__ == '__main__':
    unittest.main()
