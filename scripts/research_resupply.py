"""Resupply: the mission stratagem, its definition root, its hellpod rack and its supply-box payload. Read-only.

Proves on build F5FEE03DCFDB, in every retained snapshot (three aboard the ship, four in one mission):

1. Identity. Exactly one StratagemInfo row has the native stratagem type AmmoRack (33), the type whose game UI icon
   key is StratagemRessuply (research/stratagem-icons-F5FEE03DCFDB.json). Its id, group, row, package and payload
   list are identical in every snapshot. A second row of type AmmoRack_PresidentReward (109) is a reward variant
   that shares the rack; it is recorded but not exposed.
2. Definition. The production parser (core/stratagem.lua) reads the row's cooldown (+104), mission uses (+80)
   and call-in scalars. Its payload list is (rack, hellpod) pairs of one rack only.
3. Payload. That rack is the pod-payload catalog's 'Resupply pod' (HellpodRackComponent, four supply-box slots,
   spawn_payload_size 4; research/pod-payloads-F5FEE03DCFDB.json), already writable through hd2.pod_rack.
   Its package is the stratagem's own package; the pickups it delivers are always resident in a mission.
4. Medal. No entity in the decoded entity table is a medal pickup (the only 'medal' resource is the UI
   package packages/content/medals). The one exploration reward entity (exploration_reward_generic) interacts
   through InteractType 50, which lies outside the proven 1..8 pickup range (later values were renumbered in
   this build), and its reward is account progression granted by the game servers. It is not offered.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_regions  # noqa: E402

OUTPUT = ROOT / 'research/resupply-F5FEE03DCFDB.json'
ICONS = ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json'
PODS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap', 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
AMMO_RACK, REWARD = 33, 109
HELLPOD = '0x73F8498BFFDCF415'
STABLE = ('id', 'group', 'row', 'package', 'payloads', 'payload_count', 'cooldown', 'use_count', 'spawn_time',
    'spawn_radius', 'beacon_linger_time', 'extra_travel_time', 'cooldown_failed', 'cooldown_type',
    'max_in_loadout', 'has_shared_uses_pool')
INTERACT = 'InteractableComponentData'
ZONES, ZONE_STRIDE = 8, 136
PICKUP_RANGE = range(1, 9)
REWARD_PATH = 'content/env_shared/assets/exploration_rewards/exploration_reward_generic'

BODY = r'''
local Reader=require('hd2runtime/runtime/reader')
local stratagem=require('hd2runtime/core/stratagem')
local reader=Reader.new(source)
local records=stratagem.capture_all(source,reader,profile)
local out={records=#records,rows={}}
for _,r in ipairs(records)do
 if r.record_kind==33 or r.record_kind==109 then
  out.rows[#out.rows+1]={kind=r.record_kind,id=r.id,group=r.group,row=r.row,package=r.package,
   payloads=r.payloads,payload_count=r.payload_count,cooldown=r.cooldown,use_count=r.use_count,
   spawn_time=r.spawn_time,spawn_radius=r.spawn_radius,beacon_linger_time=r.beacon_linger_time,
   extra_travel_time=r.extra_travel_time,cooldown_failed=r.cooldown_failed,cooldown_type=r.cooldown_type,
   max_in_loadout=r.max_in_loadout,has_shared_uses_pool=r.has_shared_uses_pool}
 end
end
return require('hd2runtime/primary_mapper/json').encode(out)
'''


def snapshot_rows() -> dict:
    observed = {}
    for name in SNAPSHOTS:
        path = build_profile.snapshot_directory() / name
        if not path.exists():
            raise FileNotFoundError('retained snapshot missing: ' + name)
        report = json.loads(snapshot_regions.run_lua(BODY, path).decode())
        kinds = [row['kind'] for row in report['rows']]
        if sorted(kinds) != [AMMO_RACK, REWARD]:
            raise ValueError('AmmoRack rows are not exactly one of each kind in ' + name)
        observed[name] = {row['kind']: row for row in report['rows']}
    first = observed[SNAPSHOTS[0]]
    for name, rows in observed.items():
        for kind in (AMMO_RACK, REWARD):
            for key in STABLE:
                if rows[kind][key] != first[kind][key]:
                    raise ValueError('AmmoRack row field ' + key + ' differs in ' + name)
    return first


def medal_evidence() -> dict:
    import research_entity_authoring as entity_research
    native = entity_research.Native()
    reward = None
    for record, owners in native.owners(INTERACT).items():
        raw = native.record(INTERACT, record)
        kinds = [struct.unpack_from('<i', raw, 8 + zone * ZONE_STRIDE + 40)[0] for zone in range(ZONES)
            if struct.unpack_from('<I', raw, 8 + zone * ZONE_STRIDE)[0]]
        for owner in owners:
            path = native.path(owner) or ''
            if 'medal' in path:
                raise ValueError('an interactable medal entity now exists: ' + path)
            if path == REWARD_PATH:
                reward = {'resource': '0x%016X' % owner, 'path': path, 'interactRecord': record,
                    'interactTypes': [k for k in kinds if k]}
    if reward is None or any(k in PICKUP_RANGE for k in reward['interactTypes']):
        raise ValueError('the exploration reward entity or its interaction changed')
    medal_paths = sorted(p for p in native.paths.values() if 'medal' in p)
    return {'medalPickupEntity': None, 'medalResources': medal_paths, 'explorationReward': reward,
        'provenPickupInteractTypes': [PICKUP_RANGE.start, PICKUP_RANGE.stop - 1],
        'verdict': 'BLOCKED',
        'reason': ('No medal pickup entity exists in the decoded entity table; the only medal resource is the UI '
            'package packages/content/medals. The one exploration reward entity interacts through InteractType 50, '
            'outside the proven pickup types 1..8, and what it grants is account progression decided by the game '
            'servers, so neither its pickup identity nor a safe gameplay effect is proven.')}


def build() -> dict:
    icons = json.loads(ICONS.read_text(encoding='utf-8'))
    types = {row['value']: row for row in icons['types']}
    if (types[AMMO_RACK]['name'], types[AMMO_RACK]['iconKey']) != ('AmmoRack', 'StratagemRessuply'):
        raise ValueError('AmmoRack stratagem type or its UI icon key changed')
    if types[REWARD]['name'] != 'AmmoRack_PresidentReward':
        raise ValueError('AmmoRack reward variant type changed')
    rows = snapshot_rows()
    resupply, reward = rows[AMMO_RACK], rows[REWARD]

    pods = json.loads(PODS.read_text(encoding='utf-8'))
    racks = [r for r in pods['racks'] if any(c['nativeType'] == 'AmmoRack' for c in r['consumers'])]
    if len(racks) != 1:
        raise ValueError('the Resupply rack is not unique in the pod-payload research')
    rack = racks[0]
    consumer_ids = {c['nativeType']: c['id'] for c in rack['consumers']}
    if consumer_ids != {'AmmoRack': resupply['id'], 'AmmoRack_PresidentReward': reward['id']}:
        raise ValueError('the pod research consumers differ from the snapshot roots')
    pairs = [resupply['payloads'][i:i + 2] for i in range(0, len(resupply['payloads']), 2)]
    if not pairs or any(pair != [rack['resource'], HELLPOD] for pair in pairs):
        raise ValueError('the Resupply payload list is not (rack, hellpod) pairs of the Resupply rack')
    if resupply['package'] != rack['rackPackage'] or reward['package'] != rack['rackPackage']:
        raise ValueError('the Resupply stratagem package is not the rack package')
    spawned = [slot for slot in rack['slots'][:rack['spawnPayloadSize']]]
    items = {slot['item'] for slot in spawned}
    if len(items) != 1 or any(not slot['active'] for slot in spawned):
        raise ValueError('the Resupply rack does not spawn one kind of pickup')
    supply = next(c for c in pods['candidates'] if c['resource'] in items)
    if supply['interactTypes'] != ['PickupSupplies', 'PickupSuppliesFromRack'] or supply['package'] is not None:
        raise ValueError('the supply box pickup identity changed')

    root = {key: resupply[key] for key in STABLE}
    root['identityBasis'] = ('The only StratagemInfo row of native type AmmoRack (33, UI icon StratagemRessuply); '
        'id, group, row, package and payload list identical in every retained snapshot of build F5FEE03DCFDB.')
    return {'schemaVersion': 1, 'build': 'F5FEE03DCFDB',
        'snapshots': SNAPSHOTS,
        'stratagem': {'name': 'Resupply', 'family': 'mission', 'nativeType': 'AmmoRack', 'kind': AMMO_RACK,
            'iconKey': types[AMMO_RACK]['iconKey'], 'alwaysAvailable': True, 'currentRoot': root},
        'rewardVariant': {'nativeType': 'AmmoRack_PresidentReward', 'kind': REWARD, 'id': reward['id'],
            'sharesRack': True, 'exposed': False,
            'reason': 'A reward variant with its own definition row; it shares the Resupply rack, so rack payload '
                'changes reach it too (the pod catalog marks the rack shared).'},
        'delivery': {'rack': rack['resource'], 'rackPath': rack['path'], 'hellpod': HELLPOD,
            'payloadPairs': len(pairs), 'rackPackage': rack['rackPackage'],
            'spawnPayloadSize': rack['spawnPayloadSize'], 'configuredSlots': rack['configuredSlots'],
            'slots': [{'slot': slot['index'] + 1, 'item': slot['item'], 'rackSide': slot['rackSide'],
                'active': slot['active']} for slot in rack['slots']],
            'supplyBox': {'resource': supply['resource'], 'path': supply['path'],
                'interactTypes': supply['interactTypes'], 'interactRecord': supply['interactRecord'],
                'ownPackage': None, 'residency': 'Resident in every mission: the Resupply stratagem is always '
                    'available and its package (the rack package) carries the supply box.'}},
        'medal': medal_evidence()}


def main() -> None:
    result = build()
    text = json.dumps(result, indent=2) + '\n'
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(OUTPUT.relative_to(ROOT), hashlib.sha256(text.encode()).hexdigest()[:16])


if __name__ == '__main__':
    main()
