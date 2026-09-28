"""Shared fire_mode.* field construction for the player and support catalogs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
MODES_FIELD, BURST_FIELD = 'fire_mode.modes', 'fire_mode.burst_rounds'
MODES_OFFSET, MODES_WIDTH, BURST_OFFSET = 144, 16, 140
MODE_VALUES = {'automatic': 1, 'single': 2, 'burst': 3}
BURST_RANGE = (1, 10)
UNVERIFIED = ('The four native fire-mode slots, their enum values and the fire-mode selector are proven, but '
    'adding, removing or reordering modes on this weapon has not been gameplay-tested.')
EVIDENCE = {'nativeOwner': 'WeaponDataComponent primary..quaternary_fire_mode (+144, four FireMode slots)',
    'source': 'research/weapon-fire-modes-F5FEE03DCFDB.json', 'gameplayProven': False}


def load():
    research = json.loads(RESEARCH.read_text())
    return {(row['kind'], row['weapon']): row for row in research['weapons']}, research


def writable(row):
    return row['state'] in ('selectable', 'single_mode')


def apply_modes(field, row, identity_ok):
    """Complete a make_field result for fire_mode.modes."""
    ok = identity_ok and writable(row)
    field['currentDefault'] = list(row['modes']) if writable(row) else None
    field['nativeSlots'] = row.get('slots')
    field['allowedModes'] = sorted(MODE_VALUES, key=MODE_VALUES.get)
    field['modeValues'] = dict(MODE_VALUES)
    field['maxModes'] = row.get('maxModes')
    field['fireModeState'] = row['state']
    field['selector'] = {'left': row['selector']['left'], 'right': row['selector']['right']} if row.get('selector') else None
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else row.get('reason') or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['evidence'] = dict(EVIDENCE)
    if field.get('backing'):
        field['backing']['width'] = MODES_WIDTH
    return field


def apply_burst(field, row, identity_ok):
    ok = identity_ok and writable(row)
    field['currentDefault'] = row['burstRounds'] if writable(row) else None
    field['min'], field['max'] = BURST_RANGE
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else row.get('reason') or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['evidence'] = dict(EVIDENCE, nativeOwner='WeaponDataComponent.num_burst_rounds (+140)')
    return field
