"""Generate domains/carrier_pod_items.lua: what a custom stratagem may put in its carrier's OWN pod rack
(research/docs/carrier-pod-items-F5FEE03DCFDB.md, sections 1, 2, 6 and 11), from
research/carrier-pod-items-F5FEE03DCFDB.json (the exclusive carrier racks, the item catalogue and its verdicts),
research/carrier-pod-nodes-F5FEE03DCFDB.json (every slot's node, its role, the capacity) and
research/pod-payloads-F5FEE03DCFDB.json (each rack record's identity: record index, index row, owner count).

* the HellpodRackComponentData record layout the rack writes use (RackAttach slots, the sizes, +560);
* each EXCLUSIVE carrier rack, by its carrier stratagem: its resource, record identity, spawn size, all eight slots
  (item, node, rack side, apply_deltas, role, usable) and its capacity (usable slots inside the spawn count, distinct
  nodes of the rack unit; never a spawn-count write);
* every catalogued equipment entity a pod could hold, by its typed key (support_weapon/<name>, backpack/<name>,
  player_weapon/<name>), with its kind, resource, verdict and confidence; and per kind its slot role and status:
  CONFIRMED (support weapons and backpacks: vanilla rack items), UNVERIFIED (primaries: allow_unverified_effect), or
  REFUSED (secondaries, throwables, entities without a pickup zone).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

ITEMS = ROOT / 'research/carrier-pod-items-F5FEE03DCFDB.json'
NODES = ROOT / 'research/carrier-pod-nodes-F5FEE03DCFDB.json'
POD = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
OUTPUT = 'domains/carrier_pod_items.lua'
EMPTY = '0x0000000000000000'
KINDS = {
    'support_weapon': {'role': 'weapon', 'status': 'confirmed', 'verdicts': ['VANILLA_RACK_ITEM'],
        'doc': 'a support weapon its own vanilla rack delivers (CONFIRMED)'},
    'backpack': {'role': 'backpack', 'status': 'confirmed', 'verdicts': ['VANILLA_RACK_ITEM'],
        'doc': 'a backpack (CONFIRMED; no instance modify)'},
    'primary': {'role': 'weapon', 'status': 'unverified', 'verdicts': ['CANDIDATE'],
        'doc': 'a primary with a PickupWeaponPrimary zone (STRONG, not live-tested): allow_unverified_effect'},
    'sidearm': {'status': 'refused', 'doc': 'secondaries are refused in this pass (PLAUSIBLE at most)'},
    'throwable': {'status': 'refused', 'doc': 'a throwable is the live explosive entity (UNKNOWN): refused'},
    'unresolved': {'status': 'refused', 'doc': 'no resolvable name'},
}


def build() -> dict:
    items = json.loads(ITEMS.read_text(encoding='utf-8'))
    nodes = json.loads(NODES.read_text(encoding='utf-8'))
    pod = json.loads(POD.read_text(encoding='utf-8'))
    if items['writes'] or items['protectionChanges'] or nodes['writes']:
        raise ValueError('the carrier pod research must be read-only')
    if any(items['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    identity = {r['resource']: r for r in pod['racks']}
    exclusive = {r['resource']: r for r in items['carrierRacks']['racks'] if r['exclusiveCarrierRack']}
    racks = {}
    for r in nodes['racks']:
        ex = exclusive.get(r['resource'])
        if not ex:
            continue
        ident = identity[r['resource']]
        if ident['ownerCount'] != 1 or ident['randomPayloadSize'] != 0:
            raise ValueError(r['path'] + ': an exclusive carrier rack must have one owner and no random payload')
        slots = []
        for s in r['slots']:
            slots.append({'index': s['index'], 'item': s['item'] or EMPTY, 'node': s['node']['hash'],
                'nodeName': s['node']['name'], 'nodeIndex': s['node']['index'], 'rackSide': s['rackSide'],
                'applyDeltas': s['applyDeltas'], 'role': s['role'], 'usable': s['usable'], 'itemKind': s['itemKind']})
        racks[ex['carrier']] = {'resource': r['resource'], 'path': r['path'], 'stableId': None,
            'recordIndex': ident['recordIndex'], 'indexRow': ident['indexRow'], 'ownerCount': ident['ownerCount'],
            'spawnPayloadSize': r['spawnPayloadSize'], 'capacity': r['capacity'], 'usable': r['usableSlots'],
            'roles': [s['role'] for s in r['slots'] if s['usable']], 'vanillaPopulated': r['vanillaPopulated'],
            'slots': slots}
        consumer = next(c for c in ident['consumers'] if c['name'] == ex['carrier'])
        racks[ex['carrier']]['stableId'] = consumer.get('id') or consumer.get('stableId')
    leveller = racks['EAT-411 Leveller']
    if leveller['capacity'] != 2 or leveller['slots'][1]['nodeName'] != 'attach_1':
        raise ValueError('the Leveller facts changed')
    catalog = {}
    for i in items['itemCatalog']['items']:
        kind = KINDS.get(i['kind'])
        supported = bool(kind and i['verdict'] in kind.get('verdicts', []))
        catalog[i['key']] = {'label': i['label'], 'kind': i['kind'], 'resource': i['resource'],
            'verdict': i['verdict'], 'confidence': i['confidence'], 'supported': supported,
            'status': kind['status'] if supported else 'refused'}
    return {'source': {'research': [ITEMS.name, NODES.name, POD.name], 'build': nodes['build']},
        'record': {'slotStride': 64, 'slots': 8, 'item': 0, 'node': 8, 'applyDeltas': 48, 'rackSide': 52,
            'randomPayloadSize': 552, 'spawnPayloadSize': 556, 'byte560': 560},
        'unit': {'resource': nodes['unit']['resource'], 'nodes': nodes['unit']['sceneGraph']['nodes'],
            'named': nodes['unit']['namedNodes']},
        'kinds': {k: {key: v for key, v in d.items() if key != 'verdicts'} for k, d in KINDS.items()},
        'racks': racks, 'items': catalog}


def outputs() -> dict[str, str]:
    return {OUTPUT: '-- Generated by scripts/generate_carrier_pod_items.py; do not edit.\nreturn ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale generated carrier pod domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
