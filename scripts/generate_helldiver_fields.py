"""Generate the type-wide Helldiver fields (hd2.helldiver(); docs/helldiver-fields.md) from
research/avatar-fields-F5FEE03DCFDB.json (research/docs/avatar-fields-F5FEE03DCFDB.md) and the naming layer
schemas/helldiver_fields.json.

- domains/helldiver_fields.lua: the runtime database. The avatar_helldiver identity (resource, the AvatarComponentData
  record 0 and HealthComponentData record 76 identities, the AvatarComponentData table framing, which the runtime
  profile does not carry), the six damage zones and their name hashes, one entry per field instance (offset, storage,
  vanilla value, reviewed range, grade, lifecycle, which private copy shadows it, semantics), and the pinned avatar
  manager layout the private-copy report re-proves before it reads anything.
- sdk/HelldiverFieldCapabilities.json: the public catalog (fields, zones, ranges, grades, lifecycles and
  acknowledgements). No native identifiers are published.

Only members the research grades CONFIRMED or STRONG with a LIVE or SPAWN verdict are exposed: UNKNOWN members (+56,
+84, +340..+388) and the dormant zone explosive percentage (+0x144) are not. Every field needs allow_shared (the type
record is every Helldiver this machine simulates) and allow_unverified_effect (nothing is live-tested).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hd2_archive import resource_hash  # noqa: E402
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
from reference_format import dl_hash, lua  # noqa: E402

RESEARCH = ROOT / 'research/avatar-fields-F5FEE03DCFDB.json'
SCHEMA = ROOT / 'schemas/helldiver_fields.json'
LUA_OUTPUT = ROOT / 'domains/helldiver_fields.lua'
JSON_OUTPUT = ROOT / 'sdk/HelldiverFieldCapabilities.json'
CONTRACT = 'hd2runtime.helldiver.type_fields.v1'
HELLDIVER = '0x4D1C334D294DFA97'
OWNER = 'content/fac_helldivers/cha_avatar/avatar_helldiver'
ZONES = ('head', 'body', 'arm_left', 'arm_right', 'leg_left', 'leg_right')
AVATAR_RECORD, HEALTH_RECORD = 'AvatarComponentData#0', 'HealthComponentData#76'
EXPOSED_VERDICTS = {'WRITABLE_TYPE_LIVE': 'live', 'WRITABLE_TYPE_SPAWN': 'spawn'}
EXPOSED_GRADES = ('CONFIRMED', 'STRONG')
ENUM_NAMES = ('None', 'Critical', 'Normal', 'Reduced', 'Symbolic')
# Which private copy, if the avatar has one, the field's live reader uses instead of the type record:
# 'avatar' (0x508DB0: every avatar field), 'health' (the override-aware 0x507920: ApplyDamage, the explosion factor and
# the spawn copy of zone health) or nil (the hit builder reads the TYPE record, 0x12A1D96 -> 0x507430).
COPY_READER = {'zone.damage_multiplier': None, 'zone.damage_multiplier_dps': None, 'zone.durable_resistance': None,
    'zone.affects_main_health': 'health', 'zone.health': 'health', 'entity.explosive_damage_percentage': 'health'}
SHARED_REASON = ('The avatar_helldiver TYPE record: every Helldiver this machine simulates (the local player, and '
    'whoever else it simulates) reads it, so a write changes them all.')
UNVERIFIED_REASON = ('Native-code proven offline (research/avatar-fields-F5FEE03DCFDB.json: the reader, the record '
    'identity and the snapshot bytes); no change is live-tested.')
PRIVATE_COPIES = ('A Helldiver spawned with an entity delta carries a frozen private copy of the whole record and reads '
    'it instead of the type (the avatar aboard the ship always does; the retained mission avatars did not): a type '
    'write does not '
    'reach it until it spawns again without one. Runtime never writes private copies; a write notes the Helldivers '
    'whose copy keeps its fields, and hd2.helldiver():private_copies() checks them (read-only).')
# The avatar manager members the private-copy report reads, each checked against the pinned instruction that uses it.
LAYOUT_PINS = {'descriptorEntity': (0x508DC3, 'dword ptr [rcx + 8]', 8),
    'copyMapCapacity': (0x508DEB, '[r11 + 0x547c78]', 0x547C78), 'copyMap': (0x508E0A, '[r11 + 0x547c70]', 0x547C70),
    'copies': (0x508E69, '[r11 + 0x547d24]', 0x547D24), 'simulated': (0x82A010, '[r13 + 0x70]', 0x70),
    'descriptors': (0x82A0A0, '[r13 + rbx*8 + 0x110]', 0x110), 'healthCopyMap': (0x50797A, '[r11 + 0x1070]', 0x1070),
    'descriptorFlags': (0x8339D1, '[rcx + 0x14]', 0x14)}


def pins_by_rva(research):
    return {pin['rva']: pin for group in research['code'].values() for pin in group}


def private_copy_layout(research):
    pins = pins_by_rva(research)
    layout = {}
    for key, (rva, operand, value) in LAYOUT_PINS.items():
        pin = pins.get(rva)
        if not pin or operand not in pin['asm']:
            raise ValueError('the pinned avatar manager layout changed: %s at 0x%X' % (key, rva))
        layout[key] = value
    manager = pins[0x508DD2]
    if manager.get('ripTarget') is None or 'r11' not in manager['asm']:
        raise ValueError('the avatar manager global is not pinned')
    layout['global'] = manager['ripTarget']
    if layout['copies'] != layout['copyMap'] + 0xB4:
        raise ValueError('private copies no longer follow the map')
    used = [0x508DD2] + [rva for rva, _, _ in LAYOUT_PINS.values()]
    layout['pins'] = [{'module': 'game', 'rva': rva, 'hex': pins[rva]['bytes'], 'label': pins[rva]['role']}
        for rva in sorted(set(used))]
    layout['recordSize'] = research['identity']['avatarComponent']['recordSize']
    return layout


def avatar_component(identity):
    """The AvatarComponentData table framing (the runtime profile's component descriptor layout)."""
    avatar = identity['avatarComponent']
    index_rows, records, stride = avatar['indexRows'], avatar['records'], avatar['recordSize']
    type_hash = int(avatar['typeHash'], 16)
    if type_hash != dl_hash('AvatarComponentData'):
        raise ValueError('AvatarComponentData type hash changed')
    record_offset = index_rows * 16
    size = record_offset + records * stride
    header = struct.pack('<I4sIIIII', type_hash, b'LDLD', 1, type_hash, size, 1, 0).hex()
    return {'offset': avatar['frameOffset'], 'header': header, 'index': int(avatar['componentIndex'], 16),
        'indices': index_rows, 'records': records, 'record_offset': record_offset, 'stride': stride,
        'type': type_hash}


def research_field(research, definition, zone=None):
    """The research entry for one schema definition (and zone), checked against the schema's offset and storage."""
    record = AVATAR_RECORD if definition['record'] == 'avatar' else HEALTH_RECORD
    matches = []
    for item in research['fields']:
        if item['record'] != record or item['member'] != definition['member']:
            continue
        if zone is None and item.get('zone') not in (None, 'default'):
            continue
        if zone is not None and item.get('zone') != zone:
            continue
        matches.append(item)
    if len(matches) != 1:
        raise ValueError('research entry absent or ambiguous: %s %s' % (definition['id'], zone))
    item = matches[0]
    storage = item['storage'].split()[0]
    if storage != definition['storage']:
        raise ValueError('%s storage %s differs from the research %s' % (definition['id'], definition['storage'],
            item['storage']))
    if zone is None and item['offset'] != definition['offset']:
        raise ValueError('%s offset differs from the research' % definition['id'])
    if zone is not None and item['zoneOffset'] != definition['zoneOffset']:
        raise ValueError('%s zone offset differs from the research' % definition['id'])
    if item['grade'] not in EXPOSED_GRADES or item['verdict'] not in EXPOSED_VERDICTS:
        raise ValueError('%s is not an exposable member (%s, %s)' % (definition['id'], item['grade'], item['verdict']))
    return item


def build():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    if research['source']['writes'] != 0:
        raise ValueError('the avatar fields research must be read-only')
    if not research['pinsIdenticalInAllSnapshots']:
        raise ValueError('a pinned instruction differs between the retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['source']['gameDllSha256'] not in profile:
        raise ValueError('the avatar fields research covers another build than schemas/current.lua')
    identity = research['identity']
    avatar, health = identity['avatarComponent'], identity['healthComponent']
    rows = avatar['rows']
    if (len(rows) != 1 or rows[0]['resource'] != HELLDIVER or rows[0]['record'] != 0
            or avatar['record0']['ownerCount'] != 1 or avatar['record0']['owner'] != OWNER):
        raise ValueError('AvatarComponentData record 0 is not owned by avatar_helldiver alone')
    if health['ownerCount'] != 1 or health['record'] != 76:
        raise ValueError('HealthComponentData record 76 is not owned by avatar_helldiver alone')
    zone_layout = schema['zone']
    zones = []
    for index, zone in enumerate(health['zones']):
        if zone['index'] != index or zone['name'] != ZONES[index] or zone['recordOffset'] != (
                zone_layout['base'] + index * zone_layout['stride']):
            raise ValueError('the avatar damage zones changed')
        zones.append({'id': zone['name'], 'index': index,
            'nameHash': struct.pack('<I', resource_hash(zone['name']) >> 32).hex()})
    if [z['id'] for z in zones] != list(ZONES):
        raise ValueError('the avatar damage zones changed')
    enums = schema['enums']
    for name, values in enums.items():
        if sorted(values.values()) != list(range(len(ENUM_NAMES))):
            raise ValueError('enum ' + name + ' does not name every native value')
    multipliers = research['constants']['multiplierTable_0x21CF898']
    fields, public = [], []

    def add(definition, item, zone=None):
        field_id = definition['id']
        if definition['type'] == 'enum':
            names = {v: k for k, v in enums[definition['enum']].items()}
            vanilla = names[ENUM_NAMES.index(item['vanilla'])]
            low, high = item['range']
            if (low, high) != (0, len(ENUM_NAMES) - 1):
                raise ValueError(field_id + ' enum range changed')
            low = high = None
        else:
            vanilla = item['vanilla']
            low, high = item['range']
            if not low <= vanilla <= high:
                raise ValueError('%s vanilla %r outside the reviewed range' % (field_id, vanilla))
        offset = definition['offset'] if zone is None else (zone_layout['base'] + zone['index'] * zone_layout['stride']
            + definition['zoneOffset'])
        if offset != item['offset']:
            raise ValueError(field_id + ' record offset differs from the research')
        entry = {'id': field_id, 'path': 'entity' if zone is None else 'damage_zone', 'zone': zone and zone['id'],
            'record': definition['record'], 'offset': offset, 'storage': definition['storage'],
            'type': definition['type'], 'enum': definition.get('enum'), 'unit': definition['unit'],
            'currentDefault': vanilla, 'min': low, 'max': high, 'grade': item['grade'],
            'lifecycle': EXPOSED_VERDICTS[item['verdict']], 'reads': item['lifecycle'],
            'copyReader': COPY_READER.get(field_id, 'avatar' if definition['record'] == 'avatar' else None),
            'member': item['member'], 'semantics': item['semantics']}
        fields.append(entry)
        public.append({'semanticFieldId': field_id, 'displayName': definition['display_name'],
            'target': {'resource': 'helldiver', 'path': entry['path'], **({'zone': zone['id']} if zone else {})},
            'type': entry['type'], 'unit': entry['unit'], 'storage': entry['storage'],
            **({'allowedValues': sorted(enums[definition['enum']], key=enums[definition['enum']].get)}
               if definition['type'] == 'enum' else {'min': low, 'max': high}),
            'currentDefault': vanilla, 'grade': item['grade'], 'lifecycle': entry['lifecycle'],
            'reads': item['lifecycle'], 'shadowedByPrivateCopy': entry['copyReader'], 'semantics': item['semantics'],
            'shared': True, 'allowSharedRequired': True, 'acknowledgements': ['allow_shared', 'allow_unverified_effect'],
            'liveTested': False})

    for definition in schema['fields']:
        if 'zoneOffset' in definition:
            for zone in zones:
                add(definition, research_field(research, definition, zone['id']), zone)
        else:
            add(definition, research_field(research, definition))
    runtime = {'source': {'research': RESEARCH.name, 'build': research['source']['build'],
            'gameDllSha256': research['source']['gameDllSha256']},
        'resource': HELLDIVER, 'owner': OWNER, 'name': 'Helldiver',
        'avatar': {'component': 'AvatarComponentData', 'recordIndex': 0, 'indexRow': rows[0]['row'],
            'ownerCount': 1, 'uniqueOwner': True, 'layout': avatar_component(identity)},
        'health': {'component': 'HealthComponentData', 'recordIndex': health['record'], 'indexRow': health['indexRow'],
            'ownerCount': 1, 'uniqueOwner': True},
        'zone': {'base': zone_layout['base'], 'stride': zone_layout['stride'], 'nameOffset': zone_layout['nameOffset']},
        'zones': zones, 'enums': enums, 'multipliers': multipliers, 'speedCap': research['constants']['0x23C7554'],
        'fields': fields, 'privateCopies': private_copy_layout(research),
        'sharedReason': SHARED_REASON, 'unverifiedReason': UNVERIFIED_REASON}
    runtime = migration_overlay.apply('helldiver_fields', runtime)
    catalog = {'contract': CONTRACT, 'schemaVersion': 1, 'source': {'research': RESEARCH.name,
            'build': research['source']['build']},
        'target': {'accessor': 'hd2.helldiver()', 'type': OWNER, 'scope': SHARED_REASON,
            'zones': [{'id': z['id'], 'index': z['index']} for z in zones]},
        'enums': {name: {'values': sorted(values, key=values.get),
            **({'factors': {k: multipliers[v] for k, v in values.items()}} if name == 'damage_multiplier' else {})}
            for name, values in enums.items()},
        'speedCapMetersPerSecond': research['constants']['0x23C7554'],
        'privateCopies': PRIVATE_COPIES,
        'notExposed': [{'member': item['member'], **({'zoneOffset': item['zoneOffset']} if 'zone' in item
                else {'offset': item['offset']}), 'reason': item['verdict']}
            for item in research['fields'] if item['verdict'] not in EXPOSED_VERDICTS
            and item.get('zone') in (None, 'head')],
        'summary': {'fields': len(schema['fields']), 'instances': len(public), 'zones': len(zones)},
        'fieldInstances': public}
    return runtime, catalog


def outputs() -> dict[str, str]:
    runtime, catalog = build()
    return {'domains/helldiver_fields.lua': '-- Generated by scripts/generate_helldiver_fields.py; do not edit.\n'
            'return ' + lua(runtime) + '\n',
        'sdk/HelldiverFieldCapabilities.json': json.dumps(catalog, indent=1, ensure_ascii=True) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale Helldiver field domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
