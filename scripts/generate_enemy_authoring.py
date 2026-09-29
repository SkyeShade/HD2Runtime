"""Generate enemy and enemy-structure authoring from research/enemy-authoring-F5FEE03DCFDB.json.

- domains/enemy_authoring.lua: the runtime database. Compact: each class carries its health-record identity once, its
  damage zones, and one short entry per field (value, offset, storage, editability); field semantics (type,
  acknowledgement, range) come from schemas/enemy_fields.json.
- sdk/EnemyAuthoringCapabilities.json: the public catalog (every class, its wiki name or candidates, zones with
  their wiki labels and flags, and every field instance). No native identifiers are published.

A class is authored through hd2.enemy(name) (or hd2.structure(name)): name is the wiki name when the research
resolved one, or the native class name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/enemy_fields.json'
LUA_OUTPUT = ROOT / 'domains/enemy_authoring.lua'
JSON_OUTPUT = ROOT / 'sdk/EnemyAuthoringCapabilities.json'
CONTRACT = 'hd2runtime.enemy.guarded_authoring.v1'
COMPONENT = 'HealthComponentData'
ZONE_BASE, ZONE_STRIDE = 520, 552
# Members already gameplay-proven on this component (Bastion, Shield Relay); everything else needs acknowledgement.
PROVEN = {'entity.health', 'entity.armor', 'zone.health', 'zone.armor', 'zone.affects_main_health'}
UNVERIFIED = ('HealthComponent member identified by its hidden member-name length and exact agreement with the wiki '
    'anatomy tables; its gameplay effect on enemies is not yet live-confirmed.')
RANGES = {'entity.health': (1, 10000000), 'zone.health': (1, 10000000), 'entity.armor': (0, 10), 'zone.armor': (0, 10),
    'zone.affects_main_health': (0, 10), 'entity.constitution': (0, 10000000), 'zone.constitution': (0, 10000000),
    'entity.constitution_rate': (-1000000, 1000000), 'entity.durable_resistance': (0, 10),
    'zone.durable_resistance': (0, 10), 'entity.explosive_damage_percentage': (0, 10),
    'zone.explosive_damage_percentage': (0, 10)}
MAIN_KEYS = {'entity.health': ('main', 'health'), 'entity.armor': ('default', 'armor'),
    'entity.constitution': ('main', 'constitution'), 'entity.constitution_rate': ('main', 'constitutionRate'),
    'entity.durable_resistance': ('default', 'durableResistance'),
    'entity.explosive_damage_percentage': ('default', 'explosiveDamagePercentage')}
ZONE_KEYS = {'zone.health': 'health', 'zone.armor': 'armor', 'zone.affects_main_health': 'affectsMainHealth',
    'zone.constitution': 'constitution', 'zone.durable_resistance': 'durableResistance',
    'zone.explosive_damage_percentage': 'explosiveDamagePercentage'}
SENTINEL_REASONS = {'zone.health': 'This zone uses the main health pool (-1); giving it a pool of its own changes its '
    'behaviour and is not authored.',
    'zone.explosive_damage_percentage': 'This zone carries the not-set sentinel (explosions resolve through another '
    'zone); not authored.', 'entity.explosive_damage_percentage': 'The main zone carries the not-set sentinel.'}


def lua(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, dict):
        return '{' + ','.join(('[' + lua(key) + ']=' if not re.fullmatch(r'[A-Za-z_]\w*', str(key))
            else str(key) + '=') + lua(item) for key, item in value.items()) + '}'
    return '{' + ','.join(lua(item) for item in value) + '}'


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


def outputs():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    schema = {item['id']: item for item in json.loads(FIELDS.read_text(encoding='utf-8'))['fields']}
    runtime_schema = {}
    for field_id, item in schema.items():
        low, high = RANGES[field_id]
        runtime_schema[field_id] = {'type': item['type'], 'storage': item['storage'], 'min': low, 'max': high,
            'acknowledgement': None if field_id in PROVEN else 'allow_unverified_effect'}
    enemies, aliases, public_classes, instances = {}, {}, [], []
    for item in sorted(research['classes'], key=lambda c: c['className']):
        name = item['wikiName'] or item['className']
        if name in enemies:
            raise ValueError('duplicate enemy name ' + name)
        semantic = 'enemy/v1/' + item['faction'] + '/' + slug(item['className'])
        pairs = {}
        for pair in (item.get('wikiEvidence') or {}).get('zonePairs', []):
            if pair['unambiguous']:
                pairs.setdefault(pair['wikiZone'], []).append(pair['zone'])
        wiki_zone = {}
        for label, indexes in pairs.items():
            for ordinal, index in enumerate(sorted(indexes), 1):
                wiki_zone[index] = label if len(indexes) == 1 else f'{label} #{ordinal}'
        zones = [{'id': f"zone_{z['index']}", 'index': z['index'], 'name': z['name'],
            'wikiZone': wiki_zone.get(z['index'])} for z in item['zones']]
        fields = []

        def add(field_id, path, current, offset, zone=None):
            sentinel = current is None or (field_id == 'zone.health' and current == -1)
            entry = {'id': field_id, 'path': path, 'currentDefault': current,
                'backing': {'offset': offset, 'storage': schema[field_id]['storage'], 'width': 4},
                'editable': not sentinel}
            if zone is not None:
                entry['zone'] = zone
            if sentinel:
                entry['reason'] = SENTINEL_REASONS.get(field_id, 'Not-set sentinel value; not authored.')
            else:
                low, high = RANGES[field_id]
                if not low <= current <= high:
                    raise ValueError(f"{item['className']} {field_id} baseline {current} outside reviewed range")
            fields.append(entry)
        for field_id, (section, key) in MAIN_KEYS.items():
            add(field_id, 'entity', item[section][key], schema[field_id]['offset'])
        for zone in item['zones']:
            base = ZONE_BASE + zone['index'] * ZONE_STRIDE
            for field_id, key in ZONE_KEYS.items():
                add(field_id, 'damage_zone', zone[key], base + schema[field_id]['zoneOffset'], f"zone_{zone['index']}")
        health = item['health']
        enemies[name] = {'name': name, 'className': item['className'], 'wikiName': item['wikiName'],
            'kind': item['kind'], 'faction': item['faction'], 'semanticId': semantic,
            'resource': item['resource'], 'entityRow': item['entityRow'],
            'health': {'component': COMPONENT, 'recordIndex': health['recordIndex'], 'indexRow': health['indexRow'],
                'ownerCount': health['ownerCount'], 'uniqueOwner': health['uniqueOwner']},
            'zones': zones, 'fields': fields}
        for alias in {item['className'], item['wikiName']} - {None, name}:
            aliases[alias] = name
        consumers = [name] + health['coOwners']
        shared = not health['uniqueOwner']
        for field in fields:
            target = {'resource': 'enemy', 'enemy': name, 'path': field['path']}
            if field.get('zone'):
                target['zone'] = field['zone']
            identity = ':'.join(str(target.get(k, '')) for k in ('enemy', 'path', 'zone'))
            object_key = 'backing:' + digest({'enemy': semantic, 'component': COMPONENT})
            instance = {'instanceKey': f"enemy:{slug(item['className'])}:{slug(identity)}:{field['id']}",
                'semanticFieldId': field['id'], 'currentDefault': field['currentDefault'], 'editable': field['editable'],
                'target': target, 'operationGroup': 'operation:' + digest({'object': object_key, 'target': identity})}
            if field.get('reason'):
                instance['reason'] = field['reason']
            instances.append(instance)
        public_classes.append({'name': name, 'className': item['className'], 'wikiName': item['wikiName'],
            'wikiCandidates': item['wikiCandidates'], 'wikiCandidateEvidence': item['wikiCandidateEvidence'],
            'kind': item['kind'], 'faction': item['faction'],
            'semanticId': semantic, 'accessor': 'hd2.structure' if item['kind'] == 'structure' else 'hd2.enemy',
            'identity': {'basis': 'hash-verified resource path', 'path': item['path'],
                'wikiEvidence': item.get('wikiEvidence')},
            'main': item['main'], 'mainZone': {k: item['default'][k] for k in ('armor', 'durableResistance',
                'explosiveDamagePercentage')},
            'sharedHealthRecord': shared, 'healthRecordConsumers': consumers, 'allowSharedRequired': shared,
            'backingObjectId': 'backing:' + digest({'enemy': semantic, 'component': COMPONENT}),
            'planGroup': 'plan:enemy:' + slug(item['className']),
            'zones': [dict(zone, **{k: z[k] for k in ('health', 'armor', 'affectsMainHealth', 'constitution',
                'durableResistance', 'explosiveDamagePercentage', 'fatal', 'downsOnDeath', 'mainHealthCapped')})
                for zone, z in zip(zones, item['zones'])],
            'hasProjectileWeapon': item['weapons']['projectileWeapon'], 'mountsEquipment': item['weapons']['mount']})
    runtime = {'schema': runtime_schema, 'record': {'component': COMPONENT, 'zoneBase': ZONE_BASE,
        'zoneStride': ZONE_STRIDE}, 'enemies': enemies, 'aliases': dict(sorted(aliases.items()))}
    runtime = migration_overlay.apply('enemy_authoring', runtime)
    summary = dict(research['summary'], fieldInstances=len(instances),
        writableFieldInstances=sum(1 for i in instances if i['editable']),
        proven=sum(1 for i in instances if i['editable'] and i['semanticFieldId'] in PROVEN),
        acknowledged=sum(1 for i in instances if i['editable'] and i['semanticFieldId'] not in PROVEN),
        zones=sum(len(c['zones']) for c in public_classes))
    document = {'contract': CONTRACT, 'schemaVersion': 1, 'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'source': research['source'], 'summary': summary,
        'model': {'component': 'HealthComponent (the component vehicles, deployables and every enemy share)',
            'identity': 'Native-first: each class is a hash-verified resource path. A wiki name is attached only for '
                'a one-to-one exact anatomy match carried by at least two damage zones; otherwise wikiCandidates '
                'lists every wiki page whose anatomy the class matches exactly. Candidates are not identity: '
                'wikiCandidateEvidence gives the strength of each (zonesMatched 0 = only the main health and armor '
                'numbers agree, which can be coincidence; kindAgrees false = the page is an enemy and the class a '
                'structure path, or the reverse).',
            'fields': {field_id: {'displayName': item['display_name'], 'type': item['type'], 'unit': item.get('unit'),
                'apiFieldConstant': 'hd2.fields.' + field_id,
                'acknowledgement': runtime_schema[field_id]['acknowledgement'],
                'acknowledgementReason': None if field_id in PROVEN else UNVERIFIED,
                'evidence': 'gameplay_proven_member' if field_id in PROVEN else 'schema_wiki_correlated',
                'range': [runtime_schema[field_id]['min'], runtime_schema[field_id]['max']]}
                for field_id, item in schema.items()},
            'sentinels': {'zone.health = -1': 'the zone uses the main health pool (read-only)',
                'explosive damage percentage = not set': 'explosions resolve through another zone (read-only)'},
            'readOnlyFlags': ['fatal', 'downsOnDeath', 'mainHealthCapped'],
            'appliesTo': 'entities spawned after the write; already-spawned enemies keep their current health'},
        'unresolvedWikiPages': research['unresolvedWikiPages'], 'classes': public_classes,
        'fieldInstances': instances,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0}}
    body = json.dumps(document, indent=1) + '\n'
    return {LUA_OUTPUT: '-- Generated by scripts/generate_enemy_authoring.py; do not edit.\nreturn ' + lua(runtime) + '\n',
        JSON_OUTPUT: body}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale enemy authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(parser.parse_args().check)) or 'up to date')
