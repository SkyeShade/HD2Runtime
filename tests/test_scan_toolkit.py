"""Research scanner toolkit (scripts/scan): synthetic fixtures for the algorithms, pinned-data integration checks."""
import struct
import tempfile
import unittest
from pathlib import Path

from support import ROOT  # noqa: F401  (puts scripts/ on sys.path)

import build_profile
from scan import compare, golib, report, strides

DATALIB = build_profile.datalibrary()
HAVE_DATALIB = (DATALIB / 'generated_entities.dl_bin').is_file() and (DATALIB / 'dl_library.dl_typelib').is_file()
HAVE_SNAPSHOT = (build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap').is_file()


class PartitionAndHintTests(unittest.TestCase):
    def test_partition_is_canonical(self):
        self.assertEqual(compare.partition([5.0, 7.0, 5.0, 9.0]), (0, 1, 0, 2))
        self.assertEqual(compare.partition([1, 1, 1]), (0, 0, 0))
        # Floats that differ below the canonical rounding are one group.
        self.assertEqual(compare.partition([0.1, 0.1000000001]), (0, 0))

    def test_hints_are_leads_not_names(self):
        self.assertIn('whole_degrees_range', compare.hints('float', [-60.0, 90.0, -45.0]))
        self.assertIn('unit_interval', compare.hints('float', [0.0, 0.7, 1.0]))
        self.assertIn('sentinel_only', compare.hints('int', [0, 0xFFFFFFFF]))
        self.assertIn('boolean_like', compare.hints('int', [0, 1, 1]))
        self.assertIn('minus_one_sentinel_present', compare.hints('float', [6.0, -1.0, -1.0]))

    def test_variant_stems(self):
        self.assertEqual(compare.variant_stem('cyborg_tank_mk2'), 'cyborg_tank')
        self.assertEqual(compare.variant_stem('il_turret_01'), 'il_turret')
        groups = compare.variant_groups(['bug_warrior', 'bug_warrior_elite', 'bug_hunter'])
        self.assertEqual(groups, {'bug_warrior': ['bug_warrior', 'bug_warrior_elite']})


class StrideTests(unittest.TestCase):
    def test_detects_struct_stride(self):
        # 40 elements of a 24-byte struct {u32 hash, float a, float b, u32 small, u32 0, float c}.
        raw = b''.join(struct.pack('<IffIIf', 0xA1B2C3D4 + i * 977, 1.5 + i, 30.0, i % 4, 0, 0.25 * i + 1)
            for i in range(40))
        best = strides.score_strides(raw, min_stride=8, max_stride=96)
        self.assertEqual(best[0]['stride'], 24)
        cols = strides.columns(raw, 24)
        self.assertEqual(cols['elements'], 40)
        by_offset = {c['offset']: c for c in cols['columns']}
        self.assertTrue(by_offset[8]['constant'])
        self.assertEqual(by_offset[8]['floatRange'], [30.0, 30.0])
        self.assertTrue(by_offset[16]['constant'])
        self.assertEqual(by_offset[12]['intRange'], [0, 3])

    def test_runs_find_occupied_elements(self):
        raw = bytes(16) * 2 + struct.pack('<IIII', 5, 1, 2, 3) * 3 + bytes(16) + struct.pack('<IIII', 9, 0, 0, 0)
        self.assertEqual(strides.runs(raw, 16), [(32, 3), (96, 1)])


class GoLibraryTests(unittest.TestCase):
    def test_parses_binary_layout_without_padding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'enum').mkdir()
            (path / 'enum/kind.go').write_text('package enum\n\ntype ThingKind uint32\n')
            (path / 'thing.go').write_text(
                'package datalib\n\n'
                'type Inner struct {\n\tA float32\n\tB uint8\n\t_ [3]uint8\n}\n\n'
                'type ThingComponent struct {\n'
                '\tTurnSpeed float32 `json:"turn_speed"` // degrees per second\n'
                '\tKind enum.ThingKind\n'
                '\tParts [2]Inner\n'
                '\tName stingray.ThinHash\n'
                '}\n\n'
                'type SimpleThingComponent struct {\n\tTurnSpeed float32\n}\n')
            go = golib.GoLibrary(path)
            self.assertNotIn('SimpleThingComponent', go.structs)
            layout = go.layout('ThingComponent')
            self.assertEqual([(f['label'], f['offset'], f['size']) for f in layout],
                [('turn_speed', 0, 4), ('kind', 4, 4), ('parts', 8, 16), ('name', 24, 4)])
            self.assertEqual(go.size_of('ThingComponent'), 28)
            self.assertEqual(layout[0]['comment'], 'degrees per second')

    def test_snake_case(self):
        self.assertEqual(golib.snake('ChargeUpMuzzleFlash'), 'charge_up_muzzle_flash')
        self.assertEqual(golib.snake('HTTPServerID'), 'http_server_id')


class ReportTests(unittest.TestCase):
    def test_confidence_rules(self):
        self.assertEqual(report.confidence({'codeRead': True, 'publishedExact': True}), 'CONFIRMED')
        self.assertEqual(report.confidence({'codeRead': True, 'nameLengthFit': True, 'differential': True}), 'STRONG')
        self.assertEqual(report.confidence({'publishedExact': True, 'nameLengthFit': True, 'differential': True}),
            'STRONG')
        self.assertEqual(report.confidence({'nameLengthFit': True, 'differential': True}), 'PLAUSIBLE')
        self.assertEqual(report.confidence({'codeRead': True}), 'UNKNOWN')
        self.assertEqual(report.confidence({}), 'UNKNOWN')

    def test_candidate_records_name_length_fit(self):
        item = report.candidate('8', 8, 'FP32', 19, 'float', {'a': 50.0}, {'nameLengthFit': True,
            'differential': True}, proposed='vertical_turn_speed')
        self.assertTrue(item['proposedNameLengthFit'])
        self.assertEqual(item['confidence'], 'PLAUSIBLE')
        doc = report.document('t', {}, [item])
        self.assertEqual(doc['counts']['PLAUSIBLE'], 1)
        self.assertEqual(doc['schema'], report.SCHEMA)

    def test_markdown_escapes_pipes(self):
        text = report.markdown_table(['a', 'b'], [['x|y', 1.5]])
        self.assertIn('x\\|y', text)


@unittest.skipUnless(HAVE_DATALIB, 'pinned datalibrary absent')
class PinnedTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scan import tables
        cls.tables = tables.pinned()

    def test_every_component_table_is_enumerated(self):
        names = self.tables.component_names()
        self.assertGreaterEqual(len(names), 250)
        for name in ('TurretComponentData', 'EagleComponentData', 'JumppackComponentData', 'WeaponChargeComponentData',
                'VehicleComponentData', 'HealthComponentData', 'DisplacementComponentData'):
            self.assertIn(name, names)

    def test_turret_layout_matches_reviewed_fingerprint(self):
        # The reviewed TurretComponent members (research_defensive_stratagem_authoring.TURRET_FINGERPRINT).
        turret = self.tables.component('TurretComponentData')
        members = {m.offset: m for m in turret.members()}
        for offset, size, storage, length in ((8, 4, 'FP32', 19), (12, 4, 'FP32', 21), (20, 4, 'FP32', 18),
                (24, 4, 'FP32', 18), (28, 4, 'FP32', 20), (32, 4, 'FP32', 20)):
            self.assertEqual((members[offset].size, members[offset].storage, members[offset].name_length),
                (size, storage, length))
        self.assertEqual(turret.record_size, 76)

    def test_family_compares_sentries_and_clusters_turn_speeds(self):
        resources = {self.tables.label(r): r for r in self.tables.find(r'/(gatling_turret|rocket_turret|'
            r'mortar_turret|turret_machinegun_gpmg|flamethrower_turret|lav_autocannon)$')}
        family = compare.Family(self.tables, 'TurretComponentData', resources)
        self.assertGreaterEqual(len(family.labels), 5)
        values = {row['path']: row for row in family.classify()}
        self.assertEqual(values['12']['values']['gatling_turret'], 80.0)
        self.assertEqual(values['8']['values']['flamethrower_turret'], 140.0)
        partitions = [c['paths'] for c in family.clusters() if c['kind'] == 'same_partition']
        self.assertTrue(any({'0', '4'} <= set(paths) for paths in partitions))
        for row in family.ownership():
            self.assertFalse(row['shared'])

    def test_entity_membership_and_presence(self):
        [jump] = self.tables.find(r'jumppack_backpack/jumppack_backpack$')
        components = self.tables.entity(jump)
        self.assertIn('JumppackComponentData', components)
        self.assertIn('RechargeComponentData', components)
        marks = compare.presence(self.tables, {'jump': jump})
        self.assertIn('JumppackComponentData', marks['common'])

    def test_find_value_reverse_lookup(self):
        hits = compare.find_value(self.tables, 6.0, ('float',), components=['JumppackComponentData'])
        self.assertTrue(any(h['path'] == '156' for h in hits))

    def test_golib_alignment_on_weapon_charge(self):
        aligned = golib.align(self.tables, golib.default_library(), 'WeaponChargeComponent')
        self.assertEqual(aligned['status'], 'aligned')
        self.assertTrue(aligned['sizeMatch'])
        strong = {row['offset']: row['lead']['label'] for row in aligned['members'] if row['strength'] == 'STRONG'}
        self.assertEqual(strong.get(184), 'auto_fire_in_safety')

    def test_settings_rows_by_native_type(self):
        from scan import settings
        view = settings.SettingsView(self.tables)
        self.assertEqual(set(view.kinds()), {'arc', 'beam', 'damage', 'explosion', 'projectile'})
        # ExplosionType 188 (the EMS stun field the custom-payload research uses): type id at +0.
        self.assertEqual(view.decode('explosion', 188)['0'], 188)

    def test_shared_type_report(self):
        result = compare.shared_type_report(self.tables, 'JumppackComponentData')
        self.assertEqual(result['records'], 4)


@unittest.skipUnless(HAVE_SNAPSHOT, 'retained mission snapshot absent')
class CodeImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scan import xref
        cls.image = xref.CodeImage.from_snapshot()

    def test_code_range_and_function_map(self):
        lo, hi = self.image.text
        self.assertEqual(lo, 0x42B0)
        self.assertLess(hi, 0x399C000)
        self.assertGreater(len(self.image.pdata), 100000)
        # The reviewed explosion request (research/event-actions) is a function start.
        self.assertEqual(self.image.root(0x13C0A80), 0x13C0A80)

    def test_reference_scans(self):
        sites = self.image.calls_to(0x13C0A80)
        self.assertTrue(sites)
        for site in sites:
            ins = self.image.insn(site)
            self.assertIn(ins.mnemonic, ('call', 'jmp'))
            self.assertEqual(ins.operands[0].imm, 0x13C0A80)
        # The call index finds exactly what the full reference scan finds.
        for target in (0x13C0A80, 0x4C89C0, 0x11AD240):
            self.assertEqual(self.image.calls_to(target), [ins.address for ins in self.image.references(target)
                if ins.mnemonic in ('call', 'jmp')], hex(target))
        accessors = self.image.global_accessors(0x3326688)   # the health component manager
        self.assertGreater(len(accessors), 50)

    def test_pin_format(self):
        pin = self.image.pin(0x13C0A80, 'explosion request entry')
        self.assertEqual(set(pin) >= {'rva', 'bytes', 'asm', 'role'}, True)

    def test_call_literals_and_dispatchers(self):
        from scan.literals import Attribution, CallLiterals, Dispatcher
        behavior = Dispatcher(self.image, 'behavior', 0x4A0154, 0x2B5)
        ability = Dispatcher(self.image, 'ability', 0x115C784, 0xB33)
        # research/event-actions: BehaviorId 224 runs 0x288360 (the NUX-223 Hellbomb), AbilityId 906 runs 0x10CEA90.
        self.assertIn(224, behavior.handlers[0x288360])
        self.assertIn(906, ability.handlers[0x10CEA90])
        literals = CallLiterals(self.image, entries=set(behavior.stubs) | set(ability.stubs))
        self.assertEqual(literals.literal(0x288825, 'edx'), 242)      # mov edx, 0xf2; ...; call 0x4c89c0
        self.assertEqual(literals.literal(0x10CEB08, 'edx'), 293)
        attribution = Attribution(self.image, [behavior, ability])
        self.assertIn(('behavior', 224), attribution.site(0x288825)[0])
        self.assertIn(('ability', 906), attribution.site(0x10CEB08)[0])


class LiteralTests(unittest.TestCase):
    """scan.literals.register_literal on synthetic blocks (newest instruction first)."""

    def test_immediates_zeroing_and_moves(self):
        from scan.literals import register_literal
        self.assertEqual(register_literal([(8, 5, 'mov', 'edx, 0xf2'), (0, 3, 'mov', 'r8d, 1')], 'edx'), 242)
        self.assertEqual(register_literal([(0, 2, 'xor', 'edx, edx')], 'rdx'), 0)
        self.assertEqual(register_literal([(4, 3, 'mov', 'edx, ebx'), (0, 5, 'mov', 'ebx, 7')], 'edx'), 7)
        self.assertEqual(register_literal([(4, 4, 'lea', 'edx, [r9 + 0x31]'), (0, 3, 'xor', 'r9d, r9d')], 'edx'), 0x31)

    def test_unresolved_values_stay_none(self):
        from scan.literals import register_literal
        self.assertIsNone(register_literal([(0, 4, 'mov', 'edx, dword ptr [rbx + 8]')], 'edx'))
        self.assertIsNone(register_literal([(0, 3, 'add', 'edx, 1')], 'edx'))
        self.assertIsNone(register_literal([], 'edx'))
        # A write of another register never resolves this one.
        self.assertIsNone(register_literal([(0, 5, 'mov', 'ecx, 3')], 'edx'))
        self.assertIsNone(register_literal([(0, 5, 'mov', 'edx, 3')], 'xmm0'))


if __name__ == '__main__':
    unittest.main()
