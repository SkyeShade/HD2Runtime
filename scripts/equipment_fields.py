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


# 0.30.4 (research/las-beam-overhaul-comparison-F5FEE03DCFDB.json, research/docs/las-beam-overhaul-comparison.md):
# the firing charge (wind-up) of heat weapons and the Trident's pulsed beam. Typed members by offset and storage;
# names are leads (unproven): every write needs allow_unverified_effect until the live tests below pass.
CHARGE_RESEARCH = ROOT / 'research/las-beam-overhaul-comparison-F5FEE03DCFDB.json'
CHARGE_REASON = ('Wind-up (the firing charge, WeaponHeat +148/+152/+156/+160; typed FP32/FP32/FP32/UINT8): the weapon '
    'fires only once its charge reaches heat.firing_charge; holding the trigger adds heat.charge_gain_per_second per '
    'second, releasing it removes heat.charge_loss_per_second per second, and heat.reset_charge_after_shot empties it '
    'after every shot (the Quasar). The charge update and the fire gate that read these members are traced '
    '(research/windup-controls-F5FEE03DCFDB.json). Wind-up = firing charge / gain per second (Sickles and LAS-98 '
    '100 / 200 = 0.5 s; Scythe and Dagger 0.25 s; Quasar 3.03 s; Sai, Trident, Talon 0): set heat.firing_charge to 0 '
    'for an instant first shot, or raise heat.charge_gain_per_second for a shorter wind-up. Live test pending: '
    'Sickle 0 fires at once, 400 winds up about 2 s.')
PULSE_REASON = ('Beam fire mode and pulse (BeamWeapon +100 typed enum, +108 INT32, +112 FP32): the LAS-13 Trident is '
    'the only weapon in mode 6 (300 rpm, 2 beams per pulse, 0.15 s); continuous beams are mode 4 (1, 0), the 40-K '
    'Meltagun mode 5 (1, 1.4 s). The game branches on mode 6. Live test pending: a Scythe in mode 6 with the '
    "Trident's rate and pulse fires Trident-like blasts; the Trident's +112 / +108 changed.")
CHARGE_FIELDS = (('heat.firing_charge', '148', 148, 'f32', 0, 10000), ('heat.charge_gain_per_second', '152', 152, 'f32',
    0, 100000), ('heat.charge_loss_per_second', '156', 156, 'f32', 0, 100000),
    ('heat.reset_charge_after_shot', '160', 160, 'u8', None, None))
PULSE_FIELDS = (('beam.fire_mode', '100', 100, 'u32', 4, 6), ('beam.fire_rate', '104', 104, 'i32', 1, 6000),
    ('beam.pulse_beams', '108', 108, 'i32', 1, 8), ('beam.pulse_seconds', '112', 112, 'f32', 0, 10))


def charge_research():
    return json.loads(CHARGE_RESEARCH.read_text(encoding='utf-8'))


def _named(records, weapon):
    """A research record by its component record index (an int: the weapon's own record, as its ownership names it)
    or by the weapon name the research resolved (a str)."""
    for record in records:
        if isinstance(weapon, int) and record['record'] == weapon:
            return record
        if isinstance(weapon, str) and any(owner.get('name') == weapon for owner in record['owners']):
            return record
    return None


def charge_record(weapon):
    """The firing-charge research record of a WeaponHeat record index (or a researched weapon name), or None."""
    return _named(charge_research()['heat148']['records'], weapon)


def firing_charge_fields(make, weapon, backend, skip=()):
    """The firing-charge fields of a heat weapon the research names (its own WeaponHeat record), or []."""
    record = _named(charge_research()['heat148']['records'], weapon)
    if not record:
        return []
    fields = []
    for field_id, key, offset, storage, low, high in CHARGE_FIELDS:
        if field_id in skip:
            continue
        value = record['values'][key]
        field = make(field_id, bool(value) if storage == 'u8' else value, backend(offset, storage))
        field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': CHARGE_REASON,
            'effect': effect()})
        if low is not None:
            field.update({'min': low, 'max': high})
        fields.append(field)
    return fields


def warmup_cooldown_declarations(weapon, capacity, cool):
    """Blocked declarations for the wiki's Warmup and Cooldown After Overheat of a heat weapon the research names: no
    member of their own; each names the fields to edit and this weapon's values (the Quasar: 100 / 33 = 3.03 s warm-up;
    100 heat at 6.66 per second = about 15 s of cooling)."""
    record = _named(charge_research()['heat148']['records'], weapon)
    if not record:
        return []
    charge, gain = record['values']['148'], record['values']['152']
    warmup = 0.0 if charge <= 0 else (charge / gain if gain > 0 else None)
    out = [{'field': 'heat.warmup',
        'reason': ('Derived: heat.firing_charge / heat.charge_gain_per_second = %g / %g = %s; edit heat.firing_charge '
            'or heat.charge_gain_per_second.') % (charge, gain,
            'never (no charge gain)' if warmup is None else '%.2f s' % warmup)}]
    if capacity and cool:
        out.append({'field': 'heat.overheat_cooldown',
            'reason': ('No proven member of its own: after an overheat the weapon cools from heat.capacity (%g) at '
                'heat.cool_per_second (%g per second), about %.1f s before the native cold / hot multipliers; edit '
                'heat.capacity or heat.cool_per_second.') % (capacity, cool, capacity / cool)})
    return out


def beam_pulse_fields(make, weapon, backend, skip=()):
    """The beam fire mode, rate and pulse of a beam weapon the research names (its own BeamWeapon record), or []."""
    record = _named(charge_research()['beams']['records'], weapon)
    if not record:
        return []
    fields = []
    for field_id, key, offset, storage, low, high in PULSE_FIELDS:
        if field_id in skip:
            continue
        field = make(field_id, record['values'][key], backend(offset, storage))
        field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': PULSE_REASON,
            'min': low, 'max': high, 'effect': effect()})
        fields.append(field)
    return fields
