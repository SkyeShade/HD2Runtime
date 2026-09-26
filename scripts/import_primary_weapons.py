"""Import the normalized wiki primary-weapon snapshot into compact Lua data.

This is a build-time transform. The diagnostic never parses the large source JSON
in game and never uses display names as runtime lookup keys.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re

from reference_format import lua

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / 'data/wiki_primary_weapons.json'
DEFAULT_SUMMARY = ROOT / 'data/wiki_primary_weapons.summary.json'
DEFAULT_OUTPUT = ROOT / 'primary_mapper/wiki_data.lua'


def scalar(value):
    return value.get('value') if isinstance(value, dict) else None


def primary_weapon_stat(weapon, label, fallback):
    """Prefer the top-level Weapon section, excluding underbarrel sections."""
    for section in weapon.get('rawSections') or []:
        if section.get('name') == 'Weapon':
            for field in section.get('fields') or []:
                if field.get('label') == label:
                    match = re.search(r'-?\d+(?:\.\d+)?', str(field.get('value', '')))
                    return float(match.group()) if match else fallback
    return fallback


def pellet_count(attack):
    raw = (attack.get('extraFields') or {}).get('Projectile.Pellets')
    match = re.search(r'\d+', str(raw)) if raw is not None else None
    return int(match.group()) if match else None


def attack_record(attack):
    projectile = attack.get('projectile') or {}
    damage = attack.get('damage') or {}
    penetration = attack.get('penetration') or {}
    effects = attack.get('specialEffects') or {}
    return {
        'name': attack.get('name'),
        'kind': attack.get('kind'),
        'standard_damage': scalar(damage.get('standard')),
        'durable_damage': scalar(damage.get('durable')),
        'ap_direct': scalar(penetration.get('direct')),
        'ap_slight': scalar(penetration.get('slightAngle')),
        'ap_large': scalar(penetration.get('largeAngle')),
        'ap_extreme': scalar(penetration.get('extremeAngle')),
        'projectile_velocity': scalar(projectile.get('initialVelocityMetersPerSecond')),
        'projectile_mass': scalar(projectile.get('massGrams')),
        'drag': scalar(projectile.get('dragFactor')),
        'gravity': scalar(projectile.get('gravityFactor')),
        'demolition': scalar(effects.get('demolitionForce')),
        'stagger': scalar(effects.get('staggerForce')),
        'push_force': scalar(effects.get('pushForce')),
        'pellet_count': pellet_count(attack),
    }


def compact(source: Path, summary_path: Path):
    raw = source.read_bytes()
    root = json.loads(raw)
    summary = json.loads(summary_path.read_bytes())
    weapons = []
    for weapon in root['weapons']:
        attacks = [attack_record(item) for item in weapon.get('attacks') or []]
        if not attacks:
            raise ValueError(f"{weapon.get('name')}: no attacks")
        stats = weapon.get('weaponStats') or {}
        primary = dict(attacks[0])
        primary['fire_rate'] = primary_weapon_stat(
            weapon, 'Fire Rate', scalar(stats.get('fireRateRpm')))
        primary['capacity'] = primary_weapon_stat(
            weapon, 'Capacity', scalar(stats.get('capacity')))
        weapons.append({
            'name': weapon['name'],
            'category': weapon.get('primaryCategory'),
            'wiki_page': weapon.get('wikiPage'),
            'primary': primary,
            'attacks': attacks,
        })
    if len(weapons) != summary['totalWeapons'] or len(weapons) != 55:
        raise ValueError('expected exactly 55 normalized primary weapons')
    names = [item['name'] for item in weapons]
    if len(set(names)) != len(names):
        raise ValueError('duplicate wiki weapon name')
    return {
        'schema_version': 1,
        'source': root.get('source'),
        'imported_at': root.get('importedAt'),
        'source_sha256': hashlib.sha256(raw).hexdigest().upper(),
        'summary_sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest().upper(),
        'weapon_count': len(weapons),
        'multi_attack_weapon_count': summary['multiAttackWeaponCount'],
        'weapons': weapons,
    }


def generate(source=DEFAULT_INPUT, summary=DEFAULT_SUMMARY, output=DEFAULT_OUTPUT, check=False):
    data = compact(Path(source), Path(summary))
    body = ('-- Generated from data/wiki_primary_weapons.json; do not edit.\n'
            'return ' + lua(data) + '\n')
    output = Path(output)
    if check:
        if not output.exists() or output.read_text(encoding='ascii') != body:
            raise ValueError(f'{output} is stale; run scripts/import_primary_weapons.py')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(body, encoding='ascii')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--summary', type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = generate(args.input, args.summary, args.output, args.check)
    print(f"{data['weapon_count']} weapons -> {args.output}")


if __name__ == '__main__':
    main()
