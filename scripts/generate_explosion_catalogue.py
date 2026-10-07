"""Generate the explosion catalogue from research/explosion-identities-F5FEE03DCFDB.json.

Outputs:
* domains/explosion_catalogue.lua: every named explosion (research_explosion_identities.py) by its semantic id: its
  ExplosionSettings row identity (type, group, row, settings type: re-proven live before every write), its damage row
  (the +4 link), owners, sharing, the reviewed values of the editable fields, and its package dependency key
  (``explosion/<id>`` in domains/package_residency.lua). Runtime-only data: raw ids never reach the public API.
* sdk/ExplosionCatalogue.json: the public catalogue for ModBuilder (contract hd2runtime.explosion_catalogue.v1): names,
  labels, families, owners, sharing, package knowledge, stats and editable fields. No type, row, resource or package id.

Rules carried into the tables:
* every field of a catalogued explosion needs allow_unverified_effect (no edit through this target is live-tested);
  a row more than one owner requests, or a damage row more than one reference uses, also needs allow_shared;
* a payload (an impact or expiry explosion of a weapon projectile, an attack output slot, a custom projectile row) may
  reference an explosion whose package is known and is not an objective package; a donor without a live test needs
  allow_unverified_reference (and allow_unverified_effect, as every projectile donor);
* a spawn (hd2.explosions.spawn) needs a package (or the mission effects package resident) and the type proven against
  the settings table; an explosion outside the reviewed spawn set (event-actions: the named explosions and the
  catalogued weapon explosions) also needs allow_unverified_effect.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_entity_authoring  # noqa: E402
from migration import overlay as migration_overlay  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/explosion-identities-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
ACTIONS = ROOT / 'research/event-actions-F5FEE03DCFDB.json'
LUA_OUTPUT = ROOT / 'domains/explosion_catalogue.lua'
JSON_OUTPUT = ROOT / 'sdk/ExplosionCatalogue.json'
CONTRACT = 'hd2runtime.explosion_catalogue.v1'
# The editable fields: (id, backing row, offset, storage, type, unit, reviewed range). A range is widened to the largest
# reviewed default, so every row's own value can always be restored.
FIELDS = [
    ('explosion.inner_radius', 'explosion', 16, 'f32', 'number', 'meters', (0, 150)),
    ('explosion.outer_radius', 'explosion', 20, 'f32', 'number', 'meters', (0, 150)),
    ('explosion.shockwave_radius', 'explosion', 24, 'f32', 'number', 'meters', (0, 150)),
    ('explosion.shrapnel_count', 'explosion', 80, 'u32', 'integer', 'projectiles', (0, 64)),
    ('explosion.damage.standard_damage', 'damage', 4, 'i32', 'integer', 'damage', (0, 20000)),
    ('explosion.damage.durable_damage', 'damage', 8, 'i32', 'integer', 'damage', (0, 20000)),
    ('explosion.damage.ap_direct', 'damage', 12, 'u32', 'integer', 'armor_class', (0, 10)),
    ('explosion.damage.ap_slight', 'damage', 16, 'u32', 'integer', 'armor_class', (0, 10)),
    ('explosion.damage.ap_large', 'damage', 20, 'u32', 'integer', 'armor_class', (0, 10)),
    ('explosion.damage.ap_extreme', 'damage', 24, 'u32', 'integer', 'armor_class', (0, 10)),
    ('explosion.damage.demolition', 'damage', 28, 'u32', 'integer', 'force', (0, 200)),
    ('explosion.damage.stagger', 'damage', 32, 'u32', 'integer', 'force', (0, 500)),
    ('explosion.damage.push_force', 'damage', 36, 'u32', 'integer', 'force', (0, 5000)),
]
LABELS = {'explosion.inner_radius': 'Inner radius', 'explosion.outer_radius': 'Outer radius',
    'explosion.shockwave_radius': 'Shockwave radius', 'explosion.shrapnel_count': 'Shrapnel count',
    'explosion.damage.standard_damage': 'Standard damage', 'explosion.damage.durable_damage': 'Durable damage',
    'explosion.damage.ap_direct': 'AP: direct', 'explosion.damage.ap_slight': 'AP: slight angle',
    'explosion.damage.ap_large': 'AP: large angle', 'explosion.damage.ap_extreme': 'AP: extreme angle',
    'explosion.damage.demolition': 'Demolition', 'explosion.damage.stagger': 'Stagger',
    'explosion.damage.push_force': 'Push force'}
# Packages a payload may load: an objective package (the Cyborg Production Unit's effect and sound) is never one.
PAYLOAD_VIA = {'own_loadout_package', 'stratagem_call_in_package', 'effect_loadout_package', 'mission_effects_package',
    'named_explosion_package'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def value_of(field_id, stats):
    damage = stats.get('damage') or {}
    return {'explosion.inner_radius': stats['innerRadius'], 'explosion.outer_radius': stats['outerRadius'],
        'explosion.shockwave_radius': stats['shockwaveRadius'], 'explosion.shrapnel_count': stats['shrapnelCount'],
        'explosion.damage.standard_damage': damage.get('standard'), 'explosion.damage.durable_damage': damage.get('durable'),
        'explosion.damage.ap_direct': (damage.get('armorPenetration') or [None] * 4)[0],
        'explosion.damage.ap_slight': (damage.get('armorPenetration') or [None] * 4)[1],
        'explosion.damage.ap_large': (damage.get('armorPenetration') or [None] * 4)[2],
        'explosion.damage.ap_extreme': (damage.get('armorPenetration') or [None] * 4)[3],
        'explosion.damage.demolition': damage.get('demolition'), 'explosion.damage.stagger': damage.get('stagger'),
        'explosion.damage.push_force': damage.get('pushForce')}[field_id]


def outputs(research_path=RESEARCH):
    research = load(research_path)
    residency = load(RESIDENCY)['catalog']
    actions = load(ACTIONS)
    layout = research['layout']
    named = [r for r in research['explosions'] if r['name']]
    # The reviewed spawn set (domains/event_natives.lua explosion): named explosions and catalogued weapon explosions.
    legacy = {item['type']: {'kind': 'named', 'name': item['name']} for item in actions['namedExplosions']}
    for item in actions['catalogueTypes']:
        legacy.setdefault(item['type'], {'kind': 'weapon', 'name': item['weapon']})
    ranges = {}
    for field_id, _backing, _offset, _storage, _type, _unit, (low, high) in FIELDS:
        values = [value_of(field_id, r['stats']) for r in named if value_of(field_id, r['stats']) is not None]
        ranges[field_id] = (min([low] + values), max([high] + values))
    runtime, public = {}, []
    for item in named:
        stats, package = item['stats'], item['package']
        key = 'explosion/' + item['name']
        dependency = residency.get(key)
        known = bool(package and dependency and dependency['known'])
        damage = stats.get('damage')
        fields = {}
        for field_id, backing, offset, storage, kind, unit, _range in FIELDS:
            value = value_of(field_id, stats)
            editable, reason = True, None
            if backing == 'damage' and not damage:
                editable, reason = False, 'the explosion links no DamageInfo row (+4 is 0)'
            elif field_id == 'explosion.shrapnel_count' and not stats['shrapnelProjectile']:
                editable, reason = False, 'the explosion releases no shrapnel projectile (+84 is 0)'
            shared = item['shared'] if backing == 'explosion' else bool(damage and damage['users'] > 1)
            fields[field_id] = {'backing': backing, 'offset': offset, 'storage': storage, 'type': kind, 'unit': unit,
                'currentDefault': value, 'editable': editable, 'reason': reason, 'shared': shared,
                'range': {'min': ranges[field_id][0], 'max': ranges[field_id][1]}}
        via = package and package['via']
        payload = known and via in PAYLOAD_VIA and not (item['type'] in legacy and legacy[item['type']]['kind'] == 'named'
            and legacy[item['type']]['name'] == 'Cyborg Production Unit')
        owners = []
        for owner in item['owners']:
            entry = {'category': owner.get('category'), 'name': owner.get('name'), 'role': owner.get('role'),
                'reference': owner.get('reference')}
            if entry not in owners:
                owners.append(entry)
        runtime[item['name']] = {'label': item['label'], 'family': item['family'], 'type': item['type'],
            'row': item['row'], 'group': layout['settingsGroup']['group'],
            'settingsType': layout['settingsGroup']['settingsType'], 'shared': item['shared'],
            'evidence': item['evidenceTier'], 'owners': owners, 'ownerCount': item['ownerCount'],
            'damage': {'type': stats['damageType'], 'row': damage['row'], 'group': layout['damageGroup']['group'],
                'settingsType': layout['damageGroup']['settingsType'], 'users': damage['users'],
                'shared': damage['users'] > 1} if damage else None,
            'shrapnel': stats['shrapnelProjectile'] != 0, 'arc': stats['arc'] != 0,
            'package': {'key': key, 'via': via, 'mission': bool(package.get('mission')), 'name': package.get('name'),
                'bytes': package.get('bytes')} if known else None,
            'payload': payload, 'spawn': bool(item['settingsVerified'] and known),
            'legacy': legacy.get(item['type']), 'values': [fields[f[0]]['currentDefault'] for f in FIELDS]}
        public.append({'name': item['name'], 'label': item['label'], 'family': item['family'],
            'evidence': item['evidenceTier'], 'shared': item['shared'], 'owners': owners,
            'package': {'known': known, 'name': (package or {}).get('name') if known else None,
                'via': via if known else None, 'mission': bool(known and package.get('mission'))},
            'payload': payload, 'spawn': runtime[item['name']]['spawn'],
            'reviewedSpawn': item['type'] in legacy, 'legacyName': (legacy.get(item['type']) or {}).get('name'),
            'stats': {'innerRadius': stats['innerRadius'], 'outerRadius': stats['outerRadius'],
                'shockwaveRadius': stats['shockwaveRadius'], 'shrapnel': stats['shrapnelProjectile'] != 0,
                'shrapnelCount': stats['shrapnelCount'], 'arc': stats['arc'] != 0,
                'damage': {k: damage[k] for k in ('standard', 'durable', 'armorPenetration', 'demolition', 'stagger',
                    'pushForce')} if damage else None},
            'values': {field_id: f['currentDefault'] for field_id, f in fields.items()},
            'readOnly': {field_id: f['reason'] for field_id, f in fields.items() if not f['editable']},
            'damageShared': bool(damage and damage['users'] > 1)})
    unnamed = {}
    for item in research['explosions']:
        if not item['name']:
            unnamed[item['unnamedReason']] = unnamed.get(item['unnamedReason'], 0) + 1
    table = {'version': 1, 'build': research['build'], 'explosions': runtime, 'order': sorted(runtime),
        'layout': {'damageLink': layout['ExplosionSettings']['damageType'], 'stride': layout['ExplosionSettings']['stride']},
        'fields': [{'id': f[0], 'backing': f[1], 'offset': f[2], 'storage': f[3], 'type': f[4], 'unit': f[5],
            'min': ranges[f[0]][0], 'max': ranges[f[0]][1]} for f in FIELDS]}
    families = {}
    for item in public:
        families[item['family']] = families.get(item['family'], 0) + 1
    document = {'contract': CONTRACT, 'schemaVersion': 1, 'build': research['build'],
        'source': 'research/explosion-identities-F5FEE03DCFDB.json (scripts/research_explosion_identities.py)',
        'model': ['An explosion is one row of the game\'s ExplosionSettings table; its damage is the DamageInfo row its '
            '+4 member links. A row is named from what requests it: a projectile\'s impact or expiry, an entity\'s '
            'explosive, mine, backblast, crash or gib member, or a code literal of a behavior or ability.',
            'Editing a row changes every owner that requests it: shared rows need allow_shared. No edit through '
            'hd2.explosion(name) is live-tested: every field needs allow_unverified_effect.',
            'A payload (terminal.explosion, projectile.impact_explosion / expiry_explosion, custom projectile rows) '
            'may reference an explosion whose package is known (payload = true); the package is loaded before the '
            'write, or, for the mission effects package, is resident in every mission. Such a donor needs '
            'allow_unverified_reference and allow_unverified_effect.',
            'hd2.explosions.spawn requests any explosion with spawn = true (host only, rate-limited, credited to the '
            'local player); outside the reviewed spawn set (reviewedSpawn) it needs allow_unverified_effect.'],
        'fields': [{'id': f[0], 'label': LABELS[f[0]], 'backing': f[1], 'type': f[4], 'unit': f[5],
            'range': {'min': ranges[f[0]][0], 'max': ranges[f[0]][1]},
            'shared': 'allow_shared when the explosion (backing explosion) or its damage row (backing damage) is shared',
            'acknowledgements': ['allow_unverified_effect']} for f in FIELDS],
        'summary': {'named': len(public), 'types': len(research['explosions']), 'byFamily': dict(sorted(families.items())),
            'shared': sum(1 for p in public if p['shared']), 'packageKnown': sum(1 for p in public if p['package']['known']),
            'payload': sum(1 for p in public if p['payload']), 'spawn': sum(1 for p in public if p['spawn']),
            'reviewedSpawn': sum(1 for p in public if p['reviewedSpawn']), 'unnamed': dict(sorted(unnamed.items()))},
        'explosions': public, 'safety': {'rawIds': False, 'writes': 0}}
    lua = ('-- Generated by scripts/generate_explosion_catalogue.py from research/explosion-identities-F5FEE03DCFDB.json;'
        ' do not edit.\nreturn ' + generate_entity_authoring.lua(migration_overlay.apply('explosion_catalogue', table))
        + '\n')
    return {LUA_OUTPUT: lua, JSON_OUTPUT: json.dumps(document, indent=2) + '\n'}


def generate(check=False, research_path=RESEARCH):
    stale = []
    for path, body in outputs(research_path).items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                with open(path, 'w', encoding='utf-8', newline='') as handle:
                    handle.write(body)
    if check and stale:
        raise RuntimeError('Stale explosion catalogue outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(args.check)) or 'up to date')
