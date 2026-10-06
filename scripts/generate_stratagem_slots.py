"""Generate domains/stratagem_slots.lua: the mission stratagem record, the in-flight call-ins, the account catalogue's
ownership rule and the stratagem call-in packages that runtime/stratagem_slot_conversion.lua (development) reads, with
the pinned code it re-proves first, from research/stratagem-slot-conversion-F5FEE03DCFDB.json
(docs/custom-stratagems.md, "Mission-time slot conversion").
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/stratagem_slots.lua'


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('slot conversion research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the slot conversion research covers another build than schemas/current.lua')
    if not all(s['recordTypesHeld'] for s in research['snapshots'] if s['phase'] in ('alive', 'reinforced')):
        raise ValueError('the record types\' packages are not proven held in the mission snapshots')
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']}
        for rows in research['pins'].values() for pin in rows]
    unique = {}
    for pin in pins:
        unique.setdefault(pin['rva'], pin)
    record = research['record']
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        # [game + global] = the per-peer records: {u64 peer, ...} x count, each with its stratagem state at +state.
        'record': {'global': int(record['global'], 16), 'stride': record['stride'], 'count': record['count'],
            'state': record['state'], 'entries': record['entries'], 'entryStride': record['entryStride'],
            'entryCount': record['entryCount'], 'maxEntries': record['maxEntries'], 'entry': record['entry'],
            'key': record['key']},
        'callIns': {key: (int(value, 16) if isinstance(value, str) else value)
            for key, value in research['callIns'].items()},
        # The availability check's ownership rule (0x136FC20), read-only: the kind-10 records of [game + global] whose
        # +8 is a stable id, owned when their definition state (or their parent item's) is 2 or 4.
        'catalogue': {'global': 0x347CEF8, 'rangeFirst': 0xD1D0C, 'rangeLast': 0xD1D10, 'index': 0xD1D48,
            'records': 0xB9CE4, 'recordStride': 24, 'recordId': 8, 'recordBack': 0x10, 'definitions': 0x1CE4,
            'definitionStride': 0xB8, 'definitionState': 0x14, 'ownedStates': [2, 4]},
        # StratagemInfo members read: +0x50 max uses (-1 unlimited), +0x80 bit 1 selectable, +0xC0 bit 0 enabled,
        # +0xD4 the beam, +0xB8 the ping (research "beaconPresentation").
        'row': {'maxUses': 0x50, 'selectable': 0x80, 'selectableBit': 2, 'enabled': 0xC0, 'enabledBit': 1,
            'beam': research['beacon']['beamRow'], 'ping': research['beacon']['pingRow']},
        # The beacon's look: the beam's colour by its +0xD4 value (the beacon category: 1 red = offensive, 2 blue =
        # support, 3 yellow = other, 0 none) and the ping's colour by its +0xB8 value (0 red, 2 blue, else yellow); the
        # values observed in the snapshot by name (reference only: the Runtime reads the live row).
        'beacon': {'beams': {int(k): v['colourName'] for k, v in research['beacon']['beams'].items()},
            'categories': {1: 'offensive', 2: 'support', 3: 'other'},
            'pings': {0: 'red', 2: 'blue'}, 'pingOther': 'yellow',
            'observed': {name: {'id': v['id'], 'beam': v['beam'], 'ping': v['ping']}
                for name, v in research['beacon']['observed'].items()}},
        # A stratagem's call-in package: the root package the game holds for every record entry's type in a mission.
        'packages': research['stratagemPackages']['byStableId'],
        # Its FULL call-in package list, as the mission loader requests it (0x1753080: the row's +0xA8 package and its
        # +0xF8 weapon's), by stable id: [{package, via}]. A support weapon's is its weapon's (+0xA8 = 0). `incomplete`:
        # stratagems with a level- or entity-dependent part (never a carrier).
        'callInPackages': research['stratagemPackages']['callIn']['byStableId'],
        'callInIncomplete': research['stratagemPackages']['callIn']['incomplete'],
        'pins': sorted(unique.values(), key=lambda pin: pin['rva'])}


def outputs() -> dict[str, str]:
    return {'domains/stratagem_slots.lua': '-- Generated by scripts/generate_stratagem_slots.py; do not edit.\n'
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
        raise RuntimeError('Stale stratagem slot domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
