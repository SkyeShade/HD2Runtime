"""Shared weapon.third_person_reticle field construction for the player and support catalogs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-reticles-F5FEE03DCFDB.json'
FIELD = 'weapon.third_person_reticle'
OFFSET, STORAGE = 400, 'u32'
UNVERIFIED = ('The native crosshair policy and its bytes are proven, but this weapon\'s third-person reticle '
    'change has not been gameplay-tested (only APW-1 3 -> 4 is, by ReticleAmr).')


def load():
    research = json.loads(RESEARCH.read_text())
    return {(row['kind'], row['weapon']): row for row in research['weapons']}, research


def apply(field, row, research, writable):
    """Complete a make_field result for one weapon; returns the field (read-only unless mapped)."""
    state = row['reticle']
    mapped = state in ('shown', 'hidden')
    field['currentDefault'] = {'shown': True, 'hidden': False}.get(state)
    field['nativeValue'] = row['crosshairType']
    field['nativeName'] = row['crosshairTypeName']
    field['reticleState'] = state
    field['editable'] = field['acceptedForWrites'] = bool(writable and mapped)
    if not mapped:
        field['reason'] = row['reason']
    elif not writable:
        field['editable'] = field['acceptedForWrites'] = False
    if mapped:
        encoding = research['encoding']
        field['encoding'] = {'off': encoding['hidden'],
            'on': encoding['shownWhenBaselineHidden'] if state == 'hidden' else row['crosshairType']}
        proven = row['weapon'] == research['gameplayEvidence']['weapon'] and state == 'hidden'
        field['acknowledgement'] = None if proven else 'allow_unverified_effect'
        field['acknowledgementReason'] = None if proven else UNVERIFIED
    field['evidence'] = {'nativeOwner': 'WeaponDataComponent.crosshair_type (+400, CrosshairWeaponType)',
        'source': 'research/weapon-reticles-F5FEE03DCFDB.json',
        'gameplayProven': field.get('acknowledgement') is None and mapped,
        'gameplaySource': research['gameplayEvidence']['source'] if row['weapon'] == research['gameplayEvidence']['weapon'] else None}
    return field
