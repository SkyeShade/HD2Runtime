"""Generate guarded Booster authoring metadata from retained native evidence.

Inputs: research/booster-authoring-F5FEE03DCFDB.json (scripts/research_booster_authoring.py) and
research/booster-native-F5FEE03DCFDB.json (scripts/research_booster_native.py).
Outputs: domains/booster_authoring.lua (runtime; native coordinates and pinned code proofs) and
sdk/BoosterAuthoringCapabilities.json (public; semantic identities only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import generate_entity_authoring
import support_callin_linkage

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/booster-authoring-F5FEE03DCFDB.json'
NATIVE = ROOT / 'research/booster-native-F5FEE03DCFDB.json'
FIELDS = ROOT / 'schemas/booster_fields.json'
JSON_OUTPUT = ROOT / 'sdk/BoosterAuthoringCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/booster_authoring.lua'
UNVERIFIED = ('No booster edit is gameplay-proven yet; the native value and its consumer are proven, but the '
    'in-game effect of a changed value has not been tested.')
# Resupply is the only stratagem with a native booster entry; it is not yet in the stratagem
# authoring catalog, so the relationship uses the stable stratagem key scheme.
STRATAGEM_NAMES = {33: 'Resupply'}
STAT_FIELDS = {2: 'status.incoming_damage_scale'}
# Reviewed catalog bridge for the two boosters the UI template does not name. Each is also
# corroborated structurally below (susceptibility gate; granted EAT stratagem).
NATIVE_NAMES = {'Integrated Extinguishers': 'FireExtinguish', 'Surplus EAT Allocation': 'FreeEAT'}

# Native Booster definition table scalar: reviewed value range per semantic field. Ranges exist
# because consumers divide by, subtract from, or truncate the value (see the effect text).
RANGES = {
    'booster.damage_taken_scale': (0, 4, False, 'Multiplies incoming damage; negative values would heal.'),
    'booster.stamina_scale': (0.1, 10, False, 'Stamina drain is divided by this value.'),
    'booster.terrain_slowdown_scale': (0, 1, False, 'Movement factor is 1 - slowdown * value; above 1 it can go '
        'negative.'),
    'booster.radar_range_scale': (0.1, 10, False, 'Scales the radar scan; zero disables it.'),
    'booster.reinforcements_per_player': (0, 20, True, 'Truncated to an integer by the game.'),
    'booster.reinforcement_cooldown_scale': (0.05, 10, False, 'Scales a scheduled cooldown.'),
    'booster.encounter_rate_scale': (0.1, 10, False, 'Two encounter timers are divided by this value.'),
    'booster.extraction_time_scale': (0.05, 10, False, 'Scales the extraction call-in time.'),
    'booster.slow_scale': (0, 4, False, 'Scales an applied slow/stun amount.'),
    'booster.double_sample_chance': (0, 1, False, 'Probability.'),
    'booster.health_floor': (0, 1, False, 'Health fraction.'),
    'booster.sample_drop_cap': (0, 1000, True, 'Truncated to an integer by the game.'),
    'booster.burn_decay_bonus': (0, 0.95, False, 'Burn decay is multiplied by 1 / (1 - value); 1 divides by zero.'),
}
# Scraped wiki values used only as fingerprints for the native baseline.
FINGERPRINTS = {
    'Vitality': ('exact', 'Wiki armor table lists the Vitality Booster damage factor as 90%.'),
    'Stamina': ('not_comparable', 'Wiki reports +22.5% max stamina and +40% regeneration; the native value is '
        'a single 1.3 efficiency factor applied inside the stamina model.'),
    'MuscleEnhancement': ('none', 'No published numeric value.'),
    'UAVRecon': ('approximate', 'Wiki: radar range increased by approximately 50%.'),
    'IncreasedReinforcementBudget': ('exact', 'Wiki: +1 reinforcement per Helldiver (5 to 6 solo).'),
    'FlexibleReinforcementBudget': ('exact', 'Wiki: 25% shorter (2:00 to 1:30).'),
    'LocalizationConfusion': ('approximate', 'Wiki: encounter timer threshold ~15% longer; the native timers are '
        'divided by 0.9 (+11.1%) and the spawn rate multiplied by 0.9.'),
    'FastExtraction': ('exact', 'Wiki: 30% faster (2:00 to 1:24).'),
    'SlowStunResistance': ('differs', 'Wiki reports ~25% shorter slows; the native multiplier is 0.5 on the '
        'applied slow amount, whose relation to the observed duration is not established.'),
    'DoubleSampleChance': ('exact', 'Wiki: 15% chance to receive twice the samples.'),
    'DeathMarch': ('exact', 'Wiki: stops once health reaches 5%.'),
    'BigEnemiesDropSamples': ('exact', 'Wiki: capped at 10 drops per mission.'),
    'FireExtinguish': ('approximate', 'Wiki: burning shortened from 3 s to ~1 s; the native bonus doubles the '
        'burn decay rate.'),
}
TUNING_UNUSED = ('The native Booster definition table holds a scalar for this booster, but no game code '
    'reads it; writing it would change nothing.')
BLOCKED = {
    'HellpodSpaceOptimization': [('booster effect', 'Eight code paths select the item\'s full capacity instead of the '
        'default fill when the booster is active (a conditional select); no scalar participates.')],
    'MuscleEnhancement': [('terrain slowdown values', 'The base slowdown fractions belong to terrain data used '
        'without the booster; only the booster multiplier is exposed.')],
    'UAVRecon': [('base radar scale', 'The 0.025 base scale is a pooled literal shared by unrelated code.')],
    'FastExtraction': [('base extraction time', 'Owned by the Extract stratagem; only the booster multiplier is '
        'exposed.')],
    'LocalizationConfusion': [('base encounter timers', 'Mission settings used without the booster.')],
    'Stamina': [('stamina capacity / regeneration split', 'The booster contributes one efficiency factor; the '
        'published +22.5%/+40% split is derived inside the stamina model, not stored.')],
    'CombatDrugs': [('status row +32 scalar (3.5)', 'The type library hides this member\'s name and no fingerprint '
        'identifies it.'), ('reticle sway', 'The published +25% sway has no native value in the stim status row.')],
    'BigEnemiesDropSamples': [('per-enemy drop chance', 'Read from a runtime loot hashmap filled from enemy data, '
        'not from booster data.')],
    'FireExtinguish': [('susceptibility override', 'The two gated avatar susceptibilities swap in a particle-effect '
        'reference (spawned with an identity transform); it is cosmetic, and no scalar is exposed.')],
    'DefensiveAmmoPod': [('turret projectile / damage', 'The turret fires a projectile definition shared with player '
        'weapons; edit it through the owning weapon view with allow_shared instead.'),
        ('turret payload lifetime', 'The native value is 0 (no explicit limit); writing it would change behavior.'),
        ('turret targeting / sensor / rotation', 'The type library hides the member names and no fingerprint '
        'identifies them.')],
    'DeathMarch': [('exhausted sprint movement', 'Selected by the presence of the Dead Sprint status, not a scalar.')],
    'FreeEAT': [('granted stratagem cooldown', 'The native cooldown is 0 with the no-cooldown type; not a tunable.')],
    'ShockPods': [('stun status definition', 'Status type 40 is shared by every stun source; only this explosion\'s '
        'status strength is exposed.')],
    'FieryDrop': [('burn status definition', 'Status type 5 is shared by every fire source; only this explosion\'s '
        'status strength is exposed.')],
}
EXPLOSION_FINGERPRINT = {
    'FieryDrop': ('exact', 'Wiki "HellpodImpact Fiery Drop": 200/200 fire, AP 10, demolition 40, stagger 15, push 20, '
        'status 20, radii 2/4/4 m.'),
    'ShockPods': ('exact', 'Wiki "Explosion Hellpod Stun": 50/50 arc, AP 10, demolition 40, stagger 50, status 100, '
        'radii 2/4/4 m.'),
    'SmokePods': ('none', 'No published numeric value; the row has no damage.'),
}
SHARED_SELECTED = ('Selected by a literal in the booster branch of game code. No other literal call site and none '
    'of the decoded data carriers reference this native type, but DestructionEffect unions and dynamically '
    'typed call sites are not excluded.')


def digest(value, length=16):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:length]


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-') or 'root'


def booster_key(name):
    return 'booster/v1/' + slug(name) + '/' + digest({'booster': name})


def pins(proofs):
    return [{'rva': item['rva'], 'bytes': item['bytes']} for item in proofs]


def build(research_path=RESEARCH, native_path=NATIVE):
    research = json.loads(Path(research_path).read_text())
    native = json.loads(Path(native_path).read_text())
    definitions = {item['id']: item for item in json.loads(FIELDS.read_text())['fields']}
    constants = {value: f'hd2.fields.{domain}.{constant}' for domain, items in
        generate_entity_authoring.api_constants().items() for constant, value in items.items()}
    names = native['boosterNames']['names']
    rows = native['boosterTable']['rows']
    gates = research['susceptibilityGates']
    if sorted({gate['booster'] for gate in gates}) != [names.index('FireExtinguish')]:
        raise ValueError('the susceptibility gate no longer names FireExtinguish')
    granted = native['grant']['granted']
    if [(g['booster'], g['stratagemTypeName']) for g in granted] != [('FreeEAT', 'LATOneshot_Booster')]:
        raise ValueError('the granted-stratagem link no longer names FreeEAT -> LATOneshot_Booster')
    ui = dict(research['boosterEnum']['uiPairs'])
    settings = {(family, row['kind']): row for family, items in native['settingsRows'].items() for row in items}

    def raw(family, kind):
        return bytes.fromhex(settings[(family, kind)]['bytes'])

    gate_function = {'rva': native['isBoosterActive']['rva'], 'bytes': native['isBoosterActive']['bytes']}
    runtime, public, fields = {}, [], []

    def field(booster, target_path, field_id, current, backing, operation_group, shared, evidence, value_range=None,
            shared_note=None):
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
            'sharedScope': {'shared': shared, 'requiresAcknowledgement': shared, 'reviewedScopeComplete': not shared,
                'note': shared_note or 'Owned by this booster only.'},
            'operation': {'patchSupported': True, 'transactionGroupingKey': 'booster-operation/v1/'
                + digest({'booster': booster, 'group': operation_group}), 'planSupported': True},
            'evidence': evidence}
        if value_range:
            low, high, integer, reason = value_range
            entry['range'] = {'min': low, 'max': high, 'integer': integer}
            public_field['range'] = {'min': low, 'max': high, 'integer': integer, 'reason': reason}
        fields.append(public_field)
        return entry

    for entry in research['catalog']:
        name = entry['name']
        native_name = entry['nativeName'] or NATIVE_NAMES[name]
        value = names.index(native_name)
        candidates = entry['enumValueCandidates']
        if candidates and value not in candidates:
            raise ValueError('native name table contradicts the alias-length candidates: ' + name)
        evidence = ['game.dll enum-name table (value-indexed None..Count, 22 entries) names member '
            + native_name + ' at value ' + str(value),
            'type-library alias lengths agree with the name table for all 22 values']
        if native_name in ui:
            evidence.append('game UI template binds native member ' + native_name + ' to ' + ui[native_name])
        elif native_name == 'FireExtinguish':
            evidence.append('corroborated: the only value that gates status susceptibilities')
        else:
            evidence.append('corroborated: its native table row grants StratagemType LATOneshot_Booster')
        identity = {'status': 'RESOLVED', 'method': 'native_enum_name_table', 'nativeName': native_name,
            'uiIcon': ui.get(native_name), 'enumValue': value, 'aliasLengthCandidates': candidates, 'evidence': evidence}
        row = rows[value]
        targets, relationships, blocked, graph = {}, [], [], []
        gate_calls = [call for call in native['isBoosterActive']['calls'] if call['booster'] == value]
        graph.append({'from': 'booster', 'to': 'IsBoosterActive', 'kind': 'code_gate', 'sites': len(gate_calls)})

        # Native Booster definition table scalar.
        tuning = native['tuning'].get(native_name)
        if tuning:
            field_id = tuning['semanticFieldId']
            proofs = [mov for gate in tuning['gates'] for mov in gate['mov']] \
                + [gate['call'] for gate in tuning['gates']] + tuning['readers']
            status, note = FINGERPRINTS[native_name]
            tier = 'native_table_code_consumer' + ('_exact_fingerprint' if status == 'exact' else '')
            evidence_block = {'tier': tier, 'chain': ['Booster enum value', 'IsBoosterActive gate',
                'native Booster definition table scalar', 'gated consumer'],
                'consumerSites': len(tuning['readers']), 'effect': tuning['effect'],
                'fingerprint': {'status': status, 'note': note}, 'gameplayWriteEffect': 'unproven'}
            targets['tuning'] = {'kind': 'booster_table', 'value': value, 'proofs': pins(proofs), 'fields': {
                field_id: field(name, 'tuning', field_id, tuning['baseline'], {'kind': 'booster_table', 'row': value,
                    'offset': 8, 'storage': 'f32', 'width': 4}, 'booster_table', False, evidence_block,
                    RANGES[field_id])}}
            graph.append({'from': 'IsBoosterActive', 'to': 'BoosterDefinitionTable.scalar', 'kind': 'gated_read',
                'sites': len(tuning['readers'])})
            relationships.append({'kind': 'native_booster_table', 'effect': tuning['effect']})
        elif row['scalar']:
            blocked.append({'field': 'native table scalar (' + str(row['scalar']) + ')', 'reason': TUNING_UNUSED})

        # Granted stratagem: table[booster].+4 -> StratagemSettings row -> use count.
        if row['grantedStratagemType']:
            record = native['grantedStratagemRecord']
            if record['kind'] != row['grantedStratagemType']:
                raise ValueError('granted stratagem record kind changed')
            evidence_block = {'tier': 'structural_code_chain_exact_fingerprint',
                'chain': ['native Booster definition table +4 (granted StratagemType)', 'StratagemSettings runtime '
                    'table', 'use count read at grant time'], 'fingerprint': {'status': 'exact',
                    'note': 'Wiki: two free uses of the EAT stratagem per mission.'},
                'effect': 'Number of uses of the booster-granted EAT stratagem; read when the stratagem is granted at '
                    'mission start, so an edit applies to the next grant.', 'gameplayWriteEffect': 'unproven'}
            targets['granted_stratagem'] = {'kind': 'granted_stratagem', 'value': value,
                'stratagemType': record['kind'], 'record': {'id': record['id'], 'group': record['group'],
                    'row': record['row'], 'package': record['package'], 'payloads': record['payloads']},
                'proofs': pins(native['grant']['proof']), 'fields': {'stratagem.max_uses': field(name,
                    'granted_stratagem', 'stratagem.max_uses', record['use_count'], {'kind': 'stratagem_row',
                        'offset': 80, 'storage': 'u32', 'width': 4}, 'stratagem_row', False, evidence_block,
                    (0, 100, True, 'Stratagem use count.'))}}
            graph.append({'from': 'BoosterDefinitionTable.grantedStratagem', 'to': 'StratagemSettings',
                'kind': 'structural_pointer_table', 'stratagem': 'LATOneshot_Booster'})
            relationships.append({'kind': 'granted_stratagem', 'stratagemTypeName': 'LATOneshot_Booster',
                'effect': 'Grants a dedicated one-shot EAT stratagem with its own use count.'})

        # Code-selected hellpod-impact explosion.
        selector = native['selectors'].get(native_name)
        if selector and selector['family'] == 'explosion':
            kind = selector['nativeType']
            explosion = raw('explosion', kind)
            damage_type = struct.unpack_from('<I', explosion, 4)[0]
            row_info = settings[('explosion', kind)]
            status, note = EXPLOSION_FINGERPRINT[native_name]
            evidence_block = {'tier': 'structural_code_selector' + ('_exact_fingerprint' if status == 'exact' else ''),
                'chain': ['IsBoosterActive gate', 'hellpod-impact spawn with literal ExplosionType',
                    'ExplosionSettings row'], 'fingerprint': {'status': status, 'note': note},
                'gameplayWriteEffect': 'unproven'}
            target = {'kind': 'explosion', 'value': value, 'explosionType': kind, 'group': row_info['group'],
                'row': row_info['row'], 'damageType': damage_type,
                'proofs': pins(selector['gate'] + [selector['selector']]), 'fields': {}}
            for offset, field_id in ((16, 'explosion.inner_radius'), (20, 'explosion.outer_radius'),
                    (24, 'explosion.shockwave_radius')):
                current = round(struct.unpack_from('<f', explosion, offset)[0], 6)
                if current:
                    target['fields'][field_id] = field(name, 'explosion', field_id, current,
                        {'kind': 'explosion', 'offset': offset, 'storage': 'f32', 'width': 4}, 'explosion', True,
                        evidence_block, (0, 100, False, 'Explosion radius in meters.'), SHARED_SELECTED)
                else:
                    blocked.append({'field': field_id, 'reason': 'Native value is 0; enabling it would change '
                        'behavior rather than tune it.'})
            if damage_type:
                damage = raw('damage', damage_type)
                damage_info = settings[('damage', damage_type)]
                target.update({'damageGroup': damage_info['group'], 'damageRow': damage_info['row']})
                for offset, field_id, storage in ((4, 'explosion.damage.standard_damage', 'i32'),
                        (8, 'explosion.damage.durable_damage', 'i32'), (12, 'explosion.damage.ap_direct', 'u32'),
                        (28, 'explosion.damage.demolition', 'u32'), (32, 'explosion.damage.stagger', 'u32'),
                        (36, 'explosion.damage.push_force', 'u32')):
                    current = struct.unpack_from('<' + ('i' if storage == 'i32' else 'I'), damage, offset)[0]
                    if current:
                        target['fields'][field_id] = field(name, 'explosion', field_id, current,
                            {'kind': 'explosion_damage', 'offset': offset, 'storage': storage, 'width': 4},
                            'explosion_damage', True, evidence_block, (0, 100000, True, 'Integer damage value.'),
                            SHARED_SELECTED)
                    else:
                        blocked.append({'field': field_id, 'reason': 'Native value is 0; enabling it would change '
                            'behavior rather than tune it.'})
                status_type = struct.unpack_from('<I', damage, 44)[0]
                if status_type:
                    target['statusType'] = status_type
                    target['fields']['status.strength'] = field(name, 'explosion', 'status.strength',
                        round(struct.unpack_from('<f', damage, 48)[0], 6), {'kind': 'explosion_damage',
                            'offset': 48, 'storage': 'f32', 'width': 4}, 'explosion_damage', True, evidence_block,
                        (0, 10000, False, 'Status strength applied by this explosion.'), SHARED_SELECTED)
            targets['explosion'] = target
            graph.append({'from': 'IsBoosterActive', 'to': 'ExplosionSettings', 'kind': 'code_literal_selector'})
            relationships.append({'kind': 'hellpod_impact_explosion',
                'effect': 'When the booster is active, every hellpod impact spawns this extra explosion.'})

        # Code-selected status effect (Experimental Infusion) and status damage (Dead Sprint).
        if selector and selector['family'] == 'status':
            kind = selector['nativeType']
            status_row = settings[('status', kind)]
            proofs = pins(selector['gate'] + [selector['selector']])
            if native_name == 'CombatDrugs':
                matches = [item for item in research['statModifyingStatusRows'] if item['type'] == kind]
                if len(matches) != 1 or abs(matches[0]['strength'] - 1.1) > 1e-6 \
                        or [(m['stat'], m['value']) for m in matches[0]['multipliers']] != [(2, 0.9)]:
                    raise ValueError('Experimental Infusion status row changed')
                item = matches[0]
                evidence_block = {'tier': 'structural_code_selector_exact_fingerprint',
                    'chain': ['IsBoosterActive gate', 'stim status apply with literal StatusEffectType (29 instead of '
                        '25)', 'StatusEffectSettings row'],
                    'fingerprint': {'status': 'exact', 'note': 'movement x1.1 (strength) and damage x0.9 '
                        '(IncomingDamageScale) both match'}, 'gameplayWriteEffect': 'unproven'}
                target_fields = {
                    'status.strength': field(name, 'status_effect', 'status.strength', item['strength'],
                        {'kind': 'status_row', 'offset': 36, 'storage': 'f32', 'width': 4}, 'status_row', True,
                        evidence_block, None, SHARED_SELECTED),
                    'status.duration': field(name, 'status_effect', 'status.duration', item['duration'],
                        {'kind': 'status_row', 'offset': 40, 'storage': 'f32', 'width': 4}, 'status_row', True,
                        dict(evidence_block, fingerprint={'status': 'none', 'note': 'schema-labelled duration; no '
                            'published value'}), None, SHARED_SELECTED)}
                for index, multiplier in enumerate(item['multipliers']):
                    target_fields[STAT_FIELDS[multiplier['stat']]] = field(name, 'status_effect',
                        STAT_FIELDS[multiplier['stat']], multiplier['value'], {'kind': 'status_multiplier',
                            'storage': 'f32', 'width': 4, 'index': index, 'stat': multiplier['stat'],
                            'arrayOffset': item['multiplierArrayOffset'], 'count': len(item['multipliers'])},
                        'status_row', True, evidence_block, None, SHARED_SELECTED)
                targets['status_effect'] = {'kind': 'status_row', 'statusType': kind, 'row': item['row'],
                    'rowOffset': item['offset'], 'proofs': proofs, 'fields': target_fields}
                graph.append({'from': 'IsBoosterActive', 'to': 'StatusEffectSettings', 'kind': 'code_literal_selector'})
                relationships.append({'kind': 'status_effect', 'effect': 'Stims apply this status effect instead of '
                    'the normal stim status: movement speed multiplier, duration, incoming damage scale.'})
            else:
                status_bytes = raw('status', kind)
                damage_type = struct.unpack_from('<I', status_bytes, 44)[0]
                damage = raw('damage', damage_type)
                damage_info = settings[('damage', damage_type)]
                evidence_block = {'tier': 'structural_code_selector', 'chain': ['IsBoosterActive gate',
                    'Dead Sprint status apply with literal StatusEffectType', 'StatusEffectSettings damage type',
                    'DamageInfo row'], 'fingerprint': {'status': 'none', 'note': 'Wiki reports ~3.6% health per '
                        'second; the tick rate that turns this damage into a rate is not established.'},
                    'gameplayWriteEffect': 'unproven'}
                target_fields = {}
                for offset, field_id in ((4, 'damage.standard_damage'), (8, 'damage.durable_damage')):
                    target_fields[field_id] = field(name, 'status_damage', field_id,
                        struct.unpack_from('<i', damage, offset)[0], {'kind': 'status_damage', 'offset': offset,
                            'storage': 'i32', 'width': 4}, 'status_damage', True, evidence_block,
                        (0, 1000, True, 'Integer damage per status tick.'), SHARED_SELECTED)
                targets['status_damage'] = {'kind': 'status_damage', 'value': value, 'statusType': kind,
                    'group': status_row['group'], 'row': status_row['row'], 'damageType': damage_type,
                    'damageGroup': damage_info['group'], 'damageRow': damage_info['row'], 'proofs': proofs,
                    'fields': target_fields}
                graph.append({'from': 'IsBoosterActive', 'to': 'StatusEffectSettings', 'kind': 'code_literal_selector'})
                graph.append({'from': 'StatusEffectSettings', 'to': 'DamageInfo', 'kind': 'settings_reference'})
                relationships.append({'kind': 'status_damage', 'effect': 'While sprinting exhausted, Dead Sprint '
                    'applies a status whose damage drains the Helldiver\'s health.'})

        # Structural: stratagem booster entry -> entity delta -> rack -> turret entity.
        for link in research['stratagemBoosterEntries']:
            if value != link['booster']:
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
            graph.append({'from': 'StratagemInfo.boosterList', 'to': 'entity delta', 'kind': 'data_reference'})
            components = turret['components']
            evidence_block = {'tier': 'structural_chain_exact_fingerprint',
                'chain': ['StratagemInfo booster entry', 'entity delta', 'hellpod rack item', 'turret entity'],
                'gameplayWriteEffect': 'unproven'}
            chain = {'stratagemKind': link['recordKind'], 'stratagemId': link['id'], 'entryIndex': link['entryIndex'],
                'booster': link['booster'], 'payload': link['payload'], 'entityDelta': link['entityDelta'],
                'package': link['package'], 'hashmapSlot': link['delta']['hashmapSlot'],
                'settingsIndex': link['delta']['settingsIndex'],
                'rackComponentIndex': link['delta']['patchedComponentIndex'], 'rackSlot': item['rackSlot'],
                'dataOffset': item['dataOffset']}
            rate = components['ProjectileWeaponComponentData']
            magazine = components['WeaponMagazineComponentData']
            targets['deployed_entity'] = {'kind': 'entity', 'resource': turret['resource'],
                'entityRow': turret['entityRow'], 'chain': chain, 'fields': {
                'weapon.fire_rate': field(name, 'deployed_entity', 'weapon.fire_rate', rate['fireRate'],
                    {'kind': 'component', 'component': 'ProjectileWeaponComponentData', 'offset': 8, 'storage': 'f32',
                        'width': 4, **{k: rate[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}},
                    'component:ProjectileWeaponComponentData', False, dict(evidence_block,
                        fingerprint={'status': 'exact', 'note': '640 rpm'}), None, 'Uniquely owned native record.'),
                'magazine.capacity': field(name, 'deployed_entity', 'magazine.capacity', magazine['magazine'][0],
                    {'kind': 'component', 'component': 'WeaponMagazineComponentData', 'offset': 136, 'storage': 'u32',
                        'width': 4, **{k: magazine[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}},
                    'component:WeaponMagazineComponentData', False, dict(evidence_block,
                        fingerprint={'status': 'exact', 'note': '140 rounds'}), None, 'Uniquely owned native record.')}}

        if native_name == 'FireExtinguish':
            relationships.append({'kind': 'susceptibility_gate', 'owner': 'Helldiver avatar',
                'gatedSusceptibilities': len(gates),
                'effect': 'While active, two avatar susceptibilities swap their effect reference for a particle '
                    'effect (cosmetic).'})
            graph.append({'from': 'StatusEffectSusceptibility.boosterGate', 'to': 'particle effect override',
                'kind': 'data_reference'})
        for blocked_field, reason in BLOCKED.get(native_name, []):
            blocked.append({'field': blocked_field, 'reason': reason})
        semantic = booster_key(name)
        runtime[name] = {'name': name, 'semanticId': semantic, 'identityStatus': 'RESOLVED', 'enumValue': value,
            'nativeName': native_name, 'targets': targets}
        public.append({'name': name, 'semanticId': semantic, 'identity': identity,
            'implementation': 'native_table' if 'tuning' in targets else 'code_selected_settings' if
                ({'explosion', 'status_effect', 'status_damage'} & set(targets)) else 'data_reference' if targets
                else 'code_behavior',
            'relationships': relationships, 'nativeGraph': graph, 'writable': bool(targets),
            'targets': sorted(targets), 'fieldInstanceKeys': [f['instanceKey'] for t in targets.values()
                for f in t['fields'].values()], 'blockedFields': blocked})

    native_block = {'imageSize': native['gameDll']['imageSize'], 'namesRva': native['boosterNames']['rva'],
        'nameStrings': native['boosterNames']['stringRvas'], 'names': names,
        'tableRva': native['boosterTable']['rva'], 'stride': native['boosterTable']['stride'], 'rows': len(rows),
        'rowIdentity': [row['bytes'][:16] + '00000000' + row['bytes'][24:] for row in rows],
        'tableBound': {'rva': native['boosterTable']['bound']['rva'], 'bytes': native['boosterTable']['bound']['bytes']},
        'gateFunction': gate_function}
    summary = {'boosters': len(public), 'writableBoosters': sum(b['writable'] for b in public),
        'fieldInstances': len(fields),
        'identityStatus': {status: sum(b['identity']['status'] == status for b in public)
            for status in ('RESOLVED', 'CANDIDATES', 'EFFECT_CATEGORY', 'ELIMINATION', 'UNRESOLVED')},
        'fieldsByTarget': {path: sum(f['target']['path'] == path for f in fields) for path in
            ('tuning', 'explosion', 'status_effect', 'status_damage', 'granted_stratagem', 'deployed_entity')},
        'sharedFieldInstances': sum('allow_shared' in f['acknowledgements'] for f in fields),
        'nativeEnumValues': len(names) - 2, 'isBoosterActiveCallSites': len(native['isBoosterActive']['calls']),
        'boosterTableRows': len(rows), 'boosterTableReaders': sum(1 for r in native['boosterTable']['references']
            if r['kind'] == 'load'), 'boosterTableStores': 0, 'codeWrites': 0,
        'researchWrites': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    document = {'contract': 'hd2runtime.booster.guarded_authoring.v2', 'schemaVersion': 2,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'canonicalCollection': 'fieldInstances',
        'nativeModel': {'identity': ('game.dll\'s own Booster enum-name table (value-indexed, None..Count), '
                'validated against the type library\'s alias length for every value.'),
            'boosterSystem': ('IsBoosterActive(booster) gates every booster effect in game code. Tuning scalars live '
                'in a native Booster definition table in game.dll\'s writable data section: one row per enum value, '
                'scalar at +8, granted StratagemType at +4. The table is static: no code writes it.'),
            'typeLibraryReferences': ['StratagemInfo booster list', 'StatusEffectSusceptibility booster gate'],
            'targets': {'tuning': 'Native Booster definition table scalar; booster-local by construction.',
                'explosion': 'ExplosionSettings / DamageInfo rows selected by a literal in the hellpod-impact branch.',
                'status_effect': 'StatusEffectSettings row the stim applies while the booster is active.',
                'status_damage': 'DamageInfo row of the status Dead Sprint applies.',
                'granted_stratagem': 'StratagemSettings row the booster grants.',
                'deployed_entity': 'Turret entity attached by the booster\'s entity delta.'},
            'codeConstantPatching': 'none: every writable value is data; code bytes are only read as proofs.'},
        'acknowledgements': {'allow_unverified_effect': 'Required for every booster field. ' + UNVERIFIED,
            'allow_shared': 'Required where the owning settings row is selected by game code and other consumers '
                'cannot be fully excluded.'},
        'boosters': public, 'fieldInstances': fields, 'summary': summary,
        'safety': {'runtimeAddresses': False, 'rawResourceIdentifiers': False, 'writesDuringGeneration': 0}}
    text = json.dumps(document).lower()
    if '0x' in text:
        raise ValueError('public booster capability leaks a native identifier')
    return {'version': document['hd2RuntimeVersion'], 'native': native_block, 'boosters': runtime}, document


def outputs(research_path=RESEARCH, native_path=NATIVE):
    runtime, public = build(research_path, native_path)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_booster_authoring.py; do not edit.\nreturn '
        + generate_entity_authoring.lua(migration_overlay.apply('booster_authoring', runtime)) + '\n', JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH, native_path=NATIVE):
    stale = []
    for path, body in outputs(research_path, native_path).items():
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
