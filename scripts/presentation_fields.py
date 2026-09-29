"""Shared presentation.* field construction (armory trait labels) for the player and support catalogs.

Source: research/weapon-presentation-F5FEE03DCFDB.json (scripts/research_weapon_presentation.py).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-presentation-F5FEE03DCFDB.json'
TRAITS_FIELD, PENETRATION_FIELD = 'presentation.traits', 'presentation.armor_penetration'
COMPONENT, OFFSET, WIDTH = 'LoadoutEntryComponentData', 12, 20
UNVERIFIED = ('The five trait tags of the weapon loadout entry and the armory reader that localizes them are proven, '
    'but an edited label appearing in the menus has not been gameplay-tested. Menus build their labels when they open.')
EFFECT = {'activeSource': 'ACTIVE_DIRECT', 'appliesWhen': 'menu_build', 'instantiationOnly': False,
    'activeSourceProven': True, 'presentationOnly': True,
    'reason': 'Presentation only: read when a menu builds its item view (armory, loadout); an open menu keeps the '
        'labels it built. It never changes gameplay (damage and penetration are the projectile DamageInfo).',
    'writeVerifiedOnApply': True, 'gameplayEffectProven': False, 'unverifiedEffect': True}


def load():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    rows = {(row['kind'], row['weapon']): row for row in research['weapons']}
    traits = {item['semanticId']: int(item['nativeId'], 16) for item in research['traits'] if item['semanticId']}
    penetration = {key: int(value['nativeId'], 16) for key, value in research['penetrationLabels'].items()}
    return rows, research, traits, penetration


def backing(row, resource, storage):
    """The weapon's own LoadoutEntry record (unique owner) for the given entity resource, or None."""
    item = (row.get('backings') or {}).get('0x%016X' % int(resource, 16))
    if not item:
        return None
    return {'kind': 'component', 'component': COMPONENT, 'offset': OFFSET, 'storage': storage, 'width': WIDTH,
        'recordIndex': item['recordIndex'], 'indexRow': item['indexRow'], 'ownerCount': item['ownerCount'],
        'uniqueOwner': item['ownerCount'] == 1}


def semantic_tags(row, research):
    names = {int(item['nativeId'], 16): item['semanticId'] for item in research['traits']}
    tags = [int(tag, 16) for tag in row['tags']]
    return tags, [names.get(tag) for tag in tags if tag]


def apply_traits(field, row, research, traits, identity_ok):
    tags, current = semantic_tags(row, research)
    ok = identity_ok and row['state'] == 'writable' and all(current)
    field.update(currentDefault=current if all(current) else None, nativeTags=tags, traitValues=dict(traits),
        maxTraits=5, labels=[label for label in row['labels'] if label])
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else row.get('reason') or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['evidence'] = {'nativeOwner': 'LoadoutEntryComponent trait tags (five localization string IDs)',
        'reader': 'the armory trait builder (research proofs)', 'source': 'research/weapon-presentation-F5FEE03DCFDB.json',
        'gameplayProven': False}
    field['effect'] = dict(EFFECT)
    return field


def apply_penetration(field, row, research, penetration, identity_ok):
    tags, _ = semantic_tags(row, research)
    state = row.get('armorPenetrationState')
    ok = identity_ok and state in ('single', 'none')
    field.update(currentDefault=row.get('armorPenetration') or 'none', nativeTags=tags,
        penetrationValues=dict(penetration), penetrationSlot=row.get('armorPenetrationSlot'),
        allowedValues=['none'] + list(penetration), armorPenetrationState=state,
        labels={key: value['label'] for key, value in research['penetrationLabels'].items()})
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else row.get('armorPenetrationReason') or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['evidence'] = {'nativeOwner': 'LoadoutEntryComponent trait tags, the penetration-class tag',
        'reader': 'the armory trait builder (research proofs)', 'source': 'research/weapon-presentation-F5FEE03DCFDB.json',
        'gameplayProven': False, 'derivedFromGameplay': False}
    field['effect'] = dict(EFFECT)
    return field
