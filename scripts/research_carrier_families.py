"""Carrier families (docs/research/carrier-families-F5FEE03DCFDB.md): every StratagemInfo row of build F5FEE03DCFDB
classified into the custom-stratagem carrier families from the fields the game's own call-in system and UI read.
Read-only, offline: the mission snapshot's rows and the stratagem catalogue. Nothing is written.

The fields and their native readers (pinned in research/beacon-redirect-F5FEE03DCFDB.json and
research/stratagem-slot-conversion-F5FEE03DCFDB.json):
* +0x3C delivery kind, read by the beacon init (0x6A5D1B) and the spawn dispatcher (0x6AC007, 0x6AC052, 0x6AD4B7,
  0x6AD600): 0 Eagle, 1 orbital strike, 2 hellpod, 3 vehicle drop, 5 orbital barrage, 4/6/7 mission and special;
* +0xB8 category, read by the UI, the call voice line and the ping colour (0x13D1557): 0 offensive (red), 1 and 2
  supply (blue), 3 defensive, 4 mission;
* +0xD4 beam, read when the thrown ball lands (0x6A21A5): 1 red, 2 blue, 3 yellow;
* +0x170 bit 1 walkable-ground steering of the ball in flight (0x6A0830);
* +0x50 uses per rearm (-1 unlimited) and +0xC8 linked type (49 = Eagle Rearm, 0x6AE4B1);
* +0x80 bit 1 selectable and +0xC0 bit 0 enabled: the loadout grid's availability check (0x136FB89, 0x136FB97).

The rule (FAMILY_RULE), applied to selectable and enabled rows of the catalogue:
* special: not selectable or not enabled, category 4, a delivery kind outside {0, 1, 2, 3, 5}, or a special-cased
  type (0x31 Eagle Rearm, 0x7B, 0x7C Reinforce, 0x94);
* vehicle: delivery kind 3;
* offensive: category 0 and delivery kind 0 (eagle), 1 (orbital strike) or 5 (orbital barrage);
* deployable: category 3 and delivery kind 2 (sentries, emplacements, mines: a hellpod);
* support: category 1 or 2 and delivery kind 2 (support weapons and backpacks: a hellpod).
Each family's members are checked against the catalogue's own families (eagle/orbital, support/backpack,
sentry/emplacement/mine, vehicle, mission).

Output: research/carrier-families-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_event_state as base  # noqa: E402
from research_stratagem_calldown import TABLE  # noqa: E402
from research_stratagem_slot_conversion import catalogue_roots  # noqa: E402

OUTPUT = ROOT / 'research/carrier-families-F5FEE03DCFDB.json'
SNAPSHOT = 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'
SPECIAL_TYPES = {0x31: 'Eagle Rearm', 0x7B: 'special-cased 0x7B', 0x7C: 'Reinforce', 0x94: 'special-cased 0x94'}
KINDS = {0: 'eagle', 1: 'orbital strike', 2: 'hellpod', 3: 'vehicle drop', 5: 'orbital barrage'}
CATALOGUE_FAMILIES = {'offensive': {'eagle', 'orbital'}, 'support': {'support', 'backpack'},
    'deployable': {'sentry', 'emplacement', 'mine'}, 'vehicle': {'vehicle'}, 'special': {'mission'}}


def family_of(row):
    """The carrier family of one row's fields (FAMILY_RULE), and why."""
    if not (row['selectable'] and row['enabled']):
        return 'special', 'not selectable/enabled'
    if row['type'] in SPECIAL_TYPES:
        return 'special', SPECIAL_TYPES[row['type']]
    if row['category'] == 4:
        return 'special', 'mission category'
    if row['kind'] not in KINDS:
        return 'special', 'delivery kind %d' % row['kind']
    if row['kind'] == 3:
        return 'vehicle', 'vehicle drop'
    if row['category'] == 0 and row['kind'] in (0, 1, 5):
        return 'offensive', KINDS[row['kind']]
    if row['category'] == 3 and row['kind'] == 2:
        return 'deployable', 'hellpod, defensive'
    if row['category'] in (1, 2) and row['kind'] == 2:
        return 'support', 'hellpod, supply'
    return 'special', 'unclassified (category %d, kind %d)' % (row['category'], row['kind'])


def main():
    text = (ROOT / 'domains/stratagem_authoring.lua').read_text(encoding='utf-8')
    families = {m.group(1): m.group(2) for m in re.finditer(r'\["name"\]="([^"]+)",\["family"\]="([^"]*)"', text)}
    names = {root['id']: name for name, root in catalogue_roots().items()}
    mem = base.Mem(SNAPSHOT)
    g = mem.game
    rows = []
    for kind in range(1, 150):
        address = mem.ptr(g + TABLE + kind * 8)
        if not address:
            continue
        raw = mem.read(address, 0x180)
        u = lambda o: struct.unpack_from('<I', raw, o)[0]
        name = names.get(u(4))
        if not name:
            continue
        row = {'name': name, 'type': kind, 'id': u(4), 'catalogueFamily': families.get(name), 'kind': u(0x3C),
            'category': u(0xB8), 'beam': u(0xD4), 'follows': bool(raw[0x170] & 2),
            'uses': struct.unpack_from('<i', raw, 0x50)[0], 'linked': u(0xC8), 'selectable': bool(u(0x80) & 2),
            'enabled': bool(u(0xC0) & 1), 'callIn': round(struct.unpack_from('<f', raw, 0x54)[0], 3),
            'payloads': u(0xA0), 'waves': u(0x12C) + 1}
        row['family'], row['why'] = family_of(row)
        row['eagle'] = row['kind'] == 0
        row['rearm'] = row['linked'] == 0x31
        rows.append(row)
    mem.close()
    rows.sort(key=lambda r: (r['family'], r['name']))
    mismatches = [r['name'] for r in rows if r['selectable'] and r['enabled']
        and r['catalogueFamily'] not in CATALOGUE_FAMILIES[r['family']]]
    if mismatches:
        raise ValueError('the family rule disagrees with the catalogue for: %s' % ', '.join(mismatches))
    summary = defaultdict(lambda: {'count': 0, 'members': [], 'categories': set(), 'beams': set(), 'kinds': set(),
        'unlimited': 0, 'follows': set()})
    for r in rows:
        s = summary[r['family']]
        s['count'] += 1
        s['members'].append(r['name'])
        s['categories'].add(r['category'])
        s['beams'].add(r['beam'])
        s['kinds'].add(r['kind'])
        s['follows'].add(r['follows'])
        s['unlimited'] += r['uses'] == -1
    summary = {k: {**v, 'categories': sorted(v['categories']), 'beams': sorted(v['beams']), 'kinds': sorted(v['kinds']),
        'follows': sorted(v['follows'])} for k, v in sorted(summary.items())}
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'snapshot': SNAPSHOT,
        'rule': family_of.__doc__ + ' See the module docstring (FAMILY_RULE).',
        'fields': {'kind': 0x3C, 'category': 0xB8, 'beam': 0xD4, 'follows': 0x170, 'uses': 0x50, 'linked': 0xC8,
            'selectable': 0x80, 'enabled': 0xC0, 'callIn': 0x54},
        'families': summary, 'stratagems': rows}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), {k: v['count'] for k, v in summary.items()})


if __name__ == '__main__':
    main()
