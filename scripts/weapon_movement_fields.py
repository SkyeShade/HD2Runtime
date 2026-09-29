"""Shared helper for the weapon movement-restriction field (see scripts/research_weapon_movement.py).

`weapon.stationary_while_firing` is WeaponDataComponent +387. The Maxigun is the only weapon that sets it; game.dll
reads it while the wielder fires and, when set, sends the weapon's firing-start/stop wielder animation events and
raises wielder action bit 55. The effect of changing it has not been confirmed in game, so every write requires
allow_unverified_effect.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-movement-F5FEE03DCFDB.json'
FIELD = 'weapon.stationary_while_firing'
OFFSET = 387
STORAGE = 'u8'
UNVERIFIED = ('WeaponDataComponent +387: the Maxigun is the only weapon that sets it, and game.dll reads it while '
    'the wielder fires to send the firing-start/stop wielder animation events and raise wielder action bit 55. '
    'The in-game effect of changing it (on the Maxigun or any other weapon) is not yet confirmed.')


def load():
    """(kind, name) -> research row."""
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    return {(row['kind'], row['name']): row for row in research['weapons']}


def apply(field, row, resource):
    """Decorate a WeaponData component field; the research row's resource must be the field's owner."""
    if row['resource'].lower() != resource.lower():
        raise ValueError('movement research resolved a different weapon root: ' + row['name'])
    field['currentDefault'] = row['stationaryWhileFiring']
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['movement'] = {'firingStance': row['firingStance'], 'firingStartEvent': row['firingStartEvent'],
        'firingStopEvent': row['firingStopEvent'], 'perShotWielderAnimation': row['perShotWielderAnimation']}
    return field
