"""Generate domains/beam_table.lua: the EXPERIMENTAL, SOLO-ONLY Runtime-owned relocated BeamWeapon table that
runtime/experiment_beam_table.lua builds and runtime/experiment_beam_swap.lua (0.3.0, the 'owned table' path) uses to
give the AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand their own BeamWeapon records 24, 25 and 26.

Source (read-only research, never trusted at run time without re-proof): research/beam-table-relocation-F5FEE03DCFDB.json
(research/docs/beam-table-relocation-F5FEE03DCFDB.md): every reader of slot 270 (three instructions, each re-reads the
slot per call), the slot-array base sites (none reads slot 270), the lookup (capacity 46 and stride 0x78 in code, the
record base = the slot pointer, the record index unbounded), the default record (+0xDA8), the loader store, the reload
(no callers) and unload (stores no slot), and the offline overlay of the copy in every retained snapshot.

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
import generate_beam_swap as swap  # noqa: E402

RESEARCH = ROOT / 'research/beam-table-relocation-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/beam_table.lua'
SNAPSHOT_COUNT = 9
# The per-weapon settings the owned path writes into each weapon's own record (the 0.30.4 beam pulse fields:
# scripts/equipment_fields.py PULSE_FIELDS, the same members, storage and ranges). BeamWeapon +100 (the fire mode) is
# NOT offered: the instance's discrete-shot flag is fixed from it at spawn (0x546A4F) and only the Trident's pulsed
# mode 6 is proven with these weapons' ammunition (one round per pulse, heat per pulse).
SETTINGS = (('fire_rate', 'beam.fire_rate', 104, 'i32', 1, 6000, 'rpm'),
            ('pulse_beams', 'beam.pulse_beams', 108, 'i32', 1, 8, 'beams per pulse'),
            ('pulse_seconds', 'beam.pulse_seconds', 112, 'f32', 0, 10, 's'))


def build() -> dict:
    r = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if r['writes'] or r['protectionChanges'] or r['build'] != 'F5FEE03DCFDB':
        raise ValueError('the beam table research must be read-only research of build F5FEE03DCFDB')
    if len(r['pinnedBytesMismatchPerSnapshot']) < SNAPSHOT_COUNT or any(r['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('every beam table pin must be checked, identical, in every retained snapshot')
    census = r['slotCensus']
    if sorted(census['slot270']['sites']) != ['0x50E88F', '0x50ECA7', '0x841BC9'] or census['slotArrayBase'][
            'readsSlot270'] or census['otherWindowValuesAddressingASlot']:
        raise ValueError('slot 270 has another reader')
    entry = r['entryPoints']
    if entry['0xFDB860']['callsOrJumps'] or entry['0xFDB440']['callsOrJumps'] != ['0xAE0D8B', '0xFDB880'] \
            or not r['unloadStoresNoSlot']:
        raise ValueError('another store to a slot (loader, reload or unload changed)')
    lookup = r['lookup']
    if (lookup['capacity'], lookup['rowStride'], lookup['recordBase'], lookup['recordStride'],
            lookup['recordIndexBounded'], lookup['defaultRecord']['offset']) != (46, 16, 0x2E0, 0x78, False, 0xDA8):
        raise ValueError('the BeamWeapon lookup is not the reviewed one')
    copy = r['copy']
    if copy['size'] > 4096 or copy['records'] != 27 or copy['framing'] != 32:
        raise ValueError('the copy does not fit one page')
    for o in r['observations']:
        if not (o['otherRecordsByteIdentical'] and o['defaultRecordUnchanged'] and o['slotAligned8']
                and all(o['ownRecordsAreTheTridentRecord'].values()) and o['tableByteIdenticalToFile']
                and o['resourcesChecked'] >= 1900 and len(o['answersChanged']) == 3):
            raise ValueError('snapshot ' + o['snapshot'] + ': the offline overlay of the copy is not clean')
    domain = swap.build()
    rows = {w['id']: w['beam']['row'] for w in domain['weapons']}
    if rows != copy['rows']:
        raise ValueError('the copy rows differ from the multi-weapon swap rows')
    beam = domain['beam']
    if (beam['capacity'], beam['recordBase'], beam['recordStride'], beam['records'], beam['recordOffset']) != (
            lookup['capacity'], lookup['recordBase'], lookup['recordStride'], 24, 0xDA8):
        raise ValueError('the multi-weapon domain and the relocation research disagree on the table')
    pins = []
    seen = {p['rva'] for p in domain['pins']}
    for group, items in r['proofs'].items():
        for pin in items:
            if pin['rva'] in seen:
                continue
            seen.add(pin['rva'])
            pins.append({'rva': pin['rva'], 'hex': pin['bytes'], 'label': 'beam table: ' + group + ': ' + pin['role']})
    pins.sort(key=lambda p: p['rva'])
    return {
        'source': {'research': RESEARCH.name, 'build': r['build'], 'gameDllSha256': r['gameDllSha256']},
        'experimental': True,
        'slot': {'index': 270, 'offset': 0xF12478 + 8 * 270},
        'layout': {'framing': copy['framing'], 'rows': lookup['capacity'], 'rowStride': lookup['rowStride'],
                   'recordBase': lookup['recordBase'], 'recordStride': lookup['recordStride'], 'fileRecords': 24,
                   'records': copy['records'], 'defaultRecord': 23, 'size': copy['size']},
        'trailer': {'magic': copy['trailer']['magic'], 'size': copy['trailer']['size']},
        'records': copy['ownRecords'],
        'maxCopies': 16,
        'settings': [{'id': s[0], 'field': s[1], 'offset': s[2], 'storage': s[3], 'min': s[4], 'max': s[5],
                      'unit': s[6]} for s in SETTINGS],
        'pins': pins,
    }


def outputs() -> dict[str, str]:
    return {'domains/beam_table.lua': '-- Generated by scripts/generate_beam_table.py; do not edit.\n'
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
        raise RuntimeError('Stale beam table experiment domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
