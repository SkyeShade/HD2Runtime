"""Generate guarded mounted-weapon authoring (vehicles, Exosuits, GATER) from native evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import generate_entity_authoring

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json'
JSON_OUTPUT = ROOT / 'sdk/VehicleWeaponCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/vehicle_weapon_authoring.lua'
DAMAGE = (('standard_damage', 4, 'i32', 'Standard damage', 'damage'), ('durable_damage', 8, 'i32', 'Durable damage', 'damage'),
    ('ap_direct', 12, 'u32', 'Armor penetration (direct)', 'armor_class'), ('ap_slight', 16, 'u32', 'Armor penetration (slight angle)', 'armor_class'),
    ('ap_large', 20, 'u32', 'Armor penetration (large angle)', 'armor_class'), ('ap_extreme', 24, 'u32', 'Armor penetration (extreme angle)', 'armor_class'),
    ('demolition', 28, 'u32', 'Demolition force', 'force'), ('stagger', 32, 'u32', 'Stagger force', 'force'),
    ('push_force', 36, 'u32', 'Push force', 'force'))
PROJECTILE = (('velocity', 32, 'f32', 'Projectile velocity', 'meters_per_second'), ('mass', 36, 'f32', 'Projectile mass', 'kilograms'),
    ('drag', 40, 'f32', 'Projectile drag', None), ('gravity', 44, 'f32', 'Projectile gravity', None),
    ('pellet_count', 28, 'u32', 'Pellets per shot', 'pellets'), ('penetration_slowdown', 64, 'f32', 'Penetration slowdown', None),
    ('lifetime', 52, 'f32', 'Projectile lifetime', 'seconds'))
EXPLOSION = (('inner_radius', 16, 'f32', 'Explosion inner radius', 'meters'),
    ('outer_radius', 20, 'f32', 'Explosion outer radius', 'meters'),
    ('shockwave_radius', 24, 'f32', 'Explosion shockwave radius', 'meters'))
RELOAD_UNVERIFIED = ('Schema-labelled native reload duration; the in-game reload of a mounted weapon after an edit is '
    'not yet gameplay-confirmed.')
UNVERIFIED = ('Native ownership is proven structurally, but no working reference mod has confirmed this mounted '
    'weapon field in game yet.')
# Gameplay evidence: fields changed by known-working reference mods on exactly these native records
# (mount chains traced in research/vehicle-weapons-F5FEE03DCFDB.json). Other fields need allow_unverified_effect.
_EXO45_DAMAGE = ('standard_damage', 'durable_damage', 'ap_direct', 'ap_slight', 'ap_large', 'ap_extreme')
GAMEPLAY_EVIDENCE = {
    ('M-103 Supply FRV / gun', 'weapon.capacity'): 'Better M-103 FRV Turret 1.31',
    ('EXO-49 Emancipator Exosuit / left_gun', 'weapon.capacity'): 'Emancipator Ammo v1',
    ('EXO-49 Emancipator Exosuit / right_gun', 'weapon.capacity'): 'Emancipator Ammo v1',
    ('EXO-51 Lumberer Exosuit / left_gun', 'weapon.capacity'): 'Lumberer Ammo v1.1',
    ('EXO-51 Lumberer Exosuit / right_gun', 'weapon.capacity'): 'Lumberer Ammo v1.1',
    **{('EXO-45 Patriot Exosuit / ' + arm, field): 'EXO-45 Patriot Buff 1.12.0'
        for arm in ('left_gun', 'right_gun')
        for field in ('weapon.capacity', 'entity.health', 'entity.armor', 'zone.health', 'zone.armor')},
    ('EXO-45 Patriot Exosuit / right_gun', 'weapon.fire_rate'): 'EXO-45 Patriot Buff 1.12.0',
    **{('EXO-45 Patriot Exosuit / right_gun', 'damage.primary.' + field): 'EXO-45 Patriot Buff 1.12.0'
        for field in _EXO45_DAMAGE},
    **{('EXO-45 Patriot Exosuit / left_gun', 'damage.primary.' + field): 'EXO-45 Patriot Buff 1.12.0'
        for field in ('standard_damage', 'durable_damage', 'ap_large', 'ap_extreme', 'stagger')},
}
ADDENDS_BLOCKER = ('ProjectileWeaponComponent +128 and +136 are per-weapon damage/armor-penetration addends. The pinned '
    'type library names +128 damage_addends and +136 ap_addends, but the M-103 turret reference mod reports the '
    'opposite in game; the assignment stays read-only until one in-game test separates them.')


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in sorted(value.items(), key=lambda i: str(i[0]))) + '}'
    if isinstance(value, list):
        return '{' + ','.join(lua(item) for item in value) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def mount_label(slot):
    return slot.get('name') or slot.get('attachNodeName') or f"slot_{slot['slot']}"


def consumer_label(item):
    if item['kind'] == 'vehicle_weapon':
        return f"{item['vehicle']} (slot {item['slot']})"
    return item.get('name') or item.get('path') or 'unnamed entity'


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    constants = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}

    def api_constant(field_id):
        public = re.sub(r'^(projectile|damage|explosion)\.(primary|impact|expiry)\.', r'\1.', field_id)
        return constants.get(public)
    runtime_weapons, by_vehicle, public_vehicles, instances = {}, {}, [], []
    # One mounted weapon entity can sit in several mounts (two FRVs, or two slots of one vehicle); its own
    # records then change every one of them.
    mounted_at = {}
    for vehicle in research['vehicles']:
        for slot in vehicle['slots']:
            if slot['isWeapon']:
                mounted_at.setdefault(slot['path'], []).append(f"{vehicle['name']} / {mount_label(slot)}")
    for vehicle in research['vehicles']:
        public_mounts = []
        for slot in vehicle['slots']:
            label = mount_label(slot)
            if not slot['isWeapon']:
                public_mounts.append({'slot': slot['slot'], 'label': label, 'weapon': None,
                    'reason': 'The mount holds no weapon component (rack, seat or bare turret).'})
                continue
            key = f"{vehicle['name']} / {label}"
            semantic = 'vehicle-weapon/v1/' + slug(vehicle['name']) + '/' + slug(label) + '/' + digest({'path': slot['path']})
            own, values = slot['ownership'], slot['values']
            weapon_target = {'resource': 'vehicle_weapon', 'path': 'weapon', 'weapon': key}
            fields, blocked, attacks = [], [], {}

            co_mounted = [other for other in mounted_at[slot['path']] if other != key]

            def field(field_id, name, unit, kind, current, backing, target, scope, consumers=None, ack=None, reason=None,
                      editable=True):
                if scope == 'weapon_local' and co_mounted:
                    scope, consumers = 'shared_mounted_weapon', co_mounted
                shared = scope != 'weapon_local'
                evidence = GAMEPLAY_EVIDENCE.get((key, field_id))
                if not evidence and not ack:
                    ack = 'allow_unverified_effect'
                item = {'semanticFieldId': field_id, 'semanticTarget': field_id, 'displayName': name, 'type': kind,
                    'unit': unit, 'currentDefault': current, 'editable': editable, 'acceptedForWrites': editable,
                    'derivedReadOnly': False, 'backing': backing, 'target': target, 'writeScope': scope,
                    'sharedWithWeapons': consumers or [], 'affectsMultipleWeapons': shared,
                    'dynamicConsumersPossible': backing['kind'] == 'settings', 'reason': reason,
                    'acknowledgement': None if evidence else ack,
                    'acknowledgementReason': None if evidence else RELOAD_UNVERIFIED if field_id == 'reload.duration'
                        else UNVERIFIED, 'gameplayEvidence': evidence}
                fields.append(item)
                return item

            def component(name, offset, storage):
                identity = own[name]
                assert identity.get('uniqueOwner'), f'{key}: {name} record is shared'
                return {'kind': 'component', 'component': name, 'offset': offset, 'storage': storage,
                    'width': 1 if storage == 'u8' else 4, 'recordIndex': identity['recordIndex'],
                    'indexRow': identity['indexRow'], 'ownerCount': identity['ownerCount'], 'uniqueOwner': True}

            def settings(kind, record, offset, storage, role, linkage, **extra):
                return dict({'kind': 'settings', 'settings': kind, 'offset': offset, 'storage': storage, 'width': 4,
                    'group': record['group'], 'row': record['row'], 'recordType': record['recordType'],
                    'settingsType': record['settingsType'], 'branch': role, 'linkage': linkage}, **extra)

            def integer(kind):
                return 'integer' if kind in ('i32', 'u32') else 'number'

            if 'fireRate' in values:
                field('weapon.fire_rate', 'Fire rate', 'rpm', 'number', values['fireRate'],
                    component('ProjectileWeaponComponentData', 8, 'f32'), weapon_target, 'weapon_local')
            if 'magazine' in values:
                magazine = values['magazine']
                for field_id, name, unit, offset, value in (
                        ('weapon.capacity', 'Magazine capacity', 'rounds', 136, magazine['capacity']),
                        ('magazine.starting_magazines', 'Starting magazines', 'magazines', 140, magazine['magazines']),
                        ('magazine.magazines_from_supply', 'Magazines from supply', 'magazines', 144, magazine['refill']),
                        ('magazine.spare_magazines', 'Maximum spare magazines', 'magazines', 148, magazine['max'])):
                    field(field_id, name, unit, 'integer', value, component('WeaponMagazineComponentData', offset, 'u32'),
                        weapon_target, 'weapon_local')
            if values.get('reloadDuration'):
                field('reload.duration', 'Reload duration', 'seconds', 'number', values['reloadDuration'],
                    component('WeaponReloadComponentData', 56, 'f32'), weapon_target, 'weapon_local',
                    ack='allow_unverified_effect')
            elif 'WeaponReloadComponentData' in own:
                blocked.append({'field': 'reload.duration', 'reason': 'Native reload duration is 0 (use the default '
                    'reload ability); a non-zero value would add a timing rather than tune one.'})
            if 'health' in values:
                field('entity.health', 'Mount health', 'health', 'integer', values['health'],
                    component('HealthComponentData', 0, 'i32'), weapon_target, 'weapon_local')
                field('entity.armor', 'Mount armor', 'armor_class', 'integer', values['armor'],
                    component('HealthComponentData', 280, 'u32'), weapon_target, 'weapon_local')
            # A mount with one populated hit zone (Exosuit arms): its zone health/armor are the arm's own.
            zones = [zone for zone in values.get('zones', []) if zone['health'] > 0]
            if len(zones) == 1:
                base = 520 + zones[0]['index'] * 552
                field('zone.health', 'Mount hit zone health', 'health', 'integer', zones[0]['health'],
                    component('HealthComponentData', base + 232, 'i32'), weapon_target, 'weapon_local')
                field('zone.armor', 'Mount hit zone armor', 'armor_class', 'integer', zones[0]['armor'],
                    component('HealthComponentData', base + 216, 'u32'), weapon_target, 'weapon_local')
            elif values.get('zones'):
                blocked.append({'field': 'zone.*', 'reason': 'The mount has no single populated hit zone with its own '
                    'health; zone values follow the main health.'})
            if 'ProjectileWeaponComponentData' in own:
                blocked.append({'field': 'weapon damage/armor-penetration addends', 'reason': ADDENDS_BLOCKER})
            projectile = slot.get('projectile')
            if projectile and projectile.get('settings'):
                others = [consumer_label(c) for c in projectile['firedBy']
                    if not (c['kind'] == 'vehicle_weapon' and c['vehicle'] == vehicle['name'] and c['slot'] == slot['slot'])]
                target = {'resource': 'vehicle_weapon', 'path': 'projectile_reference', 'weapon': key, 'attack': 'primary'}
                attacks['primary'] = {'role': 'primary', 'kind': 'Projectile', 'targetPath': 'projectile_reference'}
                for suffix, offset, storage, name, unit in PROJECTILE:
                    value = projectile['values'][suffix]
                    if suffix == 'lifetime' and not value:
                        blocked.append({'attack': 'primary', 'field': 'projectile.lifetime', 'reason':
                            'Native lifetime is 0 (no explicit limit); only non-zero lifetimes are tunable.'})
                        continue
                    field('projectile.primary.' + suffix, name, unit, integer(storage), value,
                        settings('projectile', projectile['settings'], offset, storage, 'primary', 'projectile'),
                        target, 'shared_projectile', others)
                damage = projectile.get('damage') or {}
                if damage.get('settings'):
                    for suffix, offset, storage, name, unit in DAMAGE:
                        field('damage.primary.' + suffix, name, unit, 'integer', damage['values'][suffix],
                            settings('damage', damage['settings'], offset, storage, 'primary', 'projectile_damage'),
                            target, 'shared_damage', others)
                else:
                    blocked.append({'attack': 'primary', 'field': 'damage.*', 'reason':
                        'The projectile references no DamageInfo; its damage is delivered by another object.'})
                for phase, explosion in sorted((projectile.get('explosions') or {}).items()):
                    if not explosion.get('settings'):
                        continue
                    role = phase
                    target_x = {'resource': 'vehicle_weapon', 'path': 'explosion', 'weapon': key, 'attack': role}
                    attacks[role] = {'role': role, 'kind': 'Explosion', 'parentRole': 'primary', 'targetPath': 'explosion'}
                    extra = {'parentRole': 'primary', 'phase': phase}
                    for suffix, offset, storage, name, unit in EXPLOSION:
                        field('explosion.' + role + '.' + suffix, name, unit, 'number', explosion['values'][suffix],
                            settings('explosion', explosion['settings'], offset, storage, role, 'projectile_explosion', **extra),
                            target_x, 'shared_explosion', others)
                    if (explosion.get('damage') or {}).get('settings'):
                        for suffix, offset, storage, name, unit in DAMAGE:
                            field('explosion.' + role + '.damage.' + suffix, 'Explosion ' + name[0].lower() + name[1:], unit,
                                'integer', explosion['damage']['values'][suffix],
                                settings('explosion_damage', explosion['damage']['settings'], offset, storage, role,
                                    'projectile_explosion_damage', **extra), target_x, 'shared_damage', others)
            spray = slot.get('spray')
            if spray and spray.get('settings'):
                others = [consumer_label(c) for c in spray['usedBy']
                    if not (c['kind'] == 'vehicle_weapon' and c['vehicle'] == vehicle['name'] and c['slot'] == slot['slot'])]
                target = {'resource': 'vehicle_weapon', 'path': 'attack', 'weapon': key, 'attack': 'primary'}
                attacks['primary'] = {'role': 'primary', 'kind': 'Spray', 'targetPath': 'attack'}
                for suffix, offset, storage, name, unit in DAMAGE:
                    field('damage.primary.' + suffix, name, unit, 'integer', spray['values'][suffix],
                        settings('damage', spray['settings'], offset, storage, 'primary', 'spray_damage'),
                        target, 'shared_damage', others)
            chain = {'vehicle': vehicle['name'], 'vehicleResource': vehicle['resource'], 'slot': slot['slot'],
                'mountPath': slot['path']}
            runtime_weapons[key] = {'name': key, 'semanticId': semantic, 'supportWeapon': True, 'vehicleWeapon': True,
                'vehicle': vehicle['name'], 'mount': label, 'slot': slot['slot'], 'resources': [slot['path']],
                'attackResource': slot['path'], 'ordinaryWritesBlocked': False, 'mountChain': chain,
                'attacks': attacks, 'fields': fields}
            by_vehicle.setdefault(vehicle['name'], {})[str(slot['slot'])] = key
            groups = {'local': [], 'projectile': [], 'damage': [], 'explosion': []}
            for item in fields:
                group = ('local' if item['writeScope'] in ('weapon_local', 'shared_mounted_weapon') else 'explosion'
                    if item['semanticFieldId'].startswith('explosion.') else 'projectile'
                    if item['semanticFieldId'].startswith('projectile.') else 'damage')
                instance = {'instanceKey': 'vehicle-field/v1/' + slug(key) + '/' + slug(item['semanticFieldId']) + '/'
                    + digest({'weapon': key, 'field': item['semanticFieldId']}), 'weapon': key,
                    'weaponSemanticId': semantic, 'semanticFieldId': item['semanticFieldId'],
                    'apiFieldConstant': api_constant(item['semanticFieldId']),
                    'target': item['target'], 'displayName': item['displayName'], 'unit': item['unit'],
                    'type': item['type'], 'baseline': item['currentDefault'], 'writable': item['editable'],
                    'scope': item['writeScope'], 'allowSharedRequired': item['affectsMultipleWeapons'],
                    'otherConsumers': item['sharedWithWeapons'], 'acknowledgement': item['acknowledgement'],
                    'gameplayEvidence': item['gameplayEvidence'],
                    'backingComponent': item['backing'].get('component') or item['backing']['settings']}
                instances.append(instance)
                groups[group].append(instance['instanceKey'])
            public_mounts.append({'slot': slot['slot'], 'label': label, 'weapon': {'key': key, 'semanticId': semantic,
                'nativePath': slot.get('nativePath'), 'attacks': sorted(attacks), 'fieldGroups': groups,
                'values': {k: values[k] for k in ('fireRate', 'magazine', 'reloadDuration', 'health', 'armor', 'infiniteAmmo')
                    if k in values},
                'ownership': {'weaponLocal': sorted(c for c in own if c != 'MountComponentData'),
                    'alsoMountedAt': co_mounted,
                    'sharedProjectileConsumers': len((projectile or {}).get('firedBy', [])),
                    'sharedDamageConsumers': ((projectile or {}).get('damage') or {}).get('projectileUsers')},
                'blocked': blocked}})
        public_vehicles.append({'vehicle': vehicle['name'], 'mounts': public_mounts})
    summary = {'vehicles': len(public_vehicles),
        'weaponMounts': sum(1 for v in public_vehicles for m in v['mounts'] if m['weapon']),
        'fieldInstances': len(instances), 'writableFieldInstances': sum(1 for i in instances if i['writable']),
        'weaponLocalFields': sum(1 for i in instances if i['scope'] == 'weapon_local'),
        'sharedMountedWeaponFields': sum(1 for i in instances if i['scope'] == 'shared_mounted_weapon'),
        'sharedFields': sum(1 for i in instances if i['scope'] != 'weapon_local'),
        'gameplayProvenFields': sum(1 for i in instances if i['gameplayEvidence']),
        'unverifiedEffectFields': sum(1 for i in instances if i['acknowledgement'] == 'allow_unverified_effect'),
        'byField': dict(sorted(Counter(i['semanticFieldId'] for i in instances).items()))}
    public = {'contract': 'hd2runtime.vehicle_weapon.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'ownershipModel': ['vehicle MountComponentData slot path', 'mounted weapon entity (own component records: '
            'weapon-local)', 'ProjectileWeaponComponentData.projectile_type -> ProjectileSettings -> DamageInfo / '
            'ExplosionSettings (shared settings rows: allow_shared)'],
        'scopes': {'weapon_local': 'The mounted weapon\'s own component record; one owner, one mount.',
            'shared_mounted_weapon': 'The same mounted weapon entity sits in several mounts; its own records change '
                'all of them (allow_shared).',
            'shared_projectile': 'A ProjectileSettings row fired by every listed consumer.',
            'shared_damage': 'A DamageInfo row; every projectile or spray referencing it changes.',
            'shared_explosion': 'An ExplosionSettings row referenced by the projectile.'},
        'vehicles': public_vehicles, 'fieldInstances': instances, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'writesDuringGeneration': 0}}
    if re.search(r'0x[0-9a-f]{8,}', json.dumps(public).lower()):
        raise ValueError('public vehicle weapon catalog leaks a native identifier')
    runtime = {'weapons': runtime_weapons, 'byVehicle': by_vehicle, 'summary': summary}
    return runtime, public


def outputs():
    runtime, public = build()
    return {LUA_OUTPUT: '-- Generated by scripts/generate_vehicle_weapon_authoring.py; do not edit.\nreturn ' + lua(migration_overlay.apply('vehicle_weapon_authoring', runtime)) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale vehicle weapon outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
