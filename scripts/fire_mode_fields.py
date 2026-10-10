"""Shared fire_mode.* field construction for the player and support catalogs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
# The fire-mode selector (0.30.4, scripts/research_fire_mode_selector.py): the press cycles only +144..+152 (three modes
# at most), and a weapon with one mode and a free input can take the Firemode binding ('addable').
SELECTOR = ROOT / 'research/fire-mode-selector-F5FEE03DCFDB.json'
SELECTOR_MAX_MODES = 3
BINDING_VALUE = 'fire_mode'
BINDING_RULE = ('A weapon without a fire-mode selector lists two or three modes only in the same transaction as its '
    'Firemode binding (hd2.fields.weapon_function.left or .right = "fire_mode" on an unbound input), and the binding '
    'only together with two or more modes (SELECTOR_REQUIRED otherwise).')
MODES_FIELD, BURST_FIELD = 'fire_mode.modes', 'fire_mode.burst_rounds'
MODES_OFFSET, MODES_WIDTH, BURST_OFFSET = 144, 16, 140
MODE_VALUES = {'automatic': 1, 'single': 2, 'burst': 3}
BURST_RANGE = (1, 10)
UNVERIFIED = ('The native fire-mode slots, their enum values and the fire-mode selector (three modes at most) are proven, '
    'but adding, removing or reordering modes on this weapon has not been gameplay-tested.')
EVIDENCE = {'nativeOwner': 'WeaponDataComponent primary..quaternary_fire_mode (+144, four FireMode slots)',
    'source': 'research/weapon-fire-modes-F5FEE03DCFDB.json', 'gameplayProven': False}


def selector_rows():
    research = json.loads(SELECTOR.read_text())
    return {(row['kind'], row['weapon']): row for row in research['weapons']}, research


def load():
    """The fire-mode research rows with the selector research applied: a selectable weapon reaches three modes, and a
    single-mode weapon with a free input is 'addable' (its bindable inputs listed)."""
    research = json.loads(RESEARCH.read_text())
    selectors, selector = selector_rows()
    rows = {}
    for row in research['weapons']:
        row = dict(row)
        found = selectors.get((row['kind'], row['weapon']))
        if found and row['state'] in ('selectable', 'single_mode'):
            row.update(state=found['state'], maxModes=found['maxModes'], bindableInputs=found['bindableInputs'])
        rows[(row['kind'], row['weapon'])] = row
    model = dict(research['model'], selector=selector['model']['selector'], maxModes=selector['model']['maxModes'],
        binding=selector['model']['binding'])
    return rows, dict(research, model=model)


def writable(row):
    return row['state'] in ('selectable', 'single_mode', 'addable')


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
    field['selectorBound'] = row['state'] == 'selectable'
    field['bindableInputs'] = list(row.get('bindableInputs') or [])
    if row['state'] == 'addable':
        field['binding'] = {'fields': ['weapon_function.' + side for side in field['bindableInputs']],
            'value': BINDING_VALUE, 'rule': BINDING_RULE}
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
