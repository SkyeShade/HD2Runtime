"""Generate the armory presentation catalog (trait labels) from research/weapon-presentation-F5FEE03DCFDB.json.

Outputs:
- domains/weapon_presentation.lua (runtime): the trait catalog (semantic ID -> label) and the penetration labels, for
  weapon:presentation();
- sdk/WeaponPresentationCapabilities.json (public): every named trait, the penetration display choices, and per weapon
  its current traits, whether they are writable and why not. Trait IDs are published as semantic IDs with their
  en-US label; native string IDs stay internal.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import presentation_fields  # noqa: E402
from generate_fire_mode_authoring import lua  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SUPPORT = ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/weapon_presentation.lua'
JSON_OUTPUT = ROOT / 'sdk/WeaponPresentationCapabilities.json'
PENETRATION_ORDER = ['light', 'medium', 'heavy', 'light_anti_tank', 'anti_tank']


def writable():
    out = {}
    wanted = {presentation_fields.TRAITS_FIELD, presentation_fields.PENETRATION_FIELD}
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        for field in weapon['fields']:
            if field['semanticFieldId'] in wanted:
                out[('player', weapon['name'], field['semanticFieldId'])] = (field['editable'], field.get('reason'))
    for instance in json.loads(SUPPORT.read_text())['fieldInstances']:
        if instance['semanticFieldId'] in wanted:
            out[('support', instance['supportWeapon'], instance['semanticFieldId'])] = (instance['writable'],
                instance['blockedReason'])
    for weapon in json.loads(SUPPORT.read_text())['weapons']:
        for blocked in weapon['blockedFields']:
            if blocked['field'] in wanted:
                out.setdefault(('support', weapon['name'], blocked['field']), (False, blocked['reason']))
    return out


def build():
    rows, research, traits, penetration = presentation_fields.load()
    by_native = {item['nativeId']: item for item in research['traits']}
    edit = writable()
    catalog = [{'semanticId': item['semanticId'], 'label': item['label'], 'labelEnGb': item['labelEnGb'],
        'languages': item['languages'], 'weapons': item['itemCount']} for item in research['traits'] if item['semanticId']]
    unnamed = sum(1 for item in research['traits'] if not item['semanticId'])
    weapons = []
    for (kind, name), row in sorted(rows.items()):
        if row['state'] == 'absent':
            weapons.append({'kind': kind, 'weapon': name, 'traits': None, 'writable': False, 'reason': row['reason']})
            continue
        current = [by_native[tag]['semanticId'] if tag in by_native else None for tag in row['tags'] if tag != '00000000']
        traits_ok, traits_reason = edit.get((kind, name, presentation_fields.TRAITS_FIELD), (False, row.get('reason')))
        pen_ok, pen_reason = edit.get((kind, name, presentation_fields.PENETRATION_FIELD),
            (False, row.get('armorPenetrationReason')))
        weapons.append({'kind': kind, 'weapon': name, 'traits': current,
            'labels': [label for label in row['labels'] if label],
            'armorPenetration': row.get('armorPenetration') or ('none' if row.get('armorPenetrationState') in
                ('single', 'none') else None),
            'writable': {'traits': traits_ok, 'armorPenetration': pen_ok},
            'reason': {'traits': None if traits_ok else traits_reason, 'armorPenetration': None if pen_ok else
                pen_reason or row.get('armorPenetrationReason')}})
    labels = research['penetrationLabels']
    summary = {'weapons': len(weapons), 'traitsWritable': sum(1 for w in weapons if (w['writable'] or {}).get('traits')
        if isinstance(w['writable'], dict)), 'armorPenetrationWritable': sum(1 for w in weapons
        if isinstance(w['writable'], dict) and w['writable']['armorPenetration']), 'namedTraits': len(catalog),
        'unnamedTraits': unnamed, 'byPenetration': dict(sorted(Counter(str(w.get('armorPenetration'))
            for w in weapons).items()))}
    public = {'contract': 'hd2runtime.weapon.presentation.v1', 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'nativeModel': research['model'],
        'fields': {'traits': {'constant': 'hd2.fields.presentation.traits', 'type': 'ordered list of trait semantic IDs '
                '(at most five, shown in order)', 'acknowledgement': 'allow_unverified_effect'},
            'armorPenetration': {'constant': 'hd2.fields.presentation.armor_penetration',
                'choices': ['none'] + PENETRATION_ORDER, 'acknowledgement': 'allow_unverified_effect',
                'rule': 'replaces the single penetration label in place, adds one in the first empty slot, or removes '
                    'it (none); the other traits never change'}},
        'penetrationChoices': [{'value': 'none', 'label': None}] + [{'value': key, 'label': labels[key]['label']}
            for key in PENETRATION_ORDER],
        'gameplaySeparation': 'Presentation only. Gameplay penetration is damage.ap_* on the projectile (and explosion) '
            'DamageInfo; no native rule derives one from the other, so Runtime never changes a label when AP changes.',
        'refresh': 'Menus build their trait labels when they open; reopen the armory or loadout screen after a change.',
        'stats': 'The stat rows (damage, capacity, recoil, fire rate, ...) are computed from gameplay data when a menu '
            'builds the item: there is no stored display value to edit.',
        'traits': catalog, 'weapons': weapons, 'summary': summary}
    runtime = {'traits': {item['semanticId']: item['label'] for item in catalog},
        'penetration': {key: labels[key]['label'] for key in PENETRATION_ORDER}}
    return runtime, public


def outputs():
    runtime, public = build()
    return {LUA_OUTPUT: '-- Generated by scripts/generate_weapon_presentation.py; do not edit.\nreturn ' + lua(runtime)
        + '\n', JSON_OUTPUT: json.dumps(public, indent=2, ensure_ascii=False) + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n', encoding='utf-8')
    if check and stale:
        raise RuntimeError('Stale presentation outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
