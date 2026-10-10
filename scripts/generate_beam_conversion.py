"""Generate domains/beam_conversion.lua and sdk/BeamConversionCapabilities.json: the catalogue of beam conversions
(a projectile weapon fires LAS-13 Trident pulses, solo only; docs/beam-conversion.md) that runtime/beam_conversion.lua
applies through hd2.weapon(name):beam_conversion() (domains/beam_conversion_writes.lua).

Sources (read-only research, never trusted at run time without re-proof):
  * research/beam-conversion-coverage-F5FEE03DCFDB.json (research/docs/beam-conversion-coverage-F5FEE03DCFDB.md):
    every player primary, secondary and support weapon classified (supported / supported with caveats / refused, with
    the reason code), each root to convert with its exact write set (membership list window, ProjectileWeapon row kept,
    chamber magazine byte), the BeamWeapon table's vanilla rows and record 23, the donor record, and its code pins;
  * domains/beam_swap.lua (scripts/generate_beam_swap.py): the live-proven Liberator / Talon / Reprimand pins and the
    entity manager layout (the descriptor census, the entity map slot);
  * domains/beam_table.lua (scripts/generate_beam_table.py): the owned-table relocation pins (slot 270 readers, the
    lookup's capacity and record base, the default record sites);
  * research/beam-pulse-rate-F5FEE03DCFDB.json: the pulse / rate model the settings ranges follow.
Every live-proven write set (the three experiment weapons) must equal its coverage entry byte for byte.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402
import generate_beam_swap  # noqa: E402
import generate_beam_table  # noqa: E402

COVERAGE = ROOT / 'research/beam-conversion-coverage-F5FEE03DCFDB.json'
ROWS = ROOT / 'research/beam-rows-borrowed-F5FEE03DCFDB.json'
DAMAGE = ROOT / 'research/beam-damage-per-weapon-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/beam_conversion.lua'
CAPABILITIES = ROOT / 'sdk/BeamConversionCapabilities.json'
TRIDENT = '0x3C86E871923F3970'
TRIDENT_DEPENDENCY = 'player_weapon/LAS-13 Trident'
LIVE_PROVEN = {'AR-23 Liberator', 'LAS-58 Talon', 'SMG-32 Reprimand'}
MAX_COPIES = 16
MIN_FREE_ROWS = 1          # one row always stays empty (a miss stops at it instead of probing all 46)
# Pulse settings of a converted weapon's own record (BeamWeapon +104 / +108 / +112; scripts/equipment_fields.py
# PULSE_FIELDS members). The rate stops at 900 rpm: in the live test (2026-10-10) 900 rpm was the fastest rate whose
# beam was still visible ("at 1200 it's like a fast yellow projectile"); the pulse never goes below 1/30 s rounded up
# (a pulse no longer than one frame deals no damage: 30 fps is the lowest frame rate the fit covers).
SETTINGS = (
    {'id': 'fire_rate', 'field': 'beam.fire_rate', 'offset': 104, 'storage': 'i32', 'min': 1, 'max': 900,
     'unit': 'rpm', 'displayName': 'Beam fire rate (pulses per minute)',
     'rangeReason': 'at most 900 rpm: the fastest rate whose beam was still visible in the live test (2026-10-10); '
                    'every rate is capped by beam.pulse_seconds'},
    {'id': 'pulse_beams', 'field': 'beam.pulse_beams', 'offset': 108, 'storage': 'i32', 'min': 1, 'max': 8,
     'unit': 'beams', 'displayName': 'Beams per pulse'},
    {'id': 'pulse_seconds', 'field': 'beam.pulse_seconds', 'offset': 112, 'storage': 'f32', 'min': 0.0334, 'max': 2,
     'unit': 'seconds', 'displayName': 'Pulse duration (limits the fire rate)',
     'rangeReason': 'at least 0.0334 s: a pulse no longer than one frame deals no damage (30 fps); the next pulse '
                    'starts only the update after this one ended, so it caps beam.fire_rate'},
)


# Per-weapon beam and damage rows (research/docs/beam-rows-borrowed-F5FEE03DCFDB.md): members of the converted weapon's
# OWN BeamInfo row copy (a borrowed spare BeamType) and DamageInfo row copy (a borrowed spare DamageInfo id); BeamFire
# copies them into every shot. Defaults are the Trident's row 6 / row 508. +0x1C/+0x20/+0x24 keep the names the Runtime
# already publishes for them (damage.demolition / stagger / push_force: leads, the research reads them into the hit).
ROW_FIELDS = (
    {'id': 'beam.length', 'row': 'beam', 'offset': 8, 'storage': 'f32', 'min': 1, 'max': 1000, 'unit': 'meters',
     'displayName': 'Beam range (length)',
     'proof': 'BeamInfo +8 -> shot +0x44: the ray query length, the sweep end and the drawn-length clamp (CONFIRMED)'},
    {'id': 'damage.standard_damage', 'row': 'damage', 'offset': 4, 'storage': 'i32', 'min': 0, 'max': 10000,
     'unit': 'damage', 'displayName': 'Standard damage per pulse hit'},
    {'id': 'damage.durable_damage', 'row': 'damage', 'offset': 8, 'storage': 'i32', 'min': 0, 'max': 10000,
     'unit': 'damage', 'displayName': 'Durable damage per pulse hit'},
    {'id': 'damage.ap_direct', 'row': 'damage', 'offset': 12, 'storage': 'u32', 'min': 0, 'max': 10,
     'unit': 'armor_class', 'displayName': 'Armor penetration: direct'},
    {'id': 'damage.ap_slight', 'row': 'damage', 'offset': 16, 'storage': 'u32', 'min': 0, 'max': 10,
     'unit': 'armor_class', 'displayName': 'Armor penetration: slight angle'},
    {'id': 'damage.ap_large', 'row': 'damage', 'offset': 20, 'storage': 'u32', 'min': 0, 'max': 10,
     'unit': 'armor_class', 'displayName': 'Armor penetration: large angle'},
    {'id': 'damage.ap_extreme', 'row': 'damage', 'offset': 24, 'storage': 'u32', 'min': 0, 'max': 10,
     'unit': 'armor_class', 'displayName': 'Armor penetration: extreme angle'},
    {'id': 'damage.demolition', 'row': 'damage', 'offset': 28, 'storage': 'u32', 'min': 0, 'max': 1000,
     'unit': 'force', 'displayName': 'Demolition'},
    {'id': 'damage.stagger', 'row': 'damage', 'offset': 32, 'storage': 'u32', 'min': 0, 'max': 1000,
     'unit': 'force', 'displayName': 'Stagger'},
    {'id': 'damage.push_force', 'row': 'damage', 'offset': 36, 'storage': 'u32', 'min': 0, 'max': 1000,
     'unit': 'force', 'displayName': 'Push force'},
)


def _trident_rows() -> tuple[bytes, bytes]:
    t = json.loads(DAMAGE.read_text(encoding='utf-8'))['donors']['LAS-13 Trident']
    return bytes.fromhex(t['beam']['bytes']), bytes.fromhex(t['damage']['bytes'])


def rows_domain() -> dict:
    """The borrowed per-weapon rows: the spare pairs, their pinned vanilla rows, the Trident donors, the pins."""
    r = json.loads(ROWS.read_text(encoding='utf-8'))
    if r['writes'] or r['protectionChanges'] or r['build'] != 'F5FEE03DCFDB':
        raise ValueError('the borrowed rows research must be read-only research of build F5FEE03DCFDB')
    for name, mismatches in r['pinnedBytesMismatchPerSnapshot'].items():
        if mismatches:
            raise ValueError('a borrowed rows pin differs in snapshot ' + name)
    if len(r['pinnedBytesMismatchPerSnapshot']) < 9:
        raise ValueError('the borrowed rows pins must be checked in every retained snapshot')
    if not r['verdict']['optionA'].startswith('STRONG'):
        raise ValueError('option (a) is not STRONG')
    dmg = json.loads(DAMAGE.read_text(encoding='utf-8'))
    beam6, dmg508 = _trident_rows()
    beams = {b['beamType']: b for b in r['spare']['beamTypes']}
    damages = {d['id']: d for d in r['spare']['damageIds']}
    pairs = []
    for p in r['allocation']['pairs']:
        k, d = p['beamType'], p['damageInfo']
        bt, dm = beams[k], damages[d]
        if bt['proof'] != 'STRONG' or dm['proof'] != 'STRONG':
            raise ValueError(f'pair ({k}, {d}) is not STRONG')
        if bt['fileRow']['key'] != k or dm['fileRow']['key'] != d:
            raise ValueError(f'pair ({k}, {d}) keys')
        pairs.append({'beamType': k, 'damageInfo': d, 'beamHex': bt['fileRow']['bytes'],
                      'damageHex': dm['fileRow']['bytes']})
    for o in r['observations']:
        if o['beamArrayRegion'] != {'protect': '0x4', 'type': '0x1000000'} or o['damageArrayRegion'] != {
                'protect': '0x4', 'type': '0x1000000'}:
            raise ValueError(o['snapshot'] + ': the pointer arrays are not read-write image memory')
    if int.from_bytes(beam6[0:4], 'little') != 6 or int.from_bytes(beam6[12:16], 'little') != 508 \
            or int.from_bytes(dmg508[0:4], 'little') != 508:
        raise ValueError('the Trident donor rows are not row 6 naming 508')
    arrays = r['arrays']
    pins = []
    for group, rows in r['proofs'].items():
        for pin in rows:
            pins.append({'rva': pin['rva'], 'hex': pin['bytes'], 'label': 'beam rows: ' + group + ': ' + pin['role']})
    ring = dmg['ring']
    return {'research': ROWS.name, 'build': r['build'], 'gameDllSha256': r['gameDllSha256'],
            'labels': ['interim', 'borrowedVanillaRow', 'buildScoped', 'soloOnly'],
            'beamTable': {'rva': int(arrays['beamInfo']['table'], 16), 'slots': arrays['beamInfo']['slots'],
                          'stride': arrays['beamInfo']['stride']},
            'damageTable': {'rva': int(arrays['damageInfo']['table'], 16), 'slots': arrays['damageInfo']['slots'],
                            'stride': arrays['damageInfo']['stride']},
            'tridentBeamHex': beam6.hex(), 'tridentDamageHex': dmg508.hex(),
            'tridentBeamType': 6, 'tridentDamageInfo': 508, 'pairs': pairs,
            'ring': {'global': int(ring['system']['global'], 16), 'base': ring['base'], 'stride': ring['stride'],
                     'slots': ring['slots'], 'alive': ring['entry']['alive'], 'beamType': ring['entry']['beamType'],
                     'damageInfo': ring['entry']['damageInfo']},
            'magic': 'HD2RT-BEAM-ROWS1', 'pins': pins}


def row_fields() -> list[dict]:
    import struct
    beam, damage = _trident_rows()
    out = []
    for f in ROW_FIELDS:
        raw = (beam if f['row'] == 'beam' else damage)[f['offset']:f['offset'] + 4]
        value = struct.unpack({'f32': '<f', 'i32': '<i', 'u32': '<I'}[f['storage']], raw)[0]
        item = {'id': f['id'], 'row': f['row'], 'displayName': f['displayName'],
                'type': 'number' if f['storage'] == 'f32' else 'integer', 'unit': f['unit'], 'storage': f['storage'],
                'default': round(value, 6) if f['storage'] == 'f32' else value, 'min': f['min'], 'max': f['max'],
                'offset': f['offset'], 'perWeapon': True,
                'note': ('the converted weapon\'s own %s row (a borrowed spare row: owned table path only, at most 6 '
                         'weapons with own rows at once); written at once, applies from the next pulse') % (
                            'BeamInfo' if f['row'] == 'beam' else 'DamageInfo')}
        if f.get('proof'):
            item['proof'] = f['proof']
        out.append(item)
    return out


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _root_set(w: dict) -> list[dict]:
    """Every root to convert with its write set (the coverage's rootsToSwap: the loadout root first)."""
    sets = w.get('rootsToSwap')
    if not sets:
        raise ValueError(w['name'] + ': a supported weapon names no root to convert')
    if sets[0]['resource'] != w['resource']:
        raise ValueError(w['name'] + ': the first root to convert is not the catalogue root')
    return sets


def _root(w: dict, s: dict) -> dict:
    m = s['membership']
    name, resource = w['name'], s['resource']
    if not (m.get('sortedAfter', True) and m.get('uniqueAfter', True) and m.get('countUnchanged', True)):
        raise ValueError(name + ': the converted list is not sorted, unique and of the same count')
    before = bytes.fromhex(m['beforeHex'])
    after = bytes.fromhex(m['afterHex'])
    entries = lambda raw: [int.from_bytes(raw[i:i + 2], 'little') for i in range(0, len(raw), 2)]
    eb, ea = entries(before), entries(after)
    if 321 not in eb or 270 in eb or 270 not in ea or 321 in ea or len(eb) != len(ea) or ea != sorted(set(ea)):
        raise ValueError(name + ': the list change is not ProjectileWeapon -> BeamWeapon')
    if int(resource, 16) & 0xFFF != m['home']:
        raise ValueError(name + ': the entity map home is not resource & 0xFFF')
    first, end = m['changedByteRange']
    proj = s['projectileRowKept']
    if proj.get('owners') not in (None, [resource]):
        raise ValueError(name + ': its ProjectileWeapon record is shared (the row is kept, never written)')
    mag = s.get('magazine')
    magazine = None
    if mag and mag.get('chamber156', 1 if mag.get('before') == '01000000' else 0) == 1:
        if mag['owners'] != [resource]:
            raise ValueError(name + ': its chamber magazine record is shared: the conversion must be refused')
        if mag['before'] != '01000000' or mag['after'] != '00000000':
            raise ValueError(name + ': the chamber window is not 01000000 -> 00000000')
        if mag['windowOffset'] != 8640 + 160 * mag['record'] + 156:
            raise ValueError(name + ': the magazine window offset')
        le = bytes.fromhex(resource[2:].rjust(16, '0'))[::-1].hex()
        if mag['rowBytes'] != le + mag['record'].to_bytes(4, 'little').hex() + '0' * 8:
            raise ValueError(name + ': the magazine row bytes do not name the root and its record')
        magazine = {'row': mag['row'], 'home': mag['home'], 'record': mag['record'], 'rowBytes': mag['rowBytes'],
                    'windowOffset': mag['windowOffset'], 'before': mag['before'], 'after': mag['after']}
    if int(resource, 16) % 46 != s['beam']['home']:
        raise ValueError(name + ': the BeamWeapon home is not resource mod 46')
    return {'resource': '0x%016X' % int(resource, 16),
            'membership': {'row': m['entitySettingsRow'], 'home': m['home'], 'count': m['count'],
                           'networkType': int(m['networkType'], 16), 'listOffsetInBody': m['listOffsetInBody'],
                           'before': m['beforeHex'], 'after': m['afterHex'], 'firstChanged': first, 'endChanged': end},
            'beamHome': s['beam']['home'],
            'projectile': {'row': proj['row'], 'record': proj['record']},
            'magazine': magazine}


def _pins(coverage: dict, swap: dict, table: dict) -> list[dict]:
    pins: dict[int, dict] = {}

    def add(rva: int, hexbytes: str, label: str) -> None:
        if rva in pins:
            if pins[rva]['hex'] != hexbytes:
                raise ValueError(f'conflicting pin bytes at 0x{rva:X}')
            return
        pins[rva] = {'rva': rva, 'hex': hexbytes, 'label': label}
    for pin in swap['pins']:
        add(pin['rva'], pin['hex'], pin['label'])
    for pin in table['pins']:
        add(pin['rva'], pin['hex'], pin['label'])
    groups = coverage['pins']
    for group, rows in (groups.items() if isinstance(groups, dict) else [('coverage', groups)]):
        for pin in rows:
            add(pin['rva'], pin['bytes'], 'coverage: ' + group.split(':')[0] + ': ' + pin['role'])
    return [pins[rva] for rva in sorted(pins)]


def build() -> dict:
    coverage = json.loads(COVERAGE.read_text(encoding='utf-8'))
    if coverage['writes'] or coverage['protectionChanges'] or coverage['build'] != 'F5FEE03DCFDB':
        raise ValueError('the coverage research must be read-only research of build F5FEE03DCFDB')
    for name, mismatches in coverage['pinnedBytesMismatchPerSnapshot'].items():
        if mismatches:
            raise ValueError('a coverage pin differs in snapshot ' + name)
    swap = generate_beam_swap.build()
    table = generate_beam_table.build()
    if coverage['gameDllSha256'] != swap['source']['gameDllSha256'] != table['source']['gameDllSha256']:
        raise ValueError('the research covers different game.dll builds')
    donor = coverage['donor']
    if donor['resource'] != TRIDENT or donor['beamRow'] != 20 or donor['record'] != 18 or donor['mode100'] != 6:
        raise ValueError('the donor is not the Trident\'s row 20 / record 18 in mode 6')
    beam_table = coverage['beamTable']
    rows_hex = beam_table['rowsHex']
    if len(rows_hex) != 46 * 32:
        raise ValueError('the vanilla BeamWeapon rows are not 46 x 16 bytes')
    rows = bytes.fromhex(rows_hex)
    empty = [r for r in range(46) if rows[r * 16:r * 16 + 8] == bytes(8)]
    if empty != beam_table['emptyRows']:
        raise ValueError('the vanilla rows disagree with the empty-row census')
    trident_row = rows[20 * 16:21 * 16]
    if trident_row[:8] != bytes.fromhex(TRIDENT[2:])[::-1] or int.from_bytes(trident_row[8:12], 'little') != 18:
        raise ValueError('vanilla row 20 is not the Trident\'s')
    swap_by_name = {w['name']: w for w in swap['weapons']}
    weapons, seen = [], set()
    record = 24
    for w in sorted(coverage['weapons'] + coverage['outOfScope'], key=lambda x: (x['kind'], x['name'])):
        name = w['name']
        if name in seen:
            raise ValueError('duplicate catalogue name ' + name)
        seen.add(name)
        supported = w['verdict'] in ('supported', 'supported_with_caveats')
        entry = {'id': slug(name), 'name': name, 'kind': w['kind'], 'resource': '0x%016X' % int(w['resource'], 16) if w.get('resource') else None,
                 'supported': supported, 'verdict': w['verdict'], 'reasonCode': w['reasonCode'], 'reason': w['reason'],
                 'caveats': [{'code': c['code'], 'text': c['text']} for c in w.get('caveats', [])],
                 'confidence': w.get('confidence'), 'liveProven': name in LIVE_PROVEN}
        if supported:
            roots = [_root(w, s) for s in _root_set(w)]
            entry['roots'] = roots
            entry['record'] = record
            record += 1
            entry['restartAfterUse'] = bool(w.get('writeSet', {}).get('restartAfterUse')
                                            or w['customization']['defaultDeltasPatchingProjectileWeapon'])
            if w.get('package'):
                entry['package'] = w['package'].get('name')
            if w.get('heat'):
                entry['heat'] = {'record': w['heat']['record'], 'heatPerPulse': w['heat'].get('heatPerShot116')}
            proven = swap_by_name.get(name)
            if proven:
                main = roots[0]
                if (main['membership']['before'] != proven['membership']['before']
                        or main['membership']['after'] != proven['membership']['after']
                        or main['membership']['row'] != proven['membership']['row']
                        or (proven['magazine'] or {}).get('windowOffset') != (main['magazine'] or {}).get(
                            'windowOffset')):
                    raise ValueError(name + ': the coverage write set differs from the live-proven one')
        weapons.append(entry)
    if not LIVE_PROVEN <= {w['name'] for w in weapons if w['supported']}:
        raise ValueError('a live-proven weapon is not supported in the coverage')
    resources = [r['resource'] for w in weapons if w['supported'] for r in w['roots']]
    if len(resources) != len(set(resources)):
        raise ValueError('one root resource belongs to two catalogued weapons')
    records = record
    bw = swap['beam']
    domain = {
        'source': {'coverage': COVERAGE.name, 'build': coverage['build'], 'gameDllSha256': coverage['gameDllSha256']},
        'trident': {'resource': TRIDENT, 'row': 20, 'record': 18, 'recordHex': donor['bytes'],
                    'dependency': TRIDENT_DEPENDENCY},
        'donor': {'name': 'LAS-13 Trident', 'mode': 6, 'package': donor.get('package')},
        'manager': swap['manager'],
        'beam': {'component': bw['component'], 'index': bw['index'], 'capacity': bw['capacity'],
                 'rowStride': bw['rowStride'], 'fileRecords': bw['records'], 'recordBase': bw['recordBase'],
                 'recordStride': bw['recordStride'], 'defaultRecord': bw['record'],
                 'vanillaRowsHex': rows_hex, 'vanillaRecord23Hex': beam_table['record23Hex']},
        'membership': swap['membership'],
        'projectile': swap['projectile'],
        'magazine': swap['magazine'],
        'copy': {'framing': 32, 'magic': 'HD2RT-BEAM-CONV1', 'trailerSize': 32, 'maxCopies': MAX_COPIES,
                 'records': records, 'minFreeRows': MIN_FREE_ROWS, 'emptyRows': len(empty)},
        'settings': [{k: s[k] for k in ('id', 'field', 'offset', 'storage', 'min', 'max', 'unit')} for s in SETTINGS],
        'fields': fields(donor) + row_fields(),
        'rows': rows_domain(),
        'acknowledgements': ['allow_component_swap', 'allow_unverified_effect'],
        'lifecycle': lifecycle(),
        'multiplayer': multiplayer(),
        'pulse': pulse(),
        'weapons': weapons,
        'pins': _pins(coverage, swap, table),
    }
    if domain['beam']['vanillaRecord23Hex'] != swap['beam']['recordBefore']:
        raise ValueError('record 23 differs from the live-proven record 23')
    if donor['bytes'] != swap['beam']['recordAfter']:
        raise ValueError('the donor record differs from the live-proven Trident copy')
    return domain


def _donor_value(donor_hex: str, offset: int, storage: str):
    import struct
    raw = bytes.fromhex(donor_hex)[offset:offset + 4]
    return struct.unpack('<f' if storage == 'f32' else '<i', raw)[0]


def fields(donor: dict) -> list[dict]:
    out = [{'id': 'beam_conversion.enabled', 'displayName': 'Fires LAS-13 Trident pulses (beam conversion)',
            'type': 'boolean', 'default': False,
            'note': 'false = the weapon as shipped. true: from its next spawn the weapon fires Trident pulses (its '
                    'ProjectileWeapon component out, BeamWeapon in); written only with zero live instances of it, solo '
                    'only; restart the game after using it.'}]
    for s in SETTINGS:
        value = _donor_value(donor['bytes'], s['offset'], s['storage'])
        if s['storage'] == 'f32':
            value = round(value, 6)
        item = {'id': s['field'], 'setting': s['id'], 'displayName': s['displayName'], 'type':
                'integer' if s['storage'] == 'i32' else 'number', 'unit': s['unit'], 'storage': s['storage'],
                'default': value, 'min': s['min'], 'max': s['max'], 'offset': s['offset']}
        if s.get('rangeReason'):
            item['rangeReason'] = s['rangeReason']
        out.append(item)
    out[1]['note'] = ('the converted weapon\'s OWN rate (owned table path); without beam.pulse_seconds in the same '
                      'request the pulse is fitted to the rate')
    out[3]['note'] = ('how long a pulse lasts; a new pulse starts only the update after the last one ended, so it caps '
                      'the rate: n = max(ceil(60 / (rate x dt)), max(1, ceil(pulse / dt)) + 1)')
    return out


def lifecycle() -> dict:
    return {'appliesWhen': 'weapon_spawn',
            'liveInstances': 'written only while ZERO instances of every converted root exist on this machine (the '
                             'ship preview, the armory, any loadout, pickups, other players\' weapons of that type): '
                             'otherwise the request waits (TARGET_UNAVAILABLE: BUSY; an ensure with recover keeps '
                             'trying)',
            'settings': 'rate / beams / pulse of a converted weapon are written at once (read at every shot)',
            'restartAfterUse': 'restart the game after using a conversion: a weapon spawned while converted may leave a '
                               'ProjectileWeapon private copy nothing removes',
            'assets': 'the LAS-13 Trident\'s package (laser_shotgun) is loaded and held before any write',
            'table': 'a Runtime-owned copy of the BeamWeapon table (never freed; at most %d per game process); a '
                     'table another mod moved is refused (True Lasgun Beam Overhaul)' % MAX_COPIES,
            'fallback': 'without the owned table: the shared record 23 (every converted weapon fires the Trident\'s '
                        'own rate and pulse; other settings refused)'}


def multiplayer() -> dict:
    return {'apply': 'solo only: refused (waits) while another player is in the game or the lobby',
            'restore': 'allowed with other players present (it makes this machine agree with them)',
            'join': 'docs/beam-conversion.md "Multiplayer": a player who joins later builds the weapon as shipped; the '
                    'Runtime logs a loud warning and shows a notice, and changes nothing by itself',
            'research': 'research/docs/beam-conversion-mp-F5FEE03DCFDB.md'}


def pulse() -> dict:
    return {'formula': 'n = max(ceil(60 / (fire_rate x dt)), max(1, ceil(pulse_seconds / dt)) + 1); '
                       'rpm = 60 / (n x dt)',
            'fit': 'without beam.pulse_seconds: the Trident\'s 0.15 s when it fits, else max(60 / (2 rate), '
                   '60 / rate - 1/30) s, never below 0.0334 s',
            'recommendedMaxRpm': 900,
            'research': 'research/docs/beam-pulse-rate-F5FEE03DCFDB.md'}


def per_weapon_rows(domain: dict) -> dict:
    rows = domain['rows']
    return {'fields': [f['id'] for f in domain['fields'] if f.get('row')], 'capacity': len(rows['pairs']),
            'labels': rows['labels'], 'build': rows['build'],
            'pairs': [{'beamType': p['beamType'], 'damageInfo': p['damageInfo']} for p in rows['pairs']],
            'how': 'each converted weapon with non-Trident damage, AP or range borrows a spare BeamType and DamageInfo '
                   'id whose slots point at Runtime-owned copies of the Trident rows 6 / 508 (never the vanilla rows); '
                   'BeamFire copies them into every shot',
            'refusals': ['ROWS_FULL (more than %d at once)' % len(rows['pairs']), 'BORROWED_ROWS_UNVERIFIED_BUILD',
                         'SHARED_RECORD_FALLBACK'],
            'research': 'research/docs/beam-rows-borrowed-F5FEE03DCFDB.md'}


def capabilities(domain: dict) -> dict:
    out = {'schemaVersion': 1, 'contract': 'hd2.weapon(name):beam_conversion() / hd2.support_weapon(name):'
           'beam_conversion(); hd2.ensure transaction; allow_component_swap and allow_unverified_effect',
           'docs': 'docs/beam-conversion.md', 'research': 'research/docs/beam-conversion-coverage-F5FEE03DCFDB.md',
           'donor': domain['donor'], 'fields': domain['fields'], 'acknowledgements': domain['acknowledgements'],
           'lifecycle': domain['lifecycle'], 'multiplayer': domain['multiplayer'], 'pulse': domain['pulse'],
           'perWeaponRows': per_weapon_rows(domain), 'summary': {}, 'weapons': []}
    counts: dict[str, int] = {}
    for w in domain['weapons']:
        counts[w['verdict']] = counts.get(w['verdict'], 0) + 1
        item = {k: w[k] for k in ('name', 'kind', 'supported', 'verdict', 'reasonCode', 'reason', 'caveats',
                                  'liveProven')}
        item['target'] = ('hd2.support_weapon' if w['kind'] == 'support' else 'hd2.weapon') + \
            '(%s):beam_conversion()' % json.dumps(w['name'])
        if w['supported']:
            item['roots'] = [r['resource'] for r in w['roots']]
            item['restartAfterUse'] = w['restartAfterUse']
            item['chamberFix'] = any(r['magazine'] for r in w['roots'])
            if w.get('heat'):
                item['heatPerPulse'] = w['heat']['heatPerPulse']
        out['weapons'].append(item)
    out['summary'] = {'weapons': len(domain['weapons']), 'verdicts': counts,
                      'emptyBeamRows': domain['copy']['emptyRows'],
                      'maxSimultaneous': domain['copy']['emptyRows'] - domain['copy']['minFreeRows']}
    return out


def outputs() -> dict[str, str]:
    domain = build()
    return {'domains/beam_conversion.lua': '-- Generated by scripts/generate_beam_conversion.py; do not edit.\n'
            'return ' + lua(domain) + '\n',
            'sdk/BeamConversionCapabilities.json': json.dumps(capabilities(domain), indent=2) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale beam conversion domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
