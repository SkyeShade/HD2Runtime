"""Generate the per-weapon fire-mode summary (runtime table and GUI-facing SDK catalog)."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fire_mode_fields

ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / 'sdk/WeaponFireModeCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/weapon_fire_modes.lua'
STATES = {'selectable': 'Modes can be added, removed or reordered (up to three: the selector cycles the first three '
        'slots only); the fire-mode selector is bound.',
    'addable': 'One mode and a free input: the single mode can be replaced, or two or three modes listed together with '
        'the Firemode binding (weapon_function.<input> = "fire_mode") in the same transaction.',
    'single_mode': 'The single mode can be replaced (for example Single -> Automatic); no selector is bound and no '
        'input is free, so a second mode cannot be switched to in game.',
    'blocked': 'Read-only; see reason.', 'absent': 'The weapon has no fire-mode data.'}


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


def build():
    rows, research = fire_mode_fields.load()
    player = {w['name']: w for w in json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())['weapons']}
    support = {w['name']: w for w in json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())['weapons']}
    weapons = []
    for (kind, name), row in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1])):
        writable = fire_mode_fields.writable(row)
        identity_ok = True
        if kind == 'player':
            fields = {f['semanticFieldId']: f for f in player[name]['fields']}
            identity_ok = bool(fields.get(fire_mode_fields.MODES_FIELD, {}).get('editable'))
        else:
            item = support.get(name)
            identity_ok = bool(item) and fire_mode_fields.MODES_FIELD in (item.get('writableFieldsByDomain') or {}).get('fire_mode', [])
        reason = row.get('reason')
        if writable and not identity_ok:
            reason = 'The weapon\'s runtime identity is ambiguous; ordinary writes fail closed.'
        weapons.append({'kind': kind, 'weapon': name, 'state': row['state'] if identity_ok or not writable else 'blocked',
            'modes': row.get('modes'), 'defaultMode': row.get('defaultMode'),
            'selector': row.get('selector') and {'left': row['selector']['left'], 'right': row['selector']['right']},
            'selectorBound': row.get('selectorBound'), 'maxModes': row.get('maxModes') if identity_ok else None,
            'bindableInputs': list(row.get('bindableInputs') or []) if row['state'] == 'addable' and identity_ok else [],
            'binding': {'fields': ['hd2.fields.weapon_function.' + side for side in row.get('bindableInputs') or []],
                'value': fire_mode_fields.BINDING_VALUE, 'rule': fire_mode_fields.BINDING_RULE}
                if row['state'] == 'addable' and identity_ok else None,
            'burstRounds': row.get('burstRounds'),
            'writable': writable and identity_ok, 'reason': None if writable and identity_ok else reason,
            'fields': {'modes': fire_mode_fields.MODES_FIELD, 'burstRounds': fire_mode_fields.BURST_FIELD}
                if writable and identity_ok else None})
    summary = {'weapons': len(weapons),
        'byState': dict(sorted(Counter((w['kind'], w['state']) for w in weapons).items(), key=str)),
        'resolvedModeSets': sum(1 for w in weapons if w['modes']),
        'writable': sum(1 for w in weapons if w['writable']),
        'fullAutoPossible': sum(1 for w in weapons if w['writable']),
        'fullAutoAlreadyPresent': sum(1 for w in weapons if w['modes'] and 'automatic' in w['modes'])}
    summary['byState'] = {f'{k[0]}:{k[1]}': v for k, v in summary['byState'].items()}
    public = {'contract': 'hd2runtime.weapon.fire_modes.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'nativeModel': research['model'],
        'modes': {'automatic': 'FireMode Automatic (1)', 'single': 'FireMode Single (2)', 'burst': 'FireMode Burst (3)'},
        'unmappedNativeModes': 'FireMode values 4-8 (charge and safety states) are read-only and never offered.',
        'fields': {'modes': {'constant': 'hd2.fields.fire_mode.modes', 'type': 'ordered list of mode names',
                'default': 'the first entry', 'acknowledgement': 'allow_unverified_effect'},
            'burstRounds': {'constant': 'hd2.fields.fire_mode.burst_rounds', 'type': 'integer',
                'range': list(fire_mode_fields.BURST_RANGE), 'acknowledgement': 'allow_unverified_effect'}},
        'fireRate': 'One rate of fire per weapon (weapon.fire_rate), shared by every mode.',
        'states': STATES, 'shareScope': 'weapon_local: every WeaponDataComponentData record has one owner.',
        'weapons': weapons, 'summary': summary}
    runtime = {'weapons': {f"{w['kind']}:{w['weapon']}": {key: w[key] for key in
        ('state', 'modes', 'defaultMode', 'selector', 'maxModes', 'burstRounds', 'writable', 'reason', 'bindableInputs',
            'binding')} for w in weapons},
        'fireRate': public['fireRate']}
    return runtime, public


def outputs():
    runtime, public = build()
    return {LUA_OUTPUT: '-- Generated by scripts/generate_fire_mode_authoring.py; do not edit.\nreturn ' + lua(runtime) + '\n',
        JSON_OUTPUT: json.dumps(public, indent=2) + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale fire-mode outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
