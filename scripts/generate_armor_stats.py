"""Generate domains/armor_stats.lua: where a Helldiver armor's ARMOR RATING, SPEED and STAMINA REGEN come from, as
domains/armor_stats_writes.lua and runtime/armor_stats.lua read and write them (research/armor-stats-F5FEE03DCFDB.json,
scripts/research_armor_stats.py, research/docs/armor-stats-F5FEE03DCFDB.md; the kit names and the passives' armor
rows from research/armor-names-F5FEE03DCFDB.json).

The output carries: the three per-weight tables and the player damage curve (game.dll RVAs and vanilla bytes), the
kit / body / piece layouts the pins prove, the customization manager and avatar manager members, every armor kit of
the game with its vanilla piece weight per slot and the research's vanilla stats, the passives' armor-rating rows,
every instruction pin of the research plus the slot-lookup pins this feature adds (re-proven before every read and
write), and the reviewed write ranges. Checked here: the research is unchanged in every retained snapshot, every pin is
hex, the layouts are the ones the pins prove, the tables and the curve are the pinned bytes, every kit's census row
joins its name row, and each kit's vanilla piece weights are the ones the research reports.

The same build also writes sdk/ArmorStatsCapabilities.json, the public catalog ModBuilder and other SDK tools read: the
class tables, the damage curve, the display formulas, the passives' armor bonuses, every armor kit with its vanilla
piece weights and stats, one field instance per writable value (as domains/armor_stats_writes.lua describes it), the
per-player members and the evidence. No address, pin, offset or layout is published.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/armor-stats-F5FEE03DCFDB.json'
NAMES = ROOT / 'research/armor-names-F5FEE03DCFDB.json'
OUTPUT = 'domains/armor_stats.lua'
SLOTS = ['helmet', 'cape', 'torso', 'hips', 'left_leg', 'right_leg', 'left_arm', 'right_arm', 'left_shoulder',
    'right_shoulder']      # filediver CustomizationKitSlot (lead names); the game tests slot 0, 2 and 2..9 except 3
WEIGHTS = ['light', 'medium', 'heavy']
ARMOR_KEY = 'AFAE3B47'     # the armor-rating key every armor value reader passes to PassiveValue 0x11DA090
CUSTOMIZATION = {'globalRva': 0x33264F8, 'kits': 0x00, 'kitCount': 0x08}
KIT = {'id': 0x00, 'passive': 0x1C, 'type': 0x28, 'bodies': 0x30, 'bodyCount': 0x38, 'read': 0x40}
BODY = {'stride': 0x18, 'type': 0x00, 'pieces': 0x08, 'count': 0x10}
PIECE = {'stride': 0x60, 'slot': 0x08, 'type': 0x0C, 'weight': 0x10}
AVATAR = {'globalRva': 0x3326D20, 'map': 0xF8, 'staminaFactor': 0x53E900, 'staminaStride': 0x1238,
    'armorModifier': 0x546AC4, 'armorStride': 0x1B8, 'maxSlots': 16}
# The avatar manager's entity -> slot map, read by the stamina writer (0x877AB0), the hit's armor reader (0x12A15E0)
# and the armor modifier setter (0x833C50), and the 0x1B8 stride of the armor modifier. Not pinned by the research;
# added here from the same game.dll image and proven in all seven retained snapshots by
# scripts/validate_armor_stats_snapshot.py before any per-player read or write relies on them.
SLOT_PINS = [
    (0x877FC7, '458b8200010000', 'avatar slot map capacity (avatar manager +0x100)'),
    (0x877FD1, '458b8a08010000', 'avatar slot map multiplier (+0x108)'),
    (0x877FE5, '4d8b9af8000000', 'avatar slot map buckets (+0xF8)'),
    (0x877FEC, '418bb204010000', 'avatar slot map empty key (+0x104)'),
    (0x878009, '418b04d3', 'bucket key = the avatar entity'),
    (0x8780DD, '418b44d304', 'bucket value = the avatar slot (stamina factor writer)'),
    (0x12A208E, '4d8b9c24f8000000', 'hit armor reader: the same slot map (+0xF8)'),
    (0x12A219A, '438b44c304', 'hit armor reader: the avatar slot'),
    (0x12A20C8, '4869c1b8010000', 'hit armor reader: armor modifier stride 0x1B8'),
    (0x833C8B, '488b99f8000000', 'armor modifier setter 0x833C50: the same slot map'),
    (0x833CD4, '8b44cb04', 'armor modifier setter: the avatar slot'),
    (0x833CDD, '4869c8b8010000', 'armor modifier setter: stride 0x1B8'),
]
# Reviewed write ranges. The class tables and the curve sit in pages that are PAGE_EXECUTE_READWRITE at run time; they
# are written as reviewed executable data, only their exact 4-byte entries (core/page_protection.lua,
# docs/armor-stats.md).
# The field ids (hd2.fields.armor_kit.piece_weight_<slot>, armor_class.*, armor_damage_curve.*; scripts/generate_sdk.py).
FIELD_IDS = (['armor_kit.piece_weight.' + slot for slot in SLOTS if slot != 'helmet']
    + ['armor_class.' + name for name in ('rating', 'speed', 'stamina')]
    + ['armor_damage_curve.' + name for name in ('at_minus_1', 'at_0', 'at_1', 'at_2', 'at_3')])
RANGES = {'rating': [-1.0, 4.0], 'speed': [0.5, 1.5], 'stamina': [0.25, 2.0], 'damage': [0.0, 4.0],
    'armorBonus': [-1.0, 3.0], 'staminaFactor': [0.1, 3.0]}


def _f32(hex_text: str) -> list[float]:
    raw = bytes.fromhex(hex_text)
    return [round(v, 6) for v in struct.unpack('<%df' % (len(raw) // 4), raw)]


def _check_layout(d: dict) -> None:
    layouts = d['layouts']
    for key, offset in (('0x1C', KIT['passive']), ('0x28', KIT['type']), ('0x30', KIT['bodies']),
            ('0x38', KIT['bodyCount'])):
        if int(key, 16) != offset or key not in layouts['kit']:
            raise ValueError('the research kit layout lacks ' + key)
    if layouts['body']['stride'] != '0x18' or 'Piece' not in layouts['body']['0x08'] or 'count' not in \
            layouts['body']['0x10']:
        raise ValueError('the research body layout moved')
    if layouts['piece']['stride'] != '0x60' or 'WEIGHT' not in layouts['piece']['0x10'] or 'slot' not in \
            layouts['piece']['0x08'] or 'type' not in layouts['piece']['0x0C']:
        raise ValueError('the research piece layout moved')
    avatar = layouts['avatarManager']
    if '0x53E900 + i x 0x1238' not in avatar or '0x546AC4 + i x 0x1B8' not in avatar:
        raise ValueError('the research avatar members moved')
    asm = {p['rva']: p['asm'] for group in d['pins'].values() for p in group}
    for rva, text in ((0x11D9247, 'mov esi, dword ptr [rax + 0x38]'), (0x11D925D, 'mov r11, qword ptr [r14 + 0x30]'),
            (0x11D9273, 'mov ebx, dword ptr [r11 + r10*8 + 0x10]'), (0x11D928D, 'shl rcx, 5'),
            (0x11D93C7, 'cmp dword ptr [rcx + 0xc], 0'), (0x11D93CD, 'mov edx, dword ptr [rcx + 8]'),
            (0x11D93DF, 'mov edx, dword ptr [rcx + 0x10]'), (0x87802B, 'imul rax, rcx, 0x1238'),
            (0x878032, 'movss dword ptr [rax + r10 + 0x53e900], xmm0'),
            (0x12A20CF, 'movss xmm3, dword ptr [rax + r12 + 0x546ac4]'),
            (0x12A2174, 'mov ecx, dword ptr [rbx + 0x1c]'), (0x12A2177, 'mov r8d, 0xafae3b47')):
        if asm.get(rva) != text:
            raise ValueError('pin %X is not %s' % (rva, text))
    roles = {p['rva']: p['role'] for group in d['pins'].values() for p in group}
    if 'customization manager' not in roles.get(0x11D9203, '') or 'avatar manager' not in roles.get(0x877FBE, ''):
        raise ValueError('the manager globals are not the pinned ones')


def build() -> dict:
    d = json.loads(RESEARCH.read_text(encoding='utf-8'))
    names = json.loads(NAMES.read_text(encoding='utf-8'))
    _check_layout(d)
    if d['gameDll'] != names['gameDll'] or d['build'] != names['build']:
        raise ValueError('the armor stats and armor names research cover different builds')
    if any(d['pinnedBytesMismatchPerSnapshot'].values()) or d['writes']:
        raise ValueError('a pin differs in a retained snapshot, or the research wrote')
    pins, seen = [], set()
    for group, items in d['pins'].items():
        for p in items:
            if not re.fullmatch(r'[0-9a-f]+', p['bytes']):
                raise ValueError('pin %s is not hex' % p['rva'])
            if p['rva'] not in seen:
                seen.add(p['rva'])
                pins.append({'rva': p['rva'], 'hex': p['bytes'], 'label': group + ': ' + p['role'][:80]})
    for rva, hex_text, label in SLOT_PINS:
        if rva in seen:
            raise ValueError('slot pin %X repeats a research pin' % rva)
        seen.add(rva)
        pins.append({'rva': rva, 'hex': hex_text, 'label': 'avatarSlot (this feature): ' + label})
    pins.sort(key=lambda p: p['rva'])
    data = {p['rva']: p for p in d['dataPins']}
    tables = {}
    for name in ('armor', 'speed', 'stamina'):
        rva = int(d['tables'][name]['rva'], 16)
        pin = data[rva]
        if _f32(pin['bytes']) != [round(v, 6) for v in d['tables'][name]['values']] or len(pin['bytes']) != 24:
            raise ValueError('the %s table is not its pinned bytes' % name)
        tables[name] = {'rva': rva, 'hex': pin['bytes'], 'values': d['tables'][name]['values']}
    curve = d['tables']['damageCurve']
    rva = int(curve['rva'], 16)
    raw = _f32(data[rva]['bytes'])
    points = [[raw[2 * i], raw[2 * i + 1]] for i in range(5)]
    if points != [[round(k, 6), round(v, 6)] for k, v in curve['points']]:
        raise ValueError('the damage curve is not its pinned bytes')
    if [k for k, _ in points] != [3.0, 2.0, 1.0, 0.0, -1.0]:
        raise ValueError('the damage curve keys moved')
    curve_out = {'rva': rva, 'hex': data[rva]['bytes'], 'points': curve['points']}
    section = dict(d['tables']['armor']['section'])
    for name in ('speed', 'stamina', 'damageCurve'):
        if d['tables'][name]['section'] != section:
            raise ValueError('the tables are not in one section')
    constants = [{'rva': p['rva'], 'hex': p['bytes'], 'label': 'data: ' + p['role']} for p in d['dataPins']
        if p['rva'] not in {t['rva'] for t in tables.values()} | {rva}]
    # The passives' armor-rating rows (PassiveValue: (Set or mean) + sum Add, x prod Multiply).
    passives = {}
    for p in names['passives']:
        rows = [{'type': e['type'], 'value': e['value']} for e in p['effects'] if e['key'] == ARMOR_KEY]
        for row in rows:
            if row['type'] not in ('Set', 'Add', 'Multiply'):
                raise ValueError('armor row type %s of %s' % (row['type'], p['name']))
        passives[p['id']] = {'name': p['name'], 'armor': rows}
    census = {c['id']: c for c in d['armorKitCensus']}
    if not d['armorKitCensusIdenticalInAllSnapshots']:
        raise ValueError('the armor kit census differs between snapshots')
    kits = []
    for row in names['kits']:
        if row['slot'] != 'armor':
            continue
        c = census.pop(row['kitId'], None)
        if c is None:
            raise ValueError('armor kit %s has no census row' % row['kitId'])
        if c['passive'] != row['passive'] or c['passive'] not in passives:
            raise ValueError('armor kit %s passive differs' % row['kitId'])
        weights = {}
        for slot, weight in c['stats']['weights'].items():
            if slot not in SLOTS or weight not in WEIGHTS:
                raise ValueError('armor kit %s piece %s weight %s' % (row['kitId'], slot, weight))
            weights[slot] = WEIGHTS.index(weight)
        if sorted({s for s, kind in row['pieceSlots'] if kind == 'armor'}) != sorted(weights):
            raise ValueError('armor kit %s armor pieces differ between the researches' % row['kitId'])
        s = c['stats']
        kits.append({'id': row['kitId'], 'index': row['id'], 'name': row['name'] or None, 'passive': row['passive'],
            'bodies': row['bodies'], 'weights': weights, 'class': s['torsoWeight'],
            'vanilla': {'rating': s['displayRating'], 'speed': s['displaySpeed'], 'stamina': s['displayStamina'],
                'armorValue': s['armorValue'], 'speedFactor': s['gameplaySpeedFactor'],
                'staminaFactor': s['gameplayStaminaFactor'], 'damageMultiplier': s['damageMultiplier']}})
    if census:
        raise ValueError('census kits without a name row: ' + ', '.join(sorted(census)))
    by_name = {}
    for kit in kits:
        if kit['name']:
            by_name.setdefault(kit['name'].lower(), []).append(kit['id'])
    ambiguous = {name: ids for name, ids in sorted(by_name.items()) if len(ids) > 1}
    return {'source': {'research': RESEARCH.name, 'names': NAMES.name, 'build': d['build'], 'gameDllSha256': d['gameDll'],
            'pins': d['pinCount'], 'snapshots': len(d['pinnedBytesMismatchPerSnapshot'])},
        'tables': tables, 'curve': curve_out, 'section': section, 'classes': WEIGHTS, 'slots': SLOTS,
        'customization': CUSTOMIZATION, 'kit': KIT, 'body': BODY, 'piece': PIECE, 'avatar': AVATAR,
        'armorKey': ARMOR_KEY, 'passives': passives, 'kits': kits, 'ambiguousNames': ambiguous, 'ranges': RANGES,
        'pins': pins, 'constants': constants}


# The public catalog (sdk/ArmorStatsCapabilities.json). The descriptor texts below are the ones
# domains/armor_stats_writes.lua and runtime/armor_stats.lua give at run time (tests/test_armor_stats.py compares them).
CATALOG = 'sdk/ArmorStatsCapabilities.json'
CONTRACT = 'hd2runtime.armor_stats.capabilities.v1'
LIVE_SESSION = 'armor-stats-passives-r55-2026-10-08'
ACKNOWLEDGEMENTS = ['allow_shared', 'allow_unverified_effect']
UNVERIFIED = 'not live-tested (docs/armor-stats.md)'
SHARED = {'armor_kit': 'every player wearing this armor kit reads its pieces (stocky, slim and any-body pieces alike)',
    'armor_class': 'every armor whose pieces have this weight, for every player this machine simulates or hits',
    'armor_damage_curve': 'every Helldiver hit on this machine'}
KIT_LIFECYCLE = ('armor rating: the next hit (live); speed and stamina: the next armor apply (respawn or a kit '
    'change)')
APPLY = 'the next armor apply (respawn or a kit change)'
CLASS_FIELDS = [
    ('rating', 'armor', 'Armor value', 'armor_value', 'the next hit (live)', 'live'),
    ('speed', 'speed', 'Speed factor', 'speed_factor',
     APPLY + '; how the game consumes the speed product is UNPROVEN', 'armor_apply'),
    ('stamina', 'stamina', 'Stamina factor', 'stamina_factor', APPLY, 'armor_apply')]
CURVE_FIELDS = [(3, 'at_3'), (2, 'at_2'), (1, 'at_1'), (0, 'at_0'), (-1, 'at_minus_1')]   # the curve's point order
RATING_SLOTS = ['torso', 'left_leg', 'right_leg', 'left_arm', 'right_arm', 'left_shoulder', 'right_shoulder']
PLAYER_CODES = ['ACKNOWLEDGEMENT_REQUIRED', 'OUT_OF_RANGE', 'INVALID_OPTION', 'NO_PLAYER', 'NO_LOCAL_AVATAR',
    'NO_AVATAR_SLOT', 'UNEXPECTED_STATE', 'NOT_SOLO', 'NOT_PRIVATE', 'UNAVAILABLE', 'UNSUPPORTED_BUILD',
    'GUARD_REJECTED']
TRANSACTION_CODES = ['UNKNOWN_ARMOR_KIT', 'AMBIGUOUS_ARMOR_KIT', 'UNKNOWN_ARMOR_CLASS', 'UNKNOWN_WEIGHT',
    'UNKNOWN_SLOT', 'ARMOR_BUILD_CHANGED', 'ARMOR_KIT_MOVED', 'CONFLICT']
EXECUTABLE_DATA = ('The class tables and the damage curve sit in game.dll pages that are executable at run time. They '
    'are written as reviewed executable data (the user\'s decision of 2026-10-08): only their exact 4-byte entries, '
    'after the build, every pin and constant are proved. The page protection is never changed '
    '(docs/armor-stats.md, "Class tables: reviewed executable data").')


def api_constant(field_id: str) -> str:
    """The hd2.fields constant of a field id (scripts/generate_sdk.py: domain, then the rest with '.' -> '_')."""
    domain, name = field_id.split('.', 1)
    return 'hd2.fields.' + domain + '.' + name.replace('.', '_')


def _instance(field_id, display, target, kind, unit, storage, values, default, lifecycle, lifecycle_kind, group,
        executable):
    return {'semanticFieldId': field_id, 'apiFieldConstant': api_constant(field_id), 'displayName': display,
        'target': target, 'type': kind, 'unit': unit, 'storage': storage, **values, 'currentDefault': default,
        'editable': True, 'executableData': executable, 'lifecycle': lifecycle, 'lifecycleKind': lifecycle_kind,
        'shared': True, 'allowSharedRequired': True, 'sharedReason': SHARED[target['resource']],
        'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': UNVERIFIED,
        'acknowledgements': list(ACKNOWLEDGEMENTS), 'operationGroup': group, 'liveTested': False}


def _evidence() -> dict:
    """Development, nothing promoted. The r55 session ran the probe; its armor stat lines are recorded in
    schemas/live_evidence.json and not promoted. A live-proven armor stats family must be published here first."""
    import live_evidence
    registry = live_evidence.load()
    promoted = sorted(name for name, f in registry['families'].items() if f.get('domain') == 'armor_stats'
        and f['status'] == 'live_proven')
    if promoted:
        raise ValueError('armor stats families are live-proven now; publish them: ' + ', '.join(promoted))
    session = next((s for s in registry['sessions'] if s['id'] == LIVE_SESSION), None)
    if not session or not any('ArmorStatProbe' in t['observation'] and 'not promoted' in t['observation']
            for t in session['tests']):
        raise ValueError('the r55 armor stats session is not the recorded, unpromoted one')
    return {'status': 'development', 'liveTested': False, 'liveProvenFamilies': [], 'liveTest': 'proof/ArmorStatProbe',
        'sessions': [{'session': session['id'], 'date': session['date'], 'status': 'recorded_not_promoted',
            'summary': 'ArmorStatProbe 0.2.0 ran in the r55 build. The log shows the stamina factor 0.5, the kit '
                'ensure and the damage curve ensure applied and held (the curve with no protection change). Only one '
                'hit was logged, so no damage comparison exists. Recorded, not promoted.'}],
        'research': [RESEARCH.name, NAMES.name],
        'validation': 'scripts/validate_armor_stats_snapshot.py (all seven retained snapshots) and the packaged '
            'scenario proof-armor-stats'}


def catalog(d: dict) -> dict:
    """sdk/ArmorStatsCapabilities.json from build(): what ModBuilder and other SDK tools read."""
    tables, points, names = d['tables'], d['curve']['points'], d['passives']
    classes = []
    for index, name in enumerate(WEIGHTS):
        a, s, f = (tables[t]['values'][index] for t in ('armor', 'speed', 'stamina'))
        classes.append({'name': name, 'index': index, 'armorValue': a, 'speedFactor': s, 'staminaFactor': f,
            'display': {'rating': round(50 + 50 * a, 6), 'speed': round(500 * s, 6),
                'staminaRegen': round(100 * (2 - f), 6)}})
    kits, instances = [], []
    for kit in d['kits']:
        if 'helmet' in kit['weights']:
            raise ValueError('armor kit %s has a helmet piece weight' % kit['id'])
        slots = [slot for slot in SLOTS if slot in kit['weights']]
        weights = {slot: WEIGHTS[kit['weights'][slot]] for slot in slots}
        ambiguous = d['ambiguousNames'].get((kit['name'] or '').lower())
        kits.append({'id': kit['id'], 'hexId': '0x' + kit['id'], 'index': kit['index'], 'name': kit['name'],
            'nameUnique': bool(kit['name']) and not ambiguous,
            'passive': {'id': kit['passive'], 'name': names[kit['passive']]['name']}, 'class': kit['class'],
            'slots': slots, 'weights': weights, 'ratingPieces': sum(slot in RATING_SLOTS for slot in slots),
            'vanilla': kit['vanilla']})
        for slot in slots:
            instances.append(_instance('armor_kit.piece_weight.' + slot,
                slot.replace('_', ' ').capitalize() + ' piece weight',
                {'resource': 'armor_kit', 'armor_kit': kit['id'], 'path': 'piece_weight', 'slot': slot}, 'enum',
                'weight_class', 'u32', {'allowedValues': list(WEIGHTS)}, weights[slot], KIT_LIFECYCLE,
                'live_and_armor_apply', 'armor_kit/' + kit['id'], False))
    for index, name in enumerate(WEIGHTS):
        for field, table, display, unit, lifecycle, kind in CLASS_FIELDS:
            low, high = RANGES[field]
            instances.append(_instance('armor_class.' + field, display + ' (' + name + ')',
                {'resource': 'armor_class', 'armor_class': name, 'path': 'class_table'}, 'number', unit, 'f32',
                {'min': low, 'max': high}, tables[table]['values'][index], lifecycle, kind, 'armor_class/' + table,
                True))
    low, high = RANGES['damage']
    for (key, name), (point, damage) in zip(CURVE_FIELDS, points):
        if key != point:
            raise ValueError('the curve points are not in the field order')
        instances.append(_instance('armor_damage_curve.' + name, 'Damage multiplier at armor value %d' % key,
            {'resource': 'armor_damage_curve', 'path': 'damage_curve', 'armorValue': key}, 'number',
            'damage_multiplier', 'f32', {'min': low, 'max': high}, damage, 'the next hit on a Helldiver (live)', 'live',
            'armor_damage_curve', True))
    if sorted({i['semanticFieldId'] for i in instances}) != sorted(FIELD_IDS):
        raise ValueError('the field instances are not the published field ids')
    bonuses = [{'passive': pid, 'name': p['name'], 'rows': p['armor']} for pid, p in sorted(names.items())
        if p['armor']]
    kinds = [i['target']['resource'] for i in instances]
    return {'contract': CONTRACT, 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text(encoding='utf-8').strip(), 'build': d['source']['build'],
        'source': {'research': d['source']['research'], 'names': d['source']['names'],
            'generator': 'scripts/generate_armor_stats.py', 'domain': OUTPUT, 'docs': 'docs/armor-stats.md'},
        'status': 'development',
        'summary': {'kits': len(kits), 'namedKits': sum(1 for k in kits if k['name']),
            'uniquelyNamedKits': sum(1 for k in kits if k['nameUnique']), 'classes': len(classes),
            'curvePoints': len(points), 'fieldInstances': len(instances),
            'kitFieldInstances': kinds.count('armor_kit'), 'classFieldInstances': kinds.count('armor_class'),
            'curveFieldInstances': kinds.count('armor_damage_curve'), 'passiveArmorBonuses': len(bonuses)},
        'targets': {
            'armor_kit': {'accessor': "hd2.armor_stats.kit('<id>')",
                'identity': 'the kit id (8 hex digits, a number, or 0x and 8 hex digits), or its game name in any case '
                    'when nameUnique; a shared name raises AMBIGUOUS_ARMOR_KIT',
                'luaTarget': {'resource': 'armor_kit', 'armor_kit': '<id>'}, 'scope': SHARED['armor_kit'],
                'changeHelper': 'kit:changes(weight, slots)',
                'writes': 'the weight of the kit\'s armor piece in that slot, in every body that has one: one guarded '
                    '4-byte write per piece'},
            'armor_class': {'accessor': "hd2.armor_stats.class('<light|medium|heavy>')", 'alias': 'hd2.armor_class',
                'luaTarget': {'resource': 'armor_class', 'armor_class': '<light|medium|heavy>'},
                'scope': SHARED['armor_class'],
                'writes': 'one f32 entry of the class table (reviewed executable data)'},
            'armor_damage_curve': {'accessor': 'hd2.armor_stats.damage_curve()',
                'luaTarget': {'resource': 'armor_damage_curve'}, 'scope': SHARED['armor_damage_curve'],
                'writes': 'one f32: the damage of one curve point; the armor values (x) are never written'}},
        'transaction': {'operations': ['hd2.patch', 'hd2.transaction', 'hd2.ensure'], 'targetsPerRequest': 1,
            'minChanges': 1, 'maxChanges': len(SLOTS),
            'requestOptions': ['id', 'target', 'field', 'expect', 'value', 'changes', 'diagnostic', 'allow_shared',
                'allow_unverified_effect'],
            'acknowledgements': list(ACKNOWLEDGEMENTS),
            'expect': 'the vanilla currentDefault, or the value this Runtime wrote there; anything else is a CONFLICT',
            'weightValues': {name: index for index, name in enumerate(WEIGHTS)}, 'refusals': list(TRANSACTION_CODES),
            'synced': False, 'syncNote': 'Not synced: every machine evaluates with its own kits, tables and curve.'},
        'executableData': EXECUTABLE_DATA,
        'slots': [{'name': slot, 'index': index, 'ratingSlot': slot in RATING_SLOTS}
            for index, slot in enumerate(SLOTS) if slot != 'helmet'],
        'classes': classes,
        'damageCurve': {'points': [{'armorValue': k, 'damage': v} for k, v in reversed(points)],
            'interpolation': 'linear between neighbouring points; the top value above the top armor value, 1.0 below '
                'the lowest', 'readOn': 'every hit on a Helldiver'},
        'formulas': {
            'armorValue': 'A = the mean of the class armor value over the kit\'s armor pieces in the rating slots '
                '(torso, legs, arms, shoulders; not the cape or the hips), then the kit passive\'s armor rows: '
                '(Set, else the mean) + the sum of Add, times the product of Multiply. Read on every hit.',
            'damageMultiplier': 'curve(A). The attack\'s penetration does not enter it.',
            'speedFactor': 'S = the mean of the class speed factor over every armor piece of the kit (cape and hips '
                'included), applied at the next armor apply. How the game consumes S is unproven.',
            'staminaFactor': 'F = the mean of the class stamina factor over every armor piece of the kit, applied at '
                'the next armor apply. It scales stamina drain and regen alike, and the jump, dive, climb and slide '
                'costs.',
            'displayFactors': 'The armory averages the speed and stamina factors over the rating slots only, so for '
                'some kits the gameplay factors differ slightly from the displayed ones.',
            'display': {'rating': 'RATING = 50 + 50 x A', 'speed': 'SPEED = 500 x S (the display factor)',
                'staminaRegen': 'STAMINA REGEN = 100 x (2 - F) (the display factor)'},
            'displayLinear': {'rating': {'of': 'armorValue', 'scale': 50, 'plus': 50},
                'speed': {'of': 'displaySpeedFactor', 'scale': 500, 'plus': 0},
                'staminaRegen': {'of': 'displayStaminaFactor', 'scale': -100, 'plus': 200}},
            'classLabel': 'the torso piece\'s weight'},
        'passiveArmorBonuses': bonuses,
        'ranges': {'armor_class.rating': RANGES['rating'], 'armor_class.speed': RANGES['speed'],
            'armor_class.stamina': RANGES['stamina'], 'armor_damage_curve': RANGES['damage'],
            'player.armor_bonus': RANGES['armorBonus'], 'player.stamina_factor': RANGES['staminaFactor']},
        'player': {'accessor': 'hd2.armor_stats.player()',
            'methods': {'describe': '{entity, avatar, slot, armor_bonus, stamina_factor, armor_kit, derived, '
                    'effective_armor_value, overridden}, or nil, code, reason',
                'set': 'writes one or both members: {status, code, reason, armor_bonus, stamina_factor, writes, '
                    'verified}',
                'restore': 'puts the game\'s own values back where a member still holds this Runtime\'s value'},
            'options': {
                'armor_bonus': {'type': 'number', 'min': RANGES['armorBonus'][0], 'max': RANGES['armorBonus'][1],
                    'effect': 'added to the armor value of every hit on this avatar; the sum is clamped to -1..3 when '
                        'the bonus is not 0', 'lasts': 'live; a status effect writes -1 on apply and 0 on removal'},
                'stamina_factor': {'type': 'number', 'min': RANGES['staminaFactor'][0],
                    'max': RANGES['staminaFactor'][1],
                    'effect': 'the armor\'s F: scales stamina drain and regen and the action costs',
                    'lasts': 'live until the game next applies the armor (a respawn or an armor change); call set '
                        'again then'},
                'allow_unverified_effect': {'type': 'boolean', 'required': True},
                'owner': {'type': 'string', 'required': False}},
            'atLeastOne': ['armor_bonus', 'stamina_factor'], 'acknowledgements': ['allow_unverified_effect'],
            'allowSharedRequired': False, 'soloOnly': True, 'raises': False,
            'statuses': ['APPLIED', 'UNCHANGED', 'refused'], 'refusalCodes': list(PLAYER_CODES),
            'expectedState': 'each member holds the game\'s own value (armor bonus 0 or -1; the stamina factor the '
                'worn kit gives) or the value this Runtime last wrote; anything else is UNEXPECTED_STATE',
            'liveTested': False},
        'evidence': _evidence(),
        'kits': kits, 'fieldInstances': instances,
        'safety': {'runtimeAddresses': False, 'rawWrites': False, 'nativeLayouts': False,
            'writesDuringGeneration': 0}}


def outputs() -> dict[str, str]:
    d = build()
    return {OUTPUT: '-- Generated by scripts/generate_armor_stats.py; do not edit.\nreturn ' + lua(d) + '\n',
        CATALOG: json.dumps(catalog(d), indent=1, ensure_ascii=True) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale generated armor stats domain or catalog: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
