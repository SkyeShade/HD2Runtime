"""Support-weapon explosions a weapon requests through an ability (0.31.0; scripts/generate_support_weapon_authoring.py).

The CQC-20 Breaching Hammer's charge blast (the published "IE" branch, 2200 Explosion, Anti-Tank II) is not a
projectile's terminal explosion nor an ExplosiveComponent's: the hammer's own MeleeWeaponComponentData +160 (an
8-slot AbilityId array) holds AbilityId 38 and the ability dispatcher's entry 38 requests explosion type 19 through
the ability explosion wrapper (research/explosion-identities-F5FEE03DCFDB.json: evidence tier 'code', site
0x109CEE3). Proven from data and code:

* AbilityId 38 is held by this member of this one record only (no other entity data names it), and no other code
  requests the handler (dispatcher stub 0x1150C7E is its only caller);
* the explosion row (type 19) has one owner and is not shared; its DamageInfo row has one user;
* every published value of the "IE" branch equals the row exactly (asserted below).

The Runtime re-proves at every write that the weapon's own melee record still holds the reviewed ability exactly once
in its +160 array (domains/player_weapon_writes.lua ability_explosion), and that the explosion row and its +4 damage
link are the reviewed rows (the support settings identity check). The code link (ability 38 -> type 19) is fixed by
the build fingerprint. Not yet shown in game: every field needs allow_unverified_effect.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/explosion-identities-F5FEE03DCFDB.json'
WIKI = ROOT / 'data/wiki_support_weapons.json'

REVIEWED = {
    'CQC-20 Breaching Hammer': {'branch': 'CQC-20 BREACHING HAMMER IE', 'role': 'ability',
        'explosion': 'support_weapon/cqc20_breaching_hammer/ability', 'component': 'MeleeWeaponComponentData',
        'abilityOffset': 160, 'abilitySlots': 8},
}
VIA = re.compile(r'^AbilityId (\d+) \((\w+) \+(\d+)\)$')
EXPLOSION_SETTINGS_TYPE = '0x2AEA2592'
DAMAGE_SETTINGS_TYPE = '0xE0A72CF0'
REASON = ("The Breaching Hammer's charge blast (published 2200 Explosion, Anti-Tank II): the explosion its own melee "
    'record requests through an ability (MeleeWeaponComponent ability slot -> the ability dispatcher -> this '
    'explosion row), proven from the game data and code; the row and its damage row have no other user. Every write '
    're-proves the ability slot and the rows. Not yet shown in game.')
MULTIPLAYER = ('A per-type settings row on each machine: the machine that simulates the blast reads its own copy (the '
    'host for the damage it deals). Install the mod on every machine for consistent results.')


def load():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    wiki = json.loads(WIKI.read_text(encoding='utf-8'))
    return {'research': research, 'wiki': wiki}


def _entry(data, name):
    spec = REVIEWED[name]
    entry = next(item for item in data['research']['explosions'] if item['name'] == spec['explosion'])
    owners = entry['owners']
    assert entry['evidenceTier'] == 'code' and entry['settingsVerified'] and not entry['shared'], \
        name + ': the ability explosion is no longer a verified unshared code-tier row'
    assert len(owners) == 1 and owners[0]['name'] == name and owners[0]['category'] == 'support weapon' \
        and owners[0]['role'] == 'ability', name + ': the ability explosion owner changed'
    match = VIA.match(owners[0]['via'])
    assert match and match.group(2) == spec['component'] and int(match.group(3)) == spec['abilityOffset'], \
        name + ': the ability slot changed: ' + owners[0]['via']
    damage = entry['stats']['damage']
    assert damage['users'] == 1 and not damage['statuses'], name + ': the ability explosion damage row is shared'
    return entry, int(match.group(1))


def _published(data, name, branch):
    weapon = next(item for item in data['wiki']['weapons'] if item.get('name') == name)
    return next(item for item in weapon['attacks'] if item['name'] == branch)


def _compare(entry, published):
    stats, damage = entry['stats'], entry['stats']['damage']
    area, effects = published['areaOfEffect'], published['specialEffects']
    pen = published['penetration']
    pairs = {'standard_damage': (damage['standard'], published['damage']['standard']['value']),
        'durable_damage': (damage['durable'], published['damage']['durable']['value']),
        'ap_direct': (damage['armorPenetration'][0], pen['direct']['value']),
        'ap_slight': (damage['armorPenetration'][1], pen['slightAngle']['value']),
        'ap_large': (damage['armorPenetration'][2], pen['largeAngle']['value']),
        'explosion_inner_radius': (stats['innerRadius'], area['innerRadiusMeters']['value']),
        'explosion_outer_radius': (stats['outerRadius'], area['outerRadiusMeters']['value']),
        'explosion_shockwave_radius': (stats['shockwaveRadius'], area['shockwaveRadiusMeters']['value']),
        'demolition': (damage['demolition'], effects['demolitionForce']['value']),
        'stagger': (damage['stagger'], effects['staggerForce']['value']),
        'push_force': (damage['pushForce'], effects['pushForce']['value'])}
    matched = sorted(key for key, (native, wiki) in pairs.items() if abs(float(native) - float(wiki)) < 1e-6)
    return matched, sorted(set(pairs) - set(matched))


def resolve_branches(weapon, data):
    """The published ability-explosion branch, RESOLVED on its own attack role (the read-only mapper only knew the
    weapon's own attacks)."""
    spec = REVIEWED.get(weapon['name'])
    if not spec:
        return weapon
    entry, _ = _entry(data, weapon['name'])
    matched, mismatched = _compare(entry, _published(data, weapon['name'], spec['branch']))
    assert not mismatched, weapon['name'] + ': the published ability explosion no longer matches: ' + str(mismatched)
    graph = []
    for branch in weapon['attackGraph']:
        if branch['name'] == spec['branch']:
            assert branch['state'] == 'UNRESOLVED', weapon['name'] + ': the ability branch was resolved elsewhere'
            branch = dict(branch, state='RESOLVED', resolvedBy='ability_explosion', unresolvedReason=None,
                runtimeMatch={'runtimeAttackRole': spec['role'], 'runtimeAttackKind': 'Explosion',
                    'runtimeParentRole': None, 'matchedFields': matched, 'mismatchedFields': [],
                    'compared': len(matched)})
        graph.append(branch)
    links = [reason for reason in weapon.get('unresolvedLinks') or [] if not reason.startswith(spec['branch'] + ':')]
    return dict(weapon, attackGraph=graph, unresolvedLinks=links)


def attack(weapon_name, data, candidate):
    """The candidate-shaped Explosion attack and the backing extras of its fields, or None."""
    spec = REVIEWED.get(weapon_name)
    if not spec:
        return None
    entry, ability = _entry(data, weapon_name)
    owner = candidate['ownership'][spec['component']]
    assert owner['uniqueOwner'] and owner['ownerCount'] == 1, weapon_name + ': the melee record is shared'
    stats, damage = entry['stats'], entry['stats']['damage']
    resolved = {'explosion_inner_radius': stats['innerRadius'], 'explosion_outer_radius': stats['outerRadius'],
        'explosion_shockwave_radius': stats['shockwaveRadius'], 'standard_damage': damage['standard'],
        'durable_damage': damage['durable'], 'ap_direct': damage['armorPenetration'][0],
        'ap_slight': damage['armorPenetration'][1], 'ap_large': damage['armorPenetration'][2],
        'ap_extreme': damage['armorPenetration'][3], 'demolition': damage['demolition'],
        'stagger': damage['stagger'], 'push_force': damage['pushForce']}
    extra = {'abilityRecord': {'component': spec['component'], 'recordIndex': owner['recordIndex'],
        'indexRow': owner['indexRow'], 'ownerCount': owner['ownerCount']}, 'abilityOffset': spec['abilityOffset'],
        'abilitySlots': spec['abilitySlots'], 'abilityId': ability, 'explosionType': entry['type']}
    return {'role': spec['role'], 'kind': 'Explosion', 'parentRole': None, 'statusEffects': {},
        'linkage': 'ability_explosion', 'backingExtra': extra, 'catalogueExplosion': spec['explosion'],
        'explosionSettings': {'group': 0, 'recordType': entry['type'], 'row': entry['row'],
            'settingsType': EXPLOSION_SETTINGS_TYPE},
        'damageInfo': {'group': 1, 'recordType': stats['damageType'], 'row': damage['row'],
            'settingsType': DAMAGE_SETTINGS_TYPE},
        'resolvedFields': resolved}


def annotate(fields, attack_entry):
    """Acknowledgement, effect and the catalogue name on every field of the ability explosion."""
    for field in fields:
        if not str(field['backing'].get('linkage') or '').startswith('ability_explosion'):
            continue
        field['acknowledgement'] = 'allow_unverified_effect'
        field['acknowledgementReason'] = REASON
        field['effect'] = {'activeSource': 'ACTIVE_DIRECT', 'activeSourceProven': True, 'appliesWhen': 'use',
            'instantiationOnly': False, 'gameplayEffectProven': False, 'unverifiedEffect': True,
            'writeVerifiedOnApply': True, 'reason': 'The ability requests this explosion row each time the charge '
                'blast goes off (native ability code); the row is read at the request.',
            'readTiming': 'each blast'}
        field['abilityExplosion'] = {'catalogueExplosion': attack_entry['catalogueExplosion'],
            'sameRowAs': "hd2.explosion('" + attack_entry['catalogueExplosion'] + "')",
            'multiplayer': MULTIPLAYER, 'research': 'research/explosion-identities-F5FEE03DCFDB.json'}
