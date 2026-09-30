"""Shared weapon-side fields proven by research/equipment-coverage-F5FEE03DCFDB.json.

* LAS-17 Double-Edge Sickle heat levels (WeaponHeatComponent HeatLevelSetting[3], stride 24): the heat at which each
  level applies (+0), the status the level applies to the wielder (+20), and the lock-at-maximum-heat flag (+80).
  Self-damage and self-ignition are data-driven: level N applies status hotshot_laser_rifle(_2/_3) to the wielder;
  those statuses' tick DamageInfo rows (542/543/544) are referenced by nothing else, and 544 carries Fire in its
  status slot 1: that is the self-ignition.
* Beam fire rate (BeamWeaponComponent +104, INT32 rpm): exact published "Beam Fire Rate" on seven weapons.
* Maxigun recoil multipliers (WeaponDataComponent +60/+64, the first pair of the typed struct RecoilModifiers).

None of these is shown in game yet: every write requires allow_unverified_effect.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json'
DOUBLE_EDGE = 'LAS-17 Double-Edge Sickle'
HEAT_LEVEL_STATUSES = ['hotshot_laser_rifle', 'hotshot_laser_rifle_2', 'hotshot_laser_rifle_3']
BEAM_RATE_WEAPONS = ('LAS-98 Laser Cannon',)
RECOIL_MULTIPLIER_WEAPONS = ('M-1000 Maxigun',)

LEVEL_REASON = ('LAS-17 heat level {n}: from this heat the weapon fires its level-{n} projectile and applies '
    '{status} to the wielder (tick {damage} damage{fire}). Typed HeatLevelSetting member; the published '
    'LAS-17 heat bands match. Not yet shown in game.')
STATUS_REASON = ('The status heat level {n} applies to the wielder while firing: one of the three LAS-17 self-damage '
    'statuses (hotshot_laser_rifle: tick 20, _2: tick 40, _3: tick 100 plus Fire, the self-ignition), or "none" for '
    'no self-damage at this level. Not yet shown in game.')
LOCK_REASON = ('LAS-17 lock-at-maximum-heat flag (WeaponHeat +80): 0 only on the LAS-17 (whose overheating '
    'protections are removed and which never needs a heatsink change at maximum heat) among every weapon; 1 on '
    'every other heat weapon. Not yet shown in game.')
BEAM_RATE_REASON = ('Beam fire rate: exact published "Beam Fire Rate" on seven weapons (LAS-98 60, LAS-13 300, '
    '40-K 50 rpm, ...) at the typed BeamWeaponComponent member; how often the beam applies its damage. Not yet '
    'shown in game.')
RECOIL_REASON = ('First pair of the typed RecoilModifiers struct (WeaponData +60/+64): 1.0 on 364 of 366 weapon '
    'records and never changed by an attachment. Maxigun Reimagined (a research lead) edits the same members as '
    'recoil multipliers; not yet shown in game.')


def research():
    return json.loads(RESEARCH.read_text(encoding='utf-8'))


def effect(active='ACTIVE_AT_INSTANTIATION', reason=None):
    return {'activeSource': active, 'appliesWhen': 'weapon_build', 'instantiationOnly': True,
        'activeSourceProven': False, 'reason': reason or ('The member is copied into the weapon when it is built; '
            'no attachment option patches it. Whether the game reads it for this behaviour is not yet shown in game.')}


def double_edge_fields(make, backend):
    """LAS-17 heat-level fields. `make(field_id, value, backend)` builds a field; `backend(offset, storage)` a
    WeaponHeatComponent backing on the weapon's own record."""
    data = research()['heat']['doubleEdge']
    fields = []
    for level in data['levels']:
        n = level['index']
        fire = ' and Fire' if level['tickDamageStatuses'] else ''
        threshold = make(f'heat.level_{n}_threshold', level['threshold'], backend(level['thresholdOffset'], 'f32'))
        threshold.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': LEVEL_REASON.format(
            n=n, status=level['status'], damage=level['tickDamage']['standardDamage'], fire=fire),
            'min': 0, 'max': 10000, 'heatLevel': {'index': n, 'projectileType': level['projectileType'],
                'status': level['status'], 'tickDamage': level['tickDamage']}})
        status = make(f'heat.level_{n}_self_status', level['status'], backend(level['statusOffset'], 'u32'))
        status.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': STATUS_REASON.format(n=n),
            'allowedValues': list(HEAT_LEVEL_STATUSES), 'allowNone': True,
            'statusScope': 'wielder', 'heatLevel': {'index': n}})
        fields += [threshold, status]
    lock = data['overheatLock']
    flag = make('heat.overheat_lock', bool(lock['value']), backend(lock['offset'], 'u8'))
    flag.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': LOCK_REASON})
    fields.append(flag)
    for field in fields:
        field['effect'] = effect()
    return fields


def beam_rate(weapon):
    for row in research()['beamFireRate']['correlations']:
        if row['weapon'] == weapon:
            return row
    return None


def beam_rate_field(make, weapon, backend):
    row = beam_rate(weapon)
    if not row:
        return None
    field = make('beam.fire_rate', row['fireRate'], backend(104, 'i32'))
    field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': BEAM_RATE_REASON,
        'min': 1, 'max': 6000, 'effect': effect()})
    return field


def recoil_multiplier_fields(make, backend):
    data = research()['maxigun']['recoilModifiers']
    values = {member['offset']: member['value'] for member in data['members']}
    fields = []
    for item in data['exposed']:
        field = make(item['field'], values[item['offset']], backend(item['offset'], 'f32'))
        field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': RECOIL_REASON,
            'min': 0, 'max': 50, 'effect': effect()})
        fields.append(field)
    return fields
