"""Trace enemy and enemy-structure attacks to their native settings rows and cross-check them with the wiki. Read-only.

Chain (structural, the same one research_vehicle_weapons.py proves for player vehicles):
  enemy class (research/enemy-authoring-F5FEE03DCFDB.json) -> MountComponentData slot (24-byte MountInfo, path +0)
    -> mounted weapon entity (the slot path; WeaponData plus a Projectile/Spray/Beam/Arc weapon component)
    -> ProjectileWeaponComponentData +0 projectile type -> ProjectileSettings row -> +60 DamageInfo row;
       impact/expiry explosions (+144/+156) -> ExplosionSettings -> +4 DamageInfo
    -> SprayWeaponComponentData +200 DamageInfo row

Settings rows are resolved by the production resolver against the retained snapshot. Each DamageInfo row is then
compared with the ranged attacks of the wiki page(s) the class is named by or a candidate for: a match needs all nine
published values equal (standard and durable damage, the four AP values, demolition, stagger and push force). Nine
equal values on a row the class's own mount chain reaches is the identity proof; a row that matches nothing (or
whose class has no wiki page) keeps its native identity only.

Output: research/enemy-attacks-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
from research_attachment_presets import _module_sources, _lua  # noqa: E402
from tools.lua_runner import execute  # noqa: E402

OUTPUT = ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json'
ENEMIES = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_enemies.json'
SNAPSHOT = build_profile.SNAPSHOT
MOUNT_SLOT, MOUNT_SLOTS = 24, 5
WEAPON_COMPONENTS = ('ProjectileWeaponComponentData', 'SprayWeaponComponentData', 'BeamWeaponComponentData',
    'ArcWeaponComponentData')
COMPONENTS = ('MountComponentData', 'WeaponDataComponentData') + WEAPON_COMPONENTS
DAMAGE_KEYS = ('standard_damage', 'durable_damage', 'ap_direct', 'ap_slight', 'ap_large', 'ap_extreme', 'demolition',
    'stagger', 'push_force')


def u32(body, at):
    return struct.unpack_from('<I', body, at)[0]


def wiki_tuple(attack):
    """The nine published values of a wiki attack, or None when any is missing."""
    damage, pen, forces = attack.get('damage') or {}, attack.get('penetration') or {}, attack.get('specialEffects') or {}
    values = [(damage.get('standard') or {}).get('value'), (damage.get('durable') or {}).get('value')]
    values += [(pen.get(key) or {}).get('value') for key in ('direct', 'slightAngle', 'largeAngle', 'extremeAngle')]
    values += [(forces.get(key) or {}).get('value') for key in ('demolitionForce', 'staggerForce', 'pushForce')]
    return None if any(value is None for value in values) else tuple(values)


def wiki_explosion(attack):
    """(standard damage, inner, outer, shockwave radius) of a wiki attack's explosion, or None if any is missing."""
    explosion = attack.get('explosion') or {}
    area = explosion.get('areaOfEffect') or {}
    values = [((explosion.get('damage') or {}).get('standard') or {}).get('value')]
    values += [(area.get(key) or {}).get('value') for key in ('innerRadiusMeters', 'outerRadiusMeters',
        'shockwaveRadiusMeters')]
    return None if any(value is None for value in values) else tuple(values)


def explosion_tuple(damage_values, explosion_values):
    if not damage_values or not explosion_values:
        return None
    return (damage_values['standard_damage'], round(explosion_values['inner_radius'], 4),
        round(explosion_values['outer_radius'], 4), round(explosion_values['shockwave_radius'], 4))


def resolve_settings(projectile_types, spray_types):
    preload = '\n'.join('package.preload[' + _lua(name) + ']=function(...) return assert(loadstring(' + _lua(body)
        + ',' + _lua(name) + '))(...) end' for name, body in _module_sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(SNAPSHOT)) + r''',{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{projectile=true,damage=true,explosion=true})
 local function id(r)return r and {group=r.group,row=r.row,recordType=r.kind}end
 local function damage(t)
  local dr=roots.damage.records[t];local item={type=t,settings=id(dr)}
  if dr then item.values={standard_damage=b.value(dr.bytes,4,'i32'),durable_damage=b.value(dr.bytes,8,'i32'),
   ap_direct=b.u32(dr.bytes,12),ap_slight=b.u32(dr.bytes,16),ap_large=b.u32(dr.bytes,20),ap_extreme=b.u32(dr.bytes,24),
   demolition=b.u32(dr.bytes,28),stagger=b.u32(dr.bytes,32),push_force=b.u32(dr.bytes,36)}end
  return item
 end
 local out={projectiles={},spray={}}
 for _,t in ipairs(''' + _lua(spray_types) + r''')do out.spray[#out.spray+1]=damage(t)end
 for _,t in ipairs(''' + _lua(projectile_types) + r''')do
  local p=roots.projectile.records[t];local item={type=t,settings=id(p)}
  if p then
   item.values={pellet_count=b.u32(p.bytes,28),velocity=b.value(p.bytes,32,'f32'),mass=b.value(p.bytes,36,'f32'),
    drag=b.value(p.bytes,40,'f32'),gravity=b.value(p.bytes,44,'f32'),lifetime=b.value(p.bytes,52,'f32'),
    penetration_slowdown=b.value(p.bytes,64,'f32')}
   item.damage=damage(b.u32(p.bytes,60));item.explosions={}
   for phase,o in pairs({impact=144,expiry=156})do
    local e=b.u32(p.bytes,o)
    if e~=0 then
     local er=roots.explosion.records[e];local x={type=e,settings=id(er)}
     if er then
      x.values={inner_radius=b.value(er.bytes,16,'f32'),outer_radius=b.value(er.bytes,20,'f32'),
       shockwave_radius=b.value(er.bytes,24,'f32')}
      x.damage=damage(b.u32(er.bytes,4))
     end
     item.explosions[phase]=x
    end
   end
  end
  out.projectiles[#out.projectiles+1]=item
 end
 reader.verify();source.close()
 return out
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    return json.loads(execute(program.encode()))


def build() -> dict:
    native = entity_research.Native()
    enemies = json.loads(ENEMIES.read_text(encoding='utf-8'))['classes']
    owners = {c: native.owners(c) for c in COMPONENTS}
    rows = defaultdict(dict)
    for component in COMPONENTS:
        body, capacity, _, _, _ = native.table(component)
        for row in range(capacity):
            resource, record, _ = struct.unpack_from('<QII', body, row * 16)
            if resource:
                rows[component].setdefault(resource, []).append((row, record))

    def ownership(resource):
        result = {}
        for component in COMPONENTS:
            found = rows[component].get(resource, [])
            if len(found) == 1:
                row, record = found[0]
                count = len(owners[component].get(record, []))
                result[component] = {'recordIndex': record, 'indexRow': row, 'ownerCount': count,
                    'uniqueOwner': count == 1}
            elif len(found) > 1:
                result[component] = {'ambiguous': True}
        return result

    classes, projectile_types, spray_types = [], set(), set()
    for item in enemies:
        resource = int(item['resource'], 16)
        mount = ownership(resource).get('MountComponentData')
        if not mount or mount.get('ambiguous'):
            continue
        body = native.record('MountComponentData', mount['recordIndex'])
        slots = []
        for index in range(MOUNT_SLOTS):
            path = struct.unpack_from('<Q', body, index * MOUNT_SLOT)[0]
            if not path:
                continue
            own = ownership(path)
            slot = {'slot': index, 'weapon': f'0x{path:016X}', 'weaponPath': native.path(path),
                'components': sorted(own)}
            try:
                slot['weaponEntityRow'] = native.entity_row(path)
            except ValueError:
                slot['weaponEntityRow'] = None
            weapon = next((c for c in WEAPON_COMPONENTS if c in own and not own[c].get('ambiguous')), None)
            if 'WeaponDataComponentData' in own and weapon:
                slot['family'] = weapon.removesuffix('WeaponComponentData').lower()
                slot['weaponComponent'] = dict(own[weapon], component=weapon)
                raw = native.record(weapon, own[weapon]['recordIndex'])
                if weapon == 'ProjectileWeaponComponentData':
                    slot['projectileType'] = u32(raw, 0)
                    projectile_types.add(slot['projectileType'])
                elif weapon == 'SprayWeaponComponentData':
                    slot['sprayDamageType'] = u32(raw, 200)
                    spray_types.add(slot['sprayDamageType'])
            slots.append(slot)
        classes.append({'name': item['wikiName'] or item['className'], 'className': item['className'],
            'resource': item['resource'], 'entityRow': item['entityRow'],
            'kind': item['kind'], 'faction': item['faction'], 'wikiName': item['wikiName'],
            'wikiCandidates': item['wikiCandidates'], 'mount': mount, 'slots': slots})

    settings = resolve_settings(sorted(projectile_types), sorted(spray_types))
    projectiles = {p['type']: p for p in settings['projectiles']}
    sprays = {s['type']: s for s in settings['spray']}

    # Every entity firing a projectile type / spraying a damage type (shared-scope publication).
    fired_by = defaultdict(set)
    for record, resources in owners['ProjectileWeaponComponentData'].items():
        kind = u32(native.record('ProjectileWeaponComponentData', record), 0)
        fired_by[('projectile', kind)].update(resources)
    for record, resources in owners['SprayWeaponComponentData'].items():
        kind = u32(native.record('SprayWeaponComponentData', record), 200)
        fired_by[('spray', kind)].update(resources)

    wiki = {page['name']: page for page in json.loads(WIKI.read_text(encoding='utf-8'))['enemies']}

    ranged = [(page['name'], attack) for page in wiki.values() for attack in page.get('attacks') or []
        if attack.get('delivery') == 'Ranged' and wiki_tuple(attack)]

    def row_matches(values):
        """Row-level correlation: every wiki ranged attack (any page) with the same nine values. Describes the
        shared settings row, not the class."""
        if not values:
            return []
        row = tuple(values[key] for key in DAMAGE_KEYS)
        return sorted({page + ': ' + attack['name'] for page, attack in ranged if wiki_tuple(attack) == row})

    explosions = [(page['name'], attack) for page in wiki.values() for attack in page.get('attacks') or []
        if wiki_explosion(attack)]

    def explosion_matches(item, native, own_pages):
        """Wiki attack explosions equal to this explosion (standard damage and all three radii)."""
        if not native:
            return []
        pages = set([item['wikiName']] if item['wikiName'] else item['wikiCandidates'])
        return sorted({(page if own_pages else page) + ': ' + attack['name'] for page, attack in explosions
            if wiki_explosion(attack) == native and (not own_pages or page in pages)})

    def matches(item, values):
        """Wiki ranged attacks (of the class's named or candidate pages) whose nine values equal this row's."""
        if not values:
            return []
        row = tuple(values[key] for key in DAMAGE_KEYS)
        found = []
        for page in [item['wikiName']] if item['wikiName'] else item['wikiCandidates']:
            for attack in (wiki.get(page) or {}).get('attacks') or []:
                if wiki_tuple(attack) == row:
                    found.append({'page': page, 'attack': attack['name'], 'delivery': attack.get('delivery')})
        return found

    summary = defaultdict(int)
    for item in classes:
        for slot in item['slots']:
            branches = []
            if 'projectileType' in slot:
                p = projectiles.get(slot['projectileType']) or {}
                slot['projectile'] = {k: p.get(k) for k in ('type', 'settings', 'values')}
                slot['projectileConsumers'] = len(fired_by[('projectile', slot['projectileType'])])
                if p.get('damage'):
                    branches.append(('projectile', p['damage']))
                for phase, explosion in sorted((p.get('explosions') or {}).items()):
                    slot.setdefault('explosions', {})[phase] = {k: explosion.get(k) for k in ('type', 'settings', 'values')}
                    if explosion.get('damage'):
                        branches.append(('explosion_' + phase, explosion['damage']))
            if 'sprayDamageType' in slot:
                branches.append(('spray', sprays.get(slot['sprayDamageType']) or {'type': slot['sprayDamageType']}))
                slot['sprayConsumers'] = len(fired_by[('spray', slot['sprayDamageType'])])
            slot['damage'] = []
            for role, damage in branches:
                hit = matches(item, damage.get('values'))
                entry = {'role': role, 'type': damage['type'], 'settings': damage.get('settings'),
                    'values': damage.get('values'), 'wikiMatches': hit, 'rowWikiMatches': row_matches(damage.get('values'))}
                if role.startswith('explosion_'):
                    explosion = (p.get('explosions') or {}).get(role.replace('explosion_', '')) or {}
                    native = explosion_tuple(damage.get('values'), explosion.get('values'))
                    entry['explosionWikiMatches'] = explosion_matches(item, native, True)
                    entry['explosionRowWikiMatches'] = explosion_matches(item, native, False)
                    summary['explosionRows'] += 1
                    summary['explosionRowsWikiMatchedForClass'] += bool(entry['explosionWikiMatches'])
                    summary['explosionRowsWikiMatchedAnyPage'] += bool(entry['explosionRowWikiMatches'])
                slot['damage'].append(entry)
                summary['damageRows'] += 1
                summary['wikiMatchedRows'] += bool(hit)
            summary['weaponSlots'] += bool(slot.get('family'))
            summary['slots'] += 1
    reached = defaultdict(set)
    for item in classes:
        for slot in item['slots']:
            for damage in slot.get('damage', []):
                reached[damage['type']].add(item['name'])
    for item in classes:
        for slot in item['slots']:
            for damage in slot.get('damage', []):
                damage['reviewedClassesReachingRow'] = sorted(reached[damage['type']])
    summary['classesWithMounts'] = len(classes)
    summary['classesWithWeapons'] = sum(1 for c in classes if any(s.get('family') for s in c['slots']))
    wiki_ranged = [(page['name'], a['name']) for page in wiki.values() for a in page.get('attacks') or []
        if a.get('delivery') == 'Ranged']
    matched = {(m['page'], m['attack']) for c in classes for s in c['slots'] for d in s['damage']
        for m in d['wikiMatches']}
    summary['wikiRangedAttacks'] = len(wiki_ranged)
    summary['wikiRangedAttacksMatched'] = sum(1 for key in wiki_ranged if key in matched)
    return {'schemaVersion': 1, 'snapshot': SNAPSHOT.name, 'entitiesSha256': entity_research.ENTITY_SHA256,
        'writes': 0, 'fixtureFallback': 'disabled', 'damageKeys': list(DAMAGE_KEYS), 'summary': dict(summary),
        'classes': classes}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
