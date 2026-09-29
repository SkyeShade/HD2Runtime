"""Generate guarded drop-pod payload authoring (hellpod rack slots and replacement pickups)."""
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
import support_callin_linkage
import package_residency_evidence as residency_evidence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
BOOSTER_NATIVE = ROOT / 'research/booster-native-F5FEE03DCFDB.json'
BOOSTERS = ROOT / 'sdk/BoosterAuthoringCapabilities.json'
JSON_OUTPUT = ROOT / 'sdk/PodPayloadCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/pod_payload_authoring.lua'
OFFERED = ('support_weapon', 'backpack', 'ammo', 'stim', 'grenade', 'supply')
CATEGORY_LABELS = {'support_weapon': 'Support Weapons', 'backpack': 'Backpacks', 'ammo': 'Ammo', 'stim': 'Stims',
    'grenade': 'Grenades', 'supply': 'Supplies'}
AUTHORED_SLOTS = 4  # slots 1..4 carry a configured rack side in every weapon rack
NATIVE_LABELS = {'AmmoRack': 'Resupply', 'AmmoRack_PresidentReward': 'Resupply (reward variant)',
    'HealthPackRack': 'Health Pack Rack', 'HealthPackRack_PresidentReward': 'Health Pack Rack (reward variant)',
    'Machinegun_PresidentReward': 'MG-43 Machine Gun (reward variant)',
    'JumppackBackpack_PresidentReward': 'LIFT-850 Jump Pack (reward variant)',
    'MedicBackpack_PresidentReward': 'Medic Backpack (reward variant)', 'HellbombBackpack': 'Portable Hellbomb (mission)',
    'DarkFluidBackpack': 'Dark Fluid Backpack', 'ShoulderMountedCamera': 'Shoulder Mounted Camera',
    'CarryData': 'Carry Data', 'CyborgCarryData': 'Cyborg Carry Data', 'RemoteExplosives': 'Remote Explosives',
    'SpireSterilizer': 'Spire Sterilizer', 'JammedPinata': 'Jammed Pod'}
UNVERIFIED = ('Same native RackAttach reference mechanism as the vanilla payload, but this replacement has not been '
    'spawned from this pod in game.')
COUNT_UNVERIFIED = ('spawn_payload_size is the native count of spawned slots and vanilla racks use 1, 2, 4 and 6, '
    'but changing it has not been tested in game.')


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


def package_key(package):
    return None if package is None else 'package/' + digest({'package': package})


def title(path):
    base = path.rsplit('/', 1)[-1]
    base = re.sub(r'_discoverable_\d+$', '', base)
    return ' '.join(word.capitalize() for word in base.split('_'))


def package_dependency(item, resident, live_tested, family):
    """Package residency only; slot compatibility stays in compatibility/acknowledgements."""
    known = bool(item and item['known'])
    return {'known': known, 'alwaysResident': resident, 'autoLoadSupported': known and not resident,
        'package': ((item['dependency']['name'] or '').rsplit('/', 1)[-1] or None) if known else None,
        'packageResidency': ('ALWAYS_RESIDENT' if resident else family['packageResidency'] if known else
            'UNRESOLVED'),
        'liveTested': live_tested,
        'blocker': None if known or resident else ('No own loadout package is proven for this pickup; Runtime '
            'cannot load it, and its assets are present only when a rack that delivers it is loaded.')}


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    package_catalog = residency_evidence.research()['catalog']
    live_objects = set(residency_evidence.live_objects())
    pod_family = residency_evidence.families()['pod_payload_pickup']
    booster_record = json.loads(BOOSTER_NATIVE.read_text())['grantedStratagemRecord']
    booster_name = next(item['name'] for item in json.loads(BOOSTERS.read_text())['boosters']
        if any(rel['kind'] == 'granted_stratagem' for rel in item['relationships']))

    def consumer_name(row):
        if row['id'] == booster_record['id']:
            return booster_name + ' (granted stratagem)'
        return row['catalogStratagem'] or NATIVE_LABELS.get(row['nativeType'], row['nativeType'])

    # Rack names come from their primary consumer; racks are the semantic owner of their slots.
    rack_names = {}
    for rack in research['racks']:
        rack_names[rack['resource']] = consumer_name(rack['consumers'][0]) + ' pod'
    if len(set(rack_names.values())) != len(rack_names):
        raise ValueError('rack names collide')

    # Pickup catalog: typed categories only.
    candidates = [c for c in research['candidates'] if c['category'] in OFFERED and c['path'] and c['entityRow'] is not None]
    by_name = Counter(c['name'] or title(c['path']) for c in candidates)
    pickups, pickup_by_resource = [], {}
    always_resident, names_used = set(), set()
    for rack in research['racks']:
        if any(row['alwaysAvailable'] for row in rack['consumers']):
            always_resident.update(slot['item'] for slot in rack['slots'] if slot['item'])
    for candidate in sorted(candidates, key=lambda c: (c['category'], c['name'] or title(c['path']), c['path'])):
        base = candidate['name'] or title(candidate['path'])
        name = base if by_name[base] == 1 else base + (' (pod)' if candidate['vanillaRackPaths'] else ' (world)')
        if name in names_used:
            name = base + ' (' + candidate['path'].rsplit('/', 1)[-1] + ')'
        names_used.add(name)
        semantic = 'pickup/v1/' + slug(name) + '/' + digest({'entity': candidate['resource']})
        proven = bool(candidate['vanillaRackPaths'])
        if candidate['category'] == 'backpack':
            component = {'name': 'BackpackComponentData'}
        else:
            component = {'name': 'InteractableComponentData', 'recordIndex': candidate['interactRecord'],
                'interactTypes': candidate['interactTypes']}
        resident = candidate['resource'] in always_resident
        item = {'name': name, 'semanticId': semantic, 'category': candidate['category'],
            'categoryLabel': CATEGORY_LABELS[candidate['category']],
            'compatibility': 'SCHEMA_COMPATIBLE' if proven else 'UNVERIFIED_REFERENCE',
            'compatibilityBasis': ('Vanilla spawns this entity from a hellpod rack slot.' if proven else
                'Standalone typed pickup (interact type) never placed in a vanilla rack slot.'),
            'evidence': {'rackPayloadOf': sorted(rack_names[r] for r in candidate['rackPayloadOf'] if r in rack_names),
                'vanillaRackCount': len(candidate['vanillaRackPaths']),
                'worldLoot': bool(candidate['worldLootTables']), 'standalonePickup': candidate['standalonePickup'],
                'interactTypes': candidate['interactTypes'], 'ownsBackpack': candidate['ownsBackpack'],
                'ownsWeaponData': candidate['ownsWeaponData']},
            'residency': {'packageKey': package_key(candidate['package']), 'alwaysResident': resident,
                'basis': ('Delivered by an always-available mission stratagem (Resupply).' if resident else
                    'Own loadout package; Runtime loads it before writing a slot that references this pickup.'
                    if candidate['package'] else
                    'No own loadout package; its assets load with the racks that deliver it.')},
            'packageDependency': package_dependency(package_catalog.get('pickup/' + semantic), resident,
                'pickup/' + semantic in live_objects, pod_family),
            'packageOwners': [] if candidate['package'] else sorted(
                package_key(r['rackPackage']) for r in research['racks'] if r['resource'] in candidate['rackPayloadOf']
                and r['rackPackage'])}
        pickups.append(item)
        pickup_by_resource[candidate['resource']] = (item, candidate, component)

    racks_public, racks_runtime, by_stratagem, by_stratagem_id = [], {}, {}, {}
    field_count = 0
    for rack in research['racks']:
        name = rack_names[rack['resource']]
        semantic = 'pod-rack/v1/' + slug(name) + '/' + digest({'rack': rack['resource']})
        consumers = [{'name': consumer_name(row), 'nativeType': row['nativeType'],
            'stratagemSemanticId': support_callin_linkage.stratagem_key(row['catalogStratagem'])
                if row['catalogStratagem'] else None,
            'booster': booster_name if row['id'] == booster_record['id'] else None,
            'alwaysAvailable': bool(row['alwaysAvailable'])} for row in rack['consumers']]
        shared = len(consumers) > 1
        active_items = [slot['item'] for slot in rack['slots'] if slot['active'] and slot['item']]
        blocked = None
        if rack['randomPayloadSize']:
            blocked = 'The rack draws a random subset (random_payload_size); slot order does not decide what spawns.'
        elif any(item not in pickup_by_resource for item in active_items):
            typed = {c['resource']: c['category'] for c in research['candidates']}
            if all(typed.get(item) in OFFERED for item in active_items):
                blocked = ('An active slot holds a typed pickup whose entity has no resolvable name, so its current '
                    'item cannot be expressed as a reviewed pickup.')
            else:
                blocked = ('An active slot delivers a deployable or objective entity, not a pickup; its delivery '
                    'semantics differ and it is not authored as a pickup slot.')
        resident = sorted({package_key(p) for p in [rack['rackPackage']] + [row['package'] for row in rack['consumers']]
            + [pickup_by_resource[i][1]['package'] for i in active_items if i in pickup_by_resource] if p})
        acks = ['allow_unverified_reference'] + (['allow_shared'] if shared else [])
        slots_public, slots_runtime = [], {}
        for slot in rack['slots']:
            number = slot['index'] + 1
            current = pickup_by_resource.get(slot['item']) if slot['item'] else None
            authored = blocked is None and slot['index'] < AUTHORED_SLOTS
            view = {'slot': number, 'active': slot['active'],
                'current': None if not slot['item'] else ({'pickup': current[0]['semanticId'], 'name': current[0]['name'],
                    'category': current[0]['category']} if current else {'pickup': None, 'name': None, 'category': None}),
                'applyDeltas': slot['applyDeltas'], 'rackSide': slot['rackSide'], 'writable': authored,
                'reason': None if authored else (blocked or 'Slots 5 to 8 carry no rack side in weapon racks; not authored.'),
                'acknowledgements': acks if authored else []}
            slots_public.append(view)
            if authored:
                field_count += 1
                slots_runtime[str(number)] = {'index': slot['index'], 'current': current[0]['semanticId'] if current
                    else ('empty' if not slot['item'] else None), 'resource': slot['item'] or '0x0000000000000000',
                    'active': slot['active']}
                if slot['item'] and not current:
                    raise ValueError(name + ': authored slot holds an untyped entity')
        count_writable = blocked is None
        if count_writable:
            field_count += 1
        racks_public.append({'name': name, 'semanticId': semantic, 'consumers': consumers, 'shared': shared,
            'writable': blocked is None, 'reason': blocked,
            'spawnCount': {'value': rack['spawnPayloadSize'], 'writable': count_writable, 'range': [1, AUTHORED_SLOTS],
                'acknowledgements': (['allow_unverified_effect'] + (['allow_shared'] if shared else []))
                    if count_writable else [], 'field': 'hd2.fields.payload.spawn_count'},
            'randomPayloadSize': rack['randomPayloadSize'], 'slots': slots_public, 'residentPackages': resident,
            'field': 'hd2.fields.payload.entity'})
        racks_runtime[name] = {'name': name, 'semanticId': semantic, 'resource': rack['resource'],
            'recordIndex': rack['recordIndex'], 'indexRow': rack['indexRow'], 'ownerCount': rack['ownerCount'],
            'shared': shared, 'writable': blocked is None, 'reason': blocked, 'spawnCount': rack['spawnPayloadSize'],
            'consumers': [{'id': row['id'], 'name': consumer_name(row)} for row in rack['consumers']],
            'residentPackages': resident, 'slots': slots_runtime}
        for row in rack['consumers']:
            by_stratagem_id[str(row['id'])] = name
            if row['catalogStratagem']:
                by_stratagem[row['catalogStratagem']] = name
    pickups_runtime = {}
    for item, candidate, component in pickup_by_resource.values():
        pickups_runtime[item['semanticId']] = {'name': item['name'], 'semanticId': item['semanticId'],
            'category': item['category'], 'resource': candidate['resource'], 'entityRow': candidate['entityRow'],
            'component': component, 'compatibility': item['compatibility'],
            'packageKey': item['residency']['packageKey'], 'alwaysResident': item['residency']['alwaysResident'],
            'packageOwners': item['packageOwners']}
    not_offered = Counter(c['category'] or 'untyped' for c in research['candidates'] if c not in candidates)
    summary = {'racks': len(racks_public), 'writableRacks': sum(r['writable'] for r in racks_public),
        'sharedRacks': sum(r['shared'] for r in racks_public), 'writableSlots': sum(
            s['writable'] for r in racks_public for s in r['slots']),
        'writableFieldInstances': field_count, 'pickups': len(pickups),
        'pickupsByCategory': dict(sorted(Counter(p['category'] for p in pickups).items())),
        'pickupsByCompatibility': dict(sorted(Counter(p['compatibility'] for p in pickups).items())),
        'worldLootPickups': sum(p['evidence']['worldLoot'] for p in pickups),
        'alwaysResidentPickups': sum(p['residency']['alwaysResident'] for p in pickups),
        'notOffered': dict(sorted(not_offered.items()))}
    public = {'contract': 'hd2runtime.pod_payload.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'model': ['StratagemDefinition primary payload -> rack entity', 'HellpodRackComponent payloads[8] RackAttach '
            '(64 bytes): item entity reference (+0), attach node, rack side, apply_deltas',
            'spawn_payload_size (+556): the first N slots spawn', 'one rack can serve several stratagems'],
        'categories': CATEGORY_LABELS, 'compatibilityStates': {
            'PROVEN_COMPATIBLE': 'The slot\'s own vanilla occupant (restoring it needs no acknowledgement).',
            'SCHEMA_COMPATIBLE': 'Vanilla spawns this entity from some rack slot; untried in this pod.',
            'UNVERIFIED_REFERENCE': 'Standalone typed pickup never placed in a vanilla rack.',
            'INCOMPATIBLE': 'Not a typed pickup (deployables, objectives, primaries, sidearms); never offered.'},
        'packageRisk': ('Resolved by automatic loading when pickups[].packageDependency.autoLoadSupported is true: '
            'Runtime loads the pickup\'s package before writing the slot and rejects the write with '
            'ASSET_UNAVAILABLE if it cannot. Otherwise low only when the pickup is the vanilla occupant, is always '
            'resident, or its package key is in the rack\'s residentPackages.'),
        'packageResidency': pod_family,
        'residencyVersusCompatibility': ('Package loading resolves missing assets only. Whether a replacement '
            'behaves correctly from a given pod is slot compatibility, which stays unverified '
            '(allow_unverified_reference) except for the live-verified pairs.'),
        'liveVerifiedPairs': residency_evidence.live_pairs(),
        'racks': racks_public, 'pickups': pickups, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0}}
    if re.search(r'0x[0-9a-f]{8,}', json.dumps(public).lower()):
        raise ValueError('public pod payload catalog leaks a native identifier')
    runtime = {'racks': racks_runtime, 'pickups': pickups_runtime,
        'names': {item['name']: item['semanticId'] for item in pickups},
        'byStratagem': by_stratagem, 'byStratagemId': by_stratagem_id, 'boosterGranted': {booster_name: str(booster_record['id'])},
        'authoredSlots': AUTHORED_SLOTS, 'unverifiedReason': UNVERIFIED, 'countReason': COUNT_UNVERIFIED,
        'summary': summary}
    return runtime, public


def outputs():
    runtime, public = build()
    return {LUA_OUTPUT: '-- Generated by scripts/generate_pod_payload_authoring.py; do not edit.\nreturn ' + lua(migration_overlay.apply('pod_payload_authoring', runtime)) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale pod payload outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
