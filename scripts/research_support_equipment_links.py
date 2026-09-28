"""Capture native loadout identity evidence for support-equipment call-in linkage. Read-only.

Two entity components carry each loadout item's identity, and both are joined here against the
live StratagemDefinition table:

* LoadoutEntryComponent: `id` (the loadout item id) and `LoadoutItemType`. For support weapons
  the item id is the id of the call-in StratagemDefinition that grants the item.
* LoadoutPackageComponent: the resource package the item is loaded from. A call-in
  StratagemDefinition names the package its delivery needs.

This lets a call-in reach an item its hellpod rack does not attach directly (the placed C4
charge is thrown by the delivered detonator), and it proves the absence of any call-in for
items no StratagemDefinition names (world-pickup support equipment). Scraped wiki text is
recorded as supporting context only. Nothing here writes memory.
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
import snapshot_regions

OUTPUT = ROOT / 'research/support-equipment-links-F5FEE03DCFDB.json'
SUPPORT_RESEARCH = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
WIKI = ROOT / 'data/wiki_support_weapons.json'
ENTRY, PACKAGE = 'LoadoutEntryComponentData', 'LoadoutPackageComponentData'
ENTRY_RECORDS, ENTRY_STRIDE, ENTRY_INDEX = 193, 32, 386
DEPOSIT = 'DepositComponentData'
DEPOSIT_ITEM_OFFSET = 136  # UINT64 member of DepositComponent: the entity the deposit refills
FOCUS = ('B/MD C4 Pack', 'SG-88 Break-Action Shotgun', 'CQC-72 Entrenchment Tool')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def item_types(native):
    """LoadoutItemType names from the cracked list, validated against type-library alias lengths."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from research_booster_authoring import TypeLibrary
    lengths = TypeLibrary(native.typelib, native.probe).lengths('LoadoutItemType')
    names = [line.strip() for line in (entity_research.FILEDIVER / 'hashes/dl_type_names.txt')
        .read_text(encoding='utf-8').splitlines() if line.startswith('LoadoutItemType_')]
    if len(names) != len(lengths) or any(len(name) != lengths[value] for value, name in enumerate(names)):
        raise ValueError('LoadoutItemType names disagree with the type library')
    return {value: name[len('LoadoutItemType_'):] for value, name in enumerate(names)}


def loadout_entries(native):
    frame, body, _, _, _ = native.probe.find_component(native.entities, ENTRY)
    layout = native.typelib_module.layout(native.typelib, ENTRY, structured=True)['members']
    if [(m['offset64'], m['array_or_bits']) for m in layout] != [(0, ENTRY_INDEX), (6176, ENTRY_RECORDS),
            (12352, ENTRY_RECORDS)]:
        raise ValueError('LoadoutEntryComponentData layout changed')
    owners = {}
    for row in range(ENTRY_INDEX):
        resource, record, reserved = struct.unpack_from('<QII', body, row * 16)
        if resource:
            if reserved:
                raise ValueError('loadout entry index reserved field is non-zero')
            owners.setdefault(resource, []).append(record)
    entries = {}
    for resource, records in owners.items():
        if len(records) != 1:
            raise ValueError('loadout entry ownership ambiguous: ' + hexid(resource))
        at = 6176 + records[0] * ENTRY_STRIDE
        item_id, item_type = struct.unpack_from('<II', body, at)
        entries[resource] = {'record': records[0], 'itemId': item_id, 'itemType': item_type}
    return entries, frame


def packages(native):
    owners = native.owners(PACKAGE)
    by_resource, by_package = {}, {}
    for record, resources in owners.items():
        package = struct.unpack_from('<Q', native.record(PACKAGE, record), 8)[0]
        for resource in resources:
            by_resource[resource] = package
            by_package.setdefault(package, set()).add(resource)
    return by_resource, by_package


class References:
    """Locate every occurrence of a resource hash in the entity library and classify it."""

    def __init__(self, native):
        self.native = native
        header = native.probe.HEADER
        frames = []
        for match in re.finditer(b'LDLD', native.entities):
            at = match.start() - 4
            if at < 0:
                continue
            prefix, magic, _, actual, size, _ = header.unpack_from(native.entities, at)
            if prefix == actual and magic == b'LDLD' and at + native.probe.HEADER_SIZE + size <= len(native.entities):
                frames.append((at, at + native.probe.HEADER_SIZE + size, native.names.get(actual)))
        self.frames = sorted(frames)

    def classify(self, resource):
        needle = struct.pack('<Q', resource)
        result = {'ownership': 0, 'self': 0, 'external': []}
        for match in re.finditer(re.escape(needle), self.native.entities):
            at = match.start()
            frame = max((f for f in self.frames if f[0] <= at < f[1]), key=lambda f: f[0], default=None)
            name = frame and frame[2]
            if name in (None, 'EntitySettingsHashmap', ENTRY):
                result['ownership'] += 1  # entity registry / loadout-entry index rows
                continue
            body, capacity, record_offset, size, count = self.native.table(name)
            relative = at - (frame[0] + self.native.probe.HEADER_SIZE)
            if relative < capacity * 16:
                result['ownership'] += 1
                continue
            record = (relative - record_offset) // size
            owners = self.native.owners(name).get(record, [])
            if owners == [resource]:
                result['self'] += 1
            else:
                result['external'].append({'component': name, 'owners': sorted(
                    self.native.path(owner) or hexid(owner) for owner in owners)})
        return result


def main():
    native = entity_research.Native()
    research = json.loads(SUPPORT_RESEARCH.read_text())
    graph = research['nativeSupportGraph']
    types = item_types(native)
    entries, entry_frame = loadout_entries(native)
    package_of, package_owners = packages(native)

    # The loadout tables relied on are byte-identical between the pinned library and the live snapshot.
    _, live_entity = snapshot_regions.region_bytes('entity')
    live_equality = {}
    for name in (ENTRY, PACKAGE, DEPOSIT):
        frame, body, _, _, offset = native.probe.find_component(native.entities, name)
        span = (offset, offset + len(frame))
        live_equality[name] = live_entity[span[0]:span[1]] == native.entities[span[0]:span[1]]
        if not live_equality[name]:
            raise ValueError(name + ' differs live')

    stratagems = json.loads(snapshot_regions.run_lua(r'''
local Reader=require('hd2runtime/runtime/reader')
local stratagem=require('hd2runtime/core/stratagem')
local reader=Reader.new(source)
local out={}
for _,r in ipairs(stratagem.capture_all(source,reader,profile))do
 out[#out+1]={kind=r.record_kind,id=r.id,package=r.package,payloads=r.payloads}
end
return require('hd2runtime/primary_mapper/json').encode(out)
''').decode())
    by_id = {}
    for row in stratagems:
        if row['id'] in by_id:
            raise ValueError('duplicate StratagemDefinition id')
        by_id[row['id']] = row
    stratagem_packages = {}
    for row in stratagems:
        package = int(row['package'], 16)
        if package:
            stratagem_packages.setdefault(package, []).append(row['id'])

    racks = {int(rack['resourceHash'], 16): [int(item, 16) for item in rack['attachedResources']]
        for rack in graph['hellpodRacks']}

    def describe(resource):
        entry = entries.get(resource)
        package = package_of.get(resource)
        return {'resource': hexid(resource), 'path': native.path(resource),
            'loadoutEntry': None if entry is None else {'itemId': entry['itemId'],
                'itemType': types.get(entry['itemType'], str(entry['itemType'])),
                'itemIdIsStratagemId': entry['itemId'] in by_id},
            'package': None if package is None else hexid(package),
            'packageIsStratagemPackage': bool(package and package in stratagem_packages)}

    # Every support weapon root and every rack attachment, with its loadout identity.
    weapons = {}
    for weapon in research['weapons']:
        resources = [int(value, 16) for value in weapon['resourceHashes']]
        weapons[weapon['catalogIdentity']] = [describe(resource) for resource in resources]
    rack_items = {hexid(rack): [describe(item) for item in items] for rack, items in racks.items()}

    # Deposits that refill a specific entity (backpack -> the weapon it feeds).
    deposit_links = []
    deposit_owners = native.owners(DEPOSIT)
    for record, resources in deposit_owners.items():
        target = struct.unpack_from('<Q', native.record(DEPOSIT, record), DEPOSIT_ITEM_OFFSET)[0]
        if target:
            for resource in resources:
                deposit_links.append({'deposit': hexid(resource), 'refills': hexid(target)})

    # Entity deltas can rewrite component data (the Armed Resupply Pods rack delta attaches a turret).
    import research_magazine_attachments as attachment_research
    deltas_file = (attachment_research.DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    base, live_deltas = snapshot_regions.region_bytes('entity_deltas')
    if not (live_deltas[:len(deltas_file)] == deltas_file
            or snapshot_regions.compare_pinned(live_deltas[:len(deltas_file)], base, deltas_file)['identical']):
        raise ValueError('live entity delta table differs from the pinned reference')
    live_equality['entityDeltas'] = True
    references = References(native)
    focus = {}
    for name in FOCUS:
        roots = [int(value, 16) for value in next(w for w in research['weapons']
            if w['catalogIdentity'] == name)['resourceHashes']]
        items = []
        for resource in roots:
            package = package_of.get(resource)
            items.append({**describe(resource),
                'packageOwners': sorted(hexid(value) for value in package_owners.get(package, ())),
                'packageStratagemIds': stratagem_packages.get(package, []),
                'racksAttaching': sorted(hexid(rack) for rack, attached in racks.items() if resource in attached),
                'depositsRefilling': [link['deposit'] for link in deposit_links if link['refills'] == hexid(resource)],
                'entityLibraryReferences': references.classify(resource),
                'entityDeltaOccurrences': deltas_file.count(struct.pack('<Q', resource))})
        focus[name] = items

    wiki = {item['name']: item for item in json.loads(WIKI.read_text(encoding='utf-8'))['weapons']}
    acquisition = {}
    for name in FOCUS:
        text = next((section['text'] for section in wiki[name].get('rawSections', [])
            if section.get('section') == 'Procurement'), '')
        acquisition[name] = {'sourceSection': wiki[name].get('sourceSection'), 'procurement': text[:400]}

    report = {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'pinnedReferences': {'entities': sha(native.entities), 'typelib': sha(native.typelib),
            'loadoutEntryFrame': sha(entry_frame)},
        'liveEquality': live_equality, 'loadoutItemTypes': types,
        'stratagemDefinitions': [{'kind': row['kind'], 'id': row['id'], 'package': row['package'],
            'payloads': row['payloads']} for row in stratagems],
        'supportWeapons': weapons, 'rackItems': rack_items, 'depositLinks': deposit_links,
        'focus': focus, 'wikiAcquisition': acquisition, 'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps(focus, indent=1))


if __name__ == '__main__':
    main()
