"""Generate domains/player_passives.lua: the per-player armor passive store (research/player-attributes-F5FEE03DCFDB.json,
scripts/research_player_attributes.py, research/docs/player-attributes-F5FEE03DCFDB.md) as runtime/player_passives.lua
reads and writes it: the customization manager layout (kits, passives, the passive id index, the entity -> record map,
the applied records), the kit, passive and modifier layouts, every one of the game's 32 passives with its modifiers
(the game's own names and effect texts), a semantic name per modifier key, the readers that ignore the second slot
(flags 1), the record the retained snapshots hold, and every pin of the research (re-proved before any read or write).
Checked here: the layout is the one the pins prove, every pin is hex, every passive id is in range and unique, every
modifier key a passive carries has a semantic name, and every snapshot holds the same record.

Also (research/armor-names-F5FEE03DCFDB.json, scripts/research_armor_names.py): every one of the game's 411 kits
{index, id, slot, weight (its armor pieces'), passive, set, dlc, rarity, the game's name (378 resolved) and description,
the community wiki's stats where a wiki page matched (labelled as the wiki's, never read from the game)} and every
passive's game description; and (research/passive-effects-F5FEE03DCFDB.json, scripts/research_passive_effects.py) per
passive whether its effects follow a slot swap ('full' | 'partial' | 'unknown'), per modifier its reader status
('direct' | 'data-driven' | 'description-only' | 'armor rating' | 'none found' | 'no effect') with a note for the ones
that do not follow, the spawn-time stat rows, and the effect package (17, 19) under its core/assets catalogue key
'passive/<id>' (scripts/generate_package_residency.py adds that entry from the same research). Checked: the same names,
ids and key order in all three research files, every kit's passive in the table, the research's own slot and name
counts, and the snapshot kit names equal to the kit table's.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/player-attributes-F5FEE03DCFDB.json'
NAMES = ROOT / 'research/armor-names-F5FEE03DCFDB.json'
EFFECTS = ROOT / 'research/passive-effects-F5FEE03DCFDB.json'
OUTPUT = 'domains/player_passives.lua'
# A semantic name per modifier key: the research's reader census (research/docs/player-attributes-F5FEE03DCFDB.md) and
# the game's own effect text. 'unknown_<key>' where the research found neither a reader nor a text.
KEY_NAMES = {
    '00000000': 'none',
    'AF8B7112': 'movement_noise', '14ECCE15': 'enemy_detection_range', '432A7993': 'poi_identification_range',
    'B62B4AFD': 'leg_injury_immunity', 'A189ADB6': 'stamina_when_damaged', '2CFAECA3': 'chest_damage_resistance',
    '1F98D152': 'explosive_resistance', '4DF29271': 'fire_resistance', '4BDF39C4': 'arc_resistance',
    '6E99CCE5': 'gas_resistance', 'B5A50096': 'elemental_resistance', '25A59469': 'impact_resistance',
    'FBF54A40': 'limb_injury_avoidance', 'A68930C2': 'chest_bleed_prevention', '73734D67': 'flinch_prevention',
    '54A69284': 'death_explosion', 'CB814D05': 'lethal_damage_survival', '11A3C04C': 'knock_prone_resistance',
    '86A99BB9': 'limb_health', 'C36935A9': 'crouch_prone_recoil', 'C8CCB6FA': 'weapon_ergonomics',
    '26C969A1': 'throw_range', 'F6FA9626': 'grenade_capacity', '2875F44A': 'stim_capacity', '93EB16A7': 'stim_duration',
    '21A7BA64': 'radar_scan_interval', '6938BD56': 'slide_boost', 'AFAE3B47': 'armor_rating',
    'CC530B21': 'primary_reload_speed', '35F17BEC': 'support_reload_speed', 'B4F88129': 'sidearm_reload_speed',
    '33C9C713': 'ammo_capacity', 'AD5289FE': 'sidearm_draw_speed', '22035F3C': 'sidearm_recoil',
    '2559B40D': 'melee_damage', 'CD79A687': 'movement_speed', 'F6D67313': 'unknown_f6d67313',
    '8933E7F4': 'unknown_8933e7f4', '0DFF0E42': 'unknown_0dff0e42',
}
# Kit names the retained snapshots resolved (the game's own text); every other kit is reported by id.
LAYOUT = {'kits': 0x00, 'kitCount': 0x08, 'passives': 0x20, 'passiveCount': 0x28, 'passiveIndex': 0x30, 'passiveIds': 42,
    'recordCount': 0x8E8, 'map': 0x930, 'descriptors': 0x948, 'descriptorEntity': 0x08, 'applied': 0x96C,
    'appliedStride': 0x44, 'pending': 0xA7C, 'pendingStride': 0x40, 'capacity': 4}
RECORD = {'helmetKit': 0x04, 'capeKit': 0x08, 'armorKit': 0x0C, 'helmetPassive': 0x38, 'armorPassive': 0x3C}
KIT = {'id': 0x00, 'passive': 0x1C, 'type': 0x28, 'read': 0x2C}
PASSIVE = {'id': 0x00, 'name': 0x04, 'modifiers': 0x10, 'count': 0x18, 'package': 0x30, 'read': 0x34}
MODIFIER = {'key': 0x00, 'type': 0x04, 'value': 0x08, 'text': 0x0C, 'stride': 16}
TYPES = ['Set', 'Add', 'Multiply', 'Time']


def _check_layout(d: dict) -> None:
    layouts = d['layouts']
    manager = layouts['customizationManager']
    for key, offset in (('0x000', LAYOUT['kits']), ('0x020', LAYOUT['passives']), ('0x030', LAYOUT['passiveIndex']),
            ('0x930', LAYOUT['map']), ('0x948', LAYOUT['descriptors']), ('0x96C', LAYOUT['applied']),
            ('0xA7C', LAYOUT['pending']), ('0x8E8', LAYOUT['recordCount'])):
        if int(key, 16) != offset or key not in manager:
            raise ValueError('the research manager layout lacks ' + key)
    record = layouts['appliedRecord']
    for name, offset in RECORD.items():
        if '0x%02X' % offset not in record:
            raise ValueError('the research applied record lacks ' + name)
    if 'armor passive' not in record['0x3C'] or 'helmet passive' not in record['0x38'] or 'armor kit' not in record['0x0C']:
        raise ValueError('the applied record passive slots moved')
    if 'Passive' not in layouts['kit']['0x1C'] or 'package' not in layouts['passive']['0x30']:
        raise ValueError('the kit or passive layout moved')
    if layouts['modifier']['0x08'] != 'f32 value':
        raise ValueError('the modifier layout moved')
    asm = {p['rva']: p['asm'] for group in d['pins'].values() for p in group}
    for rva, text in ((0x11D9F7D, 'imul r11, rax, 0x44'), (0x11D9F81, 'mov eax, dword ptr [r11 + r9 + 0x9a8]'),
            (0x11D9FDA, 'mov eax, dword ptr [r11 + r9 + 0x9a4]'), (0x11D9F93, 'mov ecx, dword ptr [r9 + rax*4 + 0x30]'),
            (0x8748A4, 'mov dword ptr [r15 + 0x3c], eax'), (0x87467F, 'mov dword ptr [r15 + 0x38], eax'),
            (0x87480C, 'mov eax, dword ptr [rbx + 0x1c]')):
        if asm.get(rva) != text:
            raise ValueError('pin %X is not %s' % (rva, text))
    if d['globals']['customizationManager'] != 0x33264F8:
        raise ValueError('the customization manager global moved')


# The research's reader status per modifier row (research/passive-effects-F5FEE03DCFDB.json) -> the API's.
READER_STATUS = {'direct reader': 'direct', 'data-driven reader': 'data-driven',
    'stat row (kit passive, spawn time)': 'description-only', 'kit passive (PassiveValue)': 'armor rating',
    'none found': 'none found', 'no effect': 'no effect'}
READERS = sorted(set(READER_STATUS.values()))
COVERAGE = ('full', 'partial', 'unknown')


def _kits(attributes: dict, passives: list) -> list:
    """Every kit of research/armor-names-F5FEE03DCFDB.json, by index: the game's identity, slot, weight, passive, set,
    dlc, rarity, name and description, and the wiki's stats where a wiki page matched."""
    n = json.loads(NAMES.read_text(encoding='utf-8'))
    if n['gameDll'] != attributes['gameDll'] or n['build'] != attributes['build']:
        raise ValueError('the armor names research covers another game.dll build')
    names = {p['id']: p['name'] for p in passives}
    if {p['id']: p['name'] for p in n['passives']} != names:
        raise ValueError('the armor names research has other passive names')
    kits, ids, slots, resolved = [], set(), {}, 0
    for index, k in enumerate(n['kits']):
        if k['id'] != index or k['kitId'] in ids or not re.fullmatch(r'[0-9A-F]{8}', k['kitId']):
            raise ValueError('kit %s is out of order, repeated or malformed' % k['id'])
        if k['slot'] not in ('armor', 'helmet', 'cape') or k['passive'] not in names:
            raise ValueError('kit %s has slot %s or passive %s' % (index, k['slot'], k['passive']))
        if (k['slot'] == 'armor') != (k['weight'] in ('light', 'medium', 'heavy')):
            raise ValueError('kit %s: exactly the armor kits carry a weight' % index)
        if k['slot'] != 'armor' and k['passive'] != 0:
            raise ValueError('kit %s: a helmet or cape with a passive' % index)
        ids.add(k['kitId'])
        slots[k['slot']] = slots.get(k['slot'], 0) + 1
        resolved += bool(k['name'])
        kit = {'index': index, 'id': '0x' + k['kitId'], 'slot': k['slot'], 'weight': k['weight'],
            'passive': k['passive'], 'set': k['set'] and '0x' + k['set'], 'dlc': k['dlc'] and '0x' + k['dlc'],
            'rarity': k['rarity'], 'name': k['name'], 'description': k['description']}
        w = k.get('wiki')
        if w and k.get('wikiMatch'):
            wiki = {'name': w['name'], 'match': k['wikiMatch'], 'class': w.get('class'),
                'armorRating': w.get('armorRating'), 'speed': w.get('speed'), 'staminaRegen': w.get('staminaRegen'),
                'passive': w.get('passiveName'), 'passiveAgrees': k.get('wikiPassiveAgrees')}
            kit['wiki'] = {key: v for key, v in wiki.items() if v is not None}
        kits.append({key: v for key, v in kit.items() if v is not None})
    if slots != n['stats']['bySlot'] or resolved != n['stats']['namesResolved'] or len(kits) != n['stats']['kits']:
        raise ValueError('the kit table is not the research\'s counts')
    return kits


def _effects(attributes: dict, passives: list, armor_only: set) -> None:
    """Adds research/passive-effects-F5FEE03DCFDB.json to every passive: followsSwap, the game's description, per
    modifier its reader status, whether it follows a swap and a note where it does not, the spawn-time stat rows, and
    the effect package's catalogue key."""
    e = json.loads(EFFECTS.read_text(encoding='utf-8'))
    n = json.loads(NAMES.read_text(encoding='utf-8'))
    if e['gameDll'] != attributes['gameDll'] or any(e['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('the passive effects research covers another game.dll build, or a pin differs')
    by_id = {p['id']: p for p in e['passives']}
    descriptions = {p['id']: p['description'] for p in n['passives']}
    resolved = e['packageMechanism']['resolved']
    lookup = e['packageMechanism']['hashLookup']
    if len(by_id) != len(passives) or lookup['entries'] != lookup['valuesThatArePackages']:
        raise ValueError('the passive effects research has another passive table or package map')
    for p in passives:
        r = by_id[p['id']]
        if r['name'] != p['name'] or [k['key'] for k in r['keys']] != [m['key'] for m in p['modifiers']]:
            raise ValueError('passive %s has other rows in the passive effects research' % p['id'])
        if r['swapCoverage'] not in COVERAGE:
            raise ValueError('passive %s swap coverage %s' % (p['id'], r['swapCoverage']))
        stats = [{'stat': s['stat'], 'name': s['name'], 'add': s['add'], 'mul': s['mul'],
            'describedBy': s['describedBy']} for s in r['stats']]
        not_following = []
        for m, k in zip(p['modifiers'], r['keys']):
            status = READER_STATUS[k['readerStatus']]
            m['reader'], m['follows'], m['observable'] = status, k['followsRecordSwap'], k['observable']
            if m['key'] in armor_only:
                m['armorSlotOnly'] = True
            if status == 'description-only':
                stat = next((s for s in stats if s['describedBy'] == m['key']), None)
                if not stat or k['followsRecordSwap'] is not False:
                    raise ValueError('passive %s key %s: description-only without its stat row' % (p['id'], m['key']))
                m['note'] = ('stat-driven at spawn: the effect is stat %d (%s) x%g of the kit worn at spawn; a swap '
                    'never changes it' % (stat['stat'], stat['name'], stat['mul']))
            elif status == 'armor rating':
                if k['followsRecordSwap'] is not False:
                    raise ValueError('passive %s key %s: an armor rating that follows a swap' % (p['id'], m['key']))
                m['note'] = 'armor rating: it follows the worn armor kit (its own passive), never the slot'
            elif status == 'none found':
                if p['id'] != 19:
                    raise ValueError('passive %s key %s: a row without a reader' % (p['id'], m['key']))
                m['note'] = 'no reader found: the revive mechanism was not located, so whether a swap carries it is unknown'
            if m['follows'] is False:
                not_following.append(m['key_name'])
        for s in stats:
            if s['describedBy'] is None:
                not_following.append('stat %d x%g (no modifier row)' % (s['stat'], s['mul']))
        if (r['swapCoverage'] == 'partial') != bool(not_following):
            raise ValueError('passive %s: coverage %s with %s not following' % (p['id'], r['swapCoverage'],
                not_following))
        p['followsSwap'], p['description'], p['stats'] = r['swapCoverage'], descriptions[p['id']], stats
        if r['swapCoverage'] == 'partial':
            p['note'] = 'partly follows a swap: %s follow%s the kit worn (at spawn) instead' % (
                ', '.join(not_following), 's' if len(not_following) == 1 else '')
        elif r['swapCoverage'] == 'unknown':
            p['note'] = 'unknown: the revive mechanism was not located; its other rows (%s) follow a swap' % ', '.join(
                m['key_name'] for m in p['modifiers'] if m['follows'])
        if p['package'] or r['package']:
            res = resolved.get(str(p['id']))
            if not res or res['thin'] != p['package'] or res['package'] != r['package']:
                raise ValueError('passive %s: the effect package is not the resolved one' % p['id'])
            kinds = {}
            for item in e['packageMechanism']['contents'][res['package']]['resources']:
                kinds[item['type']] = kinds.get(item['type'], 0) + 1
            p['packageInfo'] = {'key': p['package'], 'dependency': 'passive/%d' % p['id'], 'package': res['package'],
                'contents': ', '.join('%d %s' % (c, t) for t, c in sorted(kinds.items())),
                'armorSlotOnly': [m['key_name'] for m in p['modifiers'] if m.get('armorSlotOnly')]}


def build() -> dict:
    d = json.loads(RESEARCH.read_text(encoding='utf-8'))
    _check_layout(d)
    if any(d['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pin differs in a retained snapshot')
    pins, seen = [], set()
    for group, items in d['pins'].items():
        for p in items:
            if not re.fullmatch(r'[0-9a-f]+', p['bytes']):
                raise ValueError('pin %s is not hex' % p['rva'])
            if p['rva'] not in seen:
                seen.add(p['rva'])
                pins.append({'rva': p['rva'], 'hex': p['bytes'], 'label': group + ': ' + p['role'][:80]})
    pins.sort(key=lambda p: p['rva'])
    keys = d['keys']
    passives, ids, names = [], set(), set()
    for p in d['passiveTable']:
        if not 0 <= p['id'] < LAYOUT['passiveIds'] or p['id'] in ids:
            raise ValueError('passive id %s out of range or repeated' % p['id'])
        if p['name'].lower() in names:
            raise ValueError('passive name repeated: ' + p['name'])
        ids.add(p['id'])
        names.add(p['name'].lower())
        modifiers = []
        for m in p['modifiers']:
            if m['key'] not in KEY_NAMES:
                raise ValueError('modifier key %s of %s has no semantic name' % (m['key'], p['name']))
            if m['type'] not in TYPES:
                raise ValueError('modifier type ' + m['type'])
            modifiers.append({'key': m['key'], 'key_name': KEY_NAMES[m['key']], 'type': m['type'], 'value': m['value'],
                'text': m.get('text')})
        passives.append({'id': p['id'], 'name': p['name'], 'nameId': p['nameId'],
            'package': None if p['package'] == '00000000' else p['package'], 'modifiers': modifiers,
            'armorKits': len(p['armorKits'])})
    passives.sort(key=lambda p: p['id'])
    unused = sorted(set(range(LAYOUT['passiveIds'])) - ids)
    for snap in d['snapshots']:
        if snap['passiveTable']['unusedIds'] != unused:
            raise ValueError('a snapshot has other unused passive ids')
    # Every reader that ignores the second (helmet) slot: flags 1; computed flags are listed apart.
    flags_one, computed = {}, {}
    for r in d['readerCensus']:
        target = flags_one if r['flags'] == 1 else computed if not isinstance(r['flags'], int) else None
        if target is None or r['key'] == 'from caller':
            continue
        target.setdefault(r['key'], []).append('0x%X' % r['site'])
    key_table = {}
    for key, k in keys.items():
        sites = len(k['entityAttributeSites'])
        key_table[key] = {'name': KEY_NAMES.get(key, 'unknown_' + key.lower()), 'text': k.get('text'), 'readers': sites,
            'flagsOne': key in flags_one}
    first = d['snapshots'][0]['players']

    def slots(players):
        return [(p['entity'], p['record']) + tuple(p['applied']['0x%02X' % o] for o in RECORD.values()) for p in players]
    for snap in d['snapshots']:
        if slots(snap['players']) != slots(first):
            raise ValueError('the retained snapshots hold different kits or passives')
    p = first[0]
    observed = {'entity': int(p['entity'], 16), 'record': p['record'], 'armorKit': p['armorKit']['id'],
        'helmetKit': p['helmetKit']['id'], 'capeKit': p['capeKit']['id'], 'armorPassive': p['armorPassive'],
        'helmetPassive': p['helmetPassive'], 'kitPassive': p['armorKit']['kitPassive']}
    kits = _kits(d, passives)
    by_kit_id = {k['id']: k for k in kits}
    for snap in d['snapshots']:
        for player in snap['players']:
            for kind in ('armorKit', 'helmetKit', 'capeKit'):
                kit = by_kit_id.get(player[kind]['id'])
                if not kit or (player[kind].get('name') and kit.get('name') != player[kind]['name']):
                    raise ValueError('snapshot kit %s is not the kit table\'s' % player[kind]['id'])
    # Keys every EntityAttribute site of which reads the armor slot only (flags 1).
    armor_only = {k for k, v in flags_one.items() if set(v) == set(keys[k]['entityAttributeSites'])}
    _effects(d, passives, armor_only)
    # The live-proven armor-slot swaps (schemas/live_evidence.json, family player_armor_passive_swap): those passive ids
    # need no allow_unverified_effect for the armor slot alone.
    import live_evidence
    swap = live_evidence.family('player_armor_passive_swap')
    live = {'armorSwap': sorted(swap.get('passives', [])) if swap['status'] == 'live_proven' else [],
        'evidence': live_evidence.proven('player_armor_passive_swap')}
    return {'live': live, 'source': {'research': RESEARCH.name, 'build': d['build'], 'gameDllSha256': d['gameDll']},
        'manager': dict(LAYOUT, globalRva=d['globals']['customizationManager']), 'record': RECORD, 'kit': KIT,
        'passive': PASSIVE, 'modifier': MODIFIER, 'types': TYPES, 'passives': passives, 'unused': unused,
        'keys': key_table,
        'flagsOne': [{'key': k, 'name': KEY_NAMES.get(k, 'unknown_' + k.lower()), 'sites': v}
            for k, v in sorted(flags_one.items())],
        'computedFlags': [{'key': k, 'name': KEY_NAMES.get(k, 'unknown_' + k.lower()), 'sites': v}
            for k, v in sorted(computed.items())],
        'observed': observed, 'kits': kits, 'slots': ['armor', 'helmet', 'cape'], 'weights': ['light', 'medium', 'heavy'],
        'readers': READERS, 'pins': pins}


def _utf8(value):
    """The game's text as Lua byte strings: a non-ASCII string (e.g. a kit description's U+2019) becomes its UTF-8
    bytes, which reference_format.lua writes as byte escapes (Lua has no \\uXXXX escape)."""
    if isinstance(value, dict):
        return {k: _utf8(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_utf8(v) for v in value]
    if isinstance(value, str) and not value.isascii():
        return value.encode('utf-8')
    return value


def outputs() -> dict[str, str]:
    return {OUTPUT: '-- Generated by scripts/generate_player_passives.py; do not edit.\nreturn ' + lua(_utf8(build()))
        + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale generated player passives domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
