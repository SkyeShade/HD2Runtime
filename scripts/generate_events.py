"""Generate the event catalog from schemas/events.json.

- domains/events_catalog.lua: the runtime view (names in catalog order, status, source, phase, hot).
- sdk/EventCatalog.json: the public catalog (every event, payload fields, handles, scripting API).
- the LuaLS stub section for the scripting API is emitted by scripts/generate_sdk.py from the same schema.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

SCHEMA = ROOT / 'schemas/events.json'
ACTIONS = ROOT / 'research/event-actions-F5FEE03DCFDB.json'
LUA_OUTPUT = ROOT / 'domains/events_catalog.lua'
JSON_OUTPUT = ROOT / 'sdk/EventCatalog.json'
STATUSES = ('available', 'blocked')
PHASES = ('post', 'pre', 'state')


def load() -> dict:
    return json.loads(SCHEMA.read_text(encoding='utf-8'))


def validate(schema: dict) -> None:
    names = [event['name'] for event in schema['events']]
    if len(names) != len(set(names)):
        raise ValueError('duplicate event names')
    sources = set(schema['sources'])
    for event in schema['events']:
        if event['status'] not in STATUSES:
            raise ValueError(event['name'] + ': unknown status ' + event['status'])
        if event['phase'] not in PHASES:
            raise ValueError(event['name'] + ': unknown phase ' + event['phase'])
        if event['status'] == 'blocked' and not event.get('reason'):
            raise ValueError(event['name'] + ': a blocked event needs its reason')
        if event['status'] == 'available' and event.get('source') not in sources:
            raise ValueError(event['name'] + ': an available event needs a known source')
        for field in event.get('payload', []):
            if not {'name', 'type', 'doc'} <= set(field):
                raise ValueError(event['name'] + ': payload fields need name, type and doc')


def action_catalog() -> dict:
    """What event scripts can request, for tools (ModBuilder pickers): names only, no ids or addresses."""
    research = json.loads(ACTIONS.read_text(encoding='utf-8'))
    common = {'hostOnly': True, 'inMissionOnly': True, 'creditedTo': 'local_player', 'liveTested': False}
    return {
        'explosions': dict(common, api='hd2.explosions.spawn', rateLimit={'burst': 6, 'perSecond': 1},
            named=[{'name': item['name'], 'aliases': ['Hellbomb'] if item['type'] == 242 else ['Portable Hellbomb'],
                'sharedType': bool(item['sharedType'])} for item in research['namedExplosions']],
            weapons=sorted({item['weapon'] for item in research['catalogueTypes']}),
            assets='Loaded automatically (the weapon\'s package; a Hellbomb\'s stratagem package).'),
        'projectiles': dict(common, api='hd2.projectiles.spawn', rateLimit={'burst': 12, 'perSecond': 4},
            weapons=sorted({item['weapon'] for item in research['projectile']['types']}),
            options={'position': 'required', 'direction': 'required, any non-zero length'},
            sideEffects=['Each projectile counts as a shot in the local player\'s stats.'],
            assets='Loaded automatically (the weapon\'s package).'),
        'statusEffects': dict(common, api='hd2.status.apply', creditedTo='local_player (instigator)',
            rateLimit={'burst': 10, 'perSecond': 5, 'perTargetBurst': 4, 'perTargetPerSecond': 2},
            statuses=[{'id': item['semanticId'], 'name': item['name'], 'family': item['family'],
                'duration': item['duration']} for item in research['status']['allowlist']],
            options={'buildup': {'default': 100, 'min_exclusive': 0, 'max': 1000,
                'meaning': 'Buildup added; the status starts at the target\'s susceptibility threshold.'},
                'strength': 'refused: strength and duration are the status\'s own'},
            unproven=['Visual effect residency is inferred (the same statuses are applied by enemies and '
                'environments).']),
        'spawnEntity': {'status': 'blocked', 'reason': 'The generic spawn\'s parameters and replication are not proven.'},
    }


def outputs() -> dict[str, str]:
    schema = load()
    validate(schema)
    runtime = {'names': [event['name'] for event in schema['events']],
        'events': {event['name']: {key: event[key] for key in ('status', 'source', 'phase', 'hot', 'reason')
            if event.get(key) is not None} for event in schema['events']}}
    header = '-- Generated from schemas/events.json by scripts/generate_events.py; do not edit.\n'
    public = {'contract': schema['contract'], 'schemaVersion': schema['schemaVersion'],
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'summary': {'events': len(schema['events']),
            'available': sorted(e['name'] for e in schema['events'] if e['status'] == 'available'),
            'blocked': sorted(e['name'] for e in schema['events'] if e['status'] == 'blocked')},
        'model': schema['model'], 'sources': schema['sources'], 'events': schema['events'],
        'handles': schema['handles'], 'api': schema['api'], 'actions': action_catalog()}
    return {str(LUA_OUTPUT.relative_to(ROOT)).replace('\\', '/'): header + 'return ' + lua(runtime) + '\n',
        str(JSON_OUTPUT.relative_to(ROOT)).replace('\\', '/'): json.dumps(public, indent=1) + '\n'}


STATIC = ('HD2Events', 'HD2Input', 'HD2Entities', 'HD2Explosions', 'HD2Actions', 'HD2Projectiles', 'HD2StatusEffects')   # tables of functions, not objects


def _class_lines(name: str, spec: dict, parent: str | None = None) -> list[str]:
    lines = ['']
    if spec.get('doc'):
        lines.append('---' + spec['doc'])
    lines.append('---@class ' + name + (' : ' + parent if parent else ''))
    for field, kind, doc in spec.get('fields', []):
        lines.append(('---@field ' + field + ' ' + kind + ' ' + doc).rstrip())
    lines.append('local ' + name + ' = {}')
    for method in spec.get('methods', []):
        if method['doc']:
            lines.append('---' + method['doc'])
        for param in method['params']:
            optional = param[1].endswith('|nil')
            lines.append('---@param ' + param[0] + ('?' if optional else '') + ' '
                + (param[1][:-4] if optional else param[1]))
        lines.append('---@return ' + method['returns'])
        lines.append('function ' + name + ('.' if name in STATIC else ':') + method['name'] + '('
            + ', '.join(p[0] for p in method['params']) + ') end')
    return lines


def stub_lines() -> tuple[list[str], list[str], list[str]]:
    """LuaLS stub sections for scripts/generate_sdk.py: (classes, HD2Runtime fields, hd2.* functions)."""
    schema = load()
    validate(schema)
    names = [event['name'] for event in schema['events']]
    lines = ['', '---@alias HD2EventName ' + '|'.join(json.dumps(n) for n in names)]
    for name, spec in schema['api']['classes'].items():
        if name in ('HD2Events', 'HD2ModContext'):
            continue
        lines += _class_lines(name, spec, spec.get('extends'))
    for name, spec in schema['handles'].items():
        lines += _class_lines(name, spec)
    for event in schema['events']:
        doc = event.get('summary') or ('Blocked: ' + event['reason'] if event['status'] == 'blocked' else '')
        lines += _class_lines('HD2Event_' + event['name'], {'doc': doc, 'fields': [
            [f['name'], f['type'], f['doc']] for f in event.get('payload', [])]}, 'HD2Event')
    # Friendly names for the payload classes: HD2EntityDiedEvent = HD2Event_entity_died, ...
    for event in schema['events']:
        friendly = 'HD2' + ''.join(part.capitalize() for part in event['name'].split('_')) + 'Event'
        lines.append('---@alias ' + friendly + ' HD2Event_' + event['name'])
    # hd2.events.on / once and the mod-context equivalents: one typed overload per available event.
    for owner in ('HD2Events', 'HD2ModContext'):
        spec = schema['api']['classes'][owner]
        plain = {'doc': spec['doc'], 'fields': spec.get('fields', []),
            'methods': [m for m in spec['methods'] if m['name'] not in ('on', 'once')]}
        lines += _class_lines(owner, plain)
        for method in ('on', 'once'):
            template = next(m for m in spec['methods'] if m['name'] == method)
            lines.append('---' + template['doc'] if template['doc'] else '---')
            for event in schema['events']:
                if event['status'] == 'available':
                    lines.append('---@overload fun(' + ('self: HD2ModContext, ' if owner == 'HD2ModContext' else '')
                        + 'name: ' + json.dumps(event['name']) + ', callback: fun(event: HD2Event_' + event['name']
                        + '), opts?: HD2SubscribeOptions): HD2Subscription')
            lines += ['---@param name HD2EventName', '---@param callback fun(event: HD2Event)',
                '---@param opts? HD2SubscribeOptions', '---@return HD2Subscription',
                'function ' + owner + (':' if owner == 'HD2ModContext' else '.') + method + '(name, callback, opts) end']
    fields = ['---@field ' + field + ' ' + kind for field, kind, _ in schema['api']['fields']]
    functions = []
    for function in schema['api']['functions']:
        functions.append('---' + function['doc'])
        for param in function['params']:
            optional = param[1].endswith('|nil')
            functions.append('---@param ' + param[0] + ('?' if optional else '') + ' '
                + (param[1][:-4] if optional else param[1]))
        functions += ['---@return ' + function['returns'],
            'function hd2.' + function['name'] + '(' + ', '.join(p[0] for p in function['params']) + ') end']
    return lines, fields, functions


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale event catalog: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
