"""Capture native evidence for attachment-owned magazine capacity.

Ownership chain (all structural):

  weapon WeaponCustomizationComponentData.DefaultCustomizations[slot 5]
    -> WeaponCustomizableItem (generated_weapon_customization_settings): ID, AddPath
    -> ComponentEntityDeltaStorage entry keyed by that AddPath (generated_entity_deltas)
    -> ComponentDeltaSettings for WeaponMagazineComponentData (component index 5)
    -> ComponentModificationDelta at offsets 136/140/144/148 (capacity, starting,
       supply, spare magazines) with its own data bytes

The same delta carries the attachment's other effects. Each is decoded against the pinned
type library: WeaponReloadComponent.duration (+56, FP32), and WeaponDataComponent
weapon_stat_modifiers (+956, eight {WeaponStatModifierType, FP32} pairs terminated by Count).
Visual magazine unit and reload animation patches are recorded as present, never decoded.

Weapon -> option relationships, strongest first:
  native_resource_default     weapon DefaultCustomizations[slot magazine] (pinned entity library)
  catalog_effects_unique      every published effect (ammo, reload, ergonomics) matches one attachment
  catalog_effects_unlock_list several attachments match; exactly one is in the weapon's own unlock list
                              (research/attachment-unlock-lists-F5FEE03DCFDB.json, observed in memory)
Anything else stays ambiguous with its candidates. Unlock-listed attachments that no catalog option
names are published as unlock_listed. None of these completes a sharing scope.

The live snapshot is used to prove that the delta table is loaded as one private
read-only allocation whose data bytes equal the pinned file, so every delta data
offset is directly addressable at runtime. Published values are used only as
correlation fingerprints; they never establish an owner.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent
SNAPSHOT = build_profile.SNAPSHOT
DATALIB = SIBLINGS / 'StrongerOrbitalLaser/local_research/dependencies/filediver-reference/datalibrary'
OPTIONS = ROOT / 'sdk/AttachmentOptionCapabilities.json'
OUTPUT = ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
PLAYER = ROOT / 'schemas/player_weapon_authoring_catalog.json'
DELTAS_SHA = '3FADC7C2475558000F9E8AD30E01D52CAEA481E1633E35674ED2864572694F4E'
MAGAZINE_SLOT = 5
MAGAZINE_COMPONENT = 5  # WeaponMagazineComponentData
RELOAD_COMPONENT = 113  # WeaponReloadComponentData
FIELDS = {136: 'capacity', 140: 'startingMagazines', 144: 'magazinesFromSupply', 148: 'spareMagazines'}
DATA_COMPONENT = 236  # WeaponDataComponentData
CUSTOMIZATION_COMPONENT = 271  # WeaponCustomizationComponentData
COMPONENT_NAMES = {MAGAZINE_COMPONENT: 'WeaponMagazineComponentData', RELOAD_COMPONENT: 'WeaponReloadComponentData',
    DATA_COMPONENT: 'WeaponDataComponentData', CUSTOMIZATION_COMPONENT: 'WeaponCustomizationComponentData'}
RELOAD_DURATION = 56
MODIFIERS, MODIFIER_STRIDE, MODIFIER_COUNT = 956, 8, 8
MAGAZINE_PATH = 128
MODIFIER_ENUM = 'WeaponStatModifierType'


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


def native_layout():
    """Prove the delta component indices and the decoded member layouts; returns modifier names."""
    import research_entity_authoring as entity_research
    from research_booster_authoring import TypeLibrary
    native = entity_research.Native()
    for index, name in COMPONENT_NAMES.items():
        found = native.probe.find_component(native.entities, name)
        if struct.unpack_from('<I', native.entities, found[4] - 4)[0] != index:
            raise ValueError(name + ' component index changed')
    layout = native.typelib_module.layout
    reload = {m['offset64']: m for m in layout(native.typelib, 'WeaponReloadComponent', structured=True)['members']}
    if not (reload[RELOAD_DURATION]['storage'] == 'FP32' and reload[RELOAD_DURATION]['name'].endswith('inferred_length=8')):
        raise ValueError('WeaponReloadComponent +56 is no longer duration')
    data = {m['offset64']: m for m in layout(native.typelib, 'WeaponDataComponent', structured=True)['members']}
    modifiers = data[MODIFIERS]
    if not (modifiers['atom'] == 'INLINE_ARRAY' and modifiers['array_or_bits'] == MODIFIER_COUNT
            and modifiers['name'].endswith('inferred_length=21')):
        raise ValueError('WeaponDataComponent +956 is no longer weapon_stat_modifiers')
    pair = layout(native.typelib, modifiers['type_hash'], structured=True)['members']
    if [(m['offset64'], m['storage']) for m in pair] != [(0, 'ENUM_UINT32'), (4, 'FP32')] \
            or pair[0]['type_hash'] != native.probe.dl_hash(MODIFIER_ENUM):
        raise ValueError('WeaponStatModifierSetting layout changed')
    lengths = TypeLibrary(native.typelib, native.probe).lengths(MODIFIER_ENUM)
    text = (entity_research.FILEDIVER / 'datalibrary/enum/weaponstatmodifiertype.go').read_text(encoding='utf-8')
    import re
    names = re.findall(r'^\s*' + MODIFIER_ENUM + r'_([A-Za-z0-9_]+)', text, re.M)
    if len(names) != len(lengths) or any(len(MODIFIER_ENUM + '_' + names[v]) != lengths[v] for v in lengths):
        raise ValueError('WeaponStatModifierType names disagree with the type library')
    customization = {m['offset64']: m for m in layout(native.typelib, 'WeaponCustomizationComponent',
        structured=True)['members']}
    if customization[0]['array_or_bits'] != 10 or customization[80]['array_or_bits'] != 10:
        raise ValueError('WeaponCustomizationComponent default/slot arrays changed')
    return native, dict(enumerate(names))


def decode_effects(entries, modifier_names):
    """Reload duration and stat modifiers patched by one delta, with their own data offsets."""
    reload, visual, animation, words = None, False, False, {}
    for entry in entries:
        component, offset, size = entry['component'], entry['offset'], entry['size']
        if component == RELOAD_COMPONENT:
            if offset == RELOAD_DURATION and size == 4:
                reload = {'value': round(struct.unpack('<f', entry['bytes'])[0], 6), 'componentOffset': offset,
                    'dataOffset': entry['dataOffset'], 'size': 4}
            elif offset < RELOAD_DURATION:
                animation = True
        elif component == DATA_COMPONENT and MODIFIERS <= offset < MODIFIERS + MODIFIER_STRIDE * MODIFIER_COUNT:
            for at in range(0, size, 4):
                words[offset + at] = (entry['bytes'][at:at + 4], entry['dataOffset'] + at, size == 4)
        elif component == CUSTOMIZATION_COMPONENT and offset == MAGAZINE_PATH:
            visual = True
    modifiers = []
    if words:
        for index in range(MODIFIER_COUNT):
            kind, value = words.get(MODIFIERS + MODIFIER_STRIDE * index), words.get(MODIFIERS + MODIFIER_STRIDE * index + 4)
            if kind is None or value is None:
                raise ValueError('stat modifier pair patched partially')
            kind_value = struct.unpack('<I', kind[0])[0]
            if modifier_names.get(kind_value) == 'Count':
                break
            modifiers.append({'index': index, 'type': kind_value, 'typeName': modifier_names[kind_value],
                'value': round(struct.unpack('<f', value[0])[0], 6),
                'componentOffset': MODIFIERS + MODIFIER_STRIDE * index + 4, 'dataOffset': value[1],
                'ownRow': value[2], 'typeComponentOffset': MODIFIERS + MODIFIER_STRIDE * index,
                'typeDataOffset': kind[1], 'typeOwnRow': kind[2]})
    return {'reload': reload, 'statModifiers': modifiers if words else None,
        'visualMagazinePatched': visual, 'reloadAnimationPatched': animation}


def native_defaults(native, items):
    """Resource default magazine option per player weapon, from the pinned entity library."""
    owners = native.owners('WeaponCustomizationComponentData')
    record_of = {}
    for record, resources in owners.items():
        for resource in resources:
            record_of.setdefault(resource, []).append(record)
    by_id = {item['optionId']: item for item in items}
    result = {}
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        defaults = set()
        for resource in weapon['resources']:
            for record in record_of.get(int(resource, 16), []):
                body = native.record('WeaponCustomizationComponentData', record)
                for at in range(0, 80, 8):
                    slot, option = struct.unpack_from('<II', body, at)
                    if slot == MAGAZINE_SLOT and option in by_id:
                        defaults.add(by_id[option]['addPath'])
        if len(defaults) == 1:
            result[weapon['name']] = defaults.pop()
    return result


def published_fingerprint(option):
    effects = option.get('effects') or {}
    return ((effects.get('capacityRounds'), effects.get('startingMagazines'), effects.get('maxMagazines')),
        effects.get('fullReloadSeconds'), effects.get('ergonomicsDelta'))


def matches(attachment, fingerprint):
    ammo, reload, ergonomics = fingerprint
    fields = attachment['fields']
    if (fields['capacity']['value'], fields.get('startingMagazines', {}).get('value'),
            fields.get('spareMagazines', {}).get('value')) != ammo:
        return False
    native_reload = (attachment['effects']['reload'] or {}).get('value')
    if reload is not None and native_reload is not None and abs(native_reload - reload) > 0.01:
        return False
    native_ergonomics = next((m['value'] for m in attachment['effects']['statModifiers'] or []
        if m['typeName'] == 'Add_Ergonomics'), None)
    return abs((ergonomics or 0) - (native_ergonomics or 0)) <= 0.01


def build():
    native, modifier_names = native_layout()
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
            'reloadPatched': RELOAD_COMPONENT in others,
            'effects': decode_effects(delta['entries'], modifier_names)})

    # Weapons: native default magazine (resource default), the weapon's own unlock list, and
    # imported catalog options correlated by every published effect.
    options = json.loads(OPTIONS.read_text())
    by_option = {int(item['addPath'], 16): item for item in magazines}
    defaults = native_defaults(native, items)
    unlock = json.loads(UNLOCK_LISTS.read_text())
    listed_by_weapon = {entry['weapon']: [option['addPath'] for option in entry['options']
        if MAGAZINE_SLOT in option['slots'] and int(option['addPath'], 16) in by_option]
        for entry in unlock['weapons'] if entry['weapon'] and entry['weaponKind'] == 'player'}
    catalog_weapons = {weapon['weapon']: weapon for weapon in options['weapons']}
    names = sorted(set(catalog_weapons) | {name for name, path in defaults.items() if path in by_option}
        | {name for name, listed in listed_by_weapon.items() if listed})
    weapons = []
    for name in names:
        weapon = catalog_weapons.get(name) or {'weapon': name, 'resources': [], 'categories': []}
        default = weapon.get('defaultOption') or {}
        native_path = defaults.get(name)
        native = by_option.get(native_path) if native_path else None
        if default.get('addPath') and native and int(default['addPath'], 16) != native_path:
            raise ValueError(name + ': catalog default disagrees with the native resource default')
        listed = listed_by_weapon.get(name)
        catalog = [option for category in weapon.get('categories', []) if category['category'] == 'Magazine'
            for option in category['options']]
        if not (native or catalog or listed):
            continue
        base = (default.get('backingBaseValues') or {}).get('capacity')
        published = (default.get('values') or {}).get('capacity')
        entry = {'weapon': weapon['weapon'], 'resources': weapon['resources'],
            'baseRecordCapacity': base, 'nativeDefault': native['addPath'] if native else None,
            'defaultRelationship': 'native_resource_default' if native else None,
            'publishedDefaultCapacity': published, 'unlockList': listed is not None,
            'unlockListed': listed or [], 'catalogOptions': []}
        if native:
            capacity = native['fields']['capacity']['value']
            entry['defaultConsistency'] = ('delta_matches_published_base_differs' if capacity == published and base != capacity
                else 'delta_base_and_published_agree' if capacity == published
                else 'delta_differs_from_published')
        for option in catalog:
            fingerprint = published_fingerprint(option)
            candidates = [item['addPath'] for item in magazines if matches(item, fingerprint)]
            in_list = [path for path in candidates if listed and path in listed]
            if option.get('default') and native:
                relation, resolved = 'native_resource_default', native['addPath']
            elif len(candidates) == 1:
                relation, resolved = 'catalog_effects_unique', candidates[0]
            elif len(candidates) > 1 and len(in_list) == 1:
                relation, resolved = 'catalog_effects_unlock_list', in_list[0]
            else:
                relation, resolved = ('catalog_effects_ambiguous' if candidates else 'catalog_effects_absent'), None
            if option.get('default') and native and native['addPath'] not in candidates and candidates:
                raise ValueError(name + ': native default does not carry the published default effects')
            entry['catalogOptions'].append({'name': option['name'], 'default': option.get('default', False),
                'effects': {'capacity': fingerprint[0][0], 'startingMagazines': fingerprint[0][1],
                    'maxMagazines': fingerprint[0][2], 'fullReloadSeconds': fingerprint[1],
                    'ergonomicsDelta': fingerprint[2]},
                'relationship': relation, 'attachment': resolved, 'candidates': candidates,
                'unlockListedCandidates': in_list if listed is not None else None})
        named = {option['attachment'] for option in entry['catalogOptions'] if option['attachment']}
        entry['unlockListedOnly'] = [path for path in entry['unlockListed']
            if path not in named and path != entry['nativeDefault']]
        weapons.append(entry)

    return {'schemaVersion': 2,
        'source': {'snapshot': SNAPSHOT.name, 'mode': 'snapshot', 'writes': 0, 'protectionChanges': 0,
            'fixtureFallback': 'disabled', 'entityDeltasSha256': DELTAS_SHA,
            'customizationSettingsSha256': sha(custom_file),
            'unlockLists': UNLOCK_LISTS.name},
        'components': {str(index): name for index, name in sorted(COMPONENT_NAMES.items())},
        'statModifierTypes': {str(value): name for value, name in sorted(modifier_names.items())},
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
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    counts = collections.Counter(option['relationship'] for weapon in report['weapons'] for option in weapon['catalogOptions'])
    print(json.dumps({'magazineAttachments': len(report['magazineAttachments']), 'weapons': len(report['weapons']),
        'relationships': counts}, indent=1))


if __name__ == '__main__':
    main()
