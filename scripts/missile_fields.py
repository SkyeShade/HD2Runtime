"""Fields of the missile a weapon spawns per shot (research/wasp-rocket-F5FEE03DCFDB.json; 0.30.4, offline only).

A weapon whose ProjectileWeapon +40 (ProjectileEntity) names an entity spawns that entity per shot instead of a
projectile; +584 is the entity of its ProgrammableAmmo function. On the W.A.S.P., Spear, Commando, P-33 and P-92 the
entity is a SeekingMissile unit whose flight is its own SeekingMissileComponent record (one owner: the missile; one
ProjectileWeapon member names it). The fields write that record through the link: every write re-proves that the
weapon's member still names the reviewed missile (domains/player_weapon_writes.lua spawned_entity).

missile.*           the entity of +40 (what the weapon fires by default)
function_missile.*  the entity of +584 (fired while the ProgrammableAmmo function is in state 1)

None of them is shown in game yet: every write requires allow_unverified_effect.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/wasp-rocket-F5FEE03DCFDB.json'
DOMAINS = {40: 'missile', 584: 'function_missile'}
PW = 'ProjectileWeaponComponentData'
SM = 'SeekingMissileComponentData'

REASON = ('A member of the SeekingMissile record of the missile this weapon spawns per shot '
    '(research/wasp-rocket-F5FEE03DCFDB.json): the name comes from a lead checked against the type library\'s '
    'hidden-name length and the code that reads it is pinned; how far the change shows in game is not yet seen.')
# What the missile does with each member (semantic text only; the instruction pins are in the research).
EFFECTS = {
    'max_lifetime': 'The missile ends when its age reaches this; 0 or less would mean no limit (not offered).',
    'starting_speed': 'The speed of the missile when it spawns.',
    'minimum_speed': 'The target speed starts here and grows by acceleration per second of flight.',
    'preferred_speed': 'The target speed the missile accelerates to (the cap).',
    'acceleration': 'How fast the target speed grows from minimum_speed to preferred_speed (per second).',
    'max_angle_to_target': ('The angle to the target (degrees) at and beyond which the turn rate is '
        'turn_rate_at_max_angle; closer to the target it blends towards turn_rate_aligned.'),
    'turn_rate_at_max_angle': 'How fast the missile turns towards its target at or beyond max_angle_to_target.',
    'turn_rate_aligned': 'How fast the missile turns towards its target when it points at it.',
    'guidance_delay': ('Seconds of flight before guidance switches on; only offered where the native value is above 0 '
        '(0 or less never switches it on by time).'),
}
MULTIPLAYER = ('A type record: every machine moves its own copy of the missile from its own record, so a player '
    'without the same edit sees the vanilla flight; damage and the explosion follow the carried projectile, whose '
    'impact the shooter decides.')


def research() -> dict:
    return json.loads(RESEARCH.read_text(encoding='utf-8'))


def spawns(resource: str) -> list[dict]:
    """The exposable missiles the weapon `resource` spawns: [{member, domain, missile, projectileWeapon}]."""
    data = research()
    out = []
    for weapon in data['weapons']:
        if weapon['resource'] != resource:
            continue
        for item in weapon['spawns']:
            if item['exposable']:
                out.append({'member': item['member'], 'domain': DOMAINS[item['member']], 'missile': item,
                    'projectileWeapon': weapon['projectileWeapon'], 'weapon': weapon})
    return out


def fields(make, resource: str, weapon_identity: dict) -> list[dict]:
    """The missile fields of the weapon `resource`. `make(field_id, value, backing)` builds a field on the weapon
    target; `weapon_identity` is the weapon's own ProjectileWeaponComponentData ownership (recordIndex, indexRow,
    ownerCount) from the catalogue, which must be the one research saw."""
    data = research()
    found = spawns(resource)
    if not found:
        return []
    out = []
    for spawn in found:
        pw = spawn['projectileWeapon']
        assert weapon_identity and all(weapon_identity[key] == pw[key] for key in ('recordIndex', 'indexRow',
            'ownerCount')), resource + ': ProjectileWeapon identity diverged from research/wasp-rocket'
        missile = spawn['missile']
        sm = missile['seekingMissile']
        assert sm['ownerCount'] == 1 and sm['owners'] == [missile['resource']], resource + ': missile record shared'
        link = {'component': PW, 'offset': spawn['member'], 'weapon': resource, 'recordIndex': pw['recordIndex'],
            'indexRow': pw['indexRow'], 'ownerCount': pw['ownerCount'], 'entity': missile['resource'],
            'entityRow': missile['entityRow']}
        values = {m['offset']: m for m in data['members']}
        for item in data['fields']:
            lead = values[item['offset']]['leadName']
            native = sm['values'][lead]
            if item['nativeRule'] == 'positive' and not native > 0:
                continue
            backing = {'kind': 'component', 'component': SM, 'offset': item['offset'], 'storage': 'f32', 'width': 4,
                'recordIndex': sm['recordIndex'], 'indexRow': sm['indexRow'], 'ownerCount': 1, 'uniqueOwner': True,
                'resource': missile['resource'], 'link': dict(link)}
            field = make(spawn['domain'] + '.' + item['field'], native, backing)
            spawn_only = item['field'] == 'starting_speed'
            field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': REASON,
                'min': item['min'], 'max': item['max'], 'unit': item['unit'],
                'rangeReason': ('reviewed range for a missile' if item['nativeRule'] is None else
                    'reviewed range; 0 or less changes what the member means (no limit / never by time), not offered'),
                'effect': {'activeSource': 'SPAWNED_ENTITY_RECORD', 'activeSourceProven': True,
                    'gameplayEffectProven': False, 'unverifiedEffect': True, 'instantiationOnly': spawn_only,
                    'appliesWhen': 'missile_spawn' if spawn_only else 'missile_update',
                    'reason': EFFECTS[item['field']] + (' A write changes the next missile.' if spawn_only else
                        ' Read on every missile update: a write changes missiles already in flight.')},
                'spawnedEntity': {'member': 'ProjectileWeapon +%d' % spawn['member'], 'resource': missile['resource'],
                    'seekingMissileRecord': sm['recordIndex'], 'projectileType': missile['projectileType'],
                    'projectileTypeSource': missile['projectileTypeSource'],
                    'research': 'research/wasp-rocket-F5FEE03DCFDB.json'},
                'multiplayer': MULTIPLAYER})
            out.append(field)
    return out
