"""Generate domains/stratagem_calldown.lua: a stratagem's calldown sequence (StratagemInfo +0x40 / +0x48), its
readers and the custom-stratagem P0 proof's target, from research/stratagem-calldown-F5FEE03DCFDB.json.

The reader pins are re-proven in game before the first write of each loaded game.dll; one mismatch refuses the write.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/stratagem_calldown.lua'


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('stratagem calldown research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned calldown reader differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the calldown research covers another game.dll than schemas/current.lua')
    table, members = research['table'], research['members']
    for key, value in (('table_rva', table['rva']), ('buffer_rva', table['bufferRva']), ('stride', table['stride']),
            ('entries', table['entries'])):
        if '["%s"]=%d' % (key, value) not in profile:
            raise ValueError('stratagem %s disagrees with schemas/current.lua' % key)
    asm = [pin['asm'] for rows in research['proofs'].values() for pin in rows]
    for offset in (members['sequence']['offset'], members['count']['offset']):
        for group in ('matcher', 'copy', 'compare'):
            if not any('+ %s]' % hex(offset) in pin['asm'] for pin in research['proofs'][group]):
                raise ValueError('reader %s does not read +0x%X' % (group, offset))
    if research['directions'] != {'1': 'up', '2': 'right', '3': 'down', '4': 'left'} or research['wikiCodes']['mismatched']:
        raise ValueError('the direction mapping is not proven')
    p0 = research['p0']
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
        for rows in research['proofs'].values() for pin in rows]
    hud = research['hud']
    if any(hud['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned HUD instruction differs between retained snapshots')
    if not hud['snapshots'] or any(s['pathOffset'] != hud['pathOffset'] or not s['spritesMatchingFormula']
            or not all(slot['match'] for slot in s['slots']) for s in hud['snapshots']):
        raise ValueError('the HUD path, formula or drawn codes are not proven in every mission snapshot')
    hud_pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
        for rows in hud['proofs'].values() for pin in rows] + [{'label': pin['role'], 'rva': pin['rva'],
        'hex': pin['bytes'], 'module': 'game'} for pin in hud['data']]
    records, slots, sprites = hud['records'], hud['slots'], hud['sprites']
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        'row': {'stride': table['stride'], 'sequence': members['sequence']['offset'], 'count': members['count']['offset'],
            'padding': members['padding']['offset']},
        'directions': {'up': 1, 'right': 2, 'down': 3, 'left': 4}, 'maxLength': research['maxLength'],
        'p0': {'stratagem': p0['stratagem'], 'id': p0['id'], 'package': p0['package'], 'nativeType': p0['nativeType'],
            'nativeTypeName': p0['nativeTypeName'], 'nativeSequence': p0['nativeSequence'], 'sequence': p0['sequence'],
            'overlaps': [{'type': o['type'], 'nativeName': o['nativeName'], 'sequence': o['sequence'],
                'relation': o['relation']} for o in p0['overlaps']]},
        'unproven': research['unproven'],
        'pins': sorted(pins, key=lambda pin: pin['rva']), 'readers': len(asm),
        # Every StratagemInfo row's native code by its stable id (the same in all seven snapshots), for the
        # calldown_code baselines and the duplicate-code guard.
        'nativeCodes': {str(row['id']): row['sequence'] for row in research['nativeRows']},
        # The in-mission stratagem list (development HUD refresh, runtime/stratagem_hud.lua). Its pins are separate:
        # the P0 write never depends on them.
        'hud': {'global': hud['global'], 'setUp': hud['setUp'], 'pathOffset': hud['pathOffset'],
            'listSlot0': hud['slot0'],
            'records': {'global': records['rva'], 'stride': records['stride'], 'count': records['count'],
                'entries': records['entries'], 'entryStride': records['entryStride'],
                'entryCount': records['entryCount']},
            'slots': {'count': slots['count'], 'stride': slots['stride'], 'index': slots['index'],
                'type': slots['type'], 'displayedType': slots['displayedType'], 'scrambled': slots['scrambled'],
                'timers': slots['timers'], 'relayout': slots['relayout']},
            'sprites': {'offset': sprites['offset'], 'stride': sprites['stride'], 'count': sprites['count'],
                'region': sprites['region'], 'derived': sprites['derived'], 'subrect': sprites['subrect'],
                'mask': sprites['mask'], 'flagParent': sprites['flagParent'], 'sibling': sprites['sibling'],
                'parent': sprites['parent'], 'cellBytes': sprites['cellBytes'], 'bits': sprites['bits']},
            'pins': sorted(hud_pins, key=lambda pin: pin['rva'])},
        # The saved ship loadout (read-only; the selectable-stratagem development proof). Only the 'saved' pins are
        # proven at run time; the 'picker' group stays research evidence.
        'loadout': loadout(research['loadout']),
        # Presentation members (development presentation proof, runtime/stratagem_presentation.lua): the fields, every
        # row's reviewed native values by stable id, and the reader pins proven before any write.
        'presentation': presentation(research['presentation'])}


def presentation(item: dict) -> dict:
    if any(item['pinnedBytesMismatchPerSnapshot'].values()) or len(item['rows']) != 149:
        raise ValueError('the presentation research is not proven on every snapshot')
    return {'fields': item['fields'],
        'values': {str(row['id']): {key: row[key] for key in item['fields']} for row in item['rows']},
        'unresolved': {str(entry['id']): {member: True for member in entry['members']}
            for entry in item['unresolvedSources']},
        'pins': sorted(({'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
            for pin in item['proofs']), key=lambda pin: pin['rva'])}


def loadout(item: dict) -> dict:
    if any(item['pinnedBytesMismatchPerSnapshot'].values()) or not item['snapshots'] \
            or not all(s['saved'] and s['pairs'] for s in item['snapshots']):
        raise ValueError('the saved-loadout research is not proven on every snapshot')
    return {'store': item['store'], 'savedFlag': item['savedFlag'], 'pairs': item['pairs'],
        'pairStride': item['pairStride'], 'pairCount': item['pairCount'], 'pair': item['pair'],
        'pins': sorted(({'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
            for pin in item['proofs']['saved']), key=lambda pin: pin['rva'])}


def outputs() -> dict[str, str]:
    return {'domains/stratagem_calldown.lua': '-- Generated by scripts/generate_stratagem_calldown.py; do not edit.\n'
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
        raise RuntimeError('Stale stratagem calldown: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
