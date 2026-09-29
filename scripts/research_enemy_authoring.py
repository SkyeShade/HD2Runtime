"""Enemy and enemy-structure health / damage-zone research. Offline; nothing here writes memory.

Inputs: the pinned decoded entity table and type library (build profile datalibrary), hash-verified resource paths
(filediver hashes.txt) and zone names (thinhashes.txt), and the wiki enemy / structure datasets
(HD2WikiImporter output) as value fingerprints only.

Identity is native-first. Every entity that owns a HealthComponent and has a hash-verified path under a hostile
faction (content/fac_bugs, fac_cyborgs, fac_illuminate) or a mission/objective asset (content/objectives, env_*) is
an enemy or structure *class*, named by its own path. A wiki name is attached only when the wiki's anatomy table
(main health, and every zone's health / armor / durable / damage-to-main) matches exactly one native class, that
class matches no other wiki page, and at least two damage zones carry the match. Everything else keeps its native class name and lists the wiki pages whose
anatomy it matches as candidates; nothing is named by guesswork.

Field semantics. The HealthComponent is the component the runtime already authors for vehicles and deployables
(entity.health, entity.armor and zone health / armor / damage-to-main are gameplay-proven on the Bastion and the
Shield Relay). The other members published here are identified by the hidden member-name length (the names are
filediver's reverse-engineered ones) and by exact agreement with the wiki anatomy tables across every resolved
class: constitution (and its rate), per-zone durable resistance and explosive damage percentage.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402
from migration import build_view  # noqa: E402

OUTPUT = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
WIKI_ENEMIES = ROOT.parent / 'HD2WikiImporter/output/wiki_enemies.json'
WIKI_STRUCTURES = ROOT.parent / 'HD2WikiImporter/output/wiki_structures.json'
HELPERS = ROOT.parent / 'StrongerOrbitalLaser/scripts/research'
RECORD_SIZE = 22096
ZONES, ZONE_BASE, ZONE_STRIDE, DEFAULT_ZONE = 38, 520, 552, 64
FLT_MAX = 3.4028234663852886e+38
# (offset, size, storage, hidden-name length) of the members read here; the names are filediver's.
HEALTH_FINGERPRINT = ((0, 4, 'INT32', 6),       # health
    (24, 4, 'INT32', 12),                      # constitution
    (28, 4, 'FP32', 23))                       # constitution_changerate
ZONE_FINGERPRINT = ((96, 4, 'UINT32', 9),      # zone_name
    (204, 4, 'FP32', 29),                      # projectile_durable_resistance
    (216, 4, 'UINT32', 5),                     # armor
    (232, 4, 'INT32', 6),                      # health
    (236, 4, 'INT32', 12),                     # constitution
    (243, 1, 'UINT8', 22),                     # causes_downed_on_death
    (244, 1, 'UINT8', 21),                     # causes_death_on_death
    (248, 4, 'FP32', 19),                      # affects_main_health
    (324, 4, 'FP32', 27),                      # explosive_damage_percentage
    (340, 1, 'UINT8', 40))                     # main_health_affect_capped_by_zone_health
FACTIONS = (('content/fac_bugs/', 'terminids'), ('content/obj_bugs/', 'terminids'), ('content/objectives/obj_bugs/',
    'terminids'), ('content/env_bugs/', 'terminids'), ('content/fac_cyborgs/', 'automatons'),
    ('content/objectives/obj_cyborgs/', 'automatons'), ('content/env_cyborg/', 'automatons'),
    ('content/fac_illuminate/', 'illuminate'), ('content/objectives/obj_illuminate/', 'illuminate'),
    ('content/env_illuminate/', 'illuminate'), ('content/objectives/obj_common/', 'neutral'))


def u32(raw, at): return struct.unpack_from('<I', raw, at)[0]
def i32(raw, at): return struct.unpack_from('<i', raw, at)[0]
def f32(raw, at): return round(struct.unpack_from('<f', raw, at)[0], 6)


def faction_of(path: str) -> str | None:
    return next((faction for prefix, faction in FACTIONS if path.startswith(prefix)), None)


def kind_of(path: str) -> str:
    if path.startswith('content/objectives/') or path.startswith('content/env_') or '/emplacements/' in path:
        return 'structure'
    return 'enemy'


def class_name(path: str) -> str:
    """content/fac_bugs/cha_charger/cha_charger -> charger; .../cyborg_turret_command_bunker_hmg -> the leaf."""
    leaf = path.rsplit('/', 1)[1]
    return re.sub(r'^(cha_|cyborg_|il_|cy_)', '', leaf)


def zone_values(raw: bytes, base: int, names: dict) -> dict:
    explosive = f32(raw, base + 324)
    return {'nameHash': u32(raw, base + 96), 'name': names.get(u32(raw, base + 96)),
        'health': i32(raw, base + 232), 'armor': u32(raw, base + 216), 'constitution': i32(raw, base + 236),
        'affectsMainHealth': f32(raw, base + 248), 'durableResistance': f32(raw, base + 204),
        'explosiveDamagePercentage': None if explosive >= FLT_MAX else explosive,
        'fatal': bool(raw[base + 244]), 'downsOnDeath': bool(raw[base + 243]),
        'mainHealthCapped': bool(raw[base + 340])}


def fingerprint(library, component: str) -> dict:
    outer = library.layout(component)
    record = build_view._record_layout(library, outer['members'][1]['type_hash'])
    zone_member = next(m for m in record.members if m['offset'] == DEFAULT_ZONE)
    zone = build_view._record_layout(library, zone_member['typeHash'])
    return {'record': {(m['offset'], m['size'], m['storage'], m['nameLength']) for m in record.members},
        'zone': {(m['offset'], m['size'], m['storage'], m['nameLength']) for m in zone.members}, 'size': record.size}


# -- wiki anatomy -----------------------------------------------------------------------------------------------------
def value(item):
    return None if item is None else item.get('value')


def percent(item):
    number = value(item)
    return None if number is None else round(number / 100, 4)


def wiki_zone(zone: dict) -> dict:
    return {'name': zone.get('name'), 'count': zone.get('count') or 1, 'isMain': bool(zone.get('isMain')),
        'health': -1 if zone.get('usesMainHealth') else value(zone.get('health')),
        'armor': (zone.get('armor') or {}).get('value'),
        'durable': percent(zone.get('durable')), 'toMain': percent(zone.get('damageToMain')),
        'constitution': value(zone.get('constitution')),
        'explosionReduction': value(zone.get('explosionDamageReduction'))}


def zone_agrees(native: dict, wiki: dict) -> bool:
    if wiki['health'] is not None and native['health'] != wiki['health']:
        return False
    if wiki['armor'] is not None and native['armor'] != wiki['armor']:
        return False
    if wiki['durable'] is not None and round(native['durableResistance'], 4) != wiki['durable']:
        return False
    if wiki['toMain'] is not None and round(native['affectsMainHealth'], 4) != wiki['toMain']:
        return False
    return True


def anatomy_match(native: dict, page: dict, anatomy: dict) -> dict | None:
    """Exact match: main health equals a wiki health pool (or the main zone's health) and every listed zone is a
    distinct native zone with identical health, armor, durable and damage-to-main."""
    zones = [wiki_zone(z) for z in anatomy['zones']]
    main = next((z for z in zones if z['isMain']), None)
    pools = [p['value'] for p in ((page.get('health') or {}).get('pools') or [])] if isinstance(
        page.get('health'), dict) else []
    main_value = main['health'] if main and main['health'] not in (None, -1) else None
    if value(page.get('mainHealth')) is not None:
        pools.append(value(page['mainHealth']))
    if native['main']['health'] not in pools and native['main']['health'] != main_value:
        return None
    used, pairs = set(), []
    for zone in zones:
        if zone['isMain']:
            if zone['armor'] is not None and native['default']['armor'] != zone['armor']:
                return None
            continue
        # A label identifies native zones only when exactly `count` native zones agree with the wiki zone; when more
        # agree (identical values, or values the wiki leaves unstated) which zone carries the label is unknowable.
        unambiguous = sum(1 for z in native['zones'] if zone_agrees(z, zone)) == zone['count']
        for _ in range(zone['count']):
            candidates = [z for z in native['zones'] if z['index'] not in used and zone_agrees(z, zone)]
            if not candidates:
                return None
            used.add(candidates[0]['index'])
            pairs.append({'wikiZone': zone['name'], 'zone': candidates[0]['index'], 'unambiguous': unambiguous})
    if not pairs and not main:
        return None
    return {'label': anatomy.get('label'), 'zonesMatched': len(pairs), 'pairs': pairs}


def build() -> dict:
    sys.path.insert(0, str(HELPERS))
    from probe_components import resource_hash
    fd = build_profile.FILEDIVER
    paths, names = {}, {}
    for line in (fd / 'hashes/hashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if line and not line.startswith('//'):
            paths[resource_hash(line)] = line
    for line in (fd / 'hashes/thinhashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if line:
            names.setdefault(resource_hash(line) >> 32, line)
    library = build_view.TypeLibrary((build_profile.datalibrary() / 'dl_library.dl_typelib').read_bytes())
    layout = fingerprint(library, 'HealthComponentData')
    if layout['size'] != RECORD_SIZE or set(HEALTH_FINGERPRINT) - layout['record'] \
            or set(ZONE_FINGERPRINT) - layout['zone']:
        raise ValueError('HealthComponent / DamageableZoneInfo layout fingerprint changed')
    saved = build_view.COMPONENTS
    build_view.COMPONENTS = ('HealthComponentData', 'ProjectileWeaponComponentData', 'MountComponentData')
    view = build_view.from_datalibrary(build_profile.datalibrary(), {})
    build_view.COMPONENTS = saved
    table = view.component('HealthComponentData')

    classes = []
    for resource, (record, row) in sorted(table.owners.items()):
        path = paths.get(resource)
        if not path or not faction_of(path):
            continue
        raw = table.records[record]
        zones = [dict(zone_values(raw, ZONE_BASE + index * ZONE_STRIDE, names), index=index)
            for index in range(ZONES) if u32(raw, ZONE_BASE + index * ZONE_STRIDE + 96)]
        owners = table.owners_of(record)
        classes.append({'resource': f'0x{resource:016X}', 'path': path, 'className': class_name(path),
            'faction': faction_of(path), 'kind': kind_of(path), 'entityRow': view.entity_rows[resource],
            'health': {'recordIndex': record, 'indexRow': row, 'ownerCount': len(owners),
                'uniqueOwner': len(owners) == 1,
                'coOwners': sorted(paths.get(o) or f'0x{o:016X}' for o in owners if o != resource)},
            'main': {'health': i32(raw, 0), 'constitution': i32(raw, 24), 'constitutionRate': f32(raw, 28)},
            'default': zone_values(raw, DEFAULT_ZONE, names), 'zones': zones,
            'weapons': {'projectileWeapon': view.record('ProjectileWeaponComponentData', resource) is not None,
                'mount': view.record('MountComponentData', resource) is not None}})
    # Unique class names (two paths can share a leaf).
    seen = {}
    for item in classes:
        seen.setdefault(item['className'], []).append(item)
    for name, items in seen.items():
        if len(items) > 1:
            for item in items:
                item['className'] = item['path'].split('/', 2)[2].replace('/', '.')

    pages = [(page, 'enemy') for page in json.loads(WIKI_ENEMIES.read_text(encoding='utf-8'))['enemies']]
    pages += [(page, 'structure') for page in json.loads(WIKI_STRUCTURES.read_text(encoding='utf-8'))['structures']]
    matches = {}
    for page, kind in pages:
        for item in classes:
            for anatomy in page.get('anatomy') or []:
                found = anatomy_match(item, page, anatomy)
                if found:
                    matches.setdefault(page['name'], []).append({'class': item['className'], **found})
                    break
    by_class = {}
    for page, found in matches.items():
        for hit in found:
            by_class.setdefault(hit['class'], []).append(page)
    kinds = {page['name']: kind for page, kind in pages}
    for item in classes:
        candidates = sorted(set(by_class.get(item['className'], [])))
        item['wikiCandidates'] = candidates
        # How strong each candidate is: zonesMatched 0 means only the main health (and armor) number agrees.
        item['wikiCandidateEvidence'] = [{'page': page, 'zonesMatched': next(h for h in matches[page]
            if h['class'] == item['className'])['zonesMatched'], 'kindAgrees': kinds[page] == item['kind'],
            'nativeClassesMatchingPage': len({h['class'] for h in matches[page]})} for page in candidates]
        # A wiki name needs a one-to-one match carried by at least two exactly matching damage zones; a main-health
        # number alone is a candidate, never a name.
        named = [page for page in candidates if len({h['class'] for h in matches[page]}) == 1
            and next(h for h in matches[page] if h['class'] == item['className'])['zonesMatched'] >= 2]
        item['wikiName'] = named[0] if len(candidates) == 1 and len(named) == 1 else None
        if item['wikiName']:
            hit = next(h for h in matches[item['wikiName']] if h['class'] == item['className'])
            item['wikiEvidence'] = {'page': item['wikiName'], 'kind': kinds[item['wikiName']],
                'anatomyLabel': hit['label'], 'zonesMatched': hit['zonesMatched'], 'zonePairs': hit['pairs']}
            item['kind'] = kinds[item['wikiName']]
    unresolved_pages = sorted({page['name'] for page, _ in pages} - {c['wikiName'] for c in classes if c['wikiName']})
    return {'schemaVersion': 1,
        'source': {'datalibrary': 'build profile ' + build_profile.BUILD_ID, 'entitiesSha256': build_profile.ENTITY_SHA256,
            'typelibSha256': build_profile.TYPELIB_SHA256, 'wiki': [WIKI_ENEMIES.name, WIKI_STRUCTURES.name],
            'writes': 0, 'fixtureFallback': 'disabled'},
        'layout': {'recordSize': RECORD_SIZE, 'zoneBase': ZONE_BASE, 'zoneStride': ZONE_STRIDE, 'zoneSlots': ZONES,
            'defaultZone': DEFAULT_ZONE},
        'summary': {'classes': len(classes), 'enemies': sum(c['kind'] == 'enemy' for c in classes),
            'structures': sum(c['kind'] == 'structure' for c in classes),
            'wikiNamed': sum(1 for c in classes if c['wikiName']),
            'withWikiCandidates': sum(1 for c in classes if c['wikiCandidates'] and not c['wikiName']),
            'sharedHealthRecords': sum(1 for c in classes if not c['health']['uniqueOwner']),
            'wikiPages': len(pages), 'wikiPagesNamed': len(pages) - len(unresolved_pages)},
        'unresolvedWikiPages': [{'page': name, 'kind': kinds[name],
            'exactNativeMatches': sorted({h['class'] for h in matches.get(name, [])})} for name in unresolved_pages],
        'classes': classes}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
