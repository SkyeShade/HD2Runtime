"""Carrier pod nodes (docs/research/carrier-pod-items-F5FEE03DCFDB.md, section 11): where each slot of a hellpod
weapon rack places its item, and so how many items a carrier's OWN rack can hold. Read-only, offline: the pinned
entity tables (scan toolkit), research/pod-payloads-F5FEE03DCFDB.json (every RackAttach slot of every rack) and the
installed game's data folder (scripts/hd2_game_data.py; the rack unit resource is only read). Nothing is written.

Proves [O] (pinned data, the game's own unit resource):

1. 51 of the 56 hellpod rack entities (every weapon and backpack rack but the CQC-1 One True Flag's) name ONE unit
   resource in their UnitComponentData (+0 UnitPath): the weapon-rack unit. So a weapon rack and a backpack rack do not
   differ in model, scene graph or attach routine: they differ only in the node each RackAttach slot names (+8) and its
   rack side (+52). The other four units: the One True Flag, the Solo Silo, the ammo / health pack racks, the Jammed
   Pod.
2. That unit's scene graph (header +52: its offset; its first u32: the node count) ends with the node-name hash array
   (one u32 murmur64-high per node), which ends where the next section the header names begins (+80 in the
   weapon-rack unit). Every node a rack slot
   names is looked up there: present means the rack event's placement (0x934690 -> attach 0x812540 at the slot node,
   research carrier-pod-items "rackPlacement") has a real node to attach the item at.
3. Per rack: its slots inside spawn_payload_size (+556) with a non-zero node that is a node of the unit and differs
   from every earlier usable slot's node (two items never share one attach point). That is the CAPACITY of a carrier's
   own rack without a spawn-count write; the vanilla populated count is not the capacity.
   The EAT-411 Leveller: spawn_payload_size 2, slot 0 its launcher at the main weapon node, slot 1 EMPTY at node
   3902607911 = murmur64('attach_1') >> 32, node 17 of the unit. The spawner (0x934CD0, research "rackSpawner") walks
   the slots in order, skips a zero node or a zero item without consuming the count, and stops after `count` items:
   with slot 1 given an item it spawns it there (count 2 reached), attached at attach_1.
4. The slot ROLE (where the item hangs): the role of the slot's vanilla item kind (support weapon -> weapon, backpack ->
   backpack); an empty slot inside the spawn count (only the Leveller's) takes the rack's own kind (weapon). The vanilla
   nodes: 1992741347 (main weapon, side 2), 2145467647 (second weapon, side 1), 85105251 (main backpack, side 2),
   3993544543 (a backpack beside a weapon, side 1); the default node of every unconfigured slot is attach_1.

Output: research/carrier-pod-nodes-F5FEE03DCFDB.json (--check compares a fresh build with the committed file).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

OUTPUT = ROOT / 'research/carrier-pod-nodes-F5FEE03DCFDB.json'
POD_PAYLOADS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
CARRIER_POD_ITEMS = ROOT / 'research/carrier-pod-items-F5FEE03DCFDB.json'
UNIT_TYPE = 0xE0A48D0BE9A7453F
SCENE_GRAPH_AT, NEXT_SECTION_AT = 52, 80
# Node names reviewed by their hash (murmur64 high word); the others stay hashes.
NAMES = ('weapon_rack', 'root', 'rack', 'attach_0', 'attach_1', 'attach_2', 'attach_3', 'root_point')
VANILLA_ROLE = {'support_weapon': 'weapon', 'backpack': 'backpack'}


def u32(raw: bytes, at: int) -> int:
    return struct.unpack_from('<I', raw, at)[0]


def node_names(unit: bytes) -> list[int]:
    graph = u32(unit, SCENE_GRAPH_AT)
    count = u32(unit, graph)
    # The scene graph ends where the next section the header names begins (the weapon-rack unit: header +80).
    later = [u32(unit, at) for at in range(SCENE_GRAPH_AT + 4, 120, 4) if u32(unit, at) > graph]
    end = min(later) if later else 0
    if not (0 < count < 4096 and graph < end - 4 * count <= len(unit) and end <= len(unit)):
        raise ValueError('the rack unit scene graph is not where it was found (graph %d, count %d, end %d)'
            % (graph, count, end))
    return [u32(unit, end - 4 * count + 4 * i) for i in range(count)]


def build() -> dict:
    from scan import tables
    import hd2_game_data as gdata
    pod = json.loads(POD_PAYLOADS.read_text(encoding='utf-8'))
    items = json.loads(CARRIER_POD_ITEMS.read_text(encoding='utf-8'))
    exclusive = {r['resource']: r for r in items['carrierRacks']['racks']}
    # An item's kind: the pod payload catalogue's category (as research carrier-pod-items classifies racks), else the
    # item catalogue's kind.
    kind_of = {i['resource']: i['kind'] for i in items['itemCatalog']['items']}
    kind_of.update({c['resource']: c['category'] for c in pod['candidates'] if c.get('category')})
    t = tables.pinned()
    uc = t.component('UnitComponentData')
    unit_of, units = {}, {}
    for rack in pod['racks']:
        rec = uc.record_of(int(rack['resource'], 16))
        if rec is None:
            raise ValueError(str(rack['path']) + ' has no UnitComponentData')
        unit_of[rack['resource']] = struct.unpack_from('<Q', uc.raw(rec), 0)[0]
        units.setdefault(unit_of[rack['resource']], []).append(rack['resource'])
    data = gdata.Data()
    found = data.find({(u, UNIT_TYPE) for u in units})
    named = {gdata.murmur64(n.encode()) >> 32: n for n in NAMES}
    graphs = {}
    for u in units:
        if (u, UNIT_TYPE) not in found:
            raise ValueError('the rack unit 0x%016X is not in the installed data folder' % u)
        archive, main, _, _ = found[(u, UNIT_TYPE)]
        graphs[u] = node_names(data.read(archive, main))
    shared = max(units, key=lambda u: len(units[u]))
    names = graphs[shared]

    def node_info(u, h):
        index = {x: i for i, x in enumerate(graphs[u])}
        return {'hash': h, 'name': named.get(h), 'index': index.get(h), 'inUnit': h in index}

    racks = []
    for rack in pod['racks']:
        ex = exclusive.get(rack['resource']) or {}
        kinds = sorted({kind_of.get(s['item']) or 'unknown' for s in rack['slots'] if s['item']})
        rack_role = None
        role_kinds = {VANILLA_ROLE.get(k) for k in kinds}
        if len(role_kinds) == 1 and None not in role_kinds:
            rack_role = next(iter(role_kinds))
        slots, used_nodes, usable = [], set(), []
        for s in rack['slots']:
            inside = s['index'] < rack['spawnPayloadSize']
            item_kind = kind_of.get(s['item']) if s['item'] else None
            role = VANILLA_ROLE.get(item_kind) if item_kind else (rack_role if inside else None)
            node = s['node'] or 0
            info = node_info(unit_of[rack['resource']], node)
            ok = inside and node != 0 and info['inUnit'] and node not in used_nodes and role is not None
            if ok:
                used_nodes.add(node)
                usable.append(s['index'])
            slots.append({'index': s['index'], 'item': s['item'], 'itemKind': item_kind, 'node': info,
                'rackSide': s['rackSide'], 'applyDeltas': s['applyDeltas'], 'insideSpawnCount': inside,
                'role': role if inside else None, 'usable': ok,
                'emptyUsable': ok and not s['item']})
        racks.append({'resource': rack['resource'], 'path': rack['path'], 'unit': '0x%016X' % unit_of[rack['resource']],
            'sharedUnit': unit_of[rack['resource']] == shared, 'consumers': [c['name'] for c in
            rack['consumers']], 'carrier': ex.get('carrier'), 'exclusiveCarrierRack': ex.get('exclusiveCarrierRack',
            False), 'spawnPayloadSize': rack['spawnPayloadSize'], 'randomPayloadSize': rack['randomPayloadSize'],
            'vanillaItemKinds': kinds, 'rackRole': rack_role, 'usableSlots': usable, 'capacity': len(usable),
            'vanillaPopulated': ex.get('maxItems'), 'slots': slots})
    for r in racks:
        if r['exclusiveCarrierRack'] and r['carrier'] != 'CQC-1 One True Flag' and not r['sharedUnit']:
            raise ValueError(r['path'] + ': an exclusive weapon/backpack rack outside the shared weapon-rack unit')
    leveller = next(r for r in racks if r['carrier'] == 'EAT-411 Leveller')
    slot1 = leveller['slots'][1]
    if not (leveller['spawnPayloadSize'] == 2 and slot1['item'] is None and slot1['node']['name'] == 'attach_1'
            and slot1['node']['inUnit'] and slot1['usable'] and leveller['capacity'] == 2):
        raise ValueError('the Leveller slot 1 facts changed: %r' % slot1)
    return {
        'schemaVersion': 1,
        'build': build_profile.BUILD_ID,
        'writes': 0,
        'sources': [POD_PAYLOADS.name, CARRIER_POD_ITEMS.name, 'the pinned entity tables (UnitComponentData)',
            'the installed data folder (the rack unit resource, read only)'],
        'unit': {'resource': '0x%016X' % shared, 'racks': len(units[shared]),
            'sceneGraph': {'headerOffset': SCENE_GRAPH_AT, 'nextSectionHeaderOffset': NEXT_SECTION_AT,
                'nodes': len(names)},
            'namedNodes': {named[h]: names.index(h) for h in sorted(named) if h in names},
            'otherUnits': {'0x%016X' % u: [r['path'] for r in pod['racks'] if unit_of[r['resource']] == u]
                for u in sorted(units) if u != shared}},
        'roles': {'1992741347': 'weapon (the main weapon node, side 2)',
            '2145467647': 'weapon (the second weapon node, side 1)',
            '85105251': 'backpack (the main backpack node, side 2)',
            '3993544543': 'backpack (beside a weapon, side 1)',
            '3902607911': 'attach_1: the default node of every unconfigured slot; the Leveller\'s slot 1 (side 1, '
                'inside its spawn count) and the Spire Sterilizer rack\'s slot 0 place items there'},
        'leveller': {'rack': leveller['resource'], 'spawnPayloadSize': 2, 'slot1': slot1, 'capacity': 2,
            'answer': 'the EAT-411 Leveller rack spawns 2: slot 0 its launcher at the main weapon node, slot 1 (empty '
                'in vanilla) at attach_1, a node of the one weapon-rack unit (node 17). The spawner reaches slot 1 '
                'inside the count and spawns any non-zero item there; the rack event attaches it at attach_1. So its '
                'capacity is 2 with no spawn-count write. Its physical placement at attach_1 is not live-tested.'},
        'racks': racks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    body = json.dumps(build(), indent=1, sort_keys=True) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != body:
            raise SystemExit('stale: ' + OUTPUT.name)
        print('up to date')
        return
    OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    print('wrote ' + str(OUTPUT.relative_to(ROOT)))


if __name__ == '__main__':
    main()
