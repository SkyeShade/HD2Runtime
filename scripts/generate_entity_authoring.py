"""Generate guarded vehicle and backpack authoring metadata from retained native evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import support_callin_linkage

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
BACKPACK_AMMO = ROOT / 'research/backpack-ammo-F5FEE03DCFDB.json'
SHIELD_RESEARCH = ROOT / 'research/ballistic-shield-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/entity_fields.json'
VEHICLE_OUTPUT = ROOT / 'sdk/VehicleAuthoringCapabilities.json'
BACKPACK_OUTPUT = ROOT / 'sdk/BackpackAuthoringCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/entity_authoring.lua'

ZONE_BASE, ZONE_STRIDE = 520, 552
TIER_ORDER = ('gameplay_proven', 'gameplay_proven_combined', 'schema_proven', 'live_write_verified',
    'structural_reference')
# Semantic members promoted by the reviewed reference-mod proofs. The key is the
# semantic field; the value names the exact entity the proof ran on.
GAMEPLAY_ENTITY = {
    'entity.health': {'TD-220 Bastion MK XVI', 'FX-12 Shield Generator Relay'},
    'entity.armor': {'TD-220 Bastion MK XVI'},
    'zone.armor': {'TD-220 Bastion MK XVI'},
    'zone.affects_main_health': {'TD-220 Bastion MK XVI'},
    'recharge.time': {'LIFT-850 Jump Pack'},
    'jump.vertical_launch_velocity': {'LIFT-850 Jump Pack'},
    'shield.radius': {'FX-12 Shield Generator Relay'},
    'shield.durability': {'FX-12 Shield Generator Relay'},
    'payload.lifetime': {'FX-12 Shield Generator Relay'},
}
COMBINED_ENTITY = {'zone.health': {'FX-12 Shield Generator Relay'}}
# FRVWeaponSwap committed the slot-0 reference write on exactly these records.
LIVE_WRITE_ENTITY = {'mount.weapon': {'M-102 Gunner FRV', 'FRV (Super Earth variant)'}}
PROOF_MOD = {
    'entity.health': 'BastionReArmored', 'entity.armor': 'BastionReArmored',
    'zone.armor': 'BastionReArmored', 'zone.affects_main_health': 'BastionReArmored',
    'zone.health': 'ShieldRelayImprovements', 'shield.radius': 'ShieldRelayImprovements',
    'shield.durability': 'ShieldRelayImprovements', 'payload.lifetime': 'ShieldRelayImprovements',
    'recharge.time': 'JumpPackImprovements', 'jump.vertical_launch_velocity': 'JumpPackImprovements',
    'mount.weapon': 'FRVWeaponSwap',
}


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def vehicle_key(name):
    return 'vehicle/v1/' + slug(name) + '/' + digest(name)


def backpack_key(name):
    return 'backpack/v1/' + slug(name) + '/' + digest(name)


# A deposit's live amount travels as the engine network field type deposit_value (int, 10 bits, min 0), and the
# owning peer's field validator clamps the live count to 0..1023 in place on every write, solo included
# (research/deposit-limits-F5FEE03DCFDB.json). Larger definitions show only until the first shot or resupply.
DEPOSIT_LIMIT = 1023
AMMO_RANGE = {'deposit.capacity': (1, DEPOSIT_LIMIT), 'deposit.start_amount': (0, DEPOSIT_LIMIT),
    'deposit.refill_amount': (0, DEPOSIT_LIMIT)}
AMMO_RANGE_REASON = ('the live deposit amount is the engine network field deposit_value (10 bits): the game clamps '
    'it to 1023 on every write, so a larger value shows only until the first shot or resupply')
AMMO_LABELS = {'deposit.capacity': 'Backpack ammo capacity', 'deposit.start_amount': 'Starting backpack ammo',
    'deposit.refill_amount': 'Backpack ammo from supply'}
AMMO_UNVERIFIED = ('The backpack DepositComponent is the proven ammunition store (exact capacity and supply '
    'fingerprints), but no edit has been confirmed in game yet.')


# SH-20 Ballistic Shield (research/ballistic-shield-F5FEE03DCFDB.json): every bullet that hits the shield resolves
# to damage zone 0 "shield" (it lists the hit actors), whose own armor is the active plate armor. The default-zone
# armor that entity.armor writes is consulted only for hits on an actor no zone lists. Both are copied into the
# shield's health instance when it spawns.
SHIELD_PLATE_REASON = ('Armor of the "shield" damage zone, which every hit on the shield plate resolves to. Copied '
    'into the shield when it spawns: a shield already in the world keeps its armor. Not yet shown in game.')
SHIELD_BODY_FIELDS = {
    ('SH-20 Ballistic Shield Backpack', 'entity.armor'): {'readOnly': ('Default-zone armor: the game uses it only for '
            'a hit on a part no damage zone lists, and the shield plate is listed by its "shield" zone, so it does not '
            'change what bullets hitting the shield do (live-failed 2026-09-29: armor 5 here, the AP 4 HMG still '
            "damaged the shield). Use hd2.backpack('SH-20 Ballistic Shield Backpack'):damage_zone('shield') with "
            'zone.armor.'),
        'effect': {'activeSource': 'DORMANT_OR_METADATA', 'activeSourceProven': True,
            'appliesWhen': 'entity_spawn', 'instantiationOnly': True, 'activeField': 'damage_zone shield / zone.armor'}},
    ('SH-51 Directional Shield', 'entity.health'): {'acknowledgement': 'allow_unverified_effect',
        'acknowledgementReason': ('Health of the SH-51 backpack body. The energy barrier is a separate entity with its '
            "own health record; which of the two the barrier's hits reach is not traced."),
        'effect': {'activeSource': 'AMBIGUOUS', 'activeSourceProven': False, 'appliesWhen': 'entity_spawn',
            'instantiationOnly': True}},
    ('SH-51 Directional Shield', 'entity.armor'): {'acknowledgement': 'allow_unverified_effect',
        'acknowledgementReason': ('Default-zone armor of the SH-51 backpack body. The energy barrier is a separate '
            "entity with its own damage zone; which of the two the barrier's hits reach is not traced."),
        'effect': {'activeSource': 'AMBIGUOUS', 'activeSourceProven': False, 'appliesWhen': 'entity_spawn',
            'instantiationOnly': True}},
}


def shield_plate(name, backpack, health):
    """The SH-20's shield zone field, re-proven against the research: same entity, record and one owner."""
    research = json.loads(SHIELD_RESEARCH.read_text(encoding='utf-8'))
    active = research['answer']['activeField']
    if backpack['resource'] != active['resource']:
        return None
    if (health['recordIndex'], health['indexRow']) != (active['recordIndex'], active['indexRow']) \
            or active['ownerCount'] != 1 or health['ownerCount'] != 1 or active['zoneName'] != 'shield':
        raise ValueError(name + ': shield zone research no longer matches the entity catalog')
    index = active['zoneIndex']
    if active['recordOffset'] != ZONE_BASE + index * ZONE_STRIDE + 216:
        raise ValueError(name + ': shield zone armor offset changed')
    return {'zoneId': zone_id(index), 'index': index, 'name': active['zoneName'], 'armor': active['vanilla'],
        'armorOffset': active['recordOffset'], 'guards': [{'offset': g['offset'], 'hex': g['hex']}
            for g in active['guards']],
        'extra': {'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': SHIELD_PLATE_REASON,
            'min': 0, 'max': 10,
            'effect': {'activeSource': 'ACTIVE_AT_INSTANTIATION', 'activeSourceProven': True,
                'appliesWhen': 'entity_spawn', 'instantiationOnly': True,
                'damageRule': 'AP - armor >= 1: full damage; AP == armor: 65%; AP < armor: none'},
            'zoneActors': active['zoneActors']}}


def backpack_ammo_name(weapon):
    return weapon + ' Backpack'


def weapon_key(resource, label):
    return 'mounted-weapon/v1/' + slug(label) + '/' + digest({'mountedEntity': resource})


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in sorted(value.items())) + '}'
    if isinstance(value, list):
        return '{' + ','.join(lua(item) for item in value) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def api_constants():
    """Mirror generate_sdk constant allocation so descriptors publish the Lua constant."""
    constants = defaultdict(dict)
    sdk = json.loads((ROOT / 'schemas/sdk.json').read_text())
    for resource in sdk['resources'].values():
        for name, field in resource['fields'].items():
            constants[field['domain']][name.replace('.', '_')] = name
    player = json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
    for field_id in sorted({field['semanticFieldId'] for weapon in player['weapons'] for field in weapon['fields']}
            | {field['id'] for field in player['fieldDefinitions']}):
        domain, name = field_id.split('.', 1); constant = name.replace('.', '_')
        if constant in constants[domain] and constants[domain][constant] != field_id:
            constant = 'player_' + constant
        constants[domain][constant] = field_id
    for definition in json.loads((ROOT / 'schemas/stratagem_fields.json').read_text())['fields']:
        domain, name = definition['id'].split('.', 1); constant = name.replace('.', '_')
        if constant in constants[domain] and constants[domain][constant] != definition['id']:
            constant = 'definition_' + constant
        constants[domain][constant] = definition['id']
    for definition in json.loads(FIELDS.read_text())['fields']:
        domain, name = definition['id'].split('.', 1); constant = name.replace('.', '_')
        if constant in constants[domain] and constants[domain][constant] != definition['id']:
            constant = 'entity_' + constant
        constants[domain][constant] = definition['id']
    for definition in json.loads((ROOT / 'schemas/attachment_fields.json').read_text())['fields']:
        domain, name = definition['id'].split('.', 1); constant = name.replace('.', '_')
        if constant in constants[domain] and constants[domain][constant] != definition['id']:
            constant = 'attachment_' + constant
        constants[domain][constant] = definition['id']
    for definition in json.loads((ROOT / 'schemas/payload_fields.json').read_text())['fields']:
        domain, name = definition['id'].split('.', 1)
        constants[domain][name.replace('.', '_')] = definition['id']
    for definition in json.loads((ROOT / 'schemas/booster_fields.json').read_text())['fields']:
        domain, name = definition['id'].split('.', 1); constant = name.replace('.', '_')
        if definition['id'] in constants[domain].values():
            continue  # Booster targets reuse the existing semantic field and its constant.
        if constant in constants[domain] and constants[domain][constant] != definition['id']:
            constant = 'booster_' + constant
        constants[domain][constant] = definition['id']
    return constants


class Builder:
    def __init__(self, family, research):
        self.family = family
        self.research = research
        self.fields = []
        self.definitions = {item['id']: item for item in json.loads(FIELDS.read_text())['fields']}
        self.definitions.update({item['id']: item for item in
            json.loads((ROOT / 'schemas/stratagem_fields.json').read_text())['fields']})
        constants = api_constants()
        self.constants = {value: f'hd2.fields.{domain}.{constant}'
            for domain, items in constants.items() for constant, value in items.items()}
        self.proofs = {name: item for name, item in research['referenceMods'].items()}

    def evidence(self, entity, field_id):
        if entity in GAMEPLAY_ENTITY.get(field_id, set()):
            tier = 'gameplay_proven'
        elif entity in COMBINED_ENTITY.get(field_id, set()):
            tier = 'gameplay_proven_combined'
        elif entity in LIVE_WRITE_ENTITY.get(field_id, set()):
            tier = 'live_write_verified'
        elif field_id == 'mount.weapon':
            tier = 'structural_reference'
        else:
            tier = 'schema_proven'
        mod = PROOF_MOD.get(field_id)
        proof = None
        if mod:
            item = self.proofs[mod]
            proof = (item.get('gameplayProofs') or {}).get(field_id) or item.get('liveWriteVerified')
        proven_on = sorted(GAMEPLAY_ENTITY.get(field_id, set()) | COMBINED_ENTITY.get(field_id, set())
            | LIVE_WRITE_ENTITY.get(field_id, set()))
        return {'tier': tier, 'referenceMod': mod, 'proof': proof, 'provenOn': proven_on,
            'sharedTypedSchema': tier == 'schema_proven'}

    def add(self, entity, target, field_id, baseline, backing, editable=True, reason=None, extra=None):
        definition = self.definitions[field_id]
        identity = ':'.join(str(target.get(key, '')) for key in (self.family, 'path', 'zone', 'mount'))
        instance_key = f'{self.family}:{slug(entity)}:{slug(identity)}:{field_id}'
        object_identity = {'component': backing['component'], 'recordIndex': backing['recordIndex']}
        object_key = 'backing:' + digest(object_identity)
        operation_key = 'operation:' + digest({'object': object_key, 'target': identity})
        consumers = [{self.family: owner} for owner in backing['semanticOwners']]
        shared = len(consumers) > 1
        editable = bool(editable and definition.get('writable', False))
        descriptor = {'instanceKey': instance_key, 'semanticFieldId': field_id,
            'displayName': definition['display_name'], 'type': definition['type'],
            'unit': definition.get('unit'), 'currentDefault': baseline, 'editable': editable,
            'reason': None if editable else (reason or definition.get('reason')),
            'target': target, 'backingObjectId': object_key, 'operationGroup': operation_key,
            'planGroup': f'plan:{self.family}:{slug(entity)}', 'requires': 'patch_or_transaction',
            'allowSharedRequired': shared, 'shared': shared, 'sharedConsumers': consumers,
            'sharedScopeKey': 'shared-scope:' + digest({'object': object_key, 'consumers': consumers}),
            'reviewedScopeComplete': True, 'dynamicConsumersPossible': False,
            'backingObjectKind': backing['component'], 'domain': field_id.split('.')[0],
            'apiFieldConstant': self.constants[field_id], 'planPhase': 1, 'dependsOn': [],
            'evidence': self.evidence(entity, field_id),
            'provenance': 'current-build typed entity schema plus exact retained-snapshot baseline'}
        if extra:
            descriptor.update(extra)
        self.fields.append((descriptor, dict(backing)))
        return descriptor

    def public(self):
        return [descriptor for descriptor, _ in self.fields]

    def runtime(self, name):
        result = []
        for descriptor, backing in self.fields:
            if descriptor['target'][self.family] != name:
                continue
            item = {key: descriptor[key] for key in ('instanceKey', 'semanticFieldId', 'type', 'currentDefault',
                'editable', 'reason', 'target', 'operationGroup', 'shared', 'sharedScopeKey')}
            item['sharedConsumers'] = descriptor['sharedConsumers']
            item['allowedValues'] = descriptor.get('allowedValues')
            item['acknowledgement'] = descriptor.get('acknowledgement')
            item['acknowledgementReason'] = descriptor.get('acknowledgementReason')
            item['min'], item['max'] = descriptor.get('min'), descriptor.get('max')
            if descriptor.get('rangeReason'):
                item['rangeReason'] = descriptor['rangeReason']
            for key in ('displayName', 'unit', 'uiGroup'):
                if descriptor.get('uiGroup'):
                    item[key] = descriptor.get(key)
            item['backing'] = {key: backing[key] for key in ('component', 'resource', 'recordIndex', 'indexRow',
                'ownerCount', 'uniqueOwner', 'offset', 'storage', 'width')}
            if backing.get('guards'):
                item['backing']['guards'] = backing['guards']
            result.append(item)
        return result


def component_backing(component, resource, offset, storage, owners):
    width = 8 if storage == 'u64' else 4
    return {'component': component['component'], 'resource': resource,
        'recordIndex': component['recordIndex'], 'indexRow': component['indexRow'],
        'ownerCount': component['ownerCount'], 'uniqueOwner': component['uniqueOwner'],
        'offset': offset, 'storage': storage, 'width': width, 'semanticOwners': owners}


def owner_names(ownership, names_by_resource):
    return sorted(names_by_resource.get(resource, 'non-catalog entity') for resource in ownership['ownerResources'])


def zone_id(index):
    return f'zone_{index}'


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    vehicles_source = research['vehicles']
    names_by_resource = {item['resource']: item['name'] for item in vehicles_source}
    names_by_resource.update({item['resource']: item['name'] for item in research['backpacks']})
    mounted = research['mountedEntities']
    mount_records = {item['record']: item for item in research['mountRecords']}

    # Mounted weapon identity catalog: every structurally weapon-bearing entity already
    # referenced by a MountComponent Path. Raw hashes stay internal.
    weapons = {}
    for resource, item in mounted.items():
        if not item['weapon']:
            continue
        label = item['path'].rsplit('/', 1)[-1] if item['path'] else None
        label_source = 'native_path' if label else 'mount_context'
        if not label:
            for use in item['referencedBy']:
                owners = [names_by_resource[o] for o in mount_records[use['record']]['owners']
                    if o in names_by_resource]
                slot = next(s for s in mount_records[use['record']]['slots'] if s['slot'] == use['slot'])
                if owners:
                    role = slot['name'] or slot['attachNodeName'] or f"slot {use['slot']}"
                    label = f'{owners[0]} {role} weapon'
                    break
        if not label:
            label, label_source = 'unnamed mounted weapon', 'none'
        semantic_id = weapon_key(resource, label)
        references = []
        for use in item['referencedBy']:
            for owner in mount_records[use['record']]['owners'] or [None]:
                references.append({'vehicle': names_by_resource.get(owner),
                    'vehicleSemanticId': vehicle_key(names_by_resource[owner]) if owner in names_by_resource else None,
                    'mountId': f"slot_{use['slot']}", 'catalogVehicle': owner in names_by_resource})
        weapons[resource] = {'semanticId': semantic_id, 'displayName': label, 'displayNameSource': label_source,
            'nativePathKnown': bool(item['path']), 'attackFamily': item['attackFamilies'][0],
            'turret': item['turret'], 'components': item['components'],
            'packageGroup': 'package:' + digest(item['loadoutPackage']) if item['loadoutPackage'] else None,
            'referencedBy': references, 'referenceCount': len(references),
            'referencedByCatalogVehicle': any(ref['catalogVehicle'] for ref in references),
            'provenance': 'MountComponent.Infos[].Path reference to an entity owning WeaponData and one attack component',
            'resource': resource, 'entityRow': item['entityRow']}
    ids = [weapon['semanticId'] for weapon in weapons.values()]
    if len(ids) != len(set(ids)):
        raise ValueError('mounted weapon semantic identities collide')

    vehicle_builder = Builder('vehicle', research)
    public_vehicles, runtime_vehicles = [], {}
    for vehicle in vehicles_source:
        name = vehicle['name']; health = vehicle['health']; ownership = health['ownership']
        owners = owner_names(ownership, names_by_resource)
        entity_target = {'resource': 'vehicle', 'vehicle': name, 'path': 'entity'}
        main = [vehicle_builder.add(name, entity_target, 'entity.health', health['mainHealth'],
                component_backing(ownership, vehicle['resource'], 0, 'i32', owners)),
            vehicle_builder.add(name, entity_target, 'entity.armor', health['defaultArmor'],
                component_backing(ownership, vehicle['resource'], 64 + 216, 'u32', owners))]
        zones = []
        by_hash = {zone['nameHash']: zone for zone in health['zones'] if zone['populated']}
        for zone in health['zones']:
            if not zone['populated']:
                continue
            target = {'resource': 'vehicle', 'vehicle': name, 'path': 'damage_zone', 'zone': zone_id(zone['index'])}
            base = ZONE_BASE + zone['index'] * ZONE_STRIDE
            keys = []
            for field_id, key, offset, storage in (('zone.armor', 'armor', 216, 'u32'),
                    ('zone.health', 'health', 232, 'i32'),
                    ('zone.affects_main_health', 'affectsMainHealth', 248, 'f32')):
                keys.append(vehicle_builder.add(name, target, field_id, zone[key],
                    component_backing(ownership, vehicle['resource'], base + offset, storage, owners))['instanceKey'])
            zones.append({'zoneId': zone_id(zone['index']), 'index': zone['index'],
                'semanticId': 'vehicle-zone/v1/' + slug(name) + '/' + zone_id(zone['index']) + '/'
                    + digest({'vehicle': name, 'zone': zone['index'], 'name': zone['nameHash']}),
                'name': zone['name'], 'nameResolved': zone['name'] is not None,
                'values': {'armor': zone['armor'], 'health': zone['health'],
                    'constitution': zone['constitution'], 'affectsMainHealth': zone['affectsMainHealth']},
                'childZones': [zone_id(by_hash[child]['index']) for child in zone['childZoneHashes'] if child in by_hash],
                'unresolvedChildLinks': sum(child not in by_hash for child in zone['childZoneHashes']),
                'actorCount': zone['actorCount'], 'fieldInstanceKeys': keys})
        mounts = []; runtime_mounts = {}
        mount = vehicle['mount']; mount_owners = owner_names(mount, names_by_resource)
        for slot in mount['slots']:
            current = mounted.get(slot['path'])
            mount_id = f"slot_{slot['slot']}"
            role = slot['name'] or slot['attachNodeName']
            entry = {'mountId': mount_id, 'slotIndex': slot['slot'], 'role': role,
                'roleSource': 'native_name' if slot['name'] else 'attach_node' if slot['attachNodeName'] else None,
                'attachNode': slot['attachNodeName'], 'mountSide': slot['mountSide'],
                'semanticId': 'mount-slot/v1/' + slug(name) + '/' + mount_id + '/'
                    + digest({'vehicle': name, 'slot': slot['slot'], 'name': slot['nameHash']})}
            if current and current['weapon']:
                weapon = weapons[slot['path']]
                allowed = sorted(item['semanticId'] for key, item in weapons.items()
                    if key != slot['path'] and item['attackFamily'] == weapon['attackFamily'])
                entry.update(currentKind='weapon', current={'semanticId': weapon['semanticId'],
                    'displayName': weapon['displayName'], 'attackFamily': weapon['attackFamily']},
                    swappable=bool(allowed), allowedReplacements=allowed,
                    compatibilityRule='same native attack-component family as the vanilla occupant')
                target = {'resource': 'vehicle', 'vehicle': name, 'path': 'mount', 'mount': mount_id}
                descriptor = vehicle_builder.add(name, target, 'mount.weapon', weapon['semanticId'],
                    component_backing(mount, vehicle['resource'], slot['slot'] * 24, 'u64', mount_owners),
                    editable=bool(allowed),
                    reason=None if allowed else 'No discovered compatible replacement identity.',
                    extra={'allowedValues': allowed, 'acknowledgement': 'allow_unverified_reference',
                        'valueKind': 'mounted_weapon_semantic_id',
                        'residencyWarning': ('Package residency: when the replacement comes from another '
                            'package that the catalog knows, Runtime loads it before writing (ASSET_UNAVAILABLE '
                            'otherwise); vehicle-mount loading is proven offline, not yet live-tested. Mount '
                            'compatibility is separate and unverified: FRVWeaponSwap verified the write live, '
                            'but in-game firing and rendering of a swapped mount are unconfirmed.')})
                entry['instanceKey'] = descriptor['instanceKey']
                runtime_mounts[mount_id] = {'slot': slot['slot'], 'current': weapon['semanticId'], 'role': role}
            else:
                entry.update(currentKind='non_weapon' if current else 'unresolved', current=None,
                    swappable=False, allowedReplacements=[],
                    blockedReason=('The mounted entity has no single weapon attack component; non-weapon '
                        'mount references are not swappable.'))
            mounts.append(entry)
        wiki = vehicle['wiki'] or {}
        root = vehicle['stratagemRoot']
        public_vehicles.append({'name': name, 'semanticId': vehicle_key(name),
            'catalogSource': vehicle['catalogSource'], 'vehicleClass': wiki.get('vehicleClass'),
            'callInStratagem': {'semanticId': support_callin_linkage.stratagem_key(name), 'name': name,
                'relationship': 'call_in', 'known': True, 'provenance': root['identityBasis']}
                if root else {'known': False, 'reason': 'Native vehicle entity without a player stratagem definition.'},
            'correlation': vehicle['correlation'],
            'durability': {'mainHealth': health['mainHealth'], 'mainArmor': health['defaultArmor'],
                'fieldInstanceKeys': [item['instanceKey'] for item in main],
                'populatedZones': len(zones), 'unpopulatedZoneSlots': 38 - len(zones), 'zones': zones},
            'mounts': mounts,
            'blockedFields': [
                {'field': 'zone.constitution / death flags', 'reason': 'Typed members without reviewed gameplay semantics.'},
                {'field': 'zone explosive damage percentage', 'reason': 'The ShieldRelayImprovements gameplay test showed no effect.'},
                {'field': 'unpopulated zone slots', 'reason': 'Zone slots without a native zone name are unused by this entity.'},
                {'field': 'motion / collision / seats', 'reason': 'Vehicle motion, collision damage, and seat components are not promoted.'}],
            'fieldInstanceKeys': [descriptor['instanceKey'] for descriptor in vehicle_builder.public()
                if descriptor['target']['vehicle'] == name]})
        runtime_vehicles[name] = {'name': name, 'semanticId': vehicle_key(name), 'resource': vehicle['resource'],
            'entityRow': vehicle['entityRow'], 'mounts': runtime_mounts,
            'zones': {zone['zoneId']: {'index': zone['index'], 'name': zone['name']} for zone in zones},
            'fields': vehicle_builder.runtime(name)}

    backpack_builder = Builder('backpack', research)
    public_backpacks, runtime_backpacks = [], {}
    for backpack in research['backpacks']:
        name = backpack['name']; components = backpack['components']
        target = {'resource': 'backpack', 'backpack': name, 'path': 'backpack'}
        blocked = []
        groups = []

        def owners_of(component):
            return owner_names(component, names_by_resource)

        recharge = components.get('RechargeComponentData')
        if recharge:
            descriptor = backpack_builder.add(name, target, 'recharge.time', recharge['values']['0'],
                component_backing(recharge, backpack['resource'], 0, 'f32', owners_of(recharge)))
            groups.append({'group': 'recharge', 'fieldInstanceKeys': [descriptor['instanceKey']]})
        jump = components.get('JumppackComponentData')
        if jump:
            proven = name in GAMEPLAY_ENTITY['jump.vertical_launch_velocity']
            descriptor = backpack_builder.add(name, target, 'jump.vertical_launch_velocity', jump['values']['0'],
                component_backing(jump, backpack['resource'], 0, 'f32', owners_of(jump)), editable=proven,
                reason=None if proven else ('The member is proven on the Jump Pack only; the Hover Pack consumer '
                    'uses distinct hover members and its launch semantics are unproven.'))
            groups.append({'group': 'movement', 'fieldInstanceKeys': [descriptor['instanceKey']]})
            blocked += [{'field': 'unlabelled launch members', 'reason': 'Two further Jumppack launch scalars were tested only as experiment profiles that were never gameplay-reported.'},
                {'field': 'horizontal impulse', 'reason': 'No horizontal or forward impulse member has been identified.'}]
        shield = components.get('ShieldComponentData')
        if shield:
            keys = [backpack_builder.add(name, target, field_id, shield['values'][str(offset)],
                component_backing(shield, backpack['resource'], offset, 'f32', owners_of(shield)))['instanceKey']
                for field_id, offset in (('shield.radius', 0), ('shield.durability', 76))]
            groups.append({'group': 'shield', 'fieldInstanceKeys': keys})
            blocked.append({'field': 'shield recharge delay/rate', 'reason':
                'Labels come from an external export only; no reference mod wrote them.'})
        health = components.get('HealthComponentData')
        zones = {}
        if health:
            correlated = backpack['correlation'].get('mainHealth') and backpack['correlation'].get('mainArmor')
            keys = []
            for field_id, offset, storage in (('entity.health', 0, 'i32'), ('entity.armor', 280, 'u32')):
                extra = dict(SHIELD_BODY_FIELDS.get((name, field_id)) or {})
                dormant = extra.pop('readOnly', None)
                keys.append(backpack_builder.add(name, target, field_id, health['values'][str(offset)],
                    component_backing(health, backpack['resource'], offset, storage, owners_of(health)),
                    editable=bool(correlated) and not dormant,
                    reason=dormant or (None if correlated else 'Wiki identity correlation absent.'),
                    extra=extra or None)['instanceKey'])
            groups.append({'group': 'durability', 'fieldInstanceKeys': keys})
            plate = shield_plate(name, backpack, health)
            if plate:
                zone_target = {'resource': 'backpack', 'backpack': name, 'path': 'damage_zone', 'zone': plate['zoneId']}
                backing = component_backing(health, backpack['resource'], plate['armorOffset'], 'u32', owners_of(health))
                backing['guards'] = plate['guards']
                descriptor = backpack_builder.add(name, zone_target, 'zone.armor', plate['armor'], backing,
                    extra=plate['extra'])
                zones[plate['zoneId']] = {'index': plate['index'], 'name': plate['name']}
                groups.append({'group': 'shield_plate', 'fieldInstanceKeys': [descriptor['instanceKey']]})
        deposit = components.get('DepositComponentData')
        if deposit:
            keys = [backpack_builder.add(name, target, field_id, deposit['values'][str(offset)],
                component_backing(deposit, backpack['resource'], offset, storage, owners_of(deposit)),
                editable=False)['instanceKey']
                for field_id, offset, storage in (('deposit.capacity', 0, 'u32'),
                    ('deposit.start_amount', 4, 'i32'), ('deposit.refill_amount', 8, 'u32'))]
            groups.append({'group': 'charges', 'fieldInstanceKeys': keys, 'readOnly': True})
        if not groups:
            blocked.append({'field': 'backpack behavior', 'reason':
                'No typed backpack behavior component with reviewed semantics is owned by this entity.'})
        public_backpacks.append({'name': name, 'semanticId': backpack_key(name),
            **({'damageZones': [{'zoneId': zone, 'index': info['index'], 'name': info['name']}
                for zone, info in sorted(zones.items())]} if zones else {}),
            'callInStratagem': {'semanticId': support_callin_linkage.stratagem_key(name), 'name': name,
                'relationship': 'call_in', 'known': True, 'provenance': 'historical debug-name identity'},
            'deliveryChain': ['stratagem_definition', 'hellpod_rack', 'backpack_entity'],
            'correlation': backpack['correlation'],
            'components': sorted(key.removesuffix('ComponentData') for key in components),
            'settingGroups': groups, 'blockedFields': blocked,
            'fieldInstanceKeys': [descriptor['instanceKey'] for descriptor in backpack_builder.public()
                if descriptor['target']['backpack'] == name]})
        rack = backpack['rack']
        runtime_backpacks[name] = {'name': name, 'semanticId': backpack_key(name), 'resource': backpack['resource'],
            'entityRow': backpack['entityRow'],
            'rack': {'resource': backpack['stratagemRoot']['payloads'][0], 'recordIndex': rack['recordIndex'],
                'indexRow': rack['indexRow']},
            **({'zones': zones} if zones else {}),
            'fields': backpack_builder.runtime(name)}

    # Weapon-fed backpacks: the call-in rack delivers the support weapon with this backpack, and the weapon's
    # WeaponLinkedAmmoComponent draws from the backpack slot through a tag only this backpack carries. The
    # backpack DepositComponent is the ammunition store (research/backpack-ammo-F5FEE03DCFDB.json).
    ammo_research = json.loads(BACKPACK_AMMO.read_text())
    for item in sorted(ammo_research['backpackFedWeapons'], key=lambda entry: entry['supportWeapon']):
        weapon = item['supportWeapon']; name = backpack_ammo_name(weapon); deposit = item['deposit']
        if not item['fingerprintExact'] or not deposit['uniqueOwner'] or item['weaponOwnsMagazine']:
            raise ValueError(name + ': backpack ammo ownership is not proven')
        target = {'resource': 'backpack', 'backpack': name, 'path': 'backpack'}
        keys = []
        for field_id, offset, storage in (('deposit.capacity', 0, 'u32'), ('deposit.start_amount', 4, 'i32'),
                ('deposit.refill_amount', 8, 'u32')):
            low, high = AMMO_RANGE[field_id]
            keys.append(backpack_builder.add(name, target, field_id, deposit['values'][str(offset)],
                component_backing(deposit, item['backpackResource'], offset, storage, [name]),
                extra={'displayName': AMMO_LABELS[field_id], 'unit': 'ammo', 'uiGroup': 'backpack_ammo',
                    'min': low, 'max': high, 'rangeReason': AMMO_RANGE_REASON,
                    'acknowledgement': 'allow_unverified_effect',
                    'acknowledgementReason': AMMO_UNVERIFIED,
                    'provenance': 'call-in rack -> weapon linked ammo tag -> backpack TagComponent -> '
                        'backpack DepositComponent; exact wiki capacity and supply fingerprints'})['instanceKey'])
        fingerprint = item['fingerprint']
        public_backpacks.append({'name': name, 'semanticId': backpack_key(name),
            'callInStratagem': {'semanticId': support_callin_linkage.stratagem_key(weapon), 'name': weapon,
                'relationship': 'delivered_with_support_weapon', 'known': True,
                'provenance': 'call-in primary payload is the rack that attaches the weapon and this backpack'},
            'deliveryChain': ['stratagem_definition', 'hellpod_rack', 'backpack_entity'],
            'feeds': {'supportWeapon': weapon, 'supportWeaponSemanticId': support_callin_linkage.support_weapon_key(weapon),
                'relationship': 'backpack_ammo', 'ammoMode': item['linkedAmmo']['ammoMode'],
                'inventorySlot': item['linkedAmmo']['inventorySlot'], 'refillStyle': deposit['refillStyle'],
                'weaponOwnsMagazine': False,
                'chain': ['call-in rack attaches the weapon and this backpack',
                    'weapon WeaponLinkedAmmoComponent: inventory slot Backpack, tag',
                    'only this backpack carries the tag (TagComponent)',
                    'backpack DepositComponent holds the ammunition']},
            'ammo': {'capacity': deposit['values']['0'], 'startAmount': deposit['values']['4'],
                'refillAmount': deposit['values']['8'],
                'fromAmmoBox': {'value': fingerprint['fromAmmoBox']['wiki'], 'writable': False,
                    'reason': 'Half of the supply refill, applied by game code; not a stored member.'},
                'fingerprint': {'capacity': fingerprint['capacity'], 'fromSupply': fingerprint['fromSupply']}},
            'correlation': {'capacity': True, 'fromSupply': True},
            'components': ['Backpack', 'Deposit', 'Tag'],
            'settingGroups': [{'group': 'backpack_ammo', 'fieldInstanceKeys': keys}],
            'blockedFields': [{'field': 'remaining ammunition', 'reason': 'The live remaining count is per-mission '
                'instance state, not a definition field; capacity, starting ammo and supply refill are authored.'}],
            'fieldInstanceKeys': keys})
        rack = item['rack']; linked = item['linkedAmmoIdentity']; tag = item['backpackTag']
        runtime_backpacks[name] = {'name': name, 'semanticId': backpack_key(name), 'resource': item['backpackResource'],
            'entityRow': item['backpackEntityRow'],
            'rack': {'resource': rack['resource'], 'recordIndex': rack['recordIndex'], 'indexRow': rack['indexRow'],
                'slots': {str(rack['weaponSlot']): item['weaponResource'], str(rack['backpackSlot']): item['backpackResource']}},
            'feeds': {'weapon': weapon, 'weaponResource': item['weaponResource'], 'weaponEntityRow': item['weaponEntityRow'],
                'linkedAmmo': {'recordIndex': linked['recordIndex'], 'indexRow': linked['indexRow']},
                'tag': {'recordIndex': tag['recordIndex'], 'indexRow': tag['indexRow'], 'value': tag['value']},
                'ammoMode': item['linkedAmmo']['ammoMode'], 'inventorySlot': ammo_research['typeLibrary']['inventorySlotBackpack']},
            'fields': backpack_builder.runtime(name)}

    runtime_weapons = {item['semanticId']: {'semanticId': item['semanticId'], 'displayName': item['displayName'],
        'resource': item['resource'], 'entityRow': item['entityRow'], 'attackFamily': item['attackFamily']}
        for item in weapons.values()}
    public_weapons = [{key: value for key, value in item.items() if key not in ('resource', 'entityRow')}
        for item in sorted(weapons.values(), key=lambda item: item['semanticId'])]

    def objects(builder):
        backing_objects, operations = {}, {}
        for descriptor in builder.public():
            item = backing_objects.setdefault(descriptor['backingObjectId'], {
                'backingObjectId': descriptor['backingObjectId'], 'kind': descriptor['backingObjectKind'],
                'shared': descriptor['shared'], 'sharedConsumers': descriptor['sharedConsumers'],
                'sharedScopeKey': descriptor['sharedScopeKey'], 'fieldInstances': []})
            if item['sharedScopeKey'] != descriptor['sharedScopeKey']:
                raise ValueError('inconsistent reviewed scope for ' + descriptor['backingObjectId'])
            item['fieldInstances'].append(descriptor['instanceKey'])
            group = operations.setdefault(descriptor['operationGroup'], {
                'operationGroup': descriptor['operationGroup'], 'backingObjectId': descriptor['backingObjectId'],
                'target': descriptor['target'], 'fieldInstances': [], 'recommendedApi': 'hd2.patch',
                'allowSharedRequired': descriptor['allowSharedRequired']})
            if group['backingObjectId'] != descriptor['backingObjectId'] or group['target'] != descriptor['target']:
                raise ValueError('operation group conflates backing objects or targets')
            group['fieldInstances'].append(descriptor['instanceKey'])
        for group in operations.values():
            if len(group['fieldInstances']) > 1:
                group['recommendedApi'] = 'hd2.transaction'
        return list(backing_objects.values()), list(operations.values())

    def audit(builder, runtime_entries):
        published = [descriptor['instanceKey'] for descriptor in builder.public()]
        internal = [field['instanceKey'] for entry in runtime_entries.values() for field in entry['fields']]
        if len(published) != len(set(published)) or set(published) != set(internal):
            raise ValueError(builder.family + ' canonical instance publication is incomplete')
        return {'internalInstances': len(internal), 'publishedInstances': len(published),
            'missingInstances': 0, 'unexpectedInstances': 0, 'exactMatch': True}

    def tiers(builder):
        counts = Counter(descriptor['evidence']['tier'] for descriptor in builder.public() if descriptor['editable'])
        return {tier: counts[tier] for tier in TIER_ORDER if counts[tier]}

    version = (ROOT / 'VERSION').read_text().strip()
    safety = {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0,
        'protectionChangesDuringGeneration': 0, 'fixtureFallback': 'disabled'}
    vehicle_objects, vehicle_operations = objects(vehicle_builder)
    vehicle_fields = vehicle_builder.public()
    swappable = [mount for vehicle in public_vehicles for mount in vehicle['mounts'] if mount['swappable']]
    vehicle_summary = {'vehicles': len(public_vehicles),
        'stratagemVehicles': sum(item['catalogSource'] == 'wiki_stratagem' for item in public_vehicles),
        'nativeOnlyVehicles': sum(item['catalogSource'] == 'native_only' for item in public_vehicles),
        'fieldInstances': len(vehicle_fields), 'writableFieldInstances': sum(item['editable'] for item in vehicle_fields),
        'populatedZones': sum(item['durability']['populatedZones'] for item in public_vehicles),
        'zoneFieldInstances': sum(item['target']['path'] == 'damage_zone' for item in vehicle_fields),
        'mountSlots': sum(len(item['mounts']) for item in public_vehicles),
        'swappableMountSlots': len(swappable),
        'nonWeaponMountSlots': sum(mount['currentKind'] != 'weapon' for item in public_vehicles for mount in item['mounts']),
        'discoveredMountedWeapons': len(public_weapons),
        'mountedWeaponsByFamily': dict(sorted(Counter(item['attackFamily'] for item in public_weapons).items())),
        'mountRecordsSurveyed': len(research['mountRecords']),
        'writableByTier': tiers(vehicle_builder),
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    vehicle_doc = {'contract': 'hd2runtime.vehicle.guarded_authoring.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': version, 'canonicalCollection': 'fieldInstances',
        'vehicles': public_vehicles, 'mountedWeapons': public_weapons, 'fieldInstances': vehicle_fields,
        'backingObjects': vehicle_objects, 'operationGroups': vehicle_operations,
        'referenceContract': {'field': 'mount.weapon', 'valueKind': 'mounted_weapon_semantic_id',
            'acknowledgement': 'allow_unverified_reference',
            'compatibility': 'same native attack-component family as the vanilla occupant',
            'identitySource': 'mountedWeapons[] discovered from MountComponent Path references',
            'arbitraryIdentifiersAccepted': False, 'rawNativeIdentifiersPublished': False,
            'runtimeChecks': ['vehicle mount record ownership', 'replacement entity is live and owns WeaponData',
                'current slot reference equals the expected identity']},
        'evidenceTiers': {'gameplay_proven': 'Reference mod confirmed this field on this entity in gameplay.',
            'gameplay_proven_combined': 'Written as part of a gameplay-confirmed edit; its individual effect is not isolated.',
            'schema_proven': 'Same typed native member was gameplay-proven on another entity of this record type.',
            'live_write_verified': 'Reference mod committed this write live; gameplay effect is unconfirmed.',
            'structural_reference': ('Same typed mount reference mechanism as the live-verified swap; '
                'this slot and replacement have no reference-mod write.')},
        'summary': vehicle_summary, 'instanceAudit': audit(vehicle_builder, runtime_vehicles), 'safety': safety}

    backpack_objects, backpack_operations = objects(backpack_builder)
    backpack_fields = backpack_builder.public()
    backpack_summary = {'backpacks': len(public_backpacks), 'fieldInstances': len(backpack_fields),
        'writableFieldInstances': sum(item['editable'] for item in backpack_fields),
        'readOnlyFieldInstances': sum(not item['editable'] for item in backpack_fields),
        'backpacksWithWritableFields': sum(any(field['editable'] for field in backpack_fields
            if field['target']['backpack'] == item['name']) for item in public_backpacks),
        'writableByTier': tiers(backpack_builder),
        'rackChainsResolved': len(public_backpacks),
        'weaponFedBackpacks': sum(1 for item in public_backpacks if item.get('feeds')),
        'backpackAmmoWritable': sum(item['editable'] for item in backpack_fields if item.get('uiGroup') == 'backpack_ammo'),
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    backpack_doc = {'contract': 'hd2runtime.backpack.guarded_authoring.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': version, 'canonicalCollection': 'fieldInstances',
        'backpacks': public_backpacks, 'fieldInstances': backpack_fields,
        'backingObjects': backpack_objects, 'operationGroups': backpack_operations,
        'evidenceTiers': vehicle_doc['evidenceTiers'], 'summary': backpack_summary,
        'instanceAudit': audit(backpack_builder, runtime_backpacks), 'safety': safety}

    for document in (vehicle_doc, backpack_doc):
        text = json.dumps(document).lower()
        if '0x' in text:
            raise ValueError('public entity capability leaks a native identifier')
        for resource in list(mounted) + [item['resource'] for item in vehicles_source] + \
                [item['resource'] for item in research['backpacks']] + \
                [x for item in ammo_research['backpackFedWeapons'] for x in (item['backpackResource'], item['weaponResource'])]:
            if resource[2:].lower() in text:
                raise ValueError('public entity capability leaks a native resource hash')

    runtime = {'version': version, 'vehicles': runtime_vehicles, 'backpacks': runtime_backpacks,
        'mountedWeapons': runtime_weapons,
        'summary': {'vehicles': vehicle_summary, 'backpacks': backpack_summary}}
    return runtime, vehicle_doc, backpack_doc


def outputs(research_path=RESEARCH):
    runtime, vehicles, backpacks = build(research_path)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_entity_authoring.py; do not edit.\nreturn ' + lua(migration_overlay.apply('entity_authoring', runtime)) + '\n',
        VEHICLE_OUTPUT: json.dumps(vehicles, indent=2) + '\n',
        BACKPACK_OUTPUT: json.dumps(backpacks, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale entity authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
