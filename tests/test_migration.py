"""Game-update migration: synthetic/adversarial builds plus real historical runs.

Every synthetic case builds a source and a target BuildView by hand, so each structural change (addresses moving,
baselines changing, layouts moving, candidates splitting, objects disappearing/appearing, scope and delivery links
changing, renamed strings, hash-only changes) is isolated. The invariants: safe mappings recover automatically,
uncertain writes downgrade to read-only, and no stale write ever survives an apply.
"""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path

from support import ROOT

import build_profile
from migration import build_view as bv, engine, overlay, report, source
import apply_migration

WEAPON, OTHER, NEWCOMER, RACK = 0x1111, 0x2222, 0x3333, 0x4444
PROJECTILE_TYPE, DAMAGE_TYPE, EXPLOSION_TYPE = 10, 20, 30


def member(offset, storage='FP32', size=4, name=8, atom='POD', count=0, type_hash=0):
    return {'offset': offset, 'size': size, 'storage': storage, 'atom': atom, 'count': count, 'nameLength': name,
        'typeHash': type_hash}


def layout(name, size, members):
    return bv.Layout(name, size, members, None)


WEAPON_DATA = layout('WeaponData', 16, [member(0, 'UINT32', name=5), member(4, name=11), member(8, name=12),
    member(12, name=13)])
PROJECTILE_WEAPON = layout('ProjectileWeapon', 8, [member(0, 'UINT32', name=14), member(4, name=9)])
PROJECTILE = layout('Projectile', 160, [member(0, 'UINT32', name=4), member(32, name=8), member(60, 'UINT32', name=6),
    member(144, 'UINT32', name=15), member(156, 'UINT32', name=15)])
DAMAGE = layout('Damage', 16, [member(0, 'UINT32', name=4), member(8, 'INT32', name=15)])
EXPLOSION = layout('Explosion', 24, [member(0, 'UINT32', name=4), member(4, 'UINT32', name=6), member(16, name=12)])
RACK_LAYOUT = layout('HellpodRack', 560, [member(0, 'STRUCT', 512, 5, 'INLINE_ARRAY', 8, 0xAB),
    member(556, 'UINT32', name=10)])


def pack(fmt, *values, size=None):
    data = struct.pack(fmt, *values)
    return data + bytes((size or len(data)) - len(data))


def row(record_type, size, **fields):
    data = bytearray(size)
    struct.pack_into('<I', data, 0, record_type)
    for offset, (fmt, value) in fields.items():
        struct.pack_into(fmt, data, int(offset[1:]), value)
    return bytes(data)


class Build:
    """A minimal two-weapon build. Tests mutate copies to model one game update at a time."""

    def __init__(self, exe='A' * 64, dll='B' * 64):
        self.exe, self.dll = exe, dll
        self.components = {
            'WeaponDataComponentData': {'layout': WEAPON_DATA, 'owners': {WEAPON: (0, 0), OTHER: (1, 1)},
                'records': [pack('<Ifff', 1, 0.5, 2.0, 3.0), pack('<Ifff', 2, 0.25, 1.0, 1.0)]},
            'ProjectileWeaponComponentData': {'layout': PROJECTILE_WEAPON, 'owners': {WEAPON: (0, 0), OTHER: (1, 1)},
                'records': [pack('<If', PROJECTILE_TYPE, 600.0), pack('<If', PROJECTILE_TYPE + 1, 700.0)]},
            'HellpodRackComponentData': {'layout': RACK_LAYOUT, 'owners': {RACK: (0, 0)},
                'records': [pack('<Q', WEAPON, size=556) + pack('<I', 1)]}}
        self.projectile = {PROJECTILE_TYPE: row(PROJECTILE_TYPE, 160, o32=('<f', 900.0), o60=('<I', DAMAGE_TYPE),
                o144=('<I', EXPLOSION_TYPE), o156=('<I', EXPLOSION_TYPE)),
            PROJECTILE_TYPE + 1: row(PROJECTILE_TYPE + 1, 160, o32=('<f', 500.0), o60=('<I', DAMAGE_TYPE + 1))}
        self.damage = {DAMAGE_TYPE: row(DAMAGE_TYPE, 16, o8=('<i', 100)), DAMAGE_TYPE + 1: row(DAMAGE_TYPE + 1, 16,
            o8=('<i', 50)), DAMAGE_TYPE + 2: row(DAMAGE_TYPE + 2, 16, o8=('<i', 75))}
        self.explosion = {EXPLOSION_TYPE: row(EXPLOSION_TYPE, 24, o4=('<I', DAMAGE_TYPE + 2), o16=('<f', 5.0))}
        self.deltas = {0x7777: {'hashmapSlot': 0, 'settingsIndex': 0, 'entries': [
            {'component': 5, 'offset': 4, 'size': 4, 'dataOffset': 100, 'bytes': pack('<f', 0.75)}]}}
        self.stratagems = None
        self.paths = {}
        self.extra_entities = []

    def view(self):
        view = bv.BuildView()
        view.build = {'exeSha256': self.exe, 'gameDllSha256': self.dll}
        view.library = None
        view._layouts = {0xAB: layout('RackSlot', 64, [member(0, 'UINT64', 8, name=4), member(8, 'UINT32', name=9)])}
        entities = set(self.extra_entities)
        for name, spec in self.components.items():
            view.components[name] = bv.ComponentTable(name, 5 if name == 'WeaponDataComponentData' else 9,
                spec['layout'], dict(spec['owners']), list(spec['records']), spec['layout'].size)
            view.delta_component_index[5 if name == 'WeaponDataComponentData' else 9] = name
            entities.update(spec['owners'])
        view.entity_rows = {resource: index for index, resource in enumerate(sorted(entities))}
        for kind, rows, lay, type_hash in (('projectile', self.projectile, PROJECTILE, 0x100),
                ('damage', self.damage, DAMAGE, 0x200), ('explosion', self.explosion, EXPLOSION, 0x300)):
            entries = [(index, record_type, data) for index, (record_type, data) in enumerate(rows.items())]
            view.settings[kind] = bv.SettingsKind(kind, [bv.SettingsTable(kind, type_hash, 0, lay, entries)])
        view.deltas = copy.deepcopy(self.deltas)
        view.stratagems = copy.deepcopy(self.stratagems)
        view.paths = dict(self.paths)
        return view


def fields():
    """The previous release's normalized fields for the synthetic build."""
    component = lambda key, name, index, row_, offset, storage, baseline, resource=WEAPON, count=1: source._record(
        'player_weapon_authoring', key, 'Rifle', key.split(':')[-1], {'kind': 'component', 'component': name,
            'recordIndex': index, 'indexRow': row_, 'ownerCount': count, 'offset': offset, 'storage': storage,
            'width': 4, 'resource': resource}, baseline, True, False,
        {'path': ['weapons', 'Rifle', 'fields', len(KEYS)], 'guard': {'semanticFieldId': key.split(':')[-1]}})
    settings = lambda key, kind, record_type, row_, offset, storage, baseline: source._record(
        'player_weapon_authoring', key, 'Rifle', key.split(':')[-1], {'kind': 'settings', 'settings': kind,
            'recordType': record_type, 'group': 0, 'row': row_, 'offset': offset, 'storage': storage, 'width': 4,
            'phase': None, 'anchors': [WEAPON]}, baseline, True, True,
        {'path': ['weapons', 'Rifle', 'fields', len(KEYS)], 'guard': {'semanticFieldId': key.split(':')[-1]}})
    items = []
    for build in (
            lambda: component('w:Rifle:weapon.sway', 'WeaponDataComponentData', 0, 0, 4, 'f32', 0.5),
            lambda: component('w:Rifle:weapon.spread', 'WeaponDataComponentData', 0, 0, 8, 'f32', 2.0),
            lambda: component('w:Rifle:weapon.fire_rate', 'ProjectileWeaponComponentData', 0, 0, 4, 'f32', 600.0),
            lambda: settings('w:Rifle:projectile.velocity', 'projectile', PROJECTILE_TYPE, 0, 32, 'f32', 900.0),
            lambda: settings('w:Rifle:damage.durable', 'damage', DAMAGE_TYPE, 0, 8, 'i32', 100),
            lambda: settings('w:Rifle:explosion.radius', 'explosion', EXPLOSION_TYPE, 0, 16, 'f32', 5.0)):
        record = build()
        KEYS.append(record['key'])
        items.append(record)
    attachment = source._record('attachment_authoring', 'att:mag:weapon.sway', 'Drum', 'attachment.sway',
        {'kind': 'delta', 'resource': 0x7777, 'component': 'WeaponDataComponentData', 'componentIndex': 5,
            'componentOffset': 4, 'dataOffset': 100, 'storage': 'f32', 'width': 4}, 0.75, True, True,
        {'path': ['attachments', 'mag', 'fields', 'attachment.sway'], 'guard': {'instanceKey': 'att:mag:weapon.sway'}})
    pod = source._record('pod_payload_authoring', 'pod:Rifle pod:slot:1', 'Rifle pod', 'payload.entity',
        {'kind': 'component', 'component': 'HellpodRackComponentData', 'recordIndex': 0, 'indexRow': 0,
            'ownerCount': 1, 'offset': 0, 'storage': 'u64', 'width': 8, 'resource': RACK}, WEAPON, True, False,
        {'path': ['racks', 'Rifle pod'], 'guard': {'semanticId': 'pod'}, 'rackLevel': True, 'slot': '1'})
    code = source._record('booster_authoring', 'booster:x:tuning', 'Booster', 'booster.scale',
        {'kind': 'code', 'code': 'booster_table', 'row': 1, 'offset': 8, 'storage': 'f32', 'width': 4}, 1.0, True,
        False, {'path': ['boosters', 'Booster', 'targets', 'tuning', 'fields', 'booster.scale'], 'guard': {}})
    return items + [attachment, pod, code]


KEYS = []


def migrate(source_build, target_build, relationships=()):
    KEYS.clear()
    release = {'fields': fields(), 'relationships': list(relationships)}
    result = engine.run(source_build.view(), target_build.view(), release)
    return result, {field['key']: field for field in result['fields']}


class SyntheticMigrationTests(unittest.TestCase):
    def assertState(self, fields_, key, state):
        self.assertEqual(fields_[key]['state'], state, fields_[key]['reasons'])

    def test_identical_build_is_exact_everywhere(self):
        result, by_key = migrate(Build(), Build())
        self.assertEqual({field['state'] for field in result['fields']}, {'EXACT'})
        self.assertEqual(report.unsafe_stale_writes(result['fields']), 0)

    def test_moved_records_and_rows_recover_with_new_coordinates(self):
        target = Build()
        spec = target.components['WeaponDataComponentData']
        spec['records'] = [spec['records'][1], spec['records'][0]]
        spec['owners'] = {WEAPON: (1, 7), OTHER: (0, 3)}
        target.projectile = {PROJECTILE_TYPE + 1: target.projectile[PROJECTILE_TYPE + 1],
            PROJECTILE_TYPE: target.projectile[PROJECTILE_TYPE]}
        _, by_key = migrate(Build(), target)
        sway = by_key['w:Rifle:weapon.sway']
        self.assertEqual(sway['state'], 'MOVED')
        self.assertEqual((sway['target']['recordIndex'], sway['target']['indexRow']), (1, 7))
        self.assertEqual(report.decide(sway)['action'], 'rebind')
        velocity = by_key['w:Rifle:projectile.velocity']
        self.assertEqual((velocity['state'], velocity['target']['row']), ('MOVED', 1))
        self.assertEqual(velocity['confidence'], 'structural')

    def test_baseline_change_records_old_and_new(self):
        target = Build()
        target.components['WeaponDataComponentData']['records'][0] = pack('<Ifff', 1, 0.5, 2.5, 3.0)
        _, by_key = migrate(Build(), target)
        spread = by_key['w:Rifle:weapon.spread']
        self.assertEqual(spread['state'], 'BASELINE_CHANGED')
        self.assertEqual((spread['baseline']['old'], spread['baseline']['new']), (2.0, 2.5))
        self.assertEqual(report.decide(spread)['action'], 'rebind')
        self.assertState(by_key, 'w:Rifle:weapon.sway', 'EXACT')

    def test_layout_move_is_recovered_by_member_signature(self):
        target = Build()
        grown = layout('WeaponData', 20, [member(0, 'UINT32', name=5), member(4, 'UINT32', name=21),
            member(8, name=11), member(12, name=12), member(16, name=13)])
        spec = target.components['WeaponDataComponentData']
        spec['layout'] = grown
        spec['records'] = [pack('<IIfff', 1, 9, 0.5, 2.0, 3.0), pack('<IIfff', 2, 9, 0.25, 1.0, 1.0)]
        _, by_key = migrate(Build(), target)
        sway = by_key['w:Rifle:weapon.sway']
        self.assertEqual(sway['state'], 'LAYOUT_CHANGED')
        self.assertEqual(sway['target']['offset'], 8)
        self.assertEqual(report.decide(sway)['action'], 'rebind')

    def test_unprovable_layout_move_downgrades(self):
        target = Build()
        # Two new members share the moved member's signature: counting cannot prove which is which.
        ambiguous = layout('WeaponData', 24, [member(0, 'UINT32', name=5), member(4, name=11), member(8, name=11),
            member(12, 'UINT32', name=3), member(16, name=12), member(20, name=13)])
        spec = target.components['WeaponDataComponentData']
        spec['layout'] = ambiguous
        spec['records'] = [pack('<IffIff', 1, 0.5, 0.5, 0, 2.0, 3.0), pack('<IffIff', 2, 0.2, 0.2, 0, 1.0, 1.0)]
        _, by_key = migrate(Build(), target)
        sway = by_key['w:Rifle:weapon.sway']
        self.assertEqual(sway['state'], 'AMBIGUOUS')
        self.assertEqual(report.decide(sway)['action'], 'readonly')
        self.assertEqual(len(sway['review']['candidates']), 2)
        self.assertTrue(sway['review']['distinguishingEvidence'])

    def test_member_type_change_blocks(self):
        target = Build()
        changed = layout('WeaponData', 16, [member(0, 'UINT32', name=5), member(4, 'UINT32', name=11),
            member(8, name=12), member(12, name=13)])
        target.components['WeaponDataComponentData']['layout'] = changed
        _, by_key = migrate(Build(), target)
        self.assertState(by_key, 'w:Rifle:weapon.sway', 'BLOCKED')
        self.assertState(by_key, 'w:Rifle:weapon.spread', 'EXACT')

    def test_one_candidate_becoming_two_is_ambiguous(self):
        target = Build()
        # Impact and expiry used to share one explosion row; now they point at two different rows.
        target.projectile[PROJECTILE_TYPE] = row(PROJECTILE_TYPE, 160, o32=('<f', 900.0), o60=('<I', DAMAGE_TYPE),
            o144=('<I', EXPLOSION_TYPE), o156=('<I', EXPLOSION_TYPE + 1))
        target.explosion[EXPLOSION_TYPE + 1] = row(EXPLOSION_TYPE + 1, 24, o4=('<I', DAMAGE_TYPE + 2),
            o16=('<f', 5.0))
        _, by_key = migrate(Build(), target)
        radius = by_key['w:Rifle:explosion.radius']
        self.assertEqual(radius['state'], 'AMBIGUOUS')
        self.assertEqual({c['recordType'] for c in radius['review']['candidates']},
            {EXPLOSION_TYPE, EXPLOSION_TYPE + 1})
        self.assertEqual(report.decide(radius)['action'], 'readonly')

    def test_shared_component_record_blocks_when_scope_widens(self):
        target = Build()
        target.components['WeaponDataComponentData']['owners'][OTHER] = (0, 1)
        _, by_key = migrate(Build(), target)
        sway = by_key['w:Rifle:weapon.sway']
        self.assertEqual(sway['state'], 'BLOCKED')
        self.assertIn('scope', sway['reasons'][0]['reason'])
        self.assertEqual(sway['review']['candidates'][0]['addedOwners'], [engine.hexid(OTHER)])

    def test_shared_settings_row_blocks_when_a_new_consumer_reaches_it(self):
        target = Build()
        target.components['ProjectileWeaponComponentData']['records'][1] = pack('<If', PROJECTILE_TYPE, 700.0)
        _, by_key = migrate(Build(), target)
        self.assertState(by_key, 'w:Rifle:projectile.velocity', 'BLOCKED')

    def test_disappearing_object_is_lost_with_candidates(self):
        target = Build()
        for spec in target.components.values():
            if WEAPON in spec['owners']:
                spec['owners'][NEWCOMER] = spec['owners'].pop(WEAPON)
        target.components['HellpodRackComponentData']['records'][0] = pack('<Q', NEWCOMER, size=556) + pack('<I', 1)
        _, by_key = migrate(Build(), target)
        sway = by_key['w:Rifle:weapon.sway']
        self.assertEqual(sway['state'], 'LOST')
        self.assertEqual(sway['review']['candidates'][0]['resource'], engine.hexid(NEWCOMER))
        self.assertTrue(sway['review']['candidates'][0]['identicalRecord'])
        self.assertEqual(report.decide(sway)['action'], 'readonly')
        self.assertState(by_key, 'w:Rifle:projectile.velocity', 'LOST')

    def test_new_objects_appear_as_unnamed_candidates(self):
        target = Build()
        for name in ('WeaponDataComponentData', 'ProjectileWeaponComponentData'):
            spec = target.components[name]
            spec['owners'][NEWCOMER] = (len(spec['records']), 9)
            spec['records'].append(spec['records'][0])
        target.damage[99] = row(99, 16, o8=('<i', 1))
        result, _ = migrate(Build(), target)
        entities = result['new']['entities']
        self.assertEqual([(e['resource'], e['category']) for e in entities], [(engine.hexid(NEWCOMER), 'weapon')])
        self.assertIn('unreviewed', entities[0]['status'])
        self.assertEqual([s['recordType'] for s in result['new']['settings']], [99])

    def test_attachment_delta_changes(self):
        target = Build()
        target.deltas[0x7777]['entries'][0]['dataOffset'] = 180
        _, by_key = migrate(Build(), target)
        self.assertState(by_key, 'att:mag:weapon.sway', 'MOVED')
        del target.deltas[0x7777]
        target.deltas[0x8888] = copy.deepcopy(Build().deltas[0x7777])
        link = {'kind': 'attachment_compatibility', 'key': 'compat', 'object': 'Rifle',
            'blocks': [['attachment_authoring', 'Drum']], 'attachment': 0x7777, 'weapons': [WEAPON],
            'relationship': 'native_resource_default'}
        result, by_key = migrate(Build(), target, [link])
        self.assertState(by_key, 'att:mag:weapon.sway', 'LOST')
        self.assertEqual(by_key['att:mag:weapon.sway']['review']['candidates'][0]['resource'], engine.hexid(0x8888))
        self.assertEqual(result['relationships'][0]['state'], 'BROKEN')

    def test_delivery_link_change_blocks_dependent_fields(self):
        link = {'kind': 'rack_delivers', 'key': 'rack', 'object': 'Rifle pod',
            'blocks': [['pod_payload_authoring', 'Rifle pod']], 'rack': RACK, 'item': WEAPON}
        result, by_key = migrate(Build(), Build(), [link])
        self.assertEqual(result['relationships'][0]['state'], 'INTACT')
        target = Build()
        target.components['HellpodRackComponentData']['records'][0] = pack('<Q', OTHER, size=556) + pack('<I', 1)
        result, by_key = migrate(Build(), target, [link])
        self.assertEqual(result['relationships'][0]['state'], 'BROKEN')
        self.assertState(by_key, 'pod:Rifle pod:slot:1', 'BLOCKED')

    def test_stratagem_payload_change_is_broken_only_when_provable(self):
        link = {'kind': 'stratagem_rack', 'key': 'call-in', 'object': 'Rifle',
            'blocks': [['pod_payload_authoring', 'Rifle pod']], 'stratagemId': 42, 'rack': RACK}
        result, by_key = migrate(Build(), Build(), [link])
        self.assertEqual(result['relationships'][0]['state'], 'UNCHECKED')
        self.assertState(by_key, 'pod:Rifle pod:slot:1', 'EXACT')
        before, after = Build(), Build()
        before.stratagems = {42: {'group': 0, 'row': 1, 'payloads': [engine.hexid(RACK)], 'bytes': ''}}
        after.stratagems = {42: {'group': 0, 'row': 1, 'payloads': [engine.hexid(OTHER)], 'bytes': ''}}
        result, by_key = migrate(before, after, [link])
        self.assertEqual(result['relationships'][0]['state'], 'BROKEN')
        self.assertState(by_key, 'pod:Rifle pod:slot:1', 'BLOCKED')

    def test_renamed_display_strings_do_not_affect_identity(self):
        before, after = Build(), Build()
        before.paths = {WEAPON: 'content/weapons/rifle'}
        after.paths = {WEAPON: 'content/weapons/rifle_renamed'}
        result, _ = migrate(before, after)
        self.assertEqual({field['state'] for field in result['fields']}, {'EXACT'})

    def test_hash_change_with_preserved_structures(self):
        result, by_key = migrate(Build(), Build(exe='C' * 64, dll='D' * 64))
        self.assertFalse(result['sameGameDll'])
        self.assertState(by_key, 'w:Rifle:weapon.sway', 'EXACT')
        self.assertState(by_key, 'w:Rifle:damage.durable', 'EXACT')
        # game.dll-resident tables cannot be re-proven from data tables: never carried forward.
        self.assertState(by_key, 'booster:x:tuning', 'UNCHECKED')
        self.assertEqual(report.decide(by_key['booster:x:tuning'])['action'], 'readonly')

    def test_renumbered_type_without_chain_is_blocked(self):
        before, after = Build(), Build()
        # Type-only identity (no anchors): the row under the old type number now holds different content.
        after.damage[DAMAGE_TYPE + 1] = row(DAMAGE_TYPE + 1, 16, o8=('<i', 51))
        KEYS.clear()
        release = {'fields': fields(), 'relationships': []}
        other = source._record('stratagem_authoring', 's:x:damage', 'Strike', 'damage.durable',
            {'kind': 'settings', 'settings': 'damage', 'recordType': DAMAGE_TYPE + 1, 'group': 0, 'row': 1,
                'offset': 8, 'storage': 'i32', 'width': 4, 'phase': None, 'anchors': []}, 50, True, False,
            {'path': ['stratagems', 'Strike', 'fields', 0], 'guard': {}})
        release['fields'].append(other)
        # OTHER's chain reaches this row in the source build, so identity follows OTHER, not the type number.
        result = engine.run(before.view(), after.view(), release)
        field = next(f for f in result['fields'] if f['key'] == 's:x:damage')
        self.assertEqual((field['state'], field['confidence']), ('BASELINE_CHANGED', 'structural'))
        after.components['ProjectileWeaponComponentData']['owners'].pop(OTHER)
        result = engine.run(before.view(), after.view(), release)
        field = next(f for f in result['fields'] if f['key'] == 's:x:damage')
        self.assertEqual(field['state'], 'LOST')

    def test_decisions_never_carry_unproven_writes(self):
        target = Build()
        target.components['WeaponDataComponentData']['owners'][OTHER] = (0, 1)
        result, by_key = migrate(Build(), target)
        self.assertEqual(report.unsafe_stale_writes(result['fields']), 0)
        forged = dict(by_key['w:Rifle:weapon.sway'], state='EXACT')
        forged_target = dict(forged, target=None, state='MOVED', confidence='structural')
        self.assertEqual(report.decide(forged)['action'], 'carry')
        self.assertEqual(report.unsafe_stale_writes([forged_target]), 0)   # no target -> read-only
        self.assertEqual(report.decide(forged_target)['action'], 'readonly')


class ApplyTests(unittest.TestCase):
    def tables(self):
        return {'player_weapon_authoring': {'weapons': {'Rifle': {'fields': [
            {'semanticFieldId': 'weapon.sway', 'editable': True, 'currentDefault': 0.5,
                'backing': {'kind': 'component', 'component': 'WeaponDataComponentData', 'recordIndex': 0,
                    'indexRow': 0, 'ownerCount': 1, 'offset': 4}},
            {'semanticFieldId': 'weapon.spread', 'editable': True, 'currentDefault': 2.0,
                'backing': {'kind': 'component', 'component': 'WeaponDataComponentData', 'recordIndex': 0,
                    'indexRow': 0, 'ownerCount': 1, 'offset': 8}}]}}}}

    def plan(self, target_build):
        KEYS.clear()
        result = engine.run(Build().view(), target_build.view(), {'fields': fields()[:2], 'relationships': []})
        decisions = {f['key']: dict(report.decide(f), state=f['state'], domain=f['domain'], locator=f['locator'],
            target=f['target'], baseline=f['baseline'], editable=f['previouslyEditable'])
            for f in result['fields'] if f['state'] != 'EXACT'}
        return {'decisions': decisions, 'exact': [f['key'] for f in result['fields'] if f['state'] == 'EXACT']}

    def apply(self, plan, tables):
        after = copy.deepcopy(tables)
        for key, decision in plan['decisions'].items():
            item = apply_migration.field_patch(key, decision, tables, 'TARGET')
            if item:
                overlay.patch(decision['domain'], after[decision['domain']], [item])
        return after

    def test_rebind_and_downgrade_leave_no_stale_writes(self):
        target = Build()
        grown = layout('WeaponData', 20, [member(0, 'UINT32', name=5), member(4, 'UINT32', name=21),
            member(8, name=11), member(12, name=12), member(16, name=13)])
        spec = target.components['WeaponDataComponentData']
        spec['layout'], spec['owners'] = grown, {WEAPON: (0, 3), OTHER: (0, 4)}
        spec['records'] = [pack('<IIfff', 1, 9, 0.5, 2.5, 3.0)]
        plan = self.plan(target)
        after = self.apply(plan, self.tables())
        sway, spread = after['player_weapon_authoring']['weapons']['Rifle']['fields']
        # Scope widened to OTHER: both fields downgrade; nothing keeps the stale offsets writable.
        self.assertFalse(sway['editable'])
        self.assertIn('Build migration to TARGET', sway['reason'])
        self.assertFalse(spread['editable'])
        self.assertEqual(apply_migration.verify(plan, after, 'TARGET'), [])

    def test_rebind_moves_coordinates_and_default(self):
        target = Build()
        grown = layout('WeaponData', 20, [member(0, 'UINT32', name=5), member(4, 'UINT32', name=21),
            member(8, name=11), member(12, name=12), member(16, name=13)])
        spec = target.components['WeaponDataComponentData']
        spec['layout'], spec['owners'] = grown, {WEAPON: (1, 3), OTHER: (0, 4)}
        spec['records'] = [pack('<IIfff', 2, 9, 0.25, 1.0, 1.0), pack('<IIfff', 1, 9, 0.5, 2.5, 3.0)]
        plan = self.plan(target)
        after = self.apply(plan, self.tables())
        sway, spread = after['player_weapon_authoring']['weapons']['Rifle']['fields']
        self.assertTrue(sway['editable'])
        self.assertEqual((sway['backing']['recordIndex'], sway['backing']['indexRow'], sway['backing']['offset']),
            (1, 3, 8))
        self.assertEqual((spread['backing']['offset'], spread['currentDefault']), (12, 2.5))
        self.assertEqual(apply_migration.verify(plan, after, 'TARGET'), [])
        # A table that was not rebound is caught as a stale write.
        self.assertTrue(apply_migration.verify(plan, self.tables(), 'TARGET'))

    def test_overlay_is_build_keyed_and_guarded(self):
        build = overlay.runtime_build()
        table = self.tables()['player_weapon_authoring']
        patch = {'key': 'k', 'path': ['weapons', 'Rifle', 'fields', 0], 'guard': {'semanticFieldId': 'weapon.sway',
            'backing.offset': 4}, 'set': {'backing.offset': 8}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'overlay.json'
            path.write_text(json.dumps({'target': {'exeSha256': 'F' * 64, 'gameDllSha256': build['gameDllSha256']},
                'patches': {'player_weapon_authoring': [patch]}}))
            self.assertIs(overlay.apply('player_weapon_authoring', table, path), table)
            self.assertEqual(table['weapons']['Rifle']['fields'][0]['backing']['offset'], 4)
            path.write_text(json.dumps({'target': build, 'patches': {'player_weapon_authoring': [patch]}}))
            overlay.apply('player_weapon_authoring', table, path)
            self.assertEqual(table['weapons']['Rifle']['fields'][0]['backing']['offset'], 8)
            with self.assertRaisesRegex(ValueError, 'guard'):
                overlay.apply('player_weapon_authoring', table, path)
        self.assertFalse(overlay.OVERLAY.exists(), 'a build-migration overlay must not ship in a release')


class GeneratorHookTests(unittest.TestCase):
    def test_generators_consume_an_overlay_for_the_current_build_only(self):
        import generate_attachment_authoring as generator
        tables = source.load_tables(source.resolve_ref('current'))
        semantic, attachment = sorted(tables['attachment_authoring']['attachments'].items())[0]
        field_id, field = sorted(attachment['fields'].items())[0]
        patch = {'key': field['instanceKey'], 'path': ['attachments', semantic, 'fields', field_id],
            'guard': {'instanceKey': field['instanceKey']}, 'set': {'editable': False, 'reason': 'test downgrade'}}
        original = overlay.OVERLAY
        with tempfile.TemporaryDirectory() as folder:
            try:
                overlay.OVERLAY = Path(folder) / 'build_migration.json'
                overlay.OVERLAY.write_text(json.dumps({'target': dict(overlay.runtime_build(), buildId='X'),
                    'patches': {'attachment_authoring': [patch]}}))
                with self.assertRaisesRegex(RuntimeError, 'attachment_authoring.lua'):
                    generator.generate(check=True)
                overlay.OVERLAY.write_text(json.dumps({'target': {'exeSha256': '0' * 64, 'gameDllSha256': '0' * 64},
                    'patches': {'attachment_authoring': [patch]}}))
                generator.generate(check=True)       # another build's overlay is ignored
            finally:
                overlay.OVERLAY = original


class CacheTests(unittest.TestCase):
    def test_cache_key_tracks_capture_and_extractor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.hd2snap'
            header = b'HD2SNAP\0' + struct.pack('<II', 1, 32) + bytes(16)
            path.write_bytes(header + b'body')
            first = bv.snapshot_cache_key(path)
            path.write_bytes(header[:-1] + b'\1' + b'body')
            self.assertNotEqual(bv.snapshot_cache_key(path), first)
            path.write_bytes(header + b'body!')
            self.assertNotEqual(bv.snapshot_cache_key(path), first)
            original = bv.EXTRACTOR_VERSION
            try:
                bv.EXTRACTOR_VERSION = original + 1
                path.write_bytes(header + b'body')
                self.assertNotEqual(bv.snapshot_cache_key(path), first)
            finally:
                bv.EXTRACTOR_VERSION = original


OLD = 'D8E23968D141'


def available(build_id=None, snapshot=None):
    try:
        if snapshot:
            return (build_profile.snapshot_directory() / snapshot).is_file() and build_profile.SNAPSHOT.is_file()
        return (build_profile.datalibrary(build_id) / bv.TYPELIB_FILE).is_file() and build_profile.SNAPSHOT.is_file()
    except (KeyError, FileNotFoundError):
        return False


class HistoricalMigrationTests(unittest.TestCase):
    """Real builds. Skipped where the retained snapshots/datalibraries are not present."""

    @classmethod
    def setUpClass(cls):
        cls.release = None

    def release_for(self, view):
        return source.load_release('current', view)

    @unittest.skipUnless(available(snapshot='F5FEE03DCFDB-20260927T155654Z.hd2snap'), 'retained snapshots absent')
    def test_same_build_snapshot_is_exact(self):
        view = bv.from_snapshot(build_profile.SNAPSHOT)
        target = bv.from_snapshot(build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260927T155654Z.hd2snap')
        result = engine.run(view, target, self.release_for(view))
        states = {field['state'] for field in result['fields']}
        self.assertEqual(states, {'EXACT'})
        self.assertFalse([r for r in result['relationships'] if r['state'] in ('BROKEN', 'AMBIGUOUS')])

    @unittest.skipUnless(available(OLD), 'historical datalibrary absent')
    def test_cross_build_recovers_structurally_and_never_carries_stale_writes(self):
        view = bv.from_snapshot(build_profile.SNAPSHOT)
        profile = build_profile.build(OLD)
        target = bv.from_datalibrary(build_profile.datalibrary(OLD), {'exeSha256': profile['exeSha256'],
            'gameDllSha256': profile['gameDllSha256']})
        self.assertEqual(target.build['typelibMemberFormat'], 52)
        result = engine.run(view, target, self.release_for(view))
        by_key = {field['key']: field for field in result['fields']}
        self.assertEqual(report.unsafe_stale_writes(result['fields']), 0)
        # WeaponDataComponent shrank by 16 bytes in the older build: members before the change keep their
        # offsets, members after it move and are proven by signature/alignment.
        sway = by_key['player_weapon:AR-23 Liberator:weapon.sway']
        self.assertEqual((sway['state'], sway['target']['offset']), ('LAYOUT_CHANGED', sway['source']['offset'] - 16))
        self.assertEqual(report.decide(sway)['action'], 'rebind')
        # A weapon that does not exist in the older build is LOST, never guessed.
        self.assertEqual({f['state'] for k, f in by_key.items() if k.startswith('player_weapon:AR-11 Arbitrator:')},
            {'LOST'})
        # game.dll-resident booster tables of a different game.dll are never carried forward.
        self.assertTrue(all(report.decide(f)['action'] == 'readonly' for f in result['fields']
            if f['source']['kind'] == 'code'))
        summary = report.summarize(result, {'extractorVersion': bv.EXTRACTOR_VERSION, 'source': {}, 'target': {},
            'cache': None})
        self.assertGreater(summary['confidence']['recoveredAutomaticallyPercent'], 70)


class BuildProfileTests(unittest.TestCase):
    def test_active_build_matches_runtime_profile(self):
        active = build_profile.ACTIVE
        runtime = overlay.runtime_build()
        self.assertEqual((active['exeSha256'], active['gameDllSha256']),
            (runtime['exeSha256'], runtime['gameDllSha256']))
        self.assertEqual(build_profile.BUILD_ID, active['exeSha256'][:12])
        self.assertTrue(active['referenceSnapshot'].startswith(build_profile.BUILD_ID + '-'))
        self.assertTrue(active['supportedByRelease'])

    def test_scripts_do_not_hard_code_the_reference_snapshot(self):
        offenders = []
        for path in sorted((ROOT / 'scripts').glob('*.py')):
            if path.name == 'build_profile.py':
                continue
            text = path.read_text(encoding='utf-8')
            if "snapshots\\\\F5FEE03DCFDB-20260926T222226Z.hd2snap')" in text or \
                    "SNAPSHOT = Path(r'" in text and 'F5FEE03DCFDB-20260926T222226Z' in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_every_build_has_complete_fingerprints(self):
        for build_id, item in build_profile.load()['builds'].items():
            self.assertEqual(build_id, item['exeSha256'][:12])
            self.assertEqual(len(item['exeSha256']), 64)
            self.assertEqual(len(item['gameDllSha256']), 64)
            self.assertEqual(len(item['datalibrary']['typelibSha256']), 64)

    def test_history_fingerprints_cover_the_release(self):
        path = ROOT / 'research/build-history' / (build_profile.BUILD_ID + '.json')
        history = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(history['exeSha256'], build_profile.ACTIVE['exeSha256'])
        self.assertGreater(len(history['fields']), 7000)
        self.assertTrue(all(value is None or value.split('|')[0] in ('component', 'settings', 'delta', 'stratagem',
            'code') for value in history['fields'].values()))


if __name__ == '__main__':
    unittest.main()
