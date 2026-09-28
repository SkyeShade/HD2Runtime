"""Capture the per-weapon customization option lists held in memory by the retained snapshot. Read-only.

The game keeps one keyed list per customizable weapon. Rows are 24 bytes (six u32):

    header: key, key, 0, 0, count, sequence
    child k (1..count): node, optionId, k, k, 0, sequence + k

The header key is the weapon's own loadout item id (LoadoutEntryComponent.id in the pinned entity
library) and each child names a WeaponCustomizableItem option id. Children cover the options the weapon
unlocks through progression: magazines, muzzles, optics, underbarrels. Free slot defaults (ammo type,
internals, triggers) are not listed. This is runtime state captured from the snapshot, not a static table,
so it is published as observed evidence: it never lifts a write guard or completes a sharing scope.

Output: research/attachment-unlock-lists-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_attachment_selection_candidates as candidates
import research_entity_authoring as entity_research
from research_magazine_attachments import SNAPSHOT, DATALIB, customization_items, sha
from research_support_equipment_links import loadout_entries

OUTPUT = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
PLAYER = ROOT / 'schemas/player_weapon_authoring_catalog.json'
SUPPORT = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
ROW = 24
MAX_CHILDREN = 64
# Anchors: magazine options of distinct weapon families. Their hits locate the allocations that hold
# option lists; each such allocation is then parsed completely, so lists without an anchor are found too.
ANCHORS = ('Rifle 5,5x50mm. Drum', 'Rifle 5,5x50mm. Standard', 'SHOTGUN 12g. Drum',
    'SMG 9x20mm. Top Mounted Standard', 'SMG 12x25mm. Drum', 'RIFLE Justice. Standard')


def read_list(snapshot, va):
    """The validated list whose header row starts at va, or None."""
    region = candidates.region_for_va(snapshot, va)
    if region is None or va + ROW > region.base + region.captured_length:
        return None
    key, value, index, index2, count, sequence = struct.unpack('<6I', candidates.read_va(snapshot, va, ROW))
    if key != value or index or index2 or not 0 < count <= MAX_CHILDREN:
        return None
    if va + ROW * (count + 1) > region.base + region.captured_length:
        return None
    body = candidates.read_va(snapshot, va + ROW, ROW * count)
    children = []
    for k in range(1, count + 1):
        node, option, i, j, n, s = struct.unpack_from('<6I', body, ROW * (k - 1))
        if i != k or j != k or n or s != sequence + k:
            return None
        children.append({'node': node, 'optionId': option})
    return {'va': va, 'key': key, 'sequence': sequence, 'children': children,
        'allocationBase': region.allocation_base, 'regionType': region.type, 'protect': region.protect}


def parse_allocation(snapshot, allocation_base):
    """Every validated list header inside one allocation (all captured regions, 4-byte aligned)."""
    found = []
    for region in candidates.allocation_regions(snapshot, allocation_base):
        if not region.captured_length:
            continue
        data = candidates.read_va(snapshot, region.base, region.captured_length)
        for offset in range(0, len(data) - 2 * ROW + 1, 4):
            key, value, index, index2, count, sequence = struct.unpack_from('<6I', data, offset)
            if key != value or index or index2 or not 0 < count <= MAX_CHILDREN:
                continue
            if offset + ROW * (count + 1) > len(data):
                continue
            children, ok = [], True
            for k in range(1, count + 1):
                node, option, i, j, n, s = struct.unpack_from('<6I', data, offset + ROW * k)
                if i != k or j != k or n or s != sequence + k:
                    ok = False
                    break
                children.append({'node': node, 'optionId': option})
            if ok:
                found.append({'va': region.base + offset, 'key': key, 'sequence': sequence, 'children': children,
                    'allocationBase': allocation_base, 'regionType': region.type, 'protect': region.protect})
    return found


def weapons_by_resource():
    names = {}
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        for resource in weapon['resources']:
            names[int(resource, 16)] = ('player', weapon['name'])
    support = json.loads(SUPPORT.read_text())
    for weapon in support['weapons']:
        identity = weapon['catalogIdentity']
        name = identity['name'] if isinstance(identity, dict) else identity
        for resource in weapon['resourceHashes']:
            names.setdefault(int(resource, 16), ('support', name))
    return names


def build():
    native = entity_research.Native()
    entries, _ = loadout_entries(native)
    by_item = collections.defaultdict(list)
    for resource, entry in entries.items():
        by_item[entry['itemId']].append(resource)
    names = weapons_by_resource()
    custom = (DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes()
    items = {item['optionId']: item for item in customization_items(custom)}

    snapshot = candidates.parse_snapshot(SNAPSHOT)
    by_name = {item['debugName']: item for item in items.values()}
    needles = [candidates.Needle(name, 4, by_name[name]['optionId']) for name in ANCHORS]
    cache = Path(__file__).resolve().parents[1] / 'build/attachment-unlock-anchors.json'
    if cache.exists() and json.loads(cache.read_text()).get('snapshot') == SNAPSHOT.name:
        cached = json.loads(cache.read_text())
        hit_count, allocations = cached['hits'], cached['allocations']
    else:
        hits = candidates.scan_exact(snapshot, needles, 'attachment-unlock-lists')
        hit_count, allocations = len(hits), sorted({hit.allocation_base for hit in hits})
        cache.write_text(json.dumps({'snapshot': SNAPSHOT.name, 'hits': hit_count, 'allocations': allocations}))
    lists = {}
    for allocation in allocations:
        for found in parse_allocation(snapshot, allocation):
            if found['key'] in by_item and any(child['optionId'] in items for child in found['children']):
                lists.setdefault(found['key'], []).append(found)

    weapons = []
    for key, copies in sorted(lists.items()):
        shapes = {tuple((c['node'], c['optionId']) for c in copy['children']) for copy in copies}
        if len(shapes) != 1:
            raise ValueError(f'loadout item {key:08X}: list copies disagree')
        resources = by_item[key]
        if len(resources) != 1:
            raise ValueError(f'loadout item {key:08X}: owned by {len(resources)} entities')
        kind, name = names.get(resources[0], (None, None))
        children = copies[0]['children']
        options = []
        for child in children:
            item = items.get(child['optionId'])
            options.append({'optionId': f"0x{child['optionId']:08X}", 'node': f"0x{child['node']:08X}",
                'known': item is not None, 'debugName': item['debugName'] if item else None,
                'slots': item['slots'] if item else [], 'addPath': f"0x{item['addPath']:016X}" if item else None})
        # Progression lists may also name non-customization unlocks; only customization options are used.
        weapons.append({'loadoutItemId': f'0x{key:08X}', 'resource': f'0x{resources[0]:016X}',
            'weaponKind': kind, 'weapon': name, 'copies': len(copies),
            'allocations': sorted({f"0x{copy['allocationBase']:X}" for copy in copies}),
            'unknownEntries': sum(1 for option in options if not option['known']),
            'options': [option for option in options if option['known']]})
    unmatched = []  # only lists keyed by a known loadout item id are collected
    return {'schemaVersion': 1,
        'source': {'snapshot': SNAPSHOT.name, 'mode': 'snapshot', 'writes': 0, 'protectionChanges': 0,
            'fixtureFallback': 'disabled', 'customizationSettingsSha256': sha(custom),
            'anchors': list(ANCHORS), 'anchorHits': hit_count, 'allocationsParsed': len(allocations)},
        'layout': {'rowBytes': ROW, 'header': ['key', 'key', 0, 0, 'count', 'sequence'],
            'child': ['node', 'optionId', 'k', 'k', 0, 'sequence + k'],
            'key': 'LoadoutEntryComponent.id of the weapon (pinned entity library)'},
        'semantics': ('Per-weapon progression option list observed in memory. It lists unlockable options, '
            'not free slot defaults, and may list options the weapon catalog does not show. Evidence only.'),
        'weapons': weapons, 'unmatchedKeys': unmatched}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps({'weapons': len(report['weapons']),
        'byKind': collections.Counter(w['weaponKind'] for w in report['weapons']),
        'unnamed': [w['resource'] for w in report['weapons'] if not w['weapon']],
        'unmatchedKeys': report['unmatchedKeys']}, indent=1, default=str))


if __name__ == '__main__':
    main()
