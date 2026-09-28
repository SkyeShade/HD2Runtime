"""Capture native evidence for attachment-owned magazine capacity.

Ownership chain (all structural):

  weapon WeaponCustomizationComponentData.DefaultCustomizations[slot 5]
    -> WeaponCustomizableItem (generated_weapon_customization_settings): ID, AddPath
    -> ComponentEntityDeltaStorage entry keyed by that AddPath (generated_entity_deltas)
    -> ComponentDeltaSettings for WeaponMagazineComponentData (component index 5)
    -> ComponentModificationDelta at offsets 136/140/144/148 (capacity, starting,
       supply, spare magazines) with its own data bytes

The live snapshot is used to prove that the delta table is loaded as one private
read-only allocation whose data bytes equal the pinned file, so every delta data
offset is directly addressable at runtime. Published capacities are used only as
correlation fingerprints; they never establish an owner.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent
SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
DATALIB = SIBLINGS / 'StrongerOrbitalLaser/local_research/dependencies/filediver-reference/datalibrary'
OPTIONS = ROOT / 'sdk/AttachmentOptionCapabilities.json'
OUTPUT = ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json'
DELTAS_SHA = '3FADC7C2475558000F9E8AD30E01D52CAEA481E1633E35674ED2864572694F4E'
MAGAZINE_SLOT = 5
MAGAZINE_COMPONENT = 5  # WeaponMagazineComponentData
RELOAD_COMPONENT = 113  # WeaponReloadComponentData
FIELDS = {136: 'capacity', 140: 'startingMagazines', 144: 'magazinesFromSupply', 148: 'spareMagazines'}


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def customization_items(data):
    count = struct.unpack_from('<I', data, 0)[0]
    at, items = 4, []
    for group in range(count):
        size = struct.unpack_from('<I', data, at + 12)[0]
        at += 24
        base = at
        offset, n = struct.unpack_from('<QQ', data, base)
        for k in range(n):
            row = base + offset + k * 88
            (debug, item_id, _nu, _nc, _desc, _fl, _pad, add, _icon, slots_offset, slots_count,
             _uo, _uc, sort) = struct.unpack_from('<QIIIIIIQQQQQQI', data, row)
            name = data[base + debug:data.index(b'\0', base + debug)].decode('utf-8', 'replace')
            slots = [struct.unpack_from('<I', data, base + slots_offset + 4 * j)[0] for j in range(slots_count)]
            items.append({'group': group, 'row': k, 'debugName': name.strip(), 'optionId': item_id,
                'addPath': add, 'slots': slots, 'sortGroups': sort})
        at = base + size
    return items


def entity_deltas(data):
    base = 28
    header = struct.unpack_from('<10Q', data, base)
    hashmap_offset, hashmap_count, settings_offset, settings_count, component_offset, component_count, \
        delta_offset, delta_count, data_offset, data_count = header
    hashmap = [struct.unpack_from('<QI', data, base + hashmap_offset + 16 * i) for i in range(hashmap_count)]
    settings = [struct.unpack_from('<II', data, base + settings_offset + 8 * i) for i in range(settings_count)]
    components = [struct.unpack_from('<III', data, base + component_offset + 12 * i) for i in range(component_count)]
    deltas = [struct.unpack_from('<III', data, base + delta_offset + 12 * i) for i in range(delta_count)]
    result = {}
    for slot, (resource, index) in enumerate(hashmap):
        if not resource:
            continue
        count, first = settings[index]
        entries = []
        for i in range(count):
            component, first_delta, n = components[first + i]
            for j in range(n):
                offset, size, raw = deltas[first_delta + j]
                entries.append({'component': component, 'offset': offset, 'size': size,
                    'dataOffset': base + data_offset + raw,
                    'bytes': data[base + data_offset + raw:base + data_offset + raw + size]})
        if resource in result:
            raise ValueError('duplicate entity delta resource')
        result[resource] = {'hashmapSlot': slot, 'settingsIndex': index, 'entries': entries}
    layout = {'headerOffset': base, 'hashmapOffset': hashmap_offset, 'hashmapCount': hashmap_count,
        'settingsOffset': settings_offset, 'settingsCount': settings_count,
        'componentOffset': component_offset, 'componentCount': component_count,
        'deltaOffset': delta_offset, 'deltaCount': delta_count,
        'dataOffset': data_offset, 'dataCount': data_count}
    return result, layout


def live_tables(files):
    """Find each table's unique allocation in the snapshot and compare it to the file."""
    sys.path.insert(0, str(ROOT / 'sdk')); sys.path.insert(0, str(ROOT / 'scripts'))
    from tools.lua_runner import execute
    import validate_stratagem_authoring_snapshot as validator

    def lua(value):
        return json.dumps(str(value), ensure_ascii=False)
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in validator.sources().items())
    specs = '{' + ','.join('{name=' + lua(name) + ',size=' + str(len(body)) + ',head=' + lua(body[:28].hex()) + '}'
        for name, body in files.items()) + '}'
    program = preload + r'''
local b=require('hd2runtime/core/bytes')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + lua(SNAPSHOT) + r''',{})
local json=require('hd2runtime/primary_mapper/json')
local specs=''' + specs + r'''
local out={}
local cursor=65536;local _,finish=source.system_info()
while cursor<finish do
  local r=source.query(cursor);if not r then break end;cursor=r.base+r.size
  if r.state==0x1000 and r.capture_status==1 and r.base==r.allocation_base then
    for _,s in ipairs(specs)do
      if r.size>=s.size and r.size<=s.size+65536 then
        local h=source.read(r.base,28)
        if h and b.hex(h)==s.head then out[#out+1]={name=s.name,base=r.base,size=r.size,type=r.type,
          protect=r.protect,data=b.hex(source.read(r.base,s.size))} end
      end
    end
  end
end
source.close();return json.encode(out)
'''
    matches = json.loads(execute(program.encode()))
    result = {}
    for name, body in files.items():
        found = [item for item in matches if item['name'] == name]
        if len(found) != 1:
            raise ValueError(f'{name}: expected one live allocation, found {len(found)}')
        item = found[0]
        live = bytes.fromhex(item['data'])
        differing = [at for at in range(0, len(body), 8) if live[at:at + 8] != body[at:at + 8]]
        result[name] = {'allocationSize': item['size'], 'type': item['type'], 'protect': item['protect'],
            'differingQwords': len(differing), 'differingOffsets': differing, 'base': item['base'], 'live': live}
    return result


def build():
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    custom_file = (DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    items = customization_items(custom_file)
    deltas, layout = entity_deltas(deltas_file)
    live = live_tables({'generated_entity_deltas.dl_bin': deltas_file,
        'generated_weapon_customization_settings.dl_bin': custom_file})

    # The live delta table differs only where the header's offset fields became
    # absolute pointers (allocation base + 28 + file offset); all data is identical.
    delta_live = live['generated_entity_deltas.dl_bin']
    # Pointer fields sit at 28 + 8*i (not qword-aligned), so compare windows overlap them.
    if not delta_live['differingOffsets'] or any(at < 24 or at >= 28 + 80
            for at in delta_live['differingOffsets']):
        raise ValueError('live entity delta table differs outside its relocated header offsets')
    relocated = [28 + 8 * i for i in (0, 2, 4, 6, 8)]
    for field in (0, 2, 4, 6, 8):
        value = struct.unpack_from('<Q', delta_live['live'], 28 + 8 * field)[0]
        expected = delta_live['base'] + 28 + struct.unpack_from('<Q', deltas_file, 28 + 8 * field)[0]
        if value != expected:
            raise ValueError('live entity delta header is not base-relative relocation')
    if delta_live['protect'] != 2 or delta_live['type'] != 0x20000:
        raise ValueError('live entity delta allocation is not private read-only')

    by_add = {}
    for item in items:
        by_add.setdefault(item['addPath'], []).append(item)
    magazines = []
    for item in items:
        if MAGAZINE_SLOT not in item['slots']:
            continue
        delta = deltas.get(item['addPath'])
        if not delta:
            continue
        if len(by_add[item['addPath']]) != 1:
            raise ValueError('magazine AddPath is shared by several customization items')
        fields = {}
        for entry in delta['entries']:
            if entry['component'] == MAGAZINE_COMPONENT and entry['offset'] in FIELDS and entry['size'] == 4:
                name = FIELDS[entry['offset']]
                if name in fields:
                    raise ValueError('duplicate magazine delta field')
                fields[name] = {'value': struct.unpack('<I', entry['bytes'])[0], 'componentOffset': entry['offset'],
                    'dataOffset': entry['dataOffset'], 'size': 4}
        if 'capacity' not in fields:
            continue  # heatsink and other slot-5 items own no magazine capacity
        others = collections.Counter(entry['component'] for entry in delta['entries']
            if not (entry['component'] == MAGAZINE_COMPONENT and entry['offset'] in FIELDS))
        magazines.append({'debugName': item['debugName'], 'optionId': f"0x{item['optionId']:08X}",
            'addPath': f"0x{item['addPath']:016X}", 'group': item['group'], 'row': item['row'],
            'hashmapSlot': delta['hashmapSlot'], 'settingsIndex': delta['settingsIndex'],
            'fields': fields, 'otherPatchedComponents': {str(key): value for key, value in sorted(others.items())},
            'reloadPatched': RELOAD_COMPONENT in others})

    # Weapons: native default magazine (resource default) plus imported catalog effects.
    options = json.loads(OPTIONS.read_text())
    by_option = {int(item['addPath'], 16): item for item in magazines}
    weapons = []
    for weapon in options['weapons']:
        default = weapon.get('defaultOption') or {}
        native = by_option.get(int(default['addPath'], 16)) if default.get('addPath') else None
        catalog = [option for category in weapon.get('categories', []) if category['category'] == 'Magazine'
            for option in category['options']]
        base = (default.get('backingBaseValues') or {}).get('capacity')
        published = (default.get('values') or {}).get('capacity')
        entry = {'weapon': weapon['weapon'], 'resources': weapon['resources'],
            'baseRecordCapacity': base, 'nativeDefault': native['addPath'] if native else None,
            'defaultRelationship': 'native_resource_default' if native else None,
            'publishedDefaultCapacity': published, 'catalogOptions': []}
        if native:
            capacity = native['fields']['capacity']['value']
            entry['defaultConsistency'] = ('delta_matches_published_base_differs' if capacity == published and base != capacity
                else 'delta_base_and_published_agree' if capacity == published
                else 'delta_differs_from_published')
        for option in catalog:
            effects = option.get('effects') or {}
            fingerprint = (effects.get('capacityRounds'), effects.get('startingMagazines'), effects.get('maxMagazines'))
            candidates = [item['addPath'] for item in magazines
                if (item['fields']['capacity']['value'], item['fields'].get('startingMagazines', {}).get('value'),
                    item['fields'].get('spareMagazines', {}).get('value')) == fingerprint]
            if option.get('default') and native:
                relation, resolved = 'native_resource_default', native['addPath']
            elif len(candidates) == 1:
                relation, resolved = 'catalog_effect_fingerprint_unique', candidates[0]
            else:
                relation, resolved = ('catalog_effect_fingerprint_ambiguous' if candidates
                    else 'catalog_effect_fingerprint_absent'), None
            entry['catalogOptions'].append({'name': option['name'], 'default': option.get('default', False),
                'effects': {'capacity': fingerprint[0], 'startingMagazines': fingerprint[1],
                    'maxMagazines': fingerprint[2]},
                'relationship': relation, 'attachment': resolved, 'candidates': candidates})
        weapons.append(entry)

    return {'schemaVersion': 1,
        'source': {'snapshot': SNAPSHOT.name, 'mode': 'snapshot', 'writes': 0, 'protectionChanges': 0,
            'fixtureFallback': 'disabled', 'entityDeltasSha256': DELTAS_SHA,
            'customizationSettingsSha256': sha(custom_file)},
        'deltaTable': {'fileSize': len(deltas_file), 'header': deltas_file[:28].hex(), 'layout': layout,
            'live': {'allocationSize': delta_live['allocationSize'], 'protect': delta_live['protect'],
                'type': delta_live['type'], 'relocatedHeaderQwords': sorted(relocated),
                'dataIdenticalToFile': True, 'uniqueAllocation': True},
            'dataOffsetsShared': False},
        'customizationTable': {'fileSize': len(custom_file), 'items': len(items),
            'live': {'allocationSize': live['generated_weapon_customization_settings.dl_bin']['allocationSize'],
                'protect': live['generated_weapon_customization_settings.dl_bin']['protect'],
                'uniqueAllocation': True}},
        'magazineAttachments': magazines, 'weapons': weapons}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n')
    counts = collections.Counter(option['relationship'] for weapon in report['weapons'] for option in weapon['catalogOptions'])
    print(json.dumps({'magazineAttachments': len(report['magazineAttachments']), 'weapons': len(report['weapons']),
        'relationships': counts}, indent=1))


if __name__ == '__main__':
    main()
