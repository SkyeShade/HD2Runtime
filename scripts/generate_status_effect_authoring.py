"""Generate status effect authoring (0.30.4) from research/status-effects-F5FEE03DCFDB.json.

A status effect's own definition, edited once for every attack that applies it (docs/status-effects.md "Status effect
stats"):

- hd2.status_effect(id): the StatusEffectSettings row (152-byte StatusEffectInfo, identity = the row's own name
  string; research/status-effects-F5FEE03DCFDB.json). Field: status.duration (+40, f32, the type library's
  StatusEffectInfo duration member; the field every weapon, stratagem and throwable catalogue already authors through
  its attacks).
- hd2.status_effect(id):damage(): the DamageInfo row the status deals while active (StatusEffectInfo +44, the type
  library's DamageInfoType member). Fields: the DamageInfo members the weapon catalogues author (damage.standard_damage
  ... damage.push_force).

Both rows are global settings rows: every attack applying the status uses them, and several statuses can share one
tick DamageInfo row (gas, gas_2 and gloom share one). Every write needs allow_shared; the tick damage also needs
allow_unverified_effect (the rate at which a status deals it is not established). Not exposed: StatusEffectInfo +36
(an unnamed FP32; its meaning is unknown) and the tick rate.

Outputs: domains/status_effect_authoring.lua (the write domain's reviewed rows) and
sdk/StatusEffectAuthoringCapabilities.json (the public catalogue for ModBuilder and stats editors).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_fields  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LUA_OUTPUT = ROOT / 'domains/status_effect_authoring.lua'
JSON_OUTPUT = ROOT / 'sdk/StatusEffectAuthoringCapabilities.json'
CONTRACT = 'hd2runtime.status_effect_authoring.v1'
DURATION_MAX = 100000.0      # bleed stores 9999 s ("until healed"); a finite, non-negative duration
DAMAGE_MAX = 100000
DAMAGE_FIELDS = (
    ('damage.standard_damage', 'Standard damage per tick', 4, 'i32', 'damage', 'standardDamage', None),
    ('damage.durable_damage', 'Durable damage per tick', 8, 'i32', 'damage', 'durableDamage', None),
    ('damage.ap_direct', 'Armor penetration: direct', 12, 'u32', 'armor_class', 'armorPenetration', 0),
    ('damage.ap_slight', 'Armor penetration: slight angle', 16, 'u32', 'armor_class', 'armorPenetration', 1),
    ('damage.ap_large', 'Armor penetration: large angle', 20, 'u32', 'armor_class', 'armorPenetration', 2),
    ('damage.ap_extreme', 'Armor penetration: extreme angle', 24, 'u32', 'armor_class', 'armorPenetration', 3),
    ('damage.demolition', 'Demolition', 28, 'u32', 'force', 'demolition', None),
    ('damage.stagger', 'Stagger', 32, 'u32', 'force', 'stagger', None),
    ('damage.push_force', 'Push force', 36, 'u32', 'force', 'pushForce', None),
)
DAMAGE_ACK = ('a status deals this DamageInfo row while it is active; the rate at which it is applied (the tick) is '
    'not established, and no in-game test has measured an edit yet')
SHARED_STATUS = ('the status definition is global: every weapon, stratagem, throwable and enemy attack that applies '
    'this status uses it')


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
        return '{' + ','.join('[' + lua(key) + ']=' + lua(item) for key, item in sorted(value.items(),
            key=lambda pair: str(pair[0]))) + '}'
    return '{' + ','.join(lua(item) for item in value) + '}'


def build():
    research = json.loads(status_fields.RESEARCH.read_text(encoding='utf-8'))
    statuses = research['statuses']
    by_damage = {}
    for s in statuses:
        if s['tickDamage']:
            by_damage.setdefault(s['tickDamage']['damageType'], []).append(s['semanticId'])
    runtime, public = {}, []
    for s in statuses:
        sid = s['semanticId']
        consumers = [c['object'] for c in s['knownConsumers']]
        duration = {'semanticFieldId': 'status.duration', 'displayName': 'Duration', 'type': 'number',
            'unit': 'seconds', 'currentDefault': s['duration'], 'editable': True, 'shared': True,
            'min': 0.0, 'max': DURATION_MAX, 'sharedReason': SHARED_STATUS,
            'target': {'resource': 'status_effect', 'status': sid, 'path': 'status'},
            'operationGroup': 'status/' + sid,
            'backing': {'kind': 'settings', 'settings': 'status', 'group': s['group'], 'row': s['row'],
                'recordType': s['nativeType'], 'offset': 40, 'width': 4, 'storage': 'f32'}}
        entry = {'semanticId': sid, 'name': s['name'], 'family': s['family'], 'nativeType': s['nativeType'],
            'group': s['group'], 'row': s['row'],
            'targets': {'status': {'fields': {'status.duration': duration}}}}
        item = {'semanticId': sid, 'name': s['name'], 'family': s['family'], 'appliedBy': s['knownConsumers'],
            'fields': [{k: v for k, v in duration.items() if k not in ('backing', 'operationGroup')}],
            'tickDamage': None}
        tick = s['tickDamage']
        if tick:
            others = sorted(x for x in by_damage[tick['damageType']] if x != sid)
            users = [c['object'] for c in tick['consumers']]
            reason = SHARED_STATUS + (('; the same tick DamageInfo row is the tick damage of ' + ', '.join(others))
                if others else '') + (('; it is also the DamageInfo row of ' + ', '.join(users)) if users else '')
            fields = {}
            for field_id, label, offset, storage, unit, key, index in DAMAGE_FIELDS:
                value = tick[key] if index is None else tick[key][index]
                fields[field_id] = {'semanticFieldId': field_id, 'displayName': label, 'type': 'integer',
                    'unit': unit, 'currentDefault': value, 'editable': True, 'shared': True,
                    'min': 0, 'max': DAMAGE_MAX if unit != 'armor_class' else 10, 'sharedReason': reason,
                    'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': DAMAGE_ACK,
                    'target': {'resource': 'status_effect', 'status': sid, 'path': 'damage'},
                    'operationGroup': 'status-damage/' + str(tick['damageType']),
                    'backing': {'kind': 'settings', 'settings': 'damage', 'group': tick['group'], 'row': tick['row'],
                        'recordType': tick['damageType'], 'offset': offset, 'width': 4, 'storage': storage}}
            entry['targets']['damage'] = {'damageType': tick['damageType'], 'group': tick['group'],
                'row': tick['row'], 'statusLink': 44, 'sharedWithStatuses': others, 'otherUsers': users,
                'fields': fields}
            item['tickDamage'] = {'sharedWithStatuses': others, 'otherUsers': users,
                'fields': [{k: v for k, v in f.items() if k not in ('backing', 'operationGroup')}
                    for f in fields.values()]}
        runtime[sid] = entry
        item['appliedByCount'] = len(consumers)
        public.append(item)
    # The runtime copy leaves out the long reasons (the write domain builds its messages from the target).
    def lean(value):
        if isinstance(value, dict):
            return {k: lean(v) for k, v in value.items() if k not in ('sharedReason', 'acknowledgementReason')}
        return value
    lua_body = ('-- Generated by scripts/generate_status_effect_authoring.py. Status effect definitions: '
        'StatusEffectSettings rows and their tick DamageInfo rows.\nreturn ' + lua({'statuses': lean(runtime),
            'damageAcknowledgement': DAMAGE_ACK}) + '\n')
    document = {'contract': CONTRACT, 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'source': research['source'],
        'api': {'status': 'hd2.status_effect(id) (fields: status.duration)',
            'damage': 'hd2.status_effect(id):damage() (fields: damage.*, the DamageInfo row the status deals)',
            'ids': 'hd2.status_effects() lists every id (the row\'s own name string, sdk/StatusEffectCatalog.json)'},
        'acknowledgements': {'allow_shared': 'every field: a status definition is global',
            'allow_unverified_effect': 'the tick damage fields: ' + DAMAGE_ACK},
        'notExposed': [
            {'member': 'StatusEffectInfo +36', 'reason': 'an unnamed FP32 (fire 5, gas 0.25, choked 50); its meaning '
                'is not established, so it stays read-only and unnamed'},
            {'member': 'tick rate', 'reason': 'how often a status applies its DamageInfo row is not located'},
            {'member': 'target-side susceptibility', 'reason': 'per enemy class tables '
                '(research/status-susceptibility-F5FEE03DCFDB.json) with stripped type names; read-only'}],
        'effectiveDuration': 'status.duration is the stored duration. In game, Stun Medium (3 s) was observed to '
            'hold enemies for about 1-2 s; target-side processing may shorten it (sdk/StatusEffectCatalog.json).',
        'summary': {'statuses': len(public), 'withTickDamage': sum(1 for x in public if x['tickDamage']),
            'sharedTickDamageRows': sum(1 for v in by_damage.values() if len(v) > 1)},
        'statuses': public}
    return lua_body, json.dumps(document, indent=2) + '\n'


def generate(check=False):
    lua_body, json_body = build()
    stale = [path for path, body in ((LUA_OUTPUT, lua_body), (JSON_OUTPUT, json_body))
        if not path.exists() or path.read_text(encoding='utf-8') != body]
    if stale and check:
        raise RuntimeError('Stale status effect authoring: ' + ', '.join(str(p) for p in stale))
    for path, body in ((LUA_OUTPUT, lua_body), (JSON_OUTPUT, json_body)):
        if path in stale:
            path.write_text(body, encoding='utf-8', newline='\n')
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(str(p) for p in generate(parser.parse_args().check)) or 'up to date')
