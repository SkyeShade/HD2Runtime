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
# Reviewed write ranges. The class tables and the curve are published read-only (docs/armor-stats.md): their pages are
# PAGE_EXECUTE_READWRITE at run time, a protection the guarded write refuses by rule (core/page_protection.lua).
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


def outputs() -> dict[str, str]:
    return {OUTPUT: '-- Generated by scripts/generate_armor_stats.py; do not edit.\nreturn ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale generated armor stats domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
