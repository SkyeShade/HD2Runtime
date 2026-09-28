"""Generate guarded Booster authoring metadata from retained native evidence.

Inputs: research/booster-authoring-F5FEE03DCFDB.json (scripts/research_booster_authoring.py).
Outputs: domains/booster_authoring.lua (runtime; native coordinates) and
sdk/BoosterAuthoringCapabilities.json (public; semantic identities only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_entity_authoring
import support_callin_linkage

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/booster-authoring-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/booster_fields.json'
JSON_OUTPUT = ROOT / 'sdk/BoosterAuthoringCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/booster_authoring.lua'
UNVERIFIED = ('No booster edit is gameplay-proven yet; the native value is proven, but whether the game '
    're-reads it for an active booster has not been tested.')
# Resupply is the only stratagem with a native booster entry; it is not yet in the stratagem
# authoring catalog, so the relationship uses the stable stratagem key scheme.
STRATAGEM_NAMES = {33: 'Resupply'}
# Experimental Infusion's stim buff: the unique status row whose values equal both published
# effects exactly (movement x1.1 via strength, damage x0.9 via IncomingDamageScale).
INFUSION = {'booster': 'Experimental Infusion', 'strength': 1.1, 'stat': 2, 'statValue': 0.9}
STAT_FIELDS = {2: 'status.incoming_damage_scale'}
# Effect-category identity for boosters missing from the UI template.
ELIMINATION = {
    'Integrated Extinguishers': ('susceptibility_gate', 'The only native booster value that gates status '
        'susceptibilities (two avatar susceptibilities); the other unnamed booster is Surplus EAT Allocation.'),
    'Surplus EAT Allocation': ('elimination', 'Remaining booster after every UI-template name and the '
        'susceptibility-gating value are assigned.'),
}


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def booster_key(name):
    return 'booster/v1/' + slug(name) + '/' + digest({'booster': name})


def build(research_path=RESEARCH):
    research = json.loads(Path(research_path).read_text())
    definitions = {item['id']: item for item in json.loads(FIELDS.read_text())['fields']}
    constants = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    enum = research['boosterEnum']
    gates = research['susceptibilityGates']
    gated_values = sorted({gate['booster'] for gate in gates})
    if len(gated_values) != 1:
        raise ValueError('expected exactly one susceptibility-gating booster value')

    # Values assigned by a unique name length; the rest stay candidate sets.
    assigned = {entry['enumValue'] for entry in research['catalog'] if entry['enumValue'] is not None}
    runtime, public, fields = {}, [], []

    def field(booster, target_path, field_id, current, backing, operation_group, shared, evidence):
        spec = definitions[field_id]
        instance = 'booster:' + slug(booster) + ':' + target_path + ':' + field_id
        entry = {'instanceKey': instance, 'semanticFieldId': field_id, 'displayName': spec['display_name'],
            'type': spec['type'], 'unit': spec['unit'], 'currentDefault': current, 'editable': True,
            'backing': backing, 'operationGroup': operation_group, 'shared': shared,
            'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': UNVERIFIED,
            'evidence': evidence}
        public_field = {'instanceKey': instance, 'booster': booster, 'semanticFieldId': field_id,
            'apiFieldConstant': constants[field_id], 'displayName': spec['display_name'], 'type': spec['type'],
            'unit': spec['unit'], 'target': {'resource': 'booster', 'path': target_path,
                'accessor': ['booster', target_path]},
            'value': {'baseline': current, 'expected': current, 'unit': spec['unit']},
            'writable': True,
            'acknowledgements': (['allow_shared'] if shared else []) + ['allow_unverified_effect'],
            'acknowledgementReason': UNVERIFIED,
            'sharedScope': {'shared': shared, 'requiresAcknowledgement': shared,
                'reviewedScopeComplete': not shared,
                'note': ('Applied by game code; no weapon damage references this status effect, but other '
                    'code paths cannot be excluded.') if shared else 'Uniquely owned native record.'},
            'operation': {'patchSupported': True, 'transactionGroupingKey': 'booster-operation/v1/'
                + digest({'booster': booster, 'group': operation_group}), 'planSupported': True},
            'evidence': evidence}
        fields.append(public_field)
        return entry

    for entry in research['catalog']:
        name = entry['name']
        candidates = entry['enumValueCandidates']
        identity = {'nativeName': entry['nativeName'], 'uiIcon': entry['uiIcon'],
            'enumValue': entry['enumValue'], 'enumValueCandidates': candidates,
            'evidence': list(entry['identityEvidence'])}
        if entry['enumValue'] is not None:
            identity['status'] = 'RESOLVED'
        elif candidates:
            identity['status'] = 'CANDIDATES'
            identity['evidence'].append('Several enum values share this alias length; the value is not guessed.')
        elif name in ELIMINATION:
            kind, reason = ELIMINATION[name]
            identity['status'] = 'EFFECT_CATEGORY' if kind == 'susceptibility_gate' else 'ELIMINATION'
            if kind == 'susceptibility_gate':
                identity['enumValue'] = gated_values[0]
            identity['evidence'].append(reason)
        else:
            identity['status'] = 'UNRESOLVED'
        targets, relationships, blocked = {}, [], []

        # Structural: stratagem booster entry -> entity delta -> rack -> turret entity.
        for link in research['stratagemBoosterEntries']:
            if identity['enumValue'] != link['booster'] or identity['status'] != 'RESOLVED':
                continue
            turret = next(t for t in research['boosterTurrets'] if t['booster'] == link['booster'])
            item = next(a for a in link['delta']['attachedEntities'] if a['resource'] == turret['resource'])
            stratagem = STRATAGEM_NAMES[link['recordKind']]
            relationships.append({'kind': 'stratagem_booster_entry', 'stratagem': stratagem,
                'stratagemSemanticId': support_callin_linkage.stratagem_key(stratagem),
                'stratagemAuthoring': 'not in StratagemAuthoringCapabilities (supply stratagems are not authored yet)',
                'effect': ('When the booster is active, a native entity delta rewrites the resupply hellpod rack: '
                    'four supply boxes plus one mounted turret.'),
                'deployedEntity': 'deployed_entity', 'turretProjectileShared': True,
                'evidence': 'structural: StratagemInfo booster list -> entity delta -> HellpodRackComponent item'})
            components = turret['components']
            evidence = {'tier': 'structural_chain_exact_fingerprint',
                'chain': ['StratagemInfo booster entry', 'entity delta', 'hellpod rack item', 'turret entity'],
                'gameplayWriteEffect': 'unproven'}
            chain = {'stratagemKind': link['recordKind'], 'stratagemId': link['id'], 'entryIndex': link['entryIndex'],
                'booster': link['booster'], 'payload': link['payload'], 'entityDelta': link['entityDelta'],
                'package': link['package'], 'hashmapSlot': link['delta']['hashmapSlot'],
                'settingsIndex': link['delta']['settingsIndex'],
                'rackComponentIndex': link['delta']['patchedComponentIndex'], 'rackSlot': item['rackSlot'],
                'dataOffset': item['dataOffset']}
            target_fields = {}
            rate = components['ProjectileWeaponComponentData']
            target_fields['weapon.fire_rate'] = field(name, 'deployed_entity', 'weapon.fire_rate', rate['fireRate'],
                {'kind': 'component', 'component': 'ProjectileWeaponComponentData', 'offset': 8, 'storage': 'f32',
                    'width': 4, **{k: rate[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}},
                'component:ProjectileWeaponComponentData', False, dict(evidence, fingerprint='640 rpm'))
            magazine = components['WeaponMagazineComponentData']
            target_fields['magazine.capacity'] = field(name, 'deployed_entity', 'magazine.capacity',
                magazine['magazine'][0],
                {'kind': 'component', 'component': 'WeaponMagazineComponentData', 'offset': 136, 'storage': 'u32',
                    'width': 4, **{k: magazine[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}},
                'component:WeaponMagazineComponentData', False, dict(evidence, fingerprint='140 rounds'))
            targets['deployed_entity'] = {'kind': 'entity', 'resource': turret['resource'],
                'entityRow': turret['entityRow'], 'chain': chain, 'fields': target_fields}
            blocked.append({'field': 'turret projectile / damage', 'reason': (
                'The turret fires a projectile definition shared with player weapons; edit it through the '
                'owning weapon view with allow_shared instead.')})

        # Fingerprint: stat-modifying status row equal to both published effects.
        if name == INFUSION['booster']:
            matches = [row for row in research['statModifyingStatusRows']
                if abs(row['strength'] - INFUSION['strength']) < 1e-6 and len(row['multipliers']) == 1
                and row['multipliers'][0]['stat'] == INFUSION['stat']
                and abs(row['multipliers'][0]['value'] - INFUSION['statValue']) < 1e-6]
            if len(matches) != 1:
                raise ValueError('Experimental Infusion status fingerprint is not unique')
            row = matches[0]
            if research['statusTypeReferencesFromDamageInfo'].get(str(row['type'])):
                raise ValueError('status row is referenced by weapon damage; scope changed')
            evidence = {'tier': 'unique_exact_multi_value_fingerprint',
                'fingerprint': 'movement x1.1 (strength) and damage x0.9 (IncomingDamageScale) both match',
                'nativeName': 'UI booster member CombatDrugs', 'gameplayWriteEffect': 'unproven'}
            group = 'status_row'
            target_fields = {
                'status.strength': field(name, 'status_effect', 'status.strength', row['strength'],
                    {'kind': 'status_row', 'offset': 36, 'storage': 'f32', 'width': 4}, group, True, evidence),
                'status.duration': field(name, 'status_effect', 'status.duration', row['duration'],
                    {'kind': 'status_row', 'offset': 40, 'storage': 'f32', 'width': 4}, group, True,
                    dict(evidence, fingerprint='schema-labelled duration; no published value')),
            }
            for index, item in enumerate(row['multipliers']):
                target_fields[STAT_FIELDS[item['stat']]] = field(name, 'status_effect', STAT_FIELDS[item['stat']],
                    item['value'], {'kind': 'status_multiplier', 'storage': 'f32', 'width': 4, 'index': index,
                        'stat': item['stat'], 'arrayOffset': row['multiplierArrayOffset'],
                        'count': len(row['multipliers'])}, group, True, evidence)
            targets['status_effect'] = {'kind': 'status_row', 'statusType': row['type'], 'row': row['row'],
                'rowOffset': row['offset'], 'fields': target_fields}
            relationships.append({'kind': 'status_effect_fingerprint',
                'effect': 'Stim-applied status effect: movement speed multiplier, duration, incoming damage scale.',
                'evidence': evidence['fingerprint'], 'sharedScope': 'applied by game code only'})

        if identity['status'] == 'EFFECT_CATEGORY':
            relationships.append({'kind': 'susceptibility_gate', 'owner': 'Helldiver avatar',
                'gatedSusceptibilities': len(gates),
                'effect': 'Replaces the status effect applied by two avatar susceptibilities while active.'})
            blocked.append({'field': 'susceptibility override', 'reason': (
                'The override is a reference to a native effect preset whose semantics are not proven; '
                'no scalar is exposed.')})
        if not targets and not blocked:
            blocked.append({'field': 'booster effect', 'reason': (
                'No native data member references this booster: the type library links the Booster enum only '
                'from stratagem booster lists and status susceptibilities. Its effect is applied by game code.')})
        semantic = booster_key(name)
        runtime[name] = {'name': name, 'semanticId': semantic, 'identityStatus': identity['status'],
            'enumValue': identity['enumValue'], 'targets': targets}
        public.append({'name': name, 'semanticId': semantic, 'identity': identity,
            'relationships': relationships, 'writable': bool(targets),
            'targets': sorted(targets), 'fieldInstanceKeys': [f['instanceKey'] for t in targets.values()
                for f in t['fields'].values()], 'blockedFields': blocked})

    summary = {'boosters': len(public), 'writableBoosters': sum(b['writable'] for b in public),
        'fieldInstances': len(fields),
        'identityStatus': {status: sum(b['identity']['status'] == status for b in public)
            for status in ('RESOLVED', 'CANDIDATES', 'EFFECT_CATEGORY', 'ELIMINATION', 'UNRESOLVED')},
        'nativeEnumValues': len(enum['aliasLengths']) - 2, 'researchWrites': 0, 'protectionChanges': 0,
        'fixtureFallback': 'disabled'}
    document = {'contract': 'hd2runtime.booster.guarded_authoring.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'canonicalCollection': 'fieldInstances',
        'nativeModel': {'identity': ('Native Booster enum member, named by the game UI template and matched to '
                'enum values by type-library alias length. Shared lengths stay candidate sets.'),
            'typeLibraryReferences': ['StratagemInfo booster list', 'StatusEffectSusceptibility booster gate'],
            'ownership': 'Boosters have no component or settings type; effects live on the records they reference.'},
        'acknowledgements': {'allow_unverified_effect': 'Required for every booster field. ' + UNVERIFIED,
            'allow_shared': 'Required where the owning record is applied by game code with an open consumer scope.'},
        'boosters': public, 'fieldInstances': fields, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0}}
    text = json.dumps(document).lower()
    if '0x' in text:
        raise ValueError('public booster capability leaks a native identifier')
    return {'version': document['hd2RuntimeVersion'], 'boosters': runtime}, document


def outputs(research_path=RESEARCH):
    runtime, public = build(research_path)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_booster_authoring.py; do not edit.\nreturn '
        + generate_entity_authoring.lua(runtime) + '\n', JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale booster authoring outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
