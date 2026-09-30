"""Acknowledgements a field gained in a later SDK, for version-aware compatibility with older mods.

A mod built with an older SDK was valid when it was written: its operations carry every acknowledgement that SDK
asked for. When a later SDK adds an acknowledgement to a field that was writable without one (0.28.0 added
allow_unverified_effect to 144 player weapon projectile, damage and explosion fields whose fired row it could no
longer establish, and to the SH-51 Directional Shield body's health and armor), Runtime accepts that field without
the acknowledgement from a mod that declares an older SDK, and logs it as a legacy operation
(docs/legacy-sdk-compatibility.md). Mods that declare the newer SDK keep the rule.

  py scripts/generate_legacy_acknowledgements.py --research v0.27.0 0.28.0
      Compare the SDK catalogs published at tag v0.27.0 with the current ones and record, in
      schemas/legacy_acknowledgements.json, every field that 0.27.0 accepted without allow_unverified_effect and
      that now needs it, as introduced in 0.28.0. Entries of other releases are kept.
  py scripts/generate_legacy_acknowledgements.py [--check]
      Write (or check) domains/legacy_acknowledgements.lua, the runtime lookup, from that reviewed file. Every entry
      must still name an existing field.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'schemas/legacy_acknowledgements.json'
LUA_OUTPUT = ROOT / 'domains/legacy_acknowledgements.lua'
ACKNOWLEDGEMENT = 'allow_unverified_effect'
PLAYER = 'sdk/PlayerWeaponAuthoringCapabilities.json'
# Catalogs whose field instances carry an instanceKey and a semantic target; only the resources the runtime lookup
# supports (domains/entity_writes.lua) may carry legacy entries.
INSTANCE_RESOURCES = {'backpack', 'vehicle'}


def lua(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(key) + ']=' + lua(item) for key, item in sorted(value.items())) + '}'
    return '{' + ','.join(lua(item) for item in value) + '}'


def entity_field_key(target, field_id):
    """The lookup key of an entity field: its target path, linked entity, damage zone and mount, then its id (the
    identity domains/entity_writes.lua find_field matches)."""
    return '|'.join((target.get('path') or '', target.get('linked') or '', target.get('zone') or '',
        target.get('mount') or '', field_id))


def fields(catalogs):
    """Every field instance of the catalogs: key -> (identity, the field entry)."""
    found = {}
    player = catalogs.get(PLAYER)
    for weapon in (player or {}).get('weapons', []):
        for field in weapon['fields']:
            found[('player_weapon', weapon['name'], field['semanticFieldId'])] = field
    for path, catalog in sorted(catalogs.items()):
        for field in catalog.get('fieldInstances', []) if isinstance(catalog, dict) else []:
            target = field.get('target') or {}
            resource = target.get('resource')
            name = target.get(resource) if resource else None
            if not isinstance(name, str) or 'semanticFieldId' not in field:
                continue
            found[(resource, name, entity_field_key(target, field['semanticFieldId']))] = field
    return found


def git_catalogs(tag):
    names = subprocess.run(['git', 'ls-tree', '--name-only', tag, 'sdk/'], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.split()
    result = {}
    for name in names:
        if name.endswith('.json'):
            body = subprocess.run(['git', 'show', f'{tag}:{name}'], cwd=ROOT, capture_output=True, check=True).stdout
            result[name] = json.loads(body.decode('utf-8'))
    return result


def current_catalogs():
    return {path.relative_to(ROOT).as_posix(): json.loads(path.read_text(encoding='utf-8'))
        for path in sorted((ROOT / 'sdk').glob('*.json'))}


def needs(field):
    return bool(field.get('editable')) and field.get('acknowledgement') == ACKNOWLEDGEMENT


def research(tag, since):
    """Record the fields `since` started to require the acknowledgement on, compared with the SDK at `tag`."""
    previous = fields(git_catalogs(tag))
    current = fields(current_catalogs())
    entries = []
    for key, field in sorted(current.items()):
        old = previous.get(key)
        if old is None or not needs(field) or not old.get('editable') or old.get('acknowledgement') == ACKNOWLEDGEMENT:
            continue
        resource, target, field_key = key
        if resource != 'player_weapon' and resource not in INSTANCE_RESOURCES:
            raise RuntimeError(f'{resource} {target} {field_key}: no runtime lookup for this resource')
        entries.append({'since': since, 'acknowledgement': ACKNOWLEDGEMENT, 'resource': resource, 'target': target,
            'field': field_key, 'apiFieldConstant': field.get('apiFieldConstant'),
            'reason': field.get('acknowledgementReason')})
    history = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'schemaVersion': 1,
        'releases': [], 'entries': []}
    commit = subprocess.run(['git', 'rev-list', '-n', '1', tag], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()
    history['description'] = ('Acknowledgements a field gained in a later SDK. A mod that declares an SDK older than '
        '`since` wrote the field without the acknowledgement and was valid then; Runtime accepts it as a legacy '
        'operation and logs it (docs/legacy-sdk-compatibility.md). Generated by '
        'scripts/generate_legacy_acknowledgements.py --research; reviewed.')
    history['releases'] = sorted([item for item in history['releases'] if item['since'] != since]
        + [{'since': since, 'comparedWith': tag, 'comparedWithCommit': commit,
            'rule': 'editable without ' + ACKNOWLEDGEMENT + ' in the SDK published at ' + tag + ', editable and '
            'requiring it in ' + since}], key=lambda item: [int(part) for part in item['since'].split('.')])
    history['entries'] = [item for item in history['entries'] if item['since'] != since] + entries
    HISTORY.write_text(json.dumps(history, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return entries


def build():
    history = json.loads(HISTORY.read_text(encoding='utf-8'))
    current = fields(current_catalogs())
    table, missing = {}, []
    for entry in history['entries']:
        key = (entry['resource'], entry['target'], entry['field'])
        if key not in current:
            missing.append(' '.join(key))
            continue
        by_target = table.setdefault(entry['acknowledgement'], {}).setdefault(entry['resource'], {})
        by_target.setdefault(entry['target'], {})[entry['field']] = entry['since']
    if missing:
        raise RuntimeError('schemas/legacy_acknowledgements.json names fields that no longer exist: '
            + ', '.join(missing))
    return ('-- Generated by scripts/generate_legacy_acknowledgements.py from schemas/legacy_acknowledgements.json;\n'
        '-- do not edit. acknowledgement -> resource -> target -> field -> the SDK version that introduced it.\n'
        'return ' + lua(table) + '\n')


def generate(check=False):
    body = build()
    stale = not LUA_OUTPUT.exists() or LUA_OUTPUT.read_text(encoding='utf-8') != body
    if stale and check:
        raise RuntimeError('Stale legacy acknowledgement table: ' + str(LUA_OUTPUT))
    if stale:
        LUA_OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    return [LUA_OUTPUT] if stale else []


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--research', nargs=2, metavar=('TAG', 'SINCE'),
        help='compare the SDK catalogs at TAG with the current ones and record them as introduced in SINCE')
    args = parser.parse_args()
    if args.research:
        print(len(research(*args.research)), 'fields gained', ACKNOWLEDGEMENT, 'in', args.research[1])
    print(', '.join(str(p) for p in generate(args.check)) or 'up to date')
