"""Generate sdk/HudIconSprites.json: the sprite name of every stratagem's and booster's own HUD icon.

The loadout screen draws stratagems and boosters from a vector icon library bound by native type (uiIcon in
StratagemAuthoringCapabilities / BoosterAuthoringCapabilities). That library leaves some types unbound or empty. The
HUD instead draws each item's own atlas sprite, named by the item's native record:
  * a stratagem: StratagemInfo +0xB0 (the presentation icon member, research/stratagem-calldown presentation rows),
    joined to the catalogue by the stratagem's uniquely resolved root id;
  * a booster: the native Booster table row (research/booster-native boosterTable, stride 0x38) +0x20, joined by the
    booster's resolved native enum value.
Only names are published: a sprite name is the lookup key of a record in the game's texture_atlas resources, and
sdk/tools/hd2_hud_icons.py resolves it against the installed game, locally. No artwork, texture name or archive
detail enters the repository.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATAGEMS = ROOT / 'schemas/stratagem_authoring_catalog.json'
STRATAGEM_PUBLIC = ROOT / 'sdk/StratagemAuthoringCapabilities.json'
CALLDOWN_RESEARCH = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
BOOSTERS = ROOT / 'sdk/BoosterAuthoringCapabilities.json'
BOOSTER_NATIVE = ROOT / 'research/booster-native-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'sdk/HudIconSprites.json'
BOOSTER_STRIDE = 0x38
BOOSTER_SPRITE = 0x20
STRATAGEM_ICON_OFFSET = 0xB0


def sprite(value: int) -> str:
    return '0x%016X' % value


def build() -> dict:
    calldown = json.loads(CALLDOWN_RESEARCH.read_text(encoding='utf-8'))
    presentation = calldown['presentation']
    if any(presentation['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('the presentation research is not proven on every snapshot')
    if presentation['fields']['icon'] != {'offset': STRATAGEM_ICON_OFFSET, 'width': 8}:
        raise ValueError('the presentation icon member moved')
    icons = {row['id']: int(row['icon'], 16) for row in presentation['rows']}
    internal = json.loads(STRATAGEMS.read_text(encoding='utf-8'))['stratagems']
    public = json.loads(STRATAGEM_PUBLIC.read_text(encoding='utf-8'))['stratagems']
    stratagems, missing = {}, {}
    for item in public:
        name = item['name']
        entry = internal.get(name)
        root = entry and entry.get('root')
        if item['rootResolution'] != 'UNIQUE' or not root:
            missing[name] = 'no call-in stratagem (rootResolution ' + item['rootResolution'] + '): no StratagemInfo row'
        elif root['id'] not in icons or icons[root['id']] == 0:
            missing[name] = 'the StratagemInfo row has no icon'
        else:
            stratagems[name] = {'sprite': sprite(icons[root['id']]), 'root': root['id']}
    native = json.loads(BOOSTER_NATIVE.read_text(encoding='utf-8'))
    table = native['boosterTable']
    if table['stride'] != BOOSTER_STRIDE or table['directStores']:
        raise ValueError('the native booster table layout changed')
    rows = {row['value']: bytes.fromhex(row['bytes']) for row in table['rows']}
    boosters = {}
    for item in json.loads(BOOSTERS.read_text(encoding='utf-8'))['boosters']:
        identity = item['identity']
        row = rows.get(identity.get('enumValue')) if identity.get('status') == 'RESOLVED' else None
        value = struct.unpack_from('<Q', row, BOOSTER_SPRITE)[0] if row and len(row) == BOOSTER_STRIDE else 0
        if value:
            boosters[item['name']] = {'sprite': sprite(value), 'nativeName': identity['nativeName']}
        else:
            missing[item['name']] = 'no resolved native booster row'
    names = [v['sprite'] for v in list(stratagems.values()) + list(boosters.values())]
    if len(names) != len(set(names)):
        raise ValueError('two items name one HUD sprite')
    return {'schemaVersion': 1, 'contract': 'hd2runtime.hud_icon_sprites.v1',
        'build': calldown['build'], 'gameDllSha256': calldown['gameDll']['sha256'],
        'note': ('Sprite names of the HUD icons: lookup keys of records in the game\'s texture_atlas resources. '
            'sdk/tools/hd2_hud_icons.py extracts the artwork locally from the installed game; none is published. '
            'Stratagem sprites are icon masks (R category colour, G white); booster sprites are colour images.'),
        'sources': {'stratagem': 'StratagemInfo +0xB0 of the uniquely resolved root (' + CALLDOWN_RESEARCH.name + ')',
            'booster': 'native Booster table row +0x20 (' + BOOSTER_NATIVE.name + ')'},
        'stratagems': dict(sorted(stratagems.items())), 'boosters': dict(sorted(boosters.items())),
        'missing': dict(sorted(missing.items()))}


def generate(check=False):
    body = json.dumps(build(), indent=1) + '\n'
    stale = []
    if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != body:
        stale.append(OUTPUT)
        if not check:
            OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale HUD icon sprites: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
