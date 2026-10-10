"""Generate domains/beam_swap.lua: the EXPERIMENTAL, SOLO-ONLY multi-weapon beam swap (the AR-23 Liberator, LAS-58 Talon
and SMG-32 Reprimand fire LAS-13 Trident pulses, together or in any subset) that runtime/experiment_beam_swap.lua
applies for the MultiBeamProof live test.

Sources (read-only research, never trusted at run time without re-proof):
  * research/multi-beam-swap-F5FEE03DCFDB.json (research/docs/multi-beam-swap-F5FEE03DCFDB.md): the per-weapon write
    sets (membership lists, BeamWeapon rows 21 / 11 / 25, the Liberator's and the Reprimand's magazine chamber bytes),
    the shared record 23, the offline overlay of every subset, the snapshot checks and 32 code pins (record sharing,
    the beam manager's growth, the Talon's instance-guarded paths);
  * research/component-swap-liberator-beam-F5FEE03DCFDB.json and research/liberator-beam-chamber-F5FEE03DCFDB.json:
    the live-proven Liberator swap (its 63 + 69 pins and its write set, which the Liberator entry here must equal);
  * research/component-membership-F5FEE03DCFDB.json: the loader, spawn and destroy pins;
  * scripts/generate_liberator_beam.py EXTRA_PINS: the lookups and descriptor writes the module re-derives addresses from.

NOT a Runtime feature: not exported by api/hd2.lua, not part of the 0.30.x line (branch exp/multi-beam only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402
import generate_liberator_beam as liberator  # noqa: E402

MULTI = ROOT / 'research/multi-beam-swap-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/beam_swap.lua'
ORDER = ('liberator', 'talon', 'reprimand')      # write order; restore runs in reverse
RESOURCES = {'liberator': '0x968211C0033DCE64', 'talon': '0x416D053372C4E433', 'reprimand': '0x94BD931B5FB4EE95'}
NAMES = {'liberator': 'AR-23 Liberator', 'talon': 'LAS-58 Talon', 'reprimand': 'SMG-32 Reprimand'}
TRIDENT = liberator.TRIDENT


def _le(resource: str) -> str:
    return bytes.fromhex(resource[2:])[::-1].hex()


def build() -> dict:
    multi = json.loads(MULTI.read_text(encoding='utf-8'))
    if multi['writes'] or multi['protectionChanges'] or multi['build'] != 'F5FEE03DCFDB':
        raise ValueError('the multi-beam research must be read-only research of build F5FEE03DCFDB')
    for name, mismatches in multi['pinnedBytesMismatchPerSnapshot'].items():
        if mismatches:
            raise ValueError('a multi-beam pin differs in snapshot ' + name)
    proven = liberator.build()          # the live-proven Liberator domain: its checks run too
    swap = json.loads(liberator.SWAP.read_text(encoding='utf-8'))
    chamber = json.loads(liberator.CHAMBER.read_text(encoding='utf-8'))
    membership = json.loads(liberator.MEMBERSHIP.read_text(encoding='utf-8'))
    shared = multi['sharedRecord']
    record = shared['beamRecord']
    if record['record'] != 23 or record['offset'] != 0xDA8 or record['size'] != 120 or record['ownersBefore']:
        raise ValueError('record 23 is not the unowned 120-byte default record at +0xDA8')
    if record['before'] != swap['writeSet']['record']['before'] or record['after'] != swap['writeSet']['record']['after']:
        raise ValueError('record 23 bytes differ from the live-proven Liberator write set')
    if shared['vanillaCensus']['recordsSharedByTwoOrMoreRows'] != 0 or shared['defaultRecordGetter'][
            'directCallsOrJumps'] != 0:
        raise ValueError('the record-sharing census changed')
    for key, subset in multi['overlay']['subsets'].items():
        if not (subset['onlyTargetsChange'] and subset['targetsFindRecord23'] and subset['otherRecordsByteIdentical']):
            raise ValueError('the offline overlay of ' + key + ' changes another lookup')
    if len(multi['overlay']['subsets']) != 8:
        raise ValueError('the overlay must cover every subset of the three weapons')
    weapons, rows_used = [], set()
    for key in ORDER:
        w = multi['weapons'][key]
        if w['resource'] != RESOURCES[key] or w['name'] != NAMES[key]:
            raise ValueError(key + ': resource or name changed')
        m, beam = w['membership'], w['beam']
        if not (m['sortedAfter'] and m['uniqueAfter'] and m['countUnchanged']):
            raise ValueError(key + ': the list after the swap is not sorted, unique and of the same count')
        if 321 not in m['before'] or 270 in m['before'] or 270 not in m['after'] or 321 in m['after']:
            raise ValueError(key + ': the list swap is not ProjectileWeapon -> BeamWeapon')
        if int(RESOURCES[key], 16) & 0xFFF != m['home'] or m['probe'][-1] != m['entitySettingsRow']:
            raise ValueError(key + ': the EntitySettings row is not the game\'s probe result')
        if int(RESOURCES[key], 16) % 46 != beam['home'] or beam['row'] != beam['firstEmptyOnPath']:
            raise ValueError(key + ': the BeamWeapon row is not the first empty row on the probe path')
        if beam['before'] != '0' * 32 or beam['after'] != _le(RESOURCES[key]) + '17000000' + '0' * 8:
            raise ValueError(key + ': the BeamWeapon row bytes changed')
        if beam['row'] in rows_used:
            raise ValueError('two weapons use one BeamWeapon row')
        rows_used.add(beam['row'])
        if w['projectileRowKept']['owners'] != [RESOURCES[key]]:
            raise ValueError(key + ': the ProjectileWeapon record is not its own')
        first, last = m['changedByteRange']
        mag = w['magazine']
        if mag is not None:
            if mag['owners'] != [RESOURCES[key]] or mag['probe'][-1]['row'] != mag['row'] or mag['before'] != '01000000' \
                    or mag['after'] != '00000000' or mag['plus157'] != 0:
                raise ValueError(key + ': the magazine record is not its own chamber record')
            if mag['rowBytes'] != _le(RESOURCES[key]) + mag['record'].to_bytes(4, 'little').hex() + '0' * 8:
                raise ValueError(key + ': the magazine row bytes do not name the weapon and its record')
            if mag['windowOffset'] != 8640 + 160 * mag['record'] + 156:
                raise ValueError(key + ': the magazine window offset changed')
            if w['customization']['deltasTouchingMagazine156']:
                raise ValueError(key + ': a customization delta writes the chamber flag')
            if w['afterNotInMeltagun']:
                raise ValueError(key + ': the swapped weapon is not a subset of the 40-K Meltagun')
        elif w['afterNotInTrident']:
            raise ValueError(key + ': a heat weapon after the swap must be a subset of the Trident')
        if w['customization']['deltasPatchingBeamWeapon']:
            raise ValueError(key + ': a customization delta patches BeamWeapon')
        for name, snap in multi['snapshots'].items():
            s = snap['weapons'][key]
            if not (s['row'] == '0' * 32 and s['listAsBefore'] and s['listPointerInsideTableAllocation']
                    and s['listProtect'] == '0x2' and not s['listWindowCrossesPage']):
                raise ValueError(key + ': snapshot ' + name + ' does not hold the reviewed before state')
            if mag is not None and not (s['magazineRow'] == mag['rowBytes'] and s['magazineWindow'] == '01000000'):
                raise ValueError(key + ': snapshot ' + name + ' does not hold the reviewed magazine bytes')
        entry = {'id': key, 'name': NAMES[key], 'resource': RESOURCES[key],
                 'beam': {'home': beam['home'], 'row': beam['row'], 'rowOffset': beam['offset'],
                          'rowBefore': beam['before'], 'rowAfter': beam['after']},
                 'membership': {'row': m['entitySettingsRow'], 'home': m['home'], 'count': m['count'],
                                'networkType': int(m['networkType'], 16), 'listOffsetInBody': m['listOffsetInBody'],
                                'before': m['beforeHex'], 'after': m['afterHex'], 'firstChanged': first,
                                'endChanged': last},
                 'projectile': {'row': w['projectileRowKept']['row'], 'record': w['projectileRowKept']['record']},
                 'magazine': None if mag is None else {'row': mag['row'], 'home': mag['home'], 'record': mag['record'],
                                                       'rowBytes': mag['rowBytes'], 'windowOffset': mag['windowOffset'],
                                                       'before': mag['before'], 'after': mag['after']},
                 'restartAdvice': bool(w['customization']['defaultDeltasPatchingProjectileWeapon']
                                       or w['customization']['optionDeltasPatchingProjectileWeapon'])}
        weapons.append(entry)
    # The Liberator entry is the live-proven write set, byte for byte.
    lib = weapons[0]
    pb, pm, pz = proven['beam'], proven['membership'], proven['magazine']
    if not (lib['beam']['row'] == pb['row'] and lib['beam']['rowOffset'] == pb['rowOffset']
            and lib['beam']['rowAfter'] == pb['rowAfter'] and lib['membership']['before'] == pm['before']
            and lib['membership']['after'] == pm['after'] and lib['membership']['row'] == pm['row']
            and lib['membership']['listOffsetInBody'] == pm['listOffsetInBody']
            and lib['magazine']['windowOffset'] == pz['windowOffset'] and lib['magazine']['row'] == pz['row']
            and lib['projectile']['row'] == proven['projectile']['row']):
        raise ValueError('the Liberator entry is not the live-proven write set')
    pins: dict[int, dict] = {}

    def add(rva: int, hexbytes: str, label: str) -> None:
        if rva in pins:
            if pins[rva]['hex'] != hexbytes:
                raise ValueError(f'conflicting pin bytes at 0x{rva:X}')
            return
        pins[rva] = {'rva': rva, 'hex': hexbytes, 'label': label}

    for pin in proven['pins']:
        add(pin['rva'], pin['hex'], pin['label'])
    for group, rows in multi['pins'].items():
        for pin in rows:
            add(pin['rva'], pin['bytes'], 'multi: ' + group + ': ' + pin['role'])
    del swap, chamber, membership
    return {
        'source': {'research': MULTI.name, 'liberator': liberator.SWAP.name, 'chamber': liberator.CHAMBER.name,
                   'membership': liberator.MEMBERSHIP.name, 'build': multi['build'],
                   'gameDllSha256': proven['source']['gameDllSha256']},
        'experimental': True,
        'trident': TRIDENT,
        'manager': proven['manager'],
        'beam': {'component': 'BeamWeaponComponentData', 'index': 270, 'capacity': 46, 'rowStride': 16, 'records': 24,
                 'recordBase': 0x2E0, 'recordStride': 0x78, 'tridentRow': 20, 'tridentRecord': 18,
                 'record': 23, 'recordOffset': record['offset'], 'recordBefore': record['before'],
                 'recordAfter': record['after']},
        'membership': {'rows': 4096, 'rowStride': 32},
        'projectile': {'component': 'ProjectileWeaponComponentData', 'index': 321},
        'magazine': {k: proven['magazine'][k] for k in ('component', 'index', 'capacity', 'rowStride', 'records',
                                                        'recordBase', 'recordStride', 'window')},
        'order': list(ORDER),
        'weapons': weapons,
        'pins': [pins[rva] for rva in sorted(pins)],
    }


def outputs() -> dict[str, str]:
    return {'domains/beam_swap.lua': '-- Generated by scripts/generate_beam_swap.py; do not edit.\n'
            '-- EXPERIMENTAL, SOLO-ONLY (branch exp/multi-beam): not a Runtime feature.\n'
            'return ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale multi-beam experiment domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
