"""Generate compact Runtime composition metadata from the reviewed snapshot catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'schemas/player_weapon_composition_catalog.json'
OUTPUT = ROOT / 'domains/player_weapon_composition.lua'


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(key) + ']=' + lua(item)
            for key, item in sorted(value.items())) + '}'
    if isinstance(value, list):
        return '{' + ','.join(lua(item) for item in value) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=True)


def build():
    source = json.loads(SOURCE.read_text())
    weapons = {}
    for name, item in source['weapons'].items():
        attacks = {}
        order = []
        for attack in item['attacks']:
            value = {'role': attack['role'], 'aliases': attack['aliases'],
                'projectile_type': attack['projectileType'],
                'projectile_settings': attack['projectileSettings'],
                'compatibility_class': attack['compatibilityClass'],
                'target_backing': attack['targetBacking'],
                'writable_reference_swap': attack['writableReferenceSwap'],
                'explosions': attack.get('explosions', []),
                'terminal_actions': {action['phase']: {
                    'phase': action['phase'], 'offset': action['offset'],
                    'reference_type': action['referenceType'],
                    'action_kind': action['actionKind'],
                    'linked_explosion_record': action['linkedExplosionRecord'],
                    'reference_class': action.get('referenceClass'),
                    'projectile_settings_consumers': action.get('projectileSettingsConsumers', []),
                    'affects_multiple_resources': action.get('affectsMultipleResources', False),
                    'readable': action['readable'], 'writable': action['writable'],
                    'reason': action['reason']} for action in attack['terminalActions']}}
            attacks[attack['role']] = value; order.append(attack['role'])
            for alias in attack['aliases']:
                attacks[alias] = value
        default = item['magazine']['defaultOption']
        weapons[name] = {'attacks': attacks, 'attack_order': order,
            'fire_mode': item['fireMode'],
            'magazine': {'simple_api': item['magazine']['simpleApi'],
                'default_option': default, 'observed_options': item['magazine']['observedOptions'],
                'attachment_categories': item['magazine'].get('attachmentCategories', [])}}
    return {'schema_version': 1, 'runtime_version': source['hd2RuntimeVersion'],
        'summary': source['summary'],
        'fields': {'attack': {'projectile': 'attack.projectile'},
            'terminal': {'explosion': 'terminal.explosion'},
            'explosion': {'inner_radius': 'explosion.inner_radius',
                'outer_radius': 'explosion.outer_radius',
                'shockwave_radius': 'explosion.shockwave_radius',
                'standard_damage': 'explosion.damage.standard_damage',
                'durable_damage': 'explosion.damage.durable_damage',
                'ap_direct': 'explosion.damage.ap_direct',
                'ap_slight': 'explosion.damage.ap_slight',
                'ap_large': 'explosion.damage.ap_large',
                'ap_extreme': 'explosion.damage.ap_extreme',
                'demolition': 'explosion.damage.demolition',
                'stagger': 'explosion.damage.stagger',
                'push_force': 'explosion.damage.push_force',
                'shrapnel_count': 'explosion.shrapnel_count',
                'shrapnel_projectile': 'explosion.shrapnel_projectile'}}, 'weapons': weapons}


def generate(check=False):
    body = '-- Generated from schemas/player_weapon_composition_catalog.json; do not edit.\nreturn ' + lua(build()) + '\n'
    if OUTPUT.exists() and OUTPUT.read_text() == body:
        return False
    if check:
        raise RuntimeError('Stale weapon composition output: ' + str(OUTPUT))
    OUTPUT.write_text(body)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(str(OUTPUT) if generate(args.check) else 'up to date')
