"""Generate sdk/WeaponMovementCapabilities.json from research/weapon-movement-F5FEE03DCFDB.json.

The public movement-restriction catalog for tools such as ModBuilder. It lists, for every resolved player and
support weapon, the writable `weapon.stationary_while_firing` field and the read-only firing animation data, and
states plainly which movement behaviour is code- or animation-driven. No native identifiers are published.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weapon_movement_fields  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'sdk/WeaponMovementCapabilities.json'
CONTRACT = 'hd2runtime.weapon_movement.v1'


def build():
    research = json.loads(weapon_movement_fields.RESEARCH.read_text(encoding='utf-8'))
    weapons = []
    for row in research['weapons']:
        writable = bool(row['weaponData']) and row['weaponData']['ownerCount'] == 1
        weapons.append({'weapon': row['name'], 'kind': row['kind'],
            'accessor': ('hd2.support_weapon' if row['kind'] == 'support' else 'hd2.weapon'),
            'stationaryWhileFiring': {'field': 'hd2.fields.' + weapon_movement_fields.FIELD,
                'baseline': row.get('stationaryWhileFiring'), 'writable': writable,
                'acknowledgement': 'allow_unverified_effect' if writable else None,
                'reason': None if writable else 'No uniquely owned WeaponData record.'},
            'firingStance': row.get('firingStance'),
            'firingStanceEvents': ([row['firingStartEvent'], row['firingStopEvent']]
                if row.get('firingStartEvent') else None),
            'perShotWielderAnimation': row.get('perShotWielderAnimation'),
            'movementRestriction': row.get('movementRestriction', 'unknown')})
    by_name = {w['weapon']: w for w in weapons}
    document = {'contract': CONTRACT, 'schemaVersion': 1, 'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'model': {
            'summary': research['model']['representation'],
            'modes': {'none': 'No data-driven firing restriction.',
                'stationary_while_firing': ('weapon.stationary_while_firing is set: firing sends the weapon\'s '
                    'firing-start/stop wielder animation events and raises wielder action bit 55 (the Maxigun).')},
            'transitions': {
                'remove_maxigun_stationary': ('Set weapon.stationary_while_firing to false on the Maxigun. Its '
                    'movement-related weapon data then equals the GL-28\'s.'),
                'apply_stationary_elsewhere': ('Set it to true on another weapon. Weapons without firing-stance '
                    'events raise only the action bit (no brace animation).')},
            'readOnly': {'firingStance': 'Firing-start/stop wielder animation events (brace/brace_exit on the '
                'Maxigun and the GL-28). The only code reader found sends them only while stationary_while_firing '
                'is set, so they are not authored separately.',
                'perShotWielderAnimation': 'Per-shot wielder animation (fire_rifle, fire_minigun, ...); its effect '
                    'on movement is animation-graph behaviour.'},
            'unavailable': [
                {'behaviour': 'movement speed multiplier while firing', 'reason': 'No weapon record carries one; '
                    'the slowdown magnitude is code- or animation-driven.'},
                {'behaviour': 'separate dive / sprint / crouch bans', 'reason': 'Not separately represented in weapon '
                    'data; stationary_while_firing raises one action bit.'},
                {'behaviour': 'GL-28 slowdown', 'reason': 'Not produced by a proven data field (its brace events are '
                    'not sent by the only reader found).'},
                {'behaviour': 'Cremator slowdown', 'reason': 'No data owner found. Its exclusive WeaponData flag '
                    '(+1220) is read only by the weapon audio update.'}],
            'evidence': ('Structural fingerprint of the WeaponData layout, a game.dll code reader re-found by byte '
                'pattern on every research run, and anchor exclusivity (the Maxigun is the only weapon that sets '
                'the flag).')},
        'liveTested': False,
        'weapons': weapons,
        'summary': {'weapons': len(weapons),
            'writable': sum(w['stationaryWhileFiring']['writable'] for w in weapons),
            'stationaryWhileFiring': [w['weapon'] for w in weapons if w['stationaryWhileFiring']['baseline']],
            'braceStance': sorted(w['weapon'] for w in weapons if w['firingStance'] == 'brace')},
        'safety': {'rawIdentifiers': False, 'writes': 0}}
    if not by_name['M-1000 Maxigun']['stationaryWhileFiring']['baseline']:
        raise ValueError('Maxigun baseline changed')
    text = json.dumps(document, indent=2) + '\n'
    if re.search(r'0x[0-9a-fA-F]{8,}', text):
        raise ValueError('movement catalog leaks a native identifier')
    return text


def generate(check=False):
    body = build()
    if OUTPUT.exists() and OUTPUT.read_text(encoding='utf-8') == body:
        return []
    if check:
        raise RuntimeError('Stale weapon movement catalog: ' + str(OUTPUT))
    OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    return [OUTPUT]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(str(p) for p in generate(parser.parse_args().check)) or 'up to date')
