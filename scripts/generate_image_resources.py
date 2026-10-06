"""Generate domains/image_resources.lua: the resource-manager lookup the Runtime reads to prove a mod's own image is
loaded before a write names it (runtime/image_resources.lua, docs/custom-images.md), from
research/image-resources-F5FEE03DCFDB.json.

The pins are re-proven in game before the first lookup of each loaded game; one mismatch refuses every custom image.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/image-resources-F5FEE03DCFDB.json'
FAMILY = ROOT / 'research/stratagem-icon-family-F5FEE03DCFDB.json'
CONSUMERS = ROOT / 'research/stratagem-icon-consumers-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/image_resources.lua'


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('image resource research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned resource lookup differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['exe']['sha256'] not in profile or research['gameDll']['sha256'] not in profile:
        raise ValueError('the image resource research covers another build than schemas/current.lua')
    if any(item['lookups'] != {'missingTexture': 'present', 'icon120mmStandalone': 'absent', 'proofImage': 'absent'}
            or any(p['state'] != 4 or p['texturesPresent'] != p['textures'] or p['luaPresent'] != p['lua']
                for p in item['bootParts']) for item in research['snapshots']):
        raise ValueError('the lookup or the boot package residency is not proven in every snapshot')
    if any(layout['differences'] for layout in research['archiveLayout']):
        raise ValueError('the archive layout is not reproduced')
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'exe'}
        for rows in research['pins']['exe'].values() for pin in rows]
    pins += [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
        for pin in research['pins']['game']]
    family = json.loads(FAMILY.read_text(encoding='utf-8'))
    if family['writes'] or family['protectionChanges'] or any(family['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('the icon family research is not proven read-only on every snapshot')
    if (family['archiveLayout']['differences'] or not family['customFamily']['roundTrip']
            or family['customFamily']['gameResourceCollisions'] or any(r['materialExact'] != r['icons']
            or r['sprite'] != r['icons'] for r in family['vanilla']['snapshots'])):
        raise ValueError('the icon family is not proven')
    # The family reader (runtime/image_resources.lua M.family) reads the material resource layout the loader writes and
    # the atlas sprite map; their code is pinned with the lookup.
    for group in ('materialLoader', 'spriteByName'):
        pins += [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'exe'}
            for pin in family['pins']['exe'][group]]
    # Every consumer of the icon value and the material / texture paths they reach (research/stratagem-icon-consumers,
    # research/stratagem-icon-family): proven before presentation_icon writes a custom icon
    # (runtime/image_resources.lua icon_ready).
    consumers = json.loads(CONSUMERS.read_text(encoding='utf-8'))
    if any(consumers['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned icon consumer differs between retained snapshots')
    consumer_pins = {}
    def add(pin, module):
        consumer_pins[(module, pin['rva'])] = {'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': module}
    for pin in consumers['readers'] + consumers['materialPath']['game']:
        add(pin, 'game')
    for pin in consumers['materialPath']['exe']:
        add(pin, 'exe')
    for rows in family['pins']['game'].values():
        for pin in rows:
            add(pin, 'game')
    for rows in family['pins']['exe'].values():
        for pin in rows:
            add(pin, 'exe')
    import hd2_image
    material = family['materialFormat']
    texture = research['texture']
    return {'source': {'research': RESEARCH.name, 'family': FAMILY.name, 'build': research['build'],
            'exeSha256': research['exe']['sha256']},
        'texture': {'type': texture['type'], 'size': texture['size'], 'mips': texture['mips'],
            'format': texture['format']},
        'manager': research['manager'], 'typeMap': research['typeMap'], 'record': research['record'],
        'names': research['names'], 'markers': research['markers'],
        # Bounds the reader enforces on what it reads (the retained snapshots hold 59 types in 79 buckets and up to
        # a few thousand textures); anything outside them is a changed or busy table, never a guess.
        'limits': {'typeBuckets': 4096, 'nameBuckets': 1048576, 'chain': 4096, 'slots': 1048576},
        # A custom icon's GUI material: exactly the vanilla icon material for its name (hd2_image.icon_material), as the
        # loader leaves it in memory (three fix-ups) with its material object.
        'material': {'type': '0x%016X' % hd2_image.MATERIAL_TYPE, 'size': 160,
            'template': hd2_image.icon_material(0).hex(), 'nameOffset': 0x8C,
            'fixups': {'object': 0x20, 'slotIds': 0x30, 'slotNames': 0x38}, 'slotIds': 0x88, 'slotNames': 0x8C,
            'body': material['header']['bodyOffset'],
            'object': {'magic': 0xD92A8333, 'body': 0x10, 'shader': 0x30, 'name': 0x38, 'size': 0x48},
            'shader': hd2_image.ICON_SHADER, 'imageSlot': hd2_image.IMAGE_SLOT,
            # Read for the development probe (runtime/image_resources.lua M.inspect): header kind, body slot count and
            # shader id, as the pinned loader and online code read them.
            'fields': {'kind': material['header']['kindOffset'],
                'slotCount': material['header']['bodyOffset'] + material['body']['slotCount'],
                'shaderId': material['header']['bodyOffset'] + material['body']['shader']}},
        # The atlas sprite map: name -> sprite record, whose +8 is its atlas page texture (GUI API +0x348).
        'sprites': {'entries': 0x2A0, 'count': 0x2B0, 'buckets': 0x2B4, 'atlasTexture': 8},
        'pins': sorted(pins, key=lambda pin: (pin['module'], pin['rva'])),
        'consumerPins': [consumer_pins[key] for key in sorted(consumer_pins)]}


def outputs() -> dict[str, str]:
    return {'domains/image_resources.lua': '-- Generated by scripts/generate_image_resources.py; do not edit.\n'
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
        raise RuntimeError('Stale image resources: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
