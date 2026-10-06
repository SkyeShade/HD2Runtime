"""Support-weapon charge fields (WeaponChargeComponentData) from research/railgun-charge-F5FEE03DCFDB.json.

Used by scripts/generate_support_weapon_authoring.py. Every member is read live from the weapon's own unique type record
by the charge update (game.dll 0x73C8F0) every frame and on every shot; no customization (entity delta) and no
per-instance copy exists for this component, so a write takes effect on the next frame, including weapons in hand.

A field is offered only on the weapons whose code path reads it:

* charge times (charge.level_1/2/3): every charge weapon (the charge update);
* projectile speed multipliers: projectile weapons (0x741A00 -> SpawnProjectile extra +0x2C);
* damage and armor-penetration multipliers: projectile weapons (SpawnProjectile extra +0x30/+0x34, applied on impact)
  and arc weapons (the arc spawn 0x13B3910);
* arc distance multipliers: arc weapons only (0x13B3910);
* auto_fire_at_full: weapons that can be in a fire mode other than 6 (the safe path of the update);
* explode_at_overcharge, overcharge_explosion, overcharge_limit_seconds: weapons that can be in fire mode 6 (the
  unbounded path; the limit applies in the overcharged state, which only mode 6 reaches);
* burst shots and interval: projectile and arc weapons (the fire helper 0x73D8C0 fires them through 0x741A00; a beam
  weapon with a burst count refuses to fire at all).

The two mislabelled ids charge.minimum_seconds / charge.maximum_seconds keep writing +72 / +76 (the projectile speed
multipliers). On projectile weapons they are deprecated aliases of charge.speed_multiplier_min / _overcharge; on arc and
beam weapons nothing reads those bytes, so the canonical ids are not offered and the legacy ids stay writable with a
one-time dormant warning. Their legacy contract (no acknowledgement, no range) is kept exactly.

Charge-level shots and overcharge explosions (research/charge-explosions-F5FEE03DCFDB.json): the charge fire helper picks
the projectile a release fires from the weapon's own WeaponCharge record (+4 partial, +28 full, +52 overcharged), and the
overcharge failure spawns the +200 explosion. Each of those rows is its own attack role on the support weapon, resolved
live through the charge record (linkages charge_projectile / charge_projectile_explosion / charge_overcharge_explosion):

* PLAS-45 Epoch: 'primary' / 'primary_impact' are the PARTIAL-charge shot and its explosion (their ids are unchanged),
  'full_charge' / 'full_charge_impact' the full-charge (and overcharged) shot and its explosion, 'overcharge_explosion'
  the explosion that destroys the weapon after the hold limit;
* RS-422 Railgun: 'overcharge_explosion' (every Railgun shot is its own projectile, 'primary').

A row only some charge levels fire is AMBIGUOUS for the weapon, like the PLAS-101 Purifier's: every such field needs
allow_unverified_effect. The Epoch's partial-charge fields gained that requirement in 0.30.0 (version-aware:
schemas/legacy_acknowledgements.json); every new field needs it because none is shown in game yet.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/railgun-charge-F5FEE03DCFDB.json'
LEVELS_RESEARCH = ROOT / 'research/charge-explosions-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
COMPONENT = 'WeaponChargeComponentData'
UNSAFE_MODE = 6

TIMES = (('charge.level_1', '0[0].0', 0, 0.0, 60.0), ('charge.level_2', '0[1].0', 24, 0.01, 60.0),
    ('charge.level_3', '0[2].0', 48, 0.01, 60.0))
TIME_RANGE_REASON = ('Charge times in seconds. Full and overcharge must be above 0: the update divides by them. Keep '
    'minimum < full < overcharge (write related times in one transaction): a write that breaks the order is applied '
    'with a one-time CHARGE ORDER notice, because these ids are older than the rule.')
MULTIPLIER_RANGE = (0.0, 10.0)
MULTIPLIER_RANGE_REASON = ('A multiplier of the shot (0 to 10): the native lerp goes from the minimum value at the '
    'minimum charge to 1.0 at full charge, then to the overcharge value at the overcharge time.')
LEGACY = {'charge.minimum_seconds': ('72.0', 72, 'charge.speed_multiplier_min'),
    'charge.maximum_seconds': ('72.4', 76, 'charge.speed_multiplier_overcharge')}
MULTIPLIERS = {
    'charge.speed_multiplier_min': ('72.0', 72, ('projectile',)),
    'charge.speed_multiplier_overcharge': ('72.4', 76, ('projectile',)),
    'charge.damage_multiplier_min': ('72.8', 80, ('projectile', 'arc')),
    'charge.damage_multiplier_overcharge': ('72.12', 84, ('projectile', 'arc')),
    'charge.penetration_multiplier_min': ('72.16', 88, ('projectile', 'arc')),
    'charge.penetration_multiplier_overcharge': ('72.20', 92, ('projectile', 'arc')),
    'charge.arc_distance_multiplier_min': ('72.24', 96, ('arc',)),
    'charge.arc_distance_multiplier_overcharge': ('72.28', 100, ('arc',)),
}
MEANING = {
    'charge.speed_multiplier_min': 'projectile launch speed multiplier at the minimum charge time (lerps to 1.0 at '
        'full charge; SpawnProjectile multiplies the launch speed by it)',
    'charge.speed_multiplier_overcharge': 'projectile launch speed multiplier at the overcharge time (from 1.0 at '
        'full charge)',
    'charge.damage_multiplier_min': 'damage multiplier at the minimum charge time (projectiles: the hit damage; arcs: '
        'the arc damage)',
    'charge.damage_multiplier_overcharge': 'damage multiplier at the overcharge time',
    'charge.penetration_multiplier_min': 'armor-penetration multiplier at the minimum charge time (each of the four '
        'armor-penetration values, rounded to a whole class)',
    'charge.penetration_multiplier_overcharge': 'armor-penetration multiplier at the overcharge time',
    'charge.arc_distance_multiplier_min': 'arc distance multiplier at the minimum charge time',
    'charge.arc_distance_multiplier_overcharge': 'arc distance multiplier at the overcharge time',
    'charge.auto_fire_at_full': 'outside fire mode 6, fire as soon as the charge reaches the full charge time instead '
        'of holding it until the trigger is released',
    'charge.explode_at_overcharge': 'in fire mode 6, reaching the overcharge time fires the shot, removes the weapon '
        'and spawns the overcharge explosion at it',
    'charge.burst_shots': 'shots fired per charge: above 1 the weapon re-fires after burst_interval_seconds until the '
        'count is reached (0 and 1 both mean one shot)',
    'charge.burst_interval_seconds': 'seconds before each further shot of one charge (0: no further shot fires)',
    'charge.overcharge_limit_seconds': 'in the overcharged state (fire mode 6 only), the weapon is removed and the '
        'overcharge explosion spawns WITHOUT a shot once the charge has been held this many seconds (0 = off)',
    'charge.overcharge_explosion': 'the explosion the overcharge failure spawns at the weapon',
}
UNVERIFIED = ('Read live by the native charge code (research/railgun-charge-F5FEE03DCFDB.json); the exact effect of an '
    'edit is not yet shown in game.')
HAZARD = ('A hazard: when it triggers, the weapon is removed (destroyed) and its overcharge explosion spawns at it. '
    + UNVERIFIED)
LEGACY_DEPRECATED = ('{id} is a deprecated, mislabelled id: WeaponChargeComponent +{offset} is the projectile speed '
    'multiplier at {when}, not a time. It still writes exactly those bytes; use {canonical}.')
LEGACY_DORMANT = ('{id} writes WeaponChargeComponent +{offset} (the projectile speed multiplier at {when}), which the '
    '{weapon} never reads: it is a{article} {family} weapon and fires no projectile. The write is kept for '
    'compatibility and has no effect.')
EFFECT = {'activeSource': 'LIVE_TYPE_RECORD', 'activeSourceProven': True, 'appliesWhen': 'next_frame',
    'instantiationOnly': False, 'gameplayEffectProven': False,
    'lifecycle': ("Read live every frame from the weapon's own WeaponChargeComponent record (one owner): a write takes "
        'effect on the next frame, including weapons already in hand. No customization or per-instance copy exists.')}


def load():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    modes = {item['weapon']: item for item in json.loads(FIRE_MODES.read_text(encoding='utf-8'))['weapons']
        if item['kind'] == 'support'}
    residency = json.loads(RESIDENCY.read_text(encoding='utf-8'))['catalog']
    return research, modes, residency


def family(ownership):
    if 'ProjectileWeaponComponentData' in ownership:
        return 'projectile'
    if 'ArcWeaponComponentData' in ownership:
        return 'arc'
    if 'BeamWeaponComponentData' in ownership:
        return 'beam'
    return None


def reachable_modes(mode_row):
    """Fire modes the weapon can be in: the default slot, and every slot when a Firemode selector is bound."""
    slots = [value for value in mode_row['slots'] if value]
    selector = mode_row['selector']
    bound = 'Firemode' in (selector.get('left'), selector.get('right'))
    return set(slots) if bound else set(slots[:1])


def record_for(research, name):
    for record in research['records']:
        if any((identity or {}).get('name') == name for identity in record['identity']):
            return record
    return None


def donors(research, modes, residency, candidates_by_name):
    """Overcharge explosion donors: charge weapons whose failure path is reachable and whose package is known."""
    result = {}
    for entry in research['overchargeExplosions']:
        name = entry['label']
        if name not in candidates_by_name or name not in modes:
            continue
        if UNSAFE_MODE not in reachable_modes(modes[name]):
            continue
        dependency = residency.get('support_weapon/' + name)
        if not dependency or not dependency.get('known'):
            continue
        row = entry['row'] or {}
        result[name] = {'weapon': name, 'explosionType': entry['explosionType'],
            'dependencyKey': 'support_weapon/' + name,
            'summary': (name + ' overcharge explosion (inner/outer/shockwave radius ' + str(row.get('innerRadius'))
                + ' / ' + str(row.get('outerRadius')) + ' / ' + str(row.get('shockwaveRadius')) + ' m)')}
    return result


def build(weapon, candidate, make_field, component, blocked, research, modes, donor_table):
    """The charge field descriptors of one support weapon (empty when it owns no WeaponChargeComponentData)."""
    ownership = candidate['ownership']
    if COMPONENT not in ownership:
        return []
    name = weapon['name']
    record = record_for(research, name)
    assert record is not None, name + ': charge weapon missing from research/railgun-charge'
    owner = ownership[COMPONENT]
    assert owner['recordIndex'] == record['record'] and owner['uniqueOwner'], name + ': charge record identity changed'
    label = record['label']
    matrix = research['matrix']

    def value(path):
        return matrix[path][label]
    kind = family(ownership)
    assert kind, name + ': charge weapon of no reviewed family'
    reachable = reachable_modes(modes[name])
    unsafe = UNSAFE_MODE in reachable
    safe = bool(reachable - {UNSAFE_MODE})
    target = {'resource': 'support_weapon', 'path': 'weapon', 'weapon': name}
    fields = []

    def add(field_id, current, offset, storage, acknowledgement=None, reason=None, **extra):
        if storage == 'f32':
            current = struct.unpack('<f', struct.pack('<f', current))[0]   # the exact stored single-precision value
        item = make_field(field_id, current, component(candidate, COMPONENT, offset, storage), target,
            acknowledgement=acknowledgement)
        if acknowledgement:
            item['acknowledgementReason'] = reason or UNVERIFIED
        item['charge'] = {'meaning': MEANING.get(field_id), 'family': kind, 'effect': EFFECT}
        item.update(extra)
        fields.append(item)
        return item

    # Charge times (existing ids): seconds; a cross-field order is checked per operation.
    cadence = candidate.get('chargeCadence') or {}
    for (field_id, path, offset, low, high), level in zip(TIMES, cadence.get('levels') or [None] * 3):
        current = value(path)
        assert level is None or abs(level - current) < 1e-6, name + ': charge time differs from the catalog'
        current = level if level is not None else current
        add(field_id, current, offset, 'f32', min=low, max=high, rangeReason=TIME_RANGE_REASON, chargeTime=True)
    # The legacy ids keep their exact contract (no acknowledgement, no range).
    for field_id, (path, offset, canonical) in LEGACY.items():
        when = 'the minimum charge time' if offset == 72 else 'full overcharge'
        item = add(field_id, value(path), offset, 'f32', legacyContract=True, deprecated=True, canonical=False,
            preferred=False, aliasOf=None)
        notices = [{'kind': 'deprecated', 'text': LEGACY_DEPRECATED.format(id=field_id, offset=offset, when=when,
            canonical=canonical)}]
        if kind != 'projectile':
            item['dormant'] = True
            notices.append({'kind': 'dormant', 'text': LEGACY_DORMANT.format(id=field_id, offset=offset, when=when,
                weapon=name, family=kind, article='n' if kind == 'arc' else '')})
        item['notices'] = notices
    for field_id, (path, offset, families) in MULTIPLIERS.items():
        if kind not in families:
            continue
        item = add(field_id, value(path), offset, 'f32', 'allow_unverified_effect', min=MULTIPLIER_RANGE[0],
            max=MULTIPLIER_RANGE[1], rangeReason=MULTIPLIER_RANGE_REASON)
        item.update(canonical=True, preferred=True, deprecated=False, aliasOf=None)
    if kind != 'projectile':
        blocked.append({'field': 'charge.speed_multiplier_min / charge.speed_multiplier_overcharge',
            'reason': 'No projectile: the ' + kind + ' fire path never reads WeaponChargeComponent +72/+76. The '
                'deprecated ids charge.minimum_seconds / charge.maximum_seconds stay writable (dormant).'})
    if kind == 'beam':
        blocked.append({'field': 'charge damage / penetration multipliers, burst', 'reason':
            'A beam weapon reads none of them; with a burst count the fire helper refuses to fire at all.'})
    if kind != 'arc':
        blocked.append({'field': 'charge.arc_distance_multiplier_*', 'reason': 'Read only by arc weapons.'})
    else:
        blocked.append({'field': 'extra arc splits / chains (+104..+116)', 'reason': 'Read by the arc spawn, but which '
            'of the two counts is splits and which is chains rests on a community field order only.'})
    if safe:
        add('charge.auto_fire_at_full', bool(value('184')), 184, 'u8', 'allow_unverified_effect')
    else:
        blocked.append({'field': 'charge.auto_fire_at_full', 'reason': 'This weapon is always in fire mode 6, where the '
            'charge is unbounded and never auto-fires.'})
    if unsafe:
        add('charge.explode_at_overcharge', bool(value('185')), 185, 'u8', 'allow_unverified_effect', HAZARD)
        add('charge.overcharge_limit_seconds', value('204.4'), 208, 'f32', 'allow_unverified_effect', HAZARD,
            min=0.0, max=60.0, rangeReason='Seconds held in the overcharged state before the weapon fails (0 = off).')
        assert value('204.0') == 2, name + ': overcharge limit state is no longer the overcharged state'
        own = donor_table.get(name)
        assert own and own['explosionType'] == value('200'), name + ': overcharge explosion donor changed'
        options = [donor_table[key] for key in sorted(donor_table)]
        explosion = add('charge.overcharge_explosion', name, 200, 'u32', 'allow_unverified_effect',
            HAZARD + ' Another weapon\'s explosion also needs allow_unverified_reference and loads that weapon\'s '
            'package first.', allowedValues=[item['weapon'] for item in options],
            explosionOptions={item['weapon']: {'explosionType': item['explosionType'],
                'dependencyKey': item['dependencyKey'], 'summary': item['summary']} for item in options},
            referenceKind='overcharge_explosion')
        explosion['type'] = 'overcharge_explosion_reference'
        blocked.append({'field': 'overcharge limit state (+204)', 'reason': 'The charge state the hold limit applies in '
            '(2 = overcharged on every record): code-proven but no record differs, so it stays read-only.'})
    else:
        blocked.append({'field': 'charge.explode_at_overcharge / charge.overcharge_limit_seconds / '
            'charge.overcharge_explosion', 'reason': 'This weapon can never be in fire mode 6 (no Firemode selector '
            'reaches it), so the overcharge failure is unreachable.'})
    if kind in ('projectile', 'arc'):
        add('charge.burst_shots', value('188'), 188, 'u32', 'allow_unverified_effect', min=0, max=10,
            rangeReason='0 and 1 both fire one shot per charge; at most 10.')
        add('charge.burst_interval_seconds', value('192'), 192, 'f32', 'allow_unverified_effect', min=0.0, max=10.0,
            rangeReason='0 means no further shot of a burst fires.')
    blocked.append({'field': 'per-charge-state projectile types and particles', 'reason': 'Attack-output selectors '
        '(docs/attack-outputs.md); not charge fields. Where reviewed, the rows they select are attack roles '
        '(support:attack(role); research/charge-explosions-F5FEE03DCFDB.json).'})
    return fields


# ---------------------------------------------------------------------------------------------------------------------
# Charge-level shots and overcharge explosions (research/charge-explosions-F5FEE03DCFDB.json)
# ---------------------------------------------------------------------------------------------------------------------
LEVEL_EVIDENCE = 'research/charge-explosions-F5FEE03DCFDB.json'
LEVEL_NOT_SHOWN = 'The charge-level selection is proven from the native fire code; the effect of an edit is not yet shown in game.'
FAILURE_NOT_SHOWN = 'Proven from the native overcharge-failure code; the effect of an edit is not yet shown in game.'
MULTIPLAYER = ('A write changes this machine\'s copy of the shared row. The charge update and the overcharge failure run '
    'where the weapon is simulated (its owner); what other players see is not tested.')
READ = {
    'projectile': ('Copied into the projectile when it is fired: the write applies to shots fired after it; a projectile '
        'already in flight keeps its copy.'),
    'projectile_damage': ('Its damage type and armour penetration are copied into the projectile when it is fired: the '
        'write applies to shots fired after it.'),
    'explosion': ('Read when the explosion happens: the game looks the row up by type in the live explosion table and '
        'reads its radii then. The write applies to the next explosion, also one a projectile already in flight '
        'releases.'),
    'explosion_damage': ('Looked up through the explosion row when the explosion happens: the write applies to the next '
        'explosion.'),
}


def load_levels():
    return json.loads(LEVELS_RESEARCH.read_text(encoding='utf-8'))


def _exact(value):
    return struct.unpack('<f', struct.pack('<f', value))[0] if isinstance(value, float) else value


def resolve_branches(weapon, levels):
    """The catalog branches the charge-level research identifies, each RESOLVED on its own attack role (the read-only
    mapper matched them to the only runtime attack it knew). Existing resolved branches stay as they are."""
    entry = levels['weapons'].get(weapon['name'])
    if not entry:
        return weapon
    published = levels['published'][weapon['name']]
    attacks = {item['role']: item for item in entry['attacks']}
    graph = []
    for branch in weapon['attackGraph']:
        role = entry['branches'].get(branch['name'])
        attack = attacks.get(role)
        if attack is None:
            graph.append(branch)
            continue
        if attack['existing']:
            match = branch.get('runtimeMatch') or {}
            assert branch['state'] == 'RESOLVED' and match.get('runtimeAttackRole') == role, \
                weapon['name'] + ': ' + branch['name'] + ' is no longer the resolved ' + role + ' branch'
            graph.append(dict(branch, chargeLevel=attack['chargeLevel']))
            continue
        item = published[branch['name']]
        assert item['allExact'] and item['row'], weapon['name'] + ': ' + branch['name'] + ' no longer matches its row'
        graph.append(dict(branch, state='RESOLVED', resolvedBy='charge_level', unresolvedReason=None,
            chargeLevel=attack['chargeLevel'],
            runtimeMatch={'runtimeAttackRole': role, 'runtimeAttackKind': attack['kind'],
                'runtimeParentRole': attack['parentRole'], 'matchedFields': item['matchedFields'],
                'mismatchedFields': [], 'compared': len(item['matchedFields'])}))
    resolved = {name for name, role in entry['branches'].items() if role in attacks and not attacks[role]['existing']}
    links = [reason for reason in weapon.get('unresolvedLinks') or []
        if not any(reason.startswith(name + ':') for name in resolved)]
    return dict(weapon, attackGraph=graph, unresolvedLinks=links)


def _record(entry, kind, view):
    identity = view['identity']
    return {'group': identity['group'], 'recordType': identity['recordType'], 'row': identity['row'],
        'settingsType': identity['settingsType']}


def _damage_fields(damage):
    return {key: value for key, value in damage['values'].items() if key != 'statuses'}


def level_attacks(weapon_name, levels, candidate):
    """Role -> charge-level attack for one weapon: the new ones shaped like catalog candidate attacks (projectile,
    damage and explosion records with resolved values), and the linkage every field of a role uses. Empty for weapons
    the research does not cover."""
    entry = levels['weapons'].get(weapon_name)
    if not entry:
        return {}
    owner = candidate['ownership']['WeaponChargeComponentData']
    identity = entry['chargeRecord']['identity']
    assert {key: owner[key] for key in identity} == identity and owner['uniqueOwner'], \
        weapon_name + ': charge record identity changed'
    by_role = {item['role']: item for item in entry['attacks']}
    out = {}
    for item in entry['attacks']:
        damage = item['damage']
        # A status on these rows would need its own (status) linkage through the charge record: none is reviewed.
        assert not damage['values']['statuses'], weapon_name + ' ' + item['role'] + ': damage row carries statuses'
        if item['kind'] == 'Projectile':
            selectors = item['selectorOffsets']
        else:
            parent = by_role.get(item['parentRole'])
            selectors = parent['selectorOffsets'] if parent else None
        extra = {'chargeRecord': dict(identity)}
        if selectors:
            extra['chargeSelectorOffsets'] = list(selectors)
        if item.get('explosionOffset') is not None:
            extra['chargeExplosionOffset'] = item['explosionOffset']
        attack = {'role': item['role'], 'kind': item['kind'], 'chargeLevel': item['chargeLevel'],
            'existing': item['existing'], 'linkage': item['linkage'], 'backingExtra': extra,
            'parentRole': item['parentRole'], 'phases': item.get('phases'), 'statusEffects': {},
            'damageInfo': _record(entry, 'damage', damage)}
        if item['kind'] == 'Projectile':
            view = item['projectile']
            values = {key: _exact(value) for key, value in view['values'].items()}
            attack.update(projectileSettings=_record(entry, 'projectile', view),
                resolvedFields=dict({'projectile_velocity': values['projectile_velocity'],
                    'projectile_mass': values['projectile_mass'], 'drag': view['exact']['drag'],
                    'gravity': values['gravity'], 'pellet_count': values['pellet_count']}, **_damage_fields(damage)),
                projectileRow={'recordType': view['identity']['recordType'], 'lifetime': view['values']['lifetime'],
                    'penetrationSlowdown': view['values']['penetration_slowdown']})
        else:
            view = item['explosion']
            values = {key: _exact(value) for key, value in view['values'].items()}
            values['explosion_inner_radius'] = view['exact']['explosion_inner_radius']
            attack.update(explosionSettings=_record(entry, 'explosion', view),
                resolvedFields=dict(values, **_damage_fields(damage)))
        out[item['role']] = attack
    return out


def _row_key(field):
    backing = field['backing']
    kind = 'damage' if backing['settings'] in ('damage', 'explosion_damage') else backing['settings']
    return kind + ':' + str(backing['recordType'])


def _semantic_row(field):
    backing = field['backing']
    if backing['settings'] == 'projectile':
        return 'projectile'
    if backing['settings'] == 'damage':
        return 'projectile_damage'
    return 'explosion_damage' if backing['settings'] == 'explosion_damage' else 'explosion'


def _consumers(levels, weapon_name, field):
    """Other weapons whose own data names the written row (semantic names only; reachability from the research)."""
    key = _row_key(field)
    sharing = levels['sharing']
    rows = [key]
    if key.startswith('damage:'):
        rows += ['explosion:' + str(item['row']) for item in sharing.get(key, []) if item['kind'] == 'explosion_damage']
    out, unidentified = [], 0
    for row in rows:
        for item in sharing.get(row, []):
            if item['kind'] != 'overcharge_failure':
                continue
            name = item.get('weapon')
            if name == weapon_name:
                continue
            if not name or name.startswith('0x') or name.startswith('unowned'):
                unidentified += 1
                continue
            out.append({'weapon': name, 'via': 'overcharge explosion', 'reachable': item.get('reachable'),
                'note': None if item.get('reachable') is not None else 'fire modes not reviewed'})
    return sorted(out, key=lambda item: item['weapon']), unidentified


def _level_texts(entry):
    """Public wording per charge level (semantic only: no native ids), with the weapon's reviewed times."""
    record = entry['chargeRecord']
    t0, t1, t2 = record['chargeTimes']
    limit = record['overchargeLimit']['seconds']
    if record['explodeWhenOvercharged']:
        failure = ('in Unsafe mode (fire mode 6), reaching the overcharge time (%.3g s) fires the shot, then the weapon '
            'is destroyed and this explosion spawns in the wielder\'s hands' % t2)
    else:
        failure = ('held overcharged (past the overcharge time, %.3g s) for %.3g s, the weapon is destroyed and this '
            'explosion spawns in the wielder\'s hands without a shot' % (t2, limit))
    return {
        'partial': {'shot': 'partial-charge shot (released from %.3g s to before %.3g s)' % (t0, t1),
            'when': 'a release at or after the minimum charge time (%.3g s) and before the full charge time (%.3g s)'
                % (t0, t1),
            'other': {'Projectile': "Full-charge and overcharged shots fire attack('full_charge') instead",
                'Explosion': "Full-charge and overcharged shots release attack('full_charge_impact') instead"}},
        'full': {'shot': 'full-charge or overcharged shot (released from %.3g s)' % t1,
            'when': ('a release at or after the full charge time (%.3g s), also past the overcharge time (%.3g s), '
                'until the hold limit destroys the weapon' % (t1, t2)),
            'other': {'Projectile': "Partial-charge shots fire attack('primary') instead",
                'Explosion': "Partial-charge shots release attack('primary_impact') instead"}},
        'overcharge': {'shot': 'overcharge failure', 'when': failure}}


SHARED_TEXT = {
    ('PLAS-45 Epoch', 'primary', 'projectile'): 'Only the PLAS-45 Epoch uses this row (its partial-charge shot).',
    ('PLAS-45 Epoch', 'primary', 'projectile_damage'): 'Only the partial-charge projectile uses this damage row.',
    ('PLAS-45 Epoch', 'primary_impact', 'explosion'): ('Only the partial-charge projectile releases this explosion, at '
        'impact and when it expires.'),
    ('PLAS-45 Epoch', 'primary_impact', 'explosion_damage'): 'Only the partial-charge explosion uses this damage row.',
    ('PLAS-45 Epoch', 'full_charge', 'projectile'): 'Only the PLAS-45 Epoch uses this row (its full-charge shot).',
    ('PLAS-45 Epoch', 'full_charge', 'projectile_damage'): 'Only the full-charge projectile uses this damage row.',
    ('PLAS-45 Epoch', 'full_charge_impact', 'explosion'): ('Only the full-charge projectile releases this explosion, at '
        'impact and when it expires.'),
    ('PLAS-45 Epoch', 'full_charge_impact', 'explosion_damage'): ("Shared with the Epoch's overcharge explosion "
        "(attack('overcharge_explosion')) and through it the 40-K Meltagun's: one write changes both explosions."),
    ('PLAS-45 Epoch', 'overcharge_explosion', 'explosion'): ("Also the 40-K Meltagun's overcharge explosion (it never "
        "reaches its failure: always fire mode 1), and any charge weapon whose charge.overcharge_explosion a mod sets "
        "to 'PLAS-45 Epoch'."),
    ('PLAS-45 Epoch', 'overcharge_explosion', 'explosion_damage'): ("Shared with the Epoch's full-charge explosion "
        "(attack('full_charge_impact')) and the 40-K Meltagun's overcharge explosion: one write changes both Epoch "
        'explosions.'),
    ('RS-422 Railgun', 'overcharge_explosion', 'explosion'): ("Also the PLAS-39 Accelerator Rifle's overcharge "
        "explosion (it never reaches its failure: always fire mode 2), and any charge weapon whose "
        "charge.overcharge_explosion a mod sets to 'RS-422 Railgun'."),
    ('RS-422 Railgun', 'overcharge_explosion', 'explosion_damage'): ('Shared with the overcharge explosion of the '
        'PLAS-101 Purifier, PLAS-15 Loyalist, ARC-3 Arc Thrower, an enemy Watcher weapon and three unidentified charge '
        'records (the player weapons and the ARC-3 never reach their failure; the Watcher\'s fire modes are not '
        'reviewed): one write changes them all.'),
}


def annotate_levels(weapon_name, fields, levels):
    """Charge-level metadata, effect and acknowledgement on every field of a charge-level role: what fires or spawns
    the row, when the game reads it, who else uses it and the self-damage of an overcharge explosion."""
    entry = levels['weapons'].get(weapon_name)
    if not entry:
        return
    by_role = {item['role']: item for item in entry['attacks']}
    texts = _level_texts(entry)
    for field in fields:
        role = field['target'].get('attack')
        attack = by_role.get(role)
        if attack is None or field['backing'].get('kind') != 'settings':
            continue
        row = _semantic_row(field)
        level = attack['chargeLevel']
        text = texts[level]
        if level == 'overcharge':
            reason = 'Changes the explosion the overcharge failure spawns: ' + text['when'] + '. It damages the wielder.'
            reason += ' ' + FAILURE_NOT_SHOWN
        else:
            fires = ('releases this explosion (at impact and when the projectile expires)'
                if attack['kind'] == 'Explosion' else 'fires this row')
            reason = ('Only the ' + text['shot'].split(' (')[0] + ' ' + fires + ': ' + text['when'] + '. '
                + text['other'][attack['kind']] + ', which this write does not change. ' + LEVEL_NOT_SHOWN)
        shared = SHARED_TEXT[(weapon_name, role, row)]
        if row == 'explosion_damage' and level in ('full', 'overcharge') or level == 'overcharge':
            reason += ' ' + shared
        consumers, unidentified = _consumers(levels, weapon_name, field)
        # A status slot keeps its own reason (a status the attack does not use is not gameplay-proven) after this one.
        prior = field.get('acknowledgementReason') if field.get('acknowledgement') == 'allow_unverified_effect' else None
        field['acknowledgement'] = 'allow_unverified_effect'
        field['acknowledgementReason'] = reason + (' ' + prior if prior and field.get('statusSlot') else '')
        # A row only some charge levels fire never inherits live proof (the Purifier rule of the player weapons).
        field.pop('liveEvidence', None)
        field.pop('liveProvenValues', None)
        field['sharedWithWeapons'] = sorted({item['weapon'] for item in consumers})
        ambiguous = level != 'overcharge'
        field['effect'] = {'activeSource': 'AMBIGUOUS' if ambiguous else 'ACTIVE_DIRECT', 'appliesWhen': 'use',
            'instantiationOnly': False, 'activeSourceProven': not ambiguous, 'chargeLevelSelectionProven': True,
            'gameplayEffectProven': False, 'unverifiedEffect': True, 'writeVerifiedOnApply': True,
            'reason': ('Only one charge level of the weapon fires this row (see chargeLevel); which level fires it '
                'is proven from the native fire code.' if ambiguous else
                'The row the overcharge failure requests every time it runs (native failure code).'),
            'readTiming': READ[row]}
        field['chargeLevel'] = {'level': level, 'shot': text['shot'], 'firedWhen': text['when'], 'row': row,
            'phases': attack.get('phases') if attack['kind'] == 'Explosion' and level != 'overcharge' else None,
            'readTiming': READ[row], 'sharedWith': shared, 'sharedConsumers': consumers,
            'unidentifiedSharedConsumers': unidentified,
            'selfDamage': ('It spawns at the weapon, in the wielder\'s hands, and damages the wielder: test lower '
                'damage first.') if level == 'overcharge' else None,
            'multiplayer': MULTIPLAYER, 'evidence': LEVEL_EVIDENCE}


def branch_roles(weapon, levels):
    """Catalog branch name -> attack role, for weapons whose branches the charge-level research re-resolved."""
    entry = levels['weapons'].get(weapon['name'])
    if not entry:
        return None
    return {branch['name']: branch['runtimeMatch']['runtimeAttackRole'] for branch in weapon['attackGraph']
        if branch.get('state') == 'RESOLVED' and (branch.get('runtimeMatch') or {}).get('runtimeAttackRole')}
