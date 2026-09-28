"""Generate guarded magazine-attachment authoring metadata from retained native evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_entity_authoring

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/attachment_fields.json'
JSON_OUTPUT = ROOT / 'sdk/MagazineAttachmentCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/attachment_authoring.lua'
FIELD_KEYS = {'attachment.magazine_capacity': 'capacity', 'attachment.starting_magazines': 'startingMagazines',
    'attachment.magazines_from_supply': 'magazinesFromSupply', 'attachment.spare_magazines': 'spareMagazines'}
EFFECT_COMPONENTS = {'113': 'reload', '236': 'handling', '271': 'visual'}


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def attachment_key(item):
    return 'weapon-attachment/v1/magazine/' + slug(item['debugName']) + '/' + digest({'addPath': item['addPath']})


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    definitions = {item['id']: item for item in json.loads(FIELDS.read_text())['fields']}
    constants = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    attachments = {item['addPath']: dict(item, semanticId=attachment_key(item))
        for item in research['magazineAttachments']}
    names = Counter(item['debugName'] for item in attachments.values())
    consumers = {path: {'nativeDefaultOf': [], 'catalogCorrelated': [], 'candidateFor': []} for path in attachments}
    consistency = {path: [] for path in attachments}
    weapons = []
    for weapon in research['weapons']:
        if not weapon['catalogOptions'] and not weapon['nativeDefault']:
            continue
        if weapon['nativeDefault']:
            consumers[weapon['nativeDefault']]['nativeDefaultOf'].append(weapon['weapon'])
            consistency[weapon['nativeDefault']].append(weapon.get('defaultConsistency'))
        options = []
        for option in weapon['catalogOptions']:
            if option['relationship'] == 'catalog_effect_fingerprint_unique':
                consumers[option['attachment']]['catalogCorrelated'].append(weapon['weapon'])
            elif option['relationship'] == 'catalog_effect_fingerprint_ambiguous':
                for candidate in option['candidates']:
                    consumers[candidate]['candidateFor'].append(weapon['weapon'])
            options.append({'name': option['name'], 'default': option['default'],
                'relationship': option['relationship'],
                'attachment': attachments[option['attachment']]['semanticId'] if option['attachment'] else None,
                'candidates': [attachments[path]['semanticId'] for path in option['candidates']],
                'publishedEffects': option['effects'],
                'blocker': None if option['attachment'] else (
                    'Several native magazine attachments share these published effects; the owner is not guessed.'
                    if option['candidates'] else 'No native magazine attachment has these published effects.')})
        weapons.append({'weapon': weapon['weapon'],
            'magazineSlot': {'slot': 'magazine',
                'defaultAttachment': attachments[weapon['nativeDefault']]['semanticId'] if weapon['nativeDefault'] else None,
                'defaultRelationship': weapon['defaultRelationship'],
                'defaultConsistency': weapon.get('defaultConsistency'),
                'baseRecordCapacityIsPlaceholder': weapon.get('defaultConsistency') == 'delta_matches_published_base_differs',
                'options': options}})

    fields, runtime_attachments, public_attachments = [], {}, []
    for path, item in sorted(attachments.items(), key=lambda pair: pair[1]['semanticId']):
        states = consistency[path]
        tier = ('native_owner_effect_consistent' if 'delta_matches_published_base_differs' in states
            else 'native_owner_value_consistent' if 'delta_base_and_published_agree' in states
            else 'native_owner')
        scope = consumers[path]
        known = sorted(set(scope['nativeDefaultOf'] + scope['catalogCorrelated']))
        object_key = 'backing:' + digest({'entityDelta': path})
        operation = 'operation:' + digest({'object': object_key, 'target': item['semanticId']})
        target = {'resource': 'weapon_attachment', 'attachment': item['semanticId'], 'path': 'magazine'}
        keys, runtime_fields = [], {}
        for field_id, key in FIELD_KEYS.items():
            if key not in item['fields']:
                continue
            definition = definitions[field_id]
            native = item['fields'][key]
            instance = item['semanticId'].replace('weapon-attachment/v1/', 'attachment:') + ':' + field_id
            fields.append({'instanceKey': instance, 'semanticFieldId': field_id,
                'displayName': definition['display_name'], 'type': definition['type'], 'unit': definition['unit'],
                'currentDefault': native['value'], 'editable': True, 'reason': None, 'target': target,
                'backingObjectId': object_key, 'backingObjectKind': 'EntityDelta:WeaponMagazineComponentData',
                'operationGroup': operation, 'planGroup': 'plan:attachment:' + slug(item['debugName']),
                'requires': 'patch_or_transaction', 'allowSharedRequired': True, 'shared': True,
                'sharedConsumers': [{'weapon': name} for name in known],
                'sharedScopeKey': 'shared-scope:' + digest({'object': object_key, 'consumers': known}),
                'reviewedScopeComplete': False, 'dynamicConsumersPossible': True,
                'acknowledgement': 'allow_unverified_effect',
                'apiFieldConstant': constants[field_id], 'domain': 'attachment', 'planPhase': 1, 'dependsOn': [],
                'evidence': {'tier': tier, 'nativeOwner': 'entity delta keyed by the attachment AddPath, '
                    'patching WeaponMagazineComponentData', 'gameplayWriteEffect': 'unproven'},
                'provenance': 'pinned entity delta table; live read-only allocation byte-identical to the file'})
            keys.append(instance)
            runtime_fields[field_id] = {'instanceKey': instance, 'componentOffset': native['componentOffset'],
                'dataOffset': native['dataOffset'], 'currentDefault': native['value'], 'operationGroup': operation,
                'backing': {'kind': 'entity_delta', 'component': 'WeaponMagazineComponentData'}}
        effects = sorted({EFFECT_COMPONENTS.get(component, 'other') for component in item['otherPatchedComponents']})
        public_attachments.append({'semanticId': item['semanticId'], 'name': item['debugName'],
            'nameUnique': names[item['debugName']] == 1, 'slot': 'magazine',
            'values': {key: value['value'] for key, value in item['fields'].items()},
            'otherPatchedEffects': effects, 'fieldInstanceKeys': keys,
            'consumers': dict(scope, scopeComplete=False,
                scopeNote='Every weapon that equips this attachment receives its patch; the native '
                    'weapon-to-attachment compatibility table is not resolved.'),
            'evidence': {'tier': tier, 'defaultConsistency': states}})
        runtime_attachments[item['semanticId']] = {'semanticId': item['semanticId'], 'name': item['debugName'],
            'resource': item['addPath'], 'hashmapSlot': item['hashmapSlot'],
            'settingsIndex': item['settingsIndex'], 'fields': runtime_fields}
    tiers = Counter(field['evidence']['tier'] for field in fields)
    summary = {'magazineAttachments': len(public_attachments), 'fieldInstances': len(fields),
        'writableFieldInstances': len(fields), 'weapons': len(weapons),
        'weaponsWithNativeDefault': sum(1 for item in weapons if item['magazineSlot']['defaultAttachment']),
        'placeholderBaseCapacityWeapons': sum(1 for item in weapons if item['magazineSlot']['baseRecordCapacityIsPlaceholder']),
        'optionRelationships': dict(sorted(Counter(option['relationship'] for item in weapons
            for option in item['magazineSlot']['options']).items())),
        'writableByTier': dict(sorted(tiers.items())), 'selectionWritable': False,
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    public = {'contract': 'hd2runtime.weapon_attachment.magazine.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'canonicalCollection': 'fieldInstances',
        'ownershipModel': {'chain': ['weapon default customization (slot magazine)', 'weapon customizable item',
                'entity delta keyed by the item AddPath', 'WeaponMagazineComponentData patch'],
            'writeScope': 'attachment definition; applies to every weapon that equips the attachment',
            'distinctFrom': ['weapon.capacity base record value', 'rounds currently loaded',
                'current or saved preset selection', 'visual magazine unit'],
            'weaponCapacityField': 'Weapons whose base record capacity is a placeholder keep weapon.capacity read-only.'},
        'acknowledgements': {'allow_shared': 'Required: consumer scope is not natively complete.',
            'allow_unverified_effect': 'Required: the live delta bytes and effective value are proven, but whether '
                'an edited delta is re-applied when a weapon is next constructed is not gameplay-proven.'},
        'supersedes': {'file': 'AttachmentOptionCapabilities.json',
            'fields': ['defaultOption.ammoValueOwnerProven', 'categories[].options[].nativeEffectOwner'],
            'note': 'Magazine ammo values are owned by these attachment definitions; the older file predates this proof.'},
        'selection': {'writable': False, 'reason': 'The player preset/selection owner is unresolved; the weapon '
            'resource default is not the player selection (R-72 Censor controlled diff).'},
        'attachments': public_attachments, 'weapons': weapons, 'fieldInstances': fields, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0,
            'protectionChangesDuringGeneration': 0, 'fixtureFallback': 'disabled'}}
    text = json.dumps(public).lower()
    if '0x' in text or any(path[2:].lower() in text for path in attachments):
        raise ValueError('public attachment capability leaks a native identifier')
    runtime = {'version': public['hd2RuntimeVersion'], 'attachments': runtime_attachments,
        'names': {item['name']: item['semanticId'] for item in public_attachments if item['nameUnique']},
        'weapons': {item['weapon']: {'default': item['magazineSlot']['defaultAttachment'],
            'options': [{'name': option['name'], 'attachment': option['attachment'],
                'relationship': option['relationship']} for option in item['magazineSlot']['options']]}
            for item in weapons},
        'summary': summary}
    return runtime, public


def lua(value):
    return generate_entity_authoring.lua(value)


def outputs(research_path=RESEARCH):
    runtime, public = build(research_path)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_attachment_authoring.py; do not edit.\nreturn ' + lua(runtime) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body)
    if check and stale:
        raise RuntimeError('Stale attachment authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
