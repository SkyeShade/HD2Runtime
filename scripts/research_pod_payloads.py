"""Trace drop-pod (hellpod rack) payload slots and the entities that can fill them. Read-only.

Native model (member identities checked against the pinned type library):

    StratagemDefinition primary payload -> rack entity -> HellpodRackComponent
        payloads[8] RackAttach (64 bytes): item (+0 u64 entity), node (+8), offset, rotation offset,
            animation/audio events, apply_deltas (+48), rack_side (+52)
        random_payload_size (+552), spawn_payload_size (+556)

The first spawn_payload_size slots spawn. Several stratagems can share one rack entity (for example the
EAT-17 call-in and the Surplus EAT Allocation booster's granted stratagem), so the rack is the semantic
owner and every consumer stratagem is published and re-proven.

Replacement candidates are typed, never inferred from names:
* rack payloads: entities that vanilla places in some rack slot (proven rack-spawnable);
* typed pickups: entities whose InteractableComponent zone carries a pickup interact type
  (PickupWeaponSupport, PickupAmmo, PickupHealth, PickupGrenades, PickupSupplies[FromRack]);
* world loot: entities in the loaded LevelGenerationSettings cache (bunker) loot tables.
Package residency is published separately from structural compatibility.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary
from snapshot_image import Snapshot, CAPTURED
import snapshot_regions

OUTPUT = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
LINKS = ROOT / 'research/support-equipment-links-F5FEE03DCFDB.json'
ICONS = ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json'
STRATAGEMS = ROOT / 'schemas/stratagem_authoring_catalog.json'
SUPPORT = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
ENTITY = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
BACKPACK_AMMO = ROOT / 'research/backpack-ammo-F5FEE03DCFDB.json'
RACK, INTERACT, LOADOUT, BACKPACK, WEAPON = ('HellpodRackComponentData', 'InteractableComponentData',
    'LoadoutPackageComponentData', 'BackpackComponentData', 'WeaponDataComponentData')
SLOTS, SLOT_STRIDE, ZONES, ZONE_STRIDE = 8, 64, 8, 136
RACK_MEMBERS = ((0, 'STRUCT', 8, 'payloads'), (552, 'UINT32', 19, 'random_payload_size'),
    (556, 'UINT32', 18, 'spawn_payload_size'))
ATTACH_MEMBERS = ((0, 'UINT64', 4, 'item'), (8, 'UINT32', 4, 'node'), (48, 'UINT8', 12, 'apply_deltas'),
    (52, 'ENUM_UINT32', 9, 'rack_side'))
# InteractType values 0..8: the type-library alias length of each value equals the Filediver name at that
# position (checked below). Later values were renumbered in this build and are not used.
PICKUP_TYPES = {1: 'PickupWeaponPrimary', 2: 'PickupWeaponSidearm', 3: 'PickupWeaponSupport', 4: 'PickupAmmo',
    5: 'PickupHealth', 6: 'PickupGrenades', 7: 'PickupSupplies', 8: 'PickupSuppliesFromRack'}
CATEGORY = {'PickupWeaponSupport': 'support_weapon', 'PickupAmmo': 'ammo', 'PickupHealth': 'stim',
    'PickupGrenades': 'grenade', 'PickupSupplies': 'supply', 'PickupSuppliesFromRack': 'supply',
    'PickupWeaponPrimary': 'primary_weapon', 'PickupWeaponSidearm': 'sidearm'}
# Mission stratagems available in every mission regardless of loadout (game rule).
ALWAYS_AVAILABLE = {'AmmoRack': 'Resupply is a mission stratagem available in every mission.'}


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def check_members(native, name, expected):
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, name, structured=True)['members']}
    proven = []
    for offset, storage, length, label in expected:
        member = members[offset]
        inferred = int(str(member['name']).rsplit('=', 1)[1])
        if member['storage'] != storage or inferred != length:
            raise ValueError(f'{name}+{offset} is not {label}')
        proven.append({'offset': offset, 'member': label, 'storage': storage, 'nameLength': inferred})
    return proven, members


def cache_loot(native):
    """Entities in the loaded LevelGenerationSettings cache loot tables (bunker/cache rewards)."""
    snap = Snapshot(snapshot_regions.SNAPSHOT)
    needle = b'LDLD\x01\x00\x00\x00' + struct.pack('<I', native.probe.dl_hash('LevelGenerationSettings'))
    hits = []
    for region in snap.regions:
        if region['status'] != CAPTURED:
            continue
        pos = 0
        while pos < region['size']:
            snap.handle.seek(region['data_offset'] + pos)
            data = snap.handle.read(min((64 << 20) + 64, region['size'] - pos))
            at = data.find(needle)
            while at >= 0:
                if at < (64 << 20):
                    hits.append(region['base'] + pos + at)
                at = data.find(needle, at + 1)
            pos += 64 << 20
    if len(hits) != 1:
        raise ValueError(f'expected one loaded LevelGenerationSettings instance, found {len(hits)}')

    def read(address, size):
        region = snap.region(address)
        assert region and region['status'] == CAPTURED
        snap.handle.seek(region['data_offset'] + address - region['base'])
        return snap.handle.read(size)
    layout = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'LevelGenerationSettings',
        structured=True)['members']}
    if layout[144]['atom'] != 'ARRAY' or layout[144]['type_hash'] != native.probe.dl_hash('CacheLootTable'):
        raise ValueError('LevelGenerationSettings cache loot member moved')
    instance = hits[0]
    size = struct.unpack_from('<I', read(instance, 24), 12)[0]
    body = read(instance + 24, size)
    pointer, count = struct.unpack_from('<QQ', body, 144)
    tables, entities = [], {}
    for index in range(count):
        raw = read(pointer + index * 40, 40)
        table_id = struct.unpack_from('<I', raw, 0)[0]
        entries_at, entries = struct.unpack_from('<QQ', raw, 24)
        items = []
        for entry in range(entries):
            item = struct.unpack_from('<Q', read(entries_at + entry * 48, 48), 0)[0]
            items.append(hexid(item))
            entities.setdefault(item, []).append(table_id)
        tables.append({'index': index, 'tableId': table_id, 'entries': items})
    return {'source': 'LevelGenerationSettings.cache_loot_tables (loaded instance in the retained snapshot)',
        'tables': tables}, entities


def build() -> dict:
    native = entity_research.Native()
    library = TypeLibrary(native.typelib, native.probe)
    rack_members, _ = check_members(native, 'HellpodRackComponent', RACK_MEMBERS)
    rack_layout = native.typelib_module.layout(native.typelib, 'HellpodRackComponent', structured=True)['members']
    attach_members, _ = check_members(native, rack_layout[0]['type_hash'], ATTACH_MEMBERS)
    zone_type = native.typelib_module.layout(native.typelib, 'InteractableComponent', structured=True)['members'][5]
    zone_members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, zone_type['type_hash'],
        structured=True)['members']}
    if zone_type['offset64'] != 8 or zone_type['array_or_bits'] != ZONES or zone_members[40]['storage'] != 'ENUM_INT32':
        raise ValueError('interact zone layout changed')
    lengths = library.lengths('InteractType')
    order = re.findall(r'\n\t(InteractType_\w+)',
        (entity_research.FILEDIVER / 'datalibrary/enum/interacttype.go').read_text())
    for value, name in PICKUP_TYPES.items():
        if order[value] != 'InteractType_' + name or lengths[value] != len(order[value]):
            raise ValueError('InteractType ' + name + ' is not proven at value ' + str(value))

    _, live = snapshot_regions.region_bytes('entity')
    live_equality = {}
    for name in (RACK, INTERACT, LOADOUT, BACKPACK, WEAPON):
        frame, _, _, _, offset = native.probe.find_component(native.entities, name)
        live_equality[name] = live[offset:offset + len(frame)] == native.entities[offset:offset + len(frame)]
        if not live_equality[name]:
            raise ValueError(name + ' differs live')

    loadout = {o: r for r, owners in native.owners(LOADOUT).items() for o in owners}

    def package_of(resource):
        record = loadout.get(resource)
        if record is None:
            return None
        value = struct.unpack_from('<Q', native.record(LOADOUT, record), 8)[0]
        return hexid(value) if value else None

    interact = {}
    for record, owners in native.owners(INTERACT).items():
        raw = native.record(INTERACT, record)
        kinds = [struct.unpack_from('<i', raw, 8 + zone * ZONE_STRIDE + 40)[0] for zone in range(ZONES)
            if struct.unpack_from('<I', raw, 8 + zone * ZONE_STRIDE)[0]]
        for owner in owners:
            interact[owner] = {'recordIndex': record, 'kinds': kinds,
                'pickups': sorted({PICKUP_TYPES[k] for k in kinds if k in PICKUP_TYPES})}
    backpacks = {o for owners in native.owners(BACKPACK).values() for o in owners}
    weapons = {o for owners in native.owners(WEAPON).values() for o in owners}

    # Names: support catalog, backpacks, stratagem types. Display names only; categories are typed.
    names = {}
    for weapon in json.loads(SUPPORT.read_text())['weapons']:
        for resource in weapon['resourceHashes']:
            names.setdefault(int(resource, 16), weapon['catalogIdentity'])
    for backpack in json.loads(ENTITY.read_text())['backpacks']:
        names[int(backpack['resource'], 16)] = backpack['name']
    for item in json.loads(BACKPACK_AMMO.read_text())['backpackFedWeapons']:
        names[int(item['backpackResource'], 16)] = item['supportWeapon'] + ' Backpack'
    icons = json.loads(ICONS.read_text())
    type_names = {row['value']: row['name'] for row in icons['types']}
    catalog = {entry['root']['id']: name for name, entry in json.loads(STRATAGEMS.read_text())['stratagems'].items()
        if entry.get('root')}
    loot_tables, loot = cache_loot(native)

    rack_owner = {o: r for r, owners in native.owners(RACK).items() for o in owners}
    consumers = {}
    for row in json.loads(LINKS.read_text())['stratagemDefinitions']:
        if not row['payloads']:
            continue
        rack = int(row['payloads'][0], 16)
        if rack not in rack_owner:
            continue
        type_name = type_names.get(row['kind'], str(row['kind']))
        consumers.setdefault(rack, []).append({'id': row['id'], 'kind': row['kind'], 'nativeType': type_name,
            'name': catalog.get(row['id']) or type_name, 'catalogStratagem': catalog.get(row['id']),
            'package': row['package'] if int(row['package'], 16) else None,
            'alwaysAvailable': ALWAYS_AVAILABLE.get(type_name)})
    # Every vanilla rack (with or without a consuming stratagem) is evidence that its items spawn from a rack.
    vanilla_racks = {}
    for record, owners in native.owners(RACK).items():
        raw = native.record(RACK, record)
        for slot in range(SLOTS):
            item = struct.unpack_from('<Q', raw, slot * SLOT_STRIDE)[0]
            if item:
                for owner in owners:
                    vanilla_racks.setdefault(item, set()).add(native.path(owner) or hexid(owner))

    racks, delivered = [], {}
    for rack, rows in sorted(consumers.items(), key=lambda item: rack_owner[item[0]]):
        record = rack_owner[rack]
        raw = native.record(RACK, record)
        random_size, spawn = struct.unpack_from('<II', raw, 552)
        component = native.component(hexid(rack), RACK)
        slots = []
        for slot in range(SLOTS):
            item, node = struct.unpack_from('<QI', raw, slot * SLOT_STRIDE)
            slots.append({'index': slot, 'item': hexid(item) if item else None, 'node': node,
                'applyDeltas': bool(raw[slot * SLOT_STRIDE + 48]),
                'rackSide': struct.unpack_from('<I', raw, slot * SLOT_STRIDE + 52)[0],
                'active': slot < spawn, 'bytesSha256': sha(raw[slot * SLOT_STRIDE:(slot + 1) * SLOT_STRIDE])})
            if item:
                delivered.setdefault(item, set()).add(rack)
        racks.append({'resource': hexid(rack), 'path': native.path(rack), 'recordIndex': record,
            'indexRow': component['index_row'], 'ownerCount': len(native.owners(RACK)[record]),
            'rackPackage': package_of(rack), 'randomPayloadSize': random_size, 'spawnPayloadSize': spawn,
            'configuredSlots': sum(1 for slot in slots if slot['node']), 'slots': slots,
            'consumers': sorted(rows, key=lambda row: (row['catalogStratagem'] is None, row['name']))})

    def category(resource):
        pickup = (interact.get(resource) or {}).get('pickups', [])
        if resource in backpacks:
            return 'backpack'
        typed = [CATEGORY[p] for p in pickup]
        if 'support_weapon' in typed:
            return 'support_weapon'
        for kind in ('ammo', 'stim', 'grenade', 'supply', 'primary_weapon', 'sidearm'):
            if kind in typed:
                return kind
        return None

    candidates = {}
    universe = set(vanilla_racks) | {r for r, i in interact.items() if i['pickups']} | set(loot)
    for resource in universe:
        cat = category(resource)
        path = native.path(resource)
        candidates[resource] = {'resource': hexid(resource), 'path': path, 'category': cat,
            'name': names.get(resource), 'interactTypes': (interact.get(resource) or {}).get('pickups', []),
            'interactRecord': (interact.get(resource) or {}).get('recordIndex'),
            'ownsWeaponData': resource in weapons, 'ownsBackpack': resource in backpacks,
            'package': package_of(resource), 'entityRow': None,
            'rackPayloadOf': sorted(hexid(r) for r in delivered.get(resource, ())),
            'vanillaRackPaths': sorted(vanilla_racks.get(resource, ())),
            'worldLootTables': sorted(set(loot.get(resource, []))), 'standalonePickup': bool(
                (interact.get(resource) or {}).get('pickups'))}
        try:
            candidates[resource]['entityRow'] = native.entity_row(resource)
        except ValueError:
            pass
    return {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'pinnedReferences': {'entities': sha(native.entities), 'typelib': sha(native.typelib)},
        'liveEquality': live_equality,
        'typeLibrary': {'HellpodRackComponent': rack_members, 'RackAttach': attach_members,
            'rackAttachStride': SLOT_STRIDE, 'interactZone': {'offset': 8, 'stride': ZONE_STRIDE, 'interactType': 40},
            'interactTypes': PICKUP_TYPES},
        'worldLoot': loot_tables, 'racks': racks,
        'candidates': sorted(candidates.values(), key=lambda item: (item['category'] or '~', item['path'] or '~',
            item['resource'])), 'writes': 0}


def main() -> None:
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    from collections import Counter
    print('racks with stratagem consumers', len(report['racks']))
    print('candidates by category', dict(Counter(c['category'] for c in report['candidates'])))
    print('world loot entities', sum(1 for c in report['candidates'] if c['worldLootTables']))


if __name__ == '__main__':
    main()
