"""Canonical player-weapon catalog to compact matcher dataset transform."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re


def scalar(value):
    return value.get('value') if isinstance(value, dict) else None


def normalized(weapon):
    return weapon.get('normalizedFields') or {}


def weapon_stats(weapon):
    return weapon.get('weaponStats') or normalized(weapon).get('weaponStats') or {}


def weapon_stat(weapon, label, fallback):
    for section in weapon.get('rawSections') or []:
        if section.get('name') == 'Weapon':
            for field in section.get('fields') or []:
                if field.get('label') == label:
                    match = re.search(r'-?\d+(?:\.\d+)?', str(field.get('value', '')))
                    return float(match.group()) if match else fallback
    return fallback


def pellet_count(attack):
    projectile=attack.get('projectile') or {}
    direct=projectile.get('pelletCount')
    direct_value=scalar(direct)
    if isinstance(direct,(int,float)):direct_value=direct
    if isinstance(direct_value,(int,float)):return int(direct_value)
    raw = (attack.get('extraFields') or {}).get('Projectile.Pellets')
    match = re.search(r'\d+', str(raw)) if raw is not None else None
    return int(match.group()) if match else None


def spread_values(weapon):
    value=weapon_stats(weapon).get('spread')
    numbers=re.findall(r'-?\d+(?:\.\d+)?',str(value or''))
    return (float(numbers[0]),float(numbers[1])) if len(numbers)>=2 else (None,None)


def attack_record(attack,index):
    projectile=attack.get('projectile') or {};damage=attack.get('damage') or {}
    penetration=attack.get('penetration') or {};effects=attack.get('specialEffects') or {}
    extra=attack.get('extraFields') or attack.get('normalizedExtraFields') or {}
    explosion_branches=sorted({str(value) for key,value in extra.items()
        if 'Explosion' in key and value not in (None,'')})
    return {'index':index,'name':attack.get('name'),'kind':attack.get('kind'),
        'standard_damage':scalar(damage.get('standard')),'durable_damage':scalar(damage.get('durable')),
        'ap_direct':scalar(penetration.get('direct')),'ap_slight':scalar(penetration.get('slightAngle')),
        'ap_large':scalar(penetration.get('largeAngle')),'ap_extreme':scalar(penetration.get('extremeAngle')),
        'projectile_velocity':scalar(projectile.get('initialVelocityMetersPerSecond')),
        'projectile_mass':scalar(projectile.get('massGrams')),'drag':scalar(projectile.get('dragFactor')),
        'gravity':scalar(projectile.get('gravityFactor')),'demolition':scalar(effects.get('demolitionForce')),
        'stagger':scalar(effects.get('staggerForce')),'push_force':scalar(effects.get('pushForce')),
        'pellet_count':pellet_count(attack),'charge':attack.get('charge'),
        'parent_attack':attack.get('parentAttack'),'child_attacks':attack.get('childAttacks') or [],
        'projectile_data':attack.get('projectile'),'area_of_effect':attack.get('areaOfEffect'),
        'beam':attack.get('beam'),
        'projectile_branch':bool(attack.get('projectile')),
        'explosion_branches':explosion_branches,'extra_fields':extra}


def compact(source: Path, summary_path: Path | None = None, slot: str | None = None):
    source=Path(source);raw=source.read_bytes();root=json.loads(raw)
    weapons=[]
    for weapon in root['weapons']:
        weapon_slot=(weapon.get('slot') or 'primary').lower()
        if slot and weapon_slot != slot.lower():continue
        attacks=[attack_record(item,index) for index,item in enumerate(weapon.get('attacks') or [],1)]
        if not attacks:raise ValueError(f"{weapon.get('name')}: no attacks")
        normalized_fields=normalized(weapon);stats=weapon_stats(weapon)
        fire_rate=weapon_stat(weapon,'Fire Rate',scalar(stats.get('fireRateRpm')))
        capacity=weapon_stat(weapon,'Capacity',scalar(stats.get('capacity')))
        spread_horizontal,spread_vertical=spread_values(weapon)
        sway=scalar(stats.get('sway'));ergonomics=scalar(stats.get('ergonomics'))
        recoil=scalar(stats.get('recoil'));horizontal_recoil=scalar(stats.get('horizontalRecoil'))
        vertical_recoil=scalar(stats.get('verticalRecoil'))
        noise=str(stats.get('noise') or'')
        is_suppressed=noise.lower().startswith('suppressed') if noise else None
        primary=dict(attacks[0]);primary['fire_rate']=fire_rate;primary['capacity']=capacity
        weapons.append({'name':weapon['name'],'slot':weapon_slot,
            'category':weapon.get('category') or weapon.get('primaryCategory') or weapon.get('sourceSection'),
            'primary_category':weapon.get('primaryCategory'),
            'weapon_type':weapon.get('weaponType') or normalized_fields.get('weaponType'),
            'traits':weapon.get('traits') or normalized_fields.get('traits') or [],
            'source_section':weapon.get('sourceSection'),'relationships':weapon.get('relationships') or [],
            'backpack_dependent':normalized_fields.get('backpackDependent'),
            'expendable':normalized_fields.get('expendable'),
            'firing_modes':normalized_fields.get('firingModes') or [],
            'selectable_ammo_modes':normalized_fields.get('selectableAmmoModes') or [],
            'wiki_page':weapon.get('wikiPage'),
            'fire_rate':fire_rate,'capacity':capacity,'spread_horizontal':spread_horizontal,
            'spread_vertical':spread_vertical,'sway':sway,'ergonomics':ergonomics,
            'recoil':recoil,'horizontal_recoil':horizontal_recoil,
            'vertical_recoil':vertical_recoil,'is_suppressed':is_suppressed,
            'primary':primary,'attacks':attacks})
    names=[item['name'] for item in weapons]
    if len(set(names))!=len(names):raise ValueError('duplicate wiki weapon name')
    summary_raw=Path(summary_path).read_bytes() if summary_path else b''
    summary=json.loads(summary_raw) if summary_raw else {}
    if summary and not slot and len(weapons)!=summary['totalWeapons']:
        raise ValueError('wiki summary count differs')
    counts={name:sum(1 for weapon in weapons if weapon['slot']==name) for name in ('primary','secondary')}
    support_count=sum(1 for weapon in weapons if weapon['slot']=='support')
    if support_count:counts['support']=support_count
    return {'schema_version':2,'source':root.get('source'),'imported_at':root.get('importedAt'),
        'source_sha256':hashlib.sha256(raw).hexdigest().upper(),
        'summary_sha256':hashlib.sha256(summary_raw).hexdigest().upper() if summary_raw else'',
        'weapon_count':len(weapons),'slot_counts':counts,
        'multi_attack_weapon_count':sum(1 for weapon in weapons if len(weapon['attacks'])>1),
        'weapons':weapons}
