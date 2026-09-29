"""Generate the weapon-mode catalogs: rate-of-fire modes, feeds (selectable ammunition/output) and output composition.

Inputs (read-only research):
- research/weapon-functions-F5FEE03DCFDB.json: rate slots, input bindings, ProgrammableAmmo and rounds feeds;
- research/output-composition-F5FEE03DCFDB.json: cross-family composition verdicts and blockers;
- sdk/PlayerWeaponAuthoringCapabilities.json and sdk/SupportWeaponAuthoringCapabilities.json: which fields are writable
  for which weapon (identity, acknowledgements), so the catalogs never claim more than the write engine accepts.

Outputs:
- domains/weapon_modes.lua (runtime): per weapon its feeds, for weapon:feeds() / weapon:feed(id);
- sdk/WeaponFireRateCapabilities.json, sdk/WeaponFeedCapabilities.json, sdk/OutputCompositionCapabilities.json.
No native identifier or address is published.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weapon_mode_fields  # noqa: E402
from generate_fire_mode_authoring import lua  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / 'research/output-composition-F5FEE03DCFDB.json'
PLAYER = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SUPPORT = ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json'
OUTPUTS = ROOT / 'sdk/AttackOutputCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/weapon_modes.lua'
RATES_OUTPUT = ROOT / 'sdk/WeaponFireRateCapabilities.json'
FEEDS_OUTPUT = ROOT / 'sdk/WeaponFeedCapabilities.json'
COMPOSITION_OUTPUT = ROOT / 'sdk/OutputCompositionCapabilities.json'
VERSION = (ROOT / 'VERSION').read_text().strip()
RATE_STATES = {'selectable': 'The rate-of-fire selector is bound: every rate can be edited, added (up to three) or removed.',
    'addable': 'No selector is bound but an input is free: rates beyond the default are written together with a '
        'weapon_function binding of "rate_of_fire" (one transaction).',
    'single_rate': 'Both inputs are bound: only the default rate (one entry) can be edited.',
    'blocked': 'Read-only; see reason.', 'absent': 'The weapon has no rate-of-fire slots.'}
FEED_MECHANISMS = {'projectile': 'The weapon normal projectile (see attack:projectile_source() for where it lives).',
    'rounds_magazine': 'One of the two WeaponRounds magazines (primary +64, alternate +68), switched with the Magazine '
        'weapon function. Both are built into every weapon; their projectiles are set by its default ammunition '
        'customization.',
    'programmable_ammo': 'ProjectileWeapon +576: fired instead of the normal projectile while the ProgrammableAmmo weapon '
        'function is on (AC-8, GR-8, RL-77 natively).'}


def writable_fields():
    """(kind, weapon) -> {field id: field descriptor} for the writable instances of the new fields."""
    wanted = {weapon_mode_fields.RATES_FIELD, weapon_mode_fields.FUNCTION_PROJECTILE_FIELD,
        *weapon_mode_fields.INPUT_FIELDS.values()}
    out = {}
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        for field in weapon['fields']:
            if field['semanticFieldId'] in wanted:
                out.setdefault(('player', weapon['name']), {})[field['semanticFieldId']] = field
    support = json.loads(SUPPORT.read_text())
    for weapon in support['weapons']:
        for blocked in weapon['blockedFields']:
            if blocked['field'] in wanted:
                out.setdefault(('support', weapon['name']), {})[blocked['field']] = {'editable': False,
                    'reason': blocked['reason']}
    for instance in support['fieldInstances']:
        if instance['semanticFieldId'] in wanted:
            out.setdefault(('support', instance['supportWeapon']), {})[instance['semanticFieldId']] = {
                'editable': instance['writable'], 'reason': instance['blockedReason'], **(instance.get('fireRate') or {}),
                **(instance.get('functionAmmo') or {}), **(instance.get('weaponFunction') or {}),
                'currentDefault': instance['value']['baseline']}
    return out


def feed_list(kind, row, fields):
    """The weapon's feeds in native order: its normal projectile or two rounds magazines, then a programmable feed."""
    feeds = []
    rounds = row.get('feeds')
    function = row.get('functionAmmo') or {}
    attack_role = 'primary'
    if rounds and rounds['alternate']['projectile']:
        for index, feed in enumerate(('primary', 'alternate'), 1):
            item = rounds[feed]
            feeds.append({'id': feed, 'index': index, 'mechanism': 'rounds_magazine', 'native': True,
                'selector': {'function': 'magazine', 'input': rounds['selectorInput'], 'bound': rounds['selectorBound']},
                'attackRole': 'feed_' + feed if kind == 'player' else None, 'capacity': item['capacity'],
                'capacityField': 'rounds.feed_capacity_' + str(index), 'ownedBy': item['ownedBy'],
                'projectileSource': {'status': 'OVERRIDDEN' if item['ownedBy'] else 'ACTIVE_AT_INSTANTIATION',
                    'writable': False, 'reason': ('The feed projectile is patched at every build by the default '
                        'customization ' + item['ownedBy'] + ' (WeaponRounds +' + ('64' if feed == 'primary' else '68')
                        + '); rounds-feed projectile swaps are not authored yet. Edit the feed projectile itself through '
                        'feed:projectile().') if item['ownedBy'] else 'Rounds-feed projectile swaps are not authored yet.'}})
        attack_role = None
    elif (row.get('fireRate') or {}).get('state') != 'absent' or function.get('state') not in (None, 'absent'):
        feeds.append({'id': 'primary', 'index': 1, 'mechanism': 'projectile', 'native': True, 'selector': None,
            'attackRole': attack_role, 'projectileSource': {'status': 'see attack:projectile_source()', 'writable': None}})
    if function.get('state') in ('native', 'addable', 'native_blocked'):
        field = fields.get(weapon_mode_fields.FUNCTION_PROJECTILE_FIELD) or {}
        native = function['state'] != 'addable'
        feeds.append({'id': 'programmable', 'index': len(feeds) + 1, 'mechanism': 'programmable_ammo', 'native': native,
            'state': function['state'], 'selector': {'function': 'programmable_ammo', 'input': function.get('selectorInput'),
                'bound': bool(function.get('selectorBound')), 'bindableInputs': function.get('bindableInputs') or []},
            'field': weapon_mode_fields.FUNCTION_PROJECTILE_FIELD, 'writable': bool(field.get('editable')),
            'reason': None if field.get('editable') else function.get('reason') or field.get('reason'),
            'nativeProjectile': bool(function.get('projectile')), 'compatibilityClass': function.get('compatibilityClass'),
            'acknowledgements': ['allow_unverified_effect', 'allow_unverified_reference'],
            'requiresBinding': not function.get('selectorBound')})
    return feeds


def build():
    rows, research = weapon_mode_fields.load()
    composition = json.loads(COMPOSITION.read_text())
    fields_by_weapon = writable_fields()
    runtime, rates_public, feeds_public = {}, [], []
    for (kind, name), row in sorted(rows.items()):
        fields = fields_by_weapon.get((kind, name), {})
        rate = row.get('fireRate') or {}
        rate_field = fields.get(weapon_mode_fields.RATES_FIELD) or {}
        writable = bool(rate_field.get('editable'))
        slots = rate.get('slots')
        rates_public.append({'kind': kind, 'weapon': name, 'state': rate.get('state') if writable or rate.get('state') in
                ('blocked', 'absent') else 'blocked', 'modes': rate.get('modes'), 'defaultRpm': rate.get('defaultRpm'),
            'slots': slots, 'slotOrder': ['y', 'z', 'x'], 'maxModes': rate.get('maxModes') if writable else None,
            'selector': {'bound': rate.get('selectorBound'), 'input': rate.get('selectorInput'),
                'bindableInputs': rate.get('bindableInputs') or []} if slots else None,
            'overriddenWhenEquipped': rate.get('overriddenWhenEquipped') or [],
            'writable': writable, 'reason': None if writable else rate.get('reason') or rate_field.get('reason'),
            'fields': {'modes': weapon_mode_fields.RATES_FIELD, 'default': 'weapon.fire_rate',
                'binding': [weapon_mode_fields.INPUT_FIELDS[side] for side in rate.get('bindableInputs') or []]}
                if writable else None,
            'acknowledgements': ['allow_unverified_effect'] if writable else None})
        feeds = feed_list(kind, row, fields)
        if feeds:
            feeds_public.append({'kind': kind, 'weapon': name, 'feeds': feeds, 'selectableNatively': any(f['native']
                and f['mechanism'] != 'projectile' and (f['selector'] or {}).get('bound') for f in feeds),
                'inputs': {side: (row.get('inputs') or {}).get(side) for side in ('left', 'right')}})
        runtime[kind + ':' + name] = {'feeds': feeds, 'fireRateState': rates_public[-1]['state']}
    rates_summary = {'weapons': len(rates_public), 'byState': dict(sorted(Counter('%s:%s' % (w['kind'], w['state'])
        for w in rates_public).items())), 'writable': sum(1 for w in rates_public if w['writable']),
        'nativeSelectors': sorted(w['weapon'] for w in rates_public if (w['selector'] or {}).get('bound')),
        'addableSelectors': sum(1 for w in rates_public if w['state'] == 'addable')}
    rates = {'contract': 'hd2runtime.weapon.fire_rates.v1', 'schemaVersion': 1, 'hd2RuntimeVersion': VERSION,
        'nativeModel': research['model']['rateOfFire'], 'states': RATE_STATES,
        'maxSlots': 3, 'slotNames': ['x', 'y', 'z'], 'defaultSlot': 'y', 'selectorOrder': ['y', 'z', 'x'],
        'range': list(weapon_mode_fields.RATE_RANGE), 'unit': 'rounds per minute',
        'fields': {'modes': {'constant': 'hd2.fields.fire_rate.modes', 'type': 'ordered list of rates (rpm)',
                'default': 'the first entry (native slot Y; also weapon.fire_rate)', 'maxEntries': 3,
                'acknowledgement': 'allow_unverified_effect'},
            'binding': {'constants': ['hd2.fields.weapon_function.left', 'hd2.fields.weapon_function.right'],
                'value': 'rate_of_fire', 'rule': 'bound in the same transaction as fire_rate.modes with 2+ rates'}},
        'compatibility': {'weapon.fire_rate': 'unchanged: the default (Y) rate; it covers the same bytes, so it cannot '
            'be combined with fire_rate.modes in one plan'},
        'shareScope': 'weapon_local: every ProjectileWeaponComponentData and WeaponDataComponentData record has one owner.',
        'addingModes': 'Three slots is the native storage; a fourth rate cannot exist. A zero slot is an absent mode that '
            'the selector skips, so adding a mode fills an empty slot of the weapon own record: no array grows, no '
            'record is reallocated and no neighbouring data is touched.',
        'weapons': rates_public, 'summary': rates_summary}
    feeds_summary = {'weaponsWithFeeds': len(feeds_public),
        'nativeMultipleOutputs': sorted(w['weapon'] for w in feeds_public if w['selectableNatively']),
        'programmableAddable': sorted(w['weapon'] for w in feeds_public for f in w['feeds']
            if f['mechanism'] == 'programmable_ammo' and f['state'] == 'addable' and f['writable']),
        'programmableNativeWritable': sorted(w['weapon'] for w in feeds_public for f in w['feeds']
            if f['mechanism'] == 'programmable_ammo' and f['state'] == 'native' and f['writable']),
        'roundsDualFeeds': sorted(w['weapon'] for w in feeds_public for f in w['feeds']
            if f['mechanism'] == 'rounds_magazine' and f['id'] == 'alternate' and f['selector']['bound']),
        'roundsAlternateWithoutSelector': sorted(w['weapon'] for w in feeds_public for f in w['feeds']
            if f['mechanism'] == 'rounds_magazine' and f['id'] == 'alternate' and not f['selector']['bound'])}
    feeds = {'contract': 'hd2runtime.weapon.feeds.v1', 'schemaVersion': 1, 'hd2RuntimeVersion': VERSION,
        'mechanisms': FEED_MECHANISMS,
        'notConflated': {'fire_mode': 'Fire modes (Automatic/Single/Burst) never select projectiles.',
            'multiple_projectiles': 'Pellets per shot are projectile.pellet_count on the projectile row.',
            'submunitions': 'Shrapnel and bomblets hang off the projectile impact explosion (explosion.shrapnel_*).',
            'default_ammunition': 'weapon:ammunition() is the customization that owns the normal projectile of six weapons.',
            'output_family': 'Beam, arc, spray and melee outputs are their own components (OutputCompositionCapabilities).'},
        'fields': {'projectile': {'constant': 'hd2.fields.function_ammo.projectile',
                'values': '"none", weapon:feed(id):projectile() (restore) or hd2.attack_output(name) (a projectile output)',
                'acknowledgements': ['allow_unverified_effect', 'allow_unverified_reference']},
            'binding': {'constants': ['hd2.fields.weapon_function.left', 'hd2.fields.weapon_function.right'],
                'value': 'programmable_ammo', 'rule': 'bound in the same transaction as function_ammo.projectile'},
            'capacity': 'rounds.feed_capacity_1 / rounds.feed_capacity_2 (rounds magazines)'},
        'assets': 'A donor output package loads automatically before function_ammo.projectile is written (0.27 loader).',
        'weapons': feeds_public, 'summary': feeds_summary}
    output_ids = {o['owner']['name']: o['semanticId'] for o in json.loads(OUTPUTS.read_text())['outputs']}
    verdicts = [dict(v, outputId=v['outputId'] or output_ids.get(v['donor'])) for v in composition['verdicts']]
    composition_public = {'contract': 'hd2runtime.output_composition.v1', 'schemaVersion': 1, 'hd2RuntimeVersion': VERSION,
        'question': 'Can a projectile weapon fire another family output (a beam) while keeping its own weapon?',
        'routes': {'reference_swap': 'A ProjectileType reference cannot name a BeamType (AttackOutputCapabilities).',
            'component_composition': 'Clone or attach the donor output component to the host entity.',
            'event_action': 'Suppress the host output on firing and emit the donor output from an event action.'},
        'blockers': composition['blockers'], 'verdicts': verdicts,
        'beamLifecycle': composition['beamLifecycle'],
        'ownership': {'beamEntities': composition['ownership']['beamEntities'],
            'beamWithHeat': composition['ownership']['beamWithHeat'],
            'magazineFedBeams': [p['weapon'] for p in composition['ownership']['magazineFedBeams']]},
        'membership': {'entityLists': composition['membership']['entities'],
            'packedWithZeroSlack': composition['membership']['zeroGapLists'] + 1},
        'nativeMultipleOutputs': composition['nativeMultipleOutputs'],
        'beamAction': {'available': False, 'reason': next(b['detail'] for b in composition['blockers']
            if b['id'] == 'BEAM_IS_ENTITY_STATE')},
        'summary': composition['summary']}
    return {'feeds': runtime}, rates, feeds, composition_public


def public_text(value):
    """Code addresses stay in the research files; the public catalog carries the explanation only."""
    if isinstance(value, dict):
        return {key: public_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_text(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r' ?\((?:0x[0-9A-Fa-f]+(?:, [^)]*)?)\)', '', value)
        return re.sub(r'\b0x[0-9A-Fa-f]+\b', 'game code', value)
    return value


def outputs():
    runtime, rates, feeds, composition = build()
    composition = public_text(composition)
    return {LUA_OUTPUT: '-- Generated by scripts/generate_weapon_modes.py; do not edit.\nreturn ' + lua(runtime) + '\n',
        RATES_OUTPUT: json.dumps(rates, indent=2) + '\n', FEEDS_OUTPUT: json.dumps(feeds, indent=2) + '\n',
        COMPOSITION_OUTPUT: json.dumps(composition, indent=2) + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text() != body:
            stale.append(path)
            if not check:
                path.write_text(body, newline='\n')
    if check and stale:
        raise RuntimeError('Stale weapon-mode outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
