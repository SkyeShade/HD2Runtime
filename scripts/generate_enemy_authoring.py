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
ATTACKS = ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json'
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
    'zone.explosive_damage_percentage': (0, 10),
    'damage.standard_damage': (0, 100000), 'damage.durable_damage': (0, 100000), 'damage.ap_direct': (0, 10),
    'damage.ap_slight': (0, 10), 'damage.ap_large': (0, 10), 'damage.ap_extreme': (0, 10),
    'damage.demolition': (0, 1000), 'damage.stagger': (0, 1000), 'damage.push_force': (0, 1000),
    'projectile.velocity': (1, 5000), 'projectile.mass': (0, 1000000), 'projectile.drag': (0, 10),
    'projectile.gravity': (0, 10), 'projectile.pellet_count': (1, 64), 'explosion.inner_radius': (0, 50),
    'explosion.outer_radius': (0, 50), 'explosion.shockwave_radius': (0, 50)}
# Enemy attacks: the DamageInfo rows a class's mounted weapons reach (research/enemy-attacks-*.json). Global settings
# rows, so every write needs allow_shared; the members are the ones player weapons use, but their effect on enemy
# attacks is not live-confirmed, so every write also needs allow_unverified_effect.
DAMAGE_FIELDS = ('damage.standard_damage', 'damage.durable_damage', 'damage.ap_direct', 'damage.ap_slight',
    'damage.ap_large', 'damage.ap_extreme', 'damage.demolition', 'damage.stagger', 'damage.push_force')
PROJECTILE_FIELDS = (('projectile.velocity', 'velocity'), ('projectile.mass', 'mass'), ('projectile.drag', 'drag'),
    ('projectile.gravity', 'gravity'), ('projectile.pellet_count', 'pellet_count'))
EXPLOSION_FIELDS = (('explosion.inner_radius', 'inner_radius'), ('explosion.outer_radius', 'outer_radius'),
    ('explosion.shockwave_radius', 'shockwave_radius'))
# Every attack-settings field: DamageInfo, ProjectileSettings and ExplosionSettings rows are all global settings.
SETTINGS_FIELDS = DAMAGE_FIELDS + tuple(f for f, _ in PROJECTILE_FIELDS + EXPLOSION_FIELDS)
ATTACK_UNVERIFIED = ('The DamageInfo row is reached through this class\'s own mount chain (re-proven before every '
    'write) and its members are the ones player weapons use, but a change to an enemy attack is not yet '
    'live-confirmed.')
# The generic damage constants are legacy fixed-resource ids; typed targets use the player_ constants.
API_CONSTANTS = {'damage.standard_damage': 'hd2.fields.damage.player_standard_damage',
    'damage.durable_damage': 'hd2.fields.damage.player_durable_damage'}
WEAPON_LINK = {'projectile': ('ProjectileWeaponComponentData', 0), 'spray': ('SprayWeaponComponentData', 200)}


projectile_users, explosion_users = {}, {}


def attack_entries(item, schema):
    """Runtime attack entries and their DamageInfo fields for one enemy class (empty without mounted weapons)."""
    attacks, fields = [], []
    for slot in item['slots']:
        if not slot.get('family') or slot['family'] not in WEAPON_LINK or slot.get('weaponEntityRow') is None:
            continue
        component, offset = WEAPON_LINK[slot['family']]
        weapon_type = slot.get('projectileType', slot.get('sprayDamageType'))
        for damage in slot['damage']:
            if not damage.get('values') or not damage.get('settings'):
                continue
            role = damage['role']
            attack_id = f"slot_{slot['slot']}" + ('' if role == 'projectile' else '_' + role.replace('explosion_', ''))
            links = [{'from': 'weapon', 'component': component, 'offset': offset, 'expect': weapon_type}]
            if role == 'projectile':
                links.append({'from': 'settings', 'settings': 'projectile', 'recordType': weapon_type,
                    'offset': 60, 'expect': damage['type']})
            elif role.startswith('explosion_'):
                explosion = slot['explosions'][role.replace('explosion_', '')]
                links.append({'from': 'settings', 'settings': 'projectile', 'recordType': weapon_type,
                    'offset': 144 if role == 'explosion_impact' else 156, 'expect': explosion['type']})
                links.append({'from': 'settings', 'settings': 'explosion', 'recordType': explosion['type'],
                    'offset': 4, 'expect': damage['type']})
            settings = damage['settings']
            attacks.append({'id': attack_id, 'slot': slot['slot'], 'role': role,
                'wikiAttacks': sorted({m['attack'] for m in damage['wikiMatches']}),
                'rowWikiMatches': damage['rowWikiMatches'], 'reviewedClassesReachingRow':
                    damage['reviewedClassesReachingRow'],
                'mount': {'offset': slot['slot'] * 24, 'expect': slot['weapon']},
                'weapon': {'resource': slot['weapon'], 'entityRow': slot['weaponEntityRow'],
                    'component': component, 'recordIndex': slot['weaponComponent']['recordIndex'],
                    'indexRow': slot['weaponComponent']['indexRow'],
                    'ownerCount': slot['weaponComponent']['ownerCount']},
                'links': links})
            if role.startswith('explosion_'):
                attacks[-1]['wikiExplosionOf'] = damage.get('explosionWikiMatches') or []
            add_settings_fields(fields, item, attack_id, schema, 'damage', damage['type'], settings,
                [(field_id, damage['values'][field_id.split('.', 1)[1]]) for field_id in DAMAGE_FIELDS])
        weapon = {'resource': slot['weapon'], 'entityRow': slot['weaponEntityRow'], 'component': component,
            'recordIndex': slot['weaponComponent']['recordIndex'], 'indexRow': slot['weaponComponent']['indexRow'],
            'ownerCount': slot['weaponComponent']['ownerCount']}
        projectile = slot.get('projectile') or {}
        if projectile.get('values') and projectile.get('settings'):
            attack_id = f"slot_{slot['slot']}_projectile"
            attacks.append({'id': attack_id, 'slot': slot['slot'], 'role': 'projectile_settings', 'wikiAttacks': [],
                'rowWikiMatches': [], 'reviewedClassesReachingRow': projectile_users[weapon_type],
                'mount': {'offset': slot['slot'] * 24, 'expect': slot['weapon']}, 'weapon': weapon,
                'links': [{'from': 'weapon', 'component': component, 'offset': offset, 'expect': weapon_type}]})
            add_settings_fields(fields, item, attack_id, schema, 'projectile', weapon_type, projectile['settings'],
                [(field_id, projectile['values'][key]) for field_id, key in PROJECTILE_FIELDS])
        for phase, explosion in sorted((slot.get('explosions') or {}).items()):
            if not explosion.get('values') or not explosion.get('settings'):
                continue
            damage = next((d for d in slot['damage'] if d['role'] == 'explosion_' + phase), {})
            attack_id = f"slot_{slot['slot']}_{phase}_explosion"
            attacks.append({'id': attack_id, 'slot': slot['slot'], 'role': 'explosion_settings_' + phase,
                'wikiAttacks': [], 'rowWikiMatches': [], 'wikiExplosionOf': damage.get('explosionWikiMatches') or [],
                'reviewedClassesReachingRow': explosion_users[explosion['type']],
                'mount': {'offset': slot['slot'] * 24, 'expect': slot['weapon']}, 'weapon': weapon,
                'links': [{'from': 'weapon', 'component': component, 'offset': offset, 'expect': weapon_type},
                    {'from': 'settings', 'settings': 'projectile', 'recordType': weapon_type,
                     'offset': 144 if phase == 'impact' else 156, 'expect': explosion['type']}]})
            add_settings_fields(fields, item, attack_id, schema, 'explosion', explosion['type'], explosion['settings'],
                [(field_id, explosion['values'][key]) for field_id, key in EXPLOSION_FIELDS])
    return attacks, fields


def add_settings_fields(fields, item, attack_id, schema, settings_kind, record_type, settings, values):
    for field_id, value in values:
        low, high = RANGES[field_id]
        if not low <= value <= high:
            raise ValueError(f"{item['className']} {attack_id} {field_id} baseline {value} outside reviewed range")
        fields.append({'id': field_id, 'path': 'attack', 'attack': attack_id, 'currentDefault': value,
            'editable': True, 'backing': {'kind': 'settings', 'settings': settings_kind, 'recordType': record_type,
                'group': settings['group'], 'row': settings['row'], 'offset': schema[field_id]['offset'],
                'storage': schema[field_id]['storage'], 'width': 4}})


def row_users(classes):
    """Reviewed classes whose mount chains reach each projectile / explosion row."""
    projectile, explosion = {}, {}
    for item in classes:
        for slot in item['slots']:
            if slot.get('projectileType') is not None:
                projectile.setdefault(slot['projectileType'], set()).add(item['name'])
            for value in (slot.get('explosions') or {}).values():
                explosion.setdefault(value['type'], set()).add(item['name'])
    return ({k: sorted(v) for k, v in projectile.items()}, {k: sorted(v) for k, v in explosion.items()})
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
    attack_research = json.loads(ATTACKS.read_text(encoding='utf-8'))
    attack_classes = {item['className']: item for item in attack_research['classes']}
    users = row_users(attack_research['classes'])
    projectile_users.clear(); projectile_users.update(users[0])
    explosion_users.clear(); explosion_users.update(users[1])
    schema = {item['id']: item for item in json.loads(FIELDS.read_text(encoding='utf-8'))['fields']}
    runtime_schema = {}
    for field_id, item in schema.items():
        low, high = RANGES[field_id]
        runtime_schema[field_id] = {'type': item['type'], 'storage': item['storage'], 'min': low, 'max': high,
            'acknowledgement': None if field_id in PROVEN else 'allow_unverified_effect',
            **({'shared': True} if field_id in SETTINGS_FIELDS else {})}
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
        attacks, attack_fields = attack_entries(attack_classes[item['className']], schema) \
            if item['className'] in attack_classes else ([], [])
        if item['className'] in attack_classes and attack_classes[item['className']]['resource'] != item['resource']:
            raise ValueError('attack research disagrees with the enemy identity: ' + item['className'])
        mount = (attack_classes.get(item['className']) or {}).get('mount')
        fields += attack_fields
        health = item['health']
        enemies[name] = {'name': name, 'className': item['className'], 'wikiName': item['wikiName'],
            'kind': item['kind'], 'faction': item['faction'], 'semanticId': semantic,
            'resource': item['resource'], 'entityRow': item['entityRow'],
            'health': {'component': COMPONENT, 'recordIndex': health['recordIndex'], 'indexRow': health['indexRow'],
                'ownerCount': health['ownerCount'], 'uniqueOwner': health['uniqueOwner']},
            'zones': zones, 'fields': fields,
            **({'mount': {'component': 'MountComponentData', 'recordIndex': mount['recordIndex'],
                'indexRow': mount['indexRow'], 'ownerCount': mount['ownerCount']}, 'attacks': attacks}
               if attacks else {})}
        for alias in {item['className'], item['wikiName']} - {None, name}:
            aliases[alias] = name
        consumers = [name] + health['coOwners']
        shared = not health['uniqueOwner']
        by_attack = {attack['id']: attack for attack in attacks}
        for field in fields:
            target = {'resource': 'enemy', 'enemy': name, 'path': field['path']}
            if field.get('zone'):
                target['zone'] = field['zone']
            if field.get('attack'):
                target['attack'] = field['attack']
            identity = ':'.join(str(target.get(k, '')) for k in ('enemy', 'path', 'zone'))
            object_key = 'backing:' + digest({'enemy': semantic, 'component': COMPONENT})
            if field.get('attack'):
                identity = ':'.join((name, 'attack', field['attack']))
                object_key = 'backing:' + digest({'settings': field['backing']['settings'],
                    'recordType': field['backing']['recordType']})
            instance = {'instanceKey': f"enemy:{slug(item['className'])}:{slug(identity)}:{field['id']}",
                'semanticFieldId': field['id'], 'currentDefault': field['currentDefault'], 'editable': field['editable'],
                'target': target, 'operationGroup': 'operation:' + digest({'object': object_key, 'target': identity})}
            if field.get('attack'):
                attack = by_attack[field['attack']]
                instance.update(shared=True, allowSharedRequired=True, backingObjectId=object_key,
                    sharedConsumers=attack['reviewedClassesReachingRow'], dynamicConsumersPossible=True)
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
            'hasProjectileWeapon': item['weapons']['projectileWeapon'], 'mountsEquipment': item['weapons']['mount'],
            'attacks': [{'id': a['id'], 'mountSlot': a['slot'], 'role': a['role'], 'wikiAttacks': a['wikiAttacks'],
                'rowWikiMatches': a['rowWikiMatches'], 'wikiExplosionOf': a.get('wikiExplosionOf', []),
                'sharedWithClasses': a['reviewedClassesReachingRow'],
                'weaponPath': (next((s['weaponPath'] for s in attack_classes[item['className']]['slots']
                    if s['slot'] == a['slot']), None))} for a in attacks]})
    runtime = {'schema': runtime_schema, 'record': {'component': COMPONENT, 'zoneBase': ZONE_BASE,
        'zoneStride': ZONE_STRIDE}, 'enemies': enemies, 'aliases': dict(sorted(aliases.items()))}
    runtime = migration_overlay.apply('enemy_authoring', runtime)
    summary = dict(research['summary'], fieldInstances=len(instances),
        writableFieldInstances=sum(1 for i in instances if i['editable']),
        proven=sum(1 for i in instances if i['editable'] and i['semanticFieldId'] in PROVEN),
        acknowledged=sum(1 for i in instances if i['editable'] and i['semanticFieldId'] not in PROVEN),
        zones=sum(len(c['zones']) for c in public_classes),
        attacks=sum(len(c['attacks']) for c in public_classes),
        classesWithAttacks=sum(1 for c in public_classes if c['attacks']),
        attackFieldInstances=sum(1 for i in instances if i['target']['path'] == 'attack'),
        attacksNamedForClass=sum(1 for c in public_classes for a in c['attacks'] if a['wikiAttacks']),
        attacksWithRowWikiMatch=sum(1 for c in public_classes for a in c['attacks'] if a['rowWikiMatches']),
        attackResearch=attack_research['summary'])
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
                'apiFieldConstant': API_CONSTANTS.get(field_id, 'hd2.fields.' + field_id),
                'acknowledgement': runtime_schema[field_id]['acknowledgement'],
                'acknowledgementReason': None if field_id in PROVEN else (ATTACK_UNVERIFIED if field_id in SETTINGS_FIELDS else UNVERIFIED),
                'evidence': 'gameplay_proven_member' if field_id in PROVEN else ('mount_chain_structural' if field_id in SETTINGS_FIELDS else 'schema_wiki_correlated'),
                'range': [runtime_schema[field_id]['min'], runtime_schema[field_id]['max']]}
                for field_id, item in schema.items()},
            'sentinels': {'zone.health = -1': 'the zone uses the main health pool (read-only)',
                'explosive damage percentage = not set': 'explosions resolve through another zone (read-only)'},
            'readOnlyFlags': ['fatal', 'downsOnDeath', 'mainHealthCapped'],
            'attacks': {'chain': 'class MountComponent slot -> mounted weapon entity -> ProjectileWeapon (+0) / '
                    'SprayWeapon (+200) -> ProjectileSettings (+60 damage, +144/+156 explosions) -> '
                    'ExplosionSettings (+4 damage) -> DamageInfo; every link is re-read live before a write',
                'ids': 'slot_<n> (projectile direct hit), slot_<n>_impact / slot_<n>_expiry (its explosions), '
                    'slot_<n>_spray',
                'wikiAttacks': 'wiki attacks of the named or candidate page of the class whose nine values '
                    '(standard, durable, four AP, demolition, stagger, push) equal the row exactly',
                'rowWikiMatches': 'every wiki ranged attack on any page with the same nine values; describes the '
                    'shared row, not the class',
                'sharing': 'DamageInfo rows are global settings; sharedWithClasses lists the reviewed classes whose '
                    'chains reach the row, and other native users (player or neutral weapons) are possible, so '
                    'writes need allow_shared',
                'acknowledgement': 'allow_unverified_effect (a change to an enemy attack is not live-confirmed)'},
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
