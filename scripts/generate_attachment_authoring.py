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
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import generate_entity_authoring

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/attachment_fields.json'
JSON_OUTPUT = ROOT / 'sdk/MagazineAttachmentCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/attachment_authoring.lua'
GENERIC_RESEARCH = ROOT / 'research/weapon-attachments-F5FEE03DCFDB.json'
GENERIC_OUTPUT = ROOT / 'sdk/WeaponAttachmentCatalog.json'
REFERENCE_BLOCKER = 'Resource reference; replacing it is not reviewed as safe.'
EFFECT_BLOCKERS = {
    'stat modifiers': 'Stat modifier values are decoded; only magazine Add_Ergonomics is exposed for writes so far.',
    'magazine unit': REFERENCE_BLOCKER, 'optics unit': REFERENCE_BLOCKER, 'muzzle unit': REFERENCE_BLOCKER,
    'underbarrel entity': REFERENCE_BLOCKER, 'magazine adjusting nodes': REFERENCE_BLOCKER,
    'material overrides': REFERENCE_BLOCKER,
    'projectile type selector': 'Projectile reference; attachment ammo-type swaps are not reviewed.',
    'feed 1 projectile type selector': 'Projectile reference; attachment ammo-type swaps are not reviewed.',
    'feed 2 projectile type selector': 'Projectile reference; attachment ammo-type swaps are not reviewed.',
}
MAGAZINE_EFFECTS = ('capacity', 'starting magazines', 'magazines from supply', 'spare magazines', 'reload duration')
AMMO_FIELDS = {'attachment.magazine_capacity': 'capacity', 'attachment.starting_magazines': 'startingMagazines',
    'attachment.magazines_from_supply': 'magazinesFromSupply', 'attachment.spare_magazines': 'spareMagazines'}
COMPONENTS = {'WeaponMagazineComponentData': 5, 'WeaponReloadComponentData': 113, 'WeaponDataComponentData': 236}
RELATIONSHIPS = ('native_resource_default', 'catalog_effects_unique', 'catalog_effects_unlock_list')
UNVERIFIED = ('The owner, live delta bytes and effective value are proven; whether an edited delta is re-applied '
    'the next time a weapon is constructed, rather than cached at load, is not gameplay-proven.')
SCOPE_NOTE = ('Every weapon that equips this attachment receives its patch. Known consumers come from native '
    'resource defaults, per-weapon unlock lists observed in memory, and catalog correlation; the native '
    'compatibility set is not proven complete, so allow_shared stays required.')


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def attachment_key(item):
    return 'weapon-attachment/v1/magazine/' + slug(item['debugName']) + '/' + digest({'addPath': item['addPath']})


def native_fields(item):
    """field id -> native location and reviewed value for one attachment delta."""
    result = {}
    for field_id, key in AMMO_FIELDS.items():
        if key in item['fields']:
            native = item['fields'][key]
            result[field_id] = {'value': native['value'], 'component': 'WeaponMagazineComponentData',
                'componentOffset': native['componentOffset'], 'dataOffset': native['dataOffset'], 'storage': 'u32'}
    reload = item['effects']['reload']
    if reload:
        result['attachment.reload_duration'] = {'value': reload['value'], 'component': 'WeaponReloadComponentData',
            'componentOffset': reload['componentOffset'], 'dataOffset': reload['dataOffset'], 'storage': 'f32'}
    ergonomics = [m for m in item['effects']['statModifiers'] or [] if m['typeName'] == 'Add_Ergonomics']
    if len(ergonomics) == 1 and ergonomics[0]['ownRow'] and ergonomics[0]['typeOwnRow']:
        modifier = ergonomics[0]
        result['attachment.ergonomics_modifier'] = {'value': modifier['value'], 'component': 'WeaponDataComponentData',
            'componentOffset': modifier['componentOffset'], 'dataOffset': modifier['dataOffset'], 'storage': 'f32',
            'guard': {'componentOffset': modifier['typeComponentOffset'], 'dataOffset': modifier['typeDataOffset'],
                'u32': modifier['type'], 'meaning': 'modifier type is Add_Ergonomics'}}
    return result


def effect_list(item, fields):
    effects = item['effects']
    result = [{'effect': 'ammo', 'writable': True,
        'fields': [field for field in AMMO_FIELDS if field in fields]}]
    if effects['reload']:
        result.append({'effect': 'reload_duration', 'value': effects['reload']['value'], 'unit': 'seconds',
            'writable': True, 'field': 'attachment.reload_duration'})
    for modifier in effects['statModifiers'] or []:
        writable = modifier['typeName'] == 'Add_Ergonomics' and 'attachment.ergonomics_modifier' in fields
        result.append({'effect': 'stat_modifier', 'modifier': modifier['typeName'], 'value': modifier['value'],
            'writable': writable, 'field': 'attachment.ergonomics_modifier' if writable else None,
            'blocker': None if writable else 'Only the Add_Ergonomics modifier has proven semantics.'})
    if effects['reloadAnimationPatched']:
        result.append({'effect': 'reload_animation', 'writable': False,
            'blocker': 'Animation event names are resource references; replacing them is not reviewed.'})
    if effects['visualMagazinePatched']:
        result.append({'effect': 'visual_magazine', 'writable': False,
            'blocker': 'The magazine unit is a resource reference; replacing meshes is not reviewed as safe.'})
    return result


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    definitions = {item['id']: item for item in json.loads(FIELDS.read_text())['fields']}
    constants = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    attachments = {item['addPath']: dict(item, semanticId=attachment_key(item))
        for item in research['magazineAttachments']}
    names = Counter(item['debugName'] for item in attachments.values())
    consumers = {path: {'nativeDefaultOf': [], 'catalogResolvedFor': [], 'unlockListedFor': [], 'candidateFor': []}
        for path in attachments}
    consistency = {path: [] for path in attachments}
    published = {path: [] for path in attachments}
    weapons = []
    for weapon in research['weapons']:
        name = weapon['weapon']
        if weapon['nativeDefault']:
            consumers[weapon['nativeDefault']]['nativeDefaultOf'].append(name)
            consistency[weapon['nativeDefault']].append(weapon.get('defaultConsistency'))
        for path in weapon['unlockListed']:
            consumers[path]['unlockListedFor'].append(name)
        options = []
        for option in weapon['catalogOptions']:
            resolved = option['attachment']
            if resolved and option['relationship'] != 'native_resource_default':
                consumers[resolved]['catalogResolvedFor'].append(name)
            if resolved:
                published[resolved].append(option['effects'])
            else:
                for candidate in option['candidates']:
                    consumers[candidate]['candidateFor'].append(name)
            options.append({'name': option['name'], 'default': option['default'],
                'relationship': option['relationship'],
                'attachment': attachments[resolved]['semanticId'] if resolved else None,
                'candidates': [attachments[path]['semanticId'] for path in option['candidates']],
                'unlockListedCandidates': None if option['unlockListedCandidates'] is None else
                    [attachments[path]['semanticId'] for path in option['unlockListedCandidates']],
                'publishedEffects': option['effects'],
                'blocker': None if resolved else (
                    'Several native magazine attachments carry every published effect and the weapon\'s unlock '
                    'list does not separate them; the owner is not guessed.' if option['candidates'] else
                    'No native magazine attachment carries these published effects.')})
        for path in weapon['unlockListedOnly']:
            options.append({'name': None, 'nativeName': attachments[path]['debugName'], 'default': False,
                'relationship': 'unlock_listed', 'attachment': attachments[path]['semanticId'], 'candidates': [],
                'unlockListedCandidates': None, 'publishedEffects': None,
                'blocker': None, 'note': 'Listed in the weapon\'s unlock list; no catalog option names it.'})
        weapons.append({'weapon': name,
            'magazineSlot': {'slot': 'magazine',
                'defaultAttachment': attachments[weapon['nativeDefault']]['semanticId'] if weapon['nativeDefault'] else None,
                'defaultRelationship': weapon['defaultRelationship'],
                'defaultConsistency': weapon.get('defaultConsistency'),
                'baseRecordCapacityIsPlaceholder': weapon.get('defaultConsistency') == 'delta_matches_published_base_differs',
                'unlockList': weapon['unlockList'],
                'options': options}})

    fields, runtime_attachments, public_attachments = [], {}, []
    for path, item in sorted(attachments.items(), key=lambda pair: pair[1]['semanticId']):
        states = consistency[path]
        scope = consumers[path]
        known = sorted(set(scope['nativeDefaultOf'] + scope['catalogResolvedFor'] + scope['unlockListedFor']))
        object_key = 'backing:' + digest({'entityDelta': path})
        target = {'resource': 'weapon_attachment', 'attachment': item['semanticId'], 'path': 'magazine'}
        keys, runtime_fields = [], {}
        natives = native_fields(item)
        for field_id, native in natives.items():
            definition = definitions[field_id]
            component = native['component']
            # One live delta allocation: every field of an attachment can share one transaction.
            operation = 'operation:' + digest({'object': object_key, 'target': item['semanticId']})
            if field_id in AMMO_FIELDS:
                tier = ('native_owner_effect_consistent' if 'delta_matches_published_base_differs' in states
                    else 'native_owner_value_consistent' if 'delta_base_and_published_agree' in states
                    else 'native_owner')
            else:
                key = 'fullReloadSeconds' if field_id == 'attachment.reload_duration' else 'ergonomicsDelta'
                agree = any(effect.get(key) is not None and abs(effect[key] - native['value']) <= 0.01
                    for effect in published[path])
                tier = 'native_owner_effect_consistent' if agree else 'native_owner'
            instance = item['semanticId'].replace('weapon-attachment/v1/', 'attachment:') + ':' + field_id
            fields.append({'instanceKey': instance, 'semanticFieldId': field_id,
                'displayName': definition['display_name'], 'type': definition['type'], 'unit': definition['unit'],
                'currentDefault': native['value'], 'min': definition.get('min'), 'max': definition.get('max'),
                'editable': True, 'reason': None, 'target': target,
                'backingObjectId': object_key, 'backingObjectKind': 'EntityDelta:' + component,
                'operationGroup': operation, 'planGroup': 'plan:attachment:' + slug(item['debugName']),
                'requires': 'patch_or_transaction', 'allowSharedRequired': True, 'shared': True,
                'sharedConsumers': [{'weapon': name} for name in known],
                'sharedScopeKey': 'shared-scope:' + digest({'object': object_key, 'consumers': known}),
                'reviewedScopeComplete': False, 'dynamicConsumersPossible': True,
                'acknowledgement': 'allow_unverified_effect',
                'apiFieldConstant': constants[field_id], 'domain': 'attachment', 'planPhase': 1, 'dependsOn': [],
                'evidence': {'tier': tier, 'nativeOwner': 'entity delta keyed by the attachment AddPath, patching '
                    + component + (' (Add_Ergonomics stat modifier)' if field_id == 'attachment.ergonomics_modifier' else ''),
                    'gameplayWriteEffect': 'unproven'},
                'provenance': 'pinned entity delta table; live read-only allocation byte-identical to the file'})
            keys.append(instance)
            runtime = {'instanceKey': instance, 'component': COMPONENTS[component], 'storage': native['storage'],
                'componentOffset': native['componentOffset'], 'dataOffset': native['dataOffset'],
                'currentDefault': native['value'], 'operationGroup': operation,
                'min': definition.get('min'), 'max': definition.get('max'),
                'backing': {'kind': 'entity_delta', 'component': component}}
            if 'guard' in native:
                runtime['guard'] = {k: native['guard'][k] for k in ('componentOffset', 'dataOffset', 'u32')}
            runtime_fields[field_id] = runtime
        public_attachments.append({'semanticId': item['semanticId'], 'name': item['debugName'],
            'nameUnique': names[item['debugName']] == 1, 'slot': 'magazine',
            'values': dict({key: value['value'] for key, value in item['fields'].items()},
                **({'reloadDuration': item['effects']['reload']['value']} if item['effects']['reload'] else {}),
                **({'ergonomicsModifier': natives['attachment.ergonomics_modifier']['value']}
                    if 'attachment.ergonomics_modifier' in natives else {})),
            'effects': effect_list(item, natives), 'fieldInstanceKeys': keys,
            'compatibleWeapons': known,
            'consumers': dict(scope, scopeComplete=False, scopeNote=SCOPE_NOTE),
            'evidence': {'tier': ('native_owner_effect_consistent' if 'delta_matches_published_base_differs' in states
                else 'native_owner_value_consistent' if 'delta_base_and_published_agree' in states
                else 'native_owner'), 'defaultConsistency': states}})
        runtime_attachments[item['semanticId']] = {'semanticId': item['semanticId'], 'name': item['debugName'],
            'resource': item['addPath'], 'hashmapSlot': item['hashmapSlot'],
            'settingsIndex': item['settingsIndex'], 'fields': runtime_fields}
    tiers = Counter(field['evidence']['tier'] for field in fields)
    relationships = Counter(option['relationship'] for item in weapons for option in item['magazineSlot']['options'])
    resolved = sum(1 for item in weapons for option in item['magazineSlot']['options'] if option['attachment'])
    summary = {'magazineAttachments': len(public_attachments), 'fieldInstances': len(fields),
        'writableFieldInstances': len(fields),
        'fieldInstancesByField': dict(sorted(Counter(field['semanticFieldId'] for field in fields).items())),
        'weapons': len(weapons),
        'weaponsWithNativeDefault': sum(1 for item in weapons if item['magazineSlot']['defaultAttachment']),
        'weaponsWithUnlockList': sum(1 for item in weapons if item['magazineSlot']['unlockList']),
        'placeholderBaseCapacityWeapons': sum(1 for item in weapons if item['magazineSlot']['baseRecordCapacityIsPlaceholder']),
        'optionRelationships': dict(sorted(relationships.items())),
        'resolvedOptions': resolved,
        'unresolvedOptions': sum(1 for item in weapons for option in item['magazineSlot']['options'] if not option['attachment']),
        'attachmentsWithKnownConsumers': sum(1 for item in public_attachments if item['compatibleWeapons']),
        'writableByTier': dict(sorted(tiers.items())), 'selectionWritable': False,
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    public = {'contract': 'hd2runtime.weapon_attachment.magazine.v1', 'schemaVersion': 2,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'canonicalCollection': 'fieldInstances',
        'ownershipModel': {'chain': ['weapon default customization (slot magazine)', 'weapon customizable item',
                'entity delta keyed by the item AddPath', 'component patches: WeaponMagazineComponentData, '
                'WeaponReloadComponentData.duration, WeaponDataComponentData.weapon_stat_modifiers'],
            'writeScope': 'attachment definition; applies to every weapon that equips the attachment',
            'distinctFrom': ['weapon.capacity base record value', 'rounds currently loaded',
                'current or saved preset selection', 'visual magazine unit'],
            'weaponCapacityField': 'Weapons whose base record capacity is a placeholder keep weapon.capacity read-only.'},
        'optionRelationships': {
            'native_resource_default': 'The weapon resource\'s DefaultCustomizations names this attachment.',
            'catalog_effects_unique': 'Exactly one native attachment carries every published effect '
                '(capacity, starting and maximum magazines, reload time, ergonomics).',
            'catalog_effects_unlock_list': 'Several attachments carry the published effects; exactly one is in the '
                'weapon\'s own unlock list observed in memory.',
            'unlock_listed': 'In the weapon\'s unlock list, but no catalog option names it.',
            'catalog_effects_ambiguous': 'Unresolved: several candidates remain.',
            'catalog_effects_absent': 'Unresolved: no magazine attachment carries these effects.'},
        'acknowledgements': {'allow_shared': 'Required: consumer scope is not natively complete.',
            'allow_unverified_effect': 'Required: ' + UNVERIFIED},
        'supersedes': {'file': 'AttachmentOptionCapabilities.json',
            'fields': ['defaultOption.ammoValueOwnerProven', 'categories[].options[].nativeEffectOwner'],
            'note': 'Magazine ammo values are owned by these attachment definitions; the older file predates this proof.'},
        'selection': {'writable': False, 'reason': 'The player preset/selection owner is unresolved; the weapon '
            'resource default is not the player selection (R-72 Censor controlled diff). Editing an attachment '
            'definition never changes which magazine is equipped.'},
        'attachments': public_attachments, 'weapons': weapons, 'fieldInstances': fields, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0,
            'protectionChangesDuringGeneration': 0, 'fixtureFallback': 'disabled'}}
    text = json.dumps(public).lower()
    if '0x' in text or any(path[2:].lower() in text for path in attachments):
        raise ValueError('public attachment capability leaks a native identifier')
    runtime = {'version': public['hd2RuntimeVersion'], 'attachments': runtime_attachments,
        'names': {item['name']: item['semanticId'] for item in public_attachments if item['nameUnique']},
        'weapons': {item['weapon']: {'default': item['magazineSlot']['defaultAttachment'],
            'options': [{'name': option['name'], 'nativeName': option.get('nativeName'),
                'attachment': option['attachment'], 'relationship': option['relationship']}
                for option in item['magazineSlot']['options']]}
            for item in weapons},
        'summary': summary}
    return runtime, public


def generic_catalog(magazine_public):
    """Read-only metadata for every weapon customization item (all slots)."""
    research = json.loads(GENERIC_RESEARCH.read_text())
    magazine_ids = {item['name']: item['semanticId'] for item in magazine_public['attachments']}
    attachments, slots = [], Counter()
    for item in research['items']:
        slot = item['slots'][0] if item['slots'] else 'None'
        slots[slot] += 1
        magazine = magazine_ids.get(item['debugName'])
        semantic = magazine or ('weapon-attachment/v1/' + slug(slot) + '/' + slug(item['debugName']) + '/'
            + digest({'addPath': item['addPath']}))
        effects = []
        for patched in item['patched']:
            name = patched['label']
            if magazine and (name in MAGAZINE_EFFECTS or (name == 'stat modifiers' and any(
                    m['type'] == 'Add_Ergonomics' for m in item['statModifiers']))):
                blocker = 'Authored through MagazineAttachmentCapabilities.json.'
            else:
                blocker = EFFECT_BLOCKERS.get(name) or 'Native owner known; effect semantics are not reviewed.'
            effects.append({'component': patched['component'], 'offset': patched['offset'], 'size': patched['size'],
                'effect': name, 'writable': False, 'blocker': blocker})
        compatible = sorted(set(item['nativeDefaultOf']) | set(item['unlockListedFor']))
        attachments.append({'semanticId': semantic, 'name': item['debugName'], 'slot': slot,
            'slots': item['slots'], 'hasEntityDelta': item['hasDelta'], 'magazineAuthoring': magazine,
            'statModifiers': item['statModifiers'], 'effects': effects, 'compatibleWeapons': compatible,
            'consumers': {'nativeDefaultOf': item['nativeDefaultOf'], 'unlockListedFor': item['unlockListedFor'],
                'scopeComplete': False},
            'writable': False})
    weapons = {}
    for item in attachments:
        for weapon in item['compatibleWeapons']:
            weapons.setdefault(weapon, {}).setdefault(item['slot'], []).append(
                {'attachment': item['semanticId'], 'name': item['name'],
                 'default': weapon in item['consumers']['nativeDefaultOf'],
                 'unlockListed': weapon in item['consumers']['unlockListedFor']})
    catalog = {'contract': 'hd2runtime.weapon_attachment.catalog.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'scope': 'Read-only metadata for every weapon customization item. Writable magazine effects are in '
            'MagazineAttachmentCapabilities.json; selection (which attachment is equipped) is not writable.',
        'consumerSources': {'nativeDefaultOf': 'weapon resource DefaultCustomizations (pinned entity library)',
            'unlockListedFor': 'per-weapon unlock lists observed in the retained snapshot'},
        'attachments': attachments,
        'weapons': [{'weapon': name, 'slots': [{'slot': slot, 'options': options}
            for slot, options in sorted(value.items())]} for name, value in sorted(weapons.items())],
        'summary': {'attachments': len(attachments), 'bySlot': dict(sorted(slots.items())),
            'withEntityDelta': sum(1 for item in attachments if item['hasEntityDelta']),
            'withKnownConsumers': sum(1 for item in attachments if item['compatibleWeapons']),
            'withStatModifiers': sum(1 for item in attachments if item['statModifiers']),
            'weapons': len(weapons), 'writableEffects': 0},
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False}}
    research_ids = {item[key][2:].lower() for item in research['items'] for key in ('optionId', 'addPath')}
    text = json.dumps(catalog).lower()
    if re.search(r'\b0x[0-9a-f]{6,}', text) or any(value in text for value in research_ids):
        raise ValueError('public attachment catalog leaks a native identifier')
    return catalog


def lua(value):
    return generate_entity_authoring.lua(value)


def outputs(research_path=RESEARCH):
    runtime, public = build(research_path)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_attachment_authoring.py; do not edit.\nreturn ' + lua(migration_overlay.apply('attachment_authoring', runtime)) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n',
        GENERIC_OUTPUT: json.dumps(generic_catalog(public), indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale attachment authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
