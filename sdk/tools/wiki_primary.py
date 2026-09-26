"""Legacy 55-primary compact transform retained for generated package compatibility."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

from .wiki_player import attack_record as player_attack_record
from .wiki_player import pellet_count, scalar, weapon_stat

primary_weapon_stat=weapon_stat
FIELDS=('name','kind','standard_damage','durable_damage','ap_direct','ap_slight','ap_large',
    'ap_extreme','projectile_velocity','projectile_mass','drag','gravity','demolition','stagger',
    'push_force','pellet_count')


def attack_record(attack):
    record=player_attack_record(attack,1)
    return {name:record[name] for name in FIELDS}


def compact(source: Path, summary_path: Path | None = None):
    source=Path(source);raw=source.read_bytes();root=json.loads(raw)
    weapons=[]
    for weapon in root['weapons']:
        attacks=[attack_record(item) for item in weapon.get('attacks') or []]
        if not attacks:raise ValueError(f"{weapon.get('name')}: no attacks")
        stats=weapon.get('weaponStats') or {};primary=dict(attacks[0])
        primary['fire_rate']=weapon_stat(weapon,'Fire Rate',scalar(stats.get('fireRateRpm')))
        primary['capacity']=weapon_stat(weapon,'Capacity',scalar(stats.get('capacity')))
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


__all__=['attack_record','compact','pellet_count','primary_weapon_stat','scalar','weapon_stat']
