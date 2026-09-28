"""Capture native evidence for the 0.24 support-weapon coverage pass.

Three independent results, all read-only:

1. ProjectileInfo lifetime (+52) and penetration slowdown (+64). The pinned type
   library's hidden member-name lengths (9 = life_time, 20 = penetration_slowdown)
   disagree with filediver's LifeTime label (+56). Exact correlation with scraped
   per-attack values, joined on a unique four-value physics fingerprint, decides it.
2. WeaponReloadComponentData.Duration (+56) and WeaponWindUpComponentData wind-up /
   wind-down (+0/+4), identified by member-name length in the pinned type library.
   A reload duration of 0 means "use the ability's default duration", so those
   weapons have no scalar owner and stay read-only.
3. Duplicate-root weapons. A root is resolved only if the linked call-in
   StratagemDefinition's hellpod rack attaches exactly one candidate root AND the
   scraped magazine tuple matches that root exactly while differing from the others.
   Structural delivery alone does not unlock a weapon.

The live snapshot is used to prove that every relied-on native table is byte-identical
to the pinned reference. Scraped values are fingerprints only; they never establish
ownership. Nothing writes memory.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
import snapshot_regions
import support_callin_linkage

WIKI = ROOT.parent / 'HD2WikiImporter/output'
CATALOG = ROOT / 'schemas/support_weapon_authoring_catalog.json'
OUTPUT = ROOT / 'research/support-weapon-coverage-F5FEE03DCFDB.json'
PROJECTILE_PIN = entity_research.FILEDIVER / 'datalibrary/generated_projectile_settings.dl_bin'
PROJECTILE_ROWS, PROJECTILE_ROOT, PROJECTILE_STRIDE = 350, 44, 272
COMPONENTS = ('WeaponReloadComponentData', 'WeaponWindUpComponentData', 'WeaponMagazineComponentData',
    'ProjectileWeaponComponentData', 'HellpodRackComponentData')
FIELD_NAMES = {  # expected hidden member-name lengths
    ('ProjectileInfo', 52): ('projectile.lifetime', 'life_time'),
    ('ProjectileInfo', 64): ('projectile.penetration_slowdown', 'penetration_slowdown'),
    ('WeaponReloadComponent', 56): ('reload.duration', 'duration'),
    ('WeaponWindUpComponent', 0): ('windup.wind_up_seconds', 'wind_up_time'),
    ('WeaponWindUpComponent', 4): ('windup.wind_down_seconds', 'wind_down_time'),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def wiki_value(item):
    return item.get('value') if isinstance(item, dict) else None


def member_names(native):
    result = {}
    for (type_name, offset), (field, name) in FIELD_NAMES.items():
        desc = native.typelib_module.layout(native.typelib, type_name, structured=True)
        member = next(m for m in desc['members'] if m['offset64'] == offset)
        length = int(member['name'].rsplit('=', 1)[1])
        if length != len(name):
            raise ValueError(f'{type_name}+{offset} name length {length} != {name}')
        result[field] = {'type': type_name, 'offset': offset, 'storage': member['storage'],
            'hiddenNameLength': length, 'matchesName': name}
    # The competing filediver label: +56 is not life_time (length 20).
    desc = native.typelib_module.layout(native.typelib, 'ProjectileInfo', structured=True)
    member = next(m for m in desc['members'] if m['offset64'] == 56)
    conflict = {'filediverLabel': 'LifeTime at +56', 'hiddenNameLengthAt56': int(member['name'].rsplit('=', 1)[1]),
        'resolution': '+56 cannot be life_time (9); +52 matches by length and by exact correlation'}
    return result, conflict


def projectile_evidence(live):
    rows = {}
    for row in range(PROJECTILE_ROWS):
        at = PROJECTILE_ROOT + row * PROJECTILE_STRIDE
        rows[row] = {'type': struct.unpack_from('<I', live, at)[0],
            'pellets': struct.unpack_from('<I', live, at + 28)[0],
            'physics': tuple(round(v, 4) for v in struct.unpack_from('<4f', live, at + 32)),
            52: f32(live, at + 52), 56: f32(live, at + 56), 64: f32(live, at + 64)}
    index = collections.defaultdict(list)
    for row, item in rows.items():
        index[item['physics']].append(row)
    tallies = {name: collections.Counter() for name in ('lifetime52', 'lifetime56', 'penetration56', 'penetration64')}
    samples, joined = [], set()
    for file_name in ('wiki_support_weapons.json', 'wiki_player_weapons.json'):
        for weapon in json.loads((WIKI / file_name).read_text(encoding='utf-8'))['weapons']:
            for attack in weapon.get('attacks', []):
                p = attack.get('projectile') or {}
                physics = (wiki_value(p.get('initialVelocityMetersPerSecond')), wiki_value(p.get('massGrams')),
                    wiki_value(p.get('dragFactor')), wiki_value(p.get('gravityFactor')))
                if None in physics:
                    continue
                key = tuple(round(float(v), 4) for v in physics)
                matches = index.get(key, [])
                if len(matches) != 1 or matches[0] in joined:
                    continue
                row = matches[0]
                joined.add(row)
                lifetime, slowdown = wiki_value(p.get('lifetimeSeconds')), wiki_value(p.get('penetrationSlowdown'))
                item = rows[row]
                if lifetime is not None:
                    tallies['lifetime52'][abs(item[52] - lifetime) < 1e-4] += 1
                    tallies['lifetime56'][abs(item[56] - lifetime) < 1e-4] += 1
                    samples.append({'weapon': weapon['name'], 'attack': attack.get('name'),
                        'wikiLifetime': lifetime, 'native52': item[52], 'native56': item[56]})
                if slowdown is not None:
                    tallies['penetration56'][abs(item[56] - slowdown) < 1e-4] += 1
                    tallies['penetration64'][abs(item[64] - slowdown) < 1e-4] += 1
    correlation = {name: {'matches': tally[True], 'mismatches': tally[False]} for name, tally in tallies.items()}
    if correlation['lifetime52']['mismatches'] or not correlation['lifetime52']['matches'] \
            or correlation['penetration64']['mismatches'] or correlation['lifetime56']['matches']:
        raise ValueError('projectile field correlation no longer decisive: ' + json.dumps(correlation))
    return rows, {'join': 'unique four-value physics fingerprint (velocity, mass, drag, gravity)',
        'joinedRows': len(joined), 'results': correlation, 'lifetimeSamples': samples}


def main():
    native = entity_research.Native()
    names, conflict = member_names(native)
    base, live_projectile = snapshot_regions.region_bytes('projectile')
    projectile_equality = snapshot_regions.compare_pinned(live_projectile, base, PROJECTILE_PIN.read_bytes())
    if not projectile_equality['identical']:
        raise ValueError('live ProjectileSettings differ from the pinned reference')
    entity_base, live_entity = snapshot_regions.region_bytes('entity')
    tables = {}
    for name in COMPONENTS:
        _, _, _, _, offset = native.probe.find_component(native.entities, name)
        _, capacity, record_offset, size, count = native.table(name)
        start = offset + 28
        spans = ((offset, start + capacity * 16), (start + record_offset, start + record_offset + count * size))
        equal = all(live_entity[a:b] == native.entities[a:b] for a, b in spans)
        if not equal:
            raise ValueError(f'live {name} table differs from the pinned reference')
        tables[name] = {'indexAndRecordsIdentical': True, 'records': count, 'stride': size}
    rows, correlation = projectile_evidence(live_projectile)

    catalog = json.loads(CATALOG.read_text())
    wiki = {w['name']: w for w in json.loads((WIKI / 'wiki_support_weapons.json').read_text(encoding='utf-8'))['weapons']}
    owners = {name: native.owners(name) for name in ('WeaponReloadComponentData', 'WeaponWindUpComponentData')}

    def component(resource, name):
        found = native.component(resource, name)
        if not found:
            return None
        ownership = native.ownership(found)
        return {'recordIndex': found['record_index'], 'indexRow': found['index_row'],
            'ownerCount': ownership['ownerCount'], 'uniqueOwner': ownership['uniqueOwner'],
            'raw': native.record(name, found['record_index'])}

    # Delivery resolution for duplicate roots.
    roots = json.loads(support_callin_linkage.STRATAGEM_RESEARCH.read_text())['supportRoots']
    graph = json.loads(support_callin_linkage.SUPPORT_RESEARCH.read_text())['nativeSupportGraph']
    racks = {rack['resourceHash']: rack for rack in graph['hellpodRacks']}
    roots_by_name = {root['name']: root for root in roots}
    delivery = {}
    for weapon in catalog['weapons']:
        if weapon['resolution'] != 'DUPLICATE':
            continue
        name = weapon['name']
        root = roots_by_name.get(name)
        candidates = set(weapon['resources'])
        entry = {'candidates': sorted(candidates), 'decision': 'BLOCKED'}
        if not root or root['resolution'] != 'UNIQUE':
            entry['reason'] = 'No uniquely correlated call-in StratagemDefinition; delivered root unknown.'
            delivery[name] = entry
            continue
        rack = racks.get(root['currentRoot']['payloads'][0])
        attached = set(rack['attachedResources']) if rack else set()
        delivered = sorted(attached & candidates)
        entry.update({'callIn': {'id': root['currentRoot']['id'], 'package': root['currentRoot']['package'],
            'recordKind': root['currentRoot']['record_kind']},
            'rack': rack and {k: rack[k] for k in ('resourceHash', 'entityRow', 'recordIndex', 'attachedResources')},
            'structurallyDelivered': delivered})
        ammo = wiki[name]['mechanics'].get('ammo') or {}
        expected = tuple(wiki_value(ammo.get(k)) for k in
            ('capacity', 'startingMagazines', 'magazinesFromSupply', 'spareMagazines'))
        prints = []
        for resource in sorted(candidates):
            magazine = component(resource, 'WeaponMagazineComponentData')
            tuple_ = list(struct.unpack_from('<4I', magazine['raw'], 136)) if magazine else None
            prints.append({'resource': resource, 'delivered': resource in delivered,
                'nativeMagazine': tuple_, 'matchesWiki': tuple_ is not None and None not in expected
                    and tuple(tuple_) == tuple(int(v) for v in expected)})
        entry['fingerprint'] = {'wikiMagazine': list(expected), 'roots': prints}
        confirmed = [p for p in prints if p['matchesWiki']]
        if len(delivered) != 1:
            entry['reason'] = 'Call-in rack does not attach exactly one candidate root.'
        elif len(confirmed) != 1 or not confirmed[0]['delivered']:
            entry['reason'] = ('Structural delivery is unique, but scraped magazine values do not independently '
                'identify the delivered root (identical alternative or conflicting values).')
        else:
            entry.update({'decision': 'RESOLVED', 'deliveredRoot': delivered[0],
                'reason': 'Call-in rack attaches exactly this root, and its native magazine tuple alone matches '
                    'the scraped values.'})
        delivery[name] = entry

    resolved_roots = {name: item['deliveredRoot'] for name, item in delivery.items() if item['decision'] == 'RESOLVED'}
    weapons = {}
    for weapon in catalog['weapons']:
        name = weapon['name']
        resource = resolved_roots.get(name) or (weapon['attackResource'] if weapon['resolution'] == 'UNIQUE' else None)
        entry = {}
        if resource:
            reload = component(resource, 'WeaponReloadComponentData')
            reload_wiki = [x['value'] for x in (wiki[name]['mechanics'].get('reload') or {}).get('full', [])
                if x.get('variant') in ('base', None)]
            if reload:
                duration = f32(reload['raw'], 56)
                entry['reload'] = {k: reload[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}
                entry['reload'].update({'resource': resource, 'duration': duration, 'wikiFullReload': reload_wiki,
                    'writable': duration > 0 and reload['uniqueOwner'],
                    'reason': None if duration > 0 else
                        'Native duration 0 means the reload ability default duration applies; no scalar owner.'})
            windup = component(resource, 'WeaponWindUpComponentData')
            if windup:
                fire = wiki[name]['mechanics'].get('fireRate') or {}
                entry['windUp'] = {k: windup[k] for k in ('recordIndex', 'indexRow', 'ownerCount', 'uniqueOwner')}
                entry['windUp'].update({'resource': resource, 'windUpSeconds': f32(windup['raw'], 0),
                    'windDownSeconds': f32(windup['raw'], 4), 'wikiSpinUp': wiki_value(fire.get('spinUpSeconds')),
                    'wikiWindDown': wiki_value(fire.get('windDownSeconds'))})
        weapons[name] = entry

    rows_used = {}
    for candidate in catalog['candidates'].values():
        for attack in candidate['attacks']:
            record = attack.get('projectileSettings')
            if record and record['group'] == 0:
                row = rows[record['row']]
                if row['type'] != record['recordType']:
                    raise ValueError('projectile row type changed')
                rows_used[str(record['row'])] = {'recordType': record['recordType'],
                    'lifetime': row[52], 'penetrationSlowdown': row[64]}

    report = {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'pinnedReferences': {'entities': sha(native.entities), 'typelib': sha(native.typelib),
            'projectileSettings': sha(PROJECTILE_PIN.read_bytes())},
        'wikiDataset': {name: sha((WIKI / name).read_bytes())
            for name in ('wiki_support_weapons.json', 'wiki_player_weapons.json')},
        'liveEquality': {'projectileSettings': projectile_equality, 'entityTables': tables},
        'fieldLayout': names, 'projectileLabelConflict': conflict, 'projectileCorrelation': correlation,
        'projectileRows': dict(sorted(rows_used.items(), key=lambda item: int(item[0]))),
        'weapons': weapons, 'deliveryResolution': delivery,
        'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'correlation': correlation['results'],
        'delivery': {k: v['decision'] for k, v in delivery.items()},
        'reloadWritable': sorted(k for k, v in weapons.items() if v.get('reload', {}).get('writable')),
        'windUp': sorted(k for k, v in weapons.items() if 'windUp' in v)}, indent=2))


if __name__ == '__main__':
    main()
