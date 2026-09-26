"""Canonical normalized-wiki to compact matcher dataset transform."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re


def scalar(value):
    return value.get('value') if isinstance(value, dict) else None


def primary_weapon_stat(weapon, label, fallback):
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
    projectile=attack.get('projectile') or {};damage=attack.get('damage') or {}
    penetration=attack.get('penetration') or {};effects=attack.get('specialEffects') or {}
    return {'name':attack.get('name'),'kind':attack.get('kind'),
        'standard_damage':scalar(damage.get('standard')),'durable_damage':scalar(damage.get('durable')),
        'ap_direct':scalar(penetration.get('direct')),'ap_slight':scalar(penetration.get('slightAngle')),
        'ap_large':scalar(penetration.get('largeAngle')),'ap_extreme':scalar(penetration.get('extremeAngle')),
        'projectile_velocity':scalar(projectile.get('initialVelocityMetersPerSecond')),
        'projectile_mass':scalar(projectile.get('massGrams')),'drag':scalar(projectile.get('dragFactor')),
        'gravity':scalar(projectile.get('gravityFactor')),'demolition':scalar(effects.get('demolitionForce')),
        'stagger':scalar(effects.get('staggerForce')),'push_force':scalar(effects.get('pushForce')),
        'pellet_count':pellet_count(attack)}


def compact(source: Path, summary_path: Path | None = None):
    source=Path(source);raw=source.read_bytes();root=json.loads(raw)
    weapons=[]
    for weapon in root['weapons']:
        attacks=[attack_record(item) for item in weapon.get('attacks') or []]
        if not attacks:raise ValueError(f"{weapon.get('name')}: no attacks")
        stats=weapon.get('weaponStats') or {};primary=dict(attacks[0])
        primary['fire_rate']=primary_weapon_stat(weapon,'Fire Rate',scalar(stats.get('fireRateRpm')))
        primary['capacity']=primary_weapon_stat(weapon,'Capacity',scalar(stats.get('capacity')))
        weapons.append({'name':weapon['name'],'category':weapon.get('primaryCategory'),
            'wiki_page':weapon.get('wikiPage'),'primary':primary,'attacks':attacks})
    names=[item['name'] for item in weapons]
    if len(set(names))!=len(names):raise ValueError('duplicate wiki weapon name')
    summary_raw=Path(summary_path).read_bytes() if summary_path else b''
    summary=json.loads(summary_raw) if summary_raw else {}
    if summary and len(weapons)!=summary['totalWeapons']:raise ValueError('wiki summary count differs')
    return {'schema_version':1,'source':root.get('source'),'imported_at':root.get('importedAt'),
        'source_sha256':hashlib.sha256(raw).hexdigest().upper(),
        'summary_sha256':hashlib.sha256(summary_raw).hexdigest().upper() if summary_raw else'',
        'weapon_count':len(weapons),'multi_attack_weapon_count':summary.get('multiAttackWeaponCount'),
        'weapons':weapons}
