"""Shared fire_rate.* / weapon_function.* / function_ammo.* field construction for the player and support catalogs.

Source: research/weapon-functions-F5FEE03DCFDB.json (scripts/research_weapon_functions.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import fire_mode_fields
import live_evidence

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-functions-F5FEE03DCFDB.json'
RATES_FIELD = 'fire_rate.modes'
INPUT_FIELDS = {'left': 'weapon_function.left', 'right': 'weapon_function.right'}
FUNCTION_PROJECTILE_FIELD = 'function_ammo.projectile'
RATES_OFFSET, RATES_WIDTH = 4, 12
INPUT_OFFSETS = {'left': 184, 'right': 188}
FUNCTION_PROJECTILE_OFFSET = 576
# Native rates span 10 (LAS-99) to 1500 (M-1000); the reviewed range leaves headroom without letting a typo reach
# thousands of shots per second.
RATE_RANGE = (1, 3000)
# Slot names in storage and weapon-menu order, and the order the ROF selector visits them from the default (Y).
SLOT_NAMES = ('x', 'y', 'z')
SELECTOR_ORDER = ('y', 'z', 'x')
FUNCTION_VALUES = {'none': 0, 'zeroing': 1, 'rate_of_fire': 2, 'fire_mode': 3, 'magazine': 4, 'light_mode': 5,
    'laser_guide': 6, 'muzzle_velocity': 7, 'programmable_ammo': 8}
FUNCTION_NAMES = {value: name for name, value in FUNCTION_VALUES.items()}
RATES_UNVERIFIED = ('The three native rate-of-fire slots, the ROF selector traversal (Y -> Z -> X, skipping 0.0 '
    'slots) and the default slot are proven, but editing, adding or removing rates on this weapon has not been '
    'gameplay-tested.')
BINDING_UNVERIFIED = ('The weapon-function input binding (WeaponDataComponent function_info +184/+188) and the function '
    'readers are proven, but binding a selector this weapon does not have natively has not been gameplay-tested.')
FUNCTION_UNVERIFIED = ('The ProgrammableAmmo fire path (while the function is on, this projectile replaces the fired '
    'one) is proven, but giving this weapon a function projectile has not been gameplay-tested.')
BUILD_EFFECT = ('A component member the game copies into the weapon when it builds it (the projectile_weapon ROF record '
    'and the weapon_data bindings): weapons built after the write use it; a weapon already built keeps its copy until it '
    'is rebuilt (redeploy, reinforce, re-equip).')
FIRE_EFFECT = ('Read at every shot from the weapon resolved ProjectileWeapon data (a per-weapon copy when the weapon has '
    'one, otherwise the entity-table record): a new weapon uses it; an already built one may pick it up at once.')
EVIDENCE = {'source': 'research/weapon-functions-F5FEE03DCFDB.json', 'gameplayProven': False}
# A selector binding and what it selects span two weapon-local records (ProjectileWeapon, WeaponData) and are written in
# one transaction: plan and tool grouping treat the three fields as one operation group.
OPERATION_GROUP = 'weapon_selector'


_SELECTORS = None


def fire_mode_selectors():
    global _SELECTORS
    if _SELECTORS is None:
        _SELECTORS = fire_mode_fields.selector_rows()
    return _SELECTORS


def load():
    research = json.loads(RESEARCH.read_text())
    return {(row['kind'], row['weapon']): row for row in research['weapons']}, research


def rates_writable(row):
    rate = (row or {}).get('fireRate') or {}
    # A wind-up weapon's X and Z hold its rate natively (the Maxigun's 1500/1500/1500) with no selector bound: they are
    # written explicitly with the binding, or cleared; every other weapon with dormant slots stays read-only.
    return rate.get('state') in ('selectable', 'addable', 'single_rate') and (not rate.get('dormantSlots')
        or bool(rate.get('windUp')))


def function_writable(row):
    return ((row or {}).get('functionAmmo') or {}).get('state') in ('native', 'addable')


def effect(reason, applies='weapon_build', **extra):
    result = {'activeSource': 'ACTIVE_AT_INSTANTIATION', 'appliesWhen': applies, 'instantiationOnly': applies ==
        'weapon_build', 'activeSourceProven': True, 'reason': reason, 'writeVerifiedOnApply': True,
        'gameplayEffectProven': False, 'unverifiedEffect': True}
    result.update(extra)
    return result


def apply_rates(field, row, identity_ok):
    """Complete a make_field result for fire_rate.modes (ProjectileWeapon +4, three f32 slots)."""
    rate = row['fireRate']
    ok = identity_ok and rates_writable(row) and 'slots' in rate
    slots = [rate['slots'][key] for key in ('x', 'y', 'z')] if 'slots' in rate else None
    # The value is the three slots in the order the weapon menu lists them (X, Y, Z; 0 = empty); the selector visits
    # them from the default Y: Y -> Z -> X.
    field.update(currentDefault=list(slots) if slots else None, nativeSlots=slots, slotNames=list(SLOT_NAMES),
        defaultSlot='y', selectorOrder=list(SELECTOR_ORDER), maxModes=rate.get('maxModes') or 1,
        selectorBound=bool(rate.get('selectorBound')),
        selectorInput=rate.get('selectorInput'),
        bindableInputs=rate.get('bindableInputs') or [], fireRateState=rate['state'], min=RATE_RANGE[0],
        max=RATE_RANGE[1], overriddenWhenEquipped=rate.get('overriddenWhenEquipped') or [])
    field['editable'] = field['acceptedForWrites'] = ok
    reason = rate.get('reason')
    if rate.get('dormantSlots'):
        reason = 'Dormant rate slots (' + ', '.join(rate['dormantSlots']) + ') hold values a bound selector would visit.'
    field['reason'] = None if ok else reason or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = RATES_UNVERIFIED
    if rate.get('windUp'):
        # A wind-up weapon (WeaponWindUpComponentData): always behind the acknowledgement, with the unproven part named.
        field['windUp'] = True
        field['dormantSlots'] = list(rate.get('dormantSlots') or [])
        field['acknowledgementReason'] = rate['windUp']['reason']
    field['operationGroup'] = OPERATION_GROUP
    field['evidence'] = dict(EVIDENCE, nativeOwner='ProjectileWeaponComponent rounds_per_minute (three f32 slots)',
        selector='the ROF cycle and weapon-function value readers (research proofs)')
    if field.get('backing'):
        field['backing']['width'] = RATES_WIDTH
    equipped = field['overriddenWhenEquipped']
    field['effect'] = effect(BUILD_EFFECT) if not equipped else effect(
        'Equipping ' + ', '.join(equipped) + ' overwrites all three rate slots at weapon build; the rates apply while an '
        'option that does not patch them is equipped.', activeSource='AMBIGUOUS', activeSourceProven=False,
        overriddenWhenEquipped=equipped)
    return live_evidence.promote_field(field, row['weapon'])


def apply_input(field, row, side, identity_ok):
    """Complete a make_field result for weapon_function.left / weapon_function.right."""
    inputs = row.get('inputs') or {}
    value = inputs.get(side + 'Value')
    other = inputs.get(('right' if side == 'left' else 'left') + 'Value')
    name = FUNCTION_NAMES.get(value)
    allowed = [name] if name else []
    rate = row.get('fireRate') or {}
    function = row.get('functionAmmo') or {}
    if name == 'none':
        if rate.get('state') == 'addable' and side in (rate.get('bindableInputs') or []) and other != 2:
            allowed.append('rate_of_fire')
        if function.get('state') == 'addable' and side in (function.get('bindableInputs') or []) and other != 8:
            allowed.append('programmable_ammo')
        # The fire-mode selector (0.30.4): a single-mode weapon whose input is free (research/fire-mode-selector).
        fire, _ = fire_mode_selectors()
        selector = fire.get((row['kind'], row['weapon'])) or {}
        if selector.get('state') == 'addable' and side in (selector.get('bindableInputs') or []) and other != 3:
            allowed.append('fire_mode')
    ok = identity_ok and name == 'none' and len(allowed) > 1
    field.update(currentDefault=name or ('function_%s' % value), nativeValue=value, input=side, allowedValues=allowed,
        functionValues=dict(FUNCTION_VALUES))
    field['editable'] = field['acceptedForWrites'] = ok
    if not ok:
        field['reason'] = field.get('reason') or ('The input already binds ' + str(name or value) + '; native bindings '
            'are not replaced.' if name != 'none' else 'No selector this weapon can host is unbound: fire_rate, '
            'fire_mode and function_ammo are not addable here (see the weapon fire_rate_modes(), fire_modes() and '
            'feeds()).')
    else:
        field['reason'] = None
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = BINDING_UNVERIFIED
    if rate.get('windUp') and 'rate_of_fire' in allowed:
        field['acknowledgementReason'] = BINDING_UNVERIFIED + ' ' + rate['windUp']['reason']
    field['operationGroup'] = OPERATION_GROUP
    field['evidence'] = dict(EVIDENCE, nativeOwner='WeaponDataComponent function_info.' + side + ' (WeaponFunctionType)')
    field['effect'] = effect(BUILD_EFFECT)
    return live_evidence.promote_field(field, row['weapon'])


def apply_function_projectile(field, row, identity_ok):
    """Complete a make_field result for function_ammo.projectile (ProjectileWeapon +576)."""
    function = row.get('functionAmmo') or {}
    ok = identity_ok and function_writable(row)
    field.update(currentDefault={'projectileType': function.get('projectile') or 0}, referenceKind='projectile',
        referenceRole='function', referenceSettings=function.get('settings'),
        compatibilityClass=function.get('compatibilityClass'), selectorBound=bool(function.get('selectorBound')),
        selectorInput=function.get('selectorInput'), bindableInputs=function.get('bindableInputs') or [],
        functionAmmoState=function.get('state'), hostRounds='rounds_feed' in (row.get('families') or []))
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else function.get('reason') or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = FUNCTION_UNVERIFIED
    field['operationGroup'] = OPERATION_GROUP
    field['evidence'] = dict(EVIDENCE, nativeOwner='ProjectileWeaponComponent weapon_function_projectile_type',
        reader='the projectile fire path (research proofs)')
    field['effect'] = effect(FIRE_EFFECT, applies='weapon_build')
    return live_evidence.promote_field(field, row['weapon'])
